#!/usr/bin/env python3
"""Fetch NASA meteorite landing data and upload to HF."""

import os
import re
import subprocess
import tempfile
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

from dataset_images import banner_markdown, download_banner
from validate import check_dataset

# NASA retired the Socrata SODA API (y77d-th95 / gh4g-9sfh).
# The full 45K-row dataset is mirrored by Wolfram Data Repository.
WOLFRAM_CSV_URL = (
    "https://www.wolframcloud.com/objects/"
    "8ae6268d-3eaf-4f3a-8928-05d140a08e20"
)
HF_REPO = "juliensimon/meteorite-landings"


def _parse_wolfram_mass(val):
    """Extract numeric mass in grams from Wolfram Quantity[..., 'Grams']."""
    if not isinstance(val, str) or "Quantity" not in val:
        return None
    m = re.search(r"Quantity\[([^,]+),", val)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def _parse_wolfram_year(val):
    """Extract year from Wolfram DateObject[{YYYY}, ...]."""
    if not isinstance(val, str) or "DateObject" not in val:
        return None
    m = re.search(r"DateObject\[\{(\d+)\}", val)
    if m:
        return int(m.group(1))
    return None


def _parse_wolfram_coords(val):
    """Extract (lat, lon) from Wolfram GeoPosition[{lat, lon}]."""
    if not isinstance(val, str) or "GeoPosition" not in val:
        return None, None
    m = re.search(r"GeoPosition\[\{([^,]+),\s*([^}]+)\}", val)
    if m:
        try:
            return float(m.group(1)), float(m.group(2))
        except ValueError:
            return None, None
    return None, None


