"""Data pipeline for the India + US Macro Dashboard.

One module does all retrieval, validation and saving. It is used by:
  - server.py   (the local dashboard server; refreshes on every page open/reload)
  - this file's CLI:  python refresh_data.py [--due]   (refresh_data.bat calls it)

Output: data/macro_snapshot.js  ->  window.MACRO_SNAPSHOT = {...}
A <script> file, so the dashboard can show saved data even when opened from disk.

Sources (all official or reference providers, no API keys, no CORS proxies):
  FRED      CPIAUCNS, PCEPILFE, PAYEMS, DFII10, MCOILBRENTEU  (graph CSV endpoint)
  MoSPI     CPI all-India Combined General index, base 2024 and base 2012 (eSankhyiki API)
            Quarterly GDP levels, base 2022-23 and base 2011-12          (eSankhyiki API)
  RBI       Current policy rates block on www.rbi.org.in (HTML, validated)
  ECB       Daily reference rates via Frankfurter (USD base)
  World Bank Annual CPI inflation and GDP growth for India (cross-check only)

Not automated, and why:
  - ForexFactory consensus calendar: answers 403 to non-browser clients and rate-limits;
    getting around that would mean disguising the client, so consensus stays manual.
  - RBI policy-decision dates: the RBI page shows the current rate, not its effective date.

Rules:
  - Every series is validated (dates, ordering, duplicates, units, numbers).
    A malformed or unexpected response raises and is reported; it never overwrites good data.
  - Missing observations stay missing. Valid zeros are kept. Nothing is interpolated.
  - A failed source keeps its last good data, marked failed_kept_previous with the error.
  - Writes are atomic and merge per source, so refreshing one source never erases another.
  - Each source has a reuse window (recheck_minutes): a request inside it reuses the
    last validated response instead of calling the provider again.

Standard library only.
"""
from __future__ import annotations

import argparse
import calendar
import concurrent.futures as cf
import datetime as dt
import html as htmllib
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
OUT_PATH = os.path.join(DATA_DIR, "macro_snapshot.js")
LEGACY_FRED_PATH = os.path.join(DATA_DIR, "fred_snapshot.js")
JS_PREFIX = "window.MACRO_SNAPSHOT = "
LEGACY_JS_PREFIX = "window.FRED_SNAPSHOT = "
SCHEMA_VERSION = 2
TIMEOUT_S = 25
ATTEMPTS = 3
FORCE_FLOOR_SECONDS = 30          # even a forced refresh reuses a check made this recently
FAILED_RETRY_MINUTES = 5          # a failed source is retried sooner than its reuse window
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MONTHS = {m: i for i, m in enumerate(calendar.month_name) if m}
# No custom User-Agent: FRED's edge stalls or resets custom UA strings from urllib, while
# the default "Python-urllib/3.x" is served normally (tested 2026-11-15). All other
# providers also accept the default client, so the client is never disguised.

_REFRESH_LOCK = threading.RLock()      # serialises snapshot read-merge-write (reentrant: see refresh())
_EXECUTOR = cf.ThreadPoolExecutor(max_workers=8, thread_name_prefix="refresh")
_IN_FLIGHT: dict[str, cf.Future] = {}   # source id -> running fetch (never fetched twice at once)
_IN_FLIGHT_LOCK = threading.Lock()


class FetchError(Exception):
    """A failed download. `kind` separates network/timeout/http failures from validation."""

    def __init__(self, kind: str, detail: str):
        super().__init__(f"{kind}: {detail}")
        self.kind = kind


# ─── HTTP ──────────────────────────────────────────────────────────────────────
def http_get(url: str) -> str:
    """GET with timeout and bounded retries. Retries network errors, 429 and 5xx only."""
    last: FetchError | None = None
    for attempt in range(1, ATTEMPTS + 1):
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                return resp.read().decode("utf-8-sig", errors="replace")
        except urllib.error.HTTPError as e:
            last = FetchError("http", f"HTTP {e.code}")
            if e.code != 429 and e.code < 500:
                raise last from None
        except urllib.error.URLError as e:
            last = FetchError("network", str(e.reason))
        except TimeoutError:
            last = FetchError("timeout", f"no response in {TIMEOUT_S}s")
        except OSError as e:  # connection reset/refused mid-request
            last = FetchError("network", f"{type(e).__name__}: {e}")
        if attempt < ATTEMPTS:
            time.sleep(2 * attempt)
    assert last is not None
    raise last


def get_json(url: str, getter) -> object:
    text = getter(url)
    if text.lstrip().startswith("<"):
        raise ValueError("response is HTML, not JSON (error or block page)")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid JSON: {e}") from None


