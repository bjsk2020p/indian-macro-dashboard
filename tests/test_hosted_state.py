"""Hosted-mode rules in the page (detectRunMode, hostedFreshState), executed in Node.

The functions live between `// <hosted-state-rule>` markers in india_macro_dashboard_v5.html;
this test extracts that block verbatim, so it tests the shipped code. Skipped if Node.js is
not installed (no other dependency).
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(ROOT, "india_macro_dashboard_v5.html")
NODE = shutil.which("node")

NOW = "2026-11-18T06:00:00Z"
# Fixtures: (name, meta, minutes before NOW of last_success_at or None, expected state).
# Window = recheck_minutes + 180 (schedule) + 60 (slack).
STATE_CASES = [
    ("monthly source, just checked", {"status": "ok", "recheck_minutes": 180}, 10, "latest"),
    ("monthly source, at window edge (420 min)", {"status": "ok", "recheck_minutes": 180}, 420, "latest"),
    ("monthly source, 1 min past window", {"status": "ok", "recheck_minutes": 180}, 421, "snapshot"),
    ("daily source, 60-min recheck: 300 min old", {"status": "ok", "recheck_minutes": 60}, 300, "latest"),
    ("daily source, 60-min recheck: 301 min old", {"status": "ok", "recheck_minutes": 60}, 301, "snapshot"),
    ("weekly-recheck source: 2 days old is still in window", {"status": "ok", "recheck_minutes": 10080}, 2880, "latest"),
    ("job's latest check failed", {"status": "failed_kept_previous", "recheck_minutes": 180}, 10, "cached"),
    ("no successful check recorded", {"status": "ok", "recheck_minutes": 180}, None, "snapshot"),
    ("missing recheck_minutes uses schedule+slack only (240)", {"status": "ok"}, 241, "snapshot"),
]
MODE_CASES = [
    ({"protocol": "file:", "hostname": ""}, "file"),
    ({"protocol": "https:", "hostname": "bjsk2020p.github.io"}, "hosted"),
    ({"protocol": "https:", "hostname": "localhost"}, "local"),
    ({"protocol": "https:", "hostname": "127.0.0.1"}, "local"),
    ({"protocol": "http:", "hostname": "127.0.0.1"}, "local"),
    ({"protocol": "http:", "hostname": "example.org"}, "local"),     # hosted requires https
]


def rule_block() -> str:
    html = open(PAGE, encoding="utf-8").read()
    m = re.search(r"// <hosted-state-rule>[^\n]*\n(.*?)// </hosted-state-rule>", html, re.S)
    if not m:
        raise AssertionError("hosted-state-rule markers not found in the page")
    return m.group(1)


@unittest.skipUnless(NODE, "Node.js not installed")
class HostedStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        now_ms = "Date.parse(%s)" % json.dumps(NOW)
        cases = []
        for name, meta, mins, _ in STATE_CASES:
            m = dict(meta)
            if mins is not None:
                m["__ago"] = mins
            cases.append({"name": name, "meta": m})
        script = rule_block() + f"""
const NOW = {now_ms};
const cases = {json.dumps(cases)};
const out = {{ states: {{}}, modes: [] }};
for (const c of cases) {{
  const meta = Object.assign({{}}, c.meta);
  if (meta.__ago !== undefined) meta.last_success_at = new Date(NOW - meta.__ago * 60000).toISOString();
  delete meta.__ago;
  out.states[c.name] = hostedFreshState(meta, NOW);
}}
for (const loc of {json.dumps([c[0] for c in MODE_CASES])}) out.modes.push(detectRunMode(loc));
out.constants = [HOSTED_SCHEDULE_MINUTES, HOSTED_SLACK_MINUTES];
console.log(JSON.stringify(out));
"""
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
            f.write(script)
            path = f.name
        try:
            run = subprocess.run([NODE, path], capture_output=True, text=True, timeout=30)
        finally:
            os.unlink(path)
        if run.returncode != 0:
            raise AssertionError(run.stderr)
        cls.out = json.loads(run.stdout)

    def test_state_rule(self):
        for name, _, _, expected in STATE_CASES:
            with self.subTest(name):
                self.assertEqual(self.out["states"][name], expected)

    def test_mode_detection(self):
        for (loc, expected), got in zip(MODE_CASES, self.out["modes"]):
            with self.subTest(loc):
                self.assertEqual(got, expected)

    def test_schedule_constants(self):
        self.assertEqual(self.out["constants"], [180, 60])


if __name__ == "__main__":
    unittest.main()
