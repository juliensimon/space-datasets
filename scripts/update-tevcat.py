#!/usr/bin/env python3
"""Fetch TeVCat (TeV gamma-ray source catalog) from HEASARC and upload to HF."""

import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset


TAP_URL = "https://heasarc.gsfc.nasa.gov/xamin/vo/tap/sync"
HF_REPO = "juliensimon/tevcat-tev-gamma-ray"

ADQL = "SELECT * FROM tevcat"


def fetch_catalog() -> pd.DataFrame:
    """Try CSV first, fall back to JSON, then pipe-delimited text."""
    # Attempt 1: CSV
    print("Fetching TeVCat catalog (CSV)...")
    resp = requests.get(TAP_URL, params={
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": ADQL,
    }, timeout=120)
    resp.raise_for_status()

    if not resp.text.strip().startswith("<?xml"):
        try:
            df = pd.read_csv(io.StringIO(resp.text))
            if len(df) > 50 and "ra" in df.columns:
                print(f"  CSV parse OK: {len(df):,} rows")
                return df
        except Exception as e:
            print(f"  CSV parse failed: {e}")
    else:
        print("  CSV not supported (got XML/VOTable response)")

    # Attempt 2: JSON
    print("Retrying with FORMAT=json...")
    resp = requests.get(TAP_URL, params={
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "json", "QUERY": ADQL,
    }, timeout=120)
    resp.raise_for_status()

    try:
        data = resp.json()
        if "data" in data and "metadata" in data:
            cols = [m["name"] for m in data["metadata"]]
            df = pd.DataFrame(data["data"], columns=cols)
        else:
            df = pd.DataFrame(data)
        if len(df) > 50 and "ra" in df.columns:
            print(f"  JSON parse OK: {len(df):,} rows")
            return df
    except Exception as e:
        print(f"  JSON parse failed: {e}")

    # Attempt 3: pipe-delimited text
    print("Retrying with FORMAT=text...")
    resp = requests.get(TAP_URL, params={
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "text", "QUERY": ADQL,
    }, timeout=120)
    resp.raise_for_status()

    lines = [l for l in resp.text.strip().splitlines() if l.strip() and not l.startswith("-")]
    if len(lines) >= 2:
        header = [c.strip() for c in lines[0].split("|")]
        rows = []
        for line in lines[1:]:
            rows.append([c.strip() for c in line.split("|")])
        df = pd.DataFrame(rows, columns=header)
        df = df.loc[:, df.columns != ""]
        if "ra" in df.columns:
            print(f"  Text parse OK: {len(df):,} rows")
            return df

    print("::error::All fetch formats failed")
    sys.exit(1)


