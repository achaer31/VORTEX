"""Offline evidence gate. Never connects to MT5, a network, or a scheduler.

READY describes reviewed DEMO operational evidence, not permission to trade.
Hashes establish consistency, not the truth or independent provenance of logs.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import hmac
import json
import math
from pathlib import Path, PurePosixPath
import re

MODEL = "VORTEX-XAU-EXTREME-v0.2"
ATTESTATION = "I reviewed the original DEMO evidence; these are actual observations, not synthetic fixtures or inferred success."
REQUIRED = ("model", "baseline_promotion", "baseline_review", "runtime", "disconnect",
            "ticks", "decisions", "recovery", "management", "blocking")
HASH = re.compile(r"[a-f0-9]{64}")
MAX_BYTES = 16 * 1024 * 1024


class InvalidEvidence(ValueError):
    pass


def utc(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z", value):
        raise InvalidEvidence("utc_required")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidEvidence("duplicate_json_key")
        result[key] = value
    return result


def parse(raw):
    return json.loads(raw, object_pairs_hook=unique_object,
                      parse_constant=lambda _: (_ for _ in ()).throw(InvalidEvidence("nonfinite_json")))


def read_verified(root, reference):
    if not isinstance(reference, dict) or set(reference) != {"path", "sha256"}:
        raise InvalidEvidence("invalid_artifact_reference")
    relative, digest = reference["path"], reference["sha256"]
    if (not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative or
            PurePosixPath(relative).is_absolute() or ".." in PurePosixPath(relative).parts or
            not isinstance(digest, str) or not HASH.fullmatch(digest)):
        raise InvalidEvidence("unsafe_artifact_reference")
    path = (root / relative).resolve(strict=True)
    if root not in path.parents or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise InvalidEvidence("artifact_outside_directory_or_too_large")
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES or not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), digest):
        raise InvalidEvidence("artifact_digest_mismatch")
    return raw


def no_sensitive_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if re.search(r"password|credential|secret|token|account.?login|account.?number|chat.?id|private.?key", key, re.I):
                raise InvalidEvidence("sensitive_field_prohibited")
            no_sensitive_keys(child)
    elif isinstance(value, list):
        for child in value:
            no_sensitive_keys(child)


def evaluate(manifest, artifact_dir, now=None):
    """Returns machine reasons only; never echoes evidence contents or paths."""
    now = now or datetime.now(timezone.utc)
    checks = []
    evidence = {}

    def check(name, condition):
        checks.append({"check": name, "passed": bool(condition)})
        return bool(condition)

    def result():
        ready = bool(checks) and all(c["passed"] for c in checks)
        return {"schemaVersion": 1, "status": "READY" if ready else "NOT_READY",
                "scope": "reviewed_DEMO_operational_autonomy_only",
                "evaluatedAtUtc": now.isoformat().replace("+00:00", "Z"),
                "checks": checks, "failedChecks": [c["check"] for c in checks if not c["passed"]],
                "baselineAutoGo": False, "realTradingEnabled": False,
                "executionEnabledByEvaluator": False, "actionsPerformed": [],
                "evidenceLimit": "Checksums verify consistency. Operator attestation is required; logs are not cryptographic proof of real-world events."}

    try:
        root = Path(artifact_dir).expanduser().resolve(strict=True)
        if not root.is_dir() or not isinstance(manifest, dict):
            raise InvalidEvidence("invalid_input")
        no_sensitive_keys(manifest)
        if not check("manifest_submitted_demo", manifest.get("schemaVersion") == 1 and
                     manifest.get("status") == "SUBMITTED" and manifest.get("model") == MODEL and
                     manifest.get("environment") == "DEMO" and manifest.get("origin") == "ACTUAL_DEMO"):
            return result()
        run = manifest["run_id"]
        model_hash = manifest["model_sha256"]
        if not isinstance(run, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", run) or not HASH.fullmatch(model_hash):
            raise InvalidEvidence("invalid_identity")
        refs = manifest["artifacts"]
        if set(refs) != set(REQUIRED):
            raise InvalidEvidence("missing_artifacts")
        hashes = {name: reference["sha256"] for name, reference in refs.items()}
        for name in REQUIRED:
            raw = read_verified(root, refs[name])
            if name != "model":
                evidence[name] = parse(raw)
                no_sensitive_keys(evidence[name])
        check("artifact_hashes_and_model_match", hashes["model"] == model_hash)
        att = manifest["operator_attestation"]
        reviewed = utc(att["reviewed_at_utc"])
        check("actual_demo_operator_review", att.get("statement") == ATTESTATION and
              att.get("actual_demo_verified") is True and att.get("not_synthetic") is True and
              isinstance(att.get("alias"), str) and bool(re.fullmatch(r"[A-Za-z0-9_-]{1,40}", att["alias"])) and
              att.get("reviewed_artifact_sha256") == hashes and 0 <= (now - reviewed).total_seconds() <= 86400)
        for name in ("runtime", "disconnect", "ticks", "decisions", "recovery", "management", "blocking"):
            item = evidence[name]
            check(name + "_identity", item.get("schemaVersion") == 1 and item.get("run_id") == run and
                  item.get("environment") == "DEMO" and item.get("origin") == "ACTUAL_DEMO" and
                  item.get("model_sha256") == model_hash)
    except (InvalidEvidence, OSError, ValueError, TypeError, KeyError, AttributeError):
        check("valid_local_artifacts_and_attestation", False)
        return result()

    def bounded(name, fn):
        try:
            check(name, fn())
        except (ValueError, TypeError, KeyError, AttributeError, IndexError, ZeroDivisionError):
            check(name, False)

    def baseline():
        p, r = evidence["baseline_promotion"], evidence["baseline_review"]
        return (p.get("status") == "ELIGIBLE_FOR_HUMAN_REVIEW" and p.get("reasons") == [] and
                r.get("status") == "PASSED_REVIEWED" and r.get("model_sha256") == model_hash and
                r.get("promotion_sha256") == hashes["baseline_promotion"] and r.get("genuine_unseen") is True and
                r.get("external_inputs_complete") is True and r.get("broker_cost_history_verified") is True and
                r["campaigns"] >= 100 and r["trading_days"] >= 60 and r["expectancy_ci95_low"] > 0 and
                r["baseline_profit_factor"] > 1.2 and r["stress_profit_factor"] > 1 and
                0 <= r["max_drawdown"] <= .15 and r["safety_failures"] == 0 and
                2 / 3 <= r["positive_walkforward_fraction"] <= 1 and r.get("reviewer_approved") is True)

    def runtime():
        r = evidence["runtime"]
        return (r.get("host") == "WINDOWS_VPS" and r.get("runtime_llm_calls") == 0 and
                type(r.get("runtime_llm_calls")) is int and r.get("mac_dependency") is False and
                r.get("chat_dependency") is False and r.get("cloud_dependency") is False and
                r.get("telegram_dependency") is False and r.get("process_kind") == "DETERMINISTIC_DEMO_ENGINE" and
                r.get("execution_mode") == "DEMO" and r.get("symbol") == "XAUUSD" and
                r.get("baseline_promotion_sha256") == hashes["baseline_promotion"])

    window = evidence["disconnect"]

    def disconnect():
        begin, end = utc(window["begin_utc"]), utc(window["end_utc"])
        samples = window["samples"]
        ticks = evidence["ticks"]["records"]
        decisions = evidence["decisions"]["records"]
        if not (900 <= (end - begin).total_seconds() and 0 <= (now - end).total_seconds() <= 86400 and
                end <= reviewed and len(samples) >= 31 and len(ticks) >= 30 and len(decisions) >= 3):
            return False
        sample_times = [utc(s["at_utc"]) for s in samples]
        if (sample_times[0] < begin or (sample_times[0] - begin).total_seconds() > 30 or
                sample_times[-1] > end or (end - sample_times[-1]).total_seconds() > 30 or
                any(not 0 < (b-a).total_seconds() <= 30 for a, b in zip(sample_times, sample_times[1:]))):
            return False
        for s in samples:
            if (any(s.get(key) is not False for key in ("mac_connected", "chat_connected", "cloud_connected", "telegram_connected")) or
                    any(s.get(key) is not True for key in ("engine_running", "broker_connected", "data_fresh")) or
                    type(s.get("runtime_llm_calls")) is not int or s["runtime_llm_calls"] != 0 or
                    s.get("ambiguous_state") is not False):
                return False
        tick_times = [utc(t["at_utc"]) for t in ticks]
        if any(not begin <= t <= end for t in tick_times) or any(a >= b for a, b in zip(tick_times, tick_times[1:])):
            return False
        for t in ticks:
            if (t.get("source") != "BROKER_DEMO" or not number(t.get("bid")) or not number(t.get("ask")) or
                    not 0 < t["bid"] <= t["ask"] or not 0 <= (utc(t["at_utc"]) - utc(t["broker_tick_utc"])).total_seconds() <= 10):
                return False
        # Fresh ticks must span the disconnect test, not be a burst at its start.
        if ((tick_times[0]-begin).total_seconds() > 30 or (end-tick_times[-1]).total_seconds() > 30 or
                any((b-a).total_seconds() > 30 for a, b in zip(tick_times, tick_times[1:]))):
            return False
        decision_times = [utc(d["decision_utc"]) for d in decisions]
        if len(set(decision_times)) != len(decisions) or decision_times != sorted(decision_times):
            return False
        previous_hash = "0" * 64
        for d in decisions:
            if not begin <= utc(d["recorded_utc"]) <= end or not 0 <= (utc(d["recorded_utc"]) - utc(d["decision_utc"])).total_seconds() <= 30:
                return False
            if d.get("source") != "BROKER_DEMO" or d.get("model_sha256") != model_hash or d.get("previous_hash") != previous_hash:
                return False
            decision = utc(d["decision_utc"])
            if (decision.minute % 5 or decision.second or decision.microsecond or
                    (decision - utc(d["bar_open_utc"])).total_seconds() != 300 or
                    d.get("action") not in ("LONG", "SHORT", "WAIT") or type(d.get("ready")) is not bool or
                    d.get("mode") not in ("NORMAL", "AGGRESSIVE", "EXTREME", "FROZEN", "KILL") or
                    ((not d["ready"] or d["mode"] in ("FROZEN", "KILL")) and d["action"] != "WAIT")):
                return False
            payload = {k: v for k, v in d.items() if k != "record_hash"}
            actual = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
            if d.get("record_hash") != actual:
                return False
            previous_hash = actual
        return (begin <= decision_times[0] <= end and begin <= decision_times[-1] <= end and
                (decision_times[-1] - decision_times[0]).total_seconds() >= 600)

    events = evidence["management"].get("events", [])
    event_map = {}

    def management():
        if not isinstance(events, list) or not events:
            return False
        previous = None
        for e in events:
            at = utc(e["at_utc"])
            if (e["id"] in event_map or e.get("source") != "BROKER_DEMO" or e.get("confirmed") is not True or
                    e.get("ambiguous") is not False or at > reviewed or (now-at).total_seconds() > 86400 or
                    (previous is not None and at < previous)):
                return False
            previous = at; event_map[e["id"]] = e
        entries = [e for e in events if e["kind"] in ("ENTRY_CONFIRMED", "PYRAMID_ADDED")]
        if not entries:
            return False
        kills = [utc(e["at_utc"]) for e in events if e["kind"] == "KILL_TRIGGERED"]
        if kills and any(utc(e["at_utc"]) >= min(kills) for e in entries):
            return False
        positions = {}
        for entry in entries:
            prior = [e for e in events if e.get("process_instance") == entry["process_instance"] and utc(e["at_utc"]) < utc(entry["at_utc"])]
            if any(not any(e["kind"] == kind for e in prior) for kind in ("ORDERS_RECONCILED", "POSITIONS_RECONCILED", "PROTECTION_CONFIRMED")):
                return False
            if (not number(entry.get("lots")) or entry["lots"] <= 0 or not HASH.fullmatch(entry.get("position_hash", "")) or
                    entry["position_hash"] in positions or not number(entry.get("price")) or entry["price"] <= 0 or
                    entry.get("symbol") != "XAUUSD"):
                return False
            positions[entry["position_hash"]] = entry
            for kind in ("SL_CONFIRMED", "TP_CONFIRMED"):
                if not any(e["kind"] == kind and e.get("position_hash") == entry["position_hash"] and
                           0 <= (utc(e["at_utc"])-utc(entry["at_utc"])).total_seconds() <= 10 and
                           number(e.get("price")) and e["price"] > 0 for e in events):
                    return False
        kinds = {e["kind"] for e in events}
        if not {"SL_FILLED", "TP_FILLED", "PYRAMID_ADDED", "KILL_TRIGGERED", "FLAT_CONFIRMED"} <= kinds:
            return False
        adds = [e for e in entries if e["kind"] == "PYRAMID_ADDED"]
        if any(e.get("winner_confirmed") is not True or e.get("all_prior_legs_protected") is not True or
               e.get("risk_caps_passed") is not True or not number(e.get("floating_pnl_before")) or
               e["floating_pnl_before"] <= 0 or not any(b["kind"] == "ENTRY_CONFIRMED" and
                   b.get("campaign") == e.get("campaign") and utc(b["at_utc"]) < utc(e["at_utc"]) for b in entries)
               for e in adds):
            return False
        if any(sum(e.get("campaign") == c for e in adds) > 2 for c in {e.get("campaign") for e in adds}):
            return False
        fill_totals = {}
        for fill in events:
            if fill["kind"] not in ("SL_FILLED", "TP_FILLED"):
                continue
            position = positions.get(fill.get("position_hash"))
            if (position is None or utc(fill["at_utc"]) < utc(position["at_utc"]) or
                    not number(fill.get("lots")) or fill["lots"] <= 0 or
                    not number(fill.get("price")) or fill["price"] <= 0):
                return False
            key = fill["position_hash"]
            fill_totals[key] = fill_totals.get(key, 0) + fill["lots"]
            if fill_totals[key] > position["lots"] + 1e-9:
                return False
        return all(any(e["kind"] == "FLAT_CONFIRMED" and e.get("campaign") == kill.get("campaign") and
                       type(e.get("broker_positions_remaining")) is int and e["broker_positions_remaining"] == 0 and
                       type(e.get("broker_orders_remaining")) is int and e["broker_orders_remaining"] == 0 and
                       utc(e["at_utc"]) >= utc(kill["at_utc"]) for e in events)
                   for kill in events if kill["kind"] == "KILL_TRIGGERED")

    def recovery():
        cases = evidence["recovery"]["cases"]
        if {c["kind"] for c in cases} != {"CRASH_RECOVERY", "UNATTENDED_BOOT"} or len(cases) != 2:
            return False
        intervals, instances, recovery_ids = [], set(), set()
        for c in cases:
            start, end = utc(c["begin_utc"]), utc(c["end_utc"])
            if not start < end <= reviewed or (now-end).total_seconds() > 86400:
                return False
            if c.get("started_without_interactive_login") is not True or c.get("trigger") not in ("ATSTARTUP", "WINDOWS_SERVICE") or c["old_instance"] == c["new_instance"]:
                return False
            ids = c["event_ids"]
            if (c["new_instance"] in instances or any(start <= old_end and old_start <= end for old_start, old_end in intervals)
                    or len(ids) != len(set(ids)) or recovery_ids.intersection(ids)):
                return False
            instances.add(c["new_instance"]); intervals.append((start, end)); recovery_ids.update(ids)
            selected = [event_map[i] for i in ids]
            if any(e.get("process_instance") != c["new_instance"] or not start <= utc(e["at_utc"]) <= end for e in selected):
                return False
            kinds = {e["kind"] for e in selected}
            if not {"ORDERS_RECONCILED", "POSITIONS_RECONCILED", "PROTECTION_CONFIRMED", "ENTRY_CONFIRMED"} <= kinds:
                return False
        return True

    def blocking():
        cases = evidence["blocking"]["cases"]
        required = {"REAL_ACCOUNT", "AMBIGUOUS_ORDER", "MISSING_STATE", "STALE_DATA", "UNCONFIRMED_PROTECTION", "BASELINE_NOT_PASSED"}
        if {x["case"] for x in cases} != required or len(cases) != len(required):
            return False
        for c in cases:
            event = event_map[c["event_id"]]
            if (c.get("environment") != "DEMO" or c.get("fault_injection") is not True or
                    c.get("order_send_count") != 0 or type(c.get("order_send_count")) is not int or
                    event["kind"] != "ENTRY_BLOCKED" or event.get("reason") != c["case"]):
                return False
        return True

    bounded("independent_strategy_baseline_passed_and_reviewed", baseline)
    bounded("deterministic_vps_runtime_without_external_dependencies", runtime)
    bounded("supervised_disconnect_15_minutes_with_live_activity", disconnect)
    bounded("actual_position_management_and_reconciliation", management)
    bounded("crash_and_unattended_boot_recovery", recovery)
    bounded("unsafe_states_block_new_entry", blocking)
    return result()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--artifact-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        raw = args.manifest.read_bytes()
        if len(raw) > MAX_BYTES:
            raise InvalidEvidence("manifest_too_large")
        output = evaluate(parse(raw), args.artifact_dir)
    except (OSError, ValueError, TypeError):
        output = {"status": "NOT_READY", "failedChecks": ["manifest_unreadable_or_invalid"],
                  "realTradingEnabled": False, "executionEnabledByEvaluator": False, "actionsPerformed": []}
    print(json.dumps(output, indent=2, allow_nan=False))
    return 0 if output["status"] == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
