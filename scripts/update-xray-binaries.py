#!/usr/bin/env python3
"""Fetch HMXB and LMXB catalogs from HEASARC and upload merged X-ray binary catalog to HF."""

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
HF_REPO = "juliensimon/xray-binary-catalog"

HMXB_ADQL = "SELECT * FROM hmxbcat"
LMXB_ADQL = "SELECT * FROM lmxbcat"


def fetch_table(adql: str, label: str) -> pd.DataFrame:
    """Try CSV first, fall back to JSON, then pipe-delimited text."""
    # Attempt 1: CSV
    print(f"Fetching {label} (CSV)...")
    resp = requests.get(TAP_URL, params={
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": adql,
    }, timeout=120)
    resp.raise_for_status()

    if not resp.text.startswith("<?xml"):
        try:
            df = pd.read_csv(io.StringIO(resp.text))
            if len(df) > 10 and "name" in df.columns:
                print(f"  CSV parse OK: {len(df):,} rows")
                return df
        except Exception as e:
            print(f"  CSV parse failed: {e}")

    # Attempt 2: JSON
    print(f"Retrying {label} with FORMAT=json...")
    resp = requests.get(TAP_URL, params={
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "json", "QUERY": adql,
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

    # Attempt 3: pipe-delimited text
    print(f"Retrying {label} with FORMAT=text...")
    resp = requests.get(TAP_URL, params={
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "text", "QUERY": adql,
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

    print(f"::error::All fetch formats failed for {label}")
    sys.exit(1)


def fetch_catalog() -> pd.DataFrame:
    """Fetch HMXB and LMXB catalogs and merge them."""
    hmxb = fetch_table(HMXB_ADQL, "HMXB catalog (hmxbcat)")
    hmxb["binary_type"] = "HMXB"

    lmxb = fetch_table(LMXB_ADQL, "LMXB catalog (lmxbcat)")
    lmxb["binary_type"] = "LMXB"

    df = pd.concat([hmxb, lmxb], ignore_index=True)
    print(f"  Merged: {len(hmxb):,} HMXB + {len(lmxb):,} LMXB = {len(df):,} total")
    return df


def main():
    df = fetch_catalog()

    # Drop columns that are >95% null
    null_pct = df.isna().mean()
    drop_cols = null_pct[null_pct > 0.95].index.tolist()
    if drop_cols:
        print(f"  Dropping {len(drop_cols)} columns >95% null: {drop_cols}")
        df = df.drop(columns=drop_cols)

    # Numeric coercion
    numeric_cols = ["ra", "dec", "flux", "period", "orbital_period"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Clean empty strings to NaN for string columns
    str_cols = df.select_dtypes(include=["object"]).columns
    for col in str_cols:
        df[col] = df[col].replace(r"^\s*$", pd.NA, regex=True)

    # Sort by name
    if "name" in df.columns:
        df = df.sort_values("name").reset_index(drop=True)

    n_total = len(df)
    n_hmxb = int((df["binary_type"] == "HMXB").sum())
    n_lmxb = int((df["binary_type"] == "LMXB").sum())
    print(f"  {n_total:,} X-ray binaries ({n_hmxb:,} HMXB, {n_lmxb:,} LMXB)")

    check_dataset(df, "xray-binaries", min_rows=300,
        expected_columns=["name", "ra", "dec", "binary_type"],
        critical_columns=["name", "ra", "dec"])

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "xray-binaries.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        # Build column schema table for README
        col_descriptions = {
            "name": "Primary catalog designation (e.g., '4U 1700-37', 'Cygnus X-1') or IAU X-ray survey name; from HMXB/LMXB catalog column 'Name'",
            "ra": "Right ascension, ICRS J2000.0 (degrees, 0–360)",
            "dec": "Declination, ICRS J2000.0 (degrees, −90 to +90)",
            "lii": "Galactic longitude (degrees, 0–360)",
            "bii": "Galactic latitude (degrees, −90 to +90); LMXBs concentrate toward the Galactic center (|b| < 10°)",
            "class": "Sub-class of the binary (e.g., 'Be/X' for Be X-ray binary, 'SFXT' for supergiant fast X-ray transient, 'Atoll' or 'Z' for LMXB X-ray color-color diagram type)",
            "binary_type": "Binary class: 'HMXB' (high-mass donor, typically O/B star >10 M☉) or 'LMXB' (low-mass donor, Roche-lobe overflow, <1 M☉); derived from the source catalog",
            "flux": "Typical X-ray flux in mCrab; 1 Crab ≈ 2.4×10⁻⁸ erg/cm²/s in 2–10 keV; null if not measured",
            "period": "Neutron-star pulse (spin) period in seconds; null for black hole systems and sources where the period is unknown",
            "orbital_period": "Binary orbital period in days; LMXBs typically 0.2–10 d, HMXBs 1–hundreds of d; null if unknown",
            "optical_counterpart": "Name of the identified optical counterpart star or system",
            "spectral_type": "MK spectral type of the companion (donor) star (e.g., 'O9.7Iab', 'B0Ve', 'K5III'); null if unidentified",
            "vmag": "Visual (V-band) magnitude of the optical counterpart; null if unmeasured or heavily obscured",
            "alt_name": "Alternative source designation from another catalog or common name",
            "time": "Reference epoch of the position or flux measurement (MJD); null if not reported",
            "search_offset_": "Angular offset between the catalog position and the HEASARC search position (arcmin)",
            "type": "HEASARC object type code for the source (e.g., 'XB' for X-ray binary)",
            "x_ray_flux": "X-ray flux in catalog-specific units (typically erg/cm²/s or mCrab); null if unmeasured",
            "right_ascension": "Right ascension in sexagesimal format (HH MM SS.s); for display/cross-matching",
            "declination": "Declination in sexagesimal format (±DD MM SS); for display/cross-matching",
            "ref_no": "Sequential reference number in the original Liu et al. (2006/2007) printed catalog",
            "remarks": "Free-text notes on the source (e.g., transient behavior, alternative classifications, special properties)",
            "max_intensity": "Peak observed X-ray intensity in Crab units or mCrab; null if no outburst maximum is recorded",
            "x_ray_range": "Description of the X-ray energy band for the flux measurement (e.g., '2-10 keV')",
            "status": "Source status from the catalog: 'confirmed' X-ray binary, 'candidate', or similar qualifier",
            "obs_type": "Observation mode or instrument type used for the primary flux measurement",
        }
        schema_rows = []
        for col in df.columns:
            dtype = df[col].dtype
            if pd.api.types.is_float_dtype(dtype):
                col_type = "float"
            elif pd.api.types.is_integer_dtype(dtype):
                col_type = "int"
            else:
                col_type = "string"
            desc = col_descriptions.get(col, "")
            schema_rows.append(f"| `{col}` | {col_type} | {desc} |")
        schema_table = "\n".join(schema_rows)

        banner_file = download_banner("xray-binaries", tmp)
        banner_md = banner_markdown("xray-binaries", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "X-ray Binary Catalog"
language:
  - en
description: "Merged catalog of high-mass and low-mass X-ray binaries from HEASARC (Liu et al. 2006/2007)"
task_categories:
  - tabular-classification
tags:
  - space
  - x-ray-binary
  - hmxb
  - lmxb
  - x-ray
  - astronomy
  - compact-object
  - neutron-star
  - black-hole
  - open-data
  - tabular-data
  - parquet
size_categories:
  - n<1K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/xray-binaries.parquet
    default: true
---

# X-ray Binary Catalog
{banner_md}
*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) and [Stellar Catalogs](https://huggingface.co/collections/juliensimon/stellar-catalogs-69c24caf2f17e36128946744) collections on Hugging Face.*

![Update X-ray Binaries](https://github.com/juliensimon/space-datasets/actions/workflows/update-xray-binaries.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.xray-binaries&label=updated&color=brightgreen)

Merged catalog of **{n_total:,}** X-ray binaries ({n_hmxb:,} high-mass, {n_lmxb:,} low-mass) from NASA HEASARC,
combining the HMXB catalog (Liu, van Paradijs & van den Heuvel 2006) and the LMXB catalog (Liu, van Paradijs & van den Heuvel 2007).

## Dataset description

X-ray binaries are stellar systems in which a compact object (neutron star or black hole) accretes matter from a
companion star, producing intense X-ray emission. They are divided into two classes based on the mass of the donor star:

- **High-Mass X-ray Binaries (HMXBs)**: The donor is a massive O or B star (typically >10 solar masses). Accretion
  occurs via stellar wind or Roche lobe overflow. HMXBs are found in star-forming regions and include Be/X-ray
  binaries (the largest subclass) and supergiant X-ray binaries.

- **Low-Mass X-ray Binaries (LMXBs)**: The donor is a low-mass star (typically <1 solar mass). Accretion proceeds
  through Roche lobe overflow, forming a bright accretion disk. LMXBs are concentrated toward the Galactic center
  and globular clusters. They include the Z and Atoll sources (classified by their X-ray color-color diagrams) and
  the soft X-ray transients.

X-ray binaries are natural laboratories for studying accretion physics, strong gravity, and the equation of state of
ultra-dense matter. Their X-ray variability (pulsations, quasi-periodic oscillations, thermonuclear bursts) encodes
information about the compact object's mass, spin, and magnetic field. Several black hole mass measurements come from
dynamical studies of X-ray binary orbits.

This dataset merges the two standard reference catalogs maintained at HEASARC, providing a unified view of the known
Galactic X-ray binary population with positions, X-ray fluxes, orbital periods, and companion star classifications.

## Schema

| Column | Type | Description |
|--------|------|-------------|
{schema_table}

## Quick stats

- **{n_total:,}** X-ray binaries total
- **{n_hmxb:,}** High-Mass X-ray Binaries (HMXB)
- **{n_lmxb:,}** Low-Mass X-ray Binaries (LMXB)

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/xray-binary-catalog", split="train")
df = ds.to_pandas()

# Count by type
print(df["binary_type"].value_counts())

# HMXBs vs LMXBs
hmxb = df[df["binary_type"] == "HMXB"]
lmxb = df[df["binary_type"] == "LMXB"]
print(f"{{len(hmxb):,}} HMXBs, {{len(lmxb):,}} LMXBs")

# Sky distribution
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(12, 6))
for btype, group in df.groupby("binary_type"):
    ax.scatter(group["ra"], group["dec"], s=5, alpha=0.7, label=btype)
ax.set_xlabel("RA (deg)")
ax.set_ylabel("Dec (deg)")
ax.legend()
ax.set_title("X-ray Binary Sky Distribution")
```

## Data source

All data comes from the HEASARC X-ray binary catalogs:
- [HMXB Catalog (hmxbcat)](https://heasarc.gsfc.nasa.gov/W3Browse/all/hmxbcat.html) — Liu, van Paradijs & van den Heuvel (2006)
- [LMXB Catalog (lmxbcat)](https://heasarc.gsfc.nasa.gov/W3Browse/all/lmxbcat.html) — Liu, van Paradijs & van den Heuvel (2007)

Accessed via the HEASARC TAP protocol.

## Update schedule

Quarterly (February, May, August, November 1st at 08:00 UTC) via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [pulsar-catalog](https://huggingface.co/datasets/juliensimon/pulsar-catalog) — ATNF Pulsar Catalog
- [mcgill-magnetar-catalog](https://huggingface.co/datasets/juliensimon/mcgill-magnetar-catalog) — McGill Magnetar Catalog
- [chandra-x-ray-sources](https://huggingface.co/datasets/juliensimon/chandra-x-ray-sources) — Chandra Source Catalog
- [gravitational-wave-events](https://huggingface.co/datasets/juliensimon/gravitational-wave-events) — LIGO/Virgo GW Events

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a heart on the [dataset page](https://huggingface.co/datasets/juliensimon/xray-binary-catalog) and share feedback in the Community tab! Also consider giving a star to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{xray_binary_catalog,
  author = {{Simon, Julien}},
  title = {{X-ray Binary Catalog}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/xray-binary-catalog}},
  note = {{Based on HEASARC HMXB (Liu et al. 2006) and LMXB (Liu et al. 2007) catalogs}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update X-ray binary catalog: {n_total:,} sources"
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
