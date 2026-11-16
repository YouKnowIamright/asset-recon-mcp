"""配置层 —— 原 cyberspace_collect.py「配置」一节原样搬出。"""

import os
import ssl

# ============================================================
# 配置
# ============================================================
# 项目根目录：默认是本文件上一级（即 asset-recon-mcp），.env 和 runs/ 都在那里
# 不再依赖启动时的 cwd，MCP host 从任何目录启动都能找到 .env
PROJECT_ROOT = os.environ.get(
    'ASSET_RECON_ROOT',
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)
RUN_DIR = os.environ.get('ASSET_RECON_RUN_DIR', os.path.join(PROJECT_ROOT, 'runs', 'default'))

# .env 加载（支持引号包裹的值）
ENV_FILE = os.path.join(PROJECT_ROOT, '.env')
if os.path.exists(ENV_FILE):
    with open(ENV_FILE, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                v = v.strip()
                # 剥离首尾引号（单引号或双引号）
                if len(v) >= 2 and ((v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'"))):
                    v = v[1:-1]
                os.environ.setdefault(k.strip(), v)

FOFA_EMAIL = os.environ.get('FOFA_EMAIL', '')
FOFA_KEY = os.environ.get('FOFA_KEY', '')
# FOFA 接口地址：官方是 https://fofa.info，中转站填它给的 BASE_URL
FOFA_BASE_URL = os.environ.get('FOFA_BASE_URL', 'https://fofa.info').rstrip('/')
# FOFA 每次最多翻几页（每页 100 条）；0 = 不限（老师原始行为）
FOFA_MAX_PAGES = int(os.environ.get('FOFA_MAX_PAGES', '0') or 0)
QUAKE_TOKEN = os.environ.get('QUAKE_TOKEN', '')
HUNTER_KEY = os.environ.get('HUNTER_KEY', '')
SHODAN_KEY = os.environ.get('SHODAN_KEY', '')

SIGNALS_DIR = os.path.join(RUN_DIR, 'signals')
ARCHIVE_DIR = os.path.join(RUN_DIR, 'recon-archive')
os.makedirs(SIGNALS_DIR, exist_ok=True)
os.makedirs(ARCHIVE_DIR, exist_ok=True)

TIMEOUT = 30

# SSL 上下文：默认启用证书校验，仅当 ASSET_RECON_INSECURE_TLS=1 时禁用
if os.environ.get('ASSET_RECON_INSECURE_TLS', '') == '1':
    SSL_CTX = ssl.create_default_context()
    SSL_CTX.check_hostname = False
    SSL_CTX.verify_mode = ssl.CERT_NONE
else:
    SSL_CTX = None  # 使用 urllib 默认行为（启用校验）
