from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import urllib.request
from urllib.parse import quote, urlparse
from pathlib import Path

import yaml


GROUP_TYPES = {"external", "auto_test", "smart", "select", "fallback", "load_balance"}
BUILTINS = {"DIRECT", "REJECT"}
INFO_RE = re.compile(r"(?:流量|官网|套餐|到期|客服|剩余|过期|重置|说明|公告)", re.I)
TAIWAN_B_RE = re.compile(r"台湾专线B", re.I)
FORBIDDEN_MODULE_RE = re.compile(
    r"hostname\s*=\s*(?:%APPEND%\s*)?\*\s*(?:,|$)|"
    r"new\.vip\.weibo|weibo_vip\.js|del\(\.data\.payment\)|"
    r"paySuccess|bankcomm|cmbchina|tenpay|alipay|appleid|"
    r"entitlement|receipt|cookie-request|cookie-response",
    re.I | re.M,
)


class ValidationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig") as handle:
        data = yaml.safe_load(handle)
    require(isinstance(data, dict), f"{path}: 顶层必须为对象")
    return data


def policy_groups(profile: dict) -> dict[str, tuple[str, dict]]:
    groups: dict[str, tuple[str, dict]] = {}
    for wrapped in profile.get("policy_groups", []):
        require(isinstance(wrapped, dict) and len(wrapped) == 1, "策略组结构无效")
        kind, body = next(iter(wrapped.items()))
        require(kind in GROUP_TYPES, f"不支持的策略组类型: {kind}")
        name = body.get("name")
        require(name and name not in groups, f"策略组名称无效或重复: {name}")
        groups[name] = (kind, body)
    return groups


def matching_rule_policy(rules: list[dict], kind: str, match: str) -> str | None:
    for rule in rules:
        body = rule.get(kind) if isinstance(rule, dict) else None
        if isinstance(body, dict) and body.get("match") == match:
            return body.get("policy")
    return None


