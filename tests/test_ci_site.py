"""ci_site.py (Pages merge base + site assembly) and the Pages workflow schedule. No network."""
import os
import re
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import ci_site  # noqa: E402
import refresh_data as rd  # noqa: E402


def entry(attempt, obs=(("2026-10-01", 1.0),), status="ok"):
    return {"status": status, "observations": [list(o) for o in obs], "fields": ["date", "value"],
            "last_obs": obs[-1][0] if obs else None, "last_attempt_at": attempt, "last_success_at": attempt}


class MergeTests(unittest.TestCase):
    def test_newer_attempt_wins_per_source(self):
        pub = {"A": entry("2026-11-18T03:00:00Z"), "B": entry("2026-11-17T00:00:00Z")}
        repo = {"B": entry("2026-11-18T01:00:00Z"), "C": entry("2026-11-01T00:00:00Z")}
        merged, picked = ci_site.merge(pub, repo)
        self.assertEqual(picked, {"A": "published", "B": "repository", "C": "repository"})
        self.assertIs(merged["B"], repo["B"])

    def test_seed_ignores_corrupt_download(self):
        with tempfile.TemporaryDirectory() as d:
            target, bad = os.path.join(d, "snap.js"), os.path.join(d, "dl.js")
            rd.write_snapshot({"A": entry("2026-11-01T00:00:00Z")}, "2026-11-01T00:00:00Z", target)
            with open(bad, "w", encoding="utf-8") as f:
                f.write("<html>404</html>")
            self.assertEqual(ci_site.seed(bad, target), 0)
            sources, problems = rd.read_snapshot(target)
            self.assertEqual(list(sources), ["A"])
            self.assertEqual(problems, [])
            self.assertTrue(os.path.exists(bad))          # inputs are never moved or deleted

    def test_seed_prefers_newer_published(self):
        with tempfile.TemporaryDirectory() as d:
            target, dl = os.path.join(d, "snap.js"), os.path.join(d, "dl.js")
            rd.write_snapshot({"A": entry("2026-11-01T00:00:00Z")}, "t", target)
            rd.write_snapshot({"A": entry("2026-11-18T00:00:00Z", (("2026-11-01", 2.0),))}, "t", dl)
            ci_site.seed(dl, target)
            self.assertEqual(rd.read_snapshot(target)[0]["A"]["last_obs"], "2026-11-01")


class BuildTests(unittest.TestCase):
    def make_root(self, d, snapshot_text=None, sources=None):
        for src in set(ci_site.SITE_FILES.values()):
            os.makedirs(os.path.join(d, os.path.dirname(src)) or d, exist_ok=True)
            shutil.copyfile(os.path.join(ROOT, src), os.path.join(d, src))
        snap = os.path.join(d, "data", "macro_snapshot.js")
        os.makedirs(os.path.dirname(snap), exist_ok=True)
        if snapshot_text is not None:
            with open(snap, "w", encoding="utf-8") as f:
                f.write(snapshot_text)
        else:
            rd.write_snapshot(sources, "2026-11-18T03:17:00Z", snap)
        # files that must never be published
        for junk in ("tests/x.py", "archive/old.html", "Releases/v1.0.0/a.html", "data/server.log", ".remember/now.md"):
            os.makedirs(os.path.join(d, os.path.dirname(junk)), exist_ok=True)
            open(os.path.join(d, junk), "w").close()

    def site_files(self, site):
        return sorted(os.path.relpath(os.path.join(r, f), site).replace(os.sep, "/")
                      for r, _, fs in os.walk(site) for f in fs)

    def test_build_allow_list_only(self):
        with tempfile.TemporaryDirectory() as d:
            self.make_root(d, sources={sid: entry("2026-11-18T03:17:00Z") for sid in rd.SOURCES})
            site = os.path.join(d, "_site")
            self.assertEqual(ci_site.build(site, root=d), 0)
            self.assertEqual(self.site_files(site), sorted(list(ci_site.SITE_FILES) + ["data/macro_snapshot.js"]))
            with open(os.path.join(site, "index.html"), "rb") as a, open(os.path.join(ROOT, ci_site.PAGE), "rb") as b:
                self.assertEqual(a.read(), b.read())

    def test_build_refuses_corrupt_or_empty(self):
        for name, text, sources in (("corrupt", "window.MACRO_SNAPSHOT = {not json", None),
                                    ("empty", None, {}),
                                    ("no observations", None, {"FRED:DFII10": entry("2026-11-18T00:00:00Z", obs=())})):
            with self.subTest(name), tempfile.TemporaryDirectory() as d:
                self.make_root(d, snapshot_text=text, sources=sources)
                site = os.path.join(d, "_site")
                self.assertEqual(ci_site.build(site, root=d), 1)
                self.assertFalse(os.path.exists(site))


class WorkflowScheduleTests(unittest.TestCase):
    def test_cron_matches_page_constant(self):
        with open(os.path.join(ROOT, ".github", "workflows", "pages.yml"), encoding="utf-8") as f:
            wf = f.read()
        with open(os.path.join(ROOT, ci_site.PAGE), encoding="utf-8") as f:
            page = f.read()
        cron = re.search(r'cron:\s*"(\S+) (\S+) \* \* \*"', wf)
        self.assertIsNotNone(cron, "pages.yml must have one cron line")
        minute, hours = cron.groups()
        self.assertNotEqual(minute, "0", "run off the hour")
        every_h = int(re.fullmatch(r"\*/(\d+)", hours).group(1))
        const = int(re.search(r"const HOSTED_SCHEDULE_MINUTES = (\d+);", page).group(1))
        self.assertEqual(every_h * 60, const)
        self.assertIn("workflow_dispatch", wf)
        self.assertNotRegex(wf, r"git (commit|push)")


if __name__ == "__main__":
    unittest.main()
