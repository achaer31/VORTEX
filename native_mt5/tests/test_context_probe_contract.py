"""Static contracts only; no terminal access, native compilation or feed proof."""
from pathlib import Path
import re
import unittest

from test_harness_contract import body, code_only, compact, definitions, external_calls


SOURCE = (Path(__file__).resolve().parents[1] / "VortexContextProbe.mq5").read_text(encoding="utf-8")


class ContextProbeContract(unittest.TestCase):
    def test_reviewed_read_only_api_surface(self):
        allowed = {"AccountInfoInteger", "AccountInfoString", "ArrayResize", "ArraySize",
                   "CalendarEventById", "CalendarValueHistory", "DoubleToString", "FileClose",
                   "FileFlush", "FileOpen", "FileWriteArray", "FolderCreate", "GetLastError",
                   "GetTickCount64", "IsStopped", "MQLInfoInteger", "MathAbs", "MathIsValidNumber",
                   "Print", "ResetLastError", "StringFind", "StringFormat", "StringLen",
                   "StringReplace", "StringToCharArray", "StringToUpper", "SymbolInfoDouble",
                   "SymbolInfoInteger", "SymbolInfoString", "SymbolName", "SymbolsTotal",
                   "TerminalInfoInteger", "TimeCurrent", "TimeGMT", "TimeToString", "TimeTradeServer"}
        self.assertEqual(external_calls(SOURCE, definitions(SOURCE)) - allowed, set())
        self.assertNotRegex(code_only(SOURCE), r"#\s*(?:include|import)\b")
        for forbidden in ("OrderSend", "OrderSendAsync", "OrderCheck", "SymbolSelect", "CopyRates",
                          "SymbolInfoTick", "WebRequest", "AccountInfoDouble", "PositionsTotal",
                          "TerminalClose", "FILE_COMMON", "FILE_SHARE_WRITE", "MqlTradeRequest"):
            self.assertNotRegex(code_only(SOURCE), r"\b" + forbidden + r"\b")

    def test_disabled_default_and_identity_precede_files_or_data(self):
        self.assertRegex(SOURCE, r"input\s+bool\s+EnableContextProbe\s*=\s*false")
        self.assertRegex(SOURCE, r"input\s+long\s+ExpectedDemoLogin\s*=\s*0")
        start = compact(body(SOURCE, "OnStart"))
        self.assertTrue(start.startswith('if(!EnableContextProbe||ExpectedDemoLogin<=0){Print("Contextprobedisabled;noaccountreadsorfiles.");return;}'))
        self.assertLess(start.index("MQLInfoInteger(MQL_TESTER)"), start.index("CpContinue(reason)"))
        self.assertLess(start.index("CpContinue(reason)"), start.index("FileOpen("))
        identity = body(SOURCE, "CpIdentity")
        self.assertEqual(identity.count("AccountInfoInteger(ACCOUNT_LOGIN)"), 2)
        for item in ("GetLastError()!=0", "login!=ExpectedDemoLogin", "login_after!=ExpectedDemoLogin",
                     "ACCOUNT_TRADE_MODE_DEMO", 'currency!="USD"', "ACCOUNT_MARGIN_MODE_RETAIL_HEDGING",
                     "TERMINAL_CONNECTED"):
            self.assertIn(item, identity)

    def test_no_identifier_or_account_values_in_persistence(self):
        for function in ("CpProperty", "CpManifest", "CpWrite", "CpMeta"):
            self.assertNotRegex(code_only(body(SOURCE, function)), r"\b(?:ExpectedDemoLogin|login|login_after|AccountInfo\w*)\b")
        self.assertNotRegex(SOURCE, r'Cp(?:Cell|Meta)\([^\n]*(?:ACCOUNT_LOGIN|ExpectedDemoLogin)')
        self.assertIn('CpCell(row,available?value:"")', body(SOURCE, "CpProperty"))

    def test_each_property_read_and_append_rechecks_identity(self):
        for function, api in (("CpReadString", "SymbolInfoString"), ("CpIntegerProperty", "SymbolInfoInteger"),
                              ("CpDoubleProperty", "SymbolInfoDouble")):
            source = body(SOURCE, function)
            at = source.index(api + "(")
            self.assertIn("CpContinue(reason)", source[:at])
            self.assertIn("CpContinue(reason)", source[at:])
            self.assertIn("GetLastError()", source[at:])
        prop = body(SOURCE, "CpProperty")
        self.assertLess(prop.index("CpContinue(reason)"), prop.index("CpWrite(cp_file,row)"))
        self.assertIn("CpContinue(reason)", body(SOURCE, "CpSymbols").split("SymbolName(i,false)", 1)[1])

    def test_candidate_scope_is_narrow_and_not_a_macro_conversion(self):
        match = body(SOURCE, "CpCandidate")
        literals = re.findall(r'StringFind\(label,"([^"\n]+)"\)', match)
        self.assertTrue({"DXY", "USDX", "DOLLAR INDEX", "US10Y", "TNX", "10-YEAR", "TREASURY"}.issubset(literals))
        self.assertNotIn("USD", literals)
        self.assertNotIn("10", literals)
        self.assertNotIn("USDJPY", SOURCE)
        self.assertIn('return "";', match)
        symbols = body(SOURCE, "CpSymbols")
        self.assertIn('if(category=="") continue;', symbols)
        self.assertIn("SymbolsTotal(false)", symbols)
        self.assertIn("SymbolName(i,false)", symbols)
        self.assertIn("SYMBOL_TRADE_CALC_MODE", symbols)
        self.assertIn("SYMBOL_CUSTOM", symbols)
        self.assertIn("SYMBOL_CURRENCY_PROFIT", symbols)

    def test_catalog_and_resource_limits_fail_explicitly(self):
        symbols = compact(body(SOURCE, "CpSymbols"))
        for token in ("cp_total>CP_MAX_SYMBOLS", "cp_candidates>=CP_MAX_CANDIDATES",
                      "GetTickCount64()-cp_start_ms>CP_SCAN_BUDGET_MS", "seen[j]==symbol",
                      "total_after!=cp_total", "ArrayResize(seen,i+1,256)!=i+1"):
            self.assertIn(token, symbols)
        self.assertIn("cp_value_rows>CP_MAX_CALENDAR_ROWS", body(SOURCE, "CpCalendar"))
        self.assertIn('reason="interrupted"; return false;', body(SOURCE, "CpContinue"))

    def test_calendar_counts_are_server_time_and_errors_are_not_empty_coverage(self):
        calendar = compact(body(SOURCE, "CpCalendar"))
        self.assertIn('CalendarValueHistory(values,cp_from,cp_to,NULL,"USD")', calendar)
        self.assertIn("cp_query_error=GetLastError()", calendar)
        self.assertIn("cp_query_returned==cp_value_rows", calendar)
        self.assertIn("cp_metadata_errors==0", calendar)
        self.assertIn("cp_ambiguous_high==0", calendar)
        self.assertIn("event.time_mode!=CALENDAR_TIMEMODE_DATETIME", calendar)
        self.assertIn("if(!ok||error!=0){++cp_metadata_errors;continue;}", calendar)
        self.assertIn("values[i].time<cp_from||values[i].time>cp_to", calendar)
        self.assertLess(calendar.index("CalendarEventById("), calendar.index("cp_received=TimeGMT()"))
        self.assertNotIn("event.name", calendar)
        self.assertNotIn("actual_value", calendar)

    def test_clock_pair_not_query_completion_is_used_for_unverified_consistency(self):
        calendar = compact(body(SOURCE, "CpCalendar"))
        self.assertIn("cp_server=TimeTradeServer();cp_server_host_sample=TimeGMT();", calendar)
        manifest = body(SOURCE, "CpManifest")
        self.assertIn("(long)cp_server-(long)cp_server_host_sample", manifest)
        self.assertNotIn("(long)cp_server-(long)cp_received", manifest)
        self.assertIn('"CONSISTENT_UNVERIFIED":"DISAGREEMENT_OR_SAMPLE_DELAY"', manifest)
        self.assertIn('"server_utc_offset","UNKNOWN_NOT_INFERRED_FROM_CLOCK_DIFFERENCE"', manifest)
        self.assertNotRegex(body(SOURCE, "CpStamp"), r'\+\s*"Z"')

    def test_private_exclusive_lock_flush_and_complete_marker(self):
        start = compact(body(SOURCE, "OnStart"))
        self.assertIn('FileOpen("VortexContextProbe.lock",FILE_READ|FILE_WRITE|FILE_BIN)', start)
        self.assertIn("FILE_WRITE|FILE_BIN|FILE_SHARE_READ", start)
        self.assertIn("if(!FolderCreate(cp_folder))", start)
        self.assertIn("if(!cp_disk_failed)CpManifest(ok,reason)", start)
        write = compact(body(SOURCE, "CpWrite"))
        self.assertIn("written!=(uint)(count-1)||GetLastError()!=0", write)
        self.assertIn("FileFlush(handle)", write)
        manifest = compact(body(SOURCE, "CpManifest"))
        self.assertIn("boolidentity_final=valid&&CpContinue(identity_reason)", manifest)
        self.assertIn('"manifest_complete",ok&&!cp_disk_failed&&identity_final?"true":"false"', manifest)
        keys = re.findall(r'CpMeta\(out,"([^"\n]+)"', body(SOURCE, "CpManifest"))
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(keys[-1], "manifest_complete")

    def test_outputs_are_discovery_not_strategy_inputs_or_approval(self):
        manifest = body(SOURCE, "CpManifest")
        for flag in ("coverage_attested", "news_valid", "macro_valid", "historical_available_at_proven",
                     "execution_enabled", "strategy_approval"):
            self.assertIn(f'CpMeta(out,"{flag}","false")', manifest)
        self.assertIn('CpMeta(out,"action","WAIT")', manifest)
        self.assertIn('"INVALID":clean?"DISCOVERY_COMPLETED":"DISCOVERY_COMPLETED_WITH_ISSUES"', manifest)
        self.assertNotIn("#include", SOURCE)
        prop = body(SOURCE, "CpProperty")
        header = re.search(r'CpWrite\(cp_file,"([^"\n]+)"\)', body(SOURCE, "OnStart")).group(1)
        self.assertEqual(len(header.split(",")), 11)
        self.assertEqual(len(re.findall(r"CpCell\(row,", prop)), 11)


if __name__ == "__main__":
    unittest.main()
