"""Deterministic, bid-OHLC XAUUSD research simulator. No order/broker APIs.

Signals, ATR and spread are consumed only from the previous completed bar.
Intrabar paths are unknown: simultaneous SL/TP touches resolve to SL first.
This is a new research hypothesis, not evidence of a profitable live strategy.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
import math
from typing import Mapping

import pandas as pd


@dataclass(frozen=True)
class SimulatorConfig:
    starting_cash: float = 50.0
    risk_fraction: float = 0.03
    contract_size: float = 100.0
    lot_min: float = 0.01
    lot_step: float = 0.01
    point: float = 0.001
    tick_size: float = 0.001
    leverage: float = 2000.0
    max_margin_fraction: float = 0.25
    stop_atr_multiple: float = 2.2
    min_stop_ticks: int = 10
    target_r: float = 2.2
    max_holding_bars: int = 36
    spread_multiplier: float = 1.0
    slippage_per_ounce: float = 0.03
    commission_per_lot_per_side: float = 0.0
    timeframe_minutes: int = 5
    session_start_hour: int = 8
    session_end_hour: int = 18
    daily_loss_fraction: float = 0.15


def floor_lots(value: float, step: float = 0.01) -> float:
    """Floor to a lot step; deliberately never round a risk allowance upward."""
    if not math.isfinite(value) or value <= 0:
        return 0.0
    steps = (Decimal(str(value)) / Decimal(str(step))).to_integral_value(rounding=ROUND_FLOOR)
    return float(steps * Decimal(str(step)))


def _finite(value) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _tick_price(value: Decimal, tick: float, upward: bool) -> float:
    size = Decimal(str(tick))
    mode = ROUND_CEILING if upward else ROUND_FLOOR
    return float((value / size).to_integral_value(rounding=mode) * size)


def _config(config) -> SimulatorConfig:
    c = config if isinstance(config, SimulatorConfig) else SimulatorConfig(**dict(config or {}))
    positive = ("starting_cash", "contract_size", "lot_min", "lot_step", "point", "tick_size",
                "leverage", "stop_atr_multiple", "target_r", "min_stop_ticks", "max_holding_bars",
                "timeframe_minutes")
    for name in positive:
        if not _finite(getattr(c, name)) or getattr(c, name) <= 0:
            raise ValueError(f"{name} must be finite and positive")
    for name in ("spread_multiplier", "slippage_per_ounce", "commission_per_lot_per_side"):
        if not _finite(getattr(c, name)) or getattr(c, name) < 0:
            raise ValueError(f"{name} must be finite and nonnegative")
    if c.risk_fraction not in (0.03, 0.05, 0.075, 0.10):
        raise ValueError("risk_fraction must be .03, .05, .075 or .10")
    if not 0 < c.max_margin_fraction <= 1 or not 0 < c.daily_loss_fraction < 1:
        raise ValueError("invalid margin or daily-loss fraction")
    if not 0 <= c.session_start_hour < c.session_end_hour <= 24:
        raise ValueError("session hours must satisfy 0 <= start < end <= 24")
    return c


def simulate(frame: pd.DataFrame, config: SimulatorConfig | Mapping | None = None) -> dict:
    """Return summary plus trades/equity/events DataFrames; input is never modified.

    Index: strictly ascending, unique, timezone-naive broker-server bar opens.
    Required columns: open/high/low/close (bid), spread_points, atr, signal, ready.
    Invalid previous spread skips an entry; if a position needs that quote, the
    run raises ValueError rather than fabricate an exit or mark-to-market price.
    """
    c = _config(config)
    required = {"open", "high", "low", "close", "spread_points", "atr", "signal", "ready"}
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is not None:
        raise ValueError("index must be a timezone-naive broker-server DatetimeIndex")
    if frame.index.hasnans or not frame.index.is_monotonic_increasing or not frame.index.is_unique:
        raise ValueError("bar opens must be nonmissing, unique and strictly ascending")
    if not required.issubset(frame.columns):
        raise ValueError(f"missing columns: {sorted(required - set(frame.columns))}")
    for ts, row in frame[["open", "high", "low", "close"]].iterrows():
        o, h, l, cl = row
        if not all(_finite(x) for x in row) or not (0 < l <= min(o, cl) <= max(o, cl) <= h):
            raise ValueError(f"invalid bid OHLC at {ts}")

    delta = pd.Timedelta(minutes=c.timeframe_minutes)
    cash = float(c.starting_cash)
    position = None
    trades, samples, events = [], [], []
    skips = Counter()
    costs = {"commission": 0.0, "slippage": 0.0, "spread_proxy": 0.0}
    day = None
    day_start = cash
    daily_blocked = streak_blocked = False
    streak = maximum_streak = 0
    peak = cash
    max_dd = 0.0
    next_trade_id = 1

    def event(ts, kind, reason, **values):
        events.append({"time": ts, "event": kind, "reason": reason, **values})

    def skip(ts, reason):
        skips[reason] += 1
        event(ts, "skip", reason)

    def liquidation_price(bid, spread):
        return (float(bid) - c.slippage_per_ounce if position["side"] == 1 else
                float(bid) + spread + c.slippage_per_ounce)

    def marked(bid, spread):
        if position is None:
            return cash
        px = liquidation_price(bid, spread)
        fee = position["lots"] * c.commission_per_lot_per_side
        return cash + position["side"] * (px - position["entry_price"]) * position["units"] - fee

    def exit_position(ts, price, spread, reason, index, slippage, phase):
        nonlocal cash, position, streak, maximum_streak, streak_blocked
        p = position
        fee = p["lots"] * c.commission_per_lot_per_side
        gross = p["side"] * (price - p["entry_price"]) * p["units"]
        net = gross - p["entry_fee"] - fee
        cash += gross - fee
        exit_slip = slippage * p["units"]
        exit_spread = spread * p["units"] if p["side"] == -1 else 0.0
        costs["commission"] += fee
        costs["slippage"] += exit_slip
        costs["spread_proxy"] += exit_spread
        streak = streak + 1 if net < -1e-12 else 0
        maximum_streak = max(maximum_streak, streak)
        if streak >= 3:
            streak_blocked = True
            event(ts, "limit", "three_losses_freeze", loss_streak=streak)
        trades.append({**p, "exit_time": ts, "exit_price": float(price), "exit_reason": reason,
                       "exit_phase": phase,
                       "exit_time_basis": ("bar_open_label_actual_intrabar_time_unknown" if phase == "intrabar"
                                           else "bar_" + phase),
                       "exit_fee": fee, "gross_pnl": gross, "net_pnl": net, "balance_after": cash,
                       "holding_bars": index - p["entry_index"], "loss_streak_after": streak,
                       "commission_cost": p["entry_fee"] + fee,
                       "slippage_cost": p["entry_slippage_cost"] + exit_slip,
                       "spread_proxy_cost": p["entry_spread_cost"] + exit_spread})
        event(ts, "exit", reason, trade_id=p["trade_id"], net_pnl=net, balance=cash, exit_phase=phase)
        position = None

    def market_exit(ts, bid, spread, reason, index):
        phase = "close" if reason in ("end_of_data", "daily_loss_close") else "open"
        exit_position(ts, liquidation_price(bid, spread), spread, reason, index, c.slippage_per_ounce, phase)

    def protective_open(ts, row, spread, index):
        """Gap stops get adverse open fills; gap targets get only the level."""
        p = position
        quote = float(row["open"]) + (spread if p["side"] == -1 else 0.0)
        stop_hit = quote <= p["stop_price"] if p["side"] == 1 else quote >= p["stop_price"]
        target_hit = quote >= p["target_price"] if p["side"] == 1 else quote <= p["target_price"]
        if stop_hit:
            market_exit(ts, row["open"], spread, "stop_gap", index)
            return True
        if target_hit:
            exit_position(ts, p["target_price"], spread, "target_gap_at_level", index, 0.0, "open")
            return True
        return False

    def intrabar_exit(ts, row, spread, index):
        p = position
        adjustment = spread if p["side"] == -1 else 0.0
        hi, lo = float(row["high"]) + adjustment, float(row["low"]) + adjustment
        stop_hit = lo <= p["stop_price"] if p["side"] == 1 else hi >= p["stop_price"]
        target_hit = hi >= p["target_price"] if p["side"] == 1 else lo <= p["target_price"]
        if stop_hit:
            price = p["stop_price"] - p["side"] * c.slippage_per_ounce
            reason = "stop_both_touched" if target_hit else "stop"
            exit_position(ts, price, spread, reason, index, c.slippage_per_ounce, "intrabar")
            return True
        if target_hit:
            exit_position(ts, p["target_price"], spread, "target", index, 0.0, "intrabar")
            return True
        return False

    def breach(ts, bid, spread, index, sample):
        nonlocal daily_blocked
        value = marked(bid, spread)
        if day_start > 0 and value <= day_start * (1.0 - c.daily_loss_fraction):
            if not daily_blocked:
                event(ts, "limit", "daily_loss", sample=sample, equity=value, day_start_balance=day_start)
            daily_blocked = True
            if position is not None:
                market_exit(ts, bid, spread, "daily_loss_" + sample, index)
                return True
        return False

    previous = None
    previous_ts = None
    for index, (ts, row) in enumerate(frame.iterrows()):
        exited = False
        raw_spread = None if previous is None else previous["spread_points"]
        spread_valid = _finite(raw_spread) and float(raw_spread) >= 0
        spread = float(raw_spread) * c.point * c.spread_multiplier if spread_valid else 0.0
        if position is not None and not spread_valid:
            raise ValueError(f"invalid previous closed-bar spread while a position is open at {ts}")

        if day != ts.date():
            if position is not None:
                exited = protective_open(ts, row, spread, index)
                if not exited:
                    market_exit(ts, row["open"], spread, "date_change_flat", index)
                    exited = True
            day = ts.date()
            day_start = cash
            daily_blocked = streak_blocked = False
            streak = 0
            event(ts, "day", "reset", day_start_balance=day_start)

        if breach(ts, row["open"], spread, index, "open"):
            exited = True
        if position is not None and protective_open(ts, row, spread, index):
            exited = True
        if position is not None and ts.hour >= c.session_end_hour:
            market_exit(ts, row["open"], spread, "session_flat", index)
            exited = True
        if position is not None and ts >= position["entry_time"] + c.max_holding_bars * delta:
            market_exit(ts, row["open"], spread, "time_exit", index)
            exited = True
        if position is not None and intrabar_exit(ts, row, spread, index):
            exited = True

        if position is not None:
            skip(ts, "position_open")
        elif exited:
            skip(ts, "same_bar_exit")
        elif daily_blocked:
            skip(ts, "daily_loss_limit")
        elif streak_blocked:
            skip(ts, "loss_streak_freeze")
        elif not c.session_start_hour <= ts.hour < c.session_end_hour:
            skip(ts, "session_closed")
        elif previous is None:
            skip(ts, "no_previous_bar")
        elif previous_ts + delta != ts:
            skip(ts, "gap")
        elif pd.isna(previous["ready"]) or not bool(previous["ready"]):
            skip(ts, "warmup")
        elif not _finite(previous["signal"]) or float(previous["signal"]) not in (-1, 0, 1):
            skip(ts, "invalid_signal")
        elif float(previous["signal"]) == 0:
            skip(ts, "no_signal")
        elif not spread_valid:
            skip(ts, "invalid_spread")
        elif not _finite(previous["atr"]) or float(previous["atr"]) <= 0:
            skip(ts, "atr_unavailable")
        elif cash <= 0:
            skip(ts, "nonpositive_cash")
        else:
            side = int(previous["signal"])
            reference = float(row["open"]) + (spread if side == 1 else 0.0)
            fill = reference + side * c.slippage_per_ounce
            unrounded_stop = max(c.stop_atr_multiple * float(previous["atr"]), c.min_stop_ticks * c.tick_size)
            distance = math.ceil(unrounded_stop / c.tick_size) * c.tick_size
            ref_decimal = Decimal(str(reference))
            stop_price = _tick_price(ref_decimal - side * Decimal(str(distance)), c.tick_size, side == -1)
            actual_distance = abs(ref_decimal - Decimal(str(stop_price)))
            distance = float(actual_distance)
            target_price = _tick_price(ref_decimal + side * actual_distance * Decimal(str(c.target_r)),
                                       c.tick_size, side == -1)
            opening_exit_quote = float(row["open"]) + (spread if side == -1 else 0.0)
            opening_stop_crossed = opening_exit_quote <= stop_price if side == 1 else opening_exit_quote >= stop_price
            risk_factor = 0.5 if streak >= 2 else 1.0
            budget = cash * c.risk_fraction * risk_factor
            loss_per_lot = c.contract_size * (distance + 2 * c.slippage_per_ounce) + 2 * c.commission_per_lot_per_side
            risk_lots = floor_lots(budget / loss_per_lot, c.lot_step)
            # Account for entry fees when applying the approximate margin cap.
            margin_per_lot = c.contract_size * reference / c.leverage
            margin_lots = floor_lots(cash * c.max_margin_fraction /
                                    (margin_per_lot + c.max_margin_fraction * c.commission_per_lot_per_side), c.lot_step)
            lots = min(risk_lots, margin_lots)
            if opening_stop_crossed:
                skip(ts, "opening_spread_crosses_stop")
            elif risk_lots < c.lot_min:
                skip(ts, "min_lot")
            elif margin_lots < c.lot_min:
                skip(ts, "margin")
            else:
                units = lots * c.contract_size
                fee = lots * c.commission_per_lot_per_side
                cash -= fee
                entry_spread = spread * units if side == 1 else 0.0
                costs["commission"] += fee
                costs["slippage"] += c.slippage_per_ounce * units
                costs["spread_proxy"] += entry_spread
                position = {"trade_id": next_trade_id, "side": side, "entry_time": ts,
                            "signal_time": previous_ts + delta, "signal_bar_open": previous_ts,
                            "entry_index": index, "entry_price": fill, "entry_reference": reference,
                            "stop_price": stop_price, "target_price": target_price,
                            "target_distance": abs(target_price - reference),
                            "effective_target_r": abs(target_price - reference) / distance,
                            "stop_distance": distance, "lots": lots, "units": units,
                            "risk_fraction": c.risk_fraction * risk_factor, "risk_budget": budget,
                            "planned_stop_loss": lots * loss_per_lot,
                            "margin_estimate": lots * margin_per_lot, "entry_fee": fee,
                            "entry_spread": spread, "entry_spread_cost": entry_spread,
                            "entry_slippage_cost": c.slippage_per_ounce * units}
                next_trade_id += 1
                event(ts, "entry", "previous_closed_signal", trade_id=position["trade_id"], lots=lots)
                # The opening quote has already been checked before sizing.
                exited = protective_open(ts, row, spread, index)
                if not exited:
                    exited = intrabar_exit(ts, row, spread, index)

        close_time = ts + delta
        breach(close_time, row["close"], spread, index, "close")
        if index == len(frame) - 1 and position is not None:
            market_exit(close_time, row["close"], spread, "end_of_data", index)
        value = marked(row["close"], spread)
        peak = max(peak, value)
        drawdown = (peak - value) / peak if peak > 0 else 0.0
        max_dd = max(max_dd, drawdown)
        samples.append({"bar_open_server": ts, "sample_time": close_time, "equity": value, "balance": cash,
                        "drawdown": drawdown, "position_lots": 0.0 if position is None else position["lots"],
                        "day_start_balance": day_start, "daily_loss_blocked": daily_blocked,
                        "loss_streak_blocked": streak_blocked, "loss_streak": streak})
        previous, previous_ts = row, ts

    wins = [t["net_pnl"] for t in trades if t["net_pnl"] > 0]
    losses = [t["net_pnl"] for t in trades if t["net_pnl"] < 0]
    costs["total_proxy"] = sum(costs.values())
    summary = {
        "starting_cash": c.starting_cash, "final_equity": cash,
        "net_profit": cash - c.starting_cash, "net_return": cash / c.starting_cash - 1,
        "n_trades": len(trades), "win_rate": len(wins) / len(trades) if trades else None,
        "profit_factor": sum(wins) / -sum(losses) if losses else (math.inf if wins else None),
        "expectancy": sum(t["net_pnl"] for t in trades) / len(trades) if trades else None,
        "max_close_sampled_drawdown": max_dd, "costs": costs,
        "loss_streak": streak, "maximum_loss_streak": maximum_streak, "skip_reasons": dict(skips),
        "vault_balance": 0.0, "config": asdict(c),
        "limits": {"daily_loss_fraction": c.daily_loss_fraction, "daily_loss_sampling": "bar_open_and_close_only",
                   "daily_loss_is_guaranteed_maximum": False, "halve_risk_after_losses": 2,
                   "freeze_after_losses": 3, "reset": "next_broker_server_date", "max_positions": 1,
                   "max_margin_fraction": c.max_margin_fraction, "margin_model_is_approximate": True},
        "assumptions": [
            "OHLC study only; no broker connection, order submission, live fill claim or profit guarantee.",
            "Bid OHLC; current bar spread proxy is ONLY previous closed-bar spread_points times point and multiplier.",
            "Broker-server timestamps have unknown historical UTC offset; session hours are a research restriction.",
            "Swap is not modeled; current account swap status is unverified. Carry is flattened on first date-change bar.",
            "Leverage-based margin is approximate and does not reproduce broker dynamic margin or stop-out rules.",
            "Slippage and zero default commission are research assumptions, not verified broker costs.",
            "SL rounds outward and TP toward reference to the tick grid; effective target R is recorded per trade.",
            "Reject opening quotes already through SL; entry and SL use adverse slippage, TP fills at its exact level.",
            "Intrabar exit_time is the bar-open bucket label, not a claimed exact fill time; exit_time_basis identifies it.",
            "Stop first when both barriers touch; gap stops use adverse open, gap targets get no favorable credit.",
            "Daily kill is observed only at bar open/close and cannot guarantee a maximum loss, especially over gaps.",
            "Equity drawdown is sampled at closes; spread/slippage cost attribution is a proxy already embedded in PnL.",
            "No martingale, risk boost, reserve transfer or vault; end-of-data positions are forcibly liquidated.",
        ],
    }
    trade_frame = pd.DataFrame(trades)
    equity_frame = pd.DataFrame(samples)
    if not equity_frame.empty:
        equity_frame = equity_frame.set_index("bar_open_server")
    return {"summary": summary, "trades": trade_frame, "equity": equity_frame, "events": pd.DataFrame(events)}
