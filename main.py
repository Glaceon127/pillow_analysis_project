"""项目主入口：分析 + 可视化 + 报告。

数据抓取与关联建议先运行：
- python tools\run_collect.py
- python tools\run_link_commits.py --repo "F:\\Pillow"

本入口读取处理后的 JSON 并产出图表/报告。
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict, List

from src.analysis_core.commit_analyzer import CommitAnalyzer
from src.analysis_core.issue_analyzer import IssueAnalyzer
from src.analysis_core.vulnerability_analyzer import VulnerabilityAnalyzer
from src.visualization.plot_generator import PlotGenerator
from src.visualization.report_builder import ReportBuilder


def _load_json(path: str) -> List[Dict[str, Any]]:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def main() -> int:
    parser = argparse.ArgumentParser(description='Pillow analysis: read processed data, generate charts and report.')
    base = os.path.abspath(os.path.dirname(__file__))

    default_commits = os.path.join(base, 'data', 'processed', 'pillow_commits_all.json')
    default_cves = os.path.join(base, 'data', 'processed', 'pillow_cves_with_commits.json')
    default_bugs = os.path.join(base, 'data', 'processed', 'pillow_bug_issues.json')

    parser.add_argument('--commits-json', default=default_commits)
    parser.add_argument('--cves-json', default=default_cves, help='Optional; if missing, vulnerability section will be skipped')
    parser.add_argument('--bugs-json', default=default_bugs, help='Optional; if missing, bug section will be skipped')
    parser.add_argument('--charts-dir', default=os.path.join(base, 'outputs', 'charts'))
    parser.add_argument('--report', default=os.path.join(base, 'outputs', 'reports', 'pillow_report.md'))
    args = parser.parse_args()

    commits = _load_json(args.commits_json)
    cves = _load_json(args.cves_json)
    bugs = _load_json(args.bugs_json)

    if not commits:
        print('[main][ERROR] commits data not found. Run tools/run_crawl_commits.py first.')
        print('Expected:', args.commits_json)
        return 2

    commit_index = {c.get('hash'): c for c in commits if isinstance(c, dict) and c.get('hash')}

    commit_stats = CommitAnalyzer().analyze(commits)
    issue_stats = IssueAnalyzer().analyze(bugs)

    vuln_stats = None
    if cves:
        vuln_stats = VulnerabilityAnalyzer().analyze(cves, commit_index=commit_index)
    else:
        print('[main][WARN] CVE json not found/empty, skipping vulnerability analysis:', args.cves_json)

    analysis_results = {
        'commit': commit_stats,
        'issues': issue_stats,
        'vulnerability': vuln_stats,
    }

    charts = PlotGenerator().generate(analysis_results, out_dir=args.charts_dir)
    report_path = ReportBuilder().build(analysis_results, charts=charts, out_path=args.report)

    print('[main] charts_dir:', args.charts_dir)
    print('[main] report:', report_path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())