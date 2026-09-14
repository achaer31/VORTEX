"""Synthetic feature chronology tests; never use fabricated bars as P/L evidence."""
import unittest

import numpy as np
import pandas as pd

from vortex_v02.engines import (build_signals, closed_asof, confirmed_pivots,
                               indicators, luna_scores, mode_from_scores, rsi, validate_frame)


def synthetic_frame(count=320, freq="5min"):
    index = pd.date_range("2026-01-01", periods=count, freq=freq, tz="UTC")
    close = 4000 + np.arange(count) * .15 + np.sin(np.arange(count) * .7) * 2
    return pd.DataFrame({"open": close - .1, "high": close + 1, "low": close - 1,
                         "close": close, "tick_volume": 100, "spread_points": 100}, index=index)


class CausalFeatureTests(unittest.TestCase):
    def test_future_values_do_not_revise_old_indicators(self):
        frame = synthetic_frame()
        original = indicators(frame)
        changed = frame.copy()
        changed.loc[changed.index[250]:, ["open", "high", "low", "close"]] += 1000
        pd.testing.assert_frame_equal(original.iloc[:250], indicators(changed).iloc[:250])

    def test_pivot_publishes_only_after_two_right_bars(self):
        frame = synthetic_frame(8)
        frame.high = [5, 6, 10, 7, 6, 5, 4, 3]
        frame.low = [2, 1, .5, 1, 2, 1, .8, 1]
        pivots = confirmed_pivots(frame)
        self.assertTrue(pivots.pivot_high_confirmed.iloc[:4].isna().all())
        self.assertEqual(pivots.pivot_high_confirmed.iloc[4], 10)
        self.assertEqual(pivots.pivot_low_confirmed.iloc[4], .5)
        self.assertTrue(pivots.swing_high.iloc[:4].isna().all())

    def test_tied_extremes_do_not_create_ambiguous_pivots(self):
        frame = synthetic_frame(6)
        frame.high = [5, 6, 10, 10, 6, 5]
        self.assertTrue(confirmed_pivots(frame).pivot_high_confirmed.isna().all())

    def test_flat_monotonic_rsi_after_warmup(self):
        for values, expected in (([10] * 40, 50), (list(range(1, 41)), 100), (list(range(40, 0, -1)), 0)):
            result = rsi(pd.Series(values, dtype=float))
            self.assertTrue(result.iloc[:14].isna().all())
            self.assertTrue(result.iloc[14:].eq(expected).all())

    def test_htf_not_visible_before_close_and_stale_after_one_period(self):
        index = pd.DatetimeIndex(["2026-01-01T00:00:00Z"])
        h1 = pd.DataFrame({"value": [17]}, index=index)
        decisions = pd.DatetimeIndex(["2026-01-01T00:55:00Z", "2026-01-01T01:00:00Z", "2026-01-01T02:00:00Z"])
        joined = closed_asof(h1, "H1", decisions)
        self.assertTrue(pd.isna(joined.value.iloc[0]))
        self.assertEqual(joined.value.iloc[1], 17)
        self.assertEqual(joined.fresh.tolist(), [False, True, False])

    def test_bad_clock_duplicates_or_ohlc_are_rejected(self):
        frames = []
        naive = synthetic_frame(); naive.index = naive.index.tz_localize(None); frames.append(naive)
        duplicate = synthetic_frame(); duplicate.index = pd.DatetimeIndex([duplicate.index[0]] * len(duplicate)); frames.append(duplicate)
        prices = synthetic_frame(); prices.loc[prices.index[5], "low"] = 10000; frames.append(prices)
        for frame in frames:
            with self.subTest(case=len(frame)), self.assertRaises(ValueError):
                validate_frame(frame, "M5")


def synthetic_inputs():
    """Synthetic synchronized clocks, not a real four-timeframe market dataset."""
    end = pd.Timestamp("2026-03-15T12:00:00Z")
    frames = {}
    for tf, freq in (("M5", "5min"), ("M15", "15min"), ("H1", "h"), ("H4", "4h")):
        index = pd.date_range(end=end, periods=321, freq=freq)[:-1]
        phase = (index.asi8 / 1e9 / 300) % 100000
        close = 4000 + phase * .0005 + np.sin(phase * .12) * 3
        frames[tf] = pd.DataFrame({"open": close - .05, "high": close + 5,
            "low": close - 5, "close": close, "tick_volume": 100,
            "spread_points": 100}, index=index)
    external = pd.DataFrame(index=frames["M5"].index + pd.Timedelta(minutes=5))
    external["news_valid"] = True; external["news_blocked"] = False
    external["macro_valid"] = True; external["dxy_roc"] = -.2; external["us10y_change"] = -.05
    external["session"] = "LONDON"; external["session_ideal"] = True
    for session in ("asia", "london", "newyork"):
        external[session + "_high"] = np.nan; external[session + "_low"] = np.nan
    return frames, external


