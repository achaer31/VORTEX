"""Synthetic audits exercise actual grouping and malformed input failure modes."""
import csv
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from vortex_xau.audit import HEADERS, TIME_BASIS, audit_export


def row(time, timeframe="M5", opening="2000.000", high="2001.000", low="1999.000",
        close="2000.500", volume=10, real_volume=2):
    return [time.isoformat(timespec="seconds"), TIME_BASIS, "XAUUSD", timeframe,
            opening, high, low, close, str(volume), "100", str(real_volume)]


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.start = datetime(2026, 1, 5, 12)

    def write(self, timeframe, rows):
        with (self.path / f"XAUUSD_{timeframe}.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(HEADERS)
            writer.writerows(rows)

    def fixture(self, m5=None, m15=None, h1=None):
        self.write("M5", m5 if m5 is not None else [row(self.start + timedelta(minutes=5*i)) for i in range(12)])
        self.write("M15", m15 if m15 is not None else [row(self.start + timedelta(minutes=15*i), "M15", volume=30, real_volume=6) for i in range(4)])
        self.write("H1", h1 if h1 is not None else [row(self.start, "H1", volume=120, real_volume=24)])
        with (self.path / "manifest.csv").open("w", newline="", encoding="utf-8") as handle:
            csv.writer(handle).writerows([
                ["scope", "key", "value", "status"],
                ["export", "symbol", "XAUUSD", "ok"],
                ["export", "timezone", TIME_BASIS, "unknown_offset_and_dst"],
                ["export", "run_status", "started", "ok"],
                ["M5", "actual_count", "12", "ok"],
                ["M5", "copy_rates_return", "13", "ok"],
                ["export", "run_status", "finished", "ok"],
            ])

    def test_complete_groups_exactly_match_and_manifest_last_wins(self):
        self.fixture()
        report = audit_export(self.path)
        self.assertTrue(report["structural_ok"])
        self.assertEqual(report["aggregates"]["M15"]["matching_groups"], 4)
        self.assertEqual(report["aggregates"]["H1"]["matching_groups"], 1)
        self.assertEqual(report["manifest"]["values"]["export"]["run_status"], "finished")
        self.assertEqual(report["manifest"]["duplicate_keys"], 1)
        self.assertEqual(report["files"]["M5"]["manifest_check"]["copy_rates_return"], "13")
        self.assertTrue(report["files"]["M5"]["manifest_check"]["matches"])
        self.assertEqual(report["csv_sha256"]["XAUUSD_M5.csv"], hashlib.sha256((self.path / "XAUUSD_M5.csv").read_bytes()).hexdigest())
        json.dumps(report)

    def test_missing_bar_skips_only_incomplete_groups_without_structural_failure(self):
        self.fixture(m5=[row(self.start + timedelta(minutes=5*i)) for i in range(12) if i != 1])
        report = audit_export(self.path)
        self.assertTrue(report["structural_ok"])
        self.assertEqual(report["files"]["M5"]["observed_gaps"], 1)
        self.assertEqual(report["aggregates"]["M15"]["full_groups"], 3)
        self.assertEqual(report["aggregates"]["M15"]["skipped_incomplete"], 1)
        self.assertEqual(report["aggregates"]["H1"]["full_groups"], 0)
        self.assertEqual(report["aggregates"]["H1"]["skipped_incomplete"], 1)

    def test_valid_wrong_higher_timeframe_prices_are_review_findings(self):
        self.fixture(h1=[row(self.start, "H1", high="2001.001", volume=121, real_volume=25)])
        report = audit_export(self.path)
        self.assertTrue(report["structural_ok"])
        result = report["aggregates"]["H1"]
        self.assertEqual(result["mismatching_groups"], 1)
        self.assertEqual(result["mismatches_by_field"]["high"], 1)
        self.assertEqual(result["mismatches_by_field"]["tick_volume"], 1)
        self.assertEqual(result["mismatches_by_field"]["real_volume"], 1)
        self.assertTrue(result["review_required"])

    def test_impossible_ohlc_is_structural_failure(self):
        rows = [row(self.start + timedelta(minutes=5*i)) for i in range(12)]
        rows[0][5] = "1998.000"  # high below low and both open/close
        self.fixture(m5=rows)
        report = audit_export(self.path)
        self.assertFalse(report["structural_ok"])
        self.assertEqual(report["files"]["M5"]["bad_rows"], 1)
        self.assertEqual(report["files"]["M5"]["structural_errors"]["invalid_ohlc"], 1)
        self.assertEqual(report["aggregates"]["H1"]["status"], "skipped_due_to_structural_errors")

    def test_no_invented_bars_or_sessions_across_weekend_gap(self):
        starts = [self.start, self.start + timedelta(days=3)]
        self.fixture(m5=[row(start + timedelta(minutes=5*i)) for start in starts for i in range(12)],
                     m15=[row(start + timedelta(minutes=15*i), "M15", volume=30, real_volume=6) for start in starts for i in range(4)],
                     h1=[row(start, "H1", volume=120, real_volume=24) for start in starts])
        report = audit_export(self.path)
        self.assertTrue(report["structural_ok"])
        result = report["aggregates"]["H1"]
        self.assertEqual(result["observed_groups"], 2)
        self.assertEqual(result["full_groups"], 2)
        self.assertEqual(result["skipped_incomplete"], 0)
        self.assertEqual(result["missing_htf"], 0)

    def test_complete_group_missing_higher_bar_is_counted(self):
        self.fixture(m15=[row(self.start + timedelta(minutes=15*i), "M15", volume=30, real_volume=6) for i in range(1, 4)])
        report = audit_export(self.path)
        self.assertTrue(report["structural_ok"])
        self.assertEqual(report["aggregates"]["M15"]["missing_htf"], 1)
        self.assertEqual(report["aggregates"]["M15"]["compared_groups"], 3)

    def test_duplicate_bad_volume_and_wrong_time_basis_fail(self):
        rows = [row(self.start + timedelta(minutes=5*i)) for i in range(12)]
        rows[1][0] = rows[0][0]
        rows[2][8] = "-1"
        rows[3][1] = "UTC"
        self.fixture(m5=rows)
        report = audit_export(self.path)
        self.assertFalse(report["structural_ok"])
        errors = report["files"]["M5"]["structural_errors"]
        self.assertEqual(errors["duplicate_timestamp"], 1)
        self.assertEqual(errors["nonascending_timestamp"], 1)
        self.assertEqual(errors["invalid_tick_volume"], 1)
        self.assertEqual(errors["invalid_time_basis"], 1)

    def test_off_grid_price_rejected_instead_of_rounded(self):
        rows = [row(self.start + timedelta(minutes=5*i)) for i in range(12)]
        rows[0][4] = "2000.0001"
        self.fixture(m5=rows)
        report = audit_export(self.path)
        self.assertFalse(report["structural_ok"])
        self.assertEqual(report["files"]["M5"]["structural_errors"]["invalid_open"], 1)

    def test_misaligned_group_rejected_instead_of_sliding_window(self):
        self.fixture(m5=[row(self.start + timedelta(minutes=1 + 5*i)) for i in range(12)])
        report = audit_export(self.path)
        self.assertFalse(report["structural_ok"])
        self.assertEqual(report["files"]["M5"]["structural_errors"]["unaligned_timestamp"], 12)


if __name__ == "__main__":
    unittest.main()
