#!/usr/bin/env python3
"""Fetch Fermi LAT Third Catalog of Hard Sources (3FHL, >10 GeV) from HEASARC and upload to HF."""

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
HF_REPO = "juliensimon/fermi-3fhl-hard-gamma-ray"

ADQL = """\
SELECT * FROM fermi3fhl\
"""


def fetch_catalog() -> pd.DataFrame:
    """Try CSV first, fall back to JSON, then pipe-delimited text."""
    # Attempt 1: CSV
    print("Fetching Fermi 3FHL catalog (CSV)...")
    resp = requests.get(TAP_URL, params={
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": ADQL,
    }, timeout=120)
    resp.raise_for_status()

    if not resp.text.strip().startswith("<?xml"):
        try:
            df = pd.read_csv(io.StringIO(resp.text))
            if len(df) > 100:
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

    # Rename columns to snake_case (HEASARC columns are already lowercase)
    rename = {}
    for col in df.columns:
        clean = col.strip().lower().replace(" ", "_").replace("-", "_")
        if clean != col:
            rename[col] = clean
    if rename:
        df = df.rename(columns=rename)

    # Clean empty strings to NaN for all string columns
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip().replace(
            {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
        )

    # Coerce numeric columns (common 3FHL columns)
    numeric_prefixes = (
        "ra", "dec", "lii", "bii", "flux", "significance", "npred",
        "energy", "pivot", "spectral_index", "error_", "cutoff",
        "semi_major", "semi_minor", "pos_angle", "variability",
    )
    numeric_cols = [c for c in df.columns if c.startswith(numeric_prefixes)]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Sort by significance descending (highest-significance sources first)
    sort_col = None
    for candidate in ["significance", "signif_avg", "sqrt_ts"]:
        if candidate in df.columns:
            sort_col = candidate
            break
    if sort_col is None:
        # Fall back to flux if no significance column
        for candidate in ["flux", "energy_flux", "flux_density"]:
            if candidate in df.columns:
                sort_col = candidate
                break

    if sort_col:
        df[sort_col] = pd.to_numeric(df[sort_col], errors="coerce")
        df = df.sort_values(sort_col, ascending=False).reset_index(drop=True)
        print(f"  Sorted by {sort_col} descending")
    else:
        df = df.reset_index(drop=True)
        print("  No significance/flux column found for sorting")

    n_total = len(df)
    print(f"  {n_total:,} hard gamma-ray sources")

    check_dataset(df, "fermi-3fhl", min_rows=1_200,
        expected_columns=["name", "ra", "dec"],
        critical_columns=["name", "ra", "dec"])

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "fermi-3fhl.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        # Compute stats for README
        n_cols = len(df.columns)
        sig_col = sort_col or "N/A"
        median_sig = df[sig_col].median() if sort_col and sort_col in df.columns else 0

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Fermi LAT Third Catalog of Hard Sources (3FHL)"
language:
  - en
description: "1,556 gamma-ray sources detected above 10 GeV by Fermi LAT over 7 years, bridging the GeV-TeV energy gap."
task_categories:
  - tabular-classification
tags:
  - space
  - gamma-ray
  - fermi
  - nasa
  - tev
  - high-energy
  - astronomy
  - open-data
  - tabular-data
size_categories:
  - 1K<n<10K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/fermi-3fhl.parquet
    default: true
---

# Fermi LAT Third Catalog of Hard Sources (3FHL)

*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

Gamma-ray sources detected above 10 GeV by the Fermi Large Area Telescope (LAT)
over 7 years of observation. Currently **{n_total:,}** sources with {n_cols} attributes each.

## Dataset description

The 3FHL catalog (Ajello et al. 2017) contains sources detected by Fermi LAT in the
10 GeV - 2 TeV energy range using 7 years of Pass 8 data. This catalog bridges the gap
between the GeV regime covered by the standard Fermi catalogs and the TeV regime
covered by ground-based Cherenkov telescopes (H.E.S.S., MAGIC, VERITAS).

Sources include blazars, pulsar wind nebulae, supernova remnants, and unidentified
gamma-ray emitters. The catalog is essential for planning observations with current
and future TeV observatories like CTA.

## Quick stats

- **{n_total:,}** gamma-ray sources above 10 GeV

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/fermi-3fhl-hard-gamma-ray", split="train")
df = ds.to_pandas()

# Highest significance sources
print(df.head(10)[["name", "ra", "dec"]])

# Sky map
import matplotlib.pyplot as plt
plt.figure(figsize=(12, 6))
plt.scatter(df["ra"], df["dec"], s=2, alpha=0.5)
plt.xlabel("RA (deg)")
plt.ylabel("Dec (deg)")
plt.title("Fermi 3FHL Sources (>10 GeV)")
plt.gca().invert_xaxis()
```

## Data source

All data comes from the [Fermi 3FHL Catalog](https://heasarc.gsfc.nasa.gov/W3Browse/fermi/fermi3fhl.html)
hosted by NASA's High Energy Astrophysics Science Archive Research Center (HEASARC),
accessed via the TAP protocol.

Reference: Ajello, M. et al. 2017, ApJS, 232, 18.

## Related datasets

- [gamma-ray-bursts](https://huggingface.co/datasets/juliensimon/gamma-ray-bursts) — Fermi GBM Gamma-Ray Burst Catalog
- [pulsar-catalog](https://huggingface.co/datasets/juliensimon/pulsar-catalog) — ATNF Pulsar Catalogue

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/fermi-3fhl-hard-gamma-ray) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{fermi_3fhl,
  author = {{Simon, Julien}},
  title = {{Fermi LAT Third Catalog of Hard Sources (3FHL)}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/fermi-3fhl-hard-gamma-ray}},
  note = {{Based on Fermi 3FHL (Ajello et al. 2017) via NASA HEASARC}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update Fermi 3FHL catalog: {n_total:,} hard gamma-ray sources"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={n_total}\n")
    print("Done.")


if __name__ == "__main__":
    main()