def validate_profile(path: Path, safe: bool) -> dict:
    profile = load_yaml(path)
    require(profile.get("ipv6") is False, f"{path.name}: ipv6 必须关闭")
    require(profile.get("hijack_dns") == ["*"], f"{path.name}: 必须劫持 53 端口 DNS")

    dns = profile.get("dns") or {}
    require(dns.get("bootstrap") == ["223.5.5.5", "119.29.29.29"], "Bootstrap 必须为明确国内 IP")
    dns_text = yaml.safe_dump(dns, allow_unicode=True)
    require("system" not in dns_text.lower(), "DNS 不得引用 system")
    require(all(str(x).startswith("https://") for x in dns.get("proxy_nameservers", [])), "代理 DNS 必须加密")
    require(dns.get("forward", [])[-1] == {"domain_wildcard": {"match": "*", "value": "Global"}}, "DNS 最终规则必须进入 Global")

    groups = policy_groups(profile)
    require(set(groups) == {"订阅", "净选", "稳净", "极速", "PROXY"}, "策略组集合不符合三组方案")
    local_proxies = profile.get("proxies") or []
    expected_subscription_type = "fallback" if local_proxies else "external"
    require(groups["订阅"][0] == expected_subscription_type, "订阅策略组类型与本地节点模式不一致")
    require(groups["净选"][0] == "auto_test", "净选必须为 auto_test")
    require(groups["稳净"][0] == "smart", "稳净必须为 smart")
    require(groups["极速"][0] == "auto_test", "极速必须为 auto_test")
    require(groups["PROXY"][1].get("policies") == ["极速", "稳净", "净选", "订阅", "DIRECT"], "PROXY 顺序错误")
    require(groups["净选"][1].get("interval") == 600 and groups["净选"][1].get("tolerance") == 50, "净选测速参数错误")
    require(groups["极速"][1].get("interval") == 600 and groups["极速"][1].get("tolerance") == 100, "极速测速参数错误")
    local_proxy_names = {
        body.get("name")
        for proxy in local_proxies
        if isinstance(proxy, dict)
        for body in proxy.values()
        if isinstance(body, dict) and body.get("name")
    }
    for _name, (_kind, body) in groups.items():
        for policy in body.get("policies", []):
            require(policy in groups or policy in BUILTINS or policy in local_proxy_names, f"策略引用不存在: {policy}")

    if local_proxies:
        local_names = []
        for proxy in local_proxies:
            require(isinstance(proxy, dict) and set(proxy) == {"trojan"}, "UDP 快照只允许 Egern 原生 Trojan 节点")
            body = proxy["trojan"]
            require(body.get("udp_relay") is True, "本地 Trojan 节点未启用 UDP 转发")
            require(body.get("block_quic") is False, "本地 Trojan 节点必须允许 QUIC")
            require(all(body.get(key) not in (None, "") for key in ["name", "server", "port", "password"]), "本地 Trojan 节点字段不完整")
            local_names.append(body["name"])
        require(len(local_names) == len(set(local_names)), "本地 Trojan 节点名称重复")
        require(groups["订阅"][1].get("policies") == local_names, "订阅组未完整引用 UDP 快照节点")

    rules = profile.get("rules") or []
    serialized_rules = [yaml.safe_dump(rule, allow_unicode=True) for rule in rules]
    require(any("169.254.0.0/16" in item for item in serialized_rules), "缺少 169.254.0.0/16")
    require(not any("192.128.0.0/16" in item for item in serialized_rules), "仍包含错误的 192.128.0.0/16")
    ad_index = next(i for i, item in enumerate(serialized_rules) if "AdvertisingLite" in item)
    ai_index = next(i for i, item in enumerate(serialized_rules) if "openai.com" in item)
    service_index = next(i for i, item in enumerate(serialized_rules) if "Microsoft/Microsoft.yaml" in item)
    china_index = next(i for i, item in enumerate(serialized_rules) if "ChinaMaxNoIP" in item)
    require(0 < ad_index < ai_index < service_index < china_index < len(rules) - 1, "规则顺序不是放行→广告→AI→服务→中国→默认")
    require(matching_rule_policy(rules, "domain_suffix", "openai.com") == "净选", "OpenAI 必须进入净选")
    require(matching_rule_policy(rules, "domain_suffix", "gemini.google.com") == "净选", "Gemini 必须进入净选")
    require(matching_rule_policy(rules, "domain_suffix", "google.com") == "极速", "普通 Google 必须进入极速")
    require(matching_rule_policy(rules, "domain_suffix", "youtube.com") == "极速", "YouTube 必须进入极速")
    require(matching_rule_policy(rules, "domain_suffix", "cloudflare.com") == "极速", "Cloudflare 必须进入极速")
    require(matching_rule_policy(rules, "rule_set", "https://raw.githubusercontent.com/Repcz/EgernRules/X/Rules/Google/Google.yaml") == "极速", "Google 规则集必须进入极速")
    require(matching_rule_policy(rules, "rule_set", "https://raw.githubusercontent.com/Repcz/EgernRules/X/Rules/PikPak/PikPak.yaml") == "极速", "PikPak 必须进入极速")
    require("default" in rules[-1] and rules[-1]["default"].get("policy") == "PROXY", "最终规则必须进入 PROXY")

    modules = profile.get("modules") or []
    if safe:
        require(modules == [], "安全版必须完全关闭模块")
        require("mitm" not in profile, "安全版不得包含 MITM 配置")
    else:
        require(len(modules) == 11, "增强版应启用 11 个通过审查的深度模块")
        require(all(module.get("enabled") is True and module.get("update_interval") == 0 for module in modules), "MITM 模块必须启用且禁止自动更新")
    return profile


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_manifest(egern_root: Path) -> None:
    manifest = load_yaml(egern_root / "modules" / "manifest.yaml")
    entries = manifest.get("modules") or []
    require(len(entries) == 15, "模块清单必须覆盖 15 个应用")
    required = {
        "id",
        "app",
        "source_url",
        "source_commit",
        "license",
        "mitm_domains",
        "script_urls",
        "sha256",
        "review_status",
        "default_enabled",
    }
    for entry in entries:
        require(required <= set(entry), f"{entry.get('id')}: 模块清单字段不完整")
        artifact_url = entry.get("module_url") or ""
        if "/egern/modules/" in artifact_url and entry["review_status"].startswith("approved"):
            rel = artifact_url.split("/egern/", 1)[1]
            artifact = egern_root / rel
            require(artifact.is_file(), f"{entry['id']}: 审查模块不存在")
            require(sha256(artifact) == entry["sha256"], f"{entry['id']}: 模块 SHA-256 不匹配")
            text = artifact.read_text(encoding="utf-8")
            match = FORBIDDEN_MODULE_RE.search(text)
            require(not match, f"{entry['id']}: 命中禁止模块内容 {match.group(0) if match else ''}")
            require(all(item.get("sha256") for item in entry["script_urls"]), f"{entry['id']}: 脚本 SHA-256 不完整")
        if entry["review_status"] == "held":
            require(entry["default_enabled"] is False, f"{entry['id']}: 暂缓模块不得默认启用")


