"""Fixture tests for the data pipeline (no network). Run from the project root:
    python -m unittest discover tests
"""
import datetime as dt
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import refresh_data as rd  # noqa: E402

NOW = dt.datetime(2026, 11, 15, 12, 0, tzinfo=dt.timezone.utc)
GOOD = "observation_date,DFII10\n2026-11-10,2.78\n2026-11-11,\n2026-11-12,2.86\n"


# ─── FRED ──────────────────────────────────────────────────────────────────────
class FredParseTests(unittest.TestCase):
    def test_valid_with_missing_marker(self):
        obs, missing = rd.parse_fred_csv(GOOD, "DFII10")
        self.assertEqual(obs, [["2026-11-10", 2.78], ["2026-11-12", 2.86]])
        self.assertEqual(missing, 1)

    def test_dot_missing_marker_and_legacy_header(self):
        obs, missing = rd.parse_fred_csv("DATE,X\n2026-01-01,.\n2026-02-01,1.5\n", "X")
        self.assertEqual((obs, missing), ([["2026-02-01", 1.5]], 1))

    def test_zero_and_negative_kept(self):
        obs, _ = rd.parse_fred_csv("observation_date,X\n2026-01-01,0\n2026-02-01,-0.25\n", "X")
        self.assertEqual([v for _, v in obs], [0.0, -0.25])

    def test_rejects(self):
        bad = {
            "html": "<html>blocked</html>", "empty": "",
            "wrong series": "observation_date,OTHER\n2026-01-01,1\n",
            "duplicate": "observation_date,X\n2026-01-01,1\n2026-01-01,2\n",
            "out of order": "observation_date,X\n2026-02-01,1\n2026-01-01,2\n",
            "bad date": "observation_date,X\n2026-02-30,1\n",
            "non-numeric": "observation_date,X\n2026-01-01,abc\n",
            "extra field": "observation_date,X\n2026-01-01,1,2\n",
            "infinite": "observation_date,X\n2026-01-01,inf\n",
        }
        for name, text in bad.items():
            with self.subTest(name), self.assertRaises(ValueError):
                rd.parse_fred_csv(text, "X")

    def test_min_obs(self):
        with self.assertRaises(ValueError):
            rd.parse_fred_csv(GOOD, "DFII10", min_obs=3)


# ─── MoSPI CPI ─────────────────────────────────────────────────────────────────
def cpi24_row(y, month, idx, yoy, **over):
    r = {"base_year": "2024", "series": "Current", "year": str(y), "month": month, "state": "All India",
         "sector": "Combined", "division": "CPI (General)", "group": None, "index": str(idx),
         "inflation": None if yoy is None else str(yoy)}
    r.update(over)
    return r


class MospiCpiTests(unittest.TestCase):
    def test_parse_and_null_yoy_kept_as_none(self):
        obs = rd.parse_mospi_cpi({"data": [cpi24_row(2026, "October", 110.05, 6.09),
                                           cpi24_row(2025, "October", 103.74, None)]}, "2024")
        self.assertEqual(obs, [["2025-10-01", None, 103.74], ["2026-10-01", 6.09, 110.05]])

    def test_zero_inflation_is_valid(self):
        obs = rd.parse_mospi_cpi({"data": [cpi24_row(2026, "May", 101.0, "0.00")]}, "2024")
        self.assertEqual(obs[0][1], 0.0)

    def test_no_data_found_is_empty_not_error(self):
        self.assertEqual(rd.parse_mospi_cpi({"msg": "No Data Found", "statusCode": True}, "2024"), [])

    def test_rejects_wrong_series_identity(self):
        for over in ({"sector": "Rural"}, {"state": "Punjab"}, {"division": "Food and beverages"}, {"base_year": "2012"}):
            with self.subTest(over), self.assertRaises(ValueError):
                rd.parse_mospi_cpi({"data": [cpi24_row(2026, "May", 101, 1, **over)]}, "2024")

    def test_rejects_duplicate_month_bad_month_and_error_payload(self):
        with self.assertRaises(ValueError):
            rd.parse_mospi_cpi({"data": [cpi24_row(2026, "May", 101, 1), cpi24_row(2026, "May", 101, 1)]}, "2024")
        with self.assertRaises(ValueError):
            rd.parse_mospi_cpi({"data": [cpi24_row(2026, "Mayo", 101, 1)]}, "2024")
        with self.assertRaises(ValueError):
            rd.parse_mospi_cpi({"error": "Missing required parameters: Level"}, "2024")

    def test_base_2012_identity(self):
        row = {"baseyear": "2012", "year": 2025, "month": "December", "state": "All India", "sector": "Combined",
               "group": "General", "subgroup": "General-Overall", "index": "198.0", "inflation": "1.33"}
        self.assertEqual(rd.parse_mospi_cpi({"data": [row]}, "2012"), [["2025-12-01", 1.33, 198.0]])
        with self.assertRaises(ValueError):
            rd.parse_mospi_cpi({"data": [{**row, "group": "Housing"}]}, "2012")

    def test_consistency_check_catches_misparsed_table(self):
        good = [["2025-10-01", None, 103.74], ["2026-10-01", 6.09, 110.05]]
        self.assertLess(rd.check_cpi_consistency(good), 0.05)
        with self.assertRaises(ValueError):
            rd.check_cpi_consistency([["2025-10-01", None, 103.74], ["2026-10-01", 9.5, 110.05]])

    def test_fetcher_requests_each_year(self):
        seen = []

        def getter(url):
            seen.append(url)
            y = int(url.split("&year=")[1].split("&")[0])
            months = ["January", "February", "March", "April", "May", "June", "July", "August",
                      "September", "October", "November", "December"]
            # 2026 index = 1.05 × 2025 index, published YoY 5.00% (consistent with the index ratio)
            return json.dumps({"data": [cpi24_row(y, m, round((100 + i) * (1.05 if y == 2026 else 1), 4),
                                                  None if y == 2025 else 5.0) for i, m in enumerate(months)]})
        out = rd.mospi_cpi_fetcher("2024", 2025, 2026)(getter, NOW.date())
        self.assertEqual(len(seen), 2)
        self.assertEqual(len(out["observations"]), 24)
        self.assertEqual(out["meta"]["yoy_null_months"], 12)


