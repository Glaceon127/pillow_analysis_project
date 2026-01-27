"""项目配置（建议用环境变量注入敏感信息）。

注意：不要把真实的 API key / Token 硬编码提交到仓库。
"""

import os


# 全局配置文件（数据库路径、API密钥等）
DB_PATH = os.getenv('PILLOW_ANALYSIS_DB_PATH', '../data/processed/pillow_analysis.db')

# NVD API Key（推荐配置以避免 403/限流）
# 环境变量：NVD_API_KEY
API_KEY = os.getenv('NVD_API_KEY', '')

# GitHub Token（可选，用于访问 GitHub Security Advisories）
# 环境变量：GITHUB_TOKEN
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN', '')

# 代理设置（如处于企业/校园网络）
# 环境变量：HTTP_PROXY / HTTPS_PROXY
HTTP_PROXY = os.getenv('HTTP_PROXY', '')   # 例: http://127.0.0.1:7890
HTTPS_PROXY = os.getenv('HTTPS_PROXY', '')  # 例: http://127.0.0.1:7890

# 自定义 CA 证书（用于“代理/抓包中间人”根证书，解决 requests 的 CERTIFICATE_VERIFY_FAILED）
# 填 PEM 文件路径，或用环境变量 REQUESTS_CA_BUNDLE 指向 PEM。
CA_BUNDLE = os.getenv('REQUESTS_CA_BUNDLE', '')

# 请求头中的 User-Agent（部分安全数据源要求）
USER_AGENT = os.getenv('USER_AGENT', 'pillow-analysis/1.0 (https://github.com/your/repo)')

# 启用数据源（逗号分隔字符串或列表）
# 支持: circl, nvd_v1, nvd_v2, osv, github
ENABLE_SOURCES = os.getenv('ENABLE_SOURCES', 'osv,nvd_v2,nvd_v1,circl,github')

# Pillow 本地 git 仓库路径（用于 run_link_commits.py 默认值）
# 推荐在 `config/local_settings.py` 中配置（机器相关路径不建议放环境变量/仓库默认值）。
PILLOW_REPO_PATH = ''

# GitHub 仓库（用于抓取 bug issues），格式："owner/repo"，例如 "python-pillow/Pillow"
# 推荐在 `config/local_settings.py` 中配置。
GITHUB_REPO = ''



# 可选：本地覆盖配置（允许把 key/token 写在本机文件里，但不要提交到仓库）
# 你可以创建 `config/local_settings.py`，在里面定义同名变量覆盖此处配置。
try:
	from config import local_settings as _local_settings  # type: ignore

	for _name in (
		'DB_PATH',
		'API_KEY',
		'GITHUB_TOKEN',
		'HTTP_PROXY',
		'HTTPS_PROXY',
		'CA_BUNDLE',
		'USER_AGENT',
		'ENABLE_SOURCES',
		'PILLOW_REPO_PATH',
		'GITHUB_REPO',
	):
		if hasattr(_local_settings, _name):
			_value = getattr(_local_settings, _name)
			if _value is not None and _value != '':
				globals()[_name] = _value
except ModuleNotFoundError:
	pass
