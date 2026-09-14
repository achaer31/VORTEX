"""Synthetic execution paths, independent of historical strategy outcomes."""
import unittest
from unittest.mock import patch

import pandas as pd

from vortex_v02.backtest import BacktestConfig, simulate, size_leg


def fixture(rows, start="2026-01-05 10:00:00", times=None):
    index = (pd.DatetimeIndex(times) if times is not None else
             pd.date_range(start, periods=len(rows), freq="5min", tz="UTC"))
    data = []
    for ts, change in zip(index, rows):
        r = dict(open=4000., high=4000.2, low=3999.8, close=4000., spread_points=0.,
                 atr=1., signal=1, ready=True, mode="NORMAL", consensus=90.,
                 orion=90., nova=90., stop_long=3998.6, stop_short=4001.4,
                 swing_low=3998., swing_high=4002., news_blocked=False,
                 execution_valid=True, decision_time=ts + pd.Timedelta(minutes=5))
        r.update(change)
        data.append(r)
    return pd.DataFrame(data, index=index)


def config(**kwargs):
    return BacktestConfig(**{**dict(starting_cash=1000, risk_fraction=.02,
                                  slippage_per_ounce=0, allow_pyramiding=False), **kwargs})


def entries(result):
    e = result["events"]
    return e[e.event == "entry"] if not e.empty else e


def exits(result):
    e = result["events"]
    return e[e.event == "exit"] if not e.empty else e


