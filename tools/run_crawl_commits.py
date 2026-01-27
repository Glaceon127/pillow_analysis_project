"""Crawl full commit history for the configured Pillow repo.

This is for evolution pace analysis (NOT limited to CVE commits).

Usage (cmd.exe):
  python tools\run_crawl_commits.py
  python tools\run_crawl_commits.py --repo "F:\\path\\to\\Pillow" --since "2018-01-01" --max-commits 20000

Output:
  data/processed/pillow_commits_all.json
"""

from __future__ import annotations

import argparse
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config import settings
from src.data_pipeline.git_crawler import GitCrawler


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Crawl full git commit history (no grep filter).')
    parser.add_argument('--repo', default=None, help='Local git repo path. If omitted, uses config.settings.PILLOW_REPO_PATH')
    parser.add_argument('--since', default=None)
    parser.add_argument('--until', default=None)
    parser.add_argument('--max-commits', type=int, default=None)
    parser.add_argument('--no-merges', action='store_true', help='Exclude merge commits (recommended for change-size stats).')
    parser.add_argument('--first-parent', action='store_true', help='Follow first-parent history only (recommended for mainline evolution).')

    base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    default_out = os.path.join(base, 'data', 'processed', 'pillow_commits_all.json')
    parser.add_argument('--out-json', default=default_out)

    args = parser.parse_args(argv)

    repo_path = (args.repo or '').strip() or (getattr(settings, 'PILLOW_REPO_PATH', '') or '').strip()
    if not repo_path:
        print('[run_crawl_commits][ERROR] missing repo path.')
        print('Provide --repo "F:\\path\\to\\Pillow" or set PILLOW_REPO_PATH in config/local_settings.py')
        return 1

    crawler = GitCrawler()
    try:
        commits = crawler.crawl(
            repo_path=repo_path,
            since=args.since,
            until=args.until,
            max_commits=args.max_commits,
            save_path=args.out_json,
            grep=None,
            no_merges=bool(args.no_merges),
            first_parent=bool(args.first_parent),
        )
    except Exception as e:
        print('[run_crawl_commits][ERROR] failed:', e)
        return 2

    print('[run_crawl_commits] repo:', repo_path)
    print('[run_crawl_commits] commits:', len(commits))
    print('[run_crawl_commits] saved:', args.out_json)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