def _num(raw, what: str, nullable: bool = False):
    if raw is None or (isinstance(raw, str) and raw.strip() in ("", "NA", "-")):
        if nullable:
            return None
        raise ValueError(f"{what}: missing value")
    if isinstance(raw, bool):
        raise ValueError(f"{what}: non-numeric value {raw!r}")
    try:
        v = float(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{what}: non-numeric value {raw!r}") from None
    if v != v or v in (float("inf"), float("-inf")):
        raise ValueError(f"{what}: non-finite value {raw!r}")
    return v


def check_series(obs: list[list], min_obs: int = 1) -> None:
    """Shared rule: ISO dates, strictly ascending (so no duplicates), at least min_obs rows."""
    prev = None
    for row in obs:
        d = row[0]
        if not isinstance(d, str) or not DATE_RE.match(d):
            raise ValueError(f"bad date {d!r}")
        dt.date.fromisoformat(d)
        if prev is not None and d <= prev:
            raise ValueError(f"date {d} is duplicate or out of order")
        prev = d
    if len(obs) < min_obs:
        raise ValueError(f"only {len(obs)} valid observations, need at least {min_obs}")


# ─── FRED ──────────────────────────────────────────────────────────────────────
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={id}&cosd={start}"


def parse_fred_csv(text: str, series_id: str, min_obs: int = 1) -> tuple[list[list], int]:
    """Validate a FRED graph CSV. Returns ([[date, value], ...], missing_count)."""
    if text.lstrip().startswith("<"):
        raise ValueError("response is HTML, not CSV (error page or proxy page)")
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    if not lines:
        raise ValueError("empty response")
    header = [h.strip() for h in lines[0].split(",")]
    if len(header) != 2 or header[0].lower() not in ("date", "observation_date") or header[1] != series_id:
        raise ValueError(f"unexpected header {lines[0]!r}")
    obs, missing, prev = [], 0, None
    for n, line in enumerate(lines[1:], start=2):
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 2:
            raise ValueError(f"line {n}: expected 2 fields, got {len(parts)}")
        date, raw = parts
        if not DATE_RE.match(date):
            raise ValueError(f"line {n}: bad date {date!r}")
        dt.date.fromisoformat(date)  # rejects impossible dates such as 2026-02-30
        if prev is not None and date <= prev:
            raise ValueError(f"line {n}: date {date} is duplicate or out of order")
        prev = date
        if raw in ("", "."):
            missing += 1
            continue
        obs.append([date, _num(raw, f"line {n}")])
    if len(obs) < min_obs:
        raise ValueError(f"only {len(obs)} valid observations, need at least {min_obs}")
    return obs, missing


def fred_fetcher(series_id: str, lookback_days: int | None = None, start: str | None = None, min_obs: int = 1):
    def fetch(getter, today: dt.date) -> dict:
        s = start or (today - dt.timedelta(days=lookback_days)).isoformat()
        url = FRED_CSV.format(id=series_id, start=s)
        obs, missing = parse_fred_csv(getter(url), series_id, min_obs)
        return {"observations": obs, "missing_skipped": missing, "request_url": url}
    return fetch


# ─── MoSPI CPI (eSankhyiki) ────────────────────────────────────────────────────
MOSPI = "https://api.mospi.gov.in/api/"
# base 2024: state_code=1 = All India, sector_code=3 = Combined, division_code=0 = CPI (General)
CPI2024_URL = MOSPI + "cpi/getCPIData?base_year=2024&series=Current&format=json&state_code=1&sector_code=3&division_code=0&year={y}&limit=20"
# base 2012: state_code=99 = All India, sector_code=3 = Combined, group_code=0 = General
CPI2012_URL = MOSPI + "cpi/getCPIIndex?base_year=2012&format=json&state_code=99&sector_code=3&group_code=0&year={y}&limit=20"


def _month_date(year, month_name: str) -> str:
    m = MONTHS.get(str(month_name).strip())
    if not m:
        raise ValueError(f"unknown month {month_name!r}")
    return f"{int(year):04d}-{m:02d}-01"


def parse_mospi_cpi(payload: object, base: str) -> list[list]:
    """Rows -> [[month_date, yoy_pct_or_None, index]]. Validates the exact series identity."""
    if not isinstance(payload, dict):
        raise ValueError("unexpected payload type")
    if payload.get("msg") == "No Data Found":
        return []
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise ValueError(f"no data array (msg={payload.get('msg')!r}, error={payload.get('error')!r})")
    out = {}
    for r in rows:
        if base == "2024":
            ident = (r.get("base_year"), r.get("state"), r.get("sector"), r.get("division"), r.get("group"))
            if ident != ("2024", "All India", "Combined", "CPI (General)", None):
                raise ValueError(f"unexpected CPI row identity {ident}")
        else:
            ident = (r.get("baseyear"), r.get("state"), r.get("sector"), r.get("group"), r.get("subgroup"))
            if ident != ("2012", "All India", "Combined", "General", "General-Overall"):
                raise ValueError(f"unexpected CPI row identity {ident}")
        d = _month_date(r.get("year"), r.get("month"))
        if d in out:
            raise ValueError(f"duplicate CPI month {d}")
        idx = _num(r.get("index"), f"CPI index {d}")
        if not 20 <= idx <= 1000:
            raise ValueError(f"CPI index {d} out of range: {idx}")
        yoy = _num(r.get("inflation"), f"CPI inflation {d}", nullable=True)
        if yoy is not None and not -30 <= yoy <= 60:
            raise ValueError(f"CPI inflation {d} out of range: {yoy}")
        out[d] = [d, yoy, idx]
    return [out[k] for k in sorted(out)]


def check_cpi_consistency(obs: list[list], tolerance_pp: float = 0.5) -> float:
    """Published YoY must agree with the index ratio (same month a year earlier) within tolerance.
    Catches a misparsed table. Returns the max absolute difference seen."""
    by = {o[0]: o for o in obs}
    worst = 0.0
    for d, yoy, idx in obs:
        prev = by.get(f"{int(d[:4]) - 1:04d}{d[4:]}")
        if yoy is None or prev is None:
            continue
        calc = (idx / prev[2] - 1) * 100
        worst = max(worst, abs(calc - yoy))
        if abs(calc - yoy) > tolerance_pp:
            raise ValueError(f"CPI {d}: published YoY {yoy} vs index ratio {calc:.2f} differ > {tolerance_pp}pp")
    return round(worst, 3)


def mospi_cpi_fetcher(base: str, first_year: int, last_year: int | None = None):
    def fetch(getter, today: dt.date) -> dict:
        y_end = last_year or today.year
        url_t = CPI2024_URL if base == "2024" else CPI2012_URL
        obs, urls = [], []
        for y in range(first_year, y_end + 1):
            url = url_t.format(y=y)
            urls.append(url)
            obs.extend(parse_mospi_cpi(get_json(url, getter), base))
        obs.sort(key=lambda o: o[0])
        check_series(obs, min_obs=12)
        worst = check_cpi_consistency(obs)
        missing = sum(1 for o in obs if o[1] is None)
        return {"observations": obs, "missing_skipped": 0, "request_url": urls[-1],
                "meta": {"yoy_null_months": missing, "max_yoy_index_gap_pp": worst}}
    return fetch


# ─── MoSPI GDP (National Accounts) ─────────────────────────────────────────────
GDP_URL = MOSPI + "nas/getNASData?base_year={base}&series=Current&frequency=Quarterly&indicator_code=5&format=json&limit=200"   # API max is 200 (300+ -> HTTP 400)
FQ_START = {"Q1": (0, 4), "Q2": (0, 7), "Q3": (0, 10), "Q4": (1, 1)}   # fiscal quarter -> (year offset, month)


def fiscal_quarter_start(fy: str, q: str) -> str:
    m = re.fullmatch(r"(\d{4})-(\d{2})", fy or "")
    if not m or q not in FQ_START:
        raise ValueError(f"bad fiscal period {fy!r} {q!r}")
    y0 = int(m.group(1))
    if (y0 + 1) % 100 != int(m.group(2)):
        raise ValueError(f"inconsistent fiscal year {fy!r}")
    off, mon = FQ_START[q]
    return f"{y0 + off:04d}-{mon:02d}-01"


def parse_mospi_gdp(payload: object, base: str) -> list[list]:
    """Quarterly GDP rows -> [[calendar_quarter_start, constant_price_crore, current_price_crore]]."""
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        msg = payload.get("msg") if isinstance(payload, dict) else None
        raise ValueError(f"no data array (msg={msg!r})")
    meta = payload.get("meta_data") or {}
    if meta.get("totalPages", 1) not in (0, 1):
        raise ValueError(f"response is paginated ({meta}); limit too small")
    out = {}
    for r in payload["data"]:
        if r.get("frequency") != "Quarterly":
            continue
        if r.get("base_year") != base or r.get("indicator") != "Gross Domestic Product" or r.get("unit") != "₹ Crore":
            raise ValueError(f"unexpected GDP row identity {(r.get('base_year'), r.get('indicator'), r.get('unit'))}")
        d = fiscal_quarter_start(r.get("year"), r.get("quarter"))
        if d in out:
            raise ValueError(f"duplicate GDP quarter {d} ({r.get('year')} {r.get('quarter')})")
        real = _num(r.get("constant_price"), f"GDP constant price {d}")
        nominal = _num(r.get("current_price"), f"GDP current price {d}")
        if real <= 0 or nominal <= 0:
            raise ValueError(f"GDP {d}: non-positive level")
        out[d] = [d, real, nominal]
    obs = [out[k] for k in sorted(out)]
    check_series(obs, min_obs=8)
    return obs


def mospi_gdp_fetcher(base: str):
    def fetch(getter, today: dt.date) -> dict:
        url = GDP_URL.format(base=base)
        return {"observations": parse_mospi_gdp(get_json(url, getter), base), "missing_skipped": 0,
                "request_url": url}
    return fetch


# ─── RBI current policy rates ──────────────────────────────────────────────────
RBI_URL = "https://www.rbi.org.in/"
RBI_RATES = [("repo", r"Policy Repo Rate"), ("sdf", r"Standing Deposit Facility Rate"),
             ("msf", r"Marginal Standing Facility Rate"), ("bank_rate", r"Bank Rate")]


def parse_rbi_rates(page: str) -> dict:
    """Extract the 'Current Rates' policy block. Fails if the block or its corridor is not as expected."""
    text = re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", page)))
    i = text.find("Policy Rates")
    if i < 0:
        raise ValueError("'Policy Rates' block not found on RBI page")
    block = text[i:i + 600]
    rates = {}
    for key, label in RBI_RATES:
        m = re.search(label + r"\s*:\s*(\d{1,2}\.\d{2})\s*%", block)
        if not m:
            raise ValueError(f"'{label}' not found in RBI policy block")
        rates[key] = float(m.group(1))
    if not 0 < rates["repo"] < 20:
        raise ValueError(f"repo rate out of range: {rates['repo']}")
    if not rates["sdf"] < rates["repo"] < rates["msf"]:
        raise ValueError(f"policy corridor inconsistent: SDF {rates['sdf']} / repo {rates['repo']} / MSF {rates['msf']}")
    return rates


def rbi_fetcher():
    def fetch(getter, today: dt.date) -> dict:
        rates = parse_rbi_rates(getter(RBI_URL))
        return {"observations": [[today.isoformat(), rates["repo"], rates["sdf"], rates["msf"], rates["bank_rate"]]],
                "missing_skipped": 0, "request_url": RBI_URL, "current_level": True}
    return fetch


# ─── ECB reference rates (Frankfurter) ─────────────────────────────────────────
FX_SYMBOLS = ["INR", "EUR", "JPY", "GBP", "CAD", "SEK", "CHF"]
FX_URL = "https://api.frankfurter.dev/v1/{start}..?base=USD&symbols=" + ",".join(FX_SYMBOLS)


def parse_frankfurter(payload: object) -> list[list]:
    if not isinstance(payload, dict) or payload.get("base") != "USD" or not isinstance(payload.get("rates"), dict):
        raise ValueError("unexpected Frankfurter payload")
    obs = []
    for d in sorted(payload["rates"]):
        r = payload["rates"][d]
        row = [d]
        for s in FX_SYMBOLS:
            v = _num(r.get(s), f"FX {s} {d}")
            if v <= 0:
                raise ValueError(f"FX {s} {d}: non-positive rate")
            row.append(v)
        obs.append(row)
    check_series(obs, min_obs=50)
    return obs


def fx_fetcher(start: str):
    def fetch(getter, today: dt.date) -> dict:
        url = FX_URL.format(start=start)
        return {"observations": parse_frankfurter(get_json(url, getter)), "missing_skipped": 0, "request_url": url}
    return fetch


# ─── World Bank annual (cross-check only) ──────────────────────────────────────
WB_URL = "https://api.worldbank.org/v2/country/IN/indicator/{ind}?format=json&mrv=12&per_page=20"


def parse_worldbank(payload: object, indicator: str) -> tuple[list[list], int]:
    if not isinstance(payload, list) or len(payload) < 2 or not isinstance(payload[1], list):
        raise ValueError("unexpected World Bank payload")
    out, missing = {}, 0
    for e in payload[1]:
        if (e.get("indicator") or {}).get("id") != indicator or (e.get("country") or {}).get("id") != "IN":
            raise ValueError("unexpected World Bank row identity")
        if not re.fullmatch(r"\d{4}", str(e.get("date"))):
            raise ValueError(f"bad WB year {e.get('date')!r}")
        if e.get("value") is None:
            missing += 1
            continue
        out[f"{e['date']}-01-01"] = [f"{e['date']}-01-01", _num(e["value"], f"WB {e['date']}")]
    obs = [out[k] for k in sorted(out)]
    check_series(obs, min_obs=3)
    return obs, missing


def worldbank_fetcher(indicator: str):
    def fetch(getter, today: dt.date) -> dict:
        url = WB_URL.format(ind=indicator)
        obs, missing = parse_worldbank(get_json(url, getter), indicator)
        return {"observations": obs, "missing_skipped": missing, "request_url": url}
    return fetch


# ─── Source registry ───────────────────────────────────────────────────────────
# recheck_minutes   : reuse window; a page open/reload inside it does not call the provider again.
# max_obs_age_days  : days from the start of the newest observation's period after which a newer
#                     release is overdue (state "Stale"). None = discontinued or current-level source.
# max_check_age_days: for current-level sources (RBI), how old a successful check may be.
def _src(**kw):
    kw.setdefault("max_obs_age_days", None)
    kw.setdefault("max_check_age_days", None)
    return kw


SOURCES = {
    "FRED:CPIAUCNS": _src(provider="FRED (BLS)", title="US CPI-U, all items, NSA", units="Index 1982-84=100",
                          frequency="Monthly", fields=["date", "value"],
                          source_url="https://fred.stlouisfed.org/series/CPIAUCNS",
                          transform="YoY % = index / same month a year earlier − 1 (missing months stay missing)",
                          fetch=fred_fetcher("CPIAUCNS", lookback_days=800, min_obs=13),
                          recheck_minutes=180, max_obs_age_days=80),
    "FRED:PCEPILFE": _src(provider="FRED (BEA)", title="US PCE price index ex food & energy, SA", units="Index 2017=100",
                          frequency="Monthly", fields=["date", "value"],
                          source_url="https://fred.stlouisfed.org/series/PCEPILFE",
                          transform="YoY % = index / same month a year earlier − 1",
                          fetch=fred_fetcher("PCEPILFE", lookback_days=800, min_obs=13),
                          recheck_minutes=180, max_obs_age_days=100),
    "FRED:PAYEMS": _src(provider="FRED (BLS)", title="US total nonfarm payrolls, SA", units="Thousands of persons",
                        frequency="Monthly", fields=["date", "value"],
                        source_url="https://fred.stlouisfed.org/series/PAYEMS",
                        transform="Monthly change (thousands of jobs) between consecutive months only",
                        fetch=fred_fetcher("PAYEMS", lookback_days=300, min_obs=3),
                        recheck_minutes=180, max_obs_age_days=70),
    "FRED:DFII10": _src(provider="FRED (Federal Reserve H.15)", title="10-year TIPS yield (real yield)", units="Percent",
                        frequency="Daily", fields=["date", "value"],
                        source_url="https://fred.stlouisfed.org/series/DFII10",
                        transform="Displayed as published; trend = change vs observation ≥30 days earlier",
                        fetch=fred_fetcher("DFII10", lookback_days=70, min_obs=10),
                        recheck_minutes=60, max_obs_age_days=6),
    "FRED:MCOILBRENTEU": _src(provider="FRED (EIA)", title="Brent crude, Europe spot, monthly average", units="USD per barrel",
                              frequency="Monthly", fields=["date", "value"],
                              source_url="https://fred.stlouisfed.org/series/MCOILBRENTEU",
                              transform="Monthly average of daily spot (not a current price); quarter = mean of 3 complete months",
                              fetch=fred_fetcher("MCOILBRENTEU", start="2021-01-01", min_obs=12),
                              recheck_minutes=180, max_obs_age_days=75),
    "MOSPI:CPI_2024": _src(provider="MoSPI (eSankhyiki API)", title="India CPI (General), All-India Combined, base 2024=100",
                           units="Index; YoY % as published", frequency="Monthly", fields=["date", "yoy", "index"],
                           source_url="https://esankhyiki.mospi.gov.in/macroindicators?product=cpi",
                           transform="Monthly YoY as published by MoSPI; quarterly point = mean of 3 monthly YoY prints",
                           fetch=mospi_cpi_fetcher("2024", 2025), recheck_minutes=180, max_obs_age_days=75),
    "MOSPI:CPI_2012": _src(provider="MoSPI (eSankhyiki API)", title="India CPI (General), All-India Combined, base 2012=100",
                           units="Index; YoY % as published", frequency="Monthly (discontinued after Dec 2025)",
                           fields=["date", "yoy", "index"],
                           source_url="https://esankhyiki.mospi.gov.in/macroindicators?product=cpi",
                           transform="Monthly YoY as published; used for quarters before the base-2024 series",
                           fetch=mospi_cpi_fetcher("2012", 2020, 2025), recheck_minutes=7 * 1440),
    "MOSPI:GDP_2022_23": _src(provider="MoSPI (eSankhyiki API, NAS)", title="India quarterly GDP, base 2022-23",
                              units="₹ crore (constant and current prices)", frequency="Quarterly",
                              fields=["date", "real", "nominal"],
                              source_url="https://esankhyiki.mospi.gov.in/macroindicators?product=nas",
                              transform="Real GDP YoY % = constant-price level / same fiscal quarter a year earlier − 1; "
                                        "fiscal Q1 (Apr–Jun) plotted as calendar Q2",
                              fetch=mospi_gdp_fetcher("2022-23"), recheck_minutes=360, max_obs_age_days=255),
    "MOSPI:GDP_2011_12": _src(provider="MoSPI (eSankhyiki API, NAS)", title="India quarterly GDP, base 2011-12 (superseded)",
                              units="₹ crore (constant and current prices)", frequency="Quarterly (superseded series)",
                              fields=["date", "real", "nominal"],
                              source_url="https://esankhyiki.mospi.gov.in/macroindicators?product=nas",
                              transform="Real GDP YoY % for quarters the base 2022-23 series does not cover",
                              fetch=mospi_gdp_fetcher("2011-12"), recheck_minutes=7 * 1440),
    "RBI:POLICY_RATES": _src(provider="Reserve Bank of India", title="Current policy rates (rbi.org.in 'Current Rates')",
                             units="Percent", frequency="Current level (page shows today's rates)",
                             fields=["date", "repo", "sdf", "msf", "bank_rate"],
                             source_url="https://www.rbi.org.in/",
                             transform="Date = day the page was read, not the decision's effective date",
                             fetch=rbi_fetcher(), recheck_minutes=60, max_check_age_days=3),
    "ECB:FX": _src(provider="ECB reference rates via Frankfurter", title="USD reference rates: INR, EUR, JPY, GBP, CAD, SEK, CHF",
                   units="Currency units per USD", frequency="Daily (TARGET business days, ≈16:00 CET)",
                   fields=["date"] + FX_SYMBOLS,
                   source_url="https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html",
                   transform="USD/INR shown as published; DXY estimated with the ICE formula from these rates",
                   fetch=fx_fetcher("2021-01-01"), recheck_minutes=60, max_obs_age_days=5),
    "WB:CPI_ANNUAL": _src(provider="World Bank WDI", title="India inflation, consumer prices (annual %)", units="Percent",
                          frequency="Annual", fields=["date", "value"],
                          source_url="https://data.worldbank.org/indicator/FP.CPI.TOTL.ZG?locations=IN",
                          transform="Cross-check only (calendar-year basis); never replaces the quarterly chart",
                          fetch=worldbank_fetcher("FP.CPI.TOTL.ZG"), recheck_minutes=1440, max_obs_age_days=950),
    "WB:GDP_ANNUAL": _src(provider="World Bank WDI", title="India GDP growth (annual %)", units="Percent",
                          frequency="Annual", fields=["date", "value"],
                          source_url="https://data.worldbank.org/indicator/NY.GDP.MKTP.KD.ZG?locations=IN",
                          transform="Cross-check only (India fiscal year, labelled by starting year)",
                          fetch=worldbank_fetcher("NY.GDP.MKTP.KD.ZG"), recheck_minutes=1440, max_obs_age_days=950),
}
PUBLIC_KEYS = ("provider", "title", "units", "frequency", "fields", "source_url", "transform",
               "recheck_minutes", "max_obs_age_days", "max_check_age_days")


# ─── Snapshot file ─────────────────────────────────────────────────────────────
def validate_entry(sid: str, e: object) -> dict:
    """Check a saved entry before trusting it. Raises ValueError if unusable."""
    if not isinstance(e, dict):
        raise ValueError("entry is not an object")
    obs = e.get("observations")
    if not isinstance(obs, list):
        raise ValueError("observations missing")
    width = len(e.get("fields") or SOURCES.get(sid, {}).get("fields") or [])
    for row in obs:
        if not isinstance(row, list) or (width and len(row) != width):
            raise ValueError("observation row has wrong shape")
        for v in row[1:]:
            if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or v != v):
                raise ValueError("non-numeric observation value")
    check_series(obs, min_obs=0)
    return e


