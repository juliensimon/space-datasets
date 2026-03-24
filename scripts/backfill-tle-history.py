#!/usr/bin/env python3
"""
Backfill TLE history from Space-Track GP History API.

Fetches one day at a time in TLE format, parses into the same schema as
build-tle-archive.py, and writes a single Parquet file. Extremely conservative
rate limiting to avoid bans.

Usage:
    export SPACETRACK_USER=you@example.com
    export SPACETRACK_PASS=yourpassword

    # Backfill 2026 (dry run — writes local parquet only)
    python scripts/backfill-tle-history.py

    # Upload to HF when done
    python scripts/backfill-tle-history.py --upload

    # Custom date range
    python scripts/backfill-tle-history.py --start 2026-01-01 --end 2026-03-23

    # Resume after interruption (reads progress file, skips completed days)
    python scripts/backfill-tle-history.py
"""

import argparse
import json
import math
import os
import random
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

# ── Constants ────────────────────────────────────────────────────────────────

MU = 398600.4418
R_EARTH = 6371.0

SPACETRACK_LOGIN = "https://www.space-track.org/ajaxauth/login"
SPACETRACK_QUERY = (
    "https://www.space-track.org/basicspacedata/query"
    "/class/gp_history"
    "/EPOCH/{start}--{end}"
    "/orderby/NORAD_CAT_ID,EPOCH"
    "/format/tle"
)

DATA_DIR = Path(__file__).parent.parent / "data" / "tle-backfill"
PROGRESS_FILE = DATA_DIR / "progress.json"
HF_REPO = "juliensimon/space-track-tle-history"

SCHEMA = pa.schema([
    ("norad_id", pa.int32()),
    ("epoch", pa.timestamp("us", tz="UTC")),
    ("inclination", pa.float32()),
    ("raan", pa.float32()),
    ("eccentricity", pa.float32()),
    ("arg_perigee", pa.float32()),
    ("mean_anomaly", pa.float32()),
    ("mean_motion", pa.float64()),
    ("mean_motion_dot", pa.float64()),
    ("bstar", pa.float64()),
    ("intl_designator", pa.string()),
    ("altitude_km", pa.float32()),
])


# ── TLE parsing (same as build-tle-archive.py) ──────────────────────────────

def altitude_from_mean_motion(n: float, ecc: float) -> float:
    if n <= 0:
        return -1.0
    n_rad = n * 2 * math.pi / 86400.0
    a = (MU / (n_rad ** 2)) ** (1.0 / 3.0)
    return a * (1 - ecc) - R_EARTH


def parse_scientific(s: str) -> float:
    s = s.strip()
    if not s or s in ("00000-0", "00000+0"):
        return 0.0
    m = re.match(r"^([+-]?)(\d+)([+-]\d+)$", s)
    if not m:
        return 0.0
    sign = -1 if m.group(1) == "-" else 1
    mantissa = float("0." + m.group(2))
    exponent = int(m.group(3))
    return sign * mantissa * (10**exponent)


def epoch_to_datetime(year: int, day: float) -> datetime:
    base = datetime(year, 1, 1, tzinfo=timezone.utc)
    return base + timedelta(days=day - 1)


def parse_tle_pair(line1: str, line2: str) -> dict | None:
    try:
        norad_id = int(line1[2:7].strip())
        intl_des = line1[9:17].strip()

        epoch_yr = int(line1[18:20].strip())
        epoch_year = 1900 + epoch_yr if epoch_yr >= 57 else 2000 + epoch_yr
        epoch_day = float(line1[20:32].strip())
        epoch_dt = epoch_to_datetime(epoch_year, epoch_day)

        ndot = float(line1[33:43].strip())
        bstar = parse_scientific(line1[53:61].strip())

        inclination = float(line2[8:16].strip())
        raan = float(line2[17:25].strip())
        ecc = float("0." + line2[26:33].strip())
        arg_perigee = float(line2[34:42].strip())
        mean_anomaly = float(line2[43:51].strip())
        mean_motion = float(line2[52:63].strip())

        altitude = altitude_from_mean_motion(mean_motion, ecc)

        return {
            "norad_id": norad_id,
            "epoch": epoch_dt,
            "inclination": round(inclination, 4),
            "raan": round(raan, 4),
            "eccentricity": ecc,
            "arg_perigee": round(arg_perigee, 4),
            "mean_anomaly": round(mean_anomaly, 4),
            "mean_motion": round(mean_motion, 8),
            "mean_motion_dot": ndot,
            "bstar": bstar,
            "intl_designator": intl_des,
            "altitude_km": round(altitude, 2),
        }
    except (ValueError, IndexError):
        return None


def parse_tle_text(text: str) -> list[dict]:
    """Parse TLE-format text into a list of record dicts."""
    records = []
    lines = text.strip().split("\n")
    prev_line = None
    for line in lines:
        line = line.rstrip()
        if prev_line is None:
            if line.startswith("1 "):
                prev_line = line
            continue
        if not line.startswith("2 "):
            prev_line = line if line.startswith("1 ") else None
            continue
        rec = parse_tle_pair(prev_line, line)
        if rec:
            records.append(rec)
        prev_line = None
    return records


# ── Space-Track ──────────────────────────────────────────────────────────────

