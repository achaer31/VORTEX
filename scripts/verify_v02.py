"""Reconcile public v0.2 results with frozen sources; requires no private bars."""
from pathlib import Path
import hashlib
import json
import math

ROOT=Path(__file__).resolve().parents[1]
report=ROOT/'reports/v0.2'
prereg=json.loads((report/'preregistration.json').read_text())
public=json.loads((ROOT/'dashboard/assets/v02.json').read_text())
manifest=json.loads((report/'artifact-manifest.json').read_text())
assert public['schemaVersion']==2 and public['environment']=='BACKTEST'
assert public['model']==prereg['version']=='VORTEX-XAU-EXTREME-v0.2'
assert public['liveFeed'] is False and public['brokerConnected'] is False
assert public['challenge']['realAllowed'] is False
assert public['challenge']['topUp']==0 and public['startingEquity']==50
assert not public['promotion']['forward_demo_trading_enabled']
assert public['promotion']==json.loads((report/'promotion.json').read_text())
for name,expected in prereg['source_hashes'].items():
    assert hashlib.sha256((ROOT/'research_v02'/name).read_bytes()).hexdigest()==expected,name
records={p.parent.name:json.loads(p.read_text()) for p in (report/'scenarios').glob('*/summary.json')}
expected_count=len(prereg['windows'])*len(prereg['profiles'])*len(prereg['costs'])
assert len(records)==len(public['scenarios'])==expected_count==100
assert len({s['id'] for s in public['scenarios']})==expected_count
for row in public['scenarios']:
    source=records[row['id']]
    for key,value in row.items():
        if key=='risk':assert value==source['config']['risk_fraction']
        else:assert value==source[key],(row['id'],key)
    path='scenarios/'+row['id']+'/summary.json'
    assert hashlib.sha256((report/path).read_bytes()).hexdigest()==manifest[path]['sha256']
    assert source['starting_cash']==50 and source['deployable_configuration'] is False
    if source['n_campaigns']==0:
        assert source['expectancy'] is None and source['risk_of_ruin_probability'] is None
        assert source['final_equity']==50 and source['net_profit']==0
        assert not any(m['hit'] for m in source['milestones'])
assert hashlib.sha256((ROOT/'dashboard/assets/v02.json').read_bytes()).hexdigest()==manifest['dashboard.json']['sha256']
assert public['diagnostics']['missing_macro_bars']==public['diagnostics']['bars']
assert public['diagnostics']['missing_news_bars']==public['diagnostics']['bars']
assert public['signal']['atlas'] is None and public['signal']['consensus'] is None
print(f'v0.2 reconciled: {expected_count} scenarios; frozen source hashes; no live or performance fabrication.')
