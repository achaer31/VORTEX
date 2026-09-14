"""Read-only structural and timeframe-consistency audit for VortexExport CSVs.

No prices are filled, no market calendar is inferred, and no strategy is tested.
All datetimes remain naive broker clock values with unknown historical offset.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

TIME_BASIS = "broker_server_unknown_offset"
TICK_SIZE = Decimal("0.001")
TIMEFRAMES = {"M5": 300, "M15": 900, "H1": 3600}
HEADERS = ["bar_open_server", "timezone", "symbol", "timeframe", "open",
           "high", "low", "close", "tick_volume", "spread_points", "real_volume"]
PRICE_FIELDS = ("open", "high", "low", "close")
SUM_FIELDS = ("tick_volume", "real_volume")
COMPARE_FIELDS = PRICE_FIELDS + SUM_FIELDS
MANIFEST_KEYS = {
    "schema_version", "symbol", "timezone", "snapshot_server_time", "terminal_build",
    "requested_history_days", "closed_bar_rule", "retry_policy", "run_status",
    "metadata_written", "all_timeframes_have_written_bars", "filename",
    "requested_start_server", "requested_end_exclusive_server", "period_seconds",
    "copy_rates_return", "copy_rates_error", "copy_elapsed_ms", "series_synchronized",
    "terminal_first_bar_server", "server_first_bar_server", "latest_series_bar_open_server",
    "effective_closed_end_exclusive_server", "export_status", "history_incomplete",
    "actual_count", "actual_first_open_server", "actual_last_open_server",
    "skipped_open_or_out_of_range_count", "rejected_invalid_or_nonascending_count",
    "observed_gap_count", "largest_gap_seconds", "start_coverage_short",
    "end_coverage_short", "completeness_verified", "gap_interpretation", "write_error",
}


def _iso(value: datetime | None) -> str | None:
    return value.isoformat(timespec="seconds") if value else None


def _time(value: str) -> datetime:
    parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S")
    if _iso(parsed) != value:
        raise ValueError("Timestamp must exactly match YYYY-MM-DDTHH:MM:SS")
    return parsed


def _integer(value: str) -> int:
    parsed = Decimal(value)
    if not parsed.is_finite() or parsed != parsed.to_integral_value() or parsed < 0:
        raise ValueError("Expected finite nonnegative integer")
    return int(parsed)


def _price_ticks(value: str) -> int:
    price = Decimal(value)
    if not price.is_finite() or price <= 0:
        raise ValueError("Expected finite positive price")
    ticks = price / TICK_SIZE
    if ticks != ticks.to_integral_value():
        raise ValueError("Price not on 0.001 tick grid")
    return int(ticks)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_manifest(path: Path) -> dict:
    result = {"present": path.is_file(), "values": {}, "statuses": {},
              "duplicate_keys": 0, "parse_errors": [], "sha256": None}
    if not path.is_file():
        return result
    result["sha256"] = _sha256(path)
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != ["scope", "key", "value", "status"]:
                result["parse_errors"].append("unexpected_manifest_header")
                return result
            for row in reader:
                scope, key = row.get("scope"), row.get("key")
                if scope not in {"export", *TIMEFRAMES} or key not in MANIFEST_KEYS:
                    continue
                values = result["values"].setdefault(scope, {})
                statuses = result["statuses"].setdefault(scope, {})
                result["duplicate_keys"] += int(key in values)
                values[key] = row.get("value")
                statuses[key] = row.get("status")
    except (UnicodeError, csv.Error) as error:
        result["parse_errors"].append(type(error).__name__)
    return result


def _read_bars(path: Path, timeframe: str, symbol: str | None) -> tuple[dict, list[dict]]:
    report = {"filename": path.name, "sha256": _sha256(path), "rows": 0,
              "valid_rows": 0, "bad_rows": 0, "header_ok": False,
              "structural_errors": {}, "bad_row_examples": [], "structural_ok": False,
              "time_basis_values": [], "symbols": [], "period": {"first": None, "last": None},
              "observed_gaps": 0, "largest_gap_seconds": 0}
    errors, times, symbols, bases, parsed_rows = Counter(), [], set(), set(), []
    previous, seen = None, set()
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != HEADERS:
            report["structural_errors"] = {"unexpected_header": 1}
            return report, []
        report["header_ok"] = True
        for line_number, row in enumerate(reader, 2):
            report["rows"] += 1
            reasons, parsed = set(), {}
            if None in row or any(row.get(field) is None for field in HEADERS):
                reasons.add("wrong_column_count")
            basis = row.get("timezone")
            bases.add(basis or "")
            if basis != TIME_BASIS:
                reasons.add("invalid_time_basis")
            actual_symbol = row.get("symbol") or ""
            symbols.add(actual_symbol)
            if not actual_symbol.startswith("XAUUSD") or (symbol and actual_symbol != symbol):
                reasons.add("unexpected_symbol")
            if row.get("timeframe") != timeframe:
                reasons.add("unexpected_timeframe")
            try:
                current = _time(row.get("bar_open_server") or "")
                parsed["time"] = current
                times.append(current)
                seconds = current.hour * 3600 + current.minute * 60 + current.second
                if seconds % TIMEFRAMES[timeframe]:
                    reasons.add("unaligned_timestamp")
                if current in seen:
                    reasons.add("duplicate_timestamp")
                if previous is not None:
                    delta = int((current - previous).total_seconds())
                    if delta <= 0:
                        reasons.add("nonascending_timestamp")
                    elif delta > TIMEFRAMES[timeframe]:
                        report["observed_gaps"] += 1
                        report["largest_gap_seconds"] = max(report["largest_gap_seconds"], delta)
                seen.add(current)
                previous = current
            except ValueError:
                reasons.add("invalid_timestamp")
            for field in PRICE_FIELDS:
                try:
                    parsed[field] = _price_ticks(row.get(field) or "")
                except (ValueError, InvalidOperation):
                    reasons.add("invalid_" + field)
            if all(field in parsed for field in PRICE_FIELDS):
                if not (parsed["low"] <= min(parsed["open"], parsed["close"])
                        <= max(parsed["open"], parsed["close"]) <= parsed["high"]):
                    reasons.add("invalid_ohlc")
            for field in SUM_FIELDS + ("spread_points",):
                try:
                    parsed[field] = _integer(row.get(field) or "")
                except (ValueError, InvalidOperation):
                    reasons.add("invalid_" + field)
            if reasons:
                report["bad_rows"] += 1
                errors.update(reasons)
                if len(report["bad_row_examples"]) < 10:
                    report["bad_row_examples"].append({"line": line_number, "reasons": sorted(reasons)})
            else:
                parsed_rows.append(parsed)
    if report["rows"] == 0:
        errors["empty_file"] += 1
    if len(symbols) > 1:
        errors["mixed_symbols"] += 1
    report.update(valid_rows=len(parsed_rows), structural_errors=dict(sorted(errors.items())),
                  structural_ok=not errors, time_basis_values=sorted(bases), symbols=sorted(symbols),
                  period={"first": _iso(min(times)) if times else None,
                          "last": _iso(max(times)) if times else None})
    return report, parsed_rows


def _aggregate(m5: list[dict], higher: list[dict], timeframe: str) -> dict:
    seconds = TIMEFRAMES[timeframe]
    group_size = seconds // TIMEFRAMES["M5"]
    result = {"status": "compared", "source": "M5", "target": timeframe,
              "expected_m5_bars_per_group": group_size, "observed_groups": 0,
              "full_groups": 0, "skipped_incomplete": 0, "missing_htf": 0,
              "compared_groups": 0, "matching_groups": 0, "mismatching_groups": 0,
              "mismatches_by_field": {field: 0 for field in COMPARE_FIELDS},
              "mismatch_examples": [], "missing_htf_examples": [],
              "unrepresented_htf_bars": 0, "review_required": False,
              "price_comparison": "exact integer ticks of 0.001",
              "gap_policy": "Only observed buckets considered; no session filling or closure inference."}
    groups = defaultdict(list)
    for bar in m5:
        time = bar["time"]
        midnight = time.replace(hour=0, minute=0, second=0)
        bucket = midnight + timedelta(seconds=int((time - midnight).total_seconds()) // seconds * seconds)
        groups[bucket].append(bar)
    target = {row["time"]: row for row in higher}
    result["observed_groups"] = len(groups)
    result["unrepresented_htf_bars"] = len(set(target) - set(groups))
    for start, group in sorted(groups.items()):
        expected_times = [start + timedelta(minutes=5 * index) for index in range(group_size)]
        if len(group) != group_size or [bar["time"] for bar in group] != expected_times:
            result["skipped_incomplete"] += 1
            continue
        result["full_groups"] += 1
        if start not in target:
            result["missing_htf"] += 1
            if len(result["missing_htf_examples"]) < 10:
                result["missing_htf_examples"].append(_iso(start))
            continue
        computed = {"open": group[0]["open"], "high": max(row["high"] for row in group),
                    "low": min(row["low"] for row in group), "close": group[-1]["close"],
                    **{field: sum(row[field] for row in group) for field in SUM_FIELDS}}
        mismatches = [field for field in COMPARE_FIELDS if computed[field] != target[start][field]]
        result["compared_groups"] += 1
        if not mismatches:
            result["matching_groups"] += 1
            continue
        result["mismatching_groups"] += 1
        for field in mismatches:
            result["mismatches_by_field"][field] += 1
        if len(result["mismatch_examples"]) < 10:
            result["mismatch_examples"].append({"bar_open_server": _iso(start), "fields": {
                field: {"m5_aggregate": str(Decimal(computed[field]) * TICK_SIZE) if field in PRICE_FIELDS else computed[field],
                        "broker_htf": str(Decimal(target[start][field]) * TICK_SIZE) if field in PRICE_FIELDS else target[start][field]}
                for field in mismatches}})
    result["review_required"] = bool(result["missing_htf"] or result["mismatching_groups"])
    return result


def audit_export(run_dir: str | Path) -> dict:
    """Return a JSON-serializable audit; ``structural_ok`` excludes TF mismatch findings.

    Files must be named ``<XAUUSD symbol>_<M5|M15|H1>.csv`` and use the exporter
    schema. Missing/ambiguous files and malformed/empty data fail structure.
    Manifest discrepancies and valid-but-different HTF values require review;
    neither proves a bad raw row or a missing market session.
    """
    run_dir = Path(run_dir)
    if not run_dir.is_dir():
        raise NotADirectoryError(run_dir)
    manifest = _read_manifest(run_dir / "manifest.csv")
    symbol = manifest["values"].get("export", {}).get("symbol")
    report = {"schema_version": 1, "structural_ok": True, "time_basis": TIME_BASIS,
              "historical_utc_offset_verified": False, "tick_size": str(TICK_SIZE),
              "files": {}, "manifest": manifest, "aggregates": {}, "review_findings": [],
              "csv_sha256": {path.name: _sha256(path) for path in sorted(run_dir.glob("*.csv"))},
              "completeness_verified": False,
              "limitations": ["Gaps may be closures or absent history; no market calendar applied.",
                              "OHLC and bar spread cannot reconstruct intrabar Bid/Ask execution.",
                              "Passing structure and aggregation does not establish historical completeness."]}
    data = {}
    for timeframe in TIMEFRAMES:
        candidates = sorted(run_dir.glob(f"XAUUSD*_{timeframe}.csv"))
        if len(candidates) != 1:
            report["files"][timeframe] = {"structural_ok": False, "rows": 0,
                                        "structural_errors": {"missing_or_ambiguous_file": 1},
                                        "candidate_count": len(candidates)}
            data[timeframe] = []
            continue
        try:
            file_report, bars = _read_bars(candidates[0], timeframe, symbol)
        except (UnicodeError, csv.Error) as error:
            file_report, bars = ({"filename": candidates[0].name, "structural_ok": False,
                                 "rows": 0, "structural_errors": {type(error).__name__: 1}}, [])
        declared = manifest["values"].get(timeframe, {})
        comparisons = {}
        for key, actual in (("actual_count", str(file_report["rows"])),
                            ("actual_first_open_server", file_report.get("period", {}).get("first")),
                            ("actual_last_open_server", file_report.get("period", {}).get("last"))):
            if key in declared:
                comparisons[key] = declared[key] == actual
        file_report["manifest_check"] = {"declared_count": declared.get("actual_count"),
                                         "copy_rates_return": declared.get("copy_rates_return"),
                                         "checks": comparisons,
                                         "matches": all(comparisons.values()) if comparisons else None}
        if comparisons and not all(comparisons.values()):
            report["review_findings"].append(f"{timeframe}: manifest count or period discrepancy")
        report["files"][timeframe], data[timeframe] = file_report, bars
    report["structural_ok"] = all(item["structural_ok"] for item in report["files"].values())
    all_symbols = {symbol for item in report["files"].values() for symbol in item.get("symbols", [])}
    if len(all_symbols) > 1:
        report["structural_ok"] = False
        report["cross_file_structural_errors"] = ["inconsistent_symbols"]
    for timeframe in ("M15", "H1"):
        if report["files"]["M5"]["structural_ok"] and report["files"][timeframe]["structural_ok"] and len(all_symbols) == 1:
            report["aggregates"][timeframe] = _aggregate(data["M5"], data[timeframe], timeframe)
            if report["aggregates"][timeframe]["review_required"]:
                report["review_findings"].append(f"{timeframe}: aggregation differences require review")
        else:
            report["aggregates"][timeframe] = {"status": "skipped_due_to_structural_errors"}
    if not manifest["present"] or manifest["parse_errors"]:
        report["review_findings"].append("Manifest missing or unreadable; completeness claims not verified")
    elif manifest["values"].get("export", {}).get("timezone") != TIME_BASIS:
        report["review_findings"].append("Manifest time basis absent or differs from row time basis")
    report["review_required"] = bool(report["review_findings"])
    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit_export(args.run_dir)
    text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    raise SystemExit(0 if result["structural_ok"] else 1)
