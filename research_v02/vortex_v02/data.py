"""Strict historical ingestion, complete H4 aggregation and point-in-time context."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd

PERIODS = {"M5": 5, "M15": 15, "H1": 60, "H4": 240}


def validate_bars(frame, timeframe):
    if timeframe not in PERIODS or frame.empty:
        raise ValueError("missing timeframe/data")
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise ValueError("timezone-aware UTC bar opens required")
    if not frame.index.is_unique or not frame.index.is_monotonic_increasing or frame.index.hasnans:
        raise ValueError("bar times must be unique, ascending, nonmissing")
    f = frame.copy()
    f.index = f.index.tz_convert("UTC")
    columns = ['open','high','low','close','tick_volume','spread_points']
    f[columns] = f[columns].apply(pd.to_numeric, errors='raise')
    if not np.isfinite(f[columns].to_numpy()).all():
        raise ValueError("nonfinite bar values")
    if ((f.low <= 0) | (f.low > f[['open','close']].min(axis=1)) |
        (f.high < f[['open','close']].max(axis=1)) |
        (f.tick_volume < 0) | (f.spread_points < 0)).any():
        raise ValueError("invalid bar OHLC/counts")
    if ((f.index.second != 0) | (f.index.minute % min(PERIODS[timeframe],60) != 0)).any():
        raise ValueError("misaligned bar opens")
    return f


def aggregate_h4(h1):
    """UTC 00/04/08/... buckets, only four exact consecutive H1 bars. No filling."""
    h1 = validate_bars(h1, 'H1')
    rows = []
    for ts, group in h1.groupby(h1.index.floor('4h')):
        if len(group) != 4 or not group.index.equals(pd.date_range(ts,periods=4,freq='h')):
            continue
        rows.append(dict(time=ts,open=group.open.iloc[0], high=group.high.max(),
                         low=group.low.min(),close=group.close.iloc[-1],
                         tick_volume=group.tick_volume.sum(),spread_points=group.spread_points.iloc[-1]))
    if not rows:
        raise ValueError("no complete UTC H4 bars")
    return validate_bars(pd.DataFrame(rows).set_index('time'),'H4')


def load_export(root, server_utc_offset_hours=0):
    """Offset is explicit experiment assumption; original CSV/metadata never rewritten."""
    if server_utc_offset_hours != 0:
        raise ValueError("v0.2 frozen experiment supports verified Exness GMT+0 only")
    root = Path(root)
    frames, hashes = {}, {}
    for tf in ('M5','M15','H1'):
        path = root / f'XAUUSD_{tf}.csv'
        f = pd.read_csv(path,encoding='utf-8-sig')
        if not f.symbol.eq('XAUUSD').all() or not f.timeframe.eq(tf).all():
            raise ValueError("mixed symbol/timeframe")
        times = pd.to_datetime(f.pop('bar_open_server'), format='%Y-%m-%dT%H:%M:%S', errors='raise')
        f.index = pd.DatetimeIndex(times).tz_localize('UTC')
        frames[tf] = validate_bars(f,tf)
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    frames['H4'] = aggregate_h4(frames['H1'])
    meta = dict(raw_sha256=hashes, counts={tf:len(f) for tf,f in frames.items()},
                timezone='UTC',source_timezone_label='broker_server_unknown_offset',
                conversion_assumption='Exness GMT+0; current broker documentation, not a historical DST attestation',
                h4_origin='derived only from four exact H1 bars aligned to UTC 00/04/08/12/16/20',
                genuine_unseen_data=False)
    return frames,meta


def session_context(m5):
    """Session membership uses local timezone/DST. Levels exclude current bar.

    Last known session levels carry between sessions; never use a future final
    session high/low. A new session resets its level until the first bar closes.
    """
    decisions = m5.index + pd.Timedelta(minutes=5)
    out = pd.DataFrame(index=decisions)
    flags = {}
    for name, zone, start, end in [('asia','Asia/Tokyo',9,15),
                                 ('london','Europe/London',8,17),
                                 ('newyork','America/New_York',8,17)]:
        local = m5.index.tz_convert(zone)
        active = (local.hour >= start) & (local.hour < end)
        # Active decision membership can differ at the exact close boundary.
        now = decisions.tz_convert(zone)
        flags[name] = (now.hour >= start) & (now.hour < end)
        highs,lows=[],[]
        hi=lo=np.nan
        key=None
        for i,t in enumerate(local):
            if active[i] and key != t.date():
                key=t.date();hi=lo=np.nan
            highs.append(hi);lows.append(lo)
            if active[i]:
                hi=float(m5.high.iloc[i]) if np.isnan(hi) else max(hi,float(m5.high.iloc[i]))
                lo=float(m5.low.iloc[i]) if np.isnan(lo) else min(lo,float(m5.low.iloc[i]))
        out[f'{name}_high']=highs;out[f'{name}_low']=lows
    out['session']=np.select([flags['london'] & flags['newyork'], flags['london'], flags['newyork'], flags['asia']],
                             ['LONDON_NEWYORK','LONDON','NEWYORK','ASIA'],default='OTHER')
    out['session_ideal']=flags['london'] | flags['newyork']
    return out


def _read(path, timestamps):
    if path is None:
        return None
    f=pd.read_csv(path)
    for key in timestamps:
        if key not in f:
            raise ValueError(f'missing {key}')
        # Explicit timezone required; naive event times are never guessed.
        raw=f[key].astype(str)
        if len(raw) and not raw.str.contains(r'(?:Z|[+-]\d\d:\d\d)$',regex=True).all():
            raise ValueError('external timestamps require explicit timezone')
        f[key]=pd.to_datetime(raw,utc=True,errors='raise')
    return f


def external_context(m5, news_path=None, coverage_path=None, macro_path=None):
    out=session_context(m5)
    times=out.index
    out['news_valid']=False;out['news_blocked']=True
    out['next_news']=None
    out['macro_valid']=False;out['dxy_roc']=np.nan;out['us10y_change']=np.nan
    news=_read(news_path,['event_time','known_at'])
    coverage=_read(coverage_path,['start','end','known_at'])
    if news is not None and coverage is not None:
        if not {'currency','impact','title'}.issubset(news):
            raise ValueError('calendar columns missing')
        if (coverage.start >= coverage.end).any():
            raise ValueError('invalid calendar coverage')
        news=news.loc[news.currency.eq('USD') & news.impact.eq('high')].sort_values('event_time')
        window=pd.Timedelta(minutes=10)
        for i,t in enumerate(times):
            covered=((coverage.start <= t-window) & (coverage.end >= t+window) & (coverage.known_at <= t)).any()
            available=news.loc[news.known_at <= t]
            blocked=((available.event_time >= t-window) & (available.event_time <= t+window)).any()
            future=available.loc[available.event_time >= t]
            out.iloc[i,out.columns.get_loc('news_valid')]=bool(covered)
            out.iloc[i,out.columns.get_loc('news_blocked')]=not covered or bool(blocked)
            if len(future):
                e=future.iloc[0]
                out.iloc[i,out.columns.get_loc('next_news')]=e.event_time.isoformat()+' '+str(e.title)
    macro=_read(macro_path,['observed_at','available_at'])
    if macro is not None and not macro.empty:
        if not {'dxy','us10y_yield'}.issubset(macro):
            raise ValueError('macro columns missing')
        if ((macro.observed_at > macro.available_at).any() or
            not macro.available_at.is_monotonic_increasing or macro.available_at.duplicated().any()):
            raise ValueError('macro point-in-time ordering invalid')
        macro[['dxy','us10y_yield']]=macro[['dxy','us10y_yield']].apply(pd.to_numeric,errors='raise')
        if not np.isfinite(macro[['dxy','us10y_yield']]).all().all() or (macro.dxy <= 0).any():
            raise ValueError('invalid macro prices')
        macro['dxy_roc']=macro.dxy.pct_change(fill_method=None)*100
        macro['us10y_change']=macro.us10y_yield.diff() # percentage points, not bps
        joined=pd.merge_asof(pd.DataFrame({'decision_time':times}),macro,left_on='decision_time',
                             right_on='available_at',direction='backward')
        fresh=((joined.decision_time-joined.observed_at) <= pd.Timedelta(minutes=60)) & (joined.observed_at <= joined.decision_time)
        valid=fresh & np.isfinite(joined[['dxy_roc','us10y_change']]).all(axis=1)
        out['macro_valid']=valid.to_numpy()
        out['dxy_roc']=joined.dxy_roc.where(valid).to_numpy()
        out['us10y_change']=joined.us10y_change.where(valid).to_numpy()
    return out
