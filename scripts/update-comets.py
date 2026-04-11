#!/usr/bin/env python3
"""Fetch comet catalog from Wikidata and upload to HF."""

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

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

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "wikidata_id": "Wikidata entity ID (e.g. 'Q1390' for Halley's Comet); stable URI key for enrichment joins; links to full orbital history, discovery details, and apparition records in the knowledge graph",
    "name": "Comet name or designation (e.g. '1P/Halley', 'C/1995 O1 (Hale-Bopp)'); periodic comets use the NP/ prefix (N=number, P=periodic); non-periodic use C/; interstellar use I/",
    "discovery_date": "ISO 8601 date (YYYY-MM-DD) of the discovery observation; null for historically known comets (e.g. Halley, visible since antiquity) or where records are too uncertain to assign a precise date",
    "discoverer": "Name(s) of the person(s) or survey program credited with discovery; null for historically anonymous comets; modern entries may list an observatory or automated survey (e.g. LINEAR, NEOWISE)",
    "orbital_period_yr": "Orbital period in years; short-period (Jupiter-family) comets are typically <20 yr; Halley-type 20-200 yr; long-period >200 yr; null for hyperbolic or parabolic orbits where the comet makes a single unbound pass",
    "perihelion_au": "Closest approach distance to the Sun in AU; determines peak cometary activity and tail development; <1 AU enters the inner solar system; <0.3 AU is the sungrazing regime",
    "eccentricity": "Orbital eccentricity; 0 = circular, <1 = elliptical (bound), =1 = parabolic, >1 = hyperbolic (unbound, possibly of interstellar origin); null when orbital solution is unavailable",
    "inclination_deg": "Orbital inclination relative to the ecliptic plane in degrees (0-180); <30 indicates prograde low-inclination orbit typical of Jupiter-family comets; >90 indicates retrograde orbit",
    "named_after": "Entity (person, place, or concept) that the comet's name commemorates, distinct from the discoverer; null when the comet is named solely after its discoverer(s)",
    "epoch": "Reference epoch for the orbital elements in ISO 8601 format (YYYY-MM-DD); elements are valid near this date and diverge for predictions far from the epoch; null when orbital solution is absent",
    "discovery_year": "Year of discovery derived from discovery_date; retained as a standalone column for easy filtering and grouping; null when discovery_date is null",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Catalog of comets sourced from Wikidata, including orbital parameters, discovery dates, \
discoverers, and named-after information.

Comets are small icy bodies that develop a coma and tails when approaching the Sun. \
They originate from the Kuiper Belt and Oort Cloud and follow highly eccentric orbits \
ranging from short-period comets (< 200 years) to long-period and hyperbolic visitors.

This dataset aggregates structured comet data from Wikidata's SPARQL endpoint, capturing \
orbital mechanics (period, perihelion distance, eccentricity, inclination), discovery \
metadata (date, discoverer), and cultural information (named-after entities). It covers \
historically significant comets like Halley's Comet and Hale-Bopp through recently \
discovered objects.

The data enables studies of comet population statistics, orbital dynamics, discovery \
rate trends over time, and the history of comet observation and naming conventions.
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

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    df = df.sort_values("name").reset_index(drop=True)
    print(f"  {len(df):,} unique comets")

    # ── Domain-specific stats for README ─────────────────────────────
    n = len(df)
    n_with_period = int(df["orbital_period_yr"].notna().sum())
    n_with_perihelion = int(df["perihelion_au"].notna().sum())
    n_with_discoverer = int(df["discoverer"].notna().sum())
    n_with_ecc = int(df["eccentricity"].notna().sum())
    n_with_year = int(df["discovery_year"].notna().sum())

    min_year = int(df["discovery_year"].min()) if n_with_year > 0 else "N/A"
    max_year = int(df["discovery_year"].max()) if n_with_year > 0 else "N/A"

    top_discoverers = df["discoverer"].value_counts().head(5)
    top_disc_str = ", ".join(
        f"{d} ({c:,})" for d, c in top_discoverers.items()
    )

    quick_stats = f"""\
- **{n:,}** comets in catalog
- **{n_with_period:,}** with orbital period data
- **{n_with_perihelion:,}** with perihelion distance
- **{n_with_ecc:,}** with eccentricity
- **{n_with_discoverer:,}** with named discoverer
- Discovery years: {min_year} -- {max_year}
- Top discoverers: {top_disc_str}"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/comet-catalog", split="train")
df = ds.to_pandas()

# Short-period comets (period < 200 years)
short_period = df[df["orbital_period_yr"] < 200].dropna(subset=["orbital_period_yr"])
print(f"{len(short_period):,} short-period comets")

# Most recently discovered comets
recent = df.dropna(subset=["discovery_year"]).nlargest(10, "discovery_year")
print(recent[["name", "discovery_year", "discoverer"]])

# Highly eccentric comets (near-parabolic or hyperbolic)
high_ecc = df[df["eccentricity"] >= 0.99].dropna(subset=["eccentricity"])
print(high_ecc[["name", "eccentricity", "orbital_period_yr"]])

# Perihelion distance distribution
import matplotlib.pyplot as plt
valid = df.dropna(subset=["perihelion_au"])
plt.hist(valid["perihelion_au"], bins=50, range=(0, 10))
plt.xlabel("Perihelion distance (AU)")
plt.ylabel("Count")
plt.title("Comet Perihelion Distribution")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Comet Catalog",
        description=DESCRIPTION,
        license="cc0-1.0",
        tags=["space", "comets", "orbital-mechanics", "wikidata",
              "open-data", "tabular-data", "parquet"],
        source_url="https://www.wikidata.org/",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA17666/PIA17666~small.jpg",
            "alt": "Rosetta spacecraft approaching Comet 67P/Churyumov-Gerasimenko",
            "credit": "NASA/ESA",
        },
        related_datasets=[
            "juliensimon/mpc-comet-elements",
            "juliensimon/jpl-small-body-database",
            "juliensimon/fireball-bolide-events",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=["orbital_period_yr", "perihelion_au", "eccentricity", "inclination_deg"],
            strings=["name", "discoverer", "named_after", "epoch"],
        )
        p.publish(
            df,
            filename="comets.parquet",
            min_rows=500,
            expected_columns=["name"],
            critical_columns=["name"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update comet catalog: {n:,} comets",
        )
    print("Done.")


if __name__ == "__main__":
    main()
