#!/usr/bin/env python3
"""Fetch CelesTrak consolidated space weather data and upload to HF."""

import io
import os
import re
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset


HF_REPO = "juliensimon/celestrak-space-weather"

SW_URL = "https://celestrak.org/SpaceData/SW-All.csv"


def main():
    print("Fetching CelesTrak consolidated space weather data...")

    resp = requests.get(SW_URL, timeout=60)
    resp.raise_for_status()

    # Skip comment lines starting with #
    lines = resp.text.splitlines()
    data_lines = [line for line in lines if not line.startswith("#")]
    clean_text = "\n".join(data_lines)

    df = pd.read_csv(io.StringIO(clean_text))
    print(f"  {len(df):,} rows")

    # Rename columns to snake_case
    df.columns = [c.lower().replace(".", "_") for c in df.columns]
    # Ensure date column exists
    if "date" not in df.columns:
        for col in df.columns:
            if "date" in col.lower():
                df = df.rename(columns={col: "date"})
                break

    # Parse date
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")

    # Convert numeric columns
    for col in df.columns:
        if col == "date":
            continue
        if df[col].dtype == object:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.sort_values("date").reset_index(drop=True)

    check_dataset(df, "celestrak-sw", min_rows=20000,
                  expected_columns=["date"],
                  critical_columns=["date"])

    # Stats for README
    n = len(df)
    n_cols = len(df.columns)
    date_min = df["date"].min().strftime("%Y-%m-%d") if "date" in df.columns else "N/A"
    date_max = df["date"].max().strftime("%Y-%m-%d") if "date" in df.columns else "N/A"

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "celestrak_space_weather.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        # Build column table for README
        col_rows = []
        for col in df.columns:
            dtype = str(df[col].dtype)
            col_rows.append(f"| `{col}` | {dtype} |")
        col_table = "\n".join(col_rows)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "CelesTrak Consolidated Space Weather"
language:
  - en
description: >-
  CelesTrak consolidated space weather data — daily Kp, Ap, F10.7, and solar/geomagnetic
  indices used by SGP4/SDP4 propagators, atmospheric models (JB2008, NRLMSISE), and
  conjunction screening. {n:,} daily records from {date_min} to {date_max}.
size_categories:
  - 10K<n<100K
task_categories:
  - tabular-regression
  - time-series-forecasting
tags:
  - space
  - space-weather
  - celestrak
  - sgp4
  - atmospheric-drag
  - orbit-propagation
  - open-data
  - tabular-data
  - parquet
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/celestrak_space_weather.parquet
---

# CelesTrak Consolidated Space Weather

*Part of the [Space Weather Datasets](https://huggingface.co/collections/juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70) collection on Hugging Face.*

![Update CelesTrak SW](https://github.com/juliensimon/space-datasets/actions/workflows/update-celestrak-sw.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$["celestrak-sw"]&label=updated&color=brightgreen)

CelesTrak consolidated space weather data — **THE** file every orbit propagator needs.
**{n:,}** daily records from **{date_min}** to **{date_max}**, with {n_cols} columns of
solar and geomagnetic indices.

## Dataset description

This dataset contains the consolidated space weather data file maintained by CelesTrak
(Dr. T.S. Kelso). It includes daily values of Kp indices (8 three-hour values per day),
Ap indices, F10.7 solar radio flux, and other solar/geomagnetic parameters essential for:

- **SGP4/SDP4 orbit propagation** — atmospheric drag modeling
- **Atmospheric density models** — JB2008, NRLMSISE-00, DTM
- **Conjunction screening** — collision avoidance maneuver planning
- **Space weather research** — solar cycle analysis, geomagnetic storm studies

The CelesTrak space weather file, maintained by Dr. T.S. Kelso, is the de facto standard input file for operational orbit determination and propagation in the space surveillance community. It consolidates data from multiple agencies -- NOAA SWPC for Kp/Ap indices and solar flux, GFZ Potsdam for definitive geomagnetic indices, and the NRC Herzberg Institute for F10.7 measurements -- into a single, consistently formatted daily time series. The file includes both historical observations and near-term predictions (typically 45 days ahead), using the same format conventions expected by legacy Fortran propagators and modern Python/C++ SGP4 implementations alike.

For orbit propagation, the key parameters are the daily and 3-hourly Ap indices (which drive geomagnetic heating in thermospheric density models) and the F10.7 solar radio flux with its 81-day running averages (which drive solar EUV heating). The NRLMSISE-00 model, for example, requires daily Ap, the 3-hourly Ap for the current and preceding 33 hours, daily F10.7, and the 81-day centered average F10.7bar. JB2008 uses additional solar indices (S10.7, M10.7, Y10.7) that are available in extended versions of this file. Errors in these space weather inputs propagate directly into drag coefficient estimates, making the quality and timeliness of this data critical for conjunction assessment and collision avoidance maneuvers.

The dataset spans the full modern era of satellite operations, with the historical record reaching back to 1957 (International Geophysical Year). This long baseline captures multiple complete solar cycles (cycles 19 through 25), enabling statistical studies of solar cycle variability and its impact on the orbital environment. The inclusion of predicted values supports operational planning for satellite constellation managers who need to anticipate drag conditions for orbit maintenance scheduling.

## Schema

| Column | Type |
|--------|------|
{col_table}

## Quick stats

- **{n:,}** daily records
- Date range: **{date_min}** to **{date_max}**
- **{n_cols}** columns

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/celestrak-space-weather", split="train")
df = ds.to_pandas()

# Recent space weather
print(df.tail(10))

# Plot F10.7 solar flux over time
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(14, 4))
ax.plot(df["date"], df.get("f10_7_obs", df.iloc[:, -1]), linewidth=0.5)
ax.set_xlabel("Date")
ax.set_ylabel("F10.7 (SFU)")
ax.set_title("Solar Radio Flux (F10.7)")
```

## Update frequency

Updated **daily at 12:00 UTC** via GitHub Actions.

## Data source

[CelesTrak Space Data](https://celestrak.org/SpaceData/) (Dr. T.S. Kelso).
Original data from NOAA SWPC, USAF, and other agencies.

## Related datasets

- [kp-index](https://huggingface.co/datasets/juliensimon/kp-index) -- GFZ Potsdam Kp geomagnetic index
- [dst-index](https://huggingface.co/datasets/juliensimon/dst-index) -- WDC Kyoto Dst geomagnetic index
- [solar-wind](https://huggingface.co/datasets/juliensimon/solar-wind) -- DSCOVR real-time solar wind
- [f107-index](https://huggingface.co/datasets/juliensimon/f107-index) -- NRCan F10.7 solar radio flux

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/celestrak-space-weather) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{celestrak_space_weather,
  author = {{Simon, Julien}},
  title = {{CelesTrak Consolidated Space Weather}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/celestrak-space-weather}},
  note = {{Based on CelesTrak Space Data (Dr. T.S. Kelso)}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update CelesTrak space weather: {n:,} records"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={n}\n")
    print("Done.")


if __name__ == "__main__":
    main()
