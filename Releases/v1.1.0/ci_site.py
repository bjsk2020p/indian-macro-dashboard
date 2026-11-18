"""GitHub Pages helpers for .github/workflows/pages.yml. Standard library only.

  python ci_site.py seed <downloaded snapshot>   Merge base: per source, keep whichever of the
                                                 published copy and the repository copy was
                                                 attempted more recently. An unreadable download
                                                 is ignored (the repository copy is used).
  python ci_site.py build <site dir>             Validate data/macro_snapshot.js, then assemble the
                                                 site from an allow-list of files. Exits 1 (and
                                                 writes nothing) if the snapshot is empty or corrupt,
                                                 so a bad snapshot is never published.

Neither command touches the network; the workflow downloads the published snapshot itself.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import refresh_data  # noqa: E402

PAGE = "india_macro_dashboard_v5.html"
# Everything the hosted page needs, and nothing else (no tests, archives, releases, logs, caches).
SITE_FILES = {                         # site path -> repo path
    "index.html": PAGE,
    PAGE: PAGE,
    "manifest.webmanifest": "manifest.webmanifest",
    "icons/icon-180.png": "icons/icon-180.png",
    "icons/icon-192.png": "icons/icon-192.png",
    "icons/icon-512.png": "icons/icon-512.png",
}
SNAPSHOT_SITE_PATH = "data/macro_snapshot.js"


def _read_copy(path: str) -> tuple[dict, list[str], str | None]:
    """read_snapshot on a temporary copy (read_snapshot moves corrupt files aside; keep inputs intact)."""
    if not os.path.isfile(path):
        return {}, [f"{path} not found"], None
    with tempfile.TemporaryDirectory() as d:
        tmp = os.path.join(d, "snap.js")
        shutil.copyfile(path, tmp)
        sources, problems = refresh_data.read_snapshot(tmp)
        gen = None
        if os.path.isfile(tmp):
            with open(tmp, encoding="utf-8") as f:
                _, _, body = f.read().partition(refresh_data.JS_PREFIX)
            try:
                gen = json.loads(body.strip().rstrip(";")).get("generated_at")
            except (ValueError, AttributeError):
                gen = None
    return sources, problems, gen


def _attempt_key(e: dict):
    t = refresh_data._parse_iso(e.get("last_attempt_at")) or refresh_data._parse_iso(e.get("last_success_at"))
    return t or dt.datetime.min.replace(tzinfo=dt.timezone.utc)


def merge(published: dict, repo: dict) -> tuple[dict, dict]:
    """Per source, the entry attempted more recently (ties go to the published copy)."""
    out, picked = {}, {}
    for sid in sorted(set(published) | set(repo)):
        a, b = published.get(sid), repo.get(sid)
        if a is not None and (b is None or _attempt_key(a) >= _attempt_key(b)):
            out[sid], picked[sid] = a, "published"
        else:
            out[sid], picked[sid] = b, "repository"
    return out, picked


def seed(downloaded: str, target: str = refresh_data.OUT_PATH) -> int:
    pub, pub_problems, _ = _read_copy(downloaded)
    repo, repo_problems, _ = _read_copy(target)
    if pub_problems or not pub:
        print(f"::notice title=merge base::Published snapshot not usable ({'; '.join(pub_problems) or 'empty'}); "
              "starting from the repository copy.")
        pub = {}
    for p in repo_problems:
        if "not found" not in p:
            print(f"::warning title=repository snapshot::{p}")
    merged, picked = merge(pub, repo)
    if not merged:
        print("::notice title=merge base::No saved data anywhere; refresh_data.py will fetch every source.")
        return 0
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    refresh_data.write_snapshot(merged, now, target)
    n_pub = sum(1 for v in picked.values() if v == "published")
    print(f"Merge base: {n_pub} source(s) from the published site, {len(picked) - n_pub} from the repository.")
    return 0


def check_publishable(path: str) -> list[str]:
    """Reasons this snapshot must not be published (empty list = OK)."""
    sources, problems, gen = _read_copy(path)
    errors = list(problems)
    if not sources:
        errors.append("snapshot has no valid sources")
    if refresh_data._parse_iso(gen) is None:
        errors.append("snapshot has no valid generated_at")
    if not any(e.get("observations") for e in sources.values()):
        errors.append("snapshot has no observations")
    return errors


def build(site_dir: str, root: str = HERE) -> int:
    snap = os.path.join(root, "data", "macro_snapshot.js")
    errors = check_publishable(snap)
    if errors:
        for e in errors:
            print(f"::error title=snapshot not published::{e}")
        return 1
    sources, _, _ = _read_copy(snap)
    missing = [sid for sid in refresh_data.SOURCES if not (sources.get(sid) or {}).get("observations")]
    for sid in missing:
        print(f"::warning title={sid}::no saved data; the page shows its embedded baseline for this source")
    if os.path.exists(site_dir):
        shutil.rmtree(site_dir)
    for dest, src in list(SITE_FILES.items()) + [(SNAPSHOT_SITE_PATH, os.path.relpath(snap, root))]:
        out = os.path.join(site_dir, *dest.split("/"))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        shutil.copyfile(os.path.join(root, src), out)
    print(f"Site assembled in {site_dir}: {len(SITE_FILES) + 1} files, "
          f"{len(refresh_data.SOURCES) - len(missing)}/{len(refresh_data.SOURCES)} sources with data.")
    return 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) == 2 and argv[0] == "seed":
        return seed(argv[1])
    if len(argv) == 2 and argv[0] == "build":
        return build(argv[1])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
