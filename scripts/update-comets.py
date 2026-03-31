#!/usr/bin/env python3
"""Fetch comet catalog from Wikidata and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset


HF_REPO = "juliensimon/comet-catalog"

WIKIDATA_URL = "https://query.wikidata.org/sparql"
HEADERS = {"User-Agent": "space-datasets/1.0 (https://github.com/juliensimon/space-datasets)"}

SPARQL_QUERY = """
SELECT ?comet ?cometLabel ?discoveryDate ?discovererLabel
       ?orbitalPeriod ?perihelion ?eccentricity ?inclination
       ?namedAfterLabel ?epoch
WHERE {
  ?comet wdt:P31/wdt:P279* wd:Q3559.
  OPTIONAL { ?comet wdt:P575 ?discoveryDate. }
  OPTIONAL { ?comet wdt:P61 ?discoverer. }
  OPTIONAL { ?comet wdt:P2146 ?orbitalPeriod. }
  OPTIONAL { ?comet wdt:P2244 ?perihelion. }
  OPTIONAL { ?comet wdt:P1096 ?eccentricity. }
  OPTIONAL { ?comet wdt:P2045 ?inclination. }
  OPTIONAL { ?comet wdt:P138 ?namedAfter. }
  OPTIONAL { ?comet wdt:P6259 ?epoch. }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,mul". }
}
"""


def fetch_comets() -> pd.DataFrame:
    """Query Wikidata SPARQL for all comets."""

    def safe_float(r, key):
        """Parse float from Wikidata value, returning None for blank nodes or bad data."""
        val = r.get(key, {}).get("value")
        if not val:
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    print("Querying Wikidata for comets...")
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
        wikidata_id = r.get("comet", {}).get("value", "").rsplit("/", 1)[-1]
        rows.append({
            "wikidata_id": wikidata_id,
            "name": r.get("cometLabel", {}).get("value"),
            "discovery_date": r.get("discoveryDate", {}).get("value", "")[:10] or None,
            "discoverer": r.get("discovererLabel", {}).get("value") or None,
            "orbital_period_yr": safe_float(r, "orbitalPeriod"),
            "perihelion_au": safe_float(r, "perihelion"),
            "eccentricity": safe_float(r, "eccentricity"),
            "inclination_deg": safe_float(r, "inclination"),
            "named_after": r.get("namedAfterLabel", {}).get("value") or None,
            "epoch": r.get("epoch", {}).get("value", "")[:10] or None,
        })

    df = pd.DataFrame(rows)

    # Deduplicate on wikidata_id: keep the most complete row
    # Score completeness by count of non-null fields
    df["_completeness"] = df.notna().sum(axis=1)
    df = df.sort_values("_completeness", ascending=False).drop_duplicates(
        subset=["wikidata_id"], keep="first"
    ).drop(columns=["_completeness"])

    # Drop bare Q-ID names (junk Wikidata entities with no label)
    df = df[~df["name"].str.match(r"^Q\d+$", na=False)]

    return df


def main():
    df = fetch_comets()

    # Clean string columns
    for col in ["name", "discoverer", "named_after", "epoch"]:
        df[col] = df[col].astype(str).str.strip().replace(
            {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
        )

    # Derive discovery_year
    df["discovery_year"] = pd.to_datetime(df["discovery_date"], errors="coerce").dt.year

    # Cast numeric columns to proper float types
    for col in ["orbital_period_yr", "perihelion_au", "eccentricity", "inclination_deg"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Float64")

    df = df.sort_values("name").reset_index(drop=True)
    print(f"  {len(df):,} unique comets")

    check_dataset(df, "comets", min_rows=500,
                  expected_columns=["name"],
                  critical_columns=["name"])

    # Stats for README
    n = len(df)
    n_with_period = int(df["orbital_period_yr"].notna().sum())
    n_with_perihelion = int(df["perihelion_au"].notna().sum())
    n_with_discoverer = int(df["discoverer"].notna().sum())
    n_with_ecc = int(df["eccentricity"].notna().sum())
    n_with_year = int(df["discovery_year"].notna().sum())

    # Earliest and latest discovery years
    min_year = int(df["discovery_year"].min()) if n_with_year > 0 else "N/A"
    max_year = int(df["discovery_year"].max()) if n_with_year > 0 else "N/A"

    # Top discoverers
    top_discoverers = df["discoverer"].value_counts().head(5)
    top_disc_str = ", ".join(
        f"{d} ({c:,})" for d, c in top_discoverers.items()
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "comets.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_kb = out.stat().st_size / 1024
        print(f"  {size_kb:.0f} KB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc0-1.0
pretty_name: "Comet Catalog"
language:
  - en
description: >-
  Catalog of comets sourced from Wikidata, including orbital parameters,
  discovery dates, discoverers, and named-after information.
  {n:,} comets with orbital mechanics data.
size_categories:
  - 1K<n<10K
task_categories:
  - tabular-classification
tags:
  - space
  - comets
  - orbital-mechanics
  - wikidata
  - open-data
  - tabular-data
  - parquet
configs:
  - config_name: default
    default: true
    data_files:
      - split: train
        path: data/comets.parquet
---

# Comet Catalog

*Part of the [Orbital Mechanics Datasets](https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994) collection on Hugging Face.*

Catalog of **{n:,}** comets sourced from [Wikidata](https://www.wikidata.org/), covering
orbital parameters, discovery history, and naming origins.

## Dataset description

Comets are small icy bodies that develop a coma and tails when approaching the Sun.
They originate from the Kuiper Belt and Oort Cloud and follow highly eccentric orbits
ranging from short-period comets (< 200 years) to long-period and hyperbolic visitors.

This dataset aggregates structured comet data from Wikidata's SPARQL endpoint, capturing
orbital mechanics (period, perihelion distance, eccentricity, inclination), discovery
metadata (date, discoverer), and cultural information (named-after entities). It covers
historically significant comets like Halley's Comet and Hale-Bopp through recently
discovered objects.

The data enables studies of comet population statistics, orbital dynamics, discovery
rate trends over time, and the history of comet observation and naming conventions.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `wikidata_id` | string | Wikidata entity ID (e.g. Q1390) |
| `name` | string | Comet name or designation |
| `discovery_date` | string | Date of discovery (YYYY-MM-DD) |
| `discoverer` | string | Name of discoverer(s) |
| `orbital_period_yr` | float | Orbital period (years) |
| `perihelion_au` | float | Perihelion distance (AU) |
| `eccentricity` | float | Orbital eccentricity |
| `inclination_deg` | float | Orbital inclination (degrees) |
| `named_after` | string | Entity the comet is named after |
| `epoch` | string | Orbital element epoch (YYYY-MM-DD) |
| `discovery_year` | int | Year of discovery (derived) |

## Quick stats

- **{n:,}** comets in catalog
- **{n_with_period:,}** with orbital period data
- **{n_with_perihelion:,}** with perihelion distance
- **{n_with_ecc:,}** with eccentricity
- **{n_with_discoverer:,}** with named discoverer
- Discovery years: {min_year} – {max_year}
- Top discoverers: {top_disc_str}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/comet-catalog", split="train")
df = ds.to_pandas()

# Short-period comets (period < 200 years)
short_period = df[df["orbital_period_yr"] < 200].dropna(subset=["orbital_period_yr"])
print(f"{{len(short_period):,}} short-period comets")

# Most recently discovered comets
recent = df.dropna(subset=["discovery_year"]).nlargest(10, "discovery_year")
print(recent[["name", "discovery_year", "discoverer"]])

# Highly eccentric comets (near-parabolic or hyperbolic)
high_ecc = df[df["eccentricity"] >= 0.99].dropna(subset=["eccentricity"])
print(high_ecc[["name", "eccentricity", "orbital_period_yr"]])

# Comets by perihelion distance
inner = df[df["perihelion_au"] < 0.3].dropna(subset=["perihelion_au"])
print(f"{{len(inner):,}} sungrazing comets (perihelion < 0.3 AU)")
```

## Data source

[Wikidata](https://www.wikidata.org/) SPARQL endpoint. Comets identified via
P31 (instance of) / P279* (subclass of) traversal from Q3559 (comet).
Data is community-curated by [WikiProject Astronomy](https://www.wikidata.org/wiki/Wikidata:WikiProject_Astronomy).

## Update schedule

Quarterly (January, April, July, October). Run `python scripts/update-comets.py` manually to refresh.

## Related datasets

- [mpc-comet-elements](https://huggingface.co/datasets/juliensimon/mpc-comet-elements) -- MPC orbital elements for comets
- [jpl-small-body-database](https://huggingface.co/datasets/juliensimon/jpl-small-body-database) -- JPL small body orbital data
- [fireball-bolide-events](https://huggingface.co/datasets/juliensimon/fireball-bolide-events) -- Fireball and bolide events

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/comet-catalog) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{comet_catalog,
  author = {{Simon, Julien}},
  title = {{Comet Catalog}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/comet-catalog}},
  note = {{Sourced from Wikidata (CC0)}}
}}
```

## License

[CC0-1.0](https://creativecommons.org/publicdomain/zero/1.0/) (Wikidata content is public domain)
""")

        print("Uploading to HF...")
        commit_msg = f"Update comet catalog: {n:,} comets"
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
