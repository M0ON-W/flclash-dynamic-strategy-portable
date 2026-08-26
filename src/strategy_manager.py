from __future__ import annotations

import argparse
import concurrent.futures
import copy
import datetime as dt
import ipaddress
import json
import os
import re
import shutil
import sqlite3
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml


APP_HOME = Path(os.environ["APPDATA"]) / "com.follow" / "clash"
MANAGED_DIR = APP_HOME / "managed"
SERVICE_RUNTIME = MANAGED_DIR / "mihomo-service"
SERVICE_CONFIG = SERVICE_RUNTIME / "config.yaml"
DATABASE = APP_HOME / "database.sqlite"
PREFERENCES = APP_HOME / "shared_preferences.json"
RUNTIME_CONFIG = APP_HOME / "config.yaml"
SCRIPTS_DIR = APP_HOME / "scripts"
STATE_FILE = MANAGED_DIR / "state.json"
STATUS_FILE = MANAGED_DIR / "latest_status.json"
LOG_FILE = MANAGED_DIR / "manager.log"
LOCK_FILE = MANAGED_DIR / "manager.lock"
INSTALLED_MANAGER = MANAGED_DIR / "strategy_manager.py"

SCRIPT_ID = 348822000000000101
SCRIPT_LABEL = "三组动态策略"
CONTROLLER = "http://127.0.0.1:9090"
SERVICE_CONTROLLER = "http://127.0.0.1:19090"
LISTENER_PORT_BASE = 23000
SERVICE_LISTENER_PORT_BASE = 33000
MAX_NODES = 180
FULL_SCAN_SECONDS = 20 * 60
SCAN_DUE_TOLERANCE_SECONDS = 90
SAMPLES_PER_DAY = 24 * 3
HISTORY_WINDOW_DAYS = 7
STABLE_MIN_DAYS = 3
HISTORY_SAMPLES = HISTORY_WINDOW_DAYS * SAMPLES_PER_DAY
STABLE_MIN_SAMPLES = STABLE_MIN_DAYS * SAMPLES_PER_DAY
WORKERS = 16
GEMINI_SPEED_TEST_BYTES = 1_048_576
GEMINI_MIN_SPEED_MBPS = 2.0
GEMINI_MAX_ACTIVE = 2
GEMINI_MIN_CONSECUTIVE_PASSES = 2
MIN_SCAN_ONLINE_RATIO = 0.20
MIN_SCAN_ONLINE_COUNT = 3

GROUP_CLEAN = "净选"
GROUP_STABLE = "稳净"
GROUP_FAST = "极速"
GROUP_GOOGLE_AI = "__谷歌AI"
GROUP_OPENAI = "__OpenAI"
MANAGED_GROUPS = [GROUP_CLEAN, GROUP_STABLE, GROUP_FAST]
RUNTIME_GROUPS = MANAGED_GROUPS + [GROUP_GOOGLE_AI, GROUP_OPENAI]

OPENAI_DOMAIN_SUFFIXES = (
    "openai.com",
    "chatgpt.com",
    "oaistatic.com",
    "oaiusercontent.com",
)

GOOGLE_DOMAIN_SUFFIXES = (
    "google.com",
    "googleapis.com",
    "gstatic.com",
    "googleusercontent.com",
    "youtube.com",
    "ytimg.com",
)

DEFAULT_GOOGLE_BLOCKED_MEMBERS: tuple[str, ...] = ()

RULESET_OPENAI = "__managed-openai"
RULESET_GOOGLE_GEMINI = "__managed-google-gemini"
RULESET_AI_NON_CN = "__managed-category-ai-non-cn"
RULESET_GOOGLE = "__managed-google"
RULESET_MICROSOFT_CN = "__managed-microsoft-cn"
RULESET_MICROSOFT = "__managed-microsoft"
RULESET_APPLE_CN = "__managed-apple-cn"
RULESET_APPLE = "__managed-apple"
RULESET_CN = "__managed-cn"
RULESET_GEOIP_CN = "__managed-geoip-cn"
META_RULESET_BASE = "https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/meta/geo"
MANAGED_RULESETS = {
    RULESET_OPENAI: ("geosite/openai.mrs", "domain"),
    RULESET_GOOGLE_GEMINI: ("geosite/google-gemini.mrs", "domain"),
    RULESET_AI_NON_CN: ("geosite/category-ai-!cn.mrs", "domain"),
    RULESET_GOOGLE: ("geosite/google.mrs", "domain"),
    RULESET_MICROSOFT_CN: ("geosite/microsoft@cn.mrs", "domain"),
    RULESET_MICROSOFT: ("geosite/microsoft.mrs", "domain"),
    RULESET_APPLE_CN: ("geosite/apple-cn.mrs", "domain"),
    RULESET_APPLE: ("geosite/apple.mrs", "domain"),
    RULESET_CN: ("geosite/cn.mrs", "domain"),
    RULESET_GEOIP_CN: ("geoip/cn.mrs", "ipcidr"),
}

STORE_DIRECT_RULES = (
    "PROCESS-NAME,WinStore.App.exe,DIRECT",
    "DOMAIN-SUFFIX,mp.microsoft.com,DIRECT",
    "DOMAIN,apps.microsoft.com,DIRECT",
    "DOMAIN,store-images.s-microsoft.com,DIRECT",
    "DOMAIN,store-images.microsoft.com,DIRECT",
    "DOMAIN,img-prod-cms-rt-microsoft-com.akamaized.net,DIRECT",
    "DOMAIN,login.live.com,DIRECT",
    "DOMAIN,account.live.com,DIRECT",
    "DOMAIN-SUFFIX,storequality.microsoft.com,DIRECT",
    "DOMAIN-SUFFIX,windowsupdate.com,DIRECT",
    "DOMAIN-SUFFIX,update.microsoft.com,DIRECT",
)

INFO_NODE_RE = re.compile(
    r"(剩余|流量|套餐|官网|订阅|到期|重置|客服|公告|更新|实时负载|使用说明|"
    r"traffic|expire|website|reset|official|subscribe)",
    re.IGNORECASE,
)


def log(message: str) -> None:
    MANAGED_DIR.mkdir(parents=True, exist_ok=True)
    if LOG_FILE.exists() and LOG_FILE.stat().st_size > 2_000_000:
        LOG_FILE.replace(LOG_FILE.with_suffix(".log.1"))
    stamp = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    with LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(f"{stamp} {message}\n")
    if "pythonw" not in Path(sys.executable).name.lower():
        print(message)


class SingleRunLock:
    def __enter__(self):
        MANAGED_DIR.mkdir(parents=True, exist_ok=True)
        if LOCK_FILE.exists():
            try:
                lock_pid = int(LOCK_FILE.read_text(encoding="ascii").strip())
            except (OSError, ValueError):
                lock_pid = 0
            stale = time.time() - LOCK_FILE.stat().st_mtime > 30 * 60
            if stale or not process_exists(lock_pid):
                LOCK_FILE.unlink(missing_ok=True)
        try:
            self.fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise RuntimeError("another manager run is active") from exc
        os.write(self.fd, str(os.getpid()).encode("ascii"))
        return self

    def __exit__(self, exc_type, exc, tb):
        os.close(self.fd)
        LOCK_FILE.unlink(missing_ok=True)


def process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        process_query_limited_information = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            process_query_limited_information, False, pid
        )
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return copy.deepcopy(default)


def write_json(path: Path, value) -> None:
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2))


def current_profile_id() -> int | None:
    outer = load_json(PREFERENCES, {})
    try:
        config = json.loads(outer.get("flutter.config", "{}"))
        value = config.get("currentProfileId")
        return int(value) if value is not None else None
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def profile_path(profile_id: int | None) -> Path | None:
    if profile_id is None:
        return None
    path = APP_HOME / "profiles" / f"{profile_id}.yaml"
    return path if path.exists() else None


def load_profile(profile_id: int | None) -> dict:
    path = profile_path(profile_id)
    if path is None:
        raise FileNotFoundError("current FlClash profile was not found")
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("current FlClash profile is not a YAML mapping")
    return value


def candidate_proxies(config: dict) -> list[dict]:
    candidates = []
    seen = set()
    for proxy in config.get("proxies") or []:
        if not isinstance(proxy, dict):
            continue
        name = str(proxy.get("name") or "").strip()
        if not name or name in seen or INFO_NODE_RE.search(name):
            continue
        if re.fullmatch(r"[\s=_|—-]+", name):
            continue
        seen.add(name)
        candidates.append(proxy)
        if len(candidates) >= MAX_NODES:
            break
    return candidates


def sanitize_members(names: list[str], allowed: set[str]) -> list[str]:
    result = []
    seen = set()
    for name in names:
        if name in allowed and name not in seen:
            seen.add(name)
            result.append(name)
    return result


def group_config(name: str, members: list[str]) -> dict:
    proxies = members or ["REJECT"]
    common = {
        "name": name,
        "type": "fallback" if name in {GROUP_FAST, GROUP_GOOGLE_AI, GROUP_OPENAI} else "url-test",
        "proxies": proxies,
        "interval": 600,
        "lazy": False,
        "timeout": 8000,
        "max-failed-times": 2,
        "hidden": False,
    }
    if name == GROUP_CLEAN:
        common.update(
            {
                "url": "https://www.gstatic.com/generate_204",
                "expected-status": "204",
                "tolerance": 40,
            }
        )
    elif name == GROUP_STABLE:
        common.update(
            {
                "url": "https://www.gstatic.com/generate_204",
                "expected-status": "204",
                "tolerance": 30,
            }
        )
    elif name == GROUP_FAST:
        common.update(
            {
                "url": "https://speed.cloudflare.com/__down?bytes=131072",
                "expected-status": "200",
            }
        )
    elif name == GROUP_GOOGLE_AI:
        common.update(
            {
                "url": "https://www.google.com/?hl=en",
                "expected-status": "200",
                "hidden": True,
            }
        )
    else:
        common.update(
            {
                "url": "https://api.openai.com/v1/models",
                "expected-status": "401",
                "hidden": True,
            }
        )
    return common


def managed_rule_providers() -> dict[str, dict]:
    return {
        name: {
            "type": "http",
            "url": f"{META_RULESET_BASE}/{relative_path}",
            "interval": 86400,
            "proxy": GROUP_FAST,
            "behavior": behavior,
            "format": "mrs",
        }
        for name, (relative_path, behavior) in MANAGED_RULESETS.items()
    }


