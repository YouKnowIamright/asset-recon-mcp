"""公共工具 —— 原 cyberspace_collect.py「HTTP 工具」+「国家/城市归一化」两节原样搬出。"""

import json
import re
import urllib.error
import urllib.request

from providers.config import SSL_CTX, TIMEOUT

# ============================================================
# HTTP 工具
# ============================================================
def sanitize_url(url):
    """对 URL 中的 key/email/token/api-key 等敏感参数脱敏，用于日志输出"""
    # 匹配 key=xxx, email=xxx, token=xxx, api-key=xxx 等参数值
    return re.sub(r'((?:api-)?key|email|token)=[^&]+', r'\1=***', url, flags=re.IGNORECASE)

def clean_host(raw):
    """清洗 host 字段：剥离协议前缀和端口后缀，返回纯域名/IP"""
    if not raw:
        return ''
    host = raw.strip()
    # 剥离协议前缀
    host = re.sub(r'^https?://', '', host, flags=re.IGNORECASE)
    # 检测 IPv6 地址（格式: [::1] 或 [fe80::1]）
    if host.startswith('['):
        # IPv6 格式 [address]:port 或 [address]
        bracket_end = host.find(']')
        if bracket_end != -1:
            return host[1:bracket_end].lower()
        # 没有闭合 ]，直接返回
        return host.lower()
    # 剥离端口后缀（:port 或 :port:port 重复端口），仅对非 IPv6 地址
    host = host.split(':')[0]
    return host.lower()

def clean_port(raw):
    """清洗 port 字段：去除重复端口"""
    if not raw:
        return ''
    port = str(raw).strip()
    # 处理 '1883:1883' 这种重复
    if ':' in port:
        parts = port.split(':')
        port = parts[0]
    # 纯数字校验
    if port and not port.isdigit():
        return ''
    return port

def http_get(url, headers=None, timeout=TIMEOUT):
    """发起 HTTP GET 请求，返回 (parsed_json, http_status_code) 元组；失败时返回 (None, status)"""
    req = urllib.request.Request(url)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as resp:
            return json.loads(resp.read().decode('utf-8')), resp.status
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        print(f'  [!] HTTP {e.code}: {body[:200]}')
        return None, e.code
    except Exception as e:
        print(f'  [!] Error: {sanitize_url(url)}')
        print(f'      {e}')
        return None, None

def http_post(url, data, headers=None, timeout=TIMEOUT):
    """发起 HTTP POST 请求，返回 (parsed_json, http_status_code) 元组；失败时返回 (None, status)"""
    body = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(url, data=body, method='POST')
    req.add_header('Content-Type', 'application/json')
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as resp:
            return json.loads(resp.read().decode('utf-8')), resp.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', errors='replace')
        print(f'  [!] HTTP {e.code}: {raw[:200]}')
        return None, e.code
    except Exception as e:
        print(f'  [!] Error: {sanitize_url(url)}')
        print(f'      {e}')
        return None, None

