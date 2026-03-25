#!/usr/bin/env python3
"""Fetch Swift-BAT 157-Month Hard X-Ray Survey from HEASARC and upload to HF."""

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
HF_REPO = "juliensimon/swift-bat-hard-xray-survey"

ADQL = """\
SELECT * FROM swbat157m\
"""


def fetch_catalog() -> pd.DataFrame:
    """Try CSV first, fall back to JSON, then pipe-delimited text."""
    # Attempt 1: CSV
    print("Fetching Swift-BAT 157-Month catalog (CSV)...")
    resp = requests.get(TAP_URL, params={
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": ADQL,
    }, timeout=120)
    resp.raise_for_status()

    if not resp.text.strip().startswith("<?xml"):
        try:
            df = pd.read_csv(io.StringIO(resp.text))
            if len(df) > 100 and "ra" in df.columns:
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
        if len(df) > 100:
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
        # Drop empty columns from leading/trailing pipes
        df = df.loc[:, df.columns != ""]
        print(f"  Text parse OK: {len(df):,} rows")
        return df

    print("::error::All fetch formats failed")
    sys.exit(1)


def main():
    df = fetch_catalog()

    # Rename columns to snake_case
    rename_map = {}
    for col in df.columns:
        new = col.strip().lower().replace(" ", "_").replace("-", "_")
        if new != col:
            rename_map[col] = new
    if rename_map:
        df = df.rename(columns=rename_map)

    # Ensure numeric columns — coerce all likely numeric fields
    numeric_cols = [
        "ra", "dec", "lii", "bii",
        "snr", "flux", "flux_error",
        "bat_flux", "bat_flux_error",
        "redshift", "nh",
        "photon_index", "photon_index_error",
        "luminosity",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Also coerce any remaining columns that look numeric
    for col in df.columns:
        if col not in numeric_cols and df[col].dtype == object:
            # Try to detect numeric columns
            sample = df[col].dropna().head(20)
            if len(sample) > 0:
                try:
                    pd.to_numeric(sample)
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                except (ValueError, TypeError):
                    pass

    # Clean empty strings to NaN for string columns
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip().replace(
            {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
        )

    # Sort by SNR descending (brightest sources first)
    if "snr" in df.columns:
        df = df.sort_values("snr", ascending=False).reset_index(drop=True)

    n_total = len(df)
    print(f"  {n_total:,} hard X-ray sources")

    check_dataset(df, "swift-bat", min_rows=1_500,
        expected_columns=["ra", "dec"],
        critical_columns=["ra", "dec"])

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "swift-bat.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        # Compute stats for README
        n_with_redshift = int(df["redshift"].notna().sum()) if "redshift" in df.columns else 0
        median_snr = df["snr"].median() if "snr" in df.columns else 0

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Swift-BAT 157-Month Hard X-Ray Survey"
language:
  - en
description: "Hard X-ray source catalog (14-195 keV) from 157 months of Swift BAT all-sky observations, including fluxes, spectral parameters, and counterpart identifications."
task_categories:
  - tabular-classification
tags:
  - space
  - x-ray
  - swift
  - nasa
  - hard-x-ray
  - astronomy
  - open-data
  - tabular-data
size_categories:
  - 1K<n<10K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/swift-bat.parquet
    default: true
---

# Swift-BAT 157-Month Hard X-Ray Survey

*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

Catalog of **{n_total:,}** hard X-ray sources detected in the 14-195 keV band by the
[Swift Burst Alert Telescope (BAT)](https://swift.gsfc.nasa.gov/about_swift/bat_desc.html)
over 157 months of all-sky survey observations, sourced from NASA HEASARC.

## Dataset description

The Swift-BAT hard X-ray survey is the most sensitive and uniform survey of the sky
in the 14-195 keV energy band. The Burst Alert Telescope (BAT) is a coded-aperture
instrument aboard the Neil Gehrels Swift Observatory that continuously monitors the
hard X-ray sky. This 157-month catalog represents over 13 years of observations,
providing positions, fluxes, and spectral parameters for detected sources including
active galactic nuclei (AGN), X-ray binaries, galaxy clusters, and other high-energy
objects.

Hard X-rays penetrate gas and dust that absorb softer X-rays, making BAT uniquely
suited for finding obscured AGN and mapping the local hard X-ray universe.

## Quick stats

- **{n_total:,}** hard X-ray sources (14-195 keV)
- **{n_with_redshift:,}** sources with measured redshifts
- Median detection SNR: **{median_snr:.1f}**

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/swift-bat-hard-xray-survey", split="train")
df = ds.to_pandas()

# Brightest sources by SNR
top = df.nlargest(10, "snr")
print(top[["name", "snr", "ra", "dec"]].to_string())

# Sources with redshifts
with_z = df.dropna(subset=["redshift"])
print(f"{{len(with_z):,}} sources with redshifts")

# Sky map
import matplotlib.pyplot as plt
fig, ax = plt.subplots(subplot_kw={{"projection": "mollweide"}})
import numpy as np
ra = np.deg2rad(df["ra"] - 180)
dec = np.deg2rad(df["dec"])
ax.scatter(ra, dec, s=1, alpha=0.5)
ax.set_title("Swift-BAT Hard X-Ray Sources")
```

## Data source

All data comes from the [Swift-BAT 157-Month Hard X-Ray Survey](https://swift.gsfc.nasa.gov/results/bs157mon/)
(Oh et al. 2018, ApJS, 235, 4), accessed via the
[NASA HEASARC TAP service](https://heasarc.gsfc.nasa.gov/xamin/vo/tap/).

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Related datasets

- [gamma-ray-bursts](https://huggingface.co/datasets/juliensimon/gamma-ray-bursts) — Fermi GBM Gamma-Ray Burst Catalog
- [pulsar-catalog](https://huggingface.co/datasets/juliensimon/pulsar-catalog) — ATNF Pulsar Catalogue
- [rosat-all-sky](https://huggingface.co/datasets/juliensimon/rosat-all-sky) — ROSAT All-Sky Survey

## Citation

```bibtex
@dataset{{swift_bat_hard_xray,
  author = {{Simon, Julien}},
  title = {{Swift-BAT 157-Month Hard X-Ray Survey}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/swift-bat-hard-xray-survey}},
  note = {{Based on Oh et al. 2018 via NASA HEASARC}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Upload Swift-BAT 157-month catalog: {n_total:,} sources"
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
