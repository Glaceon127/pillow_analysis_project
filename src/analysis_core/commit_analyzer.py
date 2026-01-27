"""提交分析模块。

输入：git_crawler 产出的 commits 列表（data/processed/pillow_commits.json）。
输出：用于可视化/报告的统计信息（纯 dict，可 JSON 化）。
"""

from __future__ import annotations

from collections import Counter
import re
from typing import Any, Dict, List

import pandas as pd


class CommitAnalyzer:
    def analyze(self, commits: List[Dict[str, Any]]) -> Dict[str, Any]:
        commits = commits or []
        if not commits:
            return {
                'total_commits': 0,
                'date_min': None,
                'date_max': None,
                'authors_top': [],
                'files_top': [],
                'commits_by_month': [],
                'fix_commits_total': 0,
                'fix_commit_ratio': 0.0,
                'fix_commits_by_month': [],
                'change_size_stats': {
                    'files_changed_total': 0,
                    'insertions_total': 0,
                    'deletions_total': 0,
                    'change_size_total': 0,
                    'change_size_mean': 0.0,
                    'change_size_median': 0.0,
                    'change_size_p90': 0.0,
                },
                'change_size_by_month': [],
            }

        df = pd.DataFrame(commits)
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'], errors='coerce', utc=True)

        # normalize numeric stats (2.2 change size)
        for col in ['files_changed', 'insertions', 'deletions']:
            if col not in df.columns:
                df[col] = 0
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
        df['change_size'] = (df['insertions'] + df['deletions']).astype(int)

        # classify fix commits (2.1 fix ratio)
        subject = df.get('subject')
        if subject is None:
            df['is_fix'] = False
        else:
            s = subject.fillna('').astype(str)
            fix_re = re.compile(
                r"(\bcve-\d{4}-\d+\b|\bsecurity\b|\bfix(?:e[ds])?\b|\bbug(?:s)?\b|\bdefect(?:s)?\b|\bregress(?:ion|ed)?\b|\bcrash(?:es|ed)?\b|\bhot\s*fix\b|\bpatch\b|\bresolve[sd]?\b|\bcloses?\b)",
                re.IGNORECASE,
            )
            df['is_fix'] = s.map(lambda x: bool(fix_re.search(x)))

        total_commits = int(len(df))
        date_min = df['date'].min() if 'date' in df.columns else None
        date_max = df['date'].max() if 'date' in df.columns else None

        fix_commits_total = int(df['is_fix'].sum()) if 'is_fix' in df.columns else 0
        fix_commit_ratio = float(fix_commits_total / total_commits) if total_commits else 0.0

        # top authors
        authors_top = []
        if 'author_name' in df.columns:
            c = df['author_name'].fillna('').astype(str)
            c = c[c != '']
            authors_top = [{'author': a, 'count': int(n)} for a, n in c.value_counts().head(10).items()]

        # top files
        files_counter: Counter[str] = Counter()
        for files in df.get('files', []):
            if isinstance(files, list):
                files_counter.update([f for f in files if isinstance(f, str) and f])
        files_top = [{'file': f, 'count': int(n)} for f, n in files_counter.most_common(15)]

        # commits by month
        commits_by_month = []
        fix_commits_by_month = []
        change_size_by_month = []
        if 'date' in df.columns and df['date'].notna().any():
            g = df.dropna(subset=['date']).copy()
            g['month'] = g['date'].dt.to_period('M').astype(str)
            bym = g.groupby('month').size().reset_index(name='count').sort_values('month')
            commits_by_month = bym.to_dict(orient='records')

            # fix ratio by month
            fm = g.groupby('month').agg(
                total_count=('hash', 'size'),
                fix_count=('is_fix', 'sum'),
            ).reset_index()
            fm['ratio'] = fm.apply(
                lambda r: float(r['fix_count'] / r['total_count']) if int(r['total_count']) else 0.0,
                axis=1,
            )
            fm = fm.sort_values('month')
            fix_commits_by_month = [
                {
                    'month': row['month'],
                    'total_count': int(row['total_count']),
                    'fix_count': int(row['fix_count']),
                    'ratio': float(row['ratio']),
                }
                for _, row in fm.iterrows()
            ]

            # change size by month
            cm = g.groupby('month').agg(
                commits=('hash', 'size'),
                files_changed=('files_changed', 'sum'),
                insertions=('insertions', 'sum'),
                deletions=('deletions', 'sum'),
                change_size_mean=('change_size', 'mean'),
                change_size_median=('change_size', 'median'),
                change_size_p90=('change_size', lambda x: float(x.quantile(0.9)) if len(x) else 0.0),
            ).reset_index().sort_values('month')
            change_size_by_month = [
                {
                    'month': row['month'],
                    'commits': int(row['commits']),
                    'files_changed': int(row['files_changed']),
                    'insertions': int(row['insertions']),
                    'deletions': int(row['deletions']),
                    'change_size_mean': float(row['change_size_mean']) if row['change_size_mean'] == row['change_size_mean'] else 0.0,
                    'change_size_median': float(row['change_size_median']) if row['change_size_median'] == row['change_size_median'] else 0.0,
                    'change_size_p90': float(row['change_size_p90']) if row['change_size_p90'] == row['change_size_p90'] else 0.0,
                }
                for _, row in cm.iterrows()
            ]

        change_size_stats = {
            'files_changed_total': int(df['files_changed'].sum()),
            'insertions_total': int(df['insertions'].sum()),
            'deletions_total': int(df['deletions'].sum()),
            'change_size_total': int(df['change_size'].sum()),
            'change_size_mean': float(df['change_size'].mean()) if total_commits else 0.0,
            'change_size_median': float(df['change_size'].median()) if total_commits else 0.0,
            'change_size_p90': float(df['change_size'].quantile(0.9)) if total_commits else 0.0,
        }

        return {
            'total_commits': total_commits,
            'date_min': date_min.isoformat() if getattr(date_min, 'isoformat', None) else None,
            'date_max': date_max.isoformat() if getattr(date_max, 'isoformat', None) else None,
            'authors_top': authors_top,
            'files_top': files_top,
            'commits_by_month': commits_by_month,
            'fix_commits_total': fix_commits_total,
            'fix_commit_ratio': fix_commit_ratio,
            'fix_commits_by_month': fix_commits_by_month,
            'change_size_stats': change_size_stats,
            'change_size_by_month': change_size_by_month,
        }
