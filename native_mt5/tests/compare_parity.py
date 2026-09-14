"""Strict synthetic parity comparison. PASS means numerical parity, never GO."""
from __future__ import annotations

import argparse
import csv
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
import re

from parity_fixtures import KIND, OUTPUT_COLUMNS, INTEGER_COLUMNS, FLAG_COLUMNS, REPO, REFERENCE_FILES

FLOAT_COLUMNS = {"orion","vortex","nova","luna","kira","atlas","consensus","atr",
                 "stop_long","stop_short","swing_low","swing_high"}
CASE_RE = re.compile(r"[A-Za-z0-9_-]{1,48}\Z")


class ComparisonError(ValueError):
    pass


def table(path, columns):
    path=Path(path)
    if path.stat().st_size>64*1024*1024:
        raise ComparisonError("oversized CSV")
    with path.open(encoding="utf-8-sig",newline="") as stream:
        reader=csv.reader(stream)
        header=next(reader,None)
        if header!=columns:
            raise ComparisonError("CSV schema mismatch: "+path.name)
        rows=[]
        for number, raw in enumerate(reader,2):
            if len(raw)!=len(columns):
                raise ComparisonError(f"CSV row width mismatch: {path.name}:{number}")
            rows.append(dict(zip(columns,raw)))
    return rows


def parsed(value, field):
    if value=="":
        return None
    if field in FLOAT_COLUMNS or field in INTEGER_COLUMNS:
        try:
            n=Decimal(value)
        except InvalidOperation as error:
            raise ComparisonError("invalid numeric field: "+field) from error
        if not n.is_finite():
            raise ComparisonError("nonfinite literal; numeric missing must be empty: "+field)
        if field in INTEGER_COLUMNS:
            if n!=n.to_integral_value() or (field in FLAG_COLUMNS and n not in (0,1)):
                raise ComparisonError("invalid integer/boolean field: "+field)
            return int(n)
        result=float(n)
        if not math.isfinite(result):
            raise ComparisonError("numeric overflow: "+field)
        return result
    return value


def compare_tables(expected, actual, columns, key, absolute=1e-7, relative=1e-10):
    if not (math.isfinite(absolute) and math.isfinite(relative) and absolute>=0 and relative>=0):
        raise ComparisonError("invalid tolerance")
    exp,act=table(expected,columns),table(actual,columns)
    def keyed(rows):
        result={}
        for row in rows:
            ident=parsed(row[key],key)
            if ident is None or ident in result:
                raise ComparisonError("missing or duplicate comparison key")
            result[ident]=row
        return result
    e,a=keyed(exp),keyed(act)
    differences=[]
    total=0
    def mismatch(ident,field,left,right):
        nonlocal total
        total+=1
        if len(differences)<30:
            differences.append({"key":ident,"field":field,"expected":left,"actual":right})
    if list(e)!=list(a):
        mismatch("rows","order_or_keys",list(e)[:30],list(a)[:30])
    for ident in e:
        if ident not in a:mismatch(ident,"missing_row",True,False)
    for ident in a:
        if ident not in e:mismatch(ident,"unexpected_row",False,True)
    for ident in e:
        if ident not in a:continue
        for field in columns:
            left,right=parsed(e[ident][field],field),parsed(a[ident][field],field)
            if left is None or right is None:
                equal=left is None and right is None
            elif field in FLOAT_COLUMNS:
                equal=math.isclose(left,right,abs_tol=absolute,rel_tol=relative)
            else:
                equal=left==right
            if not equal:mismatch(ident,field,left,right)
    return {"pass":total==0,"expected_rows":len(exp),"actual_rows":len(act),
            "mismatch_count":total,"first_mismatches":differences}


