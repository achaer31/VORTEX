"""Adversarial examples for the research execution model; no broker access."""
import unittest
from decimal import Decimal

import pandas as pd

from vortex_xau.simulator import SimulatorConfig, floor_lots, simulate


def bars(n=4, *, start="2026-09-14 08:00", atr=1 / 2.2, signal=1):
    return pd.DataFrame({"open": [4000.0] * n, "high": [4000.1] * n,
                         "low": [3999.9] * n, "close": [4000.0] * n,
                         "spread_points": [0.0] * n, "atr": [atr] * n,
                         "signal": [signal] * n, "ready": [True] * n},
                        index=pd.date_range(start, periods=n, freq="5min"))


def run(frame, **changes):
    return simulate(frame, {"slippage_per_ounce": 0.0, **changes})


class SimulatorTests(unittest.TestCase):
    def test_only_previous_signal_at_next_open_and_no_future_atr_or_spread(self):
        f = bars(3)
        f["signal"] = [0, 1, -1]
        f.iloc[-1, f.columns.get_loc("open")] = 4000.05
        a = run(f)
        changed = f.copy()
        changed.iloc[-1, changed.columns.get_indexer(["signal", "atr", "spread_points"])] = [0, 999, 99999]
        b = run(changed)
        self.assertEqual(a["summary"]["n_trades"], 1)
        self.assertEqual(a["trades"].iloc[0].entry_time, f.index[2])
        self.assertEqual(a["trades"].iloc[0].entry_price, 4000.05)
        self.assertEqual(a["trades"].iloc[0].signal_bar_open, f.index[1])
        pd.testing.assert_frame_equal(a["trades"], b["trades"])

    def test_gap_does_not_reuse_an_old_signal_for_entry(self):
        f = bars(3)
        f.index = pd.to_datetime(["2026-09-14 08:00", "2026-09-14 08:20", "2026-09-14 08:25"])
        result = run(f)
        self.assertEqual(result["summary"]["skip_reasons"]["gap"], 1)
        self.assertEqual(result["trades"].iloc[0].entry_time, f.index[2])

    def test_entry_candle_stop_is_checked(self):
        f = bars(2)
        f.loc[f.index[1], "low"] = 3998.0
        result = run(f)
        trade = result["trades"].iloc[0]
        self.assertEqual(trade.exit_reason, "stop")
        self.assertEqual(trade.entry_time, trade.exit_time)
        self.assertAlmostEqual(trade.exit_price, 3999.0)
        self.assertLess(trade.net_pnl, 0)

    def test_both_barriers_touched_uses_stop_first(self):
        f = bars(2)
        f.loc[f.index[1], ["low", "high"]] = [3998.0, 4003.0]
        result = run(f)
        self.assertEqual(result["trades"].iloc[0].exit_reason, "stop_both_touched")
        self.assertAlmostEqual(result["trades"].iloc[0].net_pnl, -1.0)

    def test_stop_gap_fills_at_adverse_open_plus_slippage(self):
        f = bars(3)
        f.loc[f.index[2], ["open", "high", "low", "close"]] = [3998.5, 3998.6, 3998.4, 3998.5]
        trade = simulate(f)["trades"].iloc[0]
        self.assertEqual(trade.exit_reason, "stop_gap")
        self.assertAlmostEqual(trade.exit_price, 3998.47)
        self.assertLess(trade.exit_price, trade.stop_price)

    def test_target_gap_gets_no_favorable_credit_or_tp_slippage(self):
        f = bars(3)
        f.loc[f.index[2], ["open", "high", "low", "close"]] = [4005.0, 4005.1, 4004.9, 4005.0]
        trade = simulate(f)["trades"].iloc[0]
        self.assertEqual(trade.exit_reason, "target_gap_at_level")
        self.assertEqual(trade.exit_price, trade.target_price)
        self.assertAlmostEqual(trade.slippage_cost, .03 * trade.units)

    def test_sell_stop_uses_ask_not_bid_and_previous_spread(self):
        f = bars(2, signal=-1)
        f.loc[f.index[0], "spread_points"] = 100.0
        f.loc[f.index[1], "high"] = 4000.95
        trade = run(f)["trades"].iloc[0]
        self.assertEqual(trade.exit_reason, "stop")
        self.assertAlmostEqual(trade.entry_spread, .1)
        self.assertLess(f.iloc[1].high, trade.stop_price)

    def test_known_opening_spread_through_stop_is_rejected_before_risk(self):
        f = bars(2, atr=.1 / 2.2)
        f.loc[f.index[0], "spread_points"] = 300.0
        result = run(f)
        self.assertEqual(result["summary"]["n_trades"], 0)
        self.assertEqual(result["summary"]["final_equity"], 50)
        self.assertEqual(result["summary"]["skip_reasons"]["opening_spread_crosses_stop"], 1)

    def test_stop_and_target_use_tick_grid_without_extra_target_profit(self):
        for side in (1, -1):
            f = bars(2, atr=1.001 / 2.2, signal=side)
            f.loc[f.index[0], "spread_points"] = 1.5
            t = run(f)["trades"].iloc[0]
            self.assertEqual(Decimal(str(t.stop_price)) % Decimal('.001'), 0)
            self.assertEqual(Decimal(str(t.target_price)) % Decimal('.001'), 0)
            self.assertLessEqual(t.effective_target_r, 2.2 + 1e-10)
            self.assertGreaterEqual(t.stop_distance, 1.001 - 1e-10)

    def test_intrabar_exit_timestamp_discloses_unknown_fill_time(self):
        f = bars(2)
        f.loc[f.index[1], "low"] = 3998.0
        t = run(f)["trades"].iloc[0]
        self.assertEqual(t.exit_phase, "intrabar")
        self.assertEqual(t.exit_time_basis, "bar_open_label_actual_intrabar_time_unknown")

    def test_no_same_bar_reentry_after_existing_position_exit(self):
        f = bars(4)
        f.loc[f.index[2], "low"] = 3998.5
        result = run(f)
        self.assertEqual(list(result["trades"].entry_time), [f.index[1], f.index[3]])
        self.assertEqual(result["summary"]["skip_reasons"]["same_bar_exit"], 1)

    def test_min_lot_floor_never_rounds_up_small_50_dollar_budget(self):
        self.assertEqual(floor_lots(.01999999), .01)
        self.assertEqual(floor_lots(.00999999), 0)
        f = bars(2, atr=2 / 2.2)
        rejected = run(f)
        self.assertEqual(rejected["summary"]["n_trades"], 0)
        self.assertEqual(rejected["summary"]["skip_reasons"]["min_lot"], 1)
        accepted = simulate(bars(2))
        t = accepted["trades"].iloc[0]
        self.assertEqual(t.lots, .01)
        self.assertLessEqual(t.planned_stop_loss, 50 * .03)
        self.assertAlmostEqual(t.planned_stop_loss, (1 + .03 + .03) * 100 * .01)

    def test_margin_can_reject_minimum_lot_independently(self):
        result = run(bars(2), leverage=1)
        self.assertEqual(result["summary"]["n_trades"], 0)
        self.assertEqual(result["summary"]["skip_reasons"]["margin"], 1)
        normal = run(bars(2), risk_fraction=.10)
        self.assertLessEqual(normal["trades"].iloc[0].margin_estimate, 50 * .25)
        self.assertTrue(normal["summary"]["limits"]["margin_model_is_approximate"])

    def test_fees_at_entry_exit_and_terminal_liquidation_reconcile(self):
        f = bars(3, atr=1.0)
        result = simulate(f, {"risk_fraction": .10, "commission_per_lot_per_side": 4.0})
        t = result["trades"].iloc[0]
        self.assertEqual(t.exit_reason, "end_of_data")
        self.assertAlmostEqual(result["equity"].iloc[1].balance, 50 - t.entry_fee)
        self.assertAlmostEqual(result["equity"].iloc[1].equity, 50 + t.net_pnl)
        self.assertAlmostEqual(t.commission_cost, 2 * t.lots * 4)
        self.assertAlmostEqual(t.net_pnl, -.06 * t.units - 2 * t.lots * 4)
        self.assertAlmostEqual(result["summary"]["final_equity"], 50 + result["trades"].net_pnl.sum())
        self.assertAlmostEqual(result["summary"]["costs"]["commission"], t.commission_cost)
        self.assertEqual(result["equity"].iloc[-1].position_lots, 0)

    def test_two_losses_halve_next_risk_and_third_freezes_until_next_day(self):
        f = bars(7, atr=.4 / 2.2)
        f.loc[:, "low"] = 3999.5
        f.index = pd.to_datetime(["2026-09-14 08:00", "2026-09-14 08:05", "2026-09-14 08:10",
                                  "2026-09-14 08:15", "2026-09-14 08:20", "2026-09-15 08:00",
                                  "2026-09-15 08:05"])
        result = run(f)
        trades = result["trades"]
        self.assertEqual(len(trades), 4)
        self.assertEqual(list(trades.risk_fraction), [.03, .03, .015, .03])
        self.assertEqual(trades.iloc[2].loss_streak_after, 3)
        self.assertEqual(trades.iloc[3].loss_streak_after, 1)
        self.assertEqual(result["summary"]["skip_reasons"]["loss_streak_freeze"], 1)

    def test_daily_kill_discrete_close_blocks_and_is_not_guaranteed_max(self):
        f = bars(5)
        f.loc[:, "low"] = 3998.5
        result = run(f, risk_fraction=.10)
        self.assertEqual(result["summary"]["n_trades"], 2)
        self.assertLess(result["summary"]["final_equity"], 50 * .85)
        self.assertTrue(result["equity"].iloc[2].daily_loss_blocked)
        self.assertGreater(result["summary"]["skip_reasons"]["daily_loss_limit"], 0)
        self.assertFalse(result["summary"]["limits"]["daily_loss_is_guaranteed_maximum"])

    def test_daily_open_mark_to_market_kill_flattens_adversely(self):
        f = bars(4)
        f.loc[f.index[2]:, ["open", "high", "low", "close"]] = [3998.0, 3998.1, 3997.9, 3998.0]
        result = run(f, risk_fraction=.10)
        self.assertEqual(result["summary"]["n_trades"], 1)
        self.assertEqual(result["trades"].iloc[0].exit_reason, "daily_loss_open")
        self.assertEqual(result["trades"].iloc[0].exit_price, 3998.0)

    def test_session_closes_at_first_1800_open(self):
        f = bars(5, start="2026-09-14 17:45")
        result = run(f)
        self.assertEqual(result["summary"]["n_trades"], 1)
        self.assertEqual(result["trades"].iloc[0].exit_time, f.index[3])
        self.assertEqual(result["trades"].iloc[0].exit_reason, "session_flat")
        self.assertEqual(result["summary"]["skip_reasons"]["session_closed"], 1)

    def test_missing_session_end_flattens_on_date_change_without_reentry(self):
        f = bars(3, start="2026-09-14 17:50")
        f.index = pd.to_datetime(["2026-09-14 17:50", "2026-09-14 17:55", "2026-09-15 08:00"])
        result = run(f)
        self.assertEqual(result["summary"]["n_trades"], 1)
        self.assertEqual(result["trades"].iloc[0].exit_reason, "date_change_flat")
        self.assertEqual(result["summary"]["skip_reasons"]["same_bar_exit"], 1)

    def test_36_nominal_bar_time_exit_and_no_reentry_on_exit_bar(self):
        f = bars(40)
        result = run(f)
        t = result["trades"].iloc[0]
        self.assertEqual(t.exit_reason, "time_exit")
        self.assertEqual(t.exit_time, f.index[37])
        self.assertEqual(t.holding_bars, 36)
        self.assertEqual(result["trades"].iloc[1].entry_time, f.index[38])

    def test_invalid_spread_skips_flat_and_refuses_to_fabricate_open_position_marks(self):
        flat = bars(2)
        flat.loc[flat.index[0], "spread_points"] = -1
        self.assertEqual(run(flat)["summary"]["skip_reasons"]["invalid_spread"], 1)
        active = bars(3)
        active.loc[active.index[1], "spread_points"] = float("nan")
        with self.assertRaisesRegex(ValueError, "spread while a position"):
            run(active)

    def test_warmup_and_no_signal_have_explicit_skip_counts(self):
        f = bars(3, signal=0)
        f.loc[f.index[0], "ready"] = False
        result = run(f)
        self.assertEqual(result["summary"]["skip_reasons"]["warmup"], 1)
        self.assertEqual(result["summary"]["skip_reasons"]["no_signal"], 1)
        self.assertEqual(result["summary"]["final_equity"], 50)
        self.assertEqual(result["summary"]["vault_balance"], 0)


if __name__ == "__main__":
    unittest.main()
