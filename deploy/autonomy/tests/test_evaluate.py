"""SYNTHETIC schema fixtures only: none of these events are acceptance evidence.

The complete fixture exercises the READY branch by mimicking operator claims.
This does not demonstrate a VPS, broker action, strategy edge, or real autonomy.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluate import ATTESTATION, MODEL, evaluate

NOW = datetime(2026, 9, 14, 8, 0, tzinfo=timezone.utc)


def stamp(t):
    return t.isoformat().replace("+00:00", "Z")


class GateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.model = b"synthetic model fixture, never actual runtime evidence"
        self.model_hash = hashlib.sha256(self.model).hexdigest()
        self.base = dict(schemaVersion=1, run_id="synthetic-schema-test", environment="DEMO",
                         origin="ACTUAL_DEMO", model_sha256=self.model_hash)
        self.documents = {}
        self.manifest = dict(schemaVersion=1, status="SUBMITTED", model=MODEL, environment="DEMO",
                             origin="ACTUAL_DEMO", run_id=self.base["run_id"], model_sha256=self.model_hash,
                             artifacts={}, operator_attestation=dict(alias="synthetic-test-operator",
                                 reviewed_at_utc=stamp(NOW-timedelta(minutes=1)), actual_demo_verified=True,
                                 not_synthetic=True, statement=ATTESTATION, reviewed_artifact_sha256={}))
        self.put("model", self.model)
        self.put("baseline_promotion", dict(status="ELIGIBLE_FOR_HUMAN_REVIEW", reasons=[],
                                            forward_demo_trading_enabled=False, real_trading_enabled=False))
        self.put("baseline_review", dict(status="PASSED_REVIEWED", model_sha256=self.model_hash,
            promotion_sha256=self.manifest["artifacts"]["baseline_promotion"]["sha256"], genuine_unseen=True,
            external_inputs_complete=True, broker_cost_history_verified=True, campaigns=100, trading_days=60,
            expectancy_ci95_low=.01, baseline_profit_factor=1.3, stress_profit_factor=1.1,
            max_drawdown=.1, safety_failures=0, positive_walkforward_fraction=.8, reviewer_approved=True))
        self.put("runtime", {**self.base, "host":"WINDOWS_VPS", "runtime_llm_calls":0,
            "mac_dependency":False, "chat_dependency":False, "cloud_dependency":False,
            "telegram_dependency":False, "process_kind":"DETERMINISTIC_DEMO_ENGINE", "execution_mode":"DEMO", "symbol":"XAUUSD",
            "baseline_promotion_sha256":self.manifest["artifacts"]["baseline_promotion"]["sha256"]})
        begin, end = NOW-timedelta(minutes=20), NOW-timedelta(minutes=5)
        times = [begin+timedelta(seconds=15*i) for i in range(61)]
        samples = [dict(at_utc=stamp(t), mac_connected=False, chat_connected=False, cloud_connected=False,
                        telegram_connected=False, engine_running=True, broker_connected=True, data_fresh=True,
                        runtime_llm_calls=0, ambiguous_state=False) for t in times]
        self.put("disconnect", {**self.base, "begin_utc":stamp(begin), "end_utc":stamp(end), "samples":samples})
        self.put("ticks", {**self.base, "records":[dict(at_utc=stamp(t), broker_tick_utc=stamp(t),
            source="BROKER_DEMO", bid=4000+i*.001, ask=4000.1+i*.001) for i,t in enumerate(times)]})
        previous = "0"*64; decisions=[]
        for minute in (5,10,15):
            t=begin+timedelta(minutes=minute)
            d=dict(recorded_utc=stamp(t), decision_utc=stamp(t), source="BROKER_DEMO",
                   model_sha256=self.model_hash, action="WAIT", mode="FROZEN", ready=False,
                   bar_open_utc=stamp(t-timedelta(minutes=5)), previous_hash=previous)
            d["record_hash"]=hashlib.sha256(json.dumps(d,sort_keys=True,separators=(",", ":")).encode()).hexdigest()
            previous=d["record_hash"]; decisions.append(d)
        self.put("decisions", {**self.base,"records":decisions})
        events=[]; cases=[]

        def add(kind,t,process="steady",campaign="coverage",**fields):
            e=dict(id=f"e{len(events)+1}",kind=kind,at_utc=stamp(t),process_instance=process,
                   campaign=campaign,source="BROKER_DEMO",confirmed=True,ambiguous=False,**fields)
            events.append(e); return e["id"]

        def reconcile(t,process):
            return [add(k,t+timedelta(seconds=i),process) for i,k in enumerate(
                    ("ORDERS_RECONCILED","POSITIONS_RECONCILED","PROTECTION_CONFIRMED"))]

        def entry(t,process,position,kind="ENTRY_CONFIRMED",**extra):
            ident=add(kind,t,process,position_hash=position,lots=.01,price=4000.,symbol="XAUUSD",**extra)
            add("SL_CONFIRMED",t+timedelta(seconds=1),process,position_hash=position,price=3999.)
            add("TP_CONFIRMED",t+timedelta(seconds=2),process,position_hash=position,price=4002.5)
            return ident

        for minutes,kind,process in ((50,"UNATTENDED_BOOT","boot-new"),(40,"CRASH_RECOVERY","crash-new")):
            t=NOW-timedelta(minutes=minutes)
            ids=reconcile(t,process)
            ids.append(entry(t+timedelta(seconds=3),process,hashlib.sha256(process.encode()).hexdigest()))
            cases.append(dict(kind=kind,begin_utc=stamp(t),end_utc=stamp(t+timedelta(minutes=1)),
                started_without_interactive_login=True,trigger="WINDOWS_SERVICE",old_instance=process+"-old",
                new_instance=process,event_ids=ids))
        t=begin+timedelta(minutes=2)
        reconcile(t,"steady")
        entry(t+timedelta(seconds=3),"steady","1"*64)
        entry(t+timedelta(minutes=1),"steady","2"*64,"PYRAMID_ADDED",winner_confirmed=True,
              all_prior_legs_protected=True,risk_caps_passed=True,floating_pnl_before=2.)
        add("TP_FILLED",t+timedelta(minutes=2),position_hash="1"*64,lots=.01,price=4002.5)
        add("SL_FILLED",t+timedelta(minutes=3),position_hash="2"*64,lots=.01,price=3999.)
        add("KILL_TRIGGERED",t+timedelta(minutes=4))
        add("FLAT_CONFIRMED",t+timedelta(minutes=4,seconds=1),broker_positions_remaining=0,broker_orders_remaining=0)
        block=[]
        for i,case in enumerate(("REAL_ACCOUNT","AMBIGUOUS_ORDER","MISSING_STATE","STALE_DATA","UNCONFIRMED_PROTECTION","BASELINE_NOT_PASSED")):
            ident=add("ENTRY_BLOCKED",t+timedelta(minutes=5,seconds=i),reason=case)
            block.append(dict(case=case,event_id=ident,environment="DEMO",fault_injection=True,order_send_count=0))
        self.put("management", {**self.base,"events":events})
        self.put("recovery", {**self.base,"cases":cases})
        self.put("blocking", {**self.base,"cases":block})

    def tearDown(self):
        self.temp.cleanup()

    def put(self,name,value):
        self.documents[name]=deepcopy(value)
        raw=value if isinstance(value,bytes) else json.dumps(value,separators=(",", ":")).encode()
        path=name+(".bin" if isinstance(value,bytes) else ".json")
        (self.root/path).write_bytes(raw)
        digest=hashlib.sha256(raw).hexdigest()
        self.manifest["artifacts"][name]=dict(path=path,sha256=digest)
        self.manifest["operator_attestation"]["reviewed_artifact_sha256"][name]=digest

    def assess(self):
        return evaluate(self.manifest,self.root,NOW)

    def test_complete_synthetic_schema_exercises_ready_without_permission(self):
        r=self.assess()
        self.assertEqual(r["status"],"READY",r["failedChecks"])
        self.assertFalse(r["realTradingEnabled"])
        self.assertFalse(r["baselineAutoGo"])
        self.assertFalse(r["executionEnabledByEvaluator"])
        self.assertEqual(r["actionsPerformed"],[])

    def test_template_is_not_tested_and_not_ready(self):
        template=json.loads((Path(__file__).resolve().parents[1]/"evidence.template.json").read_text())
        self.assertEqual(template["status"],"NOT_TESTED")
        self.assertEqual(evaluate(template,self.root,NOW)["status"],"NOT_READY")

    def test_synthetic_origin_and_real_environment_never_pass(self):
        for key,value in (("origin","SYNTHETIC"),("environment","REAL"),("environment","PAPER")):
            old=self.manifest[key];self.manifest[key]=value
            self.assertEqual(self.assess()["status"],"NOT_READY")
            self.manifest[key]=old

    def test_hash_tampering_and_unreviewed_replacement_block(self):
        (self.root/"ticks.json").write_text("{}")
        self.assertEqual(self.assess()["status"],"NOT_READY")
        self.put("ticks",self.documents["ticks"])
        self.manifest["operator_attestation"]["reviewed_artifact_sha256"]["ticks"]="f"*64
        self.assertEqual(self.assess()["status"],"NOT_READY")

    def test_path_traversal_absolute_and_symlink_escape_block(self):
        old=deepcopy(self.manifest["artifacts"]["ticks"])
        for path in ("../ticks.json","/tmp/ticks.json","C:\\ticks.json","inside/../ticks.json"):
            self.manifest["artifacts"]["ticks"]={**old,"path":path}
            self.assertEqual(self.assess()["status"],"NOT_READY")
        with tempfile.TemporaryDirectory() as outside:
            target=Path(outside)/"ticks.json";target.write_bytes((self.root/"ticks.json").read_bytes())
            (self.root/"escaped.json").symlink_to(target)
            self.manifest["artifacts"]["ticks"]={**old,"path":"escaped.json"}
            self.assertEqual(self.assess()["status"],"NOT_READY")

    def test_baseline_zero_activity_cannot_be_overridden_by_attestation(self):
        p=deepcopy(self.documents["baseline_promotion"]);p["status"]="NOT_EVALUABLE"
        self.put("baseline_promotion",p)
        self.assertIn("independent_strategy_baseline_passed_and_reviewed",self.assess()["failedChecks"])

    def test_disconnect_short_stale_and_no_decision_activity_block(self):
        original=deepcopy(self.documents["disconnect"])
        for mutate in (lambda d:d.update(end_utc=d["begin_utc"]),
                       lambda d:d["samples"][20].update(data_fresh=False),
                       lambda d:d["samples"][20].update(mac_connected=True),
                       lambda d:d["samples"][20].update(runtime_llm_calls=1)):
            value=deepcopy(original);mutate(value);self.put("disconnect",value)
            self.assertIn("supervised_disconnect_15_minutes_with_live_activity",self.assess()["failedChecks"])
        self.put("disconnect",original)
        self.put("decisions",{**self.documents["decisions"],"records":[]})
        self.assertIn("supervised_disconnect_15_minutes_with_live_activity",self.assess()["failedChecks"])

    def test_decision_chain_and_old_tick_are_checked_not_only_counts(self):
        d=deepcopy(self.documents["decisions"]);d["records"][1]["action"]="LONG"
        self.put("decisions",d)
        self.assertIn("supervised_disconnect_15_minutes_with_live_activity",self.assess()["failedChecks"])
        t=deepcopy(self.documents["ticks"]);t["records"][0]["broker_tick_utc"]=stamp(NOW-timedelta(days=1))
        self.put("ticks",t)
        self.assertEqual(self.assess()["status"],"NOT_READY")

    def test_atlogon_and_manual_login_are_not_unattended_boot(self):
        r=deepcopy(self.documents["recovery"]);r["cases"][0]["trigger"]="ATLOGON"
        self.put("recovery",r)
        self.assertIn("crash_and_unattended_boot_recovery",self.assess()["failedChecks"])

    def test_same_episode_cannot_prove_both_boot_and_crash(self):
        r=deepcopy(self.documents["recovery"])
        r["cases"][1]=deepcopy(r["cases"][0]);r["cases"][1]["kind"]="CRASH_RECOVERY"
        self.put("recovery",r)
        self.assertIn("crash_and_unattended_boot_recovery",self.assess()["failedChecks"])

    def test_hashed_timestamp_without_model_decision_is_not_activity(self):
        d=deepcopy(self.documents["decisions"]);previous="0"*64
        for record in d["records"]:
            del record["action"]
            record["previous_hash"]=previous
            payload={k:v for k,v in record.items() if k!="record_hash"}
            record["record_hash"]=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",", ":")).encode()).hexdigest()
            previous=record["record_hash"]
        self.put("decisions",d)
        self.assertIn("supervised_disconnect_15_minutes_with_live_activity",self.assess()["failedChecks"])

    def test_new_entry_after_kill_cannot_pass_acceptance(self):
        m=deepcopy(self.documents["management"])
        for e in m["events"]:
            if e["kind"]=="KILL_TRIGGERED":e["at_utc"]=stamp(NOW-timedelta(minutes=18,seconds=2))
            if e["kind"]=="FLAT_CONFIRMED":e["at_utc"]=stamp(NOW-timedelta(minutes=18,seconds=1))
        m["events"].sort(key=lambda e:e["at_utc"])
        self.put("management",m)
        self.assertIn("actual_position_management_and_reconciliation",self.assess()["failedChecks"])

    def test_entry_before_reconciliation_or_missing_sl_blocks(self):
        m=deepcopy(self.documents["management"])
        m["events"]=[e for e in m["events"] if e["kind"]!="ORDERS_RECONCILED"]
        self.put("management",m)
        self.assertIn("actual_position_management_and_reconciliation",self.assess()["failedChecks"])
        m=deepcopy(self.documents["management"])
        m["events"]=[e for e in m["events"] if e["kind"]!="SL_CONFIRMED"]
        self.put("management",m)
        self.assertEqual(self.assess()["status"],"NOT_READY")

    def test_missing_kill_coverage_or_orphan_fill_is_not_evidence(self):
        m=deepcopy(self.documents["management"])
        for e in m["events"]:
            if e["kind"]=="TP_FILLED":e["position_hash"]="f"*64
        self.put("management",m)
        self.assertIn("actual_position_management_and_reconciliation",self.assess()["failedChecks"])

    def test_unsafe_case_that_sent_any_order_fails(self):
        b=deepcopy(self.documents["blocking"]);b["cases"][0]["order_send_count"]=1
        self.put("blocking",b)
        self.assertIn("unsafe_states_block_new_entry",self.assess()["failedChecks"])

    def test_runtime_dependency_and_sensitive_fields_fail_without_echo(self):
        r=deepcopy(self.documents["runtime"]);r["mac_dependency"]=True
        self.put("runtime",r)
        self.assertIn("deterministic_vps_runtime_without_external_dependencies",self.assess()["failedChecks"])
        r["password"]="synthetic-never-echo";self.put("runtime",r)
        output=self.assess()
        self.assertEqual(output["status"],"NOT_READY")
        self.assertNotIn("synthetic-never-echo",json.dumps(output))

    def test_stale_operator_attestation_is_not_current_readiness(self):
        self.manifest["operator_attestation"]["reviewed_at_utc"]=stamp(NOW-timedelta(days=2))
        self.assertIn("actual_demo_operator_review",self.assess()["failedChecks"])


if __name__ == "__main__":
    unittest.main()
