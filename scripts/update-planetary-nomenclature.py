#!/usr/bin/env python3
"""Fetch IAU planetary nomenclature shapefiles and upload to HF.

Requires: pip install pandas pyarrow requests dbfread huggingface_hub[hf_xet]
"""

import io
import os
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests

from dataset_images import banner_markdown, download_banner
from validate import check_dataset

S3_BASE = "https://asc-planetarynames-data.s3.us-west-2.amazonaws.com"
BODIES = {
    "MOON": f"{S3_BASE}/MOON_nomenclature_center_pts.zip",
    "MARS": f"{S3_BASE}/MARS_nomenclature_center_pts.zip",
    "VENUS": f"{S3_BASE}/VENUS_nomenclature_center_pts.zip",
    "MERCURY": f"{S3_BASE}/MERCURY_nomenclature_center_pts.zip",
}
HF_REPO = "juliensimon/planetary-nomenclature"

# Map DBF field names to snake_case
COLUMN_MAP = {
    "name": "name",
    "clean_name": "clean_name",
    "approvaldt": "approvaldt",
    "origin": "origin",
    "diameter": "diameter",
    "center_lon": "center_lon",
    "center_lat": "center_lat",
    "type": "type",
    "code": "code",
    "approval": "approval",
    "min_lon": "min_lon",
    "max_lon": "max_lon",
    "min_lat": "min_lat",
    "max_lat": "max_lat",
    "ethnicity": "ethnicity",
    "continent": "continent",
    "quad_name": "quad_name",
    "quad_code": "quad_code",
    "link": "link",
}


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
        # Extract to temp file for dbfread (needs file path)
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

    # Keep only expected columns (some DBFs may have extras)
    expected_cols = list(COLUMN_MAP.values()) + ["body"]
    available = [c for c in expected_cols if c in df.columns]
    df = df[available]

    # Type coercion: numeric columns
    for col in ["diameter", "center_lon", "center_lat",
                 "min_lon", "max_lon", "min_lat", "max_lat"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Type coercion: date column
    if "approvaldt" in df.columns:
        df["approvaldt"] = pd.to_datetime(df["approvaldt"], errors="coerce")

    # Sort by body then name
    df = df.sort_values(["body", "name"], ignore_index=True)

    # Validate
    check_dataset(
        df,
        dataset_name="planetary-nomenclature",
        min_rows=10_000,
        expected_columns=["name", "clean_name", "body", "diameter",
                          "center_lon", "center_lat", "type", "approvaldt"],
        critical_columns=["name", "body", "center_lon", "center_lat"],
    )

    # Stats for README
    body_counts = df["body"].value_counts().to_dict()
    n_types = df["type"].nunique() if "type" in df.columns else 0
    n_with_diameter = int(df["diameter"].notna().sum()) if "diameter" in df.columns else 0
    year_min = int(df["approvaldt"].dt.year.min()) if df["approvaldt"].notna().any() else 0
    year_max = int(df["approvaldt"].dt.year.max()) if df["approvaldt"].notna().any() else 0
    top_types = df["type"].value_counts().head(5) if "type" in df.columns else pd.Series(dtype=int)
    top_types_str = ", ".join(f"{t} ({c:,})" for t, c in top_types.items())

    # Size category
    if len(df) < 1000:
        size_cat = "n<1K"
    elif len(df) < 10_000:
        size_cat = "1K<n<10K"
    elif len(df) < 100_000:
        size_cat = "10K<n<100K"
    else:
        size_cat = "100K<n<1M"

    body_stats = "\n".join(
        f"- **{body}**: {body_counts.get(body, 0):,} features"
        for body in BODIES
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "planetary_nomenclature.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        banner_file = download_banner("planetary-nomenclature", tmp)
        banner_md = banner_markdown("planetary-nomenclature", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "IAU Planetary Nomenclature"
language:
  - en
description: "IAU-approved named features on Moon, Mars, Venus, and Mercury — craters, mountains, plains, and more from the USGS Planetary Nomenclature database."
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - planetary-science
  - nomenclature
  - iau
  - moon
  - mars
  - venus
  - mercury
  - usgs
  - open-data
  - tabular-data
  - parquet
size_categories:
  - {size_cat}
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/planetary_nomenclature.parquet
    default: true
---

# IAU Planetary Nomenclature
{banner_md}
*Part of the [Planetary Science Datasets](https://huggingface.co/collections/juliensimon/planetary-science-datasets-69c2d4683bd6a66c34fb4af2) collection on Hugging Face.*

IAU-approved named features on Moon, Mars, Venus, and Mercury -- **{len(df):,}** features
across {len(BODIES)} planetary bodies, including craters, mountains, plains, and more
from the USGS Planetary Nomenclature database. Approval dates span **{year_min}** to **{year_max}**.

## Dataset description

This dataset contains every IAU-approved named surface feature (crater, mons, planitia,
vallis, etc.) on the Moon, Mars, Venus, and Mercury. The data comes from the USGS
Astrogeology Science Center's Planetary Nomenclature database, which maintains the
official IAU gazetteer of planetary feature names.

Each record includes the feature name, geographic coordinates (center point and bounding
box), diameter, feature type, approval status, and cultural origin/ethnicity metadata.

The naming of planetary surface features is governed by the International Astronomical Union (IAU), which established the Working Group for Planetary System Nomenclature in 1973 to bring consistency to the rapidly growing catalog of features revealed by spacecraft exploration. Each planetary body follows a distinct naming theme: lunar craters honor deceased scientists and scholars, Martian craters larger than 60 km are named for deceased scientists and writers while smaller ones take the names of villages on Earth, Venusian features are named exclusively for women and female mythological figures, and Mercurian craters honor deceased artists, musicians, and authors. These conventions reflect both scientific tradition and a deliberate effort to represent diverse cultures in the planetary record.

Feature types in the nomenclature span a rich taxonomy of geological landforms. Craters (impact structures) dominate most bodies, but the catalog also includes montes (mountains), planitiae (low-lying plains), valles (valleys), rupes (scarps), fossae (long narrow depressions), and many other morphological categories. Each feature type carries information about the geological processes that shaped a world — volcanic resurfacing, tectonic deformation, fluvial erosion, or impact bombardment. The spatial distribution and size statistics of named features provide a curated view of planetary geology that complements the raw crater databases.

The approval dates in this dataset trace the history of planetary exploration itself. Early entries correspond to features visible through ground-based telescopes, while waves of new approvals track the arrival of data from Mariner, Viking, Magellan, MESSENGER, and modern orbiters. The nomenclature database is a living record, with new features still being named as high-resolution imaging reveals previously uncharacterized terrain, particularly on Mercury following MESSENGER and BepiColombo observations.

## Features per body

{body_stats}

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `name` | string | Official IAU-approved surface feature name; unique within a body+feature_type combination but the same name may appear on different bodies; all names are approved by the IAU Working Group for Planetary System Nomenclature |
| `clean_name` | string | Name with diacritics and special characters removed or normalized for indexing and search |
| `body` | string | Planetary body the feature resides on: MOON, MARS, VENUS, or MERCURY |
| `approvaldt` | datetime | Date the IAU officially approved the feature name; null for very old features with uncertain approval records |
| `origin` | string | Cultural, mythological, or historical source of the name (e.g., "Norse goddess of the sea", "village in Nigeria"); key for understanding the naming theme applied to each body and feature type |
| `diameter` | float64 | Feature diameter or longest dimension in km; null for linear features (rima, rupes, linea) and broad regions (regio, terra) where a single diameter is not meaningful |
| `center_lon` | float64 | Center longitude in decimal degrees using IAU-standard planetocentric coordinates; longitude system varies by body — east-positive for most bodies, but historically west-positive for Moon and Mars in some references |
| `center_lat` | float64 | Center latitude in decimal degrees (planetocentric); positive north, negative south; ranges from -90 to +90 |
| `type` | string | Full English name of the feature type (e.g., Crater, Mons, Planitia, Vallis, Rupes, Fossa, Patera) |
| `code` | string | Two-letter IAU feature type code: AA=Albedo feature, CA=Catena (chain of craters), CR=Corona, DO=Dorsum (ridge), ER=Eruptive center, FL=Fluctus (flow terrain), FO=Fossa (long narrow depression), LI=Linea (elongated marking), ME=Mensa (flat-topped hill), MO=Mons (mountain), OC=Oceanus, PA=Patera (irregular crater/volcanic depression), PL=Planitia (low plain), PM=Planum (plateau/high plain), RE=Regio (large region), RI=Rima (fissure), RU=Rupes (scarp/cliff), TA=Terra (extensive land), TH=Tholus (small dome-shaped hill), UN=Undae (dune field), VA=Vallis (valley), VS=Vastitas (extensive plain) |
| `approval` | string | IAU approval status: "Approved" (in official gazetteer), "Dropped" (formerly approved, now retired), or "Provisional" (pending full approval) |
| `min_lon` | float64 | Minimum (western) longitude of the feature bounding box in decimal degrees |
| `max_lon` | float64 | Maximum (eastern) longitude of the feature bounding box in decimal degrees |
| `min_lat` | float64 | Minimum (southern) latitude of the feature bounding box in decimal degrees |
| `max_lat` | float64 | Maximum (northern) latitude of the feature bounding box in decimal degrees |
| `ethnicity` | string | Cultural/ethnic group associated with the name origin (e.g., "Norse", "African", "Greek"); useful for diversity analysis of naming conventions across bodies |
| `continent` | string | Continent of origin for the cultural source of the name (e.g., Europe, Africa, Asia); null when origin is mythological or not geographically tied |
| `quad_name` | string | USGS planetary quadrangle name covering the feature location; used for cartographic referencing |
| `quad_code` | string | USGS quadrangle alphanumeric code (e.g., "MC-01" for Mercury); null if quadrangle mapping is not available for the body |
| `link` | string | Direct URL to the feature's entry in the USGS Planetary Nomenclature online gazetteer |

## Quick stats

- **{len(df):,}** named features across {len(BODIES)} bodies
- **{n_types}** distinct feature types
- **{n_with_diameter:,}** features with known diameter
- Top types: {top_types_str}
- Approval dates: {year_min}--{year_max}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/planetary-nomenclature", split="train")
df = ds.to_pandas()

# All lunar craters
lunar_craters = df[(df["body"] == "MOON") & (df["type"] == "Crater")]

# Largest features by diameter
biggest = df.sort_values("diameter", ascending=False).head(20)

# Features by body and type
by_body_type = df.groupby(["body", "type"]).size().sort_values(ascending=False)

# Recently approved features
recent = df.sort_values("approvaldt", ascending=False).head(20)
```

## Data source

[USGS Astrogeology Science Center -- Planetary Nomenclature](https://planetarynames.wr.usgs.gov/),
maintained by the International Astronomical Union (IAU) Working Group for Planetary
System Nomenclature. Shapefiles updated nightly on AWS S3.

## Update schedule

Static dataset (nomenclature changes are infrequent).

## Related datasets

- [lunar-craters-robbins](https://huggingface.co/datasets/juliensimon/lunar-craters-robbins) -- Robbins lunar crater database
- [mars-craters-robbins](https://huggingface.co/datasets/juliensimon/mars-craters-robbins) -- Robbins Mars crater database
- [meteorite-landings](https://huggingface.co/datasets/juliensimon/meteorite-landings) -- NASA meteorite landing records
- [solar-system-moons](https://huggingface.co/datasets/juliensimon/solar-system-moons) -- Natural satellites of the solar system

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/planetary-nomenclature) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{planetary_nomenclature,
  author = {{Simon, Julien}},
  title = {{IAU Planetary Nomenclature}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/planetary-nomenclature}},
  note = {{Based on USGS Astrogeology / IAU Working Group for Planetary System Nomenclature data}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update planetary nomenclature: {len(df):,} features"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    # Emit row count for GitHub Actions
    gh_output = os.environ.get("GITHUB_OUTPUT")
    if gh_output:
        with open(gh_output, "a") as f:
            f.write(f"rows={len(df)}\n")

    print(f"Done. {len(df):,} planetary nomenclature features uploaded.")


if __name__ == "__main__":
    main()
