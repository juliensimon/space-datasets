#!/usr/bin/env python3
"""Fetch ESA JUICE observation catalog from PSA and upload to HF."""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pandas as pd
import requests

from dataset_images import banner_markdown, download_banner
from validate import check_dataset


TAP_URL = "https://psa.esa.int/psa-tap/tap/sync"
HF_REPO = "juliensimon/esa-juice-observations"

# JUICE instruments in order of expected catalog size
INSTRUMENTS = ["JMC", "RADEM", "HAA", "NAVCAM"]

PAGE_SIZE = 50_000


def try_epn_core() -> bool:
    """Try a COUNT query on epn_core to see if it responds in time."""
    query = ("SELECT COUNT(*) AS n FROM epn_core "
             "WHERE instrument_host_name LIKE '%JUICE%'")
    print("Testing epn_core availability...")
    try:
        resp = requests.get(TAP_URL, params={
            "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "json",
            "QUERY": query,
        }, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        cols = [m["name"] for m in data["metadata"]]
        rows = data["data"]
        n = int(rows[0][cols.index("n")])
        print(f"  epn_core returns {n:,} JUICE rows")
        return n > 0
    except (requests.exceptions.Timeout, requests.exceptions.RequestException) as e:
        print(f"  epn_core query failed: {e}")
        return False


def fetch_epn_core() -> pd.DataFrame:
    """Fetch all JUICE rows from epn_core, paginated by granule_uid."""
    print("Fetching from epn_core...")
    all_dfs = []
    last_id = ""
    page = 0

    while True:
        query = (
            f"SELECT TOP {PAGE_SIZE} * FROM epn_core "
            f"WHERE instrument_host_name LIKE '%JUICE%' "
            f"AND granule_uid > '{last_id}' "
            f"ORDER BY granule_uid"
        )
        resp = requests.get(TAP_URL, params={
            "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "json",
            "QUERY": query,
        }, timeout=300)
        resp.raise_for_status()

        data = resp.json()
        cols = [m["name"] for m in data["metadata"]]
        rows = data["data"]

        if not rows:
            break

        df_page = pd.DataFrame(rows, columns=cols)
        all_dfs.append(df_page)
        page += 1
        print(f"  Page {page}: {len(df_page):,} rows")

        if len(df_page) < PAGE_SIZE:
            break

        last_id = str(df_page["granule_uid"].iloc[-1])
        time.sleep(1)

    if not all_dfs:
        return pd.DataFrame()

    df = pd.concat(all_dfs, ignore_index=True)
    print(f"  epn_core total: {len(df):,} rows")
    return df


def fetch_product_ui_juice() -> pd.DataFrame:
    """Fallback: fetch from psa.product_ui_juice table."""
    print("Falling back to psa.product_ui_juice...")
    all_dfs = []
    offset = 0
    page = 0

    while True:
        query = (
            f"SELECT TOP {PAGE_SIZE} * FROM psa.product_ui_juice "
            f"WHERE 1=1 "
            f"OFFSET {offset}"
        )
        resp = requests.get(TAP_URL, params={
            "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "json",
            "QUERY": query,
        }, timeout=300)
        resp.raise_for_status()

        data = resp.json()
        cols = [m["name"] for m in data["metadata"]]
        rows = data["data"]

        if not rows:
            break

        df_page = pd.DataFrame(rows, columns=cols)
        all_dfs.append(df_page)
        page += 1
        print(f"  Page {page}: {len(df_page):,} rows")

        if len(df_page) < PAGE_SIZE:
            break

        offset += PAGE_SIZE
        time.sleep(1)

    if not all_dfs:
        return pd.DataFrame()

    df = pd.concat(all_dfs, ignore_index=True)
    print(f"  product_ui_juice total: {len(df):,} rows")
    return df


def main():
    print("Fetching ESA JUICE observation catalog...")

    # Strategy 1: try epn_core
    df = pd.DataFrame()
    if try_epn_core():
        df = fetch_epn_core()
        time.sleep(2)

    # Strategy 2: fallback to product_ui_juice
    if df.empty:
        print("epn_core returned no data, trying product_ui_juice...")
        df = fetch_product_ui_juice()

    if df.empty:
        print("::error::No data fetched from either source")
        sys.exit(1)

    print(f"  Total fetched: {len(df):,} rows")

    # ── Column cleanup ────────────────────────────────────────────────
    df.columns = [c.strip().lower() for c in df.columns]

    # Coerce numeric columns (EPN-TAP standard fields)
    numeric_cols = [
        "time_min", "time_max", "time_sampling_step_min",
        "time_sampling_step_max", "time_exp_min", "time_exp_max",
        "spectral_range_min", "spectral_range_max",
        "spectral_sampling_step_min", "spectral_sampling_step_max",
        "spectral_resolution_min", "spectral_resolution_max",
        "c1min", "c1max", "c2min", "c2max", "c3min", "c3max",
        "c1_resol_min", "c1_resol_max", "c2_resol_min", "c2_resol_max",
        "c3_resol_min", "c3_resol_max",
        "s_region_lon_min", "s_region_lon_max",
        "s_region_lat_min", "s_region_lat_max",
        "incidence_min", "incidence_max",
        "emergence_min", "emergence_max",
        "phase_min", "phase_max",
        "ra_min", "ra_max", "dec_min", "dec_max",
        "solar_longitude_min", "solar_longitude_max",
        "sun_distance_min", "sun_distance_max",
        "target_distance_min", "target_distance_max",
        "subsolar_longitude_min", "subsolar_longitude_max",
        "subsolar_latitude_min", "subsolar_latitude_max",
        "subobserver_longitude_min", "subobserver_longitude_max",
        "subobserver_latitude_min", "subobserver_latitude_max",
        "local_time_min", "local_time_max",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Clean string columns
    string_cols = [
        "granule_uid", "granule_gid", "obs_id",
        "dataproduct_type", "target_name", "target_class",
        "instrument_host_name", "instrument_name",
        "measurement_type", "processing_level",
        "creation_date", "modification_date", "release_date",
        "service_title", "access_url", "access_format",
        "thumbnail_url", "bib_reference",
    ]
    for col in string_cols:
        if col in df.columns:
            df[col] = (df[col].astype(str).str.strip()
                       .replace({"": pd.NA, "None": pd.NA,
                                 "nan": pd.NA, "null": pd.NA}))

    # Sort by observation start time
    if "time_min" in df.columns:
        df = df.sort_values("time_min", na_position="last").reset_index(drop=True)

    # ── Stats ─────────────────────────────────────────────────────────
    n_total = len(df)
    inst_col = "instrument_name" if "instrument_name" in df.columns else None
    target_col = "target_name" if "target_name" in df.columns else None

    n_instruments = df[inst_col].nunique() if inst_col else 0
    instruments_summary = (df[inst_col].value_counts()
                           .head(10).to_dict()) if inst_col else {}
    n_targets = df[target_col].nunique() if target_col else 0
    time_range_min = df["time_min"].min() if "time_min" in df.columns else None
    time_range_max = df["time_max"].max() if "time_max" in df.columns else None

    print(f"  {n_total:,} observations across {n_instruments} instruments")
    for inst, count in instruments_summary.items():
        print(f"    {inst}: {count:,}")

    # Drop columns that are >95% null
    before_cols = len(df.columns)
    for col in list(df.columns):
        if df[col].isna().mean() > 0.95:
            df = df.drop(columns=[col])
    dropped = before_cols - len(df.columns)
    if dropped:
        print(f"  Dropped {dropped} columns (>95% null)")

    # ── Validate ──────────────────────────────────────────────────────
    expected = ["granule_uid", "instrument_name", "target_name",
                "time_min", "time_max", "dataproduct_type"]
    # Only require columns that actually exist (fallback table may differ)
    expected = [c for c in expected if c in df.columns]
    critical = [c for c in ["granule_uid", "instrument_name", "time_min"]
                if c in df.columns]

    check_dataset(df, "juice", min_rows=1_000,
                  expected_columns=expected,
                  critical_columns=critical)

    # ── Write & upload ────────────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "juice_observations.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        # Format instrument breakdown for README
        inst_lines = "\n".join(
            f"- **{inst}**: {count:,} observations"
            for inst, count in instruments_summary.items()
        )

        time_info = ""
        if time_range_min is not None and time_range_max is not None:
            time_info = f"- Time span: JD {time_range_min:.1f} \u2013 {time_range_max:.1f}"

        banner_file = download_banner("juice", tmp)
        banner_md = banner_markdown("juice", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "ESA JUICE Observations"
language:
  - en
description: "Observation metadata catalog from ESA's JUICE (Jupiter Icy Moons Explorer) mission ({n_total:,} observations across {n_instruments} instruments). Updated weekly from the ESA Planetary Science Archive."
task_categories:
  - tabular-classification
tags:
  - space
  - jupiter
  - juice
  - ganymede
  - europa
  - callisto
  - esa
  - planetary-science
  - open-data
  - tabular-data
  - parquet
size_categories:
  - 1K<n<10K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/juice_observations.parquet
    default: true
---

# ESA JUICE Observations
{banner_md}
*Part of the [Solar System Datasets](https://huggingface.co/collections/juliensimon/solar-system-datasets-67d1e55a1e4f1d1e4a08d43b) and [Planetary Science Datasets](https://huggingface.co/collections/juliensimon/planetary-science-datasets-69c24cb17e3db14fc30f0716) collections on Hugging Face.*

![Update JUICE](https://github.com/juliensimon/space-datasets/actions/workflows/update-juice.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['juice']&label=updated&color=brightgreen)

Observation metadata catalog from **ESA's JUICE** (Jupiter Icy Moons Explorer) mission \u2014 **{n_total:,}**
observations across {n_instruments} instruments during the cruise phase.

## Dataset description

JUICE (Jupiter Icy Moons Explorer) is ESA's flagship mission to the Jovian system, launched April 14, 2023. After gravity assists at Earth-Moon (August 2024), Venus (August 2025), and Earth (September 2026, January 2029), JUICE will arrive at Jupiter in July 2031 for a 3.5-year tour of the Galilean moons. The primary science target is Ganymede \u2014 the only moon with its own magnetic field \u2014 where JUICE will enter orbit in December 2034, becoming the first spacecraft to orbit a moon other than Earth's. The mission will characterize the subsurface oceans of Ganymede, Europa, and Callisto, assess their habitability, and study Jupiter's atmosphere and magnetosphere.

During the cruise phase, instruments are collecting calibration data and science observations during planetary flybys. Currently available data includes radiation measurements (RADEM), monitoring camera images (JMC), and heliospheric particle data (HAA). The dataset will grow dramatically as JUICE approaches Jupiter and begins its science phase.

## Instruments

{inst_lines}

## Schema (key columns)

| Column | Type | Description |
|--------|------|-------------|
| `granule_uid` | string | Unique observation identifier |
| `granule_gid` | string | Group identifier |
| `obs_id` | string | Observation ID |
| `dataproduct_type` | string | Data product type (e.g. spectrum, image) |
| `target_name` | string | Target body (Solar Wind, Sun, Earth, Venus, etc.) |
| `target_class` | string | Target class (interplanetary_medium, star, etc.) |
| `instrument_name` | string | Instrument name (JMC, RADEM, HAA, NAVCAM) |
| `time_min` | float64 | Observation start time (JD) |
| `time_max` | float64 | Observation end time (JD) |
| `processing_level` | string | Data processing level |
| `creation_date` | string | Data product creation date |
| `access_url` | string | URL to access the data product |
| `access_format` | string | Data format |

## Quick stats

- **{n_total:,}** total observations
- **{n_instruments}** instruments
- **{n_targets}** distinct targets
{time_info}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/esa-juice-observations", split="train")
df = ds.to_pandas()

# Observations per instrument
print(df["instrument_name"].value_counts())

# RADEM radiation measurements
radem = df[df["instrument_name"] == "RADEM"]
print(f"{{len(radem):,}} RADEM observations")

# Observations per target
print(df["target_name"].value_counts())
```

## Data source

[ESA Planetary Science Archive](https://psa.esa.int/) \u2014 EPN-TAP service at
`https://psa.esa.int/psa-tap/tap/sync`.

## Update schedule

Weekly (Monday at 10:00 UTC) via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [esa-rosetta-observations](https://huggingface.co/datasets/juliensimon/esa-rosetta-observations) \u2014 ESA Rosetta comet mission
- [esa-bepicolombo-observations](https://huggingface.co/datasets/juliensimon/esa-bepicolombo-observations) \u2014 ESA BepiColombo Mercury mission
- [galileo-atmosphere](https://huggingface.co/datasets/juliensimon/galileo-atmosphere) \u2014 Galileo atmospheric probe
- [solar-system-moons](https://huggingface.co/datasets/juliensimon/solar-system-moons) \u2014 Solar system moons catalog

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a \u2764\ufe0f on the [dataset page](https://huggingface.co/datasets/juliensimon/esa-juice-observations) and share feedback in the Community tab! Also consider giving a \u2b50\ufe0f to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{juice_observations,
  author = {{Simon, Julien}},
  title = {{ESA JUICE Observations}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/esa-juice-observations}},
  note = {{Based on ESA Planetary Science Archive (PSA) EPN-TAP service}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update JUICE observations: {n_total:,} observations"
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
