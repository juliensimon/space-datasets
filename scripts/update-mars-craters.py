#!/usr/bin/env python3
"""Fetch Mars crater database (Robbins & Hynek 2012) and upload to HF."""

import io
import sys
import zipfile

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

HF_REPO = "juliensimon/mars-craters-robbins"

# ── Source URLs (multi-fallback) ─────────────────────────────────────
DATA_URLS = [
    "https://astropedia.astrogeology.usgs.gov/download/Mars/Research/Craters/RobbinsCraterDatabase_20121016.tsv",
    "https://planetarynames.wr.usgs.gov/images/RobbinsCraterDatabase_20121016.tsv",
    "https://craters.sjrdesign.net/Catalog_Mars_Release_2020_1kmPlus_FullMorphData.csv.zip",
]

# ── Column mapping — supports both 2012 TSV and 2020 CSV column names ─
KEEP_COLS = {
    "CRATER_ID": "crater_id",
    "LATITUDE_CIRCLE_IMAGE": "latitude_deg",
    "LAT_CIRC_IMG": "latitude_deg",
    "LONGITUDE_CIRCLE_IMAGE": "longitude_deg",
    "LON_CIRC_IMG": "longitude_deg",
    "DIAM_CIRCLE_IMAGE": "diameter_km",
    "DIAM_CIRC_IMG": "diameter_km",
    "DEPTH_RIMFLOOR_TOPOG": "depth_km",
    "MORPHOLOGY_EJECTA_1": "ejecta_morphology_1",
    "MORPH_EJECTA_1": "ejecta_morphology_1",
    "MORPHOLOGY_EJECTA_2": "ejecta_morphology_2",
    "MORPH_EJECTA_2": "ejecta_morphology_2",
    "MORPHOLOGY_EJECTA_3": "ejecta_morphology_3",
    "MORPH_EJECTA_3": "ejecta_morphology_3",
    "NUMBER_LAYERS": "n_ejecta_layers",
    "N_LAYERS": "n_ejecta_layers",
}

