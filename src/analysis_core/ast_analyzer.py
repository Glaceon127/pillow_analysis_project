"""AST 静态分析（标准库 ast 版）。

核心问题：识别危险模式并统计趋势。

约定：提供统一的 `ASTAnalyzer` 类，供 `CommitAnalyzer` 调用：

- analyze(code: str, file_path: str) -> dict
  返回包含 patterns_found / security_issues_potential 等字段的结果。

说明：本模块仅做“信号级”静态检测（pattern spotting），不做完整数据流/污点分析。
"""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class PatternHit:
    pattern: str
    lineno: Optional[int] = None


class ASTAnalyzer:
    """通用 AST 分析器（标准库 ast）：检测危险模式 + 基础结构指标。"""

    def analyze(self, code: str, file_path: str = "") -> Dict[str, Any]:
        file_path = file_path or ""
        if not isinstance(code, str) or not code.strip():
            return {
                'file_path': file_path,
                'patterns_found': [],
                'pattern_hits': [],
                'security_issues_potential': 0,
                'complexity_score': 0,
                'function_count': 0,
                'class_count': 0,
                'import_count': 0,
                'error': 'empty_code',
            }

        try:
            tree = ast.parse(code, filename=file_path or '<unknown>')
        except SyntaxError as e:
            return {
                'file_path': file_path,
                'patterns_found': [],
                'pattern_hits': [],
                'security_issues_potential': 0,
                'complexity_score': 0,
                'function_count': 0,
                'class_count': 0,
                'import_count': 0,
                'error': f'syntax_error: {e.msg}',
            }
        except Exception as e:
            return {
                'file_path': file_path,
                'patterns_found': [],
                'pattern_hits': [],
                'security_issues_potential': 0,
                'complexity_score': 0,
                'function_count': 0,
                'class_count': 0,
                'import_count': 0,
                'error': f'parse_error: {e}',
            }

        visitor = _DangerPatternVisitor()
        visitor.visit(tree)

        hits = visitor.hits
        patterns_found = [h.pattern for h in hits]
        return {
            'file_path': file_path,
            'patterns_found': patterns_found,
            'pattern_hits': [{'pattern': h.pattern, 'lineno': h.lineno} for h in hits],
            'security_issues_potential': int(len(patterns_found)),
            'complexity_score': int(visitor.complexity_score),
            'function_count': int(visitor.function_count),
            'class_count': int(visitor.class_count),
            'import_count': int(visitor.import_count),
            'error': None,
        }


class _DangerPatternVisitor(ast.NodeVisitor):
    """检测危险模式的 AST visitor。"""

    def __init__(self) -> None:
        self.hits: List[PatternHit] = []
        self.function_count = 0
        self.class_count = 0
        self.import_count = 0
        self.complexity_score = 0

    def _lineno(self, node: ast.AST) -> Optional[int]:
        return int(getattr(node, 'lineno', 0)) or None

    def _hit(self, pattern: str, node: ast.AST) -> None:
        self.hits.append(PatternHit(pattern=pattern, lineno=self._lineno(node)))

    def visit_Import(self, node: ast.Import) -> Any:
        self.import_count += 1
        return self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> Any:
        self.import_count += 1
        return self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        self.function_count += 1
        # complexity heuristic: each function starts with 1
        self.complexity_score += 1
        return self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        self.function_count += 1
        self.complexity_score += 1
        return self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        self.class_count += 1
        return self.generic_visit(node)

    def visit_If(self, node: ast.If) -> Any:
        self.complexity_score += 1
        return self.generic_visit(node)

    def visit_For(self, node: ast.For) -> Any:
        self.complexity_score += 1
        return self.generic_visit(node)

    def visit_While(self, node: ast.While) -> Any:
        self.complexity_score += 1
        return self.generic_visit(node)

    def visit_Try(self, node: ast.Try) -> Any:
        # each except/finally increases complexity
        self.complexity_score += max(1, len(getattr(node, 'handlers', []) or []))
        return self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> Any:
        # a and b and c roughly adds branches
        values = getattr(node, 'values', []) or []
        if len(values) >= 2:
            self.complexity_score += (len(values) - 1)
        return self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> Any:
        # 1) eval()/exec()
        if isinstance(node.func, ast.Name):
            if node.func.id == 'eval':
                self._hit('danger_eval', node)
            elif node.func.id == 'exec':
                self._hit('danger_exec', node)

        # 2) os.system / os.popen
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            mod = node.func.value.id
            attr = node.func.attr
            if mod == 'os' and attr in {'system', 'popen'}:
                self._hit(f'danger_os_{attr}', node)

            # 3) subprocess.* with shell=True
            if mod == 'subprocess' and attr in {'run', 'call', 'Popen', 'check_call', 'check_output'}:
                for kw in node.keywords or []:
                    if kw.arg == 'shell' and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                        self._hit('danger_subprocess_shell_true', node)
                        break

            # 4) pickle.load / pickle.loads
            if mod == 'pickle' and attr in {'load', 'loads'}:
                self._hit(f'danger_pickle_{attr}', node)

            # 5) yaml.load (potentially unsafe loader)
            if mod == 'yaml' and attr == 'load':
                self._hit('danger_yaml_load', node)

        return self.generic_visit(node)


