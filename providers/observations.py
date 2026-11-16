"""assets → observations 转换。

老师的产物是扁平的 assets（ip/port/host/title...），observations 这一层是我们
对外的信封：每条 observation 表示关于目标的一条可引用事实，带类型、来源和置信度。
本模块只用已有的 assets，不发起任何网络请求。
"""

from datetime import datetime, timezone
from ipaddress import ip_address

from .merge import extract_web_urls
from .utils import clean_host, clean_port

# 输出顺序：域名 → IP → 服务 → Web 入口
TYPE_ORDER = {"dns_name": 0, "ip_address": 1, "service": 2, "web_endpoint": 3}


def _is_ip(value: str) -> bool:
    try:
        ip_address(value)
        return True
    except ValueError:
        return False


def _sources(asset: dict) -> list:
    src = asset.get("source") or []
    return [src] if isinstance(src, str) else sorted(src)


def to_observations(assets: list, observed_at: str | None = None) -> list:
    """把去重后的 assets 转成 observations 列表。"""
    stamp = observed_at or f"{datetime.now(timezone.utc):%Y-%m-%dT%H:%M:%SZ}"

    ips = {}
    hosts = {}
    observations = []

    for asset in assets:
        host = clean_host(asset.get("host", ""))
        ip = (asset.get("ip") or "").strip()
        port = clean_port(asset.get("port", ""))
        domain = clean_host(asset.get("domain", ""))
        sources = _sources(asset)

        # 域名节点：一个域名对应哪些 IP
        if host and not _is_ip(host):
            node = hosts.setdefault(host, {"domain": domain, "ips": set(), "sources": set()})
            if ip:
                node["ips"].add(ip)
            node["sources"].update(sources)

        # IP 节点：一个 IP 上开了哪些端口、挂了哪些域名
        if ip:
            node = ips.setdefault(ip, {"ports": set(), "hosts": set(), "sources": set()})
            if port:
                node["ports"].add(port)
            if host:
                node["hosts"].add(host)
            node["sources"].update(sources)

        # 服务：一条引擎记录 = 某个 ip:port 上的服务
        if ip or host:
            observations.append(
                {
                    "type": "service",
                    "key": f"{ip or host}:{port}" if port else (ip or host),
                    "data": {
                        "host": host,
                        "ip": ip,
                        "port": port,
                        "title": asset.get("title", ""),
                        "server": asset.get("server", ""),
                        "domain": domain,
                        "country": asset.get("country", ""),
                        "city": asset.get("city", ""),
                        "priority": asset.get("priority", ""),
                    },
                    "sources": sources,
                    "confidence": "recorded",
                    "observed_at": stamp,
                }
            )

        # Web 入口：按老师的端口规则拼 URL，属于推断而非观测
        for url in extract_web_urls([asset]):
            observations.append(
                {
                    "type": "web_endpoint",
                    "key": url,
                    "data": {
                        "url": url,
                        "host": host,
                        "ip": ip,
                        "port": port,
                        "title": asset.get("title", ""),
                        "server": asset.get("server", ""),
                    },
                    "sources": sources,
                    "confidence": "inferred",
                    "observed_at": stamp,
                }
            )

    for ip, node in ips.items():
        observations.append(
            {
                "type": "ip_address",
                "key": ip,
                "data": {
                    "ip": ip,
                    "ports": sorted(node["ports"]),
                    "hosts": sorted(node["hosts"]),
                },
                "sources": sorted(node["sources"]),
                "confidence": "recorded",
                "observed_at": stamp,
            }
        )

    for host, node in hosts.items():
        observations.append(
            {
                "type": "dns_name",
                "key": host,
                "data": {
                    "host": host,
                    "domain": node["domain"],
                    "ip_addresses": sorted(node["ips"]),
                },
                "sources": sorted(node["sources"]),
                "confidence": "recorded",
                "observed_at": stamp,
            }
        )

    observations.sort(key=lambda o: (TYPE_ORDER.get(o["type"], 9), o["key"]))
    return observations
