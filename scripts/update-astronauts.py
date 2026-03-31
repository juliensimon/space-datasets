#!/usr/bin/env python3
"""Fetch astronaut database from Wikidata and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset


HF_REPO = "juliensimon/astronaut-database"

WIKIDATA_URL = "https://query.wikidata.org/sparql"
HEADERS = {"User-Agent": "space-datasets/1.0 (https://github.com/juliensimon/space-datasets)"}

# Wikidata entries missing P27 (nationality) — manually researched
NATIONALITY_OVERRIDES = {
    "Q136358206": "United States",      # Adam Fuhrmann, Blue Origin NS-28
    "Q9177589": "Soviet Union",         # Boris Polakow
    "Q107401704": "United States",      # Dianne Kasnic Prinz, Blue Origin NS-19
    "Q18235674": "Soviet Union",        # Galina Amelkina
    "Q111244219": "United States",      # George Nield, FAA / Blue Origin
    "Q17593755": "Soviet Union",        # Gurgens Ivanjans
    "Q94806666": "Germany",             # Hans Schneider
    "Q130301130": "United States",      # Jamila Gilbert, Blue Origin
    "Q111440855": "United States",      # Jim Kitchen, Blue Origin NS-20
    "Q55451797": "Czechoslovakia",      # Jiří Alter, Interkosmos candidate
    "Q109860538": "United States",      # Lane Bess, Blue Origin NS-18
    "Q112535527": "United States",      # Manfred von Ehrenfried, NASA
    "Q103847789": "Russia",             # Mark Serov, Roscosmos
    "Q123557435": "North Macedonia",    # Martina Dimoska, Blue Origin
    "Q107484917": "United States",      # Michael Masucci, Virgin Galactic pilot
    "Q66733632": "United States",       # Michael McKay, Virgin Galactic
    "Q124669921": "India",              # Prasanth Nair, Blue Origin NS-25
    "Q16522515": "United States",       # Ray Glynn Holt, NASA/USAF
    "Q9310786": "United States",        # Robert Everett Stevenson, NASA
    "Q118364894": "Egypt",              # Sara Sabry, Blue Origin NS-22
    "Q12051501": "Soviet Union",        # Sergej Kostěnko, Interkosmos
    "Q24005946": "Russia",              # Valeriy Makrushin, Roscosmos
    "Q112230872": "Brazil",             # Victor Correa Hespanha, Blue Origin NS-23
    "Q136675056": "China",              # Wu Fei, taikonaut
    "Q16617489": "Poland",              # Władimir Kozielski, Interkosmos
}

# One row per astronaut: name, birth, death, sex, nationality, employer,
# number of spaceflights, time in space (minutes)
SPARQL_QUERY = """
SELECT ?person ?personLabel ?birth ?death ?sexLabel ?nationalityLabel
       (GROUP_CONCAT(DISTINCT ?employerLabel; separator="; ") AS ?employers)
       (COUNT(DISTINCT ?flight) AS ?num_flights)
       ?timeInSpace
