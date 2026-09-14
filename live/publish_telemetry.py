"""Opt-in private HTTPS publisher. Default --check performs no network request."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, Request

MAX_BYTES = 128 * 1024
REPO = Path(__file__).resolve().parents[1]


class PublisherStop(RuntimeError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


@dataclass(frozen=True)
class PublisherConfig:
    endpoint: str
    token: str
    status_path: Path

    def __post_init__(self):
        u = urlsplit(self.endpoint)
        if u.scheme != "https" or not u.hostname or u.username or u.password or u.query or u.fragment or u.port not in (None, 443):
            raise PublisherStop("https_endpoint_without_url_credentials_required")
        if not re.fullmatch(r"[a-f0-9]{64}", self.token):
            raise PublisherStop("private_ingest_token_required")
        path = Path(self.status_path).expanduser().resolve()
        if path == REPO or REPO in path.parents:
            raise PublisherStop("status_must_be_outside_checkout")
        object.__setattr__(self, "status_path", path)

    @classmethod
    def from_env(cls, env):
        try:
            return cls(env["VORTEX_INGEST_ENDPOINT"], env["VORTEX_INGEST_TOKEN"], Path(env["VORTEX_STATE_DIR"]) / "status.json")
        except (KeyError, ValueError):
            raise PublisherStop("private_publisher_configuration_required") from None


def exact_keys(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= value.keys() or not value.keys() <= set(required) | set(optional):
        raise PublisherStop("snapshot_allowlist_failed")


def scalar_number(value, low=-1e12, high=1e12, nullable=False):
    if nullable and value is None:
        return
    try:
        valid = type(value) in (int, float) and math.isfinite(value) and low <= value <= high
    except OverflowError:
        valid = False
    if not valid:
        raise PublisherStop("snapshot_numeric_leaf_invalid")


def scalar_text(value, pattern, limit):
    if not isinstance(value, str) or not 1 <= len(value) <= limit or not re.fullmatch(pattern, value):
        raise PublisherStop("snapshot_text_leaf_invalid")


def scalar_time(value, utc=True):
    pattern = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z" if utc else r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    scalar_text(value, pattern, 24)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00") if utc else value + "+00:00").timestamp()
    except ValueError:
        raise PublisherStop("snapshot_time_leaf_invalid") from None


def check_leaves(s):
    """Every allowed leaf is typed before transfer; no arbitrary nested payloads."""
    scalar_text(s["sessionId"], r"[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[1-8][a-fA-F0-9]{3}-[89abAB][a-fA-F0-9]{3}-[a-fA-F0-9]{12}", 36)
    if type(s["sequence"]) is not int or not 0 <= s["sequence"] <= 9007199254740991:
        raise PublisherStop("snapshot_sequence_invalid")
    started, produced = scalar_time(s["sessionStartedAt"]), scalar_time(s["producedAt"])
    if started > produced:
        raise PublisherStop("snapshot_clock_invalid")
    if s["status"]["demoVerified"] and s["account"] is None:
        raise PublisherStop("verified_account_missing")
    if s["account"] is not None:
        for key in ("balance", "equity", "freeMargin", "margin"):
            scalar_number(s["account"][key], low=0 if key == "margin" else -1e12)
    if s["quote"] is not None:
        q = s["quote"]
        scalar_number(q["bid"], 1e-300, 1e9); scalar_number(q["ask"], 1e-300, 1e9)
        if q["ask"] < q["bid"] or scalar_time(q["changedAtUtc"]) > produced + 30:
            raise PublisherStop("snapshot_quote_invalid")
        if "brokerTimeServer" in q or "brokerTimeBasis" in q:
            if q.get("brokerTimeBasis") != "broker_server_unknown_offset":
                raise PublisherStop("snapshot_broker_time_invalid")
            scalar_time(q.get("brokerTimeServer"), False)
    ids = set()
    for p in s["positions"]:
        if p["side"] not in ("buy", "sell") or p["id"] in ids:
            raise PublisherStop("snapshot_position_invalid")
        ids.add(p["id"])
        scalar_number(p["lots"], 1e-300, 200)
        for key in ("openPrice", "currentPrice"):
            scalar_number(p[key], 1e-300, 1e9)
        scalar_number(p["profit"])
        for key in ("stopLoss", "takeProfit"):
            if key in p:
                scalar_number(p[key], 1e-300, 1e9, True)
    strategy = s["strategy"]
    scalar_text(strategy["name"], r"VORTEX(?:-[A-Z0-9]+)*", 64)
    scalar_text(strategy["version"], r"[A-Za-z0-9._-]+", 32)
    for key in ("state", "reason"):
        if key in strategy:
            scalar_text(strategy[key], r"[a-z0-9_:-]+", 80)
    if strategy["runnerMode"] not in ("observe", "armed"):
        raise PublisherStop("snapshot_runner_mode_invalid")
    if "signal" in s:
        sig = s["signal"]
        scalar_time(sig["decisionTimeServer"], False)
        offset = sig["sessionUtcOffsetMinutes"]
        if offset is not None and (type(offset) is not int or not -840 <= offset <= 840):
            raise PublisherStop("snapshot_offset_invalid")
        if type(sig["ready"]) is not bool or type(sig["direction"]) is not int or sig["direction"] not in (-1, 0, 1) or (not sig["ready"] and sig["direction"] != 0):
            raise PublisherStop("snapshot_signal_invalid")
        scalar_number(sig["atr"], 1e-300, 1e9, True); scalar_number(sig["consensus"], -100, 100, True)
        if sig["scores"] is not None:
            for value in sig["scores"].values():
                scalar_number(value, -100, 100, True)
        if sig["ready"] and (sig["atr"] is None or sig["consensus"] is None or sig["scores"] is None or any(x is None for x in sig["scores"].values())):
            raise PublisherStop("snapshot_signal_not_ready")
    if "v02" in s:
        v = s["v02"]
        if v["mode"] not in ("NORMAL", "AGGRESSIVE", "EXTREME", "FROZEN", "KILL") or v["action"] not in ("LONG", "SHORT", "WAIT"):
            raise PublisherStop("v02_mode_invalid")
        for key, value in v["metrics"].items():
            dd = key in ("dailyDrawdown", "maxDrawdown")
            nonnegative = dd or key in ("usedMargin", "openRisk", "lockedProfit")
            scalar_number(value, 0 if nonnegative else -1e12, 1 if dd else 1e12, True)
        context = v["context"]
        if context["session"] is not None and context["session"] not in ("ASIA", "LONDON", "NEWYORK", "LONDON_NEWYORK", "OTHER"):
            raise PublisherStop("v02_session_invalid")
        scalar_number(context["atr"], 1e-300, 1e9, True)
        text_pattern = r"[A-Za-z0-9 _.,:()/+\-]+"
        for key in ("volatilityState", "nextNews"):
            if context[key] is not None:
                scalar_text(context[key], text_pattern, 40 if key == "volatilityState" else 160)
        for name, engine in v["engines"].items():
            scalar_number(engine["score"], 0 if name == "kira" else -100, 100, True)
            if engine["status"] not in ("PASS", "FAIL", "INVALID") or (engine["status"] != "INVALID" and engine["score"] is None):
                raise PublisherStop("v02_engine_invalid")
            scalar_text(engine["reason"], text_pattern, 160)
        scalar_number(v["consensus"], -100, 100, True)
        protection = v["protection"]
        for key in ("confirmed", "killSwitch", "brokerConnected", "dataFresh"):
            if not (key == "confirmed" and protection[key] is None) and type(protection[key]) is not bool:
                raise PublisherStop("v02_protection_invalid")
        scalar_number(protection["latencyMs"], 0, 3600000, True)
        previous = -float("inf")
        for item in v["journal"]:
            stamp = scalar_time(item["time"])
            if stamp < previous:
                raise PublisherStop("v02_journal_order_invalid")
            previous = stamp
            scalar_text(item["event"], text_pattern, 48); scalar_text(item["reason"], text_pattern, 160)
        if v.get("position") is not None:
            p = v["position"]
            for key in ("averageEntry", "sl", "tp1", "tp2"):
                scalar_number(p[key], 1e-300, 1e9, True)
            scalar_number(p["runnerLots"], 0, 200, True)
            if type(p["pyramidCount"]) is not int or not 0 <= p["pyramidCount"] <= 3:
                raise PublisherStop("v02_pyramid_invalid")


def validate_publication(s, now):
    """Local privacy whitelist before crossing the network; cloud validates all types."""
    exact_keys(s, ("schemaVersion", "mode", "sessionId", "sessionStartedAt", "sequence", "producedAt", "quote", "status", "account", "positions", "strategy"), ("signal", "v02"))
    if type(s["schemaVersion"]) is not int or s["schemaVersion"] != 1 or s["mode"] != "demo":
        raise PublisherStop("demo_snapshot_required")
    exact_keys(s["status"], ("terminalConnected", "algoTradingEnabled", "eaRunning", "demoVerified"))
    if not all(isinstance(x, bool) for x in s["status"].values()):
        raise PublisherStop("snapshot_status_invalid")
    if not s["status"]["demoVerified"] and (s["account"] is not None or s["quote"] is not None or s["positions"] != []):
        raise PublisherStop("unverified_snapshot_not_redacted")
    if s["account"] is not None:
        exact_keys(s["account"], ("currency", "balance", "equity", "freeMargin", "margin"))
        if s["account"]["currency"] != "USD":
            raise PublisherStop("usd_snapshot_required")
    if s["quote"] is not None:
        exact_keys(s["quote"], ("symbol", "bid", "ask", "changedAtUtc"), ("brokerTimeServer", "brokerTimeBasis"))
        if s["quote"]["symbol"] != "XAUUSD":
            raise PublisherStop("xauusd_snapshot_required")
    if not isinstance(s["positions"], list) or len(s["positions"]) > 20:
        raise PublisherStop("snapshot_positions_invalid")
    for p in s["positions"]:
        exact_keys(p, ("id", "side", "lots", "openPrice", "currentPrice", "profit"), ("stopLoss", "takeProfit"))
        if not isinstance(p["id"], str) or not re.fullmatch(r"[a-f0-9]{64}", p["id"]):
            raise PublisherStop("anonymous_position_id_required")
    exact_keys(s["strategy"], ("name", "version", "state", "runnerMode"), ("reason",))
    if "signal" in s:
        exact_keys(s["signal"], ("decisionTimeServer", "sessionUtcOffsetMinutes", "ready", "direction", "atr", "consensus", "scores"))
        if s["signal"]["scores"] is not None:
            exact_keys(s["signal"]["scores"], ("orion", "vortex", "nova", "luna", "kira", "atlas"))
    if "v02" in s:
        v = s["v02"]
        exact_keys(v, ("model", "environment", "mode", "action", "metrics", "context", "engines", "consensus", "protection", "journal"), ("position",))
        if v["model"] != "VORTEX-XAU-EXTREME-v0.2" or v["environment"] not in ("PAPER", "DEMO"):
            raise PublisherStop("v02_demo_model_required")
        exact_keys(v["metrics"], ("balance", "equity", "floatingPnl", "realizedPnl", "dailyPnl", "dailyDrawdown", "maxDrawdown", "freeMargin", "usedMargin", "openRisk", "lockedProfit", "currentR"))
        if not s["status"]["demoVerified"] and (any(x is not None for x in v["metrics"].values()) or v.get("position") is not None):
            raise PublisherStop("v02_unverified_metrics_not_redacted")
        exact_keys(v["context"], ("session", "atr", "volatilityState", "nextNews"))
        exact_keys(v["engines"], ("orion", "vortex", "nova", "luna", "kira", "atlas"))
        for engine in v["engines"].values():
            exact_keys(engine, ("score", "status", "reason"))
        exact_keys(v["protection"], ("confirmed", "killSwitch", "latencyMs", "brokerConnected", "dataFresh"))
        if not isinstance(v["journal"], list) or len(v["journal"]) > 50:
            raise PublisherStop("v02_journal_invalid")
        for item in v["journal"]:
            exact_keys(item, ("time", "event", "reason"))
        if v.get("position") is not None:
            exact_keys(v["position"], ("averageEntry", "sl", "tp1", "tp2", "runnerLots", "pyramidCount"))
    check_leaves(s)
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z", s["producedAt"]):
            raise ValueError()
        produced = datetime.fromisoformat(s["producedAt"].replace("Z", "+00:00")).timestamp()
        if not now - 120 <= produced <= now + 30:
            raise ValueError()
    except (ValueError, TypeError):
        raise PublisherStop("snapshot_expired_or_bad_timestamp") from None
    return s


def load_snapshot(path, now):
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise PublisherStop("snapshot_too_large")
        s = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        validate_publication(s, now)
        return json.dumps(s, allow_nan=False, separators=(",", ":")).encode()
    except PublisherStop:
        raise
    except (OSError, ValueError, TypeError, KeyError):
        raise PublisherStop("snapshot_invalid_or_unavailable") from None


def publish_once(config, now=None, opener=None):
    body = load_snapshot(config.status_path, time.time() if now is None else now)
    request = Request(config.endpoint, data=body, method="POST", headers={"Authorization": f"Bearer {config.token}", "Content-Type": "application/json"})
    try:
        with (opener or build_opener(NoRedirect())).open(request, timeout=10) as response:
            status = response.status
            data = json.loads(response.read(4096))
        if status != 200 or data.get("reason") not in ("accepted", "duplicate"):
            return "response_invalid"
        return data["reason"]
    except HTTPError as error:
        if error.code == 409:
            return "not_newer"
        if error.code in (401, 403):
            return "authorization_failed"
        if 300 <= error.code < 400:
            return "redirect_rejected"
        return "http_rejected"
    except (URLError, TimeoutError, OSError, ValueError, TypeError):
        return "temporarily_unavailable"


def main(argv=None, env=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true")
    group.add_argument("--publish", action="store_true")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv); env = os.environ if env is None else env
    try:
        config = PublisherConfig.from_env(env)
        if not args.publish:
            print("Publisher configuration valid; no network request made."); return 0
        if env.get("VORTEX_BASELINE_STATUS") != "passed_reviewed":
            raise PublisherStop("reviewed_baseline_required")
        previous = None
        while not (config.status_path.parent / "STOP").exists():
            result = publish_once(config)
            if result != previous:
                print(f"Telemetry publisher: {result}", flush=True); previous = result
            if result in ("authorization_failed", "redirect_rejected", "response_invalid", "http_rejected", "not_newer"):
                return 2
            if args.once:
                return 0 if result in ("accepted", "duplicate") else 2
            time.sleep(15)
        return 0
    except PublisherStop as error:
        print(f"Publisher inactive: {error}", file=sys.stderr); return 2
    except KeyboardInterrupt:
        return 0
    except Exception:
        print("Publisher stopped: private_runtime_review_required", file=sys.stderr); return 3


if __name__ == "__main__":
    raise SystemExit(main())
