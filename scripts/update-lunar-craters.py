#!/usr/bin/env python3
"""Fetch Lunar crater database (Robbins 2019) and upload to HF.

Source: Robbins (2019), JGR Planets 124, 871-892.
Distributed by USGS Astrogeology Science Center.
"""

import io
import sys
import zipfile

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

DATA_URLS = [
    "https://astropedia.astrogeology.usgs.gov/download/Moon/Research/Craters/lunar_crater_database_robbins_2019.csv",
    "https://craters.sjrdesign.net/RobbinsCraterDatabase_20140829.tsv.zip",
]
HF_REPO = "juliensimon/lunar-craters-robbins"

# ── Column mapping ───────────────────────────────────────────────────
KEEP_COLS = {
    "CRATER_ID": "crater_id",
    "LAT_CIRC_IMG": "latitude_deg", "LATITUDE_CIRCLE_IMAGE": "latitude_deg",
    "LON_CIRC_IMG": "longitude_deg", "LONGITUDE_CIRCLE_IMAGE": "longitude_deg",
    "DIAM_CIRC_IMG": "diameter_km", "DIAM_CIRCLE_IMAGE": "diameter_km",
    "DEPTH_RIM_TOPO": "depth_km", "DEPTH_RIMFLOOR_TOPOG": "depth_km",
    "DEPTH_FLOOR_TOPO": "floor_elevation_km",
    "DEPTH_RIM_SD": "depth_rim_sd_km",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "crater_id": "Unique integer crater identifier assigned by Robbins (2019); stable across catalog versions",
    "latitude_deg": "Selenocentric latitude of crater center in degrees (-90 to +90; positive = north)",
    "longitude_deg": "Selenocentric longitude of crater center in degrees (0-360, positive East; prime meridian at sub-Earth point)",
    "diameter_km": "Rim-to-rim crater diameter in km; ranges from ~1 km (catalog floor) to ~2,500 km for the largest basins",
    "depth_km": "Rim-to-floor depth derived from LOLA topography in km; null for heavily eroded craters where the rim is indistinct",
    "floor_elevation_km": "Absolute floor elevation in km relative to the lunar reference ellipsoid; null when floor topography is not measured",
    "depth_rim_sd_km": "Standard deviation of rim elevation measurements in km; larger values indicate irregular or degraded rims; null when fewer than 3 rim points were measured",
    "size_class": "Derived size category: small (<5 km), medium (5-20 km), large (20-100 km), giant (>100 km); null only if diameter is missing",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
The definitive lunar impact crater database, containing craters with diameter >= 1 km. \
Essential reference for Artemis mission planning and lunar surface studies.

This database was compiled by Stuart J. Robbins (2019) using Lunar Reconnaissance Orbiter (LRO) \
imagery and LOLA topography. It is the most comprehensive catalog of lunar impact craters, \
covering the entire lunar surface with consistent methodology.

The Moon preserves a cratering record stretching back over four billion years, largely unmodified \
by the plate tectonics, erosion, and volcanism that have resurfaced Earth. This makes lunar craters \
an indispensable calibration standard for crater counting chronology across the inner solar system.

Crater morphology on the Moon transitions from simple bowl-shaped structures below about 15 km \
diameter to complex craters with central peaks, terraced walls, and flat floors at larger sizes. \
The largest impacts produced multi-ring basins -- such as South Pole-Aitken (roughly 2,500 km \
diameter), the largest confirmed impact structure in the solar system.

This database is directly relevant to NASA's Artemis program. Crater catalogs are critical for \
landing site selection, hazard assessment, and traverse planning, particularly in the permanently \
shadowed regions near the south pole where water ice deposits have been detected.
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


def fetch_data():
    """Try multiple URLs with fallback."""
    for url in DATA_URLS:
        print(f"  Trying {url[:80]}...")
        try:
            resp = requests.get(url, timeout=120, headers={"User-Agent": "space-datasets/1.0"})
            resp.raise_for_status()
            if url.endswith(".zip"):
                with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                    names = [n for n in zf.namelist()
                             if n.endswith((".csv", ".tsv", ".txt"))
                             and not n.startswith("__MACOSX")
                             and "Changelog" not in n]
                    if not names:
                        continue
                    with zf.open(names[0]) as f:
                        return pd.read_csv(f, sep="\t", low_memory=False, encoding="latin-1")
            else:
                return pd.read_csv(io.StringIO(resp.text), low_memory=False)
        except Exception as e:
            print(f"  Failed: {e}")
    print("::error::All download URLs failed")
    sys.exit(1)


def main():
    print("Fetching Lunar crater database (Robbins 2019)...")
    df = fetch_data()
    print(f"  {len(df):,} raw rows")

    # Keep and rename columns
    available = {c: v for c, v in KEEP_COLS.items() if c in df.columns}
    df = df[list(available.keys())].rename(columns=available)

    # Derived column
    df["size_class"] = df["diameter_km"].apply(size_class)

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_small = int((df["size_class"] == "small").sum())
    n_medium = int((df["size_class"] == "medium").sum())
    n_large = int((df["size_class"] == "large").sum())
    n_giant = int((df["size_class"] == "giant").sum())
    diam_min = df["diameter_km"].min()
    diam_max = df["diameter_km"].max()
    has_depth = int(df["depth_km"].notna().sum()) if "depth_km" in df.columns else 0

    quick_stats = f"""\
- **{n_total:,}** total lunar craters
- Size distribution: {n_small:,} small, {n_medium:,} medium, {n_large:,} large, {n_giant:,} giant
- Diameter range: {diam_min:.2f} -- {diam_max:.1f} km
- **{has_depth:,}** craters with depth measurements"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/lunar-craters-robbins", split="train")
df = ds.to_pandas()

# Size distribution
import matplotlib.pyplot as plt
df["diameter_km"].hist(bins=100, log=True)
plt.xlabel("Diameter (km)")
plt.ylabel("Count")
plt.title("Lunar Crater Size Distribution")
plt.show()

# South pole region (Artemis-relevant)
south_pole = df[(df["latitude_deg"] < -80)]
print(f"Craters near south pole: {len(south_pole):,}")
plt.scatter(south_pole["longitude_deg"], south_pole["latitude_deg"],
            s=south_pole["diameter_km"], alpha=0.5)
plt.title("Lunar South Pole Craters")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Lunar Crater Database (Robbins 2019)",
        description=DESCRIPTION,
        tags=["space", "moon", "lunar", "crater", "planetary-science",
              "usgs", "artemis", "open-data", "tabular-data", "parquet"],
        source_url="https://astropedia.astrogeology.usgs.gov/download/Moon/Research/Craters/",
        task_categories=["tabular-classification", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/planetary-science-datasets-69c2d4683bd6a66c34fb4af2",
        banner={
            "url": "https://images-assets.nasa.gov/image/as08-14-2506/as08-14-2506~small.jpg",
            "alt": "The Moon from Apollo 8, showing craters and surface detail",
            "credit": "NASA/Apollo 8",
        },
        related_datasets=[
            "juliensimon/impact-craters",
            "juliensimon/ceres-craters-dawn",
            "juliensimon/planetary-nomenclature",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "latitude_deg", "longitude_deg", "diameter_km", "depth_km",
                "floor_elevation_km", "depth_rim_sd_km",
            ],
        )
        p.publish(
            df,
            filename="lunar_craters.parquet",
            min_rows=300_000,
            expected_columns=["crater_id", "latitude_deg", "longitude_deg", "diameter_km"],
            critical_columns=["crater_id", "latitude_deg", "longitude_deg", "diameter_km"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Lunar craters: {n_total:,} records",
        )
    print("Done.")


if __name__ == "__main__":
    main()
