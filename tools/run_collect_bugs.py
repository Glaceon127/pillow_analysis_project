"""Collect bug issues from GitHub for Pillow.

Usage (cmd.exe):
  python tools\run_collect_bugs.py
  python tools\run_collect_bugs.py --since 2020-01-01
  python tools\run_collect_bugs.py --repo python-pillow/Pillow --max-items 5000

Output:
  data/processed/pillow_bug_issues.json
"""

from __future__ import annotations

import argparse
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config import settings
from src.data_pipeline.issue_collector import IssueCollector


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Collect bug issues from GitHub (label=bug).')
    parser.add_argument('--repo', default=None, help='GitHub repo "owner/repo". If omitted, uses config.settings.GITHUB_REPO')
    parser.add_argument('--label', default='bug')
    parser.add_argument('--since', default=None, help='Stop when created_at < since (YYYY-MM-DD)')
    parser.add_argument('--max-items', type=int, default=None)

    base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    default_out = os.path.join(base, 'data', 'processed', 'pillow_bug_issues.json')
    parser.add_argument('--out-json', default=default_out)

    args = parser.parse_args(argv)

    repo = (args.repo or '').strip() or (getattr(settings, 'GITHUB_REPO', '') or '').strip()
    if not repo:
        print('[run_collect_bugs][ERROR] missing GitHub repo.')
        print('Set GITHUB_REPO in config/local_settings.py, e.g. GITHUB_REPO="python-pillow/Pillow"')
        return 1

    collector = IssueCollector(github_repo=repo)
    try:
        items = collector.collect_bug_issues(
            repo=repo,
            label=args.label,
            since=args.since,
            max_items=args.max_items,
            save_path=args.out_json,
            verbose=True,
        )
    except Exception as e:
        print('[run_collect_bugs][ERROR] failed:', e)
        return 2

    print('[run_collect_bugs] repo:', repo)
    print('[run_collect_bugs] label:', args.label)
    print('[run_collect_bugs] issues:', len(items))
    print('[run_collect_bugs] saved:', args.out_json)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