def managed_rules(default_group: str) -> list[str]:
    return [
        *STORE_DIRECT_RULES,
        "DOMAIN-SUFFIX,local,DIRECT",
        "DOMAIN-SUFFIX,lan,DIRECT",
        "IP-CIDR,127.0.0.0/8,DIRECT,no-resolve",
        "IP-CIDR,10.0.0.0/8,DIRECT,no-resolve",
        "IP-CIDR,172.16.0.0/12,DIRECT,no-resolve",
        "IP-CIDR,192.168.0.0/16,DIRECT,no-resolve",
        "IP-CIDR,224.0.0.0/4,DIRECT,no-resolve",
        "IP-CIDR6,::1/128,DIRECT,no-resolve",
        "IP-CIDR6,fc00::/7,DIRECT,no-resolve",
        f"DOMAIN-SUFFIX,openai.com,{GROUP_OPENAI}",
        f"DOMAIN-SUFFIX,chatgpt.com,{GROUP_OPENAI}",
        f"DOMAIN-SUFFIX,oaistatic.com,{GROUP_OPENAI}",
        f"DOMAIN-SUFFIX,oaiusercontent.com,{GROUP_OPENAI}",
        f"RULE-SET,{RULESET_OPENAI},{GROUP_OPENAI}",
        f"DOMAIN,webchannel-robinfrontend-pa.googleapis.com,{GROUP_GOOGLE_AI}",
        f"DOMAIN-SUFFIX,google.com,{GROUP_GOOGLE_AI}",
        f"DOMAIN-SUFFIX,googleapis.com,{GROUP_GOOGLE_AI}",
        f"DOMAIN-SUFFIX,gstatic.com,{GROUP_GOOGLE_AI}",
        f"RULE-SET,{RULESET_GOOGLE_GEMINI},{GROUP_GOOGLE_AI}",
        f"RULE-SET,{RULESET_AI_NON_CN},{GROUP_CLEAN}",
        f"RULE-SET,{RULESET_GOOGLE},{GROUP_GOOGLE_AI}",
        f"RULE-SET,{RULESET_MICROSOFT_CN},DIRECT",
        f"RULE-SET,{RULESET_APPLE_CN},DIRECT",
        "DOMAIN-SUFFIX,apple.com.cn,DIRECT",
        "DOMAIN-SUFFIX,icloud.com.cn,DIRECT",
        f"RULE-SET,{RULESET_MICROSOFT},{GROUP_FAST}",
        f"RULE-SET,{RULESET_APPLE},{GROUP_FAST}",
        f"RULE-SET,{RULESET_CN},DIRECT",
        f"DOMAIN-SUFFIX,cloudflare.com,{GROUP_CLEAN}",
        f"RULE-SET,{RULESET_GEOIP_CN},DIRECT,no-resolve",
        f"MATCH,{default_group}",
    ]


def strict_dns(dns_proxy: str | None = None) -> dict:
    route = f"#{dns_proxy}" if dns_proxy else ""
    domestic_doh = [
        f"https://223.5.5.5/dns-query#{GROUP_FAST}",
        f"https://223.6.6.6/dns-query#{GROUP_FAST}",
    ]
    return {
        "enable": True,
        "listen": "127.0.0.1:1053",
        "cache-algorithm": "arc",
        "prefer-h3": False,
        "use-hosts": True,
        "use-system-hosts": False,
        "respect-rules": True,
        "ipv6": False,
        "default-nameserver": ["1.1.1.1", "8.8.8.8"],
        "enhanced-mode": "fake-ip",
        "fake-ip-range": "198.18.0.1/16",
        "fake-ip-filter-mode": "blacklist",
        "fake-ip-filter": ["*.lan", "*.local", "localhost", "localhost.*"],
        "nameserver": [
            f"https://1.1.1.1/dns-query{route}",
            f"https://8.8.8.8/dns-query{route}",
        ],
        "proxy-server-nameserver": [
            "https://1.1.1.1/dns-query",
            "https://8.8.8.8/dns-query",
        ],
        "fallback": [],
        "nameserver-policy": {
            f"rule-set:{RULESET_CN}": domestic_doh,
            f"rule-set:{RULESET_MICROSOFT_CN}": domestic_doh,
            f"rule-set:{RULESET_APPLE_CN}": domestic_doh,
            "+.apple.com.cn": domestic_doh,
            "+.icloud.com.cn": domestic_doh,
        },
    }


def build_effective_config(raw: dict, state: dict, tun_enable: bool = True) -> dict:
    config = copy.deepcopy(raw)
    proxies = candidate_proxies(config)
    names = [str(proxy["name"]) for proxy in proxies]
    allowed = set(names)
    memberships = state.get("memberships") or {}
    last_known_good = state.get("last_known_good") or {}
    last_memberships = last_known_good.get("memberships") or {}
    clean = sanitize_members(
        memberships.get(GROUP_CLEAN) or last_memberships.get(GROUP_CLEAN) or [],
        allowed,
    )
    stable = sanitize_members(
        memberships.get(GROUP_STABLE) or last_memberships.get(GROUP_STABLE) or [],
        allowed,
    )
    fast = sanitize_members(
        memberships.get(GROUP_FAST) or last_memberships.get(GROUP_FAST) or [],
        allowed,
    )
    google_ai = sanitize_members(
        state.get("gemini_members")
        or last_known_good.get("gemini_members")
        or state.get("gemini_verified_members")
        or [],
        allowed,
    )
    openai = sanitize_members(
        state.get("openai_members")
        or last_known_good.get("openai_members")
        or state.get("openai_verified_members")
        or [],
        allowed,
    )
    if not fast:
        fast = names[:20]
    if not stable and state.get("stable_provisional"):
        stable = clean

    config["proxy-groups"] = [
        group_config(GROUP_CLEAN, clean),
        group_config(GROUP_STABLE, stable),
        group_config(GROUP_FAST, fast),
        group_config(GROUP_GOOGLE_AI, google_ai),
        group_config(GROUP_OPENAI, openai),
    ]
    existing_rule_providers = config.get("rule-providers")
    rule_providers = (
        copy.deepcopy(existing_rule_providers)
        if isinstance(existing_rule_providers, dict)
        else {}
    )
    rule_providers.update(managed_rule_providers())
    config["rule-providers"] = rule_providers
    default_group = (
        GROUP_STABLE
        if memberships.get(GROUP_STABLE) and not state.get("stable_provisional")
        else GROUP_FAST
    )
    config["rules"] = managed_rules(default_group)
    config["allow-lan"] = False
    config["bind-address"] = "127.0.0.1"
    config["ipv6"] = False
    config["tcp-concurrent"] = True
    config["unified-delay"] = True
    config["keep-alive-interval"] = 15
    config["keep-alive-idle"] = 15
    config["disable-keep-alive"] = False
    config["external-controller"] = "127.0.0.1:9090"
    config["dns"] = strict_dns(state.get("dns_proxy"))
    tun = dict(config.get("tun") or {})
    tun.update(
        {
            "enable": tun_enable,
            "device": "FlClash",
            "stack": "mixed",
            "auto-route": True,
            "auto-detect-interface": True,
            "dns-hijack": ["any:53", "tcp://any:53"],
            "strict-route": True,
            "endpoint-independent-nat": False,
            "route-address": [],
        }
    )
    config["tun"] = tun

    preserved_listeners = []
    for listener in config.get("listeners") or []:
        if isinstance(listener, dict) and not str(listener.get("name", "")).startswith("__flt_"):
            preserved_listeners.append(listener)
    for index, name in enumerate(names):
        preserved_listeners.append(
            {
                "name": f"__flt_{index:03d}",
                "type": "mixed",
                "port": LISTENER_PORT_BASE + index,
                "listen": "127.0.0.1",
                "proxy": name,
                "udp": False,
                "users": [],
            }
        )
    config["listeners"] = preserved_listeners
    return config


def build_service_config(raw: dict, state: dict) -> dict:
    config = build_effective_config(
        raw,
        state,
        tun_enable=bool(state.get("service_tun_enabled")),
    )
    config["mode"] = "rule"
    config["mixed-port"] = 17890
    config["port"] = 0
    config["socks-port"] = 0
    config["external-controller"] = "127.0.0.1:19090"
    config["dns"]["listen"] = "127.0.0.1:11053"
    config["tun"]["device"] = "MihomoSvc"
    config["find-process-mode"] = "always"
    config["rules"] = [
        "PROCESS-NAME,FlClashCore.exe,DIRECT",
        "PROCESS-NAME,FlClash.exe,DIRECT",
    ] + list(config.get("rules") or [])
    listeners = []
    for listener in config.get("listeners") or []:
        if not isinstance(listener, dict):
            continue
        updated = copy.deepcopy(listener)
        name = str(updated.get("name") or "")
        if name.startswith("__flt_"):
            try:
                index = int(name.rsplit("_", 1)[1])
                updated["port"] = SERVICE_LISTENER_PORT_BASE + index
            except ValueError:
                continue
        listeners.append(updated)
    config["listeners"] = listeners
    return config


def write_service_config(state: dict, raw: dict | None = None) -> dict:
    if raw is None:
        raw = load_profile(current_profile_id())
    config = build_service_config(raw, state)
    require_nonempty_runtime_groups(config)
    SERVICE_RUNTIME.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        SERVICE_CONFIG,
        yaml.safe_dump(config, allow_unicode=True, sort_keys=False, width=4096),
    )
    return config


