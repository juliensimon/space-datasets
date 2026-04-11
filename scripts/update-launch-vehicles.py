#!/usr/bin/env python3
"""Fetch launch vehicle database from Wikidata and upload to HF."""

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

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

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "wikidata_id": "Wikidata entity ID (e.g. 'Q14522') linking to https://www.wikidata.org/wiki/Q14522; use for enrichment joins with other Wikidata-sourced datasets",
    "name": "Primary name of the launch vehicle (e.g. 'Saturn V', 'Falcon 9'); canonical English form as recorded in Wikidata",
    "manufacturer": "Organization that designed and built the vehicle (e.g. 'Boeing', 'SpaceX', 'Roscosmos'); null if manufacturer information is absent from Wikidata",
    "country": "Country of origin using full English name (e.g. 'United States of America', 'Russia', 'China'); reflects the operating nation at time of primary use",
    "height_m": "Total vehicle height from base to payload fairing tip, in metres; null when not recorded in Wikidata; tallest vehicles exceed 100 m (Saturn V: 110.6 m)",
    "diameter_m": "Maximum body diameter in metres; null when not recorded; typically 2-10 m for orbital-class vehicles",
    "mass_kg": "Gross liftoff mass (fully fueled with payload) in kilograms; null when not recorded; ranges from ~10,000 kg (small launchers) to ~3,000,000 kg (Saturn V)",
    "payload_leo_kg": "Maximum payload mass deliverable to low Earth orbit (approx 200-2000 km altitude) in kilograms; null for vehicles whose LEO capacity is unrecorded or not applicable",
    "payload_gto_kg": "Maximum payload mass deliverable to geostationary transfer orbit in kilograms; null for vehicles without GTO capability or where data is unrecorded",
    "first_flight": "Date of maiden flight in ISO 8601 format (YYYY-MM-DD); null for vehicles that never flew or where the date is unrecorded in Wikidata",
    "last_flight": "Date of final flight in ISO 8601 format; null for active vehicles or where last flight date is unrecorded",
    "num_stages": "Number of propulsive stages in the vehicle stack; typically 2-4 for orbital launchers; null when not recorded",
    "status": "Current operational status as recorded in Wikidata (e.g. 'retired', 'active service'); null if Wikidata has no status property set",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Orbital and suborbital launch vehicles from around the world, sourced from Wikidata. \
Covers every space launch vehicle recorded in Wikidata's structured knowledge base, \
including historical rockets, active workhorses, and vehicles under development.

From the German V-2 through the Saturn V to the Falcon 9 and Starship, launch vehicles \
have defined humanity's access to space. This dataset draws from Wikidata's community-curated \
records (class Q697175: space launch vehicle), maintained by the WikiProject Spaceflight \
community. It includes physical dimensions, payload capacities, flight history dates, and \
operational status.

Wikidata coverage varies -- some vehicles lack physical specs or payload data. Columns \
with less than 5% data coverage are automatically dropped during pipeline processing.
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

    # Deduplicate on wikidata_id -- keep row with most non-null fields
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
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
            )

    df = df.sort_values("name").reset_index(drop=True)
    print(f"  {len(df):,} unique launch vehicles")

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # ── Stats for README ──────────────────────────────────────────────────
    n = len(df)
    n_countries = int(df["country"].nunique()) if "country" in df.columns else 0
    if "country" in df.columns:
        top_countries = df["country"].value_counts().head(5)
        top_countries_str = ", ".join(f"{c} ({cnt:,})" for c, cnt in top_countries.items())
    else:
        top_countries_str = "N/A"

    tallest_str = "N/A"
    if "height_m" in df.columns and df["height_m"].notna().any():
        tallest_idx = df["height_m"].dropna().idxmax()
        tallest_str = f"{df.loc[tallest_idx, 'name']} ({df.loc[tallest_idx, 'height_m']:.1f} m)"

    heaviest_leo_str = "N/A"
    if "payload_leo_kg" in df.columns and df["payload_leo_kg"].notna().any():
        heaviest_leo_idx = df["payload_leo_kg"].dropna().idxmax()
        heaviest_leo_str = f"{df.loc[heaviest_leo_idx, 'name']} ({df.loc[heaviest_leo_idx, 'payload_leo_kg']:,.0f} kg)"

    n_active = int((df["status"].str.lower() == "active").sum()) if "status" in df.columns else 0
    n_retired = int((df["status"].str.lower() == "retired").sum()) if "status" in df.columns else 0

    quick_stats = f"""\
- **{n:,}** launch vehicles from **{n_countries}** countries
- **{n_active:,}** active, **{n_retired:,}** retired
- Tallest vehicle: {tallest_str}
- Heaviest LEO payload: {heaviest_leo_str}
- Top countries: {top_countries_str}"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/launch-vehicles", split="train")
df = ds.to_pandas()

# List all vehicles by country
print(df[["name", "country", "manufacturer"]].head(20))

# Vehicles with known height
if "height_m" in df.columns:
    tall = df.dropna(subset=["height_m"]).nlargest(10, "height_m")
    print(tall[["name", "country", "height_m"]])

# Payload capacity distribution
import matplotlib.pyplot as plt
leo = df.dropna(subset=["payload_leo_kg"])
plt.hist(leo["payload_leo_kg"], bins=30, edgecolor="black", alpha=0.7)
plt.xlabel("Payload to LEO (kg)")
plt.ylabel("Number of Vehicles")
plt.title("Launch Vehicle LEO Payload Distribution")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Launch Vehicles Database",
        description=DESCRIPTION,
        license="cc0-1.0",
        tags=["space", "rockets", "launch-vehicles", "orbital-mechanics",
              "wikidata", "open-data", "tabular-data", "parquet"],
        source_url="https://www.wikidata.org/wiki/Q697175",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994",
        banner={
            "url": "https://images-assets.nasa.gov/image/iss071e439624/iss071e439624~medium.jpg",
            "alt": "An orbital sunrise illuminates the Earth's atmosphere, seen from the ISS",
            "credit": "NASA",
        },
        related_datasets=[
            "juliensimon/space-missions",
            "juliensimon/space-launch-log",
            "juliensimon/spacecraft-database",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=["height_m", "diameter_m", "mass_kg",
                     "payload_leo_kg", "payload_gto_kg", "num_stages"],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="launch_vehicles.parquet",
            min_rows=100,
            expected_columns=["name"],
            critical_columns=["name"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update launch vehicles database: {n:,} vehicles",
        )
    print("Done.")


if __name__ == "__main__":
    main()
