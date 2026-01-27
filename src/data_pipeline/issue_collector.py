"""GitHub Issues 抓取（用于 bug 关闭规律分析）。

目标：抓取某个 GitHub 仓库的 issues，并按标签过滤（默认 label=bug）。

输出为 JSON 列表，每项包含：
- number, title, state, created_at, closed_at, labels, comments, user_login, html_url

注意：
- GitHub /issues API 会混入 PR（包含 pull_request 字段），这里会过滤掉。
- 需要更高配额时可在 config.settings.GITHUB_TOKEN 配置 token。
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests

try:
    from config import settings

    DEFAULT_GITHUB_TOKEN = getattr(settings, 'GITHUB_TOKEN', '')
    DEFAULT_HTTP_PROXY = getattr(settings, 'HTTP_PROXY', '')
    DEFAULT_HTTPS_PROXY = getattr(settings, 'HTTPS_PROXY', '')
    DEFAULT_CA_BUNDLE = getattr(settings, 'CA_BUNDLE', '')
    DEFAULT_USER_AGENT = getattr(settings, 'USER_AGENT', 'pillow-analysis/1.0')
    DEFAULT_GITHUB_REPO = getattr(settings, 'GITHUB_REPO', '')
except Exception:
    DEFAULT_GITHUB_TOKEN = ''
    DEFAULT_HTTP_PROXY = ''
    DEFAULT_HTTPS_PROXY = ''
    DEFAULT_CA_BUNDLE = ''
    DEFAULT_USER_AGENT = 'pillow-analysis/1.0'
    DEFAULT_GITHUB_REPO = ''


def _parse_iso(dt: str) -> Optional[datetime]:
    if not dt:
        return None
    try:
        # GitHub uses ISO 8601 like 2024-01-01T00:00:00Z
        return datetime.strptime(dt, '%Y-%m-%dT%H:%M:%SZ')
    except Exception:
        return None


def _parse_link_header(link: str) -> Dict[str, str]:
    """Parse RFC5988 Link header into rel->url mapping."""
    out: Dict[str, str] = {}
    if not link:
        return out
    parts = [p.strip() for p in link.split(',') if p.strip()]
    for p in parts:
        if ';' not in p:
            continue
        url_part, *attrs = [x.strip() for x in p.split(';')]
        if not (url_part.startswith('<') and url_part.endswith('>')):
            continue
        url = url_part[1:-1]
        rel = None
        for a in attrs:
            if a.startswith('rel='):
                rel = a.split('=', 1)[1].strip().strip('"')
        if rel:
            out[rel] = url
    return out


class IssueCollector:
    def __init__(
        self,
        github_token: Optional[str] = None,
        session: Optional[requests.Session] = None,
        ca_bundle: Optional[str] = None,
        proxies: Optional[Dict[str, str]] = None,
        user_agent: Optional[str] = None,
        github_repo: Optional[str] = None,
    ):
        self.github_token = github_token or DEFAULT_GITHUB_TOKEN or None
        self.session = session or requests.Session()

        ca = ca_bundle or DEFAULT_CA_BUNDLE
        if ca:
            self.session.verify = ca

        if proxies is None:
            proxies = {}
            if DEFAULT_HTTP_PROXY:
                proxies['http'] = DEFAULT_HTTP_PROXY
            if DEFAULT_HTTPS_PROXY:
                proxies['https'] = DEFAULT_HTTPS_PROXY
        if proxies:
            self.session.proxies.update(proxies)

        self.user_agent = user_agent or DEFAULT_USER_AGENT
        self.github_repo = github_repo or DEFAULT_GITHUB_REPO

    def _headers(self) -> Dict[str, str]:
        h = {
            'Accept': 'application/vnd.github+json',
            'User-Agent': self.user_agent,
        }
        if self._is_effective_token(self.github_token):
            h['Authorization'] = f'token {self.github_token}'
        return h

    @staticmethod
    def _is_effective_token(token: Optional[str]) -> bool:
        if not token:
            return False
        t = token.strip()
        if not t:
            return False
        # Common placeholders in this repo/docs
        lowered = t.lower()
        if 'your_token' in lowered or 'your token' in lowered:
            return False
        if t in {'ghp_your_token_here', 'your_github_token_here', 'your_token_here'}:
            return False
        # Too short to be a real GitHub token
        if len(t) < 20:
            return False
        return True

    def _get_json(self, url: str, params: Optional[Dict[str, Any]] = None, timeout: int = 30) -> Tuple[Any, Dict[str, str]]:
        r = self.session.get(url, params=params, headers=self._headers(), timeout=timeout)
        # Handle rate limit nicely
        if r.status_code == 401:
            raise RuntimeError(
                'GitHub API 401 Unauthorized. Most likely your GITHUB_TOKEN is invalid/expired. '
                'Fix config/local_settings.py GITHUB_TOKEN, or leave it empty to use anonymous access. '
                f'resp={r.text[:200]}'
            )
        if r.status_code == 403:
            raise RuntimeError(
                'GitHub API 403 Forbidden. This is usually rate limit or token scope/policy. '
                'Try setting a valid GITHUB_TOKEN in config/local_settings.py and re-run. '
                f'resp={r.text[:200]}'
            )
        r.raise_for_status()
        return r.json(), dict(r.headers)

    @staticmethod
    def _normalize_issue(it: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        # Filter out PRs
        if 'pull_request' in it:
            return None

        labels = []
        for lb in it.get('labels') or []:
            if isinstance(lb, dict) and lb.get('name'):
                labels.append(str(lb.get('name')))
            elif isinstance(lb, str):
                labels.append(lb)

        user = it.get('user') or {}
        return {
            'number': it.get('number'),
            'title': it.get('title') or '',
            'state': it.get('state') or '',
            'created_at': it.get('created_at'),
            'closed_at': it.get('closed_at'),
            'labels': labels,
            'comments': it.get('comments', 0),
            'user_login': user.get('login') if isinstance(user, dict) else None,
            'html_url': it.get('html_url'),
        }

    def collect_bug_issues(
        self,
        repo: Optional[str] = None,
        label: str = 'bug',
        since: Optional[str] = None,
        max_items: Optional[int] = None,
        save_path: Optional[str] = None,
        verbose: bool = False,
        sleep_seconds: float = 0.2,
    ) -> List[Dict[str, Any]]:
        """Collect bug issues for a repo.

        Args:
            repo: GitHub repo "owner/repo".
            label: Label name.
            since: Optional ISO date string "YYYY-MM-DD". When provided, stop when created_at < since.
            max_items: Max returned issues.
            save_path: Output JSON path.
        """
        repo = (repo or self.github_repo or '').strip()
        if not repo or '/' not in repo:
            raise ValueError('missing GitHub repo. Configure config.local_settings.GITHUB_REPO = "python-pillow/Pillow"')

        since_dt = None
        if since:
            try:
                since_dt = datetime.strptime(since, '%Y-%m-%d')
            except Exception:
                raise ValueError('since must be YYYY-MM-DD')

        url = f'https://api.github.com/repos/{repo}/issues'
        params = {
            'state': 'all',
            'labels': label,
            'per_page': 100,
            'sort': 'created',
            'direction': 'desc',
            'page': 1,
        }

        results: List[Dict[str, Any]] = []
        next_url = url
        next_params = dict(params)

        while next_url:
            data, headers = self._get_json(next_url, params=next_params)
            if not isinstance(data, list):
                break

            if verbose:
                print(f'[issue_collector] page={next_params.get("page")} got={len(data)} total_so_far={len(results)}')

            stop = False
            for it in data:
                norm = self._normalize_issue(it) if isinstance(it, dict) else None
                if not norm:
                    continue

                if since_dt:
                    created = _parse_iso(norm.get('created_at') or '')
                    if created and created.replace(tzinfo=None) < since_dt:
                        stop = True
                        break

                results.append(norm)
                if max_items and len(results) >= max_items:
                    stop = True
                    break

            if stop:
                break

            link = headers.get('Link') or headers.get('link') or ''
            rels = _parse_link_header(link)
            if 'next' in rels:
                next_url = rels['next']
                next_params = None  # next url already contains params
            else:
                # fallback: increment page
                next_url = url
                if next_params is None:
                    next_params = dict(params)
                next_params['page'] = int(next_params.get('page', 1)) + 1

            time.sleep(sleep_seconds)

        # de-dupe by issue number
        dedup: Dict[int, Dict[str, Any]] = {}
        for it in results:
            n = it.get('number')
            if isinstance(n, int):
                dedup[n] = it
        final = list(dedup.values())
        final.sort(key=lambda x: x.get('created_at') or '', reverse=True)

        if save_path is None:
            base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
            save_path = os.path.join(base, 'data', 'processed', 'pillow_bug_issues.json')

        if save_path:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(final, f, ensure_ascii=False, indent=2)

        return final