def generate_override_script(state: dict) -> str:
    memberships = state.get("memberships") or {}
    last_known_good = state.get("last_known_good") or {}
    last_memberships = last_known_good.get("memberships") or {}
    google_ai_members = (
        state.get("gemini_members")
        or last_known_good.get("gemini_members")
        or state.get("gemini_verified_members")
        or []
    )
    openai_members = (
        state.get("openai_members")
        or last_known_good.get("openai_members")
        or state.get("openai_verified_members")
        or []
    )
    clean_members = memberships.get(GROUP_CLEAN) or last_memberships.get(GROUP_CLEAN) or []
    stable_members = memberships.get(GROUP_STABLE) or last_memberships.get(GROUP_STABLE) or []
    if not stable_members and state.get("stable_provisional"):
        stable_members = clean_members
    clean = json.dumps(clean_members, ensure_ascii=False)
    stable = json.dumps(stable_members, ensure_ascii=False)
    fast = json.dumps(
        memberships.get(GROUP_FAST) or last_memberships.get(GROUP_FAST) or [],
        ensure_ascii=False,
    )
    google_ai = json.dumps(google_ai_members, ensure_ascii=False)
    openai = json.dumps(openai_members, ensure_ascii=False)
    default_group = GROUP_STABLE if memberships.get(GROUP_STABLE) and not state.get("stable_provisional") else GROUP_FAST
    rules = json.dumps(managed_rules(default_group), ensure_ascii=False)
    rule_providers = json.dumps(managed_rule_providers(), ensure_ascii=False)
    dns = json.dumps(strict_dns(state.get("dns_proxy")), ensure_ascii=False)
    tun_enabled = "true" if state.get("tun_enabled") else "false"
    return f'''/* Managed by FlClash strategy_manager.py. */
function main(config) {{
  if (!config || typeof config !== 'object') return config;
  var cleanMembers = {clean};
  var stableMembers = {stable};
  var fastMembers = {fast};
  var googleAiMembers = {google_ai};
  var openaiMembers = {openai};
  var proxyNames = [];
  var rawProxies = Array.isArray(config.proxies) ? config.proxies : [];
  var infoPattern = /(剩余|流量|套餐|官网|订阅|到期|重置|客服|公告|更新|实时负载|使用说明|traffic|expire|website|reset|official|subscribe)/i;
  for (var i = 0; i < rawProxies.length && proxyNames.length < {MAX_NODES}; i++) {{
    var name = rawProxies[i] && rawProxies[i].name;
    if (typeof name === 'string' && name && !infoPattern.test(name) && proxyNames.indexOf(name) < 0) proxyNames.push(name);
  }}
  function validMembers(items) {{
    var out = [];
    for (var j = 0; j < items.length; j++) {{
      if (proxyNames.indexOf(items[j]) >= 0 && out.indexOf(items[j]) < 0) out.push(items[j]);
    }}
    return out;
  }}
  cleanMembers = validMembers(cleanMembers);
  stableMembers = validMembers(stableMembers);
  fastMembers = validMembers(fastMembers);
  googleAiMembers = validMembers(googleAiMembers);
  openaiMembers = validMembers(openaiMembers);
  if (!fastMembers.length) fastMembers = proxyNames.slice(0, 20);
  function membersOrReject(items) {{ return items.length ? items : ['REJECT']; }}
  var managedRuleProviders = {rule_providers};
  var existingRuleProviders = config['rule-providers'];
  if (!existingRuleProviders || typeof existingRuleProviders !== 'object' || Array.isArray(existingRuleProviders)) existingRuleProviders = {{}};
  for (var providerName in managedRuleProviders) existingRuleProviders[providerName] = managedRuleProviders[providerName];
  config['rule-providers'] = existingRuleProviders;
  config['proxy-groups'] = [
    {{name:'{GROUP_CLEAN}',type:'url-test',proxies:membersOrReject(cleanMembers),url:'https://www.gstatic.com/generate_204','expected-status':'204',interval:600,lazy:false,timeout:8000,'max-failed-times':2,tolerance:40,hidden:false}},
    {{name:'{GROUP_STABLE}',type:'url-test',proxies:membersOrReject(stableMembers),url:'https://www.gstatic.com/generate_204','expected-status':'204',interval:600,lazy:false,timeout:8000,'max-failed-times':2,tolerance:30,hidden:false}},
    {{name:'{GROUP_FAST}',type:'fallback',proxies:membersOrReject(fastMembers),url:'https://speed.cloudflare.com/__down?bytes=131072','expected-status':'200',interval:600,lazy:false,timeout:8000,'max-failed-times':2,hidden:false}},
    {{name:'{GROUP_GOOGLE_AI}',type:'fallback',proxies:membersOrReject(googleAiMembers),url:'https://www.google.com/?hl=en','expected-status':'200',interval:600,lazy:false,timeout:8000,'max-failed-times':2,hidden:true}},
    {{name:'{GROUP_OPENAI}',type:'fallback',proxies:membersOrReject(openaiMembers),url:'https://api.openai.com/v1/models','expected-status':'401',interval:600,lazy:false,timeout:8000,'max-failed-times':2,hidden:true}}
  ];
  config.rules = {rules};
  config['allow-lan'] = false;
  config['bind-address'] = '127.0.0.1';
  config.ipv6 = false;
  config['tcp-concurrent'] = true;
  config['unified-delay'] = true;
  config['keep-alive-interval'] = 15;
  config['keep-alive-idle'] = 15;
  config['disable-keep-alive'] = false;
  config.dns = {dns};
  var tun = config.tun && typeof config.tun === 'object' ? config.tun : {{}};
  tun.enable = {tun_enabled};
  tun.device = 'FlClash';
  tun.stack = 'mixed';
  tun['auto-route'] = true;
  tun['auto-detect-interface'] = true;
  tun['dns-hijack'] = ['any:53','tcp://any:53'];
  tun['strict-route'] = true;
  tun['endpoint-independent-nat'] = false;
  tun['route-address'] = [];
  config.tun = tun;
  var listeners = [];
  var existing = Array.isArray(config.listeners) ? config.listeners : [];
  for (var k = 0; k < existing.length; k++) {{
    if (!existing[k] || String(existing[k].name || '').indexOf('__flt_') !== 0) listeners.push(existing[k]);
  }}
  for (var n = 0; n < proxyNames.length; n++) {{
    listeners.push({{name:'__flt_' + ('000' + n).slice(-3),type:'mixed',port:{LISTENER_PORT_BASE}+n,listen:'127.0.0.1',proxy:proxyNames[n],udp:false,users:[]}});
  }}
  config.listeners = listeners;
  return config;
}}
'''


def ensure_script_binding(script_text: str, clear_old: bool = False) -> None:
    now = int(time.time())
    with sqlite3.connect(DATABASE, timeout=20) as connection:
        if clear_old:
            connection.execute("DELETE FROM profile_rule_mapping")
            connection.execute("DELETE FROM rules")
            connection.execute("DELETE FROM proxy_groups")
            connection.execute("DELETE FROM scripts")
        connection.execute(
            "INSERT OR REPLACE INTO scripts(id,label,last_update_time) VALUES(?,?,?)",
            (SCRIPT_ID, SCRIPT_LABEL, now),
        )
        connection.execute(
            "UPDATE profiles SET overwrite_type='script', script_id=?",
            (SCRIPT_ID,),
        )
        connection.commit()
    SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_text(SCRIPTS_DIR / f"{SCRIPT_ID}.js", script_text)
    if clear_old:
        for old_script in SCRIPTS_DIR.glob("*.js"):
            if old_script.name != f"{SCRIPT_ID}.js":
                old_script.unlink(missing_ok=True)


def update_preferences(state: dict, enable_tun: bool | None = None) -> None:
    if enable_tun is None:
        enable_tun = bool(state.get("tun_enabled"))
    outer = load_json(PREFERENCES, {})
    config = json.loads(outer.get("flutter.config", "{}"))
    config["overrideDns"] = False
    app = config.setdefault("appSettingProps", {})
    app["autoLaunch"] = True
    app["silentLaunch"] = True
    app["autoRun"] = True
    network = config.setdefault("networkProps", {})
    network["systemProxy"] = True
    network["autoSetSystemDns"] = True
    network["appendSystemDns"] = False
    network["routeMode"] = "config"
    patch = config.setdefault("patchClashConfig", {})
    patch["mode"] = "rule"
    patch["allow-lan"] = False
    patch["ipv6"] = False
    patch["tcp-concurrent"] = True
    patch["unified-delay"] = True
    patch["dns"] = strict_dns(state.get("dns_proxy"))
    tun = patch.setdefault("tun", {})
    tun.update(
        {
            "enable": enable_tun,
            "device": "FlClash",
            "auto-route": True,
            "stack": "mixed",
            "dns-hijack": ["any:53", "tcp://any:53"],
            "route-address": [],
        }
    )
    outer["flutter.config"] = json.dumps(config, ensure_ascii=False, separators=(",", ":"))
    outer.setdefault("flutter.version", 1)
    write_json(PREFERENCES, outer)


def controller_request(path: str, method: str = "GET", payload: dict | None = None, timeout: float = 10):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        CONTROLLER + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read()
        return response.status, body


def service_controller_request(
    path: str,
    method: str = "GET",
    payload: dict | None = None,
    timeout: float = 10,
):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        SERVICE_CONTROLLER + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read()
        return response.status, body


def service_controller_online() -> bool:
    try:
        status, _ = service_controller_request("/version", timeout=3)
        return status == 200
    except Exception:
        return False


def controller_has_domain_connections(request_func, suffixes: tuple[str, ...]) -> bool:
    try:
        _, body = request_func("/connections", timeout=5)
        connections = json.loads(body).get("connections") or []
    except Exception:
        return False
    for connection in connections:
        metadata = connection.get("metadata") or {}
        hosts = (
            metadata.get("host"),
            metadata.get("sniffHost"),
            metadata.get("destinationIP"),
        )
        for host in hosts:
            normalized = str(host or "").lower().rstrip(".")
            if any(
                normalized == suffix or normalized.endswith("." + suffix)
                for suffix in suffixes
            ):
                return True
    return False


def openai_connections_active() -> bool:
    return controller_has_domain_connections(
        controller_request, OPENAI_DOMAIN_SUFFIXES
    ) or controller_has_domain_connections(
        service_controller_request, OPENAI_DOMAIN_SUFFIXES
    )


def google_connections_active() -> bool:
    return controller_has_domain_connections(
        controller_request, GOOGLE_DOMAIN_SUFFIXES
    ) or controller_has_domain_connections(
        service_controller_request, GOOGLE_DOMAIN_SUFFIXES
    )


def protected_connections_active() -> bool:
    return openai_connections_active() or google_connections_active()


def sync_service_config(state: dict, raw: dict | None = None) -> dict:
    config = write_service_config(state, raw)
    if service_controller_online():
        service_controller_request(
            "/configs?force=true",
            method="PUT",
            payload={"path": str(SERVICE_CONFIG)},
            timeout=20,
        )
    return config


