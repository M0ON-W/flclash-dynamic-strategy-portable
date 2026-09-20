import copy
import json
import unittest
from unittest.mock import patch

import strategy_manager as manager


NODE_7 = "7. IEPL·台湾专线B·TW1·均衡·沪港IEPL·600M"
NODE_10 = "10. IEPL·台湾专线B·TW3·空闲·沪港IEPL·600M"
NODE_11 = "11. IEPL·台湾专线B·TW3·空闲·沪港IEPL·600M"


def proxy(name):
    return {"name": name, "type": "ss", "server": "127.0.0.1", "port": 1}


class StrategyManagerTests(unittest.TestCase):
    def test_effective_config_uses_last_known_good_without_cross_group_fill(self):
        raw = {"proxies": [proxy("clean"), proxy("fast"), proxy("google"), proxy("openai"), proxy("netflix")]}
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
                "netflix_members": ["netflix"],
            },
        }
        config = manager.build_effective_config(raw, state, tun_enable=False)
        groups = {item["name"]: item["proxies"] for item in config["proxy-groups"]}
        self.assertEqual(groups[manager.GROUP_CLEAN], ["clean"])
        self.assertEqual(groups[manager.GROUP_GOOGLE_AI], ["google"])
        self.assertEqual(groups[manager.GROUP_OPENAI], ["openai"])
        self.assertEqual(groups[manager.GROUP_NETFLIX], ["netflix"])
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

    def test_google_validation_blocks_known_redirect_node_and_keeps_same_ip_cohort(self):
        names = [NODE_7, NODE_10, NODE_11]
        state = {
            "gemini_verified_members": copy.copy(names),
            "gemini_members": [NODE_10, NODE_11],
            "gemini_validation_streaks": {NODE_10: 1, NODE_11: 1},
            "gemini_validation": {
                NODE_10: {"exit_ip": "125.224.60.103"},
                NODE_11: {"exit_ip": "125.224.60.103"},
            },
        }

        def fake_probe(port, url, capture_body=False, timeout=12, **kwargs):
            if "api.ipify.org" in url:
                return {"ok": True, "status": 200, "body": json.dumps({"ip": "125.224.60.103"}), "redirect_url": ""}
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

        self.assertNotIn(NODE_7, state["gemini_verified_members"])
        self.assertEqual(state["gemini_members"], [NODE_10, NODE_11])
        self.assertEqual(state["gemini_primary_exit_ip"], "125.224.60.103")

    def test_dns_has_no_fake_ecs_and_respects_rules(self):
        dns = manager.strict_dns(NODE_10)
        self.assertTrue(dns["respect-rules"])
        self.assertNotIn("ecs=", json.dumps(dns))
        self.assertTrue(all(item.endswith("#" + manager.GROUP_FAST) for item in dns["nameserver"]))
        self.assertIn("+.bilibili.com", dns["fake-ip-filter"])
        self.assertIn("+.bilicdn1.com", dns["fake-ip-filter"])
        self.assertIn("+.maitokens.top", dns["fake-ip-filter"])
        self.assertIn("+.maitokens.com", dns["fake-ip-filter"])
        self.assertIn("DOMAIN-SUFFIX,bilibili.com,DIRECT", manager.managed_rules(manager.GROUP_FAST))
        self.assertIn("DOMAIN-SUFFIX,bilicdn1.com,DIRECT", manager.managed_rules(manager.GROUP_FAST))
        self.assertIn("DOMAIN-SUFFIX,maitokens.top,DIRECT", manager.managed_rules(manager.GROUP_FAST))
        self.assertIn("DOMAIN-SUFFIX,maitokens.com,DIRECT", manager.managed_rules(manager.GROUP_FAST))
        self.assertIn(
            f"DOMAIN-SUFFIX,netflix.com,{manager.GROUP_NETFLIX}",
            manager.managed_rules(manager.GROUP_FAST),
        )
        self.assertIn(
            f"RULE-SET,{manager.RULESET_NETFLIX},{manager.GROUP_NETFLIX}",
            manager.managed_rules(manager.GROUP_FAST),
        )
        self.assertEqual(
            dns["nameserver-policy"]["+.bilibili.com"], list(manager.BILIBILI_DIRECT_DOH)
        )
        self.assertEqual(
            dns["nameserver-policy"]["+.bilicdn1.com"], list(manager.BILIBILI_DIRECT_DOH)
        )
        self.assertEqual(
            dns["nameserver-policy"]["+.maitokens.top"], list(manager.BILIBILI_DIRECT_DOH)
        )
        self.assertEqual(
            dns["nameserver-policy"][f"rule-set:{manager.RULESET_CN}"],
            list(manager.BILIBILI_DIRECT_DOH),
        )
        self.assertEqual(next(iter(dns["nameserver-policy"])), "+.bilibili.com")
        raw = {"proxies": [proxy("clean"), proxy("fast")]}
        state = {
            "memberships": {
                manager.GROUP_CLEAN: ["clean"],
                manager.GROUP_STABLE: ["clean"],
                manager.GROUP_FAST: ["fast"],
            }
        }
        config = manager.build_effective_config(raw, state, tun_enable=True)
        self.assertEqual(config["tun"]["mtu"], manager.TUN_MTU)

    def test_empty_dedicated_pools_use_clean_for_google_and_fast_for_openai(self):
        raw = {"proxies": [proxy("clean"), proxy("fast")]}
        state = {
            "memberships": {
                manager.GROUP_CLEAN: ["clean"],
                manager.GROUP_STABLE: ["clean"],
                manager.GROUP_FAST: ["fast"],
            },
            "gemini_members": [],
            "openai_members": [],
        }
        config = manager.build_effective_config(raw, state, tun_enable=False)
        groups = {item["name"]: item["proxies"] for item in config["proxy-groups"]}
        self.assertEqual(groups[manager.GROUP_GOOGLE_AI], ["clean"])
        self.assertEqual(groups[manager.GROUP_OPENAI], ["fast"])
        self.assertEqual(groups[manager.GROUP_NETFLIX], ["clean"])
        self.assertEqual(manager.group_config(manager.GROUP_NETFLIX, ["clean"])["url"], "https://www.netflix.com/")
        manager.require_nonempty_runtime_groups(config)

    def test_scan_quality_allows_empty_dedicated_pools(self):
        state = {
            "memberships": {
                manager.GROUP_CLEAN: ["clean"],
                manager.GROUP_STABLE: ["clean"],
                manager.GROUP_FAST: ["fast"],
            },
            "gemini_members": [],
            "openai_members": [],
        }
        observations = [{"online": True, "strict_clean": True} for _ in range(20)]
        accepted, details = manager.scan_quality(state, observations, [str(i) for i in range(20)])
        self.assertTrue(accepted)
        self.assertEqual(details["reasons"], [])

    def test_stale_dedicated_members_do_not_bypass_fast_fallback(self):
        raw = {"proxies": [proxy("clean"), proxy("fast")]}
        state = {
            "memberships": {
                manager.GROUP_CLEAN: ["clean"],
                manager.GROUP_STABLE: ["clean"],
                manager.GROUP_FAST: ["fast"],
            },
            "gemini_members": ["removed-node"],
            "gemini_verified_members": ["fast"],
            "openai_members": ["removed-node"],
        }
        config = manager.build_effective_config(raw, state, tun_enable=False)
        groups = {item["name"]: item["proxies"] for item in config["proxy-groups"]}
        self.assertEqual(groups[manager.GROUP_GOOGLE_AI], ["clean"])
        self.assertEqual(groups[manager.GROUP_OPENAI], ["fast"])