def read_snapshot(path: str = OUT_PATH) -> tuple[dict, list[str]]:
    """Return (sources, problems). Invalid entries are dropped and reported, valid ones kept.
    A file that cannot be parsed at all is moved aside (never deleted) and reported."""
    problems: list[str] = []
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        return {}, problems
    _, sep, body = text.partition(JS_PREFIX)
    try:
        if not sep:
            raise ValueError("snapshot prefix missing")
        data = json.loads(body.strip().rstrip(";"))
        sources = data["sources"]
        if not isinstance(sources, dict):
            raise ValueError("sources is not an object")
    except (ValueError, KeyError, TypeError) as e:
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        aside = path[:-3] + f".corrupt-{stamp}.js"
        try:
            os.replace(path, aside)
        except OSError:
            aside = "(could not move)"
        problems.append(f"snapshot unreadable ({e}); moved to {os.path.basename(aside)}")
        return {}, problems
    good = {}
    for sid, e in sources.items():
        try:
            good[sid] = validate_entry(sid, e)
        except ValueError as err:
            problems.append(f"{sid}: saved entry invalid ({err}); ignored")
    return good, problems


def read_legacy_fred(path: str = LEGACY_FRED_PATH) -> dict:
    """One-time migration from the earlier data/fred_snapshot.js format."""
    try:
        with open(path, encoding="utf-8") as f:
            _, sep, body = f.read().partition(LEGACY_JS_PREFIX)
        old = json.loads(body.strip().rstrip(";"))["series"] if sep else {}
    except (OSError, ValueError, KeyError, TypeError):
        return {}
    out = {}
    for sid, e in old.items():
        key = f"FRED:{sid}"
        if key in SOURCES and e.get("observations"):
            out[key] = {"observations": e["observations"], "retrieved_at": e.get("retrieved_at"),
                        "last_success_at": e.get("retrieved_at"), "last_attempt_at": e.get("last_attempt_at"),
                        "last_obs": e.get("last_obs"), "status": "ok",
                        "missing_skipped": e.get("missing_skipped", 0)}
    return out


