#!/usr/bin/env python3
"""Run a fixed offline XAUUSD experiment from a VortexExport directory.

This runner never connects to a broker or changes a demo/real account. The 32
scenarios are fixed below; none is selected or optimized using its outcome.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from vortex_xau.audit import audit_export
from vortex_xau.signals import VERSION, WEIGHTS, build_signals_from_export
from vortex_xau.simulator import SimulatorConfig, simulate


# Fixed before inspecting results. Changes create a different experiment version.
EXPERIMENT_VERSION = "xau-50-fixed-grid-v0.1"
RISKS = (0.03, 0.05, 0.075, 0.10)
COSTS = {
    "baseline": {"spread_multiplier": 1.0, "slippage_per_ounce": 0.03},
    "stress": {"spread_multiplier": 2.0, "slippage_per_ounce": 0.10},
}
PERIOD_ORDER = ("full", "development", "validation", "holdout")
BASE_CONFIG = asdict(SimulatorConfig(starting_cash=50.0))
SUMMARY_FIELDS = (
    "starting_cash", "final_equity", "net_profit", "net_return", "n_trades",
    "win_rate", "profit_factor", "expectancy", "max_close_sampled_drawdown",
    "maximum_loss_streak", "vault_balance",
)


def serializable(value: Any) -> Any:
    """Use strict JSON, including explicit text for infinite profit factor."""
    if isinstance(value, dict):
        return {str(key): serializable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serializable(item) for item in value]
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return serializable(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None if math.isnan(value) else ("Infinity" if value > 0 else "-Infinity")
    return value


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(serializable(value), indent=2, ensure_ascii=False,
                               allow_nan=False) + "\n", encoding="utf-8")


def source_hashes() -> dict[str, str]:
    root = Path(__file__).resolve().parent
    names = ["run_research.py", "requirements.txt", "SIGNALS.md",
             "vortex_xau/audit.py", "vortex_xau/signals.py", "vortex_xau/simulator.py"]
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in names if (root / name).is_file()}


def split_periods(frame: pd.DataFrame) -> tuple[dict[str, pd.DataFrame], dict]:
    """Split elapsed calendar days, using date boundaries in the broker clock.

    The partitions are disjoint. Full is an explicitly overlapping descriptive
    run. No day is filled and no bars are moved across a boundary.
    """
    if frame.empty or not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError("A nonempty frame with broker-clock DatetimeIndex is required")
    first_day = frame.index[0].normalize()
    last_exclusive = frame.index[-1].normalize() + pd.Timedelta(days=1)
    days = (last_exclusive - first_day).days
    development_days = math.floor(days * 0.60)
    validation_days = math.floor(days * 0.20)
    if min(development_days, validation_days, days - development_days - validation_days) < 1:
        raise ValueError("At least five calendar days are needed for nonempty day partitions")
    validation_start = first_day + pd.Timedelta(days=development_days)
    holdout_start = validation_start + pd.Timedelta(days=validation_days)
    bounds = {"full": (first_day, last_exclusive),
              "development": (first_day, validation_start),
              "validation": (validation_start, holdout_start),
              "holdout": (holdout_start, last_exclusive)}
    frames, definitions = {}, {}
    for name, (start, end) in bounds.items():
        selected = frame.loc[(frame.index >= start) & (frame.index < end)].copy()
        if selected.empty:
            raise ValueError(f"{name} calendar partition has no observed bars")
        frames[name] = selected
        definitions[name] = {"start_inclusive_server": start.isoformat(),
                             "end_exclusive_server": end.isoformat(),
                             "first_bar_server": selected.index[0].isoformat(),
                             "last_bar_server": selected.index[-1].isoformat(),
                             "rows": len(selected), "calendar_days": (end - start).days,
                             "starting_cash": 50.0,
                             "overlaps_other_partitions": name == "full"}
    return frames, definitions


def save_frame(path: Path, value: Any, kind: str) -> None:
    frame = value.copy() if isinstance(value, pd.DataFrame) else pd.DataFrame(value)
    if isinstance(frame.index, pd.DatetimeIndex):
        frame = frame.reset_index()
    if len(frame.columns) == 0:
        # A zero-trade experiment still emits a machine-readable header.
        fallback = {"trades": ["trade_id", "entry_time", "exit_time", "net_pnl"],
                    "equity": ["bar_open_server", "sample_time", "equity", "balance"],
                    "events": ["time", "event", "reason"]}
        frame = pd.DataFrame(columns=fallback[kind])
    frame.to_csv(path, index=False, date_format="%Y-%m-%dT%H:%M:%S")


def context_age_diagnostics(frame: pd.DataFrame) -> dict:
    """Measure closed-context age without changing ASOF selection or signals."""
    decision = pd.to_datetime(frame["decision_time"])
    ready = frame["ready"].eq(True)
    nonzero = ready & frame["signal"].ne(0)
    masks = {"all_rows": pd.Series(True, index=frame.index), "ready": ready,
             "nonzero_signal": nonzero,
             "session_candidates": nonzero & decision.dt.hour.ge(BASE_CONFIG["session_start_hour"])
             & decision.dt.hour.lt(BASE_CONFIG["session_end_hour"])}
    result = {"definition": "decision_time minus selected closed HTF close; diagnostic only, no age gate",
              "session_candidates_definition": "ready and nonzero signal with decision hour 08:00 <= hour < 18:00 in broker clock; not guaranteed entries",
              "interpretation": "Older contexts may reflect closures or absent history; not automatically invalid data.",
              "timeframes": {}}
    for timeframe, minutes in (("M15", 15), ("H1", 60)):
        ages = (decision - pd.to_datetime(frame[f"htf_{timeframe.lower()}_close"])).dt.total_seconds() / 60
        subsets = {}
        for name, mask in masks.items():
            selected = ages.loc[mask]
            maximum = selected.max()
            subsets[name] = {"rows": int(mask.sum()), "context_available": int(selected.notna().sum()),
                             "context_missing": int(selected.isna().sum()),
                             "age_at_least_threshold": int(selected.ge(minutes).sum()),
                             "negative_age": int(selected.lt(0).sum()),
                             "max_age_minutes": None if pd.isna(maximum) else float(maximum)}
        result["timeframes"][timeframe] = {"threshold_minutes": minutes, "subsets": subsets}
    return result


def _money(value: Any) -> str:
    return "—" if value is None or pd.isna(value) else f"${float(value):.2f}"


def _percent(value: Any) -> str:
    return "—" if value is None or pd.isna(value) else f"{100 * float(value):.2f}%"


def render_report(experiment: dict, audit: dict, summaries: list[dict]) -> str:
    periods = experiment["periods"]
    labels = {"full": "Seluruh periode (deskriptif)", "development": "Development",
              "validation": "Validation", "holdout": "Holdout"}
    lines = ["# Riset XAUUSD — simulasi awal $50", "",
             "Hasil berikut berasal dari simulasi historis offline atas hipotesis baru "
             "VORTEX-XAU-v0.1. Ini bukan transaksi atau pertumbuhan saldo akun demo MT5. "
             "Program tidak menghubungi broker dan tidak mengirim order.", "",
             f"Eksperimen: `{experiment['experiment_version']}`. "
             "Empat tingkat risiko dan dua asumsi biaya ditetapkan sebelum perhitungan; "
             "seluruh hasil ditampilkan tanpa memilih pemenang atau mengoptimasi parameter.", "",
             f"Struktur CSV: {'lolos' if audit['structural_ok'] else 'gagal'}. "
             f"Temuan untuk ditinjau: {len(audit['review_findings'])}. "
             "Lihat `audit.json` untuk agregasi timeframe, SHA-256, gap, dan manifest.", ""]
    if audit["review_findings"]:
        lines.extend(f"- {item}" for item in audit["review_findings"])
        lines.append("")
    lines.extend(["## Umur konteks timeframe", "",
                  "Sinyal memakai konteks HTF terakhir yang sudah selesai tanpa batas umur tambahan. "
                  "Tabel ini hanya diagnostik dan tidak mengubah sinyal. Konteks lama dapat terjadi "
                  "karena sesi tutup atau history tidak tersedia; tidak otomatis berarti data rusak. "
                  "Kandidat jam riset berarti ready + sinyal nonnol + waktu keputusan "
                  "08:00–18:00 menurut clock server, belum tentu menjadi entry.", "",
                  "| HTF | Subset | Bar | Umur ≥ satu HTF | Umur maksimum (menit) |",
                  "| --- | --- | ---: | ---: | ---: |"])
    for timeframe, info in experiment["context_age_diagnostics"]["timeframes"].items():
        for subset, label in (("ready", "Fitur siap"), ("nonzero_signal", "Sinyal nonnol"),
                              ("session_candidates", "Kandidat jam riset")):
            item = info["subsets"][subset]
            maximum = item["max_age_minutes"]
            lines.append(f"| {timeframe} | {label} | {item['rows']} | "
                         f"{item['age_at_least_threshold']} | {'—' if maximum is None else f'{maximum:.1f}'} |")
    lines.append("")
    lines.extend(["## Pembagian data", "",
                  "Pembagian memakai hari kalender dalam clock server broker: "
                  "60% development, 20% validation, dan sisa hari holdout. "
                  "Ketiga bagian terpisah; simulasi seluruh periode bertumpang tindih dan hanya deskriptif. "
                  "Saldo direset $50 untuk setiap skenario. Indikator dihitung secara kausal sekali atas "
                  "seluruh data; setiap bagian dapat membawa riwayat indikator sebelumnya, tetapi tidak "
                  "membawa posisi atau saldo. Bar pertama setiap bagian tidak dipakai untuk entry.", "",
                  "| Bagian | Awal inklusif server | Akhir eksklusif server | Bar M5 |",
                  "| --- | --- | --- | ---: |"])
    for name in PERIOD_ORDER:
        info = periods[name]
        lines.append(f"| {labels[name]} | {info['start_inclusive_server']} | "
                     f"{info['end_exclusive_server']} | {info['rows']} |")
    lines.extend(["", "## Hasil seluruh skenario", "",
                  "Risiko adalah batas anggaran stop yang direncanakan per entry, bukan jaminan "
                  "rugi maksimum. Lot selalu dibulatkan turun; jika 0,01 lot melebihi anggaran, "
                  "sinyal dilewati. Drawdown di bawah disampel pada penutupan bar dan dapat "
                  "lebih kecil daripada penurunan intrabar yang sebenarnya.", "",
                  "| Bagian | Risiko | Biaya | Saldo akhir | P/L bersih | Trade | Win rate | Drawdown close | Lewat: min lot |",
                  "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |"])
    for item in summaries:
        lines.append(f"| {labels[item['period']]} | {_percent(item['risk_fraction'])} | "
                     f"{item['cost_profile']} | {_money(item.get('final_equity'))} | "
                     f"{_money(item.get('net_profit'))} | {item.get('n_trades', 0)} | "
                     f"{_percent(item.get('win_rate'))} | "
                     f"{_percent(item.get('max_close_sampled_drawdown'))} | "
                     f"{item.get('skip_min_lot', 0)} |")
    zero = sum(item.get("n_trades", 0) == 0 for item in summaries)
    lines.extend(["", f"Sebanyak {zero} dari {len(summaries)} skenario tidak menghasilkan trade. "
                  "Saldo yang tetap $50 pada skenario tersebut berarti tidak ada transaksi simulasi, "
                  "bukan bukti perlindungan modal atau keunggulan strategi.", "",
                  "## Asumsi dan batas hasil", "",
                  "- Baseline: spread bar sebelumnya ×1 dan slippage $0,03 per ons per sisi "
                  "yang memakai market/stop fill. Stress: spread ×2 dan slippage $0,10. "
                  "Ini sensitivitas biaya, bukan estimasi biaya broker yang sudah divalidasi.",
                  "- OHLC adalah harga Bid. Ask dibentuk dari proxy spread bar sebelumnya; "
                  "pergerakan Bid/Ask intrabar, antrean, requote dan likuiditas tidak direkonstruksi. "
                  "Jika SL dan TP tersentuh dalam satu bar, SL didahulukan.",
                  "- Komisi diasumsikan nol dan swap tidak dimodelkan. Posisi ditutup pada aturan "
                  "sesi/pergantian tanggal yang tersedia, tetapi gap data tidak menjamin nihil "
                  "rollover. Hasil bukan P/L setelah seluruh biaya broker yang terverifikasi.",
                  "- Leverage 1:2000 dan pembatas margin memakai pendekatan sederhana; perubahan "
                  "margin, persyaratan khusus berita dan stop-out broker belum direplikasi.",
                  "- Pembatas rugi harian diperiksa pada open/close; gap dapat melampaui batasnya. "
                  "Tidak ada martingale, kenaikan risiko otomatis, atau transfer dana ke vault.",
                  "- Jam 08:00–18:00 adalah pembatas riset menurut clock server, bukan identifikasi "
                  "sesi London/New York. Offset UTC/DST historis belum diketahui.",
                  "- Tick volume adalah aktivitas quote, bukan volume jual/beli transaksi. "
                  "Kelengkapan history belum tersertifikasi dan gap tidak otomatis berarti data rusak.",
                  "- Holdout dihitung satu kali dengan aturan tetap. Hasil yang sudah dibaca tidak "
                  "boleh dipakai berulang untuk memilih parameter lalu disebut holdout baru. "
                  "Tidak ada Monte Carlo, pemilihan skenario terbaik, atau klaim keunggulan.", "",
                  "Seluruh trade, equity dan event tersedia per skenario. `experiment.json` "
                  "menyimpan konfigurasi, rentang, hash data/kode, versi runtime, dan status eksekusi. "
                  "`summaries.csv` memuat hasil mentah; `signals.csv` memuat sinyal beserta konteks waktunya.", ""])
    return "\n".join(lines)


def run_research(data_dir: str | Path, output_dir: str | Path) -> dict:
    data_dir, output_dir = Path(data_dir).resolve(), Path(output_dir).resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("Output directory must be absent or empty; keep previous experiments immutable")
    if output_dir == data_dir:
        raise ValueError("Output directory must differ from raw data directory")
    output_dir.mkdir(parents=True, exist_ok=True)
    audit = audit_export(data_dir)
    write_json(output_dir / "audit.json", audit)
    if not audit["structural_ok"]:
        raise ValueError("CSV structural audit failed; inspect audit.json. No signals or simulations run.")
    snapshot = {
        "experiment_version": EXPERIMENT_VERSION, "model_version": VERSION,
        "status": "frozen_before_signal_or_pnl_calculation",
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "new_hypothesis_not_replication_of_missing_original": True,
        "parameter_selection": "fixed_grid_no_optimization_no_winner_selection",
        "risk_fractions": list(RISKS), "cost_profiles": COSTS,
        "base_simulator_config": BASE_CONFIG, "signal_weights": WEIGHTS,
        "signal_definition": "SIGNALS.md and hash-pinned vortex_xau/signals.py",
        "planned_scenario_count": 32, "starting_cash_each_scenario": 50.0,
        "split_rule": "floor(calendar_days*0.60) development; floor(calendar_days*0.20) validation; remainder holdout",
        "indicator_history": "causal full-data features; independent account and positions per partition",
        "first_bar_of_each_partition": "no entry without previous bar inside that partition",
        "full_period_interpretation": "descriptive overlapping run, not independent validation",
        "broker_time_basis": audit["time_basis"], "historical_utc_offset_verified": False,
        "runtime": {"python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__},
        "source_sha256": source_hashes(), "raw_csv_sha256": audit["csv_sha256"],
        "audit_review_findings": audit["review_findings"],
        "network_or_broker_operations": False,
    }
    write_json(output_dir / "experiment.json", snapshot)
    print("Audit structure passed; experiment parameters frozen. Building causal signals.", flush=True)
    try:
        signals = build_signals_from_export(data_dir)
        signals.to_csv(output_dir / "signals.csv", index=True, date_format="%Y-%m-%dT%H:%M:%S")
        frames, periods = split_periods(signals)
        snapshot.update(status="running", periods=periods,
                        signal_rows=len(signals), ready_rows=int(signals["ready"].sum()),
                        context_age_diagnostics=context_age_diagnostics(signals),
                        signal_counts={str(int(key)): int(value) for key, value in signals["signal"].value_counts().items()})
        write_json(output_dir / "experiment.json", snapshot)
        summaries = []
        for period in PERIOD_ORDER:
            for risk in RISKS:
                for cost_name, cost in COSTS.items():
                    scenario = f"{period}_risk{risk * 100:g}_{cost_name}".replace(".", "p")
                    print(f"Scenario {len(summaries) + 1}/32: {scenario}", flush=True)
                    config = {**BASE_CONFIG, "risk_fraction": risk, **cost}
                    result = simulate(frames[period], config)
                    destination = output_dir / "scenarios" / scenario
                    destination.mkdir(parents=True)
                    for kind in ("trades", "equity", "events"):
                        save_frame(destination / f"{kind}.csv", result[kind], kind)
                    summary = result["summary"]
                    write_json(destination / "summary.json", summary)
                    row = {"scenario": scenario, "period": period, "risk_fraction": risk,
                           "cost_profile": cost_name, **cost, "rows": len(frames[period]),
                           **{key: summary.get(key) for key in SUMMARY_FIELDS},
                           **{"cost_" + key: value for key, value in summary.get("costs", {}).items()},
                           **{"skip_" + key: value for key, value in summary.get("skip_reasons", {}).items()}}
                    summaries.append(row)
                    # Preserve completed rows even if a later scenario fails.
                    pd.DataFrame(summaries).to_csv(output_dir / "summaries.csv", index=False)
        snapshot.update(status="completed", completed_at_utc=datetime.now(timezone.utc).isoformat(),
                        completed_scenario_count=len(summaries))
        write_json(output_dir / "experiment.json", snapshot)
        (output_dir / "REPORT.md").write_text(render_report(snapshot, audit, summaries), encoding="utf-8")
        print(f"Completed {len(summaries)} fixed scenarios. Report: {output_dir / 'REPORT.md'}", flush=True)
        return {"experiment": snapshot, "audit": audit, "summaries": summaries}
    except Exception as error:
        snapshot.update(status="failed", error_type=type(error).__name__, error=str(error),
                        failed_at_utc=datetime.now(timezone.utc).isoformat())
        write_json(output_dir / "experiment.json", snapshot)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True, help="One raw VortexExport run directory")
    parser.add_argument("--out", type=Path, required=True, help="New or empty results directory")
    args = parser.parse_args()
    run_research(args.data, args.out)
