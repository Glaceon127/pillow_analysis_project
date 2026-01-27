"""生成各种图表模块。

输入：analysis_results（dict）。
输出：charts 路径映射（dict）。
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

import matplotlib.pyplot as plt


class PlotGenerator:
    def generate(self, analysis_results: Dict[str, Any], out_dir: str) -> Dict[str, str]:
        os.makedirs(out_dir, exist_ok=True)
        charts: Dict[str, str] = {}

        def _thin_month_ticks(month_labels: List[str], max_ticks: int = 24):
            """Set thinned x ticks for dense month labels.

            Returns: (xs, tick_positions, tick_labels)
            """
            month_labels = [str(m) for m in (month_labels or [])]
            n = len(month_labels)
            xs = list(range(n))
            if n == 0:
                return xs, [], []
            if n <= max_ticks:
                positions = xs
            else:
                step = max(1, n // max_ticks)
                positions = list(range(0, n, step))
                if positions[-1] != n - 1:
                    positions.append(n - 1)
            labels = [month_labels[i] for i in positions]
            return xs, positions, labels

        commit = (analysis_results or {}).get('commit') or {}
        issues = (analysis_results or {}).get('issues') or {}
        vuln = (analysis_results or {}).get('vulnerability') or {}

        # 0) Commits by month (evolution pace)
        commits_by_month: List[Dict[str, Any]] = commit.get('commits_by_month') or []
        if commits_by_month:
            months = [x.get('month') for x in commits_by_month]
            counts = [x.get('count', 0) for x in commits_by_month]
            plt.figure(figsize=(10, 4))
            xs, tick_pos, tick_labels = _thin_month_ticks(months, max_ticks=24)
            plt.plot(xs, counts, marker='o', linewidth=1)
            plt.xticks(tick_pos, tick_labels, rotation=45, ha='right')
            plt.title('Commits over time (by month)')
            plt.tight_layout()
            path = os.path.join(out_dir, 'commits_by_month.png')
            plt.savefig(path, dpi=150)
            plt.close()
            charts['commits_by_month'] = path

        # 0b) Fix ratio by month (2.1)
        fix_by_month: List[Dict[str, Any]] = commit.get('fix_commits_by_month') or []
        if fix_by_month:
            months = [x.get('month') for x in fix_by_month]
            ratios = [float(x.get('ratio', 0.0)) * 100.0 for x in fix_by_month]
            plt.figure(figsize=(10, 4))
            xs, tick_pos, tick_labels = _thin_month_ticks(months, max_ticks=24)
            plt.plot(xs, ratios, marker='o', linewidth=1)
            plt.xticks(tick_pos, tick_labels, rotation=45, ha='right')
            plt.ylim(0, 100)
            plt.title('Fix-commit ratio over time (by month, %)')
            plt.tight_layout()
            path = os.path.join(out_dir, 'fix_ratio_by_month.png')
            plt.savefig(path, dpi=150)
            plt.close()
            charts['fix_ratio_by_month'] = path

        # 0c) Change size by month (2.2)
        change_by_month: List[Dict[str, Any]] = commit.get('change_size_by_month') or []
        if change_by_month:
            months = [x.get('month') for x in change_by_month]
            mean_sizes = [float(x.get('change_size_mean', 0.0)) for x in change_by_month]
            p90_sizes = [float(x.get('change_size_p90', 0.0)) for x in change_by_month]
            plt.figure(figsize=(10, 4))
            xs, tick_pos, tick_labels = _thin_month_ticks(months, max_ticks=24)
            plt.plot(xs, mean_sizes, marker='o', linewidth=1, label='mean')
            plt.plot(xs, p90_sizes, marker='o', linewidth=1, label='p90')
            plt.xticks(tick_pos, tick_labels, rotation=45, ha='right')
            plt.title('Change size over time (insertions+deletions per commit)')
            plt.legend()
            plt.tight_layout()
            path = os.path.join(out_dir, 'change_size_by_month.png')
            plt.savefig(path, dpi=150)
            plt.close()
            charts['change_size_by_month'] = path

        # A) Bug issues: created vs closed by month
        created_by_month: List[Dict[str, Any]] = issues.get('created_by_month') or []
        closed_by_month: List[Dict[str, Any]] = issues.get('closed_by_month') or []
        if created_by_month or closed_by_month:
            # union months
            months = sorted(set([x.get('month') for x in created_by_month]) | set([x.get('month') for x in closed_by_month]))
            created_map = {x.get('month'): x.get('count', 0) for x in created_by_month}
            closed_map = {x.get('month'): x.get('count', 0) for x in closed_by_month}
            created_counts = [created_map.get(m, 0) for m in months]
            closed_counts = [closed_map.get(m, 0) for m in months]
            plt.figure(figsize=(10, 4))
            xs, tick_pos, tick_labels = _thin_month_ticks(months, max_ticks=24)
            plt.plot(xs, created_counts, marker='o', linewidth=1, label='created')
            plt.plot(xs, closed_counts, marker='o', linewidth=1, label='closed')
            plt.xticks(tick_pos, tick_labels, rotation=45, ha='right')
            plt.title('Bug issues: created vs closed (by month)')
            plt.legend()
            plt.tight_layout()
            path = os.path.join(out_dir, 'bugs_created_vs_closed_by_month.png')
            plt.savefig(path, dpi=150)
            plt.close()
            charts['bugs_created_vs_closed_by_month'] = path

        # B) Bug backlog over time
        backlog_by_month: List[Dict[str, Any]] = issues.get('backlog_by_month') or []
        if backlog_by_month:
            months = [x.get('month') for x in backlog_by_month]
            counts = [x.get('count', 0) for x in backlog_by_month]
            plt.figure(figsize=(10, 4))
            xs, tick_pos, tick_labels = _thin_month_ticks(months, max_ticks=24)
            plt.plot(xs, counts, marker='o', linewidth=1)
            plt.xticks(tick_pos, tick_labels, rotation=45, ha='right')
            plt.title('Bug backlog over time (open = cumulative created - cumulative closed)')
            plt.tight_layout()
            path = os.path.join(out_dir, 'bug_backlog_by_month.png')
            plt.savefig(path, dpi=150)
            plt.close()
            charts['bug_backlog_by_month'] = path

        # 1) CVEs by month
        cves_by_month: List[Dict[str, Any]] = vuln.get('cves_by_month') or []
        if cves_by_month:
            months = [x.get('month') for x in cves_by_month]
            counts = [x.get('count', 0) for x in cves_by_month]
            plt.figure(figsize=(10, 4))
            xs, tick_pos, tick_labels = _thin_month_ticks(months, max_ticks=24)
            plt.plot(xs, counts, marker='o', linewidth=1)
            plt.xticks(tick_pos, tick_labels, rotation=45, ha='right')
            plt.title('CVEs over time (by month)')
            plt.tight_layout()
            path = os.path.join(out_dir, 'cves_by_month.png')
            plt.savefig(path, dpi=150)
            plt.close()
            charts['cves_by_month'] = path

        # 2) Matched vs unmatched
        total = vuln.get('total_cves') or 0
        matched = vuln.get('matched_cves') or 0
        if total:
            plt.figure(figsize=(4, 4))
            plt.bar(['matched', 'unmatched'], [matched, max(total - matched, 0)])
            plt.title('Matched vs Unmatched CVEs')
            plt.tight_layout()
            path = os.path.join(out_dir, 'matched_vs_unmatched.png')
            plt.savefig(path, dpi=150)
            plt.close()
            charts['matched_vs_unmatched'] = path

        # 3) Match types distribution
        mt = vuln.get('match_types_top') or []
        if mt:
            labels = [x.get('type') for x in mt]
            values = [x.get('count', 0) for x in mt]
            plt.figure(figsize=(8, 4))
            plt.bar(labels, values)
            plt.xticks(rotation=30, ha='right')
            plt.title('Match types (top)')
            plt.tight_layout()
            path = os.path.join(out_dir, 'match_types.png')
            plt.savefig(path, dpi=150)
            plt.close()
            charts['match_types'] = path

        return charts
