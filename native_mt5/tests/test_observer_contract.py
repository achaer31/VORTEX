"""Source safety contracts only; target compiler/runtime evidence is separate."""
from pathlib import Path
import re
import unittest

SOURCE = (Path(__file__).parents[1] / "VortexNativeObserve.mq5").read_text()


class NativeObserverContract(unittest.TestCase):
    def test_no_execution_or_external_access_capability(self):
        code = re.sub(r"//[^\n]*", "", SOURCE)
        for forbidden in (r"\bOrderSend\s*\(", r"\bOrderSendAsync\s*\(",
                          r"\bMqlTradeRequest\b", r"\bCTrade\b", r"#import",
                          r"\bWebRequest\s*\(", r"\bSocket\w*\s*\(",
                          r"\bTerminalClose\s*\(", r"\bChartSet\w*\s*\("):
            self.assertNotRegex(code, forbidden)

    def test_disabled_defaults_and_expected_demo_identity(self):
        self.assertRegex(SOURCE, r"input bool EnableObservation\s*=\s*false")
        self.assertRegex(SOURCE, r"input long ExpectedDemoLogin\s*=\s*0")
        identity = SOURCE.split("bool ObsIdentity", 1)[1].split("bool ObsQuote", 1)[0]
        for required in ("ACCOUNT_TRADE_MODE_DEMO", "ACCOUNT_MARGIN_MODE_RETAIL_HEDGING",
                         'ACCOUNT_CURRENCY)=="USD"', "TERMINAL_CONNECTED", "GetLastError()!=0"):
            self.assertIn(required, identity)
        self.assertEqual(identity.count("ACCOUNT_LOGIN)==ExpectedDemoLogin"), 2)

    def test_actual_closed_history_and_bounded_scope(self):
        rates = SOURCE.split("bool ObsRates", 1)[1].split("bool ObsRecord", 1)[0]
        self.assertIn('CopyRates("XAUUSD",tf,1,required,rates)', rates)
        self.assertIn("n!=required", rates)
        self.assertIn("rates[i].time+seconds>cutoff", rates)
        self.assertIn("SERIES_SYNCHRONIZED", rates)
        self.assertIn("OBS_M5=600, OBS_M15=600, OBS_H1=1000", SOURCE)

    def test_no_invented_external_context_or_trade_readiness(self):
        self.assertIn("ArrayResize(external,0)", SOURCE)
        self.assertIn("!rows[n-1].ready", SOURCE)
        self.assertIn('rows[n-1].mode=="FROZEN"', SOURCE)
        self.assertIn('ObsCell(row,"false"); // No execution adapter', SOURCE)
        self.assertIn("calendar_macro_session_adapter_unavailable", SOURCE)

    def test_stale_protection_and_postcalculation_recheck(self):
        self.assertIn("obs_last_tick", SOURCE)
        self.assertIn("age>10", SOURCE)
        self.assertIn("GetTickCount64()-obs_tick_progress>10000", SOURCE)
        self.assertIn("frozen_symbol_point_mismatch", SOURCE)
        after = SOURCE.split("VxBuildSignals(m5,m15,h1,external,rows,reason)", 1)[1]
        self.assertIn("ObsIdentity(reason) && ObsQuote(tick,reason)", after)
        self.assertIn("target==(datetime)(((long)tick.time/300)*300)", after)

    def test_private_journal_lock_redaction_and_exact_write(self):
        self.assertIn('FileOpen("VortexNativeObserve.lock",FILE_READ|FILE_WRITE|FILE_BIN)', SOURCE)
        self.assertIn("FILE_WRITE|FILE_BIN|FILE_SHARE_READ", SOURCE)
        self.assertIn("count!=(uint)(n-1)", SOURCE)
        self.assertIn("FileFlush(obs_file)", SOURCE)
        self.assertIn("while(!IsStopped() && !obs_disk_failed)", SOURCE)
        record = SOURCE.split("bool ObsRecord", 1)[1].split("void OnStart", 1)[0]
        self.assertIn("if(signal_available && !ObsIdentity(identity_reason))", record)
        self.assertIn('signal_available=false; kind="HEALTH"', record)
        self.assertIn("return written && (!requested_decision || signal_available)", record)
        self.assertEqual(len(re.findall(r"ObsCell\(row,signal_available\?", record)), 19)
        header = re.search(r'if\(!ObsWrite\("(sequence,[^"\n]+)"\)\)', SOURCE).group(1)
        self.assertEqual(len(header.split(",")), len(re.findall(r"ObsCell\(row,", record)))
        self.assertEqual(len(header.split(",")), 30)


if __name__ == "__main__":
    unittest.main()
