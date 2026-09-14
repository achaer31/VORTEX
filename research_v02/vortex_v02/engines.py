"""Causal VORTEX-XAU-v0.2 engine features; no broker or execution operations.

Every input bar is labelled by its UTC open. Its values only become available
at open + timeframe; higher-timeframe joins use those close times.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import VERSION
PERIODS = {"M5": 5, "M15": 15, "H1": 60, "H4": 240}
WEIGHTS = {"orion": .20, "vortex": .15, "nova": .20,
           "luna": .20, "kira": .10, "atlas": .15}


def validate_frame(frame: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    if timeframe not in PERIODS or not isinstance(frame, pd.DataFrame) or frame.empty:
        raise ValueError("nonempty known-timeframe DataFrame required")
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise ValueError("bar-open index must be UTC-aware")
    if frame.index.hasnans or not frame.index.is_unique or not frame.index.is_monotonic_increasing:
        raise ValueError("bar-open index must be ascending, unique and nonmissing")
    if frame.columns.duplicated().any():
        raise ValueError("duplicate columns")
    columns = ["open", "high", "low", "close", "tick_volume", "spread_points"]
    if not set(columns).issubset(frame):
        raise ValueError("OHLC, tick_volume and spread_points are required")
    result = frame.copy()
    result.index = result.index.tz_convert("UTC")
    for key in columns:
        result[key] = pd.to_numeric(result[key], errors="raise")
        if not np.isfinite(result[key].to_numpy(dtype=float)).all():
            raise ValueError("nonfinite market observation")
    if (result[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError("nonpositive price")
    if ((result.low > result[["open", "close"]].min(axis=1)) |
            (result.high < result[["open", "close"]].max(axis=1))).any():
        raise ValueError("invalid OHLC")
    if (result[["tick_volume", "spread_points"]] < 0).any().any():
        raise ValueError("negative quote volume/spread")
    if "symbol" in result and not result.symbol.eq("XAUUSD").all():
        raise ValueError("exact XAUUSD required")
    return result


def wilder(values: pd.Series, period: int = 14) -> pd.Series:
    output = pd.Series(np.nan, index=values.index, dtype=float)
    source = values.astype(float)
    valid = np.flatnonzero(source.notna().to_numpy())
    if len(valid) < period:
        return output
    start = int(valid[0])
    if not np.isfinite(source.iloc[start:].to_numpy()).all():
        raise ValueError("internal missing/nonfinite Wilder observations")
    seed = start + period - 1
    recursion = source.iloc[seed:].copy()
    recursion.iloc[0] = source.iloc[start:seed + 1].mean()
    output.iloc[seed:] = recursion.ewm(alpha=1 / period, adjust=False).mean().to_numpy()
    return output


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    change = close.diff()
    gain, loss = wilder(change.clip(lower=0), period), wilder((-change).clip(lower=0), period)
    result = 100 - 100 / (1 + gain / loss)
    return result.mask((gain == 0) & (loss == 0), 50).mask((gain > 0) & (loss == 0), 100).mask((gain == 0) & (loss > 0), 0)


def confirmed_pivots(frame: pd.DataFrame) -> pd.DataFrame:
    """Strict 2-left/2-right pivot first published on the second right bar.

    A tied extreme is not a pivot. The returned level is forward-filled only
    after confirmation, never at the original centre bar.
    """
    high, low = frame.high, frame.low
    candidate_high, candidate_low = high.shift(2), low.shift(2)
    high_ok = pd.Series(True, index=frame.index)
    low_ok = pd.Series(True, index=frame.index)
    for shift in (0, 1, 3, 4):
        high_ok &= candidate_high > high.shift(shift)
        low_ok &= candidate_low < low.shift(shift)
    highs = candidate_high.where(high_ok)
    lows = candidate_low.where(low_ok)
    return pd.DataFrame({"pivot_high_confirmed": highs, "pivot_low_confirmed": lows,
                         "swing_high": highs.ffill(), "swing_low": lows.ffill()}, index=frame.index)


def indicators(frame: pd.DataFrame) -> pd.DataFrame:
    close = frame.close
    result = confirmed_pivots(frame)
    for period in (20, 50, 200):
        result[f"ema{period}"] = close.ewm(span=period, adjust=False, min_periods=period).mean()
    previous = close.shift(1)
    tr = pd.concat([frame.high - frame.low, (frame.high - previous).abs(),
                    (frame.low - previous).abs()], axis=1).max(axis=1)
    result["atr"] = wilder(tr)
    result["rsi"] = rsi(close)
    result["roc"] = (close / close.shift(3) - 1) * 100
    result["roc_price"] = close - close.shift(3)
    fast = close.ewm(span=12, adjust=False, min_periods=12).mean()
    slow = close.ewm(span=26, adjust=False, min_periods=26).mean()
    result["macd"] = fast - slow
    result["macd_signal"] = result.macd.ewm(span=9, adjust=False, min_periods=9).mean()
    result["macd_hist"] = result.macd - result.macd_signal
    result["prior20_high"] = frame.high.shift(1).rolling(20, min_periods=20).max()
    result["prior20_low"] = frame.low.shift(1).rolling(20, min_periods=20).min()
    result["prior20_volume"] = frame.tick_volume.shift(1).rolling(20, min_periods=20).mean()
    up = (close > result.ema20) & (result.ema20 > result.ema50) & (result.ema50 > result.ema200)
    down = (close < result.ema20) & (result.ema20 < result.ema50) & (result.ema50 < result.ema200)
    result["alignment"] = np.select([up, down], [1, -1], default=0)
    result["atr_baseline"] = result.atr.shift(1).rolling(50, min_periods=50).median()
    stack = (np.sign(close - result.ema20) + np.sign(result.ema20 - result.ema50) +
             np.sign(result.ema50 - result.ema200)) / 3 * 100
    slope = (100 * (result.ema20 - result.ema20.shift(5)) / result.atr.where(result.atr > 0)).clip(-100, 100)
    result["trend_score"] = .75 * stack + .25 * slope
    return result


def closed_asof(features: pd.DataFrame, timeframe: str, decisions: pd.DatetimeIndex) -> pd.DataFrame:
    right = features.copy()
    right["closed_at"] = right.index + pd.Timedelta(minutes=PERIODS[timeframe])
    left = pd.DataFrame({"decision_time": decisions})
    joined = pd.merge_asof(left, right.reset_index(drop=True), left_on="decision_time",
                           right_on="closed_at", direction="backward", allow_exact_matches=True)
    joined.index = decisions
    age = joined.decision_time - joined.closed_at
    joined["fresh"] = age.ge(pd.Timedelta(0)) & age.lt(pd.Timedelta(minutes=PERIODS[timeframe]))
    return joined


def nova_scores(frame, features, atr):
    """M5 confirmed structures, one breakout impulse or retest bonus per bar."""
    scores, reasons = [], []
    highs, lows = [], []
    last_break = None
    for i in range(len(frame)):
        bar, f, a = frame.iloc[i], features.iloc[i], atr.iloc[i]
        prior_high = highs[-1] if highs else np.nan
        prior_low = lows[-1] if lows else np.nan
        if np.isfinite(f.pivot_high_confirmed):
            highs.append(f.pivot_high_confirmed)
            highs = highs[-2:]
        if np.isfinite(f.pivot_low_confirmed):
            lows.append(f.pivot_low_confirmed)
            lows = lows[-2:]
        if len(highs) < 2 or len(lows) < 2 or not np.isfinite(a) or a <= 0:
            scores.append(np.nan); reasons.append("structure_warmup"); continue
        structure = (1 if highs[-1] > highs[-2] and lows[-1] > lows[-2] else
                     -1 if highs[-1] < highs[-2] and lows[-1] < lows[-2] else 0)
        previous = frame.close.iloc[i - 1] if i else np.nan
        bullish = np.isfinite(prior_high) and previous <= prior_high + .05 * a < bar.close
        bearish = np.isfinite(prior_low) and previous >= prior_low - .05 * a > bar.close
        broken = 1 if bullish and not bearish else -1 if bearish and not bullish else 0
        if bullish and bearish:
            last_break = None
            scores.append(0.0); reasons.append("conflicting_breaks"); continue
        if broken:
            last_break = (i, broken, prior_high if broken == 1 else prior_low)
        retest = False
        if last_break is not None:
            start, side, level = last_break
            touched = abs((bar.low if side == 1 else bar.high) - level) <= .15 * a
            retest = (1 <= i - start <= 6 and touched and side * (bar.close - level) > 0 and structure == side)
        if broken and broken != structure:
            value, reason = 50.0 * broken, "break_without_aligned_structure"
        elif structure and (broken == structure or retest):
            value, reason = 100.0 * structure, "aligned_break" if broken else "aligned_retest"
        else:
            value, reason = 70.0 * structure, "ordered_structure" if structure else "unresolved_structure"
        scores.append(value); reasons.append(reason)
    return pd.Series(scores, index=frame.index), pd.Series(reasons, index=frame.index)


def luna_scores(frame, features, atr, external):
    scores, reasons = [], []
    sweep = None
    for i in range(len(frame)):
        bar, f, a = frame.iloc[i], features.iloc[i], atr.iloc[i]
        if not all(np.isfinite(x) for x in (a, f.prior20_high, f.prior20_low)) or a <= 0:
            scores.append(np.nan); reasons.append("sweep_warmup"); continue
        highs, lows = [f.prior20_high], [f.prior20_low]
        for session in ("asia", "london", "newyork"):
            high, low = external[f"{session}_high"].iloc[i], external[f"{session}_low"].iloc[i]
            if np.isfinite(high): highs.append(high)
            if np.isfinite(low): lows.append(low)
        body = abs(bar.close - bar.open)
        lower_wick = min(bar.open, bar.close) - bar.low
        upper_wick = bar.high - max(bar.open, bar.close)
        bullish = lower_wick >= body and any(bar.low <= level - .05 * a and bar.close > level for level in lows)
        bearish = upper_wick >= body and any(bar.high >= level + .05 * a and bar.close < level for level in highs)
        if bullish and bearish:
            sweep = None
            value, reason = 0.0, "conflicting_sweeps"
        elif bullish or bearish:
            sweep = (i, 1 if bullish else -1)
            value, reason = 85.0 * sweep[1], "confirmed_sweep"
        elif sweep is not None and i - sweep[0] <= 3:
            value, reason = sweep[1] * (85 - 5 * (i - sweep[0])), "decaying_sweep"
        else:
            value, reason = 0.0, "no_sweep"
        scores.append(value); reasons.append(reason)
    return pd.Series(scores, index=frame.index), pd.Series(reasons, index=frame.index)


def mode_from_scores(scores, h1_alignment, h4_alignment, ideal, eligible):
    """Pure frozen thresholds. KIRA is quality, never a directional vote."""
    if not eligible or not all(np.isfinite(scores.get(k, np.nan)) for k in (*WEIGHTS, "consensus")):
        return "FROZEN", 0
    consensus = scores["consensus"]
    direction = int(np.sign(consensus))
    if direction == 0:
        return "FROZEN", 0
    o, v, n, l, a = (scores[k] * direction for k in ("orion", "vortex", "nova", "luna", "atlas"))
    k, strength = scores["kira"], abs(consensus)
    aligned = h1_alignment == h4_alignment == direction
    normal = strength >= 72 and o >= 70 and v >= 55 and n >= 75 and l >= 55 and 45 <= k < 85 and a >= -35
    aggressive = normal and strength >= 78 and o >= 75 and n >= 80 and v >= 65 and l >= 70 and a >= 50 and aligned
    extreme = (aggressive and strength >= 82 and o >= 80 and v >= 70 and n >= 80 and
               l >= 80 and a >= 70 and 60 <= k <= 84 and aligned and bool(ideal))
    mode = "EXTREME" if extreme else "AGGRESSIVE" if aggressive else "NORMAL" if normal else "FROZEN"
    return mode, direction if mode != "FROZEN" else 0


def build_signals(frames: dict[str, pd.DataFrame], external: pd.DataFrame) -> pd.DataFrame:
    """Return completed-M5 decisions; execution consumes the previous row only.

    External rows must be indexed by M5 decision time in UTC, not candle open.
    Missing mandatory point-in-time data makes ATLAS NaN and all modes FROZEN.
    Stops are candidate structural levels; sizing remains an independent gate.
    """
    data = {tf: validate_frame(frames[tf], tf) for tf in PERIODS}
    base = data["M5"]
    decisions = base.index + pd.Timedelta(minutes=5)
    if not isinstance(external, pd.DataFrame) or not isinstance(external.index, pd.DatetimeIndex) or external.index.tz is None:
        raise ValueError("external context must have UTC-aware decision-time index")
    if not external.index.is_unique or not external.index.is_monotonic_increasing or external.index.hasnans:
        raise ValueError("external context must be unique, ascending and nonmissing")
    ext = external.copy()
    ext.index = ext.index.tz_convert("UTC")
    ext = ext.reindex(decisions)
    ext.index = base.index
    for key in ("news_valid", "news_blocked", "macro_valid", "session", "session_ideal", "next_news"):
        if key not in ext:
            ext[key] = np.nan
    for key in ("dxy_roc", "us10y_change", "asia_high", "asia_low", "london_high", "london_low", "newyork_high", "newyork_low"):
        ext[key] = pd.to_numeric(ext[key], errors="coerce") if key in ext else np.nan
    features = {tf: indicators(frame) for tf, frame in data.items()}
    contexts = {tf: closed_asof(features[tf], tf, decisions) for tf in ("M15", "H1", "H4")}
    for context in contexts.values():
        context.index = base.index
    m5, m15, h1, h4 = features["M5"], contexts["M15"], contexts["H1"], contexts["H4"]
    result = base.copy()
    result["decision_time"] = decisions
    result["atr"] = m15.atr
    result["h1_alignment"], result["h4_alignment"] = h1.alignment, h4.alignment
    for tf, context in contexts.items():
        result[f"{tf.lower()}_closed_at"] = context.closed_at
        result[f"{tf.lower()}_fresh"] = context.fresh
    context_fresh = m15.fresh & h1.fresh & h4.fresh
    trend_ready = (m15.trend_score.notna() & h1.trend_score.notna() & h4.trend_score.notna() & context_fresh)
    result["orion"] = (.20 * m15.trend_score + .40 * h1.trend_score + .40 * h4.trend_score).where(trend_ready)
    result["orion_reason"] = np.where(trend_ready, "weighted_ema_stack_and_slope", "trend_warmup")
    result["vortex"] = (.4 * (4 * (m5.rsi - 50)).clip(-100, 100) +
        .35 * (400 * m5.macd_hist / m5.atr.where(m5.atr > 0)).clip(-100, 100) +
        .25 * (50 * m5.roc_price / m5.atr.where(m5.atr > 0)).clip(-100, 100))
    result["vortex_reason"] = np.where(result.vortex.notna(), "rsi_macd_roc3", "momentum_warmup")
    result["nova"], result["nova_reason"] = nova_scores(base, m5, m15.atr)
    result["luna"], result["luna_reason"] = luna_scores(base, m5, m15.atr, ext)
    for module in ("nova", "luna"):
        result.loc[~m15.fresh, module] = np.nan
        result.loc[~m15.fresh, f"{module}_reason"] = "m15_context_stale"
    ratio = m15.atr / m15.atr_baseline.where(m15.atr_baseline > 0)
    # Price denominator is the last closed M15 close, not the current M5 close.
    price_context = closed_asof(data["M15"][["close"]], "M15", decisions)
    price_context.index = base.index
    relative = m15.atr / price_context.close
    volatility_valid = np.isfinite(ratio) & np.isfinite(relative) & m15.atr.gt(0) & m15.atr_baseline.gt(0) & m15.fresh
    # Wild conditions take precedence over quiet conditions when predicates overlap.
    quality = np.select([ratio.ge(1.8) | relative.gt(.01), relative.lt(.00025) | ratio.lt(.5), ratio.lt(.8)], [90., 20., 50.], default=75.)
    result["kira"] = pd.Series(quality, index=base.index).where(volatility_valid)
    result["kira_reason"] = np.where(~volatility_valid, "volatility_baseline_invalid",
        np.where(result.kira.ge(85), "too_wild", np.where(result.kira.lt(45), "too_quiet", "volatility_quality")))
    spread = base.spread_points * .001
    execution_known = np.isfinite(spread) & spread.gt(0) & np.isfinite(m15.atr) & m15.atr.gt(0) & m15.fresh
    result["execution_valid"] = execution_known & spread.le(np.minimum(.60, .10 * m15.atr))
    news_valid = ext.news_valid.eq(True)
    macro_valid = ext.macro_valid.eq(True) & np.isfinite(ext.dxy_roc) & np.isfinite(ext.us10y_change)
    session_valid = ext.session.isin(["ASIA", "LONDON", "NEWYORK", "LONDON_NEWYORK", "OTHER"])
    atlas_valid = news_valid & macro_valid & session_valid & execution_known
    result["atlas"] = (.6 * (-100 * ext.dxy_roc / .20).clip(-100, 100) +
                       .4 * (-100 * ext.us10y_change / .05).clip(-100, 100)).where(atlas_valid)
    result["atlas_reason"] = np.select([~news_valid, ~macro_valid, ~session_valid, ~execution_known,
        ext.news_blocked.ne(False), ~result.execution_valid],
        ["calendar_invalid", "macro_invalid", "session_invalid", "execution_input_invalid", "news_blocked", "spread_blocked"], default="macro_context_valid")
    result["news_blocked"] = ~news_valid | ext.news_blocked.ne(False)
    result["news_valid"], result["macro_valid"] = news_valid, macro_valid
    result["session"], result["session_ideal"], result["next_news"] = ext.session, ext.session_ideal.eq(True), ext.next_news
    directions = ["orion", "vortex", "nova", "luna", "atlas"]
    result[directions] = result[directions].clip(-100, 100)
    raw = sum(result[key] * WEIGHTS[key] for key in directions) / .90
    result["consensus"] = (raw * (.90 + .10 * result.kira / 100)).clip(-100, 100)
    finite_scores = np.isfinite(result[[*WEIGHTS, "consensus"]]).all(axis=1)
    result["ready"] = (finite_scores & context_fresh & result.execution_valid & ~result.news_blocked & atlas_valid)
    modes = [mode_from_scores(row, row.h1_alignment, row.h4_alignment, row.session_ideal, row.ready)
             for _, row in result.iterrows()]
    result["mode"] = [m[0] for m in modes]
    result["signal"] = np.array([m[1] for m in modes], dtype=np.int8)
    result["swing_low"], result["swing_high"] = m5.swing_low, m5.swing_high
    long_distance = np.maximum(1.4 * result.atr, base.close - m5.swing_low + .1 * result.atr)
    short_distance = np.maximum(1.4 * result.atr, m5.swing_high - base.close + .1 * result.atr)
    result["stop_long"] = (base.close - long_distance).where(
        m5.swing_low.lt(base.close) & long_distance.ge(.35 * result.atr) & long_distance.le(2.2 * result.atr))
    result["stop_short"] = (base.close + short_distance).where(
        m5.swing_high.gt(base.close) & short_distance.ge(.35 * result.atr) & short_distance.le(2.2 * result.atr))
    result.attrs.update(version=VERSION, timeframe="M5", time_basis="UTC_exness_GMT0_assumption",
                        signal_available_at="decision_time", status="unvalidated_backtest_paper_only")
    return result
