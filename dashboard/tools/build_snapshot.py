#!/usr/bin/env python3
"""Build a public, allowlisted historical dashboard snapshot; standard library only.

No account identifiers, server names, credentials, local paths, raw metadata or
raw experiment objects are copied into the output. Original CSVs remain local.
"""
import argparse
import csv
import hashlib
import json
import math
import re
import statistics
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from pathlib import Path

ENGINES = ("orion", "vortex", "nova", "luna", "kira", "atlas")
PERIODS = ("full", "development", "validation", "holdout")
TIME_BASIS = "broker_server_unknown_offset"
ISO = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")


def rows(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def timestamp(value):
    if not ISO.fullmatch(value):
        raise ValueError("Unexpected historical timestamp format")
    datetime.strptime(value, "%Y-%m-%dT%H:%M:%S")
    return value


def number(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Nonfinite value in public data")
    return result


def sample(sequence, count=48):
    if len(sequence) <= count:
        return sequence
    return [sequence[round(i * (len(sequence) - 1) / (count - 1))] for i in range(count)]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sizing_diagnosis(signal_rows, config):
    risks, long_count, short_count = [], 0, 0
    for previous, current in zip(signal_rows, signal_rows[1:]):
        if previous["ready"] != "True" or int(previous["signal"]) == 0:
            continue
        entry = datetime.fromisoformat(current["bar_open_server"])
        if not 8 <= entry.hour < 18:
            continue
        if datetime.fromisoformat(previous["bar_open_server"]) + timedelta(minutes=5) != entry:
            continue
        side = int(previous["signal"])
        long_count += side == 1
        short_count += side == -1
        spread = number(previous["spread_points"]) * config["point"] * config["spread_multiplier"]
        reference = number(current["open"]) + (spread if side == 1 else 0)
        raw = max(config["stop_atr_multiple"] * number(previous["atr"]),
                  config["min_stop_ticks"] * config["tick_size"])
        distance = math.ceil(raw / config["tick_size"]) * config["tick_size"]
        ref = Decimal(str(reference))
        tick = Decimal(str(config["tick_size"]))
        stop = ((ref - side * Decimal(str(distance))) / tick).to_integral_value(
            rounding=ROUND_CEILING if side == -1 else ROUND_FLOOR) * tick
        actual = float(abs(ref - stop))
        risks.append(config["lot_min"] * (config["contract_size"] *
                     (actual + 2 * config["slippage_per_ounce"]) +
                     2 * config["commission_per_lot_per_side"]))
    return {"candidates": len(risks), "long": long_count, "short": short_count,
            "minimumLot": config["lot_min"], "minimumRisk": min(risks) if risks else None,
            "medianRisk": statistics.median(risks) if risks else None,
            "maximumRisk": max(risks) if risks else None}


def build(results, data):
    if not (data / "XAUUSD_M5.csv").is_file():
        candidates = [p.parent for p in data.glob("*/XAUUSD_M5.csv")]
        if len(candidates) != 1:
            raise ValueError("--data must identify one exporter run")
        data = candidates[0]
    experiment = json.loads((results / "experiment.json").read_text())
    if (experiment.get("model_version") != "VORTEX-XAU-v0.1" or
            experiment.get("experiment_version") != "xau-50-fixed-grid-v0.1" or
            experiment.get("status") != "completed" or
            experiment.get("broker_time_basis") != TIME_BASIS):
        raise ValueError("Snapshot requires the completed VORTEX-XAU-v0.1 fixed-grid experiment")
    expected_hashes = experiment.get("raw_csv_sha256", {})
    for timeframe in ("M5", "M15", "H1"):
        filename = f"XAUUSD_{timeframe}.csv"
        if sha(data / filename) != expected_hashes.get(filename):
            raise ValueError(f"Candle provenance mismatch: {filename}")
    signal_rows = rows(results / "signals.csv")
    valid = [r for r in signal_rows if r["ready"] == "True"]
    if not valid:
        raise ValueError("No valid historical signal snapshot")
    if any(r["symbol"] != "XAUUSD" or r["timezone"] != TIME_BASIS for r in signal_rows):
        raise ValueError("Unexpected symbol or time basis")
    latest = valid[-1]
    candles, counts, hashes = {}, {}, {}
    for timeframe in ("M5", "M15", "H1"):
        path = data / f"XAUUSD_{timeframe}.csv"
        source = rows(path)
        if not source or any(r["symbol"] != "XAUUSD" or r["timezone"] != TIME_BASIS or
                             r["timeframe"] != timeframe for r in source):
            raise ValueError("Unexpected candle schema/identity")
        counts[timeframe] = len(source)
        hashes[timeframe] = sha(path)
        candles[timeframe] = [{"t": timestamp(r["bar_open_server"]),
                              **{short: number(r[key]) for short, key in
                                 (("o", "open"), ("h", "high"), ("l", "low"), ("c", "close"))},
                              "v": int(r["tick_volume"]), "spread": int(r["spread_points"])}
                             for r in source[-200:]]
    scenarios, configs = [], {}
    for period in PERIODS:
        for risk_label in ("3", "5", "7p5", "10"):
            for cost in ("baseline", "stress"):
                ident = f"{period}_risk{risk_label}_{cost}"
                folder = results / "scenarios" / ident
                s = json.loads((folder / "summary.json").read_text())
                c = s["config"]
                configs[cost] = c
                equity = rows(folder / "equity.csv")
                rejects = [r for r in rows(folder / "events.csv") if r["event"] == "skip" and r["reason"] == "min_lot"]
                public_events = [{"time": timestamp(r["time"]), "reason": "min_lot"}
                                 for r in sample(rejects, 6)]
                scenarios.append({"id": ident, "period": period, "risk": number(c["risk_fraction"]),
                    "cost": cost, "startingEquity": number(s["starting_cash"]),
                    "finalEquity": number(s["final_equity"]), "netPnl": number(s["net_profit"]),
                    "trades": int(s["n_trades"]), "winRate": s["win_rate"],
                    "drawdown": number(s["max_close_sampled_drawdown"]),
                    "rejected": int(s["skip_reasons"].get("min_lot", 0)),
                    "budget": number(c["starting_cash"] * c["risk_fraction"]),
                    "events": public_events,
                    "equity": [{"t": timestamp(r["sample_time"]), "value": number(r["equity"])} for r in sample(equity, 48)],
                    "costAssumptions": {"spreadMultiplier": c["spread_multiplier"],
                                        "slippage": c["slippage_per_ounce"],
                                        "commission": c["commission_per_lot_per_side"]}})
    period_info = {}
    for key in PERIODS:
        p = experiment["periods"][key]
        period_info[key] = {"first": timestamp(p["first_bar_server"]),
                            "last": timestamp(p["last_bar_server"]), "bars": int(p["rows"])}
    scores = {name: number(latest[name]) for name in ENGINES}
    if not all(-100 <= value <= 100 for value in scores.values()):
        raise ValueError("Score outside allowed range")
    return {"schemaVersion": 1,
        "meta": {"model": "VORTEX-XAU-v0.1", "mode": "historical_research_snapshot",
                 "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "asOf": timestamp(latest["decision_time"]), "timeBasis": TIME_BASIS,
                 "liveFeed": False, "brokerConnection": False, "completenessVerified": False,
                 "sourceUrl": "https://github.com/achaer31/VORTEX",
                 "historyUrl": "https://github.com/achaer31/VORTEX/commits",
                 "reportUrl": "https://github.com/achaer31/VORTEX/blob/main/reports/v0.1/REPORT.md",
                 "diagnosisUrl": "https://github.com/achaer31/VORTEX/blob/main/reports/v0.1/SIZING-DIAGNOSIS.md"},
        "dataset": {"counts": counts, "periods": period_info, "sourceHashes": hashes},
        "candles": candles,
        "signal": {"time": timestamp(latest["decision_time"]), "scores": scores,
                   "consensus": number(latest["consensus"]), "direction": int(latest["signal"]),
                   "atr": number(latest["atr"]),
                   "history": {name: [number(r[name]) for r in valid[-48:]] for name in ENGINES}},
        "scenarios": scenarios,
        "diagnosis": {cost: sizing_diagnosis(signal_rows, configs[cost]) for cost in ("baseline", "stress")}}


def main():
    defaults = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=defaults / "vortex-xau-results-v0.1")
    parser.add_argument("--data", type=Path, default=defaults / "vortex-xau-data")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / "assets" / "snapshot.json")
    args = parser.parse_args()
    snapshot = build(args.results, args.data)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n", encoding="utf-8")
    print(f"Snapshot ready: {len(snapshot['scenarios'])} scenarios; 200 bars per timeframe; no account identifiers.")


if __name__ == "__main__":
    main()
