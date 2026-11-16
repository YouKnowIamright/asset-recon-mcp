"""Quake 采集 —— 原 cyberspace_collect.py「Quake 采集」一节原样搬出。"""

import json
import os
import time
from datetime import datetime, timezone

from providers.config import ARCHIVE_DIR, QUAKE_TOKEN
from providers.utils import clean_host, clean_port, http_post, normalize_country_code


def collect_quake(target):
    """Quake 全量翻页采集"""
    print('\n[Quake] 开始采集...')
    if not QUAKE_TOKEN:
        print('  [!] Quake Token 未配置，跳过')
        return [], {'status': 'skipped', 'total': 0, 'fetched': 0}

    query = f'domain:"{target}"'
    headers = {'X-QuakeToken': QUAKE_TOKEN}

    all_results = []
    start = 0
    page_size = 100
    total = 0
    page_num = 0  # 用于 total=0 时的最大页数限制

    def parse_quake_item(item):
        """解析单条 Quake 结果"""
        service = item.get('service', {})
        http_data = service.get('http', {})
        location = item.get('location', {})
        raw_host = http_data.get('host', '') or item.get('hostname', '')
        return {
            'host': clean_host(raw_host),
            'ip': item.get('ip', ''),
            'port': clean_port(item.get('port', '')),
            'title': http_data.get('title', ''),
            'domain': clean_host(raw_host),
            'country': normalize_country_code(location.get('country_cn', '')),
            'city': location.get('province_cn', ''),
            'source': 'quake',
        }

    while True:
        url = f'https://quake.360.net/api/v3/search/quake_service?start={start}&size={page_size}'
        print(f'  [Quake] start={start}...')
        data, status = http_post(url, {'query': query, 'include': ['ip', 'port', 'hostname', 'org', 'service.http.title', 'service.http.host', 'location.country_cn', 'location.province_cn']}, headers=headers)
        if not data:
            break

        code = data.get('code', 0)
        if code != 0:
            msg = data.get('message', '')
            print(f'  [!] Quake 错误 (code={code}): {msg}')
            break

        if start == 0:
            # Quake v3 meta.total 可能为 0 但实际有数据，做兼容处理
            total = data.get('meta', {}).get('total', 0)
            if total == 0:
                # 备选路径：部分版本 total 在顶层
                total = data.get('total', 0)
            if total == 0 and len(data.get('data', [])) > 0:
                print(f'  [Quake] 警告: total=0 但返回了 {len(data["data"])} 条数据，可能是 API 额度限制')
            print(f'  [Quake] 总量: {total}')

        results = data.get('data', [])
        if not results:
            break

        for item in results:
            all_results.append(parse_quake_item(item))

        # 终止条件：结果数小于页大小，或已获取 >= total（total > 0 时）
        if len(results) < page_size:
            break
        if total > 0 and len(all_results) >= total:
            break
        # 当 total=0 时，设置最大页数限制 10 页，避免持续翻页
        if total == 0:
            page_num += 1
            if page_num >= 10:
                print(f'  [Quake] total=0，已达最大页数限制 (10 页)，停止翻页')
                break

        start += page_size
        time.sleep(1)

    # 存储原始数据
    ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    archive_path = os.path.join(ARCHIVE_DIR, f'quake-{ts}.json')
    with open(archive_path, 'w') as f:
        json.dump({'query': query, 'total': total, 'results': all_results}, f, ensure_ascii=False, indent=2)

    print(f'  [Quake] 完成: 获取 {len(all_results)} 条 (总计 {total})')
    # total=0 但有数据时，报告实际获取数而非 total=0
    stat_total = total if total > 0 else len(all_results)
    stat_status = 'ok' if all_results else 'empty'
    if total == 0 and all_results:
        stat_status = 'ok_partial'  # API 额度限制导致 total 不可用
    return all_results, {'status': stat_status, 'total': stat_total, 'fetched': len(all_results)}
