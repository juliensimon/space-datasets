#!/usr/bin/env python3
"""Fetch confirmed exoplanets from NASA Exoplanet Archive and upload to HF."""

import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset


TAP_URL = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
HF_REPO = "juliensimon/nasa-exoplanets"

ADQL_QUERY = """\
SELECT pl_name,hostname,discoverymethod,disc_year,disc_facility,
  pl_orbper,pl_rade,pl_bmasse,pl_eqt,pl_orbsmax,pl_orbeccen,
  st_teff,st_rad,st_mass,sy_dist,sy_vmag,ra,dec,rowupdate
FROM ps WHERE default_flag=1 ORDER BY disc_year DESC"""


def main():
    print("Fetching confirmed exoplanets from NASA Exoplanet Archive...")
    resp = requests.get(TAP_URL, params={"query": ADQL_QUERY, "format": "csv"}, timeout=120)
    resp.raise_for_status()

    df = pd.read_csv(io.StringIO(resp.text))
    print(f"  {len(df):,} confirmed planets")

    # Type coercion
    df["disc_year"] = df["disc_year"].astype("Int64")
    for col in ["pl_orbper", "pl_rade", "pl_bmasse", "pl_eqt", "pl_orbsmax",
                "pl_orbeccen", "st_teff", "st_rad", "st_mass", "sy_dist", "sy_vmag",
                "ra", "dec"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Sort by discovery year descending
    df = df.sort_values("disc_year", ascending=False, na_position="last").reset_index(drop=True)

    check_dataset(df, "exoplanets", min_rows=5000,
        expected_columns=["pl_name", "hostname", "discoverymethod", "disc_year", "pl_orbper"],
        critical_columns=["pl_name", "hostname"])

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "exoplanets.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        # Compute stats for README
        n_total = len(df)
        method_counts = df["discoverymethod"].value_counts()
        method_lines = "\n".join(
            f"| {method} | {count:,} |" for method, count in method_counts.head(8).items()
        )

        year_counts = df["disc_year"].dropna().astype(int).value_counts().sort_index(ascending=False)
        recent_years = "\n".join(
            f"| {year} | {count:,} |" for year, count in year_counts.head(10).items()
        )

        most_recent = df.iloc[0]
        most_recent_name = most_recent["pl_name"]
        most_recent_year = int(most_recent["disc_year"]) if pd.notna(most_recent["disc_year"]) else "N/A"

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "NASA Exoplanet Archive"
language:
  - en
description: "Confirmed exoplanets with orbital, stellar, and discovery parameters from the NASA Exoplanet Archive."
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - exoplanet
  - astronomy
  - nasa
  - transit
  - radial-velocity
  - kepler
  - tess
  - open-data
size_categories:
  - 1K<n<10K
---

# NASA Exoplanet Archive

![Update Exoplanets](https://github.com/juliensimon/space-datasets/actions/workflows/update-exoplanets.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.exoplanets&label=updated&color=brightgreen)

All confirmed exoplanets from the [NASA Exoplanet Archive](https://exoplanetarchive.ipac.caltech.edu/),
with orbital parameters, stellar properties, and discovery metadata. Currently **{n_total:,}** confirmed planets.

## Dataset description

The NASA Exoplanet Archive is the authoritative database of confirmed exoplanets, maintained by
Caltech/IPAC under contract with NASA. Each entry represents a confirmed planet with its best-available
physical and orbital parameters, host star properties, and discovery information. This dataset uses the
Planetary Systems (`ps`) table with `default_flag=1` to select one row per planet with the default
parameter set.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `pl_name` | string | Planet name (e.g. "Kepler-22 b", "TRAPPIST-1 e") |
| `hostname` | string | Host star name |
| `discoverymethod` | string | Discovery method (Transit, Radial Velocity, etc.) |
| `disc_year` | Int64 | Year of discovery |
| `disc_facility` | string | Discovery facility name |
| `pl_orbper` | float | Orbital period in days |
| `pl_rade` | float | Planet radius in Earth radii |
| `pl_bmasse` | float | Planet mass in Earth masses |
| `pl_eqt` | float | Equilibrium temperature in K |
| `pl_orbsmax` | float | Semi-major axis in AU |
| `pl_orbeccen` | float | Orbital eccentricity |
| `st_teff` | float | Stellar effective temperature in K |
| `st_rad` | float | Stellar radius in solar radii |
| `st_mass` | float | Stellar mass in solar masses |
| `sy_dist` | float | Distance in parsecs |
| `sy_vmag` | float | V-band magnitude |
| `ra` | float | Right ascension in degrees |
| `dec` | float | Declination in degrees |
| `rowupdate` | string | Date of last row update |

## Quick stats

- **{n_total:,}** confirmed exoplanets
- Most recent discovery: **{most_recent_name}** ({most_recent_year})

### By discovery method

| Method | Count |
|--------|-------|
{method_lines}

### Recent discoveries by year

| Year | Count |
|------|-------|
{recent_years}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/nasa-exoplanets", split="train")
df = ds.to_pandas()

# Earth-like candidates: rocky, in habitable zone
habitable = df[
    (df["pl_rade"] < 1.6) &
    (df["pl_eqt"] > 200) & (df["pl_eqt"] < 310)
]
print(f"{{len(habitable)}} potentially habitable planets")

# Transit vs radial velocity discoveries over time
transit = df[df["discoverymethod"] == "Transit"]
rv = df[df["discoverymethod"] == "Radial Velocity"]

# Planets by discovery facility
top_facilities = df["disc_facility"].value_counts().head(10)
```

## Data source

All data comes from the [NASA Exoplanet Archive](https://exoplanetarchive.ipac.caltech.edu/),
maintained by Caltech/IPAC under contract with NASA. Data is queried via the TAP API using
the Planetary Systems table.

## Update schedule

Weekly on Monday at 16:00 UTC via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [space-track-satcat](https://huggingface.co/datasets/juliensimon/space-track-satcat) — NORAD Satellite Catalog
- [space-launch-log](https://huggingface.co/datasets/juliensimon/space-launch-log) — Global launch history from GCAT

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Citation

```bibtex
@dataset{{nasa_exoplanets,
  author = {{Simon, Julien}},
  title = {{NASA Exoplanet Archive}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/nasa-exoplanets}},
  note = {{Based on data from the NASA Exoplanet Archive, operated by Caltech/IPAC}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update exoplanets: {n_total:,} confirmed planets"
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
