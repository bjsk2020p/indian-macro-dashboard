# Changelog

All notable changes to the India + US Macro Dashboard. The version source is `VERSION`; see
`VERSIONING.md`. Releases are created only on explicit request.

Earlier history (the `_v1`–`_v5` filename iterations) predates this changelog and is not
reconstructed here.

## [Unreleased]

- Mobile publication is now part of every release. A version change pushed to `main` triggers GitHub Pages immediately. Release verification includes the public dashboard at phone width and its HTML checksum.

## [1.2.0] - 2026-11-18

MINOR release for the new three-tab dashboard guide. Snapshot in `Releases/v1.2.0/`.

- Added Overview, Help & Parameters and References & Links at the foot of the dashboard. The guide explains card and chart periods, compares asset score weights from the model, and links readings to their sources. The live source-status table stays available on every tab.
- Matched the guide to the BTC dashboard’s light theme and orange tab underline. Each parameter now has a definition and asset- or sector-specific bullish and bearish interpretations, including how US release surprises affect the scores.

### Released file hashes

| File | SHA-256 |
|---|---|
| `india_macro_dashboard_v5.html` | `4094eff02aba7c285ff74a09581db55376b80bfb02c59e0dc18e2b0d1dec2cbd` |
| `refresh_data.py` | `6a80119da5632c53994174a127729f26938448c0904ce6bad92e6e95ec5918a4` |
| `server.py` | `19a542c27693f650e402518b6db58663dd90f3bd0298f9cfe798fcb55345002b` |
| `launcher.py` | `406792d43bfac29e938d77ec589a3d471df346c03781706f01f9c2c038ed2b4f` |
| `Open_Indian_Macro_Dashboard.cmd` | `269fec87273d190dab5bb311488a24c793a94094c00a5902d91169ffd1f4217a` |
| `refresh_data.bat` | `a741f8c7beaaa152704c3e3c9e56f693883ac40d022ae67471d85792b072ff59` |
| `data/macro_snapshot.js` | `20c08f4c2cbd1b61c6edd0e3ce963e421ee57e9561cf36d3d8d8b1f7942e6b2e` |
| `manifest.webmanifest` | `94750a7b8bbb31ea233b6c56f627183ca6d9ec2088c84a9ce004fdb4f0b05e1b` |
| `icons/icon-180.png` | `d15c6eef7eaaf25a0d70792381085682f695d9761d815fc57429717fbb907a1a` |
| `icons/icon-192.png` | `3d9bacdaf753d596a7b3b7449655ee19382b4587ce5f7a20e9d6d9f07995535b` |
| `icons/icon-512.png` | `665f2c9d2f05c125fa5b0f75ebb4fe42fbdab138c98aaad7b5901ca13b93c199` |
| `ci_site.py` | `105c21add43fa645cd00d6a97190145a61002e6317e9995c2d9acae6a8a57374` |
| `ci_report.py` | `382a0f373c2fd34d214c24a4a60ddea43ee8f434256f46ddcdd0c18e023529b6` |
| `.github/workflows/pages.yml` | `8c460c67438cfd39f80486e92a6f877e6b8be462c108432b73b3c44279c2d057` |
| `.github/workflows/source-check.yml` | `1929979546dc8a665be6ed77ac7cd0d93ea86a94f89ac15dbd9e39febd090afc` |

## [1.1.0] - 2026-11-18

MINOR release: new backward-compatible capability (phone viewing via GitHub Pages, phone layout,
home-screen install). Desktop use (launcher, `file://`) is unchanged. Snapshot: `Releases/v1.1.0/`.
Released data: `data/macro_snapshot.js` as refreshed 2026-11-18 03:25 UTC (13/13 sources OK).
Live site: https://bjsk2020p.github.io/indian-macro-dashboard/

SHA-256 of the released files:

