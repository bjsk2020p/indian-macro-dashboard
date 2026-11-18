"""Print a per-source result table for the snapshot that refresh_data.py just wrote.

Used by the GitHub Actions workflows. Prints a plain-text table to the log and, when
GITHUB_STEP_SUMMARY is set, appends a Markdown table to the run summary.

A source counts as "ok" only if its latest attempt succeeded (status == "ok").
Exit code is always 0; the workflow decides whether failures should fail the job.
Standard library only.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import refresh_data  # noqa: E402


def rows(path: str = refresh_data.OUT_PATH) -> tuple[list[tuple[str, str, str, str, str]], list[str]]:
    """[(source id, ok/failed/missing, error kind, error detail, newest observation)], problems."""
    sources, problems = refresh_data.read_snapshot(path)
    out = []
    for sid in refresh_data.SOURCES:
        e = sources.get(sid)
        if e is None:
            out.append((sid, "missing", "-", "no entry in snapshot", "-"))
            continue
        ok = e.get("status") == "ok"
        err = e.get("last_error") or {}
        out.append((sid, "ok" if ok else "failed", err.get("kind", "-") if not ok else "-",
                    (err.get("detail") or "-") if not ok else "-", e.get("last_obs") or "-"))
    return out, problems


def main() -> int:
    table, problems = rows()
    head = ("source id", "result", "error kind", "newest observation")
    widths = [max(len(head[i]), *(len(r[j]) for r in table)) for i, j in ((0, 0), (1, 1), (2, 2), (3, 4))]
    line = lambda c: "  ".join(str(v).ljust(w) for v, w in zip(c, widths))  # noqa: E731
    print(line(head))
    print(line(["-" * w for w in widths]))
    for r in table:
        print(line((r[0], r[1], r[2], r[4])))
    failed = [r for r in table if r[1] != "ok"]
    for r in failed:
        print(f"::warning title={r[0]} {r[1]}::{r[2]}: {r[3]}")
    for p in problems:
        print(f"::warning title=snapshot::{p}")
    print(f"\n{len(table) - len(failed)}/{len(table)} sources ok")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("### Source check from GitHub's servers\n\n| source id | result | error kind | error | newest observation |\n|---|---|---|---|---|\n")
            for r in table:
                f.write(f"| `{r[0]}` | {'✅ ok' if r[1] == 'ok' else '❌ ' + r[1]} | {r[2]} | {r[3].replace('|', '/')} | {r[4]} |\n")
            f.write(f"\n**{len(table) - len(failed)}/{len(table)} sources ok.**\n")
            for p in problems:
                f.write(f"\n- Snapshot problem: {p}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