class EngineIntegrationTests(unittest.TestCase):
    def test_missing_macro_or_calendar_blocks_even_with_other_valid_inputs(self):
        for key in ("macro_valid", "news_valid"):
            frames, external = synthetic_inputs()
            external[key] = False
            result = build_signals(frames, external)
            self.assertTrue(result.atlas.isna().all())
            self.assertTrue(result.signal.eq(0).all())
            self.assertTrue(result["mode"].eq("FROZEN").all())

    def test_missing_external_rows_are_invalid_not_neutral(self):
        frames, external = synthetic_inputs()
        result = build_signals(frames, external.iloc[:10])
        self.assertTrue(result.atlas.iloc[10:].isna().all())
        self.assertTrue(result.news_blocked.iloc[10:].all())

    def test_schema_ready_features_and_consensus_quality_not_direction_vote(self):
        frames, external = synthetic_inputs()
        result = build_signals(frames, external)
        self.assertTrue(result.index.equals(frames["M5"].index))
        self.assertTrue(result.ready.iloc[-1])
        self.assertAlmostEqual(result.atlas.iloc[-1], 100)
        self.assertTrue({"stop_long", "stop_short", "swing_low", "swing_high", "atr", "news_blocked", "execution_valid"}.issubset(result))
        row = result.iloc[-1]
        directional = (.2 * row.orion + .15 * row.vortex + .2 * row.nova + .2 * row.luna + .15 * row.atlas) / .9
        self.assertAlmostEqual(row.consensus, directional * (.9 + .1 * row.kira / 100))

    def test_new_future_htf_price_or_external_data_cannot_change_past_decisions(self):
        frames, external = synthetic_inputs()
        cutoff = frames["M5"].index[-40]
        baseline = build_signals(frames, external)
        for tf, minutes in (("M5", 5), ("M15", 15), ("H1", 60), ("H4", 240)):
            future = frames[tf].index + pd.Timedelta(minutes=minutes) > cutoff
            frames[tf].loc[future, ["open", "high", "low", "close"]] += 2000
        external.loc[external.index > cutoff, ["dxy_roc", "us10y_change"]] = 900
        changed = build_signals(frames, external)
        past = baseline.decision_time <= cutoff
        pd.testing.assert_frame_equal(baseline.loc[past], changed.loc[past])

    def test_stale_h4_never_appears_ready(self):
        frames, external = synthetic_inputs()
        frames["H4"] = frames["H4"].iloc[:-3]
        result = build_signals(frames, external)
        self.assertFalse(result.ready.iloc[-1])
        self.assertTrue(pd.isna(result.orion.iloc[-1]))

    def test_news_or_unknown_spread_blocks_modes(self):
        frames, external = synthetic_inputs()
        external["news_blocked"] = True
        result = build_signals(frames, external)
        self.assertFalse(result.ready.any())
        external["news_blocked"] = False
        frames["M5"]["spread_points"] = 0
        result = build_signals(frames, external)
        self.assertFalse(result.execution_valid.any())
        self.assertTrue(result.atlas.isna().all())

    def test_extreme_requires_all_directional_votes_quality_alignment_and_session(self):
        scores = {k: 90.0 for k in ("orion", "vortex", "nova", "luna", "atlas")}
        scores.update(kira=75, consensus=87.75)
        self.assertEqual(mode_from_scores(scores, 1, 1, True, True), ("EXTREME", 1))
        self.assertEqual(mode_from_scores(scores, 1, 1, False, True)[0], "AGGRESSIVE")
        self.assertEqual(mode_from_scores(scores, 1, -1, True, True)[0], "NORMAL")
        scores["atlas"] = -50
        self.assertEqual(mode_from_scores(scores, 1, 1, True, True)[0], "FROZEN")
        scores["atlas"] = 90; scores["kira"] = 90
        self.assertEqual(mode_from_scores(scores, 1, 1, True, True)[0], "FROZEN")

    def test_confirmed_sweep_decays_three_bars_and_both_sides_conflict(self):
        frame = pd.DataFrame({"open": [100]*5, "high": [101]*5, "low": [89,99,99,99,99], "close": [100]*5}, index=pd.date_range("2026-01-01", periods=5, freq="5min", tz="UTC"))
        features = pd.DataFrame({"prior20_high": 110, "prior20_low": 90}, index=frame.index)
        external = pd.DataFrame(np.nan, index=frame.index, columns=[s + "_" + side for s in ("asia","london","newyork") for side in ("high","low")])
        scores, _ = luna_scores(frame, features, pd.Series(1., index=frame.index), external)
        self.assertEqual(scores.tolist(), [85, 80, 75, 70, 0])
        frame.loc[frame.index[0], "high"] = 111
        scores, reasons = luna_scores(frame, features, pd.Series(1., index=frame.index), external)
        self.assertEqual(scores.iloc[0], 0)
        self.assertEqual(reasons.iloc[0], "conflicting_sweeps")


if __name__ == "__main__":
    unittest.main()