def iter_repo_files(repo: Path):
    for path in repo.rglob("*"):
        if path.is_file() and ".git" not in path.parts:
            yield path


def read_subscription_url(source: Path) -> str:
    profile = load_yaml(source)
    for wrapped in profile.get("policy_groups", []):
        if not isinstance(wrapped, dict) or len(wrapped) != 1:
            continue
        body = next(iter(wrapped.values()))
        if isinstance(body, dict) and body.get("name") == "订阅":
            urls = body.get("urls") or []
            require(len(urls) == 1, "源订阅 URL 数量必须为 1")
            return str(urls[0])
    raise ValidationError("源配置中找不到订阅 URL")


def fetch_subscription(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "Egern/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = response.read()
    data = yaml.safe_load(payload.decode("utf-8-sig"))
    require(isinstance(data, dict), "订阅响应不是 YAML 对象")
    return data


def privacy_scan(repo: Path, source: Path, subscription: dict | None) -> None:
    source_url = read_subscription_url(source)
    needles = {source_url, str(source.resolve())}
    if subscription:
        for proxy in subscription.get("proxies", []):
            if not isinstance(proxy, dict):
                continue
            for key in ["server", "password", "uuid", "user_id", "certificate", "private_key"]:
                value = proxy.get(key)
                if isinstance(value, str) and len(value) >= 7:
                    needles.add(value)
    for path in iter_repo_files(repo):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for needle in needles:
            require(needle not in text, f"隐私扫描失败: {path.relative_to(repo)} 含私有输入或节点凭据")


def validate_live_subscription(subscription: dict) -> None:
    proxies = subscription.get("proxies") or []
    names = [str(item.get("name", "")) for item in proxies if isinstance(item, dict)]
    clean = [name for name in names if TAIWAN_B_RE.search(name)]
    info = [name for name in names if INFO_RE.search(name)]
    fast = [name for name in names if not INFO_RE.search(name)]
    require(clean, "净选/稳净候选池为空")
    require(fast, "极速候选池为空")
    require(len(clean) == 6, f"当前订阅的台湾专线B预期为 6，实际为 {len(clean)}")
    require(len(info) == 2, f"当前订阅的说明类节点预期为 2，实际为 {len(info)}")
    print(f"订阅过滤：总节点 {len(names)}，净选/稳净 {len(clean)}，极速 {len(fast)}，排除说明 {len(info)}。")


def validate_remote_rules(profile: dict) -> None:
    urls = set()
    for rule in profile.get("rules", []):
        body = rule.get("rule_set") if isinstance(rule, dict) else None
        if body and isinstance(body.get("match"), str):
            urls.add(body["match"])
    for forward in profile.get("dns", {}).get("forward", []):
        body = forward.get("proxy_rule_set") if isinstance(forward, dict) else None
        if body and isinstance(body.get("match"), str):
            urls.add(body["match"])
    fallback_count = 0
    raw_unavailable = False
    for url in sorted(urls):
        last_error = None
        if not raw_unavailable:
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "Egern/1.0"})
                with urllib.request.urlopen(request, timeout=10) as response:
                    require(response.status == 200 and bool(response.read(32)), f"远程规则不可读: {url}")
            except Exception as exc:
                last_error = exc
                raw_unavailable = True
        else:
            last_error = RuntimeError("raw.githubusercontent.com unavailable")
        if last_error is not None:
            parsed = urlparse(url)
            parts = parsed.path.lstrip("/").split("/", 3)
            require(parsed.netloc == "raw.githubusercontent.com" and len(parts) == 4, f"远程规则不可读: {url} ({type(last_error).__name__})")
            owner, repository, ref, rel = parts
            api_url = (
                f"https://api.github.com/repos/{quote(owner)}/{quote(repository)}/"
                f"contents/{quote(rel, safe='/')}?ref={quote(ref)}"
            )
            request = urllib.request.Request(
                api_url,
                headers={"Accept": "application/vnd.github+json", "User-Agent": "egern-rule-check"},
            )
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    require(response.status == 200 and bool(response.read(32)), f"GitHub 中不存在远程规则: {url}")
                fallback_count += 1
            except Exception as exc:
                endpoint = f"repos/{owner}/{repository}/contents/{rel}?ref={ref}"
                if shutil.which("gh"):
                    result = subprocess.run(
                        ["gh", "api", endpoint],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        check=False,
                    )
                    if result.returncode == 0:
                        fallback_count += 1
                        continue
                raise ValidationError(f"远程规则不可验证: {url} ({type(exc).__name__})") from exc
    print(f"远程规则检查：{len(urls)} 个 URL 存在，其中 {fallback_count} 个使用 GitHub API 回退。")


