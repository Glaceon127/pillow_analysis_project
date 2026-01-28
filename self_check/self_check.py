#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自检机制模块：用于验证 Pillow 修复行为分析系统的数据完整性与流程健壮性。
运行方式：
    python self_check.py
或在主流程中调用 run_all_checks()
"""

import os
import sys
import subprocess
import warnings
import pandas as pd
import ast
from pathlib import Path

# 配置项（可根据你的项目结构调整）
CONFIG = {
    "repo_root": ".",                     # Pillow 仓库根目录
    "data_dir": "data",                   # 中间数据目录
    "output_dir": "results",              # 最终输出目录
    "min_fix_commits": 50,                # 期望至少提取到的修复提交数
    "ast_parse_success_threshold": 0.90,  # AST 解析成功率阈值
    "required_output_files": [
        "aggregated_stats.csv",
        "fix_type_distribution.csv",
        "change_size_by_type.csv"
    ],
    "source_file_list": "data/changed_files.csv"  # 记录所有被分析的源文件
}

def log_check(name: str, status: bool, message: str = ""):
    """统一日志格式"""
    mark = "✅" if status else "❌"
    print(f"{mark} {name}: {message}")
    return status

def check_git_repo():
    """检查当前目录是否为有效的 Git 仓库且是 Pillow"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=CONFIG["repo_root"],
            capture_output=True,
            text=True,
            check=True
        )
        repo_path = result.stdout.strip()
        if not os.path.exists(os.path.join(repo_path, "src/PIL")):
            return log_check("Git 仓库检查", False, "未检测到 Pillow 源码结构（缺少 src/PIL）")
        return log_check("Git 仓库检查", True, f"路径: {repo_path}")
    except (subprocess.CalledProcessError, FileNotFoundError):
        return log_check("Git 仓库检查", False, "当前目录不是有效的 Git 仓库")

def check_extracted_commits():
    """检查是否成功提取了足够数量的修复提交"""
    commits_file = os.path.join(CONFIG["data_dir"], "fix_commits.csv")
    if not os.path.isfile(commits_file):
        return log_check("修复提交提取", False, f"文件不存在: {commits_file}")
    
    try:
        df = pd.read_csv(commits_file)
        count = len(df)
        if count < CONFIG["min_fix_commits"]:
            return log_check("修复提交提取", False, f"仅找到 {count} 个修复提交（期望 ≥{CONFIG['min_fix_commits']}）")
        return log_check("修复提交提取", True, f"共 {count} 个修复提交")
    except Exception as e:
        return log_check("修复提交提取", False, f"读取失败: {e}")

def check_ast_parse_success_rate():
    """检查 changed_files.csv 中记录的源文件能否被 AST 成功解析"""
    file_list = CONFIG["source_file_list"]
    if not os.path.isfile(file_list):
        return log_check("AST 解析检查", False, f"文件不存在: {file_list}")

    try:
        df = pd.read_csv(file_list)
        if df.empty:
            return log_check("AST 解析检查", False, "无待分析文件")

        total = 0
        success = 0
        failed_files = []

        for _, row in df.iterrows():
            filepath = row.get("file_path")
            if not filepath or not os.path.isfile(filepath):
                continue
            total += 1
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    source = f.read()
                ast.parse(source)
                success += 1
            except (SyntaxError, UnicodeDecodeError, OSError) as e:
                failed_files.append((filepath, str(e)))

        rate = success / total if total > 0 else 0
        threshold = CONFIG["ast_parse_success_threshold"]

        if rate < threshold:
            msg = f"成功率 {rate:.2%} < 阈值 {threshold:.2%}；失败示例: {failed_files[:2]}"
            return log_check("AST 解析检查", False, msg)
        else:
            return log_check("AST 解析检查", True, f"成功率 {rate:.2%} ({success}/{total})")
    except Exception as e:
        return log_check("AST 解析检查", False, f"异常: {e}")

def check_fix_type_annotation():
    """检查每个修复提交是否都有非空的 fix_type 标签"""
    stats_file = os.path.join(CONFIG["output_dir"], "fix_type_distribution.csv")
    if not os.path.isfile(stats_file):
        return log_check("修复类型标注", False, f"文件不存在: {stats_file}")

    try:
        df = pd.read_csv(stats_file)
        if df.empty:
            return log_check("修复类型标注", False, "分布文件为空")
        
        # 假设第一列为类型，第二列为数量
        other_ratio = 0.0
        total = df.iloc[:, 1].sum()
        if total == 0:
            return log_check("修复类型标注", False, "总修复数为0")

        for _, row in df.iterrows():
            fix_type = str(row.iloc[0]).lower()
            count = row.iloc[1]
            if "other" in fix_type or "unknown" in fix_type:
                other_ratio = count / total
                break

        if other_ratio > 0.7:
            return log_check("修复类型标注", False, f"'other' 类型占比过高 ({other_ratio:.2%})，分类可能失效")
        return log_check("修复类型标注", True, f"'other' 占比 {other_ratio:.2%}")
    except Exception as e:
        return log_check("修复类型标注", False, f"读取失败: {e}")

def check_output_files_exist():
    """检查 results/ 目录是否包含所有必需的输出文件"""
    missing = []
    for fname in CONFIG["required_output_files"]:
        fpath = os.path.join(CONFIG["output_dir"], fname)
        if not os.path.isfile(fpath):
            missing.append(fname)
    
    if missing:
        return log_check("输出文件完整性", False, f"缺失文件: {missing}")
    else:
        return log_check("输出文件完整性", True, f"全部 {len(CONFIG['required_output_files'])} 个文件存在")

def check_directories():
    """检查 data/ 和 results/ 目录是否存在"""
    dirs = [CONFIG["data_dir"], CONFIG["output_dir"]]
    missing = [d for d in dirs if not os.path.isdir(d)]
    if missing:
        return log_check("目录结构", False, f"缺失目录: {missing}")
    return log_check("目录结构", True, "data/ 和 results/ 目录存在")

# ==============================
# 主入口
# ==============================

def run_all_checks():
    """运行所有自检项"""
    print("🔍 正在运行 Pillow 分析系统自检机制...\n")
    
    checks = [
        check_directories,
        check_git_repo,
        check_extracted_commits,
        check_ast_parse_success_rate,
        check_fix_type_annotation,
        check_output_files_exist,
    ]

    failed = 0
    for check in checks:
        try:
            result = check()
            if not result:
                failed += 1
        except Exception as e:
            log_check(check.__name__, False, f"崩溃: {e}")
            failed += 1

    print("\n" + "="*50)
    if failed == 0:
        print("🎉 所有自检项通过！系统状态健康。")
        return True
    else:
        print(f"⚠️  共 {failed} 项检查失败，请根据上述提示修复。")
        return False

if __name__ == "__main__":
    success = run_all_checks()
    sys.exit(0 if success else 1)