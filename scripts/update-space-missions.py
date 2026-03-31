#!/usr/bin/env python3
"""Fetch space missions database from Wikidata and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset


HF_REPO = "juliensimon/space-missions"

WIKIDATA_URL = "https://query.wikidata.org/sparql"
HEADERS = {"User-Agent": "space-datasets/1.0 (https://github.com/juliensimon/space-datasets)"}

SPARQL_QUERY = """
SELECT ?mission ?missionLabel ?launch_date ?end_date
       ?operatorLabel ?destinationLabel ?launch_siteLabel
       ?vehicleLabel ?crewCount ?duration ?outcomeLabel
WHERE {
  { ?mission wdt:P31/wdt:P279* wd:Q2133344 }
  UNION { ?mission wdt:P31 wd:Q1248784 }
  UNION { ?mission wdt:P31 wd:Q12795915 }
  OPTIONAL { ?mission wdt:P619 ?launch_date. }
  OPTIONAL { ?mission wdt:P582 ?end_date. }
  OPTIONAL { ?mission wdt:P137 ?operator. }
  OPTIONAL { ?mission wdt:P1444 ?destination. }
  OPTIONAL { ?mission wdt:P1427 ?launch_site. }
  OPTIONAL { ?mission wdt:P4394 ?vehicle. }
  OPTIONAL { ?mission wdt:P1132 ?crewCount. }
  OPTIONAL { ?mission wdt:P2047 ?duration. }
  OPTIONAL { ?mission wdt:P793 ?outcome. }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,mul". }
}
"""


def fetch_missions() -> pd.DataFrame:
    """Query Wikidata SPARQL for all space missions."""
    print("Querying Wikidata for space missions...")
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
        wikidata_id = r.get("mission", {}).get("value", "").rsplit("/", 1)[-1]
        # duration from Wikidata is in minutes
        duration_raw = r.get("duration", {}).get("value")
        duration_days = None
        if duration_raw:
            try:
                duration_days = round(float(duration_raw) / 1440, 4)  # minutes -> days
            except (ValueError, TypeError):
                duration_days = None
        rows.append({
            "wikidata_id": wikidata_id,
            "name": r.get("missionLabel", {}).get("value"),
            "launch_date": r.get("launch_date", {}).get("value", "")[:10] or None,
            "end_date": r.get("end_date", {}).get("value", "")[:10] or None,
            "operator": r.get("operatorLabel", {}).get("value"),
            "destination": r.get("destinationLabel", {}).get("value"),
            "launch_site": r.get("launch_siteLabel", {}).get("value"),
            "vehicle": r.get("vehicleLabel", {}).get("value"),
            "crew_count": (
                int(r.get("crewCount", {}).get("value"))
                if r.get("crewCount", {}).get("value") else None
            ),
            "duration_days": duration_days,
            "outcome": r.get("outcomeLabel", {}).get("value"),
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
    df = fetch_missions()

    # Clean string columns
    for col in ["name", "operator", "destination", "launch_site", "vehicle", "outcome"]:
        df[col] = df[col].astype(str).str.strip().replace(
            {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
        )

    # Derive launch_year for stats
    df["launch_year"] = pd.to_datetime(df["launch_date"], errors="coerce").dt.year

    df = df.sort_values("launch_date", na_position="last").reset_index(drop=True)
    print(f"  {len(df):,} unique missions")

    check_dataset(df, "space-missions", min_rows=5000,
                  expected_columns=["name", "launch_date"],
                  critical_columns=["name"])

    # Stats for README
    n = len(df)
    n_with_date = int(df["launch_date"].notna().sum())
    n_crewed = int((df["crew_count"].fillna(0) > 0).sum())
    n_destinations = int(df["destination"].nunique())
    top_operators = df["operator"].value_counts().head(5)
    top_operators_str = ", ".join(f"{op} ({cnt:,})" for op, cnt in top_operators.items())
    earliest = df["launch_date"].dropna().min()
    latest = df["launch_date"].dropna().max()

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "space-missions.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_kb = out.stat().st_size / 1024
        print(f"  {size_kb:.0f} KB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc0-1.0
pretty_name: "Space Missions Database"
language:
  - en
description: >-
  Comprehensive database of space missions sourced from Wikidata.
  {n:,} missions covering crewed and uncrewed spaceflight from the dawn
  of the Space Age to the present.
size_categories:
  - 10K<n<100K
task_categories:
  - tabular-classification
tags:
  - space
  - missions
  - spaceflight
  - wikidata
  - open-data
  - tabular-data
  - parquet
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/space-missions.parquet
---

# Space Missions Database

*Part of the [Orbital Mechanics Datasets](https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994) collection on Hugging Face.*

Comprehensive database of **{n:,}** space missions — both crewed and uncrewed — sourced from [Wikidata](https://www.wikidata.org/).

## Dataset description

From Sputnik-1 in 1957 to today's commercial launches and deep space probes, this dataset covers the full breadth of human spaceflight and robotic exploration. Each record includes launch and end dates, operating agency, destination, launch vehicle, crew size, mission duration, and outcome where available.

The dataset draws on Wikidata's structured knowledge base using three entity types: space missions (Q2133344), crewed spaceflights (Q1248784), and uncrewed spaceflights (Q12795915). It is maintained by the WikiProject Spaceflight community and updated as new missions are flown and documented.

Records span from **{earliest}** to **{latest}**, with **{n_with_date:,}** missions having a known launch date and **{n_crewed:,}** confirmed crewed missions.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `wikidata_id` | string | Wikidata entity ID (e.g. Q183294) |
| `name` | string | Mission name |
| `launch_date` | string | Launch date (YYYY-MM-DD) |
| `end_date` | string | Mission end date (YYYY-MM-DD) |
| `operator` | string | Operating agency or organization |
| `destination` | string | Mission destination (e.g. Moon, Mars, ISS) |
| `launch_site` | string | Launch site name |
| `vehicle` | string | Launch vehicle |
| `crew_count` | int | Number of crew members (null for uncrewed) |
| `duration_days` | float | Mission duration in days (derived from Wikidata minutes) |
| `outcome` | string | Mission outcome (e.g. successful, partial failure) |
| `launch_year` | int | Launch year (derived from launch_date) |

## Quick stats

- **{n:,}** total missions in the database
- **{n_with_date:,}** missions with a known launch date
- **{n_crewed:,}** confirmed crewed missions
- **{n_destinations:,}** distinct destinations
- Date range: {earliest} to {latest}
- Top operators: {top_operators_str}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/space-missions", split="train")
df = ds.to_pandas()

# Missions by operator
print(df["operator"].value_counts().head(10))

# Crewed missions only
crewed = df[df["crew_count"].notna() & (df["crew_count"] > 0)]
print(f"{{len(crewed):,}} crewed missions")

# Missions by destination
print(df["destination"].value_counts().head(10))

# Missions by year
print(df["launch_year"].value_counts().sort_index())

# Longest missions
top_duration = df.nlargest(10, "duration_days")[["name", "operator", "duration_days", "destination"]]
print(top_duration)
```

## Data source

[Wikidata](https://www.wikidata.org/) SPARQL endpoint. Missions identified via:
- Q2133344 (space mission, including subclasses)
- Q1248784 (crewed spaceflight)
- Q12795915 (uncrewed spaceflight)

Data is community-curated by [WikiProject Spaceflight](https://www.wikidata.org/wiki/Wikidata:WikiProject_Spaceflight).

## Update schedule

Quarterly (January, April, July, October).

## Related datasets

- [astronaut-database](https://huggingface.co/datasets/juliensimon/astronaut-database) -- Every person who has traveled to space
- [launch-log](https://huggingface.co/datasets/juliensimon/launch-log) -- McDowell orbital launch log
- [spacecraft-database](https://huggingface.co/datasets/juliensimon/spacecraft-database) -- Spacecraft catalog
- [deep-space-probes](https://huggingface.co/datasets/juliensimon/deep-space-probes) -- Deep space probe trajectories

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/space-missions) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{space_missions,
  author = {{Simon, Julien}},
  title = {{Space Missions Database}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/space-missions}},
  note = {{Sourced from Wikidata (CC0)}}
}}
```

## License

[CC0-1.0](https://creativecommons.org/publicdomain/zero/1.0/) (Wikidata content is public domain)
""")

        print("Uploading to HF...")
        commit_msg = f"Update space missions database: {n:,} missions"
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
