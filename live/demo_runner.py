"""VORTEX DEMO bridge. Default observe; all sends pass a fresh DEMO/login guard.

No login/password API is used. Runs beside an already logged-in MT5 terminal.
Runtime account identity, position tickets and journals must remain outside Git.
The research module is unchanged; execution is a separate forward experiment.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
import uuid

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "research"))
from vortex_xau.signals import build_signals, TIME_BASIS, VERSION  # noqa: E402

BRIDGE_VERSION = "VORTEX-DEMO-v0.1"
SYMBOL = "XAUUSD"
MAGIC = 26091401
UTC = timezone.utc


def utc_iso(epoch):
    return datetime.fromtimestamp(epoch, UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class SafetyStop(RuntimeError):
    """A bounded machine-readable reason; never include broker response objects."""


def finite(value):
    try:
        return math.isfinite(float(value))
    except (ValueError, TypeError):
        return False


@dataclass(frozen=True)
class Config:
    expected_login: int
    session_offset_minutes: int
    risk_fraction: float = .03
    mode: str = "observe"
    capital_cap: float = 50.0
    slippage_per_ounce: float = .03
    commission_per_lot_per_side: float = 0.0
    max_margin_fraction: float = .25
    daily_loss_fraction: float = .15
    max_tick_age_seconds: int = 10
    max_decision_age_seconds: int = 30
    poll_seconds: int = 2

    def __post_init__(self):
        if isinstance(self.expected_login, bool) or not isinstance(self.expected_login, int) or self.expected_login <= 0:
            raise SafetyStop("expected_demo_login_required")
        if (isinstance(self.session_offset_minutes, bool) or
                not isinstance(self.session_offset_minutes, int) or
                not -720 <= self.session_offset_minutes <= 840):
            raise SafetyStop("verified_session_offset_required")
        if self.mode not in ("observe", "armed"):
            raise SafetyStop("invalid_mode")
        if self.risk_fraction not in (.01, .02, .03, .04, .05, .075):
            raise SafetyStop("risk_must_be_at_most_7p5_percent")
        if self.capital_cap != 50 or self.max_margin_fraction != .25 or self.daily_loss_fraction != .15:
            raise SafetyStop("fixed_demo_limits_changed")
        if (self.slippage_per_ounce != .03 or self.commission_per_lot_per_side != 0 or
                self.max_tick_age_seconds != 10 or self.max_decision_age_seconds != 30 or
                self.poll_seconds != 2):
            raise SafetyStop("fixed_execution_assumptions_changed")

    @property
    def fingerprint(self):
        values = [BRIDGE_VERSION, VERSION, self.expected_login,
                  self.session_offset_minutes, self.risk_fraction, self.capital_cap]
        return hashlib.sha256(json.dumps(values).encode()).hexdigest()


def verify_account(api, config, armed=False):
    account, terminal = api.account_info(), api.terminal_info()
    if account is None or terminal is None:
        raise SafetyStop("account_or_terminal_unavailable")
    if account.trade_mode != api.ACCOUNT_TRADE_MODE_DEMO:
        raise SafetyStop("demo_account_required")
    if account.login != config.expected_login:
        raise SafetyStop("unexpected_account")
    if account.currency != "USD":
        raise SafetyStop("usd_account_required")
    if account.margin_mode != api.ACCOUNT_MARGIN_MODE_RETAIL_HEDGING:
        raise SafetyStop("hedging_account_required")
    if not terminal.connected:
        raise SafetyStop("terminal_disconnected")
    if not all(finite(getattr(account, key, None)) for key in ("balance", "equity", "margin_free", "margin")):
        raise SafetyStop("invalid_account_values")
    if armed and (not account.trade_allowed or not account.trade_expert or
                  not terminal.trade_allowed or terminal.tradeapi_disabled):
        raise SafetyStop("algorithmic_trading_disabled")
    return account


def verify_symbol(api, info, entry=True):
    if info is None or info.name != SYMBOL:
        raise SafetyStop("exact_xauusd_required")
    if info.trade_exemode not in (api.SYMBOL_TRADE_EXECUTION_INSTANT, api.SYMBOL_TRADE_EXECUTION_REQUEST):
        raise SafetyStop("unsupported_execution_mode")
    if entry and info.trade_mode != api.SYMBOL_TRADE_MODE_FULL:
        raise SafetyStop("symbol_not_fully_tradeable")
    if info.chart_mode != api.SYMBOL_CHART_MODE_BID:
        raise SafetyStop("bid_chart_required")
    if entry and (info.order_mode & 49) != 49:  # MARKET | SL | TP
        raise SafetyStop("market_sl_tp_required")
    for name in ("point", "trade_tick_size", "volume_min", "volume_max", "volume_step"):
        if not finite(getattr(info, name, None)) or getattr(info, name) <= 0:
            raise SafetyStop("invalid_symbol_dimensions")
    if info.volume_max < info.volume_min or not finite(info.trade_stops_level) or info.trade_stops_level < 0:
        raise SafetyStop("invalid_symbol_limits")


def verify_tick(tick, now_utc, config):
    if tick is None or not all(finite(getattr(tick, key, None)) for key in ("bid", "ask", "time")):
        raise SafetyStop("tick_unavailable")
    if not 0 < tick.bid <= tick.ask:
        raise SafetyStop("invalid_bid_ask")
    if not 0 <= now_utc - tick.time <= config.max_tick_age_seconds:
        raise SafetyStop("stale_or_future_tick")


def floor_step(value, step):
    if not finite(value) or value <= 0:
        return 0.0
    return float((Decimal(str(value)) / Decimal(str(step))).to_integral_value(
        rounding=ROUND_FLOOR) * Decimal(str(step)))


def grid(value, step, upward):
    return float((Decimal(str(value)) / Decimal(str(step))).to_integral_value(
        rounding=ROUND_CEILING if upward else ROUND_FLOOR) * Decimal(str(step)))


def make_plan(api, config, account, info, tick, side, atr, loss_streak=0):
    """Size with broker profit/margin estimates, floor volume and recheck it.

    Current Bid/Ask replace the simulator's prior-bar spread approximation.
    SL is never moved inward just to make minimum lot fit the budget.
    """
    verify_symbol(api, info)
    if side not in (-1, 1) or not finite(atr) or atr <= 0:
        raise SafetyStop("invalid_signal_or_atr")
    if loss_streak >= 3:
        raise SafetyStop("loss_streak_freeze")
    cash = min(account.balance, account.equity, config.capital_cap)
    if cash <= 0 or account.margin_free <= 0:
        raise SafetyStop("nonpositive_available_capital")
    budget = cash * config.risk_fraction * (.5 if loss_streak >= 2 else 1)
    action = api.ORDER_TYPE_BUY if side == 1 else api.ORDER_TYPE_SELL
    reference = tick.ask if side == 1 else tick.bid
    liquidation = tick.bid if side == 1 else tick.ask
    distance = max(2.2 * atr, 10 * info.trade_tick_size)
    stop = grid(reference - side * distance, info.trade_tick_size, side == -1)
    distance = abs(reference - stop)
    target = grid(reference + side * distance * 2.2, info.trade_tick_size, side == -1)
    stop_floor = info.trade_stops_level * info.point
    if (side * (liquidation - stop) <= 0 or
            side * (liquidation - stop) < stop_floor or
            side * (target - liquidation) < stop_floor):
        raise SafetyStop("spread_or_broker_stop_limit")
    adverse_entry = reference + side * config.slippage_per_ounce
    adverse_exit = stop - side * config.slippage_per_ounce
    if min(stop, target, adverse_entry, adverse_exit) <= 0:
        raise SafetyStop("invalid_protective_price")

    def risk(volume):
        value = api.order_calc_profit(action, SYMBOL, volume, adverse_entry, adverse_exit)
        if not finite(value) or value >= 0:
            raise SafetyStop("broker_profit_calculation_failed")
        return -float(value) + 2 * volume * config.commission_per_lot_per_side

    min_risk = risk(info.volume_min)
    if min_risk > budget:
        raise SafetyStop("min_lot")
    lots = floor_step(min(info.volume_max, budget / min_risk * info.volume_min), info.volume_step)
    if lots < info.volume_min:
        raise SafetyStop("min_lot")
    planned_risk = risk(lots)
    if planned_risk > budget + 1e-9:
        raise SafetyStop("risk_budget_exceeded")
    margin = api.order_calc_margin(action, SYMBOL, lots, adverse_entry)
    if not finite(margin) or margin < 0:
        raise SafetyStop("broker_margin_calculation_failed")
    margin_cap = min(cash * config.max_margin_fraction, account.margin_free)
    if margin > margin_cap:
        lots = floor_step(lots * margin_cap / margin, info.volume_step)
        if lots < info.volume_min:
            raise SafetyStop("margin")
        margin = api.order_calc_margin(action, SYMBOL, lots, adverse_entry)
        planned_risk = risk(lots)
        if not finite(margin) or margin < 0 or margin > margin_cap or planned_risk > budget + 1e-9:
            raise SafetyStop("margin_or_risk_recheck_failed")
    return {"side": side, "price": reference, "sl": stop, "tp": target,
            "volume": lots, "budget": budget, "planned_risk": planned_risk,
            "minimum_lot_risk": min_risk, "margin": float(margin), "atr": float(atr)}


def fresh_decision(signal_row, current_bar_epoch, now_utc, config):
    if not 0 <= now_utc - current_bar_epoch <= config.max_decision_age_seconds:
        raise SafetyStop("late_or_future_decision")
    decision = pd.Timestamp(current_bar_epoch, unit="s") + pd.Timedelta(minutes=config.session_offset_minutes)
    if signal_row.name + pd.Timedelta(minutes=5) != decision or signal_row.decision_time != decision:
        raise SafetyStop("closed_m5_not_adjacent")
    if not bool(signal_row.ready):
        raise SafetyStop("warmup")
    for prefix, minutes in (("m15", 15), ("h1", 60)):
        closed = signal_row[f"htf_{prefix}_close"]
        if pd.isna(closed) or not pd.Timedelta(0) <= decision - closed < pd.Timedelta(minutes=minutes):
            raise SafetyStop("stale_or_future_htf")


def atomic_json(path, value):
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
    os.replace(temp, path)


class ProcessLock:
    """OS lock survives no process; a leftover filename cannot trigger a replay."""
    def __init__(self, path):
        self.file = path.open("a+b")
        try:
            if self.file.seek(0, 2) == 0:
                self.file.write(b"0"); self.file.flush()
            self.file.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.file.close()
            raise SafetyStop("another_runner_owns_state") from exc

    def close(self):
        self.file.close()


class StateStore:
    def __init__(self, directory, fingerprint, now):
        self.directory = Path(directory).resolve()
        if self.directory == REPO or REPO in self.directory.parents:
            raise SafetyStop("runtime_state_must_be_outside_repository")
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = ProcessLock(self.directory / "runner.lock")
        self.path = self.directory / "state.json"
        self.journal_path = self.directory / "journal.jsonl"
        try:
            if self.path.exists():
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
                if self.data.get("fingerprint") != fingerprint or self.data.get("schema") != 1:
                    raise SafetyStop("runtime_identity_or_config_changed")
            else:
                if self.journal_path.exists():
                    raise SafetyStop("state_missing_with_existing_journal")
                start = datetime.fromtimestamp(now, UTC).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=180)
                self.data = {"schema": 1, "fingerprint": fingerprint, "created_utc": now,
                             "history_start_utc": int(start.timestamp()), "first_bars": {},
                             "last_decision": 0, "last_close_bar": 0, "day": None,
                             "day_start_balance": None, "day_realized_pnl": 0.0,
                             "daily_blocked": False, "loss_streak": 0,
                             "pending": None, "positions": {}, "outcomes": {}, "signal": None}
                self.save()
        except Exception:
            self.lock.close()
            raise

    def save(self):
        atomic_json(self.path, self.data)

    def event(self, now, event, reason, **values):
        # Callers pass explicit numeric/status fields, never namedtuple._asdict().
        record = {"utc": datetime.fromtimestamp(now, UTC).isoformat(),
                  "event": event, "reason": reason, **values}
        with self.journal_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, allow_nan=False) + "\n")
            handle.flush(); os.fsync(handle.fileno())

    def close(self):
        self.lock.close()


class Runner:
    def __init__(self, api, config, store, clock=time.time):
        self.api, self.config, self.store, self.clock = api, config, store, clock
        self.session_id = str(uuid.uuid4())
        self.session_started = utc_iso(clock())
        self.sequence = 0

    @property
    def state(self):
        return self.store.data

    def broker_positions(self):
        positions, orders = self.api.positions_get(), self.api.orders_get()
        if positions is None or orders is None:
            raise SafetyStop("positions_or_orders_unavailable")
        return list(positions), list(orders)

    def session_time(self, epoch):
        return datetime.fromtimestamp(epoch, UTC) + timedelta(minutes=self.config.session_offset_minutes)

    def publish(self, status, reason, account=None, tick=None):
        now = self.clock()
        self.sequence += 1
        quote = None
        if tick is not None:
            quote = {"symbol": SYMBOL, "bid": float(tick.bid), "ask": float(tick.ask),
                     "changedAtUtc": utc_iso(tick.time)}
        terminal = self.api.terminal_info()
        verified = account is not None and account.trade_mode == self.api.ACCOUNT_TRADE_MODE_DEMO
        payload = {"schemaVersion": 1, "mode": "demo", "sessionId": self.session_id,
                   "sessionStartedAt": self.session_started, "sequence": self.sequence,
                   "producedAt": utc_iso(now), "quote": quote if verified else None,
                   "status": {"terminalConnected": bool(terminal and terminal.connected),
                       "algoTradingEnabled": bool(terminal and terminal.trade_allowed and not terminal.tradeapi_disabled),
                       "eaRunning": status == "running", "demoVerified": verified},
                   "account": None, "positions": [],
                   "strategy": {"name": "VORTEX", "version": VERSION, "state": status,
                       "reason": reason, "runnerMode": self.config.mode}}
        if self.state["signal"] is not None:
            payload["signal"] = self.state["signal"]
        if verified:
            payload["account"] = {"currency": "USD", "equity": float(account.equity),
                "balance": float(account.balance), "freeMargin": float(account.margin_free),
                "margin": float(account.margin)}
            positions = self.api.positions_get()
            if positions is not None:
                for p in positions:
                    if str(p.identifier) not in self.state["positions"]:
                        continue
                    public_id = hashlib.sha256(f"{self.session_id}:{p.identifier}".encode()).hexdigest()
                    payload["positions"].append({"id": public_id, "side": "buy" if p.type == 0 else "sell",
                        "lots": float(p.volume), "openPrice": float(p.price_open),
                        "currentPrice": float(p.price_current), "stopLoss": float(p.sl) if p.sl > 0 else None,
                        "takeProfit": float(p.tp) if p.tp > 0 else None, "profit": float(p.profit)})
        atomic_json(self.store.directory / "status.json", payload)

    def owned_positions(self, positions):
        owned = []
        for p in positions:
            ident = str(p.identifier)
            known = self.state["positions"].get(ident)
            if p.magic == MAGIC and p.symbol == SYMBOL and known is None:
                raise SafetyStop("untracked_bot_position")
            if known is not None:
                if (p.symbol != SYMBOL or p.magic != MAGIC or p.ticket != known["ticket"] or
                        p.type != known["type"] or abs(p.volume - known["volume"]) > 1e-9 or
                        abs(p.sl - known["sl"]) > 1e-8 or abs(p.tp - known["tp"]) > 1e-8):
                    raise SafetyStop("owned_position_changed_externally")
                owned.append(p)
        if len(owned) > 1:
            raise SafetyStop("multiple_bot_positions")
        return owned

    def reconcile_closed(self, positions, now):
        open_ids = {str(p.identifier) for p in positions}
        for ident, known in list(self.state["positions"].items()):
            if ident in open_ids:
                continue
            deals = self.api.history_deals_get(position=int(ident))
            if not deals:
                raise SafetyStop("closed_position_history_unavailable")
            entries = [d for d in deals if d.entry == self.api.DEAL_ENTRY_IN]
            exits = [d for d in deals if d.entry in (self.api.DEAL_ENTRY_OUT, self.api.DEAL_ENTRY_OUT_BY)]
            if (not entries or not exits or any(d.symbol != SYMBOL for d in deals) or
                    any(d.magic != MAGIC for d in entries) or
                    abs(sum(d.volume for d in entries) - sum(d.volume for d in exits)) > 1e-9 or
                    any(not all(finite(getattr(d, k, None)) for k in ("profit", "commission", "swap", "fee")) for d in deals)):
                raise SafetyStop("closed_position_history_ambiguous")
            pnl = sum(d.profit + d.commission + d.swap + d.fee for d in deals)
            closed = max(d.time for d in exits)
            if ident not in self.state["outcomes"]:
                if self.session_time(closed).date().isoformat() == self.state["day"]:
                    self.state["loss_streak"] = self.state["loss_streak"] + 1 if pnl < -1e-9 else 0
                    self.state["day_realized_pnl"] += pnl
                self.state["outcomes"][ident] = {"net_pnl": pnl, "closed_utc": closed}
                self.state["last_close_bar"] = max(self.state["last_close_bar"], int(closed // 300 * 300))
                self.store.event(now, "closed", "broker_history_reconciled", net_pnl=pnl)
            del self.state["positions"][ident]
            self.store.save()

    def _send(self, request, kind, context):
        """One submission only. Unknown/partial outcome deliberately stays pending."""
        if self.config.mode != "armed":
            raise SafetyStop("observe_mode_cannot_send")
        if self.state["pending"] is not None:
            raise SafetyStop("unresolved_order_intent")
        if kind not in ("entry", "close"):
            raise SafetyStop("invalid_order_intent_kind")
        if (request.get("action") != self.api.TRADE_ACTION_DEAL or request.get("magic") != MAGIC or
                request.get("type_filling") != self.api.ORDER_FILLING_FOK or
                request.get("type") not in (self.api.ORDER_TYPE_BUY, self.api.ORDER_TYPE_SELL) or
                not finite(request.get("volume")) or request["volume"] <= 0 or
                not finite(request.get("price")) or request["price"] <= 0):
            raise SafetyStop("invalid_market_order_request")
        if kind == "entry" and (not finite(context.get("decision")) or
                any(not finite(request.get(k)) or request[k] <= 0 for k in ("sl", "tp"))):
            raise SafetyStop("entry_needs_decision_and_protection")
        verify_account(self.api, self.config, armed=True)
        if request.get("symbol") != SYMBOL:
            raise SafetyStop("exact_xauusd_required")
        checked = self.api.order_check(request)
        if checked is None or checked.retcode != 0:
            raise SafetyStop("order_check_rejected")
        self.state["pending"] = {"kind": kind, "context": context, "request": request,
                                 "created_utc": self.clock()}
        self.store.save()
        self.store.event(self.clock(), "intent", kind)
        # User switching accounts after a check must never send into REAL.
        verify_account(self.api, self.config, armed=True)
        tick = self.api.symbol_info_tick(SYMBOL)
        verify_tick(tick, self.clock(), self.config)
        positions, orders = self.broker_positions()
        if kind == "entry" and (positions or orders):
            raise SafetyStop("exposure_changed_before_send")
        if kind == "close":
            owned = self.owned_positions(positions)
            if not any(p.ticket == request.get("position") and abs(p.volume - request["volume"]) < 1e-9 for p in owned):
                raise SafetyStop("ownership_changed_before_close")
        quote = tick.ask if request["type"] == self.api.ORDER_TYPE_BUY else tick.bid
        if abs(quote - request["price"]) > self.config.slippage_per_ounce:
            raise SafetyStop("quote_changed_before_send")
        if kind == "entry" and not 0 <= self.clock() - context["decision"] <= self.config.max_decision_age_seconds:
            raise SafetyStop("decision_expired_before_send")
        result = self.api.order_send(request)
        if result is None or result.retcode != self.api.TRADE_RETCODE_DONE:
            self.store.event(self.clock(), "halt", "ambiguous_or_non_done_order",
                             retcode=int(result.retcode) if result is not None else None)
            raise SafetyStop("order_outcome_requires_reconciliation")
        self.store.event(self.clock(), "accepted", kind, retcode=int(result.retcode))
        return result

    def close_position(self, position, reason, now):
        if self.config.mode == "observe":
            return "observe_would_close_" + reason
        verify_account(self.api, self.config, armed=True)
        positions, _ = self.broker_positions()
        owned = self.owned_positions(positions)
        current = next((p for p in owned if p.identifier == position.identifier), None)
        if current is None:
            raise SafetyStop("close_position_no_longer_owned")
        info, tick = self.api.symbol_info(SYMBOL), self.api.symbol_info_tick(SYMBOL)
        verify_symbol(self.api, info, entry=False); verify_tick(tick, self.clock(), self.config)
        buy = current.type == self.api.POSITION_TYPE_BUY
        request = {"action": self.api.TRADE_ACTION_DEAL, "symbol": SYMBOL,
                   "position": current.ticket, "volume": current.volume,
                   "type": self.api.ORDER_TYPE_SELL if buy else self.api.ORDER_TYPE_BUY,
                   "price": tick.bid if buy else tick.ask, "deviation": int(.03 / info.point),
                   "magic": MAGIC, "comment": "VORTEX demo close",
                   "type_time": self.api.ORDER_TIME_GTC, "type_filling": self.api.ORDER_FILLING_FOK}
        self._send(request, "close", {"position_id": current.identifier, "reason": reason})
        positions, _ = self.broker_positions()
        if any(p.identifier == current.identifier for p in positions):
            raise SafetyStop("close_not_confirmed")
        self.state["pending"] = None
        self.state["last_close_bar"] = int(now // 300 * 300)
        self.store.save()
        self.reconcile_closed(positions, now)
        return "closed_" + reason

    def load_signal(self, current_bar_epoch):
        frames = {}
        for label, minutes, enum in (("M5", 5, self.api.TIMEFRAME_M5),
                                     ("M15", 15, self.api.TIMEFRAME_M15),
                                     ("H1", 60, self.api.TIMEFRAME_H1)):
            raw = self.api.copy_rates_range(SYMBOL, enum,
                datetime.fromtimestamp(self.state["history_start_utc"], UTC),
                datetime.fromtimestamp(current_bar_epoch - 1, UTC))
            if raw is None or len(raw) == 0:
                raise SafetyStop("history_unavailable")
            frame = pd.DataFrame(raw)
            frame = frame.loc[frame.time + minutes * 60 <= current_bar_epoch].copy()
            if len(frame) < 220:
                raise SafetyStop("history_warmup_insufficient")
            if not frame.time.is_monotonic_increasing or not frame.time.is_unique:
                raise SafetyStop("history_order_invalid")
            first = int(frame.time.iloc[0])
            if label in self.state["first_bars"] and first != self.state["first_bars"][label]:
                raise SafetyStop("history_seed_boundary_changed")
            self.state["first_bars"][label] = first
            frame.index = (pd.DatetimeIndex(pd.to_datetime(frame.pop("time"), unit="s", utc=True)).tz_localize(None) +
                           pd.Timedelta(minutes=self.config.session_offset_minutes))
            frame.index.name = "bar_open_server"
            frame = frame.rename(columns={"spread": "spread_points"})
            frame["timezone"], frame["symbol"], frame["timeframe"] = TIME_BASIS, SYMBOL, label
            frames[label] = frame
        result = build_signals(frames["M5"], frames["M15"], frames["H1"]).iloc[-1]
        if bool(result.ready):
            self.state["signal"] = {"decisionTimeServer": result.decision_time.isoformat(),
                "sessionUtcOffsetMinutes": self.config.session_offset_minutes,
                "ready": True, "direction": int(result.signal), "atr": float(result.atr),
                "consensus": float(result.consensus),
                "scores": {k: float(result[k]) for k in ("orion", "vortex", "nova", "luna", "kira", "atlas")}}
        else:
            self.state["signal"] = {"ready": False}
        self.store.save()
        return result

    def enter(self, row, current_bar_epoch, now):
        # The latest requested EXTREME strategy has not been implemented. These
        # old research signals may be observed but cannot authorize an entry.
        if self.config.mode == "armed":
            raise SafetyStop("legacy_signal_observe_only_extreme_pending")
        account = verify_account(self.api, self.config, armed=self.config.mode == "armed")
        positions, orders = self.broker_positions()
        if positions or orders:
            raise SafetyStop("existing_positions_or_orders")
        tick, info = self.api.symbol_info_tick(SYMBOL), self.api.symbol_info(SYMBOL)
        verify_tick(tick, self.clock(), self.config)
        fresh_decision(row, current_bar_epoch, self.clock(), self.config)
        plan = make_plan(self.api, self.config, account, info, tick,
                         int(row.signal), float(row.atr), self.state["loss_streak"])
        if self.config.mode == "observe":
            self.store.event(now, "observe", "eligible_demo_entry", **plan)
            return "observe_eligible_demo_entry"
        request = {"action": self.api.TRADE_ACTION_DEAL, "symbol": SYMBOL,
                   "type": self.api.ORDER_TYPE_BUY if plan["side"] == 1 else self.api.ORDER_TYPE_SELL,
                   "volume": plan["volume"], "price": plan["price"], "sl": plan["sl"], "tp": plan["tp"],
                   "deviation": int(self.config.slippage_per_ounce / info.point), "magic": MAGIC,
                   "comment": f"VXdemo{int(current_bar_epoch)}", "type_time": self.api.ORDER_TIME_GTC,
                   "type_filling": self.api.ORDER_FILLING_FOK}
        self._send(request, "entry", {"decision": current_bar_epoch, "plan": plan})
        positions, orders = self.broker_positions()
        matched = [p for p in positions if p.symbol == SYMBOL and p.magic == MAGIC and p.comment == request["comment"]]
        if len(matched) != 1 or orders:
            raise SafetyStop("entry_position_not_confirmed")
        p = matched[0]
        if (abs(p.volume - plan["volume"]) > 1e-9 or abs(p.sl - plan["sl"]) > 1e-8 or
                abs(p.tp - plan["tp"]) > 1e-8):
            raise SafetyStop("entry_protection_not_confirmed")
        self.state["positions"][str(p.identifier)] = {"ticket": p.ticket, "type": p.type,
            "volume": p.volume, "sl": p.sl, "tp": p.tp, "opened_utc": p.time,
            "budget": plan["budget"], "planned_risk": plan["planned_risk"]}
        self.state["pending"] = None
        self.store.save()
        return "demo_entry_confirmed"

    def step(self):
        now = self.clock()
        account = verify_account(self.api, self.config, armed=self.config.mode == "armed")
        positions, orders = self.broker_positions()
        if self.state["pending"] is not None:
            raise SafetyStop("unresolved_order_intent")
        owned = self.owned_positions(positions)
        self.reconcile_closed(positions, now)
        local = self.session_time(now)
        day = local.date().isoformat()
        if self.state["day"] != day:
            if owned:
                status = self.close_position(owned[0], "date_change", now)
                self.publish("running", status, account); return status
            self.state.update(day=day, day_start_balance=min(account.balance, account.equity, 50),
                              day_realized_pnl=0.0, daily_blocked=False, loss_streak=0)
            self.store.save()
            self.store.event(now, "day", "baseline_set", balance=float(account.balance))
        floating = sum(p.profit + p.swap for p in owned)
        allocated_loss = self.state["day_realized_pnl"] + floating
        if allocated_loss <= -self.state["day_start_balance"] * self.config.daily_loss_fraction:
            self.state["daily_blocked"] = True; self.store.save()
        tick = self.api.symbol_info_tick(SYMBOL)
        verify_tick(tick, now, self.config)
        if owned:
            p = owned[0]
            reason = ("daily_loss" if self.state["daily_blocked"] else
                      "session_end" if not 8 <= local.hour < 18 else
                      "max_holding_time" if now - p.time >= 180 * 60 else None)
            status = self.close_position(p, reason, now) if reason else "bot_position_open"
            self.publish("running", status, account, tick); return status
        current = self.api.copy_rates_from_pos(SYMBOL, self.api.TIMEFRAME_M5, 0, 1)
        if current is None or len(current) != 1:
            raise SafetyStop("current_bar_unavailable")
        bar = int(current[0]["time"])
        if bar <= self.state["last_decision"]:
            self.publish("running", "waiting_new_m5", account, tick); return "waiting_new_m5"
        row = self.load_signal(bar)
        # Persist before *any* entry attempt: crashes cannot replay this decision.
        self.state["last_decision"] = bar; self.store.save()
        try:
            fresh_decision(row, bar, self.clock(), self.config)
            if positions or orders:
                raise SafetyStop("existing_positions_or_orders")
            if self.state["daily_blocked"]:
                raise SafetyStop("daily_loss_limit")
            if self.state["loss_streak"] >= 3:
                raise SafetyStop("loss_streak_freeze")
            if not 8 <= local.hour < 18:
                raise SafetyStop("session_closed")
            if bar <= self.state["last_close_bar"]:
                raise SafetyStop("same_bar_exit")
            if int(row.signal) == 0:
                raise SafetyStop("no_signal")
            status = self.enter(row, bar, now)
        except SafetyStop as error:
            if self.state["pending"] is not None:
                raise
            status = str(error)
            self.store.event(now, "skip", status)
        self.publish("running", status, account, tick)
        return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("observe", "armed"), default="observe")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--risk", type=float, default=.03, choices=(.01, .02, .03, .04, .05, .075))
    args = parser.parse_args()
    if args.mode == "armed":
        parser.error("EXTREME integration is pending. This scaffold may only observe the old v0.1 research signals.")
    try:
        config = Config(expected_login=int(os.environ["VORTEX_EXPECTED_LOGIN"]),
                        session_offset_minutes=int(os.environ["VORTEX_SESSION_UTC_OFFSET_MINUTES"]),
                        mode=args.mode, risk_fraction=args.risk)
        directory = Path(os.environ["VORTEX_STATE_DIR"])
    except (KeyError, ValueError):
        parser.error("Set private VORTEX_EXPECTED_LOGIN, VORTEX_SESSION_UTC_OFFSET_MINUTES and VORTEX_STATE_DIR.")
    if sys.platform != "win32":
        parser.error("Broker integration runs only on Windows; synthetic tests are cross-platform.")
    import MetaTrader5 as mt5
    store = StateStore(directory, config.fingerprint, time.time())
    runner = Runner(mt5, config, store)
    try:
        # Explicit optional path targets the installed terminal, never a login.
        terminal_path = os.environ.get("VORTEX_TERMINAL_PATH")
        connected = mt5.initialize(terminal_path, timeout=10000) if terminal_path else mt5.initialize(timeout=10000)
        if not connected:
            raise SafetyStop("mt5_initialize_failed")
        while True:
            if (store.directory / "STOP").exists():
                runner.publish("stopped", "operator_stop_file")
                break
            status = runner.step()
            print(f"{datetime.now(UTC).isoformat(timespec='seconds')} {config.mode}: {status}", flush=True)
            if args.once:
                break
            time.sleep(config.poll_seconds)
    except SafetyStop as error:
        runner.publish("halted", str(error))
        store.event(time.time(), "halt", str(error))
        print(f"VORTEX halted: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        runner.publish("stopped", "operator_stop")
    except Exception:
        runner.publish("halted", "unexpected_error_review_private_runtime")
        print("VORTEX halted: unexpected error; review private runtime.", file=sys.stderr)
        return 3
    finally:
        mt5.shutdown(); store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
