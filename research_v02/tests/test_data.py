import tempfile
from pathlib import Path
import unittest
import pandas as pd
from vortex_v02.data import aggregate_h4, external_context, session_context, validate_bars

def bars(start='2026-03-02',periods=48,freq='h'):
    ix=pd.date_range(start,periods=periods,freq=freq,tz='UTC')
    return pd.DataFrame(dict(open=2000.,high=2002.,low=1998.,close=2001.,tick_volume=100,spread_points=180),index=ix)

class DataTests(unittest.TestCase):
    def test_h4_only_complete_exact_buckets(self):
        f=bars(periods=12); f=f.drop(f.index[5])
        result=aggregate_h4(f)
        self.assertEqual(len(result),2)
        self.assertNotIn(pd.Timestamp('2026-03-02 04:00Z'),result.index)
    def test_missing_inputs_are_invalid(self):
        x=external_context(bars(periods=24,freq='5min'))
        self.assertFalse(x.news_valid.any());self.assertFalse(x.macro_valid.any())
        self.assertTrue(x.news_blocked.all());self.assertTrue(x.dxy_roc.isna().all())
    def test_session_dst_and_no_final_high_leak(self):
        before=session_context(bars('2026-03-02 08:00',periods=2,freq='5min'))
        after=session_context(bars('2026-04-02 07:00',periods=2,freq='5min'))
        self.assertEqual(before.session.iloc[0],'LONDON')
        self.assertEqual(after.session.iloc[0],'LONDON')
        f=bars('2026-03-02 00:00',periods=4,freq='5min');f.iloc[-1,f.columns.get_loc('high')]=9999
        x=session_context(f)
        self.assertTrue(pd.isna(x.asia_high.iloc[0]));self.assertEqual(x.asia_high.iloc[-1],2002)
    def test_future_calendar_and_macro_do_not_leak(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            (p/'news.csv').write_text('event_time,known_at,currency,impact,title\n2026-03-02T00:15:00Z,2026-03-02T00:12:00Z,USD,high,Test\n')
            (p/'coverage.csv').write_text('start,end,known_at\n2026-03-01T00:00:00Z,2026-03-03T00:00:00Z,2026-03-02T00:12:00Z\n')
            (p/'macro.csv').write_text('observed_at,available_at,dxy,us10y_yield\n2026-03-01T23:55:00Z,2026-03-02T00:00:00Z,100,4\n2026-03-02T00:00:00Z,2026-03-02T00:12:00Z,101,4.1\n')
            x=external_context(bars(periods=4,freq='5min'),p/'news.csv',p/'coverage.csv',p/'macro.csv')
            self.assertFalse(x.news_valid.iloc[0]);self.assertFalse(x.macro_valid.iloc[1])
            self.assertTrue(x.news_valid.iloc[2]);self.assertTrue(x.news_blocked.iloc[2]);self.assertTrue(x.macro_valid.iloc[2])
    def test_duplicate_rejected(self):
        f=bars(periods=2);f.index=[f.index[0],f.index[0]]
        with self.assertRaises(ValueError):validate_bars(f,'H1')
