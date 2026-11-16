---
name: passive-recon
description: 使用 asset-recon MCP 的 collect_assets 工具做被动资产收集，查询域名、IP 或网段在空间测绘引擎中的已收录资产。当用户要求收集资产、查子域名、看某域名的暴露面、梳理攻击面、查询某个 IP 或网段上有哪些服务、做 recon、asset discovery、subdomain enumeration、资产测绘时使用。只要涉及"某个目标有哪些资产/子域名/开放服务"，一律调用 collect_assets，不要用 WebSearch 或 WebFetch 代替。
---

# 被动资产收集

## 1. 何时使用

使用 `collect_assets`：

- 收集某个域名的资产 / 子域名
- 查某个 IP 或网段上有哪些服务
- 梳理攻击面、做前置侦察（recon）
- 用户提到 FOFA、空间测绘、被动收集

**不要使用**：

- 需要判断目标是否存活、端口是否开放 → 这是主动探测，本工具不连接目标
- 需要抓取网页内容、截图、识别技术栈 → 用其他方式
- 需要验证漏洞是否存在 → 本工具只返回引擎的历史收录数据，不能作为漏洞证据

## 2. 如何调用

只传 `target`，`mode` 可省略（省略时按 target 类型自动判定）。

| 用户给的形式 | 传给 target | 说明 |
|---|---|---|
| `https://example.com/path` | `example.com` | 去掉协议和路径 |
| `example.com:8080` | `example.com` | 去掉端口 |
| `blog.example.com` | `example.com` | **改成根域**，子域通常查不到东西 |
| `1.2.3.4` | `1.2.3.4` | 单个 IP |
| `1.2.3.0/24` | `1.2.3.0/24` | 网段原样传 |

- 一次只传一个目标；多个目标就多次调用
- 同一个目标不要重复调用，每调用一次会消耗引擎额度（单次最多 100 条）

## 3. 结果如何判读

顶层 `status` 的含义：

| status | 含义 | 该怎么回应用户 |
|---|---|---|
| `success` | 至少一个引擎查到数据 | 正常汇总结果 |
| `empty` | 引擎都跑通了，但 0 条 | 说"引擎未收录该目标"，不要说"目标没有资产" |
| `unconfigured` | 没配置任何引擎的 API key | 提示需要配置 `FOFA_KEY`，不要重试 |
| `failed` | 引擎调用出错 | 读 `query_summary[*].error` 说明原因 |
| `invalid_target` | target 不合法 | 请用户提供域名、IP 或 CIDR |

`query_summary` 里每个引擎（`fofa` / `hunter` / `quake` / `shodan`）都有：

- `status`：`ok` 已查询 / `skipped` 无 key 未查询 / `error` 调用失败
- `total`：引擎报告的总量；`fetched`：本次实际取回的条数
- `has_more: true` 表示**只取了前 100 条，还有更多没取**，汇报时必须说明"未取全"

`derived` 是去重后派生的结果，直接引用即可，不要自己再造：

- `subdomains`：子域名列表
- `ip_addresses`：IP 列表
- `web_urls`：Web 入口列表
- `root_domains`：根域列表（当前可能为空）

`observations` 是逐条观测记录，每条包含 `type`、`key`、`data`、`sources`、`confidence`、`observed_at`：

| type | key 是什么 | data 里有什么 |
|---|---|---|
| `dns_name` | 域名 | `host`、`domain`、`ip_addresses`（该域名解析到的 IP） |
| `ip_address` | IP | `ip`、`ports`（该 IP 上出现的端口）、`hosts`（挂在该 IP 上的域名） |
| `service` | `ip:port` | `host`、`ip`、`port`、`title`、`server`、`country`、`city`、`priority` |
| `web_endpoint` | URL | `url`、`host`、`ip`、`port`、`title`、`server` |

- `confidence: "recorded"` = 引擎直接记录的事实，可当数据引用
- `confidence: "inferred"` = 由端口约定推断出来的（比如把 80 端口拼成 `http://host:80`），**不能当作已验证可访问**
- `priority` 为 `high` / `medium` / `low`，来自规则打分（标题含 admin/dashboard、域名含 dev/test、非常规端口等 → high）；汇报时优先展示 `high`
- `observed_at` 是**本次查询时间**，不是资产上线时间

汇报归属关系时直接引用这些字段（例如"`blog.42yeah.is` 对应 `20.24.230.41`"），不要凭 IP 列表和域名列表自己配对。

## 4. 如何汇报

- 只引用返回值里实际存在的字段，不要补充工具没有给出的信息（操作系统、版本、漏洞等）
- 结果较多时先给数量概览，再列关键条目，不要整段贴 JSON
- `has_more` 为 true 时明确告知"结果被截断，只展示前 100 条"
- 不要把 `web_urls` 描述成"已验证可访问"，本工具从未访问过它们

## 5. 红线

- 只对用户已授权的目标执行查询；目标不明或疑似非授权时先确认
- 不自动访问、打开、探活结果中的任何 URL
- 不把本工具的返回结果当作漏洞结论或入侵证据
- 不为了"多拿点数据"反复调用同一目标——额度有限，单次固定 1 页
