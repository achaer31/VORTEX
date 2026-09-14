"""Source-contract checks, NOT an MQL compiler or a broker/runtime simulation.

These guard opt-in, read-only capability boundaries, exact-byte I/O and commit
ordering. Actual compile/run and returned private evidence need separate review.
"""
import json
from pathlib import Path
import re
import unittest

SOURCE = (Path(__file__).resolve().parents[1] / "VortexAccountEvidence.mq5").read_text()


def scan(text):
    """Yield code characters/offsets while ignoring strings and line comments."""
    i=0
    while i<len(text):
        if text.startswith("//",i):
            end=text.find("\n",i);i=len(text) if end<0 else end+1;continue
        if text[i]=='"':
            i+=1
            while i<len(text):
                if text[i]=='\\':i+=2;continue
                if text[i]=='"':i+=1;break
                i+=1
            continue
        yield i,text[i];i+=1


def function(name):
    match=re.search(r'\b(?:void|bool|string)\s+'+name+r'\([^\n]*\)(?:\n|\s)*\{',SOURCE)
    if not match:
        # Invalid's declaration spans two lines.
        match=re.search(r'\bvoid\s+'+name+r'\([^)]*\)\s*\{',SOURCE)
    assert match,name
    start=match.end();depth=1
    for offset,char in scan(SOURCE[start:]):
        if char=='{':depth+=1
        elif char=='}':
            depth-=1
            if not depth:return SOURCE[start:start+offset]
    raise AssertionError("Unterminated function "+name)


def manifest_parts(name):
    body=function(name);start=body.index('string manifest=')+len('string manifest=')
    text=body[start:]
    end=next(i for i,c in scan(text) if c==';');text=text[:end]
    parts=[];last=0;depth=0
    for offset,char in scan(text):
        if char=='(':depth+=1
        elif char==')':depth-=1
        elif char=='+' and depth==0:
            parts.append(text[last:offset].strip());last=offset+1
    parts.append(text[last:].strip());return parts


def render_manifest(name,valid=True,count=3,unsupported=0):
    expressions={
        '(valid?"VALID_CAPTURE":"INVALID")':'VALID_CAPTURE' if valid else 'INVALID',
        '(selected?"true":"false")':'true' if valid else 'false',
        'why':'capture_checks_passed' if valid else 'synthetic_invalid',
        'IntegerToString((long)from_time)':'0', 'IntegerToString((long)through_time)':'1789372800',
        'T(through_time)':'2026-09-14T08:00:00', 'IntegerToString(count)':str(count),
        'IntegerToString(ArraySize(rows))':str(max(count,0)), 'IntegerToString(unsupported)':str(unsupported),
        'IntegerToString(TerminalInfoInteger(TERMINAL_BUILD))':'6182',
        'IntegerToString(select_error)':'0' if valid else '4401',
        '(count<0?"null":IntegerToString(count))':'null' if count<0 else str(count),
    }
    result=[]
    for part in manifest_parts(name):
        if part.startswith('"'):result.append(json.loads(part))
        else:result.append(expressions[part])
    return json.loads(''.join(result))


