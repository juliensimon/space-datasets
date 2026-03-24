#!/usr/bin/env python3
"""Fetch ATNF Pulsar Catalogue from HEASARC and upload to HF."""

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
HF_REPO = "juliensimon/pulsar-catalog"

ADQL = """\
SELECT name, alt_name, ra, dec, period, period_dot, dm, flux_1400_mhz,
  companion_type, dm_distance, age, b_surf, e_dot, pulsar_type, pm_tot,
  discovery_date, assoc_object, binary_model
FROM atnfpulsar ORDER BY name\
"""


def fetch_catalog() -> pd.DataFrame:
    """Try CSV first, fall back to JSON, then pipe-delimited text."""
    # Attempt 1: CSV
    print("Fetching ATNF Pulsar Catalogue (CSV)...")
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

    # Ensure numeric columns
    for col in ["ra", "dec", "period", "period_dot", "dm", "flux_1400_mhz",
                "dm_distance", "age", "b_surf", "e_dot", "pm_tot"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Derived columns
    df["is_millisecond"] = df["period"].apply(
        lambda x: True if pd.notna(x) and x < 0.03 else (False if pd.notna(x) else None)
    )
    # Clean empty strings to NaN for string columns from text format
    for col in ["companion_type", "binary_model", "pulsar_type", "alt_name", "assoc_object"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace({"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA})

    df["is_binary"] = df["binary_model"].notna()

    # Sort by name
    df = df.sort_values("name").reset_index(drop=True)

    print(f"  {len(df):,} pulsars total")

    n_msp = int(df["is_millisecond"].sum())
    n_binary = int(df["is_binary"].sum())
    print(f"  {n_msp:,} millisecond pulsars, {n_binary:,} in binaries")

    check_dataset(df, "pulsars", min_rows=2000,
        expected_columns=["name", "ra", "dec", "period", "dm", "is_millisecond", "is_binary"],
        critical_columns=["name", "period"])

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "pulsars.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        # Compute stats for README
        n_total = len(df)
        n_typed = df["pulsar_type"].notna().sum()
        median_period = df["period"].median()
        median_dm = df["dm"].median()

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "ATNF Pulsar Catalogue"
language:
  - en
description: "Complete catalog of known radio pulsars from the ATNF Pulsar Catalogue, including spin parameters, dispersion measures, flux densities, and derived quantities. Updated monthly."
task_categories:
  - tabular-classification
tags:
  - pulsar
  - neutron-star
  - astronomy
  - radio
  - magnetar
  - atnf
  - open-data
size_categories:
  - 1K<n<10K
---

# ATNF Pulsar Catalogue

![Update Pulsars](https://github.com/juliensimon/space-datasets/actions/workflows/update-pulsars.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.pulsars&label=updated&color=brightgreen)

Complete catalog of known radio pulsars from the
[ATNF Pulsar Catalogue](https://www.atnf.csiro.au/research/pulsar/psrcat/),
sourced via NASA HEASARC. Currently **{n_total:,}** pulsars ({n_msp:,} millisecond pulsars,
{n_binary:,} in binary systems).

## Dataset description

Pulsars are rapidly rotating neutron stars that emit beams of electromagnetic radiation.
The ATNF Pulsar Catalogue (Manchester et al. 2005) is the definitive reference catalog,
maintained by CSIRO. It includes spin period, period derivative, dispersion measure,
flux density, distance estimates, and derived quantities such as characteristic age,
surface magnetic field, and spin-down luminosity.

**Millisecond pulsars** (period < 30 ms) are ancient pulsars spun up by accretion
from a companion star. They are among the most precise clocks in the universe and are
used for pulsar timing arrays to detect gravitational waves.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `name` | string | Pulsar J-name |
| `alt_name` | string | Alternative B-name designation |
| `ra` | float | Right ascension (degrees) |
| `dec` | float | Declination (degrees) |
| `period` | float | Barycentric period (seconds) |
| `period_dot` | float | Period derivative (s/s) |
| `dm` | float | Dispersion measure (pc/cm^3) |
| `flux_1400_mhz` | float | Mean flux density at 1400 MHz (mJy) |
| `companion_type` | string | Binary companion classification |
| `dm_distance` | float | DM-derived distance (kpc) |
| `age` | float | Characteristic spin-down age (years) |
| `b_surf` | float | Surface magnetic field (Gauss) |
| `e_dot` | float | Spin-down luminosity (erg/s) |
| `pulsar_type` | string | Pulsar type classification |
| `pm_tot` | float | Total proper motion (mas/yr) |
| `discovery_date` | int | Year of discovery publication |
| `assoc_object` | string | Associated objects (e.g. SNR, globular cluster) |
| `binary_model` | string | Binary model type |
| `is_millisecond` | bool | True if period < 30 ms |
| `is_binary` | bool | True if in a binary system |

## Quick stats

- **{n_total:,}** pulsars
- **{n_msp:,}** millisecond pulsars (period < 30 ms)
- **{n_binary:,}** binary pulsars
- Median period: **{median_period:.4f}** s
- Median DM: **{median_dm:.1f}** pc/cm^3

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/pulsar-catalog", split="train")
df = ds.to_pandas()

# Millisecond pulsars
msp = df[df["is_millisecond"] == True]
print(f"{{len(msp):,}} millisecond pulsars")

# Binary pulsars
binaries = df[df["is_binary"] == True]
print(f"{{len(binaries):,}} in binary systems")

# Period-period derivative diagram (P-Pdot)
import matplotlib.pyplot as plt
valid = df.dropna(subset=["period", "period_dot"])
valid = valid[valid["period_dot"] > 0]
plt.scatter(valid["period"], valid["period_dot"], s=1, alpha=0.5)
plt.xscale("log"); plt.yscale("log")
plt.xlabel("Period (s)")
plt.ylabel("Period derivative (s/s)")
plt.title("P-Pdot Diagram")
```

## Data source

All data comes from the [ATNF Pulsar Catalogue](https://www.atnf.csiro.au/research/pulsar/psrcat/)
(Manchester, R. N., Hobbs, G. B., Teoh, A. & Hobbs, M., 2005, AJ, 129, 1993),
accessed via NASA HEASARC TAP service.

## Update schedule

Monthly (1st Monday at 18:00 UTC) via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [gamma-ray-bursts](https://huggingface.co/datasets/juliensimon/gamma-ray-bursts) — Fermi GBM Gamma-Ray Burst Catalog
- [space-track-satcat](https://huggingface.co/datasets/juliensimon/space-track-satcat) — NORAD Satellite Catalog
- [solar-flare-index](https://huggingface.co/datasets/juliensimon/solar-flare-index) — Solar flare observations

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Citation

```bibtex
@dataset{{pulsar_catalog,
  author = {{Simon, Julien}},
  title = {{ATNF Pulsar Catalogue}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/pulsar-catalog}},
  note = {{Based on ATNF Pulsar Catalogue (Manchester et al. 2005) via NASA HEASARC}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update pulsar catalog: {n_total:,} pulsars"
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
