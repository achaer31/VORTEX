"""Read-only v0.2 terminal observer. Default --check is offline and inert.

Runtime state is private and outside the checkout. No execution interface is
implemented here. Calendar/macro gaps remain invalid, never filled by guesses.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import time
import uuid

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "research_v02"))
from live.collect_evidence import (CollectionError, archive_frames, archive_account_snapshot, collect_accounting)
from vortex_v02.data import aggregate_h4, external_context, validate_bars
from vortex_v02.engines import build_signals

UTC = timezone.utc
MODEL = "VORTEX-XAU-EXTREME-v0.2"
NAMES = ("orion", "vortex", "nova", "luna", "kira", "atlas")
METRICS = ("balance", "equity", "floatingPnl", "realizedPnl", "dailyPnl", "dailyDrawdown", "maxDrawdown", "freeMargin", "usedMargin", "openRisk", "lockedProfit", "currentR")


class ObserverStop(RuntimeError):
    """Only bounded machine reasons may cross the console/status boundary."""


def utc_iso(epoch):
    return datetime.fromtimestamp(epoch, UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def safe_text(value, limit=160):
    return re.sub(r"[^A-Za-z0-9 _.,:()/+\-]", "_", str(value))[:limit] or "unavailable"


def atomic_json(path, value):
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, allow_nan=False, separators=(",", ":"))
        stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
    os.replace(temp, path)


def private_path(value):
    path = Path(value).expanduser().resolve()
    if path == REPO or REPO in path.parents:
        raise ObserverStop("runtime_path_must_be_outside_checkout")
    return path


def canonical(value):
    return json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":")).encode()


class DecisionJournal:
    """Append-only hash chain. Integrity evidence, not a signed external timestamp."""
    def __init__(self, directory):
        self.path = directory / "decision-journal.jsonl"
        self.previous = "0" * 64; self.decisions = set()
        if self.path.exists():
            with self.path.open("r", encoding="utf8") as stream:
                for line in stream:
                    try:
                        record = json.loads(line)
                        digest = record.pop("recordHash")
                        if record["previousHash"] != self.previous or hashlib.sha256(canonical(record)).hexdigest() != digest:
                            raise ValueError()
                        self.previous = digest
                        if record["kind"] == "decision":
                            self.decisions.add(record["decisionTimeUtc"])
                    except (ValueError, KeyError, TypeError):
                        raise ObserverStop("decision_journal_integrity_failed") from None

    def append(self, record):
        if record["kind"] == "decision" and record["decisionTimeUtc"] in self.decisions:
            return False
        value = {**record, "previousHash": self.previous}
        digest = hashlib.sha256(canonical(value)).hexdigest()
        value["recordHash"] = digest
        with self.path.open("ab") as stream:
            stream.write(canonical(value) + b"\n"); stream.flush(); os.fsync(stream.fileno())
        self.previous = digest
        if record["kind"] == "decision":
            self.decisions.add(record["decisionTimeUtc"])
        return True


@dataclass(frozen=True)
class ObserverConfig:
    expected_login: int
    session_offset_minutes: int
    state_dir: Path
    news_path: Path | None = None
    coverage_path: Path | None = None
    macro_path: Path | None = None

    def __post_init__(self):
        if isinstance(self.expected_login, bool) or not isinstance(self.expected_login, int) or self.expected_login <= 0:
            raise ObserverStop("expected_demo_identity_required")
        if isinstance(self.session_offset_minutes, bool) or self.session_offset_minutes != 0:
            raise ObserverStop("v02_requires_verified_exness_gmt0")
        object.__setattr__(self, "state_dir", private_path(self.state_dir))
        for key in ("news_path", "coverage_path", "macro_path"):
            value = getattr(self, key)
            if value is not None:
                object.__setattr__(self, key, private_path(value))

    @classmethod
    def from_env(cls, env):
        try:
            paths = {key: Path(env[name]) if env.get(name) else None for key, name in (
                ("news_path", "VORTEX_NEWS_CSV"), ("coverage_path", "VORTEX_NEWS_COVERAGE_CSV"), ("macro_path", "VORTEX_MACRO_CSV"))}
            return cls(int(env["VORTEX_EXPECTED_LOGIN"]), int(env["VORTEX_SESSION_UTC_OFFSET_MINUTES"]), Path(env["VORTEX_STATE_DIR"]), **paths)
        except (KeyError, ValueError):
            raise ObserverStop("private_observer_configuration_required") from None

    @property
    def fingerprint(self):
        return hashlib.sha256(f"{MODEL}:{self.expected_login}:{self.session_offset_minutes}".encode()).hexdigest()


class ObserverState:
    def __init__(self, config, now):
        self.directory = config.state_dir
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = (self.directory / "observer-v02.lock").open("a+b")
        self.lock.seek(0, 2)
        if self.lock.tell() == 0:
            self.lock.write(b"0"); self.lock.flush()
        self.lock.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.lock.close(); raise ObserverStop("observer_already_running") from None
        self.path = self.directory / "observer-v02-state.json"
        try:
            if self.path.exists():
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
                if self.data.get("schema") != 1 or self.data.get("fingerprint") != config.fingerprint:
                    raise ObserverStop("private_state_identity_changed")
            else:
                start = datetime.fromtimestamp(now, UTC).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=180)
                self.data = {"schema": 1, "fingerprint": config.fingerprint,
                             "historyStartUtc": start.timestamp(), "firstBars": {}, "journal": []}
                self.save()
            if not isinstance(self.data.get("firstBars"), dict) or not isinstance(self.data.get("journal"), list):
                raise ObserverStop("invalid_private_state")
            start = number(self.data.get("historyStartUtc"))
            if start is None or start >= now:
                raise ObserverStop("invalid_history_start")
            self.audit = DecisionJournal(self.directory)
        except Exception:
            self.lock.close(); raise

    def save(self):
        atomic_json(self.path, self.data)

    def event(self, now, event, reason):
        entry = {"time": utc_iso(now), "event": safe_text(event, 48), "reason": safe_text(reason)}
        previous = self.data["journal"][-1] if self.data["journal"] else None
        if previous and (previous["event"], previous["reason"]) == (entry["event"], entry["reason"]):
            return
        if previous and entry["time"] < previous["time"]:
            raise ObserverStop("observer_clock_went_backward")
        self.data["journal"] = (self.data["journal"] + [entry])[-50:]
        self.audit.append({"kind": "state_change", "recordedAtUtc": entry["time"], "model": MODEL,
                           "specSha256": hashlib.sha256((REPO / "research_v02" / "SPEC.md").read_bytes()).hexdigest(),
                           "event": entry["event"], "reason": entry["reason"], "executionEnabled": False})
        self.save()

    def close(self):
        self.lock.close()


def verified_account(api, config):
    account, terminal = api.account_info(), api.terminal_info()
    if account is None or terminal is None:
        raise ObserverStop("account_or_terminal_unavailable")
    if account.trade_mode != api.ACCOUNT_TRADE_MODE_DEMO:
        raise ObserverStop("demo_account_required")
    if account.login != config.expected_login:
        raise ObserverStop("unexpected_account")
    if account.currency != "USD" or account.margin_mode != api.ACCOUNT_MARGIN_MODE_RETAIL_HEDGING:
        raise ObserverStop("usd_hedging_account_required")
    if not terminal.connected:
        raise ObserverStop("terminal_disconnected")
    if any(number(getattr(account, k, None)) is None for k in ("balance", "equity", "margin_free", "margin")) or account.margin < 0:
        raise ObserverStop("invalid_account_values")
    return account, terminal


def quote_from_tick(tick, now):
    if tick is None:
        return None, False
    bid, ask, epoch = (number(getattr(tick, k, None)) for k in ("bid", "ask", "time"))
    if bid is None or ask is None or epoch is None or not 0 < bid <= ask or epoch > now + 30:
        return None, False
    return {"symbol": "XAUUSD", "bid": bid, "ask": ask, "changedAtUtc": utc_iso(epoch)}, 0 <= now - epoch <= 10


def anonymous_positions(api, session):
    positions = api.positions_get(symbol="XAUUSD")
    if positions is None or len(positions) > 20:
        raise ObserverStop("positions_unavailable")
    result = []
    for p in positions:
        if p.symbol != "XAUUSD" or p.type not in (0, 1):
            raise ObserverStop("positions_invalid")
        values = {key: number(getattr(p, name, None)) for key, name in (
            ("lots", "volume"), ("openPrice", "price_open"), ("currentPrice", "price_current"), ("profit", "profit"), ("stopLoss", "sl"), ("takeProfit", "tp"))}
        if any(x is None for x in values.values()) or min(values[k] for k in ("lots", "openPrice", "currentPrice")) <= 0 or min(values[k] for k in ("stopLoss", "takeProfit")) < 0:
            raise ObserverStop("positions_invalid")
        for key in ("stopLoss", "takeProfit"):
            if values[key] == 0:
                values[key] = None
        result.append({"id": hashlib.sha256(f"{session}:{p.identifier}".encode()).hexdigest(), "side": "buy" if p.type == 0 else "sell", **values})
    return result


def collect_frames(api, state, now):
    frames = {}
    start = datetime.fromtimestamp(state.data["historyStartUtc"], UTC)
    end = datetime.fromtimestamp(now, UTC)
    first = dict(state.data["firstBars"])
    for tf, minutes in (("M5", 5), ("M15", 15), ("H1", 60)):
        raw = api.copy_rates_range("XAUUSD", getattr(api, f"TIMEFRAME_{tf}"), start, end)
        if raw is None or not len(raw):
            raise ObserverStop("history_unavailable")
        f = pd.DataFrame(raw)
        if "time" not in f or "spread" not in f:
            raise ObserverStop("history_schema_invalid")
        f.index = pd.to_datetime(f.pop("time"), unit="s", utc=True)
        f = f.rename(columns={"spread": "spread_points"})
        # API date_to includes an open bar: explicitly exclude every unclosed bar.
        f = f.loc[(f.index >= start) & (f.index + pd.Timedelta(minutes=minutes) <= end)]
        try:
            f = validate_bars(f, tf)
        except (ValueError, KeyError, TypeError):
            raise ObserverStop("history_validation_failed") from None
        observed = f.index[0].isoformat()
        if tf in first and first[tf] != observed:
            raise ObserverStop("history_start_changed")
        first[tf] = observed
        frames[tf] = f
    try:
        frames["H4"] = aggregate_h4(frames["H1"])
    except (ValueError, KeyError):
        raise ObserverStop("h4_complete_history_unavailable") from None
    state.data["firstBars"] = first; state.save()
    return frames


def calculate_row(frames, config):
    sources = {}
    decision = frames["M5"].index[-1] + pd.Timedelta(minutes=5)
    for tf, frame in frames.items():
        sources[tf] = {"sha256": hashlib.sha256(frame.to_csv().encode()).hexdigest(),
                       "latestAvailableAtUtc": (frame.index[-1] + pd.Timedelta(minutes={"M5": 5, "M15": 15, "H1": 60, "H4": 240}[tf])).isoformat(),
                       "rows": len(frame)}
    spec_hash = hashlib.sha256((REPO / "research_v02" / "SPEC.md").read_bytes()).hexdigest()
    for name, path, time_key in (("news", config.news_path, "known_at"), ("coverage", config.coverage_path, "known_at"), ("macro", config.macro_path, "available_at")):
        sources[name] = {"sha256": None, "latestAvailableAtUtc": None, "status": "missing"}
        if path is not None:
            try:
                raw = path.read_bytes()
                import io
                table = pd.read_csv(io.BytesIO(raw))
                if len(table) and not table[time_key].astype(str).str.contains(r"(?:Z|[+-]\d\d:\d\d)$", regex=True).all():
                    raise ValueError("explicit_external_timezone_required")
                times = pd.to_datetime(table[time_key], utc=True, errors="raise")
                known = times.loc[times <= decision]
                sources[name] = {"sha256": hashlib.sha256(raw).hexdigest(), "latestAvailableAtUtc": known.max().isoformat() if len(known) else None, "status": "provided"}
            except (OSError, ValueError, KeyError):
                sources[name]["status"] = "invalid"
    try:
        context = external_context(frames["M5"], config.news_path, config.coverage_path, config.macro_path)
    except (ValueError, OSError, KeyError, TypeError):
        # Keep all external gates invalid; market features can still be observed.
        context = external_context(frames["M5"])
    result = build_signals(frames, context)
    for name, path in (("news", config.news_path), ("coverage", config.coverage_path), ("macro", config.macro_path)):
        if sources[name]["sha256"] is not None:
            try:
                if hashlib.sha256(path.read_bytes()).hexdigest() != sources[name]["sha256"]:
                    raise ObserverStop("external_source_changed_during_calculation")
            except OSError:
                raise ObserverStop("external_source_changed_during_calculation") from None
    if hashlib.sha256((REPO / "research_v02" / "SPEC.md").read_bytes()).hexdigest() != spec_hash:
        raise ObserverStop("spec_changed_during_calculation")
    return {"row": result.iloc[-1], "sources": sources, "specSha256": spec_hash}


def empty_v02():
    return {"model": MODEL, "environment": "DEMO", "mode": "FROZEN", "action": "WAIT",
            "metrics": dict.fromkeys(METRICS),
            "context": {"session": None, "atr": None, "volatilityState": None, "nextNews": None},
            "engines": {name: {"score": None, "status": "INVALID", "reason": "observation_unavailable"} for name in NAMES},
            "consensus": None,
            "protection": {"confirmed": None, "killSwitch": True, "latencyMs": None, "brokerConnected": False, "dataFresh": False},
            "journal": [], "position": None}


class Observer:
    def __init__(self, api, config, state, clock=time.time, executor=None, calculator=calculate_row, collection_mode=False):
        self.api, self.config, self.state, self.clock = api, config, state, clock
        self.session = str(uuid.uuid4()); self.started = utc_iso(clock()); self.sequence = 0
        self.executor = executor or ThreadPoolExecutor(max_workers=1, thread_name_prefix="vortex-readonly-features")
        self.calculator = calculator; self.future = None; self.row = None; self.requested_bar = None
        self.collection_mode = bool(collection_mode)
        self.role = "collector" if self.collection_mode else "observer"

    def snapshot(self):
        now = self.clock(); self.sequence += 1
        payload = {"schemaVersion": 1, "mode": "demo", "sessionId": self.session,
                   "sessionStartedAt": self.started, "sequence": self.sequence, "producedAt": utc_iso(now),
                   "quote": None, "status": {"terminalConnected": False, "algoTradingEnabled": False, "eaRunning": False, "demoVerified": False},
                   "account": None, "positions": [],
                   "strategy": {"name": "VORTEX", "version": "0.2.0", "state": self.role + "_running", "reason": "observe_no_execution", "runnerMode": "observe"},
                   "v02": empty_v02()}
        try:
            account, terminal = verified_account(self.api, self.config)
        except ObserverStop as error:
            payload["strategy"]["state"] = self.role + "_blocked"
            payload["strategy"]["reason"] = str(error)
            self.state.event(now, self.role + "_blocked", str(error))
            payload["v02"]["journal"] = self.state.data["journal"]
            return self._save(payload)
        payload["status"] = {"terminalConnected": True, "algoTradingEnabled": bool(getattr(terminal, "trade_allowed", False) and not getattr(terminal, "tradeapi_disabled", True)),
                             "eaRunning": False, "demoVerified": True}
        payload["account"] = {"currency": "USD", "balance": float(account.balance), "equity": float(account.equity), "freeMargin": float(account.margin_free), "margin": float(account.margin)}
        metrics = payload["v02"]["metrics"]
        metrics.update(balance=float(account.balance), equity=float(account.equity), freeMargin=float(account.margin_free), usedMargin=float(account.margin))
        metrics["floatingPnl"] = number(getattr(account, "profit", None))
        # Realized/day P&L, drawdowns, open risk, and profit locks require journals.
        # A terminal snapshot cannot reconstruct them; keep those fields null.
        payload["quote"], quote_fresh = quote_from_tick(self.api.symbol_info_tick("XAUUSD"), now)
        bar = int(now // 300 * 300)
        reason = "observe_no_execution"
        position_error = None
        try:
            payload["positions"] = anonymous_positions(self.api, self.session)
        except ObserverStop as error:
            position_error = str(error)
        if self.future is not None and self.future.done():
            try:
                result = self.future.result(); self.row = result["row"]
            except Exception:
                self.row = None; reason = "feature_calculation_failed"
            self.future = None
            if self.row is not None:
                row = self.row
                try:
                    self._journal_decision(row, result, now)
                except Exception:
                    raise ObserverStop("decision_journal_write_failed") from None
        if self.requested_bar != bar and self.future is None:
            self.requested_bar = bar
            try:
                frames = collect_frames(self.api, self.state, now)
                if self.collection_mode:
                    verified_account(self.api, self.config)
                    archive_frames(self.state.directory, frames)
                self.future = self.executor.submit(self.calculator, frames, self.config)
            except (ObserverStop, CollectionError) as error:
                self.row = None; reason = str(error)
        v02 = payload["v02"]; protection = v02["protection"]
        protection["brokerConnected"] = True
        if self.row is not None:
            row = self.row
            decision = pd.Timestamp(row.decision_time)
            adjacent = decision == pd.Timestamp(bar, unit="s", tz="UTC")
            contexts_fresh = all(bool(row.get(f"{tf}_fresh", False)) for tf in ("m15", "h1", "h4"))
            protection["dataFresh"] = bool(quote_fresh and adjacent and contexts_fresh)
            direction = 1 if (number(row.get("consensus")) or 0) >= 0 else -1
            thresholds = {"orion": 70, "vortex": 55, "nova": 75, "luna": 55, "atlas": -35}
            for name in NAMES:
                score = number(row.get(name)); engine_reason = safe_text(row.get(f"{name}_reason", "unavailable"))
                if score is None:
                    status = "INVALID"
                elif name == "kira":
                    status = "PASS" if 45 <= score < 85 else "FAIL"
                else:
                    status = "PASS" if score * direction >= thresholds[name] else "FAIL"
                if name == "atlas" and (not bool(row.get("news_valid", False)) or not bool(row.get("macro_valid", False))):
                    status = "INVALID"
                v02["engines"][name] = {"score": score, "status": status, "reason": engine_reason}
            v02["consensus"] = number(row.get("consensus"))
            session = row.get("session")
            v02["context"] = {"session": session if session in ("ASIA", "LONDON", "NEWYORK", "LONDON_NEWYORK", "OTHER") else None,
                               "atr": number(row.get("atr")), "volatilityState": safe_text(row.get("kira_reason", "unavailable"), 40),
                               "nextNews": safe_text(row.next_news) if isinstance(row.get("next_news"), str) else None}
            if not bool(row.get("news_valid", False)):
                reason = "calendar_invalid"
            elif not bool(row.get("macro_valid", False)):
                reason = "macro_invalid"
            elif not protection["dataFresh"]:
                reason = "market_data_stale"
            elif bool(row.get("news_blocked", True)):
                reason = "news_blocked"
        elif reason == "observe_no_execution":
            reason = "features_pending"
        if not quote_fresh:
            reason = "market_quote_stale"
        if position_error:
            reason = position_error
        # Re-check immediately before publication: an account switch must redact.
        try:
            verified_account(self.api, self.config)
        except ObserverStop as error:
            payload["account"] = None; payload["quote"] = None; payload["positions"] = []
            payload["status"]["demoVerified"] = False; payload["status"]["terminalConnected"] = False
            payload["v02"] = empty_v02(); reason = str(error)
        payload["strategy"]["reason"] = reason
        self.state.event(now, self.role + "_status", reason)
        payload["v02"]["journal"] = self.state.data["journal"]
        if self.collection_mode and payload["status"]["demoVerified"]:
            collect_accounting(self.api, self.state.directory, account, now)
            try:
                verified_account(self.api, self.config)
            except ObserverStop as error:
                payload["account"] = None; payload["quote"] = None; payload["positions"] = []
                payload["status"]["demoVerified"] = False; payload["status"]["terminalConnected"] = False
                payload["strategy"]["state"] = self.role + "_blocked"
                payload["strategy"]["reason"] = str(error)
                payload["v02"] = empty_v02()
                payload["v02"]["journal"] = self.state.data["journal"]
        return self._save(payload)

    def _journal_decision(self, row, result, now):
        self.state.audit.append({"kind": "decision", "model": MODEL, "specSha256": result["specSha256"],
            "recordedAtUtc": utc_iso(now), "decisionTimeUtc": pd.Timestamp(row.decision_time).isoformat(),
            "sources": result["sources"], "scores": {name: number(row.get(name)) for name in NAMES},
            "reasons": {name: safe_text(row.get(f"{name}_reason", "unavailable")) for name in NAMES},
            "consensus": number(row.get("consensus")), "chosenMode": str(row.get("mode", "FROZEN")),
            "chosenAction": {1: "LONG", -1: "SHORT", 0: "WAIT"}.get(int(row.get("signal", 0)), "WAIT"),
            "executionEnabled": False, "collectionOnly": self.collection_mode, "meaning": "unexecuted_model_observation"})

    def _save(self, payload):
        atomic_json(self.state.directory / "status.json", payload)
        if self.collection_mode:
            archive_account_snapshot(self.state.directory, payload)
        return payload

    def close(self):
        self.executor.shutdown(wait=True, cancel_futures=True)


def main(argv=None, env=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="offline config/import validation; default")
    group.add_argument("--observe", action="store_true", help="explicit reviewed-baseline-gated read-only terminal collection")
    group.add_argument("--collect", action="store_true", help="explicit read-only DEMO evidence collection; does not assert a passed baseline")
    parser.add_argument("--once", action="store_true", help="one heartbeat in collect or observe mode")
    args = parser.parse_args(argv); env = os.environ if env is None else env
    try:
        config = ObserverConfig.from_env(env)
        if not args.observe and not args.collect:
            print("v0.2 observer imports/configuration valid; terminal untouched; baseline not asserted.")
            return 0
        if args.observe and env.get("VORTEX_BASELINE_STATUS") != "passed_reviewed":
            raise ObserverStop("reviewed_baseline_required")
        if sys.platform != "win32":
            raise ObserverStop("windows_terminal_required")
        import MetaTrader5 as mt5
        state = ObserverState(config, time.time()); observer = Observer(mt5, config, state, clock=time.time, collection_mode=args.collect)
        try:
            path = env.get("VORTEX_TERMINAL_PATH")
            connected = mt5.initialize(path, timeout=10000) if path else mt5.initialize(timeout=10000)
            if not connected:
                raise ObserverStop("terminal_connection_failed")
            while not (state.directory / "STOP").exists():
                started = time.monotonic()
                observer.snapshot()
                if args.once:
                    break
                time.sleep(max(0, 15 - (time.monotonic() - started)))
        finally:
            observer.close(); mt5.shutdown(); state.close()
        return 0
    except ObserverStop as error:
        print(f"Observer inactive: {error}", file=sys.stderr); return 2
    except KeyboardInterrupt:
        return 0
    except Exception:
        print("Observer stopped: private_runtime_review_required", file=sys.stderr); return 3


if __name__ == "__main__":
    raise SystemExit(main())
