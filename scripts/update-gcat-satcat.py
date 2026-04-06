#!/usr/bin/env python3
"""Fetch GCAT Satellite Catalog, upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from dataset_images import banner_markdown, download_banner
from validate import check_dataset


URL = "https://planet4589.org/space/gcat/tsv/cat/satcat.tsv"
HF_REPO = "juliensimon/gcat-satellite-catalog"

COL_NAMES = [
    "jcat_id", "satcat_number", "launch_tag", "piece", "type", "name",
    "pl_name", "launch_date", "parent", "separation_date", "primary",
    "decay_date", "status", "dest", "owner", "state_code", "manufacturer",
    "bus", "motor", "mass_kg", "mass_flag", "dry_mass_kg", "dry_flag",
    "total_mass_kg", "total_flag", "length_m", "length_flag", "diameter_m",
    "diameter_flag", "span_m", "span_flag", "shape", "orbit_date",
    "perigee_km", "perigee_flag", "apogee_km", "apogee_flag",
    "inclination_deg", "inclination_flag", "op_orbit", "orbit_qual",
    "alt_names",
]

NUMERIC_COLS = [
    "satcat_number", "mass_kg", "dry_mass_kg", "total_mass_kg",
    "length_m", "diameter_m", "span_m",
    "perigee_km", "apogee_km", "inclination_deg",
]


def main():
    # ── Fetch ────────────────────────────────────────────────────────────
    print("Fetching GCAT satellite catalog...")
    df = pd.read_csv(
        URL, sep="\t", comment="#", names=COL_NAMES,
        low_memory=False, skipinitialspace=True,
    )
    print(f"  {len(df):,} objects")

    # ── Transform ────────────────────────────────────────────────────────
    # Strip whitespace from string columns
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].str.strip()

    # Replace GCAT dash placeholder with NaN
    df.replace("-", pd.NA, inplace=True)

    # Coerce numeric columns
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # ── Validate ─────────────────────────────────────────────────────────
    check_dataset(
        df, "gcat-satcat", min_rows=50000,
        expected_columns=["jcat_id", "name", "status", "owner", "state_code",
                          "launch_date", "perigee_km", "apogee_km"],
        critical_columns=["jcat_id", "name"],
    )

    # ── Write parquet + README ───────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        data_dir = tmp_dir / "data"
        data_dir.mkdir()
        df.to_parquet(
            data_dir / "satcat.parquet", index=False,
            engine="pyarrow", compression="zstd",
        )

        # Stats for README
        n_countries = df["state_code"].nunique()
        n_owners = df["owner"].nunique()
        n_orbits = df["op_orbit"].nunique()
        n_active = int((df["status"] == "O").sum()) if "status" in df.columns else 0
        n_decayed = int((df["status"] == "R").sum()) if "status" in df.columns else 0
        n_types = df["type"].nunique() if "type" in df.columns else 0

        banner_file = download_banner("gcat-satcat", tmp_dir)
        banner_md = banner_markdown("gcat-satcat", banner_file)

        (tmp_dir / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "GCAT Satellite Catalog"
language:
  - en
description: "Comprehensive satellite catalog from GCAT with {len(df):,} space objects — spacecraft, rocket bodies, debris — including orbital parameters, mass, and ownership. Based on Jonathan McDowell's General Catalog of Artificial Space Objects."
task_categories:
  - tabular-classification
tags:
  - space
  - satellites
  - satellite-catalog
  - gcat
  - orbital-mechanics
  - spacecraft
  - open-data
  - tabular-data
  - parquet
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/satcat.parquet
    default: true
size_categories:
  - 10K<n<100K
---

# GCAT Satellite Catalog
{banner_md}
*Part of the [Orbital Mechanics Datasets](https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994) collection on Hugging Face.*

Comprehensive catalog of **{len(df):,}** space objects from
[GCAT](https://planet4589.org/space/gcat/) (General Catalog of Artificial Space Objects),
maintained by Jonathan McDowell at the Harvard-Smithsonian Center for Astrophysics.
Covers every cataloged spacecraft, rocket body, and debris piece from 1957 to present,
with orbital parameters, physical dimensions, mass, ownership, and operational status.

## Dataset description

The GCAT Satellite Catalog (satcat) is the most comprehensive open reference for objects that have been cataloged in Earth orbit and beyond. Unlike the US Space Force catalog (which tracks radar-observable objects) or the UCS Satellite Database (which covers only active satellites), GCAT aims to catalog every artificial space object ever assigned an identifier — including rocket bodies, mission-related debris, and objects that reentered decades ago.

Each entry includes the JCAT identifier (McDowell's own comprehensive numbering), the NORAD/Space Force catalog number, COSPAR international designator, object type classification, ownership and manufacturer information, physical properties (mass, dimensions, shape), and orbital elements at a reference epoch. The status field distinguishes between objects still in orbit ("O"), those that have reentered ("R"), and other dispositions. The operational orbit field classifies the orbit type (LEO, MEO, GEO, HEO, etc.) with inclination qualifiers.

This dataset is valuable for studying the growth of the space object population over time, analyzing debris generation events, comparing national space programs by object count and mass on orbit, and building training data for orbital classification models. It complements the GCAT launch log (which records the launches that placed these objects) and the Space-Track SATCAT (which provides the official US military catalog perspective on the same objects).

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `jcat_id` | string | GCAT unique identifier (e.g. "S00001") |
| `satcat_number` | float | NORAD/Space Force catalog number |
| `launch_tag` | string | GCAT launch identifier |
| `piece` | string | COSPAR international designator |
| `type` | string | Object type code (P=payload, R=rocket body, D=debris, etc.) |
| `name` | string | Object name |
| `pl_name` | string | Payload name |
| `launch_date` | string | Launch date |
| `parent` | string | Parent object JCAT ID |
| `separation_date` | string | Separation date/time from parent |
| `primary` | string | Primary body (Earth, Moon, Sun, etc.) |
| `decay_date` | string | Reentry/decay date (if applicable) |
| `status` | string | Status: O=in orbit, R=reentered, AR=reentered after achieving orbit, etc. |
| `dest` | string | Destination code |
| `owner` | string | Owner/operator code |
| `state_code` | string | Country/state code |
| `manufacturer` | string | Manufacturer code |
| `bus` | string | Spacecraft bus/platform |
| `motor` | string | Propulsion motor |
| `mass_kg` | float | Object mass in kg |
| `mass_flag` | string | Mass qualifier flag |
| `dry_mass_kg` | float | Dry mass in kg |
| `dry_flag` | string | Dry mass qualifier flag |
| `total_mass_kg` | float | Total mass in kg |
| `total_flag` | string | Total mass qualifier flag |
| `length_m` | float | Length in meters |
| `length_flag` | string | Length qualifier flag |
| `diameter_m` | float | Diameter in meters |
| `diameter_flag` | string | Diameter qualifier flag |
| `span_m` | float | Span (e.g. solar panel wingspan) in meters |
| `span_flag` | string | Span qualifier flag |
| `shape` | string | Shape description |
| `orbit_date` | string | Orbital elements epoch date |
| `perigee_km` | float | Perigee altitude in km |
| `perigee_flag` | string | Perigee qualifier flag |
| `apogee_km` | float | Apogee altitude in km |
| `apogee_flag` | string | Apogee qualifier flag |
| `inclination_deg` | float | Orbital inclination in degrees |
| `inclination_flag` | string | Inclination qualifier flag |
| `op_orbit` | string | Operational orbit classification (LEO, MEO, GEO, HEO, etc.) |
| `orbit_qual` | string | Orbit quality indicator |
| `alt_names` | string | Alternative names/designations |

## Quick stats

- **{len(df):,}** cataloged space objects
- **{n_active:,}** currently in orbit (status "O")
- **{n_decayed:,}** reentered (status "R")
- **{n_countries}** countries/state codes
- **{n_owners}** distinct owners/operators
- **{n_orbits}** orbit type classifications
- **{n_types}** object type codes

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/gcat-satellite-catalog", split="train")
df = ds.to_pandas()

# Currently active satellites
active = df[df["status"] == "O"]
print(f"{{len(active):,}} objects currently in orbit")

# Objects by country
print(df["state_code"].value_counts().head(10))

# Heaviest objects in orbit
in_orbit = df[df["status"] == "O"].dropna(subset=["mass_kg"])
print(in_orbit.nlargest(10, "mass_kg")[["name", "owner", "mass_kg", "op_orbit"]])

# LEO vs GEO population
leo = df[df["op_orbit"].str.contains("LEO", na=False)]
geo = df[df["op_orbit"].str.contains("GEO", na=False)]
print(f"LEO: {{len(leo):,}}, GEO: {{len(geo):,}}")

# Growth of cataloged objects over time
df["launch_year"] = df["launch_date"].str[:4]
print(df["launch_year"].value_counts().sort_index().tail(10))
```

## Data source

[GCAT](https://planet4589.org/space/gcat/) (General Catalog of Artificial Space Objects)
by Jonathan McDowell, Harvard-Smithsonian Center for Astrophysics. GCAT is the most
comprehensive public catalog of artificial space objects and is widely used in the
spaceflight research community.

## Update schedule

Static dataset — rebuilt manually when GCAT is updated (approximately monthly).

## Related datasets

- [space-launch-log](https://huggingface.co/datasets/juliensimon/space-launch-log) — Complete global launch history from GCAT
- [space-track-satcat](https://huggingface.co/datasets/juliensimon/space-track-satcat) — NORAD satellite catalog from Space-Track
- [ucs-satellite-database](https://huggingface.co/datasets/juliensimon/ucs-satellite-database) — Union of Concerned Scientists active satellite database

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/gcat-satellite-catalog) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{gcat_satellite_catalog,
  author = {{Simon, Julien}},
  title = {{GCAT Satellite Catalog}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/gcat-satellite-catalog}},
  note = {{Based on GCAT by Jonathan McDowell, Harvard-Smithsonian Center for Astrophysics}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update GCAT satellite catalog: {len(df):,} objects"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp_dir), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={len(df)}\n")
    print(f"Done. {len(df):,} objects.")


if __name__ == "__main__":
    main()
