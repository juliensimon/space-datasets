#!/usr/bin/env python3
"""
Daily incremental update for Space-Track TLE History.

Fetches yesterday's GP history (one API call), appends to the current year's
parquet file on HF. Handles year boundaries by creating a new file on Jan 1.

Requires SPACETRACK_USER and SPACETRACK_PASS environment variables.
"""

import math
import os
import re
import subprocess
import sys
import tempfile
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


# ── TLE parsing ──────────────────────────────────────────────────────────────

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


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    import requests

    user = os.environ.get("SPACETRACK_USER")
    pw = os.environ.get("SPACETRACK_PASS")
    if not user or not pw:
        print("::error::SPACETRACK_USER and SPACETRACK_PASS must be set")
        sys.exit(1)

    # Fetch yesterday's TLEs (one API call)
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    day_str = yesterday.strftime("%Y-%m-%d")
    year = yesterday.year
    next_day = (yesterday + timedelta(days=1)).strftime("%Y-%m-%d")
    parquet_name = f"tle_{year}.parquet"

    print(f"Fetching TLEs for {day_str}...")
    session = requests.Session()
    resp = session.post(SPACETRACK_LOGIN, data={"identity": user, "password": pw})
    resp.raise_for_status()
    print("  Logged in to Space-Track")

    url = SPACETRACK_QUERY.format(start=day_str, end=next_day)
    resp = session.get(url, timeout=300)
    resp.raise_for_status()

    records = parse_tle_text(resp.text)
    print(f"  {len(records):,} TLEs")

    if len(records) == 0:
        print("::warning::No TLEs returned for yesterday — Space-Track may be delayed. Skipping.")
        sys.exit(0)

    new_table = pa.Table.from_pylist(records, schema=SCHEMA)

    # Download existing year parquet from HF and append
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        data_dir = tmp_dir / "data"
        data_dir.mkdir()
        parquet_path = data_dir / parquet_name

        try:
            subprocess.run(
                ["hf", "download", HF_REPO, f"data/{parquet_name}",
                 "--repo-type", "dataset", "--local-dir", str(tmp_dir)],
                check=True, capture_output=True, timeout=600,
            )
        except subprocess.CalledProcessError:
            # New year — no existing file yet, that's OK
            print(f"  No existing {parquet_name} on HF — creating new file")

        if parquet_path.exists():
            existing = pq.read_table(parquet_path)
            print(f"  Existing: {existing.num_rows:,} TLEs")

            # Deduplicate: remove any TLEs from yesterday that might already exist
            # (idempotent re-runs)
            import pandas as pd
            df_existing = existing.to_pandas()
            df_new = new_table.to_pandas()
            df_existing["epoch"] = pd.to_datetime(df_existing["epoch"], utc=True)
            df_new["epoch"] = pd.to_datetime(df_new["epoch"], utc=True)

            # Remove existing rows for yesterday's date
            yesterday_date = yesterday.date()
            df_existing = df_existing[df_existing["epoch"].dt.date != yesterday_date]

            df_merged = pd.concat([df_existing, df_new], ignore_index=True)
            df_merged = df_merged.sort_values(["norad_id", "epoch"]).reset_index(drop=True)
            merged = pa.Table.from_pandas(df_merged, schema=SCHEMA, preserve_index=False)
        else:
            merged = new_table

        print(f"  Total: {merged.num_rows:,} TLEs")
        pq.write_table(merged, parquet_path, compression="zstd")
        size_mb = parquet_path.stat().st_size / 1024 / 1024
        print(f"  Written: {parquet_name} ({size_mb:.1f} MB)")

        print("Uploading to HF...")
        subprocess.run(
            ["hf", "upload", HF_REPO,
             str(parquet_path), f"data/{parquet_name}",
             "--repo-type", "dataset",
             "--commit-message", f"Daily TLE update: {day_str} (+{len(records):,} TLEs)"],
            check=True,
        )

    # Output row count for status tracking
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={merged.num_rows}\n")
    print("Done.")


if __name__ == "__main__":
    main()
