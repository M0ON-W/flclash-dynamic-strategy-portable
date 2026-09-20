from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import hmac
import ipaddress
import json
import os
import random
import time
import urllib.parse
from pathlib import Path

import strategy_manager as manager

PROTOCOL_VERSION = "google-observer-v1"
OBSERVER_HOME = manager.MANAGED_DIR / "google-observer"
STATE_FILE = OBSERVER_HOME / "state.json"
REPORT_FILE = OBSERVER_HOME / "report.json"
LOG_FILE = OBSERVER_HOME / "observer.log"
KEY_FILE = OBSERVER_HOME / "observer.key"
LOCK_FILE = OBSERVER_HOME / "observer.lock"
MAX_CANDIDATES = 6
MAX_LINES_PER_EXIT = 2
MAX_GAP_SECONDS = 45 * 60
REQUIRED_VALID_ROUNDS = 60
REQUIRED_SPAN_SECONDS = 24 * 60 * 60
REPUTATION_MAX_AGE_SECONDS = 24 * 60 * 60
ENDPOINT_DELAY_SECONDS = (2.0, 8.0)
RISK_MARKERS = ("/sorry/", "unusual traffic", "automated queries", "recaptcha challenge", "verify it's you", "verify it’s you", "suspicious activity", "account temporarily disabled", "location is not supported", "country is not supported")
ENDPOINTS = (
    ("search", "https://www.google.com/?hl=en", {200}, True),
    ("connectivity", "https://www.gstatic.com/generate_204", {204}, False),
    ("accounts", "https://accounts.google.com/ServiceLogin", {200, 302, 303}, True),
    ("oauth", "https://accounts.google.com/.well-known/openid-configuration", {200}, True),
    ("gmail", "https://mail.google.com/mail/", {200, 302, 303}, True),
    ("drive", "https://drive.google.com/", {200, 302, 303}, True),
    ("play", "https://play.google.com/store", {200, 302, 303}, True),
    ("recaptcha", "https://www.google.com/recaptcha/api.js", {200}, True),
    ("gemini", "https://gemini.google.com/app", {200}, True),
    ("youtube", "https://www.youtube.com/", {200}, True),
    ("googleapis", "https://www.googleapis.com/discovery/v1/apis", {200}, True),
)
IDENTITY_URL = "http://ip-api.com/json/?fields=status,countryCode,regionName,as,proxy,hosting,mobile,query"

class ObserverLock:
    def __enter__(self):
        OBSERVER_HOME.mkdir(parents=True, exist_ok=True)
        if LOCK_FILE.exists():
            try:
                lock_pid = int(LOCK_FILE.read_text(encoding="ascii").strip())
            except (OSError, ValueError):
                lock_pid = 0
            stale = time.time() - LOCK_FILE.stat().st_mtime > 30 * 60
            if stale or not manager.process_exists(lock_pid):
                LOCK_FILE.unlink(missing_ok=True)
        try:
            self.fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise RuntimeError("another observer run is active") from exc
        os.write(self.fd, str(os.getpid()).encode("ascii"))
        return self

    def __exit__(self, exc_type, exc, tb):
        os.close(self.fd)
        LOCK_FILE.unlink(missing_ok=True)

def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)

def append_log(message: str) -> None:
    OBSERVER_HOME.mkdir(parents=True, exist_ok=True)
    if LOG_FILE.exists() and LOG_FILE.stat().st_size > 2_000_000:
        LOG_FILE.replace(LOG_FILE.with_suffix(".log.1"))
    stamp = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    with LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(f"{stamp} {message}\n")

def load_state() -> dict:
    try:
        value = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        value = {}
    if value.get("protocol_version") != PROTOCOL_VERSION:
        return {"protocol_version": PROTOCOL_VERSION, "rounds": [], "exits": {}, "events": []}
    value.setdefault("rounds", []); value.setdefault("exits", {}); value.setdefault("events", [])
    return value

def observer_key() -> bytes:
    OBSERVER_HOME.mkdir(parents=True, exist_ok=True)
    if KEY_FILE.exists():
        return KEY_FILE.read_bytes()
    key = os.urandom(32)
    temporary = KEY_FILE.with_suffix(".tmp")
    temporary.write_bytes(key)
    os.replace(temporary, KEY_FILE)
    return key

def identifier(key: bytes, value: str, prefix: str) -> str:
    return f"{prefix}_{hmac.new(key, value.encode(), hashlib.sha256).hexdigest()[:16]}"

def risk_page(probe: dict) -> bool:
    text = (str(probe.get("body") or "") + " " + str(probe.get("redirect_url") or "")).lower()
    return any(marker in text for marker in RISK_MARKERS)

def redirect_host(probe: dict) -> str | None:
    try:
        return urllib.parse.urlparse(str(probe.get("redirect_url") or "")).hostname
    except ValueError:
        return None

