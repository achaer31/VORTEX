from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from live.collect_evidence import (CollectionError, archive_frames, collect_accounting)
from live.observe_v02 import (Observer, ObserverConfig, ObserverState, collect_frames, main)
from test_observe_v02 import FakeMT5, ImmediateExecutor, NOW


def deal(kind=1, profit=-5.72, ticket=777):
    return SimpleNamespace(ticket=ticket, order=778, time=int(NOW)-10, time_msc=(int(NOW)-10)*1000,
        type=kind, entry=1, magic=0, position_id=779, reason=0, volume=.01 if kind in (0,1) else 0,
        price=2500. if kind in (0,1) else 0, commission=0., swap=0., profit=profit, fee=0.,
        symbol="XAUUSD" if kind in (0,1) else "", comment="synthetic manual fixture", external_id="")


class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.directory = Path(self.tmp.name)
        self.config = ObserverConfig(123456, 0, self.directory)
        self.state = ObserverState(self.config, NOW); self.api = FakeMT5()
    def tearDown(self):
        self.state.close(); self.tmp.cleanup()
    def test_collect_cli_can_read_without_changing_a_failed_baseline(self):
        self.api.balance = 44.28; self.api.deals = [deal()]
        env = {"VORTEX_EXPECTED_LOGIN": "123456", "VORTEX_SESSION_UTC_OFFSET_MINUTES": "0",
               "VORTEX_STATE_DIR": str(self.directory / "cli"), "VORTEX_BASELINE_STATUS": "NO_GO"}
        original = deepcopy(env)
        with patch("live.observe_v02.sys.platform", "win32"), patch.dict(sys.modules, {"MetaTrader5": self.api}), patch("live.observe_v02.time.time", return_value=NOW):
            self.assertEqual(main(["--collect", "--once"], env), 0)
            self.assertEqual(main(["--observe", "--once"], env), 2)
        self.assertEqual(env, original)
        self.assertEqual(self.api.lifecycle, ["initialize", "shutdown"])
        snapshot = json.loads((self.directory / "cli" / "status.json").read_text())
        self.assertEqual(snapshot["account"]["balance"], 44.28)
        self.assertEqual(snapshot["v02"]["metrics"]["balance"], 44.28)
        self.assertEqual(snapshot["strategy"]["state"], "collector_running")
        self.assertEqual(snapshot["v02"]["mode"], "FROZEN")
        self.assertEqual(snapshot["v02"]["action"], "WAIT")
        self.assertTrue(snapshot["v02"]["protection"]["killSwitch"])
        self.assertFalse(snapshot["status"]["eaRunning"])
        self.assertIsNone(snapshot["v02"]["metrics"]["dailyDrawdown"])
    def test_collect_rejects_real_account_without_market_or_deal_archive(self):
        self.api.mode = 2
        observer = Observer(self.api, self.config, self.state, clock=lambda: NOW, executor=ImmediateExecutor(), collection_mode=True)
        try:
            snapshot = observer.snapshot()
        finally:
            observer.close()
        self.assertFalse(snapshot["status"]["demoVerified"])
        self.assertIsNone(snapshot["account"])
        self.assertEqual(self.api.calls, [])
        self.assertFalse((self.directory / "collection" / "XAUUSD_M5.csv").exists())
        self.assertFalse((self.directory / "collection" / "accounting-latest.json").exists())
    def test_archives_are_append_only_and_changed_history_fails(self):
        frames = collect_frames(self.api, self.state, NOW)
        first = archive_frames(self.directory, frames)
        second = archive_frames(self.directory, frames)
        self.assertGreater(first["M5"]["appendedRows"], 0)
        self.assertEqual(second["M5"]["appendedRows"], 0)
        path = self.directory / "collection" / "XAUUSD_M5.csv"
        original = path.read_bytes()
        frames["M5"].iloc[0, frames["M5"].columns.get_loc("close")] = 2500.5
        with self.assertRaisesRegex(CollectionError, "archived_history_changed"):
            archive_frames(self.directory, frames)
        self.assertEqual(path.read_bytes(), original)
    def test_manual_loss_reconstructs_prior_day_balance_not_current_balance(self):
        self.api.balance = 44.28; self.api.deals = [deal()]
        report = collect_accounting(self.api, self.directory, self.api.account_info(), NOW)
        self.assertAlmostEqual(report["dayStartBalance"], 50.)
        self.assertAlmostEqual(report["realizedTradingPnl"], -5.72)
        self.assertEqual(report["currentBalance"], 44.28)
        self.assertIsNone(report["dailyEquityDrawdown"])
        self.assertEqual(report["tradeDealCount"], 1)
        self.assertTrue(report["includedRegardlessOfMagic"])
        collect_accounting(self.api, self.directory, self.api.account_info(), NOW)
        records = (self.directory / "collection" / "deals-2026-09-14.jsonl").read_text().splitlines()
        self.assertEqual(len(records), 1)
        self.assertEqual(json.loads(records[0])["deal"]["ticket"], 777)
    def test_same_day_deposit_is_reported_separately_from_trading_loss(self):
        self.api.balance = 44.28; self.api.deals = [deal(2, 50., 1), deal()]
        report = collect_accounting(self.api, self.directory, self.api.account_info(), NOW)
        self.assertAlmostEqual(report["dayStartBalance"], 0.)
        self.assertAlmostEqual(report["balanceAdjustments"], 50.)
        self.assertAlmostEqual(report["dayStartPlusBalanceAdjustments"], 50.)
        self.assertAlmostEqual(report["realizedTradingPnl"], -5.72)
    def test_missing_or_unmapped_history_is_explicitly_unavailable(self):
        self.api.deals = None
        report = collect_accounting(self.api, self.directory, self.api.account_info(), NOW)
        self.assertFalse(report["historyAvailable"])
        self.assertIsNone(report["dayStartBalance"])
        self.api.deals = [deal(3, 10.)]
        report = collect_accounting(self.api, self.directory, self.api.account_info(), NOW)
        self.assertTrue(report["historyAvailable"])
        self.assertIsNone(report["dayStartBalance"])
        self.assertEqual(report["reason"], "accounting_deal_type_or_credit_requires_review")
    def test_account_switch_prevents_private_deal_archive(self):
        account = self.api.account_info(); self.api.mode = 2; self.api.deals = [deal()]
        report = collect_accounting(self.api, self.directory, account, NOW)
        self.assertEqual(report["reason"], "account_changed_during_deal_read")
        self.assertFalse((self.directory / "collection" / "deals-2026-09-14.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
