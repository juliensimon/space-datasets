#!/usr/bin/env python3
"""Fetch IAU planetary nomenclature shapefiles and upload to HF.

Source: USGS Astrogeology Science Center -- Planetary Nomenclature database.
Requires: pip install pandas pyarrow requests dbfread huggingface_hub[hf_xet]
"""

import io
import tempfile
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

S3_BASE = "https://asc-planetarynames-data.s3.us-west-2.amazonaws.com"
BODIES = {
    "MOON": f"{S3_BASE}/MOON_nomenclature_center_pts.zip",
    "MARS": f"{S3_BASE}/MARS_nomenclature_center_pts.zip",
    "VENUS": f"{S3_BASE}/VENUS_nomenclature_center_pts.zip",
    "MERCURY": f"{S3_BASE}/MERCURY_nomenclature_center_pts.zip",
}
HF_REPO = "juliensimon/planetary-nomenclature"

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "name": "Official IAU-approved surface feature name; unique within a body+type combination but the same name may appear on different bodies",
    "clean_name": "Name with diacritics and special characters removed or normalized for indexing and search",
    "body": "Planetary body the feature resides on: MOON, MARS, VENUS, or MERCURY",
    "approvaldt": "Date the IAU officially approved the feature name; null for very old features with uncertain approval records",
    "origin": "Cultural, mythological, or historical source of the name (e.g., 'Norse goddess of the sea', 'village in Nigeria'); key for understanding the naming theme applied to each body",
    "diameter": "Feature diameter or longest dimension in km; null for linear features (rima, rupes, linea) and broad regions where a single diameter is not meaningful",
    "center_lon": "Center longitude in decimal degrees using IAU-standard planetocentric coordinates; longitude system varies by body",
    "center_lat": "Center latitude in decimal degrees (planetocentric); positive north, negative south; ranges from -90 to +90",
    "type": "Full English name of the feature type (e.g., Crater, Mons, Planitia, Vallis, Rupes, Fossa, Patera)",
    "code": "Two-letter IAU feature type code: AA=Albedo, CA=Catena, CR=Corona, DO=Dorsum, FO=Fossa, LI=Linea, ME=Mensa, MO=Mons, PA=Patera, PL=Planitia, PM=Planum, RE=Regio, RI=Rima, RU=Rupes, TA=Terra, TH=Tholus, VA=Vallis, VS=Vastitas",
    "approval": "IAU approval status: 'Approved' (in official gazetteer), 'Dropped' (retired), or 'Provisional' (pending full approval)",
    "min_lon": "Minimum (western) longitude of the feature bounding box in decimal degrees",
    "max_lon": "Maximum (eastern) longitude of the feature bounding box in decimal degrees",
    "min_lat": "Minimum (southern) latitude of the feature bounding box in decimal degrees",
    "max_lat": "Maximum (northern) latitude of the feature bounding box in decimal degrees",
    "ethnicity": "Cultural/ethnic group associated with the name origin (e.g., 'Norse', 'African', 'Greek'); useful for diversity analysis of naming conventions",
    "continent": "Continent of origin for the cultural source of the name; null when origin is mythological or not geographically tied",
    "quad_name": "USGS planetary quadrangle name covering the feature location; used for cartographic referencing",
    "quad_code": "USGS quadrangle alphanumeric code (e.g., 'MC-01' for Mercury); null if quadrangle mapping is not available",
    "link": "Direct URL to the feature's entry in the USGS Planetary Nomenclature online gazetteer",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
IAU-approved named features on Moon, Mars, Venus, and Mercury -- craters, mountains, \
plains, and more from the USGS Planetary Nomenclature database.

This dataset contains every IAU-approved named surface feature (crater, mons, planitia, \
vallis, etc.) on the Moon, Mars, Venus, and Mercury. The data comes from the USGS \
Astrogeology Science Center's Planetary Nomenclature database, which maintains the \
official IAU gazetteer of planetary feature names.

The naming of planetary surface features is governed by the International Astronomical \
Union (IAU), which established the Working Group for Planetary System Nomenclature in 1973. \
Each planetary body follows a distinct naming theme: lunar craters honor deceased scientists \
and scholars, Martian craters larger than 60 km are named for deceased scientists and writers, \
Venusian features are named exclusively for women and female mythological figures, and \
Mercurian craters honor deceased artists, musicians, and authors.

Feature types span a rich taxonomy of geological landforms. Craters dominate most bodies, but \
the catalog also includes montes (mountains), planitiae (low-lying plains), valles (valleys), \
rupes (scarps), fossae (long narrow depressions), and many other morphological categories.

