#!/usr/bin/env python3
"""Fetch astronaut database from Wikidata and upload to HF.

Source: Wikidata SPARQL endpoint — property P106 (occupation) = Q11631 (astronaut).
"""

import time

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

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

SPARQL_QUERY = """
SELECT ?person ?personLabel ?birth ?death ?sexLabel ?nationalityLabel
       (GROUP_CONCAT(DISTINCT ?employerLabel; separator="; ") AS ?employers)
       (COUNT(DISTINCT ?flight) AS ?num_flights)
       ?timeInSpace
WHERE {
  ?person wdt:P106 wd:Q11631.
  ?person wdt:P31 wd:Q5.
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

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "wikidata_id": "Wikidata entity ID (e.g. 'Q1029'); resolves to https://www.wikidata.org/wiki/Q1029 — links to the astronaut's full biography, mission list, and nationality data",
    "name": "Full legal name as recorded in Wikidata (English transliteration for non-Latin scripts)",
    "birth_date": "Date of birth in ISO 8601 format (YYYY-MM-DD); null for living persons who have not disclosed their birth date or for historical records with unresolvable uncertainty",
    "death_date": "Date of death in ISO 8601 format (YYYY-MM-DD); null for living astronauts",
    "sex": "Recorded biological sex; values: 'male', 'female'; null if not recorded in Wikidata",
    "nationality": "Country of citizenship at the time of primary spaceflight career (e.g. 'United States', 'Russia'); uses full English country name; may differ from country of birth",
    "employers": "Space agencies or contractors that employed the astronaut, semicolon-separated (e.g. 'NASA; Boeing'); null if no employer is recorded in Wikidata",
    "num_flights": "Number of distinct spaceflights completed (each separate launch counts as one flight); 0 if the astronaut trained but never flew",
    "time_in_space_min": "Cumulative time spent in space across all missions, in minutes; null for astronauts with no recorded flights",
    "birth_year": "Integer year extracted from birth_date; enables age-group analysis when full date is unavailable; null only if birth date is entirely unknown",
    "time_in_space_hours": "Cumulative time in space in decimal hours, derived from time_in_space_min (divided by 60, rounded to 1 decimal); null for astronauts with no recorded flights",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Complete database of every person who has traveled to space, sourced from Wikidata.

Since Yuri Gagarin's flight aboard Vostok 1 in April 1961, fewer than 700 individuals \
have crossed the Karman line (100 km altitude). This dataset records every one of them, \
from the Mercury Seven and Voskhod cosmonauts through Space Shuttle crews, ISS expeditions, \
and the recent wave of commercial astronauts aboard Crew Dragon and New Shepard.

The dataset includes birth/death dates, sex, nationality, employer history (space agencies \
and contractors), number of spaceflights, and total time spent in space. This enables \
demographic analysis of astronaut corps, diversity-in-STEM research, and historical studies \
of human spaceflight programs.

Sourced from Wikidata's structured knowledge base (property P106=Q11631 for occupation:astronaut), \
which is maintained by the WikiProject Spaceflight community and updated as new flights occur.
"""


def fetch_astronauts() -> pd.DataFrame:
    """Query Wikidata SPARQL for all astronauts (3 retries with backoff)."""
    print("Querying Wikidata for astronauts...")
    for attempt in range(3):
        try:
            resp = requests.get(
                WIKIDATA_URL,
                params={"query": SPARQL_QUERY, "format": "json"},
                headers=HEADERS,
                timeout=120,
            )
            resp.raise_for_status()
            break
        except Exception as exc:
            if attempt < 2:
                wait = 30 * (2 ** attempt)
                print(f"  Wikidata attempt {attempt + 1}/3 failed: {exc}; retrying in {wait}s...")
                time.sleep(wait)
            else:
                print(f"  Wikidata failed after 3 attempts: {exc}")
                raise

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

    # Derive birth_year for stats
    df["birth_year"] = pd.to_datetime(df["birth_date"], errors="coerce").dt.year

    # Compute hours in space
    df["time_in_space_hours"] = (
        df["time_in_space_min"].astype("Float64") / 60
    ).round(1)

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    df = df.sort_values("name").reset_index(drop=True)
    print(f"  {len(df):,} unique astronauts")

    # ── Domain-specific stats for README ─────────────────────────────
    n = len(df)
    n_nationalities = int(df["nationality"].nunique())
    top_nations = df["nationality"].value_counts().head(5)
    top_nations_str = ", ".join(f"{nat} ({cnt:,})" for nat, cnt in top_nations.items())
    n_female = int((df["sex"] == "female").sum())
    n_male = int((df["sex"] == "male").sum())
    n_with_flights = int((df["num_flights"] > 0).sum())
    max_flights = int(df["num_flights"].max())
    max_flights_name = df.loc[df["num_flights"].idxmax(), "name"]

    quick_stats = f"""\
- **{n:,}** astronauts from **{n_nationalities}** countries
- **{n_male:,}** male, **{n_female:,}** female
- **{n_with_flights:,}** with recorded spaceflights
- Most flights: {max_flights_name} ({max_flights})
- Top nationalities: {top_nations_str}"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/astronaut-database", split="train")
df = ds.to_pandas()

# Astronauts by nationality
print(df["nationality"].value_counts().head(10))

# Female astronauts
female = df[df["sex"] == "female"]
print(f"{len(female):,} female astronauts")

# Most time in space
top_time = df.nlargest(10, "time_in_space_hours")[["name", "nationality", "time_in_space_hours"]]
print(top_time)

# NASA astronauts
nasa = df[df["employers"].str.contains("NASA", na=False)]
print(f"{len(nasa):,} NASA-affiliated astronauts")

# Flight count distribution
import matplotlib.pyplot as plt
df["num_flights"].value_counts().sort_index().plot(kind="bar")
plt.xlabel("Number of Flights")
plt.ylabel("Astronauts")
plt.title("Spaceflight Count Distribution")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Astronaut Database",
        description=DESCRIPTION,
        tags=["space", "astronaut", "human-spaceflight", "wikidata",
              "missions", "open-data", "tabular-data", "parquet"],
        source_url="https://www.wikidata.org/",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/space-essentials-69cbafd7ea046a10eff11405",
        banner={
            "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e001386/GSFC_20171208_Archive_e001386~medium.jpg",
            "alt": "Blue Marble — Earth from space",
            "credit": "NASA/GSFC/Suomi NPP",
        },
        license="cc0-1.0",
        related_datasets=[
            "juliensimon/space-launch-log",
            "juliensimon/space-track-satcat",
            "juliensimon/nasa-eva-chronology",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=["time_in_space_min", "time_in_space_hours"],
            integer=["num_flights", "birth_year"],
            strings=["name", "sex", "nationality", "employers"],
        )
        p.publish(
            df,
            filename="astronauts.parquet",
            min_rows=400,
            expected_columns=["name", "nationality"],
            critical_columns=["name", "nationality"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update astronaut database: {n:,} astronauts",
        )
    print("Done.")


if __name__ == "__main__":
    main()
