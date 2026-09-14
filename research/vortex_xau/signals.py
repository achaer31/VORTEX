"""VORTEX-XAU-v0.1: a NEW research hypothesis, with no execution capabilities.

All datetimes are timezone-naive broker server clock values, with unknown UTC
offset. Signals belong to M5 close; execution must occur no earlier than the
next bar open. See SIGNALS.md for indicator seeds and all research assumptions.
"""

from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd


VERSION = "VORTEX-XAU-v0.1"
TIME_BASIS = "broker_server_unknown_offset"
PERIOD_MINUTES = {"M5": 5, "M15": 15, "H1": 60}
WEIGHTS = {"orion": 0.22, "vortex": 0.18, "nova": 0.20,
           "luna": 0.15, "kira": 0.10, "atlas": 0.15}
PRICE_COLUMNS = ["open", "high", "low", "close"]
COUNT_COLUMNS = ["tick_volume", "spread_points", "real_volume"]
REQUIRED_COLUMNS = ["timezone", "symbol", "timeframe", *PRICE_COLUMNS,
                    *COUNT_COLUMNS]


def validate_frame(frame: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Return a normalized copy; reject malformed, unsorted or mixed exports.

    Accepts exporter columns including bar_open_server, or a naive DatetimeIndex
    plus the remaining exporter columns. Never sorts, deduplicates, fills gaps,
    or translates the server clock to UTC.
    """
    if timeframe not in PERIOD_MINUTES:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise ValueError(f"{timeframe}: a nonempty DataFrame is required")
    if frame.columns.duplicated().any():
        raise ValueError(f"{timeframe}: duplicate column names")
    result = frame.copy()
    missing = set(REQUIRED_COLUMNS) - set(result.columns)
    if missing:
        raise ValueError(f"{timeframe}: missing columns {sorted(missing)}")
    if "bar_open_server" in result:
        values = result.pop("bar_open_server")
        if not values.map(lambda item: isinstance(item, str)).all():
            raise ValueError(f"{timeframe}: timestamps must be ISO server-clock strings")
        if not values.str.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}").all():
            raise ValueError(f"{timeframe}: timestamps need YYYY-MM-DDTHH:MM:SS without offset")
        try:
            index = pd.DatetimeIndex(pd.to_datetime(values, format="%Y-%m-%dT%H:%M:%S", errors="raise"))
        except (ValueError, TypeError) as error:
            raise ValueError(f"{timeframe}: invalid timestamp") from error
    elif isinstance(result.index, pd.DatetimeIndex):
        index = result.index
    else:
        raise ValueError(f"{timeframe}: missing bar_open_server or DatetimeIndex")
    if index.tz is not None or index.hasnans:
        raise ValueError(f"{timeframe}: timestamps must be valid naive server times")
    if not index.is_unique or not index.is_monotonic_increasing:
        raise ValueError(f"{timeframe}: timestamps must be unique and strictly ascending")
    result.index = index.rename("bar_open_server")
    for column, expected in (("symbol", "XAUUSD"), ("timeframe", timeframe),
                             ("timezone", TIME_BASIS)):
        if not result[column].eq(expected).all():
            raise ValueError(f"{timeframe}: every {column} must equal {expected!r}")
    for column in PRICE_COLUMNS + COUNT_COLUMNS:
        try:
            numeric = pd.to_numeric(result[column], errors="raise")
        except (ValueError, TypeError) as error:
            raise ValueError(f"{timeframe}: nonnumeric {column}") from error
        if not np.isfinite(numeric.to_numpy(dtype=float)).all():
            raise ValueError(f"{timeframe}: nonfinite {column}")
        result[column] = numeric
    if (result[PRICE_COLUMNS] <= 0).any().any():
        raise ValueError(f"{timeframe}: prices must be positive")
    if ((result.low > result[["open", "close"]].min(axis=1)) |
            (result.high < result[["open", "close"]].max(axis=1))).any():
        raise ValueError(f"{timeframe}: invalid OHLC relationship")
    for column in COUNT_COLUMNS:
        values = result[column].to_numpy(dtype=float)
        if ((values < 0) | (values != np.floor(values))).any():
            raise ValueError(f"{timeframe}: {column} must be nonnegative integers")
    result.attrs.update(version=VERSION, timezone=TIME_BASIS, timeframe=timeframe)
    return result


def load_exporter_data(run_dir: str | Path) -> dict[str, pd.DataFrame]:
    """Load XAUUSD_M5.csv, XAUUSD_M15.csv and XAUUSD_H1.csv from one run.

    This checks the CSV contents, not historical completeness or broker identity.
    No manifest is required and no account/terminal connection is attempted.
    """
    root = Path(run_dir)
    return {
        timeframe: validate_frame(
            pd.read_csv(root / f"XAUUSD_{timeframe}.csv", encoding="utf-8-sig"), timeframe
        )
        for timeframe in PERIOD_MINUTES
    }


def _wilder_mean(values: pd.Series, period: int = 14) -> pd.Series:
    """SMA seed of the first period finite observations, then alpha=1/period.

    Leading NaNs are allowed (RSI differences); later missing values are rejected
    rather than silently skipped. The seed is only available at its last sample.
    """
    if period < 1:
        raise ValueError("period must be positive")
    source = values.astype(float)
    output = pd.Series(np.nan, index=source.index, dtype=float)
    present = np.flatnonzero(source.notna().to_numpy())
    if len(present) < period:
        return output
    start = int(present[0])
    if not np.isfinite(source.iloc[start:].to_numpy()).all():
        raise ValueError("Wilder smoothing does not accept internal missing/nonfinite data")
    seed_index = start + period - 1
    seed = float(source.iloc[start:seed_index + 1].mean())
    recursive = source.iloc[seed_index:].copy()
    recursive.iloc[0] = seed
    output.iloc[seed_index:] = recursive.ewm(alpha=1 / period, adjust=False).mean().to_numpy()
    return output


def rsi_wilder(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder RSI; flat=50, gains-only=100, losses-only=0 after warm-up."""
    change = close.astype(float).diff()
    gain = _wilder_mean(change.clip(lower=0), period)
    loss = _wilder_mean((-change).clip(lower=0), period)
    with np.errstate(divide="ignore", invalid="ignore"):
        result = 100 - 100 / (1 + gain / loss)
    result = result.mask((gain == 0) & (loss == 0), 50.0)
    result = result.mask((gain > 0) & (loss == 0), 100.0)
    result = result.mask((gain == 0) & (loss > 0), 0.0)
    return result.rename("rsi")


def calculate_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Calculate causal features on a validated frame, retaining its index.

    Windows count observed bars. Gaps stay present in time and are not filled.
    """
    features = pd.DataFrame(index=frame.index)
    close = frame.close.astype(float)
    for period in (20, 50, 200):
        features[f"ema{period}"] = close.ewm(span=period, adjust=False, min_periods=period).mean()
    features["rsi"] = rsi_wilder(close, 14)
    previous_close = close.shift(1)
    true_range = pd.concat([
        frame.high - frame.low,
        (frame.high - previous_close).abs(),
        (frame.low - previous_close).abs(),
    ], axis=1).max(axis=1)
    features["atr"] = _wilder_mean(true_range, 14)
    features["roc12"] = (close / close.shift(12) - 1) * 100
    features["prior20_high"] = frame.high.shift(1).rolling(20, min_periods=20).max()
    features["prior20_low"] = frame.low.shift(1).rolling(20, min_periods=20).min()
    features["prior20_tick_volume_mean"] = frame.tick_volume.shift(1).rolling(20, min_periods=20).mean()
    up = ((close > features.ema20) & (features.ema20 > features.ema50) &
          (features.ema50 > features.ema200))
    down = ((close < features.ema20) & (features.ema20 < features.ema50) &
            (features.ema50 < features.ema200))
    features["alignment"] = np.select([up, down], [100.0, -100.0], default=0.0)
    feature_values = features.drop(columns="alignment").to_numpy(dtype=float)
    features["features_finite"] = np.isfinite(feature_values).all(axis=1)
    return features


def _closed_context(features: pd.DataFrame, timeframe: str,
                    decisions: pd.DatetimeIndex) -> pd.DataFrame:
    """Backward ASOF on HTF close, preserving the M5 decision index/order."""
    prefix = timeframe.lower()
    right = features[["alignment", "features_finite"]].copy()
    right[f"htf_{prefix}_open"] = right.index
    right[f"htf_{prefix}_close"] = right.index + pd.Timedelta(minutes=PERIOD_MINUTES[timeframe])
    right = right.rename(columns={"alignment": f"{prefix}_alignment",
                                  "features_finite": f"{prefix}_features_finite"})
    left = pd.DataFrame({"decision_time": decisions})
    joined = pd.merge_asof(
        left, right.reset_index(drop=True), left_on="decision_time",
        right_on=f"htf_{prefix}_close", direction="backward", allow_exact_matches=True,
    )
    return joined


def build_signals(m5: pd.DataFrame, m15: pd.DataFrame,
                  h1: pd.DataFrame) -> pd.DataFrame:
    """Return closed-M5 research signals with broker bar-open DatetimeIndex.

    Required simulator columns: open/high/low/close/spread_points/atr/signal/ready.
    Six component scores, consensus and HTF timestamps are retained for audit.
    Unready rows have signal=0 and NaN scores/consensus; prices are never dropped.
    """
    frames: Mapping[str, pd.DataFrame] = {
        "M5": validate_frame(m5, "M5"), "M15": validate_frame(m15, "M15"),
        "H1": validate_frame(h1, "H1"),
    }
    features = {timeframe: calculate_features(frame) for timeframe, frame in frames.items()}
    base = frames["M5"]
    f = features["M5"]
    output = base.copy()
    decisions = base.index + pd.Timedelta(minutes=5)
    output["decision_time"] = decisions
    output["atr"] = f.atr
    for timeframe in ("M15", "H1"):
        context = _closed_context(features[timeframe], timeframe, decisions)
        for column in context.columns:
            if column != "decision_time":
                output[column] = context[column].to_numpy()

    span = f.prior20_high - f.prior20_low
    ready = (f.features_finite & output.m15_features_finite.eq(True) &
             output.h1_features_finite.eq(True) & (f.atr > 0) & (span > 0) &
             (f.prior20_tick_volume_mean > 0))
    output["ready"] = ready.astype(bool)
    output["orion"] = (f.alignment + output.m15_alignment + output.h1_alignment) / 3
    rsi_score = ((f.rsi - 50) * 4).clip(-100, 100)
    normalized_roc = (f.roc12 / (f.atr.where(f.atr > 0) / base.close * 100) * 50).clip(-100, 100)
    output["vortex"] = (rsi_score + normalized_roc) / 2
    midpoint = (f.prior20_high + f.prior20_low) / 2
    nova = ((base.close - midpoint) / (span.where(span > 0) / 2) * 100).clip(-100, 100)
    nova = nova.mask(base.close > f.prior20_high, 100.0)
    output["nova"] = nova.mask(base.close < f.prior20_low, -100.0)
    activity = (base.tick_volume / f.prior20_tick_volume_mean.where(f.prior20_tick_volume_mean > 0)).clip(upper=1)
    output["luna"] = ((base.close - base.open) / f.atr.where(f.atr > 0) * 100).clip(-100, 100) * activity
    relative_atr = f.atr / base.close
    output["kira"] = np.where(relative_atr.between(0.0003, 0.005, inclusive="both"),
                              np.sign(base.close - f.ema20) * 100, 0.0)
    output["atlas"] = (output.m15_alignment + output.h1_alignment) / 2
    components = list(WEIGHTS)
    output[components] = output[components].clip(-100, 100).where(ready, np.nan)
    output["consensus"] = sum(output[name] * weight for name, weight in WEIGHTS.items())
    output["signal"] = np.select(
        [ready & output.consensus.ge(75), ready & output.consensus.le(-75)], [1, -1], default=0,
    ).astype(np.int8)
    output.attrs.update(version=VERSION, timezone=TIME_BASIS,
                        signal_available_at="decision_time", hypothesis_status="unvalidated")
    return output


def build_signals_from_export(run_dir: str | Path) -> pd.DataFrame:
    """Convenience wrapper for an existing exporter run; no network requests."""
    frames = load_exporter_data(run_dir)
    return build_signals(frames["M5"], frames["M15"], frames["H1"])
