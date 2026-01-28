"""演示AST分析功能的工具脚本。

此脚本演示如何使用AST分析器分析代码变更，并将其与修复类型关联。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.analysis_core.ast_analyzer import ASTAnalyzer
from src.analysis_core.commit_analyzer import CommitAnalyzer


def analyze_sample_code_changes():
    """分析一些示例代码变更"""
    print("=== AST分析演示 ===")
    
    # 示例代码变更
    sample_fixes = [
        {
            'name': '安全修复示例',
            'code': '''
def validate_input(user_input):
    # 修复了潜在的代码注入漏洞
    if eval(user_input):
        return True
    return False
            ''',
            'file_path': 'security_fix.py'
        },
        {
            'name': '错误修复示例',
            'code': '''
def calculate_sum(numbers):
    total = 0
    for num in numbers:
        # 修复了边界条件错误
        if num > 0:
            total += num
    return total
            ''',
            'file_path': 'bug_fix.py'
        },
        {
            'name': '正常功能实现',
            'code': '''
def get_user_data(user_id):
    # 正常的功能实现
    user = db.fetch_user(user_id)
    return user.to_dict()
            ''',
            'file_path': 'feature.py'
        }
    ]
    
    analyzer = ASTAnalyzer()
    
    print("\n正在分析代码变更...")
    for i, sample in enumerate(sample_fixes, 1):
        print(f"\n{i}. {sample['name']}")
        print("-" * 40)
        
        result = analyzer.analyze(sample['code'], sample['file_path'])
        
        print(f"  模式发现: {result.get('patterns_found', [])}")
        print(f"  潜在安全问题: {result.get('security_issues_potential', 0)}")
        print(f"  复杂度评分: {result.get('complexity_score', 0)}")
        print(f"  函数数量: {result.get('function_count', 0)}")
        print(f"  类数量: {result.get('class_count', 0)}")


def analyze_commits_with_ast():
    """分析提交数据中的AST信息"""
    print("\n\n=== 提交数据分析（含AST）===")
    
    # 尝试加载提交数据
    base = os.path.abspath(os.path.dirname(__file__))
    commits_path = os.path.join(base, '..', 'data', 'processed', 'pillow_commits_all.json')
    
    if not os.path.exists(commits_path):
        print(f"警告: 找不到提交数据文件 {commits_path}")
        print("提示: 运行 'python tools/run_crawl_commits.py' 来生成提交数据")
        return
    
    try:
        with open(commits_path, 'r', encoding='utf-8') as f:
            commits = json.load(f)
        
        if not commits:
            print("提交数据为空")
            return
        
        print(f"加载了 {len(commits)} 个提交记录")
        
        # 使用CommitAnalyzer进行分析，它会自动执行AST分析
        analyzer = CommitAnalyzer()
        result = analyzer.analyze(commits)
        
        ast_summary = result.get('ast_analysis_summary', {})
        
        if ast_summary.get('enabled', False):
            print(f"AST分析状态: 已启用")
            print(f"分析的提交数: {ast_summary.get('analyzed_commits_count', 0)}")
            print(f"检测到的安全问题总数: {ast_summary.get('security_issues_total', 0)}")
            print(f"总复杂度评分: {ast_summary.get('complexity_total', 0)}")
            print(f"总函数数: {ast_summary.get('function_count_total', 0)}")
            
            if ast_summary.get('has_security_related_fixes'):
                print("包含安全相关修复: 是")
            
            top_patterns = ast_summary.get('top_patterns', [])
            if top_patterns:
                print("\n最常见的模式:")
                for i, pattern in enumerate(top_patterns[:5], 1):
                    print(f"  {i}. {pattern.get('pattern', 'Unknown')}: {pattern.get('count', 0)} 次")
        else:
            print(f"AST分析状态: {ast_summary.get('message', '未启用')}")
    
    except Exception as e:
        print(f"分析提交数据时出错: {e}")


def main():
    parser = argparse.ArgumentParser(description='演示AST分析功能')
    parser.add_argument('--commits-only', action='store_true', 
                       help='只分析提交数据，跳过代码示例')
    parser.add_argument('--code-only', action='store_true', 
                       help='只分析代码示例，跳过提交数据')
    
    args = parser.parse_args()
    
    if not args.code_only:
        analyze_commits_with_ast()
    
    if not args.commits_only:
        analyze_sample_code_changes()


if __name__ == '__main__':
    main()