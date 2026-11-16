"""asset-recon MCP server —— 四个引擎一起跑，缺 key / 单引擎报错都不崩。"""

import ipaddress
import os
import re
import sys
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlsplit

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "asset-recon",
    instructions=(
        "被动资产收集服务。提供 collect_assets 工具，用于查询域名、IP 或 CIDR 网段"
        "在空间测绘引擎（FOFA / Hunter / Quake / Shodan）中已被收录的暴露资产。\n"
        "本服务只读取第三方引擎数据库，不向目标发起任何请求。\n"
        "返回 JSON：status 为整体结果，query_summary 为各引擎执行情况，"
        "derived 为派生的子域名 / IP / URL 列表，stats 为统计。"
    ),
)

# providers/ 是英招采集脚本拆分后的实现，和本文件放在同一目录
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

# 类型 → 查询模式，沿用英招的命名
QUERY_MODES = {"domain": "domain_expand", "ip": "ip_scan", "cidr": "cidr_scan"}

# 域名：至少两段，每段由字母数字和连字符组成
DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}$"
)

ENGINE_NAMES = ("fofa", "hunter", "quake", "shodan")


# 去掉协议、端口、路径，得到干净的 host（搬自英招 clean_host）
def _clean_target(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    if "://" in s:
        return (urlsplit(s).hostname or "").rstrip(".").lower()
    # IPv6 带端口：[2001:db8::1]:443
    m = re.fullmatch(r"\[([0-9a-fA-F:]+)\](?::\d+)?", s)
    if m:
        return m.group(1).lower()
    # IP 或 CIDR 交给标准库规范化（1.2.3.4/24 → 1.2.3.0/24）
    try:
        net = ipaddress.ip_network(s, strict=False)
        return str(net) if "/" in s else str(net.network_address)
    except ValueError:
        pass
    # host:port 或 host/path
    s = s.split("?")[0].split("#")[0].split("/")[0]
    if s.count(":") == 1:
        s = s.split(":")[0]
    return s.rstrip(".").lower()


# 判断 target 属于哪一类
def _detect_type(target: str) -> str:
    if not target:
        return "unknown"
    if "/" in target:
        return "cidr"
    try:
        ipaddress.ip_address(target)
        return "ip"
    except ValueError:
        pass
    if DOMAIN_RE.match(target):
        return "domain"
    return "unknown"


# 加载本地 providers（英招四引擎实现 + 调用胶水 + 去重）
def _providers():
    if PROJECT_DIR not in sys.path:
        sys.path.insert(0, PROJECT_DIR)
    from providers import merge, observations, runner

    return merge, observations, runner


# 所有引擎都没跑时的占位状态
def _empty_summary(reason: str) -> dict:
    return {
        name: {
            "status": "skipped",
            "total": None,
            "fetched": 0,
            "has_more": False,
            "elapsed_ms": 0,
            "error": reason,
        }
        for name in ENGINE_NAMES
    }


# 四个引擎汇总成一个整体状态
def _overall_status(query_summary: dict) -> tuple[str, str | None]:
    statuses = [s["status"] for s in query_summary.values()]
    if "ok" in statuses:
        return "success", None
    if "error" in statuses:
        detail = "; ".join(
            f"{name}: {s['error']}"
            for name, s in query_summary.items()
            if s["status"] == "error"
        )
        return "failed", detail
    if all(s == "skipped" for s in statuses):
        return "unconfigured", "四个引擎的 API key 都没配置，本次没有发起任何请求"
    return "empty", None


# 把collect_assets这个函数注册成工具。注册后 LLM 才能在 tools/list 里看到它
@mcp.tool()
async def collect_assets(
    target: str,
    mode: Literal["domain", "ip", "cidr"] | None = None,
) -> dict:
    """在空间测绘引擎中检索指定目标的已收录资产。

    数据来源为 FOFA、Hunter、Quake、Shodan 等第三方引擎的既有收录数据，
    属于被动信息收集，不向目标发起请求，也不建立任何连接。

    适用：子域名枚举、资产清点、攻击面梳理、IP 或网段的服务发现。
    不适用：目标探活、网页内容抓取、漏洞验证，这些需使用其他工具。

    Args:
        target: 查询目标。根域名（如 example.com）、单个 IP，或 CIDR（如 192.0.2.0/24）。
            不接受 URL 或带端口的 host；子域名建议改传其根域，否则结果可能为空。
        mode: 查询模式，可省略。省略时依据 target 的类型自动判定；
            显式指定用于覆盖该判定。
    """
    target = _clean_target(target)
    target_type = _detect_type(target)

    if target_type in QUERY_MODES:
        query_mode = QUERY_MODES[mode] if mode else QUERY_MODES[target_type]
    else:
        query_mode = "auto"

    if target_type == "unknown":
        query_summary = _empty_summary("target 非法，未执行查询")
        status, error = "invalid_target", "target 为空，或不是合法的域名 / IP / CIDR"
        assets, subdomains, web_urls, ip_addresses = [], [], [], []
        observations = []
    else:
        merge, transform, runner = _providers()
        query_summary, entries = await runner.collect_all(target)
        assets = merge.dedup_and_merge(entries)
        subdomains = merge.extract_subdomains(assets, target)
        web_urls = merge.extract_web_urls(assets)
        ip_addresses = sorted({a["ip"] for a in assets if a.get("ip")})
        observations = transform.to_observations(assets)
        status, error = _overall_status(query_summary)

    return {
        "schema_version": "1.0",
        "run_id": f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{target}",
        "target": target,
        "target_type": target_type,
        "query_mode": query_mode,
        "status": status,
        "query_summary": query_summary,
        "observations": observations,
        "derived": {
            "subdomains": subdomains,
            "ip_addresses": ip_addresses,
            "web_urls": web_urls,
            "root_domains": [],
        },
        "stats": {
            "observations": len(observations),
            "returned": len(assets),
            "truncated": False,
            "providers_succeeded": sum(
                1 for s in query_summary.values() if s["status"] == "ok"
            ),
            "providers_failed": sum(
                1 for s in query_summary.values() if s["status"] == "error"
            ),
        },
        "artifact": None,
        "error": error,
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
