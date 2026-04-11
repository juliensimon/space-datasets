#!/usr/bin/env python3
"""Fetch NASA meteorite landing data and upload to HF.

Source: NASA/Meteoritical Society via Wolfram Data Repository
(NASA retired the original Socrata SODA API in 2025).
"""

import re
from io import StringIO

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

# NASA retired the Socrata SODA API (y77d-th95 / gh4g-9sfh).
# The full 45K-row dataset is mirrored by Wolfram Data Repository.
WOLFRAM_CSV_URL = (
    "https://www.wolframcloud.com/objects/"
    "8ae6268d-3eaf-4f3a-8928-05d140a08e20"
)
HF_REPO = "juliensimon/meteorite-landings"

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "name": "Official meteorite name assigned by the Meteoritical Society (e.g., 'Allende', 'NWA 869'); typically reflects recovery location plus sequence number",
    "id": "Unique integer identifier from the NASA/Meteoritical Society database",
    "nametype": "Name validity: 'Valid' (standard accepted name) or 'Relict' (heavily weathered, likely terrestrial origin); almost all entries are 'Valid'",
    "recclass": "Meteoritical Society classification (e.g., 'L5', 'H6', 'CM2', 'Iron-IVA'); letters = chemical group, numbers = petrologic grade; >400 distinct classes",
    "mass": "Total known mass in grams; null for ~15% of entries; range from <1 g to ~60,000,000 g (Hoba meteorite)",
    "mass_kg": "Total known mass in kilograms (mass / 1000); null when mass is null",
    "fall": "Discovery context: 'Fell' (witnessed falling, ~1,100 records) or 'Found' (discovered on ground, ~44,000 records)",
    "year": "Year of fall or recovery as a datetime (day and month set to January 1 of the recorded year); null for entries without a year",
    "reclat": "Recovery site latitude in decimal degrees (positive = N, negative = S); null for ~one-third of entries, especially older finds without GPS records",
    "reclong": "Recovery site longitude in decimal degrees (positive = E, negative = W); null when reclat is null",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
NASA's comprehensive database of all known meteorite landings on Earth, with \
classification, mass, coordinates, and discovery context.

Meteorites are the only extraterrestrial materials available for direct laboratory \
analysis, making them indispensable for understanding solar system formation and \
evolution. The classification system reflects mineralogy and petrogenesis: ordinary \
chondrites (H, L, LL groups) are the most common falls and sample undifferentiated \
material from the inner asteroid belt, while carbonaceous chondrites (CI, CM, CV, CO, \
CR groups) preserve pre-solar grains and organic molecules dating to before the Sun's \
formation. Iron meteorites (e.g., Iron-IVA, Iron-IIIAB) are fragments of the metallic \
cores of differentiated asteroids that were disrupted by collisions, and achondrites \
(e.g., HED meteorites from 4 Vesta, SNC meteorites from Mars, and lunar meteorites) \
sample the crusts and mantles of differentiated bodies.