def login(session) -> None:
    import requests
    user = os.environ.get("SPACETRACK_USER")
    pw = os.environ.get("SPACETRACK_PASS")
    if not user or not pw:
        print("Set SPACETRACK_USER and SPACETRACK_PASS environment variables.")
        sys.exit(1)
    resp = session.post(SPACETRACK_LOGIN, data={"identity": user, "password": pw})
    resp.raise_for_status()
    print("Logged in to Space-Track.")


def fetch_day(session, day: datetime) -> str:
    """Fetch all GP history TLE records for a single day. Returns raw TLE text."""
    start = day.strftime("%Y-%m-%d")
    end = (day + timedelta(days=1)).strftime("%Y-%m-%d")
    url = SPACETRACK_QUERY.format(start=start, end=end)
    resp = session.get(url, timeout=300)
    resp.raise_for_status()
    return resp.text


# ── Progress ─────────────────────────────────────────────────────────────────

def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text())
    return {"completed_days": []}


def save_progress(progress: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PROGRESS_FILE.write_text(json.dumps(progress, indent=2) + "\n")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    import requests

    parser = argparse.ArgumentParser(description="Backfill TLE history from Space-Track")
    parser.add_argument("--start", default="2026-01-01", help="Start date (inclusive)")
    parser.add_argument("--end", default="2026-03-23", help="End date (inclusive)")
    parser.add_argument("--delay", type=int, default=120, help="Seconds between requests (default: 120)")
    parser.add_argument("--upload", action="store_true", help="Upload to HF when done")
    args = parser.parse_args()

    start = datetime.strptime(args.start, "%Y-%m-%d")
    end = datetime.strptime(args.end, "%Y-%m-%d")
    delay = args.delay

    all_days = []
    d = start
    while d <= end:
        all_days.append(d)
        d += timedelta(days=1)

    progress = load_progress()
    completed = set(progress["completed_days"])
    remaining = [d for d in all_days if d.strftime("%Y-%m-%d") not in completed]

    print(f"Date range: {args.start} to {args.end} ({len(all_days)} days)")
    print(f"Already completed: {len(completed)}")
    print(f"Remaining: {len(remaining)}")
    print(f"Delay between requests: {delay}s")
    print(f"Output dir: {DATA_DIR}")
    print()

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if remaining:
        session = requests.Session()
        login(session)
        print()

        for i, day in enumerate(remaining):
            day_str = day.strftime("%Y-%m-%d")
            day_file = DATA_DIR / f"tle_{day_str}.parquet"
            print(f"[{i+1}/{len(remaining)}] Fetching {day_str}...", end=" ", flush=True)

            try:
                text = fetch_day(session, day)
                records = parse_tle_text(text)
                print(f"{len(records):,} TLEs.", end=" ", flush=True)

                if records:
                    table = pa.Table.from_pylist(records, schema=SCHEMA)
                    pq.write_table(table, day_file, compression="zstd")
                    size_mb = day_file.stat().st_size / 1024 / 1024
                    print(f"({size_mb:.1f} MB)")
                else:
                    print("No data.")

                progress["completed_days"].append(day_str)
                save_progress(progress)

            except requests.HTTPError as e:
                if e.response is not None and e.response.status_code == 429:
                    print(f"\nRate limited! Waiting 10 minutes...")
                    time.sleep(600)
                    continue
                else:
                    print(f"\nHTTP error: {e}")
                    print("Progress saved. Re-run to resume.")
                    save_progress(progress)
                    sys.exit(1)
            except Exception as e:
                print(f"\nError: {e}")
                print("Progress saved. Re-run to resume.")
                save_progress(progress)
                sys.exit(1)

            # Be very gentle
            if i < len(remaining) - 1:
                jitter = delay * random.uniform(-0.25, 0.25)
                wait = delay + jitter
                # Extra 5-min cooldown every 10 requests
                if (i + 1) % 10 == 0:
                    wait += 300
                    print(f"  Cooldown — waiting {wait:.0f}s...", flush=True)
                else:
                    print(f"  Waiting {wait:.0f}s...", flush=True)
                time.sleep(wait)

    # ── Merge daily parquets into single yearly file ─────────────────────────
    day_files = sorted(DATA_DIR.glob("tle_2026-*.parquet"))
    if not day_files:
        print("No daily parquet files to merge.")
        return

    print(f"\nMerging {len(day_files)} daily files...")
    tables = []
    for f in day_files:
        tables.append(pq.read_table(f))
    merged = pa.concat_tables(tables)
    print(f"Total: {merged.num_rows:,} TLEs")

    out_path = DATA_DIR / "tle_2026.parquet"
    pq.write_table(merged, out_path, compression="zstd")
    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f"Written: {out_path} ({size_mb:.1f} MB)")

    if not args.upload:
        print("\nDry run — skipping HF upload. Use --upload to push.")
        return

    print("\nUploading to HF...")
    subprocess.run(
        ["hf", "upload", HF_REPO, str(out_path), "data/tle_2026.parquet",
         "--repo-type", "dataset",
         "--commit-message", f"Add 2026 TLE history ({merged.num_rows:,} TLEs, {args.start} to {args.end})"],
        check=True,
    )
    print("Done!")


if __name__ == "__main__":
    main()
