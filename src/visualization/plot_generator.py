"""生成各种图表模块。

输入：analysis_results（dict）。
输出：charts 路径映射（dict）。
"""

from __future__ import annotations

import os
import sys
import logging
from typing import Any, Dict, List

import matplotlib.pyplot as plt

from src.visualization.style import (
    apply_style,
    COLOR_AST,
    COLOR_BUG,
    COLOR_COMMIT,
    COLOR_CVE,
    COLOR_FIX,
    COLOR_MEAN,
    COLOR_P90,
)

# ===================== 统一风格入口 =====================
apply_style()

class PlotGenerator:
    def generate(self, analysis_results: Dict[str, Any], out_dir: str) -> Dict[str, str]:
        os.makedirs(out_dir, exist_ok=True)
        charts: Dict[str, str] = {}

        # Optional debug output
        if os.getenv('PILLOW_ANALYSIS_DEBUG', '').strip() in {'1', 'true', 'True', 'yes', 'YES'}:
            print("=== 数据检查 ===")
            print("commit数据：", analysis_results.get('commit'))
            print("issues数据：", analysis_results.get('issues'))
            print("vuln数据：", analysis_results.get('vulnerability'))
        def _thin_month_ticks(month_labels: List[str], max_ticks: int = None):
            if max_ticks is None:
                max_ticks = 24
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
        # 0) Commits by month (evolution pace)
        commits_by_month: List[Dict[str, Any]] = commit.get('commits_by_month') or []
        if commits_by_month:
            months = [x.get('month') for x in commits_by_month]
            counts = [x.get('count', 0) for x in commits_by_month]
            plt.figure(figsize=(10, 4))
            xs, tick_pos, tick_labels = _thin_month_ticks(months, max_ticks=24)
            # 改进：指定统一配色 + 用全局线条宽度
            plt.plot(xs, counts, marker='o', color=COLOR_COMMIT)
            plt.xticks(tick_pos, tick_labels, rotation=45, ha='right')
            plt.title('每月提交量趋势（演化节奏）')
            # 新增：坐标轴标签
            plt.xlabel('月份')
            plt.ylabel('提交数量（次）')
            plt.tight_layout()
            path = os.path.join(out_dir, 'commits_by_month.png')
            plt.savefig(path, dpi=150)
            plt.close()
            charts['commits_by_month'] = path

        # 0b) Fix ratio by month (2.1)
        # 0b) Fix ratio by month (2.1)
        fix_by_month: List[Dict[str, Any]] = commit.get('fix_commits_by_month') or []
        if fix_by_month:
            months = [x.get('month') for x in fix_by_month]
            ratios = [float(x.get('ratio', 0.0)) * 100.0 for x in fix_by_month]
            plt.figure(figsize=(10, 4))
            xs, tick_pos, tick_labels = _thin_month_ticks(months, max_ticks=24)
            # 改进：指定统一配色 + 用全局线条宽度
            plt.plot(xs, ratios, marker='o', color=COLOR_FIX)
            plt.xticks(tick_pos, tick_labels, rotation=45, ha='right')
            plt.ylim(0, 100)
            plt.title('每月修复提交占比（%）')
            # 新增：坐标轴标签
            plt.xlabel('月份')
            plt.ylabel('修复提交占比（%）')
            plt.tight_layout()
            path = os.path.join(out_dir, 'fix_ratio_by_month.png')
            plt.savefig(path, dpi=150)
            plt.close()
            charts['fix_ratio_by_month'] = path

        # 0c) Change size by month (2.2)
        # 0c) Change size by month (2.2)
        change_by_month: List[Dict[str, Any]] = commit.get('change_size_by_month') or []
        if change_by_month:
            months = [x.get('month') for x in change_by_month]
            mean_sizes = [float(x.get('change_size_mean', 0.0)) for x in change_by_month]
            p90_sizes = [float(x.get('change_size_p90', 0.0)) for x in change_by_month]
            plt.figure(figsize=(10, 4))
            xs, tick_pos, tick_labels = _thin_month_ticks(months, max_ticks=24)
            # 改进：指定统一配色 + 用全局线条宽度 + 统一图例位置
            plt.plot(xs, mean_sizes, marker='o', color=COLOR_MEAN, label='平均值')
            plt.plot(xs, p90_sizes, marker='o', color=COLOR_P90, label='P90值')
            plt.xticks(tick_pos, tick_labels, rotation=45, ha='right')
            plt.title('每月变更规模趋势（单次提交增删代码行数）')
            # 新增：坐标轴标签
            plt.xlabel('月份')
            plt.ylabel('代码增删行数（行）')
            # 改进：统一图例位置
            plt.legend(loc='upper right')
            plt.tight_layout()
            path = os.path.join(out_dir, 'change_size_by_month.png')
            plt.savefig(path, dpi=150)
            plt.close()
            charts['change_size_by_month'] = path

        # 0d) AST dangerous patterns by month (signal-only)
        ast_summary = (commit.get('ast_analysis_summary') or {}) if isinstance(commit, dict) else {}
        ast_by_month: List[Dict[str, Any]] = ast_summary.get('patterns_by_month') or []
        if ast_summary.get('enabled') and ast_by_month:
            months = [x.get('month') for x in ast_by_month]
            counts = [int(x.get('patterns_total', 0) or 0) for x in ast_by_month]
            plt.figure(figsize=(10, 4))
            xs, tick_pos, tick_labels = _thin_month_ticks(months, max_ticks=24)
            plt.plot(xs, counts, marker='o', color=COLOR_AST)
            plt.xticks(tick_pos, tick_labels, rotation=45, ha='right')
            plt.title('每月危险模式命中次数（AST信号）')
            plt.xlabel('月份')
            plt.ylabel('命中次数（次）')
            plt.tight_layout()
            path = os.path.join(out_dir, 'ast_patterns_by_month.png')
            plt.savefig(path, dpi=150)
            plt.close()
            charts['ast_patterns_by_month'] = path

        # 0e) AST top patterns (overall)
        top_patterns: List[Dict[str, Any]] = ast_summary.get('top_patterns') or []
        if ast_summary.get('enabled') and top_patterns:
            names = [x.get('pattern', '') for x in top_patterns[:10]]
            values = [int(x.get('count', 0) or 0) for x in top_patterns[:10]]
            plt.figure(figsize=(10, 4))
            plt.bar(names, values, color=COLOR_AST)
            plt.title('危险模式 Top 10（AST信号）')
            plt.xlabel('模式')
            plt.ylabel('出现次数（次）')
            plt.xticks(rotation=45, ha='right')
            plt.tight_layout()
            path = os.path.join(out_dir, 'ast_top_patterns.png')
            plt.savefig(path, dpi=150)
            plt.close()
            charts['ast_top_patterns'] = path

        # A) Bug issues: created vs closed by month
        created_by_month: List[Dict[str, Any]] = issues.get('created_by_month') or []
        closed_by_month: List[Dict[str, Any]] = issues.get('closed_by_month') or []
        if created_by_month or closed_by_month:
            # union months
            months = sorted(
                set([x.get('month') for x in created_by_month]) | set([x.get('month') for x in closed_by_month]))
            created_map = {x.get('month'): x.get('count', 0) for x in created_by_month}
            closed_map = {x.get('month'): x.get('count', 0) for x in closed_by_month}
            created_counts = [created_map.get(m, 0) for m in months]
            closed_counts = [closed_map.get(m, 0) for m in months]
            plt.figure(figsize=(10, 4))
            xs, tick_pos, tick_labels = _thin_month_ticks(months, max_ticks=24)
            # 改进：指定统一配色 + 用全局线条宽度 + 统一图例位置
            plt.plot(xs, created_counts, marker='o', color=COLOR_BUG, label='新增Bug')
            plt.plot(xs, closed_counts, marker='o', color=COLOR_COMMIT, label='关闭Bug')
            plt.xticks(tick_pos, tick_labels, rotation=45, ha='right')
            plt.title('Bug工单：每月新增 vs 每月关闭')
            # 新增：坐标轴标签
            plt.xlabel('月份')
            plt.ylabel('Bug工单数量（个）')
            # 改进：统一图例位置
            plt.legend(loc='upper right')
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
            # 改进：指定统一配色 + 用全局线条宽度
            plt.plot(xs, counts, marker='o', color=COLOR_BUG)
            plt.xticks(tick_pos, tick_labels, rotation=45, ha='right')
            plt.title('Bug积压量趋势（未关闭=累计新增-累计关闭）')
            # 新增：坐标轴标签
            plt.xlabel('月份')
            plt.ylabel('未关闭Bug数量（个）')
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
            # 改进：指定统一配色 + 用全局线条宽度
            plt.plot(xs, counts, marker='o', color=COLOR_CVE)
            plt.xticks(tick_pos, tick_labels, rotation=45, ha='right')
            plt.title('每月CVE漏洞数量趋势')
            # 新增：坐标轴标签
            plt.xlabel('月份')
            plt.ylabel('CVE漏洞数量（个）')
            plt.tight_layout()
            path = os.path.join(out_dir, 'cves_by_month.png')
            plt.savefig(path, dpi=150)
            plt.close()
            charts['cves_by_month'] = path

        # 2) Matched vs unmatched
        total = vuln.get('total_cves') or 0
        matched = vuln.get('matched_cves') or 0
        if total:
            labels = ['匹配', '未匹配']
            values = [matched, max(total - matched, 0)]
            bar_colors = [COLOR_COMMIT, COLOR_CVE]  # 两种不同颜色
            plt.figure(figsize=(8, 5))
            bars = plt.bar(
                labels,
                values,
                color=bar_colors,
                width=0.6,
                alpha=0.85,
                edgecolor='black',
                linewidth=1.2
            )
            plt.xticks(rotation=25, ha='center', fontsize=12)
            plt.title('CVE漏洞匹配情况（关联提交 vs 未关联）', fontsize=15, fontweight='bold')
            plt.xlabel('匹配状态', fontsize=13)
            plt.ylabel('漏洞数量（个）', fontsize=13)
            plt.grid(axis='y', linestyle='--', alpha=0.5)
            plt.ylim(0, max(values) * 1.20)  # 上调y轴
            plt.tight_layout()
            # 美化数值标注，略微上调
            for bar, value in zip(bars, values):
                plt.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + max(values) * 0.04,  # 上调数值
                    str(value),
                    ha='center',
                    va='bottom',
                    fontsize=14,
                    fontweight='bold',
                    color='#333',
                    bbox=dict(facecolor='white', edgecolor='none', alpha=0.7, boxstyle='round,pad=0.2')
                )
            path = os.path.join(out_dir, 'matched_vs_unmatched.png')
            plt.savefig(path, dpi=150)
            plt.close()
            charts['matched_vs_unmatched'] = path

        # 3) Match types distribution
        mt = vuln.get('match_types_top') or []
        if mt:
            type_cn_map = {
                'commit_reference': '提交引用',
                'pr_reference': 'PR引用',
                'cve_in_subject': '标题中包含 CVE 编号',
                'keyword': '关键词',
                'filename': '文件名',
                'description': '描述',
            }
            labels = [
                f"{x.get('type')}（{type_cn_map.get(x.get('type'), '未知')}）"
                for x in mt
            ]
            values = [x.get('count', 0) for x in mt]
            # 为3个柱子指定不同颜色
            bar_colors = ['#2E86AB', '#A23B72', '#F18F01']  # 可根据需要调整顺序和色值
            plt.figure(figsize=(8, 5))
            bars = plt.bar(labels, values, color=bar_colors[:len(values)], width=0.6, alpha=0.85, edgecolor='black', linewidth=1.2)
            plt.xticks(rotation=25, ha='center', fontsize=12)
            plt.title('CVE漏洞匹配类型分布（Top类型）', fontsize=15, fontweight='bold')
            plt.xlabel('匹配类型', fontsize=13)
            plt.ylabel('漏洞数量（个）', fontsize=13)
            plt.grid(axis='y', linestyle='--', alpha=0.5)
            plt.ylim(0, max(values) * 1.20)  # 上调y轴
            plt.tight_layout()
            for bar, value in zip(bars, values):
                plt.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + max(values) * 0.04,  # 上调数值
                    str(value),
                    ha='center',
                    va='bottom',
                    fontsize=14,
                    fontweight='bold',
                    color='#333',
                    bbox=dict(facecolor='white', edgecolor='none', alpha=0.7, boxstyle='round,pad=0.2')
                )
            path = os.path.join(out_dir, 'match_types.png')
            plt.savefig(path, dpi=150)
            plt.close()
            charts['match_types'] = path

        return charts