| File | SHA-256 |
|---|---|
| `india_macro_dashboard_v5.html` | `b202bcb876f8492a481148b8a3eadeda0862368415b9308fd8480a6a443b6d10` |
| `refresh_data.py` | `6a80119da5632c53994174a127729f26938448c0904ce6bad92e6e95ec5918a4` |
| `server.py` | `19a542c27693f650e402518b6db58663dd90f3bd0298f9cfe798fcb55345002b` |
| `launcher.py` | `406792d43bfac29e938d77ec589a3d471df346c03781706f01f9c2c038ed2b4f` |
| `Open_Indian_Macro_Dashboard.cmd` | `269fec87273d190dab5bb311488a24c793a94094c00a5902d91169ffd1f4217a` |
| `refresh_data.bat` | `a741f8c7beaaa152704c3e3c9e56f693883ac40d022ae67471d85792b072ff59` |
| `data/macro_snapshot.js` | `20c08f4c2cbd1b61c6edd0e3ce963e421ee57e9561cf36d3d8d8b1f7942e6b2e` |
| `manifest.webmanifest` | `94750a7b8bbb31ea233b6c56f627183ca6d9ec2088c84a9ce004fdb4f0b05e1b` |
| `icons/icon-180.png` | `d15c6eef7eaaf25a0d70792381085682f695d9761d815fc57429717fbb907a1a` |
| `icons/icon-192.png` | `3d9bacdaf753d596a7b3b7449655ee19382b4587ce5f7a20e9d6d9f07995535b` |
| `icons/icon-512.png` | `665f2c9d2f05c125fa5b0f75ebb4fe42fbdab138c98aaad7b5901ca13b93c199` |
| `ci_site.py` | `105c21add43fa645cd00d6a97190145a61002e6317e9995c2d9acae6a8a57374` |
| `ci_report.py` | `382a0f373c2fd34d214c24a4a60ddea43ee8f434256f46ddcdd0c18e023529b6` |
| `.github/workflows/pages.yml` | `8c460c67438cfd39f80486e92a6f877e6b8be462c108432b73b3c44279c2d057` |
| `.github/workflows/source-check.yml` | `1929979546dc8a665be6ed77ac7cd0d93ea86a94f89ac15dbd9e39febd090afc` |

### Added

- **Phone viewing with the PC off.** `.github/workflows/pages.yml` runs every 3 hours (:17 UTC)
  and on demand. It refreshes due sources on GitHub's servers with `refresh_data.py --due`,
  using the published snapshot as the merge base, and deploys to GitHub Pages. It never commits
  data. An empty or corrupt snapshot fails the run and is never published, so the previous site
  stays up. Only an allow-list of 7 files is published (`ci_site.py`).
- **Hosted mode in the page** (https on any host other than this PC). It makes no `/api` calls,
  re-reads the published snapshot without cache, and fetches ECB rates directly. A source shows
  LATEST only if the scheduled job's last success is within its reuse window + 3 h schedule +
  1 h slack, and CACHED if the job's latest check of it failed. The notice reads "Data checked by
  scheduled job at …".
- **Phone layout** (≤480 px): one column, tap targets ≥44 px, shorter charts, the header no
  longer pinned, and the status table scrolling inside its own box. No sideways scrolling at
  360 px. The desktop and tablet layout is unchanged.
- **Add to Home screen**: a PWA manifest and icons (`tools/make_icons.py`), loaded on the
  hosted site only. There is no service worker and no data caching.
- `.github/workflows/source-check.yml` (manual test that GitHub's servers can reach every
  source; all 13 can) and `ci_report.py` (per-source run summary).
- Tests: 60 in total (was 44). New: the hosted freshness rule and mode detection (run in
  Node), the phone assets, the Pages merge/build, and a check that the cron schedule matches
  the page's constant.

### Changed

- `CLAUDE.md` and `VERSIONING.md` record the authorised GitHub remote and Actions use, hosted
  mode, the workflow and schedule, and the hosting files that are now part of a release.

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
