# -*- coding: utf-8 -*-
"""
项目自检脚本（Self Check）

用法：
  1) 在项目根目录执行：
     python -m self_check.self_check
  2) 或直接执行：
     python self_check/self_check.py

常用参数：
  --strict        任意检查失败则退出码=1（适合 CI 或脚本调用）
  --no-network    跳过网络 & GitHub API 检查（公司/校园网环境常用）
  --run-check-https  额外运行 tools/check_https.py（如果存在）
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# -----------------------------
# 基础配置与工具函数
# -----------------------------

# 项目根目录：self_check/self_check.py 的上两级目录
PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass
class CheckResult:
    """
    单项检查结果结构体
    - name: 检查项名称
    - ok: 是否通过
    - details: 结果详情（给人看）
    - fix: 修复建议（给人看）
    """
    name: str
    ok: bool
    details: str = ""
    fix: str = ""
    # severity is informational; exit code is still driven by `ok` and strict/core rules.
    severity: str = "PASS"  # PASS | WARN | FAIL


def _warn(name: str, details: str = "", fix: str = "") -> CheckResult:
    return CheckResult(name=name, ok=True, details=details, fix=fix, severity="WARN")


def _fail(name: str, details: str = "", fix: str = "") -> CheckResult:
    return CheckResult(name=name, ok=False, details=details, fix=fix, severity="FAIL")


def _pass(name: str, details: str = "") -> CheckResult:
    return CheckResult(name=name, ok=True, details=details, severity="PASS")


def _run_cmd(cmd: List[str], cwd: Optional[Path] = None, timeout: int = 30) -> Tuple[int, str]:
    """
    执行命令行命令并返回 (退出码, 输出文本)
    - 统一合并 stdout/stderr，方便输出给用户排查
    - timeout 防止命令卡死
    """
    try:
        p = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
        )
        return p.returncode, p.stdout.strip()
    except FileNotFoundError as e:
        # 例如 git 未安装/不在 PATH
        return 127, f"Command not found: {cmd[0]} ({e})"
    except subprocess.TimeoutExpired:
        return 124, f"Timeout after {timeout}s: {' '.join(cmd)}"
    except Exception as e:
        return 1, f"Failed to run {' '.join(cmd)}: {e}"


def _safe_rel(p: Path) -> str:
    """
    尽量把路径显示为相对项目根目录的形式，方便阅读。
    如果无法相对，则返回绝对路径。
    """
    try:
        return str(p.relative_to(PROJECT_ROOT))
    except Exception:
        return str(p)


def _load_py_settings(py_file: Path) -> Dict[str, Any]:
    """
    读取 config/local_settings.py 这类 python 配置文件，返回其中变量字典。
    注意：这里使用 exec 载入，不依赖项目包 import。
    """
    ns: Dict[str, Any] = {}
    code = py_file.read_text(encoding="utf-8", errors="replace")
    exec(compile(code, str(py_file), "exec"), ns, ns)
    # 过滤掉 __xxx__ 变量
    return {k: v for k, v in ns.items() if not k.startswith("__")}


def _mkdir_and_test_write(dir_path: Path) -> Tuple[bool, str]:
    """
    确保目录存在，并测试是否可写（创建临时文件再删除）。
    目的：避免项目运行到一半才发现 outputs/data 目录无权限。
    """
    try:
        dir_path.mkdir(parents=True, exist_ok=True)
        test_file = dir_path / ".write_test.tmp"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink(missing_ok=True)
        return True, f"Writable: {_safe_rel(dir_path)}"
    except Exception as e:
        return False, f"Not writable: {_safe_rel(dir_path)} ({e})"


def _parse_requirements(req_file: Path) -> List[str]:
    """
    解析 requirements.txt 里的包名（best-effort）
    - 跳过空行/注释
    - 跳过 -r / -e / -- 这类特殊指令
    - 提取每行开头的包名
    """
    pkgs: List[str] = []
    if not req_file.exists():
        return pkgs
    for line in req_file.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # requirements 的特殊指令（-r other.txt / -e git+... / --find-links ...）
        if line.startswith(("-", "--")):
            continue
        # 提取包名（允许 pep508 extras）
        m = re.match(r"^\s*([A-Za-z0-9_.-]+)", line)
        if m:
            pkgs.append(m.group(1))
    return pkgs


def _check_import(pkg: str) -> Tuple[bool, str]:
    """
    通过 import 来验证依赖是否安装/可用
    """
    try:
        __import__(pkg)
        return True, f"import {pkg} OK"
    except Exception as e:
        return False, f"import {pkg} FAILED: {e}"


# -----------------------------
# 各项检查逻辑
# -----------------------------

def check_python_version(min_major: int = 3, min_minor: int = 8) -> CheckResult:
    """
    检查 Python 版本是否满足最低要求（默认 >= 3.8）
    """
    v = sys.version_info
    ok = (v.major, v.minor) >= (min_major, min_minor)
    details = f"Python: {v.major}.{v.minor}.{v.micro} ({platform.python_implementation()})"
    fix = f"Use Python >= {min_major}.{min_minor}."
    if ok:
        return _pass("Python version", details)
    return _fail("Python version", details, fix)


def check_project_layout() -> CheckResult:
    """
    检查项目关键文件/目录是否存在，防止用户不在正确目录运行或项目结构缺失
    """
    must_exist = [
        PROJECT_ROOT / "config",
        PROJECT_ROOT / "src",
        PROJECT_ROOT / "tools",
        PROJECT_ROOT / "main.py",
        PROJECT_ROOT / "requirements.txt",
    ]
    missing = [p for p in must_exist if not p.exists()]
    ok = len(missing) == 0
    details = "OK" if ok else "Missing: " + ", ".join(_safe_rel(p) for p in missing)
    fix = "Please ensure you're running self_check inside the repository root, and files are not deleted."
    if ok:
        return _pass("Project layout", details)
    return _fail("Project layout", details, fix)


def check_local_settings() -> Tuple[CheckResult, Dict[str, Any]]:
    """
    检查 config/local_settings.py 是否存在并包含关键字段
    README 通常要求：
      复制 config/local_settings.py.example -> config/local_settings.py
      至少填写：
        PILLOW_REPO_PATH
        GITHUB_REPO
    """
    example = PROJECT_ROOT / "config" / "local_settings.py.example"
    local = PROJECT_ROOT / "config" / "local_settings.py"

    if not example.exists():
        # 模板缺失：属于异常情况（不一定致命，但很可疑）
        return (
            _fail(
                "local_settings template",
                f"Missing: {_safe_rel(example)}",
                "Restore config/local_settings.py.example from repo.",
            ),
            {},
        )

    if not local.exists():
        # local_settings 未创建：给出清晰的“怎么修”
        fix = textwrap.dedent(
            f"""\
            Create local settings:
              1) Copy {_safe_rel(example)} -> {_safe_rel(local)}
              2) Edit {_safe_rel(local)} and set at least:
                 - PILLOW_REPO_PATH = r'...'
                 - GITHUB_REPO = 'python-pillow/Pillow'
            """
        ).strip()
        return (_fail("config/local_settings.py", "Not found", fix), {})

    try:
        cfg = _load_py_settings(local)
    except Exception as e:
        # 配置文件语法错误时，exec 会失败
        return (
            _fail(
                "config/local_settings.py",
                f"Failed to load: {e}",
                "Fix python syntax errors in config/local_settings.py.",
            ),
            {},
        )

    required = ["PILLOW_REPO_PATH", "GITHUB_REPO"]
    missing_keys = [k for k in required if not cfg.get(k)]
    ok = len(missing_keys) == 0
    details = "OK" if ok else "Missing/empty keys: " + ", ".join(missing_keys)
    fix = (
        "Edit config/local_settings.py and set required fields (README requires at least PILLOW_REPO_PATH and GITHUB_REPO)."
        if not ok
        else ""
    )
    if ok:
        return (_pass("config/local_settings.py keys", details), cfg)
    return (_fail("config/local_settings.py keys", details, fix), cfg)


def check_pillow_repo_path(cfg: Dict[str, Any]) -> CheckResult:
    """
    检查 PILLOW_REPO_PATH 配置：
    - 是否填写
    - 路径是否存在
    - 是否看起来是一个 git 仓库（至少包含 .git 目录）
    """
    p = cfg.get("PILLOW_REPO_PATH")
    if not p:
        return _fail(
            "PILLOW_REPO_PATH",
            "Not set",
            "Set PILLOW_REPO_PATH in config/local_settings.py to your local clone path of python-pillow/Pillow.",
        )

    repo_path = Path(str(p)).expanduser()
    if not repo_path.exists():
        return _fail(
            "PILLOW_REPO_PATH",
            f"Path not found: {repo_path}",
            "Ensure the path exists and points to your local Pillow repo clone.",
        )

    git_dir = repo_path / ".git"
    ok = git_dir.exists()
    details = f"Found: {repo_path}" + (" (looks like a git repo)" if ok else " (missing .git)")
    fix = "PILLOW_REPO_PATH should point to a git clone of Pillow (directory containing .git)." if not ok else ""
    if ok:
        return _pass("PILLOW_REPO_PATH validity", details)
    return _fail("PILLOW_REPO_PATH validity", details, fix)


def check_outputs_dirs() -> List[CheckResult]:
    """
    检查/创建项目输出目录，并验证可写：
    - data/processed
    - outputs/charts
    - outputs/reports
    """
    targets = [
        PROJECT_ROOT / "data" / "processed",
        PROJECT_ROOT / "outputs" / "charts",
        PROJECT_ROOT / "outputs" / "reports",
    ]
    results: List[CheckResult] = []
    for d in targets:
        ok, msg = _mkdir_and_test_write(d)
        results.append(
            CheckResult(
                f"Writable dir: {_safe_rel(d)}",
                ok,
                msg,
                "Check permissions / disk space, or choose a writable workspace." if not ok else "",
                "PASS" if ok else "FAIL",
            )
        )
    return results


def check_requirements_imports() -> List[CheckResult]:
    """
    根据 requirements.txt 逐个尝试 import，判断依赖是否安装齐全。
    注意：包名与 import 名可能不同，因此做了少量 alias 映射（best-effort）。
    """
    req_file = PROJECT_ROOT / "requirements.txt"
    pkgs = _parse_requirements(req_file)
    if not pkgs:
        return [_fail("requirements.txt", "No requirements parsed", "Check requirements.txt format/existence.")]

    alias = {
        # 常见“安装名 != import 名”的情况
        "PyYAML": "yaml",
        "python-dateutil": "dateutil",
        "beautifulsoup4": "bs4",
        "scikit-learn": "sklearn",
    }

    results: List[CheckResult] = []
    all_ok = True
    missing: List[str] = []

    for pkg in pkgs:
        imp = alias.get(pkg, pkg)
        ok, msg = _check_import(imp)
        all_ok = all_ok and ok
        if not ok:
            missing.append(pkg)
        results.append(
            CheckResult(
                f"Dependency import: {pkg}",
                ok,
                msg,
                "Install deps: python -m pip install -r requirements.txt" if not ok else "",
                "PASS" if ok else "FAIL",
            )
        )

    # 汇总项：让用户一眼看到是否“整体缺依赖”
    if not all_ok:
        results.insert(
            0,
            _fail(
                "Dependencies overall",
                "Missing imports: " + ", ".join(missing),
                "Run: python -m pip install -r requirements.txt",
            ),
        )
    else:
        results.insert(0, _pass("Dependencies overall", f"{len(pkgs)} packages import OK"))

    return results


def check_git_available() -> CheckResult:
    """
    检查 git 是否可用（很多分析/对比仓库任务会用到 git）
    """
    code, out = _run_cmd(["git", "--version"], cwd=PROJECT_ROOT)
    ok = code == 0
    fix = "Install Git and ensure 'git' is on PATH." if not ok else ""
    if ok:
        return _pass("Git availability", out or "git OK")
    return _fail("Git availability", out or "git --version failed", fix)


def check_local_settings_safety() -> List[CheckResult]:
    """自检：local_settings 是否安全。

    - 如果 config/local_settings.py 被 git 跟踪：FAIL（高风险误提交）
    - 如果文件包含疑似 token/key：WARN（提醒不要外发/不要提交）
    """
    results: List[CheckResult] = []
    local = PROJECT_ROOT / "config" / "local_settings.py"
    if not local.exists():
        return results

    # 1) tracked by git?
    code, out = _run_cmd(["git", "ls-files", "--", str(local)], cwd=PROJECT_ROOT)
    if code == 0 and out.strip():
        results.append(
            _fail(
                "config/local_settings.py tracked",
                f"Tracked by git: {_safe_rel(local)}",
                "Remove it from git index (keep local file):\n"
                "  git rm --cached config/local_settings.py\n"
                "And ensure it is listed in .gitignore.",
            )
        )
    else:
        results.append(_pass("config/local_settings.py tracked", "Not tracked by git"))

    # 2) token-like patterns
    try:
        text = local.read_text(encoding="utf-8", errors="replace")
        patterns = {
            "github_token": r"\b(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b",
            "generic_token": r"\b(token|api[_-]?key|secret)\b\s*=\s*['\"][^'\"]{12,}['\"]",
        }
        hits = [name for name, pat in patterns.items() if re.search(pat, text, flags=re.IGNORECASE)]
        if hits:
            results.append(
                _warn(
                    "config/local_settings.py secrets",
                    f"Potential secret patterns found: {', '.join(hits)}",
                    "Make sure config/local_settings.py is not committed and do not share it. "
                    "Prefer using environment variables for tokens.",
                )
            )
        else:
            results.append(_pass("config/local_settings.py secrets", "No obvious token patterns"))
    except Exception as e:
        results.append(_warn("config/local_settings.py secrets", f"Cannot scan file: {e}"))

    return results


def check_ast_coverage() -> List[CheckResult]:
    """自检：AST 分析覆盖率与跳过原因（非阻断）。"""
    results: List[CheckResult] = []
    analysis_json = PROJECT_ROOT / "outputs" / "analysis_results.json"
    if not analysis_json.exists():
        return results

    try:
        data = json.loads(analysis_json.read_text(encoding="utf-8", errors="replace"))
        commit = data.get('commit') if isinstance(data, dict) else None
        if not isinstance(commit, dict):
            return results
        asts = commit.get('ast_analysis_summary')
        if not isinstance(asts, dict):
            return results
        if not asts.get('enabled'):
            msg = asts.get('message') or 'disabled'
            results.append(_warn('AST coverage', f"AST disabled: {msg}", "Set PILLOW_REPO_PATH to a local Pillow git clone."))
            return results

        candidates_total = int(asts.get('candidates_total') or 0)
        selected_commits = int(asts.get('selected_commits') or 0)
        analyzed_commits = int(asts.get('analyzed_commits') or 0)
        analyzed_files = int(asts.get('analyzed_files') or 0)
        skipped_no_files = int(asts.get('skipped_no_files_listed') or 0)
        skipped_no_py = int(asts.get('skipped_no_python_files') or 0)
        strategy = str(asts.get('sample_strategy') or '')

        details = (
            f"strategy={strategy}; candidates={candidates_total}; selected={selected_commits}; "
            f"analyzed_commits={analyzed_commits}; analyzed_files={analyzed_files}; "
            f"skipped_no_files={skipped_no_files}; skipped_no_python={skipped_no_py}"
        )

        # Heuristics: warn if analysis is tiny compared to selected
        if selected_commits >= 200 and analyzed_commits < max(50, int(0.1 * selected_commits)):
            results.append(
                _warn(
                    'AST coverage',
                    details,
                    "Many selected commits were skipped. Common reasons: commits without file lists, or no .py files. "
                    "Try increasing max commits and/or include tests in analysis (future option), and ensure git can read commit file lists.",
                )
            )
        elif selected_commits > 0 and (skipped_no_py / max(1, selected_commits)) >= 0.5:
            results.append(
                _warn(
                    'AST coverage',
                    details,
                    "High 'no python files' ratio. This is expected if many fixes touch C/docs/CI. "
                    "If you want more Python coverage, consider including Tests/ in future.",
                )
            )
        else:
            results.append(_pass('AST coverage', details))
    except Exception as e:
        results.append(_warn('AST coverage', f"Failed to parse outputs/analysis_results.json: {e}"))

    return results


def check_artifact_consistency() -> List[CheckResult]:
    """自检：主流程产物一致性（非阻断）。

    - outputs/analysis_results.json 与 outputs/charts/* 和 outputs/reports/pillow_report.md 的时间顺序
    - 若存在 outputs/reports/analysis_results.json，提示用户避免混淆
    """
    results: List[CheckResult] = []

    analysis_json = PROJECT_ROOT / "outputs" / "analysis_results.json"
    report = PROJECT_ROOT / "outputs" / "reports" / "pillow_report.md"
    charts_dir = PROJECT_ROOT / "outputs" / "charts"
    alt_analysis = PROJECT_ROOT / "outputs" / "reports" / "analysis_results.json"

    if alt_analysis.exists():
        results.append(
            _warn(
                'Duplicate analysis_results.json',
                f"Found: {_safe_rel(alt_analysis)}",
                "Canonical file is outputs/analysis_results.json. Consider deleting the duplicate to avoid confusion.",
            )
        )

    if not analysis_json.exists():
        return results

    try:
        a_mtime = analysis_json.stat().st_mtime
    except Exception as e:
        return results + [_warn('Artifact consistency', f"Cannot stat analysis json: {e}")]

    # Report should not be older than analysis (main writes analysis then report)
    if report.exists():
        try:
            r_mtime = report.stat().st_mtime
            if r_mtime + 1 < a_mtime:
                results.append(
                    _warn(
                        'Artifact consistency',
                        f"Report appears older than analysis json: {_safe_rel(report)}",
                        'Re-run: python main.py (ensure you are looking at the latest outputs).',
                    )
                )
            else:
                results.append(_pass('Artifact consistency (report)', 'Report is consistent with analysis json'))
        except Exception as e:
            results.append(_warn('Artifact consistency (report)', f"Cannot stat report: {e}"))

    # At least one chart should be newer than analysis (charts generated after analysis)
    if charts_dir.exists():
        try:
            charts = list(charts_dir.glob('*.png'))
            if charts:
                newest = max((p.stat().st_mtime for p in charts), default=0)
                if newest + 1 < a_mtime:
                    results.append(
                        _warn(
                            'Artifact consistency (charts)',
                            'Charts appear older than analysis json.',
                            'Re-run: python main.py; ensure charts are refreshed.',
                        )
                    )
                else:
                    results.append(_pass('Artifact consistency (charts)', f"{len(charts)} charts look consistent"))
        except Exception as e:
            results.append(_warn('Artifact consistency (charts)', f"Cannot inspect charts: {e}"))

    return results


def check_network_and_github(cfg: Dict[str, Any], timeout: int = 8) -> List[CheckResult]:
    """
    可选网络检查：
    1) 能否访问 GitHub API（https://api.github.com）
    2) GitHub API rate limit 是否可用（并提示 token 是否生效）
    3) GITHUB_REPO 格式是否正确（owner/repo）
    """
    results: List[CheckResult] = []

    # Use requests so that proxy/CA settings (HTTP_PROXY/HTTPS_PROXY/CA_BUNDLE) take effect.
    try:
        import requests
    except Exception as e:
        return [_warn("Network checks", f"requests not available, skipping network checks: {e}")]

    http_proxy = cfg.get('HTTP_PROXY') or os.getenv('HTTP_PROXY') or ''
    https_proxy = cfg.get('HTTPS_PROXY') or os.getenv('HTTPS_PROXY') or ''
    ca_bundle = cfg.get('CA_BUNDLE') or os.getenv('REQUESTS_CA_BUNDLE') or ''

    s = requests.Session()
    if http_proxy or https_proxy:
        s.proxies.update({k: v for k, v in {'http': http_proxy, 'https': https_proxy}.items() if v})
    if ca_bundle:
        s.verify = ca_bundle

    # 1) 基础 HTTPS 连通性
    try:
        r = s.get('https://api.github.com/rate_limit', timeout=timeout, headers={'User-Agent': 'self_check'})
        ok = (r.status_code == 200)
        if ok:
            results.append(_pass('HTTPS to api.github.com', f'status={r.status_code}'))
        else:
            results.append(_fail('HTTPS to api.github.com', f'status={r.status_code}', 'Check proxy/CA settings.'))
            return results
    except Exception as e:
        results.append(
            _fail(
                'HTTPS to api.github.com',
                f'Failed: {e}',
                'Network blocked or proxy/CA not configured. '
                '(See README: HTTP_PROXY/HTTPS_PROXY/REQUESTS_CA_BUNDLE and tools/check_https.py.)',
            )
        )
        return results

    # 2) GitHub API 限额检查（可选 token）
    token = cfg.get("GITHUB_TOKEN")
    headers = {"User-Agent": "self_check"}
    if token:
        headers["Authorization"] = f"token {token}"

    try:
        r = s.get('https://api.github.com/rate_limit', timeout=timeout, headers=headers)
        data = r.json() if r.headers.get('content-type', '').startswith('application/json') else {}

        core = data.get("resources", {}).get("core", {})
        remaining = core.get("remaining")
        limit = core.get("limit")
        reset = core.get("reset")

        ok = isinstance(remaining, int) and remaining >= 1
        details = f"rate_limit core remaining={remaining}/{limit}, reset_epoch={reset}, auth={'yes' if token else 'no'}"
        fix = "Set GITHUB_TOKEN in config/local_settings.py to increase API quota." if not token else ""
        if ok:
            results.append(_pass('GitHub API rate limit', details))
        else:
            results.append(_warn('GitHub API rate limit', details, fix))
    except Exception as e:
        results.append(_warn('GitHub API rate limit', f'Failed: {e}', 'Check token validity or network.'))

    # 3) 校验 GITHUB_REPO 格式
    repo = cfg.get("GITHUB_REPO")
    if repo:
        ok = bool(re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", str(repo)))
        if ok:
            results.append(_pass('GITHUB_REPO format', f'GITHUB_REPO={repo}'))
        else:
            results.append(_fail('GITHUB_REPO format', f'GITHUB_REPO={repo}', "Set GITHUB_REPO like 'python-pillow/Pillow'."))

    return results


def check_tools_check_https() -> CheckResult:
    """
    尝试运行 tools/check_https.py（如果项目里有这个脚本）
    目的：让用户按 README 建议快速定位代理/证书/HTTPS 问题。
    """
    script = PROJECT_ROOT / "tools" / "check_https.py"
    if not script.exists():
        return _warn(
            "tools/check_https.py",
            "Not found",
            "If you want network self-check, add/restore tools/check_https.py.",
        )

    code, out = _run_cmd([sys.executable, str(script)], cwd=PROJECT_ROOT, timeout=40)
    ok = code == 0
    # 输出过长会影响阅读，这里截断最后 800 字符
    if ok:
        return _pass("Run tools/check_https.py", out[-800:] if out else "OK")
    return _fail(
        "Run tools/check_https.py",
        out[-800:] if out else f"exit_code={code}",
        "See output above; fix proxy/CA/network issues.",
    )


def _load_json_file(path: Path) -> Tuple[bool, Any, str]:
    try:
        data = json.loads(path.read_text(encoding='utf-8', errors='replace'))
        return True, data, ''
    except Exception as e:
        return False, None, str(e)


def check_processed_data_sanity() -> List[CheckResult]:
    """Validate current pipeline inputs under data/processed.

    - commits_all is required for main.py
    - bugs/cves are optional (warn if missing/empty)
    """
    results: List[CheckResult] = []
    processed = PROJECT_ROOT / 'data' / 'processed'

    commits_path = processed / 'pillow_commits_all.json'
    if not commits_path.exists():
        results.append(
            _fail(
                'Processed commits JSON',
                f'Missing: {_safe_rel(commits_path)}',
                'Run: python tools\\run_crawl_commits.py',
            )
        )
        return results

    ok, data, err = _load_json_file(commits_path)
    if not ok:
        results.append(_fail('Processed commits JSON', f'Invalid JSON: {err}', 'Re-generate commits JSON.'))
        return results
    if not isinstance(data, list) or not data:
        results.append(_fail('Processed commits JSON', 'Empty or not a list', 'Re-generate commits JSON.'))
        return results

    # Basic schema checks (sample to avoid heavy cost)
    sample = data[:200] if len(data) > 200 else data
    missing_hash = sum(1 for c in sample if not isinstance(c, dict) or not c.get('hash'))
    missing_date = sum(1 for c in sample if not isinstance(c, dict) or not c.get('date'))
    missing_subject = sum(1 for c in sample if not isinstance(c, dict) or c.get('subject') in (None, ''))
    if missing_hash or missing_date:
        results.append(
            _fail(
                'Commits schema',
                f'sample_size={len(sample)} missing_hash={missing_hash} missing_date={missing_date} missing_subject={missing_subject}',
                'Ensure git crawler outputs hash/date/subject fields correctly.',
            )
        )
    else:
        results.append(_pass('Processed commits JSON', f'commits={len(data)} (sample checked)'))

    # Numstat sanity: detect the classic "all zeros" bug/regression.
    numstat_fields = ['insertions', 'deletions', 'files_changed']
    nonzero = 0
    for c in sample:
        if not isinstance(c, dict):
            continue
        s = 0
        for f in numstat_fields:
            v = c.get(f)
            if isinstance(v, int):
                s += v
            elif isinstance(v, str) and v.isdigit():
                s += int(v)
        if s > 0:
            nonzero += 1
    if nonzero == 0:
        results.append(
            _warn(
                'Change size sanity',
                f'sample_size={len(sample)} nonzero_numstat=0',
                'All numstat fields are zero in sample. If this is unexpected, check git log --numstat parsing; also merges often have empty numstat (use --no-merges or --first-parent).',
            )
        )
    else:
        results.append(_pass('Change size sanity', f'sample_size={len(sample)} nonzero_numstat={nonzero}'))

    # Optional bugs
    bugs_path = processed / 'pillow_bug_issues.json'
    if not bugs_path.exists():
        results.append(_warn('Processed bug issues JSON', f'Missing: {_safe_rel(bugs_path)}', 'If you need bug metrics, run: python tools\\run_collect_bugs.py --since 2020-01-01'))
    else:
        ok, bugs, err = _load_json_file(bugs_path)
        if (not ok) or (not isinstance(bugs, list)):
            results.append(_warn('Processed bug issues JSON', f'Invalid JSON/list: {err}', 'Re-generate bug issues JSON.'))
        elif not bugs:
            results.append(_warn('Processed bug issues JSON', 'File exists but empty', 'Re-run bug collection with correct repo/token/time range.'))
        else:
            results.append(_pass('Processed bug issues JSON', f'issues={len(bugs)}'))

    # Optional CVEs
    cves_path = processed / 'pillow_cves_with_commits.json'
    if not cves_path.exists():
        results.append(_warn('Processed CVE JSON', f'Missing: {_safe_rel(cves_path)}', 'If you need CVE metrics, run: python tools\\run_collect.py ; python tools\\run_link_commits.py'))
    else:
        ok, cves, err = _load_json_file(cves_path)
        if (not ok) or (not isinstance(cves, list)):
            results.append(_warn('Processed CVE JSON', f'Invalid JSON/list: {err}', 'Re-generate CVE JSON.'))
        elif not cves:
            results.append(_warn('Processed CVE JSON', 'File exists but empty', 'Re-run CVE collection/linking.'))
        else:
            # quick schema check for current analyzer expectations
            sample_cves = cves[:50] if len(cves) > 50 else cves
            missing_id = sum(1 for x in sample_cves if not isinstance(x, dict) or not x.get('id'))
            missing_published = sum(1 for x in sample_cves if not isinstance(x, dict) or not x.get('published'))
            if missing_id:
                results.append(_warn('CVE schema', f'sample_size={len(sample_cves)} missing_id={missing_id}', 'Ensure CVE collector outputs id field.'))
            else:
                results.append(_pass('Processed CVE JSON', f'cves={len(cves)} (sample checked)'))
            if missing_published:
                results.append(_warn('CVE timeline fields', f'sample_size={len(sample_cves)} missing_published={missing_published}', 'Published date missing may affect monthly CVE charts.'))

    return results


def check_output_artifacts() -> List[CheckResult]:
    """Non-blocking checks for expected outputs."""
    results: List[CheckResult] = []
    charts_dir = PROJECT_ROOT / 'outputs' / 'charts'
    reports_dir = PROJECT_ROOT / 'outputs' / 'reports'
    report = reports_dir / 'pillow_report.md'

    if charts_dir.exists():
        pngs = list(charts_dir.glob('*.png'))
        if not pngs:
            results.append(_warn('Charts outputs', f'No PNG found under {_safe_rel(charts_dir)}', 'Run: python main.py'))
        else:
            results.append(_pass('Charts outputs', f'png_count={len(pngs)}'))
    else:
        results.append(_warn('Charts outputs', f'Missing dir: {_safe_rel(charts_dir)}', 'Run: python main.py'))

    if report.exists():
        try:
            size = report.stat().st_size
            if size <= 50:
                results.append(_warn('Report output', f'{_safe_rel(report)} too small ({size} bytes)', 'Re-run: python main.py ; check console errors.'))
            else:
                results.append(_pass('Report output', f'{_safe_rel(report)} ({size} bytes)'))
        except Exception as e:
            results.append(_warn('Report output', f'Cannot stat report: {e}', 'Check filesystem permissions.'))
    else:
        results.append(_warn('Report output', f'Missing: {_safe_rel(report)}', 'Run: python main.py'))

    return results


# -----------------------------
# 总执行逻辑
# -----------------------------

def run_all(strict: bool, no_network: bool, run_https_tool: bool) -> int:
    """
    运行所有检查项，打印报告，并根据 strict / 核心失败项决定退出码。
    """
    results: List[CheckResult] = []

    # 1) 基础环境类检查
    results.append(check_python_version())
    results.append(check_project_layout())
    results.append(check_git_available())

    # 2) 配置检查（local_settings）
    local_settings_res, cfg = check_local_settings()
    results.append(local_settings_res)

    # 2b) local_settings 安全检查（防误提交/泄露）
    results.extend(check_local_settings_safety())

    # 3) 依赖配置后才能检查 Pillow repo path
    if cfg:
        results.append(check_pillow_repo_path(cfg))

    # 4) 输出目录可写
    results.extend(check_outputs_dirs())

    # 4b) 当前数据口径自检（data/processed）
    results.extend(check_processed_data_sanity())

    # 5) requirements 依赖是否安装
    results.extend(check_requirements_imports())

    # 5b) 输出产物检查（不阻断）
    results.extend(check_output_artifacts())

    # 5c) AST 覆盖率与产物一致性（不阻断）
    results.extend(check_ast_coverage())
    results.extend(check_artifact_consistency())

    # 6) 网络相关检查（可关闭）
    if (not no_network) and cfg:
        results.extend(check_network_and_github(cfg))

    # 7) 可选运行 tools/check_https.py
    if run_https_tool:
        results.append(check_tools_check_https())

    # ----------------- 打印报告 -----------------
    ok_count = sum(1 for r in results if r.ok)
    total = len(results)

    print("=" * 72)
    print("Self Check Report")
    print(f"Project: {PROJECT_ROOT}")
    print(f"Platform: {platform.platform()}  |  Python: {sys.version.splitlines()[0]}")
    print("-" * 72)

    for r in results:
        status = r.severity if r.severity else ("PASS" if r.ok else "FAIL")
        print(f"[{status}] {r.name}")
        if r.details:
            print("  -", r.details)
        if (not r.ok) and r.fix:
            for line in r.fix.splitlines():
                print("  *", line)
        print()

    print("-" * 72)
    print(f"Summary: {ok_count}/{total} checks passed.")
    print("=" * 72)

    # strict：只要有失败就返回 1
    if strict and ok_count != total:
        return 1

    # 非 strict：核心失败项（严重影响运行）才返回 1
    core_fail_names = {
        "Python version",
        "Project layout",
        "Dependencies overall",
        "config/local_settings.py",
        "config/local_settings.py keys",
        "Processed commits JSON",
        "Commits schema",
    }
    core_failed = any((not r.ok) and (r.name in core_fail_names) for r in results)
    return 1 if core_failed else 0


def main(argv: Optional[List[str]] = None) -> int:
    """
    命令行入口：解析参数 -> 执行自检
    """
    parser = argparse.ArgumentParser(description="Self check for pillow_analysis_project")
    parser.add_argument("--strict", action="store_true", help="Any failure makes exit code = 1")
    parser.add_argument("--no-network", action="store_true", help="Skip network & GitHub API checks")
    parser.add_argument("--run-check-https", action="store_true", help="Run tools/check_https.py if exists")
    args = parser.parse_args(argv)
    return run_all(strict=args.strict, no_network=args.no_network, run_https_tool=args.run_check_https)


if __name__ == "__main__":
    # 作为脚本运行时：把退出码抛给系统，方便 CI 判断
    raise SystemExit(main())
