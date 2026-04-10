#!/usr/bin/env python3
"""Fetch OpenNGC deep-sky catalog from GitHub and upload to HF."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

from dataset_images import banner_markdown, download_banner
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

        banner_file = download_banner("ngc-ic", tmp)
        banner_md = banner_markdown("ngc-ic", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-sa-4.0
pretty_name: "NGC/IC Deep-Sky Object Catalog"
language:
  - en
description: "Complete NGC and IC deep-sky object catalog from OpenNGC — galaxies, nebulae, and star clusters. Updated monthly."
task_categories:
  - tabular-classification
tags:
  - space
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
  - parquet
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
{banner_md}
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

The New General Catalogue was compiled by John Louis Emil Dreyer in 1888, consolidating and correcting the observations of William Herschel, his son John Herschel, and other nineteenth-century visual observers. The two Index Catalogues (IC I in 1895 and IC II in 1908) extended the NGC with additional discoveries, many made with the new generation of photographic telescopes. Together, the NGC and IC catalogs defined the standard reference system for deep-sky objects for over a century and remain in daily use by professional and amateur astronomers alike. Every major observatory and planetarium software system uses NGC/IC designations as primary identifiers.

The objects in this catalog span an extraordinary range of astrophysical phenomena. The galaxies include everything from nearby dwarf irregulars to giant ellipticals at the centers of rich clusters, with Hubble types recorded for the brighter entries. The nebulae encompass star-forming HII regions where new stars are being born, planetary nebulae ejected by dying low-mass stars, supernova remnants marking the explosive deaths of massive stars, and reflection nebulae illuminated by nearby hot stars. The star clusters range from young open clusters of a few hundred stars in the Galactic disk to ancient globular clusters containing hundreds of thousands of stars in the Galactic halo, with ages spanning from a few million to over 12 billion years.

The OpenNGC project has corrected many historical errors in position and classification that accumulated over more than a century of visual observation, and has added modern multi-band photometry (B, V, J, H, K) that enables quantitative analysis of stellar populations, dust content, and distance estimates. This makes the catalog valuable not only as a reference for identification and pointing, but also as a dataset for statistical studies of the nearby deep-sky object population.

## Quick stats

- **{len(df):,}** cataloged objects
- **{n_galaxies:,}** galaxies, **{n_nebulae:,}** nebulae, **{n_clusters:,}** star clusters, **{n_other:,}** other
- **{n_messier}** Messier objects cross-referenced
- **{n_constellations}** constellations represented

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `name` | string | Object designation (e.g. "NGC0001", "IC1234") |
| `type` | string | Morphological type code from OpenNGC classification: G=galaxy, OCl=open cluster, GCl=globular cluster, PN=planetary nebula, EmN=emission nebula, RfN=reflection nebula, SNR=supernova remnant, Dup=duplicate entry, Other=miscellaneous |
| `object_category` | string | Broad category derived from type code: Galaxy, Nebula, Star Cluster, Other |
| `ra` | string | ICRS J2000.0 right ascension of the object center in sexagesimal (HH:MM:SS.s); suitable for telescope pointing |
| `dec` | string | ICRS J2000.0 declination of the object center in sexagesimal (±DD:MM:SS); suitable for telescope pointing |
| `const` | string | Standard 3-letter IAU constellation abbreviation (e.g., "And" for Andromeda, "Ori" for Orion); 88 possible values |
| `majax` | float | Angular size of the major axis in arcminutes; null for unresolved objects or those without reliable extent measurements |
| `minax` | float | Angular size of the minor axis in arcminutes; null for unresolved or circular objects, or those without reliable measurements |
| `posang` | float | Position angle of the major axis in degrees, measured east from north (0–180°); null for circular or unresolved objects |
| `b_mag` | float | Integrated blue-band (B, ~440 nm) magnitude; brighter objects have lower (or negative) values; typical NGC range 6–16; null for objects too extended for reliable integrated photometry |
| `v_mag` | float | Integrated visual-band (V, ~550 nm) magnitude; the standard optical brightness measure; brighter = lower number; typical NGC range 6–16; null for objects too extended for reliable integrated photometry |
| `j_mag` | float | Integrated near-infrared J-band (~1.25 µm) magnitude from 2MASS; null if not measured |
| `h_mag` | float | Integrated near-infrared H-band (~1.65 µm) magnitude from 2MASS; null if not measured |
| `k_mag` | float | Integrated near-infrared K-band (~2.17 µm) magnitude from 2MASS; null if not measured |
| `surfbr` | float | Mean surface brightness in mag/arcmin²; measures how spread out the object's light is; useful for observability under light-polluted skies; null if not available |
| `hubble` | string | Hubble/de Vaucouleurs morphological classification for galaxies (e.g., "E2" for elliptical, "SBbc" for barred spiral); null for non-galaxies |
| `m` | string | Messier catalog number (e.g., "M31"); null for objects not in the Messier catalog |
| `ngc` | string | Cross-referenced NGC (New General Catalogue) number; null for IC-only objects |
| `ic` | string | Cross-referenced IC (Index Catalogue) number; null for NGC-only objects |
| `common_names` | string | Well-known popular names (e.g., "Andromeda Galaxy", "Orion Nebula"); null for objects without widely-used common names |
| `identifiers` | string | Additional catalog cross-references (e.g., UGC, MCG, Arp numbers); null if no additional identifiers available |

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
