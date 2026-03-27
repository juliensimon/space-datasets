#!/usr/bin/env python3
"""
Fetch active satellite constellations from CelesTrak, classify by shell, and upload to HF.

Covers ~20 constellations: Starlink, OneWeb, Kuiper, Qianfan, Hulianwang, Iridium,
Globalstar, ORBCOMM, Planet, Spire, GPS, Galileo, BeiDou, GLONASS, SBAS, SES,
Intelsat, Eutelsat, Telesat.
"""

import math
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset


HF_REPO = "juliensimon/constellation-census"

MU = 398600.4418  # Earth GM (km³/s²)
R_EARTH = 6371.0  # km

# ── Constellation definitions ────────────────────────────────────────────────

# Each entry maps a constellation ID to its CelesTrak group, name pattern,
# metadata, and orbital shell definitions.
#
# Shell classification uses inclination ranges. For constellations with a single
# shell (most non-mega-constellations), we define one shell covering the full
# inclination range of the group.

CONSTELLATIONS = {
    "starlink": {
        "group": "starlink",
        "pattern": "STARLINK",
        "operator": "SpaceX",
        "country": "US",
        "orbit_type": "LEO",
        "shells": {
            0: {"name": "Shell 1 (33°/328km)", "inc": (0, 38), "alt": (300, 570)},
            1: {"name": "Shell 2 (43°/340km)", "inc": (38, 48), "alt": (300, 570)},
            2: {"name": "Shell 3 (53°/550km)", "inc": (48, 60), "alt": (460, 600)},
            3: {"name": "Shell 4 (70°/570km)", "inc": (60, 80), "alt": (460, 910)},
            4: {"name": "Shell 5 (97.6°/560km)", "inc": (80, 105), "alt": (460, 600)},
        },
    },
    "oneweb": {
        "group": "oneweb",
        "pattern": "ONEWEB",
        "operator": "Eutelsat OneWeb",
        "country": "GB",
        "orbit_type": "LEO",
        "shells": {
            0: {"name": "Gen1 (87.9°/1200km)", "inc": (85, 90), "alt": (1100, 1300)},
        },
    },
    "kuiper": {
        "group": "kuiper",
        "pattern": "KUIPER",
        "operator": "Amazon",
        "country": "US",
        "orbit_type": "LEO",
        "shells": {
            0: {"name": "Shell 1 (51.9°/590km)", "inc": (48, 55), "alt": (550, 650)},
            1: {"name": "Shell 2 (33°/610km)", "inc": (0, 38), "alt": (550, 650)},
            2: {"name": "Shell 3 (42°/610km)", "inc": (38, 48), "alt": (550, 650)},
        },
    },
    "qianfan": {
        "group": "qianfan",
        "pattern": "QIANFAN",
        "operator": "Shanghai Spacecom (G60)",
        "country": "CN",
        "orbit_type": "LEO",
        "shells": {
            0: {"name": "Primary (89°/~1160km)", "inc": (85, 95), "alt": (1000, 1300)},
        },
    },
    "hulianwang": {
        "group": "hulianwang",
        "pattern": "HULIANWANG",
        "operator": "China SatNet (GuoWang)",
        "country": "CN",
        "orbit_type": "LEO",
        "shells": {
            0: {"name": "Primary (86.5°)", "inc": (83, 90), "alt": (500, 1300)},
        },
    },
    "iridium": {
        "group": "iridium-NEXT",
        "pattern": "IRIDIUM",
        "operator": "Iridium",
        "country": "US",
        "orbit_type": "LEO",
        "shells": {
            0: {"name": "NEXT (86.4°/780km)", "inc": (84, 88), "alt": (760, 800)},
        },
    },
    "globalstar": {
        "group": "globalstar",
        "pattern": "GLOBALSTAR",
        "operator": "Globalstar",
        "country": "US",
        "orbit_type": "LEO",
        "shells": {
            0: {"name": "Primary (52°/1410km)", "inc": (48, 56), "alt": (1380, 1600)},
        },
    },
    "orbcomm": {
        "group": "orbcomm",
        "pattern": "ORBCOMM",
        "operator": "ORBCOMM",
        "country": "US",
        "orbit_type": "LEO",
        "shells": {
            0: {"name": "Primary", "inc": (0, 110), "alt": (400, 900)},
        },
    },
    "planet": {
        "group": "planet",
        "pattern": "SKYSAT",
        "operator": "Planet Labs",
        "country": "US",
        "orbit_type": "LEO",
        "shells": {
            0: {"name": "SSO (~97°/~500km)", "inc": (94, 100), "alt": (400, 600)},
        },
    },
    "spire": {
        "group": "spire",
        "pattern": "LEMUR",
        "operator": "Spire Global",
        "country": "US",
        "orbit_type": "LEO",
        "shells": {
            0: {"name": "SSO (~97°/~500km)", "inc": (94, 100), "alt": (400, 600)},
        },
    },
    "gps": {
        "group": "gps-ops",
        "pattern": "NAVSTAR",
        "operator": "USSF",
        "country": "US",
        "orbit_type": "MEO",
        "shells": {
            0: {"name": "GPS (55°/20200km)", "inc": (53, 58), "alt": (19500, 20700)},
        },
    },
    "galileo": {
        "group": "galileo",
        "pattern": "GSAT",
        "operator": "EU/ESA",
        "country": "EU",
        "orbit_type": "MEO",
        "shells": {
            0: {"name": "Galileo (56°/23220km)", "inc": (54, 58), "alt": (22800, 23600)},
        },
    },
    "beidou": {
        "group": "beidou",
        "pattern": "BEIDOU",
        "operator": "CNSA",
        "country": "CN",
        "orbit_type": "MEO",
        "shells": {
            0: {"name": "MEO (55°/21500km)", "inc": (53, 58), "alt": (21000, 22500)},
            1: {"name": "IGSO (55°/35800km)", "inc": (53, 58), "alt": (35000, 36500)},
            2: {"name": "GEO (0-5°/35800km)", "inc": (0, 10), "alt": (35000, 36500)},
        },
    },
    "glonass": {
        "group": "glo-ops",
        "pattern": "COSMOS",
        "operator": "Roscosmos",
        "country": "RU",
        "orbit_type": "MEO",
        "shells": {
            0: {"name": "GLONASS (64.8°/19100km)", "inc": (63, 67), "alt": (18800, 19500)},
        },
    },
    "sbas": {
        "group": "sbas",
        "pattern": None,  # Mixed names (EGNOS, WAAS, GAGAN, etc.)
        "operator": "Various",
        "country": "INT",
        "orbit_type": "GEO",
        "shells": {
            0: {"name": "GEO (~0-5°/35800km)", "inc": (0, 10), "alt": (35000, 36500)},
        },
    },
    "ses": {
        "group": "ses",
        "pattern": None,  # Mixed: AMC, NSS, SES, ASTRA
        "operator": "SES",
        "country": "LU",
        "orbit_type": "GEO",
        "shells": {
            0: {"name": "GEO", "inc": (0, 20), "alt": (35000, 36500)},
        },
    },
    "intelsat": {
        "group": "intelsat",
        "pattern": "INTELSAT",
        "operator": "Intelsat",
        "country": "US",
        "orbit_type": "GEO",
        "shells": {
            0: {"name": "GEO", "inc": (0, 20), "alt": (35000, 36500)},
        },
    },
    "eutelsat": {
        "group": "eutelsat",
        "pattern": "EUTELSAT",
        "operator": "Eutelsat",
        "country": "FR",
        "orbit_type": "GEO",
        "shells": {
            0: {"name": "GEO", "inc": (0, 20), "alt": (35000, 36500)},
        },
    },
    "telesat": {
        "group": "telesat",
        "pattern": "TELESAT",
        "operator": "Telesat",
        "country": "CA",
        "orbit_type": "GEO",
        "shells": {
            0: {"name": "GEO", "inc": (0, 20), "alt": (35000, 36500)},
        },
    },
}


