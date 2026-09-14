#!/usr/bin/env python3
"""Frozen v0.2 experiment, no broker/network calls or parameter optimization."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
from dataclasses import asdict
import hashlib
import json
import math
import platform
import numpy as np
import pandas as pd
from vortex_v02 import VERSION
from vortex_v02.data import load_export, external_context
from vortex_v02.engines import build_signals
from vortex_v02.backtest import BacktestConfig, simulate
from vortex_v02.statistics import campaign_metrics
from protocol import RISKS, PROFILES, COSTS, partitions, promotion_assessment


def clean(value):
    if isinstance(value,dict):return {str(k):clean(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)):return [clean(v) for v in value]
    if isinstance(value,np.generic):return clean(value.item())
    if isinstance(value,(datetime,pd.Timestamp)):return value.isoformat()
    if isinstance(value,float) and not math.isfinite(value):return None
    return value

def write(path,value):
    path.write_text(json.dumps(clean(value),indent=2,allow_nan=False)+'\n')

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def run(source,out,news=None,coverage=None,macro=None):
    out=Path(out)
    if out.exists() and any(out.iterdir()):raise ValueError('refusing to overwrite an existing experiment')
    out.mkdir(parents=True,exist_ok=True)
    root=Path(__file__).resolve().parent
    hashes={str(p.relative_to(root)):sha(p) for p in sorted(root.rglob('*'))
            if p.is_file() and p.suffix in ('.py','.md','.txt') and '__pycache__' not in p.parts}
    frames,audit=load_export(source)
    windows=partitions(frames['M5'].index)
    prereg=dict(experiment='xau50-fixed-v02-001',version=VERSION,
                frozen_before_evaluation_at=datetime.now(timezone.utc),source_hashes=hashes,
                risks=RISKS,costs=COSTS,profiles=PROFILES,protocol_amendment='A1_user_adaptive_exits_and_10pct_stress',
                windows=windows,external_sources={k:sha(Path(v)) if v else None for k,v in
                    [('news',news),('calendar_coverage',coverage),('macro',macro)]},
                input_audit=audit,python=platform.python_version(),numpy=np.__version__,pandas=pd.__version__)
    write(out/'preregistration.json',prereg)
    external=external_context(frames['M5'],news,coverage,macro)
    signals=build_signals(frames,external)
    signals.to_csv(out/'signals.csv')
    write(out/'data-audit.json',audit)
    diagnostics={
        'bars':len(signals),'ready':int(signals.ready.sum()),'eligible_signals':int(signals.signal.ne(0).sum()),
        'missing_news_bars':int((~external.news_valid).sum()),
        'missing_macro_bars':int((~external.macro_valid).sum()),
        'mode_counts':signals['mode'].value_counts().to_dict(),
        'engine_invalid_counts':{k:int(signals[k].isna().sum()) for k in ['orion','vortex','nova','luna','kira','atlas']},
        'h4_complete_bars':len(frames['H4']),
    }
    # Diagnostic only: cost of actual minimum volume using valid known stops.
    # It never overrides missing external inputs or generates trades.
    for cost_name,cost in COSTS.items():
        requirements=[]
        for side,col in [(1,'stop_long'),(-1,'stop_short')]:
            distance=side*(signals.close-signals[col])
            spread=signals.spread_points*.001*cost['spread_multiplier']
            need=.01*(100*(distance+spread+2*cost['slippage_per_ounce'])+2*cost['commission_per_lot_per_side'])
            valid=distance.gt(0)&np.isfinite(need)&signals.atr.gt(0)
            requirements.extend(need[valid].tolist())
        diagnostics[cost_name+'_minimum_lot_risk']={
            'count':len(requirements),'min':min(requirements) if requirements else None,
            'median':float(np.median(requirements)) if requirements else None,
            'scope':'known valid stop anchors, both directions; not eligible setups or executed trades'}
    write(out/'diagnostics.json',diagnostics)
    summaries=[];table=[]
    total=len(windows)*len(PROFILES)*len(COSTS)
    for period,bounds in windows.items():
        selected=signals.loc[(signals.index>=bounds['start'])&(signals.index<bounds['end'])]
        for allocation,profile in PROFILES.items():
            risk=profile['risk_fraction']
            for cost_name,cost in COSTS.items():
                config=BacktestConfig(starting_cash=50.,**profile,**cost)
                result=simulate(selected,config)
                sid=f'{period}__{allocation}__risk-{risk:g}__{cost_name}'
                target=out/'scenarios'/sid;target.mkdir(parents=True)
                s=result['summary'];s.update(id=sid,period=period,allocation=allocation,cost=cost_name,rows=len(selected))
                s['statistics']=campaign_metrics([x['net_pnl'] for x in s['campaigns']],
                    trading_days=len(selected.index.normalize().unique()))
                write(target/'summary.json',s)
                for name in ['trades','equity','events']:result[name].to_csv(target/f'{name}.csv',index=True)
                summaries.append(s)
                table.append({k:s.get(k) for k in ['id','period','allocation','cost','rows','starting_cash','final_equity',
                    'net_profit','n_trades','n_campaigns','n_adds','expectancy','profit_factor','max_close_sampled_drawdown',
                    'observed_log_growth_per_day','geometric_return_per_campaign','risk_of_ruin_probability','milestones','censored']}
                    |{'risk':risk})
                print(f'[{len(summaries)}/{total}] {sid}: campaigns={s["n_campaigns"]}, equity={s["final_equity"]:.2f}',flush=True)
    pd.DataFrame(table).to_csv(out/'summaries.csv',index=False)
    gate=promotion_assessment(summaries,external_complete=bool(external.news_valid.all() and external.macro_valid.all()))
    write(out/'promotion.json',gate)
    last=signals.iloc[-1]
    public=dict(schemaVersion=2,environment='BACKTEST',model=VERSION,liveFeed=False,brokerConnected=False,
        generatedAt=datetime.now(timezone.utc),sourceAsOf=last['decision_time'],startingEquity=50,
        promotion=gate,diagnostics=diagnostics,scenarios=table,
        signal={k:last.get(k) for k in ['mode','signal','consensus','atr','session','orion','vortex','nova','luna','kira','atlas',
                                       'orion_reason','vortex_reason','nova_reason','luna_reason','kira_reason','atlas_reason',
                                       'ready','news_blocked','execution_valid','next_news']},
        market=dict(symbol='XAUUSD',bid=last.close,spreadPoints=last.spread_points,time=last.decision_time,basis='historical_bar'),
        journal=[dict(event='BLOCK',reason='mandatory_news_and_macro_unavailable'),
                 dict(event='NO_GO',reason='baseline_not_statistically_evaluable')],
        milestones=[50,100,250,500,1000],milestonesAreTargetsNotForecasts=True,
        challenge=dict(startingCapital=50,maximumExternalCapital=50,topUp=0,target=50000,
                       targetType='stretch_not_forecast',endDate='2026-09-30',status='NO_GO',realAllowed=False))
    write(out/'dashboard.json',public)
    manifest={str(p.relative_to(out)):dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(out.rglob('*')) if p.is_file()}
    write(out/'artifact-manifest.json',manifest)
    return public

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',required=True);p.add_argument('--out',required=True)
    p.add_argument('--news');p.add_argument('--coverage');p.add_argument('--macro')
    a=p.parse_args();run(a.data,a.out,a.news,a.coverage,a.macro)