WHERE {
  ?person wdt:P106 wd:Q11631.
  ?person wdt:P31 wd:Q5.          # instance of: human (excludes fictional chars, animals)
  OPTIONAL { ?person wdt:P569 ?birth. }
  OPTIONAL { ?person wdt:P570 ?death. }
  OPTIONAL { ?person wdt:P21 ?sex. }
  OPTIONAL { ?person wdt:P27 ?nationality. }
  OPTIONAL { ?person wdt:P108 ?employer.
             ?employer rdfs:label ?employerLabel. FILTER(LANG(?employerLabel) = "en") }
  OPTIONAL { ?person wdt:P450 ?flight. }
  OPTIONAL { ?person wdt:P2873 ?timeInSpace. }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,mul". }
}
GROUP BY ?person ?personLabel ?birth ?death ?sexLabel ?nationalityLabel ?timeInSpace
"""


def fetch_astronauts() -> pd.DataFrame:
    """Query Wikidata SPARQL for all astronauts."""
    print("Querying Wikidata for astronauts...")
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
        wikidata_id = r.get("person", {}).get("value", "").rsplit("/", 1)[-1]
        rows.append({
            "wikidata_id": wikidata_id,
            "name": r.get("personLabel", {}).get("value"),
            "birth_date": r.get("birth", {}).get("value", "")[:10] or None,
            "death_date": r.get("death", {}).get("value", "")[:10] or None,
            "sex": r.get("sexLabel", {}).get("value"),
            "nationality": r.get("nationalityLabel", {}).get("value"),
            "employers": r.get("employers", {}).get("value") or None,
            "num_flights": int(r.get("num_flights", {}).get("value", 0)),
            "time_in_space_min": (
                int(float(r.get("timeInSpace", {}).get("value", 0)))
                if r.get("timeInSpace", {}).get("value") else None
            ),
        })

    df = pd.DataFrame(rows)

    # Deduplicate: multiple nationalities can create duplicate rows
    # Keep the row with the most info (longest employers string)
    df["_sort"] = df["employers"].fillna("").str.len()
    df = df.sort_values("_sort", ascending=False).drop_duplicates(
        subset=["wikidata_id"], keep="first"
    ).drop(columns=["_sort"])

    # Apply nationality overrides for entries missing P27
    for qid, nat in NATIONALITY_OVERRIDES.items():
        mask = (df["wikidata_id"] == qid) & df["nationality"].isna()
        df.loc[mask, "nationality"] = nat

    # Drop entries with no real name (bare Q-IDs = junk Wikidata entities)
    df = df[~df["name"].str.match(r"^Q\d+$", na=False)]

    return df


def main():
    df = fetch_astronauts()

    # Clean string columns
    for col in ["name", "sex", "nationality", "employers"]:
        df[col] = df[col].astype(str).str.strip().replace(
            {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
        )

    # Derive birth_year for stats
    df["birth_year"] = pd.to_datetime(df["birth_date"], errors="coerce").dt.year

    # Compute hours in space
    df["time_in_space_hours"] = (
        df["time_in_space_min"].astype("Float64") / 60
    ).round(1)

    df = df.sort_values("name").reset_index(drop=True)
    print(f"  {len(df):,} unique astronauts")

    check_dataset(df, "astronauts", min_rows=400,
                  expected_columns=["name", "nationality"],
                  critical_columns=["name", "nationality"])

    # Stats for README
    n = len(df)
    n_nationalities = int(df["nationality"].nunique())
    top_nations = df["nationality"].value_counts().head(5)
    top_nations_str = ", ".join(f"{nat} ({cnt:,})" for nat, cnt in top_nations.items())
    n_female = int((df["sex"] == "female").sum())
    n_male = int((df["sex"] == "male").sum())
    n_with_flights = int((df["num_flights"] > 0).sum())
    max_flights = int(df["num_flights"].max())
    max_flights_name = df.loc[df["num_flights"].idxmax(), "name"]

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "astronauts.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_kb = out.stat().st_size / 1024
        print(f"  {size_kb:.0f} KB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc0-1.0
pretty_name: "Astronaut Database"
language:
  - en
description: >-
  Every person who has traveled to space, sourced from Wikidata.
  {n:,} astronauts from {n_nationalities} countries with flight counts
  and time in space.
size_categories:
  - n<1K
task_categories:
  - tabular-classification
tags:
  - space
  - astronaut
  - human-spaceflight
  - wikidata
  - missions
  - open-data
  - tabular-data
  - parquet
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/astronauts.parquet
---

# Astronaut Database

*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

Complete database of every person who has traveled to space — **{n:,}** astronauts
from **{n_nationalities}** countries, sourced from [Wikidata](https://www.wikidata.org/).

## Dataset description

Since Yuri Gagarin's flight aboard Vostok 1 in April 1961, fewer than 700 individuals
have crossed the Karman line (100 km altitude). This dataset records every one of them,
from the Mercury Seven and Voskhod cosmonauts through Space Shuttle crews, ISS expeditions,
and the recent wave of commercial astronauts aboard Crew Dragon and New Shepard.

The dataset includes birth/death dates, sex, nationality, employer history (space agencies
and contractors), number of spaceflights, and total time spent in space. This enables
demographic analysis of astronaut corps, diversity-in-STEM research, and historical studies
of human spaceflight programs.

Sourced from Wikidata's structured knowledge base (property P106=Q11631 for occupation:astronaut),
which is maintained by the WikiProject Spaceflight community and updated as new flights occur.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `wikidata_id` | string | Wikidata entity ID (e.g. Q1029) |
| `name` | string | Full name |
| `birth_date` | string | Date of birth (YYYY-MM-DD) |
| `death_date` | string | Date of death if deceased |
| `sex` | string | Sex (male/female) |
| `nationality` | string | Nationality |
| `employers` | string | Employers, semicolon-separated (space agencies, contractors) |
| `num_flights` | int | Number of spaceflights |
| `time_in_space_min` | int | Total time in space (minutes) |
| `birth_year` | int | Year of birth (derived) |
| `time_in_space_hours` | float | Total time in space (hours, derived) |

## Quick stats

- **{n:,}** astronauts from **{n_nationalities}** countries
- **{n_male:,}** male, **{n_female:,}** female
- **{n_with_flights:,}** with recorded spaceflights
- Most flights: {max_flights_name} ({max_flights})
- Top nationalities: {top_nations_str}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/astronaut-database", split="train")
df = ds.to_pandas()

# Astronauts by nationality
print(df["nationality"].value_counts().head(10))

# Female astronauts
female = df[df["sex"] == "female"]
print(f"{{len(female):,}} female astronauts")

# Most time in space
top_time = df.nlargest(10, "time_in_space_hours")[["name", "nationality", "time_in_space_hours"]]
print(top_time)

# NASA astronauts
nasa = df[df["employers"].str.contains("NASA", na=False)]
print(f"{{len(nasa):,}} NASA-affiliated astronauts")
```

## Data source

[Wikidata](https://www.wikidata.org/) SPARQL endpoint. Astronauts identified via
property P106 (occupation) = Q11631 (astronaut). Data is community-curated by
[WikiProject Spaceflight](https://www.wikidata.org/wiki/Wikidata:WikiProject_Spaceflight).

## Update schedule

Static dataset. Re-run manually to pick up new astronauts.

## Related datasets

- [launch-log](https://huggingface.co/datasets/juliensimon/launch-log) -- McDowell launch log
- [satcat](https://huggingface.co/datasets/juliensimon/satcat) -- Satellite catalog
- [nasa-eva](https://huggingface.co/datasets/juliensimon/nasa-eva) -- NASA EVA history

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/astronaut-database) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{astronaut_database,
  author = {{Simon, Julien}},
  title = {{Astronaut Database}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/astronaut-database}},
  note = {{Sourced from Wikidata (CC0)}}
}}
```

## License

[CC0-1.0](https://creativecommons.org/publicdomain/zero/1.0/) (Wikidata content is public domain)
""")

        print("Uploading to HF...")
        commit_msg = f"Update astronaut database: {n:,} astronauts"
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