class AccountEvidenceSourceTests(unittest.TestCase):
    def test_opt_in_is_required_before_reads_or_folder_creation(self):
        self.assertRegex(SOURCE,r'input\s+bool\s+EnableExport=false\s*;')
        self.assertRegex(SOURCE,r'input\s+long\s+ExpectedDemoLogin=0\s*;')
        body=function('OnStart')
        self.assertTrue(body.index('if(!EnableExport || ExpectedDemoLogin<=0)') < body.index('Snapshot(before)') < body.index('HistorySelect('))
        self.assertIn('return;',body[:body.index('Snapshot(before)')])

    def test_demo_usd_hedge_identity_and_stability_bracket_reads_writes(self):
        identity=function('Identity')
        for gate in ('ACCOUNT_LOGIN)==ExpectedDemoLogin','ACCOUNT_TRADE_MODE_DEMO',
                     'ACCOUNT_MARGIN_MODE_RETAIL_HEDGING','ACCOUNT_CURRENCY)=="USD"','TERMINAL_CONNECTED','MQL_TESTER'):
            self.assertIn(gate,identity)
        for name in ('Snapshot','WriteText','WriteDeals'):
            self.assertIn('if(!Identity()) return false;',function(name))
        body=function('OnStart')
        self.assertIn('!Snapshot(after) || !Same(before,after)',body)
        self.assertGreaterEqual(body.count('!Snapshot(commit) || !Same(before,commit)'),3)
        for metric in ('balance','equity','profit','credit','margin','free_margin','leverage','positions','orders'):
            self.assertIn('a.'+metric,function('Same'))

    def test_full_history_and_raw_accounting_fields_without_strategy_filter(self):
        body=function('OnStart')
        self.assertIn('datetime from_time=0,through_time=TimeTradeServer();',body)
        self.assertEqual(body.count('HistorySelect('),1)
        self.assertIn('HistorySelect(from_time,through_time)',body)
        self.assertIn('HistoryDealsTotal()',body)
        self.assertIn('count>MAX_DEALS',body)
        self.assertNotRegex(SOURCE,r'\bHistoryDealSelect\s*\(')
        for property_name in ('DEAL_ORDER','DEAL_POSITION_ID','DEAL_TIME_MSC','DEAL_ENTRY','DEAL_REASON','DEAL_MAGIC',
                              'DEAL_VOLUME','DEAL_PRICE','DEAL_COMMISSION','DEAL_SWAP','DEAL_PROFIT','DEAL_FEE',
                              'DEAL_SL','DEAL_TP','DEAL_COMMENT','DEAL_EXTERNAL_ID'):
            self.assertIn(property_name,function('ReadDeal'))
        for getter in ('HistoryDealGetInteger','HistoryDealGetDouble','HistoryDealGetString'):
            self.assertRegex(function('ReadDeal'),r'if\(!'+getter+r'\(')
        self.assertNotIn('_Symbol',SOURCE)

    def test_no_trading_authentication_network_timer_or_shared_file_capability(self):
        code=''.join(char for _,char in scan(SOURCE))
        for call in ('OrderSend','OrderSendAsync','OrderCheck','WebRequest','SendMail','SendNotification',
                     'AccountOpen','TerminalClose','EventSetTimer','EventSetMillisecondTimer','ShellExecuteW'):
            self.assertNotRegex(code,r'\b'+call+r'\s*\(')
        self.assertNotIn('#import',code);self.assertNotIn('#include',code)
        self.assertNotIn('FILE_COMMON',code);self.assertNotIn('FILE_REWRITE',code)

    def test_all_bytes_must_be_written_before_flush_close_and_commit(self):
        writer=function('WriteUtf8')
        self.assertIn('uchar bytes[];',writer)
        self.assertIn('StringToCharArray(value,bytes,0,WHOLE_ARRAY,CP_UTF8)',writer)
        self.assertIn('bytes[count-1]!=0',writer)
        self.assertIn('int expected=count-1;',writer)
        self.assertIn('FileWriteArray(handle,bytes,0,expected)',writer)
        self.assertIn('written==(uint)expected && GetLastError()==0',writer)
        self.assertNotIn('FileWriteString(',SOURCE)
        for name in ('WriteText','WriteDeals'):
            body=function(name)
            self.assertIn('FILE_WRITE|FILE_BIN',body)
            self.assertIn('WriteUtf8(h,',body)
            self.assertIn('FileFlush(h); ok=(ok && GetLastError()==0);',body)
            self.assertIn('FileClose(h); return(ok && GetLastError()==0);',body)

    def test_manifest_is_last_guarded_commit_and_invalid_marker_is_distinct(self):
        body=function('OnStart')
        deals=body.index('!FileMove(folder+"\\\\deals.part"')
        account=body.index('!FileMove(folder+"\\\\account.part"')
        manifest=body.index('!FileMove(folder+"\\\\manifest.part"')
        self.assertLess(deals,account);self.assertLess(account,manifest)
        self.assertIn('!Snapshot(commit) || !Same(before,commit)',body[account:manifest])
        self.assertIn('commit_failed',body[manifest:])
        self.assertIn('INVALID.json',function('Invalid'))
        self.assertNotIn('manifest.json',function('Invalid'))

    def test_actual_manifest_templates_parse_and_do_not_claim_go_or_completeness(self):
        valid=render_manifest('OnStart')
        self.assertEqual(valid['status'],'VALID_CAPTURE')
        self.assertEqual(valid['returnedDealCount'],valid['writtenDealCount'])
        self.assertEqual(valid['requestedFromEpochSeconds'],0)
        self.assertFalse(valid['baselineGo']);self.assertFalse(valid['capitalOrCostsApproved'])
        self.assertFalse(valid['atomicBrokerSnapshot']);self.assertIsNone(valid['dailyEquityDrawdown'])
        self.assertEqual(valid['independentHistoryCompleteness'],'NOT_PROVEN')
        self.assertEqual(render_manifest('OnStart',False,count=0)['status'],'INVALID')
        invalid=render_manifest('Invalid',False,count=-1)
        self.assertEqual(invalid['status'],'INVALID');self.assertIsNone(invalid['returnedDealCount'])
        self.assertFalse(invalid['dataWrittenCompletely'])
        self.assertEqual(render_manifest('Invalid',False,count=100001)['returnedDealCount'],100001)


if __name__=='__main__':unittest.main()
