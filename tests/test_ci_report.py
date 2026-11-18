"""ci_report.py: per-source table used by the GitHub Actions workflows (no network)."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ci_report  # noqa: E402
import refresh_data as rd  # noqa: E402


class CiReportTests(unittest.TestCase):
    def test_rows_ok_failed_missing(self):
        ok = {"status": "ok", "observations": [["2026-11-13", 2.9]], "fields": ["date", "value"], "last_obs": "2026-11-13"}
        failed = {"status": "failed_kept_previous", "observations": [["2026-11-17", 5.5, 5.25, 5.75, 5.75]],
                  "fields": ["date", "repo", "sdf", "msf", "bank_rate"], "last_obs": "2026-11-17",
                  "last_error": {"kind": "http", "detail": "http: HTTP 403"}}
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "snap.js")
            rd.write_snapshot({"FRED:DFII10": ok, "RBI:POLICY_RATES": failed}, "t", path)
            table, problems = ci_report.rows(path)
        by = {r[0]: r for r in table}
        self.assertEqual(by["FRED:DFII10"][1:], ("ok", "-", "-", "2026-11-13"))
        self.assertEqual(by["RBI:POLICY_RATES"][1:], ("failed", "http", "http: HTTP 403", "2026-11-17"))
        self.assertEqual(by["MOSPI:CPI_2024"][1], "missing")
        self.assertEqual(len(table), len(rd.SOURCES))
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
