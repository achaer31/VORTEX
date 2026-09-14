"""Reconcile the published dashboard with the archived experiment, without raw data."""
from datetime import datetime, timedelta
from pathlib import Path
import json
import math


def verify(repo):
    report = repo / 'reports' / 'v0.1'
    snapshot = json.loads((repo / 'dashboard/assets/snapshot.json').read_text())
    experiment = json.loads((report / 'experiment.json').read_text())
    audit = json.loads((report / 'audit.json').read_text())
    assert snapshot['meta']['model'] == experiment['model_version']
    assert snapshot['meta']['mode'] == 'historical_research_snapshot'
    assert snapshot['meta']['liveFeed'] is False
    assert snapshot['meta']['brokerConnection'] is False
    assert snapshot['meta']['timeBasis'] == experiment['broker_time_basis']
    cutoff = datetime.fromisoformat(snapshot['meta']['asOf'])
    for timeframe, minutes in [('M5', 5), ('M15', 15), ('H1', 60)]:
        assert snapshot['dataset']['sourceHashes'][timeframe] == experiment['raw_csv_sha256'][f'XAUUSD_{timeframe}.csv']
        assert snapshot['dataset']['counts'][timeframe] == audit['files'][timeframe]['rows']
        candles = snapshot['candles'][timeframe]
        assert 1 <= len(candles) <= 200
        times = [datetime.fromisoformat(c['t']) for c in candles]
        assert all(a < b for a, b in zip(times, times[1:]))
        assert all(t + timedelta(minutes=minutes) <= cutoff for t in times)
        for c in candles:
            assert all(math.isfinite(c[k]) for k in ('o', 'h', 'l', 'c'))
            assert c['l'] <= min(c['o'], c['c']) <= max(c['o'], c['c']) <= c['h']
            assert c['v'] >= 0 and c['spread'] >= 0
    actual = {p.parent.name: json.loads(p.read_text()) for p in (report / 'scenarios').glob('*/summary.json')}
    public = snapshot['scenarios']
    assert len(public) == len(actual) == experiment['completed_scenario_count']
    assert len({s['id'] for s in public}) == len(public)
    assert {s['id'] for s in public} == set(actual)
    for s in public:
        source = actual[s['id']]
        for published, original in [('startingEquity', 'starting_cash'), ('finalEquity', 'final_equity'), ('netPnl', 'net_profit'), ('trades', 'n_trades'), ('drawdown', 'max_close_sampled_drawdown'), ('winRate', 'win_rate')]:
            assert s[published] == source[original], (s['id'], published)
        assert s['rejected'] == source['skip_reasons'].get('min_lot', 0)
        assert s['risk'] == source['config']['risk_fraction']
        assert math.isclose(s['budget'], s['startingEquity'] * s['risk'])
        if s['trades'] == 0:
            assert all(point['value'] == source['starting_cash'] for point in s['equity'])
    scores = snapshot['signal']['scores']
    combined = sum(scores[name] * weight for name, weight in experiment['signal_weights'].items())
    assert math.isclose(snapshot['signal']['consensus'], combined, abs_tol=1e-8)
    print(f'Public snapshot reconciled: {len(public)} scenarios, three candle timeframes, six weighted scores.')


if __name__ == '__main__':
    verify(Path(__file__).resolve().parents[1])
