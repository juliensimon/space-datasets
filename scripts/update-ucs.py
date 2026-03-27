#!/usr/bin/env python3
"""Fetch UCS Satellite Database and upload to HF."""

import io
import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset


HF_REPO = "juliensimon/ucs-satellite-database"

UCS_URLS = [
    "https://www.ucs.org/sites/default/files/2025-02/UCS-Satellite-Database-5-1-2024.xlsx",
    "https://www.ucsusa.org/sites/default/files/2025-02/UCS-Satellite-Database-5-1-2024.xlsx",
    "https://www.ucsusa.org/media/2025-02/UCS-Satellite-Database-5-1-2024.xlsx",
    "https://s3.amazonaws.com/ucs-documents/nuclear-weapons/sat-database/5-2024-update/UCS-Satellite-Database-5-1-2024.xlsx",
]

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; space-datasets/1.0; +https://github.com/juliensimon/space-datasets)",
}


def main():
    print("Fetching UCS Satellite Database...")
    df = None
    for url in UCS_URLS:
        print(f"  Trying {url}...")
        try:
            resp = requests.get(url, timeout=120, allow_redirects=True, headers=_HEADERS)
            resp.raise_for_status()
            df = pd.read_excel(io.BytesIO(resp.content), engine="openpyxl")
            print(f"  Success: {len(df):,} rows")
            break
        except Exception as e:
            print(f"  Failed: {e}")

    if df is None or len(df) == 0:
        print("::error::Failed to fetch UCS Satellite Database from any URL")
        import sys
        sys.exit(1)

    # Rename columns to snake_case
    col_rename = {
        "Name of Satellite": "satellite_name",
        "Country/Org of UN Registry": "country_registry",
        "Operator/Owner": "operator",
        "Users": "users",
        "Purpose": "purpose",
        "Detailed Purpose": "detailed_purpose",
        "Class of Orbit": "orbit_class",
        "Type of Orbit": "orbit_type",
        "Longitude of GEO (degrees)": "geo_longitude",
        "Perigee (Kilometers)": "perigee_km",
        "Apogee (Kilometers)": "apogee_km",
        "Eccentricity": "eccentricity",
        "Inclination (Degrees)": "inclination_deg",
        "Period (Minutes)": "period_minutes",
        "Launch Mass (Kilograms)": "launch_mass_kg",
        "Dry Mass (Kilograms)": "dry_mass_kg",
        "Power (Watts)": "power_watts",
        "Date of Launch": "launch_date",
        "Expected Lifetime (Years)": "expected_lifetime_years",
        "Contractor": "contractor",
        "Country of Contractor": "contractor_country",
        "Launch Site": "launch_site",
        "Launch Vehicle": "launch_vehicle",
        "COSPAR Number": "cospar_id",
        "NORAD Number": "norad_id",
        "Source Used for Orbital Data": "source_refs",
    }
    df = df.rename(columns=col_rename)

    # Snake-case any remaining columns not in the rename map
    rename_map = {}
    for col in df.columns:
        if col not in col_rename.values():
            snake = col.replace(" ", "_").replace("-", "_").replace("(", "").replace(")", "").lower()
            if snake != col:
                rename_map[col] = snake
    if rename_map:
        df = df.rename(columns=rename_map)

    # Convert numerics
    for col in ["geo_longitude", "perigee_km", "apogee_km", "eccentricity",
                "inclination_deg", "period_minutes", "launch_mass_kg", "dry_mass_kg",
                "power_watts", "expected_lifetime_years", "norad_id"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Clean string columns
    for col in ["satellite_name", "country_registry", "operator", "users",
                "purpose", "detailed_purpose", "orbit_class", "orbit_type",
                "contractor", "contractor_country", "launch_site", "launch_vehicle",
                "cospar_id", "source_refs"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
            )

    check_dataset(df, "ucs", min_rows=5000,
        expected_columns=["satellite_name", "norad_id", "purpose", "orbit_class"],
        critical_columns=["satellite_name"])

    # Stats for README
    n_total = len(df)
    n_countries = int(df["country_registry"].nunique()) if "country_registry" in df.columns else 0
    n_purposes = int(df["purpose"].nunique()) if "purpose" in df.columns else 0
    top_orbits = df["orbit_class"].value_counts().head(5) if "orbit_class" in df.columns else pd.Series()
    top_orbits_str = ", ".join(f"{o} ({c:,})" for o, c in top_orbits.items())

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "ucs_satellite_database.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "UCS Satellite Database"
language:
  - en
description: "Comprehensive database of active satellites maintained by the Union of Concerned Scientists, including orbital parameters, purpose, and ownership. Updated quarterly."
task_categories:
  - tabular-classification
tags:
  - space
  - satellite
  - orbit
  - ucs
  - launch
  - open-data
  - tabular-data
size_categories:
  - 1K<n<10K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/ucs_satellite_database.parquet
    default: true
---

# UCS Satellite Database

*Part of the [Orbital Mechanics Datasets](https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994) collection on Hugging Face.*

![Update UCS](https://github.com/juliensimon/space-datasets/actions/workflows/update-ucs.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.ucs&label=updated&color=brightgreen)

The Union of Concerned Scientists (UCS) Satellite Database is the most comprehensive
publicly available database of operational satellites, currently tracking **{n_total:,}**
active satellites from {n_countries} countries/organizations across {n_purposes} purpose categories.

## Dataset description

The UCS Satellite Database has been maintained since 2005 and is updated roughly quarterly.
It includes detailed information about each operational satellite: its name, country of
registry, operator, purpose (communications, Earth observation, navigation, scientific,
technology development, etc.), orbital parameters, launch details, and physical characteristics.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `satellite_name` | string | Name of the satellite |
| `country_registry` | string | Country/organization of UN registry |
| `operator` | string | Satellite operator/owner |
| `users` | string | User category (civil, commercial, government, military) |
| `purpose` | string | Primary purpose |
| `detailed_purpose` | string | Detailed purpose description |
| `orbit_class` | string | Orbit class (LEO, MEO, GEO, Elliptical) |
| `orbit_type` | string | Orbit type |
| `perigee_km` | float64 | Perigee altitude (km) |
| `apogee_km` | float64 | Apogee altitude (km) |
| `inclination_deg` | float64 | Orbital inclination (degrees) |
| `period_minutes` | float64 | Orbital period (minutes) |
| `launch_mass_kg` | float64 | Launch mass (kg) |
| `launch_date` | string | Date of launch |
| `norad_id` | float64 | NORAD catalog number |
| `cospar_id` | string | COSPAR designation |

## Quick stats

- **{n_total:,}** active satellites
- **{n_countries}** countries/organizations
- **{n_purposes}** purpose categories
- Orbit classes: {top_orbits_str}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/ucs-satellite-database", split="train")
df = ds.to_pandas()

# Satellites by orbit class
print(df["orbit_class"].value_counts())

# Communications satellites
comms = df[df["purpose"].str.contains("Communications", na=False)]
print(f"{{len(comms):,}} communications satellites")

# Satellites by country
by_country = df["country_registry"].value_counts().head(10)
print(by_country)
```

## Data source

[Union of Concerned Scientists Satellite Database](https://www.ucsusa.org/resources/satellite-database).

## Update schedule

Quarterly (1st of the month at 06:00 UTC) via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [space-track-satcat](https://huggingface.co/datasets/juliensimon/space-track-satcat) -- NORAD Satellite Catalog
- [satnogs-transmitters](https://huggingface.co/datasets/juliensimon/satnogs-transmitters) -- SatNOGS Transmitter Database

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/ucs-satellite-database) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{ucs_satellite_database,
  author = {{Simon, Julien}},
  title = {{UCS Satellite Database}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/ucs-satellite-database}},
  note = {{Based on the Union of Concerned Scientists Satellite Database}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update UCS satellite database: {n_total:,} satellites"
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