if __name__ == "__main__":
    unittest.main()


class NetflixRepinTests(unittest.TestCase):
    NOW = 1_800_000_000

    def setUp(self):
        self.pool = [
            "20. IEPL·美国US·A220·空闲·Netflix美国 ChatGPT解锁 台湾隧道2·1000M",
            "21. IEPL·美国US·36·空闲·500M",
            "22. IEPL·美国US·A125·爆满·Netflix美国 ChatGPT解锁 沪港IEPL·1000M",
            "23. IEPL·美国US·A125·爆满·Netflix美国 ChatGPT解锁 台湾隧道2·1000M",
            "24. IEPL·美国US·A220·均衡·Netflix美国 ChatGPT解锁 沪港IEPL·1000M",
        ]
        self.dead = "52. IEPL·美国US·A241·空闲·Netflix美国 ChatGPT解锁·1000M"
        self.names = self.pool + [self.dead]

    def history(self, rate, latency=300.0, samples=504):
        step = 1200
        if rate <= 0:
            period = 0
        elif rate >= 1:
            period = None
        else:
            period = max(2, int(round(1.0 / (1.0 - rate))))
        items = []
        for i in range(samples):
            if period is None:
                online = True
            elif period == 0:
                online = False
            else:
                online = (i % period) != period - 1
            items.append(
                {
                    "time": int(self.NOW - (samples - i) * step),
                    "online": online,
                    "service_ok": True,
                    "clean": False,
                    "latency_ms": latency,
                    "speed_mbps": 5.0,
                    "exit_ip": "1.2.3.4",
                }
            )
        return items

    def state_with(self, rates, selected=None, last_pin=0, last_seen=None):
        histories = {name: self.history(rates[name]) for name in rates}
        return {
            "history": histories,
            "netflix_selected": selected,
            "netflix_last_pin_at": last_pin,
            "netflix_last_conn_seen": self.NOW - 300 if last_seen is None else last_seen,
        }

    def patch_env(self, connections=False, probes=None):
        probes = probes or {name: {"online": True, "latency_ms": 300.0} for name in self.names}
        return (
            patch.object(manager, "controller_has_domain_connections", return_value=connections),
            patch.object(manager, "probe_node", side_effect=lambda index, name, *a, **k: probes.get(name, {"online": False, "latency_ms": None})),
            patch.object(manager, "controller_request", return_value=(204, b"")),
            patch.object(manager, "service_controller_request", return_value=(204, b"")),
        )

    def test_dead_nodes_and_out_of_pool_names_excluded(self):
        rates = {name: 1.0 for name in self.pool}
        rates[self.dead] = 0.0
        rates[self.pool[4]] = 0.0
        state = self.state_with(rates)
        pool = manager.netflix_pool_candidates(state, self.names)
        self.assertEqual(pool, self.pool[:4])

    def test_active_connection_blocks_repin(self):
        rates = {name: 1.0 for name in self.pool}
        state = self.state_with(rates, selected=self.pool[3])
        p1, p2, p3, p4 = self.patch_env(connections=True)
        with p1, p2, p3, p4:
            result = manager.netflix_repin(state, self.names, now=self.NOW)
        self.assertEqual(result["action"], "skip")
        self.assertEqual(state["netflix_last_conn_seen"], self.NOW)

    def test_short_gap_blocks_repin(self):
        rates = {name: 1.0 for name in self.pool}
        state = self.state_with(rates, selected=self.pool[3], last_seen=self.NOW - 30)
        p1, p2, p3, p4 = self.patch_env(connections=False)
        with p1, p2, p3, p4:
            result = manager.netflix_repin(state, self.names, now=self.NOW)
        self.assertEqual(result["action"], "skip")

    def test_current_failed_switches_to_best(self):
        rates = {name: 1.0 for name in self.pool}
        rates[self.pool[0]] = 0.5
        state = self.state_with(rates, selected=self.pool[0])
        p1, p2, p3, p4 = self.patch_env()
        with p1, p2, p3 as req, p4 as sreq:
            result = manager.netflix_repin(state, self.names, now=self.NOW)
        self.assertEqual(result["action"], "switch")
        self.assertTrue(result["current_failed"])
        self.assertEqual(state["netflix_selected"], self.pool[1])
        self.assertEqual(state["netflix_last_pin_at"], self.NOW)
        self.assertEqual(req.call_count, 1)
        self.assertEqual(sreq.call_count, 1)

    def test_cooldown_holds_better_candidate(self):
        rates = {name: 0.95 for name in self.pool}
        rates[self.pool[0]] = 0.60
        state = self.state_with(rates, selected=self.pool[0], last_pin=self.NOW - 3600)
        p1, p2, p3, p4 = self.patch_env()
        with p1, p2, p3, p4:
            result = manager.netflix_repin(state, self.names, now=self.NOW)
        self.assertEqual(result["action"], "cooldown")
        self.assertEqual(state.get("netflix_selected"), self.pool[0])

    def test_all_unqualified_holds(self):
        rates = {name: 0.5 for name in self.pool}
        state = self.state_with(rates, selected=self.pool[0])
        p1, p2, p3, p4 = self.patch_env()
        with p1, p2, p3 as req, p4:
            result = manager.netflix_repin(state, self.names, now=self.NOW)
        self.assertEqual(result["action"], "hold")
        self.assertEqual(req.call_count, 0)

    def test_ranking_prefers_rate_then_latency(self):
        rates = {name: 0.95 for name in self.pool}
        probes = {name: {"online": True, "latency_ms": 300.0} for name in self.names}
        probes[self.pool[0]] = {"online": True, "latency_ms": 900.0}
        probes[self.pool[1]] = {"online": True, "latency_ms": 200.0}
        state = self.state_with(rates)
        p1, p2, p3, p4 = self.patch_env(probes=probes)
        with p1, p2, p3, p4:
            result = manager.netflix_repin(state, self.names, now=self.NOW)
        self.assertEqual(result["to"], self.pool[1])

    def test_keep_when_current_is_best(self):
        rates = {name: 0.95 for name in self.pool}
        state = self.state_with(rates, selected=self.pool[3])
        p1, p2, p3, p4 = self.patch_env()
        with p1, p2, p3 as req, p4:
            result = manager.netflix_repin(state, self.names, now=self.NOW)
        self.assertEqual(result["action"], "keep")
        self.assertEqual(req.call_count, 0)
