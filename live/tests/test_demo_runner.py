"""Synthetic DEMO-runner guard tests. This module never imports MetaTrader5."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import contextlib
import io
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from demo_runner import (Config, MAGIC, Runner, SafetyStop, StateStore,
                         fresh_decision, main, make_plan, verify_account, verify_tick)

NOW = int(pd.Timestamp("2026-09-14T08:00:00Z").timestamp())


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_TRADE_MODE_REAL = 2
    ACCOUNT_MARGIN_MODE_RETAIL_HEDGING = 2
    ACCOUNT_MARGIN_MODE_RETAIL_NETTING = 0
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    SYMBOL_TRADE_MODE_FULL = 4
    SYMBOL_TRADE_EXECUTION_INSTANT = 1
    SYMBOL_TRADE_EXECUTION_REQUEST = 0
    SYMBOL_TRADE_EXECUTION_MARKET = 2
    SYMBOL_CHART_MODE_BID = 0
    SYMBOL_FILLING_FOK = 1
    SYMBOL_FILLING_IOC = 2
    ORDER_FILLING_FOK = 0
    ORDER_FILLING_IOC = 1
    ORDER_FILLING_RETURN = 2
    TRADE_ACTION_DEAL = 1
    TRADE_ACTION_SLTP = 6
    ORDER_TIME_GTC = 0
    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_DONE_PARTIAL = 10010
    POSITION_TYPE_BUY = 0
    TIMEFRAME_M5 = 5
    TIMEFRAME_M15 = 15
    TIMEFRAME_H1 = 16385
    DEAL_ENTRY_IN = 0
    DEAL_ENTRY_OUT = 1
    DEAL_ENTRY_OUT_BY = 3

    def __init__(self):
        self.account = SimpleNamespace(login=424242, trade_mode=0, currency="USD",
            margin_mode=2, balance=10000.0, equity=10000.0, margin_free=10000.0,
            margin=0.0, trade_allowed=True, trade_expert=True, leverage=2000, server="Synthetic-Demo")
        self.terminal = SimpleNamespace(connected=True, trade_allowed=True,
                                       tradeapi_disabled=False, build=6182)
        self.info = SimpleNamespace(name="XAUUSD", currency_base="XAU", currency_profit="USD",
            currency_margin="USD", custom=False, visible=True, select=True, trade_mode=4,
            digits=3, point=.001, trade_tick_size=.001, trade_contract_size=100.0,
            trade_tick_value=.1, trade_tick_value_profit=.1, trade_tick_value_loss=.1,
            volume_min=.01, volume_step=.01, volume_max=200.0, volume_limit=0.0,
            trade_stops_level=10, trade_freeze_level=0, filling_mode=3, trade_exemode=1,
            chart_mode=0, order_mode=49)
        self.tick = SimpleNamespace(bid=4000.0, ask=4000.2, last=4000.1,
                                    time=NOW, time_msc=NOW * 1000)
        self.profit_result = "calculate"
        self.margin_result = "calculate"
        self.sent = []
        self.positions = ()
        self.orders = ()
        self.deals = ()
        self.send_result = None
        self.send_error = None
        self.check_callback = None
        self.before_send = None

    def account_info(self):
        return deepcopy(self.account)

    def terminal_info(self):
        return deepcopy(self.terminal)

    def symbol_info(self, symbol):
        return deepcopy(self.info)

    def symbol_info_tick(self, symbol):
        return deepcopy(self.tick)

    def positions_get(self):
        return deepcopy(self.positions)

    def orders_get(self):
        return deepcopy(self.orders)

    def history_deals_get(self, **kwargs):
        return deepcopy(self.deals)

    def copy_rates_from_pos(self, symbol, timeframe, start, count):
        return [{"time": NOW}]

    def order_check(self, request):
        if self.check_callback:
            self.check_callback()
        return SimpleNamespace(retcode=0)

    def order_calc_profit(self, action, symbol, volume, price_open, price_close):
        if self.profit_result != "calculate":
            return self.profit_result
        side = 1 if action == self.ORDER_TYPE_BUY else -1
        return side * volume * 100 * (price_close - price_open)

    def order_calc_margin(self, action, symbol, volume, price):
        if self.margin_result != "calculate":
            return self.margin_result
        return volume * 100 * price / 2000

    def order_send(self, request):
        if self.before_send:
            self.before_send()
        self.sent.append(deepcopy(request))
        if self.send_error:
            raise self.send_error
        return self.send_result


def config(**changes):
    return Config(expected_login=424242, session_offset_minutes=0, **changes)


def decision():
    when = pd.Timestamp(NOW, unit="s")
    return pd.Series({"decision_time": when, "ready": True, "signal": 1, "atr": .2,
                      "htf_m15_close": when, "htf_h1_close": when},
                     name=when - pd.Timedelta(minutes=5))


class AccountGuardTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeMT5()

    def test_expected_usd_demo_account_passes_without_sending(self):
        verify_account(self.api, config(), armed=False)
        self.assertEqual(self.api.sent, [])

    def test_real_account_is_rejected_even_with_matching_login(self):
        self.api.account.trade_mode = self.api.ACCOUNT_TRADE_MODE_REAL
        with self.assertRaises(SafetyStop):
            verify_account(self.api, config(), armed=True)
        self.assertEqual(self.api.sent, [])

    def test_wrong_demo_login_is_rejected(self):
        self.api.account.login = 434343
        with self.assertRaises(SafetyStop):
            verify_account(self.api, config(), armed=False)

    def test_netting_account_is_rejected_to_prevent_manual_volume_merging(self):
        self.api.account.margin_mode = self.api.ACCOUNT_MARGIN_MODE_RETAIL_NETTING
        with self.assertRaisesRegex(SafetyStop, "hedging"):
            verify_account(self.api, config(), armed=False)

    def test_non_usd_account_cannot_reinterpret_the_50_dollar_budget(self):
        for currency in ("EUR", "USC"):
            self.api.account.currency = currency
            with self.subTest(currency=currency), self.assertRaises(SafetyStop):
                verify_account(self.api, config(), armed=False)

    def test_missing_account_is_unknown_not_an_empty_account(self):
        self.api.account = None
        with self.assertRaises(SafetyStop):
            verify_account(self.api, config(), armed=False)

    def test_disconnected_terminal_blocks_armed_mode(self):
        self.api.terminal.connected = False
        with self.assertRaises(SafetyStop):
            verify_account(self.api, config(), armed=True)

    def test_disabled_algorithmic_permission_blocks_armed_mode(self):
        self.api.terminal.trade_allowed = False
        with self.assertRaises(SafetyStop):
            verify_account(self.api, config(), armed=True)

    def test_account_switch_is_detected_on_a_second_preflight(self):
        verify_account(self.api, config(), armed=False)
        self.api.account.trade_mode = self.api.ACCOUNT_TRADE_MODE_REAL
        with self.assertRaises(SafetyStop):
            verify_account(self.api, config(), armed=True)


class SizingGuardTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeMT5()

    def plan(self, atr=10, **changes):
        return make_plan(self.api, config(**changes), self.api.account,
                         self.api.info, self.api.tick, side=1, atr=atr)

    def test_large_demo_balance_does_not_raise_the_50_dollar_risk_basis(self):
        # 0.01 lot at a 22-dollar stop risks about $22, although this account
        # has $10,000. The $50 allocation cannot afford it at 3% or 7.5%.
        for risk in (.03, .075):
            with self.subTest(risk=risk), self.assertRaisesRegex(SafetyStop, "min_lot"):
                self.plan(atr=10, risk_fraction=risk)
        self.assertEqual(self.api.sent, [])

    def test_missing_broker_profit_estimate_never_falls_back_to_guessed_risk(self):
        self.api.profit_result = None
        with self.assertRaisesRegex(SafetyStop, "broker_profit_calculation_failed"):
            self.plan(atr=.2)

    def test_missing_broker_margin_estimate_never_becomes_zero_margin(self):
        self.api.margin_result = None
        with self.assertRaisesRegex(SafetyStop, "broker_margin_calculation_failed"):
            self.plan(atr=.2)

    def test_valid_lot_is_floored_and_actual_rechecked_risk_fits_budget(self):
        p = self.plan(atr=.3)
        self.assertEqual(p["budget"], 1.5)
        self.assertGreaterEqual(p["volume"], .01)
        self.assertLessEqual(p["planned_risk"], 1.5)
        self.assertLessEqual(p["margin"], 12.5)
        self.assertLess(p["sl"], self.api.tick.bid)
        self.assertGreater(p["tp"], self.api.tick.ask)
        self.assertEqual(self.api.sent, [])

    def test_loss_streak_halves_budget_and_third_loss_freezes(self):
        p = make_plan(self.api, config(), self.api.account, self.api.info,
                      self.api.tick, side=1, atr=.3, loss_streak=2)
        self.assertEqual(p["budget"], .75)
        self.assertLessEqual(p["planned_risk"], .75)
        with self.assertRaisesRegex(SafetyStop, "loss_streak_freeze"):
            make_plan(self.api, config(), self.api.account, self.api.info,
                      self.api.tick, side=1, atr=.3, loss_streak=3)

    def test_known_spread_through_stop_is_rejected(self):
        self.api.tick.ask = 4001.0
        with self.assertRaisesRegex(SafetyStop, "spread_or_broker_stop_limit"):
            self.plan(atr=.2)


class ChronologyTests(unittest.TestCase):
    def test_adjacent_closed_m5_and_closed_htf_are_eligible(self):
        fresh_decision(decision(), NOW, NOW + 1, config())

    def test_recent_tick_does_not_make_a_late_bar_decision_fresh(self):
        tick = FakeMT5().tick
        tick.time = NOW + 299
        verify_tick(tick, NOW + 299, config())
        with self.assertRaisesRegex(SafetyStop, "late_or_future_decision"):
            fresh_decision(decision(), NOW, NOW + 299, config())

    def test_missing_m5_interval_is_not_replayed(self):
        row = decision()
        row.name -= pd.Timedelta(minutes=5)
        with self.assertRaisesRegex(SafetyStop, "closed_m5_not_adjacent"):
            fresh_decision(row, NOW, NOW + 1, config())

    def test_future_or_stale_higher_timeframe_context_is_rejected(self):
        for field, delta in (("htf_m15_close", pd.Timedelta(minutes=1)),
                             ("htf_m15_close", pd.Timedelta(minutes=-15)),
                             ("htf_h1_close", pd.Timedelta(minutes=-60))):
            row = decision()
            row[field] += delta
            with self.subTest(field=field, delta=delta), self.assertRaisesRegex(SafetyStop, "stale_or_future_htf"):
                fresh_decision(row, NOW, NOW + 1, config())

    def test_stale_future_missing_or_crossed_tick_is_rejected(self):
        for changes in ({"time": NOW - 11}, {"time": NOW + 1}, {"bid": 4001.0}, {"ask": float("nan")}):
            tick = FakeMT5().tick
            for key, value in changes.items():
                setattr(tick, key, value)
            with self.subTest(changes=changes), self.assertRaises(SafetyStop):
                verify_tick(tick, NOW, config())


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="vortex-demo-test-")
        self.api = FakeMT5()
        self.cfg = config(mode="armed")
        self.store = StateStore(self.temp.name, self.cfg.fingerprint, NOW)
        self.runner = Runner(self.api, self.cfg, self.store, clock=lambda: NOW + 1)
        self.runner.load_signal = lambda bar: decision()
        self.request = {"action": 1, "symbol": "XAUUSD", "type": 0, "volume": .01,
                        "price": 4000.2, "sl": 3999.5, "tp": 4001.74,
                        "magic": MAGIC, "type_filling": 0, "type_time": 0}
        self.context = {"decision": NOW}

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def restart(self):
        self.store.close()
        self.store = StateStore(self.temp.name, self.cfg.fingerprint, NOW + 2)
        self.runner = Runner(self.api, self.cfg, self.store, clock=lambda: NOW + 2)
        self.runner.load_signal = lambda bar: decision()

    def test_second_process_cannot_share_a_state_directory(self):
        with self.assertRaisesRegex(SafetyStop, "another_runner_owns_state"):
            StateStore(self.temp.name, self.cfg.fingerprint, NOW)

    def test_observe_mode_cannot_send_even_when_helper_called_directly(self):
        runner = Runner(self.api, config(), self.store, clock=lambda: NOW + 1)
        with self.assertRaisesRegex(SafetyStop, "observe_mode_cannot_send"):
            runner._send(self.request, "entry", {})
        self.assertEqual(self.api.sent, [])

    def test_intent_is_on_disk_before_the_first_send_and_none_result_never_retries(self):
        import json
        def assert_intent_saved():
            saved = json.loads(self.store.path.read_text())
            self.assertIsNotNone(saved["pending"])
            self.assertEqual(saved["pending"]["request"]["volume"], .01)
        self.api.before_send = assert_intent_saved
        with self.assertRaisesRegex(SafetyStop, "order_outcome_requires_reconciliation"):
            self.runner._send(self.request, "entry", self.context)
        self.assertEqual(len(self.api.sent), 1)
        self.api.before_send = None
        self.restart()
        with self.assertRaisesRegex(SafetyStop, "unresolved_order_intent"):
            self.runner.step()
        self.assertEqual(len(self.api.sent), 1)

    def test_partial_fill_leaves_pending_and_does_not_top_up(self):
        self.api.send_result = SimpleNamespace(retcode=self.api.TRADE_RETCODE_DONE_PARTIAL)
        with self.assertRaisesRegex(SafetyStop, "order_outcome_requires_reconciliation"):
            self.runner._send(self.request, "entry", self.context)
        with self.assertRaisesRegex(SafetyStop, "unresolved_order_intent"):
            self.runner._send(self.request, "entry", self.context)
        self.assertEqual(len(self.api.sent), 1)

    def test_account_switch_during_order_check_prevents_send(self):
        self.api.check_callback = lambda: setattr(self.api.account, "trade_mode", 2)
        with self.assertRaisesRegex(SafetyStop, "demo_account_required"):
            self.runner._send(self.request, "entry", self.context)
        self.assertEqual(self.api.sent, [])

    def test_api_position_or_order_error_is_unknown_not_empty(self):
        for attribute in ("positions", "orders"):
            setattr(self.api, attribute, None)
            with self.subTest(attribute=attribute), self.assertRaisesRegex(SafetyStop, "positions_or_orders_unavailable"):
                self.runner.step()
            setattr(self.api, attribute, ())
        self.assertEqual(self.api.sent, [])

    def test_processed_bar_is_not_replayed_after_restart(self):
        self.runner.state["last_decision"] = NOW
        self.runner.state["daily_blocked"] = True
        self.runner.state["day"] = "2026-09-14"
        self.runner.state["day_start_balance"] = 50.0
        self.store.save()
        self.restart()
        self.assertTrue(self.runner.state["daily_blocked"])
        self.assertEqual(self.runner.step(), "waiting_new_m5")
        self.assertEqual(self.api.sent, [])

    def test_no_reentry_in_a_bar_with_a_prior_bot_exit(self):
        self.runner.state["last_close_bar"] = NOW
        self.store.save()
        self.assertEqual(self.runner.step(), "same_bar_exit")
        self.assertEqual(self.api.sent, [])

    def test_untracked_bot_position_is_not_adopted_or_modified(self):
        self.api.positions = (SimpleNamespace(identifier=7001, magic=MAGIC, symbol="XAUUSD"),)
        with self.assertRaisesRegex(SafetyStop, "untracked_bot_position"):
            self.runner.step()
        self.assertEqual(self.api.sent, [])

    def test_owned_position_with_manual_volume_change_is_not_closed(self):
        self.runner.state["positions"]["7001"] = {"ticket": 7002, "type": 0, "volume": .01,
                                                   "sl": 3999.5, "tp": 4001.7}
        self.api.positions = (SimpleNamespace(identifier=7001, ticket=7002, magic=MAGIC, symbol="XAUUSD",
                                             type=0, volume=.02, sl=3999.5, tp=4001.7),)
        with self.assertRaisesRegex(SafetyStop, "owned_position_changed_externally"):
            self.runner.step()
        self.assertEqual(self.api.sent, [])

    def test_manual_exposure_appearing_during_order_check_prevents_entry_send(self):
        for attribute in ("positions", "orders"):
            self.runner.state["pending"] = None
            self.store.save()
            self.api.positions = self.api.orders = ()
            self.api.check_callback = lambda name=attribute: setattr(self.api, name, (SimpleNamespace(magic=0),))
            with self.subTest(attribute=attribute), self.assertRaisesRegex(SafetyStop, "exposure_changed_before_send"):
                self.runner._send(self.request, "entry", self.context)
        self.assertEqual(self.api.sent, [])

    def test_quote_change_after_order_check_prevents_entry_send(self):
        self.api.check_callback = lambda: setattr(self.api.tick, "ask", 4000.4)
        with self.assertRaisesRegex(SafetyStop, "quote_changed_before_send"):
            self.runner._send(self.request, "entry", self.context)
        self.assertEqual(self.api.sent, [])

    def test_eight_dollar_bot_loss_blocks_even_on_ten_thousand_dollar_demo(self):
        self.runner.state.update(day="2026-09-14", day_start_balance=50.0,
                                 day_realized_pnl=-8.0, daily_blocked=False)
        self.store.save()
        self.api.account.balance = self.api.account.equity = 9992.0
        self.assertEqual(self.runner.step(), "daily_loss_limit")
        self.assertTrue(self.runner.state["daily_blocked"])
        self.assertEqual(self.api.sent, [])

    def test_missing_state_with_existing_journal_cannot_reset_safety_history(self):
        self.store.event(NOW, "test", "existing_history")
        self.store.close()
        self.store.path.unlink()
        with self.assertRaisesRegex(SafetyStop, "state_missing_with_existing_journal"):
            StateStore(self.temp.name, self.cfg.fingerprint, NOW + 1)

    def test_changed_account_fingerprint_cannot_adopt_prior_state(self):
        self.store.close()
        other = Config(expected_login=999999, session_offset_minutes=0)
        with self.assertRaisesRegex(SafetyStop, "runtime_identity_or_config_changed"):
            StateStore(self.temp.name, other.fingerprint, NOW + 1)

    def test_cli_cannot_arm_legacy_profile_before_new_profile_validation(self):
        with patch.object(sys, "argv", ["demo_runner.py", "--mode", "armed"]):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                main()
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(self.api.sent, [])


if __name__ == "__main__":
    unittest.main()