def main():
    df = fetch_catalog()

    # Column sanity check
    if "ra" not in df.columns:
        print(f"::error::Column sanity check failed: 'ra' not in {list(df.columns)}")
        sys.exit(1)

    # Rename columns to snake_case (HEASARC columns are already lowercase,
    # but normalize any oddities)
    rename = {}
    for col in df.columns:
        clean = col.strip().lower().replace(" ", "_").replace("-", "_")
        if clean != col:
            rename[col] = clean
    if rename:
        df = df.rename(columns=rename)

    # Coerce numeric columns
    numeric_cols = ["ra", "dec", "lii", "bii", "flux", "flux_error",
                    "distance", "redshift"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Clean empty strings to NaN for string columns
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip().replace(
            {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
        )

    # Sort by source name (or RA if no name column)
    if "source_name" in df.columns:
        df = df.sort_values("source_name").reset_index(drop=True)
    elif "name" in df.columns:
        df = df.sort_values("name").reset_index(drop=True)
    else:
        df = df.sort_values("ra").reset_index(drop=True)

    # Determine the name column for display
    name_col = "source_name" if "source_name" in df.columns else "name"

    print(f"  {len(df):,} TeV sources total")
    print(f"  Columns: {list(df.columns)}")

    check_dataset(df, "tevcat", min_rows=200,
        expected_columns=["ra", "dec"],
        critical_columns=["ra", "dec"])

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "tevcat.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        # Compute stats for README
        n_total = len(df)
        n_with_redshift = int(df["redshift"].notna().sum()) if "redshift" in df.columns else 0
        n_with_flux = int(df["flux"].notna().sum()) if "flux" in df.columns else 0

        # Count source types if available
        type_col = None
        for candidate in ["source_type", "class", "source_class", "category"]:
            if candidate in df.columns:
                type_col = candidate
                break
        type_summary = ""
        if type_col:
            top_types = df[type_col].value_counts().head(5)
            type_lines = [f"- **{count:,}** {name}" for name, count in top_types.items()]
            type_summary = "\n".join(type_lines)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "TeVCat — TeV Gamma-Ray Source Catalog"
language:
  - en
description: "Catalog of astronomical sources detected at very high energies (>50 GeV) by ground-based gamma-ray telescopes, from the TeVCat reference catalog via NASA HEASARC."
task_categories:
  - tabular-classification
tags:
  - space
  - gamma-ray
  - tev
  - astronomy
  - physics
  - open-data
  - tabular-data
size_categories:
  - n<1K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/tevcat.parquet
    default: true
---

# TeVCat — TeV Gamma-Ray Source Catalog

*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

Catalog of **{n_total:,}** astronomical sources detected at very high energies
(>50 GeV) by ground-based gamma-ray telescopes such as H.E.S.S., MAGIC, and VERITAS.
TeVCat is the reference catalog for the ground-based VHE gamma-ray community.

## Dataset description

Very-high-energy (VHE) gamma-ray astronomy probes the most extreme environments
in the universe: supernova remnants, pulsar wind nebulae, active galactic nuclei,
and gamma-ray binaries. TeVCat maintains the canonical list of sources detected
above ~50 GeV by imaging atmospheric Cherenkov telescopes and water Cherenkov
detectors.

This dataset is sourced from the HEASARC mirror of TeVCat and includes sky
coordinates, flux measurements, redshifts, and source classifications.

## Quick stats

- **{n_total:,}** TeV gamma-ray sources
- **{n_with_redshift:,}** with measured redshift
- **{n_with_flux:,}** with flux measurements
{f'''

## Top source types

{type_summary}
''' if type_summary else ''}
## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/tevcat-tev-gamma-ray", split="train")
df = ds.to_pandas()

print(f"{{len(df):,}} TeV gamma-ray sources")

# Sky map
import matplotlib.pyplot as plt
fig, ax = plt.subplots(subplot_kw={{"projection": "aitoff"}})
import numpy as np
ra_rad = np.deg2rad(df["ra"].dropna() - 180)
dec_rad = np.deg2rad(df["dec"].dropna())
ax.scatter(ra_rad, dec_rad, s=5, alpha=0.7)
ax.set_title("TeV Gamma-Ray Sky")
ax.grid(True)
```

## Data source

All data comes from [TeVCat](http://tevcat.uchicago.edu/) (Wakely & Horan),
accessed via NASA's [HEASARC TAP service](https://heasarc.gsfc.nasa.gov/xamin/vo/tap/).

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Related datasets

- [gamma-ray-bursts](https://huggingface.co/datasets/juliensimon/gamma-ray-bursts) — Fermi GBM Gamma-Ray Burst Catalog
- [pulsar-catalog](https://huggingface.co/datasets/juliensimon/pulsar-catalog) — ATNF Pulsar Catalogue

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/tevcat-tev-gamma-ray) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{tevcat_tev_gamma_ray,
  author = {{Simon, Julien}},
  title = {{TeVCat — TeV Gamma-Ray Source Catalog}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/tevcat-tev-gamma-ray}},
  note = {{Based on TeVCat (Wakely & Horan) via NASA HEASARC}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update TeVCat: {n_total:,} TeV gamma-ray sources"
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
