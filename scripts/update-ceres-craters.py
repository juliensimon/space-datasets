#!/usr/bin/env python3
"""Fetch Ceres crater database (Zeilnhofer 2020) and upload to HF.

Source: Zeilnhofer & Hiesinger (2020), Dawn Framing Camera 2.
Distributed by USGS Astrogeology Science Center via Astropedia.
"""

import io
import sys
import time
import zipfile

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

DATA_URL = "https://astropedia.astrogeology.usgs.gov/download/Ceres/Dawn/Craters/ceres_dawn_fc2_craterdatabase_zeilnhofer_2020_v2.zip"
HF_REPO = "juliensimon/ceres-craters-dawn"

# ── Column mapping ───────────────────────────────────────────────────
RENAME = {
    "CRATER_ID": "crater_id", "Crater_ID": "crater_id", "ID": "crater_id",
    "LAT_CIRC_IMG": "latitude_deg", "LATITUDE_CIRCLE_IMAGE": "latitude_deg",
    "Lat_Circ_Img": "latitude_deg", "Lat": "latitude_deg", "lat": "latitude_deg",
    "LON_CIRC_IMG": "longitude_deg", "LONGITUDE_CIRCLE_IMAGE": "longitude_deg",
    "Lon_Circ_Img": "longitude_deg", "Lon": "longitude_deg", "lon": "longitude_deg",
    "DIAM_CIRC_IMG": "diameter_km", "DIAM_CIRCLE_IMAGE": "diameter_km",
    "Diam_Circ_Img": "diameter_km", "Diam_km": "diameter_km", "diam_km": "diameter_km",
    "Diameter": "diameter_km", "D_km": "diameter_km",
    "DEPTH_RIM_TOPO": "depth_km", "DEPTH_RIMFLOOR_TOPOG": "depth_km",
    "Depth_Rim_Topo": "depth_km", "Depth_km": "depth_km", "d_km": "depth_km",
    "DEPTH_DIAM_RATIO": "depth_diameter_ratio", "Depth_Diam_Ratio": "depth_diameter_ratio",
    "d_D": "depth_diameter_ratio", "dD": "depth_diameter_ratio",
    "MORPHOLOGY_EJECTA_1": "ejecta_morphology", "MORPH_EJECTA_1": "ejecta_morphology",
    "Morphology": "morphology", "morphology": "morphology",
    "Degradation": "degradation_state", "Degradation_State": "degradation_state",
    "DEG_STATE": "degradation_state",
    "Preservation": "preservation_state",
    "Confidence": "confidence", "CONFIDENCE": "confidence",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "crater_id": "Unique integer crater identifier assigned in the Zeilnhofer (2020) catalog; stable across versions",
    "latitude_deg": "Crater center planetocentric latitude (degrees, -90 to +90)",
    "longitude_deg": "Crater center east longitude on Ceres (degrees, 0-360 E; Ceres uses east-positive convention)",
    "diameter_km": "Crater rim-to-rim diameter (km); range ~0.1-280 km (largest: Kerwan basin)",
    "depth_km": "Rim-to-floor depth (km); shallower than expected for size suggests infill by mass wasting or cryovolcanism; null if not measured",
    "depth_diameter_ratio": "Depth divided by diameter; fresh craters ~0.15-0.20; decreases with degradation and ice-driven viscous relaxation",
    "ejecta_morphology": "Morphological classification of the crater ejecta blanket (e.g., layered, radial); null for craters without distinct ejecta",
    "morphology": "General morphological classification of the crater (e.g., simple, complex, degraded); null for unclassified craters",
    "degradation_state": "Qualitative degradation state indicating crater freshness; fresh craters have sharp rims, degraded ones are partially infilled",
    "preservation_state": "Preservation quality assessment of the crater structure; complements the degradation state",
    "confidence": "Confidence level in the crater identification; lower values indicate ambiguous or uncertain detections",
    "size_class": "Derived size category: small (<5 km), medium (5-20 km), large (20-100 km), giant (>100 km)",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
The most comprehensive catalog of impact craters on dwarf planet Ceres, containing \
craters with diameter >= 1 km identified from Dawn Framing Camera (FC2) imagery.

This database was compiled by M. F. Zeilnhofer and H. Hiesinger (2020) using images from NASA's Dawn \
spacecraft Framing Camera 2. Every crater >= 1 km in diameter on Ceres was identified and measured, \
providing positions, diameters, and depth measurements where available.

Ceres occupies a unique position in solar system science as a volatile-rich body that has remained \
largely intact since the early stages of planetary formation. With a mean diameter of approximately \
940 km and a bulk density of about 2.16 g/cm3, Ceres is thought to harbor a substantial water ice \
component beneath its regolith, and possibly a residual subsurface brine layer. The Dawn spacecraft's \
orbital observations revealed bright deposits of sodium carbonate and ammonium-bearing minerals in \
several craters -- most famously in Occator crater -- interpreted as recent or ongoing cryovolcanic \
activity where brines have migrated to the surface.

The crater population on Ceres provides key constraints on the age and evolution of the asteroid belt. \
Notably, Ceres has a deficit of large craters (greater than 100 km) compared to predictions from \
collisional models, suggesting that viscous relaxation of the ice-rich crust has erased large basins \
over geological time. The depth-to-diameter ratios of Cerean craters are systematically shallower than \
those on Vesta or the Moon, consistent with a mechanically weak, ice-bearing lithosphere.
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


def main():
    print("Fetching Ceres crater database (Zeilnhofer 2020)...")

    # Download zip with retries
    df = None
    for attempt in range(1, 4):
        try:
            print(f"  Attempt {attempt}: {DATA_URL[:80]}...")
            resp = requests.get(DATA_URL, timeout=120, headers={"User-Agent": "space-datasets/1.0"})
            resp.raise_for_status()
            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                names = [n for n in zf.namelist()
                         if n.endswith((".csv", ".tsv", ".txt"))
                         and not n.startswith("__MACOSX")]
                if not names:
                    print("  No CSV/TSV found in zip")
                    continue
                print(f"  Extracting {names[0]}")
                with zf.open(names[0]) as f:
                    df = pd.read_csv(f, low_memory=False, encoding="utf-8")
            break
        except Exception as e:
            print(f"  Failed: {e}")
            if attempt < 3:
                time.sleep(2 * attempt)
    if df is None:
        print("::error::All download attempts failed")
        sys.exit(1)

    print(f"  {len(df):,} raw rows, {len(df.columns)} columns")

    # Strip whitespace from column names
    df.columns = df.columns.str.strip()

    # Rename columns
    actual_rename = {c: v for c, v in RENAME.items() if c in df.columns}
    df = df.rename(columns=actual_rename)

    # Also snake_case any remaining columns not yet renamed
    df.columns = (
        df.columns
        .str.strip()
        .str.replace(r"[() /]+", "_", regex=True)
        .str.replace(r"_+", "_", regex=True)
        .str.strip("_")
        .str.lower()
    )

    # Compute depth/diameter ratio if not present but components exist
    if "depth_diameter_ratio" not in df.columns and "depth_km" in df.columns and "diameter_km" in df.columns:
        df["depth_diameter_ratio"] = (df["depth_km"] / df["diameter_km"]).round(4)

    # Derived column: size class
    df["size_class"] = df["diameter_km"].apply(size_class)

    # Drop VizieR/source internal columns not in COLUMN_DESCRIPTIONS
    for col in ["recno"]:
        if col in df.columns:
            df = df.drop(columns=[col])

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    df = df.sort_values("latitude_deg").reset_index(drop=True)

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
- **{n_total:,}** total craters on Ceres
- Size distribution: {n_small:,} small, {n_medium:,} medium, {n_large:,} large, {n_giant:,} giant
- Diameter range: {diam_min:.2f} -- {diam_max:.1f} km
- **{has_depth:,}** craters with depth measurements"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/ceres-craters-dawn", split="train")
df = ds.to_pandas()