def set_service_tun(enabled: bool) -> dict:
    if not service_controller_online():
        raise RuntimeError("independent Mihomo service is offline")
    state = load_json(STATE_FILE, {"memberships": {}, "history": {}, "reputation": {}})
    previous = bool(state.get("service_tun_enabled"))
    state["service_tun_enabled"] = enabled
    write_json(STATE_FILE, state)
    try:
        sync_service_config(state)
        time.sleep(1.5)
        _, body = service_controller_request("/configs", timeout=5)
        runtime = json.loads(body)
        active = bool((runtime.get("tun") or {}).get("enable"))
        if active != enabled:
            raise RuntimeError("independent Mihomo service did not apply the requested TUN state")
    except Exception:
        state["service_tun_enabled"] = previous
        write_json(STATE_FILE, state)
        try:
            sync_service_config(state)
        except Exception:
            pass
        raise
    status = {
        "time": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "service_tun_enabled": enabled,
        "previous_service_tun_enabled": previous,
    }
    log(f"independent service TUN set to {'on' if enabled else 'off'}")
    return status


def controller_online() -> bool:
    try:
        status, _ = controller_request("/version", timeout=3)
        return status == 200
    except Exception:
        return False


def current_global_target() -> str | None:
    try:
        _, body = controller_request("/proxies/GLOBAL", timeout=5)
        value = json.loads(body)
        now = value.get("now")
        return str(now) if now else None
    except Exception:
        return None


def select_global(name: str) -> None:
    controller_request(
        "/proxies/GLOBAL",
        method="PUT",
        payload={"name": name},
        timeout=8,
    )


def mixed_port_health(
    expect_openai: bool,
    expect_google: bool = False,
    proxy_port: int = 7890,
) -> tuple[bool, dict]:
    checks = {
        "cloudflare": ("https://cp.cloudflare.com/generate_204", {204}),
    }
    if expect_google:
        checks["google_search"] = ("https://www.google.com/?hl=en", {200})
        checks["google_204"] = ("https://www.gstatic.com/generate_204", {204})
        checks["google_accounts"] = (
            "https://accounts.google.com/ServiceLogin",
            {200, 302, 303},
        )
        checks["gemini"] = ("https://gemini.google.com/app", {200})
    else:
        checks["google"] = ("https://www.gstatic.com/generate_204", {204})
    if expect_openai:
        checks["openai"] = ("https://api.openai.com/v1/models", {401})
        checks["gemini"] = ("https://gemini.google.com/app", {200, 301, 302, 303, 307, 308})
    outcomes = {}
    for label, (url, expected) in checks.items():
        for attempt in range(3):
            probe = curl_probe(
                proxy_port,
                url,
                capture_body=label in {"google_search", "google_accounts", "gemini"},
                timeout=18 if expect_google else 12,
                connect_timeout=8 if expect_google else 4,
            )
            outcomes[label] = probe.get("status")
            valid = probe.get("ok") and probe.get("status") in expected
            if label == "google_search":
                valid = valid and not probe.get("redirect_url") and not google_risk_page(probe)
            elif label == "google_accounts":
                valid = valid and same_site_redirect(probe, "accounts.google.com") and not google_risk_page(probe)
            elif label == "gemini" and expect_google:
                valid = valid and not google_risk_page(probe)
            if valid:
                break
            if attempt < 2:
                time.sleep(0.6)
        else:
            return False, outcomes
    return True, outcomes


def reload_config(config: dict, allow_tun_fallback: bool) -> tuple[bool, str | None]:
    text = yaml.safe_dump(config, allow_unicode=True, sort_keys=False, width=4096)
    atomic_write_text(RUNTIME_CONFIG, text)
    try:
        controller_request(
            "/configs?force=true",
            method="PUT",
            payload={"path": str(RUNTIME_CONFIG)},
            timeout=20,
        )
        return True, None
    except Exception as exc:
        error = str(exc)
        if not allow_tun_fallback:
            return False, error
        fallback = copy.deepcopy(config)
        fallback.setdefault("tun", {})["enable"] = False
        atomic_write_text(
            RUNTIME_CONFIG,
            yaml.safe_dump(fallback, allow_unicode=True, sort_keys=False, width=4096),
        )
        try:
            controller_request(
                "/configs?force=true",
                method="PUT",
                payload={"path": str(RUNTIME_CONFIG)},
                timeout=20,
            )
            return True, "TUN reload failed; scan used a temporary non-TUN runtime: " + error
        except Exception as fallback_exc:
            return False, error + "; fallback also failed: " + str(fallback_exc)


