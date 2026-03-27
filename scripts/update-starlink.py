#!/usr/bin/env python3
"""
Fetch latest Starlink TLEs from CelesTrak, classify, aggregate, and upload to HF.

This is a lightweight daily updater — it fetches the current constellation snapshot,
not historical data. For historical backfill, use the bulk ingestion scripts in
the starlink-viz repo.
"""

import math
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset


CELESTRAK_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=json"
HF_REPO = "juliensimon/starlink-fleet-data"

MU = 398600.4418
R_EARTH = 6371.0

SHELL_NAMES = {
    0: "Shell 1 (33° / 328km)",
    1: "Shell 2 (43° / 340km)",
    2: "Shell 3 (53° / 550km)",
    3: "Shell 4 (70° / 570km)",
    4: "Shell 5 (97.6° / 560km)",
}

# Operational altitude bands per shell [min, max] in km

# Synced from starlink-viz src/lib/config.ts SHELL_ALT_BANDS
SHELL_ALT_BANDS = {
    0: (460, 570),   # 33° — Gen2, deploying at ~480-530 km, target 328 km (will lower)
    1: (460, 570),   # 43° — Gen2, deploying at ~480-530 km, target 340 km (will lower)
    2: (460, 570),   # 53° — Gen1 at 480-490 + 540-560 km
    3: (460, 910),   # 70° — wide range, some at ~880-900 km
    4: (460, 600),   # 97.6° — observed 550-590 km
}


def altitude_from_mean_motion(n: float, ecc: float) -> float:
    if n <= 0:
        return -1.0
    n_rad = n * 2 * math.pi / 86400.0
    a = (MU / (n_rad ** 2)) ** (1.0 / 3.0)
    return a * (1 - ecc) - R_EARTH


def get_shell_id(inc: float) -> int:
    if inc < 38:
        return 0
    if inc < 48:
        return 1
    if inc < 60:
        return 2
    if inc < 80:
        return 3
    return 4


def classify_status(
    alt: float, inc: float, ecc: float,
    epoch_age_hours: float, mm_dot: float,
) -> str:
    """Single-snapshot status classification.

    Without altitude history, we use mean_motion_dot (orbital decay rate)
    as a proxy for raising vs deorbiting:
      mm_dot > 0  →  orbit shrinking (natural drag or active deorbit)
      mm_dot < 0  →  orbit growing (active raising via thrust)

    Starlink deployment: satellites are inserted at a parking orbit
    (often ~300-530km) then raise to their operational altitude using
    ion thrusters. Shells 1-2 (33°/43°) operate at ~330-350km but are
    deployed at ~490-530km and lower down. All other shells raise up.
    """
    shell_id = get_shell_id(inc)
    band = SHELL_ALT_BANDS.get(shell_id, (0, 0))
    min_alt, max_alt = band

    # Decayed: very low or stale epoch + low altitude
    if alt < 150:
        return "decayed"
    if epoch_age_hours > 336 and alt < 250:  # 14 days stale + low
        return "decayed"

    # Anomalous: high eccentricity
    if ecc > 0.005:
        return "anomalous"

    # Operational: within shell altitude band
    if min_alt <= alt <= max_alt:
        return "operational"

    # Above the band — in parking/drift orbit, lowering to operational alt
    # (common for Shells 1-2 which operate at ~330-350km but deploy at ~490-530km)
    if alt > max_alt:
        # mm_dot > 0 means orbit shrinking → actively lowering to operational alt
        if mm_dot > 0:
            return "raising"
        # mm_dot ~ 0 or slightly negative: just deployed, not yet maneuvering
        return "raising"

    # Below the band — raising or deorbiting?
    if alt < min_alt:
        # mm_dot < 0 means orbit is growing = raising
        if mm_dot < -0.0001:
            return "raising"
        # Actively deorbiting: strong positive mm_dot or very low altitude
        if mm_dot > 0.01 or alt < 300:
            return "deorbiting"
        # Close to band (within 20km), unclear direction
        if alt >= min_alt - 20:
            return "raising"
        return "raising"  # below band, assume still raising

    return "unknown"


