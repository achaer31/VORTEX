"""Deterministic SYNTHETIC fixtures; the unchanged Python v0.2 code is the oracle.

No broker, terminal, account, network, order or P/L access. Generated large files
belong outside the repository. The external rows below are declared test inputs,
not news coverage, market feeds, or evidence that the strategy has an edge.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "research_v02"))
from vortex_v02.engines import build_signals, mode_from_scores, WEIGHTS
from vortex_v02.data import aggregate_h4, session_context

KIND = "SYNTHETIC_OFFLINE_PARITY_V1"
FRAME_COLUMNS = ["epoch_utc", "open", "high", "low", "close", "tick_volume", "spread_points", "real_volume"]
EXTERNAL_COLUMNS = ["decision_epoch", "news_valid", "news_blocked", "macro_valid", "session_valid", "session_ideal",
                    "dxy_roc", "us10y_change", "asia_high", "asia_low", "london_high", "london_low", "newyork_high", "newyork_low"]
OUTPUT_COLUMNS = ["bar_open_epoch", "decision_epoch", "m15_closed_epoch", "h1_closed_epoch", "h4_closed_epoch",
                  "orion", "vortex", "nova", "luna", "kira", "atlas", "consensus", "atr", "stop_long", "stop_short",
                  "swing_low", "swing_high", "orion_reason", "vortex_reason", "nova_reason", "luna_reason",
                  "kira_reason", "atlas_reason", "mode", "signal", "h1_alignment", "h4_alignment",
                  "m15_fresh", "h1_fresh", "h4_fresh", "execution_valid", "ready"]
MODE_COLUMNS = ["case_id", "orion", "vortex", "nova", "luna", "kira", "atlas", "consensus",
                "h1_alignment", "h4_alignment", "session_ideal", "eligible"]
FLAG_COLUMNS = {"news_valid", "news_blocked", "macro_valid", "session_valid", "session_ideal", "m15_fresh",
                "h1_fresh", "h4_fresh", "execution_valid", "ready", "eligible"}
INTEGER_COLUMNS = {"epoch_utc", "decision_epoch", "bar_open_epoch", "m15_closed_epoch", "h1_closed_epoch", "h4_closed_epoch",
                   "tick_volume", "spread_points", "real_volume", "signal", "h1_alignment", "h4_alignment"} | FLAG_COLUMNS
REFERENCE_FILES = ["research_v02/vortex_v02/engines.py", "research_v02/vortex_v02/data.py",
                   "research_v02/vortex_v02/__init__.py", "research_v02/SPEC.md"]


def cell(value, column):
    if value is None or pd.isna(value):
        return ""
    if column in INTEGER_COLUMNS:
        if not math.isfinite(float(value)) or float(value) != int(value):
            raise ValueError("nonintegral fixture field: " + column)
        return str(int(value))
    if isinstance(value, (float, np.floating)):
        return format(float(value), ".17g") if math.isfinite(float(value)) else ""
    return str(value)


def write_csv(path, columns, rows):
    with Path(path).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(columns)
        for row in rows:
            writer.writerow([cell(row.get(key), key) for key in columns])


def epoch(value):
    return None if pd.isna(value) else int(pd.Timestamp(value).timestamp())


def fine_bars(side=1, variant="trend"):
    """960 complete H1 / 240 complete H4, with no random state or real prices."""
    n = 960 * 12
    t = np.arange(n, dtype=float)
    center = 3500. + side * (.035*t + 1.15*np.sin(t/4.1) + .27*np.sin(t/1.7))
    opening = np.r_[center[0] - side*.04, center[:-1]]
    wick = .18 + .07*(1+np.sin(t/2.3))
    high = np.maximum(opening, center) + wick
    low = np.minimum(opening, center) - wick
    # Declared liquidity probes, independent of oracle results or any P/L.
    probe = (np.arange(n) % 29 == 0)
    if side > 0:
        low[probe] -= 2.8
    else:
        high[probe] += 2.8
    if variant == "quiet":
        center = 3500. + .012*np.sin(t/5)
        opening = np.r_[center[0], center[:-1]]
        high, low = np.maximum(opening, center)+.15, np.minimum(opening, center)-.15
    elif variant == "volatility":
        # A known quiet -> ordinary -> wild -> recovery sequence in the tail.
        amplitude = np.ones(n)
        amplitude[-1500:-1200] = .10
        amplitude[-1200:-1050] = 35.
        amplitude[-1050:-900] = .20
        amplitude[-900:-600] = 1.
        amplitude[-600:-480] = 50.
        amplitude[-480:-240] = .20
        high, low = np.maximum(opening, center)+amplitude, np.minimum(opening, center)-amplitude
    elif variant == "zero_atr":
        center = np.full(n, 3500.)
        opening, high, low = center.copy(), center.copy(), center.copy()
    index = pd.date_range("2025-01-06T00:00:00Z", periods=n, freq="5min")
    return pd.DataFrame({"open": np.round(opening, 3), "high": np.round(high, 3), "low": np.round(low, 3),
                         "close": np.round(center, 3), "tick_volume": (100 + (np.arange(n)*37)%91),
                         "spread_points": np.full(n, 20), "real_volume": np.zeros(n, dtype=int)}, index=index)


def aggregate(frame, rule, expected_count):
    groups = frame.resample(rule)
    result = groups.agg({"open":"first", "high":"max", "low":"min", "close":"last",
                         "tick_volume":"sum", "spread_points":"last", "real_volume":"sum"})
    return result.loc[groups.size().eq(expected_count)].copy()


def scenario(name, side=1, variant="trend"):
    fine = fine_bars(side, variant)
    frames = {"M5": fine.iloc[-960:].copy(), "M15": aggregate(fine, "15min", 3).iloc[-640:].copy(),
              "H1": aggregate(fine, "h", 12)}
    if name == "gaps":
        # No session filling: native H4 must skip the incomplete four-H1 bucket.
        middle = frames["M5"].index[450]
        frames["M5"] = frames["M5"].drop(frames["M5"].index[[210,211,680]])
        frames["M15"] = frames["M15"].drop(middle.floor("15min"))
        frames["H1"] = frames["H1"].drop(middle.floor("h"))
    elif name == "absent_context":
        early = fine.iloc[:48].copy()
        early.index = pd.date_range(fine.index[0]-pd.Timedelta(hours=4), periods=48, freq="5min")
        frames["M5"] = pd.concat([early, frames["M5"]])
    ext = session_context(frames["M5"])
    ext["news_valid"] = True
    ext["news_blocked"] = False
    ext["macro_valid"] = True
    ext["dxy_roc"] = -.2*side
    ext["us10y_change"] = -.05*side
    ext["next_news"] = None
    if name == "external_edges":
        ext.iloc[220:245,ext.columns.get_loc("news_valid")] = False
        ext.iloc[260:280,ext.columns.get_loc("news_blocked")] = True
        ext.iloc[300:320,ext.columns.get_loc("macro_valid")] = False
        ext.iloc[340:355,ext.columns.get_loc("dxy_roc")] = np.nan
        ext.iloc[370:385,ext.columns.get_loc("us10y_change")] = np.nan
        ext.iloc[400:415,ext.columns.get_loc("session")] = "INVALID_SYNTHETIC"
        frames["M5"].iloc[440:460,frames["M5"].columns.get_loc("spread_points")] = 900
        frames["M5"].iloc[480:495,frames["M5"].columns.get_loc("spread_points")] = 0
        ext.iloc[520:540,ext.columns.get_loc("dxy_roc")] = 0.
        ext.iloc[520:540,ext.columns.get_loc("us10y_change")] = 0.
    elif name == "missing_external":
        ext = ext.iloc[:0]
    frames["H4"] = aggregate_h4(frames["H1"])
    return frames, ext


def fixture_cases():
    for name, side, variant in [("trend_up",1,"trend"),("trend_down",-1,"trend"),("quiet",1,"quiet"),
                               ("volatility",1,"volatility"),("zero_atr",1,"zero_atr"),
                               ("gaps",1,"trend"),("absent_context",1,"trend"),
                               ("external_edges",1,"trend"),("missing_external",1,"trend")]:
        yield name, *scenario(name, side, variant)


def mode_cases():
    cases = []
    def add(name, side=1, aligned=0, ideal=False, eligible=True, **overrides):
        row = {k:100.*side for k in WEIGHTS if k!="kira"}
        row.update(kira=75.,h1_alignment=aligned*side,h4_alignment=aligned*side,session_ideal=ideal,eligible=eligible)
        row.update(overrides)
        row["consensus"] = sum(row[k]*WEIGHTS[k] for k in WEIGHTS if k!="kira")/.9*(.9+.1*row["kira"]/100)
        row["case_id"] = name
        cases.append(row)
    for side, label in ((1,"long"),(-1,"short")):
        add(label+"_normal",side)
        add(label+"_aggressive",side,aligned=1)
        add(label+"_extreme",side,aligned=1,ideal=True)
    for quality in (20.,44.999,45.,50.,60.,84.,84.999,85.,90.):
        add("kira_"+str(quality).replace(".","_"),kira=quality,aligned=1,ideal=True)
    add("ineligible",eligible=False)
    add("orion_below_normal",orion=69.999)
    add("nova_below_normal",nova=74.999)
    add("kira_missing",kira=np.nan)
    add("atlas_missing",atlas=np.nan)
    add("mixed_alignment",aligned=1,h4_alignment=-1,ideal=True)
    add("opposed_luna",luna=-100.)
    return cases


def expected_rows(result):
    for index, row in result.iterrows():
        value = row.to_dict()
        value.update(bar_open_epoch=epoch(index), decision_epoch=epoch(row.decision_time),
                     m15_closed_epoch=epoch(row.m15_closed_at), h1_closed_epoch=epoch(row.h1_closed_at),
                     h4_closed_epoch=epoch(row.h4_closed_at))
        yield value


def generate(directory):
    directory = Path(directory).resolve()
    if directory == REPO or REPO in directory.parents:
        raise ValueError("large synthetic fixture output must be outside repository")
    directory.mkdir(parents=True, exist_ok=False)
    (directory/"fixture_kind.txt").write_text(KIND+"\n", encoding="ascii")
    coverage = {}
    for name, frames, external in fixture_cases():
        for tf in ("M5","M15","H1"):
            write_csv(directory/f"{name}_{tf}.csv",FRAME_COLUMNS,
                      (dict(row.to_dict(),epoch_utc=epoch(index)) for index,row in frames[tf].iterrows()))
        write_csv(directory/f"{name}_external.csv",EXTERNAL_COLUMNS,
                  (dict(row.to_dict(),decision_epoch=epoch(index),session_valid=row.session in
                        ("ASIA","LONDON","NEWYORK","LONDON_NEWYORK","OTHER")) for index,row in external.iterrows()))
        result = build_signals(frames,external)
        write_csv(directory/f"expected_{name}_signals.csv",OUTPUT_COLUMNS,expected_rows(result))
        coverage[name] = {"counts":{tf:len(frame) for tf,frame in frames.items()},
                          "modes":result["mode"].value_counts().to_dict(),
                          "directions":{str(int(k)):int(v) for k,v in result.signal.value_counts().items()},
                          "ready_rows":int(result.ready.sum()),
                          "kira_values":sorted(result.kira.dropna().unique().tolist()),
                          "reasons":{k:sorted(result[k].unique().tolist()) for k in result if k.endswith("_reason")},
                          "stale_context_rows":{tf:int((~result[f"{tf}_fresh"]).sum()) for tf in ("m15","h1","h4")}}
    write_csv(directory/"cases.csv",["case_id"],({"case_id":name} for name in coverage))
    modes = mode_cases()
    write_csv(directory/"mode_cases.csv",MODE_COLUMNS,modes)
    expected_modes=[]
    for row in modes:
        mode, signal = mode_from_scores(row,row["h1_alignment"],row["h4_alignment"],row["session_ideal"],row["eligible"])
        expected_modes.append({"case_id":row["case_id"],"mode":mode,"signal":signal})
    write_csv(directory/"expected_mode_results.csv",["case_id","mode","signal"],expected_modes)
    manifest = {"fixture_kind":KIND,"model":"VORTEX-XAU-EXTREME-v0.2","reference":"unchanged frozen Python functions",
                "reference_sha256":{p:hashlib.sha256((REPO/p).read_bytes()).hexdigest() for p in REFERENCE_FILES},
                "runtime":{"python":sys.version.split()[0],"pandas":pd.__version__,"numpy":np.__version__},
                "cases":coverage,"mode_case_count":len(modes),
                "files":{p.name:{"sha256":hashlib.sha256(p.read_bytes()).hexdigest(),"bytes":p.stat().st_size}
                         for p in sorted(directory.iterdir()) if p.is_file()},
                "limitations":["synthetic deterministic data, no observed prices or feeds",
                               "no backtest, fill, P/L, baseline promotion or order",
                               "mode fixtures test frozen voting independently of indicator pipeline",
                               "native parity requires a separately compiled native run and comparison"]}
    (directory/"python_reference_manifest.json").write_text(json.dumps(manifest,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output",type=Path)
    args=parser.parse_args()
    manifest=generate(args.output)
    print(json.dumps({"fixture_kind":KIND,"cases":len(manifest["cases"]),"mode_cases":manifest["mode_case_count"],
                      "native_execution":False,"output":str(args.output)},indent=2))
