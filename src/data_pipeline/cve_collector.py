"""收集 CVE / NVD 漏洞数据（针对关键字，如 Pillow）。

实现策略：
- 按启用的数据源抓取：circl / nvd_v2 / nvd_v1 / github / osv。
- 将不同来源统一为同一字段结构，并按 id 去重合并。
"""

from __future__ import annotations

import json
import os
import time
from typing import List, Dict, Optional

import requests

try:
    from config import settings
    DEFAULT_API_KEY = getattr(settings, 'API_KEY', '')
    DEFAULT_GITHUB_TOKEN = getattr(settings, 'GITHUB_TOKEN', '')
    DEFAULT_HTTP_PROXY = getattr(settings, 'HTTP_PROXY', '')
    DEFAULT_HTTPS_PROXY = getattr(settings, 'HTTPS_PROXY', '')
    DEFAULT_CA_BUNDLE = getattr(settings, 'CA_BUNDLE', '')
    DEFAULT_USER_AGENT = getattr(settings, 'USER_AGENT', 'pillow-analysis/1.0')
    DEFAULT_SOURCES = getattr(settings, 'ENABLE_SOURCES', 'osv,nvd_v2,nvd_v1,circl,github')
except Exception:
    DEFAULT_API_KEY = ''
    DEFAULT_GITHUB_TOKEN = ''
    DEFAULT_HTTP_PROXY = ''
    DEFAULT_HTTPS_PROXY = ''
    DEFAULT_CA_BUNDLE = ''
    DEFAULT_USER_AGENT = 'pillow-analysis/1.0'
    DEFAULT_SOURCES = 'osv,nvd_v2,nvd_v1,circl,github'