GP_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP={group}&FORMAT=json"
FETCH_DELAY = 1.0  # seconds between CelesTrak requests
MAX_RETRIES = 3


def altitude_from_mean_motion(n: float, ecc: float) -> float:
    """Compute perigee altitude from mean motion (rev/day) and eccentricity."""
    if n <= 0:
        return -1.0
    n_rad = n * 2 * math.pi / 86400.0
    a = (MU / (n_rad ** 2)) ** (1.0 / 3.0)
    return a * (1 - ecc) - R_EARTH


def classify_shell(constellation_id: str, inc: float) -> tuple[int, str]:
    """Assign satellite to a shell within its constellation by inclination."""
    shells = CONSTELLATIONS[constellation_id]["shells"]
    for shell_id, shell in shells.items():
        lo, hi = shell["inc"]
        if lo <= inc < hi:
            return shell_id, shell["name"]
    # Default to first defined shell
    first_id = next(iter(shells))
    return first_id, shells[first_id]["name"]


def classify_status(alt: float, inc: float, ecc: float,
                    epoch_age_hours: float, mm_dot: float,
                    constellation_id: str) -> str:
    """Classify satellite operational status from GP orbital elements."""
    shells = CONSTELLATIONS[constellation_id]["shells"]
    orbit_type = CONSTELLATIONS[constellation_id]["orbit_type"]

    # Find the matching shell's altitude band
    shell_id, _ = classify_shell(constellation_id, inc)
    band = shells.get(shell_id, {}).get("alt", (0, 100000))
    min_alt, max_alt = band

    # Decayed: very low altitude or stale epoch + low
    if alt < 150:
        return "decayed"
    if epoch_age_hours > 336 and alt < 250:
        return "decayed"

    # GEO/MEO sats: simpler classification (no raising/deorbiting dynamics)
    if orbit_type in ("GEO", "MEO"):
        if ecc > 0.02:
            return "anomalous"
        if min_alt <= alt <= max_alt:
            return "operational"
        return "non-operational"

    # LEO: full classification with mm_dot
    if ecc > 0.005:
        return "anomalous"
    if min_alt <= alt <= max_alt:
        return "operational"
    if alt > max_alt:
        return "raising"  # above band, drifting/parking
    if alt < min_alt:
        if mm_dot < -0.0001:
            return "raising"
        if mm_dot > 0.01 or alt < 300:
            return "deorbiting"
        if alt >= min_alt - 20:
            return "raising"
        return "raising"

    return "unknown"