def write_snapshot(sources: dict, now_iso: str, path: str = OUT_PATH) -> None:
    payload = {"schema_version": SCHEMA_VERSION, "generated_at": now_iso, "generator": "refresh_data.py",
               "sources": sources}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write("// Generated by refresh_data.py. Do not edit by hand.\n")
        f.write(JS_PREFIX + json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + ";\n")
    os.replace(tmp, path)


# ─── Refresh logic ─────────────────────────────────────────────────────────────
def _parse_iso(s):
    try:
        return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def is_due(prev: dict | None, spec: dict, now: dt.datetime, force: bool) -> tuple[bool, str]:
    """Decide whether to call the provider, or reuse the last validated response."""
    if not prev or not prev.get("observations"):
        return True, "no saved data"
    last_attempt = _parse_iso(prev.get("last_attempt_at"))
    if last_attempt is None:
        return True, "never checked"
    age_s = (now - last_attempt).total_seconds()
    if age_s < FORCE_FLOOR_SECONDS:
        return False, f"checked {int(age_s)}s ago"
    age_min = age_s / 60
    if force:
        return True, "manual refresh"
    if prev.get("status") != "ok":
        if age_min >= FAILED_RETRY_MINUTES:
            return True, "retry after failure"
        return False, f"last attempt failed {int(age_min)} min ago; retry after {FAILED_RETRY_MINUTES} min"
    if age_min >= spec["recheck_minutes"]:
        return True, f"reuse window ({spec['recheck_minutes']} min) expired"
    return False, f"checked {int(age_min)} min ago (reuse window {spec['recheck_minutes']} min)"


