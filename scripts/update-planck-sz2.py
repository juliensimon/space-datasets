#!/usr/bin/env python3
"""Fetch Planck Second SZ Source Catalog from HEASARC and upload to HF."""

import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd
import requests

from dataset_images import banner_markdown, download_banner
from validate import check_dataset


TAP_URL = "https://heasarc.gsfc.nasa.gov/xamin/vo/tap/sync"
HF_REPO = "juliensimon/planck-sz2-clusters"

ADQL = """\
SELECT * FROM plancksz2\
"""


def fetch_catalog() -> pd.DataFrame:
    """Try CSV first, fall back to JSON, then pipe-delimited text."""
    # Attempt 1: CSV
    print("Fetching Planck SZ2 catalog (CSV)...")
    resp = requests.get(TAP_URL, params={
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": ADQL,
    }, timeout=120)
    resp.raise_for_status()

    if not resp.text.strip().startswith("<?xml"):
        try:
            df = pd.read_csv(io.StringIO(resp.text))
            if len(df) > 100 and "name" in df.columns:
                print(f"  CSV parse OK: {len(df):,} rows")
                return df
        except Exception as e:
            print(f"  CSV parse failed: {e}")

    # Attempt 2: JSON
    print("Retrying with FORMAT=json...")
    resp = requests.get(TAP_URL, params={
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "json", "QUERY": ADQL,
    }, timeout=120)
    resp.raise_for_status()

    try:
        data = resp.json()
        # VOTable JSON format: metadata + data arrays
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

    # Auto-drop columns that are >95% null
    null_pct = df.isna().mean()
    drop_cols = null_pct[null_pct > 0.95].index.tolist()
    if drop_cols:
        print(f"  Dropping {len(drop_cols)} columns with >95% nulls: {drop_cols}")
        df = df.drop(columns=drop_cols)

    # Ensure numeric columns
    numeric_cols = ["ra", "dec", "lii", "bii", "redshift", "redshift_err",
                    "snr", "msz", "msz_err_up", "msz_err_low",
                    "y5r500", "y5r500_err_up", "y5r500_err_low",
                    "theta", "theta_err_up", "theta_err_low"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Derived column: is_confirmed (has a measured redshift)
    if "redshift" in df.columns:
        df["is_confirmed"] = df["redshift"].notna()
    elif "validation" in df.columns:
        df["is_confirmed"] = df["validation"].astype(str).str.strip().str.len() > 0
    else:
        df["is_confirmed"] = False

    # Sort by SNR descending
    if "snr" in df.columns:
        df = df.sort_values("snr", ascending=False).reset_index(drop=True)

    print(f"  {len(df):,} galaxy clusters total")

    check_dataset(df, "planck-sz2", min_rows=1000,
        expected_columns=["name", "ra", "dec"],
        critical_columns=["name", "ra", "dec"])

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "planck-sz2.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        # Compute stats for README
        n_total = len(df)
        n_confirmed = int(df["is_confirmed"].sum())
        n_unconfirmed = n_total - n_confirmed
        snr_max = df["snr"].max() if "snr" in df.columns else 0
        snr_median = df["snr"].median() if "snr" in df.columns else 0
        n_with_redshift = int(df["redshift"].notna().sum()) if "redshift" in df.columns else 0
        z_median = df["redshift"].median() if "redshift" in df.columns and n_with_redshift > 0 else 0

        highest_snr_idx = df["snr"].idxmax() if "snr" in df.columns else None
        highest_snr_name = df.loc[highest_snr_idx, "name"] if highest_snr_idx is not None else "N/A"
        highest_snr_val = df.loc[highest_snr_idx, "snr"] if highest_snr_idx is not None else 0

        # Build column schema from actual DataFrame
        col_descriptions = {
            "name": "PSZ2 catalog designation",
            "ra": "Right ascension (J2000, degrees)",
            "dec": "Declination (J2000, degrees)",
            "lii": "Galactic longitude (degrees)",
            "bii": "Galactic latitude (degrees)",
            "snr": "Signal-to-noise ratio of the SZ detection",
            "redshift": "Spectroscopic or photometric redshift",
            "redshift_err": "Uncertainty on the redshift",
            "redshift_type": "Source of redshift measurement (spectroscopic/photometric)",
            "redshift_source": "Reference or survey providing the redshift",
            "msz": "SZ-derived cluster mass M_SZ (10^14 solar masses)",
            "msz_err_up": "Upper uncertainty on M_SZ",
            "msz_err_low": "Lower uncertainty on M_SZ",
            "y5r500": "Integrated Compton parameter Y_5R500 (arcmin^2)",
            "y5r500_err_up": "Upper uncertainty on Y_5R500",
            "y5r500_err_low": "Lower uncertainty on Y_5R500",
            "theta": "Cluster angular size estimate (arcmin)",
            "theta_err_up": "Upper uncertainty on theta",
            "theta_err_low": "Lower uncertainty on theta",
            "pipeline_det": "Detection pipeline flags (MMF1, MMF3, PwS)",
            "validation": "External validation status of the detection",
            "external_name": "Cross-matched name from external catalogs",
            "external_class": "Classification from external catalogs",
            "is_confirmed": "Has a measured redshift (derived column)",
        }
        schema_rows = []
        for col in df.columns:
            dtype = str(df[col].dtype)
            if dtype.startswith("float"):
                col_type = "float"
            elif dtype.startswith("int"):
                col_type = "int"
            elif dtype == "bool":
                col_type = "bool"
            else:
                col_type = "string"
            desc = col_descriptions.get(col, "")
            schema_rows.append(f"| `{col}` | {col_type} | {desc} |")
        schema_table = "\n".join(schema_rows)

        banner_file = download_banner("planck-sz2", tmp)
        banner_md = banner_markdown("planck-sz2", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Planck Second Sunyaev-Zeldovich Source Catalog (PSZ2)"
language:
  - en
description: "Galaxy clusters detected via the Sunyaev-Zeldovich effect by ESA Planck, with redshifts, masses, and integrated Compton parameters"
task_categories:
  - tabular-classification
tags:
  - space
  - planck
  - sunyaev-zeldovich
  - galaxy-cluster
  - cmb
  - esa
  - cosmology
  - astronomy
  - open-data
  - tabular-data
  - parquet
size_categories:
  - 1K<n<10K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/planck-sz2.parquet
    default: true
---

# Planck Second Sunyaev-Zeldovich Source Catalog (PSZ2)
{banner_md}
*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) and [Galaxies & Cosmology](https://huggingface.co/collections/juliensimon/galaxies-cosmology-datasets-6839d94f11ba2e03cd4b18cb) collections on Hugging Face.*

![Update Planck SZ2](https://github.com/juliensimon/space-datasets/actions/workflows/update-planck-sz2.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.planck-sz2&label=updated&color=brightgreen)

Complete catalog of galaxy clusters detected via the thermal Sunyaev-Zeldovich (SZ) effect
by the [ESA Planck satellite](https://www.cosmos.esa.int/web/planck), sourced from NASA HEASARC.
Currently **{n_total:,}** galaxy clusters ({n_confirmed:,} confirmed with redshifts,
{n_unconfirmed:,} candidates).

## Dataset description

The Sunyaev-Zeldovich (SZ) effect is the inverse Compton scattering of cosmic microwave background
(CMB) photons by the hot intracluster medium (ICM) of galaxy clusters. As CMB photons pass through
the ICM (electron temperatures of 10^7-10^8 K), they receive a characteristic energy boost that
produces a spectral distortion observable at millimeter wavelengths: a decrement below ~217 GHz
and an increment above. This effect is unique in cosmology because its surface brightness is
**redshift-independent**, making it an extraordinarily powerful tool for detecting massive clusters
at any distance.

The Planck satellite's all-sky survey at nine frequencies (30-857 GHz) provided the first
uniform all-sky SZ cluster catalog. The PSZ2 catalog represents the largest SZ-selected
sample of galaxy clusters, detected using three independent methods: two implementations of
matched multi-frequency filters (MMF1 and MMF3) and PowellSnakes (PwS), a Bayesian detection
algorithm. Each cluster's integrated Compton parameter Y5R500 quantifies the total thermal
energy of the ICM and serves as a low-scatter mass proxy through the Y-M scaling relation.

These SZ-selected clusters are essential for constraining cosmological parameters
(Omega_m, sigma_8), calibrating the cluster mass function, understanding large-scale
structure formation, and cross-matching with optical, X-ray, and gravitational lensing surveys.

## Schema

| Column | Type | Description |
|--------|------|-------------|
{schema_table}

## Quick stats

- **{n_total:,}** galaxy clusters detected via the SZ effect
- **{n_confirmed:,}** confirmed with measured redshifts (median z = {z_median:.3f})
- Highest SNR: **{highest_snr_name}** (SNR = {highest_snr_val:.1f})
- Median SNR: **{snr_median:.1f}**, Max SNR: **{snr_max:.1f}**

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/planck-sz2-clusters", split="train")
df = ds.to_pandas()

# Confirmed clusters with redshifts
confirmed = df[df["is_confirmed"]]
print(f"{{len(confirmed):,}} clusters with measured redshifts")

# Highest SNR detections
top = df.nlargest(10, "snr")[["name", "snr", "redshift", "msz"]]

# Redshift distribution
import matplotlib.pyplot as plt
df["redshift"].dropna().hist(bins=50)
plt.xlabel("Redshift")
plt.ylabel("Count")
plt.title("Planck SZ2 Cluster Redshift Distribution")
```

## Data source

All data comes from the [Planck PSZ2 Catalog](https://heasarc.gsfc.nasa.gov/W3Browse/all/plancksz2.html)
hosted by NASA's High Energy Astrophysics Science Archive Research Center (HEASARC),
accessed via the TAP protocol. The original catalog was published by the Planck Collaboration
(Planck Collaboration XXVII, 2016, A&A, 594, A27).

## Update schedule

Semi-annual on January 1st and July 1st at 07:00 UTC via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [galaxy-clusters](https://huggingface.co/datasets/juliensimon/galaxy-clusters) — Multi-wavelength galaxy cluster catalog
- [desi-dr1-redshifts](https://huggingface.co/datasets/juliensimon/desi-dr1-redshifts) — DESI DR1 spectroscopic redshifts
- [pantheon-plus-sne-ia](https://huggingface.co/datasets/juliensimon/pantheon-plus-sne-ia) — Pantheon+ Type Ia supernovae for cosmology

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/planck-sz2-clusters) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{planck_sz2_clusters,
  author = {{Simon, Julien}},
  title = {{Planck Second Sunyaev-Zeldovich Source Catalog (PSZ2)}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/planck-sz2-clusters}},
  note = {{Based on Planck Collaboration XXVII (2016) data via NASA HEASARC}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update Planck SZ2 catalog: {n_total:,} clusters"
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