def is_isl_capable(inc: float, launch_year: int) -> bool:
    shell = get_shell_id(inc)
    if shell == 4:
        return launch_year >= 2022
    if shell == 2:
        return launch_year >= 2022
    if shell == 3:
        return launch_year >= 2022
    if shell == 1:
        return launch_year >= 2023
    if shell == 0:
        return launch_year >= 2024
    return False


def generate_readme(df_latest: pd.DataFrame, df_daily: pd.DataFrame, active: int) -> str:
    """Generate a comprehensive README.md for the HF dataset."""
    total = len(df_latest)
    daily_rows = len(df_daily)
    date_range_start = df_daily["date"].min().strftime("%Y-%m-%d") if len(df_daily) > 0 else "N/A"
    date_range_end = df_daily["date"].max().strftime("%Y-%m-%d") if len(df_daily) > 0 else "N/A"

    raising = int((df_latest["status"] == "raising").sum())
    deorbiting = int((df_latest["status"] == "deorbiting").sum())
    decayed = int((df_latest["status"] == "decayed").sum())
    isl_count = int(df_latest["is_isl_capable"].sum())

    return f"""---
license: cc-by-4.0
pretty_name: "Starlink Constellation Fleet Data"
language:
  - en
description: "Daily snapshots of SpaceX's Starlink mega-constellation — satellite count, orbital shells, and operational status from CelesTrak."
size_categories:
  - 100K<n<1M
task_categories:
  - time-series-forecasting
  - tabular-classification
tags:
  - space
  - starlink
  - satellites
  - orbital-mechanics
  - tle
  - spacex
  - constellation
  - open-data
  - norad
  - leo
  - mega-constellation
  - tabular-data
configs:
  - config_name: daily_snapshots
    data_files: data/daily_snapshots.parquet
---

# Starlink Fleet Data

*Part of the [Orbital Mechanics Datasets](https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994) collection on Hugging Face.*

![Update Starlink Fleet](https://github.com/juliensimon/space-datasets/actions/workflows/update-starlink.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.starlink&label=updated&color=brightgreen)

Daily health snapshots of the SpaceX Starlink constellation, derived from
[CelesTrak](https://celestrak.org/) GP (General Perturbations) data.
Currently tracking **{total:,}** satellites (**{active:,}** operational,
**{raising:,}** raising, **{deorbiting:,}** deorbiting, **{isl_count:,}** ISL-capable).

## Dataset description

This dataset tracks the Starlink constellation's health over time through
**daily aggregate snapshots per orbital shell**. Each day, the pipeline fetches
the latest TLE/GP data from CelesTrak, classifies every satellite's operational
status using orbital mechanics heuristics, and appends per-shell summary
statistics to a growing time series.

The `daily_snapshots` config contains historical daily aggregates — one row per
shell per day — enabling trend analysis of constellation growth, shell fill
rates, deployment cadence, and ISL (inter-satellite laser link) rollout.

## Config: `daily_snapshots`

Historical daily aggregates per orbital shell. Currently **{daily_rows:,}** rows
spanning {date_range_start} to {date_range_end}.

| Column | Type | Description |
|--------|------|-------------|
| `date` | datetime | Snapshot date (UTC) |
| `shell_id` | int | Shell identifier (0-4) |
| `shell_name` | string | Human-readable shell name, e.g. "Shell 3 (53deg / 550km)" |
| `total_count` | int | Total satellites in this shell |
| `operational_count` | int | Satellites at operational altitude |
| `raising_count` | int | Satellites actively raising orbit |
| `deorbiting_count` | int | Satellites deorbiting |
| `isl_operational_count` | int | ISL-capable satellites in this shell |
| `new_launches` | int | New launches detected this day (reserved) |

### Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/starlink-fleet-data", "daily_snapshots", split="train")
df = ds.to_pandas()

# Constellation growth over time
growth = df.groupby("date")["operational_count"].sum()
print(growth.tail(10))

# Per-shell fill rates
latest = df[df["date"] == df["date"].max()]
for _, row in latest.iterrows():
    print(f"{{row['shell_name']}}: {{row['operational_count']}} / {{row['total_count']}}")
```

## Status classification

Each satellite is classified into one of six statuses based on its orbital
parameters and a single-snapshot heuristic:

| Status | Criteria |
|--------|----------|
| **operational** | Altitude within the shell's operational band |
| **raising** | Below or above operational band, orbit changing toward target |
| **deorbiting** | Below operational band with strong positive mean motion derivative (orbit shrinking) or very low altitude (<300 km) |
| **decayed** | Altitude below 150 km, or stale epoch (>14 days) with altitude below 250 km |
| **anomalous** | Eccentricity > 0.005 (unusual for Starlink's near-circular orbits) |
| **unknown** | Does not match any classification rule |

The classifier uses `mean_motion_dot` (first derivative of mean motion) as a
proxy for orbital maneuvering direction: positive values indicate orbit decay
(shrinking), negative values indicate active thrust (raising).

## Shell assignment

Satellites are assigned to shells by inclination:

| Shell | Inclination | Target altitude | Inclination range |
|-------|-------------|-----------------|-------------------|
| Shell 1 (33deg) | 33.0deg | 328 km | < 38deg |
| Shell 2 (43deg) | 43.0deg | 340 km | 38deg - 48deg |
| Shell 3 (53deg) | 53.0deg | 550 km | 48deg - 60deg |
| Shell 4 (70deg) | 70.0deg | 570 km | 60deg - 80deg |
| Shell 5 (97.6deg) | 97.6deg | 560 km | > 80deg |

## Update frequency

Updated **daily at 08:00 UTC** via GitHub Actions. Each run fetches the current
CelesTrak GP snapshot, classifies all satellites, and appends the day's
per-shell aggregates to `daily_snapshots.parquet`. Re-runs on the same day are
idempotent (existing rows for that date are replaced).

## Data source

All orbital data comes from [CelesTrak](https://celestrak.org/) GP data
(NORAD/18th Space Defense Squadron). Only objects with names matching
`STARLINK-*` are included (Starshield, debris, and unidentified objects are
excluded).

## Related datasets

- [space-track-tle-history](https://huggingface.co/datasets/juliensimon/space-track-tle-history) — 232M historical TLEs (1959-present)
- [space-track-satcat](https://huggingface.co/datasets/juliensimon/space-track-satcat) — NORAD satellite catalog
- [space-launch-log](https://huggingface.co/datasets/juliensimon/space-launch-log) — Global launch history from GCAT
- [starlink-ground-stations](https://huggingface.co/datasets/juliensimon/starlink-ground-stations) — Starlink gateway and PoP locations

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/starlink-fleet-data) and share feedback in the Community tab!

## Citation

```bibtex
@dataset{{starlink_fleet_data,
  author = {{Simon, Julien}},
  title = {{Starlink Fleet Data: Daily Constellation Health Snapshots}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/starlink-fleet-data}},
  note = {{Based on NORAD/18th Space Defense Squadron GP data via CelesTrak (Dr. T.S. Kelso)}}
}}
```
"""