def compare_directory(fixtures, actual, absolute=1e-7, relative=1e-10):
    fixtures,actual=Path(fixtures).resolve(),Path(actual).resolve()
    if (fixtures/"fixture_kind.txt").read_text(encoding="ascii").strip()!=KIND:
        raise ComparisonError("synthetic fixture marker required")
    manifest=json.loads((fixtures/"python_reference_manifest.json").read_text())
    if manifest.get("fixture_kind")!=KIND or manifest.get("model")!="VORTEX-XAU-EXTREME-v0.2" or not manifest.get("files"):
        raise ComparisonError("reference fixture manifest required")
    reference_hashes={p:hashlib.sha256((REPO/p).read_bytes()).hexdigest() for p in REFERENCE_FILES}
    if manifest.get("reference_sha256")!=reference_hashes:
        raise ComparisonError("frozen Python reference digest mismatch")
    for name,info in manifest["files"].items():
        if Path(name).name!=name or hashlib.sha256((fixtures/name).read_bytes()).hexdigest()!=info["sha256"]:
            raise ComparisonError("reference fixture digest mismatch")
    cases=table(fixtures/"cases.csv",["case_id"])
    names=[r["case_id"] for r in cases]
    if not names or len(names)!=len(set(names)) or not all(CASE_RE.fullmatch(name) for name in names):
        raise ComparisonError("invalid fixture case identifiers")
    required_files={"fixture_kind.txt","cases.csv","mode_cases.csv","expected_mode_results.csv"}
    for name in names:
        required_files.update({f"{name}_M5.csv",f"{name}_M15.csv",f"{name}_H1.csv",f"{name}_external.csv",
                               f"expected_{name}_signals.csv"})
    if set(manifest["files"])!=required_files or set(manifest.get("cases",{}))!=set(names):
        raise ComparisonError("reference manifest does not cover every consumed fixture and expected file")
    declarations=table(actual/"manifest.csv",["key","value"])
    native={row["key"]:row["value"] for row in declarations}
    required={"schema","fixture_kind","harness_version","core_version","status","cases_requested","cases_completed",
              "signal_rows","mode_cases","mode_results","error","parity_evaluated","strategy_approval"}
    if len(native)!=len(declarations) or set(native)!=required:
        raise ComparisonError("native manifest fields missing, duplicate or unexpected")
    fixed={"schema":"vortex.native.parity-result.v1","fixture_kind":KIND,
           "harness_version":"VORTEX-NATIVE-PARITY-0.1","core_version":"v0.2-parity-1",
           "status":"COMPUTED_FOR_COMPARISON","error":"","parity_evaluated":"false","strategy_approval":"false"}
    if any(native[k]!=v for k,v in fixed.items()):
        raise ComparisonError("native computation failed or declared schema/version/status mismatch")
    result={}
    for name in names:
        result[name]=compare_tables(fixtures/f"expected_{name}_signals.csv",actual/f"{name}_signals.csv",
                                    OUTPUT_COLUMNS,"bar_open_epoch",absolute,relative)
    result["pure_modes"]=compare_tables(fixtures/"expected_mode_results.csv",actual/"mode_results.csv",
                                        ["case_id","mode","signal"],"case_id",absolute,relative)
    counts={"cases_requested":len(names),"cases_completed":len(names),
            "signal_rows":sum(value["actual_rows"] for key,value in result.items() if key!="pure_modes"),
            "mode_cases":result["pure_modes"]["expected_rows"],"mode_results":result["pure_modes"]["actual_rows"]}
    if any(not re.fullmatch(r"[0-9]+",native[k]) or int(native[k])!=value for k,value in counts.items()):
        raise ComparisonError("native manifest completion counts mismatch")
    return {"status":"PARITY_PASS" if all(v["pass"] for v in result.values()) else "PARITY_FAIL",
            "scope":"synthetic numerical parity only; not strategy GO or live execution evidence",
            "absolute_tolerance":absolute,"relative_tolerance":relative,"cases":result,
            "reference_sha256":manifest["reference_sha256"],"native_manifest":native}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures",required=True,type=Path)
    parser.add_argument("--actual",required=True,type=Path)
    parser.add_argument("--report",type=Path)
    args=parser.parse_args()
    try:
        report=compare_directory(args.fixtures,args.actual)
    except (ComparisonError,OSError,ValueError,KeyError) as error:
        report={"status":"PARITY_INPUT_INVALID","reason":str(error)}
    text=json.dumps(report,indent=2,allow_nan=False)+"\n"
    if args.report:
        args.report.write_text(text,encoding="utf-8")
    print(text,end="")
    raise SystemExit(0 if report["status"]=="PARITY_PASS" else 1)
