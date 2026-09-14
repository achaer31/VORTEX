"""Causal v0.2 OHLC execution experiment; no broker or order APIs.

This module is deliberately independent of the frozen v0.1 simulator. Exact
25/25/50 exits are used only when volume permits; otherwise the entire leg uses
a single stop/trail and full 2.5R take profit. No volume is rounded upward.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
import math

import numpy as np
import pandas as pd

from .risk import BrokerSpec, Costs, size_order


MODE_RISK = {"NORMAL": .02, "AGGRESSIVE": .035, "EXTREME": .05}
BAR = pd.Timedelta(minutes=5)


@dataclass(frozen=True)
class BacktestConfig:
    starting_cash: float = 50.0
    risk_fraction: float = .02
    extreme_risk: float = .05
    stress_fixed_risk: bool = False
    contract_size: float = 100.0
    lot_min: float = .01
    lot_step: float = .01
    lot_max: float = 200.0
    point: float = .001
    tick_size: float = .001
    leverage: float = 2000.0
    max_margin_fraction: float = .25
    spread_multiplier: float = 1.0
    slippage_per_ounce: float = .03
    commission_per_lot_per_side: float = 0.0
    swap_long_per_lot_per_day: float = 0.0
    swap_short_per_lot_per_day: float = 0.0
    triple_swap_weekday: int = 2
    daily_disable_extreme_drawdown: float = .10
    daily_kill_drawdown: float = .15
    max_campaign_risk_fraction: float = .075
    allow_pyramiding: bool = True

    def __post_init__(self):
        if self.risk_fraction not in (.02, .035, .05, .075, .10):
            raise ValueError("invalid research risk_fraction")
        if self.extreme_risk not in (.05, .075, .10):
            raise ValueError("extreme_risk must be .05, .075 or .10")
        if self.risk_fraction == .10 and self.extreme_risk != .10:
            raise ValueError("10% risk requires explicit EXTREME stress profile")
        for key in ("starting_cash", "contract_size", "lot_min", "lot_step", "lot_max",
                    "point", "tick_size", "leverage"):
            if not finite(getattr(self, key)) or getattr(self, key) <= 0:
                raise ValueError(f"invalid {key}")
        for key in ("spread_multiplier", "slippage_per_ounce", "commission_per_lot_per_side"):
            if not finite(getattr(self, key)) or getattr(self, key) < 0:
                raise ValueError(f"invalid {key}")
        for key in ("swap_long_per_lot_per_day", "swap_short_per_lot_per_day"):
            if not finite(getattr(self, key)):
                raise ValueError("swap assumptions must be explicit finite numbers")
        if not (0 < self.max_margin_fraction <= 1 and
                0 < self.daily_disable_extreme_drawdown < self.daily_kill_drawdown < 1 and
                0 < self.max_campaign_risk_fraction <= max(.075, self.extreme_risk)):
            raise ValueError("invalid risk limits")
        if self.triple_swap_weekday not in range(5):
            raise ValueError("triple_swap_weekday must be a weekday")


def finite(value):
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def flag(value):
    return isinstance(value, (bool, np.bool_)) and bool(value)


def grid(value, tick, up=False):
    size = Decimal(str(tick))
    ratio = Decimal(str(value)) / size
    nearest = ratio.to_integral_value()
    # Remove only arithmetic noise far below one price tick before flooring.
    if abs(ratio - nearest) < Decimal("0.0000001"):
        ratio = nearest
    return float(ratio.to_integral_value(rounding=ROUND_CEILING if up else ROUND_FLOOR) * size)


def floor_lots(value, step):
    if not finite(value) or value <= 0:
        return 0.0
    size = Decimal(str(step))
    return float((Decimal(str(value)) / size).to_integral_value(rounding=ROUND_FLOOR) * size)


def size_leg(equity, risk_fraction, reference, stop, side, config, free_margin):
    """Adapt the independent risk gate; reference excludes entry slippage."""
    c = config
    plan = size_order(float(equity), float(risk_fraction),
                      float(reference + side * c.slippage_per_ounce), float(stop), side,
                      BrokerSpec(contract_size=c.contract_size, lot_min=c.lot_min,
                                 lot_step=c.lot_step, lot_max=c.lot_max, tick_size=c.tick_size,
                                 leverage=c.leverage, max_margin_fraction=c.max_margin_fraction),
                      Costs(c.slippage_per_ounce, c.commission_per_lot_per_side),
                      float(free_margin), max_risk_fraction=max(.075, c.extreme_risk))
    return {**plan, "risk_cash": equity * risk_fraction,
            "planned_loss": plan["risk_cash"]}


def simulate(frame: pd.DataFrame, config: BacktestConfig | None = None) -> dict:
    c = config or BacktestConfig()
    if isinstance(c, dict):
        c = BacktestConfig(**c)
    needed = {"open", "high", "low", "close", "spread_points", "decision_time", "atr", "signal",
              "ready", "mode", "consensus", "orion", "nova", "stop_long", "stop_short",
              "swing_low", "swing_high", "news_blocked", "execution_valid"}
    if not needed.issubset(frame.columns):
        raise ValueError(f"missing columns: {sorted(needed - set(frame.columns))}")
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise ValueError("UTC-aware M5 bar-open index required")
    if frame.index.hasnans or not frame.index.is_unique or not frame.index.is_monotonic_increasing:
        raise ValueError("bar-open index must be unique, ascending and nonmissing")
    f = frame.copy(deep=False)
    f.index = frame.index.tz_convert("UTC")
    for ts, r in f[["open", "high", "low", "close"]].iterrows():
        o, h, l, close = r
        if not all(finite(v) for v in r) or not 0 < l <= min(o, close) <= max(o, close) <= h:
            raise ValueError(f"invalid bid OHLC at {ts}")

    balance = float(c.starting_cash)
    legs, completed, events, samples, campaign_results = [], [], [], [], []
    skips = Counter()
    costs = {"commission": 0.0, "slippage": 0.0, "spread_proxy": 0.0, "swap": 0.0}
    campaign = None
    next_leg = next_campaign = 1
    losing_campaigns = maximum_losing_campaigns = 0
    frozen = False
    day = None
    day_start = balance
    daily_killed = extreme_disabled = False
    peak = balance
    max_dd = 0.0
    last_signal = None

    def emit(ts, event, reason, **fields):
        events.append({"time": ts, "event": event, "reason": reason, **fields})

    def skip(ts, reason, kind="base"):
        skips[reason] += 1
        emit(ts, "skip", reason, kind=kind)

    def exit_quote(leg, bid, spread):
        return float(bid) + (spread if leg["side"] == -1 else 0) - leg["side"] * c.slippage_per_ounce

    def mark(bid, spread):
        return balance + sum(p["side"] * (exit_quote(p, bid, spread) - p["entry_price"]) *
                             p["remaining_lots"] * c.contract_size -
                             p["remaining_lots"] * c.commission_per_lot_per_side for p in legs)

    def used_margin(bid):
        return sum(p["remaining_lots"] * c.contract_size * float(bid) / c.leverage for p in legs)

    def open_risk():
        return sum(max(0, p["side"] * (p["entry_price"] -
                   (p["stop"] - p["side"] * c.slippage_per_ounce)) *
                   p["remaining_lots"] * c.contract_size +
                   p["remaining_lots"] * c.commission_per_lot_per_side) for p in legs)

    def finish_campaign(ts):
        nonlocal campaign, losing_campaigns, maximum_losing_campaigns, frozen
        if campaign is None or legs:
            return
        pnl = sum(p["net_pnl"] for p in completed if p["campaign_id"] == campaign["id"])
        losing_campaigns = losing_campaigns + 1 if pnl < -1e-9 else 0
        maximum_losing_campaigns = max(maximum_losing_campaigns, losing_campaigns)
        if losing_campaigns >= 3:
            frozen = True
            emit(ts, "limit", "three_losing_campaigns_freeze")
        campaign_results.append({"campaign_id": campaign["id"], "net_pnl": pnl,
                                 "closed_time": ts, "losing_streak_after": losing_campaigns})
        emit(ts, "campaign_closed", "flat", campaign_id=campaign["id"], net_pnl=pnl)
        campaign = None

    def close_part(p, lots, price, spread, ts, reason, phase, slip):
        nonlocal balance
        lots = min(lots, p["remaining_lots"])
        fee = lots * c.commission_per_lot_per_side
        gross = p["side"] * (price - p["entry_price"]) * lots * c.contract_size
        swap_share = p["unallocated_swap"] * lots / p["remaining_lots"]
        p["unallocated_swap"] -= swap_share
        balance += gross - fee
        p["gross_pnl"] += gross
        p["exit_fees"] += fee
        p["exit_lots"] += lots
        p["remaining_lots"] = round(p["remaining_lots"] - lots, 12)
        p["fill_count"] += 1
        costs["commission"] += fee
        costs["slippage"] += slip * lots * c.contract_size
        spread_cost = spread * lots * c.contract_size if p["side"] == -1 else 0
        costs["spread_proxy"] += spread_cost
        emit(ts, "exit", reason, leg_id=p["id"], campaign_id=p["campaign_id"], lots=lots,
             price=price, gross_pnl=gross, exit_fee=fee, allocated_swap=swap_share,
             exit_phase=phase, exit_time_basis=("bar_open_label_intrabar_time_unknown" if phase == "intrabar" else phase))
        if p["remaining_lots"] <= 1e-12:
            p["exit_time"], p["exit_reason"] = ts, reason
            p["net_pnl"] = p["gross_pnl"] - p["entry_fee"] - p["exit_fees"] + p["swap_pnl"]
            completed.append(dict(p))
            legs.remove(p)

    def market_close(p, bid, spread, ts, reason, phase="open"):
        close_part(p, p["remaining_lots"], exit_quote(p, bid, spread), spread, ts, reason, phase,
                   c.slippage_per_ounce)

    def old_open_protection(row, spread, ts):
        any_exit = False
        for p in list(legs):
            quote = float(row["open"]) + (spread if p["side"] == -1 else 0)
            if p["side"] * (quote - p["stop"]) <= 0:
                market_close(p, row["open"], spread, ts, "stop_gap")
                any_exit = True
                continue
            if p["exit_policy"] == "single_trailing":
                if p["side"] * (quote - p["tp2"]) >= 0:
                    close_part(p, p["remaining_lots"], p["tp2"], spread, ts,
                               "single_tp_gap_at_level", "open", 0)
                    any_exit = True
                continue
            for number, level in ((1, p["tp1"]), (2, p["tp2"])):
                if not p[f"tp{number}_done"] and p["side"] * (quote - level) >= 0:
                    p[f"tp{number}_done"] = True
                    close_part(p, p["parts"][number - 1], level, spread, ts,
                               f"tp{number}_gap_at_level", "open", 0)
                    any_exit = True
        return any_exit

    def intrabar_protection(row, spread, ts):
        any_exit = False
        for p in list(legs):
            offset = spread if p["side"] == -1 else 0
            high, low = float(row["high"]) + offset, float(row["low"]) + offset
            stop_hit = low <= p["stop"] if p["side"] == 1 else high >= p["stop"]
            favorable = high if p["side"] == 1 else low
            target_hit = (p["side"] * (favorable - p["tp2"]) >= 0 if p["exit_policy"] == "single_trailing"
                          else any(not p[f"tp{k}_done"] and p["side"] * (favorable - p[f"tp{k}"]) >= 0 for k in (1, 2)))
            if stop_hit:
                close_part(p, p["remaining_lots"], p["stop"] - p["side"] * c.slippage_per_ounce,
                           spread, ts, "stop_both_touched" if target_hit else "stop", "intrabar",
                           c.slippage_per_ounce)
                any_exit = True
                continue
            if p["exit_policy"] == "single_trailing":
                if target_hit:
                    close_part(p, p["remaining_lots"], p["tp2"], spread, ts,
                               "single_tp", "intrabar", 0)
                    any_exit = True
                continue
            for number in (1, 2):
                if not p[f"tp{number}_done"] and p["side"] * (favorable - p[f"tp{number}"]) >= 0:
                    p[f"tp{number}_done"] = True
                    close_part(p, p["parts"][number - 1], p[f"tp{number}"], spread, ts,
                               f"tp{number}", "intrabar", 0)
                    any_exit = True
        return any_exit

    def breakeven(p):
        cost_per_unit = (2 * c.commission_per_lot_per_side / c.contract_size + c.slippage_per_ounce +
                         max(0, -p["unallocated_swap"]) / (p["remaining_lots"] * c.contract_size))
        return grid(p["entry_price"] + p["side"] * cost_per_unit, c.tick_size, p["side"] == 1)

    def update_protection(previous, row, spread, ts):
        any_exit = False
        if (previous is None or previous.name + BAR != ts or
                ("m15_fresh" in previous.index and not flag(previous["m15_fresh"])) or
                not finite(previous["atr"]) or previous["atr"] <= 0):
            return any_exit
        atr = float(previous["atr"])
        for p in list(legs):
            proposal = p["stop"]
            previous_quote = float(previous["close"]) + (spread if p["side"] == -1 else 0)
            if p["side"] * (previous_quote - p["entry_price"]) >= p["initial_r"]:
                be = breakeven(p)
                proposal = max(proposal, be) if p["side"] == 1 else min(proposal, be)
            if (p["tp2_done"] or (p["exit_policy"] == "single_trailing" and
                    p["side"] * (previous_quote - p["entry_price"]) >= 1.5 * p["initial_r"])):
                p["trail_started"] = True
            if p["trail_started"]:
                trail = float(previous["close"]) - p["side"] * 1.3 * atr
                swing = previous["swing_low"] if p["side"] == 1 else previous["swing_high"]
                if finite(swing):
                    structural = float(swing) - p["side"] * .1 * atr
                    trail = max(trail, structural) if p["side"] == 1 else min(trail, structural)
                proposal = max(proposal, trail) if p["side"] == 1 else min(proposal, trail)
            proposal = grid(proposal, c.tick_size, p["side"] == -1)
            if p["side"] * (proposal - p["stop"]) > 1e-10:
                quote = float(row["open"]) + (spread if p["side"] == -1 else 0)
                if p["side"] * (quote - proposal) <= 0:
                    market_close(p, row["open"], spread, ts, "new_protection_crossed_at_open")
                    any_exit = True
                else:
                    p["stop"] = proposal
                    emit(ts, "stop_update", "previous_closed_data", leg_id=p["id"], stop=proposal)
        return any_exit

    def charge_swap(previous_ts, ts):
        nonlocal balance
        if previous_ts is None or not legs:
            return
        date = previous_ts.date()
        while date < ts.date():
            if date.weekday() < 5:
                multiplier = 3 if date.weekday() == c.triple_swap_weekday else 1
                for p in legs:
                    rate = c.swap_long_per_lot_per_day if p["side"] == 1 else c.swap_short_per_lot_per_day
                    amount = rate * p["remaining_lots"] * multiplier
                    balance += amount
                    p["swap_pnl"] += amount
                    p["unallocated_swap"] += amount
                    costs["swap"] -= amount
                    emit(ts, "swap", "modeled_weekday_rollover", leg_id=p["id"], rollover_date=str(date),
                         multiplier=multiplier, cash_change=amount)
            date += timedelta(days=1)

    def daily_guard(bid, spread, ts, phase):
        nonlocal daily_killed, extreme_disabled
        value = mark(bid, spread)
        dd = (day_start - value) / day_start if day_start > 0 else 1.0
        if dd >= c.daily_disable_extreme_drawdown:
            if not extreme_disabled:
                emit(ts, "limit", "daily_disable_extreme", sample=phase, drawdown=dd)
            extreme_disabled = True
        if dd >= c.daily_kill_drawdown:
            if not daily_killed:
                emit(ts, "limit", "daily_kill", sample=phase, drawdown=dd)
            daily_killed = True
            had = bool(legs)
            for p in list(legs):
                market_close(p, bid, spread, ts, "daily_kill_" + phase, phase)
            return had
        return False

    def eligibility(previous, previous_ts, ts, spread_valid):
        if previous is None:
            return "no_previous_bar"
        if previous_ts + BAR != ts or pd.Timestamp(previous["decision_time"]) != ts:
            return "gap_or_noncausal_decision"
        if not flag(previous["ready"]):
            return "decision_invalid_or_warmup"
        if not isinstance(previous["news_blocked"], (bool, np.bool_)) or flag(previous["news_blocked"]):
            return "news_blocked_or_missing"
        if not flag(previous["execution_valid"]) or not spread_valid:
            return "execution_missing_or_invalid"
        if previous["mode"] not in MODE_RISK:
            return "frozen_or_unknown_mode"
        if previous["mode"] == "EXTREME" and extreme_disabled:
            return "daily_extreme_disabled"
        if previous["mode"] == "EXTREME" and losing_campaigns >= 2:
            return "losing_streak_extreme_disabled"
        if not finite(previous["signal"]) or float(previous["signal"]) not in (-1, 0, 1):
            return "invalid_signal"
        if int(previous["signal"]) == 0:
            return "no_signal"
        return None

    def open_leg(previous, row, spread, ts, kind, risk_fraction):
        nonlocal balance, next_leg, next_campaign, campaign
        side = int(previous["signal"]) if campaign is None else campaign["side"]
        atr = previous["atr"]
        structural = previous["stop_long"] if side == 1 else previous["stop_short"]
        if not finite(atr) or float(atr) <= 0 or not finite(structural):
            return "stop_data_missing"
        atr = float(atr)
        reference = float(row["open"]) + (spread if side == 1 else 0)
        entry_price = reference + side * c.slippage_per_ounce
        raw = min(float(structural), entry_price - 1.4 * atr) if side == 1 else max(float(structural), entry_price + 1.4 * atr)
        stop = grid(raw, c.tick_size, side == -1)
        distance = side * (entry_price - stop)
        if distance > 2.2 * atr + 1e-9:
            return "stop_exceeds_atr_cap"
        liquidation = float(row["open"]) + (spread if side == -1 else 0)
        if side * (liquidation - stop) <= 0:
            return "opening_spread_crosses_stop"
        equity = mark(row["open"], spread)
        risk_factor = .5 if losing_campaigns >= 2 else 1.0
        fraction = risk_fraction * risk_factor
        plan = size_leg(equity, fraction, reference, stop, side, c,
                        max(0, equity * c.max_margin_fraction - used_margin(row["open"])))
        if not plan["allowed"]:
            return plan["reason"]
        base_equity = equity if campaign is None else campaign["base_equity"]
        prior_nominal = 0 if campaign is None else campaign["nominal_risk"]
        if prior_nominal + plan["risk_cash"] > base_equity * c.max_campaign_risk_fraction + 1e-9:
            return "campaign_nominal_risk_cap"
        if open_risk() + plan["planned_loss"] > equity * c.max_campaign_risk_fraction + 1e-9:
            return "net_open_risk_cap"
        if campaign is None:
            campaign = {"id": next_campaign, "side": side, "base_equity": equity,
                        "nominal_risk": 0.0, "adds": 0, "base_id": next_leg}
            next_campaign += 1
        else:
            campaign["adds"] += 1
        campaign["nominal_risk"] += plan["risk_cash"]
        lots = plan["lots"]
        fee = lots * c.commission_per_lot_per_side
        balance -= fee
        costs["commission"] += fee
        costs["slippage"] += c.slippage_per_ounce * lots * c.contract_size
        costs["spread_proxy"] += spread * lots * c.contract_size if side == 1 else 0
        p = {"id": next_leg, "campaign_id": campaign["id"], "kind": kind, "side": side,
             "entry_time": ts, "signal_bar_open": previous.name, "reference": reference,
             "entry_price": entry_price, "initial_stop": stop,
             "initial_r": distance, "stop": stop, "initial_lots": lots, "remaining_lots": lots,
             "parts": plan["parts"], "risk_fraction": fraction, "risk_budget": plan["risk_cash"],
             "exit_policy": plan["exit_policy"], "trail_started": False,
             "initial_planned_loss": plan["planned_loss"], "margin_at_entry": plan["margin"],
             "tp1": grid(entry_price + side * distance * 1.5, c.tick_size, side == -1),
             "tp2": grid(entry_price + side * distance * 2.5, c.tick_size, side == -1),
             "tp1_done": False, "tp2_done": False, "entry_fee": fee, "exit_fees": 0.0,
             "gross_pnl": 0.0, "swap_pnl": 0.0, "unallocated_swap": 0.0, "exit_lots": 0.0,
             "fill_count": 0}
        next_leg += 1
        legs.append(p)
        emit(ts, "entry", kind, leg_id=p["id"], campaign_id=p["campaign_id"], lots=lots,
             risk_budget=p["risk_budget"], planned_loss=p["initial_planned_loss"], stop=stop,
             exit_policy=p["exit_policy"],
             cumulative_nominal_risk=campaign["nominal_risk"], campaign_base_equity=base_equity)
        return None

    def try_add(previous, row, spread, ts):
        if not c.allow_pyramiding or campaign["adds"] >= 2:
            return "pyramid_limit_or_disabled"
        base = next((p for p in legs if p["id"] == campaign["base_id"]), None)
        if base is None:
            return "base_leg_already_closed"
        side = campaign["side"]
        if int(previous["signal"]) != side:
            return "pyramid_signal_not_aligned"
        level = 1 if campaign["adds"] == 0 else 2
        previous_quote = float(previous["close"]) + (spread if side == -1 else 0)
        if side * (previous_quote - base["entry_price"]) < level * base["initial_r"]:
            return "pyramid_r_trigger_not_reached"
        if any(p["side"] * (exit_quote(p, row["open"], spread) - p["entry_price"]) *
               p["remaining_lots"] * c.contract_size -
               p["remaining_lots"] * 2 * c.commission_per_lot_per_side +
               p["unallocated_swap"] < -1e-9 for p in legs):
            return "pyramid_would_average_loser"
        threshold = 78 if level == 1 else 82
        if not finite(previous["consensus"]) or side * float(previous["consensus"]) < threshold:
            return "pyramid_consensus"
        if level == 2 and any(not finite(previous[k]) or side * float(previous[k]) < 80 for k in ("orion", "nova")):
            return "pyramid_components"
        if side * (base["stop"] - breakeven(base)) < -1e-9:
            return "base_breakeven_not_confirmed"
        if level == 2 and any(side * (p["stop"] - breakeven(p)) < -1e-9 for p in legs):
            return "earlier_legs_breakeven_not_confirmed"
        return open_leg(previous, row, spread, ts, f"add{level}", .015 if level == 1 else .01)

    previous = None
    previous_ts = None
    for index, (ts, row) in enumerate(f.iterrows()):
        valid_spread = previous is not None and finite(previous["spread_points"]) and previous["spread_points"] >= 0
        spread = float(previous["spread_points"]) * c.point * c.spread_multiplier if valid_spread else 0.0
        if legs and not valid_spread:
            raise ValueError(f"cannot price existing position protection without prior spread at {ts}")
        if day != ts.date():
            day = ts.date()
            day_start = mark(row["open"], spread)
            daily_killed = extreme_disabled = False
            emit(ts, "day", "starting_equity", equity=day_start)
        charge_swap(previous_ts, ts)
        exited = old_open_protection(row, spread, ts)
        exited = update_protection(previous, row, spread, ts) or exited
        exited = daily_guard(row["open"], spread, ts, "open") or exited
        finish_campaign(ts)
        reason = eligibility(previous, previous_ts, ts, valid_spread)
        if exited:
            skip(ts, "same_bar_exit", "add" if campaign else "base")
        elif frozen:
            skip(ts, "three_campaign_freeze")
        elif daily_killed:
            skip(ts, "daily_kill_block")
        elif reason:
            skip(ts, reason, "add" if campaign else "base")
        elif previous_ts == last_signal:
            skip(ts, "signal_already_consumed")
        else:
            last_signal = previous_ts
            if campaign is None:
                mode_risk = c.extreme_risk if previous["mode"] == "EXTREME" else MODE_RISK[previous["mode"]]
                risk = c.risk_fraction if c.stress_fixed_risk else min(mode_risk, c.risk_fraction)
                reason = open_leg(previous, row, spread, ts, "base", risk)
            else:
                reason = try_add(previous, row, spread, ts)
            if reason:
                skip(ts, reason, "add" if campaign else "base")
        intrabar_protection(row, spread, ts)
        close_time = ts + BAR
        daily_guard(row["close"], spread, close_time, "close")
        if index == len(f) - 1:
            for p in list(legs):
                market_close(p, row["close"], spread, close_time, "end_of_data", "close")
        finish_campaign(close_time)
        value = mark(row["close"], spread)
        peak = max(peak, value)
        dd = (peak - value) / peak if peak > 0 else 0
        max_dd = max(max_dd, dd)
        samples.append({"bar_open_utc": ts, "sample_time": close_time, "equity": value,
                        "balance": balance, "drawdown": dd, "open_legs": len(legs),
                        "open_lots": sum(p["remaining_lots"] for p in legs),
                        "net_open_risk": open_risk(), "margin_estimate": used_margin(row["close"]),
                        "day_start_equity": day_start, "daily_killed": daily_killed,
                        "extreme_disabled": extreme_disabled, "losing_campaigns": losing_campaigns,
                        "run_frozen": frozen})
        previous, previous_ts = row, ts

    pnls = [x["net_pnl"] for x in campaign_results]
    wins, losses = [x for x in pnls if x > 0], [x for x in pnls if x < 0]
    costs["total_proxy"] = sum(costs.values())
    summary = {"version": "VORTEX-XAU-v0.2-execution", "starting_cash": c.starting_cash,
        "final_equity": balance, "net_profit": balance - c.starting_cash,
        "net_return": balance / c.starting_cash - 1, "n_trades": len(completed),
        "n_campaigns": len(campaign_results), "n_adds": sum(p["kind"] != "base" for p in completed),
        "win_rate": len(wins) / len(pnls) if pnls else None,
        "profit_factor": sum(wins) / -sum(losses) if losses else (math.inf if wins else None),
        "expectancy": sum(pnls) / len(pnls) if pnls else None,
        "max_close_sampled_drawdown": max_dd, "maximum_losing_campaigns": maximum_losing_campaigns,
        "run_frozen": frozen, "skip_reasons": dict(skips), "costs": costs, "config": asdict(c),
        "campaigns": campaign_results, "deployable_configuration": False,
        "production_risk_profile": not c.stress_fixed_risk and c.extreme_risk == .05,
        "exit_policy_counts": dict(Counter(p["exit_policy"] for p in completed)),
        "assumptions": [
            "Research OHLC model, not a live fill or profitability claim; no broker APIs.",
            "Entry/add uses only prior closed M5 row at the next contiguous M5 open; mode/news/execution must be available.",
            "Current Ask is Bid plus previous closed-bar spread times the configured multiplier.",
            "Affordable volume floors to broker step; exact 25/25/50 is used when executable, otherwise full single SL/trail/TP without pretend partials.",
            "Partial policy: TP1=1.5R, TP2=2.5R; remaining 50% trails after TP2. Single policy: trail activates on prior close >=1.5R, full TP=2.5R.",
            "Old stops handle opening gaps before new BE/trails; intrabar dual touches resolve stop first; no favorable TP gap credit.",
            "No BE/trail amendment after a missing M5 bar or a supplied stale M15 flag; the previous protective stop remains active.",
            "Each leg BE at prior close +1R includes modeled fees/slippage/swap debit; add #2 requires prior legs protected at cost-adjusted BE.",
            "At most two adds (1.5% then 1% risk); each leg has its own volume-based exit policy; cumulative nominal risk uses configured campaign cap.",
            "Open-risk sum conservatively does not offset losing risk with locked profits; margin/leverage remain approximate.",
            "Daily baseline is UTC-day opening liquidation equity before modeled rollover costs; 10% disables EXTREME, 15% kills at sampled open/close.",
            "Daily limits and close-sampled drawdown cannot guarantee intrabar/gap loss bounds.",
            "Two losing campaigns halve future base/add budgets and disable EXTREME; three freeze the remaining run, without daily reset.",
            "Swap inputs are signed USD per lot per weekday rollover, Wednesday triple by default, weekends skipped; not verified broker swap schedules.",
            "News/execution flags block new risk but never disable existing protection; absent price/spread needed for protection aborts the simulation.",
            "No independent session-hour limit or maximum hold; signal eligibility controls sessions, and end-of-data legs liquidate with costs.",
            "Intrabar exit timestamps label their M5 bucket; they do not reveal exact fill sequence/time.",
            "EXTREME 7.5%/10% and fixed-base sensitivities are offline nondeployable; no thresholds are adjusted from results."]}
    equity = pd.DataFrame(samples)
    if not equity.empty:
        equity = equity.set_index("bar_open_utc")
    active = bool(completed)
    observed_failure = bool(not equity.empty and (equity.equity <= 0).any())
    failure_rows = equity[equity.equity <= 0] if not equity.empty else equity
    elapsed_days = ((f.index[-1] + BAR - f.index[0]).total_seconds() / 86400) if len(f) else 0
    milestones = []
    for amount in (100, 250, 500, 1000, 10000, 50000):
        hits = equity[equity.equity >= amount] if not equity.empty else equity
        hit_time = (f.index[0] if len(f) and c.starting_cash >= amount else
                    hits.iloc[0].sample_time if not hits.empty else None)
        milestones.append({"equity_usd": amount, "hit": hit_time is not None,
                           "first_observed_time": hit_time,
                           "elapsed_days": (hit_time - f.index[0]).total_seconds() / 86400 if hit_time is not None else None,
                           "status": "observed" if hit_time is not None else
                                     "account_failed_before_observed_hit" if observed_failure else "censored_at_data_end"})
    summary.update({"account_failure": observed_failure if active else None,
                    "ruin_time": failure_rows.iloc[0].sample_time if not failure_rows.empty else None,
                    "risk_of_ruin_probability": None,
                    "ruin_status": "observed_account_failure" if observed_failure else
                                   "not_observed_in_active_path" if active else "insufficient_activity",
                    "geometric_return_per_campaign": (balance / c.starting_cash) ** (1 / len(pnls)) - 1 if pnls and balance > 0 else None,
                    "observed_log_growth_per_day": math.log(balance / c.starting_cash) / elapsed_days if active and balance > 0 and elapsed_days > 0 else None,
                    "observed_days": elapsed_days, "milestones": milestones,
                    "censored": not observed_failure,
                    "future_growth_projection": None})
    summary["assumptions"].append("Growth and milestones describe this observed segment only; unhit milestones are censored. No ruin probability or future timeline is inferred from one historical path.")
    return {"summary": summary, "trades": pd.DataFrame(completed), "equity": equity, "events": pd.DataFrame(events)}
