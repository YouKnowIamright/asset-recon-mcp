"""去重合并与派生 —— 原 cyberspace_collect.py「资产去重与合并」一节原样搬出。"""

from providers.utils import clean_host, clean_port, normalize_country_code


def dedup_and_merge(all_raw_results):
    """去重合并所有引擎结果"""
    asset_map = {}  # key: ip:port or host:port

    for item in all_raw_results:
        # 入口统一清洗，确保 host 和 port 格式一致
        ip = (item.get('ip') or '').strip()
        port = clean_port(item.get('port', ''))
        host = clean_host(item.get('host', '') or item.get('domain', ''))

        if not host and not ip:
            continue

        # 归一化 country 和 city
        country = normalize_country_code(item.get('country', ''))
        city = item.get('city', '')

        # 去重 key：优先 ip:port，其次 host:port，再次 host/ip
        if ip and port:
            key = f'{ip}:{port}'
        elif host and port:
            key = f'{host}:{port}'
        elif ip:
            key = ip
        elif host:
            key = host
        else:
            continue

        if key in asset_map:
            # 合并来源
            if item.get('source', '') not in asset_map[key].get('_sources', []):
                asset_map[key]['_sources'].append(item.get('source', ''))
            # 补充缺失字段
            for field in ['title', 'server', 'domain', 'country', 'city']:
                if not asset_map[key].get(field) and item.get(field):
                    asset_map[key][field] = item[field]
            # 归一化已有记录的 country（可能之前未归一化）
            if asset_map[key].get('country'):
                asset_map[key]['country'] = normalize_country_code(asset_map[key]['country'])
            # 补充缺失的 ip 或 host
            if not asset_map[key].get('ip') and ip:
                asset_map[key]['ip'] = ip
            if not asset_map[key].get('host') and host:
                asset_map[key]['host'] = host
        else:
            entry = {
                'ip': ip,
                'port': port,
                'host': host,
                'title': item.get('title', ''),
                'server': item.get('server', ''),
                'domain': host,  # domain = 完整子域名（已清洗后的 host），而非根域名
                'country': country,
                'city': city,
                '_sources': [item.get('source', '')],
            }
            asset_map[key] = entry

    # 转换为数组并标记优先级
    assets = []
    for entry in asset_map.values():
        sources = entry.pop('_sources', [])
        entry['source'] = sources

        # 优先级分类
        title_lower = (entry.get('title') or '').lower()
        host_lower = (entry.get('host') or '').lower()
        port_str = entry.get('port') or ''
        port_num = int(port_str) if port_str.isdigit() else 0

        priority = 'medium'
        # 高价值：title 包含管理后台等关键字
        if any(kw in title_lower for kw in ['admin', '管理', 'dashboard', '后台', 'console', 'manage']):
            priority = 'high'
        # 高价值：host 包含测试/开发环境关键字
        elif any(kw in host_lower for kw in ['dev', 'test', 'staging', 'uat', 'pre']):
            priority = 'high'
        # 高价值：title 包含 API 相关关键字
        elif any(kw in title_lower for kw in ['swagger', 'graphql', 'api']):
            priority = 'high'
        # 高价值：非标准 Web 端口（排除常见 Web 端口 80/443/8080/8443/8000/3000 后，其余端口有交互界面的可能）
        # 同时结合 title 判断：非标准端口且有 title，说明有 Web 服务，标记为高价值
        elif port_num > 0 and port_str not in ['80', '443', '8080', '8443', '8000', '3000'] and entry.get('title'):
            priority = 'high'
        # 高价值：常见非 Web 服务端口（数据库、中间件等），这些通常不应暴露在公网
        elif port_num in [22, 21, 3389, 5432, 1433, 3306, 6379, 27017, 9200, 11211, 9090, 2375, 4243, 10250, 2376, 6443, 4444]:
            priority = 'high'
        # 低价值：标准 Web 端口且无 title
        elif port_str in ['80', '443'] and not entry.get('title'):
            priority = 'low'

        entry['priority'] = priority
        assets.append(entry)

    return assets


def extract_subdomains(assets, target):
    """提取所有子域名"""
    subdomains = set()
    for a in assets:
        host = a.get('host', '') or a.get('domain', '')
        host = clean_host(host)
        if host and target in host:
            subdomains.add(host)
    return sorted(subdomains)


def extract_web_urls(assets):
    """提取 Web URL 列表"""
    urls = set()
    # 常见 HTTPS 端口
    HTTPS_PORTS = {'443', '8443', '4443', '7443', '18443', '18110'}
    # 常见 HTTP 端口
    HTTP_PORTS = {'80', '8080', '8081', '8000', '8001', '8002', '8003', '8010', '8011', '8021', '8031', '8041', '8043', '8051', '8071', '9554', '3554', '7554', '10002', '8850', '9200'}
    # 非标准 Web 端口，同时尝试 http 和 https
    AMBIGUOUS_PORTS = {'8553', '8663', '8023', '8020', '4000', '2080', '35869', '1443', '10443', '83'}
    # 明确的非 Web 端口（RDP、Redis 等），这些端口不生成 Web URL
    NON_WEB_PORTS = {'22', '25', '110', '123', '465', '1883', '3389', '6379', '3306', '5432', '1433', '27017', '11211'}

    for a in assets:
        host = clean_host(a.get('host', ''))
        port = clean_port(a.get('port', ''))
        if not host:
            continue
        # host 已清洗过，不含协议和端口，安全拼接
        if port in HTTPS_PORTS:
            if port == '443':
                urls.add(f'https://{host}')
            else:
                urls.add(f'https://{host}:{port}')
        elif port in HTTP_PORTS:
            urls.add(f'http://{host}:{port}')
        elif port in AMBIGUOUS_PORTS:
            # 同时生成 http 和 https，让 httpx 自动判断
            urls.add(f'http://{host}:{port}')
            urls.add(f'https://{host}:{port}')
        elif port in NON_WEB_PORTS:
            # 非标准 Web 端口（RDP/Redis/SSH/数据库等），不生成 Web URL
            continue
        elif port:
            # 其他未知端口，同时尝试两种协议
            urls.add(f'http://{host}:{port}')
            urls.add(f'https://{host}:{port}')
        else:
            # 无端口，同时尝试 http 和 https
            urls.add(f'http://{host}')
            urls.add(f'https://{host}')

    return sorted(urls)