# ─── MoSPI GDP ─────────────────────────────────────────────────────────────────
def gdp_row(fy, q, real, nominal=None, **over):
    r = {"base_year": "2022-23", "series": "Current", "year": fy, "indicator": "Gross Domestic Product",
         "frequency": "Quarterly", "revision": None, "quarter": q, "current_price": str(nominal or real * 1.1),
         "constant_price": str(real), "unit": "₹ Crore"}
    r.update(over)
    return r


class MospiGdpTests(unittest.TestCase):
    def test_fiscal_to_calendar_quarter_mapping(self):
        self.assertEqual(rd.fiscal_quarter_start("2026-27", "Q1"), "2026-04-01")   # Apr-Jun -> calendar Q2
        self.assertEqual(rd.fiscal_quarter_start("2025-26", "Q3"), "2025-10-01")
        self.assertEqual(rd.fiscal_quarter_start("2025-26", "Q4"), "2026-01-01")   # Jan-Mar of next calendar year
        with self.assertRaises(ValueError):
            rd.fiscal_quarter_start("2025-27", "Q1")                              # inconsistent FY label
        with self.assertRaises(ValueError):
            rd.fiscal_quarter_start("2025-26", "Q5")

    def _payload(self, rows, pages=1):
        return {"data": rows, "meta_data": {"totalPages": pages}}

    def _quarters(self, n=8):
        out, fy = [], 2022
        for i in range(n):
            q = f"Q{i % 4 + 1}"
            if i and i % 4 == 0:
                fy += 1
            out.append(gdp_row(f"{fy}-{str(fy + 1)[2:]}", q, 1000 + i))
        return out

    def test_parse_skips_annual_rows_and_sorts(self):
        rows = self._quarters() + [{**gdp_row("2025-26", None, 999), "frequency": "Annual"}]
        obs = rd.parse_mospi_gdp(self._payload(list(reversed(rows))), "2022-23")
        self.assertEqual(obs[0][0], "2022-04-01")
        self.assertEqual(len(obs), 8)

    def test_rejects_pagination_duplicates_units(self):
        with self.assertRaises(ValueError):
            rd.parse_mospi_gdp(self._payload(self._quarters(), pages=2), "2022-23")
        with self.assertRaises(ValueError):
            rd.parse_mospi_gdp(self._payload(self._quarters() + [self._quarters()[0]]), "2022-23")
        bad = self._quarters()
        bad[3] = {**bad[3], "unit": "₹ Lakh"}
        with self.assertRaises(ValueError):
            rd.parse_mospi_gdp(self._payload(bad), "2022-23")
        bad = self._quarters()
        bad[3] = {**bad[3], "constant_price": "-5"}
        with self.assertRaises(ValueError):
            rd.parse_mospi_gdp(self._payload(bad), "2022-23")