def select_candidates(candidates: list[dict]) -> list[dict]:
    usable = [x for x in candidates if x["online"] and x["reputation_complete"]]
    usable.sort(key=lambda x: (x["reputation_conflict"], not x["strict_clean"], x["risk"], x["latency_ms"], -x["speed_mbps"]))
    selected, per_exit, seen_asn = [], {}, set()
    for item in usable:
        if per_exit.get(item["exit_ip"], 0) >= MAX_LINES_PER_EXIT:
            continue
        if item["asn"] in seen_asn and any(x["asn"] not in seen_asn for x in usable):
            continue
        selected.append(item); per_exit[item["exit_ip"]] = per_exit.get(item["exit_ip"], 0) + 1; seen_asn.add(item["asn"])
        if len(selected) >= MAX_CANDIDATES: break
    for item in usable:
        if len(selected) >= MAX_CANDIDATES: break
        if item in selected or per_exit.get(item["exit_ip"], 0) >= MAX_LINES_PER_EXIT: continue
        selected.append(item); per_exit[item["exit_ip"]] = per_exit.get(item["exit_ip"], 0) + 1
    return selected

def current_candidates() -> list[dict]:
    raw = manager.load_profile(manager.current_profile_id())
    names = [str(x["name"]) for x in manager.candidate_proxies(raw)]
    formal = manager.load_json(manager.STATE_FILE, {})
    observations = {str(x.get("name")): x for x in formal.get("last_observations") or [] if x.get("name")}
    now, candidates = int(time.time()), []
    for index, name in enumerate(names):
        item = observations.get(name) or {}; exit_ip = item.get("exit_ip")
        try: exit_ip = str(ipaddress.ip_address(exit_ip))
        except (ValueError, TypeError): continue
        cached = (formal.get("reputation") or {}).get(exit_ip) or {}; checked = int(cached.get("checked_at") or 0)
        candidates.append({"name": name, "port": manager.LISTENER_PORT_BASE + index, "exit_ip": exit_ip,
            "risk": int(cached.get("risk") or 100), "strict_clean": bool(item.get("strict_clean")), "online": bool(item.get("online")),
            "latency_ms": float(item.get("latency_ms") or 999999), "speed_mbps": float(item.get("speed_mbps") or 0),
            "reputation_complete": checked > 0 and now - checked <= REPUTATION_MAX_AGE_SECONDS,
            "reputation_conflict": cached.get("proxy") == "no" and (cached.get("ipapi_proxy") is True or cached.get("ipapi_hosting") is True),
            "asn": str(cached.get("asn") or "unknown"), "region": str(cached.get("countryCode") or cached.get("country") or "unapproved")})
    return select_candidates(candidates)

def probe_candidate(candidate: dict, sleep=time.sleep) -> dict:
    identity_probe = manager.curl_probe(candidate["port"], IDENTITY_URL, capture_body=True, timeout=15, connect_timeout=8)
    identity = {}
    try:
        parsed = json.loads(identity_probe.get("body") or "{}")
        if identity_probe.get("status") == 200 and parsed.get("status") == "success":
            observed_ip = str(ipaddress.ip_address(parsed.get("query")))
            if observed_ip == candidate["exit_ip"]:
                identity = {"country": str(parsed.get("countryCode") or ""), "region": str(parsed.get("regionName") or ""), "asn": str(parsed.get("as") or ""),
                    "proxy": parsed.get("proxy"), "hosting": parsed.get("hosting"), "mobile": parsed.get("mobile")}
    except (ValueError, TypeError, json.JSONDecodeError):
        identity = {}
    outcomes, hard, unknown = {}, False, False
    for pos, (label, url, expected, capture) in enumerate(ENDPOINTS):
        probe = manager.curl_probe(candidate["port"], url, capture_body=capture, timeout=20, connect_timeout=8)
        status, host, risky = probe.get("status"), redirect_host(probe), risk_page(probe)
        cross = bool(host and not (host == "google.com" or host.endswith(".google.com") or host == "youtube.com" or host.endswith(".youtube.com")))
        passed = bool(probe.get("ok") and status in expected and not risky and not cross)
        hard = hard or risky or cross; unknown = unknown or bool(probe.get("ok") and status not in expected and not risky)
        outcomes[label] = {"status": status, "passed": passed, "risk": risky, "redirect_class": "cross_site" if cross else ("same_site" if host else "none"),
            "evidence": hashlib.sha256(f"{status}|{host or ''}|{risky}".encode()).hexdigest()[:16]}
        if pos + 1 < len(ENDPOINTS): sleep(random.uniform(*ENDPOINT_DELAY_SECONDS))
    public = {"search", "connectivity", "youtube", "googleapis"}; strict = set(outcomes) - public
    reputation_conflict = bool(identity and (identity.get("proxy") is True or identity.get("hosting") is True))
    return {"public_pass": all(outcomes[x]["passed"] for x in public), "strict_pass": all(outcomes[x]["passed"] for x in strict), "hard_risk": hard,
        "unknown_risk": unknown, "outcomes": outcomes, "identity": identity, "identity_complete": bool(identity.get("country") and identity.get("asn")), "reputation_conflict": reputation_conflict}

