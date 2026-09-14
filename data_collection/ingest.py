"""Offline prospective adapters. No networking, broker API, scores, or promotion.

Hashes establish byte consistency, not authenticity. Source/clock/coverage claims
need human review backed by provider documentation and actual acquisition logs.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import re

UTC = timezone.utc
MAX_BYTES = 16 * 1024 * 1024
NEWS_COLUMNS = ["event_time", "known_at", "currency", "impact", "title"]
COVERAGE_COLUMNS = ["start", "end", "known_at"]
MACRO_COLUMNS = ["observed_at", "available_at", "dxy", "us10y_yield"]


class InvalidData(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise InvalidData(message)


def utc(value):
    require(isinstance(value, str) and re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})", value),
        "explicit timezone timestamp required")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError as exc:
        raise InvalidData("invalid timestamp") from exc


def iso(value):
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def bounded_read(path):
    with Path(path).open("rb") as handle:
        data = handle.read(MAX_BYTES + 1)
    require(len(data) <= MAX_BYTES, "artifact too large")
    return data


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_parse(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result

    def nonfinite(_):
        raise InvalidData("nonfinite JSON number")

    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)
    except (ValueError, UnicodeError) as exc:
        raise InvalidData("invalid JSON artifact") from exc


def json_read(path):
    return json_parse(bounded_read(path))


def csv_read(data, columns):
    try:
        reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig")), strict=True)
        require(reader.fieldnames == columns, "unexpected CSV columns")
        rows = list(reader)
        require(all(None not in r and all(v is not None for v in r.values()) for r in rows),
                "CSV width mismatch")
        return rows
    except (csv.Error, UnicodeError) as exc:
        raise InvalidData("invalid CSV") from exc


def calendar_snapshot(directory, attestation=None):
    """Normalize ONE immutable snapshot; absent coverage review yields zero coverage.

    Receipt is after all metadata lookups. Review never backdates known_at. A
    coverage lease lasts at most five minutes from capture, not the query horizon.
    """
    root = Path(directory).resolve()
    paths = [root / "manifest.csv", root / "events.csv"]
    require(all(p.resolve().parent == root for p in paths), "snapshot symlink escapes directory")
    manifest_bytes, events_bytes = (bounded_read(p) for p in paths)
    entries = csv_read(manifest_bytes, ["key", "value"])
    require(len({r["key"] for r in entries}) == len(entries), "duplicate manifest field")
    m = {r["key"]: r["value"] for r in entries}
    require(m.get("schema") == "vortex.calendar.snapshot.v1" and
            m.get("origin") == "actual_terminal_capture" and
            m.get("currency_filter") == "USD", "wrong snapshot identity")
    require(m.get("run_status") == "captured_needs_review" and
            m.get("terminal_connected") == "true", "incomplete or disconnected snapshot")
    require(all(m.get(k) == "0" for k in ["query_error", "metadata_errors", "ambiguous_high_times"]),
            "calendar errors or ambiguous high-impact times")
    require(m.get("host_utc_clock_verified") == "true", "host UTC clock not verified")
    started, received = utc(m["started_at_utc"]), utc(m["received_at_utc"])
    start, end = utc(m["query_start_utc"]), utc(m["query_end_utc"])
    require(start < end and start <= started <= received <= end and
            received - started <= timedelta(seconds=60), "invalid or slow snapshot window")
    try:
        offset = int(m["server_utc_offset_minutes"])
        count = int(m["rows"])
    except (KeyError, ValueError) as exc:
        raise InvalidData("missing integer metadata") from exc
    require(-840 <= offset <= 840 and count >= 0, "unknown server timezone or count")
    raw = csv_read(events_bytes, ["value_id", "event_id", "event_time_server", "importance",
                                  "time_mode", "title", "source_url", "metadata_error"])
    require(len(raw) == count and len({r["value_id"] for r in raw}) == count,
            "calendar row count/identity mismatch")
    news = []
    for row in raw:
        require(row["metadata_error"] == "0" and row["value_id"].isdigit() and
                row["event_id"].isdigit(), "event metadata invalid")
        require(row["importance"] in {"CALENDAR_IMPORTANCE_NONE", "CALENDAR_IMPORTANCE_LOW",
                "CALENDAR_IMPORTANCE_MODERATE", "CALENDAR_IMPORTANCE_HIGH"}, "unknown importance")
        try:
            server = datetime.strptime(row["event_time_server"], "%Y-%m-%dT%H:%M:%S")
        except ValueError as exc:
            raise InvalidData("invalid server event time") from exc
        event = (server - timedelta(minutes=offset)).replace(tzinfo=UTC)
        require(start <= event <= end, "event outside query")
        if row["importance"] == "CALENDAR_IMPORTANCE_HIGH":
            require(row["time_mode"] == "CALENDAR_TIMEMODE_DATETIME" and row["title"].strip(),
                    "high-impact release has unknown time/title")
            news.append(dict(event_time=iso(event), known_at=iso(received),
                             currency="USD", impact="high", title=row["title"]))
    hashes = {"manifest.csv": digest(manifest_bytes), "events.csv": digest(events_bytes)}
    coverage = []
    if attestation is not None:
        a = json_read(attestation)
        require(isinstance(a, dict), "coverage review must be an object")
        require(a.get("schema") == "vortex.calendar.coverage-review.v1" and
                a.get("status") == "REVIEWED" and a.get("snapshot_sha256") == hashes,
                "missing review or snapshot hash mismatch")
        require(a.get("source") == "MT5_ECONOMIC_CALENDAR_USD" and
                a.get("scope") == "ALL_USD_HIGH_IMPACT_SCHEDULED_EVENTS" and
                all(a.get(k) is True for k in ["clock_and_offset_verified", "feed_current_verified",
                                                "query_scope_complete_verified"]),
                "coverage prerequisite unverified")
        require(isinstance(a.get("evidence_note"), str) and 20 <= len(a["evidence_note"]) <= 2000,
                "specific clock/feed/coverage evidence required")
        reviewed = utc(a["reviewed_at"])
        require(reviewed >= received, "coverage review predates capture")
        # A late review cannot manufacture earlier availability or extend freshness.
        known = max(received, reviewed)
        last_decision = min(received + timedelta(minutes=5), end - timedelta(minutes=10))
        require(known <= last_decision, "coverage review expired; capture again")
        coverage.append(dict(start=iso(max(start, received - timedelta(minutes=10))),
                             end=iso(last_decision + timedelta(minutes=10)), known_at=iso(known)))
    return dict(status="VALIDATED_FOR_REVIEW" if coverage else "NEEDS_COVERAGE_REVIEW",
                news=news, coverage=coverage, source_sha256=hashes,
                historical_coverage_proven=False, strategy_approval=False)


def macro_snapshots(path):
    """Validate normalized paired live samples; no provider connection is invented.

    Both receipt times come from actual collector logs. Pair observation uses the
    OLDER component time, so fresh DXY can never refresh an old Treasury yield.
    """
    raw_bytes = bounded_read(path)
    data = json_parse(raw_bytes)
    require(isinstance(data, dict), "macro capture must be an object")
    require(data.get("schema") == "vortex.macro.capture.v1" and
            data.get("status") == "CAPTURED" and data.get("origin") == "actual_live_capture" and
            data.get("host_utc_clock_verified") is True, "macro capture/clock not verified")
    sources = data.get("sources")
    require(isinstance(sources, dict) and set(sources) == {"dxy", "us10y_yield"}, "macro sources missing")
    for field, expected, units in [("dxy", "ICE_DXY_SPOT", "index_points"),
                                    ("us10y_yield", "US_TREASURY_10Y_YIELD", "percent_per_annum")]:
        source = sources[field]
        require(isinstance(source, dict) and source.get("instrument") == expected and
                source.get("normalized_unit") == units and source.get("reviewed") is True,
                "wrong/unreviewed macro instrument or unit")
        require(all(isinstance(source.get(k), str) and 1 <= len(source[k]) <= 500
                    for k in ["provider", "feed_symbol", "unit_conversion", "documentation_url"]),
                "source mapping metadata missing")
        require(source["documentation_url"].startswith("https://") and
                source.get("entitlement_confirmed") is True,
                "provider documentation/access unverified")
    samples = data.get("samples")
    require(isinstance(samples, list) and len(samples) >= 2, "two actual paired macro samples required")
    output, previous, prior_available = [], {}, None
    for sample in samples:
        require(isinstance(sample, dict) and set(sample) == set(sources), "wrong macro sample fields")
        times, receipts, values, now_components = [], [], {}, {}
        for field in sources:
            row = sample[field]
            require(isinstance(row, dict) and set(row) == {"observed_at", "received_at", "value"},
                    "wrong macro component fields")
            observed, received = utc(row["observed_at"]), utc(row["received_at"])
            value = row["value"]
            require(type(value) in (int, float) and math.isfinite(value), "invalid macro number")
            require(field != "dxy" or value > 0, "DXY must be positive")
            require(observed <= received, "macro received before observation")
            if field in previous:
                old_observed, old_value = previous[field]
                require(observed >= old_observed, "macro observation moved backward")
                require(observed != old_observed or value == old_value,
                        "same-time macro revision requires separate reviewed revision adapter")
            now_components[field] = (observed, value)
            times.append(observed); receipts.append(received); values[field] = value
        available, observed = max(receipts), min(times)
        require(available - observed <= timedelta(minutes=60), "macro pair already stale on receipt")
        require(prior_available is None or available > prior_available, "macro availability not unique/ascending")
        require(now_components != previous, "repeated observations cannot manufacture a second sample")
        output.append(dict(observed_at=iso(observed), available_at=iso(available), **values))
        previous, prior_available = now_components, available
    return dict(status="VALIDATED_FOR_REVIEW", macro=output, source_sha256=digest(raw_bytes),
                historical_coverage_proven=False, strategy_approval=False)


def write_result(directory, result):
    """Create a NEW private result directory; never append/merge snapshots implicitly."""
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=False)
    for key, filename, columns in [("news", "news.csv", NEWS_COLUMNS),
                                    ("coverage", "coverage.csv", COVERAGE_COLUMNS),
                                    ("macro", "macro.csv", MACRO_COLUMNS)]:
        if key in result:
            with (root / filename).open("x", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=columns)
                writer.writeheader(); writer.writerows(result[key])
    report = {k: v for k, v in result.items() if k not in {"news", "coverage", "macro"}}
    report["rows"] = {k: len(result[k]) for k in ["news", "coverage", "macro"] if k in result}
    (root / "validation.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="kind", required=True)
    for kind in ["calendar", "macro"]:
        p = sub.add_parser(kind)
        p.add_argument("input", type=Path)
        p.add_argument("--output", type=Path, help="optional NEW private directory")
        if kind == "calendar":
            p.add_argument("--attestation", type=Path)
    args = parser.parse_args(argv)
    try:
        result = (calendar_snapshot(args.input, args.attestation) if args.kind == "calendar"
                  else macro_snapshots(args.input))
        if args.output:
            write_result(args.output, result)
        print(json.dumps({"status": result["status"], "strategy_approval": False,
                          "rows": {k: len(result[k]) for k in ["news", "coverage", "macro"] if k in result}}))
        return 0 if result["status"] == "VALIDATED_FOR_REVIEW" else 2
    except (InvalidData, OSError, KeyError, TypeError, ValueError):
        print(json.dumps({"status": "REJECTED", "strategy_approval": False,
                          "reason": "invalid or unreadable capture; inspect locally with documented schema"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
