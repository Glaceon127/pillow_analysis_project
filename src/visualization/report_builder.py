"""生成 Markdown/HTML 报告模块（先实现 Markdown）。"""

from __future__ import annotations

import os
from typing import Any, Dict


class ReportBuilder:
    def build(self, analysis_results: Dict[str, Any], charts: Dict[str, str], out_path: str) -> str:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)

        commit = (analysis_results or {}).get('commit') or {}
        issues = (analysis_results or {}).get('issues') or {}
        vuln = (analysis_results or {}).get('vulnerability') or {}

        def rel(p: str) -> str:
            # make chart paths relative to report file for Markdown
            try:
                return os.path.relpath(p, os.path.dirname(out_path)).replace('\\', '/')
            except Exception:
                return p

        lines = []
        lines.append('# Pillow Analysis Report')
        lines.append('')
        lines.append('## Summary')
        lines.append(f"- Total commits: {commit.get('total_commits', 0)}")
        lines.append(f"- Bug issues (total/open/closed): {issues.get('total_issues', 0)}/{issues.get('open_issues', 0)}/{issues.get('closed_issues', 0)}")
        if vuln:
            lines.append(f"- Total CVEs: {vuln.get('total_cves', 0)}")
            lines.append(f"- CVEs with CVE-ID: {vuln.get('with_cve_id', 0)}")
            lines.append(f"- Matched CVEs (linked to commits): {vuln.get('matched_cves', 0)}")
        lines.append('')

        lines.append('## Evolution Pace (Commits)')
        # 2.1 Fix ratio summary
        lines.append(f"- Fix commits: {commit.get('fix_commits_total', 0)} ({commit.get('fix_commit_ratio', 0.0) * 100.0:.2f}% of commits)")
        # 2.2 Change size summary
        cs = commit.get('change_size_stats') or {}
        if cs:
            lines.append(
                "- Change size (insertions+deletions per commit): "
                f"mean={float(cs.get('change_size_mean', 0.0)):.2f}, "
                f"median={float(cs.get('change_size_median', 0.0)):.2f}, "
                f"p90={float(cs.get('change_size_p90', 0.0)):.2f}"
            )
        if 'commits_by_month' in charts:
            lines.append(f"![commits_by_month]({rel(charts['commits_by_month'])})")
            lines.append('')
        if 'fix_ratio_by_month' in charts:
            lines.append(f"![fix_ratio_by_month]({rel(charts['fix_ratio_by_month'])})")
            lines.append('')
        if 'change_size_by_month' in charts:
            lines.append(f"![change_size_by_month]({rel(charts['change_size_by_month'])})")
            lines.append('')
        lines.append('')

        lines.append('## Bug Closing Dynamics')
        ttc = issues.get('time_to_close_days_stats') or {}
        if ttc.get('n'):
            lines.append(f"- Time-to-close (days) n={ttc.get('n')}, median={ttc.get('median'):.2f}, p90={ttc.get('p90'):.2f}, mean={ttc.get('mean'):.2f}")
        if 'bugs_created_vs_closed_by_month' in charts:
            lines.append(f"![bugs_created_vs_closed_by_month]({rel(charts['bugs_created_vs_closed_by_month'])})")
            lines.append('')
        if 'bug_backlog_by_month' in charts:
            lines.append(f"![bug_backlog_by_month]({rel(charts['bug_backlog_by_month'])})")
            lines.append('')
        lines.append('')

        # AST分析结果部分（危险模式识别 + 趋势统计）
        ast_summary = commit.get('ast_analysis_summary', {})
        if ast_summary and ast_summary.get('enabled', False):
            lines.append('## AST Dangerous Pattern Analysis')
            if ast_summary.get('message'):
                lines.append(f"- Note: {ast_summary.get('message')}")
            lines.append(f"- Local repo: {ast_summary.get('repo_path', '')}")
            lines.append(f"- Analyzed commits (cap applied): {ast_summary.get('analyzed_commits', 0)}")
            lines.append(f"- Analyzed python files: {ast_summary.get('analyzed_files', 0)}")
            lines.append(f"- Commits with patterns: {ast_summary.get('commits_with_patterns', 0)}")
            lines.append(f"- Total pattern hits: {ast_summary.get('patterns_total', 0)}")

            top_patterns = ast_summary.get('top_patterns', [])
            if top_patterns:
                lines.append('### Top Dangerous Patterns (overall)')
                for pattern in top_patterns:
                    lines.append(f"- {pattern.get('pattern', 'Unknown')}: {pattern.get('count', 0)}")
            lines.append('')

            if 'ast_patterns_by_month' in charts:
                lines.append(f"![ast_patterns_by_month]({rel(charts['ast_patterns_by_month'])})")
                lines.append('')
            if 'ast_top_patterns' in charts:
                lines.append(f"![ast_top_patterns]({rel(charts['ast_top_patterns'])})")
                lines.append('')

        if vuln:
            lines.append('## Vulnerability Linking (Optional)')
            lines.append('### Match Types')
            for x in (vuln.get('match_types_top') or []):
                lines.append(f"- {x.get('type')}: {x.get('count')}")
            lines.append('')

        lines.append('## Charts')
        if 'commits_by_month' in charts:
            lines.append(f"![commits_by_month]({rel(charts['commits_by_month'])})")
            lines.append('')
        if 'fix_ratio_by_month' in charts:
            lines.append(f"![fix_ratio_by_month]({rel(charts['fix_ratio_by_month'])})")
            lines.append('')
        if 'change_size_by_month' in charts:
            lines.append(f"![change_size_by_month]({rel(charts['change_size_by_month'])})")
            lines.append('')
        if 'bugs_created_vs_closed_by_month' in charts:
            lines.append(f"![bugs_created_vs_closed_by_month]({rel(charts['bugs_created_vs_closed_by_month'])})")
            lines.append('')
        if 'bug_backlog_by_month' in charts:
            lines.append(f"![bug_backlog_by_month]({rel(charts['bug_backlog_by_month'])})")
            lines.append('')
        if 'matched_vs_unmatched' in charts:
            lines.append(f"![matched_vs_unmatched]({rel(charts['matched_vs_unmatched'])})")
            lines.append('')
        if 'match_types' in charts:
            lines.append(f"![match_types]({rel(charts['match_types'])})")
            lines.append('')
        if 'cves_by_month' in charts:
            lines.append(f"![cves_by_month]({rel(charts['cves_by_month'])})")
            lines.append('')

        lines.append('## Notes')
        lines.append('- Evolution pace uses full commit history (recommended: crawl without grep filter).')
        lines.append('- Bug dynamics uses GitHub issues with label=bug (PRs are filtered out).')
        if vuln:
            lines.append('- CVE link rule: CVE-in-subject first; then strong signals from references (commit/PR).')
            lines.append('- CVE data sources may be incomplete if external APIs are blocked (e.g., NVD in restricted networks).')

        with open(out_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')

        return out_path