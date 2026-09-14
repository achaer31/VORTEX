"""Strict offline risk comparison. A computed native manifest is not a pass."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import re
from risk_fixtures import KIND,CORE_VERSION,HARNESS_VERSION,TABLES,REPO,REFERENCES

class ComparisonError(ValueError):
    pass

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def read_table(path,columns):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size>32*1024*1024:
        raise ComparisonError('missing_or_unsafe_file:'+path.name)
    with path.open(encoding='utf-8-sig',newline='') as stream:
        reader=csv.reader(stream)
        if next(reader,None)!=columns:raise ComparisonError('header_mismatch:'+path.name)
        result=[]
        for row in reader:
            if len(row)!=len(columns):raise ComparisonError('row_width:'+path.name)
            result.append(dict(zip(columns,row)))
            if len(result)>512:raise ComparisonError('row_limit:'+path.name)
        return result

def numeric(value,kind,where):
    if kind=='string':return value
    if value=='':return None
    if kind=='bool':
        if value not in ('0','1'):raise ComparisonError('invalid_boolean:'+where)
        return int(value)
    if not re.fullmatch(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?',value):
        raise ComparisonError('invalid_numeric:'+where)
    parsed=float(value)
    if not math.isfinite(parsed):raise ComparisonError('nonfinite_numeric:'+where)
    if kind=='int':
        if not parsed.is_integer() or abs(parsed)>2147483647:raise ComparisonError('invalid_integer:'+where)
        return int(parsed)
    return parsed

def compare(reference,native):
    reference,native=Path(reference).resolve(),Path(native).resolve()
    manifest_path=reference/'risk_reference_manifest.json'
    if manifest_path.is_symlink() or manifest_path.stat().st_size>1_000_000:raise ComparisonError('reference_manifest_unsafe')
    manifest=json.loads(manifest_path.read_text())
    if manifest.get('fixture_kind')!=KIND or manifest.get('core_version')!=CORE_VERSION or manifest.get('harness_version')!=HARNESS_VERSION:
        raise ComparisonError('reference_version_mismatch')
    if manifest.get('strategy_approval') is not False or manifest.get('actual_native_run') is not False:
        raise ComparisonError('reference_claim_mismatch')
    required={'fixture_kind.txt'}|{f'risk_{name}_cases.csv' for name in TABLES}|{f'expected_risk_{name}_results.csv' for name in TABLES}
    if set(manifest.get('files',{}))!=required:raise ComparisonError('reference_file_set_mismatch')
    for name in required:
        path=reference/name
        if path.is_symlink() or not path.is_file() or digest(path)!=manifest['files'][name]:raise ComparisonError('reference_hash_mismatch:'+name)
    if (reference/'fixture_kind.txt').read_text()!=KIND+'\n':raise ComparisonError('fixture_marker_mismatch')
    if set(manifest.get('reference_sha256',{}))!=set(REFERENCES):raise ComparisonError('oracle_source_set_mismatch')
    for name in REFERENCES:
        if digest(REPO/name)!=manifest['reference_sha256'][name]:raise ComparisonError('oracle_source_changed:'+name)
    if set(manifest.get('families',{}))!=set(TABLES):raise ComparisonError('family_set_mismatch')
    raw_native=read_table(native/'manifest.csv',['key','value'])
    metadata={row['key']:row['value'] for row in raw_native}
    if len(metadata)!=len(raw_native):raise ComparisonError('duplicate_native_manifest_key')
    fixed=dict(schema='vortex.native.risk-result.v1',fixture_kind=KIND,core_version=CORE_VERSION,
      harness_version=HARNESS_VERSION,status='COMPUTED_FOR_COMPARISON',error='',parity_evaluated='false',
      strategy_approval='false',execution_authorized='false')
    expected_keys=set(fixed)|{f'{family}_{field}' for family in TABLES for field in ('cases','results')}
    if set(metadata)!=expected_keys:raise ComparisonError('native_manifest_key_set_mismatch')
    for key,value in fixed.items():
        if metadata.get(key)!=value:raise ComparisonError('native_manifest_mismatch:'+key)
    differences=[];counts={};max_error=0.;finite_pairs=0
    for family,(inputs,fields) in TABLES.items():
        inputrows=read_table(reference/f'risk_{family}_cases.csv',['case_id']+[f[0] for f in inputs])
        expected=read_table(reference/f'expected_risk_{family}_results.csv',['case_id']+[f[0] for f in fields])
        actual=read_table(native/f'risk_{family}_results.csv',['case_id']+[f[0] for f in fields])
        ids=[row['case_id'] for row in inputrows]
        if not ids or len(set(ids))!=len(ids) or any(not re.fullmatch('[A-Za-z0-9_-]{1,48}',x) for x in ids):
            raise ComparisonError('invalid_case_ids:'+family)
        if [row['case_id'] for row in expected]!=ids or [row['case_id'] for row in actual]!=ids:
            raise ComparisonError('case_identity_or_order_mismatch:'+family)
        family_meta=manifest['families'][family]
        if family_meta.get('cases')!=len(ids) or set(family_meta.get('oracle_scope',{}))!=set(ids):
            raise ComparisonError('reference_case_metadata_mismatch:'+family)
        for field in ('cases','results'):
            if metadata[family+'_'+field]!=str(len(ids)):raise ComparisonError('native_count_mismatch:'+family)
        counts[family]=len(ids)
        for row_a,row_b in zip(expected,actual):
            if family in ('size','campaign') and row_b['allowed']=='1':
                actual_risk=numeric(row_b['risk_cash'],'double',family+':risk_cash')
                actual_budget=numeric(row_b['budget'],'double',family+':budget')
                if actual_risk is None or actual_budget is None or actual_risk<=0 or actual_risk>actual_budget:
                    raise ComparisonError('native_cash_budget_invariant:'+family+':'+row_b['case_id'])
            for name,_,kind in fields:
                where=family+':'+row_a['case_id']+':'+name
                a=numeric(row_a[name],kind,where);b=numeric(row_b[name],kind,where)
                equal=a==b
                if a is not None and b is not None and kind=='double':
                    finite_pairs+=1;max_error=max(max_error,abs(a-b))
                    # Zero is meaningful and never equivalent to absent or nonzero.
                    # Risk budget/allocation fields have tighter absolute tolerance.
                    if a==0 or b==0:equal=a==b
                    else:equal=math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-12 if ('lots' in name or name=='risk_fraction') else 1e-9)
                if not equal:
                    differences.append(dict(family=family,case_id=row_a['case_id'],field=name,expected=a,actual=b,
                       oracle_scope=family_meta['oracle_scope'][row_a['case_id']]))
    return dict(schema='vortex.native.risk-comparison.v1',status='PARITY_PASS' if not differences else 'PARITY_FAIL',
      fixture_kind=KIND,core_version=CORE_VERSION,harness_version=HARNESS_VERSION,case_counts=counts,
      total_cases=sum(counts.values()),difference_count=len(differences),differences=differences,
      finite_numeric_pairs=finite_pairs,max_absolute_numeric_error=max_error,
      reference_manifest_sha256=digest(manifest_path),
      native_files_sha256={name:digest(native/name) for name in ['manifest.csv']+[f'risk_{family}_results.csv' for family in TABLES]},
      tolerances=dict(relative=1e-10,absolute=1e-9,allocation_absolute=1e-12,zero_exact=True),
      strategy_approval=False,execution_authorized=False,
      limitations=['Synthetic arithmetic and declared safety cases only; not profitability or execution approval.',
                   'Caller identity, freshness and calculator facts are assertions in these offline fixtures.',
                   'Source and original fixture transport require separate operator provenance evidence.'])

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference',type=Path);parser.add_argument('native',type=Path);parser.add_argument('--out',type=Path)
    args=parser.parse_args()
    try:result=compare(args.reference,args.native)
    except (ComparisonError,OSError,ValueError,KeyError,TypeError) as error:
        result=dict(status='COMPARISON_REJECTED',reason=str(error),strategy_approval=False,execution_authorized=False)
    encoded=json.dumps(result,indent=2,allow_nan=False)+'\n'
    if args.out:args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(encoded)
    print(encoded,end='');raise SystemExit(0 if result['status']=='PARITY_PASS' else 1)
