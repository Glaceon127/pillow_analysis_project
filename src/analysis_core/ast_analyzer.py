"""AST代码静态分析模块（基于libcst）。

功能：
- 分析提交的代码变更（diff）中的语法结构变化
- 识别特定修复模式（如安全修复、错误修复等）
- 与变更规模和修复类型进行关联分析
"""

from __future__ import annotations

import libcst as cst
from libcst.metadata import MetadataWrapper, QualifiedNameProvider
from typing import Any, Dict, List, Optional


class ASTAnalyzer:
    def __init__(self):
        pass

    def analyze(self, code: str, file_path: Optional[str] = None) -> Dict[str, Any]:
        """对代码进行AST静态分析
        
        Args:
            code: 要分析的代码字符串
            file_path: 文件路径（可选，用于确定上下文）
            
        Returns:
            包含分析结果的字典
        """
        try:
            tree = cst.parse_expression(code) if self._is_expression(code) else cst.parse_module(code)
        except Exception:
            try:
                # 如果是模块解析失败，尝试作为语句列表解析
                tree = cst.parse_module(code)
            except Exception:
                # 如果都无法解析，返回空结果
                return {
                    'error': 'Could not parse code',
                    'patterns_found': [],
                    'security_issues_potential': 0,
                    'complexity_score': 0
                }
        
        visitor = ASTAnalysisVisitor()
        wrapper = MetadataWrapper(tree)
        wrapper.visit(visitor)
        
        return {
            'patterns_found': visitor.patterns,
            'security_issues_potential': len(visitor.security_patterns),
            'complexity_score': self._calculate_complexity(tree),
            'function_count': len(visitor.functions),
            'class_count': len(visitor.classes),
            'import_count': len(visitor.imports),
            'file_path': file_path
        }
    
    def _is_expression(self, code: str) -> bool:
        """判断代码是否为表达式"""
        code = code.strip()
        return not (code.startswith('def ') or code.startswith('class ') or 
                   code.startswith('@') or code.startswith('import ') or 
                   code.startswith('from '))
    
    def _calculate_complexity(self, tree: cst.CSTNode) -> int:
        """计算代码复杂度"""
        complexity = 1  # 基础复杂度
        
        # 遍历树中的节点计算复杂度
        def count_control_structures(node):
            count = 0
            if isinstance(node, (cst.If, cst.For, cst.While, cst.ExceptHandler)):
                count = 1
            elif isinstance(node, cst.FunctionDef):
                # 函数内部的控制结构也会计数
                for child in node.body.body:
                    count += count_control_structures(child)
            elif hasattr(node, 'body') and hasattr(node.body, '__iter__'):
                # 对于有body的节点，遍历其子节点
                try:
                    for child in node.body:
                        count += count_control_structures(child)
                except TypeError:
                    # body不是可迭代对象
                    pass
            elif hasattr(node, 'body') and hasattr(node.body, 'body'):
                # 对于FunctionDef等特殊的body结构
                for child in node.body.body:
                    count += count_control_structures(child)
            return count
        
        complexity += count_control_structures(tree)
        return complexity


class ASTAnalysisVisitor(cst.CSTVisitor):
    """AST分析访问器"""
    
    METADATA_DEPENDENCIES = (QualifiedNameProvider,)
    
    def __init__(self):
        self.patterns = []
        self.security_patterns = []
        self.functions = []
        self.classes = []
        self.imports = []
    
    def visit_FunctionDef(self, node: cst.FunctionDef) -> Optional[bool]:
        self.functions.append({
            'name': node.name.value,
            'params_count': len(node.params.params),
            'async': bool(node.asynchronous)
        })
        
        # 检查函数中是否存在潜在安全问题
        self._check_security_patterns(node)
    
    def visit_ClassDef(self, node: cst.ClassDef) -> Optional[bool]:
        self.classes.append({
            'name': node.name.value,
            'bases_count': len(node.bases)
        })
    
    def visit_Import(self, node: cst.Import) -> Optional[bool]:
        for alias in node.names:
            self.imports.append(alias.name.value)
    
    def visit_ImportFrom(self, node: cst.ImportFrom) -> Optional[bool]:
        module_name = ""
        if node.module:
            if isinstance(node.module, cst.Name):
                module_name = node.module.value
            elif isinstance(node.module, cst.Attribute):
                module_name = node.module.attr.value
        for alias in node.names:
            self.imports.append(f"{module_name}.{alias.name.value}")
    
    def _check_security_patterns(self, node: cst.CSTNode) -> None:
        """检查潜在安全模式"""
        # 检查是否有eval调用
        for child in self._get_all_subnodes(node):
            if isinstance(child, cst.Call) and isinstance(child.func, cst.Name):
                if child.func.value in ['eval', 'exec', 'compile']:
                    self.security_patterns.append({
                        'type': 'dangerous_function_call',
                        'function': child.func.value,
                        'location': getattr(child, 'lpar', None)
                    })
                    self.patterns.append('security_eval_exec_usage')
                
                # 检查不安全的导入
                if child.func.value == 'getattr' or child.func.value == 'setattr':
                    self.patterns.append('dynamic_attribute_access')
    
    def _get_all_subnodes(self, node: cst.CSTNode):
        """递归获取所有子节点"""
        yield node
        for child in node.children:
            yield from self._get_all_subnodes(child)