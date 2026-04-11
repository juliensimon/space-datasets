#!/usr/bin/env python3
"""Daily incremental update for Space-Track TLE History.

Fetches yesterday's GP history (one API call), appends to the current year's
parquet file on HF. Handles year boundaries by creating a new file on Jan 1.

Requires SPACETRACK_USER and SPACETRACK_PASS environment variables.
"""

import math
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import requests

from hf_dataset_utils import Pipeline

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

# ── Column descriptions ────────────────────────────────────────────────
COLUMN_DESCRIPTIONS = {
    "norad_id": "NORAD catalog number — unique integer ID assigned to each tracked object by the US Space Surveillance Network; used worldwide as the primary satellite identifier",
    "epoch": "UTC timestamp of the TLE's reference epoch — the moment at which the orbital elements are valid; propagation accuracy degrades with time from epoch",
    "inclination": "Orbital inclination in degrees (0-180); angle between the orbital plane and Earth's equatorial plane; 0=equatorial, 90=polar, >90=retrograde",
    "raan": "Right ascension of the ascending node in degrees (0-360); longitude where the orbit crosses the equatorial plane northward; precesses due to Earth's oblateness",
    "eccentricity": "Orbital eccentricity (0-1); 0=circular, values near 1=highly elliptical; most LEO objects have eccentricity < 0.01",
    "arg_perigee": "Argument of perigee in degrees (0-360); angle from ascending node to perigee measured in the orbital plane; defines the orientation of the ellipse",
    "mean_anomaly": "Mean anomaly in degrees (0-360); fraction of the orbital period elapsed since perigee, linearized; gives the satellite's position along its orbit at epoch",
    "mean_motion": "Mean motion in revolutions per day; related to semi-major axis via Kepler's third law; LEO objects typically 14-16 rev/day, GEO ~1.0 rev/day",
    "mean_motion_dot": "First derivative of mean motion (rev/day^2); indicates orbital decay rate; negative values suggest boosting maneuvers, positive indicates atmospheric drag",
    "bstar": "BSTAR drag coefficient (1/Earth radii); models atmospheric drag in the SGP4 propagator; higher values indicate greater drag area-to-mass ratio or lower altitude",
    "intl_designator": "International designator (COSPAR ID) in format YYNNNPPP — launch year, launch number, and piece letter; identifies the launch and specific object from that launch",
    "altitude_km": "Approximate perigee altitude in km, derived from mean motion and eccentricity via Kepler's third law; negative values indicate decayed objects or parsing errors",
}

DESCRIPTION = """\
Daily archive of Two-Line Element sets (TLEs) from Space-Track.org, providing \
the orbital state of every tracked object in Earth orbit. TLEs are the standard \
format used by the US Space Surveillance Network to distribute orbital elements \
for satellites, rocket bodies, and debris. Each record contains the classical \
orbital elements (inclination, eccentricity, RAAN, argument of perigee, mean \
anomaly, mean motion) plus drag parameters needed by the SGP4/SDP4 propagator. \
This dataset captures the full GP history — one TLE per object per day — enabling \
studies of orbital evolution, atmospheric drag effects, conjunction analysis, and \
space debris tracking over time. Data is partitioned by year for efficient access."""


# ── TLE parsing (domain-specific) ──────────────────────────────────────

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
        print("::warning::No TLEs returned for yesterday -- Space-Track may be delayed. Skipping.")
        sys.exit(0)

    new_table = pa.Table.from_pylist(records, schema=SCHEMA)

    # Download existing year parquet from HF and append
    with Pipeline(
        repo=HF_REPO,
        pretty_name="Space-Track TLE History",
        description=DESCRIPTION,
        tags=["space", "satellites", "tle", "orbits", "space-track",
              "orbital-mechanics", "open-data", "tabular-data", "parquet"],
        source_url="https://www.space-track.org/",
        task_categories=["time-series-forecasting"],
        update_schedule="Daily via [GitHub Actions](https://github.com/juliensimon/space-datasets). Fetches yesterday's GP history from Space-Track.",
        collection_url="https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994",
        banner={
            "url": "https://images-assets.nasa.gov/image/iss071e439624/iss071e439624~medium.jpg",
            "alt": "An orbital sunrise illuminates the Earth's atmosphere, seen from the ISS",
            "credit": "NASA",
        },
        related_datasets=[
            "juliensimon/space-track-satcat",
            "juliensimon/starlink-fleet-data",
            "juliensimon/space-launch-log",
        ],
    ) as p:
        # Download existing year parquet
        df_existing = p.download_existing(parquet_name)

        if df_existing is not None:
            df_existing["epoch"] = pd.to_datetime(df_existing["epoch"], utc=True)
            print(f"  Existing: {len(df_existing):,} TLEs")

            df_new = new_table.to_pandas()
            df_new["epoch"] = pd.to_datetime(df_new["epoch"], utc=True)

            # Remove existing rows for yesterday's date (idempotent re-runs)
            yesterday_date = yesterday.date()
            df_existing = df_existing[df_existing["epoch"].dt.date != yesterday_date]

            df_merged = p.merge(df_existing, df_new,
                                dedup_on=["norad_id", "epoch"],
                                sort_by=["norad_id", "epoch"])
        else:
            df_merged = new_table.to_pandas()

        n_total = len(df_merged)
        print(f"  Total: {n_total:,} TLEs")

        # Write using PyArrow for schema enforcement
        parquet_path = p.data_dir / parquet_name
        merged_table = pa.Table.from_pandas(df_merged, schema=SCHEMA, preserve_index=False)
        pq.write_table(merged_table, parquet_path, compression="zstd")
        size_mb = parquet_path.stat().st_size / 1024 / 1024
        print(f"  Written: {parquet_name} ({size_mb:.1f} MB)")

        # Single-file upload (year-partitioned, no README regen)
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
            f.write(f"rows={n_total}\n")
    print("Done.")


if __name__ == "__main__":
    main()