def compare_observations(old: list, new: list) -> tuple[int, int]:
    """(new_dates, revised_points) between two observation lists."""
    old_by = {r[0]: r[1:] for r in old or []}
    newest_old = max(old_by) if old_by else None
    new_dates = sum(1 for r in new if r[0] not in old_by and (newest_old is None or r[0] > newest_old))
    revised = sum(1 for r in new if r[0] in old_by and old_by[r[0]] != r[1:])
    return new_dates, revised


def refresh_source(sid: str, spec: dict, prev: dict | None, now: dt.datetime, getter=http_get) -> tuple[dict, dict]:
    """Fetch one source. Returns (entry, run_result). Failure keeps previous data."""
    now_iso = now.isoformat().replace("+00:00", "Z")
    public = {k: spec[k] for k in PUBLIC_KEYS}
    prev = prev or {}
    base = {**public, "id": sid, "last_attempt_at": now_iso}
    try:
        got = spec["fetch"](getter, now.date())
    except FetchError as e:
        error = {"kind": e.kind, "detail": str(e)}
    except ValueError as e:
        error = {"kind": "validation", "detail": str(e)}
    except Exception as e:  # an adapter bug must not break other sources
        error = {"kind": "internal", "detail": f"{type(e).__name__}: {e}"}
    else:
        obs = got["observations"]
        if got.get("current_level"):
            # keep a short history of readings so the page can say since when a value has been seen
            history = [r for r in prev.get("observations") or [] if r[0] < obs[-1][0]] + obs
            obs = history[-60:]
        new_dates, revised = compare_observations(prev.get("observations"), obs)
        last_obs = obs[-1][0] if obs else None
        advanced = last_obs is not None and last_obs != prev.get("last_obs")
        entry = {**base, "status": "ok", "observations": obs, "count": len(obs),
                 "missing_skipped": got.get("missing_skipped", 0),
                 "first_obs": obs[0][0] if obs else None, "last_obs": last_obs,
                 "request_url": got.get("request_url"), "meta": got.get("meta"),
                 "retrieved_at": now_iso, "last_success_at": now_iso, "last_error": None,
                 "last_new_obs_at": now_iso if advanced else (prev.get("last_new_obs_at") or now_iso),
                 "last_change": {"new_obs": new_dates, "revised": revised, "at": now_iso}}
        return entry, {"id": sid, "action": "checked", "new_obs": new_dates, "revised": revised,
                       "last_obs": last_obs}
    if prev.get("observations"):
        kept = {k: prev.get(k) for k in ("observations", "count", "missing_skipped", "first_obs", "last_obs",
                                         "request_url", "meta", "retrieved_at", "last_success_at",
                                         "last_new_obs_at", "last_change")}
        entry = {**base, **kept, "status": "failed_kept_previous", "last_error": error}
    else:
        entry = {**base, "status": "failed_no_data", "observations": [], "count": 0, "last_obs": None,
                 "retrieved_at": None, "last_success_at": None, "last_error": error}
    return entry, {"id": sid, "action": "failed", "error": error, "kept_previous": bool(prev.get("observations"))}


