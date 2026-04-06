#!/usr/bin/env python3
"""Fetch NASA Five Millennium Catalog of Solar Eclipses and upload to HF.

Static dataset — uploaded once. No GitHub Actions workflow.

Source: Fred Espenak's Five Millennium Canon of Solar Eclipses (-1999 to +3000),
hosted by NASA GSFC. Uses the Besselian elements CSV export which contains all
~12,000 eclipses in a single machine-readable file.
"""

import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd
import requests

from dataset_images import banner_markdown, download_banner
from validate import check_dataset

CSV_URL = "https://eclipse.gsfc.nasa.gov/eclipse_besselian_from_mysqldump2.csv"
HF_REPO = "juliensimon/solar-eclipse-catalog"

# Columns to keep (from the 48-column Besselian elements CSV)
KEEP_COLS = [
    "cat_no", "year", "month", "day", "td_ge", "dt",
    "luna_num", "saros", "eclipse_type",
    "gamma", "magnitude",
    "lat_dd_ge", "lng_dd_ge", "sun_alt", "path_width", "central_duration",
]

RENAME = {
    "cat_no": "catalog_number",
    "td_ge": "td_of_greatest_eclipse",
    "dt": "delta_t",
    "luna_num": "luna_number",
    "saros": "saros_number",
    "lat_dd_ge": "latitude",
    "lng_dd_ge": "longitude",
    "sun_alt": "sun_altitude",
    "path_width": "path_width_km",
}

NUMERIC_COLS = [
    "gamma", "magnitude", "latitude", "longitude",
    "sun_altitude", "path_width_km", "delta_t",
]

ECLIPSE_TYPE_NAMES = {
    "T": "Total",
    "A": "Annular",
    "H": "Hybrid",
    "P": "Partial",
}


def fetch_catalog() -> pd.DataFrame:
    """Download the Besselian elements CSV from NASA GSFC."""
    print("Fetching Five Millennium Solar Eclipse Catalog from NASA GSFC...")
    resp = requests.get(CSV_URL, timeout=120, headers={"User-Agent": "space-datasets/1.0"})
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text), low_memory=False)
    print(f"  {len(df):,} raw rows, {len(df.columns)} columns")
    return df


