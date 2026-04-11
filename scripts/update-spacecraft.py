#!/usr/bin/env python3
"""Fetch spacecraft database from Wikidata and upload to HF.

Source: Wikidata SPARQL — all instances of Q40218 (spacecraft) and subclasses.
"""

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

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

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "wikidata_id": "Wikidata entity ID (e.g. 'Q48371'); stable URI used for cross-referencing enrichment sources",
    "name": "Spacecraft name as recorded in Wikidata (e.g. 'Hubble Space Telescope', 'Sputnik 1', 'Starlink-1234')",
    "launch_date": "ISO 8601 UTC launch date in YYYY-MM-DD format; null if the spacecraft has not yet launched or date is unknown",
    "decommissioned_date": "ISO 8601 UTC date the spacecraft was decommissioned or declared lost (YYYY-MM-DD); null if still operational or decommission date not recorded",
    "operator": "Agency or organization operating the spacecraft (e.g. 'NASA', 'ESA', 'SpaceX', 'Roscosmos'); null if not recorded in Wikidata",
    "manufacturer": "Organization that built the spacecraft bus (e.g. 'Boeing', 'Lockheed Martin', 'Airbus'); null if not recorded",
    "orbit_type": "Orbital regime (e.g. 'LEO', 'GEO', 'heliocentric', 'lunar orbit', 'deep space'); null if orbital data not available in Wikidata",
    "mass_kg": "Total spacecraft mass in kilograms at launch; null for ~90% of entries where Wikidata has no mass recorded",
    "mission": "Associated mission name linked in Wikidata (e.g. 'Apollo program', 'Mars Science Laboratory'); null if no mission link recorded",
    "launch_year": "Year of launch derived from launch_date; null if launch_date is null; useful for time-series aggregation",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Comprehensive database of spacecraft sourced from Wikidata — satellites, probes, \
space stations, and more — spanning the entire history of the Space Age.

From the earliest Sputnik satellites to modern mega-constellations and deep space \
probes, this dataset catalogs spacecraft across seven decades of spaceflight. Each \
record includes launch and decommission dates, operating agency, manufacturer, \
orbital regime, mass, and associated mission where available.

The dataset draws on Wikidata's structured knowledge base using the spacecraft class \
(Q40218) and all its subclasses. It is maintained by the WikiProject Spaceflight \
community and updated as new spacecraft are launched and documented.
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

    # Cast mass_kg to Float64 for nullable float support
    df["mass_kg"] = df["mass_kg"].astype("Float64")

    # Derive launch_year for stats
    df["launch_year"] = pd.to_datetime(df["launch_date"], errors="coerce").dt.year

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    df = df.sort_values("launch_date", na_position="last").reset_index(drop=True)
    print(f"  {len(df):,} unique spacecraft")

    # ── Stats for README ────────────────────────────────────────────
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

    quick_stats = f"""\
- **{n:,}** total spacecraft in the database
- **{n_with_date:,}** spacecraft with a known launch date
- **{n_with_mass:,}** spacecraft with a recorded mass
- **{n_operators:,}** distinct operators
- **{n_orbits:,}** distinct orbital regimes
- Date range: {earliest} to {latest}
- Top operators: {top_operators_str}
- Top orbital regimes: {top_orbits_str}"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/spacecraft-database", split="train")
df = ds.to_pandas()

# Spacecraft by operator
print(df["operator"].value_counts().head(10))

# Spacecraft by orbital regime
print(df["orbit_type"].value_counts().head(10))

# Launches per year
import matplotlib.pyplot as plt
df["launch_year"].dropna().astype(int).value_counts().sort_index().plot(kind="bar", figsize=(14, 4))
plt.xlabel("Year")
plt.ylabel("Spacecraft Launched")
plt.title("Spacecraft Launches Per Year")
plt.tight_layout()
plt.show()

# Heaviest spacecraft
heaviest = df.nlargest(10, "mass_kg")[["name", "operator", "mass_kg", "orbit_type"]]
print(heaviest)
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Spacecraft Database",
        description=DESCRIPTION,
        tags=["space", "spacecraft", "satellites", "wikidata",
              "open-data", "tabular-data", "parquet"],
        source_url="https://www.wikidata.org/",
        license="cc0-1.0",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA14111/PIA14111~small.jpg",
            "alt": "Voyager spacecraft artist concept",
            "credit": "NASA/JPL-Caltech",
        },
        related_datasets=[
            "juliensimon/space-missions",
            "juliensimon/space-track-satcat",
            "juliensimon/launch-vehicles",
        ],
    ) as p:
        df = p.clean(
            df,
            strings=["name", "operator", "manufacturer", "orbit_type", "mission"],
        )
        p.publish(
            df,
            filename="spacecraft.parquet",
            min_rows=2000,
            expected_columns=["name", "launch_date"],
            critical_columns=["name"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update spacecraft database: {n:,} spacecraft",
        )
    print("Done.")


if __name__ == "__main__":
    main()
