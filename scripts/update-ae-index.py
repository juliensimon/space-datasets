#!/usr/bin/env python3
"""Fetch hourly AE/AU/AL/AO auroral electrojet indices from WDC Kyoto and upload to HF."""

import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset


# Data directory with WDC-format files (minute-resolution, hourly means)
# Realtime data_dir has data from 2021 onward; older data is no longer served
AE_DATA_DIR = "https://wdc.kugi.kyoto-u.ac.jp/ae_realtime/data_dir"
AE_INDICES = ["ae", "al", "ao", "au"]
AE_START_YEAR = 2021  # Oldest year in data_dir
HF_REPO = "juliensimon/auroral-electrojet-index"


def parse_ae_data_file(text, index_name):
    """Parse a WDC minute-resolution AE data file.

    Format: each line is one hour with 60 minute values + 1 hourly mean.
    Line format: AEALAOAU    YYMMDDEHHINDEX QUALITY    val1  val2  ... val60  mean
    We extract the hourly mean (last value on each line).
    """
    records = []
    col_map = {"ae": "ae_index", "au": "au_index",
               "al": "al_index", "ao": "ao_index"}
    col = col_map.get(index_name)
    if not col:
        return []

    for line in text.splitlines():
        line = line.rstrip()
        if len(line) < 40:
            continue

        # Header: AEALAOAU    YYMMDDEHHINDEX QUALITY
        try:
            # Extract date and hour from fixed positions
            # Format: "AEALAOAU    260301E00AE QUICKLK      193   186 ..."
            parts = line.split()
            if len(parts) < 5:
                continue

            # Second field: YYMMDDEHHINDEX (e.g., "260301E00AE")
            date_field = parts[1]
            yy = int(date_field[0:2])
            mm = int(date_field[2:4])
            dd = int(date_field[4:6])
            # Skip 'E' at position 6
            hh = int(date_field[7:9])
            year = 1900 + yy if yy >= 57 else 2000 + yy

            # The hourly mean is the last numeric value on the line
            mean_str = parts[-1].strip()
            if mean_str in ("9999", "99999", ""):
                val = None
            else:
                val = int(mean_str)

            records.append({
                "datetime": datetime(year, mm, dd, hh),
                col: val,
            })
        except (ValueError, IndexError):
            continue

    return records


def fetch_day(year, month, day):
    """Fetch all 4 AE indices for a single day from data_dir."""
    records = {}  # keyed by (year, month, day, hour)
    yy = year % 100
    date_str = f"{yy:02d}{month:02d}{day:02d}"

    for idx in AE_INDICES:
        url = f"{AE_DATA_DIR}/{year}/{month:02d}/{day:02d}/{idx}{date_str}"
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code != 200:
                continue
            parsed = parse_ae_data_file(resp.text, idx)
            for rec in parsed:
                key = (rec["datetime"].year, rec["datetime"].month,
                       rec["datetime"].day, rec["datetime"].hour)
                if key not in records:
                    records[key] = {
                        "datetime": rec["datetime"],
                        "ae_index": None, "au_index": None,
                        "al_index": None, "ao_index": None,
                        "quality": "realtime",
                    }
                # Merge index value
                for col in ("ae_index", "au_index", "al_index", "ao_index"):
                    if col in rec and rec[col] is not None:
                        records[key][col] = rec[col]
        except Exception:
            continue

    return list(records.values())


def list_days(year, month):
    """List available day directories for a year/month."""
    url = f"{AE_DATA_DIR}/{year}/{month:02d}/"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return []
        days = re.findall(r'href="(\d{2})/"', resp.text)
        return [int(d) for d in sorted(set(days))]
    except Exception:
        return []


def load_existing_ae(tmp_dir):
    """Download existing AE parquet from HF. Returns DataFrame or None."""
    parquet_path = tmp_dir / "data" / "ae_index.parquet"
    try:
        subprocess.run(
            ["hf", "download", HF_REPO, "data/ae_index.parquet",
             "--repo-type", "dataset", "--local-dir", str(tmp_dir)],
            check=True, capture_output=True, timeout=30,
        )
        if parquet_path.exists():
            df = pd.read_parquet(parquet_path)
            df["datetime"] = pd.to_datetime(df["datetime"])
            print(f"  Loaded existing: {len(df):,} hourly records")
            return df
    except Exception as e:
        print(f"  Could not load existing ({e}), doing full rebuild")
    return None