def curl_probe(
    port: int,
    url: str,
    capture_body: bool = False,
    timeout: int = 12,
    connect_timeout: int = 4,
) -> dict:
    marker = "__FLM__"
    args = [
        "curl.exe",
        "--silent",
        "--show-error",
        "--connect-timeout",
        str(connect_timeout),
        "--max-time",
        str(timeout),
        "--proxy",
        f"http://127.0.0.1:{port}",
    ]
    if not capture_body:
        args.extend(["--output", "NUL"])
    args.extend(
        [
            "--write-out",
            f"\\n{marker}%{{http_code}}|%{{time_starttransfer}}|%{{speed_download}}|%{{size_download}}|%{{redirect_url}}",
            url,
        ]
    )
    started = time.perf_counter()
    try:
        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        result = subprocess.run(
            args,
            capture_output=True,
            timeout=timeout + 3,
            creationflags=creation_flags,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": str(exc), "elapsed_ms": int((time.perf_counter() - started) * 1000)}
    output = result.stdout.decode("utf-8", "replace")
    body, separator, metrics = output.rpartition("\n" + marker)
    if not separator:
        return {
            "ok": False,
            "error": result.stderr.decode("utf-8", "replace")[:200],
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
        }
    try:
        code_text, ttfb_text, speed_text, size_text, redirect_url = metrics.strip().split("|", 4)
        return {
            "ok": result.returncode == 0,
            "status": int(code_text),
            "ttfb_ms": round(float(ttfb_text) * 1000, 1),
            "speed_bps": float(speed_text),
            "size": int(float(size_text)),
            "redirect_url": redirect_url,
            "body": body if capture_body else "",
            "error": result.stderr.decode("utf-8", "replace")[:200],
        }
    except (ValueError, TypeError) as exc:
        return {"ok": False, "error": str(exc), "elapsed_ms": int((time.perf_counter() - started) * 1000)}


def google_risk_page(probe: dict) -> bool:
    body = str(probe.get("body") or "").lower()
    redirect = str(probe.get("redirect_url") or "").lower()
    return any(marker in body or marker in redirect for marker in ("/sorry/", "unusual traffic"))


def same_site_redirect(probe: dict, suffix: str) -> bool:
    redirect = str(probe.get("redirect_url") or "")
    if not redirect:
        return True
    try:
        host = str(urllib.parse.urlparse(redirect).hostname or "").lower()
    except ValueError:
        return False
    return host == suffix or host.endswith("." + suffix)


def probe_node(index: int, name: str, listener_port_base: int = LISTENER_PORT_BASE) -> dict:
    port = listener_port_base + index
    ip_result = curl_probe(port, "https://api.ipify.org?format=json", capture_body=True)
    exit_ip = None
    if ip_result.get("ok") and ip_result.get("status") == 200:
        try:
            candidate = json.loads(ip_result.get("body") or "{}").get("ip")
            exit_ip = str(ipaddress.ip_address(candidate))
        except (ValueError, TypeError, json.JSONDecodeError):
            exit_ip = None
    probes = {
        "cloudflare": curl_probe(port, "https://cp.cloudflare.com/generate_204"),
        "google": curl_probe(port, "https://www.gstatic.com/generate_204"),
        "openai": curl_probe(port, "https://api.openai.com/v1/models"),
        "gemini": curl_probe(port, "https://gemini.google.com/app"),
        "speed": curl_probe(port, "https://speed.cloudflare.com/__down?bytes=131072", timeout=15),
    }
    service_ok = (
        probes["cloudflare"].get("status") == 204
        and probes["google"].get("status") == 204
        and probes["openai"].get("status") == 401
        and probes["gemini"].get("status") in {200, 301, 302, 303, 307, 308}
    )
    online = bool(exit_ip) and probes["cloudflare"].get("status") == 204
    return {
        "name": name,
        "exit_ip": exit_ip,
        "online": online,
        "service_ok": service_ok,
        "latency_ms": probes["cloudflare"].get("ttfb_ms"),
        "speed_mbps": round((probes["speed"].get("speed_bps") or 0) * 8 / 1_000_000, 3),
        "statuses": {key: value.get("status") for key, value in probes.items() if key != "speed"},
    }


def reputation_lookup(
    ips: list[str],
    observations: list[dict],
    names: list[str],
    listener_port_base: int = LISTENER_PORT_BASE,
) -> dict[str, dict]:
    name_index = {name: index for index, name in enumerate(names)}
    routes = {}
    for item in observations:
        ip = item.get("exit_ip")
        index = name_index.get(item.get("name"))
        if ip and index is not None and ip not in routes:
            routes[ip] = listener_port_base + index

    def lookup(ip: str) -> tuple[str, dict | None]:
        port = routes.get(ip)
        if port is None:
            return ip, None
        pc = curl_probe(
            port,
            f"https://proxycheck.io/v2/{urllib.parse.quote(ip, safe='.:')}?vpn=1&risk=1",
            capture_body=True,
            timeout=20,
        )
        ipa = curl_probe(
            port,
            f"http://ip-api.com/json/{urllib.parse.quote(ip, safe='.:')}?fields=status,message,proxy,hosting,mobile",
            capture_body=True,
            timeout=15,
        )
        try:
            pc_payload = json.loads(pc.get("body") or "{}")
            pc_item = pc_payload.get(ip) if pc_payload.get("status") in {"ok", "warning"} else None
        except json.JSONDecodeError:
            pc_item = None
        try:
            ipa_item = json.loads(ipa.get("body") or "{}")
            if ipa_item.get("status") != "success":
                ipa_item = None
        except json.JSONDecodeError:
            ipa_item = None
        if not isinstance(pc_item, dict):
            return ip, None
        try:
            risk = int(float(pc_item.get("risk", 100)))
        except (TypeError, ValueError):
            risk = 100
        return ip, {
            "checked_at": int(time.time()),
            "proxy": str(pc_item.get("proxy", "unknown")).lower(),
            "type": str(pc_item.get("type", "unknown")),
            "risk": risk,
            "ipapi_proxy": ipa_item.get("proxy") if isinstance(ipa_item, dict) else None,
            "ipapi_hosting": ipa_item.get("hosting") if isinstance(ipa_item, dict) else None,
            "ipapi_mobile": ipa_item.get("mobile") if isinstance(ipa_item, dict) else None,
        }

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        for ip, value in pool.map(lookup, ips):
            if value is not None:
                results[ip] = value
    return results


def median(values: list[float]) -> float:
    usable = [float(value) for value in values if isinstance(value, (int, float))]
    return statistics.median(usable) if usable else 0.0


def classify(
    state: dict,
    observations: list[dict],
    names: list[str],
    listener_port_base: int = LISTENER_PORT_BASE,
) -> None:
    now = int(time.time())
    reputation = state.setdefault("reputation", {})
    histories = state.setdefault("history", {})

    unique_ips = sorted({item["exit_ip"] for item in observations if item.get("exit_ip")})
    stale_ips = [
        ip
        for ip in unique_ips
        if now - int((reputation.get(ip) or {}).get("checked_at", 0)) >= 24 * 60 * 60
        or "ipapi_proxy" not in (reputation.get(ip) or {})
    ]
    reputation.update(
        reputation_lookup(stale_ips, observations, names, listener_port_base)
    )

    current = {}
    for item in observations:
        rep = reputation.get(item.get("exit_ip")) or {}
        risk = int(rep.get("risk", 100))
        proxy_type = str(rep.get("type", "unknown")).lower()
        conservative_allow = (
            risk <= 66
            and (rep.get("proxy") == "no" or proxy_type == "vpn")
            and proxy_type not in {"tor", "compromised server", "socks", "web"}
            and rep.get("ipapi_hosting") is not True
        )
        strict_rep_clean = (
            rep.get("proxy") == "no"
            and risk <= 32
            and rep.get("ipapi_proxy") is False
            and rep.get("ipapi_hosting") is False
        )
        item["reputation"] = {
            "proxy": rep.get("proxy"),
            "type": rep.get("type"),
            "risk": rep.get("risk"),
            "ipapi_proxy": rep.get("ipapi_proxy"),
            "ipapi_hosting": rep.get("ipapi_hosting"),
        }
        item["clean_now"] = bool(item.get("service_ok") and conservative_allow)
        item["strict_clean"] = bool(item.get("service_ok") and strict_rep_clean)
        sample = {
            "time": now,
            "online": bool(item.get("online")),
            "service_ok": bool(item.get("service_ok")),
            "clean": bool(item.get("strict_clean")),
            "latency_ms": item.get("latency_ms"),
            "speed_mbps": item.get("speed_mbps"),
            "exit_ip": item.get("exit_ip"),
        }
        history = histories.setdefault(item["name"], [])
        history.append(sample)
        histories[item["name"]] = history[-HISTORY_SAMPLES:]
        current[item["name"]] = item

    clean_ranked = sorted(
        [item for item in observations if item.get("strict_clean")],
        key=lambda item: (
            int((item.get("reputation") or {}).get("risk", 100)),
            item.get("latency_ms") or 999999,
            -(item.get("speed_mbps") or 0),
        ),
    )
    blocked_google = set(DEFAULT_GOOGLE_BLOCKED_MEMBERS)
    blocked_google.update(state.get("gemini_blocked_members") or [])
    verified_google = sanitize_members(
        state.get("gemini_verified_members") or state.get("gemini_members") or [],
        set(names),
    )
    discovered_google = [
        item["name"]
        for item in clean_ranked
        if item["name"] not in blocked_google
        and (item.get("statuses") or {}).get("google") == 204
        and (item.get("statuses") or {}).get("gemini") == 200
    ]
    state["gemini_verified_members"] = verified_google + [
        name for name in discovered_google if name not in verified_google
    ]
    openai_candidates = [
        item["name"]
        for item in clean_ranked
        if (item.get("statuses") or {}).get("openai") == 401
    ]
    previous_openai = sanitize_members(
        state.get("openai_members") or [], set(openai_candidates)
    )
    state["openai_members"] = previous_openai + [
        name for name in openai_candidates if name not in previous_openai
    ]

    stable_ranked = []
    fast_ranked = []
    for name in names:
        history = (histories.get(name) or [])[-HISTORY_SAMPLES:]
        if not history:
            continue
        online_rate = sum(1 for sample in history if sample.get("online")) / len(history)
        clean_rate = sum(1 for sample in history if sample.get("clean")) / len(history)
        latency = median([sample.get("latency_ms") for sample in history])
        speed = median([sample.get("speed_mbps") for sample in history])
        latest = current.get(name) or {}
        if (
            len(history) >= STABLE_MIN_SAMPLES
            and online_rate >= 0.99
            and clean_rate == 1.0
            and latest.get("strict_clean")
            and latency <= 500
            and speed >= 5
        ):
            stable_ranked.append((name, online_rate, latency, speed))
        if latest.get("online") and (latest.get("speed_mbps") or 0) > 0:
            score = speed / (1 + latency / 200) if latency else speed
            fast_ranked.append((name, score, latency, speed))

    stable_ranked.sort(key=lambda item: (-item[1], item[2], -item[3]))
    fast_ranked.sort(key=lambda item: (-item[1], item[2]))
    stable_members = [item[0] for item in stable_ranked[:20]]
    provisional_stable = False
    if not stable_members:
        stable_members = [item["name"] for item in clean_ranked[:10]]
        provisional_stable = bool(stable_members)
    state["memberships"] = {
        GROUP_CLEAN: [item["name"] for item in clean_ranked],
        GROUP_STABLE: stable_members,
        GROUP_FAST: [item[0] for item in fast_ranked[:20]],
    }
    state["stable_provisional"] = provisional_stable
    state["history_policy"] = {
        "scan_interval_minutes": FULL_SCAN_SECONDS // 60,
        "window_days": HISTORY_WINDOW_DAYS,
        "stable_min_days": STABLE_MIN_DAYS,
        "stable_min_samples": STABLE_MIN_SAMPLES,
    }
    state["last_full_scan"] = now
    state["last_observations"] = observations


def choose_dns_proxy(state: dict, names: list[str]) -> str | None:
    allowed = set(names)
    for name in state.get("gemini_members") or []:
        if name in allowed:
            state["dns_proxy"] = name
            return name
    memberships = state.get("memberships") or {}
    for group in (GROUP_CLEAN, GROUP_STABLE, GROUP_FAST):
        for name in memberships.get(group) or []:
            if name in allowed:
                state["dns_proxy"] = name
                return name
    state.pop("dns_proxy", None)
    return None


def refresh_gemini_members(
    state: dict, names: list[str], listener_port_base: int = LISTENER_PORT_BASE
) -> None:
    allowed = set(names)
    blocked = set(DEFAULT_GOOGLE_BLOCKED_MEMBERS)
    blocked.update(state.get("gemini_blocked_members") or [])
    state["gemini_blocked_members"] = sorted(blocked)
    verified = sanitize_members(
        state.get("gemini_verified_members") or state.get("gemini_members") or [],
        allowed,
    )
    verified = [name for name in verified if name not in blocked]
    if not verified:
        return
    state["gemini_verified_members"] = verified
    name_index = {name: index for index, name in enumerate(names)}

    def measure(name: str) -> dict:
        port = listener_port_base + name_index[name]
        ip_result = curl_probe(port, "https://api.ipify.org?format=json", capture_body=True)
        exit_ip = None
        if ip_result.get("ok") and ip_result.get("status") == 200:
            try:
                exit_ip = str(
                    ipaddress.ip_address(json.loads(ip_result.get("body") or "{}").get("ip"))
                )
            except (ValueError, TypeError, json.JSONDecodeError):
                exit_ip = None
        google_home = curl_probe(
            port,
            "https://www.google.com/?hl=en",
            capture_body=True,
            timeout=18,
            connect_timeout=8,
        )
        google_204 = curl_probe(
            port, "https://www.gstatic.com/generate_204", timeout=15, connect_timeout=8
        )
        accounts = curl_probe(
            port,
            "https://accounts.google.com/ServiceLogin",
            capture_body=True,
            timeout=18,
            connect_timeout=8,
        )
        gemini = curl_probe(
            port,
            "https://gemini.google.com/app",
            capture_body=True,
            timeout=18,
            connect_timeout=8,
        )
        speed = curl_probe(
            port,
            f"https://speed.cloudflare.com/__down?bytes={GEMINI_SPEED_TEST_BYTES}",
            timeout=28,
        )
        speed_mbps = round((speed.get("speed_bps") or 0) * 8 / 1_000_000, 3)
        latency_ms = float(google_home.get("ttfb_ms") or 999999)
        complete = bool(
            speed.get("ok")
            and speed.get("status") == 200
            and int(speed.get("size") or 0) >= GEMINI_SPEED_TEST_BYTES
        )
        score = speed_mbps / (1 + latency_ms / 500) if complete else 0
        regional_redirect = bool(
            google_home.get("redirect_url") or google_home.get("status") in {301, 302, 303, 307, 308}
        )
        risk_page = any(google_risk_page(probe) for probe in (google_home, accounts, gemini))
        google_ok = bool(
            exit_ip
            and google_home.get("ok")
            and google_home.get("status") == 200
            and not regional_redirect
            and not risk_page
            and google_204.get("status") == 204
            and accounts.get("status") in {200, 302, 303}
            and same_site_redirect(accounts, "accounts.google.com")
            and gemini.get("status") == 200
        )
        return {
            "name": name,
            "time": int(time.time()),
            "exit_ip": exit_ip,
            "google_ok": google_ok,
            "regional_redirect": regional_redirect,
            "risk_page": risk_page,
            "statuses": {
                "www_google": google_home.get("status"),
                "gstatic": google_204.get("status"),
                "accounts": accounts.get("status"),
                "gemini": gemini.get("status"),
            },
            "complete": complete,
            "latency_ms": latency_ms,
            "speed_mbps": speed_mbps,
            "score": round(score, 4),
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(verified))) as pool:
        measurements = list(pool.map(measure, verified))
    measurements.sort(key=lambda item: (-item["score"], item["latency_ms"]))
    previous_active = sanitize_members(
        state.get("gemini_members")
        or (state.get("last_known_good") or {}).get("gemini_members")
        or [],
        allowed,
    )
    previous_active = [name for name in previous_active if name not in blocked]
    streaks = state.setdefault("gemini_validation_streaks", {})
    previous_validation = state.get("gemini_validation") or {}
    for item in measurements:
        name = item["name"]
        previous_ip = (previous_validation.get(name) or {}).get("exit_ip")
        item["identity_changed"] = bool(
            previous_ip and item.get("exit_ip") and previous_ip != item["exit_ip"]
        )
        if item["google_ok"]:
            streaks[name] = int(streaks.get(name, 0)) + 1 if previous_ip == item["exit_ip"] else 1
        else:
            streaks[name] = 0
        item["consecutive_passes"] = streaks[name]

    eligible = [
        item
        for item in measurements
        if item["google_ok"] and item["consecutive_passes"] >= GEMINI_MIN_CONSECUTIVE_PASSES
    ]
    active = []
    if eligible:
        eligible_by_name = {item["name"]: item for item in eligible}
        primary_ip = None
        for name in previous_active:
            item = eligible_by_name.get(name)
            if item:
                primary_ip = item["exit_ip"]
                break
        if not primary_ip:
            counts = {}
            for item in eligible:
                counts[item["exit_ip"]] = counts.get(item["exit_ip"], 0) + 1
            primary_ip = max(counts, key=counts.get)
        previous_order = {name: index for index, name in enumerate(previous_active)}
        cohort = [item for item in eligible if item["exit_ip"] == primary_ip]
        cohort.sort(
            key=lambda item: (
                previous_order.get(item["name"], 999999),
                -item["score"],
                item["latency_ms"],
            )
        )
        active = [item["name"] for item in cohort[:GEMINI_MAX_ACTIVE]]
        state["gemini_primary_exit_ip"] = primary_ip
    if not active:
        hard_failed = {
            item["name"]
            for item in measurements
            if item["regional_redirect"] or item["risk_page"] or item["identity_changed"]
        }
        active = [name for name in previous_active if name not in hard_failed]
    if active:
        state["gemini_members"] = active
    state["gemini_performance"] = {item["name"]: item for item in measurements}
    state["gemini_validation"] = {item["name"]: item for item in measurements}


