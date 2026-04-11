#!/usr/bin/env python3
"""Fetch impact crater database from Wikidata and upload to HF.

Source: Wikidata SPARQL endpoint (class Q55818: impact crater).
Community-curated by WikiProject Astronomy and WikiProject Solar System.
"""

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

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

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "wikidata_id": "Wikidata entity ID (e.g. Q12345); used for cross-referencing with other Wikidata-linked datasets",
    "name": "IAU or locally recognised crater name; unnamed craters filtered out during processing",
    "diameter_km": "Crater rim-to-rim diameter in km; range 0.001 km (microcraters) to ~2,500 km (South Pole-Aitken Basin); null for craters without measured diameter in Wikidata",
    "age_mya": "Estimated formation age in millions of years ago; null for the majority of craters where age is unconstrained; highly uncertain for many entries",
    "location": "Administrative or geographic region label from Wikidata (e.g., 'Ontario', 'Sahara'); null for bodies without administrative subdivisions or when not recorded",
    "body": "Planetary body hosting the crater (e.g., 'Earth', 'Moon', 'Mars', 'Vesta'); null for a small number of entries with missing body data",
    "latitude": "Crater center latitude in decimal degrees; coordinate system is body-centric for each object; null for craters without coordinates in Wikidata",
    "longitude": "Crater center longitude in decimal degrees; East-positive convention; null for craters without coordinates in Wikidata",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Comprehensive database of impact craters across the solar system, sourced from Wikidata.

Impact craters are among the most widespread geological features in the solar system, \
formed when asteroids, comets, or meteoroids collide with a planetary surface. They are \
critical windows into a body's geological history: crater size-frequency distributions \
reveal relative ages of surfaces, and large craters like Chicxulub on Earth have been \
linked to mass extinction events.

This dataset aggregates crater records for bodies ranging from Mercury and the Moon to \
Mars, Ceres, Vesta, and outer-planet moons. Each record includes the crater name, \
diameter (where known), estimated age in millions of years, the parent body, and \
geographic coordinates for bodies with established coordinate systems.

Sourced from Wikidata's structured knowledge base (class Q55818: impact crater), \
maintained by the WikiProject Astronomy and WikiProject Solar System communities.
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

    # Deduplicate on wikidata_id -- multiple location/body matches can create duplicates
    df["_filled"] = df.notna().sum(axis=1)
    df = df.sort_values("_filled", ascending=False).drop_duplicates(
        subset=["wikidata_id"], keep="first"
    ).drop(columns=["_filled"])

    # Drop bare Q-ID names (junk Wikidata entities with no label)
    df = df[~df["name"].str.match(r"^Q\d+$", na=False)]

    return df


def main():
    df = fetch_craters()

    df = df.sort_values("name").reset_index(drop=True)
    print(f"  {len(df):,} unique craters")

    # ── Domain-specific stats for README ─────────────────────────────
    n = len(df)
    n_with_diameter = int(df["diameter_km"].notna().sum())
    n_with_age = int(df["age_mya"].notna().sum())
    n_with_coords = int(df["latitude"].notna().sum())
    n_bodies = int(df["body"].nunique())

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

    quick_stats = f"""\
- **{n:,}** craters on **{n_bodies}** planetary bodies
- **{n_with_diameter:,}** craters with known diameter
- **{n_with_age:,}** craters with estimated age
- **{n_with_coords:,}** craters with coordinates
- Largest crater: {largest_name} ({largest_km:,.0f} km)
- Oldest crater: {oldest_name} ({oldest_mya:,.0f} Ma)
- Craters per body: {top_bodies_str}"""

    usage = """\
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
import matplotlib.pyplot as plt
earth = df[(df["body"] == "Earth") & df["latitude"].notna()]
plt.scatter(earth["longitude"], earth["latitude"], s=earth["diameter_km"] / 5, alpha=0.6)
plt.xlabel("Longitude")
plt.ylabel("Latitude")
plt.title(f"Earth Impact Craters ({len(earth)} with coordinates)")
plt.show()

# Ancient craters (> 2 Ga)
ancient = df[df["age_mya"] > 2000].sort_values("age_mya", ascending=False)
print(ancient[["name", "body", "diameter_km", "age_mya"]].head(10))
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Impact Craters",
        description=DESCRIPTION,
        license="cc0-1.0",
        tags=["space", "planetary-science", "craters", "impact",
              "wikidata", "open-data", "tabular-data", "parquet"],
        source_url="https://www.wikidata.org/wiki/Q55818",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/planetary-science-datasets-69c2d4683bd6a66c34fb4af2",
        banner={
            "url": "https://images-assets.nasa.gov/image/as08-14-2506/as08-14-2506~small.jpg",
            "alt": "The Moon seen from Apollo 8, showing craters and surface detail",
            "credit": "NASA/Apollo 8",
        },
        related_datasets=[
            "juliensimon/ceres-craters-dawn",
            "juliensimon/lunar-craters-robbins",
            "juliensimon/planetary-nomenclature",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=["diameter_km", "age_mya", "latitude", "longitude"],
            strings=["name", "location", "body"],
        )
        p.publish(
            df,
            filename="impact_craters.parquet",
            min_rows=1000,
            expected_columns=["name", "body"],
            critical_columns=["name"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update impact craters: {n:,} craters",
        )
    print("Done.")


if __name__ == "__main__":
    main()
