"""Hunter 采集 —— 原 cyberspace_collect.py「Hunter 采集」一节原样搬出。"""

import base64
import json
import os
import time
from datetime import datetime, timezone

from providers.config import ARCHIVE_DIR, HUNTER_KEY
from providers.utils import clean_host, clean_port, http_get, normalize_country_code


def collect_hunter(target):
    """Hunter 全量翻页采集"""
    print('\n[Hunter] 开始采集...')
    if not HUNTER_KEY:
        print('  [!] Hunter Key 未配置，跳过')
        return [], {'status': 'skipped', 'total': 0, 'fetched': 0}

    query = f'domain.suffix="{target}"'
    # Hunter API 要求 search 参数为 URLBase64 编码（URL 安全的 Base64）
    search_b64 = base64.urlsafe_b64encode(query.encode('utf-8')).decode('utf-8')

    all_results = []
    page = 1
    total = 0
    page_size = 100  # Hunter 只接受 10/20/50/100

    while True:
        url = f'https://hunter.qianxin.com/openApi/search?api-key={HUNTER_KEY}&search={search_b64}&page={page}&page_size={page_size}&is_web=3'
        print(f'  [Hunter] 第 {page} 页...')
        data, status = http_get(url)
        if not data:
            break

        code = data.get('code')
        if code != 200:
            msg = data.get('message', '')
            print(f'  [!] Hunter 错误 (code={code}): {msg}')
            break

        d = data.get('data', {})
        if page == 1:
            total = d.get('total', 0)
            print(f'  [Hunter] 总量: {total}')

        results = d.get('arr', [])
        if not results:
            break

        for item in results:
            # component 字段可能为 None，用 isinstance 检查避免 TypeError
            component = item.get('component')
            if isinstance(component, list) and len(component) > 0 and isinstance(component[0], dict):
                server_name = component[0].get('name', '')
            else:
                server_name = ''
            entry = {
                'host': clean_host(item.get('url', '')),
                'ip': item.get('ip', ''),
                'port': clean_port(item.get('port', '')),
                'title': item.get('web_title', ''),
                'server': server_name,
                'domain': clean_host(item.get('domain', '')),
                'country': normalize_country_code('China'),
                'source': 'hunter',
            }
            # raw 中保留更多字段
            entry['_raw'] = item
            all_results.append(entry)

        if len(all_results) >= total or len(results) < page_size:
            break
        page += 1
        time.sleep(1.5)

    # 存储原始数据
    ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    archive_path = os.path.join(ARCHIVE_DIR, f'hunter-{ts}.json')
    with open(archive_path, 'w') as f:
        json.dump({'query': query, 'total': total, 'results': all_results}, f, ensure_ascii=False, indent=2)

    print(f'  [Hunter] 完成: 获取 {len(all_results)} 条 (总计 {total})')
    return all_results, {'status': 'ok', 'total': total, 'fetched': len(all_results)}
