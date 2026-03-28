#!/usr/bin/env python3
"""Fetch ESA Mars Express observation catalog from PSA EPN-TAP and upload to HF."""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset


TAP_URL = "https://psa.esa.int/psa-tap/tap/sync"
HF_REPO = "juliensimon/esa-mars-express-observations"

# Mars Express instruments in order of expected catalog size
INSTRUMENTS = [
    "ASPERA-3",
    "HRSC",
    "VMC",
    "MaRS",
    "PFS",
    "SPICAM",
    "MARSIS",
    "OMEGA",
]

PAGE_SIZE = 500_000


def fetch_count() -> int:
    """Sanity-check: fetch total row count."""
    query = ("SELECT COUNT(*) AS n FROM epn_core "
             "WHERE instrument_host_name = 'Mars Express'")
    print("Checking total row count...")
    resp = requests.get(TAP_URL, params={
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "json",
        "QUERY": query,
    }, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    cols = [m["name"] for m in data["metadata"]]
    rows = data["data"]
    n = int(rows[0][cols.index("n")])
    print(f"  Total rows in catalog: {n:,}")
    return n


def fetch_instrument(instrument: str) -> pd.DataFrame:
    """Fetch all rows for one instrument using granule_uid pagination."""
    print(f"  Fetching {instrument}...")
    all_dfs = []
    last_id = ""
    page = 0

    while True:
        query = (
            f"SELECT TOP {PAGE_SIZE} * FROM epn_core "
            f"WHERE instrument_host_name = 'Mars Express' "
            f"AND instrument_name = '{instrument}' "
            f"AND granule_uid > '{last_id}' "
            f"ORDER BY granule_uid"
        )
        resp = requests.get(TAP_URL, params={
            "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "json",
            "QUERY": query,
        }, timeout=600)
        resp.raise_for_status()

        data = resp.json()
        cols = [m["name"] for m in data["metadata"]]
        rows = data["data"]

        if not rows:
            break

        df_page = pd.DataFrame(rows, columns=cols)
        all_dfs.append(df_page)
        page += 1
        print(f"    Page {page}: {len(df_page):,} rows")

        if len(df_page) < PAGE_SIZE:
            break

        last_id = str(df_page["granule_uid"].iloc[-1])
        time.sleep(1)  # Be polite to the server

    if not all_dfs:
        print(f"    WARNING: No rows for {instrument}")
        return pd.DataFrame()

    df = pd.concat(all_dfs, ignore_index=True)
    print(f"    {instrument} total: {len(df):,} rows")
    return df


def main():
    print("Fetching ESA Mars Express observation catalog...")

    # Verify expected size
    total_expected = fetch_count()

    # Fetch per instrument, then concatenate
    dfs = []
    for inst in INSTRUMENTS:
        df_inst = fetch_instrument(inst)
        if len(df_inst) > 0:
            dfs.append(df_inst)
        time.sleep(2)  # Pause between instruments

    if not dfs:
        print("::error::No data fetched")
        sys.exit(1)

    df = pd.concat(dfs, ignore_index=True)
    print(f"  Total fetched: {len(df):,} rows")

    # ── Column cleanup ────────────────────────────────────────────────
    # Columns already arrive in snake_case from EPN-TAP; ensure consistency
    df.columns = [c.strip().lower() for c in df.columns]

    # Coerce numeric columns
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
    df = df.sort_values("time_min", na_position="last").reset_index(drop=True)

    # ── Stats ─────────────────────────────────────────────────────────
    n_total = len(df)
    n_instruments = df["instrument_name"].nunique()
    instruments_summary = (df["instrument_name"].value_counts()
                           .head(8).to_dict())
    n_targets = df["target_name"].nunique() if "target_name" in df.columns else 0
    time_range_min = df["time_min"].min()
    time_range_max = df["time_max"].max()

    print(f"  {n_total:,} observations across {n_instruments} instruments")
    for inst, count in instruments_summary.items():
        print(f"    {inst}: {count:,}")

    # ── Validate ──────────────────────────────────────────────────────
    check_dataset(df, "mars-express", min_rows=1_000_000,
        expected_columns=["granule_uid", "instrument_name", "target_name",
                          "time_min", "time_max", "dataproduct_type"],
        critical_columns=["granule_uid", "instrument_name", "time_min"])

    # ── Write & upload ────────────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "mars_express_observations.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        # Format instrument breakdown for README
        inst_lines = "\n".join(
            f"- **{inst}**: {count:,} observations"
            for inst, count in instruments_summary.items()
        )

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "ESA Mars Express Observations"
language:
  - en
description: "Complete observation metadata catalog from the ESA Mars Express mission ({n_total:,} observations across {n_instruments} instruments), orbiting Mars since 2003. Updated weekly from the ESA Planetary Science Archive."
task_categories:
  - tabular-classification
tags:
  - space
  - mars
  - mars-express
  - esa
  - planetary-science
  - open-data
  - tabular-data
  - parquet
size_categories:
  - 1M<n<10M
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/mars_express_observations.parquet
    default: true
---

# ESA Mars Express Observations

*Part of the [Planetary Science Datasets](https://huggingface.co/collections/juliensimon/planetary-science-datasets-69c24cb17e3db14fc30f0716) collection on Hugging Face.*

![Update Mars Express](https://github.com/juliensimon/space-datasets/actions/workflows/update-mars-express.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['mars-express']&label=updated&color=brightgreen)

Complete observation metadata catalog from the **ESA Mars Express** mission \u2014 **{n_total:,}**
observations across {n_instruments} instruments, covering over two decades of Mars exploration
since the spacecraft entered orbit in December 2003.

## Dataset description

Mars Express is a European Space Agency mission that has been studying the Martian atmosphere,
surface, subsurface, and space environment since 2003. It carries a suite of instruments
including a high-resolution stereo camera (HRSC), radar sounder (MARSIS), infrared imaging
spectrometer (OMEGA), atmospheric spectrometers (PFS, SPICAM), plasma analyzer (ASPERA-3),
radio science experiment (MaRS), and visual monitoring camera (VMC).

This dataset contains the full observation metadata from the ESA Planetary Science Archive
(PSA), conforming to the EPN-TAP standard. Each row represents one observation or data
granule, with timing, spatial coverage, instrument parameters, and access URLs.

## Instruments

{inst_lines}

## Schema (key columns)

| Column | Type | Description |
|--------|------|-------------|
| `granule_uid` | string | Unique observation identifier |
| `granule_gid` | string | Group identifier |
| `obs_id` | string | Observation ID |
| `dataproduct_type` | string | Data product type (e.g. spectrum, image, profile) |
| `target_name` | string | Target body (Mars, Phobos, Deimos, etc.) |
| `target_class` | string | Target class (planet, satellite, etc.) |
| `instrument_name` | string | Instrument name (HRSC, MARSIS, OMEGA, etc.) |
| `time_min` | float64 | Observation start time (JD) |
| `time_max` | float64 | Observation end time (JD) |
| `c1min`/`c1max` | float64 | Spatial coordinate 1 range |
| `c2min`/`c2max` | float64 | Spatial coordinate 2 range |
| `spectral_range_min`/`max` | float64 | Spectral range bounds |
| `processing_level` | string | Data processing level |
| `creation_date` | string | Data product creation date |
| `access_url` | string | URL to access the data product |
| `access_format` | string | Data format (e.g. application/x-pds) |

The full schema contains up to ~50 columns following the EPN-TAP standard.

## Quick stats

- **{n_total:,}** total observations
- **{n_instruments}** instruments
- **{n_targets}** distinct targets
- Time span: JD {time_range_min:.1f} \u2013 {time_range_max:.1f}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/esa-mars-express-observations", split="train")
df = ds.to_pandas()

# Observations per instrument
print(df["instrument_name"].value_counts())

# HRSC images
hrsc = df[df["instrument_name"] == "HRSC"]
print(f"{{len(hrsc):,}} HRSC observations")

# Timeline of observations
import matplotlib.pyplot as plt
df["year"] = ((df["time_min"] - 2451545.0) / 365.25 + 2000).astype(int)
df.groupby(["year", "instrument_name"]).size().unstack().plot(kind="bar", stacked=True)
plt.title("Mars Express observations per year")
plt.ylabel("Count")
```

## Data source

[ESA Planetary Science Archive](https://psa.esa.int/) \u2014 EPN-TAP service at
`https://psa.esa.int/psa-tap/tap/sync`.

## Update schedule

Weekly (Monday at 07:00 UTC) via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [mars-craters](https://huggingface.co/datasets/juliensimon/mars-craters) \u2014 Robbins Mars crater catalog
- [exoplanet-archive](https://huggingface.co/datasets/juliensimon/exoplanet-archive) \u2014 NASA Exoplanet Archive
- [lunar-craters](https://huggingface.co/datasets/juliensimon/lunar-craters) \u2014 Lunar crater catalog

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/esa-mars-express-observations) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{mars_express_observations,
  author = {{Simon, Julien}},
  title = {{ESA Mars Express Observations}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/esa-mars-express-observations}},
  note = {{Based on ESA Planetary Science Archive (PSA) EPN-TAP service}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update Mars Express observations: {n_total:,} observations"
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
