#!/usr/bin/env python3
"""Fetch meteorite database from Wikidata and upload to HF.

Source: Wikidata SPARQL endpoint — all entities of type Q60186 (meteorite).
"""

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

HF_REPO = "juliensimon/meteorite-database"

WIKIDATA_URL = "https://query.wikidata.org/sparql"
HEADERS = {"User-Agent": "space-datasets/1.0 (https://github.com/juliensimon/space-datasets)"}

SPARQL_QUERY = """
SELECT ?met ?metLabel ?fallDate ?mass
       ?classLabel ?countryLabel
       ?lat ?lon
WHERE {
  ?met wdt:P31 wd:Q60186.
  OPTIONAL { ?met wdt:P585 ?pointInTime. }
  OPTIONAL { ?met wdt:P575 ?discoveryDate. }
  BIND(COALESCE(?pointInTime, ?discoveryDate) AS ?fallDate)
  OPTIONAL { ?met wdt:P2067 ?mass. }
  OPTIONAL { ?met wdt:P31 ?class.
             ?class wdt:P279* wd:Q60186.
             FILTER(?class != wd:Q60186) }
  OPTIONAL { ?met wdt:P17 ?country. }
  OPTIONAL { ?met p:P625 ?coordStmt.
             ?coordStmt psv:P625 ?coordNode.
             ?coordNode wikibase:geoLatitude ?lat.
             ?coordNode wikibase:geoLongitude ?lon. }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,mul". }
}
"""

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "wikidata_id": "Wikidata entity ID (e.g. Q1029); stable cross-reference key for linking to other Wikidata properties",
    "name": "Official meteorite name assigned by the Meteoritical Society (e.g., 'Allende', 'NWA 7034', 'Chelyabinsk'); typically location of find plus sequence number",
    "fall_date": "Date of observed fall or discovery/recovery in ISO format (YYYY-MM-DD); null for historical finds without a recorded date; precision often year-only (day defaults to 01)",
    "mass_g": "Total known mass in grams; null if unknown; range from <1 g (tiny fragments) to ~60,000,000 g (Hoba, the largest known meteorite)",
    "classification": "Meteoritical Society mineralogical/petrological class (e.g., 'L5', 'CM2', 'Iron IIIAB'); letters = chemical group, numbers = petrologic grade; null if not recorded in Wikidata",
    "country": "Country of recovery (English label from Wikidata); null for finds without a recorded country or in international territory (e.g., Antarctica)",
    "latitude": "Recovery location latitude in decimal degrees (positive = N, negative = S); null for historical or poorly documented finds",
    "longitude": "Recovery location longitude in decimal degrees (positive = E, negative = W); null for historical or poorly documented finds",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Catalogue of known meteorites sourced from Wikidata, covering mass, classification, \
fall date, country of recovery, and geographic coordinates.

Meteorites are extraterrestrial rocks that survive passage through Earth's atmosphere and \
reach the surface. They are classified by mineralogy and petrology (e.g., chondrites, \
achondrites, iron meteorites) and recorded either as falls (witnessed descent) or \
finds (recovered without observation).

This dataset aggregates Wikidata entries for all entities of type Q60186 (meteorite), pulling \
structured properties including mass (P2067), fall/discovery date (P585/P575), country (P17), \
coordinates (P625), and mineralogical class (via P31 subclass hierarchy). It complements NASA \
and Meteoritical Society databases with Wikidata's multilingual, cross-linked knowledge graph.
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
        })

    df = pd.DataFrame(rows)

    # Deduplicate on wikidata_id -- keep the most complete row
    df["_completeness"] = df.notna().sum(axis=1)
    df = df.sort_values("_completeness", ascending=False).drop_duplicates(
        subset=["wikidata_id"], keep="first"
    ).drop(columns=["_completeness"])

    # Drop bare Q-ID names (junk Wikidata entries without a real label)
    df = df[~df["name"].str.match(r"^Q\d+$", na=False)]

    return df


def main():
    df = fetch_meteorites()

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    df = df.sort_values("name").reset_index(drop=True)
    print(f"  {len(df):,} unique meteorites")

    # ── Domain-specific stats for README ─────────────────────────────
    n = len(df)
    n_with_mass = int(df["mass_g"].notna().sum())
    n_with_coords = int(df["latitude"].notna().sum())
    n_countries = int(df["country"].nunique())
    n_classified = int(df["classification"].notna().sum())

    heaviest = df.loc[df["mass_g"].idxmax()] if n_with_mass > 0 else None
    heaviest_str = (
        f"{heaviest['name']} ({heaviest['mass_g']:,.0f} g)"
        if heaviest is not None else "N/A"
    )

    top_countries = df["country"].value_counts().head(5)
    top_countries_str = ", ".join(
        f"{c} ({cnt:,})" for c, cnt in top_countries.items()
    )

    top_classes = df["classification"].value_counts().head(5)
    top_classes_str = ", ".join(
        f"{c} ({cnt:,})" for c, cnt in top_classes.items()
    )

    quick_stats = f"""\
- **{n:,}** meteorites total
- **{n_with_mass:,}** with recorded mass
- **{n_with_coords:,}** with geographic coordinates
- **{n_classified:,}** with classification
- **{n_countries:,}** countries of recovery
- Heaviest: {heaviest_str}
- Top countries: {top_countries_str}
- Top classifications: {top_classes_str}"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/meteorite-database", split="train")
df = ds.to_pandas()

# Heaviest meteorites
print(df.nlargest(10, "mass_g")[["name", "mass_g", "country", "classification"]])

# Meteorites by country
import matplotlib.pyplot as plt
df["country"].value_counts().head(15).plot.barh()
plt.xlabel("Count")
plt.ylabel("Country")
plt.title("Meteorites by Country of Recovery")
plt.tight_layout()
plt.show()

# Mass distribution (log scale)
import numpy as np
masses = df["mass_g"].dropna()
plt.hist(np.log10(masses[masses > 0]), bins=50)
plt.xlabel("log10(mass in grams)")
plt.ylabel("Count")
plt.title("Meteorite Mass Distribution")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Meteorite Database",
        description=DESCRIPTION,
        tags=["space", "planetary-science", "meteorites", "wikidata",
              "open-data", "tabular-data", "parquet"],
        source_url="https://www.wikidata.org/",
        license="cc0-1.0",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA17666/PIA17666~small.jpg",
            "alt": "Rosetta spacecraft approaching Comet 67P/Churyumov-Gerasimenko",
            "credit": "NASA/ESA",
        },
        related_datasets=[
            "juliensimon/impact-craters",
            "juliensimon/fireball-bolide-events",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=["mass_g", "latitude", "longitude"],
            strings=["name", "classification", "country"],
        )
        p.publish(
            df,
            filename="meteorites.parquet",
            min_rows=500,
            expected_columns=["name", "wikidata_id"],
            critical_columns=["name"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update meteorite database: {n:,} meteorites",
        )
    print("Done.")


if __name__ == "__main__":
    main()
