"""Static native-harness contracts; these do not execute or compile MQL5.

They guard the small permitted API surface, source ordering and the CSV boundary.
Actual parser behavior and numerical parity require a separately observed native
run plus the Python comparator. Synthetic scanner mutations below are not broker
or strategy acceptance evidence.
"""
from pathlib import Path
import ast
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
HARNESS = (ROOT / "VortexParityCheck.mq5").read_text(encoding="utf-8")
CORE = (ROOT / "VortexSignalCore.mqh").read_text(encoding="utf-8")
TOKENS = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\n]*|/\*[\s\S]*?\*/')


def code_only(source):
    """Blank comments and literals without moving source offsets."""
    return TOKENS.sub(lambda match: "".join("\n" if c == "\n" else " " for c in match[0]), source)


def body(source, name):
    code = code_only(source)
    match = re.search(r"\b(?:bool|void|int|long|double|string)\s+" + re.escape(name) + r"\s*\([^)]*\)\s*\{", code)
    if not match:
        raise AssertionError("missing source function: " + name)
    start, depth = match.end(), 1
    for index in range(start, len(code)):
        depth += (code[index] == "{") - (code[index] == "}")
        if not depth:
            return source[start:index]
    raise AssertionError("unbalanced source function: " + name)


def compact(source):
    return re.sub(r"\s+", "", source)


PURE_APIS = {"ArrayResize", "ArraySize", "ArraySort", "MathAbs", "MathIsValidNumber", "MathMax", "MathMin"}
HARNESS_APIS = PURE_APIS | {
    "ArraySetAsSeries", "DoubleToString", "FileClose", "FileFlush", "FileIsEnding",
    "FileOpen", "FileReadString", "FileSize", "FileWriteArray", "FolderCreate",
    "GetLastError", "GetTickCount64", "IsStopped", "MathFloor", "Print",
    "ResetLastError", "StringFind", "StringFormat", "StringGetCharacter", "StringLen",
    "StringReplace", "StringSplit", "StringSubstr", "StringToCharArray", "StringToDouble",
}


def external_calls(source, definitions):
    code = code_only(source)
    return set(re.findall(r"\b([A-Za-z_]\w*)\s*\(", code)) - definitions - {"if", "for", "while", "return"}


def definitions(source):
    return set(re.findall(r"\b(?:bool|void|int|long|double|string)\s+(\w+)\s*\(", code_only(source)))


def assert_offline_calls(harness, core):
    known = definitions(harness) | definitions(core)
    if external_calls(harness, known) - HARNESS_APIS:
        raise AssertionError("harness introduced an unreviewed API")
    if external_calls(core, definitions(core)) - PURE_APIS:
        raise AssertionError("pure core introduced an impure or unreviewed API")
    if re.search(r"#\s*import\b", code_only(harness + core)):
        raise AssertionError("external code import is not permitted")


