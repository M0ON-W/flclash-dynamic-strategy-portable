import unittest
import google_observer as observer

def candidate(ip, asn="AS1"):
    return {"name":"redacted","port":23000,"exit_ip":ip,"risk":10,"strict_clean":True,"online":True,"latency_ms":50,"speed_mbps":10,"reputation_complete":True,"reputation_conflict":False,"asn":asn,"region":"approved"}

class GoogleObserverTests(unittest.TestCase):
    def test_selection_caps_candidates_and_lines(self):
        items=[candidate("192.0.2.1",f"AS{i}") for i in range(4)]+[candidate(f"198.51.100.{i}",f"BS{i}") for i in range(1,8)]
        selected=observer.select_candidates(items)
        self.assertEqual(len(selected),6); self.assertLessEqual(sum(x["exit_ip"]=="192.0.2.1" for x in selected),2)
    def test_risk_markers_fail_closed(self):
        self.assertTrue(observer.risk_page({"body":"unusual traffic"})); self.assertTrue(observer.risk_page({"redirect_url":"https://google.com/sorry/"})); self.assertFalse(observer.risk_page({"body":"normal"}))
    def test_identity_change_restarts(self):
        state={"protocol_version":observer.PROTOCOL_VERSION,"rounds":[],"exits":{},"events":[]}; good={"public_pass":True,"strict_pass":True,"hard_risk":False,"unknown_risk":False,"outcomes":{}}
        observer.update_state(state,[candidate("192.0.2.1")],[good],1000,b"k"*32); exit_id=next(iter(state["exits"])); state["exits"][exit_id]["identity_id"]="changed"
        observer.update_state(state,[candidate("192.0.2.1")],[good],2000,b"k"*32); self.assertEqual(state["exits"][exit_id]["valid_rounds"],1); self.assertEqual(state["exits"][exit_id]["first_seen"],2000)
    def test_hard_risk_requires_manual_release(self):
        state={"protocol_version":observer.PROTOCOL_VERSION,"rounds":[],"exits":{},"events":[]}; bad={"public_pass":False,"strict_pass":False,"hard_risk":True,"unknown_risk":False,"outcomes":{},"identity":{},"identity_complete":False,"reputation_conflict":False}
        observer.update_state(state,[candidate("192.0.2.1")],[bad],1000,b"x"*32); item=next(iter(state["exits"].values())); self.assertEqual(item["quarantine"],"manual_release_required"); self.assertEqual(item["valid_rounds"],0)
    def test_report_requires_time_rounds_and_strict(self):
        now=100000; rounds=[{"time":now-86400+i*1200,"valid":True} for i in range(73)]; state={"protocol_version":observer.PROTOCOL_VERSION,"rounds":rounds,"events":[],"exits":{"exit_test":{"first_seen":now-86400,"public_passes":73,"strict_passes":73,"region_approved":True,"reputation_complete":True}}}
        result=observer.report(state,now); self.assertTrue(result["observation_complete"]); self.assertTrue(result["atomic_switch_ready"])
    def test_unapproved_region_never_enters_strict_pool(self):
        now=100000; state={"protocol_version":observer.PROTOCOL_VERSION,"rounds":[{"time":now-86400+i*1200,"valid":True} for i in range(73)],"events":[],"exits":{"exit_test":{"first_seen":now-86400,"public_passes":73,"strict_passes":73,"region_approved":False,"reputation_complete":True}}}
        result=observer.report(state,now); self.assertEqual(result["strict_pool_count"],0); self.assertFalse(result["atomic_switch_ready"])
    def test_lock_recovers_after_killed_process(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            lock=Path(directory)/"observer.lock"; lock.write_text("99999999",encoding="ascii")
            with patch.object(observer,"OBSERVER_HOME",Path(directory)), patch.object(observer,"LOCK_FILE",lock):
                with observer.ObserverLock(): self.assertTrue(lock.exists())
                self.assertFalse(lock.exists())

if __name__ == "__main__": unittest.main()
