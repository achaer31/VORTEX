"""Independent, pure risk gate. No signals, broker calls, or credential access."""
from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR, ROUND_CEILING
import math


@dataclass(frozen=True)
class BrokerSpec:
    contract_size: float = 100.0
    lot_min: float = 0.01
    lot_step: float = 0.01
    lot_max: float = 200.0
    tick_size: float = 0.001
    leverage: float = 2000.0
    min_stop_distance: float = 0.0
    max_margin_fraction: float = 0.25


@dataclass(frozen=True)
class Costs:
    slippage_per_ounce: float = 0.03
    commission_per_lot_per_side: float = 0.0


def floor_step(value, step):
    if not math.isfinite(value) or value <= 0:
        return 0.0
    if not math.isfinite(step) or step <= 0:
        raise ValueError("invalid volume step")
    return float((Decimal(str(value)) / Decimal(str(step))).to_integral_value(rounding=ROUND_FLOOR) * Decimal(str(step)))


def tick_price(value, tick, up=False):
    return float((Decimal(str(value)) / Decimal(str(tick))).to_integral_value(
        rounding=ROUND_CEILING if up else ROUND_FLOOR) * Decimal(str(tick)))


def exact_parts(lots, spec):
    """Requested 25/25/50, all closes and residuals executable at broker volume step."""
    parts = (lots / 4, lots / 4, lots / 2)
    if any(p < spec.lot_min - 1e-10 or abs(floor_step(p + 1e-12, spec.lot_step) - p) > 1e-9 for p in parts):
        return None
    return tuple(round(p, 10) for p in parts)


def size_order(equity, risk_fraction, entry, stop, side, spec=None, costs=None,
               free_margin=None, max_risk_fraction=.075):
    """USD-linear contract estimate for OFFLINE tests, never a live MT5 calculator.

    entry is an estimated executable fill including entry spread/slippage.
    Planned stop loss reserves one further adverse stop slippage plus both fees.
    Live adapter MUST instead use broker order_calc_profit/order_calc_margin.
    """
    s, c = spec or BrokerSpec(), costs or Costs()
    def reject(reason, **extra):
        return dict(allowed=False, reason=reason, lots=0.0, risk_cash=0.0, margin=0.0, parts=None, **extra)
    values = [equity, risk_fraction, max_risk_fraction, entry, stop, s.contract_size, s.lot_min,
              s.lot_step, s.lot_max, s.tick_size, s.leverage, s.max_margin_fraction,
              s.min_stop_distance, c.slippage_per_ounce, c.commission_per_lot_per_side]
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in values):
        return reject("invalid_risk_input")
    if (equity <= 0 or entry <= 0 or stop <= 0 or side not in (-1, 1) or
        not 0 < risk_fraction <= max_risk_fraction <= .10 or min(s.contract_size, s.lot_min, s.lot_step, s.lot_max, s.tick_size, s.leverage) <= 0 or
        min(c.slippage_per_ounce, c.commission_per_lot_per_side, s.min_stop_distance) < 0 or not 0 < s.max_margin_fraction <= 1):
        return reject("invalid_risk_input")
    stop = tick_price(stop, s.tick_size, up=side == -1)
    distance = side * (entry - stop)
    if distance <= max(0, s.min_stop_distance) or distance < s.tick_size:
        return reject("invalid_stop")
    per_lot = (distance + c.slippage_per_ounce) * s.contract_size + 2 * c.commission_per_lot_per_side
    budget = equity * risk_fraction
    raw = floor_step(min(budget / per_lot, s.lot_max), s.lot_step)
    if raw < s.lot_min - 1e-10:
        return reject("min_lot", minimum_risk=s.lot_min * per_lot, budget=budget)
    # User amendment: preserve affordable volume; adapt exits instead of sizing up.
    lots = raw
    parts = exact_parts(lots, s)
    exit_policy = 'partial_25_25_50' if parts is not None else 'single_trailing'
    if parts is None:
        parts = (0.0, 0.0, lots)
    margin = lots * s.contract_size * entry / s.leverage
    free_margin = equity if free_margin is None else free_margin
    if not math.isfinite(free_margin) or free_margin < 0:
        return reject("invalid_margin")
    if margin > min(free_margin, equity * s.max_margin_fraction) + 1e-10:
        return reject("margin")
    return dict(allowed=True, reason="PASS", lots=lots, risk_cash=lots * per_lot,
                margin=margin, parts=parts, stop=stop, budget=budget, exit_policy=exit_policy)


def mode_gate(day_start_equity, equity, loss_streak, requested_mode, connected=True,
              data_fresh=True, protective_orders_confirmed=True):
    if (not all(math.isfinite(v) for v in (day_start_equity, equity)) or day_start_equity <= 0):
        return "FROZEN", "invalid_equity", 0.0
    dd = max(0.0, 1 - equity / day_start_equity)
    if dd >= .15:
        return "KILL", "daily_drawdown_15", 0.0
    if loss_streak >= 3:
        return "FROZEN", "three_losses", 0.0
    if not connected or not data_fresh or not protective_orders_confirmed:
        return "FROZEN", "connection_data_or_protection", 0.0
    risk = {"NORMAL": .02, "AGGRESSIVE": .035, "EXTREME": .05}.get(requested_mode)
    if risk is None:
        return "FROZEN", "invalid_mode", 0.0
    if requested_mode == "EXTREME" and (dd >= .10 or loss_streak >= 2):
        return "FROZEN", "extreme_disabled", 0.0
    return requested_mode, "PASS", risk * (.5 if loss_streak >= 2 else 1)