The approval dates trace the history of planetary exploration itself, from features visible \
through ground-based telescopes to waves of new approvals tracking Mariner, Viking, Magellan, \
MESSENGER, and modern orbiters.
"""


def fetch_body(body_name, url):
    """Download shapefile zip and extract DBF records."""
    from dbfread import DBF

    print(f"  Fetching {body_name}...")
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        dbf_files = [n for n in zf.namelist() if n.lower().endswith(".dbf")]
        if not dbf_files:
            raise RuntimeError(f"No .dbf file found in {body_name} zip")
        dbf_name = dbf_files[0]
        with tempfile.NamedTemporaryFile(suffix=".dbf", delete=False) as tmp:
            tmp.write(zf.read(dbf_name))
            tmp_path = tmp.name

    try:
        records = list(DBF(tmp_path, encoding="utf-8"))
        df = pd.DataFrame(records)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    # Normalize column names to lowercase
    df.columns = df.columns.str.lower().str.strip()

    # Add body column
    df["body"] = body_name

    print(f"    {len(df):,} features")
    return df


def main():
    print("Fetching IAU planetary nomenclature from USGS S3...")

    frames = []
    for body_name, url in BODIES.items():
        df = fetch_body(body_name, url)
        frames.append(df)
        time.sleep(1)

    df = pd.concat(frames, ignore_index=True)
    print(f"  {len(df):,} total features across {len(BODIES)} bodies")

    # Keep only expected columns
    expected_cols = list(COLUMN_DESCRIPTIONS.keys())
    available = [c for c in expected_cols if c in df.columns]
    df = df[available]

    # Type coercion: date column
    if "approvaldt" in df.columns:
        df["approvaldt"] = pd.to_datetime(df["approvaldt"], errors="coerce")

    # Sort by body then name
    df = df.sort_values(["body", "name"], ignore_index=True)

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    body_counts = df["body"].value_counts().to_dict()
    n_types = df["type"].nunique() if "type" in df.columns else 0
    n_with_diameter = int(df["diameter"].notna().sum()) if "diameter" in df.columns else 0
    year_min = int(df["approvaldt"].dt.year.min()) if df["approvaldt"].notna().any() else 0
    year_max = int(df["approvaldt"].dt.year.max()) if df["approvaldt"].notna().any() else 0
    top_types = df["type"].value_counts().head(5) if "type" in df.columns else pd.Series(dtype=int)
    top_types_str = ", ".join(f"{t} ({c:,})" for t, c in top_types.items())

    body_stats = "\n".join(
        f"- **{body}**: {body_counts.get(body, 0):,} features"
        for body in BODIES
    )

    quick_stats = f"""\
- **{n_total:,}** named features across {len(BODIES)} bodies
{body_stats}
- **{n_types}** distinct feature types
- **{n_with_diameter:,}** features with known diameter
- Top types: {top_types_str}
- Approval dates: {year_min}--{year_max}"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/planetary-nomenclature", split="train")
df = ds.to_pandas()

# All lunar craters
lunar_craters = df[(df["body"] == "MOON") & (df["type"] == "Crater")]
print(f"Lunar craters: {len(lunar_craters):,}")

# Features by body and type
import matplotlib.pyplot as plt
by_body = df["body"].value_counts()
by_body.plot.bar()
plt.title("Named Features per Body")
plt.ylabel("Count")
plt.show()

# Largest features by diameter
biggest = df.sort_values("diameter", ascending=False).head(20)
print(biggest[["name", "body", "type", "diameter"]])

# Recently approved features
recent = df.sort_values("approvaldt", ascending=False).head(20)
print(recent[["name", "body", "type", "approvaldt"]])
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="IAU Planetary Nomenclature",
        description=DESCRIPTION,
        tags=["space", "planetary-science", "nomenclature", "iau", "moon",
              "mars", "venus", "mercury", "usgs", "open-data", "tabular-data", "parquet"],
        source_url="https://planetarynames.wr.usgs.gov/",
        task_categories=["tabular-classification", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/planetary-science-datasets-69c2d4683bd6a66c34fb4af2",
        banner={
            "url": "https://images-assets.nasa.gov/image/as08-14-2506/as08-14-2506~small.jpg",
            "alt": "The Moon seen from Apollo 8, showing craters and surface detail",
            "credit": "NASA/Apollo 8",
        },
        related_datasets=[
            "juliensimon/lunar-craters-robbins",
            "juliensimon/impact-craters",
            "juliensimon/solar-system-moons",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "diameter", "center_lon", "center_lat",
                "min_lon", "max_lon", "min_lat", "max_lat",
            ],
        )
        p.publish(
            df,
            filename="planetary_nomenclature.parquet",
            min_rows=10_000,
            expected_columns=["name", "clean_name", "body", "diameter",
                              "center_lon", "center_lat", "type", "approvaldt"],
            critical_columns=["name", "body", "center_lon", "center_lat"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update planetary nomenclature: {n_total:,} features",
        )
    print("Done.")


if __name__ == "__main__":
    main()
