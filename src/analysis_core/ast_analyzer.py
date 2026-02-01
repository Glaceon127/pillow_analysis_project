import ast
import os
from typing import Dict, List, Tuple, Optional

class PillowASTAnalyzer:
    """Pillow 代码库 AST 分析器：提取修复代码的模式/热区特征"""
    
    def __init__(self, pillow_repo_path: str):
        """初始化：传入 Pillow 本地仓库路径"""
        self.repo_path = os.path.abspath(pillow_repo_path)
        # 缓存：文件路径 -> AST 树（避免重复解析）
        self.ast_cache: Dict[str, ast.AST] = {}
        # 忽略的文件后缀/路径
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
