#!/usr/bin/env python3
"""Fetch UCS Satellite Database and upload to HF."""

import io
import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

from dataset_images import banner_markdown, download_banner
from validate import check_dataset


HF_REPO = "juliensimon/ucs-satellite-database"

UCS_URLS = [
    # Stable media redirect — points to whatever version UCS currently hosts
    "https://www.ucs.org/media/11492",
    # Direct file link (May 2023 version, latest available as of Apr 2026)
    "https://www.ucs.org/sites/default/files/2024-01/UCS-Satellite-Database%205-1-2023.xlsx",
    # Legacy paths in case UCS publishes a newer version
    "https://www.ucsusa.org/sites/default/files/2025-02/UCS-Satellite-Database-5-1-2024.xlsx",
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

    # Drop unnamed/empty columns (Excel artifacts)
    df = df.loc[:, ~df.columns.str.startswith("Unnamed")]
    df = df.loc[:, ~df.columns.str.startswith("Source.")]
    # Drop the standalone "Source" column if "Source Used for Orbital Data" exists
    if "Source Used for Orbital Data" in df.columns and "Source" in df.columns:
        df = df.drop(columns=["Source"])

    # Rename columns to snake_case — handle both 2023 and 2024 UCS column naming
    col_rename = {
        "Name of Satellite": "satellite_name",
        "Name of Satellite, Alternate Names": "satellite_name",
        "Current Official Name of Satellite": "official_name",
        "Country/Org of UN Registry": "country_registry",
        "Country of Operator/Owner": "operator_country",
        "Operator/Owner": "operator",
        "Users": "users",
        "Purpose": "purpose",
        "Detailed Purpose": "detailed_purpose",
        "Class of Orbit": "orbit_class",
        "Type of Orbit": "orbit_type",
        "Longitude of GEO (degrees)": "geo_longitude",
        "Perigee (Kilometers)": "perigee_km",
        "Perigee (km)": "perigee_km",
        "Apogee (Kilometers)": "apogee_km",
        "Apogee (km)": "apogee_km",
        "Eccentricity": "eccentricity",
        "Inclination (Degrees)": "inclination_deg",
        "Inclination (degrees)": "inclination_deg",
        "Period (Minutes)": "period_minutes",
        "Period (minutes)": "period_minutes",
        "Launch Mass (Kilograms)": "launch_mass_kg",
        "Launch Mass (kg.)": "launch_mass_kg",
        "Dry Mass (Kilograms)": "dry_mass_kg",
        "Dry Mass (kg.)": "dry_mass_kg",
        "Power (Watts)": "power_watts",
        "Power (watts)": "power_watts",
        "Date of Launch": "launch_date",
        "Expected Lifetime (Years)": "expected_lifetime_years",
        "Expected Lifetime (yrs.)": "expected_lifetime_years",
        "Contractor": "contractor",
        "Country of Contractor": "contractor_country",
        "Launch Site": "launch_site",
        "Launch Vehicle": "launch_vehicle",
        "COSPAR Number": "cospar_id",
        "NORAD Number": "norad_id",
        "Comments": "comments",
        "Source Used for Orbital Data": "source_refs",
        "Source": "source_refs",
    }
    df = df.rename(columns=col_rename)

    # Snake-case any remaining columns not in the rename map
    rename_map = {}
    for col in df.columns:
        if col not in col_rename.values():
            snake = col.replace(" ", "_").replace("-", "_").replace("(", "").replace(")", "").replace(".", "").lower()
            if snake != col:
                rename_map[col] = snake
    if rename_map:
        df = df.rename(columns=rename_map)

    # Drop duplicate columns (can happen when both 2023 and 2024 names map to same target)
    df = df.loc[:, ~df.columns.duplicated()]

    # Convert numerics (coerce handles strings like "1,500-1,900" gracefully)
    numeric_cols = ["geo_longitude", "perigee_km", "apogee_km", "eccentricity",
                    "inclination_deg", "period_minutes", "launch_mass_kg", "dry_mass_kg",
                    "power_watts", "expected_lifetime_years", "norad_id"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Coerce remaining object columns to clean strings
    str_cols = [c for c in df.columns if c not in numeric_cols and df[c].dtype == "object"]
    for col in str_cols:
        df[col] = df[col].astype(str).str.strip().replace(
            {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA, "none": pd.NA}
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

        banner_file = download_banner("ucs", tmp)
        banner_md = banner_markdown("ucs", banner_file)

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
  - parquet
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
{banner_md}
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

What makes the UCS database uniquely valuable is its focus on the "why" behind each satellite, not just the "where." While NORAD's SATCAT tracks orbital parameters and the TLE catalog provides ephemeris data, the UCS database adds the human layer: who operates each satellite, what it does, who pays for it, and what sector it serves. This makes it the go-to source for policy researchers studying the militarization of space, economists analyzing the satellite communications market, and journalists reporting on the growing commercial space industry. The database distinguishes between civil, commercial, government, and military users, and categorizes purposes from broadband communications to weather monitoring to signals intelligence.

The database captures the full diversity of the operational satellite population across all orbit regimes. LEO satellites (below 2,000 km) include Earth observation platforms, broadband mega-constellations, and scientific missions. MEO hosts navigation constellations like GPS and Galileo. GEO satellites at 35,786 km serve as communications relays, weather sentinels, and early warning platforms. Elliptical orbits like Molniya and Tundra provide high-latitude coverage for nations like Russia. Physical parameters such as launch mass, dry mass, and power output help characterize satellite capability classes, from 1-kg CubeSats to 6,000-kg GEO communications platforms.

Because the UCS database is curated by analysts rather than generated automatically from tracking data, it includes contextual information that no orbital catalog can provide -- contractor details, expected lifetime, and purpose classifications that require human judgment. This makes it an essential complement to the SATCAT and TLE datasets for any comprehensive analysis of the space environment.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `satellite_name` | string | Official satellite name as registered with UNOOSA (e.g. "STARLINK-1234", "GPS IIF-10", "Sentinel-2A") |
| `country_registry` | string | Country or organization that registered the satellite with the UN; may differ from operator's nationality |
| `operator` | string | Organization operating or owning the satellite (e.g. "SpaceX", "NASA", "ESA", "Intelsat") |
| `users` | string | Primary user category: "Civil", "Commercial", "Government", or "Military"; occasionally multi-value slash-separated |
| `purpose` | string | Primary mission purpose (e.g. "Communications", "Earth Observation", "Navigation", "Technology Development", "Space Science") |
| `detailed_purpose` | string | Expanded purpose description from the UCS spreadsheet (e.g. "Communications/Maritime tracking", "Earth Observation/SAR"); null for entries without a sub-classification |
| `orbit_class` | string | Orbital regime: "LEO" (altitude <2,000 km), "MEO" (2,000–35,786 km), "GEO" (~35,786 km geostationary), "Elliptical" (highly elliptical/Molniya orbits) |
| `orbit_type` | string | More specific orbit description (e.g. "Sun-synchronous", "Polar", "Inclined geosynchronous"); null if not classified |
| `perigee_km` | float64 | Closest orbital altitude above Earth's surface in km; null for GEO satellites (listed as circular) or missing TLE data |
| `apogee_km` | float64 | Farthest orbital altitude above Earth's surface in km; null for GEO satellites or missing TLE data; equals perigee for circular orbits |
| `inclination_deg` | float64 | Orbital inclination in degrees relative to the equatorial plane; range 0° (equatorial) to 98° (sun-synchronous); null if not available |
| `period_minutes` | float64 | Orbital period in minutes; ~90 min for LEO (400 km), ~1,436 min for GEO; null if not available |
| `launch_mass_kg` | float64 | Satellite mass at launch in kilograms; null for most entries (UCS coverage is incomplete) |
| `launch_date` | string | ISO 8601 UTC date of launch (YYYY-MM-DD); null for entries with missing registry dates |
| `norad_id` | float64 | NORAD Space Surveillance Network catalog number; unique per object; float due to pandas NA handling; join key with TLE/SATCAT datasets |
| `cospar_id` | string | COSPAR/NSSDC international designator (e.g. "2019-074A"); format YYYY-NNNL; null if not assigned |

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