# ── Column descriptions for README schema table ──────────────────────
COLUMN_DESCRIPTIONS = {
    "crater_id": "Unique crater identifier assigned by Robbins & Hynek; integer starting from 1",
    "latitude_deg": "Crater center planetocentric latitude in degrees (-90 to +90)",
    "longitude_deg": "Crater center east longitude in degrees (0–360 E; Mars uses east-positive convention)",
    "diameter_km": "Rim-to-rim crater diameter in km; catalog minimum is 1 km; maximum is ~2300 km (Hellas basin)",
    "depth_km": "Rim-to-floor depth in km derived from MOLA topography; null for heavily degraded or partially buried craters where the rim is poorly defined",
    "ejecta_morphology_1": 'Primary ejecta blanket morphology class (e.g. "Rd" = radial, "SLEP" = single-layer ejecta, "DLEP" = double-layer, "MLEPX" = multiple-layer; null if ejecta not preserved); indicates subsurface volatile content at time of impact',
    "ejecta_morphology_2": "Secondary ejecta morphology layer class; null if only one layer type is present",
    "ejecta_morphology_3": "Tertiary ejecta morphology layer class; null for most craters",
    "n_ejecta_layers": "Number of distinct ejecta layers identified; 0 = no preserved ejecta, 1–3+ for layered ejecta craters; null if not determined",
    "size_class": 'Derived size category: "small" (<5 km), "medium" (5–20 km), "large" (20–100 km), "giant" (>100 km)',
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
The only global Mars impact crater database, containing craters with diameter >= 1 km
identified from high-resolution imagery. This is the definitive reference catalog for Mars crater studies.

This database was compiled by Stuart J. Robbins and Brian M. Hynek (2012) using THEMIS, CTX,
and other Mars imagery. Every crater >= 1 km in diameter on the Martian surface was identified
and measured, including ejecta morphology classification and depth measurements where available.

Impact craters are the dominant geological landform on Mars, recording billions of years of bombardment
history across the planet's surface. The size-frequency distribution of craters is a primary tool for
estimating the ages of geological units on Mars and other planetary bodies — a technique known as
crater counting chronology. Larger craters excavate deeper into the crust, exposing subsurface materials
and creating central peaks, while smaller craters probe the mechanical properties of surface layers.
The transition diameter between simple (bowl-shaped) and complex (terraced, central-peak) craters on
Mars occurs near 6-8 km, reflecting the lower surface gravity compared to Earth.

Ejecta morphology is particularly diagnostic on Mars because many craters display layered or fluidized
ejecta blankets — rampart craters — that are interpreted as evidence for subsurface volatiles (water ice
or liquid water) at the time of impact. The number of ejecta layers and their morphological classification
correlate with crater size, latitude, and inferred subsurface ice distribution. This makes the Robbins
database an essential resource for mapping the planet's volatile inventory and understanding the evolution
of Mars's climate and hydrological cycle.

The depth-to-diameter ratios recorded in this catalog also carry important information. Fresh craters
follow a predictable scaling relationship between depth and diameter, while degraded craters exhibit
shallower profiles due to infilling by sediments, lava, or aeolian deposits. Systematic deviations from
the fresh-crater scaling law across different regions of Mars reveal patterns of resurfacing and erosion
that constrain the geological history of the Martian surface.
"""


def size_class(diameter):
    if pd.isna(diameter):
        return None
    if diameter < 5:
        return "small"
    if diameter <= 20:
        return "medium"
    if diameter <= 100:
        return "large"
    return "giant"


def fetch_craters():
    """Fetch crater data from multiple fallback URLs, handling both TSV and ZIP+CSV."""
    print("Fetching Mars crater database (Robbins & Hynek 2012)...")
    for url in DATA_URLS:
        try:
            print(f"  Trying {url[:80]}...")
            resp = requests.get(url, timeout=120, headers={"User-Agent": "space-datasets/1.0"})
            resp.raise_for_status()
            if url.endswith(".zip"):
                with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                    names = [n for n in zf.namelist() if n.endswith((".csv", ".tsv"))]
                    if not names:
                        continue
                    sep = "\t" if names[0].endswith(".tsv") else ","
                    with zf.open(names[0]) as f:
                        df = pd.read_csv(f, sep=sep, low_memory=False)
            else:
                df = pd.read_csv(io.StringIO(resp.text), sep="\t", low_memory=False)
            print(f"  {len(df):,} raw rows")
            return df
        except Exception as e:
            print(f"  Failed: {e}")
    print("::error::All download URLs failed")
    sys.exit(1)


def main():
    df_raw = fetch_craters()

    # Keep and rename columns (conditional mapping for 2012 vs 2020 source)
    available = {c: v for c, v in KEEP_COLS.items() if c in df_raw.columns}
    df = df_raw[list(available.keys())].rename(columns=available)

    # Derived column
    df["size_class"] = df["diameter_km"].apply(size_class)

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_small = int((df["size_class"] == "small").sum())
    n_medium = int((df["size_class"] == "medium").sum())
    n_large = int((df["size_class"] == "large").sum())
    n_giant = int((df["size_class"] == "giant").sum())
    diam_min = df["diameter_km"].min()
    diam_max = df["diameter_km"].max()

    quick_stats = f"""\
- **{n_total:,}** total craters (diameter >= 1 km)
- Size distribution: **{n_small:,}** small (<5 km), **{n_medium:,}** medium (5–20 km), **{n_large:,}** large (20–100 km), **{n_giant:,}** giant (>100 km)
- Diameter range: {diam_min:.2f} – {diam_max:.1f} km"""

    # ── Custom usage example ─────────────────────────────────────────
    usage = """\
```python
from datasets import load_dataset
import matplotlib.pyplot as plt

ds = load_dataset("juliensimon/mars-craters-robbins", split="train")
df = ds.to_pandas()

# Size distribution histogram (log scale)
df["diameter_km"].hist(bins=100, log=True, color="firebrick", edgecolor="none")
plt.xlabel("Diameter (km)")
plt.ylabel("Count (log scale)")
plt.title("Mars Crater Size Distribution")
plt.tight_layout()
plt.show()

# Map of large craters scaled by diameter
large = df[df["size_class"].isin(["large", "giant"])]
plt.figure(figsize=(12, 6))
plt.scatter(large["longitude_deg"], large["latitude_deg"],
            s=large["diameter_km"] / 5, alpha=0.5, c="firebrick", linewidths=0)
plt.xlabel("Longitude (deg E)")
plt.ylabel("Latitude (deg)")
plt.title("Large Mars Craters (>20 km diameter)")
plt.tight_layout()
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Mars Crater Database (Robbins & Hynek 2012)",
        description=DESCRIPTION,
        tags=["space", "mars", "crater", "planetary-science", "usgs", "open-data", "tabular-data", "parquet"],
        source_url="https://astropedia.astrogeology.usgs.gov/download/Mars/Research/Craters/RobbinsCraterDatabase_20121016.tsv",
        task_categories=["tabular-classification", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/planetary-science-datasets-69c2d4683bd6a66c34fb4af2",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA24309/PIA24309~small.jpg",
            "alt": "Exploring Jezero Crater on Mars (illustration)",
            "credit": "NASA/JPL-Caltech",
        },
        related_datasets=[
            "juliensimon/lunar-craters",
            "juliensimon/impact-craters",
            "juliensimon/planetary-nomenclature",
        ],
    ) as p:
        numeric_cols = [c for c in ["latitude_deg", "longitude_deg", "diameter_km", "depth_km", "n_ejecta_layers"] if c in df.columns]
        df = p.clean(df, numeric=numeric_cols)
        p.publish(
            df,
            filename="mars_craters.parquet",
            min_rows=300_000,
            expected_columns=["crater_id", "latitude_deg", "longitude_deg", "diameter_km"],
            critical_columns=["crater_id", "latitude_deg", "longitude_deg", "diameter_km"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Mars craters: {n_total:,} records",
        )
    print("Done.")


if __name__ == "__main__":
    main()
