#!/usr/bin/env python3
"""Fetch known black hole systems from SIMBAD and upload to HF."""

import io
import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset


HF_REPO = "juliensimon/black-hole-catalog"

SIMBAD_TAP = "https://simbad.u-strasbg.fr/simbad/sim-tap/sync"

# Query all objects typed as black hole candidates (X*) and confirmed BHs (BH*)

# SIMBAD otypes: BH = black hole, BH? = BH candidate, XB* = X-ray binary,
# HXB = High-mass XRB, LXB = Low-mass XRB
ADQL = """SELECT main_id AS name, ra, dec, otype_txt AS object_type, sp_type AS spectral_type
FROM basic
WHERE otype_txt = 'BH' OR otype_txt = 'BH?' OR otype_txt = 'XB*' OR otype_txt = 'HXB' OR otype_txt = 'LXB'
ORDER BY main_id"""


def main():
    print("Fetching black hole systems from SIMBAD...")

    resp = requests.get(SIMBAD_TAP, params={
        "REQUEST": "doQuery",
        "LANG": "ADQL",
        "FORMAT": "csv",
        "QUERY": ADQL,
    }, timeout=120)
    resp.raise_for_status()

    df = pd.read_csv(io.StringIO(resp.text))
    print(f"  {len(df)} objects from SIMBAD")

    # Clean columns
    df = df.rename(columns={
        "name": "name",
        "ra": "ra_deg",
        "dec": "dec_deg",
        "object_type": "object_type",
        "spectral_type": "spectral_type",
        "v_mag": "v_mag",
        "b_mag": "b_mag",
        "k_mag": "k_mag",
        "distance_pc": "distance_pc",
        "angular_size_arcmin": "angular_size_arcmin",
    })

    for col in ["ra_deg", "dec_deg"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Deduplicate (same object may appear with multiple distance measurements)
    df = df.drop_duplicates("name", keep="first")

    # Classify BH type
    type_map = {
        "BH": "Confirmed Black Hole",
        "BH?": "Black Hole Candidate",
        "XB*": "X-ray Binary",
        "HXB": "High-Mass X-ray Binary",
        "LXB": "Low-Mass X-ray Binary",
    }
    df["bh_category"] = df["object_type"].map(type_map).fillna("Other")

    df = df.sort_values("name").reset_index(drop=True)

    check_dataset(df, "black-holes", min_rows=50,
                  expected_columns=["name", "ra_deg", "dec_deg", "object_type"],
                  critical_columns=["name", "ra_deg"])

    n = len(df)
    n_confirmed = int((df["object_type"] == "BH").sum())
    n_candidate = int((df["object_type"] == "BH?").sum())
    n_xrb = int(df["object_type"].isin(["XB*", "HXB", "LXB"]).sum())

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        data_dir = tmp_dir / "data"
        data_dir.mkdir()

        out = data_dir / "black_holes.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        print(f"  {out.stat().st_size / 1024:.0f} KB parquet")

        (tmp_dir / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Black Hole Catalog"
language:
  - en
description: >-
  Catalog of known black hole systems — confirmed black holes, candidates, and
  X-ray binaries from the SIMBAD astronomical database. Updated weekly.
size_categories:
  - n<1K
task_categories:
  - tabular-classification
tags:
  - open-data
  - astronomy
  - black-hole
  - x-ray-binary
  - simbad
  - high-energy
  - tabular-data
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/black_holes.parquet
---

# Black Hole Catalog

*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

![Update Black Holes](https://github.com/juliensimon/space-datasets/actions/workflows/update-black-holes.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['black-holes']&label=updated&color=brightgreen)

Catalog of **{n}** known black hole systems from [SIMBAD](https://simbad.u-strasbg.fr/):
**{n_confirmed}** confirmed black holes, **{n_candidate}** candidates, and
**{n_xrb}** X-ray binary systems hosting black hole companions.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `name` | string | Primary SIMBAD identifier |
| `ra_deg` | float | Right ascension (degrees) |
| `dec_deg` | float | Declination (degrees) |
| `object_type` | string | SIMBAD type code (BH, BH?, XB*, HXB, LXB) |
| `bh_category` | string | Readable category |
| `spectral_type` | string | Spectral classification |
| `v_mag` | float | Visual magnitude |
| `b_mag` | float | Blue magnitude |
| `k_mag` | float | K-band (infrared) magnitude |
| `distance_pc` | float | Distance in parsecs |
| `angular_size_arcmin` | float | Angular size (arcmin) |

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/black-hole-catalog", split="train")
df = ds.to_pandas()

# Confirmed black holes only
confirmed = df[df["object_type"] == "BH"]

# By category
df["bh_category"].value_counts()
```

## Update frequency

Updated **weekly on Monday at 18:30 UTC** via GitHub Actions.

## Data source

[SIMBAD Astronomical Database](https://simbad.u-strasbg.fr/) (CDS, Strasbourg).

## Related datasets

- [gravitational-wave-events](https://huggingface.co/datasets/juliensimon/gravitational-wave-events) — Black hole and neutron star mergers from LIGO/Virgo
- [quasar-catalog](https://huggingface.co/datasets/juliensimon/quasar-catalog) — 50K quasars and AGN (supermassive black holes)
- [pulsar-catalog](https://huggingface.co/datasets/juliensimon/pulsar-catalog) — 4,300+ pulsars (neutron stars)

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Citation

```bibtex
@dataset{{black_hole_catalog,
  author = {{Simon, Julien}},
  title = {{Black Hole Catalog}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/black-hole-catalog}},
  note = {{Based on SIMBAD astronomical database (CDS Strasbourg)}}
}}
```
""")

        print("Uploading to HF...")
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp_dir), ".",
             "--repo-type", "dataset",
             "--commit-message", f"Update black hole catalog: {n} systems"],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={n}\n")
    print("Done.")


if __name__ == "__main__":
    main()
