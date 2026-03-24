#!/usr/bin/env python3
"""
Fetch geomagnetic Kp index from NOAA SWPC and upload to HF.

Kp is a 3-hourly index (0-9) measuring geomagnetic disturbance. Incremental:
appends recent SWPC data to existing dataset.
"""

import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset


HF_REPO = "juliensimon/geomagnetic-kp-index"

KP_URL = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"


def fetch_kp():
    """Fetch recent Kp data from NOAA SWPC (30-day rolling window)."""
    print("  Fetching Kp data from SWPC...")
    resp = requests.get(KP_URL, timeout=30)
    resp.raise_for_status()
    raw = resp.json()

    # First row is header: ["time_tag", "Kp", "Kp_fraction", "a_running", "station_count"]
    header = raw[0]
    rows = raw[1:]
    df = pd.DataFrame(rows, columns=header)

    df["time_tag"] = pd.to_datetime(df["time_tag"])
    df = df.rename(columns={
        "time_tag": "datetime",
        "Kp": "kp_value",
        "a_running": "ap_running",
        "station_count": "station_count",
    })

    for col in ["kp_value", "ap_running", "station_count"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Storm classification
    df["storm_level"] = pd.cut(
        df["kp_value"],
        bins=[-float("inf"), 4, 5, 6, 7, 8, float("inf")],
        labels=["quiet", "G1-minor", "G2-moderate", "G3-strong", "G4-severe", "G5-extreme"],
    )

    df = df.sort_values("datetime").reset_index(drop=True)
    print(f"  {len(df):,} readings")
    return df


def load_existing(tmp_dir):
    """Download existing parquet from HF."""
    parquet_path = tmp_dir / "data" / "kp_index.parquet"
    try:
        subprocess.run(
            ["hf", "download", HF_REPO, "data/kp_index.parquet",
             "--repo-type", "dataset", "--local-dir", str(tmp_dir)],
            check=True, capture_output=True, timeout=30,
        )
        if parquet_path.exists():
            df = pd.read_parquet(parquet_path)
            df["datetime"] = pd.to_datetime(df["datetime"])
            print(f"  Loaded existing: {len(df):,} readings")
            return df
    except Exception as e:
        print(f"  No existing data ({e}), starting fresh")
    return None


def generate_readme(df):
    """Generate HF dataset README."""
    n = len(df)
    date_min = df["datetime"].min().strftime("%Y-%m-%d")
    date_max = df["datetime"].max().strftime("%Y-%m-%d")
    max_kp = df["kp_value"].max()
    n_storm = int((df["kp_value"] >= 5).sum())
    avg_kp = df["kp_value"].mean()

    return f"""---
license: cc-by-4.0
pretty_name: "Geomagnetic Kp Index (3-Hourly)"
language:
  - en
description: >-
  3-hourly geomagnetic Kp index from NOAA SWPC, measuring planetary magnetic
  disturbance on a 0-9 scale. Updated daily, growing incrementally.
size_categories:
  - 1K<n<10K
task_categories:
  - time-series-forecasting
  - tabular-classification
tags:
  - open-data
  - space
  - space-weather
  - kp-index
  - geomagnetic
  - noaa
  - magnetosphere
  - aurora
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/kp_index.parquet
---

# Geomagnetic Kp Index (3-Hourly)

![Update Kp Index](https://github.com/juliensimon/space-datasets/actions/workflows/update-kp-index.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['kp-index']&label=updated&color=brightgreen)

3-hourly geomagnetic Kp index from [NOAA SWPC](https://www.swpc.noaa.gov/),
measuring planetary magnetic disturbance. Currently **{n:,}** readings spanning
**{date_min}** to **{date_max}**.

## Dataset description

The Kp index is a quasi-logarithmic scale (0-9) that quantifies geomagnetic
disturbance based on magnetometer readings from 13 ground stations worldwide.
It is the basis for the NOAA G-scale storm classification:

| Kp | NOAA Scale | Effect |
|----|-----------|--------|
| 0-4 | Quiet | No significant effects |
| 5 | G1 Minor | Weak power grid fluctuations, minor satellite impact |
| 6 | G2 Moderate | High-latitude power systems affected, satellite drag increases |
| 7 | G3 Strong | Power grid corrections needed, satellite orientation issues |
| 8 | G4 Severe | Widespread voltage control problems, satellite charging |
| 9 | G5 Extreme | Grid collapse risk, satellite damage, GPS degraded |

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `datetime` | datetime | 3-hour interval start (UTC) |
| `kp_value` | float | Kp index (0.0 to 9.0) |
| `ap_running` | float | Running ap equivalent index |
| `station_count` | float | Number of contributing stations |
| `storm_level` | string | NOAA storm classification (quiet/G1-G5) |

## Quick stats

- **{n:,}** readings ({date_min} to {date_max})
- Average Kp: **{avg_kp:.1f}**, Maximum: **{max_kp:.1f}**
- **{n_storm}** storm-level readings (Kp >= 5)

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/geomagnetic-kp-index", split="train")
df = ds.to_pandas()

# Storm events
storms = df[df["kp_value"] >= 5]
print(f"{{len(storms)}} storm readings")

# Kp time series
df.plot(x="datetime", y="kp_value", title="Kp Index")

# Correlate with solar wind Bz
# Join with juliensimon/solar-wind dataset
```

## Update frequency

Updated **daily at 15:30 UTC** via GitHub Actions. Each run fetches the latest
~30-day window from SWPC and appends new readings.

## Data source

[NOAA Space Weather Prediction Center](https://www.swpc.noaa.gov/products/planetary-k-index).
Kp is derived from magnetometer data at 13 geomagnetic observatories and
maintained by GFZ Potsdam under the International Service of Geomagnetic Indices.

## Related datasets

- [dst-index](https://huggingface.co/datasets/juliensimon/dst-index) — Hourly Dst storm index (complementary)
- [solar-wind](https://huggingface.co/datasets/juliensimon/solar-wind) — Real-time solar wind (Kp driver)
- [space-weather-indices](https://huggingface.co/datasets/juliensimon/space-weather-indices) — Daily Ap, F10.7
- [donki-space-weather-events](https://huggingface.co/datasets/juliensimon/donki-space-weather-events) — CMEs, storms

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Citation

```bibtex
@dataset{{kp_index,
  author = {{Simon, Julien}},
  title = {{Geomagnetic Kp Index (3-Hourly)}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/geomagnetic-kp-index}},
  note = {{Based on NOAA SWPC planetary K-index data, derived from GFZ Potsdam}}
}}
```
"""


def main():
    print("Fetching Kp index from NOAA SWPC...")

    df_new = fetch_kp()

    # Try incremental
    with tempfile.TemporaryDirectory() as probe:
        df_existing = load_existing(Path(probe))

    if df_existing is not None and len(df_existing) > 0:
        df = pd.concat([df_existing, df_new], ignore_index=True)
        df = df.drop_duplicates("datetime", keep="last")
        df = df.sort_values("datetime").reset_index(drop=True)
        print(f"  Merged: {len(df):,} readings ({len(df) - len(df_existing):+,} net new)")
    else:
        df = df_new

    min_rows = 50
    check_dataset(df, "kp-index", min_rows=min_rows,
                  expected_columns=["datetime", "kp_value", "storm_level"],
                  critical_columns=["datetime", "kp_value"])

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        data_dir = tmp_dir / "data"
        data_dir.mkdir()

        out = data_dir / "kp_index.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        print(f"  {out.stat().st_size / 1024:.0f} KB parquet")

        (tmp_dir / "README.md").write_text(generate_readme(df))

        print("Uploading to HF...")
        commit_msg = f"Update Kp index: {len(df):,} readings"
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
