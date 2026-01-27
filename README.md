# Pillow Analysis Project

用 Pillow（python-pillow/Pillow）作为样例项目，输出可复现的「演化节奏」与「Bug 关闭规律」指标，并可选做 CVE 采集与漏洞-提交关联。

本项目的数据产物主要是 JSON（`data/processed/*.json`），最终输出为图表（`outputs/charts/*.png`）与 Markdown 报告（`outputs/reports/pillow_report.md`）。

## 一分钟跑通（推荐路径）

- 安装依赖：`python -m pip install -r requirements.txt`

- 配置本机私有配置（不要提交到仓库）：

  - 复制 `config/local_settings.py.example` 为 `config/local_settings.py`
  - 至少填两项：
    - `PILLOW_REPO_PATH = r'F:\\path\\to\\Pillow'`（你本机 clone 的 Pillow 仓库）
    - `GITHUB_REPO = 'python-pillow/Pillow'`
    - （可选）`GITHUB_TOKEN = '...'`（提高 GitHub API 配额）

- 抓取全量提交（演化节奏 + 变更规模）：`python tools\run_crawl_commits.py`

- 抓取 bug issues（bug 关闭规律）：`python tools\run_collect_bugs.py --since 2020-01-01`

- 生成图表与报告：`python main.py`

输出：

- `outputs/charts/`
- `outputs/reports/pillow_report.md`

## 项目结构（简版）

- `config/settings.py`：默认配置（支持环境变量）
- `config/local_settings.py`：本机覆盖配置（在 .gitignore 中）
- `src/data_pipeline/`：抓取与清洗（git / GitHub issues / CVE）
- `src/analysis_core/`：统计分析（commit / issues / vulnerability）
- `src/visualization/`：图表与报告生成
- `tools/`：命令行脚本入口

## 命令行入口（Windows cmd.exe）

- 抓全量提交：`python tools\run_crawl_commits.py`
  - 可选：排除 merge（更适合变更规模统计）：`python tools\run_crawl_commits.py --no-merges`
  - 可选：只看主线（更适合演化节奏）：`python tools\run_crawl_commits.py --first-parent`
- 抓 bug issues：`python tools\run_collect_bugs.py --since 2020-01-01`
- 生成报告：`python main.py`

可选（CVE 方向）：

- 抓取 CVE：`python tools\run_collect.py`
- 关联 CVE↔commit：`python tools\run_link_commits.py`（默认按 CVE 编号/引用信号关联）

可选（网络自检）：`python tools\check_https.py`

## 常见问题

- GitHub 401/403：优先检查 `GITHUB_TOKEN` 是否有效；无 token 会更容易触发匿名限流。
- 公司/校园网络：可用 `HTTP_PROXY/HTTPS_PROXY/REQUESTS_CA_BUNDLE`，并运行 `python tools\check_https.py` 排查。
- cmd.exe 里不要复制形如 `[text](url)` 的 Markdown 链接当命令，会触发参数解析错误；请只复制纯命令。

## 已知限制 / 待完善点（路线图）

- `src/analysis_core/ast_analyzer.py` 目前是占位实现（未接入主流程）；后续可做“修复代码模式/修复热区”的静态分析扩展。
- `git log --numstat` 对 merge commit 默认不给出 diff，因此 merge commit 的变更规模会显示为 0；做变更规模建议 `--no-merges` 或 `--first-parent`。
