import json
import os
import matplotlib.pyplot as plt
import seaborn as sns
from collections import Counter
from config.settings import OUTPUT_CHARTS_DIR

# 设置中文字体（避免乱码）
plt.rcParams["font.family"] = ["SimHei", "WenQuanYi Micro Hei", "Heiti TC"]
plt.rcParams["axes.unicode_minus"] = False

def plot_ast_feature_distribution(ast_results_path: str, output_dir: str = OUTPUT_CHARTS_DIR):
    """生成 AST 特征分布图表：修复涉及的节点类型/函数热区
    Args:
        ast_results_path: AST分析结果JSON文件路径
        output_dir: 图表输出目录
    """
    # 1. 读取 AST 分析结果
    if not os.path.exists(ast_results_path):
        print(f" AST分析结果文件不存在：{ast_results_path}")
        return
    
    with open(ast_results_path, "r", encoding="utf-8") as f:
        ast_results = json.load(f)
    
    # 2. 统计核心特征
    node_type_counter = Counter()  # 节点类型频次
    function_counter = Counter()  # 函数修改频次
    file_counter = Counter()      # 文件修改频次

    for commit in ast_results:
        for file_analysis in commit["ast_analysis"]:
            # 跳过解析失败的文件
            if file_analysis.get("error"):
                continue
            
            # 累加统计
            node_types = file_analysis.get("unique_node_types", [])
            functions = file_analysis.get("touched_functions", [])
            file_path = file_analysis.get("file_path", "")

            node_type_counter.update(node_types)
            function_counter.update(functions)
            if file_path:
                file_counter[file_path] += 1

    # 3. 生成节点类型分布图表（Top 10）
    plt.figure(figsize=(12, 6))
    top_node_types = node_type_counter.most_common(10)
    if top_node_types:
        sns.barplot(x=[x[0] for x in top_node_types], y=[x[1] for x in top_node_types])
        plt.title("Bug 修复涉及的 AST 节点类型（Top 10）", fontsize=14)
        plt.xlabel("节点类型", fontsize=12)
        plt.ylabel("出现频次", fontsize=12)
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, "ast_node_type_dist.png"), dpi=300)
    else:
        print(" 无节点类型数据，跳过节点类型图表生成")

    # 4. 生成函数修改热区图表（Top 10）
    plt.figure(figsize=(12, 6))
    top_functions = function_counter.most_common(10)
    if top_functions:
        sns.barplot(x=[x[0] for x in top_functions], y=[x[1] for x in top_functions])
        plt.title("Bug 修复热区函数（Top 10）", fontsize=14)
        plt.xlabel("函数名", fontsize=12)
        plt.ylabel("修改频次", fontsize=12)
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, "ast_function_hotspot.png"), dpi=300)
    else:
        print(" 无函数数据，跳过热区函数图表生成")

    # 5. 生成文件修改频次图表（Top 10）
    plt.figure(figsize=(12, 6))
    top_files = file_counter.most_common(10)
    if top_files:
        # 简化文件名（只保留最后两级）
        simplified_files = ["/".join(x[0].split("/")[-2:]) for x in top_files]
        sns.barplot(x=simplified_files, y=[x[1] for x in top_files])
        plt.title("Bug 修复热区文件（Top 10）", fontsize=14)
        plt.xlabel("文件路径（简化）", fontsize=12)
        plt.ylabel("修改频次", fontsize=12)
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, "ast_file_hotspot.png"), dpi=300)
    else:
        print(" 无文件数据，跳过热区文件图表生成")

    plt.close("all")
    print(f" AST可视化图表已生成至：{output_dir}")

def plot_commit_ast_summary(ast_results_path: str, output_dir: str = OUTPUT_CHARTS_DIR):
    """生成Commit级别的AST分析汇总图表"""
    if not os.path.exists(ast_results_path):
        print(f" AST分析结果文件不存在：{ast_results_path}")
        return
    
    with open(ast_results_path, "r", encoding="utf-8") as f:
        ast_results = json.load(f)
    
    # 统计每个Commit匹配的行数/节点数
    commit_matched_lines = []
    commit_node_types = []
    commit_hashes = []

    for commit in ast_results:
        total_matched = 0
        total_nodes = 0
        for file_analysis in commit["ast_analysis"]:
            total_matched += file_analysis.get("matched_lines", 0)
            total_nodes += len(file_analysis.get("unique_node_types", []))
        
        if total_matched > 0:
            commit_hashes.append(commit["commit_hash"][:8])  # 只显示前8位hash
            commit_matched_lines.append(total_matched)
            commit_node_types.append(total_nodes)

    # 生成Commit匹配行数分布
    plt.figure(figsize=(15, 6))
    if commit_hashes:
        sns.barplot(x=commit_hashes, y=commit_matched_lines)
        plt.title("各Commit修复代码匹配行数", fontsize=14)
        plt.xlabel("Commit Hash（前8位）", fontsize=12)
        plt.ylabel("匹配行数", fontsize=12)
        plt.xticks(rotation=90)
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, "commit_matched_lines.png"), dpi=300)
    else:
        print(" 无Commit匹配数据，跳过Commit行数图表生成")

    plt.close("all")
