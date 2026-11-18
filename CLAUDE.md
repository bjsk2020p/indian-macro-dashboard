# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An India + US macro dashboard: one HTML page plus a small Python standard-library updater.

| File | Role |
|---|---|
| `india_macro_dashboard_v5.html` | The dashboard (HTML, CSS, JS in one file; ~2850 lines). Active entry point; keep this name. |
| `refresh_data.py` | **The only data pipeline**: source adapters, validation, reuse windows, atomic snapshot writes. CLI: `python refresh_data.py [--due]`. |
| `server.py` | Local server on 127.0.0.1. Serves the page + snapshot, and refreshes on every page open/reload by calling `refresh_data.refresh()`. |
| `launcher.py` | Starts or reuses the server (ports 8817–8826), waits for readiness, opens the browser. |
| `Open_Indian_Macro_Dashboard.cmd` | What the user double-clicks. Runs `launcher.py` with `pyw`/`pythonw` (no console). |
| `refresh_data.bat` | Compatible entry point: visible full refresh via `refresh_data.py`, then opens the dashboard via the `.cmd`. |
| `data/macro_snapshot.js` | Saved, validated data (`window.MACRO_SNAPSHOT`). Generated; never edit by hand. `data/server.log` is the server log. |
| `tests/` | `python -m unittest discover tests` — fixture-based, no network (pipeline, server, launcher). |

No build system or package manager; Python 3.9+ standard library only. Chart.js 4.4.2 (+ date-fns adapter, annotation plugin) and Google Fonts load from CDN; a CDN failure only removes charts (cards, badges, status table still render).

The version lives in `VERSION` (see "Versioning and archives"). The `_v5` in the filename and the v2/v3 in the `<title>`/comments are legacy labels. Edit the HTML in place; do not save a new `_vN+1.html`.

### Running it
- **Normal use:** double-click `Open_Indian_Macro_Dashboard.cmd`. Works from any folder; reuses a running instance; never stops unrelated processes on a busy port (moves to the next port). Server exits after 12 idle hours.
- **Direct `file://` open:** shows saved data with an early notice that automatic updates need the launcher. A web page cannot start Python. ECB rates are fetched directly by the browser in this mode (CORS-enabled).
- **Tests / headless:** `MACRO_DASHBOARD_NO_BROWSER=1 python launcher.py` prints the URL instead of opening a tab.

## Core architecture: saved-first, then refresh

1. The page paints embedded baseline + validated saved data (`data/macro_snapshot.js`) immediately.
2. On every load/reload it calls `POST /api/refresh` (header `X-Dashboard: 1`). The server refreshes **due** sources only — each source has a reuse window (`recheck_minutes` in `refresh_data.SOURCES`); a failed source is retried after 5 min. The Refresh button sends `force=1` (re-checks everything not checked in the last 30 s).
3. The page re-renders from the returned snapshot. Every render step runs inside `guard()`; charts go through `chartOrNotice()`. Never let a chart/CDN error block cards, badges or the Refresh button (this was a real defect).

