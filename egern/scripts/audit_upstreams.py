from __future__ import annotations

import argparse
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import yaml

from catalog import COMMITS


REPOSITORIES = {
    "fmz200/wool_scripts": ("main", COMMITS["fmz"]),
    "app2smile/rules": ("master", COMMITS["app2smile"]),
    "BiliUniverse/ADBlock": ("main", COMMITS["bili"]),
    "QingRex/LoonKissSurge": ("main", COMMITS["qingrex"]),
    "zmqcherish/proxy-script": ("main", COMMITS["zmqcherish"]),
    "ishowshu/qx": ("main", COMMITS["ishowshu"]),
    "Keywos/rule": ("main", COMMITS["keywos"]),
}


def get_json(url: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "egern-upstream-audit"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 MITM 上游变更报告，不修改或发布模块")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest_path = Path(__file__).resolve().parents[1] / "modules" / "manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    lines = [
        "# Egern MITM 上游审计报告",
        "",
        f"生成时间：{datetime.now(timezone.utc).isoformat()}",
        "",
        "本报告只提示候选更新；不会改写、提交或发布 MITM 模块。",
        "",
        "| 上游 | 已审提交 | 当前提交 | 状态 |",
        "|---|---|---|---|",
    ]
    changed = False
    for repo, (branch, pinned) in REPOSITORIES.items():
        try:
            current = get_json(f"https://api.github.com/repos/{repo}/commits/{branch}")["sha"]
            status = "无变化" if current == pinned else "待人工审查"
            changed = changed or current != pinned
            lines.append(f"| `{repo}` | `{pinned[:12]}` | `{current[:12]}` | {status} |")
        except Exception as exc:  # 网络失败也必须进入报告，不能伪装成无变化。
            lines.append(f"| `{repo}` | `{pinned[:12]}` | 未取得 | 检查失败：{type(exc).__name__} |")
            changed = True

    lines.extend(["", "## 当前模块状态", ""])
    for item in manifest["modules"]:
        lines.append(
            f"- `{item['id']}`：{item['review_status']}，默认启用={str(item['default_enabled']).lower()}，SHA-256=`{item['sha256']}`"
        )
    lines.extend(["", f"结论：{'存在待审变化或检查失败' if changed else '未发现上游提交变化'}。", ""])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
