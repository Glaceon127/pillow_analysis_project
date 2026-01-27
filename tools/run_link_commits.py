"""Link collected CVE records to git commits using "git log + CVE id" matching.

What it does:
- Loads CVE JSON (default: data/processed/pillow_cves.json)
- Crawls a local git repo's commit history
- Associates CVEs to commits when commit subject contains the CVE id (exact rule)
- Writes enriched JSON + CSV

Usage (cmd.exe):
  python tools\run_link_commits.py --repo "F:\\path\\to\\Pillow"

Optional:
  python tools\run_link_commits.py --repo "..." --since "2020-01-01" --max-commits 5000
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any, Dict, List, Tuple

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.data_pipeline.git_crawler import GitCrawler
from src.data_pipeline.data_cleaner import DataCleaner
from config import settings


_COMMIT_SHA_RE = re.compile(r'(?i)(?:/commit/|/-/commit/)([0-9a-f]{7,40})')
_PR_RE = re.compile(r'(?i)(?:/pull/|/pulls/)(\d+)')


def _extract_strong_signals(refs: List[Any]) -> Tuple[List[str], List[int], List[str]]:
    """Return (commit_shas, pr_numbers, normalized_urls) extracted from references."""
    urls: List[str] = []
    for r in refs or []:
        if isinstance(r, str) and r.strip():
            urls.append(r.strip())
        elif isinstance(r, dict) and r.get('url'):
            urls.append(str(r.get('url')).strip())

    commit_shas: List[str] = []
    pr_numbers: List[int] = []
    for u in urls:
        for m in _COMMIT_SHA_RE.findall(u):
            commit_shas.append(m.lower())
        for m in _PR_RE.findall(u):
            try:
                pr_numbers.append(int(m))
            except Exception:
                pass

    # de-dupe
    commit_shas = list(dict.fromkeys(commit_shas))
    pr_numbers = list(dict.fromkeys(pr_numbers))
    urls = list(dict.fromkeys(urls))
    return commit_shas, pr_numbers, urls


def _load_json(path: str) -> List[Dict[str, Any]]:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_json(path: str, data: List[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description='Link CVE records to git commits via commit subject containing CVE id.')
    parser.add_argument('--repo', required=False, default=None, help='Local git repository path (must be a git repo). If omitted, uses config.settings.PILLOW_REPO_PATH')

    default_cve_json = os.path.join(PROJECT_ROOT, 'data', 'processed', 'pillow_cves.json')
    default_commits_json = os.path.join(PROJECT_ROOT, 'data', 'processed', 'pillow_commits.json')
    default_out_json = os.path.join(PROJECT_ROOT, 'data', 'processed', 'pillow_cves_with_commits.json')

    parser.add_argument('--cve-json', default=default_cve_json, help=f'CVE JSON path (default: {default_cve_json})')
    parser.add_argument('--commits-json', default=default_commits_json, help=f'Commits JSON output (default: {default_commits_json})')
    parser.add_argument('--out-json', default=default_out_json, help=f'Output JSON path (default: {default_out_json})')

    parser.add_argument('--since', default=None, help='git log --since (e.g. "2020-01-01" or "2 years ago")')
    parser.add_argument('--until', default=None, help='git log --until')
    parser.add_argument('--max-commits', type=int, default=None, help='Maximum commits to crawl')
    parser.add_argument('--grep', default='CVE', help='git log --grep filter for initial crawl (default: CVE). Use "" for no filter.')
    parser.add_argument('--max-pr-hits', type=int, default=20, help='Max commits to return per PR grep search (default: 20)')

    args = parser.parse_args(argv)

    repo_path = (args.repo or '').strip() or (getattr(settings, 'PILLOW_REPO_PATH', '') or '').strip()
    if not repo_path:
        print('[run_link_commits][ERROR] missing repo path.')
        print('Provide --repo "F:\\path\\to\\Pillow" or set PILLOW_REPO_PATH in env/config/local_settings.py')
        return 1

    cves = _load_json(args.cve_json)
    if not cves:
        print(f'[run_link_commits][ERROR] no CVEs loaded from: {args.cve_json}')
        print('Tip: run collection first: python tools\\run_collect.py')
        return 2

    crawler = GitCrawler()
    try:
        commits = crawler.crawl(
            repo_path=repo_path,
            since=args.since,
            until=args.until,
            max_commits=args.max_commits,
            save_path=args.commits_json,
            grep=(args.grep if args.grep != '' else None),
        )
    except Exception as e:
        print('[run_link_commits][ERROR] failed to crawl git history:', e)
        return 3

    cleaner = DataCleaner()
    cleaned = cleaner.clean_cves(cves)

    # A) Strict match: commit subject contains CVE id
    linked = cleaner.associate_with_commits(cleaned, commits)

    # Record match type for strict matches
    strict_matched = 0
    for item in linked:
        item.setdefault('match_types', [])
        if item.get('matched'):
            item['match_types'] = sorted(set(item.get('match_types') or []) | {'cve_in_subject'})
            strict_matched += 1

    # B/C) Strong signals for remaining CVEs:
    #   - commit URL (contains a commit sha) -> verify sha exists locally
    #   - PR URL -> search merge commit message via git log --grep
    strong_matched = 0
    for item in linked:
        if item.get('matched'):
            continue

        refs = item.get('references') or []
        commit_shas, pr_numbers, ref_urls = _extract_strong_signals(refs)
        evidence: Dict[str, Any] = item.get('evidence') or {}
        evidence_urls: List[str] = list(dict.fromkeys((evidence.get('urls') or []) + ref_urls))
        evidence['urls'] = evidence_urls

        matched_hashes: List[str] = list(item.get('matched_commits') or [])
        match_types = set(item.get('match_types') or [])

        # B) commit sha in references
        valid_shas: List[str] = []
        for sha in commit_shas:
            if crawler.commit_exists(repo_path, sha):
                valid_shas.append(sha)
                matched_hashes.append(sha)

        if valid_shas:
            match_types.add('commit_reference')
            evidence['commit_shas'] = valid_shas

        # C) PR in references -> search merge commits locally
        pr_hits: Dict[str, List[str]] = {}
        for pr in pr_numbers:
            # Try a few common patterns
            patterns = [
                f'Merge pull request #{pr}',
                f'pull request #{pr}',
                f'PR #{pr}',
                f'#{pr}',
            ]
            hits: List[str] = []
            for p in patterns:
                hits.extend(crawler.grep_commits(repo_path, p, max_hits=args.max_pr_hits))
                if hits:
                    # stop early on first successful pattern to reduce noise
                    break
            if hits:
                pr_hits[str(pr)] = list(dict.fromkeys(hits))
                matched_hashes.extend(pr_hits[str(pr)])

        if pr_hits:
            match_types.add('pr_reference')
            evidence['pr_hits'] = pr_hits

        matched_hashes = list(dict.fromkeys(matched_hashes))
        item['matched_commits'] = matched_hashes
        item['matched_commits_count'] = len(matched_hashes)
        item['match_types'] = sorted(match_types)
        item['evidence'] = evidence
        item['matched'] = bool(matched_hashes)

        if item['matched']:
            strong_matched += 1

    _save_json(args.out_json, linked)
    # also save csv next to json
    csv_path = os.path.splitext(args.out_json)[0] + '.csv'
    cleaner.save_csv(linked, csv_path)

    total = len(linked)
    with_id = sum(1 for x in linked if x.get('id'))
    matched = sum(1 for x in linked if x.get('matched'))

    print('[run_link_commits] CVE input:', args.cve_json)
    print('[run_link_commits] repo:', repo_path)
    print('[run_link_commits] commits crawled:', len(commits), f'(saved to {args.commits_json})')
    print('[run_link_commits] CVEs:', total, 'with_cve_id:', with_id, 'matched:', matched, f'(strict={strict_matched} strong={strong_matched})')
    print('[run_link_commits] output:', args.out_json)
    print('[run_link_commits] csv:', csv_path)

    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
