#!/usr/bin/env python3
"""Fetch Ceres crater database (Zeilnhofer 2020) and upload to HF."""

import io
import os
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset

DATA_URL = "https://astropedia.astrogeology.usgs.gov/download/Ceres/Dawn/Craters/ceres_dawn_fc2_craterdatabase_zeilnhofer_2020_v2.zip"
HF_REPO = "juliensimon/ceres-craters-dawn"

NUMERIC_COLS = [
    "latitude_deg", "longitude_deg", "diameter_km", "depth_km",
    "depth_diameter_ratio",
]


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
    print("Fetching Ceres crater database (Zeilnhofer 2020)...")

    # Download zip with retries
    df = None
    for attempt in range(1, 4):
        try:
            print(f"  Attempt {attempt}: {DATA_URL[:80]}...")
            resp = requests.get(DATA_URL, timeout=120, headers={"User-Agent": "space-datasets/1.0"})
            resp.raise_for_status()
            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                names = [n for n in zf.namelist()
                         if n.endswith((".csv", ".tsv", ".txt"))
                         and not n.startswith("__MACOSX")]
                if not names:
                    print("  No CSV/TSV found in zip")
                    continue
                print(f"  Extracting {names[0]}")
                with zf.open(names[0]) as f:
                    df = pd.read_csv(f, low_memory=False, encoding="utf-8")
            break
        except Exception as e:
            print(f"  Failed: {e}")
            if attempt < 3:
                time.sleep(2 * attempt)
    if df is None:
        print("::error::All download attempts failed")
        sys.exit(1)

    print(f"  {len(df):,} raw rows, {len(df.columns)} columns")
    print(f"  Raw columns: {list(df.columns)}")

    # Strip whitespace from column names
    df.columns = df.columns.str.strip()

    # Rename columns to snake_case
    # The Zeilnhofer 2020 CSV uses mixed-case names; map all known variants
    rename_map = {
        # Crater ID
        "CRATER_ID": "crater_id",
        "Crater_ID": "crater_id",
        "crater_id": "crater_id",
        "ID": "crater_id",
        # Latitude
        "LAT_CIRC_IMG": "latitude_deg",
        "LATITUDE_CIRCLE_IMAGE": "latitude_deg",
        "Lat_Circ_Img": "latitude_deg",
        "Lat": "latitude_deg",
        "lat": "latitude_deg",
        # Longitude
        "LON_CIRC_IMG": "longitude_deg",
        "LONGITUDE_CIRCLE_IMAGE": "longitude_deg",
        "Lon_Circ_Img": "longitude_deg",
        "Lon": "longitude_deg",
        "lon": "longitude_deg",
        # Diameter
        "DIAM_CIRC_IMG": "diameter_km",
        "DIAM_CIRCLE_IMAGE": "diameter_km",
        "Diam_Circ_Img": "diameter_km",
        "Diam_km": "diameter_km",
        "diam_km": "diameter_km",
        "Diameter": "diameter_km",
        "D_km": "diameter_km",
        # Depth
        "DEPTH_RIM_TOPO": "depth_km",
        "DEPTH_RIMFLOOR_TOPOG": "depth_km",
        "Depth_Rim_Topo": "depth_km",
        "Depth_km": "depth_km",
        "depth_km": "depth_km",
        "d_km": "depth_km",
        # Depth/Diameter ratio
        "DEPTH_DIAM_RATIO": "depth_diameter_ratio",
        "Depth_Diam_Ratio": "depth_diameter_ratio",
        "d_D": "depth_diameter_ratio",
        "dD": "depth_diameter_ratio",
        # Morphology / degradation
        "MORPHOLOGY_EJECTA_1": "ejecta_morphology",
        "Morphology": "morphology",
        "morphology": "morphology",
        "MORPH_EJECTA_1": "ejecta_morphology",
        "Degradation": "degradation_state",
        "Degradation_State": "degradation_state",
        "DEG_STATE": "degradation_state",
        # Preservation / confidence
        "Preservation": "preservation_state",
        "Confidence": "confidence",
        "CONFIDENCE": "confidence",
    }

    # Apply rename for columns that exist
    actual_rename = {c: v for c, v in rename_map.items() if c in df.columns}
    df = df.rename(columns=actual_rename)

    # Also snake_case any remaining columns not yet renamed
    df.columns = (
        df.columns
        .str.strip()
        .str.replace(r"[() /]+", "_", regex=True)
        .str.replace(r"_+", "_", regex=True)
        .str.strip("_")
        .str.lower()
    )

    # Type conversions
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Compute depth/diameter ratio if not present but components exist
    if "depth_diameter_ratio" not in df.columns and "depth_km" in df.columns and "diameter_km" in df.columns:
        df["depth_diameter_ratio"] = (df["depth_km"] / df["diameter_km"]).round(4)

    # Derived column: size class
    df["size_class"] = df["diameter_km"].apply(size_class)

    # Stats
    n_total = len(df)
    n_small = int((df["size_class"] == "small").sum())
    n_medium = int((df["size_class"] == "medium").sum())
    n_large = int((df["size_class"] == "large").sum())
    n_giant = int((df["size_class"] == "giant").sum())
    diam_min = df["diameter_km"].min()
    diam_max = df["diameter_km"].max()
    has_depth = int(df["depth_km"].notna().sum()) if "depth_km" in df.columns else 0

    print(f"  {n_total:,} craters after processing")
    print(f"  Diameter range: {diam_min:.2f} -- {diam_max:.1f} km")
    print(f"  {has_depth:,} with depth measurements")
    print(f"  Final columns: {list(df.columns)}")

    # Validate
    check_dataset(
        df,
        "ceres-craters",
        min_rows=40_000,
        expected_columns=["latitude_deg", "longitude_deg", "diameter_km"],
        critical_columns=["latitude_deg", "longitude_deg", "diameter_km"],
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "ceres_craters.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Ceres Crater Database (Zeilnhofer 2020, Dawn FC2)"
language:
  - en
description: "44,594 impact craters on Ceres (>= 1 km) from the Dawn Framing Camera, with positions, diameters, depths, and morphology (Zeilnhofer 2020)."
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - ceres
  - dawn
  - craters
  - planetary-science
  - usgs
  - asteroid
  - nasa
  - open-data
  - tabular-data
  - parquet
size_categories:
  - 10K<n<100K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/ceres_craters.parquet
    default: true
---

# Ceres Crater Database (Zeilnhofer 2020, Dawn FC2)

*Part of the [Planetary Science Datasets](https://huggingface.co/collections/juliensimon/planetary-science-datasets-69c2d4683bd6a66c34fb4af2) collection on Hugging Face.*

The most comprehensive catalog of impact craters on dwarf planet Ceres, containing **{n_total:,}** craters
with diameter >= 1 km identified from Dawn Framing Camera (FC2) imagery.

## Dataset description

This database was compiled by M. F. Zeilnhofer and H. Hiesinger (2020) using images from NASA's Dawn
spacecraft Framing Camera 2. Every crater >= 1 km in diameter on Ceres was identified and measured,
providing positions, diameters, and depth measurements where available. Ceres is the largest object in the
asteroid belt and the only dwarf planet in the inner solar system.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `latitude_deg` | float64 | Crater center latitude (degrees, planetocentric) |
| `longitude_deg` | float64 | Crater center longitude (degrees, 0-360 E) |
| `diameter_km` | float64 | Crater rim-to-rim diameter (km) |
| `depth_km` | float64 | Rim-to-floor depth (km) |
| `depth_diameter_ratio` | float64 | Depth-to-diameter ratio |
| `size_class` | string | Derived: small (<5 km), medium (5-20), large (20-100), giant (>100) |

*Additional columns from the source may be present (morphology, degradation state, confidence, etc.).*

## Quick stats

- **{n_total:,}** total craters
- Size distribution: {n_small:,} small, {n_medium:,} medium, {n_large:,} large, {n_giant:,} giant
- Diameter range: {diam_min:.2f} -- {diam_max:.1f} km
- **{has_depth:,}** craters with depth measurements

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/ceres-craters-dawn", split="train")
df = ds.to_pandas()

# Size distribution histogram
import matplotlib.pyplot as plt
df["diameter_km"].hist(bins=100, log=True)
plt.xlabel("Diameter (km)")
plt.ylabel("Count")
plt.title("Ceres Crater Size Distribution")
plt.show()

# Map of craters
plt.scatter(df["longitude_deg"], df["latitude_deg"],
            s=df["diameter_km"] / 5, alpha=0.3)
plt.xlabel("Longitude (deg)")
plt.ylabel("Latitude (deg)")
plt.title("Ceres Impact Craters (Dawn FC2)")
plt.show()

# Large craters (>50 km)
large = df[df["diameter_km"] > 50].sort_values("diameter_km", ascending=False)
print(f"Craters >50 km: {{len(large)}}")
```

## Data source

Zeilnhofer, M. F. and Hiesinger, H. (2020), *Ceres Crater Database*, version 2.
Dawn Framing Camera 2 data, distributed by USGS Astrogeology Science Center via Astropedia.

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/ceres-craters-dawn) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{ceres_craters_dawn,
  author = {{Simon, Julien}},
  title = {{Ceres Crater Database (Zeilnhofer 2020, Dawn FC2)}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/ceres-craters-dawn}},
  note = {{Based on Zeilnhofer & Hiesinger (2020) via USGS Astrogeology}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update Ceres craters: {n_total:,} records"
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
