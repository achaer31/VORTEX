"""Static contract checks only: these do NOT execute MQL5 or prove VPS behavior."""
from pathlib import Path
import re
import unittest


SOURCE = Path(__file__).resolve().parents[1] / 'VortexEvidenceCollector.mq5'
TEXT = SOURCE.read_text(encoding='utf-8')
CODE = re.sub(r'//[^\n]*|/\*.*?\*/', '', TEXT, flags=re.S)


def body(name):
    match = re.search(r'\b(?:bool|void|int|string)\s+'+re.escape(name)+r'\s*\([^)]*\)\s*\{',CODE)
    if not match:
        raise AssertionError('function not found: '+name)
    start=match.end(); depth=1
    for i in range(start,len(CODE)):
        if CODE[i]=='{': depth+=1
        elif CODE[i]=='}': depth-=1
        if depth==0: return CODE[start:i]
    raise AssertionError('unclosed function: '+name)


class NativeCollectorContract(unittest.TestCase):
    def test_default_is_inactive_and_expected_identity_unconfigured(self):
        self.assertRegex(CODE,r'input\s+bool\s+EnableCollection\s*=\s*false\s*;')
        self.assertRegex(CODE,r'input\s+long\s+ExpectedDemoLogin\s*=\s*0\s*;')
        entry=body('OnStart')
        self.assertLess(entry.index('if(!EnableCollection)'),entry.index('FileOpen('))
        self.assertLess(entry.index('ExpectedDemoLogin <= 0'),entry.index('FileOpen('))
        self.assertIn('MQL_TESTER',entry)

    def test_no_order_auth_network_dll_shell_or_settings_mutation_capability(self):
        calls=set(re.findall(r'\b([A-Za-z_]\w*)\s*\(',CODE))
        banned={'OrderSend','OrderSendAsync','OrderCheck','WebRequest','SendMail','SendNotification',
                'SocketCreate','SocketConnect','SocketSend','SocketTlsSend','ShellExecuteW','WinExec',
                'SymbolSelect','ChartSetInteger','ChartSetString','ChartApplyTemplate','TerminalClose',
                'ExpertRemove','FileDelete','FileCopy','FileMove'}
        self.assertFalse(calls & banned)
        self.assertNotRegex(CODE,r'#\s*(?:include|import)\b')
        self.assertNotIn('CTrade',CODE)

    def test_identity_guard_requires_expected_demo_usd_hedge_connection(self):
        guard=body('Identity')
        for required in ['ACCOUNT_LOGIN','ExpectedDemoLogin','ACCOUNT_TRADE_MODE_DEMO',
                         'ACCOUNT_CURRENCY','"USD"','ACCOUNT_MARGIN_MODE_RETAIL_HEDGING','TERMINAL_CONNECTED']:
            self.assertIn(required,guard)
        self.assertIn('ResetLastError()',guard)
        self.assertIn('GetLastError() != 0',guard)
        self.assertIn('login_after != ExpectedDemoLogin',guard)
        self.assertIn('Identity(reason)',body('SaveBars'))
        self.assertGreaterEqual(body('Heartbeat').count('Identity(reason)'),2)

    def test_lock_has_no_share_flags_and_retains_handle_until_close(self):
        lock=re.search(r'lock_handle\s*=\s*FileOpen\("VortexEvidenceCollector.lock",\s*([^;]+)\);',CODE)
        self.assertIsNotNone(lock)
        self.assertNotIn('FILE_SHARE',lock.group(1))
        self.assertIn('FILE_READ',lock.group(1)); self.assertIn('FILE_WRITE',lock.group(1))
        self.assertEqual(CODE.count('FileClose(lock_handle)'),1)
        self.assertIn('FileClose(lock_handle)',body('CloseAll'))
        self.assertIn('FILE_SHARE_READ',body('NewFile'))
        self.assertNotIn('FILE_SHARE_WRITE',CODE)

    def test_csv_header_width_matches_every_unconditional_record_cell(self):
        # Detect field insertion/omission that silently shifts metrics into another column.
        heartbeat=re.search(r'Line\(heartbeat_handle,\s*"([^"]+)"\)',CODE).group(1)
        bars=re.search(r'string header\s*=\s*"([^"]+)";',CODE).group(1)
        spec=re.search(r'Line\(spec_handle,\s*"([^"]+)"\)',body('SaveSpec')).group(1)
        for function,header,width in [('Heartbeat',heartbeat,25),('SaveBars',bars,17),('SpecLine',spec,8)]:
            with self.subTest(function=function):
                names=header.split(',')
                self.assertEqual(len(names),width)
                self.assertEqual(len(set(names)),width)
                self.assertEqual(len(re.findall(r'\bCell\(line,',body(function))),width)

    def test_invalid_heartbeat_redacts_every_quote_and_account_value(self):
        records=re.findall(r'Cell\(line, ([^;]+)\);',body('Heartbeat'))
        for record in records:
            if any(token in record for token in ['Number(','Integer(positions)','Stamp(tick.time)',
                                                 'Integer(tick.time_msc)','Stamp(TimeCurrent())',
                                                 'TimeTradeServer()']):
                self.assertTrue(record.startswith('valid ? '),record)
                self.assertTrue(record.endswith(': ""'),record)
        self.assertIn('valid ? "COLLECTING_ONLY" : "INVALID"',body('Heartbeat'))
        self.assertIn('Cell(line, "WAIT")',body('Heartbeat'))
        self.assertIn('Cell(line, "false")',body('Heartbeat'))
        self.assertIn('ResetLastError()',body('Heartbeat'))
        self.assertIn('GetLastError() != 0',body('Heartbeat'))
        self.assertNotRegex(CODE,r'(?:Cell|Print)\([^;]*ExpectedDemoLogin')

    def test_candle_closure_order_and_cursor_follow_successful_flush(self):
        load=body('LoadBars'); save=body('SaveBars')
        for required in ['rates[i].time <= previous','rates[i].time < next_bar[slot]',
                         'rates[i].time + period > (long)cutoff','SERIES_SYNCHRONIZED',
                         'rates[i].spread < 0','rates[i].real_volume < 0']:
            self.assertIn(required,load)
        self.assertLess(save.index('if(!Line('),save.index('next_bar[slot] ='))
        self.assertNotIn('next_bar[slot] =',load)
        self.assertIn('(long)rates[i].time - (long)next_bar[slot]',save)
        self.assertNotRegex(CODE,r'ArrayFill|ArrayInitialize')

    def test_write_checks_full_utf8_count_and_flush_then_stops_on_error(self):
        writer=body('Line')
        self.assertIn('CP_UTF8',writer)
        self.assertIn('written != (uint)(count - 1)',writer)
        self.assertIn('FileFlush(handle)',writer)
        self.assertGreaterEqual(writer.count('disk_failed = true'),3)
        self.assertIn('while(!IsStopped() && !disk_failed)',body('OnStart'))

    def test_heartbeat_cadence_and_both_stale_tick_checks_are_explicit(self):
        self.assertIn('const int INTERVAL_MS = 5000;',CODE)
        self.assertIn('age < 0 || age > 10',body('Quote'))
        self.assertIn('monotonic - last_tick_progress_ms > 10000',body('Quote'))
        self.assertIn('tick.time_msc < last_tick_msc',body('Quote'))
        self.assertIn('Sleep(100)',body('OnStart'))

    def test_spec_fields_remain_raw_snapshot_and_commission_unknown(self):
        spec=body('SaveSpec')
        for key in ['digits','point','tick_size','tick_value','tick_value_profit','tick_value_loss',
                    'contract_size','volume_min','volume_step','volume_max','stops_level','freeze_level',
                    'trade_exemode','order_mode','filling_mode','swap_mode','swap_long','swap_short',
                    'swap_rollover3days']:
            self.assertIn('"'+key+'"',spec)
        self.assertIn('SpecRow(h, "commission", "", "UNKNOWN", reason)',spec)
        self.assertIn('"current_snapshot_only"',body('SpecLine'))
        self.assertIn('"unavailable"',body('SpecDouble'))
        self.assertIn('"unavailable"',body('SpecInteger'))

    def test_spec_identity_checks_follow_reads_and_precede_each_write(self):
        for function,api in [('SpecDouble','SymbolInfoDouble'),('SpecInteger','SymbolInfoInteger')]:
            fn=body(function)
            self.assertLess(fn.index(api+'('),fn.index('Identity(reason)'))
            self.assertLess(fn.index('Identity(reason)'),fn.index('SpecRow('))
            self.assertIn(', reason)',fn)
        row=body('SpecRow')
        self.assertLess(row.index('Identity(reason)'),row.index('SpecLine('))
        spec=body('SaveSpec')
        self.assertIn('if(spec_handle == INVALID_HANDLE)',spec)
        self.assertEqual(spec.count('NewFile("symbol-spec.csv")'),1)
        self.assertNotIn('FileClose(',spec)
        self.assertIn('"INCOMPLETE_" + reason',spec)
        self.assertIn('if(disk_failed) reason = "disk_write_failed"',spec)
        self.assertLess(spec.rindex('Identity(reason)'),spec.index('"COMPLETE"'))
        main=body('OnStart')
        self.assertRegex(main,r'valid = SaveSpec\(reason\);\s*if\(valid\) valid = Identity\(reason\);\s*if\(valid\) spec_written=true;')


if __name__=='__main__': unittest.main()
