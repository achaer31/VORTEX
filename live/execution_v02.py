"""Inert-by-default DEMO manager, used by the separate run_demo_v02.py CLI.

Only an explicitly approved caller may inject an MT5-compatible broker. The
read-only Observer remains unchanged. Every mutation re-verifies DEMO identity.
Frozen research risk/mode/grid/exit-allocation rules are imported, never edited.

Partial policy uses three independently protected hedging tickets: 25% TP1,
25% TP2, 50% SL-only runner. Runner TP=0 is intentional and confirmed, since the
frozen rule has no fixed runner target. Sequential submissions are not atomic:
any uncertain/incomplete group freezes entries; accepted tickets retain SL.

Limitations: no automatic approval, midnight floating-equity reconstruction,
unexplained cashflows, netting, IOC/partial-fill top-up, broker-side trailing,
or recovery from unprovable outcomes. Such states require review. Stops cannot
guarantee fills through gaps/outages. See official API semantics:
https://www.mql5.com/en/docs/python_metatrader5/mt5ordersend_py
https://www.mql5.com/en/docs/python_metatrader5/mt5historydealsget_py
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
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
sys.path.insert(0, str(REPO / "research_v02"))
from vortex_v02.risk import BrokerSpec, exact_parts, floor_step, tick_price, mode_gate
from vortex_v02.engines import mode_from_scores, WEIGHTS

SYMBOL, MAGIC, MODEL = "XAUUSD", 26091402, "VORTEX-XAU-EXTREME-v0.2"
UTC = timezone.utc


class ExecutionStop(RuntimeError):
    """Machine reason only; do not expose broker/account objects in public logs."""


def finite(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def require(ok, reason):
    if not ok:
        raise ExecutionStop(reason)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


@dataclass(frozen=True)
class Config:
    expected_login: int
    history_origin_utc: float  # Verified earlier than initial funding; never guessed.
    baseline_approved: bool = False
    manual_approved: bool = False
    costs_verified: bool = False
    slippage: float = .03
    commission_per_lot_side: float = 0.0

    def __post_init__(self):
        require(isinstance(self.expected_login, int) and not isinstance(self.expected_login, bool)
                and self.expected_login > 0, "expected_demo_login_required")
        require(finite(self.history_origin_utc) and self.history_origin_utc > 0, "verified_history_origin_required")
        require(all(type(v) is bool for v in (self.baseline_approved, self.manual_approved, self.costs_verified)), "boolean_approval_required")
        require(finite(self.slippage) and self.slippage >= .03 and
                finite(self.commission_per_lot_side) and self.commission_per_lot_side >= 0, "invalid_cost_reserve")

    @property
    def approved(self):
        return self.baseline_approved and self.manual_approved and self.costs_verified

    @property
    def fingerprint(self):
        fields = asdict(self)
        for key in ("baseline_approved", "manual_approved", "costs_verified"):
            fields.pop(key)
        fields["model"] = MODEL
        fields["source_hashes"] = {p: hashlib.sha256((REPO / p).read_bytes()).hexdigest() for p in
            ("research_v02/SPEC.md", "research_v02/vortex_v02/risk.py", "research_v02/vortex_v02/engines.py")}
        return hashlib.sha256(canonical(fields)).hexdigest()


class Store:
    """Private hash-chained full-state journal + OS single-writer lock.

    Each intent is fsynced before submission. A torn last record blocks startup;
    it is never discarded to make the manager run. Hashes detect corruption,
    not an attacker rewriting the whole private directory.
    """
    def __init__(self, directory, config):
        self.directory = Path(directory).resolve()
        require(self.directory != REPO and REPO not in self.directory.parents, "private_state_outside_repository_required")
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = (self.directory / "execution-v02.lock").open("a+b")
        try:
            self.lock.seek(0, 2)
            if self.lock.tell() == 0:
                self.lock.write(b"0"); self.lock.flush()
            self.lock.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.lock.close(); raise ExecutionStop("execution_already_running") from None
        self.path = self.directory / "execution-v02.jsonl"
        marker = self.directory / "execution-v02.created"
        self.previous = "0" * 64
        self.data = None
        try:
            if self.path.exists():
                for raw in self.path.read_bytes().splitlines(keepends=True):
                    require(raw.endswith(b"\n"), "torn_execution_journal")
                    record = json.loads(raw)
                    digest = record.pop("sha256")
                    require(record["previous"] == self.previous and hashlib.sha256(canonical(record)).hexdigest() == digest,
                            "execution_journal_corrupt")
                    self.previous, self.data = digest, record["state"]
                require(self.data is not None and self.data["fingerprint"] == config.fingerprint, "execution_identity_changed")
            else:
                require(not marker.exists(), "execution_journal_missing")
                marker.write_text("Private execution state has been initialized.\n")
                self.data = {"schema": 1, "fingerprint": config.fingerprint, "pending": None,
                    "campaign": None, "positions": {}, "outcomes": [], "loss_streak": 0,
                    "frozen": False, "day": None, "day_start": None, "daily_killed": False,
                    "extreme_disabled": False, "last_decision": 0, "last_exit_bar": 0,
                    "last_clock": 0, "opening": False, "ledger_hash": None}
                self.save("initialize")
        except Exception:
            self.lock.close(); raise

    def save(self, event):
        record = {"previous": self.previous, "event": event, "state": self.data}
        digest = hashlib.sha256(canonical(record)).hexdigest()
        with self.path.open("ab") as stream:
            stream.write(canonical(dict(record, sha256=digest)) + b"\n")
            stream.flush(); os.fsync(stream.fileno())
        self.previous = digest

    def close(self):
        self.lock.close()


@dataclass(frozen=True)
class Decision:
    """Pure observer boundary: completed M5 row plus verified HTF availability."""
    bar_open: float
    row: dict
    available: dict
    spec_sha256: str

    @classmethod
    def from_observer(cls, observation):
        row = observation["row"]
        index = pd.Timestamp(row.name)
        require(index.tz is not None, "decision_utc_required")
        available = {}
        for tf in ("M5", "M15", "H1", "H4"):
            value = pd.Timestamp(observation["sources"][tf]["latestAvailableAtUtc"])
            require(value.tz is not None, "source_utc_required")
            available[tf] = value.timestamp()
        return cls(index.timestamp(), row.to_dict(), available, observation["specSha256"])

    @property
    def closed_at(self):
        return self.bar_open + 300

    def validate(self, now, entry=True):
        require(finite(self.bar_open) and self.bar_open % 300 == 0 and
                0 <= now - self.closed_at <= 30, "late_or_nonadjacent_decision")
        require(self.spec_sha256 == hashlib.sha256((REPO / "research_v02/SPEC.md").read_bytes()).hexdigest(), "decision_spec_mismatch")
        for tf, seconds in (("M5", 300), ("M15", 900), ("H1", 3600), ("H4", 14400)):
            age = self.closed_at - self.available.get(tf, math.nan)
            require(finite(age) and 0 <= age < seconds, "stale_or_future_" + tf.lower())
        require(self.available["M5"] == self.closed_at, "closed_m5_not_adjacent")
        for key in ("close", "atr"):
            require(finite(float(self.row.get(key, math.nan))) and self.row[key] > 0, "invalid_decision_price")
        if entry:
            require(self.row.get("ready") == True and self.row.get("execution_valid") == True and
                    self.row.get("news_blocked") == False, "entry_inputs_invalid")
            scores = {k: float(self.row.get(k, math.nan)) for k in ("orion", "vortex", "nova", "luna", "kira", "atlas", "consensus")}
            expected = sum(WEIGHTS[k] * scores[k] for k in WEIGHTS if k != "kira") / .90 * (.90 + .10 * scores["kira"] / 100)
            require(abs(expected - scores["consensus"]) < 1e-7, "consensus_mismatch")
            mode, direction = mode_from_scores(scores, self.row.get("h1_alignment"), self.row.get("h4_alignment"),
                                                self.row.get("session_ideal", False), True)
            require(mode != "FROZEN" and mode == self.row.get("mode") and direction == self.row.get("signal"), "independent_voting_gate")
        return self


class Manager:
    def __init__(self, broker, config, store, clock=time.time):
        self.api, self.config, self.store, self.clock = broker, config, store, clock
        self.state = store.data
        require(self.state["fingerprint"] == config.fingerprint, "execution_identity_changed")

    def account(self, mutation=False):
        a, t = self.api.account_info(), self.api.terminal_info()
        require(a is not None and t is not None, "account_or_terminal_unavailable")
        require(a.trade_mode == self.api.ACCOUNT_TRADE_MODE_DEMO, "real_account_rejected")
        require(a.login == self.config.expected_login, "account_changed")
        require(a.currency == "USD" and a.margin_mode == self.api.ACCOUNT_MARGIN_MODE_RETAIL_HEDGING, "usd_hedging_required")
        require(t.connected, "broker_disconnected")
        require(all(finite(float(getattr(a, k, math.nan))) for k in ("balance", "equity", "margin_free", "margin")), "account_values_invalid")
        if mutation:
            require(self.config.approved, "baseline_manual_or_cost_gate_blocked")
            require(a.trade_allowed and a.trade_expert and t.trade_allowed and not t.tradeapi_disabled, "algo_disabled")
        return a

    def market(self):
        self.account()
        info, tick = self.api.symbol_info(SYMBOL), self.api.symbol_info_tick(SYMBOL)
        require(info is not None and info.name == SYMBOL and info.chart_mode == self.api.SYMBOL_CHART_MODE_BID,
                "xauusd_bid_metadata_required")
        require(info.trade_exemode in (self.api.SYMBOL_TRADE_EXECUTION_INSTANT, self.api.SYMBOL_TRADE_EXECUTION_REQUEST), "fok_execution_unsupported")
        require((info.order_mode & 49) == 49, "market_sl_tp_required")
        for k in ("point", "trade_tick_size", "trade_contract_size", "volume_min", "volume_step", "volume_max"):
            require(finite(float(getattr(info, k, math.nan))) and getattr(info, k) > 0, "symbol_dimensions_invalid")
        require(info.volume_min <= info.volume_max and info.trade_stops_level >= 0 and info.trade_freeze_level >= 0, "symbol_limits_invalid")
        require(tick is not None and all(finite(float(getattr(tick, k, math.nan))) for k in ("time", "bid", "ask")) and
                0 < tick.bid <= tick.ask and 0 <= self.clock() - tick.time <= 10, "stale_or_invalid_tick")
        return info, tick

    def exposures(self):
        self.account()
        positions, orders = self.api.positions_get(), self.api.orders_get()
        require(positions is not None and orders is not None, "exposure_unknown")
        return list(positions), list(orders)

    def profit(self, side, lots, entry, exit_price):
        self.account()
        result = self.api.order_calc_profit(self.api.ORDER_TYPE_BUY if side == 1 else self.api.ORDER_TYPE_SELL,
                                            SYMBOL, lots, entry, exit_price)
        require(finite(result), "broker_profit_unknown")
        return result

    def margin(self, side, lots, entry):
        self.account()
        result = self.api.order_calc_margin(self.api.ORDER_TYPE_BUY if side == 1 else self.api.ORDER_TYPE_SELL,
                                            SYMBOL, lots, entry)
        require(finite(result) and result >= 0, "broker_margin_unknown")
        return result

    def ledger(self, positions):
        """Prove capital and day-start balance from the full account deal ledger.

        All manual P/L is included. A position carried across midnight makes its
        floating midnight equity unknown; new entries remain frozen that day.
        """
        a = self.account(); now = self.clock()
        deals = self.api.history_deals_get(datetime.fromtimestamp(self.config.history_origin_utc, UTC), datetime.fromtimestamp(now, UTC))
        require(deals is not None and len(deals) > 0, "capital_history_unavailable")
        deals = sorted(deals, key=lambda d: (d.time, d.ticket))
        require(len({d.ticket for d in deals}) == len(deals), "duplicate_history")
        day = datetime.fromtimestamp(now, UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        day_epoch = day.timestamp(); initial = None; balance = 0.0; prior = 0.0
        volumes, midnight = {}, {}
        for d in deals:
            require(all(finite(float(getattr(d, k, math.nan))) for k in ("time", "profit", "commission", "swap", "fee", "volume")) and
                    self.config.history_origin_utc <= d.time <= now, "invalid_capital_history")
            net = d.profit + d.commission + d.swap + d.fee
            if d.type == self.api.DEAL_TYPE_BALANCE:
                require(initial is None and balance == 0 and 0 < net <= 50 and d.volume == 0, "external_capital_or_topup_unproven")
                initial = net
            else:
                require(initial is not None and d.type in (self.api.DEAL_TYPE_BUY, self.api.DEAL_TYPE_SELL) and
                        d.entry in (self.api.DEAL_ENTRY_IN, self.api.DEAL_ENTRY_OUT) and d.volume > 0, "unsupported_ledger_event")
                ident = str(d.position_id)
                change = d.volume if d.entry == self.api.DEAL_ENTRY_IN else -d.volume
                volumes[ident] = volumes.get(ident, 0) + change
                require(volumes[ident] >= -1e-8, "incomplete_position_history")
                if d.time < day_epoch:
                    midnight[ident] = midnight.get(ident, 0) + change
            balance += net
            if d.time < day_epoch:
                prior += net
        require(initial is not None and abs(balance - a.balance) <= .011, "cashflow_balance_mismatch")
        actual = {str(p.identifier): p.volume for p in positions}
        require(all(abs(v - actual.get(k, 0)) <= 1e-8 for k, v in volumes.items()) and
                all(abs(v - volumes.get(k, 0)) <= 1e-8 for k, v in actual.items()), "ledger_position_mismatch")
        # Funding on the account's first day is the anchor, not post-loss balance.
        anchor = prior if deals[0].time < day_epoch else initial
        known = not any(abs(v) > 1e-8 for v in midnight.values())
        if self.state["day"] != day.date().isoformat():
            self.state.update(day=day.date().isoformat(), day_start=anchor if known else None,
                              daily_killed=False, extreme_disabled=False)
        elif self.state["day_start"] is not None:
            require(known and abs(self.state["day_start"] - anchor) <= .011, "day_anchor_changed")
        if known and anchor > 0:
            dd = max(0, 1 - a.equity / anchor)
            self.state["extreme_disabled"] |= dd >= .10
            self.state["daily_killed"] |= dd >= .15
        self.state["ledger_hash"] = hashlib.sha256(canonical([[d.ticket, d.time, d.type, d.entry, d.volume,
            d.profit, d.commission, d.swap, d.fee] for d in deals])).hexdigest()
        self.store.save("ledger_reconciled")
        return deals

    def owned(self, positions, pending=False, allow_missing=False):
        result = {}
        for p in positions:
            known = self.state["positions"].get(str(p.identifier))
            if known is None:
                require(p.magic != MAGIC, "untracked_manager_position")
                continue
            require(p.symbol == SYMBOL and p.magic == MAGIC and p.ticket == known["ticket"] and
                    p.type == (0 if known["side"] == 1 else 1) and abs(p.volume - known["lots"]) < 1e-8 and
                    abs(p.price_open - known["entry"]) < 1e-8, "ownership_changed")
            if not pending:
                exact = abs(p.sl - known["sl"]) < 1e-8 and abs(p.tp - known["tp"]) < 1e-8 and p.sl > 0
                missing = (p.sl == 0 or known["side"] * (p.sl - known["sl"]) < -1e-8 or
                           (p.tp == 0 and known["tp"] > 0))
                require(exact or (allow_missing and missing),
                        "protection_changed_or_missing")
            result[str(p.identifier)] = p
        return result

    def closed_pnl(self, ident):
        self.account()
        deals = self.api.history_deals_get(position=int(ident))
        require(deals is not None and len(deals) > 0, "closure_history_unknown")
        entries = [d for d in deals if d.entry == self.api.DEAL_ENTRY_IN]
        exits = [d for d in deals if d.entry == self.api.DEAL_ENTRY_OUT]
        known = self.state["positions"][ident]
        require(entries and exits and all(d.symbol == SYMBOL and d.magic == MAGIC for d in entries) and
                all(d.entry in (self.api.DEAL_ENTRY_IN, self.api.DEAL_ENTRY_OUT) for d in deals) and
                abs(sum(d.volume for d in entries) - known["lots"]) < 1e-8 and
                abs(sum(d.volume for d in exits) - known["lots"]) < 1e-8,
                "partial_or_ambiguous_closure")
        require(all(all(finite(float(getattr(d, k, math.nan))) for k in ("profit", "commission", "swap", "fee")) for d in deals), "closure_costs_unknown")
        target_hit = all(getattr(d, "reason", None) == self.api.DEAL_REASON_TP for d in exits)
        return sum(d.profit + d.commission + d.swap + d.fee for d in deals), max(d.time for d in exits), target_hit

    def reconcile(self):
        positions, orders = self.exposures()
        pending = self.state["pending"]
        if pending:
            r, kind = pending["request"], pending["kind"]
            if kind == "entry":
                matches = [p for p in positions if p.symbol == SYMBOL and p.magic == MAGIC and p.comment == r["comment"]]
                require(len(matches) == 1, "unresolved_intent_no_retry")
                p = matches[0]
                require(abs(p.volume - r["volume"]) < 1e-8 and p.type == r["type"], "partial_or_unprotected_fill")
                # Establish immutable fill ownership even when protection was
                # dropped, so emergency close can address that exact ticket.
                leg = dict(pending["leg"], ticket=int(p.ticket), entry=float(p.price_open), sl=float(r["sl"]), tp=float(r["tp"]))
                require(abs(p.price_open - r["price"]) <= self.config.slippage + 1e-8, "fill_exceeded_reserve")
                leg["initial_r"] = leg["side"] * (p.price_open - r["sl"])
                require(.35 * leg["atr"] <= leg["initial_r"] <= 2.2 * leg["atr"] + 1e-8, "filled_stop_outside_atr")
                self.state["positions"][str(p.identifier)] = leg
            elif kind == "modify":
                owned = self.owned(positions, pending=True)
                p = owned.get(pending["ident"])
                if p is not None:
                    require((abs(p.sl - r["sl"]) < 1e-8 and abs(p.tp - r["tp"]) < 1e-8) or p.sl == 0,
                            "unresolved_modify_no_retry")
                    self.state["positions"][pending["ident"]]["sl"] = float(r["sl"])
                    self.state["positions"][pending["ident"]]["tp"] = float(r["tp"])
                else:
                    self.closed_pnl(pending["ident"])
            elif kind == "close":
                require(not any(str(p.identifier) == pending["ident"] for p in positions), "unresolved_close_no_retry")
                self.closed_pnl(pending["ident"])
            self.state["pending"] = None
            self.store.save("intent_reconciled")
        owned = self.owned(positions, allow_missing=True)
        for ident, leg in list(self.state["positions"].items()):
            if ident in owned:
                continue
            pnl, closed_at, target_hit = self.closed_pnl(ident)
            self.state["campaign"]["pnl"] += pnl
            if target_hit:
                self.state["campaign"]["closed_roles"].append([leg["group"], leg["role"]])
            self.state["last_exit_bar"] = max(self.state["last_exit_bar"], int(closed_at // 300) * 300)
            del self.state["positions"][ident]
        c = self.state["campaign"]
        if c and not self.state["positions"] and not self.state["opening"]:
            self.state["loss_streak"] = self.state["loss_streak"] + 1 if c["pnl"] < -1e-8 else 0
            self.state["frozen"] |= self.state["loss_streak"] >= 3
            self.state["outcomes"].append({"pnl": c["pnl"], "adds": c["adds"]})
            self.state["campaign"] = None
        self.store.save("positions_reconciled")
        return positions, orders, owned

    def plan(self, decision, fraction):
        decision.validate(self.clock())
        a = self.account(); info, tick = self.market(); side = int(decision.row["signal"])
        require(info.trade_mode == self.api.SYMBOL_TRADE_MODE_FULL, "entry_symbol_closed")
        atr = float(decision.row["atr"])
        require(0 < tick.ask - tick.bid <= min(.60, .1 * atr), "actual_spread_gate")
        reference = tick.ask if side == 1 else tick.bid
        stop = float(decision.row.get("stop_long" if side == 1 else "stop_short", math.nan))
        require(finite(stop) and stop > 0, "structural_stop_missing")
        adverse = reference + side * self.config.slippage
        stop = min(stop, adverse - 1.4 * atr) if side == 1 else max(stop, adverse + 1.4 * atr)
        stop = tick_price(stop, info.trade_tick_size, up=side == -1)
        distance = side * (adverse - stop)
        require(.35 * atr <= distance <= 2.2 * atr + 1e-8, "stop_exceeds_atr_cap")
        liquidation = tick.bid if side == 1 else tick.ask
        require(side * (liquidation - stop) > max(info.trade_stops_level * info.point, 0), "stop_inside_spread_or_limit")
        require(0 < fraction <= .05 and a.equity > 0, "baseline_risk_only")
        budget = a.equity * fraction  # No minimum, recapitalization, or fixed $50 basis.
        def loss(lots):
            value = -self.profit(side, lots, adverse, stop - side * self.config.slippage)
            require(value > 0, "invalid_broker_loss")
            return value + 2 * lots * self.config.commission_per_lot_side
        minimum = loss(info.volume_min)
        require(minimum <= budget + 1e-10, "min_lot")
        lots = floor_step(min(info.volume_max, budget / minimum * info.volume_min), info.volume_step)
        require(lots >= info.volume_min, "min_lot")
        margin_cap = min(a.margin_free, .25 * a.equity)
        margin = self.margin(side, lots, adverse)
        if margin > margin_cap:
            lots = floor_step(lots * margin_cap / margin, info.volume_step)
            require(lots >= info.volume_min, "margin")
        risk, margin = loss(lots), self.margin(side, lots, adverse)
        require(risk <= budget + 1e-9 and margin <= margin_cap + 1e-9, "broker_risk_or_margin_recheck")
        parts = exact_parts(lots, BrokerSpec(lot_min=info.volume_min, lot_step=info.volume_step))
        initial_distance = side * (reference - stop)
        targets = [tick_price(reference + side * initial_distance * r, info.trade_tick_size, up=side == -1) for r in (1.5, 2.5)]
        return {"side": side, "lots": lots, "sl": stop, "price": reference, "adverse": adverse,
                "atr": atr, "risk": risk, "budget": budget, "margin": margin, "fraction": fraction,
                "parts": list(parts) if parts else None, "tp1": targets[0], "tp2": targets[1]}

    def send(self, request, kind, leg=None, ident=None, decision=None):
        """Never resubmit after submission uncertainty. Exact broker state may recover."""
        self.account(mutation=True)
        require(self.state["pending"] is None, "unresolved_intent_no_retry")
        require(kind in ("entry", "modify", "close") and request.get("action") ==
                (self.api.TRADE_ACTION_SLTP if kind == "modify" else self.api.TRADE_ACTION_DEAL), "unsupported_mutation")
        require(request["symbol"] == SYMBOL and request["magic"] == MAGIC, "invalid_request_identity")
        if kind != "modify":
            require(request.get("type_filling") == self.api.ORDER_FILLING_FOK and request.get("type_time") == self.api.ORDER_TIME_GTC and
                    finite(request.get("volume")) and request["volume"] > 0 and finite(request.get("price")) and request["price"] > 0,
                    "invalid_fok_deal")
        before, orders = self.exposures(); self.owned(before, allow_missing=kind == "close")
        if kind == "entry":
            require(not orders, "pending_orders_block")
            require(all(str(p.identifier) in self.state["positions"] for p in before), "manual_exposure_blocks_entry")
            require(leg is not None and decision is not None and "position" not in request and
                    abs(request["volume"] - leg["lots"]) < 1e-8 and request["type"] ==
                    (self.api.ORDER_TYPE_BUY if leg["side"] == 1 else self.api.ORDER_TYPE_SELL) and
                    finite(request.get("sl")) and request["sl"] > 0 and finite(request.get("tp")) and
                    (request["tp"] > 0 or leg["role"] == "runner"), "entry_identity_or_protection_invalid")
        else:
            require(ident in self.owned(before, allow_missing=kind == "close"), "owned_position_required")
            p = self.owned(before, allow_missing=kind == "close")[ident]
            require(request.get("position") == p.ticket, "request_ticket_changed")
            if kind == "close":
                require(abs(request["volume"] - p.volume) < 1e-8 and request["type"] ==
                        (self.api.ORDER_TYPE_SELL if p.type == self.api.ORDER_TYPE_BUY else self.api.ORDER_TYPE_BUY), "close_volume_or_side_invalid")
        checked = self.api.order_check(request)
        require(checked is not None and checked.retcode == 0, "broker_check_rejected")
        # Recheck every mutable invariant after broker preflight, before journal/send.
        a = self.account(mutation=True); info, tick = self.market()
        after, orders = self.exposures(); self.owned(after, allow_missing=kind == "close")
        signature = lambda ps: sorted((p.identifier, p.ticket, p.volume, p.sl, p.tp) for p in ps)
        require((kind != "entry" or not orders) and signature(before) == signature(after), "exposure_changed_before_send")
        if kind == "entry":
            decision.validate(self.clock())
            self.ledger(after)
            require(not self.state["daily_killed"] and not self.state["frozen"] and self.state["day_start"] is not None, "risk_changed_before_send")
            mode, _, _ = mode_gate(self.state["day_start"], a.equity, self.state["loss_streak"], decision.row["mode"])
            require(mode not in ("FROZEN", "KILL") and not (mode == "EXTREME" and self.state["extreme_disabled"]), "mode_changed_before_send")
            require(abs((tick.ask if leg["side"] == 1 else tick.bid) - request["price"]) <= 1e-9, "quote_changed_before_send")
            risk = -self.profit(leg["side"], request["volume"], request["price"] + leg["side"] * self.config.slippage,
                                request["sl"] - leg["side"] * self.config.slippage) + 2 * request["volume"] * self.config.commission_per_lot_side
            current_tranche_budget = a.equity * leg["fraction"] * leg["allocation"]
            require(risk <= min(leg["budget"], current_tranche_budget) + 1e-9 and
                    self.open_risk(after) + risk <= .075 * a.equity + 1e-9, "risk_changed_before_send")
            margin = self.margin(leg["side"], request["volume"], request["price"] + leg["side"] * self.config.slippage)
            require(margin <= min(a.margin_free, max(0, .25 * a.equity - a.margin)) + 1e-9, "margin_changed_before_send")
        elif kind == "close":
            require(abs((tick.ask if request["type"] == self.api.ORDER_TYPE_BUY else tick.bid) - request["price"]) <= self.config.slippage, "close_quote_changed")
        elif kind == "modify":
            p = self.owned(after)[ident]; side = self.state["positions"][ident]["side"]
            quote = tick.bid if side == 1 else tick.ask
            require((side * (request["sl"] - p.sl) > 0 or (abs(request["sl"] - p.sl) < 1e-8 and abs(request["tp"] - p.tp) > 1e-8)) and side * (quote - request["sl"]) >
                    max(info.trade_stops_level, info.trade_freeze_level) * info.point, "protection_not_tighter_or_executable")
        self.state["pending"] = {"kind": kind, "request": request, "leg": leg, "ident": ident}
        self.store.save("intent_before_send")
        latest = self.account(mutation=True)  # A changed account can never consume the intent.
        final_positions, final_orders = self.exposures()
        require(signature(after) == signature(final_positions) and (kind != "entry" or not final_orders),
                "exposure_changed_at_submission")
        if decision is not None:
            decision.validate(self.clock())
            _, final_tick = self.market()
            require(abs((final_tick.ask if leg["side"] == 1 else final_tick.bid) - request["price"]) <= 1e-9 and
                    latest.equity >= a.equity - 1e-8 and latest.margin_free >= a.margin_free - 1e-8,
                    "quote_or_equity_changed_at_submission")
        self.account(mutation=True)
        try:
            result = self.api.order_send(request)
        except Exception:
            raise ExecutionStop("ambiguous_submission_no_retry") from None
        if result is None or result.retcode != self.api.TRADE_RETCODE_DONE:
            raise ExecutionStop("ambiguous_submission_no_retry")
        _, _, confirmed = self.reconcile()
        unsafe = [i for i, p in confirmed.items() if self.unsafe_protection(i, p)]
        if unsafe and kind != "close":
            for i in unsafe:
                self.close_position(i, "missing_protection")
            raise ExecutionStop("protection_failed_emergency_closed")

    def unsafe_protection(self, ident, position):
        known = self.state["positions"][ident]
        return (position.sl == 0 or known["side"] * (position.sl - known["sl"]) < -1e-8 or
                (position.tp == 0 and known["tp"] > 0))

    def open_risk(self, positions):
        risk = 0.0
        for ident, p in self.owned(positions).items():
            leg = self.state["positions"][ident]
            net = self.profit(leg["side"], p.volume, p.price_open, p.sl - leg["side"] * self.config.slippage)
            reserve = 2 * p.volume * self.config.commission_per_lot_side + max(0, -p.swap)
            risk += max(0, reserve - net)  # Locked wins never subsidize losing risk.
        return risk

    def breakeven(self, p, leg, info):
        # Broker USD calculator, including both fees, stop slippage and swap debit.
        step_profit = self.profit(leg["side"], p.volume, p.price_open,
                                 p.price_open + leg["side"] * info.trade_tick_size)
        require(step_profit > 0, "breakeven_calculator_invalid")
        cost = 2 * p.volume * self.config.commission_per_lot_side + max(0, -p.swap)
        proposal = p.price_open + leg["side"] * (cost / step_profit * info.trade_tick_size + self.config.slippage)
        proposal = tick_price(proposal, info.trade_tick_size, up=leg["side"] == 1)
        require(self.profit(leg["side"], p.volume, p.price_open, proposal - leg["side"] * self.config.slippage) + 1e-8 >= cost,
                "breakeven_not_cost_covered")
        return proposal

    def close_position(self, ident, reason):
        positions, _ = self.exposures(); p = self.owned(positions, allow_missing=True).get(ident)
        require(p is not None, "owned_position_required")
        info, tick = self.market(); side = self.state["positions"][ident]["side"]
        request = {"action": self.api.TRADE_ACTION_DEAL, "symbol": SYMBOL, "magic": MAGIC,
            "position": p.ticket, "volume": p.volume, "type": self.api.ORDER_TYPE_SELL if side == 1 else self.api.ORDER_TYPE_BUY,
            "price": tick.bid if side == 1 else tick.ask, "deviation": int(self.config.slippage / info.point),
            "type_time": self.api.ORDER_TIME_GTC, "type_filling": self.api.ORDER_FILLING_FOK, "comment": "VX02 " + reason}
        self.send(request, "close", ident=ident)

    def protect(self, decision, owned):
        decision.validate(self.clock(), entry=False)
        info, tick = self.market(); row = decision.row
        for ident, p in list(owned.items()):
            leg = self.state["positions"][ident]; side = leg["side"]
            previous = float(row["close"])  # Bid closed candle; do not invent historical Ask.
            gain = side * (previous - p.price_open)
            if side == -1:
                gain -= tick.ask - tick.bid  # Conservative current spread reserve.
            proposal = p.sl
            if gain >= leg["initial_r"]:
                be = self.breakeven(p, leg, info)
                proposal = max(proposal, be) if side == 1 else min(proposal, be)
            tp2_done = [leg["group"], "tp2"] in self.state["campaign"]["closed_roles"]
            if (leg["role"] == "single" and gain >= 1.5 * leg["initial_r"]) or (leg["role"] == "runner" and tp2_done):
                leg["trail_started"] = True
                self.store.save("trailing_activated")
            if leg.get("trail_started", False):
                trail = previous - side * 1.3 * row["atr"]
                swing = row.get("swing_low" if side == 1 else "swing_high")
                if swing is not None and finite(float(swing)):
                    structural = swing - side * .1 * row["atr"]
                    trail = max(trail, structural) if side == 1 else min(trail, structural)
                proposal = max(proposal, trail) if side == 1 else min(proposal, trail)
            proposal = tick_price(proposal, info.trade_tick_size, up=side == -1)
            if side * (proposal - p.sl) <= 1e-9:
                continue
            quote = tick.bid if side == 1 else tick.ask
            if side * (quote - proposal) <= 0:
                self.close_position(ident, "protection_crossed")
                continue
            if side * (quote - proposal) <= max(info.trade_stops_level, info.trade_freeze_level) * info.point:
                continue  # Broker's old confirmed hard stop remains; never loosen it.
            self.send({"action": self.api.TRADE_ACTION_SLTP, "symbol": SYMBOL, "magic": MAGIC,
                       "position": p.ticket, "sl": proposal, "tp": p.tp}, "modify", ident=ident)

    def enter(self, decision, positions):
        a = self.account(); c = self.state["campaign"]; row = decision.row
        require(self.state["day_start"] is not None, "midnight_equity_unproven")
        mode, reason, fraction = mode_gate(self.state["day_start"], a.equity, self.state["loss_streak"], row["mode"])
        require(mode not in ("FROZEN", "KILL") and not self.state["frozen"] and not self.state["daily_killed"], reason)
        require(not (mode == "EXTREME" and self.state["extreme_disabled"]), "extreme_disabled")
        require(not self.state["opening"], "incomplete_campaign_open_requires_review")
        if c:
            require(c["adds"] < 2 and c["side"] == row["signal"], "add_limit_or_direction")
            level = c["adds"] + 1; side = c["side"]
            info, tick = self.market(); owned = self.owned(positions)
            require(any(p["group"] == 0 for p in self.state["positions"].values()), "base_closed_no_add")
            gain = side * (row["close"] - c["base_entry"]) - (tick.ask - tick.bid if side == -1 else 0)
            require(gain >= level * c["base_r"] and side * row["consensus"] >= (78 if level == 1 else 82), "winner_threshold_not_met")
            if level == 2:
                require(side * row["orion"] >= 80 and side * row["nova"] >= 80, "second_add_votes")
            for ident, p in owned.items():
                leg = self.state["positions"][ident]
                quote = tick.bid if side == 1 else tick.ask
                require(self.profit(side, p.volume, p.price_open, quote) + p.swap -
                        2 * p.volume * self.config.commission_per_lot_side > 0, "loser_add_forbidden")
                if level == 2 or leg["group"] == 0:
                    require(side * (p.sl - self.breakeven(p, leg, info)) >= -1e-8, "breakeven_not_confirmed")
            fraction = (.015 if level == 1 else .01) * (.5 if self.state["loss_streak"] >= 2 else 1)
        else:
            level = 0
        plan = self.plan(decision, fraction)
        nominal = (c["nominal_risk"] if c else 0) + plan["budget"]
        require(nominal <= .075 * (c["starting_equity"] if c else a.equity) + 1e-9, "campaign_nominal_cap")
        require(self.open_risk(positions) + plan["risk"] <= .075 * a.equity + 1e-9, "campaign_open_risk_cap")
        if c is None:
            c = {"side": plan["side"], "starting_equity": a.equity, "nominal_risk": 0,
                 "adds": 0, "pnl": 0.0, "closed_roles": [], "base_entry": plan["adverse"],
                 "base_r": plan["side"] * (plan["adverse"] - plan["sl"])}
            self.state["campaign"] = c
        c["nominal_risk"] = nominal
        if level:
            c["adds"] = level
        self.state["opening"] = True
        self.store.save("campaign_reserved")
        parts = list(zip(("tp1", "tp2", "runner"), plan["parts"], (plan["tp1"], plan["tp2"], 0.0))) if plan["parts"] else [("single", plan["lots"], plan["tp2"])]
        for role, lots, tp in parts:
            info, _ = self.market()
            leg = {"side": plan["side"], "lots": lots, "atr": plan["atr"], "group": level,
                   "role": role, "budget": plan["budget"] * lots / plan["lots"],
                   "fraction": fraction, "allocation": lots / plan["lots"]}
            request = {"action": self.api.TRADE_ACTION_DEAL, "symbol": SYMBOL, "magic": MAGIC,
                "type": self.api.ORDER_TYPE_BUY if plan["side"] == 1 else self.api.ORDER_TYPE_SELL,
                "volume": lots, "price": plan["price"], "sl": plan["sl"], "tp": tp,
                "deviation": int(self.config.slippage / info.point), "type_time": self.api.ORDER_TIME_GTC,
                "type_filling": self.api.ORDER_FILLING_FOK, "comment": "V02" + uuid.uuid4().hex[:24]}
            self.send(request, "entry", leg=leg, decision=decision)
            # Requested protection is confirmed first. Correct target from actual
            # broker fill before the next tranche, never from an invented fill.
            if tp:
                current, _ = self.exposures()
                matches = [(i, p) for i, p in self.owned(current).items() if p.comment == request["comment"]]
                require(len(matches) == 1, "filled_ticket_unavailable")
                ident, p = matches[0]
                actual_r = self.state["positions"][ident]["initial_r"]
                actual_tp = tick_price(p.price_open + plan["side"] * actual_r * (1.5 if role == "tp1" else 2.5),
                                       info.trade_tick_size, up=plan["side"] == -1)
                if abs(actual_tp - p.tp) > 1e-8:
                    self.send({"action": self.api.TRADE_ACTION_SLTP, "symbol": SYMBOL, "magic": MAGIC,
                               "position": p.ticket, "sl": p.sl, "tp": actual_tp}, "modify", ident=ident)
        if level == 0:
            base = [p for p in self.state["positions"].values() if p["group"] == 0]
            require(base, "base_closed_during_submission")
            total = sum(p["lots"] for p in base)
            c["base_entry"] = sum(p["entry"] * p["lots"] for p in base) / total
            c["base_r"] = sum(p["initial_r"] * p["lots"] for p in base) / total
        self.state["opening"] = False
        self.store.save("campaign_open_confirmed")
        return "base_confirmed" if level == 0 else "add_confirmed"

    def step(self, decision=None):
        """One bounded poll. Exceptions never retry an order or relax a gate.

        run_demo_v02 passes Decision.from_observer(calculate_row(...)).
        None still reconciles broker exits/daily kill; it cannot create an entry.
        """
        now = self.clock()
        require(now >= self.state["last_clock"], "clock_went_backward")
        self.state["last_clock"] = now; self.store.save("poll")
        self.account()
        positions, orders, owned = self.reconcile()
        missing = [ident for ident, p in owned.items() if self.unsafe_protection(ident, p)]
        if missing:
            if not self.config.approved:
                return "unprotected_position_manual_gate_blocked"
            for ident in missing:
                self.close_position(ident, "missing_protection")
            return "unprotected_position_closed"
        self.ledger(positions)
        if not self.config.approved:
            return "baseline_manual_or_cost_gate_blocked"
        self.market()
        if self.state["daily_killed"]:
            for ident in list(owned):
                self.close_position(ident, "daily_kill")
            return "daily_kill"
        if decision is None:
            return "no_completed_decision"
        decision.validate(self.clock(), entry=False)
        if decision.closed_at <= self.state["last_decision"]:
            return "duplicate_decision"
        self.state["last_decision"] = decision.closed_at
        self.store.save("decision_consumed_before_actions")
        self.protect(decision, owned)
        positions, orders, owned = self.reconcile()
        require(not orders and all(str(p.identifier) in owned for p in positions), "manual_exposure_blocks_entry")
        require(decision.closed_at > self.state["last_exit_bar"], "same_bar_exit")
        decision.validate(self.clock())
        return self.enter(decision, positions)
