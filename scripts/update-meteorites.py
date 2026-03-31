#!/usr/bin/env python3
"""Fetch meteorite database from Wikidata and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset


HF_REPO = "juliensimon/meteorite-database"

WIKIDATA_URL = "https://query.wikidata.org/sparql"
HEADERS = {"User-Agent": "space-datasets/1.0 (https://github.com/juliensimon/space-datasets)"}

SPARQL_QUERY = """
SELECT ?met ?metLabel ?fallDate ?mass
       ?classLabel ?countryLabel
       ?lat ?lon ?fallFind
WHERE {
  ?met wdt:P31 wd:Q60186.
  OPTIONAL { ?met wdt:P585 ?fallDate. }
  OPTIONAL { ?met wdt:P2067 ?mass. }
  OPTIONAL { ?met wdt:P279 ?class. }
  OPTIONAL { ?met wdt:P17 ?country. }
  OPTIONAL { ?met p:P625 ?coordStmt.
             ?coordStmt psv:P625 ?coordNode.
             ?coordNode wikibase:geoLatitude ?lat.
             ?coordNode wikibase:geoLongitude ?lon. }
  OPTIONAL { ?met wdt:P1269 ?fallFindType.
             BIND(IF(?fallFindType = wd:Q194288, "Fall", "Find") AS ?fallFind) }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,mul". }
}
"""


def fetch_meteorites() -> pd.DataFrame:
    """Query Wikidata SPARQL for all meteorites."""
    print("Querying Wikidata for meteorites...")
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
        wikidata_id = r.get("met", {}).get("value", "").rsplit("/", 1)[-1]
        mass_raw = r.get("mass", {}).get("value")
        lat_raw = r.get("lat", {}).get("value")
        lon_raw = r.get("lon", {}).get("value")
        fall_date_raw = r.get("fallDate", {}).get("value", "")
        rows.append({
            "wikidata_id": wikidata_id,
            "name": r.get("metLabel", {}).get("value"),
            "fall_date": fall_date_raw[:10] if fall_date_raw else None,
            "mass_g": float(mass_raw) if mass_raw else None,
            "classification": r.get("classLabel", {}).get("value"),
            "country": r.get("countryLabel", {}).get("value"),
            "latitude": float(lat_raw) if lat_raw else None,
            "longitude": float(lon_raw) if lon_raw else None,
            "fall_or_find": r.get("fallFind", {}).get("value"),
        })

    df = pd.DataFrame(rows)

    # Deduplicate on wikidata_id — multiple optional properties can produce
    # multiple rows for the same entity; keep first occurrence
    df = df.drop_duplicates(subset=["wikidata_id"], keep="first")

    # Drop bare Q-ID names (junk Wikidata entries without a real label)
    df = df[~df["name"].str.match(r"^Q\d+$", na=False)]

    return df


def main():
    df = fetch_meteorites()

    # Clean string columns
    for col in ["name", "classification", "country", "fall_or_find"]:
        df[col] = df[col].astype(str).str.strip().replace(
            {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
        )

    # Ensure numeric types
    df["mass_g"] = pd.to_numeric(df["mass_g"], errors="coerce")
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")

    df = df.sort_values("name").reset_index(drop=True)
    print(f"  {len(df):,} unique meteorites")

    check_dataset(df, "meteorites", min_rows=500,
                  expected_columns=["name"],
                  critical_columns=["name"])

    # Stats for README
    n = len(df)
    n_with_mass = int(df["mass_g"].notna().sum())
    n_with_coords = int(df["latitude"].notna().sum())
    n_countries = int(df["country"].nunique())

    heaviest = df.loc[df["mass_g"].idxmax()] if n_with_mass > 0 else None
    heaviest_str = (
        f"{heaviest['name']} ({heaviest['mass_g']:,.0f} g)"
        if heaviest is not None else "N/A"
    )

    top_countries = df["country"].value_counts().head(5)
    top_countries_str = ", ".join(
        f"{c} ({cnt:,})" for c, cnt in top_countries.items()
    )

    n_falls = int((df["fall_or_find"] == "Fall").sum())
    n_finds = int((df["fall_or_find"] == "Find").sum())

    top_classes = df["classification"].value_counts().head(5)
    top_classes_str = ", ".join(
        f"{c} ({cnt:,})" for c, cnt in top_classes.items()
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "meteorites.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_kb = out.stat().st_size / 1024
        print(f"  {size_kb:.0f} KB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc0-1.0
pretty_name: "Meteorite Database"
language:
  - en
description: >-
  Known meteorites catalogued in Wikidata, including mass, classification,
  fall date, country of recovery, and geographic coordinates.
  {n:,} meteorites with metadata sourced from the community-curated
  Wikidata knowledge base.
size_categories:
  - 1K<n<10K
task_categories:
  - tabular-classification
tags:
  - space
  - planetary-science
  - meteorites
  - wikidata
  - open-data
  - tabular-data
  - parquet
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/meteorites.parquet
---

# Meteorite Database

*Part of the [Planetary Science Datasets](https://huggingface.co/collections/juliensimon/planetary-science-datasets-69c2d4683bd6a66c34fb4af2) collection on Hugging Face.*

Catalogue of **{n:,}** known meteorites sourced from [Wikidata](https://www.wikidata.org/),
covering mass, classification, fall date, country of recovery, and geographic coordinates.

## Dataset description

Meteorites are extraterrestrial rocks that survive passage through Earth's atmosphere and
reach the surface. They are classified by mineralogy and petrology (e.g., chondrites,
achondrites, iron meteorites) and recorded either as *falls* (witnessed descent) or
*finds* (recovered without observation).

This dataset aggregates Wikidata entries for all entities of type Q60186 (meteorite), pulling
structured properties including mass (P2067), fall date (P585), country (P17), coordinates
(P625), and mineralogical class (P279). It complements NASA and Meteoritical Society
databases with Wikidata's multilingual, cross-linked knowledge graph.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `wikidata_id` | string | Wikidata entity ID (e.g. Q1029) |
| `name` | string | Meteorite name |
| `fall_date` | string | Date of fall or recovery (YYYY-MM-DD) |
| `mass_g` | float | Mass in grams |
| `classification` | string | Mineralogical/petrological classification |
| `country` | string | Country of recovery |
| `latitude` | float | Recovery latitude (decimal degrees) |
| `longitude` | float | Recovery longitude (decimal degrees) |
| `fall_or_find` | string | "Fall" (witnessed) or "Find" (unwitnessed recovery) |

## Quick stats

- **{n:,}** meteorites total
- **{n_with_mass:,}** with recorded mass
- **{n_with_coords:,}** with geographic coordinates
- **{n_countries:,}** countries of recovery
- **{n_falls:,}** falls, **{n_finds:,}** finds
- Heaviest: {heaviest_str}
- Top countries: {top_countries_str}
- Top classifications: {top_classes_str}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/meteorite-database", split="train")
df = ds.to_pandas()

# Heaviest meteorites
print(df.nlargest(10, "mass_g")[["name", "mass_g", "country", "classification"]])

# Falls vs finds
print(df["fall_or_find"].value_counts())

# Meteorites by country
print(df["country"].value_counts().head(10))

# Meteorites with coordinates (mappable)
mappable = df.dropna(subset=["latitude", "longitude"])
print(f"{{len(mappable):,}} meteorites with coordinates")

# Filter by classification
chondrites = df[df["classification"].str.contains("chondrite", case=False, na=False)]
print(f"{{len(chondrites):,}} chondrites")
```

## Data source

[Wikidata](https://www.wikidata.org/) SPARQL endpoint. Meteorites identified via
property P31 (instance of) = Q60186 (meteorite). Data is community-curated and
cross-referenced with the [Meteoritical Bulletin Database](https://www.lpi.usra.edu/meteor/).

## Update schedule

Quarterly (January, April, July, October). Run manually to capture interim additions.

## Related datasets

- [impact-craters](https://huggingface.co/datasets/juliensimon/impact-craters) -- Earth impact crater database
- [fireballs](https://huggingface.co/datasets/juliensimon/fireball-bolide-events) -- NASA fireball and bolide events

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/meteorite-database) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{meteorite_database,
  author = {{Simon, Julien}},
  title = {{Meteorite Database}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/meteorite-database}},
  note = {{Sourced from Wikidata (CC0)}}
}}
```

## License

[CC0-1.0](https://creativecommons.org/publicdomain/zero/1.0/) (Wikidata content is public domain)
""")

        print("Uploading to HF...")
        commit_msg = f"Update meteorite database: {n:,} meteorites"
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
