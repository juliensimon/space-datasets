#!/usr/bin/env python3
"""Fetch IceCube Neutrino Point Source Catalog from HEASARC and upload to HF."""

import io
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd
import requests

from dataset_images import banner_markdown, download_banner
from validate import check_dataset


TAP_URL = "https://heasarc.gsfc.nasa.gov/xamin/vo/tap/sync"
HF_REPO = "juliensimon/icecube-neutrino-catalog"

ADQL = "SELECT * FROM icecubepsc"


def fetch_catalog() -> pd.DataFrame:
    """Try text first (HEASARC prefers pipe-delimited), fall back to CSV, then JSON."""
    # Attempt 1: pipe-delimited text
    print("Fetching IceCube Neutrino Point Source Catalog (text)...")
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
        if len(df) > 10:
            print(f"  Text parse OK: {len(df):,} rows")
            return df

    # Attempt 2: CSV
    print("Retrying with FORMAT=csv...")
    resp = requests.get(TAP_URL, params={
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": ADQL,
    }, timeout=120)
    resp.raise_for_status()

    if not resp.text.strip().startswith("<?xml"):
        try:
            df = pd.read_csv(io.StringIO(resp.text))
            if len(df) > 10:
                print(f"  CSV parse OK: {len(df):,} rows")
                return df
        except Exception as e:
            print(f"  CSV parse failed: {e}")
    else:
        print("  CSV not supported (got XML/VOTable response)")

    # Attempt 3: JSON
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
        if len(df) > 10:
            print(f"  JSON parse OK: {len(df):,} rows")
            return df
    except Exception as e:
        print(f"  JSON parse failed: {e}")

    print("::error::All fetch formats failed")
    sys.exit(1)


def to_snake_case(name: str) -> str:
    """Convert column name to snake_case."""
    s = re.sub(r"[^\w]", "_", name.strip().lower())
    s = re.sub(r"_+", "_", s).strip("_")
    return s


def main():
    df = fetch_catalog()

    # Rename columns to snake_case
    df.columns = [to_snake_case(c) for c in df.columns]

    # Coerce numeric columns
    numeric_cols = ["ra", "dec", "lii", "bii", "flux", "flux_err",
                    "spectral_index", "spectral_index_err",
                    "n_s", "ts", "dec_deg", "ra_deg"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Clean empty strings to NaN for string columns
    for col in df.select_dtypes(include="object").columns:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
            )

    df = df.reset_index(drop=True)

    n_total = len(df)
    print(f"  {n_total:,} sources total")

    check_dataset(df, "icecube", min_rows=100,
                  expected_columns=[c for c in ["ra", "dec"] if c in df.columns],
                  critical_columns=[c for c in ["ra", "dec"] if c in df.columns])

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "icecube_neutrino_catalog.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        col_table = "\n".join(
            f"| `{c}` | {str(df[c].dtype)} | |"
            for c in df.columns
        )

        banner_file = download_banner("icecube", tmp)
        banner_md = banner_markdown("icecube", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "IceCube Neutrino Point Source Catalog"
language:
  - en
description: "IceCube Neutrino Point Source Catalog from NASA HEASARC — point sources of high-energy astrophysical neutrinos detected by the IceCube Neutrino Observatory."
task_categories:
  - tabular-classification
tags:
  - space
  - neutrino
  - icecube
  - high-energy
  - astronomy
  - open-data
  - tabular-data
  - parquet
size_categories:
  - n<1K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/icecube_neutrino_catalog.parquet
    default: true
---

# IceCube Neutrino Point Source Catalog
{banner_md}
*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

Point source catalog from the [IceCube Neutrino Observatory](https://icecube.wisc.edu/),
sourced via NASA HEASARC. Currently **{n_total:,}** sources.

## Dataset description

The IceCube Neutrino Observatory is a cubic-kilometer particle detector buried in the
Antarctic ice at the South Pole. It detects high-energy neutrinos from astrophysical
sources such as active galactic nuclei, blazars, and other extreme cosmic environments.
This catalog lists point sources identified in IceCube neutrino data.

The point source catalog represents the result of searches for statistically significant clustering of neutrino arrival directions above the isotropic atmospheric background. Each candidate source is characterized by a test statistic (TS) reflecting the likelihood of a genuine astrophysical signal versus the null hypothesis, along with a best-fit number of signal events and spectral index. These searches are sensitive to both steady emitters and time-integrated emission from variable sources, probing hadronic acceleration in jets, accretion flows, and shock environments across the sky.

Neutrino point source detection is inherently challenging because the atmospheric neutrino background is orders of magnitude larger than the astrophysical signal, and the angular resolution of muon track reconstruction in ice (~0.5--1 degree at TeV energies) limits the ability to resolve individual sources. The catalog therefore includes both high-confidence detections and sub-threshold candidates that may become significant with additional exposure. Cross-correlation with gamma-ray, X-ray, and radio catalogs is a key strategy for identifying the astrophysical counterparts and understanding the relative contributions of leptonic and hadronic processes in candidate source populations such as blazars, Seyfert galaxies, and starburst galaxies.

## Schema

| Column | Type | Description |
|--------|------|-------------|
{col_table}

## Quick stats

- **{n_total:,}** neutrino point sources

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/icecube-neutrino-catalog", split="train")
df = ds.to_pandas()

# Sky map of neutrino sources
print(f"{{len(df):,}} IceCube point sources")
```

## Data source

[IceCube Neutrino Observatory](https://icecube.wisc.edu/) via
[NASA HEASARC](https://heasarc.gsfc.nasa.gov/) TAP service (`icecubepsc` table).

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/icecube-neutrino-catalog) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{icecube_neutrino_catalog,
  author = {{Simon, Julien}},
  title = {{IceCube Neutrino Point Source Catalog}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/icecube-neutrino-catalog}},
  note = {{Based on IceCube data via NASA HEASARC}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update IceCube neutrino catalog: {n_total:,} sources"
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
