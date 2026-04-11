#!/usr/bin/env python3
"""Fetch constellation catalog from Wikidata and upload to HF.

Source: Wikidata SPARQL — all IAU-recognized constellations identified
via P31 (instance of) = Q8928 (constellation).
"""

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

HF_REPO = "juliensimon/constellation-catalog"

WIKIDATA_URL = "https://query.wikidata.org/sparql"
HEADERS = {"User-Agent": "space-datasets/1.0 (https://github.com/juliensimon/space-datasets)"}

SPARQL_QUERY = """
SELECT ?cons ?consLabel ?iauAbbrev ?symbolLabel
       ?brightestStarLabel ?areaSquareDeg
       ?namedAfterLabel
WHERE {
  ?cons wdt:P31 wd:Q8928.
  OPTIONAL { ?cons wdt:P1813 ?iauAbbrev. }
  OPTIONAL { ?cons wdt:P367 ?symbol. }
  OPTIONAL { ?cons wdt:P7015 ?brightestStar. }
  OPTIONAL { ?cons wdt:P2046 ?areaSquareDeg. }
  OPTIONAL { ?cons wdt:P138 ?namedAfter. }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,mul". }
}
"""

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "wikidata_id": "Wikidata entity ID (e.g. 'Q8928'); stable URI for cross-referencing enrichment sources and linking to other knowledge bases",
    "name": "Full IAU-recognized English name (e.g. 'Orion', 'Ursa Major'); all 88 official constellations covering the entire celestial sphere",
    "iau_abbreviation": "IAU 3-letter abbreviation used in star names and catalogs (e.g. 'Ori', 'UMa'); standardized by Delporte 1930; null for non-standard entries",
    "symbol": "Traditional figure or symbol the constellation depicts (e.g. 'hunter', 'bear'); null for constellations without a recorded symbol in Wikidata",
    "brightest_star": "Common name of the visually brightest star in the constellation (e.g. 'Rigel' for Orion); null if not recorded in Wikidata",
    "area_sq_deg": "Area enclosed by IAU boundary in square degrees; range ~68 sq deg (Crux) to ~1303 sq deg (Hydra); total sky = 41,253 sq deg",
    "named_after": "Mythological figure, animal, instrument, or object the constellation represents (e.g. 'Orion' the hunter); null for constellations without a recorded origin",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Complete catalog of all IAU-recognized constellations sourced from Wikidata, \
with IAU abbreviations, area in square degrees, brightest star, and \
mythological origin.

The International Astronomical Union (IAU) officially recognizes 88 constellations that \
together tile the entire celestial sphere. These range from ancient Greek figures catalogued \
by Ptolemy in the Almagest to southern-hemisphere constellations added by European explorers \
in the 16th-18th centuries and formalized by Eugene Delporte in 1930.

This dataset records each constellation with its IAU three-letter abbreviation, the area it \
covers in square degrees, its brightest star, and the mythological figure or object it was \
named after. This enables sky-coverage analysis, educational tools, and cross-referencing \
with star and deep-sky-object catalogs.

Sourced from Wikidata's structured knowledge base (property P31=Q8928 for \
instance-of:constellation), maintained by the astronomy community.
"""


def fetch_constellations() -> pd.DataFrame:
    """Query Wikidata SPARQL for all constellations."""
    print("Querying Wikidata for constellations...")
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
        wikidata_id = r.get("cons", {}).get("value", "").rsplit("/", 1)[-1]
        area_raw = r.get("areaSquareDeg", {}).get("value")
        rows.append({
            "wikidata_id": wikidata_id,
            "name": r.get("consLabel", {}).get("value"),
            "iau_abbreviation": r.get("iauAbbrev", {}).get("value") or None,
            "symbol": r.get("symbolLabel", {}).get("value") or None,
            "brightest_star": r.get("brightestStarLabel", {}).get("value") or None,
            "area_sq_deg": float(area_raw) if area_raw else None,
            "named_after": r.get("namedAfterLabel", {}).get("value") or None,
        })

    df = pd.DataFrame(rows)

    # Deduplicate on wikidata_id -- keep first occurrence
    df = df.drop_duplicates(subset=["wikidata_id"], keep="first")

    # Drop entries with no real name (bare Q-IDs = junk Wikidata entities)
    df = df[~df["name"].str.match(r"^Q\d+$", na=False)]

    return df


def main():
    df = fetch_constellations()

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    df = df.sort_values("name").reset_index(drop=True)
    print(f"  {len(df):,} unique constellations")

    # ── Domain-specific stats for README ─────────────────────────────
    n = len(df)
    n_with_area = int(df["area_sq_deg"].notna().sum())
    n_with_brightest = int(df["brightest_star"].notna().sum())
    n_with_named_after = int(df["named_after"].notna().sum())
    total_area = df["area_sq_deg"].sum()

    quick_stats = f"""\
- **{n}** IAU-recognized constellations
- **{n_with_area:,}** with area in square degrees (total sky: ~{total_area:,.0f} sq deg)
- **{n_with_brightest:,}** with brightest star identified
- **{n_with_named_after:,}** with named-after mythology or origin"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/constellation-catalog", split="train")
df = ds.to_pandas()

# Largest constellations by area
print(df.nlargest(10, "area_sq_deg")[["name", "iau_abbreviation", "area_sq_deg"]])

# Constellations named after mythological figures
myth = df[df["named_after"].notna()]
print(myth[["name", "named_after"]].head(10))

# Area distribution
import matplotlib.pyplot as plt
df.dropna(subset=["area_sq_deg"]).sort_values("area_sq_deg").plot.barh(
    x="name", y="area_sq_deg", figsize=(8, 18), legend=False
)
plt.xlabel("Area (sq deg)")
plt.title("Constellation Areas")
plt.tight_layout()
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Constellation Catalog",
        description=DESCRIPTION,
        license="cc0-1.0",
        tags=["space", "astronomy", "constellations", "wikidata",
              "open-data", "tabular-data", "parquet"],
        source_url="https://www.wikidata.org/",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/space-essentials-69cbafd7ea046a10eff11405",
        banner={
            "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e000191/GSFC_20171208_Archive_e000191~medium.jpg",
            "alt": "A field of stars observed by the Hubble Space Telescope",
            "credit": "NASA/ESA/Hubble",
        },
        related_datasets=[
            "juliensimon/astronomer-database",
            "juliensimon/observatory-database",
            "juliensimon/bright-star-catalog",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=["area_sq_deg"],
            strings=["name", "wikidata_id", "iau_abbreviation", "symbol",
                     "brightest_star", "named_after"],
        )
        p.publish(
            df,
            filename="constellations.parquet",
            min_rows=50,
            expected_columns=["name"],
            critical_columns=["name"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update constellation catalog: {n:,} constellations",
        )
    print("Done.")


if __name__ == "__main__":
    main()