# ============================================================
# 国家/城市归一化
# ============================================================
# 常见国家名到 ISO 3166-1 alpha-2 代码的映射
COUNTRY_CODE_MAP = {
    'china': 'CN', 'china Mainland': 'CN', '中国': 'CN',
    'united states': 'US', 'usa': 'US', 'u.s.a.': 'US', 'united states of america': 'US', '美国': 'US',
    'japan': 'JP', '日本': 'JP',
    'korea': 'KR', 'south korea': 'KR', '韩国': 'KR',
    'united kingdom': 'GB', 'uk': 'GB', 'great britain': 'GB', '英国': 'GB',
    'germany': 'DE', '德国': 'DE',
    'france': 'FR', '法国': 'FR',
    'russia': 'RU', 'russian federation': 'RU', '俄罗斯': 'RU',
    'canada': 'CA', '加拿大': 'CA',
    'australia': 'AU', '澳大利亚': 'AU',
    'india': 'IN', '印度': 'IN',
    'brazil': 'BR', '巴西': 'BR',
    'singapore': 'SG', '新加坡': 'SG',
    'hong kong': 'HK', '香港': 'HK',
    'taiwan': 'TW', '台湾': 'TW',
    'netherlands': 'NL', '荷兰': 'NL',
    'sweden': 'SE', '瑞典': 'SE',
    'switzerland': 'CH', '瑞士': 'CH',
    'ireland': 'IE', '爱尔兰': 'IE',
    'italy': 'IT', '意大利': 'IT',
    'spain': 'ES', '西班牙': 'ES',
    'mexico': 'MX', '墨西哥': 'MX',
    'indonesia': 'ID', '印度尼西亚': 'ID',
    'thailand': 'TH', '泰国': 'TH',
    'vietnam': 'VN', '越南': 'VN',
    'malaysia': 'MY', '马来西亚': 'MY',
    'philippines': 'PH', '菲律宾': 'PH',
    'turkey': 'TR', '土耳其': 'TR',
    'israel': 'IL', '以色列': 'IL',
    'uae': 'AE', 'united arab emirates': 'AE', '阿联酋': 'AE',
    'south africa': 'ZA', '南非': 'ZA',
    'argentina': 'AR', '阿根廷': 'AR',
    'new zealand': 'NZ', '新西兰': 'NZ',
    'finland': 'FI', '芬兰': 'FI',
    'norway': 'NO', '挪威': 'NO',
    'denmark': 'DK', '丹麦': 'DK',
    'poland': 'PL', '波兰': 'PL',
    'belgium': 'BE', '比利时': 'BE',
    'austria': 'AT', '奥地利': 'AT',
    'czech republic': 'CZ', 'czechia': 'CZ', '捷克': 'CZ',
    'romania': 'RO', '罗马尼亚': 'RO',
    'ukraine': 'UA', '乌克兰': 'UA',
    'portugal': 'PT', '葡萄牙': 'PT',
    'greece': 'GR', '希腊': 'GR',
    'egypt': 'EG', '埃及': 'EG',
    'iran': 'IR', '伊朗': 'IR',
    'saudi arabia': 'SA', '沙特阿拉伯': 'SA',
}

def normalize_country_code(raw):
    """将国家名归一化为 ISO 3166-1 alpha-2 代码；如果无法识别则原样返回"""
    if not raw:
        return ''
    val = str(raw).strip()
    if not val:
        return ''
    # 如果已经是 2 位大写字母代码，直接返回
    if re.match(r'^[A-Z]{2}$', val):
        return val
    # 尝试从映射表中查找（不区分大小写）
    lookup = val.lower()
    if lookup in COUNTRY_CODE_MAP:
        return COUNTRY_CODE_MAP[lookup]
    # 如果是 3 位字母代码，尝试常见映射
    alpha3_map = {'CHN': 'CN', 'USA': 'US', 'JPN': 'JP', 'KOR': 'KR', 'GBR': 'GB',
                  'DEU': 'DE', 'FRA': 'FR', 'RUS': 'RU', 'CAN': 'CA', 'AUS': 'AU',
                  'IND': 'IN', 'BRA': 'BR', 'SGP': 'SG', 'HKG': 'HK', 'TWN': 'TW',
                  'NLD': 'NL', 'SWE': 'SE', 'CHE': 'CH', 'IRL': 'IE', 'ITA': 'IT',
                  'ESP': 'ES', 'MEX': 'MX', 'IDN': 'ID', 'THA': 'TH', 'VNM': 'VN',
                  'MYS': 'MY', 'PHL': 'PH', 'TUR': 'TR', 'ISR': 'IL', 'ARE': 'AE',
                  'ZAF': 'ZA', 'ARG': 'AR', 'NZL': 'NZ', 'FIN': 'FI', 'NOR': 'NO',
                  'DNK': 'DK', 'POL': 'PL', 'BEL': 'BE', 'AUT': 'AT', 'CZE': 'CZ',
                  'ROU': 'RO', 'UKR': 'UA', 'PRT': 'PT', 'GRC': 'GR', 'EGY': 'EG',
                  'IRN': 'IR', 'SAU': 'SA'}
    if val.upper() in alpha3_map:
        return alpha3_map[val.upper()]
    # 无法识别，原样返回
    return val
