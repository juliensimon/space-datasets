#!/usr/bin/env python3
"""Fetch launch vehicle database from Wikidata and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset


HF_REPO = "juliensimon/launch-vehicles"

WIKIDATA_URL = "https://query.wikidata.org/sparql"
HEADERS = {"User-Agent": "space-datasets/1.0 (https://github.com/juliensimon/space-datasets)"}

SPARQL_QUERY = """
SELECT ?vehicle ?vehicleLabel ?manufacturerLabel ?countryLabel
       ?height ?diameter ?massKg
       ?payloadLeo ?payloadGto
       ?firstFlight ?lastFlight
       ?numStages ?statusLabel
WHERE {
  ?vehicle wdt:P31/wdt:P279* wd:Q697175.
  OPTIONAL { ?vehicle wdt:P176 ?manufacturer. }
  OPTIONAL { ?vehicle wdt:P495 ?country. }
  OPTIONAL { ?vehicle wdt:P2048 ?height. }
  OPTIONAL { ?vehicle wdt:P2049 ?diameter. }
  OPTIONAL { ?vehicle wdt:P2067 ?massKg. }
  OPTIONAL { ?vehicle wdt:P4519 ?payloadLeo. }
  OPTIONAL { ?vehicle wdt:P4520 ?payloadGto. }
  OPTIONAL { ?vehicle wdt:P606 ?firstFlight. }
  OPTIONAL { ?vehicle wdt:P3999 ?lastFlight. }
  OPTIONAL { ?vehicle wdt:P1132 ?numStages. }
  OPTIONAL { ?vehicle wdt:P5765 ?status. }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,mul". }
}
"""


def fetch_launch_vehicles() -> pd.DataFrame:
    """Query Wikidata SPARQL for all launch vehicles."""
    print("Querying Wikidata for launch vehicles...")
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
        wikidata_id = r.get("vehicle", {}).get("value", "").rsplit("/", 1)[-1]

        def val(key):
            return r.get(key, {}).get("value") or None

        def fval(key):
            v = val(key)
            return float(v) if v is not None else None

        def ival(key):
            v = val(key)
            return int(float(v)) if v is not None else None

        rows.append({
            "wikidata_id": wikidata_id,
            "name": val("vehicleLabel"),
            "manufacturer": val("manufacturerLabel"),
            "country": val("countryLabel"),
            "height_m": fval("height"),
            "diameter_m": fval("diameter"),
            "mass_kg": fval("massKg"),
            "payload_leo_kg": fval("payloadLeo"),
            "payload_gto_kg": fval("payloadGto"),
            "first_flight": (val("firstFlight") or "")[:10] or None,
            "last_flight": (val("lastFlight") or "")[:10] or None,
            "num_stages": ival("numStages"),
            "status": val("statusLabel"),
        })

    df = pd.DataFrame(rows)

    # Deduplicate on wikidata_id — keep row with most non-null fields
    df["_non_null"] = df.notna().sum(axis=1)
    df = df.sort_values("_non_null", ascending=False).drop_duplicates(
        subset=["wikidata_id"], keep="first"
    ).drop(columns=["_non_null"])

    # Drop entries with no real name (bare Q-IDs = junk Wikidata entities)
    df = df[~df["name"].str.match(r"^Q\d+$", na=False)]

    return df


def main():
    df = fetch_launch_vehicles()

    # Clean string columns
    for col in ["name", "manufacturer", "country", "first_flight", "last_flight", "status"]:
        df[col] = df[col].astype(str).str.strip().replace(
            {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
        )

    # Ensure numeric types
    for col in ["height_m", "diameter_m", "mass_kg", "payload_leo_kg", "payload_gto_kg"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Float64")

    for col in ["num_stages"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    df = df.sort_values("name").reset_index(drop=True)
    print(f"  {len(df):,} unique launch vehicles")

    check_dataset(df, "launch-vehicles", min_rows=100,
                  expected_columns=["name"],
                  critical_columns=["name"])

    # Stats for README
    n = len(df)
    n_countries = int(df["country"].nunique())
    top_countries = df["country"].value_counts().head(5)
    top_countries_str = ", ".join(f"{c} ({cnt:,})" for c, cnt in top_countries.items())

    # Tallest vehicle
    tallest_idx = df["height_m"].dropna().idxmax() if df["height_m"].notna().any() else None
    tallest_str = (
        f"{df.loc[tallest_idx, 'name']} ({df.loc[tallest_idx, 'height_m']:.1f} m)"
        if tallest_idx is not None else "N/A"
    )

    # Heaviest LEO payload
    heaviest_leo_idx = df["payload_leo_kg"].dropna().idxmax() if df["payload_leo_kg"].notna().any() else None
    heaviest_leo_str = (
        f"{df.loc[heaviest_leo_idx, 'name']} ({df.loc[heaviest_leo_idx, 'payload_leo_kg']:,.0f} kg)"
        if heaviest_leo_idx is not None else "N/A"
    )

    n_active = int((df["status"].str.lower() == "active").sum())
    n_retired = int((df["status"].str.lower() == "retired").sum())

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "launch-vehicles.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_kb = out.stat().st_size / 1024
        print(f"  {size_kb:.0f} KB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc0-1.0
pretty_name: "Launch Vehicles Database"
language:
  - en
description: >-
  Orbital and suborbital launch vehicles from around the world, sourced from Wikidata.
  {n:,} vehicles from {n_countries} countries with dimensions, payload capacity,
  flight history, and operational status.
size_categories:
  - n<1K
task_categories:
  - tabular-classification
tags:
  - space
  - rockets
  - launch-vehicles
  - orbital-mechanics
  - wikidata
  - open-data
  - tabular-data
  - parquet
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/launch-vehicles.parquet
---

# Launch Vehicles Database

*Part of the [Orbital Mechanics Datasets](https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994) collection on Hugging Face.*

Complete database of orbital and suborbital launch vehicles — **{n:,}** rockets and boosters
from **{n_countries}** countries, sourced from [Wikidata](https://www.wikidata.org/).

## Dataset description

From the German V-2 through the Saturn V to the Falcon 9 and Starship, launch vehicles have
defined humanity's access to space. This dataset covers every orbital and suborbital launch
vehicle recorded in Wikidata, including historical rockets, active workhorses, and vehicles
under development.

Each entry includes physical dimensions (height, diameter, liftoff mass), payload capacity
to low Earth orbit (LEO) and geostationary transfer orbit (GTO), first and last flight dates,
number of stages, operational status, manufacturer, and country of origin.

This enables analysis of global launch capability, rocket engineering evolution over decades,
national space programme comparisons, and payload capacity trends across generations of vehicles.

Sourced from Wikidata's structured knowledge base (class Q697175: space launch vehicle),
maintained by the WikiProject Spaceflight community.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `wikidata_id` | string | Wikidata entity ID (e.g. Q697175) |
| `name` | string | Vehicle name |
| `manufacturer` | string | Manufacturer organisation |
| `country` | string | Country of origin |
| `height_m` | float | Total height (metres) |
| `diameter_m` | float | Core diameter (metres) |
| `mass_kg` | float | Liftoff mass (kg) |
| `payload_leo_kg` | float | Payload capacity to LEO (kg) |
| `payload_gto_kg` | float | Payload capacity to GTO (kg) |
| `first_flight` | string | Date of first flight (YYYY-MM-DD) |
| `last_flight` | string | Date of last flight if retired (YYYY-MM-DD) |
| `num_stages` | int | Number of stages |
| `status` | string | Operational status (active/retired/in development) |

## Quick stats

- **{n:,}** launch vehicles from **{n_countries}** countries
- **{n_active:,}** active, **{n_retired:,}** retired
- Tallest vehicle: {tallest_str}
- Heaviest LEO payload: {heaviest_leo_str}
- Top countries: {top_countries_str}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/launch-vehicles", split="train")
df = ds.to_pandas()

# Active vehicles by country
active = df[df["status"].str.lower() == "active"]
print(active["country"].value_counts().head(10))

# Heaviest LEO payload capacity
top_leo = df.nlargest(10, "payload_leo_kg")[["name", "country", "payload_leo_kg"]]
print(top_leo)

# Vehicles by first flight decade
df["decade"] = (df["first_flight"].str[:4].astype(float) // 10 * 10).astype("Int64")
print(df["decade"].value_counts().sort_index())

# Height vs payload correlation
import matplotlib.pyplot as plt
subset = df.dropna(subset=["height_m", "payload_leo_kg"])
plt.scatter(subset["height_m"], subset["payload_leo_kg"])
plt.xlabel("Height (m)")
plt.ylabel("LEO Payload (kg)")
plt.title("Rocket Height vs Payload Capacity")
plt.show()
```

## Data source

[Wikidata](https://www.wikidata.org/) SPARQL endpoint. Launch vehicles identified as
instances of Q697175 (space launch vehicle) and its subclasses. Data is community-curated
by [WikiProject Spaceflight](https://www.wikidata.org/wiki/Wikidata:WikiProject_Spaceflight).

## Update schedule

Quarterly (January, April, July, October). Re-run manually to pick up newly added vehicles.

## Related datasets

- [space-missions](https://huggingface.co/datasets/juliensimon/space-missions) — Crewed and robotic space missions
- [launch-log](https://huggingface.co/datasets/juliensimon/launch-log) — McDowell orbital launch log
- [spacecraft-database](https://huggingface.co/datasets/juliensimon/spacecraft-database) — Spacecraft catalogue

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/launch-vehicles) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{launch_vehicles,
  author = {{Simon, Julien}},
  title = {{Launch Vehicles Database}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/launch-vehicles}},
  note = {{Sourced from Wikidata (CC0)}}
}}
```

## License

[CC0-1.0](https://creativecommons.org/publicdomain/zero/1.0/) (Wikidata content is public domain)
""")

        print("Uploading to HF...")
        commit_msg = f"Update launch vehicles database: {n:,} vehicles"
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