def main():
    print("Fetching Starlink TLEs from CelesTrak...")
    resp = requests.get(CELESTRAK_URL, timeout=60)
    resp.raise_for_status()
    records = resp.json()
    print(f"  {len(records):,} satellites")

    now = datetime.now(timezone.utc)
    rows = []

    for r in records:
        name = r.get("OBJECT_NAME", "")
        if not name.startswith("STARLINK"):
            continue

        norad_id = r["NORAD_CAT_ID"]
        epoch_str = r["EPOCH"]
        if epoch_str.endswith("Z"):
            epoch_str = epoch_str[:-1] + "+00:00"
        epoch = datetime.fromisoformat(epoch_str)
        if epoch.tzinfo is None:
            epoch = epoch.replace(tzinfo=timezone.utc)
        inc = r["INCLINATION"]
        ecc = r["ECCENTRICITY"]
        mm = r["MEAN_MOTION"]
        alt = altitude_from_mean_motion(mm, ecc)

        if alt < 0 or alt > 2000:
            continue

        intl = r.get("OBJECT_ID", "")
        # OBJECT_ID is COSPAR format: "2024-123A" (4-digit year)
        launch_year = int(intl[:4]) if intl and intl[:4].isdigit() else 0

        shell_id = get_shell_id(inc)
        mm_dot = r["MEAN_MOTION_DOT"]
        epoch_age_hours = (now - epoch).total_seconds() / 3600

        status = classify_status(alt, inc, ecc, epoch_age_hours, mm_dot)

        rows.append({
            "norad_id": norad_id,
            "name": name,
            "epoch_utc": epoch,
            "inclination": round(inc, 4),
            "raan": round(r["RA_OF_ASC_NODE"], 4),
            "eccentricity": ecc,
            "mean_motion": mm,
            "mean_motion_dot": mm_dot,
            "altitude_km": round(alt, 2),
            "launch_year": launch_year,
            "shell_id": shell_id,
            "shell_name": SHELL_NAMES.get(shell_id, "Unknown"),
            "status": status,
            "is_isl_capable": is_isl_capable(inc, launch_year),
        })

    df = pd.DataFrame(rows)
    print(f"  {len(df):,} Starlink satellites processed")

    check_dataset(df, "starlink", min_rows=5000,
        expected_columns=["norad_id", "name", "altitude_km", "shell_id",
                          "inclination", "status"],
        critical_columns=["norad_id", "altitude_km"])

    # Build latest_satellites
    df_latest = df.sort_values("epoch_utc").drop_duplicates("norad_id", keep="last")
    df_latest["epoch_ts"] = df_latest["epoch_utc"].astype("int64") // 10**9

    # Build daily_snapshots: per-shell aggregates for today
    today = pd.Timestamp(now.strftime("%Y-%m-%d"))
    daily_rows = []
    for sid in sorted(df_latest["shell_id"].unique()):
        shell = df_latest[df_latest["shell_id"] == sid]
        daily_rows.append({
            "date": today,
            "shell_id": int(sid),
            "shell_name": SHELL_NAMES.get(int(sid), "Unknown"),
            "total_count": len(shell),
            "operational_count": int((shell["status"] == "operational").sum()),
            "raising_count": int((shell["status"] == "raising").sum()),
            "deorbiting_count": int((shell["status"] == "deorbiting").sum()),
            "isl_operational_count": int((shell["is_isl_capable"] & (shell["status"] == "operational")).sum()),
            "new_launches": 0,
        })
    df_today = pd.DataFrame(daily_rows)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        data_dir = tmp_dir / "data"
        data_dir.mkdir()

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
        if len(df_existing) < 100:
            print(f"::error::daily_snapshots has only {len(df_existing)} rows — aborting to protect historical data")
            sys.exit(1)
        # Remove any existing rows for today (idempotent re-runs)
        df_existing = df_existing[df_existing["date"] != today]
        df_daily = pd.concat([df_existing, df_today], ignore_index=True)
        print(f"  daily_snapshots: appended {today} ({len(df_daily):,} total rows)")

        df_daily.to_parquet(daily_path, index=False, engine="pyarrow", compression="zstd")

        active = len(df_latest[df_latest["status"] == "operational"])
        print(f"  {active:,} operational, {len(df_latest):,} total")

        (tmp_dir / "README.md").write_text(generate_readme(df_latest, df_daily, active))

        raising = int((df_latest["status"] == "raising").sum())
        deorbiting = int((df_latest["status"] == "deorbiting").sum())

        print("Uploading to HF...")
        commit_msg = (
            f"Update Starlink fleet: {len(df_latest):,} satellites "
            f"({active:,} operational, {raising:,} raising, "
            f"{deorbiting:,} deorbiting)"
        )
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp_dir), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={len(df_latest)}\n")
    print("Done.")


if __name__ == "__main__":
    main()