def remember_last_known_good(state: dict, names: list[str]) -> bool:
    allowed = set(names)
    memberships = state.get("memberships") or {}
    snapshot = {
        "memberships": {
            group: sanitize_members(memberships.get(group) or [], allowed)
            for group in MANAGED_GROUPS
        },
        "gemini_members": sanitize_members(state.get("gemini_members") or [], allowed),
        "openai_members": sanitize_members(state.get("openai_members") or [], allowed),
        "dns_proxy": state.get("dns_proxy") if state.get("dns_proxy") in allowed else None,
        "saved_at": int(time.time()),
    }
    required = [
        *(snapshot["memberships"].get(group) or [] for group in MANAGED_GROUPS),
        snapshot["gemini_members"],
        snapshot["openai_members"],
    ]
    if not all(required):
        return False
    state["last_known_good"] = snapshot
    return True


def restore_last_known_good(state: dict, names: list[str]) -> bool:
    snapshot = state.get("last_known_good") or {}
    allowed = set(names)
    memberships = snapshot.get("memberships") or {}
    clean = sanitize_members(memberships.get(GROUP_CLEAN) or [], allowed)
    stable = sanitize_members(memberships.get(GROUP_STABLE) or [], allowed)
    fast = sanitize_members(memberships.get(GROUP_FAST) or [], allowed)
    google_ai = sanitize_members(snapshot.get("gemini_members") or [], allowed)
    openai = sanitize_members(snapshot.get("openai_members") or [], allowed)
    if not all((clean, stable, fast, google_ai, openai)):
        return False
    state["memberships"] = {
        GROUP_CLEAN: clean,
        GROUP_STABLE: stable,
        GROUP_FAST: fast,
    }
    state["gemini_members"] = google_ai
    state["openai_members"] = openai
    dns_proxy = snapshot.get("dns_proxy")
    if dns_proxy in allowed:
        state["dns_proxy"] = dns_proxy
    return True


def scan_quality(state: dict, observations: list[dict], names: list[str]) -> tuple[bool, dict]:
    online_count = sum(1 for item in observations if item.get("online"))
    strict_clean_count = sum(1 for item in observations if item.get("strict_clean"))
    required_online = max(
        MIN_SCAN_ONLINE_COUNT,
        int(len(names) * MIN_SCAN_ONLINE_RATIO + 0.999),
    )
    memberships = state.get("memberships") or {}
    reasons = []
    if online_count < required_online:
        reasons.append(f"online nodes {online_count} below required {required_online}")
    if not memberships.get(GROUP_CLEAN):
        reasons.append("strict clean group collapsed to zero")
    if not memberships.get(GROUP_STABLE):
        reasons.append("stable clean group collapsed to zero")
    if not memberships.get(GROUP_FAST):
        reasons.append("fast group collapsed to zero")
    if not state.get("gemini_members"):
        reasons.append("Google group collapsed to zero")
    if not state.get("openai_members"):
        reasons.append("OpenAI group collapsed to zero")
    if any(name in set(DEFAULT_GOOGLE_BLOCKED_MEMBERS) for name in state.get("gemini_members") or []):
        reasons.append("blocked Google member re-entered the active group")
    return not reasons, {
        "accepted": not reasons,
        "reasons": reasons,
        "online_count": online_count,
        "required_online_count": required_online,
        "strict_clean_count": strict_clean_count,
    }


def require_nonempty_runtime_groups(config: dict) -> None:
    groups = {
        str(group.get("name")): list(group.get("proxies") or [])
        for group in config.get("proxy-groups") or []
        if isinstance(group, dict)
    }
    empty = [
        name
        for name in RUNTIME_GROUPS
        if not groups.get(name) or groups.get(name) == ["REJECT"]
    ]
    if empty:
        raise RuntimeError("candidate has no usable members for: " + ", ".join(empty))


def evaluate_scan(
    state: dict,
    observations: list[dict],
    names: list[str],
    listener_port_base: int,
) -> tuple[dict, dict]:
    candidate = copy.deepcopy(state)
    classify(candidate, observations, names, listener_port_base)
    refresh_gemini_members(candidate, names, listener_port_base)
    choose_dns_proxy(candidate, names)
    accepted, quality = scan_quality(candidate, observations, names)
    if accepted and remember_last_known_good(candidate, names):
        candidate.pop("last_scan_rejected", None)
        candidate["last_scan_quality"] = quality
        return candidate, quality

    rejected = copy.deepcopy(state)
    restored = restore_last_known_good(rejected, names)
    rejected.pop("pending_runtime_apply", None)
    quality["accepted"] = False
    if not restored:
        quality["reasons"].append("last-known-good groups were unavailable")
    rejected["last_scan_attempt"] = int(time.time())
    rejected["last_scan_rejected"] = quality
    return rejected, quality


def install() -> None:
    MANAGED_DIR.mkdir(parents=True, exist_ok=True)
    if Path(__file__).resolve() != INSTALLED_MANAGER.resolve():
        shutil.copy2(Path(__file__), INSTALLED_MANAGER)
    state = load_json(STATE_FILE, {"memberships": {}, "history": {}, "reputation": {}})
    raw = load_profile(current_profile_id())
    names = [str(proxy["name"]) for proxy in candidate_proxies(raw)]
    bootstrap = names[:3]
    memberships = state.setdefault("memberships", {})
    memberships[GROUP_CLEAN] = memberships.get(GROUP_CLEAN) or bootstrap
    memberships[GROUP_STABLE] = memberships.get(GROUP_STABLE) or bootstrap
    memberships[GROUP_FAST] = memberships.get(GROUP_FAST) or names[:20]
    state["gemini_members"] = state.get("gemini_members") or bootstrap
    state["openai_members"] = state.get("openai_members") or bootstrap
    state["stable_provisional"] = True
    choose_dns_proxy(state, names)
    script = generate_override_script(state)
    ensure_script_binding(script, clear_old=True)
    update_preferences(state, enable_tun=False)
    write_json(STATE_FILE, state)
    log(f"installed manager; candidates={len(names)}")