# Size distribution histogram
import matplotlib.pyplot as plt
df["diameter_km"].hist(bins=100, log=True)
plt.xlabel("Diameter (km)")
plt.ylabel("Count")
plt.title("Ceres Crater Size Distribution")
plt.show()

# Map of craters
plt.scatter(df["longitude_deg"], df["latitude_deg"],
            s=df["diameter_km"] / 5, alpha=0.3)
plt.xlabel("Longitude (deg)")
plt.ylabel("Latitude (deg)")
plt.title("Ceres Impact Craters (Dawn FC2)")
plt.show()

# Large craters (>50 km)
large = df[df["diameter_km"] > 50].sort_values("diameter_km", ascending=False)
print(f"Craters >50 km: {len(large)}")
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Ceres Crater Database (Zeilnhofer 2020, Dawn FC2)",
        description=DESCRIPTION,
        tags=["space", "ceres", "dawn", "craters", "planetary-science",
              "usgs", "asteroid", "nasa", "open-data", "tabular-data", "parquet"],
        source_url="https://astropedia.astrogeology.usgs.gov/download/Ceres/Dawn/Craters/",
        task_categories=["tabular-classification", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/planetary-science-datasets-69c2d4683bd6a66c34fb4af2",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA12031/PIA12031~small.jpg",
            "alt": "Dawn spacecraft orbiting Ceres (artist concept)",
            "credit": "NASA/JPL-Caltech",
        },
        related_datasets=[
            "juliensimon/impact-craters",
            "juliensimon/lunar-craters-robbins",
            "juliensimon/planetary-nomenclature",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "latitude_deg", "longitude_deg", "diameter_km", "depth_km",
                "depth_diameter_ratio",
            ],
        )
        p.publish(
            df,
            filename="ceres_craters.parquet",
            min_rows=40_000,
            expected_columns=["latitude_deg", "longitude_deg", "diameter_km"],
            critical_columns=["latitude_deg", "longitude_deg", "diameter_km"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Ceres craters: {n_total:,} records",
        )
    print("Done.")


if __name__ == "__main__":
    main()
