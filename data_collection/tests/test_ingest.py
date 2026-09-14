"""Synthetic adapter checks in temporary folders; NOT real acquisition evidence."""
import copy
import csv
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ingest import InvalidData, calendar_snapshot, macro_snapshots, utc, write_result


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.capture = self.root / 'capture'
        self.capture.mkdir()

    def write_csv(self, name, columns, rows):
        path = self.capture / name
        with path.open('w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=columns)
            w.writeheader(); w.writerows(rows)

    def snapshot(self, events=None, **changes):
        m = dict(schema='vortex.calendar.snapshot.v1', origin='actual_terminal_capture',
                 currency_filter='USD', run_status='captured_needs_review', terminal_connected='true',
                 query_error='0', metadata_errors='0', ambiguous_high_times='0',
                 host_utc_clock_verified='true', started_at_utc='2026-09-14T10:00:00Z',
                 received_at_utc='2026-09-14T10:00:01Z', query_start_utc='2026-09-14T09:00:00Z',
                 query_end_utc='2026-09-15T10:00:00Z', server_utc_offset_minutes='120')
        if events is None:
            events = [dict(value_id='1', event_id='2', event_time_server='2026-09-14T12:15:00',
                           importance='CALENDAR_IMPORTANCE_HIGH', time_mode='CALENDAR_TIMEMODE_DATETIME',
                           title='SYNTHETIC test, "event"', source_url='https://example.invalid', metadata_error='0')]
        m['rows'] = str(len(events)); m.update(changes)
        self.write_csv('manifest.csv', ['key', 'value'], [dict(key=k, value=v) for k,v in m.items()])
        self.write_csv('events.csv', ['value_id','event_id','event_time_server','importance','time_mode',
                                      'title','source_url','metadata_error'], events)
        return events

    def review(self, **changes):
        a = dict(schema='vortex.calendar.coverage-review.v1', status='REVIEWED',
                 snapshot_sha256={n: hashlib.sha256((self.capture/n).read_bytes()).hexdigest()
                                  for n in ['manifest.csv','events.csv']},
                 source='MT5_ECONOMIC_CALENDAR_USD', scope='ALL_USD_HIGH_IMPACT_SCHEDULED_EVENTS',
                 clock_and_offset_verified=True, feed_current_verified=True, query_scope_complete_verified=True,
                 reviewed_at='2026-09-14T10:01:00Z', evidence_note='SYNTHETIC fixture only; no real feed/clock evidence.')
        a.update(changes)
        path = self.root/'review.json'; path.write_text(json.dumps(a))
        return path

    def macro(self, **changes):
        sources = {}
        for field, instrument, unit in [('dxy','ICE_DXY_SPOT','index_points'),
                                        ('us10y_yield','US_TREASURY_10Y_YIELD','percent_per_annum')]:
            sources[field] = dict(instrument=instrument, normalized_unit=unit, reviewed=True,
                                 entitlement_confirmed=True, provider='SYNTHETIC', feed_symbol='TEST',
                                 unit_conversion='synthetic already normalized', documentation_url='https://example.invalid')
        data = dict(schema='vortex.macro.capture.v1', status='CAPTURED', origin='actual_live_capture',
                    host_utc_clock_verified=True, sources=sources, samples=[])
        for minute in ['00','05']:
            data['samples'].append({
                'dxy': dict(value=100+(minute=='05'), observed_at=f'2026-09-14T10:{minute}:00Z',
                            received_at=f'2026-09-14T10:{minute}:03Z'),
                'us10y_yield': dict(value=4.0, observed_at=f'2026-09-14T09:{50+int(minute):02d}:00Z',
                                    received_at=f'2026-09-14T10:{minute}:04Z')})
        data.update(changes)
        return data

    def macro_file(self, data):
        p=self.root/'macro.json'; p.write_text(json.dumps(data)); return p

    def test_snapshot_preserves_receipt_not_historical_event_time(self):
        self.snapshot()
        r=calendar_snapshot(self.capture)
        self.assertEqual(r['news'][0]['event_time'],'2026-09-14T10:15:00Z')
        self.assertEqual(r['news'][0]['known_at'],'2026-09-14T10:00:01Z')
        self.assertEqual(r['news'][0]['title'],'SYNTHETIC test, "event"')
        self.assertEqual(r['coverage'],[])
        self.assertFalse(r['strategy_approval'])

    def test_empty_query_never_implies_coverage(self):
        self.snapshot(events=[])
        self.assertEqual(calendar_snapshot(self.capture)['coverage'],[])

    def test_review_receipt_and_lease_prevent_backdated_or_daylong_coverage(self):
        self.snapshot()
        r=calendar_snapshot(self.capture,self.review())['coverage'][0]
        self.assertEqual(r['known_at'],'2026-09-14T10:01:00Z')
        self.assertEqual(r['end'],'2026-09-14T10:15:01Z')
        self.assertEqual(utc(r['end'])-timedelta(minutes=10),utc('2026-09-14T10:05:01Z'))

    def test_delayed_or_backdated_review_rejected(self):
        self.snapshot()
        for t in ['2026-09-14T09:59:59Z','2026-09-14T10:06:00Z']:
            with self.subTest(t=t),self.assertRaises(InvalidData):
                calendar_snapshot(self.capture,self.review(reviewed_at=t))

    def test_review_hash_binds_exact_snapshot(self):
        self.snapshot(); review=self.review()
        with (self.capture/'events.csv').open('a') as f: f.write('\n')
        with self.assertRaises(InvalidData): calendar_snapshot(self.capture,review)

    def test_error_timeout_partial_disconnect_and_clock_all_block(self):
        for changes in [dict(query_error='5400'),dict(query_error='5401'),dict(metadata_errors='1'),
                        dict(terminal_connected='false'),dict(host_utc_clock_verified='false'),
                        dict(server_utc_offset_minutes='100000'),dict(rows='5'),
                        dict(received_at_utc='2026-09-14T10:05:00Z')]:
            with self.subTest(changes=changes):
                self.snapshot(**changes)
                with self.assertRaises(InvalidData): calendar_snapshot(self.capture)

    def test_ambiguous_high_time_or_unknown_importance_blocks(self):
        rows=self.snapshot()
        for field,value in [('time_mode','CALENDAR_TIMEMODE_DATE'),('importance','UNKNOWN')]:
            changed=copy.deepcopy(rows); changed[0][field]=value
            self.snapshot(events=changed)
            with self.assertRaises(InvalidData): calendar_snapshot(self.capture)

    def test_symlink_snapshot_escape_blocks(self):
        self.snapshot(); original=self.capture/'events.csv'; outside=self.root/'outside.csv'
        original.rename(outside); original.symlink_to(outside)
        with self.assertRaises(InvalidData): calendar_snapshot(self.capture)

    def test_macro_older_component_controls_freshness_later_receipt_controls_availability(self):
        r=macro_snapshots(self.macro_file(self.macro()))
        self.assertEqual(r['macro'][0]['observed_at'],'2026-09-14T09:50:00Z')
        self.assertEqual(r['macro'][0]['available_at'],'2026-09-14T10:00:04Z')
        self.assertFalse(r['historical_coverage_proven'])

    def test_fresh_dxy_does_not_refresh_stale_yield(self):
        d=self.macro(); d['samples'][0]['us10y_yield']['observed_at']='2026-09-14T08:00:00Z'
        with self.assertRaises(InvalidData): macro_snapshots(self.macro_file(d))

    def test_futures_price_wrong_yield_units_and_unreviewed_source_rejected(self):
        for field,key,value in [('dxy','instrument','DOLLAR_INDEX_FUTURES'),
                                ('us10y_yield','normalized_unit','bond_price'),
                                ('us10y_yield','reviewed',False),('dxy','entitlement_confirmed',False)]:
            d=self.macro(); d['sources'][field][key]=value
            with self.subTest(field=field,key=key),self.assertRaises(InvalidData):
                macro_snapshots(self.macro_file(d))

    def test_duplicate_observations_do_not_create_macro_change_history(self):
        d=self.macro(); d['samples'][1]=copy.deepcopy(d['samples'][0])
        for component in d['samples'][1].values(): component['received_at']='2026-09-14T10:05:04Z'
        with self.assertRaises(InvalidData): macro_snapshots(self.macro_file(d))

    def test_future_observation_naive_timestamp_bool_nan_and_order_rejected(self):
        for key,value in [('observed_at','2026-09-14T10:30:00Z'),
                          ('received_at','2026-09-14T10:00:04'),('value',True),('value',float('nan'))]:
            d=self.macro(); d['samples'][0]['dxy'][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(InvalidData):
                macro_snapshots(self.macro_file(d))
        d=self.macro(); d['samples'].reverse()
        with self.assertRaises(InvalidData): macro_snapshots(self.macro_file(d))

    def test_templates_fail_closed_and_no_implicit_overwrite(self):
        module_root=Path(__file__).resolve().parents[1]
        with self.assertRaises(InvalidData): macro_snapshots(module_root/'macro.template.json')
        self.snapshot()
        with self.assertRaises(InvalidData): calendar_snapshot(self.capture,module_root/'coverage.template.json')
        result=calendar_snapshot(self.capture)
        write_result(self.root/'new',result)
        with self.assertRaises(FileExistsError): write_result(self.root/'new',result)
        with (self.root/'new'/'coverage.csv').open() as f: self.assertEqual(len(list(csv.reader(f))),1)

    def test_nonobject_json_rejected_without_attribute_crash(self):
        path=self.macro_file([])
        with self.assertRaises(InvalidData): macro_snapshots(path)
        self.snapshot()
        with self.assertRaises(InvalidData): calendar_snapshot(self.capture,path)

    def test_frozen_loader_consumes_receipt_times_and_expires_both_contexts(self):
        import pandas as pd
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'research_v02'))
        from vortex_v02.data import external_context
        self.snapshot()
        write_result(self.root/'calendar-output',calendar_snapshot(self.capture,self.review()))
        write_result(self.root/'macro-output',macro_snapshots(self.macro_file(self.macro())))
        bars=pd.DataFrame({'high':100.,'low':99.},
                          index=pd.date_range('2026-09-14T09:50:00Z',periods=16,freq='5min'))
        context=external_context(bars,self.root/'calendar-output'/'news.csv',
                                 self.root/'calendar-output'/'coverage.csv',
                                 self.root/'macro-output'/'macro.csv')
        # Snapshot/review did not exist at 10:00, and its brief lease ends before 10:10.
        self.assertFalse(context.loc['2026-09-14T10:00:00Z','news_valid'])
        self.assertTrue(context.loc['2026-09-14T10:05:00Z','news_valid'])
        self.assertTrue(context.loc['2026-09-14T10:05:00Z','news_blocked'])
        self.assertFalse(context.loc['2026-09-14T10:10:00Z','news_valid'])
        # Second macro pair arrives 10:05:04: a 10:05 decision cannot consume it.
        self.assertFalse(context.loc['2026-09-14T10:05:00Z','macro_valid'])
        self.assertTrue(context.loc['2026-09-14T10:10:00Z','macro_valid'])
        self.assertTrue(context.loc['2026-09-14T10:55:00Z','macro_valid'])
        self.assertFalse(context.loc['2026-09-14T11:00:00Z','macro_valid'])


if __name__=='__main__': unittest.main()