def _save_late_result(sid: str, fut: cf.Future, path: str) -> None:
    """A fetch that outlived the request's wait: merge its result into the file when it lands."""
    try:
        entry, _ = fut.result()
    except Exception:          # refresh_source never raises, but never kill the worker either
        return
    with _REFRESH_LOCK:
        latest, _ = read_snapshot(path)
        merged = {k: v for k, v in latest.items() if k in SOURCES}
        merged[sid] = entry
        write_snapshot(merged, entry.get("last_attempt_at") or "", path)


def refresh(force: bool = False, only: list[str] | None = None, getter=http_get, path: str = OUT_PATH,
            now: dt.datetime | None = None, max_workers: int | None = None,
            wait_seconds: float | None = None) -> dict:
    """Refresh due sources, merge into the snapshot atomically, and return {snapshot, run}.

    wait_seconds=None waits for every source (CLI). The server passes a limit so a page gets
    finished sources quickly; slower ones keep running, are reported as 'pending', and are saved
    when they finish. max_workers is accepted for compatibility (a shared pool is used).
    """
    with _REFRESH_LOCK:
        now = now or dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        now_iso = now.isoformat().replace("+00:00", "Z")
        current, problems = read_snapshot(path)
        if not current and path == OUT_PATH:
            current = read_legacy_fred()
        ids = [s for s in SOURCES if not only or s in only]
        due, results = [], []
        for sid in ids:
            with _IN_FLIGHT_LOCK:
                running = sid in _IN_FLIGHT
            if running:
                results.append({"id": sid, "action": "pending", "reason": "check already in progress",
                                "last_obs": (current.get(sid) or {}).get("last_obs")})
                continue
            ok, why = is_due(current.get(sid), SOURCES[sid], now, force)
            if ok:
                due.append(sid)
            else:
                results.append({"id": sid, "action": "reused", "reason": why,
                                "last_obs": current[sid].get("last_obs")})
        if due:
            futs = {}
            for sid in due:
                fut = _EXECUTOR.submit(refresh_source, sid, SOURCES[sid], current.get(sid), now, getter)
                with _IN_FLIGHT_LOCK:
                    _IN_FLIGHT[sid] = fut
                fut.add_done_callback(lambda f, sid=sid: _forget(sid, f))
                futs[fut] = sid
            done, not_done = cf.wait(futs, timeout=wait_seconds)
            updated = {}
            for fut in done:
                entry, res = fut.result()
                updated[futs[fut]] = entry
                results.append(res)
            for fut in not_done:
                sid = futs[fut]
                results.append({"id": sid, "action": "pending", "reason": "slow provider; result is saved when it arrives",
                                "last_obs": (current.get(sid) or {}).get("last_obs")})
            # merge against the file as it is now, so a concurrent writer's other sources survive
            latest, more = read_snapshot(path)
            problems += [p for p in more if p not in problems]
            merged = {sid: e for sid, e in {**current, **latest}.items() if sid in SOURCES}
            merged.update(updated)
            write_snapshot(merged, now_iso, path)
            current = merged
            # registered after our write, so a late result can never be overwritten by it
            for fut in not_done:
                fut.add_done_callback(lambda f, sid=futs[fut]: _save_late_result(sid, f, path))
        results.sort(key=lambda r: list(SOURCES).index(r["id"]))
        snapshot = {"schema_version": SCHEMA_VERSION, "generated_at": now_iso, "sources": current}
        return {"snapshot": snapshot,
                "run": {"at": now_iso, "forced": force, "results": results, "problems": problems}}