# ─── RBI / FX / World Bank ─────────────────────────────────────────────────────
RBI_PAGE = ("<div>1. Current Rates</div><div>Policy Rates</div><table><tr><td>Policy Repo Rate</td><td>: 5.50%</td></tr>"
            "<tr><td>Standing Deposit Facility Rate</td><td>: 5.25%</td></tr><tr><td>Marginal Standing Facility Rate</td>"
            "<td>: 5.75%</td></tr><tr><td>Bank Rate</td><td>: 5.75%</td></tr></table>")


class RbiFxWbTests(unittest.TestCase):
    def test_rbi_parse(self):
        self.assertEqual(rd.parse_rbi_rates(RBI_PAGE), {"repo": 5.5, "sdf": 5.25, "msf": 5.75, "bank_rate": 5.75})

    def test_rbi_format_change_fails_visibly(self):
        for page in ("<html>maintenance</html>", RBI_PAGE.replace("5.50%", "5.50 per cent"),
                     RBI_PAGE.replace("5.25%", "5.60%")):            # corridor SDF > repo
            with self.subTest(page[:40]), self.assertRaises(ValueError):
                rd.parse_rbi_rates(page)

    def test_frankfurter(self):
        rates = {f"2026-01-{d:02d}": {s: 1.0 + d / 100 for s in rd.FX_SYMBOLS} for d in range(1, 31)}
        rates.update({f"2026-02-{d:02d}": {s: 2.0 for s in rd.FX_SYMBOLS} for d in range(1, 29)})
        obs = rd.parse_frankfurter({"base": "USD", "rates": rates})
        self.assertEqual(len(obs[0]), 1 + len(rd.FX_SYMBOLS))
        with self.assertRaises(ValueError):
            rd.parse_frankfurter({"base": "EUR", "rates": rates})
        bad = {**rates, "2026-03-01": {**rates["2026-01-01"], "INR": 0}}
        with self.assertRaises(ValueError):
            rd.parse_frankfurter({"base": "USD", "rates": bad})

    def test_worldbank_null_skipped_and_counted(self):
        rows = [{"indicator": {"id": "X"}, "country": {"id": "IN"}, "date": str(y), "value": (None if y == 2025 else 1.0 * y % 7)}
                for y in range(2019, 2026)]
        obs, missing = rd.parse_worldbank([{"page": 1}, rows], "X")
        self.assertEqual((missing, obs[-1][0]), (1, "2024-01-01"))
        with self.assertRaises(ValueError):
            rd.parse_worldbank([{"page": 1}, [{**rows[0], "country": {"id": "US"}}]], "X")


# ─── HTTP retry policy ─────────────────────────────────────────────────────────
class HttpGetTests(unittest.TestCase):
    def setUp(self):
        self._urlopen, self._sleep = rd.urllib.request.urlopen, rd.time.sleep
        rd.time.sleep = lambda s: None
        self.calls = 0

    def tearDown(self):
        rd.urllib.request.urlopen, rd.time.sleep = self._urlopen, self._sleep

    def test_connection_reset_retried_then_reported(self):
        def reset(req, timeout):
            self.calls += 1
            raise ConnectionResetError(10054, "forcibly closed")
        rd.urllib.request.urlopen = reset
        with self.assertRaises(rd.FetchError) as cm:
            rd.http_get("https://example.invalid")
        self.assertEqual((cm.exception.kind, self.calls), ("network", rd.ATTEMPTS))

    def test_404_not_retried(self):
        def nf(req, timeout):
            self.calls += 1
            raise rd.urllib.error.HTTPError(req.full_url, 404, "nf", {}, None)
        rd.urllib.request.urlopen = nf
        with self.assertRaises(rd.FetchError) as cm:
            rd.http_get("https://example.invalid")
        self.assertEqual((cm.exception.kind, self.calls), ("http", 1))

    def test_no_custom_user_agent(self):
        seen = {}

        def capture(req, timeout):
            seen.update(dict(req.header_items()))
            raise rd.urllib.error.HTTPError(req.full_url, 404, "nf", {}, None)
        rd.urllib.request.urlopen = capture
        with self.assertRaises(rd.FetchError):
            rd.http_get("https://example.invalid")
        self.assertNotIn("User-agent", seen)