class BacktestTests(unittest.TestCase):
    def test_next_bar_entry_and_current_signal_cannot_trade_itself(self):
        f = fixture([dict(signal=0), dict(signal=1), dict(signal=0)])
        result = simulate(f, config())
        self.assertEqual(list(entries(result).time), [f.index[2]])
        self.assertEqual(result["trades"].iloc[0].signal_bar_open, f.index[1])
        one = simulate(f.iloc[:2], config())
        self.assertEqual(one["summary"]["n_trades"], 0)

    def test_current_feature_and_spread_cannot_change_own_entry(self):
        a = fixture([{}, {}])
        b = a.copy()
        b.loc[b.index[1], ["atr", "spread_points", "stop_long", "signal"]] = [100, 9000, 1, -1]
        ta = simulate(a, config())["trades"].iloc[0]
        tb = simulate(b, config())["trades"].iloc[0]
        for key in ("entry_price", "initial_stop", "initial_lots", "side"):
            self.assertEqual(ta[key], tb[key])

    def test_gap_and_future_decision_reject_entry(self):
        for time in ("2026-01-05 10:10:00+00:00", "2026-01-05 10:15:00+00:00"):
            f = fixture([{}, {}], times=["2026-01-05 10:00:00+00:00", time])
            r = simulate(f, config())
            self.assertEqual(r["summary"]["n_trades"], 0)
            self.assertEqual(r["summary"]["skip_reasons"]["gap_or_noncausal_decision"], 1)
        f = fixture([{}, {}])
        f.loc[f.index[0], "decision_time"] = f.index[1] + pd.Timedelta(minutes=5)
        self.assertEqual(simulate(f, config())["summary"]["n_trades"], 0)

    def test_entry_candle_stop_and_double_touch_are_stop_first(self):
        for high, reason in ((4000.2, "stop"), (4004., "stop_both_touched")):
            f = fixture([{}, dict(high=high, low=3998., close=3999.)])
            r = simulate(f, config())
            self.assertEqual(list(exits(r).reason), [reason])
            t = r["trades"].iloc[0]
            self.assertAlmostEqual(t.net_pnl, -t.initial_lots * 100 * 1.4)
            self.assertEqual(exits(r).iloc[0].exit_time_basis, "bar_open_label_intrabar_time_unknown")

    def test_short_stops_use_ask_proxy(self):
        f = fixture([dict(signal=-1, spread_points=200),
                     dict(high=4001.3, low=3999.8, signal=0)])
        r = simulate(f, config())
        self.assertEqual(list(exits(r).reason), ["stop"])
        self.assertEqual(r["trades"].iloc[0].side, -1)

    def test_stop_gap_fills_adverse_open_and_blocks_same_bar_reentry(self):
        f = fixture([{}, {}, dict(open=3997., high=3998., low=3996., close=3997.),
                     dict(open=3997., high=3997.2, low=3996.8, close=3997.)])
        r = simulate(f, config())
        gap = exits(r)[exits(r).reason == "stop_gap"].iloc[0]
        self.assertEqual(gap.price, 3997.)
        self.assertNotIn(f.index[2], list(entries(r).time))
        self.assertEqual(r["summary"]["skip_reasons"]["same_bar_exit"], 1)

    def test_old_stop_precedes_new_breakeven_after_gap(self):
        f = fixture([{}, dict(high=4001.6, close=4001.5),
                     dict(open=3997., high=3997.3, low=3996.8, close=3997.)])
        r = simulate(f, config())
        self.assertEqual(list(exits(r).reason), ["stop_gap"])
        self.assertEqual(exits(r).iloc[0].price, 3997.)

    def test_exact_partial_sizes_and_target_gap_no_favorable_credit(self):
        f = fixture([{}, {}, dict(open=4004., high=4004.2, low=4003.8, close=4004., signal=0)])
        r = simulate(f, config(starting_cash=900))
        x = exits(r)
        self.assertEqual(list(x.reason), ["tp1_gap_at_level", "tp2_gap_at_level", "end_of_data"])
        self.assertEqual(list(x.lots), [.03, .03, .06])
        self.assertAlmostEqual(x.iloc[0].price, 4002.1)
        self.assertAlmostEqual(x.iloc[1].price, 4003.5)
        self.assertEqual(r["trades"].iloc[0].fill_count, 3)

    def test_trailing_uses_prior_closed_values_and_is_monotonic(self):
        f = fixture([{}, dict(high=4003.6, close=4003.5),
                     dict(open=4003.5, high=4004., low=4003., close=4003.5,
                          atr=20., swing_low=3900., signal=0),
                     dict(open=4003.5, high=4003.6, low=4002., close=4002.5, signal=0)])
        r = simulate(f, config(starting_cash=900))
        updates = r["events"][r["events"].event == "stop_update"]
        self.assertAlmostEqual(updates.iloc[0].stop, 4002.2)
        self.assertTrue(updates.stop.is_monotonic_increasing)
        self.assertAlmostEqual(exits(r).iloc[-1].price, 4002.2)

    def test_current_high_cannot_tighten_before_same_bar_low(self):
        f = fixture([{}, dict(high=4001.6, low=3999., close=4001.5)])
        r = simulate(f, config())
        self.assertEqual(list(exits(r).reason), ["end_of_data"])
        self.assertEqual(len(r["events"][r["events"].event == "stop_update"]), 0)

    def test_costs_entry_fee_and_forced_close_reconcile(self):
        f = fixture([dict(spread_points=100), {}])
        r = simulate(f, config(slippage_per_ounce=.03, commission_per_lot_per_side=3.5))
        t = r["trades"].iloc[0]
        expected = -t.initial_lots * (100 * (.10 + .03 + .03) + 2 * 3.5)
        self.assertAlmostEqual(t.net_pnl, expected)
        self.assertAlmostEqual(r["summary"]["final_equity"], 1000 + expected)
        self.assertAlmostEqual(t.entry_fee, t.initial_lots * 3.5)
        self.assertAlmostEqual(r["summary"]["costs"]["total_proxy"], -expected)
        self.assertAlmostEqual(r["summary"]["final_equity"], r["equity"].iloc[-1].equity)

    def test_fifty_dollars_never_rounds_to_unaffordable_minimum(self):
        f = fixture([dict(atr=10, stop_long=3986), {}])
        r = simulate(f, config(starting_cash=50, risk_fraction=.075, stress_fixed_risk=True))
        self.assertEqual(r["summary"]["n_trades"], 0)
        self.assertEqual(r["summary"]["skip_reasons"]["min_lot"], 1)
        self.assertEqual(r["summary"]["final_equity"], 50)
        self.assertFalse(r["summary"]["deployable_configuration"])

    def test_risk_gate_floors_down_and_recognizes_exact_split(self):
        p = size_leg(50, .02, 4000, 3999.77, 1, config(starting_cash=50), 12.5)
        self.assertTrue(p["allowed"])
        self.assertEqual(p["lots"], .04)
        self.assertEqual(p["parts"], (.01, .01, .02))
        self.assertLessEqual(p["planned_loss"], 1.)

    def test_independent_risk_gate_is_used(self):
        with patch("vortex_v02.backtest.size_order", return_value={
            "allowed": False, "reason": "independent_gate_denied", "risk_cash": 0}) as gate:
            r = simulate(fixture([{}, {}]), config())
        self.assertTrue(gate.called)
        self.assertEqual(r["summary"]["skip_reasons"]["independent_gate_denied"], 1)

    def test_margin_cap_rejects_instead_of_rounding_risk_up(self):
        r = simulate(fixture([{}, {}]), config(leverage=10))
        self.assertEqual(r["summary"]["skip_reasons"]["margin"], 1)
        self.assertEqual(r["summary"]["n_trades"], 0)

    def test_actual_fill_distance_cap_and_open_spread_crossing(self):
        f = fixture([dict(stop_long=3997.9), {}])
        r = simulate(f, config(slippage_per_ounce=.2))
        self.assertEqual(r["summary"]["skip_reasons"]["stop_exceeds_atr_cap"], 1)
        f = fixture([dict(atr=.1, stop_long=4000.5, spread_points=200), {}])
        r = simulate(f, config())
        self.assertEqual(r["summary"]["skip_reasons"]["opening_spread_crosses_stop"], 1)

    def test_targets_stops_are_on_price_grid(self):
        f = fixture([dict(atr=1.001, stop_long=3998.5986), {}])
        t = simulate(f, config())["trades"].iloc[0]
        for key in ("tp1", "tp2", "initial_stop"):
            self.assertAlmostEqual(t[key] / .001, round(t[key] / .001), places=6)
        self.assertLessEqual(t.tp1 - t.entry_price, 1.5 * t.initial_r + 1e-9)

    def test_missing_execution_or_news_fails_closed(self):
        for change, reason in ((dict(execution_valid=False), "execution_missing_or_invalid"),
                               (dict(news_blocked=pd.NA), "news_blocked_or_missing"),
                               (dict(news_blocked=True), "news_blocked_or_missing"),
                               (dict(ready=False), "decision_invalid_or_warmup"),
                               (dict(spread_points=-1), "execution_missing_or_invalid"),
                               (dict(signal=1.5), "invalid_signal")):
            with self.subTest(change=change):
                r = simulate(fixture([change, {}]), config())
                self.assertEqual(r["summary"]["n_trades"], 0)
                self.assertEqual(r["summary"]["skip_reasons"][reason], 1)

    def test_invalid_execution_news_cannot_disable_existing_stop(self):
        f = fixture([{}, dict(news_blocked=True, execution_valid=False, ready=False),
                     dict(low=3998., close=3999.)])
        r = simulate(f, config())
        self.assertEqual(list(exits(r).reason), ["stop"])
        self.assertEqual(r["summary"]["n_trades"], 1)

    def test_missing_spread_for_open_protection_aborts_honestly(self):
        f = fixture([{}, dict(spread_points=float("nan")), {}])
        with self.assertRaisesRegex(ValueError, "cannot price existing"):
            simulate(f, config())

    def test_daily_kill_from_gap_and_block_reentry(self):
        f = fixture([{}, {}, dict(open=3980., high=3980.2, low=3979.8, close=3980.),
                     dict(open=3980., high=3980.2, low=3979.8, close=3980.)])
        r = simulate(f, config())
        self.assertGreaterEqual(r["summary"]["max_close_sampled_drawdown"], .15)
        self.assertTrue(r["equity"].iloc[-1].daily_killed)
        self.assertEqual(len(entries(r)), 1)
        self.assertIn("daily_kill", list(r["events"].reason))

    def test_three_campaign_losses_freeze_across_day_reset(self):
        rows = [{}, dict(low=3998., close=3999.),
                dict(low=3998., close=3999.), dict(low=3998., close=3999.), {}, {}]
        f = fixture(rows, times=["2026-01-05 10:00Z", "2026-01-05 10:05Z", "2026-01-05 10:10Z",
                                 "2026-01-05 10:15Z", "2026-01-06 10:00Z", "2026-01-06 10:05Z"])
        r = simulate(f, config())
        self.assertEqual(r["summary"]["n_campaigns"], 3)
        self.assertTrue(r["summary"]["run_frozen"])
        self.assertEqual(r["summary"]["maximum_losing_campaigns"], 3)
        self.assertEqual(list(r["trades"].risk_fraction), [.02, .02, .01])
        self.assertTrue(r["equity"].iloc[-1].run_frozen)

    def test_two_campaign_losses_disable_extreme(self):
        f = fixture([{}, dict(low=3998., close=3999.),
                     dict(low=3998., close=3999., mode="EXTREME"), {}])
        r = simulate(f, config(risk_fraction=.05))
        self.assertEqual(r["summary"]["n_campaigns"], 2)
        self.assertEqual(r["summary"]["skip_reasons"]["losing_streak_extreme_disabled"], 1)

    def test_mode_risk_cap_and_stress_are_distinct(self):
        f = fixture([{}, {}])
        normal = simulate(f, config(risk_fraction=.075))
        stress = simulate(f, config(risk_fraction=.075, stress_fixed_risk=True))
        self.assertEqual(normal["trades"].iloc[0].risk_fraction, .02)
        self.assertEqual(stress["trades"].iloc[0].risk_fraction, .075)
        self.assertFalse(stress["summary"]["production_risk_profile"])

    def test_rollover_swap_is_charged_and_can_trip_daily_kill(self):
        f = fixture([{}, {}, {}], start="2026-01-07 23:50:00")
        r = simulate(f, config(swap_long_per_lot_per_day=-500))
        swap = r["events"][r["events"].event == "swap"]
        self.assertEqual(list(swap.multiplier), [3])
        self.assertAlmostEqual(swap.iloc[0].cash_change, -210.)
        self.assertAlmostEqual(r["summary"]["final_equity"], 790.)
        self.assertEqual(list(exits(r).reason), ["daily_kill_open"])
        self.assertEqual(r["equity"].iloc[-1].day_start_equity, 1000.)
        self.assertAlmostEqual(r["trades"].iloc[0].net_pnl, -210.)

    def test_partial_swap_only_charges_remaining_lots(self):
        f = fixture([{}, dict(high=4002.2, close=4002.1),
                     dict(open=4002.1, high=4002.2, low=4002., close=4002.1)],
                    start="2026-01-06 23:50:00")
        r = simulate(f, config(starting_cash=900, swap_long_per_lot_per_day=-10))
        swap = r["events"][r["events"].event == "swap"]
        self.assertAlmostEqual(swap.iloc[0].cash_change, -.9)
        self.assertAlmostEqual(r["trades"].iloc[0].swap_pnl, -.9)
        self.assertAlmostEqual(r["trades"].net_pnl.sum(), r["summary"]["net_profit"])

    def test_affordable_point_zero_one_has_no_fictional_partials(self):
        f = fixture([dict(mode="AGGRESSIVE"), dict(high=4002.2, close=4002.1)])
        r = simulate(f, config(starting_cash=50, risk_fraction=.035))
        t = r["trades"].iloc[0]
        self.assertEqual(t.initial_lots, .01)
        self.assertEqual(t.exit_policy, "single_trailing")
        self.assertEqual(t.parts, (0., 0., .01))
        self.assertEqual(list(exits(r).reason), ["end_of_data"])
        self.assertEqual(list(exits(r).lots), [.01])

    def test_single_lot_full_target_and_double_touch_stop_first(self):
        for low, reason in ((3999.8, "single_tp"), (3998., "stop_both_touched")):
            f = fixture([dict(mode="AGGRESSIVE"), dict(high=4004., low=low)])
            r = simulate(f, config(starting_cash=50, risk_fraction=.035))
            self.assertEqual(list(exits(r).reason), [reason])
            self.assertEqual(list(exits(r).lots), [.01])
            self.assertEqual(r["trades"].iloc[0].fill_count, 1)

    def test_single_lot_trails_only_after_prior_close_one_point_five_r(self):
        f = fixture([dict(mode="AGGRESSIVE"), dict(high=4002.3, low=3999.8, close=4002.2),
                     dict(open=4002.2, high=4002.3, low=4000.8, close=4001.)])
        r = simulate(f, config(starting_cash=50, risk_fraction=.035))
        updates = r["events"][r["events"].event == "stop_update"]
        self.assertEqual(list(updates.time), [f.index[2]])
        self.assertAlmostEqual(updates.iloc[0].stop, 4000.9)
        self.assertEqual(list(exits(r).reason), ["stop"])
        self.assertEqual(list(exits(r).lots), [.01])

    def test_single_target_gap_fills_level_only(self):
        f = fixture([dict(mode="AGGRESSIVE"), {},
                     dict(open=4005., high=4005.2, low=4004.8, close=4005.)])
        r = simulate(f, config(starting_cash=50, risk_fraction=.035))
        self.assertEqual(list(exits(r).reason), ["single_tp_gap_at_level"])
        self.assertAlmostEqual(exits(r).iloc[0].price, 4003.5)

    def test_two_additions_require_prior_closes_and_stop_at_two(self):
        f = self.pyramid_fixture()
        r = simulate(f, config(starting_cash=10000, allow_pyramiding=True))
        e = entries(r)
        self.assertEqual(list(e.reason), ["base", "add1", "add2"])
        self.assertEqual(list(e.time), list(f.index[1:4]))
        self.assertEqual(r["summary"]["n_campaigns"], 1)
        self.assertEqual(r["summary"]["n_adds"], 2)
        self.assertIn("pyramid_limit_or_disabled", r["summary"]["skip_reasons"])
        self.assertTrue((e.cumulative_nominal_risk <= e.campaign_base_equity * .075 + 1e-9).all())
        self.assertAlmostEqual(r["trades"].net_pnl.sum(), r["summary"]["net_profit"])

    def pyramid_fixture(self):
        return fixture([{},
            dict(high=4001.6, close=4001.5, stop_long=4000.1),
            dict(open=4001.5, high=4003.1, low=4001.4, close=4003., stop_long=4001.6),
            dict(open=4003., high=4003.3, low=4002.9, close=4003.2, stop_long=4001.8),
            dict(open=4003.2, high=4003.3, low=4003.1, close=4003.2)])

    def test_current_bar_spike_cannot_trigger_early_add(self):
        f = fixture([{}, dict(high=4001.6, close=4000.),
                     dict(high=4001.6, close=4000.)])
        r = simulate(f, config(starting_cash=10000, allow_pyramiding=True))
        self.assertEqual(list(entries(r).reason), ["base"])
        self.assertIn("pyramid_r_trigger_not_reached", r["summary"]["skip_reasons"])

    def test_second_add_needs_prior_leg_be_and_components(self):
        f = self.pyramid_fixture().iloc[:4].copy()
        f.loc[f.index[2], ["high", "close"]] = [4002.85, 4002.81]
        f.loc[f.index[3], ["open", "high", "low", "close"]] = [4002.81, 4002.85, 4002.7, 4002.81]
        r = simulate(f, config(starting_cash=10000, allow_pyramiding=True))
        self.assertEqual(list(entries(r).reason), ["base", "add1"])
        self.assertIn("earlier_legs_breakeven_not_confirmed", r["summary"]["skip_reasons"])
        f = self.pyramid_fixture().iloc[:4].copy()
        f.loc[f.index[2], "orion"] = -90
        r = simulate(f, config(starting_cash=10000, allow_pyramiding=True))
        self.assertEqual(list(entries(r).reason), ["base", "add1"])
        self.assertIn("pyramid_components", r["summary"]["skip_reasons"])

    def test_adverse_open_cannot_average_a_losing_leg(self):
        f = self.pyramid_fixture().iloc[:4].copy()
        f.loc[f.index[3], ["open", "high", "low", "close"]] = [4001.4, 4001.6, 4001.3, 4001.4]
        r = simulate(f, config(starting_cash=10000, allow_pyramiding=True))
        self.assertEqual(list(entries(r).reason), ["base", "add1"])
        self.assertIn("new_protection_crossed_at_open", list(exits(r).reason))
        self.assertNotIn(f.index[3], list(entries(r).time))

    def test_high_extreme_sensitivities_respect_campaign_nominal_cap(self):
        for risk in (.075, .10):
            f = self.pyramid_fixture().iloc[:3].copy()
            f["mode"] = "EXTREME"
            r = simulate(f, config(starting_cash=10000, risk_fraction=risk, extreme_risk=risk,
                                   max_campaign_risk_fraction=risk, allow_pyramiding=True))
            self.assertEqual(list(entries(r).reason), ["base"])
            self.assertIn("campaign_nominal_risk_cap", r["summary"]["skip_reasons"])
            self.assertFalse(r["summary"]["production_risk_profile"])
            self.assertFalse(r["summary"]["deployable_configuration"])
            self.assertEqual(r["trades"].iloc[0].risk_fraction, risk)

    def test_ten_percent_daily_drawdown_disables_extreme_without_kill(self):
        f = fixture([{}, {}, dict(open=3991., high=3991.2, low=3990.8, close=3991.,
                                      mode="EXTREME", stop_long=3989.6),
                     dict(open=3991., high=3991.2, low=3990.8, close=3991.)])
        r = simulate(f, config(risk_fraction=.05))
        self.assertTrue(r["equity"].iloc[-1].extreme_disabled)
        self.assertFalse(r["equity"].iloc[-1].daily_killed)
        self.assertIn("daily_extreme_disabled", r["summary"]["skip_reasons"])

    def test_milestones_are_observed_or_censored_never_projected(self):
        r = simulate(fixture([dict(signal=0), dict(signal=0)]), config(starting_cash=50))
        self.assertEqual(r["summary"]["ruin_status"], "insufficient_activity")
        self.assertIsNone(r["summary"]["risk_of_ruin_probability"])
        self.assertIsNone(r["summary"]["future_growth_projection"])
        self.assertIsNone(r["summary"]["geometric_return_per_campaign"])
        self.assertIn(250, [m["equity_usd"] for m in r["summary"]["milestones"]])
        self.assertTrue(all(m["status"] == "censored_at_data_end" for m in r["summary"]["milestones"]))
        r = simulate(fixture([{}, {}]), config())
        self.assertTrue(next(m for m in r["summary"]["milestones"] if m["equity_usd"] == 100)["hit"])
        self.assertIsNone(r["summary"]["risk_of_ruin_probability"])

    def test_boolean_flags_are_not_string_truthiness(self):
        for change, reason in ((dict(execution_valid="false"), "execution_missing_or_invalid"),
                               (dict(ready="false"), "decision_invalid_or_warmup"),
                               (dict(news_blocked="false"), "news_blocked_or_missing")):
            r = simulate(fixture([change, {}]), config())
            self.assertEqual(r["summary"]["n_trades"], 0)
            self.assertIn(reason, r["summary"]["skip_reasons"])

    def test_observed_bankruptcy_is_distinct_from_unaffordable_lot(self):
        f = fixture([dict(mode="AGGRESSIVE"), {},
                     dict(open=3900., high=3900.2, low=3899.8, close=3900.)])
        r = simulate(f, config(starting_cash=50, risk_fraction=.035))
        self.assertAlmostEqual(r["summary"]["final_equity"], -50.)
        self.assertTrue(r["summary"]["account_failure"])
        self.assertFalse(r["summary"]["censored"])
        self.assertEqual(r["summary"]["ruin_status"], "observed_account_failure")
        self.assertIsNotNone(r["summary"]["ruin_time"])
        self.assertIsNone(r["summary"]["risk_of_ruin_probability"])
        self.assertIsNone(r["summary"]["future_growth_projection"])
        self.assertIsNone(r["summary"]["geometric_return_per_campaign"])
        self.assertTrue(all(m["status"] == "account_failed_before_observed_hit" for m in r["summary"]["milestones"]))

    def test_weekend_gap_does_not_amend_stop_from_stale_close(self):
        f = fixture([{}, dict(high=4001.6, close=4001.5),
                     dict(open=4001.5, high=4001.6, low=3999.7, close=4001.5)],
                    times=["2026-01-09 20:50Z", "2026-01-09 20:55Z", "2026-01-12 01:00Z"])
        r = simulate(f, config())
        self.assertEqual(len(r["events"][r["events"].event == "stop_update"]), 0)
        self.assertEqual(list(exits(r).reason), ["end_of_data"])

    def test_stale_m15_keeps_old_stop_active(self):
        f = fixture([{}, dict(high=4001.6, close=4001.5, m15_fresh=False),
                     dict(open=4001.5, high=4001.6, low=3998., close=4001.5)])
        r = simulate(f, config())
        self.assertEqual(len(r["events"][r["events"].event == "stop_update"]), 0)
        self.assertEqual(list(exits(r).reason), ["stop"])
        self.assertAlmostEqual(exits(r).iloc[0].price, 3998.6)

    def test_empty_and_invalid_inputs(self):
        f = fixture([{}, {}])
        r = simulate(f.iloc[:0], config())
        self.assertEqual(r["summary"]["n_trades"], 0)
        self.assertEqual(r["summary"]["final_equity"], 1000)
        for bad in (f.set_axis(f.index.tz_localize(None)),
                    f.set_axis([f.index[0], f.index[0]]),
                    f.assign(low=4100.)):
            with self.assertRaises(ValueError):
                simulate(bad, config())
        with self.assertRaises(ValueError):
            config(risk_fraction=.10)


if __name__ == "__main__":
    unittest.main()
