#!/usr/bin/env python3
"""Fetch Ceres crater database (Zeilnhofer 2020) and upload to HF.

Source: Zeilnhofer & Barlow (2021), Icarus, from Dawn Framing Camera 2 images.
Distributed by USGS Astrogeology Science Center via Astropedia.
"""

import io
import sys
import time
import zipfile

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

DATA_URL = "https://astrogeology.usgs.gov/ckan/dataset/6c684fc5-91e2-4381-9d72-15dd5e02cdcf/resource/9ffe7225-0d7c-42db-ac3b-bb2a2320d67b/download/ceres_dawn_fc2_craterdatabase_zeilnhofer_2020_v2.zip"
HF_REPO = "juliensimon/ceres-craters-dawn"

# ── Column mapping ───────────────────────────────────────────────────
# The source CSV's first two headers are swapped relative to their contents:
# the column labelled "Latitude" holds longitude (0-360) and "Longitude" holds
# latitude (-84.66 to +89.62). Confirmed two ways: the published coverage is
# 84.66S-89.62N, and the documented Crater_ID rule ("first four digits of the
# longitude, first three of the latitude, separated by the latitude sign")
# pairs ID 1039-846 with Latitude=103.93, Longitude=-84.66.
RENAME = {
    "Latitude": "longitude_deg",
    "Longitude": "latitude_deg",
    "Crater_ID": "crater_id",
    "Dc_km": "diameter_km",
    "Minor_Dc_km": "minor_diameter_km",
    "Pres": "preservation_state",
    "Ejecta": "ejecta_morphology",
    "Int_1": "interior_morphology_1",
    "Int_2": "interior_morphology_2",
    "Dpk_km": "central_peak_diameter_km",
    "Dpk_Dc": "peak_crater_diameter_ratio",
    "Dp_km": "central_pit_diameter_km",
    "Dp_Dc": "pit_crater_diameter_ratio",
    "rim_km_Mean_Sphere": "rim_height_km_mean_sphere",
    "d_km_Mean_Sphere": "depth_km_mean_sphere",
    "rim_km_Oblate_Sphere": "rim_height_km_oblate_sphere",
    "d_km_Oblate_Sphere": "depth_km_oblate_sphere",
}

# ── Column descriptions for README schema table ─────────────────────
# Wording follows the column-definition document shipped inside the source zip.
COLUMN_DESCRIPTIONS = {
    "crater_id": "Crater identifier built from its centre coordinates: the first four digits of the longitude and the first three of the latitude, separated by the latitude sign (e.g. '1039-846' is 103.93E, 84.66S)",
    "latitude_deg": "Crater centre latitude in degrees, positive north, measured in JMARS; coverage runs 84.66S to 89.62N",
    "longitude_deg": "Crater centre east longitude in degrees (0-360), measured in JMARS",
    "diameter_km": "Crater (major) diameter in km, measured in JMARS to the nearest tenth of a km; range 1.0-282.0 km",
    "minor_diameter_km": "Minor-axis diameter in km, reported only where it differs from the major diameter by at least 0.1 km; 0.0 means the crater is effectively circular, not that the value is missing",
    "preservation_state": "Preservation on a 0-5 scale: 1 highly degraded to the point of erasure, 2 highly degraded, 3 moderate, 4 slight, 5 fresh; 0 would be a 'ghost' crater but none are reported",
    "ejecta_morphology": "Ejecta morphology from Low Altitude Mapping Orbit images: 'CE' for a continuous ejecta blanket, 'No' where none is visible",
    "interior_morphology_1": "Most prominent interior morphology: BA/DA bright or dark albedo feature, EB external ejecta blanket deposit, Pk central peak, SP summit pit, SY floor pit, FD floor deposit, WT wall terrace; 'No' where none is present",
    "interior_morphology_2": "Second most prominent interior morphology, same coding as interior_morphology_1",
    "central_peak_diameter_km": "Basal diameter of the central peak in km, averaged over three measurements; applies to craters with a central peak (Pk) or summit pit (SP); 0.0 where not applicable",
    "peak_crater_diameter_ratio": "Central peak basal diameter divided by crater diameter; 0.0 where no peak was measured",
    "central_pit_diameter_km": "Diameter of the central pit in km, averaged over three measurements; applies to floor pits (SY) and summit pits (SP); 0.0 where not applicable",
    "pit_crater_diameter_ratio": "Central pit diameter divided by crater diameter; 0.0 where no pit was measured",
    "rim_height_km_mean_sphere": "Crater rim height in km under the Mean Spheroid model of Ceres topography, averaged over three profiles taken out to about two crater radii",
    "depth_km_mean_sphere": "Crater depth in km under the Mean Spheroid model, averaged over three profiles taken out to about two crater radii",
    "rim_height_km_oblate_sphere": "Crater rim height in km under the Oblate Spheroid model, same three-profile method",
    "depth_km_oblate_sphere": "Crater depth in km under the Oblate Spheroid model, same three-profile method",
    "depth_diameter_ratio": "depth_km_mean_sphere divided by diameter_km; derived, not in the source file. Fresh craters sit near 0.15-0.20 and the ratio falls as craters degrade or relax viscously",
    "size_class": "Derived size category: small (<5 km), medium (5-20 km), large (20-100 km), giant (>100 km)",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
The most comprehensive catalog of impact craters on dwarf planet Ceres, containing \
craters with diameter >= 1 km identified from Dawn Framing Camera (FC2) imagery.

This database was compiled by M. F. Zeilnhofer and N. G. Barlow (2021) using images from NASA's Dawn \
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
    if "depth_km_mean_sphere" in df.columns and "diameter_km" in df.columns:
        df["depth_diameter_ratio"] = (
            df["depth_km_mean_sphere"] / df["diameter_km"]
        ).round(4)

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
    has_depth = int((df["depth_km_mean_sphere"] > 0).sum()) if "depth_km_mean_sphere" in df.columns else 0

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
        source_url="https://astrogeology.usgs.gov/search/map/ceres_dawn_zeilnhofer_crater_database_2020",
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
                "latitude_deg", "longitude_deg", "diameter_km",
                "minor_diameter_km", "central_peak_diameter_km",
                "peak_crater_diameter_ratio", "central_pit_diameter_km",
                "pit_crater_diameter_ratio", "rim_height_km_mean_sphere",
                "depth_km_mean_sphere", "rim_height_km_oblate_sphere",
                "depth_km_oblate_sphere", "depth_diameter_ratio",
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
