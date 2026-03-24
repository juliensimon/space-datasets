#!/usr/bin/env python3
"""Fetch the Messier catalog (110 deep-sky objects) from SIMBAD and upload to HF."""

import io
import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset


HF_REPO = "juliensimon/messier-catalog"

SIMBAD_TAP = "https://simbad.u-strasbg.fr/simbad/sim-tap/sync"

ADQL = """SELECT main_id, ra, dec, otype_txt AS object_type,
       galdim_majaxis AS major_axis_arcmin,
       galdim_minaxis AS minor_axis_arcmin
FROM basic
WHERE main_id LIKE 'M  %' OR main_id LIKE 'M %'
ORDER BY main_id"""


MESSIER_TYPES = {
    "GlC": "Globular Cluster",
    "OpC": "Open Cluster",
    "HII": "HII Region",
    "PN": "Planetary Nebula",
    "SNR": "Supernova Remnant",
    "G": "Galaxy",
    "AGN": "Active Galaxy",
    "Sy2": "Seyfert Galaxy",
    "GiG": "Galaxy in Group",
    "GiC": "Galaxy in Cluster",
    "As*": "Stellar Association",
    "Cl*": "Star Cluster",
    "RNe": "Reflection Nebula",
    "DNe": "Dark Nebula",
    "EmO": "Emission Object",
    "ISM": "Interstellar Medium",
    "Rad": "Radio Source",
}


def main():
    print("Fetching Messier catalog from SIMBAD...")

    resp = requests.get(SIMBAD_TAP, params={
        "REQUEST": "doQuery",
        "LANG": "ADQL",
        "FORMAT": "csv",
        "QUERY": ADQL,
    }, timeout=60)
    resp.raise_for_status()

    df = pd.read_csv(io.StringIO(resp.text))
    print(f"  {len(df)} raw objects from SIMBAD")

    df = df.rename(columns={
        "main_id": "name",
        "ra": "ra_deg",
        "dec": "dec_deg",
        "object_type": "object_type",
        "major_axis_arcmin": "major_axis_arcmin",
        "minor_axis_arcmin": "minor_axis_arcmin",
    })

    # Filter to actual Messier objects (M 1 through M 110)
    # SIMBAD main_id format: "M  1", "M 42", "M 110" (variable spacing)
    df["messier_number"] = df["name"].str.extract(r'^M\s+(\d+)$').astype(float)
    df = df[df["messier_number"].notna() & (df["messier_number"] <= 110)]
    df["messier_number"] = df["messier_number"].astype(int)
    df["messier_id"] = "M " + df["messier_number"].astype(str)

    # Map object types to readable names
    df["object_category"] = df["object_type"].map(MESSIER_TYPES).fillna(df["object_type"])

    df = df.sort_values("messier_number").reset_index(drop=True)

    for col in ["ra_deg", "dec_deg", "major_axis_arcmin", "minor_axis_arcmin"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    check_dataset(df, "messier", min_rows=80,
                  expected_columns=["messier_id", "name", "ra_deg", "dec_deg", "object_type"],
                  critical_columns=["messier_id", "name"])

    n = len(df)
    n_galaxy = int(df["object_category"].str.contains("Galaxy", na=False).sum())
    n_cluster = int(df["object_category"].str.contains("Cluster", na=False).sum())
    n_nebula = int(df["object_category"].str.contains("Nebula|HII|SNR", na=False, regex=True).sum())

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        data_dir = tmp_dir / "data"
        data_dir.mkdir()

        out = data_dir / "messier.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        print(f"  {out.stat().st_size / 1024:.0f} KB parquet")

        (tmp_dir / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Messier Catalog"
language:
  - en
description: >-
  The complete Messier catalog of 110 deep-sky objects — galaxies, nebulae, and
  star clusters visible from the Northern Hemisphere. From SIMBAD.
size_categories:
  - n<1K
task_categories:
  - tabular-classification
tags:
  - open-data
  - astronomy
  - messier
  - deep-sky
  - galaxy
  - nebula
  - star-cluster
  - simbad
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/messier.parquet
---

# Messier Catalog

![Update Messier](https://github.com/juliensimon/space-datasets/actions/workflows/update-messier.yml/badge.svg)

The complete **Messier catalog** — {n} deep-sky objects catalogued by Charles Messier
in the 18th century. Includes {n_galaxy} galaxies, {n_cluster} star clusters,
and {n_nebula} nebulae/remnants.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `messier_id` | string | Messier designation (M 1, M 2, ...) |
| `messier_number` | int | Messier number (1-110) |
| `name` | string | Primary SIMBAD name (e.g. "NGC 224", "Crab Nebula") |
| `ra_deg` | float | Right ascension (degrees) |
| `dec_deg` | float | Declination (degrees) |
| `object_type` | string | SIMBAD object type code |
| `object_category` | string | Human-readable category (Galaxy, Globular Cluster, etc.) |
| `major_axis_arcmin` | float | Major axis angular size (arcmin) |
| `minor_axis_arcmin` | float | Minor axis angular size (arcmin) |

## Quick stats

- **{n}** Messier objects
- **{n_galaxy}** galaxies, **{n_cluster}** star clusters, **{n_nebula}** nebulae/remnants

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/messier-catalog", split="train")
df = ds.to_pandas()

# Galaxies only
galaxies = df[df["object_category"].str.contains("Galaxy", na=False)]

# Objects by category
df["object_category"].value_counts()
```

## Data source

[SIMBAD Astronomical Database](https://simbad.u-strasbg.fr/) (CDS, Strasbourg).

## Citation

```bibtex
@dataset{{messier_catalog,
  author = {{Simon, Julien}},
  title = {{Messier Catalog}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/messier-catalog}},
  note = {{Based on SIMBAD astronomical database (CDS Strasbourg)}}
}}
```
""")

        print("Uploading to HF...")
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp_dir), ".",
             "--repo-type", "dataset",
             "--commit-message", f"Update Messier catalog: {n} objects"],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={n}\n")
    print("Done.")


if __name__ == "__main__":
    main()
