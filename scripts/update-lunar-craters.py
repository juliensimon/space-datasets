#!/usr/bin/env python3
"""Fetch Lunar crater database (Robbins 2019) and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from validate import check_dataset

DATA_URL = "https://astropedia.astrogeology.usgs.gov/download/Moon/Research/Craters/lunar_crater_database_robbins_2019.csv"
HF_REPO = "juliensimon/lunar-craters-robbins"

KEEP_COLS = {
    "CRATER_ID": "crater_id",
    "LAT_CIRC_IMG": "latitude_deg",
    "LON_CIRC_IMG": "longitude_deg",
    "DIAM_CIRC_IMG": "diameter_km",
    "DEPTH_RIM_TOPO": "depth_km",
    "DEPTH_FLOOR_TOPO": "floor_elevation_km",
    "DEPTH_RIM_SD": "depth_rim_sd_km",
}

NUMERIC_COLS = ["latitude_deg", "longitude_deg", "diameter_km", "depth_km",
                "floor_elevation_km", "depth_rim_sd_km"]


def size_class(diameter):
    if pd.isna(diameter):
        return None
    if diameter < 5:
        return "small"
    if diameter <= 20:
        return "medium"
    if diameter <= 100:
        return "large"
    return "giant"


def main():
    print("Fetching Lunar crater database (Robbins 2019)...")
    df = pd.read_csv(DATA_URL)
    print(f"  {len(df):,} raw rows")

    # Keep and rename columns
    available = {c: v for c, v in KEEP_COLS.items() if c in df.columns}
    df = df[list(available.keys())].rename(columns=available)

    # Type conversions
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Derived column
    df["size_class"] = df["diameter_km"].apply(size_class)

    # Stats
    n_total = len(df)
    n_small = int((df["size_class"] == "small").sum())
    n_medium = int((df["size_class"] == "medium").sum())
    n_large = int((df["size_class"] == "large").sum())
    n_giant = int((df["size_class"] == "giant").sum())
    diam_min = df["diameter_km"].min()
    diam_max = df["diameter_km"].max()

    # Validate
    check_dataset(
        df,
        "lunar-craters",
        min_rows=1_000_000,
        expected_columns=["crater_id", "latitude_deg", "longitude_deg", "diameter_km"],
        critical_columns=["crater_id", "latitude_deg", "longitude_deg", "diameter_km"],
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "lunar_craters.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Lunar Crater Database (Robbins 2019)"
language:
  - en
description: "Definitive lunar impact crater database with {n_total:,} craters >= 1 km diameter from Robbins (2019). Artemis-relevant."
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - moon
  - lunar
  - crater
  - planetary-science
  - usgs
  - artemis
  - open-data
size_categories:
  - 1M<n<10M
---

# Lunar Crater Database (Robbins 2019)

The definitive lunar impact crater database, containing **{n_total:,}** craters with diameter >= 1 km.
Essential reference for Artemis mission planning and lunar surface studies.

## Dataset description

This database was compiled by Stuart J. Robbins (2019) using Lunar Reconnaissance Orbiter (LRO)
imagery and LOLA topography. It is the most comprehensive catalog of lunar impact craters,
covering the entire lunar surface with consistent methodology.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `crater_id` | int64 | Unique crater identifier |
| `latitude_deg` | float64 | Crater center latitude (degrees, planetocentric) |
| `longitude_deg` | float64 | Crater center longitude (degrees, 0-360 E) |
| `diameter_km` | float64 | Crater rim-to-rim diameter (km) |
| `depth_km` | float64 | Rim-to-floor depth (km) |
| `floor_elevation_km` | float64 | Floor elevation (km) |
| `depth_rim_sd_km` | float64 | Rim depth standard deviation (km) |
| `size_class` | string | Derived: small (<5 km), medium (5-20), large (20-100), giant (>100) |

## Quick stats

- **{n_total:,}** total craters
- Size distribution: {n_small:,} small, {n_medium:,} medium, {n_large:,} large, {n_giant:,} giant
- Diameter range: {diam_min:.2f} -- {diam_max:.1f} km

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/lunar-craters-robbins", split="train")
df = ds.to_pandas()

# Size distribution
import matplotlib.pyplot as plt
df["diameter_km"].hist(bins=100, log=True)
plt.xlabel("Diameter (km)")
plt.ylabel("Count")
plt.title("Lunar Crater Size Distribution")
plt.show()

# South pole region (Artemis-relevant)
south_pole = df[(df["latitude_deg"] < -80)]
print(f"Craters near south pole: {{len(south_pole):,}}")
plt.scatter(south_pole["longitude_deg"], south_pole["latitude_deg"],
            s=south_pole["diameter_km"], alpha=0.5)
plt.title("Lunar South Pole Craters")
plt.show()
```

## Data source

Robbins, S.J. (2019), *A New Global Database of Lunar Impact Craters >1-2 km:
1. Crater Locations and Sizes, Comparisons With Published Databases, and Global Analysis.*
Journal of Geophysical Research: Planets, 124, 871-892.
Distributed by USGS Astrogeology Science Center.

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Citation

```bibtex
@dataset{{lunar_craters_robbins,
  author = {{Simon, Julien}},
  title = {{Lunar Crater Database (Robbins 2019)}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/lunar-craters-robbins}},
  note = {{Based on Robbins (2019) via USGS Astrogeology}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update Lunar craters: {n_total:,} records"
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
