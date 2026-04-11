#!/usr/bin/env python3
"""Fetch Mercury crater database (Herrick et al. 2011) and upload to HF."""

import io

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

CSV_URL = "https://drive.google.com/uc?export=download&id=1e5UwToruFpV3UJ9Hnt_1ANrzcpWk3UxQ"
HF_REPO = "juliensimon/mercury-craters-herrick"

RENAME = {
    "id": "crater_id",
    "lat_n": "latitude_deg",
    "lon_e_0": "longitude_deg",
    "diameter": "diameter_km",
    "int_shp": "interior_shape",
    "rim_shp": "rim_shape",
    "cent_struc": "central_structure",
    "rayed": "rayed",
    "name": "name",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "crater_id": "Unique integer crater identifier from the Herrick et al. (2011) catalog",
    "latitude_deg": "Crater center latitude in degrees North (-90 to +90); derived from MESSENGER and Mariner 10 imagery",
    "longitude_deg": "Crater center longitude in degrees East (-180 to +180); referenced to Mercury's IAU coordinate system",
    "diameter_km": "Crater rim-to-rim diameter in kilometers; measured from ortho-projected imagery; ranges from ~5 km to >1000 km for multi-ring basins",
    "interior_shape": "Interior morphology code: b=bowl-shaped (simple craters), sh=shallow, ff=flat-floored (volcanic infill or melt sheet), x=indeterminate",
    "rim_shape": "Rim morphology code: c=circular, sc=subcircular, t=polygonal/terraced (complex craters with wall failure), x=indeterminate",
    "central_structure": "Central structure code: n=none, cp=central peak, mp=multiple peaks, pi=central pit, pr=peak ring, mr=multiple rings, x=indeterminate; structure type transitions with crater size",
    "rayed": "Rayed crater flag (y/n); rays indicate relatively young impacts (Kuiperian period) where ejecta has not yet been space-weathered",
    "name": "IAU-assigned crater name (e.g. 'Caloris', 'Degas', 'Kuiper'); null for unnamed craters; only ~400 of ~17,000 craters are named",
    "size_class": "Derived size classification: small (<10 km, simple craters), medium (10-50 km, complex craters), large (50-200 km, peak-ring basins), giant (>200 km, multi-ring basins)",
    "has_central_structure": "Derived boolean: True if central_structure is not 'none' or 'indeterminate'; flags craters with peaks, pits, or rings diagnostic of complex crater formation",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
The global Mercury impact crater database containing craters identified from Mariner 10 \
and MESSENGER flyby imagery. This catalog provides the most complete inventory of Mercury's \
cratered surface, with morphological classifications for interior shape, rim geometry, and \
central structures.

Mercury's heavily cratered surface records ~4 billion years of bombardment history in the \
inner solar system. Unlike the Moon, Mercury lacks large-scale volcanic resurfacing (outside \
the northern plains), making its crater record one of the most complete in the solar system. \
The transition from simple to complex craters occurs at ~10 km on Mercury — smaller than \
Mars (~6-8 km) but larger than the Moon (~15 km) — reflecting Mercury's higher surface gravity.

This dataset completes the crater quad alongside Lunar Craters, Mars Craters, and Ceres \
Craters, enabling cross-body crater population studies across the inner solar system.
"""


def size_class(diameter):
    if pd.isna(diameter):
        return None
    if diameter < 10:
        return "small"
    if diameter <= 50:
        return "medium"
    if diameter <= 200:
        return "large"
    return "giant"


def main():
    print("Fetching Mercury crater database (Herrick et al. 2011)...")
    resp = requests.get(CSV_URL, timeout=120, headers={"User-Agent": "space-datasets/1.0"})
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    print(f"  {len(df):,} raw rows, {len(df.columns)} columns")

    # Rename columns
    df = df.rename(columns={c: v for c, v in RENAME.items() if c in df.columns})

    # Clean string columns
    for col in ["interior_shape", "rim_shape", "central_structure", "rayed", "name"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
            df[col] = df[col].replace({"nan": None, "": None})

    # Derived columns
    df["size_class"] = df["diameter_km"].apply(size_class)
    df["has_central_structure"] = df["central_structure"].apply(
        lambda x: x not in (None, "n", "x") if pd.notna(x) else None
    )

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Stats
    n_total = len(df)
    n_named = int(df["name"].notna().sum())
    diam_min = df["diameter_km"].min()
    diam_max = df["diameter_km"].max()
    diam_median = df["diameter_km"].median()
    n_small = int((df["size_class"] == "small").sum())
    n_medium = int((df["size_class"] == "medium").sum())
    n_large = int((df["size_class"] == "large").sum())
    n_giant = int((df["size_class"] == "giant").sum())
    n_rayed = int((df["rayed"] == "y").sum())
    n_central = int(df["has_central_structure"].fillna(False).sum())

    quick_stats = f"""\
- **{n_total:,}** total craters
- **{n_named}** named (IAU designated)
- **{n_rayed}** rayed craters
- **{n_central}** with central structures (peaks, pits, or rings)
- Size distribution: {n_small:,} small, {n_medium:,} medium, {n_large:,} large, {n_giant:,} giant
- Diameter range: {diam_min:.1f} -- {diam_max:.1f} km (median {diam_median:.1f} km)"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/mercury-craters-herrick", split="train")
df = ds.to_pandas()

# Size-frequency distribution
import matplotlib.pyplot as plt
df["diameter_km"].hist(bins=100, log=True)
plt.xlabel("Diameter (km)")
plt.ylabel("Count")
plt.title("Mercury Crater Size-Frequency Distribution")
plt.show()

# Map of named craters
named = df[df["name"].notna()]
plt.scatter(named["longitude_deg"], named["latitude_deg"],
            s=named["diameter_km"] / 10, alpha=0.6)
for _, row in named.head(15).iterrows():
    plt.annotate(row["name"], (row["longitude_deg"], row["latitude_deg"]),
                 fontsize=6, alpha=0.7)
plt.xlabel("Longitude (deg E)")
plt.ylabel("Latitude (deg N)")
plt.title("Named Mercury Craters")
plt.show()

# Morphology breakdown
print(df["central_structure"].value_counts())
print(f"Rayed craters: {len(df[df['rayed'] == 'y'])}")
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Mercury Crater Database (Herrick et al. 2011)",
        description=DESCRIPTION,
        tags=["space", "mercury", "crater", "planetary-science",
              "messenger", "open-data", "tabular-data", "parquet"],
        source_url="https://doi.org/10.1016/j.icarus.2011.06.021",
        task_categories=["tabular-classification", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/planetary-science-datasets-69c2d4683bd6a66c34fb4af2",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA11245/PIA11245~small.jpg",
            "alt": "Mercury as seen by the MESSENGER spacecraft",
            "credit": "NASA/Johns Hopkins APL/Carnegie Institution of Washington",
        },
        related_datasets=[
            "juliensimon/lunar-craters-robbins",
            "juliensimon/mars-craters-robbins",
            "juliensimon/ceres-craters-dawn",
            "juliensimon/planetary-nomenclature",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=["latitude_deg", "longitude_deg", "diameter_km"],
            integer=["crater_id"],
        )
        p.publish(
            df,
            filename="mercury_craters.parquet",
            min_rows=10_000,
            expected_columns=["crater_id", "latitude_deg", "longitude_deg", "diameter_km"],
            critical_columns=["crater_id", "latitude_deg", "longitude_deg", "diameter_km"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Mercury craters: {n_total:,} records",
        )
    print("Done.")


if __name__ == "__main__":
    main()
