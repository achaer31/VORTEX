"""Synthetic supervisor integration; every broker and terminal call is fake."""
from concurrent.futures import Future
from datetime import datetime, timezone
from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace as NS
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from execution_v02 import Config, ExecutionStop, Manager, Store
from run_demo_v02 import Supervisor, main, configs
from observe_v02 import ObserverState
from test_execution_v02 import FakeBroker, NOW, decision


def observation(api, **kwargs):
    d=decision(api,**kwargs)
    row=pd.Series(d.row,name=pd.Timestamp(d.bar_open,unit="s",tz="UTC"))
    return {"row":row,"sources":{tf:{"latestAvailableAtUtc":datetime.fromtimestamp(ts,timezone.utc).isoformat(),
                                    "rows":220,"sha256":"0"*64} for tf,ts in d.available.items()},"specSha256":d.spec_sha256}


class ControlledExecutor:
    def __init__(self): self.jobs=[];self.stopped=False
    def submit(self,fn,*args):
        future=Future();self.jobs.append((future,fn,args));return future
    def complete(self):
        future,fn,args=self.jobs[-1];future.set_result(fn(*args))
    def shutdown(self,**kwargs): self.stopped=True


def environment(directory):
    return {"VORTEX_STATE_DIR":str(directory),"VORTEX_EXPECTED_LOGIN":"123", "VORTEX_SESSION_UTC_OFFSET_MINUTES":"0",
        "VORTEX_ACCOUNT_HISTORY_ORIGIN_UTC":datetime.fromtimestamp(NOW-86400,timezone.utc).isoformat(),
        "VORTEX_VERIFIED_SLIPPAGE_USD":"0.03","VORTEX_VERIFIED_COMMISSION_PER_LOT_SIDE_USD":"0",
        "VORTEX_BASELINE_STATUS":"passed_reviewed", "VORTEX_DEMO_EXECUTION_APPROVAL":"demo_execution_reviewed",
        "VORTEX_EXECUTION_COST_STATUS":"verified_reviewed"}


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)
        self.api=FakeBroker();self.oc,self.ec=configs(environment(self.path))
        self.store=Store(self.path,self.ec);self.manager=Manager(self.api,self.ec,self.store,lambda:self.api.now)
        self.executor=ControlledExecutor();self.collected=[]
        def collect(api,state,now):
            self.collected.append(threading.get_ident());return observation(self.api)
        self.sup=Supervisor(self.api,self.oc,NS(directory=self.path),self.manager,clock=lambda:self.api.now,
                            executor=self.executor,collector=collect,calculator=lambda frames,config:frames)

    def tearDown(self):
        self.sup.close();self.store.close();self.temp.cleanup()

    def test_reconcile_precedes_collect_and_completed_decision(self):
        calls=[];original=self.manager.step
        def step(value=None):calls.append("health" if value is None else "decision");return original(value)
        self.manager.step=step
        collector=self.sup.collector
        self.sup.collector=lambda *args:(calls.append("collect") or collector(*args))
        self.sup.poll();self.assertEqual(calls,["health","collect"])
        self.executor.complete();self.sup.poll()
        self.assertEqual(calls,["health","collect","health","decision"])
        self.assertEqual(len(self.api.sent),1)

    def test_late_worker_result_is_skipped_not_replayed(self):
        self.sup.poll();self.api.advance(seconds=31);self.executor.complete()
        result=self.sup.poll()
        self.assertEqual(result["state"],"decision_skipped")
        self.assertEqual(result["reason"],"late_or_nonadjacent_decision")
        self.assertEqual(self.api.sent,[])
        self.sup.poll();self.assertEqual(len(self.executor.jobs),1)

    def test_pending_features_still_poll_health_and_daily_kill(self):
        self.manager.step(decision(self.api));self.sup.poll()
        self.assertFalse(self.executor.jobs[-1][0].done())
        self.api.manual_loss(8.)
        self.assertEqual(self.sup.poll()["reason"],"daily_kill")
        self.assertEqual(self.api.positions,[])

    def test_read_outage_then_recovery_does_not_call_mutation_retry(self):
        self.api.t.connected=False
        self.assertEqual(self.sup.poll()["state"],"waiting_recovery")
        self.assertEqual(self.executor.jobs,[])
        self.api.t.connected=True
        self.assertEqual(self.sup.poll()["state"],"features_pending")
        self.assertEqual(self.api.sent,[])

    def test_ambiguous_submission_halts_and_retains_fatal_status(self):
        self.sup.poll();self.executor.complete();self.api.result_mode="accepted_lost"
        with self.assertRaisesRegex(ExecutionStop,"ambiguous"):self.sup.poll()
        self.sup.close()
        value=json.loads(self.sup.status_path.read_text())
        self.assertEqual(value["state"],"halted");self.assertTrue(value["unresolvedIntent"])
        self.assertFalse(value["executionArmed"]);self.assertEqual(len(self.api.sent),1)

    def test_stop_does_not_flatten_or_wait_for_worker(self):
        self.manager.step(decision(self.api));self.sup.poll()
        count=len(self.api.sent);(self.path/"STOP").touch()
        self.assertEqual(self.sup.poll()["state"],"stopped")
        self.sup.close();self.assertEqual(len(self.api.sent),count)
        self.assertEqual(len(self.api.positions),1);self.assertTrue(self.executor.stopped)

    def test_status_does_not_overwrite_observer_or_contain_identity(self):
        (self.path/"status.json").write_text('"observer sentinel"')
        self.sup.poll()
        self.assertEqual((self.path/"status.json").read_text(),'"observer sentinel"')
        value=json.loads(self.sup.status_path.read_text())
        for name in ("login","account","quote","server","password","ip","positions"):
            self.assertNotIn(name,value)
        self.assertEqual(value["role"],"demo_execution_supervisor")
        self.assertNotIn("executionEnabled",value);self.assertIsNone(value["entryEligible"])

    def test_real_worker_only_calculates_main_thread_owns_broker_reads(self):
        from concurrent.futures import ThreadPoolExecutor
        owner=threading.get_ident();reads=[];worker=[]
        old=self.api.account_info
        def account():reads.append(threading.get_ident());return old()
        self.api.account_info=account
        self.sup.executor.shutdown();self.sup.executor=ThreadPoolExecutor(max_workers=1)
        self.sup.calculator=lambda frames,config:(worker.append(threading.get_ident()) or frames)
        self.sup.poll();self.sup.future.result(timeout=2);self.sup.poll()
        self.assertTrue(worker and all(t!=owner for t in worker))
        self.assertTrue(reads and all(t==owner for t in reads))
        self.assertTrue(all(t==owner for t in self.collected))

    def test_expected_no_signal_is_skipped_while_health_remains_available(self):
        self.sup.calculator=lambda frames,config:{**frames,"row":frames["row"].copy()}
        self.sup.poll();self.executor.complete();self.sup.future.result()["row"]["ready"]=False
        self.assertEqual(self.sup.poll()["state"],"decision_skipped")
        self.assertEqual(self.sup.poll()["state"],"running")
        self.assertEqual(self.api.sent,[])


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/"runtime"
        self.env=environment(self.path);self.calls=[]
    def tearDown(self):self.temp.cleanup()
    def factory(self):self.calls.append("factory");raise AssertionError("Unexpected terminal access")

    def test_default_and_check_create_no_state_or_terminal(self):
        for args in ([],["--check"],["--check","--once"]):
            self.assertEqual(main(args,self.env,broker_factory=self.factory),0)
        self.assertFalse(self.path.exists());self.assertEqual(self.calls,[])

    def test_each_approval_missing_blocks_before_state_and_init(self):
        for key in ("VORTEX_BASELINE_STATUS","VORTEX_DEMO_EXECUTION_APPROVAL","VORTEX_EXECUTION_COST_STATUS"):
            env=dict(self.env);env.pop(key)
            self.assertEqual(main(["--run-demo"],env,broker_factory=self.factory,platform="win32"),2)
            self.assertFalse(self.path.exists())
        self.assertEqual(self.calls,[])

    def test_bad_history_or_cost_configuration_blocks_without_state(self):
        for key,value in (("VORTEX_ACCOUNT_HISTORY_ORIGIN_UTC","2026-09-14"),
                          ("VORTEX_VERIFIED_SLIPPAGE_USD","nan"),
                          ("VORTEX_VERIFIED_COMMISSION_PER_LOT_SIDE_USD","-1")):
            env=dict(self.env);env[key]=value
            self.assertEqual(main(["--run-demo"],env,broker_factory=self.factory,platform="win32"),2)
            self.assertFalse(self.path.exists())

    def test_non_windows_rejected_before_state(self):
        self.assertEqual(main(["--run-demo"],self.env,broker_factory=self.factory,platform="linux"),2)
        self.assertFalse(self.path.exists())

    def test_existing_collector_lock_blocks_before_initialization(self):
        oc,_=configs(self.env);state=ObserverState(oc,NOW)
        try:
            self.assertEqual(main(["--run-demo","--once"],self.env,broker_factory=self.factory,clock=lambda:NOW,platform="win32"),2)
            self.assertEqual(self.calls,[])
        finally:state.close()

    def test_once_with_fake_terminal_initializes_only_after_gates_and_shuts_down(self):
        api=FakeBroker();api.initialize=lambda *args,**kwargs:(self.calls.append("initialize") or True)
        api.shutdown=lambda:self.calls.append("shutdown")
        executor=ControlledExecutor()
        def supervisor(*args,**kwargs):
            return Supervisor(*args,**kwargs,executor=executor,collector=lambda *a:observation(api),calculator=lambda f,c:f)
        result=main(["--run-demo","--once"],self.env,broker_factory=lambda:api,clock=lambda:NOW,
                    platform="win32",supervisor_factory=supervisor)
        self.assertEqual(result,0);self.assertEqual(self.calls,["initialize","shutdown"])
        self.assertEqual(api.sent,[]);self.assertTrue((self.path/"execution-status.json").exists())
        self.assertFalse((self.path/"status.json").exists())

    def test_unexpected_error_halts_redacted_and_still_releases_terminal(self):
        api=FakeBroker();api.initialize=lambda **kwargs:True
        api.shutdown=lambda:self.calls.append("shutdown")
        def fail(*args):raise RuntimeError("synthetic-private-error-detail")
        def supervisor(*args,**kwargs):
            return Supervisor(*args,**kwargs,executor=ControlledExecutor(),collector=fail)
        stderr=io.StringIO()
        with redirect_stderr(stderr):
            result=main(["--run-demo","--once"],self.env,broker_factory=lambda:api,clock=lambda:NOW,
                        platform="win32",supervisor_factory=supervisor)
        self.assertEqual(result,3);self.assertEqual(self.calls,["shutdown"])
        value=json.loads((self.path/"execution-status.json").read_text())
        self.assertEqual(value["state"],"halted");self.assertFalse(value["executionArmed"])
        self.assertNotIn("synthetic-private-error-detail",stderr.getvalue())


if __name__=="__main__":unittest.main()