The distinction between "Fell" and "Found" meteorites has important implications for \
collection bias. Observed falls provide an unbiased sample of the meteorite flux at \
Earth, dominated by ordinary chondrites (~80% of falls). Found meteorites are biased \
toward durable iron-rich specimens that survive weathering and are visually distinctive. \
The geographic distribution of finds is heavily concentrated in deserts (the Sahara, \
Antarctica, the Nullarbor Plain) where dark meteorites contrast against light terrain \
and minimal weathering preserves specimens for thousands of years.
"""


def _parse_wolfram_mass(val):
    """Extract numeric mass in grams from Wolfram Quantity[..., 'Grams']."""
    if not isinstance(val, str) or "Quantity" not in val:
        return None
    m = re.search(r"Quantity\[([^,]+),", val)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def _parse_wolfram_year(val):
    """Extract year from Wolfram DateObject[{YYYY}, ...]."""
    if not isinstance(val, str) or "DateObject" not in val:
        return None
    m = re.search(r"DateObject\[\{(\d+)\}", val)
    if m:
        return int(m.group(1))
    return None


def _parse_wolfram_coords(val):
    """Extract (lat, lon) from Wolfram GeoPosition[{lat, lon}]."""
    if not isinstance(val, str) or "GeoPosition" not in val:
        return None, None
    m = re.search(r"GeoPosition\[\{([^,]+),\s*([^}]+)\}", val)
    if m:
        try:
            return float(m.group(1)), float(m.group(2))
        except ValueError:
            return None, None
    return None, None


def main():
    print("Fetching meteorite landings from Wolfram Data Repository...")
    resp = requests.get(WOLFRAM_CSV_URL, timeout=120)
    resp.raise_for_status()

    df = pd.read_csv(StringIO(resp.text))
    print(f"  {len(df):,} raw rows")

    # Rename columns to match original schema
    df = df.rename(columns={
        "Name": "name",
        "ID": "id",
        "NameType": "nametype",
        "Classification": "recclass",
        "Mass": "mass_raw",
        "Fall": "fall",
        "Year": "year_raw",
        "Coordinates": "coords_raw",
    })

    # Parse Wolfram-encoded fields
    df["mass"] = df["mass_raw"].apply(_parse_wolfram_mass)
    df["year"] = df["year_raw"].apply(_parse_wolfram_year)
    coords = df["coords_raw"].apply(lambda v: pd.Series(_parse_wolfram_coords(v)))
    df["reclat"] = coords[0]
    df["reclong"] = coords[1]

    # Build proper datetime from year (matching original schema)
    df["year"] = pd.to_datetime(df["year"], format="%Y", errors="coerce")

    # Drop raw columns
    df = df.drop(columns=["mass_raw", "year_raw", "coords_raw"])

    # Derived column: mass in kg
    df["mass_kg"] = (df["mass"] / 1000).round(3)

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Sort by year descending
    df = df.sort_values("year", ascending=False, na_position="last").reset_index(drop=True)

    print(f"  {len(df):,} meteorite landings")

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_fell = int((df["fall"] == "Fell").sum())
    n_found = int((df["fall"] == "Found").sum())
    n_with_mass = int(df["mass"].notna().sum())
    n_classes = df["recclass"].nunique()
    year_min = int(df["year"].dt.year.min()) if df["year"].notna().any() else 0
    year_max = int(df["year"].dt.year.max()) if df["year"].notna().any() else 0

    if df["mass"].notna().any():
        _h = df.loc[df["mass"].idxmax()]
        heaviest_name = _h["name"]
        heaviest_kg = f"{_h['mass_kg']:,.1f}"
    else:
        heaviest_name = "N/A"
        heaviest_kg = "0"

    quick_stats = f"""\
- **{n_total:,}** meteorite landings ({year_min}--{year_max})
- **{n_fell:,}** observed falls, **{n_found:,}** found specimens
- **{n_with_mass:,}** records with known mass
- **{n_classes}** distinct classification types
- Heaviest: **{heaviest_name}** at **{heaviest_kg} kg**"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/meteorite-landings", split="train")
df = ds.to_pandas()

# Observed falls sorted by mass
fell = df[df["fall"] == "Fell"].sort_values("mass_kg", ascending=False)

# Distribution of classification types
import matplotlib.pyplot as plt
df["recclass"].value_counts().head(20).plot.barh()
plt.xlabel("Count")
plt.ylabel("Classification")
plt.title("Top 20 Meteorite Classifications")
plt.tight_layout()
plt.show()

# Map of all landings with coordinates
with_coords = df.dropna(subset=["reclat", "reclong"])
plt.scatter(with_coords["reclong"], with_coords["reclat"], s=1, alpha=0.3)
plt.xlabel("Longitude")
plt.ylabel("Latitude")
plt.title(f"Meteorite Recovery Sites ({len(with_coords):,} with coordinates)")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Meteorite Landings",
        description=DESCRIPTION,
        tags=["space", "meteorites", "planetary-science", "nasa",
              "open-data", "tabular-data", "parquet"],
        source_url="https://data.nasa.gov/dataset/meteorite-landings",
        task_categories=["tabular-classification", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA17666/PIA17666~small.jpg",
            "alt": "Rosetta spacecraft approaching Comet 67P/Churyumov-Gerasimenko",
            "credit": "NASA/ESA",
        },
        related_datasets=[
            "juliensimon/neo-close-approaches",
            "juliensimon/nasa-exoplanets",
            "juliensimon/sentry-impact-risk",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=["mass", "mass_kg", "reclat", "reclong"],
            integer=["id"],
        )
        p.publish(
            df,
            filename="meteorite_landings.parquet",
            min_rows=40_000,
            expected_columns=["name", "id", "recclass", "mass", "fall", "year", "reclat", "reclong"],
            critical_columns=["name", "id", "recclass"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update meteorite landings: {n_total:,} records",
        )
    print("Done.")


if __name__ == "__main__":
    main()