def fetch_constellation_gp(constellation_id: str, cdef: dict, now: datetime) -> list[dict]:
    """Fetch GP data for one constellation from CelesTrak and return row dicts."""
    group = cdef["group"]
    url = GP_URL.format(group=group)

    records = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            records = resp.json()
            break
        except Exception as e:
            if attempt < MAX_RETRIES:
                wait = attempt * 2
                print(f"  WARNING: {constellation_id} attempt {attempt}/{MAX_RETRIES}: {e}, retrying in {wait}s...")
                time.sleep(wait)
            else:
                print(f"  WARNING: {constellation_id} ({group}): {e} (gave up after {MAX_RETRIES} attempts)")
                return []

    if not records:
        return []

    rows = []
    for r in records:
        norad_id = r["NORAD_CAT_ID"]
        name = r.get("OBJECT_NAME", "").strip()
        epoch_str = r["EPOCH"]
        if epoch_str.endswith("Z"):
            epoch_str = epoch_str[:-1] + "+00:00"
        epoch = datetime.fromisoformat(epoch_str)
        if epoch.tzinfo is None:
            epoch = epoch.replace(tzinfo=timezone.utc)

        inc = r["INCLINATION"]
        ecc = r["ECCENTRICITY"]
        mm = r["MEAN_MOTION"]
        mm_dot = r["MEAN_MOTION_DOT"]
        alt = altitude_from_mean_motion(mm, ecc)

        if alt < 0 or alt > 50000:
            continue

        intl = r.get("OBJECT_ID", "")
        launch_year = int(intl[:4]) if intl and intl[:4].isdigit() else 0

        shell_id, shell_name = classify_shell(constellation_id, inc)
        epoch_age_hours = (now - epoch).total_seconds() / 3600
        status = classify_status(alt, inc, ecc, epoch_age_hours, mm_dot, constellation_id)

        rows.append({
            "norad_id": norad_id,
            "name": name,
            "constellation": constellation_id,
            "operator": cdef["operator"],
            "country": cdef["country"],
            "orbit_type": cdef["orbit_type"],
            "shell_id": shell_id,
            "shell_name": shell_name,
            "altitude_km": round(alt, 2),
            "inclination": round(inc, 4),
            "eccentricity": ecc,
            "mean_motion": mm,
            "status": status,
            "launch_year": launch_year,
            "epoch_utc": epoch,
        })

    return rows


