#!/usr/bin/env python3
"""Fetch impact crater database from Wikidata and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset


HF_REPO = "juliensimon/impact-craters"

WIKIDATA_URL = "https://query.wikidata.org/sparql"
HEADERS = {"User-Agent": "space-datasets/1.0 (https://github.com/juliensimon/space-datasets)"}

SPARQL_QUERY = """
SELECT ?crater ?craterLabel ?diameter ?age
       ?locationLabel ?bodyLabel
       ?lat ?lon
WHERE {
  ?crater wdt:P31/wdt:P279* wd:Q55818.
  OPTIONAL { ?crater wdt:P2386 ?diameter. }
  OPTIONAL { ?crater wdt:P7584 ?age. }
  OPTIONAL { ?crater wdt:P131 ?location. }
  OPTIONAL { ?crater wdt:P376 ?body. }
  OPTIONAL { ?crater p:P625 ?coordStmt.
             ?coordStmt psv:P625 ?coordNode.
             ?coordNode wikibase:geoLatitude ?lat.
             ?coordNode wikibase:geoLongitude ?lon. }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,mul". }
}
"""


def fetch_craters() -> pd.DataFrame:
    """Query Wikidata SPARQL for all impact craters."""
    print("Querying Wikidata for impact craters...")
    resp = requests.get(
        WIKIDATA_URL,
        params={"query": SPARQL_QUERY, "format": "json"},
        headers=HEADERS,
        timeout=180,
    )
    resp.raise_for_status()

    results = resp.json()["results"]["bindings"]
    print(f"  {len(results):,} raw rows from Wikidata")

    rows = []
    for r in results:
        wikidata_id = r.get("crater", {}).get("value", "").rsplit("/", 1)[-1]
        diameter_raw = r.get("diameter", {}).get("value")
        age_raw = r.get("age", {}).get("value")
        rows.append({
            "wikidata_id": wikidata_id,
            "name": r.get("craterLabel", {}).get("value"),
            "diameter_km": float(diameter_raw) if diameter_raw else None,
            "age_mya": float(age_raw) if age_raw else None,
            "location": r.get("locationLabel", {}).get("value") or None,
            "body": r.get("bodyLabel", {}).get("value") or None,
            "latitude": float(r["lat"]["value"]) if r.get("lat") else None,
            "longitude": float(r["lon"]["value"]) if r.get("lon") else None,
        })

    df = pd.DataFrame(rows)

    # Deduplicate on wikidata_id — multiple location/body matches can create duplicates
    # Keep the row with the most filled-in fields
    df["_filled"] = df.notna().sum(axis=1)
    df = df.sort_values("_filled", ascending=False).drop_duplicates(
        subset=["wikidata_id"], keep="first"
    ).drop(columns=["_filled"])

    # Drop bare Q-ID names (junk Wikidata entities with no label)
    df = df[~df["name"].str.match(r"^Q\d+$", na=False)]

    return df


def main():
    df = fetch_craters()

    # Clean string columns
    for col in ["name", "location", "body"]:
        df[col] = df[col].astype(str).str.strip().replace(
            {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
        )

    # Numeric coercions (guard against any stray non-numeric values)
    df["diameter_km"] = pd.to_numeric(df["diameter_km"], errors="coerce").astype("Float64")
    df["age_mya"] = pd.to_numeric(df["age_mya"], errors="coerce").astype("Float64")
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce").astype("Float64")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce").astype("Float64")

    df = df.sort_values("name").reset_index(drop=True)
    print(f"  {len(df):,} unique craters")

    check_dataset(df, "impact-craters", min_rows=1000,
                  expected_columns=["name", "body"],
                  critical_columns=["name"])

    # Stats for README
    n = len(df)
    n_with_diameter = int(df["diameter_km"].notna().sum())
    n_with_age = int(df["age_mya"].notna().sum())
    n_with_coords = int(df["latitude"].notna().sum())

    largest_idx = df["diameter_km"].idxmax() if n_with_diameter > 0 else None
    largest_name = df.loc[largest_idx, "name"] if largest_idx is not None else "N/A"
    largest_km = float(df.loc[largest_idx, "diameter_km"]) if largest_idx is not None else 0.0

    oldest_idx = df["age_mya"].idxmax() if n_with_age > 0 else None
    oldest_name = df.loc[oldest_idx, "name"] if oldest_idx is not None else "N/A"
    oldest_mya = float(df.loc[oldest_idx, "age_mya"]) if oldest_idx is not None else 0.0

    body_counts = df["body"].value_counts()
    top_bodies = body_counts.head(8)
    top_bodies_str = ", ".join(
        f"{body} ({cnt:,})" for body, cnt in top_bodies.items()
        if pd.notna(body) and str(body) not in ("nan", "None", "")
    )
    n_bodies = int(df["body"].nunique())

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "impact_craters.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_kb = out.stat().st_size / 1024
        print(f"  {size_kb:.0f} KB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc0-1.0
pretty_name: "Impact Craters"
language:
  - en
description: >-
  Impact craters across the solar system sourced from Wikidata.
  {n:,} craters spanning {n_bodies} planetary bodies, with diameter,
  age, and coordinates where available.
size_categories:
  - 1K<n<10K
task_categories:
  - tabular-classification
tags:
  - space
  - planetary-science
  - craters
  - impact
  - wikidata
  - open-data
  - tabular-data
  - parquet
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/impact_craters.parquet
---

# Impact Craters

*Part of the [Planetary Science Datasets](https://huggingface.co/collections/juliensimon/planetary-science-datasets-69c2d4683bd6a66c34fb4af2) collection on Hugging Face.*

Comprehensive database of impact craters across the solar system — **{n:,}** craters
on **{n_bodies}** planetary bodies, sourced from [Wikidata](https://www.wikidata.org/).

## Dataset description

Impact craters are among the most widespread geological features in the solar system,
formed when asteroids, comets, or meteoroids collide with a planetary surface. They are
critical windows into a body's geological history: crater size-frequency distributions
reveal relative ages of surfaces, and large craters like Chicxulub on Earth have been
linked to mass extinction events.

This dataset aggregates crater records for bodies ranging from Mercury and the Moon to
Mars, Ceres, Vesta, and outer-planet moons. Each record includes the crater name,
diameter (where known), estimated age in millions of years, the parent body, and
geographic coordinates for bodies with established coordinate systems.

Sourced from Wikidata's structured knowledge base (class Q55818: impact crater),
maintained by the WikiProject Astronomy and WikiProject Solar System communities.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `wikidata_id` | string | Wikidata entity ID (e.g. Q12345) |
| `name` | string | Crater name |
| `diameter_km` | float | Crater diameter (kilometres) |
| `age_mya` | float | Estimated age (millions of years ago) |
| `location` | string | Administrative or geographic location label |
| `body` | string | Planetary body (Earth, Moon, Mars, etc.) |
| `latitude` | float | Latitude (degrees) |
| `longitude` | float | Longitude (degrees) |

## Quick stats

- **{n:,}** craters on **{n_bodies}** planetary bodies
- **{n_with_diameter:,}** craters with known diameter
- **{n_with_age:,}** craters with estimated age
- **{n_with_coords:,}** craters with coordinates
- Largest crater: {largest_name} ({largest_km:,.0f} km)
- Oldest crater: {oldest_name} ({oldest_mya:,.0f} Ma)
- Craters per body: {top_bodies_str}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/impact-craters", split="train")
df = ds.to_pandas()

# Craters by body
print(df["body"].value_counts())

# Largest craters
largest = df.nlargest(10, "diameter_km")[["name", "body", "diameter_km", "age_mya"]]
print(largest)

# Earth craters with coordinates
earth = df[(df["body"] == "Earth") & df["latitude"].notna()]
print(f"{{len(earth):,}} Earth craters with coordinates")

# Ancient craters (> 2 Ga)
ancient = df[df["age_mya"] > 2000].sort_values("age_mya", ascending=False)
print(ancient[["name", "body", "diameter_km", "age_mya"]].head(10))
```

## Data source

[Wikidata](https://www.wikidata.org/) SPARQL endpoint. Craters identified via
instance-of (P31) / subclass-of (P279) chain anchored at Q55818 (impact crater).
Data is community-curated by
[WikiProject Astronomy](https://www.wikidata.org/wiki/Wikidata:WikiProject_Astronomy)
and [WikiProject Solar System](https://www.wikidata.org/wiki/Wikidata:WikiProject_Solar_System).

## Update schedule

Quarterly (January, April, July, October). Re-run manually at any time to pick up
newly catalogued craters.

## Related datasets

- [ceres-craters](https://huggingface.co/datasets/juliensimon/ceres-craters) — Ceres crater catalog
- [meteorite-database](https://huggingface.co/datasets/juliensimon/meteorite-database) — Meteorite landings
- [planetary-nomenclature](https://huggingface.co/datasets/juliensimon/planetary-nomenclature) — IAU planetary feature names

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/impact-craters) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{impact_craters,
  author = {{Simon, Julien}},
  title = {{Impact Craters}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/impact-craters}},
  note = {{Sourced from Wikidata (CC0)}}
}}
```

## License

[CC0-1.0](https://creativecommons.org/publicdomain/zero/1.0/) (Wikidata content is public domain)
""")

        print("Uploading to HF...")
        commit_msg = f"Update impact craters: {n:,} craters"
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
