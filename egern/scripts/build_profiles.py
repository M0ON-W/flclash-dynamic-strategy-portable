from __future__ import annotations

import argparse
from pathlib import Path
import re
import urllib.request

import yaml

from catalog import enabled_module_urls


ADVERTISING_LITE = (
    "https://raw.githubusercontent.com/Repcz/EgernRules/X/Rules/"
    "AdvertisingLite/AdvertisingLite.yaml"
)
RULE_BASE = "https://raw.githubusercontent.com/Repcz/EgernRules/X/Rules"

ALLOWLIST = [
    "captive.apple.com",
    "connectivitycheck.gstatic.com",
]

AD_SDK_DOMAINS = [
    "ad.zijieapi.com",
    "ads3-normal-hl.zijieapi.com",
    "ads5-normal-hl.zijieapi.com",
    "is.snssdk.com",
    "log-api.pangolin-sdk-toutiao.com",
    "pangolin-sdk-toutiao-b.com",
    "pangolin-sdk-toutiao.com",
    "pangolin.snssdk.com",
    "adsmind.apdcdn.tc.qq.com",
    "gdt.qq.com",
    "mi.gdt.qq.com",
    "pgdt.gtimg.cn",
    "qzs.gdtimg.com",
    "sdk.e.qq.com",
    "v.gdt.qq.com",
]

OPENAI_DOMAINS = [
    "openai.com",
    "chatgpt.com",
    "oaistatic.com",
    "oaiusercontent.com",
]

GOOGLE_DOMAINS = [
    "google.com",
    "googleapis.com",
    "gstatic.com",
    "googleusercontent.com",
    "youtube.com",
    "ytimg.com",
]

GEMINI_DOMAINS = [
    "gemini.google.com",
    "aistudio.google.com",
    "ai.google.dev",
    "generativelanguage.googleapis.com",
    "webchannel-robinfrontend-pa.googleapis.com",
]

MICROSOFT_CN = [
    "microsoft.cn",
    "officewebapps.cn",
    "partner.microsoftonline.cn",
    "windowsazure.cn",
    "azure.cn",
    "onmschina.cn",
    "21vbluecloud.com",
    "21vianet.com.cn",
]

APPLE_CN = ["apple.com.cn", "icloud.com.cn"]
UDP_MARKER = " [UDP]"
INFO_NODE_PATTERN = r"实时负载|流量|官网|套餐|到期|客服|剩余|过期|重置|说明|公告"
INFO_NODE_RE = re.compile(INFO_NODE_PATTERN, re.I)


def domain_rule(domain: str, policy: str, *, exact: bool = False) -> dict:
    kind = "domain" if exact else "domain_suffix"
    return {kind: {"match": domain, "policy": policy}}


def rule_set(name: str, policy: str, interval: int = 86400) -> dict:
    return {
        "rule_set": {
            "match": f"{RULE_BASE}/{name}/{name}.yaml",
            "policy": policy,
            "update_interval": interval,
        }
    }


def build_rules() -> list[dict]:
    rules: list[dict] = []

    # 本地网络与必要连通性放行。
    rules.extend(domain_rule(domain, "DIRECT", exact=True) for domain in ALLOWLIST)
    rules.extend(
        [
            domain_rule("local", "DIRECT"),
            domain_rule("lan", "DIRECT"),
            {"ip_cidr": {"match": "127.0.0.0/8", "policy": "DIRECT", "no_resolve": True}},
            {"ip_cidr": {"match": "10.0.0.0/8", "policy": "DIRECT", "no_resolve": True}},
            {"ip_cidr": {"match": "172.16.0.0/12", "policy": "DIRECT", "no_resolve": True}},
            {"ip_cidr": {"match": "192.168.0.0/16", "policy": "DIRECT", "no_resolve": True}},
            {"ip_cidr": {"match": "169.254.0.0/16", "policy": "DIRECT", "no_resolve": True}},
            {"ip_cidr": {"match": "224.0.0.0/4", "policy": "DIRECT", "no_resolve": True}},
        ]
    )

    # 广告规则必须位于 AI、服务和中国规则之前。
    rules.append(
        {
            "rule_set": {
                "match": ADVERTISING_LITE,
                "policy": "REJECT",
                "update_interval": 86400,
            }
        }
    )
    rules.extend(domain_rule(domain, "REJECT") for domain in AD_SDK_DOMAINS)

    # 仅对出口地区和 IP 风控严格的 AI 服务使用净选。
    rules.extend(domain_rule(domain, "净选") for domain in OPENAI_DOMAINS)
    rules.extend(domain_rule(domain, "净选") for domain in GEMINI_DOMAINS)
    rules.extend(
        rule_set(name, "净选")
        for name in ["OpenAI", "Gemini", "Anthropic", "Claude", "Copilot"]
    )

    # 普通 Google、YouTube 等服务不占用安全节点，统一走极速。
    rules.extend(domain_rule(domain, "极速") for domain in GOOGLE_DOMAINS)
    rules.append(rule_set("Google", "极速"))
    rules.append(rule_set("PikPak", "极速"))

    # Apple/Microsoft 中国区先直连，再匹配国际服务。
    rules.extend(domain_rule(domain, "DIRECT") for domain in MICROSOFT_CN)
    rules.extend(domain_rule(domain, "DIRECT") for domain in APPLE_CN)
    rules.append(rule_set("Microsoft", "极速"))
    rules.append(rule_set("Apple", "极速"))

    # 中国域名与地址直连，Cloudflare 等普通国际服务走极速。
    rules.append(domain_rule("cloudflare.com", "极速"))
    rules.append(rule_set("ChinaMaxNoIP", "DIRECT"))
    rules.append({"geoip": {"match": "CN", "policy": "DIRECT", "no_resolve": True}})
    rules.append({"default": {"policy": "PROXY"}})
    return rules


