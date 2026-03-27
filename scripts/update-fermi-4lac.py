#!/usr/bin/env python3
"""Fetch Fermi LAT Fourth AGN Catalog (4LAC) from HEASARC and upload to HF."""

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
HF_REPO = "juliensimon/fermi-4lac-agn-catalog"

ADQL = """\
SELECT * FROM fermilac\
"""


def fetch_catalog() -> pd.DataFrame:
    """Try CSV first, fall back to JSON, then pipe-delimited text."""
    # Attempt 1: CSV
    print("Fetching Fermi 4LAC catalog (CSV)...")
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
        df = df.loc[:, df.columns != ""]
        print(f"  Text parse OK: {len(df):,} rows")
        return df

    print("::error::All fetch formats failed")
    sys.exit(1)


def main():
    df = fetch_catalog()

    # Rename columns to snake_case (HEASARC columns are already lowercase)
    # Clean up any remaining uppercase or awkward names
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    # Ensure numeric columns
    numeric_cols = [
        "ra", "dec", "lii", "bii", "glon", "glat",
        "significance", "pivot_energy", "flux",
        "energy_flux", "spectral_index", "redshift",
        "variability_index", "frac_variability",
        "flux_band1", "flux_band2", "flux_band3", "flux_band4", "flux_band5",
        "unc_flux", "unc_energy_flux", "unc_spectral_index",
        "pl_flux", "lp_flux", "lp_index", "lp_beta",
        "npred", "sed_class_index",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Clean empty strings to NaN for string columns
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip().replace(
            {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
        )

    # Sort by significance or flux descending (prefer significance)
    if "significance" in df.columns:
        df = df.sort_values("significance", ascending=False).reset_index(drop=True)
        print(f"  Sorted by significance descending")
    elif "flux" in df.columns:
        df = df.sort_values("flux", ascending=False).reset_index(drop=True)
        print(f"  Sorted by flux descending")

    n_total = len(df)
    print(f"  {n_total:,} AGN total")

    # Count by class if available
    class_col = None
    for candidate in ["class", "source_class", "optical_class", "agn_class", "clean_class"]:
        if candidate in df.columns:
            class_col = candidate
            break

    if class_col:
        class_counts = df[class_col].value_counts()
        print(f"  AGN classes ({class_col}):")
        for cls, count in class_counts.head(10).items():
            print(f"    {cls}: {count:,}")

    n_with_redshift = int(df["redshift"].notna().sum()) if "redshift" in df.columns else 0
    print(f"  {n_with_redshift:,} sources with redshift")

    check_dataset(df, "fermi-4lac", min_rows=2_500,
        expected_columns=["ra", "dec"],
        critical_columns=["ra", "dec"])

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "fermi-4lac.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        # Stats for README
        median_redshift = df["redshift"].median() if "redshift" in df.columns else 0

        # Build class summary string
        class_summary = ""
        if class_col:
            top_classes = df[class_col].value_counts().head(5)
            parts = [f"{count:,} {cls}" for cls, count in top_classes.items()]
            class_summary = ", ".join(parts)

        # Build schema table from actual columns
        schema_rows = []
        for col in df.columns:
            dtype = str(df[col].dtype)
            if "float" in dtype:
                col_type = "float"
            elif "int" in dtype:
                col_type = "int"
            elif "datetime" in dtype:
                col_type = "datetime"
            elif "bool" in dtype:
                col_type = "bool"
            else:
                col_type = "string"
            schema_rows.append(f"| `{col}` | {col_type} |")
        schema_table = "\n".join(schema_rows)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Fermi LAT Fourth AGN Catalog (4LAC)"
language:
  - en
description: "Active galactic nuclei detected by the Fermi Large Area Telescope, the largest gamma-ray AGN catalog with source classifications, spectral parameters, and redshifts."
task_categories:
  - tabular-classification
tags:
  - space
  - gamma-ray
  - fermi
  - nasa
  - agn
  - blazars
  - astronomy
  - open-data
  - tabular-data
size_categories:
  - 1K<n<10K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/fermi-4lac.parquet
    default: true
---

# Fermi LAT Fourth AGN Catalog (4LAC)

*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

The largest catalog of gamma-ray active galactic nuclei (AGN), detected by the
[Fermi Large Area Telescope (LAT)](https://fermi.gsfc.nasa.gov/). Currently **{n_total:,}**
sources with classifications, spectral parameters, and multiwavelength associations.

## Dataset description

Active galactic nuclei (AGN) are supermassive black holes at the centers of galaxies that
produce powerful jets of relativistic particles. When one of these jets points toward Earth,
the AGN appears as a blazar -- the most common type of gamma-ray source in the sky.

The Fourth LAT AGN Catalog (4LAC) is based on Fermi LAT observations and represents the
most comprehensive census of gamma-ray AGN. It includes BL Lac objects, flat-spectrum radio
quasars (FSRQs), and other AGN types, with spectral parameters, variability indices, and
multiwavelength counterpart associations.

## Schema

| Column | Type |
|--------|------|
{schema_table}

## Quick stats

- **{n_total:,}** active galactic nuclei
- **{n_with_redshift:,}** sources with measured redshift
- Median redshift: **{median_redshift:.3f}**
{f"- Top classes: {class_summary}" if class_summary else ""}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/fermi-4lac-agn-catalog", split="train")
df = ds.to_pandas()

# Brightest AGN by flux
top = df.nlargest(10, "flux")[["name", "flux", "spectral_index", "redshift"]] if "name" in df.columns else df.nlargest(10, "flux")

# Redshift distribution
import matplotlib.pyplot as plt
df["redshift"].dropna().hist(bins=50)
plt.xlabel("Redshift")
plt.title("4LAC AGN Redshift Distribution")
```

## Data source

All data comes from the [Fermi LAT 4LAC Catalog](https://heasarc.gsfc.nasa.gov/W3Browse/fermi/fermilac.html)
hosted by NASA's High Energy Astrophysics Science Archive Research Center (HEASARC),
accessed via the TAP protocol.

**Reference:** Ajello, M. et al. (2020), "The Fourth Catalog of Active Galactic Nuclei
Detected by the Fermi Large Area Telescope", ApJ, 892, 105.

## Related datasets

- [gamma-ray-bursts](https://huggingface.co/datasets/juliensimon/gamma-ray-bursts) -- Fermi GBM Gamma-Ray Burst Catalog
- [pulsar-catalog](https://huggingface.co/datasets/juliensimon/pulsar-catalog) -- ATNF Pulsar Catalogue
- [near-earth-objects](https://huggingface.co/datasets/juliensimon/near-earth-objects) -- NEO close approaches

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/fermi-4lac-agn-catalog) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{fermi_4lac,
  author = {{Simon, Julien}},
  title = {{Fermi LAT Fourth AGN Catalog (4LAC)}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/fermi-4lac-agn-catalog}},
  note = {{Based on Fermi LAT 4LAC (Ajello et al. 2020) via NASA HEASARC}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update Fermi 4LAC AGN catalog: {n_total:,} sources"
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
