"""引擎调用胶水层 —— 把老师四个同步引擎包成异步、不污染 stdout、缺 key / 报错都不崩的调用。"""

import asyncio
import contextlib
import sys
import time

from providers import fofa, hunter, quake, shodan

# 引擎名 → 老师的采集函数，顺序与老师 main() 一致
ENGINES = {
    'fofa': fofa.collect_fofa,
    'hunter': hunter.collect_hunter,
    'quake': quake.collect_quake,
    'shodan': shodan.collect_shodan,
}

# 缺 key 时给调用方看的提示（只提示，不报错）
KEY_HINTS = {
    'fofa': 'FOFA_KEY',
    'hunter': 'HUNTER_KEY',
    'quake': 'QUAKE_TOKEN',
    'shodan': 'SHODAN_KEY',
}


def _elapsed(started):
    return int((time.perf_counter() - started) * 1000)


async def collect_one(name, target):
    """跑一个引擎，返回 (entries, summary)。这个引擎失败不影响其它引擎。"""
    started = time.perf_counter()
    try:
        # 老师的函数是同步的，丢到线程里跑，避免卡住 MCP 事件循环
        # 老师的 print 全部改到 stderr，避免污染 MCP 的 stdout 协议
        with contextlib.redirect_stdout(sys.stderr):
            entries, raw = await asyncio.to_thread(ENGINES[name], target)
    except Exception as exc:
        return [], {
            'status': 'error',
            'total': None,
            'fetched': 0,
            'has_more': False,
            'elapsed_ms': _elapsed(started),
            'error': f'{type(exc).__name__}: {exc}',
        }

    status = raw.get('status', 'error')
    total = raw.get('total') or 0
    fetched = raw.get('fetched') or 0

    if status == 'skipped':
        # 没配 key：正常跳过，不算失败
        status, error = 'skipped', f'{KEY_HINTS[name]} 未配置，已跳过'
    elif status in ('ok', 'ok_partial'):
        # ok_partial 是 Quake 在 total 不可用但拿到数据时的状态
        status, error = ('ok' if fetched else 'empty'), None
    elif status == 'empty':
        error = None
    else:
        error = f'{name}: {status}'

    return entries, {
        'status': status,
        'total': total or None,
        'fetched': fetched,
        'has_more': bool(total and fetched < total),
        'elapsed_ms': _elapsed(started),
        'error': error,
    }


async def collect_all(target):
    """顺序跑四个引擎，返回 (query_summary, 四个引擎的 entries 拼在一起)。"""
    query_summary = {}
    entries = []
    for name in ENGINES:
        engine_entries, summary = await collect_one(name, target)
        query_summary[name] = summary
        entries.extend(engine_entries)
    return query_summary, entries
