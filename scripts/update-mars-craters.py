#!/usr/bin/env python3
"""Fetch Mars crater database (Robbins & Hynek 2012) and upload to HF."""

import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset

DATA_URLS = [
    "https://astropedia.astrogeology.usgs.gov/download/Mars/Research/Craters/RobbinsCraterDatabase_20121016.tsv",
    "https://planetarynames.wr.usgs.gov/images/RobbinsCraterDatabase_20121016.tsv",
    "https://craters.sjrdesign.net/Catalog_Mars_Release_2020_1kmPlus_FullMorphData.csv.zip",
]
HF_REPO = "juliensimon/mars-craters-robbins"

KEEP_COLS = {
    "CRATER_ID": "crater_id",
    "LATITUDE_CIRCLE_IMAGE": "latitude_deg",
    "LONGITUDE_CIRCLE_IMAGE": "longitude_deg",
    "DIAM_CIRCLE_IMAGE": "diameter_km",
    "DEPTH_RIMFLOOR_TOPOG": "depth_km",
    "MORPHOLOGY_EJECTA_1": "ejecta_morphology_1",
    "MORPHOLOGY_EJECTA_2": "ejecta_morphology_2",
    "MORPHOLOGY_EJECTA_3": "ejecta_morphology_3",
    "NUMBER_LAYERS": "n_ejecta_layers",
}

NUMERIC_COLS = ["latitude_deg", "longitude_deg", "diameter_km", "depth_km", "n_ejecta_layers"]


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
    print("Fetching Mars crater database (Robbins & Hynek 2012)...")
    import zipfile
    df = None
    for url in DATA_URLS:
        try:
            print(f"  Trying {url[:80]}...")
            resp = requests.get(url, timeout=120)
            resp.raise_for_status()
            if url.endswith(".zip"):
                with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                    names = [n for n in zf.namelist() if n.endswith((".csv", ".tsv"))]
                    if not names:
                        continue
                    sep = "\t" if names[0].endswith(".tsv") else ","
                    with zf.open(names[0]) as f:
                        df = pd.read_csv(f, sep=sep, low_memory=False)
            else:
                df = pd.read_csv(io.StringIO(resp.text), sep="\t", low_memory=False)
            break
        except Exception as e:
            print(f"  Failed: {e}")
    if df is None:
        print("::error::All download URLs failed")
        sys.exit(1)
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
        "mars-craters",
        min_rows=300_000,
        expected_columns=["crater_id", "latitude_deg", "longitude_deg", "diameter_km"],
        critical_columns=["crater_id", "latitude_deg", "longitude_deg", "diameter_km"],
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "mars_craters.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Mars Crater Database (Robbins & Hynek 2012)"
language:
  - en
description: "Global Mars impact crater database with {n_total:,} craters >= 1 km diameter from Robbins & Hynek (2012)."
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - mars
  - crater
  - planetary-science
  - usgs
  - open-data
  - tabular-data
size_categories:
  - 100K<n<1M
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/mars_craters.parquet
    default: true
---

# Mars Crater Database (Robbins & Hynek 2012)

*Part of the [Planetary Science Datasets](https://huggingface.co/collections/juliensimon/planetary-science-datasets-69c2d4683bd6a66c34fb4af2) collection on Hugging Face.*

The only global Mars impact crater database, containing **{n_total:,}** craters with diameter >= 1 km
identified from high-resolution imagery. This is the definitive reference catalog for Mars crater studies.

## Dataset description

This database was compiled by Stuart J. Robbins and Brian M. Hynek (2012) using THEMIS, CTX,
and other Mars imagery. Every crater >= 1 km in diameter on the Martian surface was identified
and measured, including ejecta morphology classification and depth measurements where available.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `crater_id` | int64 | Unique crater identifier |
| `latitude_deg` | float64 | Crater center latitude (degrees, planetocentric) |
| `longitude_deg` | float64 | Crater center longitude (degrees, 0-360 E) |
| `diameter_km` | float64 | Crater rim-to-rim diameter (km) |
| `depth_km` | float64 | Rim-to-floor depth (km, from MOLA topography) |
| `ejecta_morphology_1` | string | Primary ejecta morphology classification |
| `ejecta_morphology_2` | string | Secondary ejecta morphology classification |
| `ejecta_morphology_3` | string | Tertiary ejecta morphology classification |
| `n_ejecta_layers` | int64 | Number of ejecta layers |
| `size_class` | string | Derived: small (<5 km), medium (5-20), large (20-100), giant (>100) |

## Quick stats

- **{n_total:,}** total craters
- Size distribution: {n_small:,} small, {n_medium:,} medium, {n_large:,} large, {n_giant:,} giant
- Diameter range: {diam_min:.2f} -- {diam_max:.1f} km

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/mars-craters-robbins", split="train")
df = ds.to_pandas()

# Size distribution histogram
import matplotlib.pyplot as plt
df["diameter_km"].hist(bins=100, log=True)
plt.xlabel("Diameter (km)")
plt.ylabel("Count")
plt.title("Mars Crater Size Distribution")
plt.show()

# Map of large craters
large = df[df["size_class"].isin(["large", "giant"])]
plt.scatter(large["longitude_deg"], large["latitude_deg"],
            s=large["diameter_km"] / 5, alpha=0.5)
plt.xlabel("Longitude")
plt.ylabel("Latitude")
plt.title("Large Mars Craters (>20 km)")
plt.show()
```

## Data source

Robbins, S.J. and Hynek, B.M. (2012), *A new global database of Mars impact craters >= 1 km:
1. Database creation, properties, and parameters.* Journal of Geophysical Research, 117, E05004.
Distributed by USGS Astrogeology Science Center.

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/mars-craters-robbins) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{mars_craters_robbins,
  author = {{Simon, Julien}},
  title = {{Mars Crater Database (Robbins & Hynek 2012)}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/mars-craters-robbins}},
  note = {{Based on Robbins & Hynek (2012) via USGS Astrogeology}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update Mars craters: {n_total:,} records"
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
