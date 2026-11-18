# Changelog

All notable changes to the India + US Macro Dashboard. The version source is `VERSION`; see
`VERSIONING.md`. Releases are created only on explicit request.

Earlier history (the `_v1`–`_v5` filename iterations) predates this changelog and is not
reconstructed here.

## [Unreleased]

## [1.0.0] - 2026-11-17

Initial release (first assigned version, requested as 1.0.0). Snapshot: `Releases/v1.0.0/`.
Released data: `data/macro_snapshot.js` as refreshed 2026-11-17 15:49 UTC (13/13 sources OK).

SHA-256 of the released files:

| File | SHA-256 |
|---|---|
| `india_macro_dashboard_v5.html` | `6fa2e163a7ee8c640a35cecd4b79e9c04ab30928a4ac6a1370e8222fc2612085` |
| `refresh_data.py` | `6a80119da5632c53994174a127729f26938448c0904ce6bad92e6e95ec5918a4` |
| `server.py` | `19a542c27693f650e402518b6db58663dd90f3bd0298f9cfe798fcb55345002b` |
| `launcher.py` | `406792d43bfac29e938d77ec589a3d471df346c03781706f01f9c2c038ed2b4f` |
| `Open_Indian_Macro_Dashboard.cmd` | `269fec87273d190dab5bb311488a24c793a94094c00a5902d91169ffd1f4217a` |
| `refresh_data.bat` | `a741f8c7beaaa152704c3e3c9e56f693883ac40d022ae67471d85792b072ff59` |
| `data/macro_snapshot.js` | `e2a429f97143d7a2b86b645aca14aa51b9a7e814e04c0f40313293f3c6358059` |

### Added

- **One-click launcher with automatic updates.** `Open_Indian_Macro_Dashboard.cmd` → `launcher.py`
  starts (or reuses) a local server (`server.py`, 127.0.0.1, ports 8817–8826) and opens the
  browser. Every page open or reload refreshes due sources; the Refresh button re-checks all.
  Works from any folder and from paths with spaces, never stops unrelated processes on a busy
  port, explains missing Python, and exits after 12 idle hours.
- **Automated India data from official sources:** MoSPI CPI (base 2012 to Dec 2025, base 2024
  from Jan 2026), MoSPI quarterly real GDP (base 2022-23, older quarters base 2011-12), and the
  RBI's current policy rates. Also ECB reference rates (USD/INR, DXY estimate) and World Bank
  annual cross-checks, saved server-side for offline reopening.
- `data/macro_snapshot.js`: one validated, atomically written snapshot for all sources, with
  per-source reuse windows, publication-schedule staleness, revision/new-observation tracking,
  keep-last-good on failure, and corrupt-file quarantine. Migrates the earlier
  `data/fred_snapshot.js` automatically.
- Source & refresh status table: provider, link, newest observation, last success and attempt,
  what this page load did (fetched / reused / failed and why), units, transform and state.
- Provenance states LATEST, CACHED, SNAPSHOT, STALE, BASELINE, MANUAL, UNAVAILABLE.
- Early notice when the page is opened directly as a file, or when no server is detected.
- Score coverage: inputs that are not current are shown as excluded; a score is withheld with
  fewer than 3 of 5 current inputs. Weights unchanged.
- Tests: 44 fixture tests covering parsers, validation, reuse rules, partial failure and recovery,
  corrupt cache, server request guards and launcher port handling (`python -m unittest discover tests`).
- Versioning scheme: `VERSION` (currently `unversioned`), `VERSIONING.md`, this changelog,
  `archive/html-dashboards/` with a manifest, and a local Git repository with `.gitignore`.
  No dashboards needed archiving.

### Changed

- US CPI, Core PCE, NFP, 10Y real yield and Brent are fetched server-side from FRED. The public
  CORS proxies (allorigins, corsproxy, codetabs) and the ForexFactory fetch were removed: the
  proxies failed (401/522/timeout) and ForexFactory refuses automated clients (403). Consensus
  forecasts remain manual.
- Brent now comes from FRED MCOILBRENTEU (EIA spot, monthly average) instead of the World Bank
  GEM endpoint, which returned "Invalid value". Basis differs slightly from the Pink Sheet
  baseline (Q1 2026: 80.2 vs 80.5).
- The time axis extends automatically to the latest quarter with official data (now Q3 2026).
  Series without verified data there stay blank (repo after Q1 2026, GDP for Jul–Sep 2026).
- Card labels now state the basis: CPI card = latest monthly YoY (quarterly average in the
  subtitle); GDP = real constant-price YoY with its fiscal quarter; USD/INR = ECB reference rate,
  not a live quote; Brent = monthly average, not a current price; DXY = estimate from ECB rates.
- Rate changes are shown in percentage points (pp).
- `refresh_data.bat` now refreshes every source and opens the dashboard through the launcher.
- The World Bank cross-check no longer changes a card's state; it is shown beside the source.

### Fixed

- A chart-library (CDN) failure left every India card blank, the badge on "Fetching…" and the
  Refresh button permanently disabled. Render steps are now isolated.
- Embedded data was presented as current although months old: repo 5.25% (RBI now publishes
  5.50%), CPI Q4 2025 1.8% (official 0.76%), CPI Q1 2026 1.6% (official base-2024 3.12%),
  GDP ended at Jan–Mar 2026 (official data now through Apr–Jun 2026, 7.8%).
- The World Bank GDP cross-check always failed in the browser (CORS); it now runs server-side.
- Past "upcoming" releases (June/July 2026) were still drawn as upcoming, and the Impact
  Tracker and scores used June surprises as if current. Expired rows are hidden; stale surprise
  inputs are excluded and labelled.
- Missing surprise inputs defaulted to 0; they are now treated as missing.
- A single 7-day staleness rule applied to every series; each source now uses its own
  publication schedule.
- On Windows, Python's `http.server` let two servers bind the same port; the server now
  requires exclusive use of its port.
- Monthly YoY used an array offset, so a month missing at source (Oct-2025 CPI) produced a
  13-month change labelled as YoY. Now matched by calendar month; NFP differences only
  consecutive months.
