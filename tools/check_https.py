"""Quick HTTPS / proxy / certificate sanity checks.

Usage (cmd.exe):
  python tools\check_https.py

What it does:
- Prints proxy + CA bundle config from config.settings and env.
- Tries GET https://api.github.com (no token) to isolate TLS issues.
- If GITHUB_TOKEN is present, tries an authenticated request.
"""

import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import requests

try:
    from config import settings
except Exception as e:
    print('[check_https][ERROR] failed to import config.settings:', e)
    settings = None


def _get(name: str, default: str = '') -> str:
    if settings is None:
        return default
    return getattr(settings, name, default) or default


def main() -> int:
    http_proxy = _get('HTTP_PROXY')
    https_proxy = _get('HTTPS_PROXY')
    ca_bundle = _get('CA_BUNDLE')
    gh_token = _get('GITHUB_TOKEN')

    print('=== Config (settings / env) ===')
    print('HTTP_PROXY:', http_proxy or '(empty)')
    print('HTTPS_PROXY:', https_proxy or '(empty)')
    print('CA_BUNDLE:', ca_bundle or '(empty)')
    print('ENV REQUESTS_CA_BUNDLE:', os.getenv('REQUESTS_CA_BUNDLE', '') or '(empty)')
    print('ENV SSL_CERT_FILE:', os.getenv('SSL_CERT_FILE', '') or '(empty)')

    s = requests.Session()
    if http_proxy or https_proxy:
        s.proxies.update({k: v for k, v in {'http': http_proxy, 'https': https_proxy}.items() if v})
    if ca_bundle:
        s.verify = ca_bundle

    print('\n=== requests runtime ===')
    print('proxies:', s.proxies or '(none)')
    print('verify:', getattr(s, 'verify', None))

    def try_get(url: str, headers=None):
        print(f'\n--- GET {url} ---')
        try:
            r = s.get(url, timeout=20, headers=headers)
            print('status:', r.status_code)
            print('content-type:', r.headers.get('content-type'))
            print('body-snippet:', (r.text or '')[:200].replace('\n', ' '))
            return True
        except requests.exceptions.SSLError as e:
            print('[TLS/SSL ERROR]', e)
            return False
        except Exception as e:
            print('[ERROR]', e)
            return False

    # 1) No-token GitHub check: if this fails with SSLError, it's CA/trust problem.
    ok = try_get('https://api.github.com')

    # 2) Token check: only meaningful after TLS is OK
    if gh_token:
        headers = {'Authorization': f'token {gh_token}', 'Accept': 'application/vnd.github+json'}
        try_get('https://api.github.com/rate_limit', headers=headers)
    else:
        print('\n(no GITHUB_TOKEN configured; skipping authenticated check)')

    if not ok:
        print('\nResult: TLS still failing. Fix CA_BUNDLE / REQUESTS_CA_BUNDLE first.')
        return 2

    print('\nResult: HTTPS handshake OK. If GitHub API queries still fail, then check token scopes/endpoint usage.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
