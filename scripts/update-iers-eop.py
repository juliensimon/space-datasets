#!/usr/bin/env python3
"""Fetch IERS Earth Orientation Parameters and upload to HF."""

import io
import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset


IERS_URL = "https://datacenter.iers.org/data/csv/finals2000A.data.csv"
HF_REPO = "juliensimon/iers-earth-orientation"


def main():
    print("Fetching IERS Earth Orientation Parameters...")
    resp = requests.get(IERS_URL, timeout=120)
    resp.raise_for_status()

    # IERS CSV uses semicolons as separator
    try:
        df = pd.read_csv(io.StringIO(resp.text), sep=';')
    except Exception:
        df = pd.read_csv(io.StringIO(resp.text))

    print(f"  {len(df):,} rows, columns: {list(df.columns)[:10]}...")

    # Create date column from Year/Month/Day if present
    year_col = [c for c in df.columns if c.strip().lower() == 'year']
    month_col = [c for c in df.columns if c.strip().lower() == 'month']
    day_col = [c for c in df.columns if c.strip().lower() == 'day']

    if year_col and month_col and day_col:
        df["date"] = pd.to_datetime(
            df[year_col[0]].astype(int).astype(str) + "-" +
            df[month_col[0]].astype(int).astype(str).str.zfill(2) + "-" +
            df[day_col[0]].astype(int).astype(str).str.zfill(2),
            errors="coerce",
        )

    # Build rename mapping (guard all column accesses)
    rename_map = {}
    for col in df.columns:
        cl = col.strip().lower()
        if cl == "mjd":
            rename_map[col] = "mjd"
        elif cl in ("x_pole", "x", "x_arcsec"):
            rename_map[col] = "x_pole_arcsec"
        elif cl in ("y_pole", "y", "y_arcsec"):
            rename_map[col] = "y_pole_arcsec"
        elif cl in ("sigma_x_pole",):
            rename_map[col] = "sigma_x_pole_arcsec"
        elif cl in ("sigma_y_pole",):
            rename_map[col] = "sigma_y_pole_arcsec"
        elif cl in ("ut1-utc", "ut1_utc"):
            rename_map[col] = "ut1_utc_sec"
        elif cl in ("sigma_ut1-utc",):
            rename_map[col] = "sigma_ut1_utc_sec"
        elif cl in ("lod",):
            rename_map[col] = "lod_ms"
        elif cl in ("dx",):
            rename_map[col] = "dx_mas"
        elif cl in ("dy",):
            rename_map[col] = "dy_mas"

    if rename_map:
        df = df.rename(columns=rename_map)

    # Convert numeric columns
    for col in ["mjd", "x_pole_arcsec", "y_pole_arcsec", "ut1_utc_sec",
                "lod_ms", "dx_mas", "dy_mas"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.sort_values("date").reset_index(drop=True) if "date" in df.columns else df

    check_dataset(df, "iers-eop", min_rows=10000,
                  expected_columns=["date", "x_pole_arcsec", "y_pole_arcsec", "ut1_utc_sec"],
                  critical_columns=["date", "x_pole_arcsec", "y_pole_arcsec"])

    # Stats for README
    n = len(df)
    date_min = df["date"].min().strftime("%Y-%m-%d") if "date" in df.columns else "N/A"
    date_max = df["date"].max().strftime("%Y-%m-%d") if "date" in df.columns else "N/A"

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "iers_earth_orientation.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "IERS Earth Orientation Parameters"
language:
  - en
description: >-
  Earth Orientation Parameters (EOP) from the IERS finals2000A series.
  Includes polar motion, UT1-UTC, and nutation offsets. Updated daily.
size_categories:
  - 10K<n<100K
task_categories:
  - tabular-regression
tags:
  - space
  - earth-orientation
  - iers
  - geodesy
  - ut1
  - polar-motion
  - open-data
  - tabular-data
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/iers_earth_orientation.parquet
---

# IERS Earth Orientation Parameters

*Part of the [Space Weather Datasets](https://huggingface.co/collections/juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70) collection on Hugging Face.*

![Update IERS EOP](https://github.com/juliensimon/space-datasets/actions/workflows/update-iers-eop.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.iers-eop&label=updated&color=brightgreen)

Earth Orientation Parameters from the IERS finals2000A series, spanning **{date_min}** to
**{date_max}**. Currently **{n:,}** daily records.

## Dataset description

Earth Orientation Parameters (EOP) describe the irregularities in Earth's rotation and
the motion of its poles. These parameters are essential for transforming between
celestial and terrestrial reference frames, which is critical for:

- **Satellite operations**: precise orbit determination and manoeuvre planning
- **GPS/GNSS**: sub-centimetre positioning requires accurate UT1-UTC and polar motion
- **Precise pointing**: telescope and antenna tracking, deep-space navigation
- **Geodesy**: monitoring Earth's rotation rate, polar wander, and length of day

The IERS finals2000A series combines observed values (from VLBI, SLR, GPS) with
predictions extending ~1 year into the future.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `date` | datetime | Calendar date (UTC) |
| `mjd` | float64 | Modified Julian Date |
| `x_pole_arcsec` | float64 | Pole coordinate x (arcseconds) |
| `y_pole_arcsec` | float64 | Pole coordinate y (arcseconds) |
| `ut1_utc_sec` | float64 | UT1-UTC difference (seconds) |
| `lod_ms` | float64 | Length of Day excess (milliseconds) |
| `dx_mas` | float64 | Celestial pole offset dX (milliarcseconds) |
| `dy_mas` | float64 | Celestial pole offset dY (milliarcseconds) |

## Quick stats

- **{n:,}** daily records ({date_min} to {date_max})

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/iers-earth-orientation", split="train")
df = ds.to_pandas()

# Recent UT1-UTC values
recent = df[df["date"] > "2025-01-01"].sort_values("date")
print(recent[["date", "ut1_utc_sec", "x_pole_arcsec", "y_pole_arcsec"]])

# Polar motion scatter plot
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(8, 8))
ax.scatter(df["x_pole_arcsec"], df["y_pole_arcsec"], s=0.5, alpha=0.3)
ax.set_xlabel("x pole (arcsec)")
ax.set_ylabel("y pole (arcsec)")
ax.set_title("Polar Motion")
plt.show()
```

## Data source

[International Earth Rotation and Reference Systems Service (IERS)](https://www.iers.org/)
finals2000A data series from the IERS Earth Orientation Centre.

## Update schedule

Daily at 13:00 UTC via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/iers-earth-orientation) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{iers_earth_orientation,
  author = {{Simon, Julien}},
  title = {{IERS Earth Orientation Parameters}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/iers-earth-orientation}},
  note = {{Based on IERS finals2000A Earth Orientation Parameters}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update IERS EOP: {n:,} records"
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
