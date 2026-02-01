# AST静态代码分析功能

## 概述

本项目新增了AST（Abstract Syntax Tree，抽象语法树）静态代码分析功能，用于分析Pillow项目中的代码变更模式。此功能可以：

1. 分析代码变更中的语法结构变化
2. 识别特定修复模式（如安全修复、错误修复等）
3. 与变更规模和修复类型进行关联分析
4. 检测潜在的安全问题模式

## 功能特点

### 代码模式检测
- 识别常见的安全漏洞模式（如`eval()`、`exec()`调用）
- 检测动态属性访问（如`getattr()`、`setattr()`）
- 统计代码复杂度和结构变化

### 修复类型分类
- 根据代码变更特征判断修复类型
- 区分安全修复和普通错误修复
- 量化修复的复杂度

### 与现有功能集成
- 与变更规模统计相结合
- 按修复类型聚合分析结果
- 在最终报告中显示AST分析摘要

## 使用方法

### 前置条件

AST 分析使用标准库 `ast`（无需额外三方 AST 依赖），但需要：

1) 本机存在 Pillow 的本地 git 仓库
2) 在 [config/local_settings.py](../config/local_settings.py) 或环境变量中配置 `PILLOW_REPO_PATH`

### 运行AST分析

您可以单独运行AST分析演示：

```bash
python tools/run_ast_analysis.py
```

或者只分析提交数据：

```bash
python tools/run_ast_analysis.py --commits-only
```

或者只查看代码示例：

```bash
python tools/run_ast_analysis.py --code-only
```

### 在完整流程中使用

在运行完整的分析流程时，AST分析将自动执行：

```bash
python main.py
```

说明：AST 分析默认只对“疑似修复类提交（subject 命中 fix/security/bug 等关键词）”做扫描，以控制性能。

## 实现细节

### ASTAnalyzer类

位于`src/analysis_core/ast_analyzer.py`，提供了以下功能：

- 解析Python代码为AST
- 访问AST节点并提取模式
- 计算代码复杂度
- 检测安全相关模式

### 与CommitAnalyzer集成

`src/analysis_core/commit_analyzer.py`中的`_perform_ast_analysis`方法将AST分析结果与提交数据相结合：

- 对每个候选 commit，通过 `git show <sha>:<path>` 读取该 commit 版本的源码
- 运行 ASTAnalyzer 识别危险模式（如 `eval/exec`、`os.system`、`subprocess.*(shell=True)`、`pickle.loads` 等）
- 按月聚合趋势与 Top patterns

- 分析的提交数量/文件数量
- 危险模式命中次数（总计、按月）
- Top patterns（整体）

### 报告生成

`src/visualization/report_builder.py`将AST分析结果整合到最终报告中，包括：

- 分析的提交数
- 检测到的安全问题
- 代码复杂度统计
- 常见模式列表

## 输出示例（单文件）

AST分析会生成以下类型的输出：

```json
{
  "patterns_found": ["danger_eval"],
  "security_issues_potential": 1,
  "complexity_score": 3,
  "function_count": 1,
  "class_count": 0,
  "import_count": 1,
  "file_path": "example.py"
}
```

## 注意事项

1. AST分析目前仅支持Python代码
2. 对于非Python代码，分析器将返回空结果
3. 为了获得最佳效果，建议在运行AST分析之前先获取足够的提交数据
4. AST分析可能会增加整体分析时间，特别是在处理大量提交时
5. 可通过环境变量限制分析规模：
  - `PILLOW_AST_MAX_COMMITS`（默认 300）
  - `PILLOW_AST_MAX_FILES_PER_COMMIT`（默认 30）