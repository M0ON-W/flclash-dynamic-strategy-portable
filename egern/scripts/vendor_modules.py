from __future__ import annotations

import argparse
import hashlib
import re
import shutil
from pathlib import Path

import yaml

from catalog import COMMITS, MODULES, PUBLIC_RAW_BASE, REPO_ROOT_NAMES, source_url


RAW_REPLACEMENTS = {
    "https://github.com/fmz200/wool_scripts/raw/main/": (
        f"https://raw.githubusercontent.com/fmz200/wool_scripts/{COMMITS['fmz']}/"
    ),
    "https://raw.githubusercontent.com/fmz200/wool_scripts/main/": (
        f"https://raw.githubusercontent.com/fmz200/wool_scripts/{COMMITS['fmz']}/"
    ),
    "https://raw.githubusercontent.com/zmqcherish/proxy-script/main/": (
        f"https://raw.githubusercontent.com/zmqcherish/proxy-script/{COMMITS['zmqcherish']}/"
    ),
    "https://raw.githubusercontent.com/ishowshu/qx/refs/heads/main/": (
        f"https://raw.githubusercontent.com/ishowshu/qx/{COMMITS['ishowshu']}/"
    ),
    "https://raw.githubusercontent.com/Keywos/rule/main/": (
        f"https://raw.githubusercontent.com/Keywos/rule/{COMMITS['keywos']}/"
    ),
    "https://raw.githubusercontent.com/app2smile/rules/master/": (
        f"https://raw.githubusercontent.com/app2smile/rules/{COMMITS['app2smile']}/"
    ),
}

BILI_SCRIPT_HASHES = {
    "https://github.com/BiliUniverse/ADBlock/releases/download/v0.6.24/request.bundle.js": (
        "adc2f2f2e09466ab9f21f4a0e39e212a741b753279b993a773c23af81bf43ecf"
    ),
    "https://github.com/BiliUniverse/ADBlock/releases/download/v0.6.24/response.bundle.js": (
        "f805f7dd5dad9f43ac67ce47b9d3ac294b5848a59b1d0ea9d504707fe406f4a1"
    ),
}

RAW_URL_RE = re.compile(
    r"https://raw\.githubusercontent\.com/([^/]+)/([^/]+)/([^/]+)/([^,\s]+)"
)
SCRIPT_URL_RE = re.compile(r"script-path=(https?://[^,\s]+)")
HOSTNAME_RE = re.compile(r"^hostname\s*=\s*(?:%APPEND%\s*)?(.+)$", re.MULTILINE)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def read_source(audit_root: Path, item: dict) -> str:
    source = audit_root / REPO_ROOT_NAMES[item["repo"]] / item["source_rel"]
    return source.read_text(encoding="utf-8-sig")


def pin_urls(text: str) -> str:
    for old, new in RAW_REPLACEMENTS.items():
        text = text.replace(old, new)
    return text


def sanitize_fmz(item_id: str, text: str) -> str:
    if item_id == "weibo":
        forbidden = ("自定义tab皮肤", "非会员设置tab皮肤", "解锁微博会员APP图标")
        text = "\n".join(line for line in text.splitlines() if not any(x in line for x in forbidden))
    if item_id == "smzdm":
        text = "\n".join(
            line
            for line in text.splitlines()
            if not ("type=http-response" in line and re.search(r"\\?/vip(?:\\?/|\$|,)", line))
        )
    if item_id == "taobao":
        pinned = (
            f"https://raw.githubusercontent.com/fmz200/wool_scripts/{COMMITS['fmz']}/"
            "Scripts/myBlockAds.js"
        )
        text = text.replace(
            pinned,
            f"{PUBLIC_RAW_BASE}/modules/gpl-3.0/scripts/myBlockAds-ad-only.js",
        )
    return text


def build_bili(text: str) -> str:
    section = text[text.index("[URL Rewrite]") :]
    section = section.replace("v{{@package 'version'}}", "v0.6.24")
    section = section.replace(", argument={{{scriptParams}}}", "")
    section = "\n".join(line for line in section.splitlines() if "del(.data.payment)" not in line)
    if "{{" in section or "}}" in section:
        raise ValueError("BiliUniverse 模板仍含未展开变量")
    header = "\n".join(
        [
            "#!name = BiliBili ADBlock（广告净化审查版）",
            "#!desc = 基于 BiliUniverse/ADBlock v0.6.24；删除 payment 字段改写。",
            "#!author = BiliUniverse contributors",
            "#!homepage = https://github.com/BiliUniverse/ADBlock",
            "#!version = 0.6.24-ad-only.1",
            "",
        ]
    )
    return header + section


def normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").rstrip() + "\n"


def source_root_map(audit_root: Path, egern_root: Path) -> dict[tuple[str, str], Path]:
    return {
        ("fmz200", "wool_scripts"): audit_root / REPO_ROOT_NAMES["fmz"],
        ("app2smile", "rules"): audit_root / REPO_ROOT_NAMES["app2smile"],
        ("zmqcherish", "proxy-script"): audit_root / REPO_ROOT_NAMES["zmqcherish"],
        ("ishowshu", "qx"): audit_root / REPO_ROOT_NAMES["ishowshu"],
        ("Keywos", "rule"): audit_root / REPO_ROOT_NAMES["keywos"],
        ("M0ON-W", "flclash-dynamic-strategy-portable"): egern_root.parent,
    }


