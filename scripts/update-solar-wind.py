#!/usr/bin/env python3
"""
Fetch real-time solar wind data from NOAA SWPC and upload to HF.

Merges plasma (density, speed, temperature) and magnetometer (Bt, Bx/By/Bz GSM)
data from the DSCOVR/ACE L1 monitors. Incremental: appends 7-day rolling window
to existing dataset.
"""

import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset


HF_REPO = "juliensimon/solar-wind"

PLASMA_URL = "https://services.swpc.noaa.gov/products/solar-wind/plasma-7-day.json"
MAG_URL = "https://services.swpc.noaa.gov/products/solar-wind/mag-7-day.json"


def fetch_solar_wind():
    """Fetch and merge plasma + magnetometer 7-day data from SWPC."""
    print("  Fetching plasma data...")
    resp = requests.get(PLASMA_URL, timeout=60)
    resp.raise_for_status()
    plasma_raw = resp.json()
    # First row is header: ["time_tag", "density", "speed", "temperature"]
    df_plasma = pd.DataFrame(plasma_raw[1:], columns=plasma_raw[0])

    print("  Fetching magnetometer data...")
    resp = requests.get(MAG_URL, timeout=60)
    resp.raise_for_status()
    mag_raw = resp.json()
    df_mag = pd.DataFrame(mag_raw[1:], columns=mag_raw[0])

    # Parse time_tag
    df_plasma["time_tag"] = pd.to_datetime(df_plasma["time_tag"])
    df_mag["time_tag"] = pd.to_datetime(df_mag["time_tag"])

    # Convert numeric columns
    for col in ["density", "speed", "temperature"]:
        df_plasma[col] = pd.to_numeric(df_plasma[col], errors="coerce")
    for col in ["bt", "bx_gsm", "by_gsm", "bz_gsm"]:
        df_mag[col] = pd.to_numeric(df_mag[col], errors="coerce")

    # Keep only the columns we want from mag
    df_mag = df_mag[["time_tag", "bt", "bx_gsm", "by_gsm", "bz_gsm"]]

    # Merge on time_tag (outer join to keep all timestamps)
    df = pd.merge(df_plasma, df_mag, on="time_tag", how="outer")
    df = df.sort_values("time_tag").reset_index(drop=True)

    print(f"  {len(df):,} readings ({len(df_plasma):,} plasma, {len(df_mag):,} mag)")
    return df


def load_existing(tmp_dir):
    """Download existing parquet from HF."""
    parquet_path = tmp_dir / "data" / "solar_wind.parquet"
    try:
        subprocess.run(
            ["hf", "download", HF_REPO, "data/solar_wind.parquet",
             "--repo-type", "dataset", "--local-dir", str(tmp_dir)],
            check=True, capture_output=True, timeout=30,
        )
        if parquet_path.exists():
            df = pd.read_parquet(parquet_path)
            df["time_tag"] = pd.to_datetime(df["time_tag"])
            print(f"  Loaded existing: {len(df):,} readings")
            return df
    except Exception as e:
        print(f"  No existing data ({e}), starting fresh")
    return None


