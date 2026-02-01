"""提交分析模块。

输入：git_crawler 产出的 commits 列表（data/processed/pillow_commits.json）。
输出：用于可视化/报告的统计信息（纯 dict，可 JSON 化）。
"""

from __future__ import annotations

from collections import Counter
import math
import os
import re
import subprocess
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

# 导入AST分析器
try:
    from .ast_analyzer import ASTAnalyzer
except ImportError:
    ASTAnalyzer = None


class CommitAnalyzer:
    def analyze(self, commits: List[Dict[str, Any]]) -> Dict[str, Any]:
        commits = commits or []
        if not commits:
            return {
                'total_commits': 0,
                'date_min': None,
                'date_max': None,
                'authors_top': [],
                'files_top': [],
                'commits_by_month': [],
                'fix_commits_total': 0,
                'fix_commit_ratio': 0.0,
                'fix_commits_by_month': [],
                'change_size_stats': {
                    'files_changed_total': 0,
                    'insertions_total': 0,
                    'deletions_total': 0,
                    'change_size_total': 0,
                    'change_size_mean': 0.0,
                    'change_size_median': 0.0,
                    'change_size_p90': 0.0,
                },
                'change_size_by_month': [],
                'ast_analysis_summary': {},
            }

        df = pd.DataFrame(commits)
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'], errors='coerce', utc=True)

        # normalize numeric stats (2.2 change size)
        for col in ['files_changed', 'insertions', 'deletions']:
            if col not in df.columns:
                df[col] = 0
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
        df['change_size'] = (df['insertions'] + df['deletions']).astype(int)

        # classify fix commits (2.1 fix ratio)
        subject = df.get('subject')
        if subject is None:
            df['is_fix'] = False
        else:
            s = subject.fillna('').astype(str)
            fix_re = re.compile(
                r"(\bcve-\d{4}-\d+\b|\bsecurity\b|\bfix(?:e[ds])?\b|\bbug(?:s)?\b|\bdefect(?:s)?\b|\bregress(?:ion|ed)?\b|\bcrash(?:es|ed)?\b|\bhot\s*fix\b|\bpatch\b|\bresolve[sd]?\b|\bcloses?\b)",
                re.IGNORECASE,
            )
            df['is_fix'] = s.map(lambda x: bool(fix_re.search(x)))

        total_commits = int(len(df))
        date_min = df['date'].min() if 'date' in df.columns else None
        date_max = df['date'].max() if 'date' in df.columns else None

        fix_commits_total = int(df['is_fix'].sum()) if 'is_fix' in df.columns else 0
        fix_commit_ratio = float(fix_commits_total / total_commits) if total_commits else 0.0

        # top authors
        authors_top = []
        if 'author_name' in df.columns:
            c = df['author_name'].fillna('').astype(str)
            c = c[c != '']
            authors_top = [{'author': a, 'count': int(n)} for a, n in c.value_counts().head(10).items()]

        # top files
        files_counter: Counter[str] = Counter()
        for files in df.get('files', []):
            if isinstance(files, list):
                files_counter.update([f for f in files if isinstance(f, str) and f])
        files_top = [{'file': f, 'count': int(n)} for f, n in files_counter.most_common(15)]

        # commits by month
        commits_by_month = []
        fix_commits_by_month = []
        change_size_by_month = []
        if 'date' in df.columns and df['date'].notna().any():
            g = df.dropna(subset=['date']).copy()
            g['month'] = g['date'].dt.to_period('M').astype(str)
            bym = g.groupby('month').size().reset_index(name='count').sort_values('month')
            commits_by_month = bym.to_dict(orient='records')

            # fix ratio by month
            fm = g.groupby('month').agg(
                total_count=('hash', 'size'),
                fix_count=('is_fix', 'sum'),
            ).reset_index()
            fm['ratio'] = fm.apply(
                lambda r: float(r['fix_count'] / r['total_count']) if int(r['total_count']) else 0.0,
                axis=1,
            )
            fm = fm.sort_values('month')
            fix_commits_by_month = [
                {
                    'month': row['month'],
                    'total_count': int(row['total_count']),
                    'fix_count': int(row['fix_count']),
                    'ratio': float(row['ratio']),
                }
                for _, row in fm.iterrows()
            ]

            # change size by month
            cm = g.groupby('month').agg(
                commits=('hash', 'size'),
                files_changed=('files_changed', 'sum'),
                insertions=('insertions', 'sum'),
                deletions=('deletions', 'sum'),
                change_size_mean=('change_size', 'mean'),
                change_size_median=('change_size', 'median'),
                change_size_p90=('change_size', lambda x: float(x.quantile(0.9)) if len(x) else 0.0),
            ).reset_index().sort_values('month')
            change_size_by_month = [
                {
                    'month': row['month'],
                    'commits': int(row['commits']),
                    'files_changed': int(row['files_changed']),
                    'insertions': int(row['insertions']),
                    'deletions': int(row['deletions']),
                    'change_size_mean': float(row['change_size_mean']) if row['change_size_mean'] == row['change_size_mean'] else 0.0,
                    'change_size_median': float(row['change_size_median']) if row['change_size_median'] == row['change_size_median'] else 0.0,
                    'change_size_p90': float(row['change_size_p90']) if row['change_size_p90'] == row['change_size_p90'] else 0.0,
                }
                for _, row in cm.iterrows()
            ]

        change_size_stats = {
            'files_changed_total': int(df['files_changed'].sum()),
            'insertions_total': int(df['insertions'].sum()),
            'deletions_total': int(df['deletions'].sum()),
            'change_size_total': int(df['change_size'].sum()),
            'change_size_mean': float(df['change_size'].mean()) if total_commits else 0.0,
            'change_size_median': float(df['change_size'].median()) if total_commits else 0.0,
            'change_size_p90': float(df['change_size'].quantile(0.9)) if total_commits else 0.0,
        }

        # AST分析摘要
        ast_analysis_summary = self._perform_ast_analysis(commits)

        return {
            'total_commits': total_commits,
            'date_min': date_min.isoformat() if getattr(date_min, 'isoformat', None) else None,
            'date_max': date_max.isoformat() if getattr(date_max, 'isoformat', None) else None,
            'authors_top': authors_top,
            'files_top': files_top,
            'commits_by_month': commits_by_month,
            'fix_commits_total': fix_commits_total,
            'fix_commit_ratio': fix_commit_ratio,
            'fix_commits_by_month': fix_commits_by_month,
            'change_size_stats': change_size_stats,
            'change_size_by_month': change_size_by_month,
            'ast_analysis_summary': ast_analysis_summary,
        }

    def _perform_ast_analysis(self, commits: List[Dict[str, Any]]) -> Dict[str, Any]:
        """执行 AST 分析（标准库 ast）：识别危险模式并统计趋势。

        实现要点：
        - 使用本机 Pillow 仓库（config.settings.PILLOW_REPO_PATH），对 commit 的变更文件执行 `git show <sha>:<path>` 获取源码。
        - 用 ASTAnalyzer.analyze(code, file_path) 提取危险模式与基础指标。
        - 聚合到 month 粒度，输出趋势与 top patterns。
        """

        if not ASTAnalyzer:
            return {
                'enabled': False,
                'message': 'ASTAnalyzer not available.',
            }

        try:
            from config.settings import PILLOW_REPO_PATH
        except Exception:
            PILLOW_REPO_PATH = ''

        repo_path = os.path.abspath(PILLOW_REPO_PATH) if PILLOW_REPO_PATH else ''
        if not repo_path or not os.path.isdir(repo_path):
            return {
                'enabled': False,
                'message': 'PILLOW_REPO_PATH is not set or does not exist; cannot run git-based AST analysis.',
            }
        if not os.path.isdir(os.path.join(repo_path, '.git')):
            return {
                'enabled': False,
                'message': f'PILLOW_REPO_PATH is not a git repository: {repo_path}',
            }

        max_commits = int(os.getenv('PILLOW_AST_MAX_COMMITS', '300') or '300')
        max_files_per_commit = int(os.getenv('PILLOW_AST_MAX_FILES_PER_COMMIT', '30') or '30')
        sample_strategy = (os.getenv('PILLOW_AST_SAMPLE_STRATEGY', 'recent') or 'recent').strip().lower()

        fix_re = re.compile(
            r"(\bcve-\d{4}-\d+\b|\bsecurity\b|\bfix(?:e[ds])?\b|\bbug(?:s)?\b|\bdefect(?:s)?\b|\bregress(?:ion|ed)?\b|\bcrash(?:es|ed)?\b|\bhot\s*fix\b|\bpatch\b|\bresolve[sd]?\b|\bcloses?\b)",
            re.IGNORECASE,
        )

        def _git(args: List[str]) -> Tuple[int, str, str]:
            try:
                p = subprocess.run(
                    ['git', *args],
                    cwd=repo_path,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    capture_output=True,
                )
                return int(p.returncode), p.stdout or '', p.stderr or ''
            except FileNotFoundError:
                return 127, '', 'git_not_found'

        def _get_files_for_commit(commit_hash: str) -> List[str]:
            # Prefer files list from processed JSON; fallback to git show --name-only
            rc, out, _ = _git(['show', '--name-only', '--pretty=format:', commit_hash])
            if rc != 0:
                return []
            paths = [line.strip() for line in (out.splitlines() if out else []) if line.strip()]
            return paths

        def _get_file_at_commit(commit_hash: str, path: str) -> Optional[str]:
            rc, out, _ = _git(['show', f'{commit_hash}:{path}'])
            if rc != 0:
                return None
            return out

        def _is_python_file(path: str) -> bool:
            p = (path or '').replace('\\', '/')
            if not p.lower().endswith('.py'):
                return False
            # Speed: skip tests/docs/vendor-like paths by default
            lowered = p.lower()
            if lowered.startswith('tests/') or lowered.startswith('docs/') or '/tests/' in lowered or '/docs/' in lowered:
                return False
            return True

        analyzer = ASTAnalyzer()

        # Preflight: ensure git is available
        rc, _, err = _git(['--version'])
        if rc != 0:
            return {
                'enabled': False,
                'message': f'git is not available in PATH ({err}); cannot run git-based AST analysis.',
            }

        analyzed_commits = 0
        analyzed_files = 0
        commits_with_patterns = 0
        patterns_total = 0
        complexity_total = 0
        function_count_total = 0
        errors_total = 0

        selected_commits = 0
        skipped_missing_hash = 0
        skipped_no_files_listed = 0
        skipped_no_python_files = 0

        pattern_counts: Counter[str] = Counter()
        pattern_counts_by_month: Dict[str, Counter[str]] = {}
        month_totals: Dict[str, Dict[str, int]] = {}

        def _take_evenly(items: List[Any], k: int) -> List[Any]:
            if k <= 0 or not items:
                return []
            if len(items) <= k:
                return list(items)
            # deterministic even spacing across list
            idxs = [int(round(i * (len(items) - 1) / (k - 1))) for i in range(k)]
            seen = set()
            out: List[Any] = []
            for idx in idxs:
                if idx not in seen:
                    out.append(items[idx])
                    seen.add(idx)
            return out

        # Candidate commits: subject matches fix/security keywords
        candidates: List[Dict[str, Any]] = []
        for c in (commits or []):
            if not isinstance(c, dict):
                continue
            subject = (c.get('subject') or '')
            if isinstance(subject, str) and fix_re.search(subject):
                candidates.append(c)

        # Prepare candidates with parsed datetime/month for sampling
        enriched: List[Tuple[pd.Timestamp, str, Dict[str, Any]]] = []
        for c in candidates:
            dt = pd.to_datetime(c.get('date'), errors='coerce', utc=True)
            if pd.isna(dt):
                continue
            month = dt.to_period('M').strftime('%Y-%m')
            enriched.append((dt, month, c))

        if not enriched:
            return {
                'enabled': True,
                'repo_path': repo_path,
                'message': 'No candidate commits matched fix/security keywords; AST analysis skipped.',
                'analyzed_commits': 0,
                'analyzed_files': 0,
                'commits_with_patterns': 0,
                'patterns_total': 0,
                'errors_total': 0,
                'top_patterns': [],
                'patterns_by_month': [],
                'candidates_total': 0,
                'sample_strategy': sample_strategy,
            }

        candidates_total = len(enriched)

        # Select commits according to sampling strategy
        selected: List[Dict[str, Any]] = []
        if sample_strategy in {'recent', 'latest', 'head'}:
            enriched_sorted = sorted(enriched, key=lambda x: x[0], reverse=True)
            selected = [c for _, _, c in enriched_sorted[:max_commits]]
            sample_strategy = 'recent'
        elif sample_strategy in {'chronological', 'oldest', 'asc'}:
            enriched_sorted = sorted(enriched, key=lambda x: x[0])
            selected = [c for _, _, c in enriched_sorted[:max_commits]]
            sample_strategy = 'chronological'
        elif sample_strategy in {'uniform_by_month', 'stratified_by_month', 'month'}:
            # stable, spread across time
            enriched_sorted = sorted(enriched, key=lambda x: x[0])
            month_groups: Dict[str, List[Dict[str, Any]]] = {}
            for _, m, c in enriched_sorted:
                month_groups.setdefault(m, []).append(c)
            months_sorted = sorted(month_groups.keys())
            per_month = max(1, int(math.ceil(max_commits / max(1, len(months_sorted)))))
            tmp: List[Dict[str, Any]] = []
            for m in months_sorted:
                tmp.extend(_take_evenly(month_groups[m], per_month))
            selected = _take_evenly(tmp, max_commits)
            sample_strategy = 'uniform_by_month'
        else:
            # fallback: keep old behavior but make it deterministic (recent)
            enriched_sorted = sorted(enriched, key=lambda x: x[0], reverse=True)
            selected = [c for _, _, c in enriched_sorted[:max_commits]]
            sample_strategy = 'recent'

        for commit in selected:
            selected_commits += 1
            commit_hash = commit.get('hash') or ''
            if not commit_hash:
                skipped_missing_hash += 1
                continue

            dt = pd.to_datetime(commit.get('date'), errors='coerce', utc=True)
            if pd.isna(dt):
                continue
            month = dt.to_period('M').strftime('%Y-%m')

            files = commit.get('files') if isinstance(commit.get('files'), list) else None
            file_paths = [f for f in (files or []) if isinstance(f, str) and f]
            if not file_paths:
                file_paths = _get_files_for_commit(commit_hash)

            if not file_paths:
                skipped_no_files_listed += 1
                continue

            py_files = [p for p in file_paths if _is_python_file(p)]
            if not py_files:
                skipped_no_python_files += 1
                continue
            py_files = py_files[:max_files_per_commit]

            analyzed_commits += 1
            month_bucket = month_totals.setdefault(month, {'commits': 0, 'commits_with_patterns': 0, 'patterns_total': 0})
            month_bucket['commits'] += 1
            month_counter = pattern_counts_by_month.setdefault(month, Counter())

            commit_patterns = 0
            for path in py_files:
                code = _get_file_at_commit(commit_hash, path)
                if code is None:
                    errors_total += 1
                    continue

                analyzed_files += 1
                r = analyzer.analyze(code, file_path=path)
                if r.get('error'):
                    errors_total += 1
                    continue

                pts = r.get('patterns_found') or []
                if pts:
                    commit_patterns += len(pts)
                    pattern_counts.update(pts)
                    month_counter.update(pts)

                patterns_total += int(r.get('security_issues_potential') or 0)
                complexity_total += int(r.get('complexity_score') or 0)
                function_count_total += int(r.get('function_count') or 0)

            if commit_patterns > 0:
                commits_with_patterns += 1
                month_bucket['commits_with_patterns'] += 1
                month_bucket['patterns_total'] += commit_patterns

        # Build month series
        months_sorted = sorted(month_totals.keys())
        patterns_by_month = []
        for m in months_sorted:
            b = month_totals[m]
            commits_n = int(b.get('commits') or 0)
            patterns_n = int(b.get('patterns_total') or 0)
            patterns_by_month.append(
                {
                    'month': m,
                    'commits_analyzed': commits_n,
                    'commits_with_patterns': int(b.get('commits_with_patterns') or 0),
                    'patterns_total': patterns_n,
                    'patterns_per_commit': float(patterns_n / commits_n) if commits_n else 0.0,
                }
            )

        # top patterns time series (only for overall top N)
        top_patterns = [{'pattern': p, 'count': int(n)} for p, n in pattern_counts.most_common(10)]
        top_pattern_names = [x['pattern'] for x in top_patterns]
        top_patterns_by_month: Dict[str, List[Dict[str, Any]]] = {}
        for p in top_pattern_names:
            top_patterns_by_month[p] = [
                {'month': m, 'count': int((pattern_counts_by_month.get(m) or Counter()).get(p, 0))}
                for m in months_sorted
            ]

        return {
            'enabled': True,
            'repo_path': repo_path,
            'message': None,
            'candidates_total': candidates_total,
            'sample_strategy': sample_strategy,
            'selected_commits': selected_commits,
            'skipped_missing_hash': skipped_missing_hash,
            'skipped_no_files_listed': skipped_no_files_listed,
            'skipped_no_python_files': skipped_no_python_files,
            'analyzed_commits': analyzed_commits,
            'analyzed_files': analyzed_files,
            'commits_with_patterns': commits_with_patterns,
            'patterns_total': patterns_total,
            'errors_total': errors_total,
            'complexity_total': complexity_total,
            'function_count_total': function_count_total,
            'top_patterns': top_patterns,
            'patterns_by_month': patterns_by_month,
            'top_patterns_by_month': top_patterns_by_month,
            'limits': {
                'max_commits': max_commits,
                'max_files_per_commit': max_files_per_commit,
            },
        }