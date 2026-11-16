"""FOFA 采集 —— 原 cyberspace_collect.py「FOFA 采集」一节原样搬出。"""

import base64
import json
import os
import time
import urllib.parse
from datetime import datetime, timezone

from providers.config import (
    ARCHIVE_DIR,
    FOFA_BASE_URL,
    FOFA_EMAIL,
    FOFA_KEY,
    FOFA_MAX_PAGES,
)
from providers.utils import clean_host, clean_port, http_get, normalize_country_code


def collect_fofa(target):
    """FOFA 全量翻页采集"""
    print('\n[FOFA] 开始采集...')
    if not FOFA_KEY:
        print('  [!] FOFA Key 未配置，跳过')
        return [], {'status': 'skipped', 'total': 0, 'fetched': 0}

    query = f'domain="{target}"'
    qbase64 = base64.b64encode(query.encode()).decode()

    all_results = []
    page = 1
    total = 0
    page_size = 100
    # 使用函数局部变量记录 429 重试次数，状态隔离
    retry_count = 0

    while True:
        url = f'{FOFA_BASE_URL}/api/v1/search/all?email={FOFA_EMAIL}&key={FOFA_KEY}&qbase64={urllib.parse.quote(qbase64)}&page={page}&size={page_size}&fields=host,ip,port,title,server,banner,country,city,domain'
        print(f'  [FOFA] 第 {page} 页...')
        data, status = http_get(url)
        # 仅对 HTTP 429 (Too Many Requests) 进行重试
        if data is None and status == 429:
            if retry_count < 3:
                retry_count += 1
                wait = 5 * (2 ** retry_count)
                print(f'  [FOFA] 429 限流，等待 {wait}s 后重试 (第 {retry_count} 次)...')
                time.sleep(wait)
                continue
            else:
                print(f'  [!] FOFA 重试次数耗尽，停止')
                break
        # 非 429 的失败或成功，重置重试计数
        retry_count = 0

        if not data:
            break

        if data.get('error') and data.get('errmsg'):
            print(f'  [!] FOFA 错误: {data["errmsg"]}')
            break

        if page == 1:
            total = data.get('size', 0)
            print(f'  [FOFA] 总量: {total}')

        results = data.get('results', [])
        if not results:
            break

        for item in results:
            # FOFA 返回数组，按 fields 顺序
            # fields=host,ip,port,title,server,banner,country,city,domain
            if isinstance(item, list):
                raw_host = item[0] if len(item) > 0 else ''
                raw_port = item[2] if len(item) > 2 else ''
                raw_server = item[4] if len(item) > 4 else ''
                raw_banner = item[5] if len(item) > 5 else ''
                # server 为空时从 banner 中提取 Server header
                if not raw_server and raw_banner:
                    for line in raw_banner.split('\n'):
                        if line.lower().startswith('server:'):
                            raw_server = line.split(':', 1)[1].strip()
                            break
                entry = {
                    'host': clean_host(raw_host),
                    'ip': item[1] if len(item) > 1 else '',
                    'port': clean_port(raw_port),
                    'title': item[3] if len(item) > 3 else '',
                    'server': raw_server,
                    'country': normalize_country_code(item[6] if len(item) > 6 else ''),
                    'city': item[7] if len(item) > 7 else '',
                    'domain': clean_host(item[8] if len(item) > 8 else ''),
                }
            elif isinstance(item, dict):
                entry = {
                    'host': clean_host(item.get('host', '')),
                    'ip': item.get('ip', ''),
                    'port': clean_port(item.get('port', '')),
                    'title': item.get('title', ''),
                    'server': item.get('server', ''),
                    'country': normalize_country_code(item.get('country', '')),
                    'city': item.get('city', ''),
                    'domain': clean_host(item.get('domain', '')),
                }
            else:
                continue
            entry['source'] = 'fofa'
            all_results.append(entry)

        if len(all_results) >= total or len(results) < page_size:
            break
        # 达到配置的页数上限就停，避免一次性消耗过多查询额度
        if FOFA_MAX_PAGES and page >= FOFA_MAX_PAGES:
            print(f'  [FOFA] 已达页数上限 {FOFA_MAX_PAGES}，停止翻页')
            break
        page += 1
        time.sleep(2)

    # 存储原始数据
    ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    archive_path = os.path.join(ARCHIVE_DIR, f'fofa-{ts}.json')
    with open(archive_path, 'w') as f:
        json.dump({'query': query, 'total': total, 'results': all_results}, f, ensure_ascii=False, indent=2)

    print(f'  [FOFA] 完成: 获取 {len(all_results)} 条 (总计 {total})')
    return all_results, {'status': 'ok', 'total': total, 'fetched': len(all_results)}
