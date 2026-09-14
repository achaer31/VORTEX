"""Synthetic fixtures only: these tests contain no market or profit evidence."""

import unittest

import numpy as np
import pandas as pd

from vortex_xau.signals import (
    TIME_BASIS, build_signals, calculate_features, rsi_wilder, validate_frame,
)


def synthetic_frame(timeframe, count):
    """Artificial steadily rising quotes, explicitly not real trading data."""
    minutes = {"M5": 5, "M15": 15, "H1": 60}[timeframe]
    index = pd.date_range("2025-01-01", periods=count, freq=f"{minutes}min",
                          name="bar_open_server")
    close = 2000 + np.arange(count) * minutes * 0.01
    return pd.DataFrame({
        "timezone": TIME_BASIS, "symbol": "XAUUSD", "timeframe": timeframe,
        "open": close - 0.25, "high": close + 0.5, "low": close - 0.5,
        "close": close, "tick_volume": 100, "spread_points": 180, "real_volume": 0,
    }, index=index)


class SignalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m5 = synthetic_frame("M5", 241 * 12)
        cls.m15 = synthetic_frame("M15", 241 * 4)
        cls.h1 = synthetic_frame("H1", 241)
        cls.signals = build_signals(cls.m5, cls.m15, cls.h1)

    def test_htf_only_available_when_closed(self):
        start = self.h1.index[0]
        just_before = start + pd.Timedelta(hours=200, minutes=-10)
        at_boundary = start + pd.Timedelta(hours=200, minutes=-5)
        before = self.signals.loc[just_before]
        at = self.signals.loc[at_boundary]
        self.assertEqual(before.htf_h1_open, start + pd.Timedelta(hours=198))
        self.assertEqual(at.htf_h1_open, start + pd.Timedelta(hours=199))
        for tf in ("h1", "m15"):
            rows = self.signals.dropna(subset=[f"htf_{tf}_close"])
            self.assertTrue((rows[f"htf_{tf}_close"] <= rows.decision_time).all())

    def test_future_htf_change_does_not_change_prior_signals(self):
        modified = self.h1.copy()
        future = modified.index[200]
        modified.loc[future, ["open", "high", "low", "close"]] = [3500, 3600, 3400, 3550]
        alternate = build_signals(self.m5, self.m15, modified)
        before_future_close = self.signals.decision_time < future + pd.Timedelta(hours=1)
        columns = ["orion", "vortex", "nova", "luna", "kira", "atlas", "consensus", "signal", "ready"]
        pd.testing.assert_frame_equal(self.signals.loc[before_future_close, columns],
                                      alternate.loc[before_future_close, columns])

    def test_warmup_requires_200_closed_h1_bars(self):
        earliest = self.h1.index[0] + pd.Timedelta(hours=200)
        early = self.signals.decision_time < earliest
        self.assertFalse(self.signals.loc[early, "ready"].any())
        self.assertTrue(self.signals.loc[early, "signal"].eq(0).all())
        self.assertTrue(self.signals.loc[early, "consensus"].isna().all())
        first_ready = self.signals.loc[self.signals.ready].iloc[0]
        self.assertEqual(first_ready.decision_time, earliest)

    def test_rsi_flat_up_and_down_have_defined_results(self):
        scenarios = [(np.full(40, 100.0), 50.0),
                     (np.arange(40, dtype=float) + 100, 100.0),
                     (200 - np.arange(40, dtype=float), 0.0)]
        for close, expected in scenarios:
            with self.subTest(expected=expected):
                rsi = rsi_wilder(pd.Series(close))
                self.assertTrue(rsi.iloc[:14].isna().all())
                self.assertTrue(rsi.iloc[14:].eq(expected).all())

    def test_prior_range_and_volume_exclude_current_bar(self):
        frame = synthetic_frame("M5", 25)
        baseline = calculate_features(frame)
        changed = frame.copy()
        changed.loc[changed.index[20], ["high", "low", "tick_volume"]] = [10000, 1, 1000000]
        features = calculate_features(changed)
        previous = frame.iloc[:20]
        self.assertEqual(features.iloc[20].prior20_high, previous.high.max())
        self.assertEqual(features.iloc[20].prior20_low, previous.low.min())
        self.assertEqual(features.iloc[20].prior20_tick_volume_mean, previous.tick_volume.mean())
        for name in ("prior20_high", "prior20_low", "prior20_tick_volume_mean"):
            self.assertEqual(features.iloc[20][name], baseline.iloc[20][name])
        self.assertEqual(features.iloc[21].prior20_high, 10000)
        self.assertEqual(features.iloc[21].prior20_low, 1)

    def test_bad_identity_order_and_ohlc_are_rejected(self):
        for flaw in ("identity", "duplicate", "reversed", "ohlc", "timezone"):
            bad = synthetic_frame("M5", 25)
            if flaw == "identity":
                bad.iloc[0, bad.columns.get_loc("symbol")] = "EURUSD"
            elif flaw == "duplicate":
                bad.index = pd.DatetimeIndex([bad.index[0], *bad.index[:-1]])
            elif flaw == "reversed":
                bad = bad.iloc[::-1]
            elif flaw == "ohlc":
                bad.iloc[0, bad.columns.get_loc("high")] = 1
            else:
                bad["timezone"] = "UTC"
            with self.subTest(flaw=flaw), self.assertRaises(ValueError):
                validate_frame(bad, "M5")


if __name__ == "__main__":
    unittest.main()
