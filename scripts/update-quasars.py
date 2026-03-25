#!/usr/bin/env python3
"""Fetch quasar/AGN catalog from SIMBAD and upload to HF."""

import io
import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset


HF_REPO = "juliensimon/quasar-catalog"

SIMBAD_TAP = "https://simbad.u-strasbg.fr/simbad/sim-tap/sync"

# SIMBAD otypes for AGN: QSO (quasar), AGN (active galactic nucleus),

# Sy1/Sy2 (Seyfert), BLL (BL Lac), Bla (Blazar), LIN (LINER)
ADQL = """SELECT TOP 100000 main_id AS name, ra, dec, otype_txt AS object_type
FROM basic
WHERE otype_txt = 'QSO' OR otype_txt = 'AGN' OR otype_txt = 'Sy1' OR otype_txt = 'Sy2' OR otype_txt = 'BLL' OR otype_txt = 'Bla' OR otype_txt = 'LIN'
ORDER BY main_id"""


def main():
    print("Fetching quasar/AGN catalog from SIMBAD...")

    resp = requests.get(SIMBAD_TAP, params={
        "REQUEST": "doQuery",
        "LANG": "ADQL",
        "FORMAT": "csv",
        "QUERY": ADQL,
    }, timeout=300)
    resp.raise_for_status()

    df = pd.read_csv(io.StringIO(resp.text))
    print(f"  {len(df)} objects from SIMBAD")

    df = df.rename(columns={
        "name": "name",
        "ra": "ra_deg",
        "dec": "dec_deg",
        "object_type": "object_type",
    })

    for col in ["ra_deg", "dec_deg"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Deduplicate (multiple redshift measurements)
    df = df.drop_duplicates("name", keep="first")

    # Readable AGN category
    type_map = {
        "QSO": "Quasar",
        "AGN": "Active Galactic Nucleus",
        "Sy1": "Seyfert 1",
        "Sy2": "Seyfert 2",
        "BLL": "BL Lac Object",
        "Bla": "Blazar",
        "LIN": "LINER",
    }
    df["agn_category"] = df["object_type"].map(type_map).fillna(df["object_type"])

    df = df.sort_values("name").reset_index(drop=True)

    check_dataset(df, "quasars", min_rows=1000,
                  expected_columns=["name", "ra_deg", "dec_deg", "object_type"],
                  critical_columns=["name", "ra_deg"])

    n = len(df)
    n_qso = int((df["object_type"] == "QSO").sum())
    n_agn = int((df["object_type"] == "AGN").sum())
    n_seyfert = int(df["object_type"].isin(["Sy1", "Sy2"]).sum())
    n_blazar = int(df["object_type"].isin(["BLL", "Bla"]).sum())
    pass  # stats computed from available columns only

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        data_dir = tmp_dir / "data"
        data_dir.mkdir()

        out = data_dir / "quasars.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp_dir / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Quasar & AGN Catalog"
language:
  - en
description: >-
  Catalog of {n:,} quasars and active galactic nuclei from SIMBAD — quasars,
  Seyfert galaxies, blazars, and LINERs with redshifts and photometry.
size_categories:
  - {"10K<n<100K" if n >= 10000 else "1K<n<10K"}
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - open-data
  - astronomy
  - quasar
  - agn
  - blazar
  - seyfert
  - redshift
  - simbad
  - cosmology
  - tabular-data
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/quasars.parquet
---

# Quasar & AGN Catalog

*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

![Update Quasars](https://github.com/juliensimon/space-datasets/actions/workflows/update-quasars.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.quasars&label=updated&color=brightgreen)

Catalog of **{n:,}** quasars and active galactic nuclei from
[SIMBAD](https://simbad.u-strasbg.fr/): **{n_qso:,}** quasars, **{n_seyfert:,}**
Seyfert galaxies, **{n_blazar:,}** blazars/BL Lacs, **{n_agn:,}** general AGN.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `name` | string | Primary SIMBAD identifier |
| `ra_deg` | float | Right ascension (degrees) |
| `dec_deg` | float | Declination (degrees) |
| `object_type` | string | SIMBAD type code (QSO, AGN, Sy1, Sy2, BLL, Bla, LIN) |
| `agn_category` | string | Readable category (Quasar, Seyfert 1, Blazar, etc.) |



## Quick stats

- **{n:,}** objects
- **{n_qso:,}** quasars, **{n_seyfert:,}** Seyferts, **{n_blazar:,}** blazars

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/quasar-catalog", split="train")
df = ds.to_pandas()

# AGN type breakdown
df["agn_category"].value_counts()
```

## Update frequency

Updated **weekly on Monday at 19:00 UTC** via GitHub Actions.

## Data source

[SIMBAD Astronomical Database](https://simbad.u-strasbg.fr/) (CDS, Strasbourg).

## Related datasets

- [black-hole-catalog](https://huggingface.co/datasets/juliensimon/black-hole-catalog) — Known black hole systems and X-ray binaries
- [messier-catalog](https://huggingface.co/datasets/juliensimon/messier-catalog) — 110 iconic deep-sky objects
- [ngc-ic-catalog](https://huggingface.co/datasets/juliensimon/ngc-ic-catalog) — 14K deep-sky objects (NGC + IC)
- [galaxy-clusters](https://huggingface.co/datasets/juliensimon/galaxy-clusters) — 1,650+ Planck SZ-detected clusters

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Citation

```bibtex
@dataset{{quasar_catalog,
  author = {{Simon, Julien}},
  title = {{Quasar & AGN Catalog}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/quasar-catalog}},
  note = {{Based on SIMBAD astronomical database (CDS Strasbourg)}}
}}
```
""")

        print("Uploading to HF...")
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp_dir), ".",
             "--repo-type", "dataset",
             "--commit-message", f"Update quasar catalog: {n:,} objects"],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={n}\n")
    print("Done.")


if __name__ == "__main__":
    main()