# ─── Reuse window / freshness ──────────────────────────────────────────────────
class DueTests(unittest.TestCase):
    SPEC = {"recheck_minutes": 60}

    def entry(self, minutes_ago, status="ok"):
        t = (NOW - dt.timedelta(minutes=minutes_ago)).isoformat().replace("+00:00", "Z")
        return {"observations": [["2026-01-01", 1.0]], "last_attempt_at": t, "status": status}

    def test_rules(self):
        cases = [(None, False, True), (self.entry(10), False, False), (self.entry(61), False, True),
                 (self.entry(10), True, True), (self.entry(0.2), True, False),           # 30 s floor
                 (self.entry(3, "failed_kept_previous"), False, False),
                 (self.entry(6, "failed_kept_previous"), False, True)]
        for prev, force, expect in cases:
            with self.subTest(prev=prev and prev["last_attempt_at"], force=force):
                self.assertEqual(rd.is_due(prev, self.SPEC, NOW, force)[0], expect)

    def test_compare_observations(self):
        old = [["2026-01-01", 1.0], ["2026-02-01", 2.0]]
        new = [["2026-01-01", 1.0], ["2026-02-01", 2.5], ["2026-03-01", 3.0]]
        self.assertEqual(rd.compare_observations(old, new), (1, 1))    # 1 new month, 1 revision
        self.assertEqual(rd.compare_observations([], new), (3, 0))