def main():
    df = fetch_catalog()

    # Keep only the columns we need
    available = [c for c in KEEP_COLS if c in df.columns]
    missing = set(KEEP_COLS) - set(available)
    if missing:
        print(f"  Warning: missing columns in source: {sorted(missing)}")
    df = df[available].copy()

    # Rename columns
    df = df.rename(columns=RENAME)

    # Build a proper date column from year/month/day
    # Years can be negative (BCE); pd.Timestamp doesn't handle that,
    # so store as string "YYYY-MM-DD" for negative years
    def make_date_str(row):
        y, m, d = int(row["year"]), int(row["month"]), int(row["day"])
        if y < 0:
            return f"{y:05d}-{m:02d}-{d:02d}"
        return f"{y:04d}-{m:02d}-{d:02d}"

    df["date"] = df.apply(make_date_str, axis=1)

    # Drop the raw year/month/day columns (keep year for century derivation)
    year_col = df["year"].copy()
    df = df.drop(columns=["month", "day"])

    # Numeric coercion
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["catalog_number"] = pd.to_numeric(df["catalog_number"], errors="coerce").astype("Int64")
    df["luna_number"] = pd.to_numeric(df["luna_number"], errors="coerce").astype("Int64")
    df["saros_number"] = pd.to_numeric(df["saros_number"], errors="coerce").astype("Int64")
    df["year"] = pd.to_numeric(year_col, errors="coerce").astype("Int64")

    # Strip whitespace from string columns
    for col in ["eclipse_type", "td_of_greatest_eclipse", "central_duration"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    # Derived columns
    df["eclipse_type_name"] = df["eclipse_type"].map(ECLIPSE_TYPE_NAMES)
    df["is_total"] = df["eclipse_type"] == "T"
    df["is_annular"] = df["eclipse_type"] == "A"
    df["century"] = (df["year"] / 100).apply(
        lambda x: int(x) if pd.notna(x) else None
    ).astype("Int64")

    # Reorder columns
    col_order = [
        "catalog_number", "date", "year", "td_of_greatest_eclipse", "delta_t",
        "luna_number", "saros_number",
        "eclipse_type", "eclipse_type_name", "is_total", "is_annular",
        "gamma", "magnitude",
        "latitude", "longitude", "sun_altitude",
        "path_width_km", "central_duration", "century",
    ]
    col_order = [c for c in col_order if c in df.columns]
    df = df[col_order]

    # Sort by date ascending (catalog_number tracks chronological order)
    df = df.sort_values("catalog_number", ascending=True).reset_index(drop=True)

    print(f"  {len(df):,} solar eclipses")

    # Stats
    n_total_eclipses = len(df)
    n_total = int(df["is_total"].sum())
    n_annular = int(df["is_annular"].sum())
    n_hybrid = int((df["eclipse_type"] == "H").sum())
    n_partial = int((df["eclipse_type"] == "P").sum())
    year_min = int(df["year"].min())
    year_max = int(df["year"].max())

    print(f"  Types: {n_total} total, {n_annular} annular, {n_hybrid} hybrid, {n_partial} partial")
    print(f"  Year range: {year_min} to {year_max}")

    check_dataset(
        df,
        "solar-eclipses",
        min_rows=10000,
        expected_columns=["catalog_number", "date", "eclipse_type", "gamma", "magnitude"],
        critical_columns=["catalog_number", "date", "eclipse_type"],
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "solar_eclipses.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        banner_file = download_banner("solar-eclipses", tmp)
        banner_md = banner_markdown("solar-eclipses", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Five Millennium Catalog of Solar Eclipses"
language:
  - en
description: "All {n_total_eclipses:,} solar eclipses from {year_min} to {year_max}, from NASA's Five Millennium Canon by Fred Espenak."
task_categories:
  - tabular-classification
tags:
  - space
  - solar-eclipse
  - eclipse
  - sun
  - moon
  - astronomy
  - nasa
  - planetary-science
  - open-data
  - tabular-data
  - parquet
size_categories:
  - 10K<n<100K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/solar_eclipses.parquet
    default: true
---

# Five Millennium Catalog of Solar Eclipses
{banner_md}
*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) and [Solar System Datasets](https://huggingface.co/collections/juliensimon/solar-system-datasets-69dd8a8b30395bb6e91abc76) collections on Hugging Face.*

Static dataset -- uploaded once.

Complete catalog of **{n_total_eclipses:,}** solar eclipses spanning five millennia ({year_min} to {year_max}),
computed by Fred Espenak as part of NASA's Five Millennium Canon of Solar Eclipses.

## Dataset description

A solar eclipse occurs when the Moon passes between Earth and the Sun, casting its shadow on Earth's surface. The geometry of each eclipse depends on the Moon's orbital elements at the moment of conjunction, producing four distinct types: **total** (Moon fully covers the Sun), **annular** (Moon appears smaller than the Sun, leaving a bright ring), **hybrid** (transitions between total and annular along the eclipse path), and **partial** (Moon only partially obscures the Sun).

This catalog is derived from Fred Espenak's Five Millennium Canon of Solar Eclipses, a monumental computational effort that uses Besselian elements and the polynomial expressions of Chapront, Chapront-Touze, and Francou for lunar and solar coordinates to predict every solar eclipse from -1999 to +3000. The calculations account for the secular acceleration of the Moon, the variable rotation of the Earth (via Delta-T extrapolations), and the irregular lunar limb profile.

The **gamma** parameter measures how close the Moon's shadow axis passes to Earth's center — values near zero produce central eclipses at low latitudes, while values exceeding roughly 0.9972 produce partial eclipses. Eclipse **magnitude** gives the fraction of the Sun's diameter covered at greatest eclipse. The **Saros number** groups eclipses into families that repeat every 18 years 11 days 8 hours — each Saros series produces 70-80 eclipses over roughly 1,300 years, cycling through partial, total/annular, and back to partial phases.

The dataset has {n_total:,} total eclipses, {n_annular:,} annular eclipses, {n_hybrid:,} hybrid eclipses, and {n_partial:,} partial eclipses.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `catalog_number` | int64 | Sequential catalog number (1 to {n_total_eclipses:,}) |
| `date` | string | Date of greatest eclipse (YYYY-MM-DD, negative years for BCE) |
| `year` | int64 | Calendar year (negative for BCE) |
| `td_of_greatest_eclipse` | string | Time of greatest eclipse (Terrestrial Dynamical Time) |
| `delta_t` | float64 | Delta-T: difference TDT minus UT in seconds |
| `luna_number` | int64 | Lunation number (Brown's series) |
| `saros_number` | int64 | Saros series number |
| `eclipse_type` | string | Eclipse type code: T (total), A (annular), H (hybrid), P (partial) |
| `eclipse_type_name` | string | Full name of eclipse type |
| `is_total` | bool | True if eclipse is total |
| `is_annular` | bool | True if eclipse is annular |
| `gamma` | float64 | Distance of Moon shadow axis from Earth center |
| `magnitude` | float64 | Eclipse magnitude (fraction of Sun diameter covered) |
| `latitude` | float64 | Latitude of greatest eclipse (degrees, + N / - S) |
| `longitude` | float64 | Longitude of greatest eclipse (degrees, + E / - W) |
| `sun_altitude` | float64 | Sun altitude at greatest eclipse (degrees) |
| `path_width_km` | float64 | Width of central eclipse path (km, null for partial) |
| `central_duration` | string | Duration of central eclipse (e.g. "04m57s", null for partial) |
| `century` | int64 | Derived century (year / 100, truncated) |

## Quick stats

- **{n_total_eclipses:,}** solar eclipses ({year_min} to {year_max})
- **{n_total:,}** total, **{n_annular:,}** annular, **{n_hybrid:,}** hybrid, **{n_partial:,}** partial
- Average: ~4.7 eclipses per year

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/solar-eclipse-catalog", split="train")
df = ds.to_pandas()

# Filter by eclipse type
total = df[df["is_total"]]
print(f"{{len(total):,}} total solar eclipses across 5 millennia")

# Eclipses per century
by_century = df.groupby("century")["eclipse_type"].value_counts().unstack(fill_value=0)
print(by_century.tail(10))

# Total eclipses visible from a region (e.g. Europe: lat 35-70, lon -10 to 40)
europe_total = df[
    (df["is_total"]) &
    (df["latitude"].between(35, 70)) &
    (df["longitude"].between(-10, 40)) &
    (df["year"].between(2000, 2100))
]
print(f"Total eclipses over Europe (2000-2100): {{len(europe_total)}}")

# Saros series analysis
saros = df.groupby("saros_number").agg(
    count=("catalog_number", "size"),
    first_year=("year", "min"),
    last_year=("year", "max"),
).sort_values("count", ascending=False)
print(saros.head(10))
```

## Data source

[Five Millennium Canon of Solar Eclipses: -1999 to +3000](https://eclipse.gsfc.nasa.gov/SEcat5/SEcatalog.html)
by Fred Espenak (NASA/GSFC). Besselian elements CSV export.

## Update schedule

Static dataset -- uploaded once. The underlying catalog covers -1999 to +3000 and is not expected to change.

## Related datasets

- [silso-sunspot-number](https://huggingface.co/datasets/juliensimon/silso-sunspot-number) -- Daily sunspot numbers from SILSO
- [iers-earth-orientation](https://huggingface.co/datasets/juliensimon/iers-earth-orientation) -- Earth orientation parameters (UT1-UTC, polar motion)
- [lunar-craters-robbins](https://huggingface.co/datasets/juliensimon/lunar-craters-robbins) -- Lunar crater database

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/solar-eclipse-catalog) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{solar_eclipse_catalog,
  author = {{Simon, Julien}},
  title = {{Five Millennium Catalog of Solar Eclipses}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/solar-eclipse-catalog}},
  note = {{Based on Fred Espenak's Five Millennium Canon of Solar Eclipses (NASA/GSFC)}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Upload solar eclipse catalog: {n_total_eclipses:,} eclipses"
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
