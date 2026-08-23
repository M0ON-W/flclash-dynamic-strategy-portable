from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import urllib.request
from pathlib import Path

import yaml


APP_HOME = Path(os.environ["APPDATA"]) / "com.follow" / "clash"
INFO_NODE_RE = re.compile(
    r"(剩余|流量|套餐|官网|订阅|到期|重置|客服|公告|更新|实时负载|使用说明|"
    r"traffic|expire|website|reset|official|subscribe)",
    re.IGNORECASE,
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def controller_headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    config_path = APP_HOME / "config.yaml"
    if config_path.exists():
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        secret = str(config.get("secret") or "")
        if secret:
            headers["Authorization"] = f"Bearer {secret}"
    return headers


def main() -> int:
    errors: list[str] = []
    preferences_path = APP_HOME / "shared_preferences.json"
    database_path = APP_HOME / "database.sqlite"
    if not preferences_path.exists():
        errors.append("找不到 FlClash shared_preferences.json")
    if not database_path.exists():
        errors.append("找不到 FlClash database.sqlite")
    if errors:
        print(json.dumps({"ok": False, "errors": errors}, ensure_ascii=False, indent=2))
        return 1

    outer = load_json(preferences_path)
    config = json.loads(outer.get("flutter.config", "{}"))
    profile_id = config.get("currentProfileId")
    profile_path = APP_HOME / "profiles" / f"{profile_id}.yaml"
    if profile_id is None or not profile_path.exists():
        errors.append("FlClash 没有可读取的当前配置文件")
        profile = {}
    else:
        profile = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}

    candidates = []
    for proxy in profile.get("proxies") or []:
        if not isinstance(proxy, dict):
            continue
        name = str(proxy.get("name") or "").strip()
        if name and not INFO_NODE_RE.search(name):
            candidates.append(name)
    if not candidates:
        errors.append("当前配置没有内联代理节点；只有 proxy-providers 的配置暂不兼容")

    required_columns = {
        "scripts": {"id", "label", "last_update_time"},
        "profiles": {"script_id", "overwrite_type"},
    }
    required_tables = {"scripts", "profiles", "profile_rule_mapping", "rules", "proxy_groups"}
    with sqlite3.connect(f"file:{database_path}?mode=ro", uri=True, timeout=5) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing_tables = sorted(required_tables - tables)
        if missing_tables:
            errors.append("数据库缺少表: " + ", ".join(missing_tables))
        for table, expected in required_columns.items():
            if table not in tables:
                continue
            columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
            missing = sorted(expected - columns)
            if missing:
                errors.append(f"数据库表 {table} 缺少字段: " + ", ".join(missing))

    controller_ok = False
    try:
        request = urllib.request.Request(
            "http://127.0.0.1:9090/version", headers=controller_headers()
        )
        with urllib.request.urlopen(request, timeout=4) as response:
            controller_ok = response.status == 200
    except Exception:
        pass
    if not controller_ok:
        errors.append("FlClash 核心控制端口 127.0.0.1:9090 不可用；请先启动 FlClash")

    result = {
        "ok": not errors,
        "python": sys.version.split()[0],
        "app_home": str(APP_HOME),
        "profile_id": profile_id,
        "candidate_count": len(candidates),
        "controller_online": controller_ok,
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