class CVECollector:
    def __init__(self, api_key: Optional[str] = None, github_token: Optional[str] = None,
                 session: Optional[requests.Session] = None, proxies: Optional[Dict[str, str]] = None,
                 user_agent: Optional[str] = None, enabled_sources: Optional[List[str]] = None,
                 ca_bundle: Optional[str] = None):
        """初始化 CVECollector。

        Args:
            api_key: 如果有 NVD API key，可传入以提高配额；否则会尝试从 `config.settings.API_KEY` 读取。
            session: 可传入 requests.Session 以复用连接或在测试中注入。
        """
        self.api_key = api_key or DEFAULT_API_KEY or None
        self.github_token = github_token or DEFAULT_GITHUB_TOKEN or None
        self.user_agent = user_agent or DEFAULT_USER_AGENT
        self.enabled_sources = self._normalize_sources(enabled_sources or DEFAULT_SOURCES)
        self.session = session or requests.Session()

        # TLS / CA bundle support (important when HTTPS is intercepted by a proxy)
        ca = ca_bundle or DEFAULT_CA_BUNDLE
        if ca:
            # requests accepts verify=True/False or a path to a CA bundle (PEM)
            self.session.verify = ca

        # proxy support
        if proxies is None:
            proxies = {}
            if DEFAULT_HTTP_PROXY:
                proxies['http'] = DEFAULT_HTTP_PROXY
            if DEFAULT_HTTPS_PROXY:
                proxies['https'] = DEFAULT_HTTPS_PROXY
        if proxies:
            self.session.proxies.update(proxies)

    @staticmethod
    def _normalize_sources(sources) -> List[str]:
        if isinstance(sources, str):
            items = [s.strip() for s in sources.split(',') if s.strip()]
        else:
            items = [s.strip() for s in sources if isinstance(s, str) and s.strip()]
        return [s.lower() for s in items]

    def _headers(self) -> Dict[str, str]:
        return {
            'User-Agent': self.user_agent,
            'Accept': 'application/json'
        }

    def _request_json(self, method: str, url: str, *,
                      params: Optional[Dict] = None,
                      json_body: Optional[Dict] = None,
                      headers: Optional[Dict[str, str]] = None,
                      timeout: int = 20,
                      context: str = '') -> Dict:
        """Small helper to reduce repeated requests+error handling boilerplate."""
        resp = None
        try:
            if method.upper() == 'GET':
                resp = self.session.get(url, params=params, headers=headers, timeout=timeout)
            elif method.upper() == 'POST':
                resp = self.session.post(url, params=params, json=json_body, headers=headers, timeout=timeout)
            else:
                raise ValueError(f'unsupported method: {method}')

            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            status = getattr(resp, 'status_code', None) if resp is not None else None
            ctype = None
            snippet = ''
            try:
                if resp is not None:
                    ctype = resp.headers.get('content-type')
                    snippet = (resp.text or '')[:200]
            except Exception:
                pass

            prefix = (context + ' ') if context else ''
            raise RuntimeError(
                f'{prefix}status={status} err={e} content_type={ctype} resp_snippet="{snippet}"'
            )

    def _query_circl(self, keyword: str) -> List[Dict]:
        """使用 cve.circl.lu 的自由 API 搜索关键字。"""
        url = f'https://cve.circl.lu/api/search/{keyword}'
        data = self._request_json('GET', url, headers=self._headers(), timeout=15,
                                  context=f'circl query failed for "{keyword}"')

        # circl search returns a list
        if not isinstance(data, list):
            return []

        results = []
        for it in data:
            results.append({
                'id': it.get('id'),
                'summary': it.get('summary'),
                'published': it.get('Published'),
                'modified': it.get('Modified'),
                'references': it.get('references') or [],
                'source': 'circl',
            })
        return results

    def _query_nvd(self, keyword: str, results_per_page: int = 2000) -> List[Dict]:
        """使用 NVD 1.0 API 的 keywordSearch，并返回统一格式的条目列表。"""
        endpoint = 'https://services.nvd.nist.gov/rest/json/cves/1.0'
        params = {'keywordSearch': keyword, 'resultsPerPage': results_per_page}
        if self.api_key:
            params['apiKey'] = self.api_key

        headers = self._headers()

        results: List[Dict] = []
        start_index = 0
        while True:
            params['startIndex'] = start_index
            data = self._request_json(
                'GET',
                endpoint,
                params=params,
                headers=headers,
                timeout=20,
                context=f'nvd query failed for "{keyword}" startIndex={start_index}',
            )

            ci = data.get('result') or data
            items = ci.get('CVE_Items') if isinstance(ci, dict) else None
            if not items:
                break

            for it in items:
                cve_meta = it.get('cve', {}).get('CVE_data_meta', {})
                cid = cve_meta.get('ID')
                descs = it.get('cve', {}).get('description', {}).get('description_data', [])
                summary = descs[0].get('value') if descs else ''
                published = it.get('publishedDate')
                modified = it.get('lastModifiedDate')
                refs = []
                for r in it.get('cve', {}).get('references', {}).get('reference_data', []):
                    url = r.get('url')
                    if url:
                        refs.append(url)

                results.append({
                    'id': cid,
                    'summary': summary,
                    'published': published,
                    'modified': modified,
                    'references': refs,
                    'source': 'nvd',
                })

            total = ci.get('totalResults') or len(items)
            start_index += len(items)
            if start_index >= total:
                break
            time.sleep(0.6)

        return results

    def _query_nvd_v2(self, keyword: str, results_per_page: int = 2000) -> List[Dict]:
        """使用 NVD 2.0 API 的 keywordSearch。"""
        endpoint = 'https://services.nvd.nist.gov/rest/json/cves/2.0'
        params = {'keywordSearch': keyword, 'resultsPerPage': results_per_page}
        if self.api_key:
            params['apiKey'] = self.api_key

        results: List[Dict] = []
        start_index = 0
        while True:
            params['startIndex'] = start_index
            data = self._request_json(
                'GET',
                endpoint,
                params=params,
                headers=self._headers(),
                timeout=20,
                context=f'nvd_v2 query failed for "{keyword}" startIndex={start_index}',
            )

            vulns = data.get('vulnerabilities') or []
            if not vulns:
                break

            for v in vulns:
                cve = v.get('cve', {})
                cid = cve.get('id')
                descs = cve.get('descriptions') or []
                summary = ''
                for d in descs:
                    if d.get('lang') == 'en':
                        summary = d.get('value') or ''
                        break
                published = cve.get('published')
                modified = cve.get('lastModified')
                refs = [r.get('url') for r in (cve.get('references') or []) if r.get('url')]

                results.append({
                    'id': cid,
                    'summary': summary,
                    'published': published,
                    'modified': modified,
                    'references': refs,
                    'source': 'nvd_v2',
                })

            total = data.get('totalResults') or len(vulns)
            start_index += len(vulns)
            if start_index >= total:
                break
            time.sleep(0.6)

        return results

    def _query_github_advisories(self, package_name: str) -> List[Dict]:
        """查询 GitHub Security Advisories（可选，需 GitHub Token）。"""
        if not self.github_token:
            return []
        endpoint = 'https://api.github.com/advisories'
        params = {'affects': package_name, 'per_page': 100}
        headers = self._headers()
        headers['Authorization'] = f'token {self.github_token}'

        items = self._request_json(
            'GET',
            endpoint,
            params=params,
            headers=headers,
            timeout=20,
            context=f'github advisories query failed for "{package_name}"',
        )

        if not isinstance(items, list):
            return []

        results: List[Dict] = []
        for it in items:
            cve_id = it.get('cve_id')
            ghsa_id = it.get('ghsa_id')
            summary = it.get('summary') or ''
            published = it.get('published_at')
            modified = it.get('updated_at')
            refs = []
            if it.get('html_url'):
                refs.append(it['html_url'])
            if it.get('url'):
                refs.append(it['url'])

            results.append({
                'id': cve_id or ghsa_id,
                'summary': summary,
                'published': published,
                'modified': modified,
                'references': refs,
                'source': 'github',
            })

        return results

    def _query_osv(self, package_name: str) -> List[Dict]:
        """使用 OSV API 作为 NVD/circl 的后备数据源（针对 PyPI 包名）。"""
        url = 'https://api.osv.dev/v1/query'
        payload = {'package': {'name': package_name, 'ecosystem': 'PyPI'}}
        data = self._request_json(
            'POST',
            url,
            json_body=payload,
            timeout=15,
            context=f'osv query failed for "{package_name}"',
        )

        results: List[Dict] = []
        # OSV responses may include 'vulns' or 'vulnerabilities' or 'results'
        vulns = data.get('vulns') or data.get('vulnerabilities') or data.get('results') or []
        for v in vulns:
            # Try to extract a CVE id if present in aliases
            aliases = v.get('aliases') or []
            cve_id = None
            for a in aliases:
                if a and a.upper().startswith('CVE-'):
                    cve_id = a.upper()
                    break
            vid = cve_id or v.get('id')
            summary = v.get('summary') or v.get('details') or ''
            published = v.get('published') or v.get('modified') or None
            refs = []
            for r in v.get('references') or []:
                urlr = r.get('url') if isinstance(r, dict) else r
                if urlr:
                    refs.append(urlr)

            results.append({
                'id': vid,
                'summary': summary,
                'published': published,
                'modified': v.get('modified'),
                'references': refs,
                'source': 'osv',
            })

        return results

    def collect(self, keyword: str = 'Pillow', save_path: Optional[str] = None,
                max_items: Optional[int] = None, verbose: bool = False) -> List[Dict]:
        """收集与关键字相关的 CVE 条目。

        Args:
            keyword: 搜索关键字（例如 'Pillow'）。
            save_path: 可选，若提供则把结果写入该 JSON 文件（会覆盖）。
            max_items: 可选，限制返回的最大条目数量（对去重后的结果生效）。

        Returns:
            列表，每项为包含至少 `id` 和 `summary` 的 dict。
        """
        results: List[Dict] = []

        # 1) 多数据源抓取（可由 ENABLE_SOURCES 控制）
        circl = []
        nvd = []
        nvd_v2 = []
        github = []
        osv = []

        if 'circl' in self.enabled_sources:
            try:
                circl = self._query_circl(keyword)
                results.extend(circl)
            except Exception as e:
                if verbose:
                    print(f'[cve_collector][ERROR] circl query error: {e}')

        if 'nvd_v2' in self.enabled_sources:
            try:
                nvd_v2 = self._query_nvd_v2(keyword)
                results.extend(nvd_v2)
            except Exception as e:
                if verbose:
                    print(f'[cve_collector][ERROR] nvd_v2 query error: {e}')

        if 'nvd_v1' in self.enabled_sources:
            try:
                nvd = self._query_nvd(keyword)
                results.extend(nvd)
            except Exception as e:
                if verbose:
                    print(f'[cve_collector][ERROR] nvd query error: {e}')

        if 'github' in self.enabled_sources:
            try:
                github = self._query_github_advisories(keyword.lower())
                results.extend(github)
            except Exception as e:
                if verbose:
                    print(f'[cve_collector][ERROR] github advisories query error: {e}')

        # OSV：只要启用就执行并合并（OSV 更适合使用 PyPI 包名，如 pillow）
        if 'osv' in self.enabled_sources:
            osv_names: List[str] = []
            if keyword:
                osv_names.append(keyword.lower())
            osv_names.append('pillow')
            # 去重并保持顺序
            seen = set()
            osv_names = [n for n in osv_names if not (n in seen or seen.add(n))]

            for name in osv_names:
                try:
                    osv_results = self._query_osv(name)
                except Exception as e:
                    osv_results = []
                    if verbose:
                        print(f'[cve_collector][ERROR] osv({name}) {e}')
                if verbose:
                    print(f'[cve_collector] osv_name="{name}" osv_count={len(osv_results)}')
                osv.extend(osv_results)
                results.extend(osv_results)

        if verbose:
            print(
                f'[cve_collector] keyword="{keyword}" '
                f'circl_count={len(circl)} nvd_v2_count={len(nvd_v2)} '
                f'nvd_count={len(nvd)} github_count={len(github)} osv_count={len(osv)} total_raw={len(results)}'
            )

        # 注：所有启用的数据源都会执行并合并

        # 去重（以 id 为准），并合并不同来源的信息
        merged: Dict[str, Dict] = {}
        for item in results:
            cid = item.get('id')
            if not cid:
                continue
            if cid not in merged:
                merged[cid] = dict(item)
            else:
                # 合并字段，保留已有字段并补充 references
                base = merged[cid]
                if not base.get('summary') and item.get('summary'):
                    base['summary'] = item['summary']
                if not base.get('published') and item.get('published'):
                    base['published'] = item['published']
                if not base.get('modified') and item.get('modified'):
                    base['modified'] = item['modified']
                # 合并 references
                refs = set(base.get('references') or [])
                refs.update(item.get('references') or [])
                base['references'] = list(refs)
                # record sources
                srcs = set(base.get('source').split('|')) if base.get('source') else set()
                srcs.update((item.get('source') or '').split('|'))
                base['source'] = '|'.join(sorted(x for x in srcs if x))

        final = list(merged.values())

        # 可选排序：按发布时间降序（若无发布时间则放后面）
        final.sort(key=lambda x: x.get('published') or '', reverse=True)

        if max_items:
            final = final[:max_items]

        # 默认保存路径：项目的 data/processed/pillow_cves.json
        if save_path is None:
            base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
            save_path = os.path.join(base, 'data', 'processed', 'pillow_cves.json')

        if save_path:
            try:
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                with open(save_path, 'w', encoding='utf-8') as f:
                    json.dump(final, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

        return final


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print('Usage: python cve_collector.py <repo_keyword|Pillow> [out_json]')
        sys.exit(1)

    kw = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) >= 3 else None
    collector = CVECollector()
    items = collector.collect(keyword=kw, save_path=out)
    print(f'Collected {len(items)} CVE items for keyword "{kw}"')
    if items:
        print(items[0])
