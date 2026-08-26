import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import strategy_manager as manager


NODE_BLOCKED = "test-google-blocked"
NODE_PRIMARY = "test-google-primary"
NODE_STANDBY = "test-google-standby"
TEST_EXIT_IP = "203.0.113.10"


def proxy(name):
    return {"name": name, "type": "ss", "server": "127.0.0.1", "port": 1}


class StrategyManagerTests(unittest.TestCase):
    def test_effective_config_uses_last_known_good_without_cross_group_fill(self):
        raw = {"proxies": [proxy("clean"), proxy("fast"), proxy("google"), proxy("openai")]}
        state = {
            "memberships": {manager.GROUP_CLEAN: [], manager.GROUP_STABLE: [], manager.GROUP_FAST: []},
            "gemini_members": [],
            "openai_members": [],
            "last_known_good": {
                "memberships": {
                    manager.GROUP_CLEAN: ["clean"],
                    manager.GROUP_STABLE: ["clean"],
                    manager.GROUP_FAST: ["fast"],
                },
                "gemini_members": ["google"],
                "openai_members": ["openai"],
            },
        }
        config = manager.build_effective_config(raw, state, tun_enable=False)
        groups = {item["name"]: item["proxies"] for item in config["proxy-groups"]}
        self.assertEqual(groups[manager.GROUP_CLEAN], ["clean"])
        self.assertEqual(groups[manager.GROUP_GOOGLE_AI], ["google"])
        self.assertEqual(groups[manager.GROUP_OPENAI], ["openai"])
        manager.require_nonempty_runtime_groups(config)

    def test_scan_quality_rejects_empty_clean_groups(self):
        state = {
            "memberships": {
                manager.GROUP_CLEAN: [],
                manager.GROUP_STABLE: [],
                manager.GROUP_FAST: ["fast"],
            },
            "gemini_members": ["google"],
            "openai_members": ["openai"],
        }
        observations = [{"online": True, "strict_clean": False} for _ in range(20)]
        accepted, details = manager.scan_quality(state, observations, [str(i) for i in range(20)])
        self.assertFalse(accepted)
        self.assertIn("strict clean group collapsed to zero", details["reasons"])

    def test_strict_clean_observation_is_discovered_for_google_validation(self):
        state = {"reputation": {}, "history": {}}
        observations = [
            {
                "name": NODE_PRIMARY,
                "exit_ip": TEST_EXIT_IP,
                "online": True,
                "service_ok": True,
                "latency_ms": 100,
                "speed_mbps": 10,
                "statuses": {"google": 204, "gemini": 200, "openai": 401},
            }
        ]
        reputation = {
            TEST_EXIT_IP: {
                "checked_at": 1,
                "proxy": "no",
                "type": "residential",
                "risk": 10,
                "ipapi_proxy": False,
                "ipapi_hosting": False,
            }
        }
        with patch.object(manager, "reputation_lookup", return_value=reputation):
            manager.classify(state, observations, [NODE_PRIMARY])
        self.assertEqual(state["gemini_verified_members"], [NODE_PRIMARY])

    def test_google_validation_blocks_known_redirect_node_and_keeps_same_ip_cohort(self):
        names = [NODE_BLOCKED, NODE_PRIMARY, NODE_STANDBY]
        state = {
            "gemini_verified_members": copy.copy(names),
            "gemini_members": [NODE_PRIMARY, NODE_STANDBY],
            "gemini_blocked_members": [NODE_BLOCKED],
            "gemini_validation_streaks": {NODE_PRIMARY: 1, NODE_STANDBY: 1},
            "gemini_validation": {
                NODE_PRIMARY: {"exit_ip": TEST_EXIT_IP},
                NODE_STANDBY: {"exit_ip": TEST_EXIT_IP},
            },
        }

        def fake_probe(port, url, capture_body=False, timeout=12, **kwargs):
            if "api.ipify.org" in url:
                return {"ok": True, "status": 200, "body": json.dumps({"ip": TEST_EXIT_IP}), "redirect_url": ""}
            if "www.google.com" in url:
                return {"ok": True, "status": 200, "body": "", "redirect_url": "", "ttfb_ms": 100}
            if "generate_204" in url:
                return {"ok": True, "status": 204, "body": "", "redirect_url": ""}
            if "accounts.google.com" in url or "gemini.google.com" in url:
                return {"ok": True, "status": 200, "body": "", "redirect_url": ""}
            return {
                "ok": True,
                "status": 200,
                "body": "",
                "redirect_url": "",
                "speed_bps": 1_000_000,
                "size": manager.GEMINI_SPEED_TEST_BYTES,
            }

        with patch.object(manager, "curl_probe", side_effect=fake_probe):
            manager.refresh_gemini_members(state, names)

        self.assertNotIn(NODE_BLOCKED, state["gemini_verified_members"])
        self.assertEqual(state["gemini_members"], [NODE_PRIMARY, NODE_STANDBY])
        self.assertEqual(state["gemini_primary_exit_ip"], TEST_EXIT_IP)

    def test_dns_has_no_fake_ecs_and_respects_rules(self):
        dns = manager.strict_dns(NODE_PRIMARY)
        self.assertTrue(dns["respect-rules"])
        self.assertNotIn("ecs=", json.dumps(dns))
        self.assertTrue(all(item.endswith("#" + NODE_PRIMARY) for item in dns["nameserver"]))


if __name__ == "__main__":
    unittest.main()