Provenance states (`PROV` in the page; per card, tag, footer badge and status-table row):
- `latest` — the provider was checked this load (or within its reuse window) and this is its newest observation.
- `cached` — saved data shown because this load's check failed.
- `snapshot` — saved data, not re-checked (file:// or no server).
- `stale` — a newer release is overdue per that source's schedule (`max_obs_age_days`; `max_check_age_days` for current-level sources). No universal threshold.
- `baseline` — embedded data. `manual` — hand-maintained. `unavailable` — no usable data.

"Checked" ≠ "new data": the status table shows last success, last attempt, when the newest observation arrived, and whether this load fetched new/revised points. The header badge counts per-card states; it is green only if all five are `latest` ("Bug 1 fix" — never revert to a single success flag). A World Bank cross-check never changes a card's state.

No localStorage. Saved state lives only in `data/macro_snapshot.js`.

## Data sources (all automated ones go through `refresh_data.SOURCES`)

| Card / series | Source (adapter id) | Notes |
|---|---|---|
| Repo card | RBI home page "Current Rates" (`RBI:POLICY_RATES`) | HTML parse, validated (SDF < repo < MSF). Current level only — **no effective date** on the page. Keeps a short history of readings ("unchanged since"). |
| Repo chart | `FALLBACK.repo` — **manual** | Quarter-end levels from verified MPC decisions. Quarters after the last verified decision are `null`. |
| CPI card + chart | MoSPI eSankhyiki API: base 2024 (`MOSPI:CPI_2024`, `cpi/getCPIData`, `state_code=1&sector_code=3&division_code=0`) and base 2012 (`MOSPI:CPI_2012`, `cpi/getCPIIndex`, `state_code=99&sector_code=3&group_code=0`) | All-India Combined General. Card = latest **monthly** YoY as published. Chart = mean of 3 monthly YoY prints, complete quarters only. Base 2012 to Dec 2025, base 2024 from Jan 2026 (growth rates, not spliced levels). Published YoY is cross-checked against the index ratio (≤0.5 pp). |
| GDP card + chart | MoSPI NAS API (`MOSPI:GDP_2022_23`, `MOSPI:GDP_2011_12`; `nas/getNASData`, `indicator_code=5`, `limit` ≤ 200) | Real (constant-price) YoY vs same fiscal quarter a year earlier. Fiscal Q1 (Apr–Jun) → calendar Q2. 2022-23 base where both quarters exist, else 2011-12. Latest revised estimates, not first prints. |
| USD/INR, DXY | ECB reference rates via Frankfurter (`ECB:FX`) | Daily reference rate (≈16:00 CET), **not a live quote**. DXY is an **estimate** (ICE weights on ECB rates), not the traded index. |
| Brent | FRED `MCOILBRENTEU` | EIA spot **monthly average**, not a current price. Quarter = mean of 3 complete months. |
| US CPI, Core PCE, NFP, real yield | FRED `CPIAUCNS`, `PCEPILFE`, `PAYEMS`, `DFII10` | YoY matched by calendar month (`usYoY`); NFP = consecutive-month differences only (thousands). Oct-2025 CPI was never published → Oct-2026 YoY shown n/a. |
| Cross-checks | World Bank `FP.CPI.TOTL.ZG`, `NY.GDP.MKTP.KD.ZG` | Display only (CPI vs calendar-year average of the chart; GDP vs India fiscal-year average). ⚠ when > 0.8 pp apart. |
| US consensus / surprises | `US_RELEASES`, `US_UPCOMING` — **manual** | ForexFactory refuses automated clients (403, rate-limited). Do not disguise the client or add CORS proxies to get around it. |

Pipeline rules: validate every response (identity, dates, ordering, duplicates, units, numbers); missing stays missing, valid zero is kept, nothing is interpolated; a failed source keeps its last good data (`failed_kept_previous`); writes are atomic and merge per source; a corrupt snapshot is moved aside (`*.corrupt-*.js`), never deleted. Do **not** set a custom User-Agent in urllib: FRED stalls on custom UAs while the default `Python-urllib/3.x` works (tested 2026-11-15). Add a source by adding an adapter + an entry in `SOURCES` (with `recheck_minutes`, `max_obs_age_days`, units, transform text) and a fixture test.

Server safety: binds 127.0.0.1 only with exclusive port use (`SO_EXCLUSIVEADDRUSE`; plain `http.server` lets two servers share a port on Windows), rejects foreign `Host` headers, requires `X-Dashboard: 1` on refresh, never approves CORS preflights, serves only allow-listed files.

## Two domains in one page

1. **India** (top): unprefixed functions — `assembleIndiaData`, `extendAxis`, `applyFx`, `applyBrent`, `applyCrossChecks`, `buildChart`, `updateStatCards`, `updateSourceBadges`, `renderStatusTable`, `loadAllData`.
2. **US spillover** (bottom): everything prefixed `us`/`US_` — `usLoadFromSnapshot`, `usSnapshot`, `usInputCurrency`, `usScore`, `usRenderAll`, etc.

## Methodology invariants — do not break these

- **No annual-to-quarterly scaling or interpolation anywhere.** Gaps stay `null`.
- **Time axis**: `BASE_QUARTERS`/`BASE_QUARTER_ENDS` are the embedded axis; `extendAxis()` extends the live `QUARTERS`/`QUARTER_ENDS` to the latest quarter with complete official CPI or official GDP data. `FALLBACK` arrays are padded with `null`; series without data there stay blank.
- Changes in rates display in **pp**.
- **WB conventions**: CPI annual ≈ calendar year; GDP annual = India fiscal year (Apr–Mar, labelled by starting year). Preserve `avgCY`/`avgFY`.
- Do not present stale or manual inputs as current: a surprise counts in scores only if its reference month equals the latest published FRED actual (`usInputCurrency`). Excluded inputs are shown as excluded chips (never as 0); a score is withheld below `US_MIN_SCORE_INPUTS` (3 of 5). The Impact Tracker is withheld when the surprise log is not current. Do not change `US_SCORE_WEIGHTS` as part of data fixes.

## Manual maintenance (what is still hand-updated)

Read the comment blocks at the top of the India and US script sections before editing data arrays.
- `FALLBACK.repo` — append the quarter-end level once each MPC decision is verified (the card already reads the current rate).
- `US_RELEASES` / `US_UPCOMING` — actual + consensus for each CPI/NFP/PCE release; this re-enables surprise inputs and the Impact Tracker. `US_UPCOMING` rows with past dates and no actual are hidden.
- `FALLBACK.cpi/gdp/usdinr/brent`, `US_FALLBACK`, `US_MONTHLY` are now **offline baselines only** (shown when no saved data exists); refreshing them is optional.

## Versioning and archives

This project overrides the global executable policy for HTML releases (there are no `.exe` files). Full rules are in `VERSIONING.md`.

- `VERSION` is the single version source (`MAJOR.MINOR.PATCH` or `unversioned`; currently `1.0.0`, released 2026-11-17 — snapshot in `Releases/v1.0.0/`).
- Bump `VERSION`, create `Releases/v<X.Y.Z>/` snapshots, or create git tags **only when the user explicitly asks** for a release or names a version. Routine edits, including data refreshes, go under `## [Unreleased]` in `CHANGELOG.md`.
- On a release request without a number, infer PATCH/MINOR/MAJOR from the Unreleased changes and state why. Ask if the scope is unclear. Never overwrite an existing `Releases/` snapshot.
- Superseded dashboards go to `archive/html-dashboards/<YYYY-MM-DD_HHMMSS>/`. Move them (never delete or overwrite), verify their hashes, and log them in `MANIFEST.md`. Never archive the active entry point or its dependencies. Archiving is not a release.
- Git: no commits, tags or pushes unless the user asks. **Exception (authorised 2026-11-18, hosting work only):** the repo may have a GitHub remote, and commits/pushes needed to run and deploy the GitHub Actions workflows for phone hosting are allowed. Never force-push; never rewrite published history; tags still need an explicit request.

## GitHub Actions (authorised 2026-11-18)

- `refresh_data.py` may run inside GitHub Actions and its snapshot may be published to a static site (GitHub Pages). All pipeline rules still apply there: no CORS proxies, no custom User-Agent, no disguised clients, never publish an empty or invalid snapshot.
- `.github/workflows/source-check.yml` — manual trigger only; runs `python refresh_data.py` on GitHub's servers and prints a per-source table (`ci_report.py`). It never commits or deploys.
