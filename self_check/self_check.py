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
    return CheckResult("Python version", ok, details, fix if not ok else "")


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
    return CheckResult("Project layout", ok, details, fix if not ok else "")


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
            CheckResult(
                "local_settings template",
                False,
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
        return (CheckResult("config/local_settings.py", False, "Not found", fix), {})

    try:
        cfg = _load_py_settings(local)
    except Exception as e:
        # 配置文件语法错误时，exec 会失败
        return (
            CheckResult(
                "config/local_settings.py",
                False,
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
    return (CheckResult("config/local_settings.py keys", ok, details, fix), cfg)


def check_pillow_repo_path(cfg: Dict[str, Any]) -> CheckResult:
    """
    检查 PILLOW_REPO_PATH 配置：
    - 是否填写
    - 路径是否存在
    - 是否看起来是一个 git 仓库（至少包含 .git 目录）
    """
    p = cfg.get("PILLOW_REPO_PATH")
    if not p:
        return CheckResult(
            "PILLOW_REPO_PATH",
            False,
            "Not set",
            "Set PILLOW_REPO_PATH in config/local_settings.py to your local clone path of python-pillow/Pillow.",
        )

    repo_path = Path(str(p)).expanduser()
    if not repo_path.exists():
        return CheckResult(
            "PILLOW_REPO_PATH",
            False,
            f"Path not found: {repo_path}",
            "Ensure the path exists and points to your local Pillow repo clone.",
        )

    git_dir = repo_path / ".git"
    ok = git_dir.exists()
    details = f"Found: {repo_path}" + (" (looks like a git repo)" if ok else " (missing .git)")
    fix = "PILLOW_REPO_PATH should point to a git clone of Pillow (directory containing .git)." if not ok else ""
    return CheckResult("PILLOW_REPO_PATH validity", ok, details, fix)


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
        return [CheckResult("requirements.txt", False, "No requirements parsed", "Check requirements.txt format/existence.")]

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
            )
        )

    # 汇总项：让用户一眼看到是否“整体缺依赖”
    if not all_ok:
        results.insert(
            0,
            CheckResult(
                "Dependencies overall",
                False,
                "Missing imports: " + ", ".join(missing),
                "Run: python -m pip install -r requirements.txt",
            ),
        )
    else:
        results.insert(0, CheckResult("Dependencies overall", True, f"{len(pkgs)} packages import OK"))

    return results


def check_git_available() -> CheckResult:
    """
    检查 git 是否可用（很多分析/对比仓库任务会用到 git）
    """
    code, out = _run_cmd(["git", "--version"], cwd=PROJECT_ROOT)
    ok = code == 0
    fix = "Install Git and ensure 'git' is on PATH." if not ok else ""
    return CheckResult("Git availability", ok, out or "git --version failed", fix)


def check_network_and_github(cfg: Dict[str, Any], timeout: int = 8) -> List[CheckResult]:
    """
    可选网络检查：
    1) 能否访问 GitHub API（https://api.github.com）
    2) GitHub API rate limit 是否可用（并提示 token 是否生效）
    3) GITHUB_REPO 格式是否正确（owner/repo）
    """
    import urllib.request

    results: List[CheckResult] = []

    # 1) 基础 HTTPS 连通性
    try:
        req = urllib.request.Request(
            "https://api.github.com/rate_limit",
            headers={"User-Agent": "self_check"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ok = resp.status == 200
            # 只为确认能读，内容不在此处展开
            _ = resp.read()
        results.append(
            CheckResult(
                "HTTPS to api.github.com",
                ok,
                f"status={resp.status}",
                "" if ok else "Check proxy/CA settings.",
            )
        )
    except Exception as e:
        # 如果连 api.github.com 都访问不了，后续 GitHub 检查没意义
        results.append(
            CheckResult(
                "HTTPS to api.github.com",
                False,
                f"Failed: {e}",
                "Network blocked or proxy/CA not configured. "
                "(See README: HTTP_PROXY/HTTPS_PROXY/REQUESTS_CA_BUNDLE and tools/check_https.py.)",
            )
        )
        return results

    # 2) GitHub API 限额检查（可选 token）
    token = cfg.get("GITHUB_TOKEN")
    headers = {"User-Agent": "self_check"}
    if token:
        headers["Authorization"] = f"token {token}"

    try:
        req = urllib.request.Request("https://api.github.com/rate_limit", headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))

        core = data.get("resources", {}).get("core", {})
        remaining = core.get("remaining")
        limit = core.get("limit")
        reset = core.get("reset")

        ok = isinstance(remaining, int) and remaining >= 1
        details = f"rate_limit core remaining={remaining}/{limit}, reset_epoch={reset}, auth={'yes' if token else 'no'}"
        fix = "Set GITHUB_TOKEN in config/local_settings.py to increase API quota." if not token else ""
        results.append(CheckResult("GitHub API rate limit", ok, details, fix))
    except Exception as e:
        results.append(CheckResult("GitHub API rate limit", False, f"Failed: {e}", "Check token validity or network."))

    # 3) 校验 GITHUB_REPO 格式
    repo = cfg.get("GITHUB_REPO")
    if repo:
        ok = bool(re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", str(repo)))
        results.append(
            CheckResult(
                "GITHUB_REPO format",
                ok,
                f"GITHUB_REPO={repo}",
                "Set GITHUB_REPO like 'python-pillow/Pillow'." if not ok else "",
            )
        )

    return results


def check_tools_check_https() -> CheckResult:
    """
    尝试运行 tools/check_https.py（如果项目里有这个脚本）
    目的：让用户按 README 建议快速定位代理/证书/HTTPS 问题。
    """
    script = PROJECT_ROOT / "tools" / "check_https.py"
    if not script.exists():
        return CheckResult(
            "tools/check_https.py",
            False,
            "Not found",
            "If you want network self-check, add/restore tools/check_https.py.",
        )

    code, out = _run_cmd([sys.executable, str(script)], cwd=PROJECT_ROOT, timeout=40)
    ok = code == 0
    # 输出过长会影响阅读，这里截断最后 800 字符
    return CheckResult(
        "Run tools/check_https.py",
        ok,
        out[-800:] if out else f"exit_code={code}",
        "" if ok else "See output above; fix proxy/CA/network issues.",
    )


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

    # 3) 依赖配置后才能检查 Pillow repo path
    if cfg:
        results.append(check_pillow_repo_path(cfg))

    # 4) 输出目录可写
    results.extend(check_outputs_dirs())

    # 5) requirements 依赖是否安装
    results.extend(check_requirements_imports())

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
        status = "PASS" if r.ok else "FAIL"
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
    core_fail_names = {"Python version", "Project layout", "Dependencies overall", "config/local_settings.py"}
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
