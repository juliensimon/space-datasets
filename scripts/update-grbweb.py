#!/usr/bin/env python3
"""Fetch GRBweb unified multi-instrument GRB catalog and upload to HF.

Source: IceCube GRBweb public Summary_table.txt
Combines data from Fermi, Swift, BATSE, BeppoSAX, IPN, and other instruments.
"""

import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset

SUMMARY_URL = "https://user-web.icecube.wisc.edu/~grbweb_public/Summary_table.txt"
HF_REPO = "juliensimon/grbweb-unified-grb-catalog"

# Column names from the # header comment in the file
COLUMNS = [
    "grb_name", "grb_name_fermi", "t0_utc", "ra", "dec",
    "pos_error", "t90", "t90_error", "t90_start", "fluence",
    "fluence_error", "redshift", "t100", "gbm_located", "mjd",
]

NUMERIC_COLS = [
    "ra", "dec", "pos_error", "t90", "t90_error", "fluence",
    "fluence_error", "redshift", "t100", "mjd",
]

SENTINEL = "-999"


def fetch_summary() -> pd.DataFrame:
    """Download the GRBweb summary table and parse into a DataFrame."""
    print("Fetching GRBweb Summary_table.txt ...")
    resp = requests.get(SUMMARY_URL, timeout=120)
    resp.raise_for_status()

    rows = []
    for line in resp.text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 15:
            print(f"  Skipping malformed line ({len(parts)} fields): {line[:80]}")
            continue
        rows.append(parts)

    print(f"  Parsed {len(rows):,} data rows")
    df = pd.DataFrame(rows, columns=COLUMNS)
    return df


def transform(df: pd.DataFrame) -> pd.DataFrame:
    """Clean types, replace sentinels, derive columns."""
    # Replace -999 sentinel with NaN
    df = df.replace(SENTINEL, pd.NA)
    df = df.replace("None", pd.NA)

    # Coerce numeric columns
    for col in NUMERIC_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Convert MJD to datetime (MJD epoch: 1858-11-17T00:00:00)
    mjd_epoch = pd.Timestamp("1858-11-17")
    df["trigger_time"] = mjd_epoch + pd.to_timedelta(df["mjd"], unit="D")

    # Boolean for GBM located
    df["gbm_located"] = df["gbm_located"].map({"True": True, "False": False})

    # Clean GRB name — strip trailing asterisk (marks updated entries)
    df["grb_name"] = df["grb_name"].str.rstrip("*")

    # Duration class based on T90
    df["duration_class"] = df["t90"].apply(
        lambda x: "short" if pd.notna(x) and x < 2.0
        else ("long" if pd.notna(x) else None)
    )

    # Sort by trigger_time descending (newest first)
    df = df.sort_values("trigger_time", ascending=False).reset_index(drop=True)

    return df


def main():
    df = fetch_summary()
    df = transform(df)

    n_total = len(df)
    print(f"  {n_total:,} GRBs total")

    # Stats
    n_short = int((df["duration_class"] == "short").sum())
    n_long = int((df["duration_class"] == "long").sum())
    n_with_z = int(df["redshift"].notna().sum())
    n_gbm = int(df["gbm_located"].sum())
    date_min = df["trigger_time"].min()
    date_max = df["trigger_time"].max()
    date_range = f"{date_min:%Y-%m-%d} to {date_max:%Y-%m-%d}"

    print(f"  {n_short:,} short, {n_long:,} long GRBs")
    print(f"  {n_with_z:,} with redshift")
    print(f"  Date range: {date_range}")

    check_dataset(df, "grbweb", min_rows=2_000,
                  expected_columns=["grb_name", "trigger_time", "ra", "dec",
                                    "t90", "fluence", "redshift"],
                  critical_columns=["grb_name", "trigger_time"])

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "grbweb.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        brightest_idx = df["fluence"].idxmax()
        brightest_name = df.loc[brightest_idx, "grb_name"] if pd.notna(brightest_idx) else "N/A"
        brightest_fluence = df.loc[brightest_idx, "fluence"] if pd.notna(brightest_idx) else 0

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "GRBweb Unified Multi-Instrument GRB Catalog"
language:
  - en
description: "Unified gamma-ray burst catalog from GRBweb combining Fermi, Swift, BATSE, BeppoSAX, IPN, and other detectors"
task_categories:
  - tabular-classification
tags:
  - space
  - grb
  - gamma-ray-bursts
  - multi-instrument
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
        path: data/grbweb.parquet
    default: true
---

# GRBweb Unified Multi-Instrument GRB Catalog