class PillowASTAnalyzer:
    """（可选）Pillow repo 级 AST 分析器：基于 changed_lines 做热区/节点类型。

注意：该类用于行号热区类研究；危险模式统计的主入口应优先使用 ASTAnalyzer.analyze(code,...)
并通过 git show 获取指定 commit 的源码版本。
"""

    def __init__(self, pillow_repo_path: str):
        self.repo_path = os.path.abspath(pillow_repo_path)
        self.ast_cache: Dict[str, ast.AST] = {}
        self.ignore_patterns = [".c", ".h", "tests/", "docs/", "vendor/"]

    def _is_ignored(self, file_path: str) -> bool:
        """判断文件是否需要忽略"""
        for pattern in self.ignore_patterns:
            if pattern in file_path:
                return True
        return not file_path.endswith(".py")

    def _parse_file(self, file_path: str) -> Optional[ast.AST]:
        """解析单个 Python 文件为 AST（带缓存）"""
        # 处理忽略文件
        if self._is_ignored(file_path):
            return None
        
        # 转为绝对路径
        abs_path = os.path.join(self.repo_path, file_path)
        if abs_path in self.ast_cache:
            return self.ast_cache[abs_path]
        
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=abs_path)
                self.ast_cache[abs_path] = tree
                return tree
        except (SyntaxError, FileNotFoundError, PermissionError, UnicodeDecodeError) as e:
            print(f" 解析文件失败 {abs_path}: {str(e)[:50]}")
            return None

    def analyze_file_changes(self, file_path: str, line_numbers: List[int]) -> Dict:
        """分析单个文件中指定行的代码变更对应的 AST 特征
        Args:
            file_path: Pillow 仓库内的相对路径（如 src/PIL/Image.py）
            line_numbers: 变更的行号列表
        Returns:
            特征字典：包含修改的节点类型、函数名、代码位置等
        """
        # 基础校验
        if not line_numbers:
            return {
                "file_path": file_path,
                "error": "无变更行号",
                "total_changed_lines": 0,
                "matched_lines": 0,
                "unique_node_types": [],
                "touched_functions": []
            }

        tree = self._parse_file(file_path)
        if not tree:
            return {
                "file_path": file_path,
                "error": "解析失败/非Python文件",
                "total_changed_lines": len(line_numbers),
                "matched_lines": 0,
                "unique_node_types": [],
                "touched_functions": []
            }
        
        # 自定义访问器：遍历 AST 并匹配行号对应的节点
        class ChangeAnalyzer(ast.NodeVisitor):
            def __init__(self, target_lines):
                self.target_lines = set(target_lines)
                self.findings = {
                    "function_defs": [],  # 修改的函数名
                    "node_types": [],     # 修改的节点类型（如 Assign、If、BinOp）
                    "lines_matched": []   # 匹配到的行号
                }
            
            def visit(self, node):
                """重写 visit：检查节点行号是否在目标范围内"""
                # 获取节点的起始行（ast 节点的 lineno 属性）
                if hasattr(node, "lineno") and node.lineno in self.target_lines:
                    self.findings["lines_matched"].append(node.lineno)
                    self.findings["node_types"].append(type(node).__name__)
                    # 如果是函数/类定义，记录名称
                    if isinstance(node, ast.FunctionDef):
                        self.findings["function_defs"].append(node.name)
                    elif isinstance(node, ast.AsyncFunctionDef):
                        self.findings["function_defs"].append(f"async.{node.name}")
                    elif isinstance(node, ast.ClassDef):
                        self.findings["function_defs"].append(f"Class.{node.name}")
                # 继续遍历子节点
                self.generic_visit(node)
        
        analyzer = ChangeAnalyzer(line_numbers)
        analyzer.visit(tree)
        
        # 去重 + 整理结果
        return {
            "file_path": file_path,
            "total_changed_lines": len(line_numbers),
            "matched_lines": len(analyzer.findings["lines_matched"]),
            "unique_node_types": list(set(analyzer.findings["node_types"])),
            "touched_functions": list(set(analyzer.findings["function_defs"])),
            "raw_findings": analyzer.findings,
            "error": None
        }

    def analyze_commit_fix(self, commit_data: Dict) -> List[Dict]:
        """分析单个 Commit 的修复代码 AST 特征
        Args:
            commit_data: Commit 数据（需包含 hash + 文件diff）
            示例格式：
            {
                "hash": "a1b2c3d4",
                "files": [
                    {"path": "src/PIL/Image.py", "changed_lines": [10, 11, 12]},
                    {"path": "src/PIL/ImageDraw.py", "changed_lines": [5, 6]}
                ]
            }
        Returns:
            每个文件的 AST 分析结果列表
        """
        results = []
        if not commit_data.get("files"):
            return results
        
        for file_diff in commit_data["files"]:
            file_path = file_diff.get("path", "")
            changed_lines = file_diff.get("changed_lines", [])
            res = self.analyze_file_changes(file_path, changed_lines)
            res["commit_hash"] = commit_data.get("hash", "")
            results.append(res)
        
        return results

    def clear_cache(self):
        """清空 AST 缓存（避免内存占用过高）"""
        self.ast_cache.clear()
