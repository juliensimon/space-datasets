#!/usr/bin/env python3
"""Fetch OpenNGC deep-sky catalog from GitHub and upload to HF."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

from validate import check_dataset


NGC_CSV_URL = "https://raw.githubusercontent.com/mattiaverga/OpenNGC/master/database_files/NGC.csv"
HF_REPO = "juliensimon/ngc-ic-catalog"

# Map OpenNGC Type codes to broad categories

_TYPE_TO_CATEGORY = {
    "G": "Galaxy",
    "GGroup": "Galaxy",
    "GPair": "Galaxy",
    "GTrpl": "Galaxy",
    "Gx": "Galaxy",
    "EmN": "Nebula",
    "HII": "Nebula",
    "Neb": "Nebula",
    "PN": "Nebula",
    "RfN": "Nebula",
    "SNR": "Nebula",
    "Cl+N": "Nebula",
    "Nova": "Nebula",
    "OCl": "Star Cluster",
    "GCl": "Star Cluster",
    "*Ass": "Star Cluster",
}


def _snake_case(col: str) -> str:
    """Convert column name to snake_case."""
    return col.strip().lower().replace(" ", "_").replace("-", "_")


def main():
    print("Fetching OpenNGC catalog...")
    df = pd.read_csv(NGC_CSV_URL, sep=";")
    print(f"  {len(df):,} objects")

    # Rename columns to snake_case
    df.columns = [_snake_case(c) for c in df.columns]

    # Add broad object_category
    df["object_category"] = df["type"].map(_TYPE_TO_CATEGORY).fillna("Other")

    check_dataset(
        df,
        "ngc-ic",
        min_rows=10000,
        expected_columns=["name", "type", "ra", "dec", "const", "object_category"],
        critical_columns=["name", "type"],
    )

    # Stats for README
    n_galaxies = int((df["object_category"] == "Galaxy").sum())
    n_nebulae = int((df["object_category"] == "Nebula").sum())
    n_clusters = int((df["object_category"] == "Star Cluster").sum())
    n_other = int((df["object_category"] == "Other").sum())
    n_messier = int(df["m"].notna().sum()) if "m" in df.columns else 0
    n_constellations = df["const"].nunique() if "const" in df.columns else 0

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "ngc-ic.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-sa-4.0
pretty_name: "NGC/IC Deep-Sky Object Catalog"
language:
  - en
description: "Complete NGC and IC deep-sky object catalog from OpenNGC — galaxies, nebulae, and star clusters. Updated monthly."
task_categories:
  - tabular-classification
tags:
  - ngc
  - ic
  - deep-sky
  - nebula
  - galaxy
  - star-cluster
  - astronomy
  - open-data
  - messier
  - tabular-data
size_categories:
  - 10K<n<100K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/ngc_ic_catalog.parquet
    default: true
---

# NGC/IC Deep-Sky Object Catalog

*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

![Update NGC/IC](https://github.com/juliensimon/space-datasets/actions/workflows/update-ngc-ic.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.ngc-ic&label=updated&color=brightgreen)

Complete catalog of **{len(df):,}** deep-sky objects from the
[OpenNGC](https://github.com/mattiaverga/OpenNGC) project, covering every NGC and IC
entry — galaxies, nebulae, star clusters, and more.

## Dataset description

The New General Catalogue (NGC) and Index Catalogue (IC) are the standard references for
deep-sky objects beyond the Messier catalog. This dataset is built from the community-maintained
OpenNGC database, which provides accurate positions, magnitudes, dimensions, and classifications
for all NGC/IC entries.

## Quick stats

- **{len(df):,}** cataloged objects
- **{n_galaxies:,}** galaxies, **{n_nebulae:,}** nebulae, **{n_clusters:,}** star clusters, **{n_other:,}** other
- **{n_messier}** Messier objects cross-referenced
- **{n_constellations}** constellations represented

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `name` | string | Object designation (e.g. "NGC0001", "IC1234") |
| `type` | string | Morphological type code (G, OCl, PN, EmN, etc.) |
| `object_category` | string | Broad category: Galaxy, Nebula, Star Cluster, Other |
| `ra` | string | Right ascension (J2000) |
| `dec` | string | Declination (J2000) |
| `const` | string | Constellation abbreviation |
| `majax` | float | Major axis (arcmin) |
| `minax` | float | Minor axis (arcmin) |
| `posang` | float | Position angle (degrees) |
| `b_mag` | float | B-band magnitude |
| `v_mag` | float | V-band (visual) magnitude |
| `j_mag` | float | J-band magnitude |
| `h_mag` | float | H-band magnitude |
| `k_mag` | float | K-band magnitude |
| `surfbr` | float | Surface brightness |
| `hubble` | string | Hubble morphological type (galaxies) |
| `m` | string | Messier number, if applicable |
| `ngc` | string | Cross-referenced NGC number |
| `ic` | string | Cross-referenced IC number |
| `common_names` | string | Common names (e.g. "Andromeda Galaxy") |
| `identifiers` | string | Other catalog identifiers |

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/ngc-ic-catalog", split="train")
df = ds.to_pandas()

# All galaxies
galaxies = df[df["object_category"] == "Galaxy"]
print(f"{{len(galaxies):,}} galaxies")

# Messier objects
messier = df[df["m"].notna()]
print(f"{{len(messier)}} Messier objects")

# Brightest objects by V-mag
brightest = df.dropna(subset=["v_mag"]).nsmallest(20, "v_mag")

# Objects per constellation
by_const = df["const"].value_counts().head(10)
```

## Data source

All data comes from the [OpenNGC](https://github.com/mattiaverga/OpenNGC) project,
a community-maintained database of NGC/IC objects licensed under CC-BY-SA-4.0.

## Update schedule

Monthly (1st Monday at 18:30 UTC) via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [space-track-satcat](https://huggingface.co/datasets/juliensimon/space-track-satcat) — NORAD Satellite Catalog
- [space-launch-log](https://huggingface.co/datasets/juliensimon/space-launch-log) — Global launch history from GCAT
- [starlink-fleet-data](https://huggingface.co/datasets/juliensimon/starlink-fleet-data) — Daily Starlink constellation health

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/ngc-ic-catalog) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{ngc_ic_catalog,
  author = {{Simon, Julien}},
  title = {{NGC/IC Deep-Sky Object Catalog}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/ngc-ic-catalog}},
  note = {{Based on OpenNGC (Mattia Verga) — CC-BY-SA-4.0}}
}}
```

## License

[CC-BY-SA-4.0](https://creativecommons.org/licenses/by-sa/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update NGC/IC catalog: {len(df):,} objects"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={len(df)}\n")
    print("Done.")


if __name__ == "__main__":
    main()
