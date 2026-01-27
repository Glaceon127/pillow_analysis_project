"""Bug 关闭规律分析模块（基于 GitHub issues 数据）。

输入：issues 列表（data/processed/pillow_bug_issues.json）。
输出：用于可视化/报告的统计信息（纯 dict，可 JSON 化）。

核心指标：
- created_by_month / closed_by_month
- backlog_by_month（累计 created - 累计 closed）
- time_to_close_days（中位数、P90、平均数、样本量）
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd


class IssueAnalyzer:
    def analyze(self, issues: List[Dict[str, Any]]) -> Dict[str, Any]:
        issues = issues or []
        if not issues:
            return {
                'total_issues': 0,
                'open_issues': 0,
                'closed_issues': 0,
                'created_by_month': [],
                'closed_by_month': [],
                'backlog_by_month': [],
                'time_to_close_days_stats': {
                    'n': 0,
                    'median': None,
                    'p90': None,
                    'mean': None,
                },
            }

        df = pd.DataFrame(issues)
        df['created_dt'] = pd.to_datetime(df.get('created_at'), errors='coerce', utc=True)
        df['closed_dt'] = pd.to_datetime(df.get('closed_at'), errors='coerce', utc=True)
        df['state'] = df.get('state', '').fillna('').astype(str)

        total = int(len(df))
        open_issues = int((df['state'] == 'open').sum())
        closed_issues = int((df['state'] == 'closed').sum())

        created_by_month = []
        closed_by_month = []
        backlog_by_month = []

        if df['created_dt'].notna().any():
            c = df.dropna(subset=['created_dt']).copy()
            c['month'] = c['created_dt'].dt.to_period('M').astype(str)
            created = c.groupby('month').size().reset_index(name='count').sort_values('month')
            created_by_month = created.to_dict(orient='records')

        if df['closed_dt'].notna().any():
            d = df.dropna(subset=['closed_dt']).copy()
            d['month'] = d['closed_dt'].dt.to_period('M').astype(str)
            closed = d.groupby('month').size().reset_index(name='count').sort_values('month')
            closed_by_month = closed.to_dict(orient='records')

        # backlog by month: cumulative created - cumulative closed
        if created_by_month:
            created_series = pd.DataFrame(created_by_month).set_index('month')['count']
            closed_series = pd.Series(dtype='int64')
            if closed_by_month:
                closed_series = pd.DataFrame(closed_by_month).set_index('month')['count']

            # align months
            all_months = sorted(set(created_series.index.tolist()) | set(closed_series.index.tolist()))
            created_aligned = created_series.reindex(all_months, fill_value=0).cumsum()
            closed_aligned = closed_series.reindex(all_months, fill_value=0).cumsum()
            backlog = (created_aligned - closed_aligned).astype(int)
            backlog_by_month = [{'month': m, 'count': int(backlog.loc[m])} for m in all_months]

        # time to close stats
        ttl = df.dropna(subset=['created_dt', 'closed_dt']).copy()
        ttl['ttc_days'] = (ttl['closed_dt'] - ttl['created_dt']).dt.total_seconds() / 86400.0
        ttl = ttl[ttl['ttc_days'].notna()]

        stats = {
            'n': int(len(ttl)),
            'median': float(ttl['ttc_days'].median()) if len(ttl) else None,
            'p90': float(ttl['ttc_days'].quantile(0.9)) if len(ttl) else None,
            'mean': float(ttl['ttc_days'].mean()) if len(ttl) else None,
        }

        return {
            'total_issues': total,
            'open_issues': open_issues,
            'closed_issues': closed_issues,
            'created_by_month': created_by_month,
            'closed_by_month': closed_by_month,
            'backlog_by_month': backlog_by_month,
            'time_to_close_days_stats': stats,
        }