def build_dns() -> dict:
    return {
        "bootstrap": ["223.5.5.5", "119.29.29.29"],
        "upstreams": {
            "China": [
                "https://223.5.5.5/dns-query",
                "https://1.12.12.12/dns-query",
            ],
            "Global": [
                "https://1.1.1.1/dns-query",
                "https://8.8.8.8/dns-query",
            ],
        },
        "forward": [
            {"domain_suffix": {"match": "cn", "value": "China"}},
            *(
                {"domain_suffix": {"match": domain, "value": "China"}}
                for domain in MICROSOFT_CN + APPLE_CN
            ),
            {
                "proxy_rule_set": {
                    "match": f"{RULE_BASE}/ChinaMaxNoIP/ChinaMaxNoIP.yaml",
                    "value": "China",
                    "update_interval": 86400,
                }
            },
            {"domain_wildcard": {"match": "*", "value": "Global"}},
        ],
        "proxy_nameservers": [
            "https://223.5.5.5/dns-query",
            "https://1.1.1.1/dns-query",
        ],
        "skip_tls_verify": False,
    }


def build_policy_groups(subscription_url: str, local_proxy_names: list[str] | None = None) -> list[dict]:
    source_filter = rf"^(?!.*(?:{INFO_NODE_PATTERN})).+$"
    if local_proxy_names:
        clean_filter = r"(?i)台湾专线B.* \[UDP\]$"
        fast_filter = rf"^(?!.*(?:台湾专线B|{INFO_NODE_PATTERN})).* \[UDP\]$"
    else:
        clean_filter = "(?i)台湾专线B"
        fast_filter = "^(?!.*(?:台湾专线B|流量|官网|套餐|到期|客服|剩余|过期|重置|说明|公告)).+$"
    if local_proxy_names:
        subscription_group = {
            "fallback": {
                "name": "订阅",
                "policies": local_proxy_names,
                "urls": [subscription_url],
                "filter": source_filter,
                "interval": 600,
                "timeout": 8,
                "update_interval": 86400,
                "hidden": False,
            }
        }
    else:
        subscription_group = {
            "external": {
                "name": "订阅",
                "type": "fallback",
                "urls": [subscription_url],
                "filter": source_filter,
                "interval": 600,
                "timeout": 8,
                "update_interval": 86400,
                "hidden": False,
            }
        }
    return [
        subscription_group,
        {
            "auto_test": {
                "name": "净选",
                "policies": ["订阅"],
                "flatten": True,
                "filter": clean_filter,
                "interval": 600,
                "tolerance": 50,
                "timeout": 8,
                "latency_test_url": "https://www.gstatic.com/generate_204",
                "hidden": False,
            }
        },
        {
            "smart": {
                "name": "稳净",
                "policies": ["订阅"],
                "flatten": True,
                "filter": clean_filter,
                "latency_test_url": "https://www.gstatic.com/generate_204",
                "hidden": False,
            }
        },
        {
            "smart": {
                "name": "极速",
                "policies": ["订阅"],
                "flatten": True,
                "filter": fast_filter,
                "latency_test_url": "https://speed.cloudflare.com/__down?bytes=131072",
                "block_quic": False,
                "hidden": False,
            }
        },
        {
            "select": {
                "name": "PROXY",
                "policies": ["极速", "稳净", "净选", "订阅", "DIRECT"],
                "hidden": False,
            }
        },
    ]


def build_profile(subscription_url: str, enhanced: bool, udp_proxies: list[dict] | None = None) -> dict:
    udp_proxies = udp_proxies or []
    profile = {
        "ipv6": False,
        "hijack_dns": ["*"],
        "close_connections_on_policy_change": False,
        "dns": build_dns(),
        "policy_groups": build_policy_groups(
            subscription_url,
            [proxy["trojan"]["name"] for proxy in udp_proxies],
        ),
        "rules": build_rules(),
        "default_subscription_group": "订阅",
        "default_proxy_group": "PROXY",
        "modules": enabled_module_urls() if enhanced else [],
    }
    if udp_proxies:
        profile["proxies"] = udp_proxies
    return profile