def _forget(sid: str, fut: cf.Future) -> None:
    with _IN_FLIGHT_LOCK:
        if _IN_FLIGHT.get(sid) is fut:
            del _IN_FLIGHT[sid]


# ─── CLI ───────────────────────────────────────────────────────────────────────
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Refresh dashboard data into data/macro_snapshot.js")
    ap.add_argument("--due", action="store_true", help="only refresh sources whose reuse window has expired")
    args = ap.parse_args(argv)
    out = refresh(force=not args.due)
    for p in out["run"]["problems"]:
        print(f"  NOTE   {p}")
    failures = 0
    for r in out["run"]["results"]:
        e = out["snapshot"]["sources"].get(r["id"], {})
        if r["action"] == "checked":
            extra = [f"{r['new_obs']} new" if r["new_obs"] else "", f"{r['revised']} revised" if r["revised"] else ""]
            extra = ", ".join(x for x in extra if x)
            print(f"  OK     {r['id']:<20} {e.get('count', 0):>5} obs  latest {e.get('last_obs')}"
                  + (f"  ({extra})" if extra else ""))
        elif r["action"] == "reused":
            print(f"  REUSE  {r['id']:<20} latest {r.get('last_obs')}  [{r['reason']}]")
        else:
            failures += 1
            kept = f"kept data to {e.get('last_obs')}" if r.get("kept_previous") else "no data"
            print(f"  FAIL   {r['id']:<20} {r['error']['detail']}  [{kept}]")
    print(f"Wrote {os.path.relpath(OUT_PATH, HERE)} at {out['run']['at']} - "
          f"{len(out['run']['results']) - failures}/{len(out['run']['results'])} sources OK")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