*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

Unified catalog of **{n_total:,}** gamma-ray bursts detected across multiple space missions,
sourced from the [GRBweb](https://user-web.icecube.wisc.edu/~grbweb_public/) database maintained
by the IceCube Collaboration. Combines data from **Fermi GBM**, **Swift BAT**, **BATSE**,
**BeppoSAX**, **IPN**, and other instruments into a single deduplicated catalog.

## Dataset description

Gamma-ray bursts (GRBs) are the most energetic explosions in the universe. Different space
missions have detected GRBs since the early 1990s, but each instrument covers different
energy ranges, sky regions, and time periods. GRBweb unifies detections across all major
GRB instruments, providing a single cross-referenced catalog with consistent columns for
position, duration, fluence, and redshift.

Currently **{n_total:,}** GRBs ({n_short:,} short, {n_long:,} long), of which
**{n_with_z:,}** have measured redshifts. Date range: **{date_range}**.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `grb_name` | string | Canonical GRB name (e.g. "GRB260326A") |
| `grb_name_fermi` | string | Fermi GBM trigger name (null if not detected by Fermi) |
| `t0_utc` | string | Trigger time (UTC, HH:MM:SS.sss) |
| `ra` | float | Right ascension (degrees, J2000) |
| `dec` | float | Declination (degrees, J2000) |
| `pos_error` | float | Position uncertainty (degrees, 1-sigma) |
| `t90` | float | T90 duration (s) — time containing 90% of fluence |
| `t90_error` | float | T90 uncertainty (s) |
| `t90_start` | string | T90 interval start time (UTC) |
| `fluence` | float | Total fluence (erg/cm^2) |
| `fluence_error` | float | Fluence uncertainty (erg/cm^2) |
| `redshift` | float | Spectroscopic or photometric redshift |
| `t100` | float | T100 duration (s) — total burst duration |
| `gbm_located` | bool | Whether Fermi GBM provided the localization |
| `mjd` | float | Modified Julian Date of trigger |
| `trigger_time` | datetime | Trigger time as datetime (derived from MJD) |
| `duration_class` | string | "short" (T90 < 2 s) or "long" (T90 >= 2 s) |

## Quick stats

- **{n_total:,}** gamma-ray bursts from multiple instruments
- **{n_short:,}** short GRBs, **{n_long:,}** long GRBs
- **{n_with_z:,}** with measured redshift
- **{n_gbm:,}** with Fermi GBM localization
- Date range: **{date_range}**
- Brightest burst: **{brightest_name}** (fluence {brightest_fluence:.2e} erg/cm^2)

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/grbweb-unified-grb-catalog", split="train")
df = ds.to_pandas()

# Short vs long GRBs
short = df[df["duration_class"] == "short"]
long = df[df["duration_class"] == "long"]
print(f"{{len(short):,}} short, {{len(long):,}} long GRBs")

# GRBs with measured redshift
z_known = df[df["redshift"].notna()]
print(f"{{len(z_known):,}} GRBs with redshift (z_max={{z_known['redshift'].max():.2f}})")

# T90 distribution
import matplotlib.pyplot as plt
df["t90"].dropna().apply(lambda x: max(x, 1e-3)).hist(bins=50, log=True)
plt.xlabel("T90 (s)")
plt.title("GRB Duration Distribution (GRBweb)")
```

## Data source

[GRBweb](https://user-web.icecube.wisc.edu/~grbweb_public/) — unified GRB database maintained
by the IceCube Collaboration at the University of Wisconsin-Madison. Combines detections from
Fermi GBM, Swift BAT, CGRO/BATSE, BeppoSAX, INTEGRAL, IPN, and other missions.

## Update schedule

Static dataset, rebuilt monthly. Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets).

## Related datasets

- [gamma-ray-bursts](https://huggingface.co/datasets/juliensimon/gamma-ray-bursts) — Fermi GBM Burst Catalog
- [fermi-4fgl](https://huggingface.co/datasets/juliensimon/fermi-4fgl) — Fermi LAT 4FGL Source Catalog
- [near-earth-objects](https://huggingface.co/datasets/juliensimon/near-earth-objects) — NEO close approaches

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/grbweb-unified-grb-catalog) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{grbweb_unified,
  author = {{Simon, Julien}},
  title = {{GRBweb Unified Multi-Instrument GRB Catalog}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/grbweb-unified-grb-catalog}},
  note = {{Based on GRBweb data from IceCube/University of Wisconsin-Madison}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update GRBweb catalog: {n_total:,} GRBs"
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