def generate_readme(df: pd.DataFrame, df_daily: pd.DataFrame) -> str:
    """Generate HF dataset README."""
    total = len(df)
    n_constellations = df["constellation"].nunique()
    n_operational = int((df["status"] == "operational").sum())
    daily_rows = len(df_daily)
    date_range = ""
    if daily_rows > 0:
        d_min = df_daily["date"].min().strftime("%Y-%m-%d")
        d_max = df_daily["date"].max().strftime("%Y-%m-%d")
        date_range = f" spanning {d_min} to {d_max}"

    # Top constellations by size
    top = df.groupby("constellation")["norad_id"].count().sort_values(ascending=False).head(5)
    top_str = ", ".join(f"{c} ({n:,})" for c, n in top.items())

    return f"""---
license: cc-by-4.0
pretty_name: Constellation Census
language:
  - en
description: >-
  Daily census of {n_constellations} active satellite constellations with orbital
  shell classification, tracking {total:,} satellites from CelesTrak GP data.
size_categories:
  - 10K<n<100K
task_categories:
  - tabular-classification
  - time-series-forecasting
tags:
  - open-data
  - space
  - satellites
  - constellation
  - orbital-mechanics
  - tle
  - norad
  - starlink
  - oneweb
  - kuiper
  - gps
  - galileo
  - tabular-data
configs:
  - config_name: latest_satellites
    data_files:
      - split: train
        path: data/latest_satellites.parquet
    default: true
  - config_name: daily_snapshots
    data_files:
      - split: train
        path: data/daily_snapshots.parquet
---

# Constellation Census

*Part of the [Orbital Mechanics Datasets](https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994) collection on Hugging Face.*

![Update Constellation Census](https://github.com/juliensimon/space-datasets/actions/workflows/update-constellation-census.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.constellation-census&label=updated&color=brightgreen)

Daily census of **{n_constellations}** active satellite constellations, tracking
**{total:,}** satellites (**{n_operational:,}** operational). Top constellations:
{top_str}.

## Dataset description

This dataset provides a daily snapshot of all major satellite constellations in
orbit, derived from [CelesTrak](https://celestrak.org/) GP (General Perturbations)
data. Each satellite is classified by constellation, orbital shell, and operational
status. Covers LEO mega-constellations (Starlink, OneWeb, Kuiper, Qianfan,
Hulianwang), navigation systems (GPS, Galileo, BeiDou, GLONASS), communications
fleets (Iridium, Globalstar, ORBCOMM, SES, Intelsat, Eutelsat, Telesat), and
Earth observation (Planet, Spire).

## Config: `latest_satellites`

One row per satellite. Currently **{total:,}** satellites across
**{n_constellations}** constellations.

| Column | Type | Description |
|--------|------|-------------|
| `norad_id` | int32 | NORAD catalog number |
| `name` | string | Object name |
| `constellation` | string | Constellation ID (e.g. "starlink", "oneweb") |
| `operator` | string | Operator name |
| `country` | string | Country code |
| `orbit_type` | string | LEO / MEO / GEO |
| `shell_id` | int | Shell within constellation |
| `shell_name` | string | Human-readable shell name |
| `altitude_km` | float | Perigee altitude in km |
| `inclination` | float | Orbital inclination in degrees |
| `eccentricity` | float | Orbital eccentricity |
| `mean_motion` | float | Mean motion in rev/day |
| `status` | string | operational / raising / deorbiting / decayed / anomalous / non-operational |
| `launch_year` | int | Launch year from COSPAR ID |
| `epoch_utc` | datetime | TLE epoch (UTC) |

## Config: `daily_snapshots`

Per-constellation daily aggregates. Currently **{daily_rows:,}** rows{date_range}.

| Column | Type | Description |
|--------|------|-------------|
| `date` | datetime | Snapshot date (UTC) |
| `constellation` | string | Constellation ID |
| `operator` | string | Operator name |
| `orbit_type` | string | LEO / MEO / GEO |
| `total_count` | int | Total satellites |
| `operational_count` | int | Operational satellites |
| `median_altitude_km` | float | Median altitude in km |
| `median_inclination` | float | Median inclination in degrees |

### Usage

```python
from datasets import load_dataset

# Per-satellite data
ds = load_dataset("juliensimon/constellation-census", "latest_satellites", split="train")
df = ds.to_pandas()

# Constellation sizes
sizes = df.groupby("constellation")["norad_id"].count().sort_values(ascending=False)
print(sizes)

# Daily growth trends
daily = load_dataset("juliensimon/constellation-census", "daily_snapshots", split="train")
df_daily = daily.to_pandas()
starlink_growth = df_daily[df_daily["constellation"] == "starlink"][["date", "total_count"]]
```

## Status classification

| Status | Criteria |
|--------|----------|
| **operational** | Altitude within the constellation's shell band |
| **raising** | Below or above band, orbit changing toward target (LEO only) |
| **deorbiting** | Below band with strong orbital decay (LEO only) |
| **decayed** | Altitude below 150 km, or stale epoch + low altitude |
| **anomalous** | Unusually high eccentricity |
| **non-operational** | MEO/GEO satellite outside expected altitude band |

## Update frequency

Updated **daily at 09:00 UTC** via GitHub Actions.

## Data sources

All orbital data comes from [CelesTrak](https://celestrak.org/) GP data
(NORAD/18th Space Defense Squadron). Constellation membership is determined by
CelesTrak's predefined satellite groups.

## Related datasets

- [starlink-fleet-data](https://huggingface.co/datasets/juliensimon/starlink-fleet-data) — Detailed Starlink-specific analysis with per-shell daily time series
- [space-track-satcat](https://huggingface.co/datasets/juliensimon/space-track-satcat) — Full NORAD satellite catalog
- [space-track-tle-history](https://huggingface.co/datasets/juliensimon/space-track-tle-history) — 232M historical TLEs (1959-present)
- [space-launch-log](https://huggingface.co/datasets/juliensimon/space-launch-log) — Global launch history from GCAT

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/constellation-census) and share feedback in the Community tab!

## Citation

```bibtex
@dataset{{constellation_census,
  author = {{Simon, Julien}},
  title = {{Constellation Census: Daily Satellite Constellation Tracking}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/constellation-census}},
  note = {{Based on NORAD/18th Space Defense Squadron GP data via CelesTrak (Dr. T.S. Kelso)}}
}}
```
"""


