"""Separate DEMO supervisor. Default --check is offline; no automatic activation.

All terminal calls belong to the caller thread. Only calculate_row runs in a
worker. The read-only observer and its status.json contract remain unchanged.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import time

try:
    from .execution_v02 import Config, Decision, ExecutionStop, Manager, Store, canonical
    from .observe_v02 import ObserverConfig, ObserverState, ObserverStop, collect_frames, calculate_row, atomic_json
except ImportError:
    from execution_v02 import Config, Decision, ExecutionStop, Manager, Store, canonical
    from observe_v02 import ObserverConfig, ObserverState, ObserverStop, collect_frames, calculate_row, atomic_json

UTC = timezone.utc
READ_RETRY = frozenset({"account_or_terminal_unavailable", "broker_disconnected", "exposure_unknown",
                        "stale_or_invalid_tick", "capital_history_unavailable"})
DECISION_SKIP = frozenset({"late_or_nonadjacent_decision", "stale_or_future_m5", "stale_or_future_m15",
    "stale_or_future_h1", "stale_or_future_h4", "closed_m5_not_adjacent", "invalid_decision_price",
    "entry_inputs_invalid", "independent_voting_gate", "min_lot", "margin", "broker_risk_or_margin_recheck",
    "actual_spread_gate", "stop_exceeds_atr_cap", "structural_stop_missing", "stop_inside_spread_or_limit",
    "winner_threshold_not_met", "loser_add_forbidden", "breakeven_not_confirmed", "add_limit_or_direction",
    "base_closed_no_add", "second_add_votes", "campaign_nominal_cap", "campaign_open_risk_cap", "same_bar_exit",
    "three_losses", "extreme_disabled", "midnight_equity_unproven", "entry_symbol_closed"})


def reason(error):
    value = str(error)
    return value if re.fullmatch(r"[a-z0-9_]{1,96}", value) else "private_runtime_review_required"


def iso(epoch):
    return datetime.fromtimestamp(epoch, UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def configs(env):
    observer = ObserverConfig.from_env(env)
    try:
        origin = datetime.fromisoformat(env["VORTEX_ACCOUNT_HISTORY_ORIGIN_UTC"].replace("Z", "+00:00"))
        if origin.tzinfo is None:
            raise ValueError()
        # Values are explicit private settings, not inferred from an account.
        slippage = float(env["VORTEX_VERIFIED_SLIPPAGE_USD"])
        commission = float(env["VORTEX_VERIFIED_COMMISSION_PER_LOT_SIDE_USD"])
    except (KeyError, ValueError, TypeError, OverflowError):
        raise ExecutionStop("private_execution_configuration_required") from None
    execution = Config(observer.expected_login, origin.timestamp(),
        baseline_approved=env.get("VORTEX_BASELINE_STATUS") == "passed_reviewed",
        manual_approved=env.get("VORTEX_DEMO_EXECUTION_APPROVAL") == "demo_execution_reviewed",
        costs_verified=env.get("VORTEX_EXECUTION_COST_STATUS") == "verified_reviewed",
        slippage=slippage, commission_per_lot_side=commission)
    return observer, execution


class Audit:
    """Separate private journal: no account/ticket/config/endpoint fields."""
    def __init__(self, directory):
        self.path = Path(directory) / "execution-supervisor-journal.jsonl"
        self.previous = "0" * 64
        if self.path.exists():
            for raw in self.path.read_bytes().splitlines(keepends=True):
                if not raw.endswith(b"\n"):
                    raise ExecutionStop("supervisor_journal_torn")
                record = json.loads(raw); digest = record.pop("sha256")
                if record.get("previous") != self.previous or hashlib.sha256(canonical(record)).hexdigest() != digest:
                    raise ExecutionStop("supervisor_journal_corrupt")
                self.previous = digest

    def append(self, event):
        record = dict(event, previous=self.previous)
        digest = hashlib.sha256(canonical(record)).hexdigest()
        with self.path.open("ab") as stream:
            stream.write(canonical(dict(record, sha256=digest)) + b"\n")
            stream.flush(); os.fsync(stream.fileno())
        self.previous = digest


class Supervisor:
    def __init__(self, api, observer_config, observer_state, manager, *, clock=time.time,
                 executor=None, collector=collect_frames, calculator=calculate_row):
        self.api, self.config, self.observer_state, self.manager = api, observer_config, observer_state, manager
        self.clock, self.collector, self.calculator = clock, collector, calculator
        self.executor = executor or ThreadPoolExecutor(max_workers=1, thread_name_prefix="vortex-execution-features")
        self.future = None; self.attempted_bar = None; self.closed = False; self.last_status = None
        self.audit = Audit(observer_state.directory)
        self.status_path = observer_state.directory / "execution-status.json"

    def status(self, state, detail, connected=False):
        private = self.manager.state
        payload = {"schemaVersion": 1, "role": "demo_execution_supervisor", "mode": "demo",
            "producedAt": iso(self.clock()), "state": state, "reason": detail,
            # Configuration arming is distinct from current entry eligibility.
            # A status poll never asserts the next decision passed every gate.
            "executionArmed": self.manager.config.approved and state not in ("stopped", "halted"),
            "entryEligible": None,
            "brokerConnected": connected, "managedPositions": len(private["positions"]),
            "unresolvedIntent": private["pending"] is not None, "incompleteCampaign": bool(private["opening"]),
            "dailyKill": bool(private["daily_killed"]), "persistentFreeze": bool(private["frozen"]),
            "brokerOrdersMayRemain": True}
        atomic_json(self.status_path, payload)
        if (state, detail) != self.last_status:
            self.audit.append({"event": "status", "recordedAtUtc": payload["producedAt"], "state": state, "reason": detail})
            self.last_status = (state, detail)
        return payload

    def decision_audit(self, result, disposition, detail):
        row = result["row"]
        scores = {}
        for name in ("orion", "vortex", "nova", "luna", "kira", "atlas", "consensus"):
            value = row.get(name)
            scores[name] = float(value) if value is not None and math.isfinite(float(value)) else None
        sources = {name: {key: source.get(key) for key in ("sha256", "rows", "latestAvailableAtUtc", "status") if key in source}
                   for name, source in result["sources"].items() if name in ("M5", "M15", "H1", "H4", "news", "coverage", "macro")}
        self.audit.append({"event": "decision", "recordedAtUtc": iso(self.clock()),
            "decisionTimeUtc": iso(Decision.from_observer(result).closed_at), "specSha256": result["specSha256"],
            "scores": scores, "sources": sources, "disposition": disposition, "reason": detail})

    def poll(self):
        """Health first, no blanket retry of Manager mutations or failed groups."""
        if (self.observer_state.directory / "STOP").exists():
            return self.status("stopped", "operator_stop_no_implicit_flatten")
        try:
            health = self.manager.step(None)
        except ExecutionStop as error:
            detail = reason(error)
            if detail in READ_RETRY and self.manager.state["pending"] is None and not self.manager.state["opening"]:
                return self.status("waiting_recovery", detail)
            self.status("halted", detail)
            raise
        if self.manager.state["pending"] is not None or self.manager.state["opening"]:
            self.status("halted", "incomplete_intent_or_campaign_requires_review", True)
            raise ExecutionStop("incomplete_intent_or_campaign_requires_review")
        detail, state = health, "running"
        if self.future is not None and self.future.done():
            future, self.future = self.future, None
            try:
                result = future.result()
                decision = Decision.from_observer(result)
                decision.validate(self.clock(), entry=False)
            except (ExecutionStop, ObserverStop) as error:
                detail, state = reason(error), "decision_skipped"
                if detail not in DECISION_SKIP:
                    self.status("halted", detail, True); raise
                if "result" in locals():
                    self.decision_audit(result, "skipped", detail)
            except Exception:
                self.status("halted", "feature_calculation_failed", True)
                raise ExecutionStop("feature_calculation_failed") from None
            else:
                try:
                    detail = self.manager.step(decision)
                    self.decision_audit(result, "manager_returned", detail)
                except ExecutionStop as error:
                    detail = reason(error)
                    blocked_intent = self.manager.state["pending"] is not None or self.manager.state["opening"]
                    self.decision_audit(result, "halted" if blocked_intent or detail not in DECISION_SKIP else "skipped", detail)
                    if blocked_intent or detail not in DECISION_SKIP:
                        self.status("halted", detail, True); raise
                    state = "decision_skipped"
        bar = int(self.clock() // 300) * 300
        if self.future is None and self.attempted_bar != bar:
            self.attempted_bar = bar
            try:
                frames = self.collector(self.api, self.observer_state, self.clock())
                self.future = self.executor.submit(self.calculator, frames, self.config)
                if state == "running" and health == "no_completed_decision":
                    state, detail = "features_pending", "closed_m5_calculation_pending"
            except ObserverStop as error:
                # A data read cannot submit an order; wait for a later M5 attempt.
                state, detail = "data_unavailable", reason(error)
        return self.status(state, detail, True)

    def close(self, detail="process_stopped_no_implicit_flatten"):
        if self.closed:
            return
        self.closed = True
        if self.future is not None:
            self.future.cancel()
        self.executor.shutdown(wait=False, cancel_futures=True)
        fatal = self.last_status and self.last_status[0] == "halted"
        self.status("halted" if fatal else "stopped", self.last_status[1] if fatal else detail)


def main(argv=None, env=None, *, broker_factory=None, clock=time.time, sleep=time.sleep,
         platform=None, supervisor_factory=Supervisor):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="offline imports/configuration only; default")
    group.add_argument("--run-demo", action="store_true", help="explicit fully gated DEMO supervisor")
    parser.add_argument("--once", action="store_true", help="one health/management poll; does not wait for feature work")
    args = parser.parse_args(argv); env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    observer_state = execution_store = supervisor = api = None
    initialized = False
    try:
        observer_config, execution_config = configs(env)
        if not args.run_demo:
            print("DEMO supervisor configuration valid; terminal and state untouched; baseline not asserted.")
            return 0
        if not execution_config.approved:
            raise ExecutionStop("baseline_manual_or_cost_gate_blocked")
        if platform != "win32":
            raise ExecutionStop("windows_terminal_required")
        if execution_config.history_origin_utc >= clock():
            raise ExecutionStop("history_origin_must_precede_runtime")
        # Same runtime directory: acquire BOTH locks before importing/initializing MT5.
        observer_state = ObserverState(observer_config, clock())
        execution_store = Store(observer_state.directory, execution_config)
        if broker_factory is None:
            import MetaTrader5 as mt5
            api = mt5
        else:
            api = broker_factory()
        path = env.get("VORTEX_TERMINAL_PATH")
        initialized = bool(api.initialize(path, timeout=10000) if path else api.initialize(timeout=10000))
        if not initialized:
            raise ExecutionStop("terminal_initialization_failed")
        manager = Manager(api, execution_config, execution_store, clock)
        supervisor = supervisor_factory(api, observer_config, observer_state, manager, clock=clock)
        while True:
            result = supervisor.poll()
            if result["state"] == "stopped" or args.once:
                break
            sleep(2)
        return 0
    except (ExecutionStop, ObserverStop) as error:
        if supervisor is not None:
            try:
                supervisor.status("halted", reason(error))
            except Exception:
                pass  # Preserve original bounded error and finish every cleanup.
        print("DEMO supervisor inactive: " + reason(error), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0
    except Exception:
        if supervisor is not None:
            try:
                supervisor.status("halted", "private_runtime_review_required")
            except Exception:
                pass
        print("DEMO supervisor inactive: private_runtime_review_required", file=sys.stderr)
        return 3
    finally:
        # Cleanup must release later resources even if a status write fails.
        for resource, method in ((supervisor, "close"), (api, "shutdown"),
                                 (execution_store, "close"), (observer_state, "close")):
            if resource is not None:
                try:
                    getattr(resource, method)()
                except Exception:
                    print("DEMO supervisor cleanup: private_runtime_review_required", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