def update_state(state: dict, candidates: list[dict], results: list[dict], now: int, key: bytes) -> dict:
    grouped = {}
    for candidate, result in zip(candidates, results): grouped.setdefault(candidate["exit_ip"], []).append((candidate, result))
    item = {"time": now, "candidate_count": len(candidates), "exit_count": len(grouped), "valid": True}
    if state["rounds"] and now - int(state["rounds"][-1]["time"]) > MAX_GAP_SECONDS: item["gap_seconds"] = now - int(state["rounds"][-1]["time"])
    state["rounds"].append(item); state["rounds"] = [x for x in state["rounds"] if now - int(x["time"]) <= 30 * 86400]
    for exit_ip, lines in grouped.items():
        exit_id = identifier(key, exit_ip, "exit"); candidate, sample = lines[0]
        observed_identity = sample.get("identity") or {}
        observed_asn = str(observed_identity.get("asn") or candidate["asn"])
        observed_region = "|".join((str(observed_identity.get("country") or ""), str(observed_identity.get("region") or "")))
        identity_id = identifier(key, "|".join((exit_ip, observed_asn, observed_region)), "identity")
        old = state["exits"].get(exit_id) or {}
        if old.get("identity_id") != identity_id: old = {"identity_id": identity_id, "first_seen": now, "valid_rounds": 0, "public_passes": 0, "strict_passes": 0}
        old.update({"last_seen": now, "line_redundancy": len(lines), "asn_known": bool(observed_asn and observed_asn != "unknown"), "region_approved": False,
            "region_status": "awaiting_explicit_approval" if observed_region.strip("|") else "unverified", "reputation_complete": candidate["reputation_complete"] and bool(sample.get("identity_complete")),
            "reputation_conflict": candidate["reputation_conflict"] or any(x[1].get("reputation_conflict") for x in lines), "hard_risk": any(x[1]["hard_risk"] for x in lines),
            "unknown_risk": any(x[1]["unknown_risk"] for x in lines), "last_outcomes": sample["outcomes"]})
        old["valid_rounds"] += 1; old["public_passes"] = old["public_passes"] + 1 if all(x[1]["public_pass"] for x in lines) else 0; old["strict_passes"] = old["strict_passes"] + 1 if all(x[1]["strict_pass"] for x in lines) else 0
        if old["hard_risk"]: old["quarantine"] = "manual_release_required"; old["first_seen"] = now; old["valid_rounds"] = 0
        state["exits"][exit_id] = old
    state["last_round"] = now
    return state

def report(state: dict, now: int) -> dict:
    rounds = [x for x in state["rounds"] if x.get("valid")]; first = int(rounds[0]["time"]) if rounds else now
    gaps = [int(x.get("gap_seconds") or 0) for x in rounds if x.get("gap_seconds")]
    public, strict = [], []
    for exit_id, item in state.get("exits", {}).items():
        if item.get("hard_risk") or item.get("unknown_risk") or item.get("reputation_conflict"): continue
        if item.get("public_passes", 0) >= 2 and now - int(item.get("first_seen", now)) >= 1200: public.append(exit_id)
        if item.get("strict_passes", 0) >= 6 and now - int(item.get("first_seen", now)) >= 7200 and item.get("region_approved") and item.get("reputation_complete"): strict.append(exit_id)
    excess = sum(max(0, gap - 1200) for gap in gaps)
    complete = now - first >= REQUIRED_SPAN_SECONDS and len(rounds) >= REQUIRED_VALID_ROUNDS and max(gaps, default=0) <= MAX_GAP_SECONDS and excess <= 7200
    return {"protocol_version": PROTOCOL_VERSION, "generated_at": dt.datetime.fromtimestamp(now).astimezone().isoformat(timespec="seconds"), "valid_rounds": len(rounds),
        "observation_span_seconds": max(0, now-first), "effective_observation_seconds": max(0, now-first-excess), "maximum_gap_seconds": max(gaps, default=0),
        "public_pool_count": len(public), "strict_pool_count": len(strict), "independent_exit_count": len(state.get("exits", {})), "public_exit_ids": sorted(public), "strict_exit_ids": sorted(strict),
        "observation_complete": complete, "atomic_switch_ready": bool(complete and strict), "real_traffic_unchanged": True}

def run_once(no_delay=False) -> dict:
    with ObserverLock():
        state, key, candidates = load_state(), observer_key(), current_candidates()
        results = [probe_candidate(x, sleep=(lambda _: None) if no_delay else time.sleep) for x in candidates]
        now = int(time.time()); update_state(state, candidates, results, now, key); output = report(state, now)
        atomic_json(STATE_FILE, state); atomic_json(REPORT_FILE, output); append_log(f"round complete candidates={len(candidates)} exits={output['independent_exit_count']} strict={output['strict_pool_count']} public={output['public_pool_count']}")
        return output

def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--status", action="store_true"); parser.add_argument("--scheduled", action="store_true"); parser.add_argument("--no-delay", action="store_true", help=argparse.SUPPRESS); args = parser.parse_args()
    if args.scheduled:
        time.sleep(random.uniform(0, 5 * 60))
    output = report(load_state(), int(time.time())) if args.status else run_once(args.no_delay)
    print(json.dumps(output, ensure_ascii=False, indent=2)); return 0

if __name__ == "__main__": raise SystemExit(main())