def run_once(force_scan: bool = False) -> dict:
    state = load_json(STATE_FILE, {"memberships": {}, "history": {}, "reputation": {}})
    profile_id = current_profile_id()
    raw = load_profile(profile_id)
    proxies = candidate_proxies(raw)
    names = [str(proxy["name"]) for proxy in proxies]
    script = generate_override_script(state)
    ensure_script_binding(script)

    status = {
        "time": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "profile_id": profile_id,
        "candidate_count": len(names),
        "controller_online": controller_online(),
        "scan_performed": False,
        "groups": {name: len((state.get("memberships") or {}).get(name, [])) for name in MANAGED_GROUPS},
    }
    if not status["controller_online"]:
        write_json(STATUS_FILE, status)
        log("FlClash core is offline; bindings preserved and scan skipped")
        return status

    initial_config = build_effective_config(raw, state, tun_enable=bool(state.get("tun_enabled")))
    require_nonempty_runtime_groups(initial_config)
    loaded, warning = reload_config(initial_config, allow_tun_fallback=True)
    status["initial_reload"] = loaded
    status["reload_warning"] = warning
    if not loaded:
        write_json(STATUS_FILE, status)
        log("runtime reload failed: " + str(warning))
        return status

    due = (
        int(time.time()) - int(state.get("last_full_scan", 0))
        >= FULL_SCAN_SECONDS - SCAN_DUE_TOLERANCE_SECONDS
    )
    if not (force_scan or due):
        write_json(STATUS_FILE, status)
        log("bindings checked; full scan not yet due")
        return status

    time.sleep(1.5)
    observations = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        future_map = {
            pool.submit(probe_node, index, name): name for index, name in enumerate(names)
        }
        for future in concurrent.futures.as_completed(future_map):
            name = future_map[future]
            try:
                observations.append(future.result())
            except Exception as exc:
                observations.append(
                    {
                        "name": name,
                        "exit_ip": None,
                        "online": False,
                        "service_ok": False,
                        "latency_ms": None,
                        "speed_mbps": 0,
                        "statuses": {},
                        "error": str(exc),
                    }
                )
    order = {name: index for index, name in enumerate(names)}
    observations.sort(key=lambda item: order.get(item["name"], 999999))
    state, quality = evaluate_scan(state, observations, names, LISTENER_PORT_BASE)
    write_json(STATE_FILE, state)

    if not quality["accepted"]:
        status.update(
            {
                "scan_performed": True,
                "scan_accepted": False,
                "scan_quality": quality,
                "online_count": sum(1 for item in observations if item.get("online")),
                "strict_clean_count": sum(1 for item in observations if item.get("strict_clean")),
                "groups": {
                    name: len((state.get("memberships") or {}).get(name, []))
                    for name in MANAGED_GROUPS
                },
            }
        )
        write_json(STATUS_FILE, status)
        log("full scan rejected; " + "; ".join(quality["reasons"]))
        return status

    updated_script = generate_override_script(state)
    ensure_script_binding(updated_script)
    final_config = build_effective_config(raw, state, tun_enable=bool(state.get("tun_enabled")))
    require_nonempty_runtime_groups(final_config)
    final_loaded, final_error = reload_config(final_config, allow_tun_fallback=False)
    sync_service_config(state, raw)
    status.update(
        {
            "scan_performed": True,
            "scan_accepted": True,
            "scan_quality": quality,
            "online_count": sum(1 for item in observations if item.get("online")),
            "service_clean_count": sum(1 for item in observations if item.get("service_ok")),
            "strict_clean_count": sum(1 for item in observations if item.get("strict_clean")),
            "usable_clean_count": sum(1 for item in observations if item.get("clean_now")),
            "final_reload": final_loaded,
            "final_reload_error": final_error,
            "groups": {name: len((state.get("memberships") or {}).get(name, [])) for name in MANAGED_GROUPS},
        }
    )
    write_json(STATUS_FILE, status)
    log(
        "full scan complete; "
        f"online={status['online_count']}/{len(names)} "
        f"strict_clean={status['strict_clean_count']} groups={status['groups']} "
        f"final_reload={final_loaded}"
    )
    return status


def scan_existing(listener_port_base: int = LISTENER_PORT_BASE) -> dict:
    state = load_json(STATE_FILE, {"memberships": {}, "history": {}, "reputation": {}})
    profile_id = current_profile_id()
    raw = load_profile(profile_id)
    proxies = candidate_proxies(raw)
    names = [str(proxy["name"]) for proxy in proxies]
    scan_source = "service" if listener_port_base == SERVICE_LISTENER_PORT_BASE else "flclash"
    source_online = service_controller_online() if scan_source == "service" else controller_online()
    status = {
        "time": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "profile_id": profile_id,
        "candidate_count": len(names),
        "controller_online": source_online,
        "scan_source": scan_source,
        "scan_performed": False,
        "safe_mode": "existing-listeners-only",
    }
    if not status["controller_online"]:
        write_json(STATUS_FILE, status)
        return status
    observations = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        future_map = {
            pool.submit(probe_node, index, name, listener_port_base): name
            for index, name in enumerate(names)
        }
        for future in concurrent.futures.as_completed(future_map):
            name = future_map[future]
            try:
                observations.append(future.result())
            except Exception as exc:
                observations.append(
                    {
                        "name": name,
                        "exit_ip": None,
                        "online": False,
                        "service_ok": False,
                        "latency_ms": None,
                        "speed_mbps": 0,
                        "statuses": {},
                        "error": str(exc),
                    }
                )
    order = {name: index for index, name in enumerate(names)}
    observations.sort(key=lambda item: order.get(item["name"], 999999))
    state, quality = evaluate_scan(state, observations, names, listener_port_base)
    write_json(STATE_FILE, state)
    if not quality["accepted"]:
        status.update(
            {
                "scan_performed": True,
                "scan_accepted": False,
                "scan_quality": quality,
                "online_count": sum(1 for item in observations if item.get("online")),
                "service_clean_count": sum(1 for item in observations if item.get("service_ok")),
                "strict_clean_count": sum(1 for item in observations if item.get("strict_clean")),
                "usable_clean_count": sum(1 for item in observations if item.get("clean_now")),
                "groups": {
                    name: len((state.get("memberships") or {}).get(name, []))
                    for name in MANAGED_GROUPS
                },
            }
        )
        write_json(STATUS_FILE, status)
        log("safe existing-listener scan rejected; " + "; ".join(quality["reasons"]))
        return status
    ensure_script_binding(generate_override_script(state))
    update_preferences(state)
    write_service_config(state)
    state["pending_runtime_apply"] = True
    write_json(STATE_FILE, state)
    status["runtime_apply_deferred"] = True
    status.update(
        {
            "scan_performed": True,
            "scan_accepted": True,
            "scan_quality": quality,
            "online_count": sum(1 for item in observations if item.get("online")),
            "service_clean_count": sum(1 for item in observations if item.get("service_ok")),
            "strict_clean_count": sum(1 for item in observations if item.get("strict_clean")),
            "usable_clean_count": sum(1 for item in observations if item.get("clean_now")),
            "stable_provisional": bool(state.get("stable_provisional")),
            "groups": {name: len((state.get("memberships") or {}).get(name, [])) for name in MANAGED_GROUPS},
        }
    )
    write_json(STATUS_FILE, status)
    log(
        "safe existing-listener scan complete; "
        f"online={status['online_count']}/{len(names)} strict_clean={status['strict_clean_count']} "
        f"groups={status['groups']}"
    )
    return status


def reclassify_existing() -> dict:
    state = load_json(STATE_FILE, {"memberships": {}, "history": {}, "reputation": {}})
    raw = load_profile(current_profile_id())
    names = [str(proxy["name"]) for proxy in candidate_proxies(raw)]
    observations = state.get("last_observations") or []
    if not observations:
        raise RuntimeError("no existing observations to reclassify")
    candidate = copy.deepcopy(state)
    candidate["history"] = {}
    state, quality = evaluate_scan(candidate, observations, names, LISTENER_PORT_BASE)
    write_json(STATE_FILE, state)
    if quality["accepted"]:
        ensure_script_binding(generate_override_script(state))
        update_preferences(state)
    status = {
        "time": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "profile_id": current_profile_id(),
        "candidate_count": len(names),
        "controller_online": controller_online(),
        "scan_performed": False,
        "scan_accepted": quality["accepted"],
        "scan_quality": quality,
        "safe_mode": "reputation-enrichment-only",
        "strict_clean_count": sum(1 for item in observations if item.get("strict_clean")),
        "usable_clean_count": sum(1 for item in observations if item.get("clean_now")),
        "stable_provisional": bool(state.get("stable_provisional")),
        "groups": {name: len((state.get("memberships") or {}).get(name, [])) for name in MANAGED_GROUPS},
    }
    write_json(STATUS_FILE, status)
    log(f"reputation enrichment complete; groups={status['groups']}")
    return status


def safe_apply() -> dict:
    if not controller_online():
        raise RuntimeError("FlClash core is offline")
    _, runtime_body = controller_request("/configs", timeout=5)
    runtime_before = json.loads(runtime_body)
    original_mode = str(runtime_before.get("mode") or "global")
    original_tun = bool((runtime_before.get("tun") or {}).get("enable"))
    previous_state_text = STATE_FILE.read_text(encoding="utf-8")
    previous_preferences_text = PREFERENCES.read_text(encoding="utf-8")
    previous_service_text = SERVICE_CONFIG.read_text(encoding="utf-8")
    script_path = SCRIPTS_DIR / f"{SCRIPT_ID}.js"
    previous_script_text = script_path.read_text(encoding="utf-8")

    def restore_persisted_files() -> None:
        atomic_write_text(STATE_FILE, previous_state_text)
        atomic_write_text(PREFERENCES, previous_preferences_text)
        atomic_write_text(script_path, previous_script_text)
        atomic_write_text(SERVICE_CONFIG, previous_service_text)

    state = load_json(STATE_FILE, {"memberships": {}, "history": {}, "reputation": {}})
    raw = load_profile(current_profile_id())
    original_target = current_global_target()
    names = [str(proxy["name"]) for proxy in candidate_proxies(raw)]
    restorable_targets = set(names) | set(RUNTIME_GROUPS) | {"DIRECT"}
    if original_target not in restorable_targets:
        raise RuntimeError("current GLOBAL target cannot be restored after managed reload")
    choose_dns_proxy(state, names)
    state["tun_enabled"] = original_tun
    write_json(STATE_FILE, state)
    ensure_script_binding(generate_override_script(state))
    update_preferences(state)

    previous_text = RUNTIME_CONFIG.read_text(encoding="utf-8")
    previous_config = yaml.safe_load(previous_text)
    atomic_write_text(MANAGED_DIR / "last-known-good.yaml", previous_text)
    candidate = build_effective_config(raw, state, tun_enable=original_tun)
    candidate["mode"] = original_mode
    require_nonempty_runtime_groups(candidate)
    loaded, error = reload_config(candidate, allow_tun_fallback=False)
    if not loaded:
        restore_persisted_files()
        atomic_write_text(RUNTIME_CONFIG, previous_text)
        try:
            controller_request(
                "/configs?force=true",
                method="PUT",
                payload={"path": str(RUNTIME_CONFIG)},
                timeout=20,
            )
            time.sleep(0.8)
            controller_request(
                "/configs",
                method="PATCH",
                payload={"mode": original_mode},
                timeout=5,
            )
            select_global(original_target)
        except Exception:
            pass
        raise RuntimeError("candidate reload failed: " + str(error))

    results = {}
    success = False
    try:
        deadline = time.time() + 40
        while time.time() < deadline and not managed_rule_providers_ready(controller_request):
            time.sleep(1)
        if not managed_rule_providers_ready(controller_request):
            raise RuntimeError("managed rule providers failed to load")
        results["规则集"] = {"ok": True, "count": len(MANAGED_RULESETS)}
        time.sleep(1)
        select_global(original_target)
        time.sleep(0.4)
        original_ok, original_checks = mixed_port_health(expect_openai=False)
        results["原节点"] = {"ok": original_ok, "checks": original_checks}
        if not original_ok:
            raise RuntimeError(
                f"original node failed after candidate reload: {original_checks}"
            )
        for group in [GROUP_FAST, GROUP_CLEAN, GROUP_STABLE, GROUP_GOOGLE_AI, GROUP_OPENAI]:
            if group == GROUP_GOOGLE_AI:
                members = state.get("gemini_members")
            elif group == GROUP_OPENAI:
                members = state.get("openai_members")
            else:
                members = (state.get("memberships") or {}).get(group)
            if not members:
                raise RuntimeError(f"group {group} has no configured members")
            member_checks = {}
            successful = []
            members_to_test = list(members) if group == GROUP_GOOGLE_AI else list(members)[:3]
            for member in members_to_test:
                try:
                    proxy_port = LISTENER_PORT_BASE + names.index(member)
                except ValueError:
                    member_checks[member] = {"ok": False, "checks": {"member": "missing"}}
                    continue
                ok, checks = mixed_port_health(
                    expect_openai=group == GROUP_OPENAI,
                    expect_google=group == GROUP_GOOGLE_AI,
                    proxy_port=proxy_port,
                )
                member_checks[member] = {"ok": ok, "checks": checks}
                if ok:
                    successful.append(member)
                    if group != GROUP_GOOGLE_AI:
                        break
            ok = len(successful) == len(members_to_test) if group == GROUP_GOOGLE_AI else bool(successful)
            results[group] = {"ok": ok, "members": member_checks}
            if not ok:
                raise RuntimeError(
                    f"group {group} failed connectivity verification: {member_checks}"
                )
        success = True
    finally:
        if success:
            select_global(original_target)
            time.sleep(0.4)
            restored_ok, restored_checks = mixed_port_health(expect_openai=False)
            results["恢复"] = {"ok": restored_ok, "checks": restored_checks}
            if not restored_ok:
                success = False
        if not success:
            restore_persisted_files()
            reload_config(previous_config, allow_tun_fallback=False)
            time.sleep(0.8)
            try:
                controller_request(
                    "/configs",
                    method="PATCH",
                    payload={"mode": original_mode},
                    timeout=5,
                )
                select_global(original_target)
            except Exception:
                pass

    if not success:
        raise RuntimeError("candidate was rolled back after connectivity failure")
    try:
        sync_service_config(state, raw)
        update_preferences(state)
    except Exception as exc:
        restore_persisted_files()
        reload_config(previous_config, allow_tun_fallback=False)
        try:
            service_controller_request(
                "/configs?force=true",
                method="PUT",
                payload={"path": str(SERVICE_CONFIG)},
                timeout=20,
            )
            select_global(original_target)
        except Exception:
            pass
        raise RuntimeError("service candidate failed and both cores were rolled back: " + str(exc))
    state.pop("pending_runtime_apply", None)
    write_json(STATE_FILE, state)
    status = {
        "time": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "safe_mode": f"preserve-{original_mode}-and-tun-{'on' if original_tun else 'off'}",
        "applied": True,
        "original_target_restored": True,
        "groups": {name: len((state.get("memberships") or {}).get(name, [])) for name in MANAGED_GROUPS},
        "checks": results,
    }
    write_json(STATUS_FILE, status)
    log(f"safe candidate applied and verified; groups={status['groups']}")
    return status