def generate_readme(df):
    """Generate HF dataset README."""
    n = len(df)
    date_min = df["time_tag"].min().strftime("%Y-%m-%d")
    date_max = df["time_tag"].max().strftime("%Y-%m-%d")
    avg_speed = df["speed"].mean()
    max_speed = df["speed"].max()
    min_bz = df["bz_gsm"].min()
    n_southward = int((df["bz_gsm"] < 0).sum())

    return f"""---
license: cc-by-4.0
pretty_name: "Real-Time Solar Wind (DSCOVR/ACE)"
language:
  - en
description: >-
  Real-time solar wind plasma and magnetic field measurements from the DSCOVR and ACE
  spacecraft at the L1 Lagrange point, via NOAA SWPC. Updated daily.
size_categories:
  - 10K<n<100K
task_categories:
  - time-series-forecasting
  - tabular-regression
tags:
  - open-data
  - space
  - space-weather
  - solar-wind
  - dscovr
  - ace
  - noaa
  - magnetosphere
  - bz
  - geomagnetic
  - tabular-data
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/solar_wind.parquet
---

# Real-Time Solar Wind

*Part of the [Space Weather Datasets](https://huggingface.co/collections/juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70) collection on Hugging Face.*

![Update Solar Wind](https://github.com/juliensimon/space-datasets/actions/workflows/update-solar-wind.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['solar-wind']&label=updated&color=brightgreen)

Real-time solar wind measurements from [NOAA SWPC](https://www.swpc.noaa.gov/),
combining plasma and magnetic field data from the DSCOVR and ACE spacecraft at the
Sun-Earth L1 Lagrange point. Currently **{n:,}** minute-resolution readings spanning
**{date_min}** to **{date_max}**.

## Dataset description

The solar wind is a continuous stream of charged particles flowing from the Sun.
Its speed, density, and magnetic field orientation (especially Bz) are the primary
drivers of geomagnetic storms. When Bz turns strongly southward (negative), it
couples with Earth's magnetosphere and can trigger storms that affect satellites,
power grids, and GPS.

This dataset is the **missing link** in the Sun-to-Earth causal chain:
solar flare → CME → **solar wind** → Dst/Kp storm → orbital drag.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `time_tag` | datetime | Measurement time (UTC, ~1-minute cadence) |
| `density` | float | Proton density (particles/cm³) |
| `speed` | float | Bulk solar wind speed (km/s) |
| `temperature` | float | Proton temperature (K) |
| `bt` | float | Total magnetic field magnitude (nT) |
| `bx_gsm` | float | Magnetic field Bx in GSM coordinates (nT) |
| `by_gsm` | float | Magnetic field By in GSM coordinates (nT) |
| `bz_gsm` | float | Magnetic field Bz in GSM coordinates (nT) — **key storm driver** |

## Quick stats

- **{n:,}** readings ({date_min} to {date_max})
- Average speed: **{avg_speed:.0f} km/s**, max: **{max_speed:.0f} km/s**
- Minimum Bz: **{min_bz:.1f} nT** ({n_southward:,} southward readings)

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/solar-wind", split="train")
df = ds.to_pandas()

# Solar wind speed time series
df.plot(x="time_tag", y="speed", title="Solar Wind Speed")

# Bz southward events (storm drivers)
southward = df[df["bz_gsm"] < -5]
print(f"{{len(southward)}} readings with Bz < -5 nT")

# Correlate with Dst index
# Join with juliensimon/dst-index on nearest hourly timestamp
```

## Update frequency

Updated **daily at 15:00 UTC** via GitHub Actions. Each run fetches the latest
7-day rolling window from SWPC and appends new readings to the growing dataset.

## Data source

[NOAA Space Weather Prediction Center](https://www.swpc.noaa.gov/products/real-time-solar-wind).
Data from DSCOVR (primary) and ACE (backup) spacecraft at the Sun-Earth L1 point,
~1.5 million km sunward of Earth (~60 minutes ahead of arriving solar wind).

## Related datasets

- [dst-index](https://huggingface.co/datasets/juliensimon/dst-index) — Hourly Dst geomagnetic storm index (driven by solar wind)
- [donki-space-weather-events](https://huggingface.co/datasets/juliensimon/donki-space-weather-events) — CMEs, storms, shocks
- [solar-flare-events](https://huggingface.co/datasets/juliensimon/solar-flare-events) — Individual flare detections
- [space-weather-indices](https://huggingface.co/datasets/juliensimon/space-weather-indices) — Daily Kp, Ap, F10.7

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/solar-wind) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{solar_wind,
  author = {{Simon, Julien}},
  title = {{Real-Time Solar Wind (DSCOVR/ACE)}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/solar-wind}},
  note = {{Based on NOAA SWPC real-time solar wind data from DSCOVR and ACE}}
}}
```
"""


def main():
    now = datetime.now(timezone.utc)
    print("Fetching solar wind data from NOAA SWPC...")

    df_new = fetch_solar_wind()

    # Try incremental
    with tempfile.TemporaryDirectory() as probe:
        df_existing = load_existing(Path(probe))

    if df_existing is not None and len(df_existing) > 0:
        df = pd.concat([df_existing, df_new], ignore_index=True)
        df = df.drop_duplicates("time_tag", keep="last")
        df = df.sort_values("time_tag").reset_index(drop=True)
        print(f"  Merged: {len(df):,} readings ({len(df) - len(df_existing):+,} net new)")
    else:
        df = df_new

    check_dataset(df, "solar-wind", min_rows=5000,
                  expected_columns=["time_tag", "density", "speed", "temperature",
                                    "bt", "bz_gsm"],
                  critical_columns=["time_tag", "speed"])

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        data_dir = tmp_dir / "data"
        data_dir.mkdir()

        out = data_dir / "solar_wind.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        print(f"  {out.stat().st_size / 1024 / 1024:.1f} MB parquet")

        (tmp_dir / "README.md").write_text(generate_readme(df))

        print("Uploading to HF...")
        commit_msg = f"Update solar wind: {len(df):,} readings"
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
