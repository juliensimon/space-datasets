#!/usr/bin/env python3
"""Fetch Mercury crater degradation catalog (Kinczyk et al. 2020) and upload to HF."""

import io

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

MENDELEY_URL = "https://data.mendeley.com/public-files/datasets/35nvbpfggx/files/a9751d05-4ceb-4548-b545-7ba0a98f0c8f/file_downloaded"
HF_REPO = "juliensimon/mercury-crater-degradation"

# Degradation class descriptions (from Kinczyk et al. 2020)
DEGRADATION_CLASSES = {
    0: "unclassified",
    1: "freshest (sharp rim, prominent ejecta)",
    2: "fresh (well-defined rim, partial ejecta)",
    3: "moderately degraded (subdued rim, no ejecta)",
    4: "degraded (heavily subdued rim)",
    5: "highly degraded (barely distinguishable rim)",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "crater_id": "Unique crater feature identifier (FID) from the Kinczyk et al. (2020) catalog; integer index for each classified crater",
    "longitude_deg": "Crater center longitude in degrees East; referenced to Mercury's IAU coordinate system from MESSENGER global basemap",
    "latitude_deg": "Crater center latitude in degrees North (-90 to +90); derived from MESSENGER MDIS imagery",
    "diameter_km": "Crater rim-to-rim diameter in kilometers; all craters in this catalog have D >= 40 km, the threshold for reliable degradation classification",
    "degradation_class": "Morphological degradation state on 1-5 scale: 1=freshest (Kuiperian), 2=fresh (Mansurian), 3=moderately degraded, 4=degraded, 5=highly degraded (pre-Tolstojan); correlates with relative crater age",
    "degradation_label": "Human-readable description of the degradation class (e.g. 'freshest (sharp rim, prominent ejecta)'); derived from degradation_class",
    "size_class": "Derived size classification: small (<50 km), medium (50-100 km), large (100-300 km), giant (>300 km); thresholds chosen for Mercury's gravity regime",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
A global catalog of Mercury impact craters (diameter >= 40 km) classified by morphological \
degradation state using MESSENGER imagery. Each crater is assigned a degradation class from \
1 (freshest) to 5 (highly degraded), providing a relative chronology of Mercury's surface.

Crater degradation is the primary tool for determining the relative ages of planetary surfaces \
where radiometric dating is unavailable. On Mercury, impact craters undergo progressive \
modification through subsequent impacts, seismic shaking, volcanic infilling, and regolith \
gardening. Fresh craters display sharp rims, prominent ejecta blankets, and well-defined \
interior structures, while highly degraded craters are barely distinguishable from the \
surrounding terrain.

Kinczyk et al. (2020) developed a 5-point degradation classification scheme calibrated across \
Mercury's entire surface using MESSENGER's global imaging coverage. The classification \
correlates with established stratigraphic systems (Kuiperian, Mansurian, Calorian periods).
"""


def size_class(d):
    if pd.isna(d):
        return None
    if d < 50:
        return "small"
    if d <= 100:
        return "medium"
    if d <= 300:
        return "large"
    return "giant"


def main():
    print("Fetching Mercury crater degradation catalog (Kinczyk et al. 2020)...")
    resp = requests.get(MENDELEY_URL, timeout=60, headers={"User-Agent": "space-datasets/1.0"})
    resp.raise_for_status()

    df = pd.read_csv(io.StringIO(resp.text), sep="\t")
    print(f"  {len(df):,} raw rows, {len(df.columns)} columns: {list(df.columns)}")

    # Rename columns to snake_case
    rename = {
        "FID": "crater_id",
        "x_coord": "longitude_deg",
        "y_coord": "latitude_deg",
        "Diameter_km": "diameter_km",
        "Class": "degradation_class",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

    # Derived columns
    df["degradation_label"] = df["degradation_class"].map(DEGRADATION_CLASSES)
    df["size_class"] = df["diameter_km"].apply(size_class)

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Stats
    n_total = len(df)
    diam_min = df["diameter_km"].min()
    diam_max = df["diameter_km"].max()
    diam_median = df["diameter_km"].median()
    class_counts = df["degradation_class"].value_counts().sort_index().to_dict()

    class_lines = "\n".join(
        f"| {cls} | {DEGRADATION_CLASSES.get(cls, 'unknown')} | {count:,} |"
        for cls, count in sorted(class_counts.items())
    )

    quick_stats = f"""\
- **{n_total:,}** craters with degradation classification
- Diameter range: {diam_min:.0f} -- {diam_max:.0f} km (median {diam_median:.0f} km)
- All craters D >= 40 km on Mercury's surface

## Degradation classes

| Class | Description | Count |
|:-----:|-------------|------:|
{class_lines}"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/mercury-crater-degradation", split="train")
df = ds.to_pandas()

# Degradation class distribution
import matplotlib.pyplot as plt
df["degradation_class"].value_counts().sort_index().plot(kind="bar")
plt.xlabel("Degradation Class")
plt.ylabel("Count")
plt.title("Mercury Crater Degradation Distribution")
plt.show()

# Size vs degradation
df.boxplot(column="diameter_km", by="degradation_class")
plt.ylabel("Diameter (km)")
plt.title("Crater Size by Degradation Class")
plt.show()

# Map colored by degradation
plt.scatter(df["longitude_deg"], df["latitude_deg"],
            c=df["degradation_class"], cmap="RdYlGn_r",
            s=df["diameter_km"] / 20, alpha=0.6)
plt.colorbar(label="Degradation Class")
plt.xlabel("Longitude (deg E)")
plt.ylabel("Latitude (deg N)")
plt.title("Mercury Craters by Degradation State")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Mercury Crater Degradation (Kinczyk et al. 2020)",
        description=DESCRIPTION,
        tags=["space", "mercury", "crater", "degradation",
              "planetary-science", "messenger",
              "open-data", "tabular-data", "parquet"],
        source_url="https://doi.org/10.1016/j.icarus.2020.113637",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/planetary-science-datasets-69c2d4683bd6a66c34fb4af2",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA11245/PIA11245~small.jpg",
            "alt": "Mercury as seen by the MESSENGER spacecraft",
            "credit": "NASA/Johns Hopkins APL/Carnegie Institution of Washington",
        },
        related_datasets=[
            "juliensimon/mercury-craters-herrick",
            "juliensimon/mars-craters-robbins",
            "juliensimon/lunar-craters-robbins",
            "juliensimon/planetary-nomenclature",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=["longitude_deg", "latitude_deg", "diameter_km"],
            integer=["crater_id", "degradation_class"],
        )
        p.publish(
            df,
            filename="mercury_crater_degradation.parquet",
            min_rows=1_000,
            expected_columns=["crater_id", "latitude_deg", "longitude_deg", "diameter_km", "degradation_class"],
            critical_columns=["latitude_deg", "longitude_deg", "diameter_km", "degradation_class"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Mercury crater degradation: {n_total:,} records",
        )
    print("Done.")


if __name__ == "__main__":
    main()
