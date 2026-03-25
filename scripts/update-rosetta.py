#!/usr/bin/env python3
"""Fetch ESA Rosetta mission observation metadata from PSA EPN-TAP and upload to HF.

The catalog has ~8.3M records across multiple instruments. We query per instrument
and paginate large instruments (ROSINA, OSIRIS) using cursor-based pagination on
granule_uid to keep each query manageable.
"""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset

HF_REPO = "juliensimon/esa-rosetta-observations"
TAP_URL = "https://psa.esa.int/psa-tap/tap/sync"
PAGE_SIZE = 500_000
REQUEST_TIMEOUT = 600  # 10 min per request


# ── Instruments ordered by expected size (largest first) ─────────────────────
INSTRUMENTS = [
    "ROSINA",
    "OSIRIS",
    "RPC",
    "ALICE",
    "MIRO",
    "VIRTIS",
    "GIADA",
    "CONSERT",
    "COSIMA",
    "LANDER",
    "NAVCAM",
    "RSI",
    "SREM",
]


def fetch_page(adql: str) -> pd.DataFrame:
    """Execute a single synchronous TAP query, return a DataFrame."""
    resp = requests.post(TAP_URL, data={
        "REQUEST": "doQuery",
        "LANG": "ADQL",
        "FORMAT": "json",
        "QUERY": adql,
    }, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()

    payload = resp.json()
    if "data" not in payload or "metadata" not in payload:
        print(f"::error::Unexpected TAP response keys: {list(payload.keys())}")
        sys.exit(1)

    columns = [col["name"] for col in payload["metadata"]]
    return pd.DataFrame(payload["data"], columns=columns)


def fetch_instrument(instrument: str) -> pd.DataFrame:
    """Fetch all rows for one instrument, paginating via granule_uid cursor."""
    print(f"  Fetching {instrument}...")

    # First page
    adql = (
        f"SELECT TOP {PAGE_SIZE} * FROM epn_core "
        f"WHERE instrument_host_name = 'Rosetta' "
        f"AND instrument_name = '{instrument}' "
        f"ORDER BY granule_uid"
    )
    df = fetch_page(adql)
    print(f"    {instrument}: {len(df):,} rows (page 1)")

    if len(df) < PAGE_SIZE:
        return df

    # Need pagination
    all_dfs = [df]
    page = 2
    while True:
        last_uid = df["granule_uid"].max()
        adql = (
            f"SELECT TOP {PAGE_SIZE} * FROM epn_core "
            f"WHERE instrument_host_name = 'Rosetta' "
            f"AND instrument_name = '{instrument}' "
            f"AND granule_uid > '{last_uid}' "
            f"ORDER BY granule_uid"
        )
        time.sleep(1)
        df = fetch_page(adql)
        if len(df) == 0:
            break
        all_dfs.append(df)
        total = sum(len(d) for d in all_dfs)
        print(f"    {instrument}: {total:,} rows (page {page})")
        page += 1

    result = pd.concat(all_dfs, ignore_index=True)
    print(f"    {instrument} total: {len(result):,} rows")
    return result


def main():
    # ── Sanity check: total count ────────────────────────────────────────
    print("Checking total record count...")
    count_adql = (
        "SELECT COUNT(*) AS cnt FROM epn_core "
        "WHERE instrument_host_name = 'Rosetta'"
    )
    count_df = fetch_page(count_adql)
    total_expected = int(count_df["cnt"].iloc[0])
    print(f"  ESA PSA reports {total_expected:,} Rosetta observations")

    # ── Instrument breakdown ─────────────────────────────────────────────
    print("Fetching instrument breakdown...")
    breakdown_adql = (
        "SELECT instrument_name, COUNT(*) AS cnt FROM epn_core "
        "WHERE instrument_host_name = 'Rosetta' "
        "GROUP BY instrument_name ORDER BY cnt DESC"
    )
    time.sleep(1)
    breakdown = fetch_page(breakdown_adql)
    print("  Instruments:")
    for _, row in breakdown.iterrows():
        print(f"    {row['instrument_name']}: {int(row['cnt']):,}")

    # Use actual instruments from breakdown (in case list differs)
    actual_instruments = breakdown["instrument_name"].tolist()

    # ── Fetch all instruments ────────────────────────────────────────────
    print(f"\nFetching {len(actual_instruments)} instruments...")
    all_dfs = []
    for instrument in actual_instruments:
        time.sleep(1)
        df = fetch_instrument(instrument)
        all_dfs.append(df)

    df = pd.concat(all_dfs, ignore_index=True)
    print(f"\nTotal fetched: {len(df):,} observations")

    # ── Transform ────────────────────────────────────────────────────────
    # Ensure instrument_name column exists (it should from epn_core)
    if "instrument_name" not in df.columns:
        print("::error::instrument_name column missing from epn_core")
        sys.exit(1)

    # Convert numeric columns — skip known string columns, try coercion on the rest
    for col in df.columns:
        if col in ["granule_uid", "granule_gid", "obs_id", "dataproduct_type",
                    "target_name", "target_class", "instrument_host_name",
                    "instrument_name", "measurement_type", "processing_level",
                    "service_title", "access_url", "access_format",
                    "spatial_frame_type", "time_scale", "publisher",
                    "bib_reference", "creation_date", "modification_date",
                    "release_date", "thumbnail_url", "file_name",
                    "species", "alt_target_name", "access_estsize",
                    "access_md5", "time_sampling_step_min",
                    "time_sampling_step_max", "time_exp_min", "time_exp_max",
                    "spectral_range_min", "spectral_range_max",
                    "spectral_sampling_step_min", "spectral_sampling_step_max",
                    "spectral_resolution_min", "spectral_resolution_max"]:
            continue  # skip string / already-typed columns
        # Try numeric coercion on remaining columns
        if df[col].dtype == object:
            converted = pd.to_numeric(df[col], errors="coerce")
            if converted.notna().sum() > converted.isna().sum():
                df[col] = converted

    # Parse time columns
    for col in ["time_min", "time_max"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Parse date columns
    for col in ["creation_date", "modification_date", "release_date"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True).dt.strftime(
                "%Y-%m-%dT%H:%M:%S"
            )

    # Clean string columns
    str_cols = df.select_dtypes(include=["object"]).columns
    for col in str_cols:
        df[col] = df[col].astype(str).str.strip().replace(
            {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
        )

    # Deduplicate by granule_uid (should be unique)
    before = len(df)
    df = df.drop_duplicates(subset=["granule_uid"], keep="first")
    if len(df) < before:
        print(f"  Removed {before - len(df):,} duplicate granule_uids")

    df = df.sort_values("granule_uid").reset_index(drop=True)

    # ── Stats ────────────────────────────────────────────────────────────
    n = len(df)
    n_instruments = df["instrument_name"].nunique() if "instrument_name" in df.columns else 0
    top_instruments = (
        df["instrument_name"].value_counts().head(5).to_dict()
        if "instrument_name" in df.columns else {}
    )
    n_targets = df["target_name"].nunique() if "target_name" in df.columns else 0
    top_targets = (
        df["target_name"].value_counts().head(5).to_dict()
        if "target_name" in df.columns else {}
    )

    print(f"\n  {n:,} observations, {n_instruments} instruments, {n_targets} targets")

    # ── Validate ─────────────────────────────────────────────────────────
    check_dataset(
        df, "rosetta", min_rows=5_000_000,
        expected_columns=["granule_uid", "instrument_name", "target_name"],
        critical_columns=["granule_uid", "instrument_name"],
    )

    # ── Write & upload ───────────────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "rosetta_observations.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        # Format top instruments/targets for README
        top_inst_lines = "\n".join(
            f"  - **{name}**: {count:,}" for name, count in top_instruments.items()
        )
        top_target_lines = "\n".join(
            f"  - **{name}**: {count:,}" for name, count in top_targets.items()
        )

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "ESA Rosetta Mission Observations"
language:
  - en
description: >-
  Complete observation metadata catalog from ESA's Rosetta mission to comet
  67P/Churyumov-Gerasimenko — {n:,} instrument observations covering 12 years of
  operations (2004-2016). Sourced from the ESA Planetary Science Archive.
size_categories:
  - 1M<n<10M
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - rosetta
  - comet
  - 67p
  - esa
  - planetary-science
  - open-data
  - tabular-data
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/rosetta_observations.parquet
    default: true
---

# ESA Rosetta Mission Observations

*Part of the [Planetary Science Datasets](https://huggingface.co/collections/juliensimon/planetary-science-datasets-69c2d4683bd6a66c34fb4af2) collection on Hugging Face.*

The complete observation metadata catalog from ESA's Rosetta mission — **{n:,}**
individual instrument observations spanning the entire mission from launch (2004) through
end of mission at comet 67P/Churyumov-Gerasimenko (2016).

## Dataset description

Rosetta was ESA's cornerstone mission to study comet 67P/Churyumov-Gerasimenko up close.
Launched in March 2004, it entered orbit around 67P in August 2014 and deployed the Philae
lander in November 2014. The mission ended with a controlled descent onto the comet surface
on 30 September 2016. Rosetta carried 11 orbiter instruments and 10 lander instruments,
generating an enormous archive of observations covering the comet nucleus, coma, solar wind
interaction, dust environment, and surface composition.

This dataset contains the full EPN-TAP metadata for every Rosetta observation in the ESA
Planetary Science Archive, including observation times, target information, spatial coverage,
instrument parameters, and data product access URLs.

## Quick stats

- **{n:,}** total observations
- **{n_instruments}** instruments
- **{n_targets}** distinct targets

### Top instruments
{top_inst_lines}

### Top targets
{top_target_lines}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/esa-rosetta-observations", split="train")
df = ds.to_pandas()

# Observations per instrument
print(df["instrument_name"].value_counts())

# OSIRIS camera observations of 67P
osiris = df[(df["instrument_name"] == "OSIRIS") & (df["target_name"].str.contains("67P", na=False))]
print(f"{{len(osiris):,}} OSIRIS observations of 67P")

# Timeline: observations per month (using Julian Date time_min)
import matplotlib.pyplot as plt
valid = df[df["time_min"].notna()].copy()
valid["year"] = ((valid["time_min"] - 2451545.0) / 365.25 + 2000).astype(int)
valid.groupby("year").size().plot(kind="bar")
plt.xlabel("Year")
plt.ylabel("Observations")
plt.title("Rosetta Observations per Year")
```

## Data source

[ESA Planetary Science Archive](https://psa.esa.int/) — EPN-TAP service.
Query: `SELECT * FROM epn_core WHERE instrument_host_name = 'Rosetta'`

## Related datasets

- [lunar-craters-robbins](https://huggingface.co/datasets/juliensimon/lunar-craters-robbins) -- Lunar impact craters
- [mars-craters-robbins](https://huggingface.co/datasets/juliensimon/mars-craters-robbins) -- Mars impact craters

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Citation

```bibtex
@dataset{{esa_rosetta_observations,
  author = {{Simon, Julien}},
  title = {{ESA Rosetta Mission Observations}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/esa-rosetta-observations}},
  note = {{Based on ESA Planetary Science Archive EPN-TAP metadata}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Upload Rosetta observations: {n:,} records"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={n}\n")
    print("Done.")


if __name__ == "__main__":
    main()