def managed_rule_providers_ready(request) -> bool:
    try:
        _, body = request("/providers/rules", timeout=5)
        providers = json.loads(body).get("providers") or {}
        return all(
            name in providers and int((providers.get(name) or {}).get("ruleCount", 0)) > 0
            for name in MANAGED_RULESETS
        )
    except Exception:
        return False


def managed_runtime_ready() -> bool:
    try:
        _, body = controller_request("/proxies", timeout=5)
        proxies = (json.loads(body).get("proxies") or {})
        return all(name in proxies for name in RUNTIME_GROUPS) and managed_rule_providers_ready(
            controller_request
        )
    except Exception:
        return False


def service_runtime_ready(state: dict) -> bool:
    try:
        _, proxies_body = service_controller_request("/proxies", timeout=5)
        proxies = json.loads(proxies_body).get("proxies") or {}
        _, config_body = service_controller_request("/configs", timeout=5)
        runtime = json.loads(config_body)
        tun_matches = bool((runtime.get("tun") or {}).get("enable")) == bool(
            state.get("service_tun_enabled")
        )
        return (
            tun_matches
            and all(name in proxies for name in RUNTIME_GROUPS)
            and managed_rule_providers_ready(service_controller_request)
        )
    except Exception:
        return False


def stable_progress(state: dict) -> dict:
    counts = [len(samples or []) for samples in (state.get("history") or {}).values()]
    maximum = max(counts, default=0)
    return {
        "window_days": HISTORY_WINDOW_DAYS,
        "minimum_days": STABLE_MIN_DAYS,
        "required_samples": STABLE_MIN_SAMPLES,
        "maximum_samples_collected": maximum,
        "completion_percent": round(min(maximum / STABLE_MIN_SAMPLES, 1) * 100, 1),
        "mature_node_count": sum(1 for count in counts if count >= STABLE_MIN_SAMPLES),
        "provisional": bool(state.get("stable_provisional", True)),
    }


def finish_scheduled(status: dict, state: dict) -> dict:
    update_preferences(state)
    write_json(STATUS_FILE, status)
    return status


def scheduled_safe() -> dict:
    state = load_json(STATE_FILE, {"memberships": {}, "history": {}, "reputation": {}})
    if controller_online():
        try:
            _, runtime_body = controller_request("/configs", timeout=5)
            runtime = json.loads(runtime_body)
            state["tun_enabled"] = bool((runtime.get("tun") or {}).get("enable"))
            write_json(STATE_FILE, state)
        except Exception:
            pass
    ensure_script_binding(generate_override_script(state))
    update_preferences(state)
    if service_controller_online() and not service_runtime_ready(state):
        if protected_connections_active():
            write_service_config(state)
            state["pending_runtime_apply"] = True
            write_json(STATE_FILE, state)
        else:
            sync_service_config(state)
    if not controller_online():
        due = (
            int(time.time()) - int(state.get("last_full_scan", 0))
            >= FULL_SCAN_SECONDS - SCAN_DUE_TOLERANCE_SECONDS
        )
        if service_controller_online() and due:
            scan_status = scan_existing(SERVICE_LISTENER_PORT_BASE)
            updated_state = load_json(STATE_FILE, state)
            if scan_status.get("scan_accepted") is False:
                service_apply = {"applied": False, "reason": "scan quality gate rejected candidate"}
            elif protected_connections_active():
                service_apply = {"deferred": True, "reason": "active Google/OpenAI connections"}
            else:
                sync_service_config(updated_state)
                updated_state.pop("pending_runtime_apply", None)
                write_json(STATE_FILE, updated_state)
                service_apply = {"applied": True}
            status = {
                "time": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
                "flclash_controller_online": False,
                "service_controller_online": True,
                "scan": scan_status,
                "service_apply": service_apply,
                "bindings_preserved": True,
                "stable_progress": stable_progress(updated_state),
            }
            return finish_scheduled(status, updated_state)
        status = {
            "time": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "controller_online": False,
            "scan_performed": False,
            "service_controller_online": service_controller_online(),
            "bindings_preserved": True,
        }
        log("scheduled check: FlClash is offline; bindings preserved")
        return finish_scheduled(status, state)

    if not managed_runtime_ready():
        if protected_connections_active():
            state["pending_runtime_apply"] = True
            write_json(STATE_FILE, state)
        else:
            safe_apply()
    due = (
        int(time.time()) - int(state.get("last_full_scan", 0))
        >= FULL_SCAN_SECONDS - SCAN_DUE_TOLERANCE_SECONDS
    )
    if not due:
        if state.get("pending_runtime_apply") and not protected_connections_active():
            apply_status = safe_apply()
            updated_state = load_json(STATE_FILE, state)
            status = {
                "time": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
                "scan_performed": False,
                "pending_apply_completed": True,
                "apply": apply_status,
                "stable_progress": stable_progress(updated_state),
            }
            return finish_scheduled(status, updated_state)
        status = {
            "time": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "controller_online": True,
            "scan_performed": False,
            "bindings_preserved": True,
            "groups_ready": True,
            "stable_progress": stable_progress(state),
        }
        log("scheduled check: groups present; full scan not yet due")
        return finish_scheduled(status, state)

    scan_status = scan_existing()
    if scan_status.get("scan_accepted") is False:
        apply_status = {
            "applied": False,
            "reason": "scan quality gate rejected candidate",
        }
    elif protected_connections_active():
        updated_state = load_json(STATE_FILE, state)
        updated_state["pending_runtime_apply"] = True
        write_json(STATE_FILE, updated_state)
        apply_status = {
            "deferred": True,
            "reason": "active Google/OpenAI connections",
        }
        log("runtime apply deferred; active Google/OpenAI connections preserved")
    else:
        apply_status = safe_apply()
    updated_state = load_json(STATE_FILE, state)
    status = {
        "time": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "scan": scan_status,
        "apply": apply_status,
        "stable_progress": stable_progress(updated_state),
    }
    return finish_scheduled(status, updated_state)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--force-scan", action="store_true")
    parser.add_argument("--scheduled", action="store_true")
    parser.add_argument("--scan-existing", action="store_true")
    parser.add_argument("--reclassify-existing", action="store_true")
    parser.add_argument("--safe-apply", action="store_true")
    parser.add_argument("--service-tun-on", action="store_true")
    parser.add_argument("--service-tun-off", action="store_true")
    arguments = parser.parse_args()
    try:
        with SingleRunLock():
            if arguments.safe_apply:
                status = safe_apply()
            elif arguments.service_tun_on:
                status = set_service_tun(True)
            elif arguments.service_tun_off:
                status = set_service_tun(False)
            elif arguments.scheduled:
                status = scheduled_safe()
            elif arguments.reclassify_existing:
                status = reclassify_existing()
            elif arguments.scan_existing:
                status = scan_existing()
            else:
                if arguments.install:
                    install()
                status = run_once(force_scan=arguments.force_scan or arguments.install)
            if "pythonw" not in Path(sys.executable).name.lower():
                print(json.dumps(status, ensure_ascii=False, indent=2))
        return 0
    except RuntimeError as exc:
        log(str(exc))
        return 0 if "another manager run" in str(exc) else 1
    except Exception as exc:
        log(f"fatal: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
