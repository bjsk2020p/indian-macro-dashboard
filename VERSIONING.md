# Versioning

## Version source

- `VERSION` (project root) is the **only** authoritative version. It contains either
  `MAJOR.MINOR.PATCH` or the word `unversioned`.
- Current status: **1.2.0**, released 2026-11-18 (snapshot `Releases/v1.2.0/`, hashes in `CHANGELOG.md`).
  Earlier: 1.1.0 (2026-11-18) and 1.0.0 (2026-11-17).
- Legacy labels are **not** version sources. The `_v5` in `india_macro_dashboard_v5.html`, the
  page title `India + US Macro Dashboard v3`, and the inline "v2" comments predate this scheme
  and disagree with each other. The active file keeps its path so existing links and launch
  habits keep working. Edits are now made in place, replacing the old practice of saving a new
  `_vN+1.html` file.

## When a version changes

Versions change **only when the user explicitly asks** for a new version or release, or names a
number. Routine edits, including the regular baseline-data refreshes, never bump `VERSION`,
never create a snapshot, and never create a tag. They are recorded under `## [Unreleased]` in
`CHANGELOG.md`.

If a release is requested without a number, infer the increment from the Unreleased changes and
state the reason:

- **PATCH**: baseline data refreshes, fixes, data-source corrections, copy or style tweaks with
  no new capability.
- **MINOR**: new backward-compatible capability (new indicator, chart, control, data source).
- **MAJOR**: removed features, a changed entry-point path, or anything that breaks how the
  dashboard is opened or used.

If the release scope or compatibility is unclear, ask. The first release defaults to `1.0.0`
unless the user specifies another number.

## Release procedure (only on explicit request)

1. Confirm that `VERSION` and `CHANGELOG.md` agree. Choose the new version and confirm that
   `Releases/v<X.Y.Z>/` does not exist yet. If it does, stop: never overwrite a release.
2. Write the version to `VERSION`.
3. In `CHANGELOG.md`, move the Unreleased items into `## [X.Y.Z] - YYYY-MM-DD`, note the
   increment type, and leave an empty `## [Unreleased]` section.
4. Copy, unchanged, into `Releases/v<X.Y.Z>/` at the same relative paths:
   `india_macro_dashboard_v5.html`, `refresh_data.py`, `server.py`, `launcher.py`,
   `Open_Indian_Macro_Dashboard.cmd`, `refresh_data.bat`, and `data/macro_snapshot.js` (the data
   as released; libraries load from CDN). From 1.1.0, also copy the hosting files:
   `manifest.webmanifest`, `icons/*.png`, `ci_site.py`, `ci_report.py`,
   `.github/workflows/pages.yml` and `.github/workflows/source-check.yml`. Do not copy
   `data/server.log`. Record the SHA-256 of each copied file in the changelog entry.
5. Run `python -m unittest discover tests`, then open the snapshot's HTML directly (saved data)
   and confirm it loads. The active dashboard must still open via the launcher.
6. Every release includes publication to the mobile site. The release request authorises a
   release commit and a normal push to `origin/main`. Include the version change, active
   dashboard and its dependencies, release notes and immutable snapshot in the release commit.
   Keep unrelated working-tree changes out. Tags require a separate explicit request.
7. Pushing a change to the root `VERSION` on `main` starts `.github/workflows/pages.yml`.
   Follow the run for that commit through the deploy job. If publication needs a retry,
   rerun the workflow for the release commit. Keep the existing version and snapshot.
8. Before reporting completion, open the [mobile dashboard](https://bjsk2020p.github.io/indian-macro-dashboard/)
   at phone width and verify the released feature. Compare the served root HTML's SHA-256
   with the HTML digest in the release changelog. Allow for CDN propagation and recheck
   the ordinary URL. The hosted data snapshot has its own three-hour refresh cycle and can
   be newer than the archived data. Report the version, live link and verification result.

Snapshots in `Releases/` are immutable.

## Archive structure

```
archive/
  html-dashboards/            legacy (pre-versioning) superseded dashboards
    MANIFEST.md               original path → archived path, date, version, reason
    <YYYY-MM-DD_HHMMSS>/      one batch folder per archival run; original relative paths kept
Releases/
  v<X.Y.Z>/                   immutable release snapshots (created only on explicit release)
```

Archiving rules:

- Move only confirmed superseded dashboards, never the active entry point or its dependencies.
- Keep their filenames and relative paths, and copy any local assets they need into the batch.
- Verify SHA-256 before and after the move.
- Never delete and never overwrite.
- Add every move to `MANIFEST.md`.
- Archiving never creates a release.

## Restoring

- **An archived legacy dashboard:** find its row in `archive/html-dashboards/MANIFEST.md`.
  Copy (don't move) the archived file back to its original path, or to a new name if that path
  is in use. Check its SHA-256 against the manifest, then open it in a browser.
- **A released version:** stop the dashboard server (close it via Task Manager → `pythonw`
  running `server.py`, or wait for its 12-hour idle exit), preserve the current files, then copy
  the release's HTML and Python/launcher files back over them. Keep the current
  `data/macro_snapshot.js` unless you want the released data; the updater refreshes it anyway. Once commits or tags exist, you can
  also use `git show v<X.Y.Z>:india_macro_dashboard_v5.html > restored.html`.
- Restoring old code does not change `VERSION`. Record the restore under Unreleased, and
  release it only when asked.