def main():
    now = datetime.now(timezone.utc)
    today = pd.Timestamp(now.strftime("%Y-%m-%d"))

    all_rows = []
    seen_norad_ids = set()

    print(f"Fetching {len(CONSTELLATIONS)} constellations from CelesTrak...")

    for cid, cdef in CONSTELLATIONS.items():
        rows = fetch_constellation_gp(cid, cdef, now)
        # Deduplicate: keep first occurrence (constellation ordering is priority)
        new_rows = []
        for r in rows:
            if r["norad_id"] not in seen_norad_ids:
                seen_norad_ids.add(r["norad_id"])
                new_rows.append(r)
        all_rows.extend(new_rows)
        print(f"  {cid:20s} {len(new_rows):6,} satellites")
        time.sleep(FETCH_DELAY)

    df = pd.DataFrame(all_rows)
    df["norad_id"] = df["norad_id"].astype("int32")
    print(f"\nTotal: {len(df):,} satellites across {df['constellation'].nunique()} constellations")

    check_dataset(df, "constellation-census", min_rows=5000,
                  expected_columns=["norad_id", "name", "constellation", "altitude_km",
                                    "inclination", "status", "shell_id"],
                  critical_columns=["norad_id", "altitude_km", "constellation"])

    # Build daily_snapshots: per-constellation aggregates
    daily_rows = []
    for cid in sorted(df["constellation"].unique()):
        cdf = df[df["constellation"] == cid]
        cdef = CONSTELLATIONS.get(cid, {})
        daily_rows.append({
            "date": today,
            "constellation": cid,
            "operator": cdef.get("operator", "Unknown"),
            "orbit_type": cdef.get("orbit_type", "Unknown"),
            "total_count": len(cdf),
            "operational_count": int((cdf["status"] == "operational").sum()),
            "median_altitude_km": round(cdf["altitude_km"].median(), 2),
            "median_inclination": round(cdf["inclination"].median(), 4),
        })
    df_today = pd.DataFrame(daily_rows)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        data_dir = tmp_dir / "data"
        data_dir.mkdir()

        # Save latest_satellites
        latest_path = data_dir / "latest_satellites.parquet"
        df.to_parquet(latest_path, index=False, engine="pyarrow", compression="zstd")
        print(f"  latest_satellites: {len(df):,} rows ({latest_path.stat().st_size / 1024 / 1024:.1f} MB)")

        # Download existing daily_snapshots and append today
        daily_path = data_dir / "daily_snapshots.parquet"
        subprocess.run(
            ["hf", "download", HF_REPO, "data/daily_snapshots.parquet",
             "--repo-type", "dataset", "--local-dir", str(tmp_dir)],
            check=True, capture_output=True, timeout=120,
        )
        if not daily_path.exists():
            print("::error::daily_snapshots.parquet not found after download — aborting to protect historical data")
            sys.exit(1)
        df_existing = pd.read_parquet(daily_path)
        df_existing["date"] = pd.to_datetime(df_existing["date"])
        if len(df_existing) < 10:
            print(f"::error::daily_snapshots has only {len(df_existing)} rows — aborting to protect historical data")
            sys.exit(1)
        df_existing = df_existing[df_existing["date"] != today]
        df_daily = pd.concat([df_existing, df_today], ignore_index=True)
        print(f"  daily_snapshots: appended {today} ({len(df_daily):,} total rows)")

        df_daily.to_parquet(daily_path, index=False, engine="pyarrow", compression="zstd")

        # Stats
        operational = int((df["status"] == "operational").sum())
        n_constellations = df["constellation"].nunique()
        print(f"\n  {operational:,} operational across {n_constellations} constellations")

        (tmp_dir / "README.md").write_text(generate_readme(df, df_daily))

        print("Uploading to HF...")
        commit_msg = (
            f"Update constellation census: {len(df):,} satellites "
            f"({operational:,} operational) across {n_constellations} constellations"
        )
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp_dir), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={len(df)}\n")
    print("Done.")


if __name__ == "__main__":
    main()