def main():
    print("Fetching AE index from WDC Kyoto...")
    now = datetime.utcnow()

    # Try incremental
    import tempfile as _tf
    with _tf.TemporaryDirectory() as probe:
        df_existing = load_existing_ae(Path(probe))

    if df_existing is not None and len(df_existing) > 0:
        # Incremental: fetch current month + previous month
        print("  Incremental mode: fetching recent data only")
        new_records = []

        # Current month
        for day in list_days(now.year, now.month):
            new_records.extend(fetch_day(now.year, now.month, day))
        print(f"  {now.year}/{now.month:02d}: {len(new_records)} records")

        # Previous month (re-fetch for corrections)
        prev_year, prev_month = (now.year, now.month - 1) if now.month > 1 else (now.year - 1, 12)
        prev_count = len(new_records)
        for day in list_days(prev_year, prev_month):
            new_records.extend(fetch_day(prev_year, prev_month, day))
        print(f"  {prev_year}/{prev_month:02d}: {len(new_records) - prev_count} records")

        df_new = pd.DataFrame(new_records)
        if not df_new.empty:
            df_new["datetime"] = pd.to_datetime(df_new["datetime"])
            cutoff = df_new["datetime"].min()
            df_kept = df_existing[df_existing["datetime"] < cutoff]
            df = pd.concat([df_kept, df_new], ignore_index=True)
            print(f"  Merged: {len(df):,} records (kept {len(df_kept):,} + {len(df_new):,} new)")
        else:
            df = df_existing
            print("  No new data")
    else:
        # Full rebuild from data_dir (2021 onward)
        print(f"  Full rebuild from {AE_START_YEAR}...")
        all_records = []
        for year in range(AE_START_YEAR, now.year + 1):
            end_month = now.month if year == now.year else 12
            for month in range(1, end_month + 1):
                days = list_days(year, month)
                for day in days:
                    all_records.extend(fetch_day(year, month, day))
                import time
                time.sleep(0.3)
            print(f"  {year}: {len(all_records):,} records so far")
        df = pd.DataFrame(all_records)

    if df.empty:
        print("::error::No AE data retrieved")
        sys.exit(1)

    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values("datetime").reset_index(drop=True)

    # Remove future/empty rows
    df = df[df["datetime"] <= pd.Timestamp.now()]

    # Ensure numeric columns
    for col in ["ae_index", "au_index", "al_index", "ao_index"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Derived columns
    if "ae_index" in df.columns:
        df["is_active"] = df["ae_index"] >= 500
        df["activity_level"] = pd.cut(
            df["ae_index"],
            bins=[-float("inf"), 100, 300, 500, 1000, float("inf")],
            labels=["quiet", "moderate", "active", "minor_storm", "major_storm"],
        )

    n_total = len(df)
    date_min = df["datetime"].min().strftime("%Y-%m-%d")
    date_max = df["datetime"].max().strftime("%Y-%m-%d")
    n_active = int(df["is_active"].sum()) if "is_active" in df.columns else 0
    max_ae = df["ae_index"].max() if "ae_index" in df.columns else None
    n_prov = int((df["quality"] == "provisional").sum()) if "quality" in df.columns else 0
    n_rt = int((df["quality"] == "realtime").sum()) if "quality" in df.columns else 0

    print(f"  {n_total:,} hourly records ({date_min} to {date_max})")

    check_dataset(df, "ae-index", min_rows=30000,
                  expected_columns=["datetime", "ae_index"],
                  critical_columns=["datetime", "ae_index"])

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "ae_index.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Auroral Electrojet (AE) Index"
language:
  - en
description: "Hourly Auroral Electrojet (AE/AU/AL/AO) indices from WDC Kyoto — measures auroral zone magnetic activity driven by magnetospheric substorms."
task_categories:
  - time-series-forecasting
  - tabular-regression
tags:
  - space
  - geomagnetic
  - auroral-electrojet
  - ae-index
  - space-weather
  - kyoto
  - open-data
  - tabular-data
size_categories:
  - 100K<n<1M
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/ae_index.parquet
    default: true
---

# Auroral Electrojet (AE) Index

*Part of the [Space Weather Datasets](https://huggingface.co/collections/juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70) collection on Hugging Face.*

![Update AE Index](https://github.com/juliensimon/space-datasets/actions/workflows/update-ae-index.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['ae-index']&label=updated&color=brightgreen)

Hourly Auroral Electrojet indices from [WDC Kyoto](https://wdc.kugi.kyoto-u.ac.jp/aeasy/).
Covers **{date_min}** to **{date_max}** with **{n_total:,}** hourly readings.

## Dataset description

The AE index measures auroral zone magnetic activity caused by enhanced ionospheric
currents flowing in the auroral oval. It is derived from geomagnetic variations at
10-13 stations along the auroral zone. The AE family includes four indices:

- **AE** (Auroral Electrojet): overall auroral activity (AU - AL)
- **AU** (Auroral Upper): measures eastward electrojet intensity
- **AL** (Auroral Lower): measures westward electrojet intensity
- **AO** (Auroral Origin): baseline level (AU + AL) / 2

AE complements the Dst index (ring current) by specifically tracking substorm-driven
auroral activity, which is critical for high-latitude communications and power grids.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `datetime` | datetime | Observation time (UTC, hourly) |
| `ae_index` | int | AE value in nanotesla (nT) |
| `au_index` | int | AU value in nanotesla (nT) |
| `al_index` | int | AL value in nanotesla (nT), typically negative |
| `ao_index` | int | AO value in nanotesla (nT) |
| `quality` | string | Data quality: "provisional" or "realtime" |
| `is_active` | bool | True if AE >= 500 nT |
| `activity_level` | string | "quiet" (< 100), "moderate" (100-300), "active" (300-500), "minor_storm" (500-1000), "major_storm" (> 1000) |

## Quick stats

- **{n_total:,}** hourly readings ({date_min} to {date_max})
- **{n_active:,}** active hours (AE >= 500 nT)
- Peak AE: **{max_ae} nT**
- Data quality: {n_prov:,} provisional, {n_rt:,} realtime

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/auroral-electrojet-index", split="train")
df = ds.to_pandas()

# Substorm activity
active = df[df["ae_index"] >= 500].sort_values("ae_index", ascending=False)

# AE time series
df["year"] = df["datetime"].dt.year
annual = df.groupby("year")["ae_index"].mean()

# Compare AE with AL (westward electrojet drives substorms)
import matplotlib.pyplot as plt
storm = df[(df["datetime"] >= "2024-05-10") & (df["datetime"] <= "2024-05-15")]
plt.plot(storm["datetime"], storm["ae_index"], label="AE")
plt.plot(storm["datetime"], storm["al_index"], label="AL")
plt.legend(); plt.ylabel("nT"); plt.title("AE/AL during May 2024 storm")
```

## Data source

[WDC for Geomagnetism, Kyoto](https://wdc.kugi.kyoto-u.ac.jp/aeasy/). Two quality tiers:
- **Provisional**: Visually screened but not final
- **Real-time**: Quicklook values, may be revised

## Update schedule

Daily at 19:00 UTC via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [dst-index](https://huggingface.co/datasets/juliensimon/dst-index) — Dst geomagnetic storm index (ring current)
- [space-weather-indices](https://huggingface.co/datasets/juliensimon/space-weather-indices) — Daily Kp, Ap, F10.7 indices
- [kp-index](https://huggingface.co/datasets/juliensimon/kp-index) — Kp geomagnetic index

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Citation

```bibtex
@dataset{{auroral_electrojet_index,
  author = {{Simon, Julien}},
  title = {{Auroral Electrojet (AE) Index}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/auroral-electrojet-index}}
}}
```

### Data source

[WDC for Geomagnetism, Kyoto](https://wdc.kugi.kyoto-u.ac.jp/aeasy/)

## License

MIT (pipeline code). AE data: free for non-commercial use per WDC Kyoto terms.
""")

        print("Uploading to HF...")
        commit_msg = f"Update AE index: {n_total:,} hourly readings"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
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
