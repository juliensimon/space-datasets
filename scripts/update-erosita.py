#!/usr/bin/env python3
"""Fetch eROSITA eRASS1 X-ray source catalog from VizieR and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from validate import check_dataset
from vizier_tap import vizier_query

HF_REPO = "juliensimon/erosita-erass1-xray"

ADQL = """SELECT * FROM "J/A+A/682/A34/erass1-m" """


def main():
    print("Fetching eROSITA eRASS1 catalog from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} X-ray sources")

    # Rename columns
    df = df.rename(columns={
        "IAUName": "source_name",
        "RA_ICRS": "ra_deg",
        "DE_ICRS": "dec_deg",
        "GLON": "glon_deg",
        "GLAT": "glat_deg",
        "EXT": "extent_arcsec",
        "posErr": "position_error_arcsec",
        "MJD": "mjd",
    })

    # Convert numerics
    numeric_cols = [
        "ra_deg", "dec_deg", "glon_deg", "glat_deg",
        "extent_arcsec", "position_error_arcsec", "mjd",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Derived columns
    df["is_extended"] = df["extent_arcsec"].fillna(0) > 0

    # Validation
    check_dataset(
        df, "erosita",
        min_rows=500000,
        expected_columns=[
            "source_name", "ra_deg", "dec_deg",
        ],
        critical_columns=["source_name", "ra_deg", "dec_deg"],
    )

    # Stats for README
    n_total = len(df)
    n_extended = int(df["is_extended"].sum())
    n_pointlike = n_total - n_extended

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "erosita_erass1_xray.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "eROSITA eRASS1 X-Ray Source Catalog"
language:
  - en
description: "The largest X-ray source catalog ever compiled — {n_total:,} sources from the first eROSITA All-Sky Survey (eRASS1), released January 2024."
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - x-ray
  - erosita
  - erass1
  - astronomy
  - mpe
  - open-data
  - tabular-data
size_categories:
  - 100K<n<1M
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/erosita_erass1_xray.parquet
    default: true
---

# eROSITA eRASS1 X-Ray Source Catalog

*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

![Update eROSITA](https://github.com/juliensimon/space-datasets/actions/workflows/update-erosita.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.erosita&label=updated&color=brightgreen)

The largest X-ray source catalog ever compiled: **{n_total:,}** sources from the
first eROSITA All-Sky Survey (eRASS1).

## Dataset description

The extended ROentgen Survey with an Imaging Telescope Array (eROSITA) aboard
the Spectrum-Roentgen-Gamma (SRG) satellite performed its first All-Sky Survey
(eRASS1) in the 0.2--2.3 keV band, detecting approximately 900,000 X-ray
sources across the Western Galactic hemisphere. This is the largest X-ray
source catalog ever produced, comprising active galactic nuclei, galaxy clusters,
stars, X-ray binaries, and other X-ray-emitting objects.

Released in January 2024, the eRASS1 catalog represents a four-fold increase
over the total number of X-ray sources known before eROSITA.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `source_name` | string | eROSITA IAU source designation |
| `ra_deg` | float64 | Right Ascension (degrees, ICRS) |
| `dec_deg` | float64 | Declination (degrees, ICRS) |
| `glon_deg` | float64 | Galactic longitude (degrees) |
| `glat_deg` | float64 | Galactic latitude (degrees) |
| `extent_arcsec` | float64 | Source extent (arcsec, 0 = point-like) |
| `position_error_arcsec` | float64 | Positional uncertainty (arcsec) |
| `mjd` | float64 | Modified Julian Date of observation |
| `is_extended` | bool | Extended source flag (extent > 0) |

## Quick stats

- **{n_total:,}** X-ray sources
- **{n_extended:,}** extended sources (galaxy clusters, etc.)
- **{n_pointlike:,}** point-like sources (AGN, stars, etc.)

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/erosita-erass1-xray", split="train")
df = ds.to_pandas()

# Extended sources (galaxy clusters)
clusters = df[df["is_extended"] == True]

# Sky map
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(12, 6))
ax.scatter(df["ra_deg"], df["dec_deg"], s=0.01, alpha=0.1)
ax.set_xlabel("RA (deg)")
ax.set_ylabel("Dec (deg)")
ax.invert_xaxis()
```

## Data source

Merloni et al. (2024), *The SRG/eROSITA All-Sky Survey: The first X-ray
catalogue (eRASS1)*. A&A 682, A34. Data retrieved via
[VizieR CDS](https://vizier.cds.unistra.fr/viz-bin/VizieR?-source=J/A+A/682/A34).

## Update schedule

Semi-annual (June 1) via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [fermi-4fgl-dr4](https://huggingface.co/datasets/juliensimon/fermi-4fgl-dr4) -- Fermi gamma-ray source catalog
- [pulsar-catalog](https://huggingface.co/datasets/juliensimon/pulsar-catalog) -- Pulsar catalog
- [galaxy-cluster-catalog](https://huggingface.co/datasets/juliensimon/galaxy-cluster-catalog) -- Galaxy cluster catalog

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Citation

```bibtex
@dataset{{erosita_erass1,
  author = {{Simon, Julien}},
  title = {{eROSITA eRASS1 X-Ray Source Catalog}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/erosita-erass1-xray}},
  note = {{Based on eROSITA eRASS1 catalog (Merloni et al. 2024) via VizieR CDS}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update eROSITA eRASS1: {n_total:,} X-ray sources"
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
