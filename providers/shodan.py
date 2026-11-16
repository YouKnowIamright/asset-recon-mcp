"""Shodan 采集 —— 原 cyberspace_collect.py「Shodan 采集」一节原样搬出。"""

import json
import os
import time
import urllib.parse
from datetime import datetime, timezone

from providers.config import ARCHIVE_DIR, SHODAN_KEY
from providers.utils import clean_host, clean_port, http_get, normalize_country_code


def collect_shodan(target):
    """Shodan 全量翻页采集"""
    print('\n[Shodan] 开始采集...')
    if not SHODAN_KEY:
        print('  [!] Shodan Key 未配置，跳过')
        return [], {'status': 'skipped', 'total': 0, 'fetched': 0}

    query = f'hostname:{target}'

    all_results = []
    page = 1
    # page_size 仅用于本地判断是否为最后一页；Shodan API 不支持 size 参数，每页固定返回 100 条
    page_size = 100
    total = 0

    while True:
        url = f'https://api.shodan.io/shodan/host/search?key={SHODAN_KEY}&query={urllib.parse.quote(query)}&page={page}'
        print(f'  [Shodan] 第 {page} 页...')
        data, status = http_get(url)
        if not data:
            break

        if 'error' in data:
            print(f'  [!] Shodan 错误: {data["error"]}')
            # 免费Key降级用 dns/domain
            if 'credit' in data.get('error', '').lower() or 'plan' in data.get('error', '').lower():
                print('  [Shodan] 尝试降级为 dns/domain 模式...')
                return collect_shodan_dns(target)
            break

        if page == 1:
            total = data.get('total', 0)
            print(f'  [Shodan] 总量: {total}')

        results = data.get('matches', [])
        if not results or len(results) < page_size:
            for item in results:
                raw_host = item.get('hostnames', [''])[0] if item.get('hostnames') else ''
                entry = {
                    'host': clean_host(raw_host),
                    'ip': item.get('ip_str', ''),
                    'port': clean_port(item.get('port', '')),
                    'title': item.get('http', {}).get('title', '') if isinstance(item.get('http'), dict) else '',
                    'server': item.get('http', {}).get('server', '') if isinstance(item.get('http'), dict) else '',
                    'domain': clean_host(raw_host),
                    'country': normalize_country_code(item.get('country_name', '')),
                    'city': item.get('city', ''),
                    'source': 'shodan',
                }
                all_results.append(entry)
            break

        for item in results:
            raw_host = item.get('hostnames', [''])[0] if item.get('hostnames') else ''
            entry = {
                'host': clean_host(raw_host),
                'ip': item.get('ip_str', ''),
                'port': clean_port(item.get('port', '')),
                'title': item.get('http', {}).get('title', '') if isinstance(item.get('http'), dict) else '',
                'server': item.get('http', {}).get('server', '') if isinstance(item.get('http'), dict) else '',
                'domain': clean_host(raw_host),
                'country': normalize_country_code(item.get('country_name', '')),
                'city': item.get('city', ''),
                'source': 'shodan',
            }
            all_results.append(entry)

        page += 1
        time.sleep(1)

    # 存储原始数据
    ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    archive_path = os.path.join(ARCHIVE_DIR, f'shodan-{ts}.json')
    with open(archive_path, 'w') as f:
        json.dump({'query': query, 'total': total, 'results': all_results}, f, ensure_ascii=False, indent=2)

    print(f'  [Shodan] 完成: 获取 {len(all_results)} 条 (总计 {total})')
    return all_results, {'status': 'ok', 'total': total, 'fetched': len(all_results)}


def collect_shodan_dns(target):
    """Shodan DNS domain 模式（免费Key降级）"""
    print('  [Shodan DNS] 使用 dns/domain 模式...')
    url = f'https://api.shodan.io/dns/domain/{target}?key={SHODAN_KEY}'
    data, status = http_get(url)
    if not data:
        return [], {'status': 'error', 'total': 0, 'fetched': 0}

    subdomains = set()
    for item in data.get('subdomains', []):
        subdomains.add(f'{item}.{target}')

    all_results = []
    for sd in sorted(subdomains):
        all_results.append({
            'host': clean_host(sd),
            'ip': '',
            'port': '',
            'title': '',
            'server': '',
            'domain': clean_host(sd),
            'country': '',
            'city': '',
            'source': 'shodan-dns',
        })

    total = data.get('total', len(subdomains))
    ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    archive_path = os.path.join(ARCHIVE_DIR, f'shodan-dns-{ts}.json')
    with open(archive_path, 'w') as f:
        json.dump({'target': target, 'total': total, 'results': all_results}, f, ensure_ascii=False, indent=2)

    print(f'  [Shodan DNS] 完成: 获取 {len(all_results)} 个子域名')
    return all_results, {'status': 'ok', 'total': total, 'fetched': len(all_results)}
