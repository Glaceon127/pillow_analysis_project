"""抓取 Git 提交历史的轻量实现。

实现要点：
- 使用系统的 `git`（需安装）通过 `subprocess` 调用，避免额外依赖。
- 解析 `git log` 的自定义输出（使用不可见分隔符）为 Python 字典列表。

每个返回的提交为 dict:
    {
        'hash': ..., 'author_name': ..., 'author_email': ...,
        'date': ..., 'subject': ...,
        'files': [...],
        'files_changed': int,
        'insertions': int,
        'deletions': int,
    }

示例用法见模块底部的 `__main__`。
"""

from __future__ import annotations

import os
import subprocess
from typing import List, Dict, Optional


class GitCrawler:
    def __init__(self, git_executable: str = "git"):
        """初始化 GitCrawler。

        Args:
            git_executable: 如果系统 git 不在 PATH，可传入完整路径。
        """
        self.git = git_executable

    def _run_git(self, repo_path: str, args: List[str]) -> subprocess.CompletedProcess:
        """Run a git command in the given repo and return the CompletedProcess.

        This is the single place where we call subprocess for git.
        """
        return subprocess.run(
            [self.git, '-C', repo_path] + args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
        )

    def commit_exists(self, repo_path: str, sha: str) -> bool:
        """Check if a commit object exists in the repo."""
        if not sha:
            return False
        proc = self._run_git(repo_path, ['cat-file', '-e', f'{sha}^{{commit}}'])
        return proc.returncode == 0

    def grep_commits(self, repo_path: str, pattern: str, max_hits: int = 20) -> List[str]:
        """Search commits by message pattern and return matching commit hashes."""
        if not pattern:
            return []
        proc = self._run_git(
            repo_path,
            [
                'log',
                '-n',
                str(max_hits),
                '--pretty=format:%H',
                '--grep',
                pattern,
                '--regexp-ignore-case',
            ],
        )
        if proc.returncode != 0:
            return []
        out = (proc.stdout or '').strip()
        if not out:
            return []
        return [ln.strip() for ln in out.splitlines() if ln.strip()]

    def _is_git_repo(self, repo_path: str) -> bool:
        try:
            subprocess.run([self.git, '-C', repo_path, 'rev-parse', '--is-inside-work-tree'],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def crawl(
        self,
        repo_path: str,
        since: Optional[str] = None,
        until: Optional[str] = None,
        max_commits: Optional[int] = None,
        save_path: Optional[str] = None,
        grep: Optional[str] = None,
        no_merges: bool = False,
        first_parent: bool = False,
    ) -> List[Dict]:
        """抓取并解析指定仓库的提交历史。

        Args:
            repo_path: 本地仓库路径（必须已 clone）。
            since: 可选的 git --since 参数（例如 '2020-01-01' 或 '2 weeks ago'）。
            until: 可选的 git --until 参数。
            max_commits: 可选的最多返回提交数量（对应 git -n）。

        Returns:
            列表，每项为提交信息字典（见模块顶部说明）。

        Raises:
            FileNotFoundError: repo_path 不存在。
            ValueError: 指定路径不是一个 git 仓库。
            subprocess.CalledProcessError: git 调用失败时抛出（上层可捕获）。
        """
        if not os.path.isdir(repo_path):
            raise FileNotFoundError(f"repo path not found: {repo_path}")

        if not self._is_git_repo(repo_path):
            raise ValueError(f"not a git repository: {repo_path}")

        # 使用不可见字符作为字段分隔，方便解析；不要使用“记录分隔”来 split，
        # 因为 --numstat 的输出在 commit header 之后，split 会把 numstat 行切碎。
        field_sep = "\x1f"  # unit separator
        fmt = f"%H{field_sep}%an{field_sep}%ae{field_sep}%ad{field_sep}%s"

        cmd = [self.git, '-C', repo_path, 'log', f'--pretty=format:{fmt}', '--date=iso']
        if first_parent:
            cmd += ['--first-parent']
        if no_merges:
            cmd += ['--no-merges']
        if since:
            cmd += ['--since', since]
        if until:
            cmd += ['--until', until]
        if max_commits:
            cmd += ['-n', str(max_commits)]
        if grep:
            # Filter commits whose message matches grep (git will search full commit message)
            cmd += ['--grep', grep, '--regexp-ignore-case']
        # 使用 numstat：输出每个文件的增删行数（不受本地语言影响），便于统计变更规模
        # 格式为：<insertions>\t<deletions>\t<path>，二进制文件为 -\t-\t<path>
        cmd += ['--numstat']

        proc = subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
        )
        out = proc.stdout

        commits: List[Dict] = []
        if not out:
            return commits

        # 逐行扫描：遇到 header 行（包含 field_sep）开始新提交；后续行解析 numstat。
        current: Optional[Dict] = None

        def finalize_current() -> None:
            nonlocal current
            if current is None:
                return
            commits.append(current)
            current = None

        for raw_line in out.splitlines():
            line = raw_line.strip('\r\n')
            if not line.strip():
                continue

            if field_sep in line:
                # commit header
                parts = line.split(field_sep)
                if len(parts) < 5:
                    continue
                finalize_current()
                commit_hash, author_name, author_email, date, subject = parts[:5]
                current = {
                    'hash': commit_hash,
                    'author_name': author_name,
                    'author_email': author_email,
                    'date': date,
                    'subject': subject,
                    'files': [],
                    'files_changed': 0,
                    'insertions': 0,
                    'deletions': 0,
                }
                continue

            # numstat line for current commit
            if current is None:
                continue

            parts = line.split('\t')
            if len(parts) < 3:
                continue
            ins_s, del_s = parts[0], parts[1]
            path = '\t'.join(parts[2:]).strip()
            current['files_changed'] += 1
            if path:
                current['files'].append(path)
            if ins_s.isdigit():
                current['insertions'] += int(ins_s)
            if del_s.isdigit():
                current['deletions'] += int(del_s)

        finalize_current()

        # 如果需要，默认保存到 data/processed/pillow_commits.json
        if save_path is None:
            base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
            save_path = os.path.join(base, 'data', 'processed', 'pillow_commits.json')

        try:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            import json
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(commits, f, ensure_ascii=False, indent=2)
        except Exception:
            # 保存失败不影响返回
            pass

        return commits


if __name__ == '__main__':
    # 简易命令行示例：python git_crawler.py <repo_path> [max_commits]
    import sys

    if len(sys.argv) < 2:
        print('Usage: python git_crawler.py <repo_path> [max_commits]')
        sys.exit(1)

    path = sys.argv[1]
    maxc = int(sys.argv[2]) if len(sys.argv) >= 3 else None
    crawler = GitCrawler()
    try:
        commits = crawler.crawl(path, max_commits=maxc)
    except Exception as e:
        print('Error:', e)
        sys.exit(2)

    print(f'Found {len(commits)} commits in {path}')
    if commits:
        first = commits[0]
        print('Most recent commit:')
        print(f"  {first['hash']} {first['date']} {first['author_name']} <{first['author_email']}>")
        print('  Subject:', first['subject'])
