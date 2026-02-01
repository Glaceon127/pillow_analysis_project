from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict, List, Optional

import matplotlib.pyplot as plt


def plot_danger_patterns(ast_summary: Dict[str, Any], output_dir: str) -> Dict[str, str]:
    """基于 CommitAnalyzer 的 ast_analysis_summary 生成图表。

    输入 schema（关键字段）：
    - enabled: bool
    - patterns_by_month: [{'month','patterns_total',...}]
    - top_patterns: [{'pattern','count'}]
    """
    os.makedirs(output_dir, exist_ok=True)
    charts: Dict[str, str] = {}

    if not (ast_summary or {}).get('enabled'):
        print('[ast_visualizer] AST summary disabled or missing.')
        return charts

    patterns_by_month: List[Dict[str, Any]] = ast_summary.get('patterns_by_month') or []
    if patterns_by_month:
        months = [x.get('month') for x in patterns_by_month]
        counts = [int(x.get('patterns_total', 0) or 0) for x in patterns_by_month]
        xs = list(range(len(months)))
        plt.figure(figsize=(10, 4))
        plt.plot(xs, counts, marker='o')
        # thin ticks
        max_ticks = 24
        if len(months) > max_ticks:
            step = max(1, len(months) // max_ticks)
            positions = list(range(0, len(months), step))
            if positions and positions[-1] != len(months) - 1:
                positions.append(len(months) - 1)
        else:
            positions = xs
        labels = [months[i] for i in positions]
        plt.xticks(positions, labels, rotation=45, ha='right')
        plt.title('每月危险模式命中次数（AST信号）')
        plt.xlabel('月份')
        plt.ylabel('命中次数（次）')
        plt.tight_layout()
        path = os.path.join(output_dir, 'ast_patterns_by_month.png')
        plt.savefig(path, dpi=150)
        plt.close()
        charts['ast_patterns_by_month'] = path

    top_patterns: List[Dict[str, Any]] = ast_summary.get('top_patterns') or []
    if top_patterns:
        names = [x.get('pattern', '') for x in top_patterns[:10]]
        values = [int(x.get('count', 0) or 0) for x in top_patterns[:10]]
        plt.figure(figsize=(10, 4))
        plt.bar(names, values)
        plt.title('危险模式 Top 10（AST信号）')
        plt.xlabel('模式')
        plt.ylabel('出现次数（次）')
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        path = os.path.join(output_dir, 'ast_top_patterns.png')
        plt.savefig(path, dpi=150)
        plt.close()
        charts['ast_top_patterns'] = path

    return charts


def _load_ast_summary_from_analysis_results(path: str) -> Optional[Dict[str, Any]]:
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return None
    commit = (data.get('commit') or {}) if isinstance(data.get('commit'), dict) else {}
    ast_summary = commit.get('ast_analysis_summary')
    return ast_summary if isinstance(ast_summary, dict) else None


def main() -> int:
    parser = argparse.ArgumentParser(description='AST dangerous-pattern visualizer (reads analysis_results.json)')
    parser.add_argument('--analysis-json', required=True, help='Path to analysis_results.json produced by main.py')
    parser.add_argument('--out', default=os.path.join('outputs', 'charts'), help='Output charts directory')
    args = parser.parse_args()

    ast_summary = _load_ast_summary_from_analysis_results(args.analysis_json)
    if not ast_summary:
        print('[ast_visualizer][ERROR] ast_analysis_summary not found in analysis json.')
        return 2

    charts = plot_danger_patterns(ast_summary, output_dir=args.out)
    print('[ast_visualizer] wrote:', charts)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
