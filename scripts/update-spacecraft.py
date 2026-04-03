#!/usr/bin/env python3
"""Fetch spacecraft database from Wikidata and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

from dataset_images import banner_markdown, download_banner
from validate import check_dataset


HF_REPO = "juliensimon/spacecraft-database"

WIKIDATA_URL = "https://query.wikidata.org/sparql"
HEADERS = {"User-Agent": "space-datasets/1.0 (https://github.com/juliensimon/space-datasets)"}

SPARQL_QUERY = """
SELECT ?craft ?craftLabel ?launch_date ?decommissioned
       ?operatorLabel ?manufacturerLabel
       ?orbitLabel ?massKg ?missionLabel
WHERE {
  ?craft wdt:P31/wdt:P279* wd:Q40218.
  OPTIONAL { ?craft wdt:P619 ?launch_date. }
  OPTIONAL { ?craft wdt:P3999 ?decommissioned. }
  OPTIONAL { ?craft wdt:P137 ?operator. }
  OPTIONAL { ?craft wdt:P176 ?manufacturer. }
  OPTIONAL { ?craft wdt:P522 ?orbit. }
  OPTIONAL { ?craft wdt:P2067 ?massKg. }
  OPTIONAL { ?craft wdt:P361 ?mission. }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,mul". }
}
"""


def fetch_spacecraft() -> pd.DataFrame:
    """Query Wikidata SPARQL for all spacecraft."""
    print("Querying Wikidata for spacecraft...")
    resp = requests.get(
        WIKIDATA_URL,
        params={"query": SPARQL_QUERY, "format": "json"},
        headers=HEADERS,
        timeout=120,
    )
    resp.raise_for_status()

    results = resp.json()["results"]["bindings"]
    print(f"  {len(results):,} raw rows from Wikidata")

    rows = []
    for r in results:
        wikidata_id = r.get("craft", {}).get("value", "").rsplit("/", 1)[-1]
        mass_raw = r.get("massKg", {}).get("value")
        mass_kg = None
        if mass_raw:
            try:
                mass_kg = float(mass_raw)
            except (ValueError, TypeError):
                mass_kg = None
        rows.append({
            "wikidata_id": wikidata_id,
            "name": r.get("craftLabel", {}).get("value"),
            "launch_date": r.get("launch_date", {}).get("value", "")[:10] or None,
            "decommissioned_date": r.get("decommissioned", {}).get("value", "")[:10] or None,
            "operator": r.get("operatorLabel", {}).get("value"),
            "manufacturer": r.get("manufacturerLabel", {}).get("value"),
            "orbit_type": r.get("orbitLabel", {}).get("value"),
            "mass_kg": mass_kg,
            "mission": r.get("missionLabel", {}).get("value"),
        })

    df = pd.DataFrame(rows)

    # Deduplicate: keep the row with the most non-null fields per wikidata_id
    df["_non_null"] = df.notna().sum(axis=1)
    df = df.sort_values("_non_null", ascending=False).drop_duplicates(
        subset=["wikidata_id"], keep="first"
    ).drop(columns=["_non_null"])

    # Drop entries with no real name (bare Q-IDs = junk Wikidata entities)
    df = df[~df["name"].str.match(r"^Q\d+$", na=False)]

    return df


def main():
    df = fetch_spacecraft()

    # Clean string columns
    for col in ["name", "operator", "manufacturer", "orbit_type", "mission"]:
        df[col] = df[col].astype(str).str.strip().replace(
            {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
        )

    # Cast mass_kg to Float64 for nullable float support
    df["mass_kg"] = df["mass_kg"].astype("Float64")

    # Derive launch_year for stats
    df["launch_year"] = pd.to_datetime(df["launch_date"], errors="coerce").dt.year

    df = df.sort_values("launch_date", na_position="last").reset_index(drop=True)
    print(f"  {len(df):,} unique spacecraft")

    check_dataset(df, "spacecraft", min_rows=2000,
                  expected_columns=["name", "launch_date"],
                  critical_columns=["name"])

    # Stats for README
    n = len(df)
    n_with_date = int(df["launch_date"].notna().sum())
    n_with_mass = int(df["mass_kg"].notna().sum())
    n_operators = int(df["operator"].nunique())
    n_orbits = int(df["orbit_type"].nunique())
    top_operators = df["operator"].value_counts().head(5)
    top_operators_str = ", ".join(f"{op} ({cnt:,})" for op, cnt in top_operators.items())
    top_orbits = df["orbit_type"].value_counts().head(5)
    top_orbits_str = ", ".join(f"{orb} ({cnt:,})" for orb, cnt in top_orbits.items())
    earliest = df["launch_date"].dropna().min()
    latest = df["launch_date"].dropna().max()

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "spacecraft.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_kb = out.stat().st_size / 1024
        print(f"  {size_kb:.0f} KB parquet")

        banner_file = download_banner("spacecraft", tmp)
        banner_md = banner_markdown("spacecraft", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc0-1.0
pretty_name: "Spacecraft Database"
language:
  - en
description: >-
  Comprehensive database of spacecraft sourced from Wikidata.
  {n:,} spacecraft including satellites, probes, and space stations,
  with launch dates, operators, manufacturers, and orbital parameters.
size_categories:
  - 1K<n<10K
task_categories:
  - tabular-classification
tags:
  - space
  - spacecraft
  - satellites
  - wikidata
  - open-data
  - tabular-data
  - parquet
configs:
  - config_name: default
    default: true
    data_files:
      - split: train
        path: data/spacecraft.parquet
---

# Spacecraft Database
{banner_md}
*Part of the [Orbital Mechanics Datasets](https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994) collection on Hugging Face.*

Comprehensive database of **{n:,}** spacecraft — satellites, probes, space stations, and more — sourced from [Wikidata](https://www.wikidata.org/).

## Dataset description

From the earliest Sputnik satellites to modern mega-constellations and deep space probes, this dataset catalogs spacecraft across the entire history of the Space Age. Each record includes launch and decommission dates, operating agency, manufacturer, orbital regime, mass, and associated mission where available.

The dataset draws on Wikidata's structured knowledge base using the spacecraft class (Q40218) and all its subclasses. It is maintained by the WikiProject Spaceflight community and updated as new spacecraft are launched and documented.

Records span from **{earliest}** to **{latest}**, with **{n_with_date:,}** spacecraft having a known launch date and **{n_with_mass:,}** with a recorded mass.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `wikidata_id` | string | Wikidata entity ID (e.g. Q48371) |
| `name` | string | Spacecraft name |
| `launch_date` | string | Launch date (YYYY-MM-DD) |
| `decommissioned_date` | string | Decommissioning date (YYYY-MM-DD) |
| `operator` | string | Operating agency or organization |
| `manufacturer` | string | Manufacturer name |
| `orbit_type` | string | Orbital regime (e.g. LEO, GEO, heliocentric) |
| `mass_kg` | float | Spacecraft mass in kilograms |
| `mission` | string | Associated mission name |
| `launch_year` | int | Launch year (derived from launch_date) |

## Quick stats

- **{n:,}** total spacecraft in the database
- **{n_with_date:,}** spacecraft with a known launch date
- **{n_with_mass:,}** spacecraft with a recorded mass
- **{n_operators:,}** distinct operators
- **{n_orbits:,}** distinct orbital regimes
- Date range: {earliest} to {latest}
- Top operators: {top_operators_str}
- Top orbital regimes: {top_orbits_str}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/spacecraft-database", split="train")
df = ds.to_pandas()

# Spacecraft by operator
print(df["operator"].value_counts().head(10))

# Spacecraft by orbital regime
print(df["orbit_type"].value_counts().head(10))

# Spacecraft launched per year
print(df["launch_year"].value_counts().sort_index())

# Heaviest spacecraft
heaviest = df.nlargest(10, "mass_kg")[["name", "operator", "mass_kg", "orbit_type"]]
print(heaviest)

# Still operational (no decommission date)
operational = df[df["decommissioned_date"].isna() & df["launch_date"].notna()]
print(f"{{len(operational):,}} spacecraft with no recorded decommission date")
```

## Data source

[Wikidata](https://www.wikidata.org/) SPARQL endpoint. Spacecraft identified via
property P31 (instance of) = Q40218 (spacecraft) and all subclasses via P279*.
Data is community-curated by [WikiProject Spaceflight](https://www.wikidata.org/wiki/Wikidata:WikiProject_Spaceflight).

## Update schedule

Quarterly (January, April, July, October).

## Related datasets

- [space-missions](https://huggingface.co/datasets/juliensimon/space-missions) -- Space missions database
- [satcat](https://huggingface.co/datasets/juliensimon/space-track-satcat) -- Satellite catalog (SATCAT)
- [launch-vehicles](https://huggingface.co/datasets/juliensimon/launch-vehicles) -- Launch vehicle catalog

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/spacecraft-database) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{spacecraft_database,
  author = {{Simon, Julien}},
  title = {{Spacecraft Database}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/spacecraft-database}},
  note = {{Sourced from Wikidata (CC0)}}
}}
```

## License

[CC0-1.0](https://creativecommons.org/publicdomain/zero/1.0/) (Wikidata content is public domain)
""")

        print("Uploading to HF...")
        commit_msg = f"Update spacecraft database: {n:,} spacecraft"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={n}\n")
    print("Done.")


if __name__ == "__main__":
    main()
