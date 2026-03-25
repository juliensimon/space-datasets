#!/usr/bin/env python3
"""Fetch NASA meteorite landing data and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset

SODA_URL = "https://data.nasa.gov/resource/y77d-th95.csv"
HF_REPO = "juliensimon/meteorite-landings"


def main():
    print("Fetching meteorite landings from NASA SODA API...")
    resp = requests.get(SODA_URL, params={"$limit": 50000}, timeout=120)
    resp.raise_for_status()

    from io import StringIO
    df = pd.read_csv(StringIO(resp.text))
    print(f"  {len(df):,} meteorite landings")

    # Drop redundant GeoLocation column
    if "geolocation" in df.columns:
        df = df.drop(columns=["geolocation"])
    if "GeoLocation" in df.columns:
        df = df.drop(columns=["GeoLocation"])

    # Type coercion
    df["id"] = pd.to_numeric(df["id"], errors="coerce").astype("Int64")
    df["mass"] = pd.to_numeric(df["mass"], errors="coerce")
    df["reclat"] = pd.to_numeric(df["reclat"], errors="coerce")
    df["reclong"] = pd.to_numeric(df["reclong"], errors="coerce")
    df["year"] = pd.to_datetime(df["year"], errors="coerce")

    # Derived column: mass in kg
    df["mass_kg"] = (df["mass"] / 1000).round(3)

    # Sort by year descending
    df = df.sort_values("year", ascending=False, na_position="last").reset_index(drop=True)

    # Validate
    check_dataset(
        df,
        dataset_name="meteorite-landings",
        min_rows=40_000,
        expected_columns=["name", "id", "recclass", "mass", "fall", "year", "reclat", "reclong"],
        critical_columns=["name", "id", "recclass"],
    )

    # Stats for README
    n_fell = int((df["fall"] == "Fell").sum())
    n_found = int((df["fall"] == "Found").sum())
    n_with_mass = int(df["mass"].notna().sum())
    heaviest = df.loc[df["mass"].idxmax()] if df["mass"].notna().any() else None
    n_classes = df["recclass"].nunique()
    year_min = int(df["year"].dt.year.min()) if df["year"].notna().any() else 0
    year_max = int(df["year"].dt.year.max()) if df["year"].notna().any() else 0

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "meteorite_landings.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Meteorite Landings"
language:
  - en
description: "NASA's comprehensive database of all known meteorite landings on Earth, with classification, mass, coordinates, and discovery context."
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - meteorites
  - planetary-science
  - nasa
  - open-data
  - tabular-data
size_categories:
  - 10K<n<100K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/meteorite_landings.parquet
    default: true
---

# Meteorite Landings

*Part of the [Planetary Science Datasets](https://huggingface.co/collections/juliensimon/planetary-science-datasets-69c2d4683bd6a66c34fb4af2) collection on Hugging Face.*

NASA's comprehensive catalog of all known meteorite landings on Earth -- **{len(df):,}** records
spanning **{year_min}** to **{year_max}**, including {n_fell:,} observed falls and {n_found:,} found specimens
across {n_classes} classification types.

## Dataset description

This dataset contains every meteorite recorded in NASA's Meteorite Landings database,
sourced from The Meteoritical Society. Each record includes the meteorite's name,
classification, mass (where known), geographic coordinates, and whether the meteorite
was observed falling ("Fell") or found after the fact ("Found").

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `name` | string | Official meteorite name |
| `id` | int64 | Unique identifier |
| `nametype` | string | Name type: "Valid" or "Relict" |
| `recclass` | string | Meteorite classification (e.g. L5, H6, Iron-IVA) |
| `mass` | float64 | Mass in grams |
| `mass_kg` | float64 | Mass in kilograms |
| `fall` | string | "Fell" (observed fall) or "Found" (discovered later) |
| `year` | datetime | Year of fall or discovery |
| `reclat` | float64 | Recovery latitude (decimal degrees) |
| `reclong` | float64 | Recovery longitude (decimal degrees) |

## Quick stats

- **{len(df):,}** meteorite landings ({year_min}--{year_max})
- **{n_fell:,}** observed falls, **{n_found:,}** found specimens
- **{n_with_mass:,}** records with known mass
- **{n_classes}** distinct classification types
- Heaviest: **{heaviest['name'] if heaviest is not None else 'N/A'}** at **{heaviest['mass_kg']:,.1f if heaviest is not None else 0} kg**{f" ({heaviest['recclass']})" if heaviest is not None else ''}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/meteorite-landings", split="train")
df = ds.to_pandas()

# Observed falls sorted by mass
fell = df[df["fall"] == "Fell"].sort_values("mass_kg", ascending=False)

# Meteorites by classification
by_class = df["recclass"].value_counts().head(20)

# Map of all landings with coordinates
with_coords = df.dropna(subset=["reclat", "reclong"])
```

## Data source

[NASA Open Data Portal -- Meteorite Landings](https://data.nasa.gov/Space-Science/Meteorite-Landings/gh4g-9sfh),
maintained by The Meteoritical Society and published via NASA's Socrata SODA API.

## Update schedule

Static dataset (meteorite records are updated infrequently).

## Related datasets

- [neo-close-approaches](https://huggingface.co/datasets/juliensimon/neo-close-approaches) -- Near-Earth object close approaches from NASA JPL
- [confirmed-exoplanets](https://huggingface.co/datasets/juliensimon/confirmed-exoplanets) -- NASA Exoplanet Archive confirmed planets
- [impact-risk](https://huggingface.co/datasets/juliensimon/impact-risk) -- Sentry impact risk assessments

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Citation

```bibtex
@dataset{{meteorite_landings,
  author = {{Simon, Julien}},
  title = {{Meteorite Landings}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/meteorite-landings}},
  note = {{Based on NASA/The Meteoritical Society meteorite landing data via the Socrata SODA API}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update meteorite landings: {len(df):,} records"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    # Emit row count for GitHub Actions
    gh_output = os.environ.get("GITHUB_OUTPUT")
    if gh_output:
        with open(gh_output, "a") as f:
            f.write(f"rows={len(df)}\n")

    print(f"Done. {len(df):,} meteorite landings uploaded.")


if __name__ == "__main__":
    main()