def main():
    print("Fetching meteorite landings from Wolfram Data Repository...")
    resp = requests.get(WOLFRAM_CSV_URL, timeout=120)
    resp.raise_for_status()

    df = pd.read_csv(StringIO(resp.text))
    print(f"  {len(df):,} raw rows")

    # Rename columns to match original schema
    df = df.rename(columns={
        "Name": "name",
        "ID": "id",
        "NameType": "nametype",
        "Classification": "recclass",
        "Mass": "mass_raw",
        "Fall": "fall",
        "Year": "year_raw",
        "Coordinates": "coords_raw",
    })

    # Parse Wolfram-encoded fields
    df["mass"] = df["mass_raw"].apply(_parse_wolfram_mass)
    df["year"] = df["year_raw"].apply(_parse_wolfram_year)
    coords = df["coords_raw"].apply(lambda v: pd.Series(_parse_wolfram_coords(v)))
    df["reclat"] = coords[0]
    df["reclong"] = coords[1]

    # Build proper datetime from year (matching original schema)
    df["year"] = pd.to_datetime(df["year"], format="%Y", errors="coerce")

    # Drop raw columns
    df = df.drop(columns=["mass_raw", "year_raw", "coords_raw"])

    # Type coercion
    df["id"] = pd.to_numeric(df["id"], errors="coerce").astype("Int64")
    df["mass"] = pd.to_numeric(df["mass"], errors="coerce")
    df["reclat"] = pd.to_numeric(df["reclat"], errors="coerce")
    df["reclong"] = pd.to_numeric(df["reclong"], errors="coerce")

    print(f"  {len(df):,} meteorite landings")

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
    if df["mass"].notna().any():
        _h = df.loc[df["mass"].idxmax()]
        heaviest_name = _h["name"]
        heaviest_kg = f"{_h['mass_kg']:,.1f}"
        heaviest_class = _h["recclass"]
    else:
        heaviest_name = "N/A"
        heaviest_kg = "0"
        heaviest_class = ""
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

        banner_file = download_banner("meteorite-landings", tmp)
        banner_md = banner_markdown("meteorite-landings", banner_file)

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
  - parquet
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
{banner_md}
*Part of the [Planetary Science Datasets](https://huggingface.co/collections/juliensimon/planetary-science-datasets-69c2d4683bd6a66c34fb4af2) collection on Hugging Face.*

NASA's comprehensive catalog of all known meteorite landings on Earth -- **{len(df):,}** records
spanning **{year_min}** to **{year_max}**, including {n_fell:,} observed falls and {n_found:,} found specimens
across {n_classes} classification types.

## Dataset description

This dataset contains every meteorite recorded in NASA's Meteorite Landings database,
sourced from The Meteoritical Society. Each record includes the meteorite's name,
classification, mass (where known), geographic coordinates, and whether the meteorite
was observed falling ("Fell") or found after the fact ("Found").

Meteorites are the only extraterrestrial materials available for direct laboratory analysis, making them indispensable for understanding solar system formation and evolution. The classification system reflects mineralogy and petrogenesis: ordinary chondrites (H, L, LL groups) are the most common falls and sample undifferentiated material from the inner asteroid belt, while carbonaceous chondrites (CI, CM, CV, CO, CR groups) preserve pre-solar grains and organic molecules dating to before the Sun's formation. Iron meteorites (e.g., Iron-IVA, Iron-IIIAB) are fragments of the metallic cores of differentiated asteroids that were disrupted by collisions, and achondrites (e.g., HED meteorites from 4 Vesta, SNC meteorites from Mars, and lunar meteorites) sample the crusts and mantles of differentiated bodies.

The distinction between "Fell" and "Found" meteorites has important implications for collection bias. Observed falls provide an unbiased sample of the meteorite flux at Earth, dominated by ordinary chondrites (~80% of falls). Found meteorites are biased toward durable iron-rich specimens that survive weathering and are visually distinctive, which is why iron meteorites are overrepresented in "Found" collections relative to their actual fall rate (~5%). The geographic distribution of finds is heavily concentrated in deserts (the Sahara, Antarctica, the Nullarbor Plain) where dark meteorites contrast against light terrain and minimal weathering preserves specimens for thousands of years. Antarctic meteorite collection programs alone have recovered over 60,000 specimens since the 1960s.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `name` | string | Official meteorite name assigned by the Meteoritical Society (e.g., "Allende", "NWA 869"); typically reflects recovery location plus sequence number |
| `id` | int64 | Unique integer identifier from the NASA/Meteoritical Society database |
| `nametype` | string | Name validity: "Valid" (standard accepted name) or "Relict" (heavily weathered, likely terrestrial origin); almost all entries are "Valid" |
| `recclass` | string | Meteoritical Society classification (e.g., "L5", "H6", "CM2", "Iron-IVA", "Achondrite-ungrouped"); letters = chemical group, numbers = petrologic grade; >400 distinct classes |
| `mass` | float64 | Total known mass in grams; null for ~15% of entries; range from <1 g to ~60,000,000 g (Hoba meteorite) |
| `mass_kg` | float64 | Total known mass in kilograms (mass / 1000); null when mass is null |
| `fall` | string | Discovery context: "Fell" (witnessed falling, more pristine, ~1,100 records) or "Found" (discovered on ground, may be weathered, ~44,000 records) |
| `year` | datetime | Year of fall or recovery as a datetime (day and month set to January 1 of the recorded year); null for entries without a year |
| `reclat` | float64 | Recovery site latitude in decimal degrees (positive = N, negative = S); null for ~one-third of entries, especially older finds without GPS records |
| `reclong` | float64 | Recovery site longitude in decimal degrees (positive = E, negative = W); null when reclat is null |

## Quick stats

- **{len(df):,}** meteorite landings ({year_min}--{year_max})
- **{n_fell:,}** observed falls, **{n_found:,}** found specimens
- **{n_with_mass:,}** records with known mass
- **{n_classes}** distinct classification types
- Heaviest: **{heaviest_name}** at **{heaviest_kg} kg**{f" ({heaviest_class})" if heaviest_class else ''}

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

[NASA Open Data Portal -- Meteorite Landings](https://data.nasa.gov/dataset/meteorite-landings),
maintained by The Meteoritical Society. Full dataset mirrored by the
[Wolfram Data Repository](https://datarepository.wolframcloud.com/resources/Meteorite-Landings)
(NASA retired the original Socrata SODA API in 2025).

## Update schedule

Static dataset (meteorite records are updated infrequently).

## Related datasets

- [neo-close-approaches](https://huggingface.co/datasets/juliensimon/neo-close-approaches) -- Near-Earth object close approaches from NASA JPL
- [confirmed-exoplanets](https://huggingface.co/datasets/juliensimon/nasa-exoplanets) -- NASA Exoplanet Archive confirmed planets
- [impact-risk](https://huggingface.co/datasets/juliensimon/sentry-impact-risk) -- Sentry impact risk assessments

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
  note = {{Based on NASA/The Meteoritical Society meteorite landing data via Wolfram Data Repository}}
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