def fixture_columns(name):
    # Read declarations only: no execution of the generator or oracle is needed.
    tree = ast.parse((ROOT / "tests" / "parity_fixtures.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("missing fixture schema: " + name)


class NativeHarnessContract(unittest.TestCase):
    def test_entire_compilation_unit_has_only_reviewed_offline_apis(self):
        assert_offline_calls(HARNESS, CORE)
        self.assertEqual(re.findall(r'^\s*#\s*include\s+([^\n]+)', HARNESS, re.M), ['"VortexSignalCore.mqh"'])
        self.assertNotRegex(CORE, r"#\s*(?:include|import)\b")
        self.assertNotRegex(code_only(HARNESS + CORE), r"\b(?:MqlTradeRequest|CTrade|FILE_COMMON|FILE_SHARE_WRITE)\b")

    def test_capability_guard_detects_new_calls_even_inside_helpers(self):
        for addition in (
            "void Bad(){ OrderSendAsync(request,result); }",
            'void Bad(){ CopyRates("XAUUSD",0,0,1,rates); }',
            "void Bad(){ AccountInfoInteger(ACCOUNT_LOGIN); }",
            "void Bad(){ TimeCurrent(); }",
            'void Bad(){ WebRequest("GET",url,headers,timeout,data,result,response); }',
            '#import "external.dll"\nvoid Run();\n#import',
        ):
            with self.subTest(addition=addition), self.assertRaises(AssertionError):
                assert_offline_calls(HARNESS + addition, CORE)
        with self.assertRaises(AssertionError):
            assert_offline_calls(HARNESS, CORE + "\nvoid Hidden(){ FileOpen(path,flags); }")
        assert_offline_calls(HARNESS + '\n// OrderSend(request,result);\nvoid Note(){ Print("AccountInfoInteger(login)"); }', CORE)

    def test_disabled_and_synthetic_gates_precede_all_file_outputs(self):
        self.assertRegex(HARNESS, r"input\s+bool\s+EnableOfflineParity\s*=\s*false\s*;")
        start = compact(body(HARNESS, "OnStart"))
        self.assertTrue(start.startswith('if(!EnableOfflineParity){Print("Offlineparityharnessdisabled;nofilesopened.");return;}'))
        ordered = ["if(!SafeName(FixtureDirectory))", 'InputFile("fixture_kind.txt",error)',
                   "if(marker==INVALID_HANDLE)", "Header(marker,FIXTURE_KIND,error)", "if(!synthetic)",
                   "if(!LoadCases(cases,error))", "if(!FolderCreate(result_folder))", "LoadRates(", "VxBuildSignals("]
        positions = [start.index(token) for token in ordered]
        self.assertEqual(positions, sorted(positions))
        self.assertIn('conststringFIXTURE_KIND="SYNTHETIC_OFFLINE_PARITY_V1";', compact(HARNESS))
        self.assertIn('if(!FolderCreate(result_folder)){Print("Offlineparitycannotcreatenewoutputfolder.");return;}', start)

    def test_paths_are_single_bounded_names_and_only_fixture_reads(self):
        safe = compact(body(HARNESS, "SafeName"))
        self.assertIn("if(n<1||n>48)returnfalse;", safe)
        self.assertIn("if(!((c>='A'&&c<='Z')||(c>='a'&&c<='z')||(c>='0'&&c<='9')||c=='_'||c=='-'))returnfalse;", safe)
        self.assertIn("if(!SafeName(name)||ArraySize(cases)>=MAX_CASES)", compact(body(HARNESS, "LoadCases")))
        inp = compact(body(HARNESS, "InputFile"))
        self.assertIn('FileOpen(FixtureDirectory+"\\\\"+name,FILE_READ|FILE_TXT|FILE_ANSI,0,CP_UTF8)', inp)
        self.assertIn("if(FileSize(h)>33554432)", inp)
        self.assertIn('FileClose(h);error="fixture_file_too_large";returnINVALID_HANDLE;', inp)
        self.assertIn('FileOpen(result_folder+"\\\\"+name,FILE_WRITE|FILE_BIN)', compact(body(HARNESS, "OutputFile")))
        self.assertEqual(len(re.findall(r"\bFileOpen\s*\(", code_only(HARNESS))), 2)
        self.assertNotIn("expected_", HARNESS)  # Native calculation cannot read the oracle CSVs.

    def test_exact_headers_width_and_no_quoted_input_shortcuts(self):
        header = compact(body(HARNESS, "Header"))
        self.assertIn("if(FileIsEnding(h))", header)
        self.assertIn("StringGetCharacter(line,0)==65279", header)
        self.assertIn('if(line!=expected){error="fixture_header_mismatch";returnfalse;}', header)
        fields = compact(body(HARNESS, "Fields"))
        self.assertIn('StringFind(line,"\\\"")>=0||StringSplit(line,\',\',fields)!=count', fields)
        self.assertIn('error="fixture_csv_width_or_quoting";returnfalse;', fields)
        for function, schema in (("LoadRates", "FRAME_COLUMNS"), ("LoadExternal", "EXTERNAL_COLUMNS"), ("ModeCases", "MODE_COLUMNS")):
            function_source = body(HARNESS, function)
            declared = re.search(r'Header\([^,]+,"([^"\n]+)",error\)', function_source).group(1).split(",")
            self.assertEqual(declared, fixture_columns(schema))
            self.assertIn(f"Fields(line,{len(declared)},f,error)", function_source)

    def test_numeric_missingness_and_full_token_checks_remain_fail_closed(self):
        numeric = compact(body(HARNESS, "Numeric"))
        for required in ('if(text==""){value=EMPTY_VALUE;return!required;}', "if(!digits)returnfalse;",
                         "if(i==exponent_start)returnfalse;", "if(i!=n)returnfalse;", "returnVxValid(value);"):
            self.assertIn(required, numeric)
        self.assertLess(numeric.index("if(i!=n)returnfalse;"), numeric.index("StringToDouble(text)"))
        integer = compact(body(HARNESS, "IntegerValue"))
        self.assertIn("!Numeric(text,true,number)||MathAbs(number)>9000000000000000.0||MathFloor(number)!=number", integer)
        self.assertIn('if(text!="0"&&text!="1")returnfalse;', compact(body(HARNESS, "Flag")))

    def test_bars_reject_duplicates_bad_prices_negative_volume_and_oversized_spread(self):
        rates = compact(body(HARNESS, "LoadRates"))
        for required in ("longprevious=0;", "epoch>previous", "spread<0", "spread>2147483647",
                         "row.tick_volume<0", "row.real_volume<0", "row.low<=0",
                         "row.low>MathMin(row.open,row.close)", "row.high<MathMax(row.open,row.close)",
                         "n>=MAX_FRAME_ROWS", 'error="empty_fixture_frame";returnfalse;'):
            self.assertIn(required, rates)
        self.assertEqual(len(re.findall(r"Numeric\(f\[\d+\],true,row\.", rates)), 4)
        self.assertIn("rates[n]=row;previous=epoch;", rates)

    def test_external_missingness_and_mode_ids_are_not_silently_invented(self):
        external = compact(body(HARNESS, "LoadExternal"))
        self.assertIn("VxResetExternal(row)", external)
        self.assertIn("epoch>previous", external)
        self.assertEqual(len(re.findall(r"Numeric\(f\[\d+\],false,row\.", external)), 8)
        self.assertEqual(len(re.findall(r"Flag\(f\[\d+\],row\.", external)), 5)
        self.assertNotIn("empty_fixture_frame", external)  # Header-only external input is intentional.
        modes = compact(body(HARNESS, "ModeCases"))
        for required in ("SafeName(f[0])", "h1>=-1&&h1<=1&&h4>=-1&&h4<=1", "ids[j]==f[0]",
                         "n>=MAX_MODE_CASES", 'error="no_mode_cases";returnfalse;'):
            self.assertIn(required, modes)
        self.assertIn('error="duplicate_case_id"', body(HARNESS, "LoadCases"))

    def test_csv_output_column_count_and_missing_context_agree_with_oracle_schema(self):
        output = body(HARNESS, "SaveSignals")
        header = re.search(r'WriteLine\(h,"([^"\n]+)"\)', output).group(1).split(",")
        self.assertEqual(header, fixture_columns("OUTPUT_COLUMNS"))
        self.assertEqual(len(re.findall(r"Cell\(line,", output)), len(header))
        self.assertEqual(len(header), 32)
        self.assertIn('return VxValid(value) ? DoubleToString(value,16) : "";', body(HARNESS, "FloatText"))
        self.assertIn('return value == 0 ? "" : IntText((long)value);', body(HARNESS, "TimeText"))
        for timeframe in ("h1", "h4"):
            self.assertIn(f'Cell(line,r.{timeframe}ClosedAt==0 ? "" : IntText(r.{timeframe}Alignment))', output)

    def test_disk_short_write_flush_and_interrupt_cannot_report_computed(self):
        write = compact(body(HARNESS, "WriteLine"))
        self.assertIn("FileWriteArray(h,bytes,0,(uint)(count-1))", write)
        self.assertIn("written!=(uint)(count-1)||GetLastError()!=0", write)
        self.assertIn("output_failed=true;returnfalse;", write)
        self.assertIn("if(GetLastError()!=0)output_failed=true;", compact(body(HARNESS, "FinishFile")))
        start = compact(body(HARNESS, "OnStart"))
        self.assertIn('if(IsStopped()){ok=false;error="interrupted";}', start)
        self.assertIn('if(output_failed){ok=false;error="output_write_failed";}', start)
        self.assertLess(start.index('if(output_failed)'), start.index("Manifest(ok,"))
        self.assertIn('if(ok&&ArraySize(result)!=ArraySize(m5))', start)
        self.assertIn("if(ok)++completed;", start)

    def test_manifest_records_counts_but_never_approves_parity_or_strategy(self):
        manifest = body(HARNESS, "Manifest")
        keys = re.findall(r'ManifestRow\(h,"([^"\n]+)"', manifest)
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(set(keys), {"schema", "fixture_kind", "harness_version", "core_version", "status",
                                   "cases_requested", "cases_completed", "signal_rows", "mode_cases", "mode_results",
                                   "error", "parity_evaluated", "strategy_approval"})
        self.assertIn('computed && !output_failed ? "COMPUTED_FOR_COMPARISON" : "FAILED"', manifest)
        self.assertIn('ManifestRow(h,"parity_evaluated","false")', manifest)
        self.assertIn('ManifestRow(h,"strategy_approval","false")', manifest)
        self.assertIn("Python comparison still required", body(HARNESS, "OnStart"))


if __name__ == "__main__":
    unittest.main()
