import ast
from concurrent.futures import Future
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from live.observe_v02 import (Observer, ObserverConfig, ObserverState, ObserverStop,
                              DecisionJournal, collect_frames, main)
from live.publish_telemetry import (PublisherConfig, PublisherStop, NoRedirect,
                                    publish_once, validate_publication, main as publisher_main)
from live.telegram_notify import queue_change, send_pending

NOW = datetime(2026, 9, 14, 8, 0, 5, tzinfo=timezone.utc).timestamp()


class ImmediateExecutor:
    def __init__(self):
        self.count = 0
    def submit(self, fn, *args):
        self.count += 1; future = Future()
        try:
            future.set_result(fn(*args))
        except Exception as error:
            future.set_exception(error)
        return future
    def shutdown(self, **kwargs):
        pass


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_MARGIN_MODE_RETAIL_HEDGING = 2
    TIMEFRAME_M5 = 5; TIMEFRAME_M15 = 15; TIMEFRAME_H1 = 60
    def __init__(self):
        self.now = NOW; self.mode = 0; self.account_reads = 0; self.switch_after_first = False
        self.calls = []; self.truncated = False
        self.balance = 50.; self.deals = []; self.lifecycle = []
    def account_info(self):
        self.account_reads += 1
        mode = 2 if self.switch_after_first and self.account_reads > 1 else self.mode
        return SimpleNamespace(trade_mode=mode, login=123456, currency="USD", margin_mode=2,
                               balance=self.balance, equity=self.balance, margin_free=self.balance, margin=0., profit=0., credit=0.)
    def initialize(self, *args, **kwargs):
        self.lifecycle.append("initialize"); return True
    def shutdown(self):
        self.lifecycle.append("shutdown")
    def history_deals_get(self, start, end):
        return self.deals
    def terminal_info(self):
        return SimpleNamespace(connected=True, trade_allowed=False, tradeapi_disabled=True)
    def symbol_info_tick(self, symbol):
        return SimpleNamespace(bid=2500., ask=2500.1, time=self.now)
    def positions_get(self, **kwargs):
        return []
    def copy_rates_range(self, symbol, timeframe, start, end):
        self.calls.append((symbol, timeframe, start, end))
        times = pd.date_range("2026-09-13T08:00:00Z", "2026-09-14T08:05:00Z", freq=f"{timeframe}min")
        if self.truncated:
            times = times[1:]
        return [dict(time=int(t.timestamp()), open=2500., high=2501., low=2499., close=2500., tick_volume=100, spread=100, real_volume=0) for t in times]


class ObserverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.directory = Path(self.tmp.name)
        self.config = ObserverConfig(123456, 0, self.directory)
        self.state = ObserverState(self.config, NOW)
        self.api = FakeMT5(); self.executor = ImmediateExecutor()
        self.observer = Observer(self.api, self.config, self.state, clock=lambda: self.api.now, executor=self.executor)
    def tearDown(self):
        self.observer.close(); self.state.close(); self.tmp.cleanup()
    def test_default_check_and_baseline_gate_never_import_mt5(self):
        env = {"VORTEX_EXPECTED_LOGIN": "123456", "VORTEX_SESSION_UTC_OFFSET_MINUTES": "0", "VORTEX_STATE_DIR": str(self.directory)}
        with patch.dict(sys.modules, {"MetaTrader5": None}):
            self.assertEqual(main([], env), 0)
            self.assertEqual(main(["--observe"], env), 2)
        self.assertNotIn("VORTEX_BASELINE_STATUS", env)
    def test_no_execution_or_account_authentication_calls_in_observer_ast(self):
        module = ast.parse((REPO / "live" / "observe_v02.py").read_text())
        forbidden = {"order_send", "order_check", "login"}
        attrs = {node.func.attr for node in ast.walk(module) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
        self.assertFalse(attrs & forbidden)
    def test_filters_unclosed_bars_and_h4_requires_exact_groups(self):
        frames = collect_frames(self.api, self.state, NOW)
        for tf, frame in frames.items():
            minutes = {"M5": 5, "M15": 15, "H1": 60, "H4": 240}[tf]
            self.assertTrue((frame.index + pd.Timedelta(minutes=minutes) <= pd.Timestamp(NOW, unit="s", tz="UTC")).all())
        self.assertEqual(len(frames["H4"]), 6)
        self.assertTrue(all(call[2].tzinfo is not None for call in self.api.calls))
    def test_history_start_is_persisted_and_rebased_history_rejected(self):
        collect_frames(self.api, self.state, NOW)
        original = self.state.data["historyStartUtc"]
        self.api.truncated = True
        with self.assertRaisesRegex(ObserverStop, "history_start_changed"):
            collect_frames(self.api, self.state, NOW + 300)
        self.assertEqual(original, self.state.data["historyStartUtc"])
    def test_only_one_calculation_per_close_missing_external_stays_invalid(self):
        self.observer.snapshot(); result = self.observer.snapshot(); self.observer.snapshot()
        self.assertEqual(self.executor.count, 1)
        self.assertEqual(result["v02"]["engines"]["atlas"]["status"], "INVALID")
        self.assertEqual(result["v02"]["mode"], "FROZEN")
        self.assertEqual(result["v02"]["action"], "WAIT")
        self.assertTrue(result["v02"]["protection"]["killSwitch"])
        self.assertIsNone(result["v02"]["metrics"]["realizedPnl"])
        self.assertNotIn("123456", json.dumps(result))
        records = [json.loads(line) for line in (self.directory / "decision-journal.jsonl").read_text().splitlines()]
        decisions = [x for x in records if x["kind"] == "decision"]
        self.assertEqual(len(decisions), 1)
        self.assertFalse(decisions[0]["executionEnabled"])
        self.assertEqual(decisions[0]["sources"]["news"]["status"], "missing")
        self.assertEqual(len(decisions[0]["specSha256"]), 64)
        self.assertEqual(len(decisions[0]["sources"]["M5"]["sha256"]), 64)
    def test_real_or_changed_account_is_redacted_before_write(self):
        self.api.mode = 2
        result = self.observer.snapshot()
        self.assertIsNone(result["account"]); self.assertIsNone(result["quote"])
        self.assertEqual(len(self.api.calls), 0)
        self.api.mode = 0; self.api.account_reads = 0; self.api.switch_after_first = True
        result = self.observer.snapshot()
        self.assertFalse(result["status"]["demoVerified"])
        self.assertTrue(all(x is None for x in result["v02"]["metrics"].values()))
        self.assertIsNone(result["quote"])
    def test_stale_quote_is_not_refreshed_by_a_heartbeat(self):
        self.observer.snapshot(); self.observer.snapshot()
        self.api.symbol_info_tick = lambda _: SimpleNamespace(bid=2500., ask=2500.1, time=NOW - 11)
        result = self.observer.snapshot()
        self.assertFalse(result["v02"]["protection"]["dataFresh"])
        self.assertEqual(result["strategy"]["reason"], "market_quote_stale")
    def test_positions_are_anonymous_and_missing_protection_is_null(self):
        self.api.positions_get = lambda **_: [SimpleNamespace(symbol="XAUUSD", type=0, identifier=987654321,
            volume=.01, price_open=2499., price_current=2500., profit=1., sl=0., tp=0.)]
        snapshot = self.observer.snapshot()
        self.assertEqual(len(snapshot["positions"][0]["id"]), 64)
        self.assertIsNone(snapshot["positions"][0]["stopLoss"])
        self.assertNotIn("987654321", json.dumps(snapshot))
        validate_publication(snapshot, NOW)
    def test_produced_snapshot_passes_the_actual_cloud_validator(self):
        self.observer.snapshot(); snapshot = self.observer.snapshot()
        validate_publication(snapshot, NOW)
        node = os.environ.get("VORTEX_NODE_BIN") or shutil.which("node")
        if not node:
            self.skipTest("Node unavailable; set VORTEX_NODE_BIN for cloud contract check")
        code = "import {validateSnapshot} from './cloud/functions/vortex-live/core.mjs'; let s='';for await(const x of process.stdin)s+=x;validateSnapshot(JSON.parse(s),{now:" + str(int(NOW * 1000)) + "});"
        result = subprocess.run([node, "--input-type=module", "-e", code], input=json.dumps(snapshot), text=True, cwd=REPO, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
    def test_journal_recovery_deduplicates_and_detects_tampering(self):
        self.observer.snapshot(); self.observer.snapshot()
        restored = DecisionJournal(self.directory)
        lines = (self.directory / "decision-journal.jsonl").read_text().splitlines()
        decision = next(json.loads(x) for x in lines if json.loads(x)["kind"] == "decision")
        self.assertFalse(restored.append(decision))
        value = json.loads(lines[-1]); value["reason"] = "tampered"; lines[-1] = json.dumps(value)
        (self.directory / "decision-journal.jsonl").write_text("\n".join(lines) + "\n")
        with self.assertRaisesRegex(ObserverStop, "integrity_failed"):
            DecisionJournal(self.directory)
    def test_runtime_paths_and_nonzero_utc_offset_are_rejected(self):
        with self.assertRaises(ObserverStop):
            ObserverConfig(123456, 0, REPO / "private")
        with self.assertRaises(ObserverStop):
            ObserverConfig(123456, 60, self.directory)


class FakeResponse:
    status = 200
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def read(self, size):
        return b'{"reason":"accepted","ok":true}'


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.directory = Path(self.tmp.name)
        self.state = ObserverState(ObserverConfig(123456, 0, self.directory), NOW)
        self.observer = Observer(FakeMT5(), ObserverConfig(123456, 0, self.directory), self.state, clock=lambda: NOW, executor=ImmediateExecutor())
        self.snapshot = self.observer.snapshot()
    def tearDown(self):
        self.observer.close(); self.state.close(); self.tmp.cleanup()
    def test_publisher_offline_default_and_https_configuration(self):
        env = {"VORTEX_INGEST_ENDPOINT": "https://example.test/functions/v1/vortex-live", "VORTEX_INGEST_TOKEN": "a" * 64, "VORTEX_STATE_DIR": str(self.directory)}
        with patch("live.publish_telemetry.build_opener", side_effect=AssertionError("network prohibited")):
            self.assertEqual(publisher_main([], env), 0)
            self.assertEqual(publisher_main(["--publish", "--once"], env), 2)
        for endpoint in ("http://example.test", "https://example.test/?token=x", "https://user:secret@example.test"):
            with self.assertRaises(PublisherStop):
                PublisherConfig(endpoint, "a" * 64, self.directory / "status.json")
    def test_network_sends_only_header_token_and_no_redirect(self):
        calls = []
        opener = SimpleNamespace(open=lambda request, timeout: (calls.append(request) or FakeResponse()))
        config = PublisherConfig("https://example.test/", "a" * 64, self.directory / "status.json")
        self.assertEqual(publish_once(config, NOW, opener), "accepted")
        self.assertEqual(calls[0].get_header("Authorization"), "Bearer " + "a" * 64)
        self.assertNotIn("a" * 64, calls[0].full_url)
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, None, None, "https://evil.test"))
    def test_nested_sensitive_field_is_blocked_before_network(self):
        self.snapshot["account"]["password"] = "synthetic-do-not-transmit"
        (self.directory / "status.json").write_text(json.dumps(self.snapshot))
        opener = SimpleNamespace(open=lambda *args, **kwargs: self.fail("network reached"))
        config = PublisherConfig("https://example.test/", "a" * 64, self.directory / "status.json")
        with self.assertRaises(PublisherStop):
            publish_once(config, NOW, opener)
    def test_credential_objects_in_allowed_leaves_never_reach_network(self):
        import copy
        for path in (("account", "balance"), ("quote", "bid"), ("v02", "metrics", "equity"), ("v02", "engines", "orion", "score"), ("v02", "context", "nextNews")):
            value = copy.deepcopy(self.snapshot); target = value
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = {"password": "synthetic-secret-do-not-transmit"}
            (self.directory / "status.json").write_text(json.dumps(value))
            opener = SimpleNamespace(open=lambda *args, **kwargs: self.fail("network reached"))
            config = PublisherConfig("https://example.test/", "a" * 64, self.directory / "status.json")
            with self.assertRaises(PublisherStop):
                publish_once(config, NOW, opener)
    def test_conflicting_session_stops_without_retry_loop(self):
        env = {"VORTEX_INGEST_ENDPOINT": "https://example.test/", "VORTEX_INGEST_TOKEN": "a" * 64, "VORTEX_STATE_DIR": str(self.directory), "VORTEX_BASELINE_STATUS": "passed_reviewed"}
        with patch("live.publish_telemetry.publish_once", return_value="not_newer") as publish:
            self.assertEqual(publisher_main(["--publish"], env), 2)
            self.assertEqual(publish.call_count, 1)
    def test_telegram_queue_ignores_price_changes_and_requires_explicit_owner_enable(self):
        self.assertTrue(queue_change(self.directory, self.snapshot))
        self.snapshot["quote"]["bid"] += .01
        self.assertFalse(queue_change(self.directory, self.snapshot))
        with self.assertRaises(PublisherStop):
            send_pending(self.directory, {})
        state = json.loads((self.directory / "telegram-state.json").read_text())
        self.assertEqual(len(state["pending"]), 1)
        self.assertNotIn("2500", state["pending"][0]["text"])
    def test_telegram_uncertain_delivery_is_not_retried_automatically(self):
        queue_change(self.directory, self.snapshot)
        env = {"VORTEX_TELEGRAM_ENABLE": "user_enabled", "VORTEX_TELEGRAM_BOT_TOKEN": "1:" + "a" * 30, "VORTEX_TELEGRAM_CHAT_ID": "1"}
        opener = SimpleNamespace(open=lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError()))
        self.assertEqual(send_pending(self.directory, env, opener), "delivery_uncertain")
        with self.assertRaisesRegex(PublisherStop, "uncertain_delivery"):
            send_pending(self.directory, env, opener)


if __name__ == "__main__":
    unittest.main()