def fetch_subscription(subscription_url: str) -> dict:
    request = urllib.request.Request(subscription_url, headers={"User-Agent": "Egern/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = yaml.safe_load(response.read().decode("utf-8-sig"))
    if not isinstance(data, dict) or not isinstance(data.get("proxies"), list):
        raise ValueError("订阅响应不是有效的 YAML 节点列表")
    return data


def build_udp_trojan_snapshot(subscription: dict) -> list[dict]:
    proxies: list[dict] = []
    names: set[str] = set()
    for index, source in enumerate(subscription.get("proxies", []), start=1):
        if not isinstance(source, dict) or source.get("type") != "trojan":
            continue
        source_name = str(source.get("name", ""))
        if INFO_NODE_RE.search(source_name):
            continue
        required = ["name", "server", "port", "password"]
        if any(source.get(key) in (None, "") for key in required):
            raise ValueError(f"订阅中的第 {index} 个 Trojan 节点缺少必要字段")
        if source_name in names:
            raise ValueError("订阅中的 Trojan 节点名称重复，无法安全覆盖")
        names.add(source_name)
        body = {
            "name": f"{source_name}{UDP_MARKER}",
            "server": source["server"],
            "port": source["port"],
            "password": source["password"],
            "udp_relay": True,
            "block_quic": False,
            "skip_tls_verify": bool(source.get("skip-cert-verify", False)),
        }
        if source.get("sni"):
            body["sni"] = source["sni"]
        proxies.append({"trojan": body})
    if not proxies:
        raise ValueError("订阅中没有可转换的 Trojan 节点")
    return proxies


def read_cached_udp_snapshot(source: Path) -> list[dict]:
    with source.open("r", encoding="utf-8-sig") as handle:
        data = yaml.safe_load(handle)
    proxies: list[dict] = []
    for wrapped in data.get("proxies", []) if isinstance(data, dict) else []:
        body = wrapped.get("trojan") if isinstance(wrapped, dict) else None
        if not isinstance(body, dict) or INFO_NODE_RE.search(str(body.get("name", ""))):
            continue
        if body.get("udp_relay") is True and str(body.get("name", "")).endswith(UDP_MARKER):
            proxies.append({"trojan": dict(body)})
    if not proxies:
        raise ValueError("订阅暂不可用，源配置中也没有可复用的 UDP 节点快照")
    return proxies


def read_subscription_url(source: Path) -> str:
    with source.open("r", encoding="utf-8-sig") as handle:
        data = yaml.safe_load(handle)
    for group in data.get("policy_groups", []):
        if not isinstance(group, dict) or len(group) != 1:
            continue
        body = next(iter(group.values()))
        if isinstance(body, dict) and body.get("name") == "订阅":
            urls = body.get("urls") or []
            if len(urls) != 1 or not isinstance(urls[0], str):
                raise ValueError("原配置的订阅组必须且只能包含一个 URL")
            return urls[0]
    raise ValueError("原配置中未找到带 URL 的“订阅”策略组")


def write_yaml(path: Path, profile: dict, private: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    label = "PRIVATE - DO NOT COMMIT" if private else "PUBLIC REDACTED TEMPLATE"
    body = yaml.safe_dump(
        profile,
        allow_unicode=True,
        sort_keys=False,
        width=1000,
        default_flow_style=False,
    )
    path.write_text(f"# {label}\n{body}", encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 Egern 公开模板和私有配置")
    parser.add_argument("--source", type=Path, help="原 Egern Profile.yaml；仅用于提取订阅 URL")
    parser.add_argument("--private-dir", type=Path, help="仓库外私有输出目录")
    args = parser.parse_args()

    egern_dir = Path(__file__).resolve().parents[1]
    write_yaml(egern_dir / "Profile.example.yaml", build_profile("SUBSCRIPTION_URL", True), False)
    write_yaml(egern_dir / "Profile.safe.example.yaml", build_profile("SUBSCRIPTION_URL", False), False)

    if args.source or args.private_dir:
        if not args.source or not args.private_dir:
            parser.error("--source 与 --private-dir 必须同时提供")
        subscription_url = read_subscription_url(args.source.resolve())
        try:
            udp_proxies = build_udp_trojan_snapshot(fetch_subscription(subscription_url))
        except (OSError, UnicodeError, yaml.YAMLError):
            udp_proxies = read_cached_udp_snapshot(args.source.resolve())
            print("订阅暂不可用；已使用现有私有配置中的 UDP 节点快照。")
        private_dir = args.private_dir.resolve()
        if egern_dir.parent.resolve() in private_dir.parents or private_dir == egern_dir.parent.resolve():
            raise ValueError("私有输出目录必须位于 Git 仓库之外")
        write_yaml(private_dir / "Profile.enhanced.yaml", build_profile(subscription_url, True, udp_proxies), True)
        write_yaml(private_dir / "Profile.safe.yaml", build_profile(subscription_url, False, udp_proxies), True)
        write_yaml(private_dir / "Profile.rollback.yaml", build_profile(subscription_url, False), True)

    print("Egern 配置已生成；私有版已为 Trojan 节点启用 UDP，未输出订阅 URL 或节点信息。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