# ─── End-to-end refresh against a temp snapshot (fake providers) ──────────────
class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "data", "macro_snapshot.js")
        self._sources = rd.SOURCES
        mk = lambda sid: {**self._sources[sid]}   # noqa: E731
        rd.SOURCES = {"FRED:DFII10": mk("FRED:DFII10"), "RBI:POLICY_RATES": mk("RBI:POLICY_RATES")}
        self.fail = set()

    def tearDown(self):
        rd.SOURCES = self._sources
        self.tmp.cleanup()

    def getter(self, url):
        if "fred" in url:
            if "fred" in self.fail:
                raise rd.FetchError("http", "HTTP 503")
            return "observation_date,DFII10\n" + "".join(f"2026-10-{d:02d},{2 + d / 100}\n" for d in range(1, 21))
        if "rbi" in url:
            if "rbi" in self.fail:
                return "<html>changed layout</html>"
            return RBI_PAGE
        raise AssertionError(url)

    def run_refresh(self, force=True, now=NOW):
        return rd.refresh(force=force, getter=self.getter, path=self.path, now=now, max_workers=2)

    def test_empty_cache_first_run_then_partial_failure_and_recovery(self):
        out = self.run_refresh()
        self.assertEqual({r["action"] for r in out["run"]["results"]}, {"checked"})
        self.fail = {"fred"}
        out = self.run_refresh(now=NOW + dt.timedelta(minutes=1))
        res = {r["id"]: r for r in out["run"]["results"]}
        self.assertEqual(res["FRED:DFII10"]["action"], "failed")
        fred = out["snapshot"]["sources"]["FRED:DFII10"]
        self.assertEqual(fred["status"], "failed_kept_previous")
        self.assertEqual(len(fred["observations"]), 20)                   # last good data kept
        self.assertEqual(fred["last_success_at"], "2026-11-15T12:00:00Z")  # not relabelled as fresh
        self.assertEqual(out["snapshot"]["sources"]["RBI:POLICY_RATES"]["status"], "ok")   # other source unaffected
        self.fail = set()
        out = self.run_refresh(now=NOW + dt.timedelta(minutes=10))
        self.assertEqual(out["snapshot"]["sources"]["FRED:DFII10"]["status"], "ok")

    def test_validation_failure_is_reported_not_saved(self):
        self.run_refresh()
        self.fail = {"rbi"}
        out = self.run_refresh(now=NOW + dt.timedelta(minutes=1))
        r = {x["id"]: x for x in out["run"]["results"]}["RBI:POLICY_RATES"]
        self.assertEqual(r["error"]["kind"], "validation")
        self.assertEqual(out["snapshot"]["sources"]["RBI:POLICY_RATES"]["observations"][-1][1], 5.5)

    def test_reuse_window_skips_provider(self):
        self.run_refresh()
        calls = []
        out = rd.refresh(force=False, getter=lambda u: calls.append(u), path=self.path,
                         now=NOW + dt.timedelta(minutes=5))
        self.assertEqual(calls, [])
        self.assertEqual({r["action"] for r in out["run"]["results"]}, {"reused"})

    def test_current_level_history_records_since_when(self):
        self.run_refresh()
        out = self.run_refresh(now=NOW + dt.timedelta(days=1))
        obs = out["snapshot"]["sources"]["RBI:POLICY_RATES"]["observations"]
        self.assertEqual([o[0] for o in obs], ["2026-11-15", "2026-11-16"])

    def test_corrupt_cache_moved_aside_and_rebuilt(self):
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(rd.JS_PREFIX + "{broken")
        out = self.run_refresh()
        self.assertTrue(any("unreadable" in p for p in out["run"]["problems"]))
        self.assertTrue(any(n.startswith("macro_snapshot.corrupt-") for n in os.listdir(os.path.dirname(self.path))))
        self.assertEqual(rd.read_snapshot(self.path)[1], [])               # new file is valid

    def test_invalid_saved_entry_dropped_others_kept(self):
        self.run_refresh()
        src, _ = rd.read_snapshot(self.path)
        src["FRED:DFII10"]["observations"].append(["2026-10-01", 9.9])    # duplicate/out-of-order
        rd.write_snapshot(src, "x", self.path)
        good, problems = rd.read_snapshot(self.path)
        self.assertNotIn("FRED:DFII10", good)
        self.assertIn("RBI:POLICY_RATES", good)
        self.assertTrue(problems)

    def test_merge_keeps_sources_written_by_another_writer(self):
        self.run_refresh()
        src, _ = rd.read_snapshot(self.path)
        other = dict(src["FRED:DFII10"], observations=[["2026-10-01", 1.0]])
        rd.SOURCES["FRED:EXTRA"] = {**rd.SOURCES["FRED:DFII10"]}
        src["FRED:EXTRA"] = other
        rd.write_snapshot(src, "x", self.path)
        out = rd.refresh(force=True, only=["RBI:POLICY_RATES"], getter=self.getter, path=self.path,
                         now=NOW + dt.timedelta(minutes=2))
        self.assertIn("FRED:EXTRA", out["snapshot"]["sources"])
        self.assertFalse([n for n in os.listdir(os.path.dirname(self.path)) if n.endswith(".tmp")])

    def test_adapter_crash_isolated(self):
        rd.SOURCES["FRED:DFII10"] = {**rd.SOURCES["FRED:DFII10"], "fetch": lambda g, d: 1 / 0}
        out = self.run_refresh()
        r = {x["id"]: x for x in out["run"]["results"]}
        self.assertEqual(r["FRED:DFII10"]["error"]["kind"], "internal")
        self.assertEqual(r["RBI:POLICY_RATES"]["action"], "checked")

    def test_slow_source_reported_pending_then_saved_without_duplicate_fetch(self):
        import threading
        release, calls = threading.Event(), []

        def getter(url):
            if "rbi" in url:
                calls.append(url)
                release.wait(5)              # slow provider
                return RBI_PAGE
            return self.getter(url)
        out = rd.refresh(force=True, getter=getter, path=self.path, now=NOW, wait_seconds=0.3)
        r = {x["id"]: x["action"] for x in out["run"]["results"]}
        self.assertEqual(r, {"FRED:DFII10": "checked", "RBI:POLICY_RATES": "pending"})
        self.assertIn("FRED:DFII10", rd.read_snapshot(self.path)[0])       # fast result saved now
        again = rd.refresh(force=True, getter=getter, path=self.path, now=NOW + dt.timedelta(minutes=1), wait_seconds=0.3)
        self.assertEqual({x["id"]: x["action"] for x in again["run"]["results"]}["RBI:POLICY_RATES"], "pending")
        self.assertEqual(len(calls), 1)                                     # in-flight fetch not duplicated
        release.set()
        for _ in range(50):                                                 # background result lands in the file
            if "RBI:POLICY_RATES" in rd.read_snapshot(self.path)[0]:
                break
            import time
            time.sleep(0.1)
        saved = rd.read_snapshot(self.path)[0]
        self.assertEqual(saved["RBI:POLICY_RATES"]["observations"][-1][1], 5.5)
        self.assertIn("FRED:DFII10", saved)                                 # late write kept the other source

    def test_legacy_fred_snapshot_migrates(self):
        legacy = os.path.join(self.tmp.name, "fred.js")
        with open(legacy, "w", encoding="utf-8") as f:
            f.write(rd.LEGACY_JS_PREFIX + json.dumps({"series": {"DFII10": {
                "observations": [["2026-10-01", 2.0]], "retrieved_at": "2026-11-01T00:00:00Z", "last_obs": "2026-10-01"}}}))
        got = rd.read_legacy_fred(legacy)
        self.assertEqual(got["FRED:DFII10"]["observations"], [["2026-10-01", 2.0]])


if __name__ == "__main__":
    unittest.main()