def script_hash(url: str, roots: dict[tuple[str, str], Path]) -> str | None:
    if url in BILI_SCRIPT_HASHES:
        return BILI_SCRIPT_HASHES[url]
    match = RAW_URL_RE.fullmatch(url)
    if not match:
        return None
    owner, repo, _commit, rel = match.groups()
    root = roots.get((owner, repo))
    if not root:
        return None
    target = root / rel
    if not target.is_file():
        return None
    return sha256_bytes(target.read_bytes())


def parse_hosts(text: str) -> list[str]:
    hosts: list[str] = []
    for match in HOSTNAME_RE.finditer(text):
        hosts.extend(host.strip() for host in match.group(1).split(",") if host.strip())
    return sorted(set(hosts), key=str.lower)


def parse_scripts(text: str, roots: dict[tuple[str, str], Path]) -> list[dict]:
    urls = sorted(set(SCRIPT_URL_RE.findall(text)))
    return [{"url": url, "sha256": script_hash(url, roots)} for url in urls]


def validate_module(item: dict, text: str) -> None:
    lowered = text.lower()
    if re.search(r"hostname\s*=\s*(?:%append%\s*)?\*\s*(?:,|$)", lowered):
        raise ValueError(f"{item['id']}: 禁止 hostname = *")
    forbidden = [
        "new.vip.weibo",
        "weibo_vip.js",
        "del(.data.payment)",
        "authorization",
        "cookie-request",
        "cookie-response",
        "daily-checkin",
    ]
    found = [token for token in forbidden if token in lowered]
    if found:
        raise ValueError(f"{item['id']}: 命中禁止项 {found}")


def write_license(audit_root: Path, egern_root: Path, repo: str, target_dir: str) -> None:
    root = audit_root / REPO_ROOT_NAMES[repo]
    source = root / "LICENSE"
    if not source.is_file():
        source = root / "LICENSE.md"
    destination = egern_root / "modules" / target_dir / "LICENSE"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def build_manifest(audit_root: Path, egern_root: Path) -> dict:
    roots = source_root_map(audit_root, egern_root)
    records = []
    local_rule_hash = sha256_bytes((egern_root / "rules" / "ad-sdk.yaml").read_bytes())
    for item in MODULES:
        record = {
            "id": item["id"],
            "app": item["app"],
            "source_url": source_url(item),
            "source_commit": COMMITS.get(item["repo"], "local"),
            "license": item["license"],
            "mitm_domains": [],
            "script_urls": [],
            "sha256": None,
            "review_status": item["review_status"],
            "default_enabled": item["default_enabled"],
            "notes": item["notes"],
        }
        if item["artifact"]:
            artifact = egern_root / item["artifact"]
            text = artifact.read_text(encoding="utf-8")
            record["module_url"] = f"{PUBLIC_RAW_BASE}/{item['artifact']}"
            record["sha256"] = sha256_bytes(artifact.read_bytes())
            record["mitm_domains"] = parse_hosts(text)
            record["script_urls"] = parse_scripts(text, roots)
        elif item["repo"] == "qingrex":
            text = read_source(audit_root, item)
            record["module_url"] = source_url(item)
            record["sha256"] = sha256_bytes(text.encode("utf-8"))
            record["mitm_domains"] = parse_hosts(text)
            record["script_urls"] = parse_scripts(text, roots)
        else:
            record["module_url"] = None
            record["sha256"] = local_rule_hash
        records.append(record)
    return {"schema_version": 1, "modules": records}


def main() -> int:
    parser = argparse.ArgumentParser(description="生成经审查并固定版本的 Egern Surge 模块副本")
    parser.add_argument("--audit-root", type=Path, required=True, help="只读上游仓库集合目录")
    args = parser.parse_args()

    audit_root = args.audit_root.resolve()
    egern_root = Path(__file__).resolve().parents[1]

    source_script = audit_root / REPO_ROOT_NAMES["fmz"] / "Scripts" / "myBlockAds.js"
    script_text = source_script.read_text(encoding="utf-8-sig")
    script_text = "\n".join(
        line for line in script_text.splitlines() if "obj.data.user.is_vip = true;" not in line
    )
    script_target = egern_root / "modules" / "gpl-3.0" / "scripts" / "myBlockAds-ad-only.js"
    script_target.parent.mkdir(parents=True, exist_ok=True)
    script_target.write_text(normalize(script_text), encoding="utf-8", newline="\n")

    for item in MODULES:
        if not item["artifact"]:
            continue
        text = read_source(audit_root, item)
        if item["repo"] == "bili":
            text = build_bili(text)
        else:
            text = sanitize_fmz(item["id"], pin_urls(text))
        text = normalize(text)
        validate_module(item, text)
        target = egern_root / item["artifact"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")

    write_license(audit_root, egern_root, "fmz", "gpl-3.0")
    write_license(audit_root, egern_root, "app2smile", "mit")
    write_license(audit_root, egern_root, "bili", "apache-2.0")

    manifest = build_manifest(audit_root, egern_root)
    (egern_root / "modules" / "manifest.yaml").write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
        newline="\n",
    )
    print("已生成审查模块及 manifest.yaml。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