def main() -> int:
    parser = argparse.ArgumentParser(description="Egern 配置静态检查")
    parser.add_argument("--source", type=Path, help="私有源 Profile；仅本地隐私扫描使用")
    parser.add_argument("--private-dir", type=Path, help="仓库外私有增强版/安全版目录")
    parser.add_argument("--live-subscription", action="store_true", help="读取订阅做节点过滤验证")
    parser.add_argument("--check-remote-rules", action="store_true", help="检查运行时纯规则 URL")
    args = parser.parse_args()

    egern_root = Path(__file__).resolve().parents[1]
    repo = egern_root.parent
    enhanced_public = validate_profile(egern_root / "Profile.example.yaml", safe=False)
    validate_profile(egern_root / "Profile.safe.example.yaml", safe=True)
    validate_manifest(egern_root)
    if args.check_remote_rules:
        validate_remote_rules(enhanced_public)

    if args.private_dir:
        private_dir = args.private_dir.resolve()
        require(repo.resolve() not in private_dir.parents and private_dir != repo.resolve(), "私有目录必须位于仓库外")
        enhanced_private = validate_profile(private_dir / "Profile.enhanced.yaml", safe=False)
        safe_private = validate_profile(private_dir / "Profile.safe.yaml", safe=True)
        rollback_private = validate_profile(private_dir / "Profile.rollback.yaml", safe=True)
        require(not rollback_private.get("proxies"), "回滚版不得包含本地 UDP 快照")
        for private_profile in [enhanced_private, safe_private, rollback_private]:
            urls = policy_groups(private_profile)["订阅"][1].get("urls") or []
            require(len(urls) == 1 and urls[0] != "SUBSCRIPTION_URL", "私有配置未写入订阅 URL")

    subscription = None
    if args.source:
        if args.live_subscription:
            subscription = fetch_subscription(read_subscription_url(args.source))
            validate_live_subscription(subscription)
        privacy_scan(repo, args.source, subscription)

    print("静态检查通过：YAML、策略引用、DNS、规则顺序、模块清单与隐私边界均符合要求。")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(1)
