"""Synthetic oracle/comparator integrity tests. No native run is performed here."""
import csv
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parent))
from parity_fixtures import (KIND, OUTPUT_COLUMNS, generate, fine_bars, scenario,
                             mode_cases, mode_from_scores, write_csv)
from compare_parity import ComparisonError, compare_directory, compare_tables


class ComparatorTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.columns=["bar_open_epoch","orion","h1_alignment","ready","mode","orion_reason"]
        self.row={"bar_open_epoch":300,"orion":0.,"h1_alignment":None,"ready":False,
                  "mode":"FROZEN","orion_reason":"trend_warmup"}
        self.expected=self.root/"expected.csv";self.actual=self.root/"actual.csv"
        write_csv(self.expected,self.columns,[self.row])

    def tearDown(self):self.temp.cleanup()

    def compare(self,rows):
        write_csv(self.actual,self.columns,rows)
        return compare_tables(self.expected,self.actual,self.columns,"bar_open_epoch")

    def test_missing_context_alignment_is_distinct_from_valid_zero(self):
        value=self.compare([{**self.row,"h1_alignment":0}])
        self.assertFalse(value["pass"])
        self.assertEqual(value["first_mismatches"][0]["field"],"h1_alignment")
        self.assertTrue(self.compare([self.row])["pass"])

    def test_zero_score_is_not_numeric_missing(self):
        self.assertFalse(self.compare([{**self.row,"orion":None}])["pass"])

    def test_float_tolerance_does_not_relax_flags_or_reasons(self):
        self.assertTrue(self.compare([{**self.row,"orion":1e-8}])["pass"])
        self.assertFalse(self.compare([{**self.row,"orion":1e-5}])["pass"])
        self.assertFalse(self.compare([{**self.row,"ready":True}])["pass"])
        self.assertFalse(self.compare([{**self.row,"orion_reason":"different_reason"}])["pass"])

    def test_duplicate_missing_and_out_of_order_rows_fail(self):
        with self.assertRaisesRegex(ComparisonError,"duplicate"):
            self.compare([self.row,self.row])
        self.assertFalse(self.compare([])["pass"])
        second={**self.row,"bar_open_epoch":600}
        write_csv(self.expected,self.columns,[self.row,second])
        self.assertFalse(self.compare([second,self.row])["pass"])

    def test_nonfinite_literals_and_nonbinary_flags_are_rejected(self):
        self.compare([self.row])
        for column,value in (("orion","NaN"),("orion","Infinity"),("ready","2"),("ready","true")):
            row={k:str(v) if v is not None else "" for k,v in self.row.items()}
            row["ready"]="0";row[column]=value
            with self.actual.open("w",newline="") as f:
                writer=csv.DictWriter(f,fieldnames=self.columns);writer.writeheader();writer.writerow(row)
            with self.assertRaises(ComparisonError):
                compare_tables(self.expected,self.actual,self.columns,"bar_open_epoch")

    def test_schema_and_short_record_rejected(self):
        self.actual.write_text("bar_open_epoch,orion\n300,0\n")
        with self.assertRaisesRegex(ComparisonError,"schema"):
            compare_tables(self.expected,self.actual,self.columns,"bar_open_epoch")
        self.actual.write_text(",".join(self.columns)+"\n300,0\n")
        with self.assertRaisesRegex(ComparisonError,"width"):
            compare_tables(self.expected,self.actual,self.columns,"bar_open_epoch")


class FixtureIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name)
        cls.fixtures=cls.root/"fixtures"
        cls.manifest=generate(cls.fixtures)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def fake_native(self,directory):
        """Deliberately fake test output: validates comparator, not MQL parity."""
        directory.mkdir()
        names=list(self.manifest["cases"])
        for name in names:
            shutil.copyfile(self.fixtures/f"expected_{name}_signals.csv",directory/f"{name}_signals.csv")
        shutil.copyfile(self.fixtures/"expected_mode_results.csv",directory/"mode_results.csv")
        fields={"schema":"vortex.native.parity-result.v1","fixture_kind":KIND,"harness_version":"VORTEX-NATIVE-PARITY-0.1",
                "core_version":"v0.2-parity-1","status":"COMPUTED_FOR_COMPARISON","cases_requested":len(names),
                "cases_completed":len(names),"signal_rows":sum(v["counts"]["M5"] for v in self.manifest["cases"].values()),
                "mode_cases":self.manifest["mode_case_count"],"mode_results":self.manifest["mode_case_count"],
                "error":"","parity_evaluated":"false","strategy_approval":"false"}
        write_csv(directory/"manifest.csv",["key","value"],({"key":k,"value":v} for k,v in fields.items()))
        return fields

    def test_deterministic_market_inputs_and_mode_direction_coverage(self):
        self.assertTrue(fine_bars().equals(fine_bars()))
        results={r["case_id"]:mode_from_scores(r,r["h1_alignment"],r["h4_alignment"],r["session_ideal"],r["eligible"])
                 for r in mode_cases()}
        for side,label in ((1,"long"),(-1,"short")):
            for mode in ("NORMAL","AGGRESSIVE","EXTREME"):
                self.assertEqual(results[label+"_"+mode.lower()],(mode,side))
        self.assertEqual(results["kira_85_0"],("FROZEN",0))
        self.assertEqual(results["atlas_missing"],("FROZEN",0))

    def test_actual_reference_fixture_coverage_without_profit_selection(self):
        cases=self.manifest["cases"]
        self.assertGreater(cases["trend_up"]["directions"].get("1",0),0)
        self.assertGreater(cases["trend_down"]["directions"].get("-1",0),0)
        self.assertEqual(cases["volatility"]["kira_values"],[20.,50.,75.,90.])
        self.assertEqual(cases["gaps"]["counts"]["H4"],239)
        self.assertEqual(cases["trend_up"]["counts"]["H4"],240)
        self.assertTrue(all(cases["gaps"]["stale_context_rows"][k]>0 for k in ("m15","h1","h4")))
        self.assertEqual(cases["missing_external"]["ready_rows"],0)
        self.assertTrue({"calendar_invalid","macro_invalid","session_invalid","execution_input_invalid","news_blocked","spread_blocked"}
                        .issubset(cases["external_edges"]["reasons"]["atlas_reason"]))

    def test_full_schema_comparison_and_manifest_reject_incomplete_native_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            actual=Path(temporary)/"fake_native";fields=self.fake_native(actual)
            self.assertEqual(compare_directory(self.fixtures,actual)["status"],"PARITY_PASS")
            for key,value in (("status","FAILED"),("cases_completed",0),("signal_rows",0),("parity_evaluated","true"),
                              ("core_version","wrong_version")):
                modified={**fields,key:value}
                write_csv(actual/"manifest.csv",["key","value"],({"key":k,"value":v} for k,v in modified.items()))
                with self.assertRaises(ComparisonError):compare_directory(self.fixtures,actual)
            (actual/"manifest.csv").unlink()
            with self.assertRaises(OSError):compare_directory(self.fixtures,actual)

    def test_reference_hash_tampering_detected_before_comparison(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied=Path(temporary)/"copied";shutil.copytree(self.fixtures,copied)
            with (copied/"trend_up_M5.csv").open("a") as f:f.write("\n")
            with self.assertRaisesRegex(ComparisonError,"digest"):
                compare_directory(copied,Path(temporary)/"absent")

    def test_manifest_cannot_omit_an_expected_output_from_digest_coverage(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied=Path(temporary)/"copied";shutil.copytree(self.fixtures,copied)
            path=copied/"python_reference_manifest.json"
            manifest=json.loads(path.read_text())
            manifest["files"].pop("expected_trend_up_signals.csv")
            path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ComparisonError,"cover every"):
                compare_directory(copied,Path(temporary)/"absent")

    def test_large_fixture_cannot_be_written_inside_repository(self):
        from parity_fixtures import REPO
        with self.assertRaisesRegex(ValueError,"outside repository"):
            generate(REPO/"native_mt5"/"generated-fixtures")


if __name__=="__main__":unittest.main()
