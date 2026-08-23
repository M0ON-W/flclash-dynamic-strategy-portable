from __future__ import annotations

import argparse
import json
import os
import subprocess
import urllib.request
from pathlib import Path

import yaml


APP_HOME = Path(os.environ["APPDATA"]) / "com.follow" / "clash"
SERVICE_CONFIG = APP_HOME / "managed" / "mihomo-service" / "config.yaml"


def headers(config_path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        secret = str(config.get("secret") or "")
        if secret:
            result["Authorization"] = f"Bearer {secret}"
    except (OSError, yaml.YAMLError):
        pass
    return result


def request_json(base: str, path: str, config_path: Path) -> dict:
    request = urllib.request.Request(base + path, headers=headers(config_path))
    with urllib.request.urlopen(request, timeout=6) as response:
        return json.loads(response.read())


def curl_status(arguments: list[str]) -> int:
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    result = subprocess.run(
        [
            "curl.exe",
            "--silent",
            "--show-error",
            "--output",
            "NUL",
            "--write-out",
            "%{http_code}",
            "--connect-timeout",
            "5",
            "--max-time",
            "12",
            *arguments,
        ],
        capture_output=True,
        timeout=15,
        creationflags=flags,
    )
    try:
        return int(result.stdout.decode("ascii", "ignore")[-3:])
    except ValueError:
        return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-tun-check", action="store_true")
    args = parser.parse_args()
    checks: dict[str, object] = {}
    errors: list[str] = []
    runtime_config = APP_HOME / "config.yaml"

    try:
        proxies = request_json("http://127.0.0.1:9090", "/proxies", runtime_config).get("proxies") or {}
        expected_groups = {"净选", "稳净", "极速", "__谷歌AI"}
        present = sorted(expected_groups & set(proxies))
        checks["flclash_groups"] = present
        if set(present) != expected_groups:
            errors.append("FlClash 运行时缺少动态策略组")

        rules = request_json("http://127.0.0.1:9090", "/rules", runtime_config).get("rules") or []
        match_rules = [item for item in rules if str(item.get("type")).lower() == "match"]
        match_target = match_rules[-1].get("proxy") if match_rules else None
        checks["match_target"] = match_target
        if match_target not in {"极速", "稳净"}:
            errors.append("默认 MATCH 规则没有指向 极速/稳净")
        google_routes = {
            item.get("payload"): item.get("proxy")
            for item in rules
            if item.get("payload") in {"google.com", "googleapis.com", "gstatic.com"}
        }
        checks["google_routes"] = google_routes
        if len(google_routes) != 3 or set(google_routes.values()) != {"__谷歌AI"}:
            errors.append("Google/Gemini 域名没有全部指向专用动态组")
    except Exception as exc:
        errors.append(f"FlClash 控制器检查失败: {exc}")

    try:
        service = request_json("http://127.0.0.1:19090", "/configs", SERVICE_CONFIG)
        service_tun = bool((service.get("tun") or {}).get("enable"))
        checks["service_tun"] = service_tun
        if not args.skip_tun_check and not service_tun:
            errors.append("独立服务 TUN 未启用")
    except Exception as exc:
        errors.append(f"独立服务控制器检查失败: {exc}")

    proxy_google = curl_status(
        ["--proxy", "http://127.0.0.1:7890", "https://www.google.com/generate_204"]
    )
    checks["proxy_google_http"] = proxy_google
    if proxy_google != 204:
        errors.append("FlClash 7890 入口无法访问 Google 204")

    if not args.skip_tun_check:
        tun_google = curl_status(
            ["--noproxy", "*", "https://www.google.com/generate_204"]
        )
        checks["tun_google_http"] = tun_google
        if tun_google != 204:
            errors.append("独立 TUN 无法访问 Google 204")

    result = {"ok": not errors, "checks": checks, "errors": errors}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
