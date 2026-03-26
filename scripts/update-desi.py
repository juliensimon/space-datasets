#!/usr/bin/env python3
"""Fetch DESI DR1 Bright Galaxy Survey redshifts from NOIRLab and upload to HF."""

import io
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset

TAP_URL = "https://datalab.noirlab.edu/tap/sync"
HF_REPO = "juliensimon/desi-dr1-redshifts"

COLUMNS = (
    "targetid, mean_fiber_ra, mean_fiber_dec, z, zerr, zwarn, "
    "spectype, subtype, survey, program, deltachi2, chi2, "
    "coadd_numexp, coadd_numnight, coadd_numtile, coadd_exptime"
)

BASE_WHERE = (
    "survey = 'main' AND program = 'bright' "
    "AND zwarn = 0 AND main_primary = 't'"
)

CHUNK_SIZE = 500_000
MAX_ROWS = 5_000_000


def fetch_chunk(offset: int, limit: int) -> pd.DataFrame:
    """Fetch a single chunk using TOP/OFFSET."""
    adql = (
        f"SELECT TOP {limit} {COLUMNS} "
        f"FROM desi_dr1.zpix "
        f"WHERE {BASE_WHERE} "
        f"OFFSET {offset}"
    )
    for attempt in range(3):
        try:
            resp = requests.get(
                TAP_URL,
                params={
                    "REQUEST": "doQuery",
                    "LANG": "ADQL",
                    "FORMAT": "csv",
                    "QUERY": adql,
                },
                timeout=600,
            )
            resp.raise_for_status()
            if resp.text.strip().startswith("<?xml"):
                raise RuntimeError(f"Got VOTable error: {resp.text[:300]}")
            df = pd.read_csv(io.StringIO(resp.text))
            return df
        except Exception as e:
            print(f"  Chunk offset={offset} attempt {attempt+1} failed: {e}")
            if attempt < 2:
                time.sleep(5 * (attempt + 1))
    print(f"::error::Failed to fetch chunk at offset {offset} after 3 attempts")
    sys.exit(1)


def fetch_catalog() -> pd.DataFrame:
    """Fetch DESI DR1 BGS in chunks."""
    print("Fetching DESI DR1 Bright Galaxy Survey redshifts...")

    # Get total count
    count_query = f"SELECT COUNT(*) as cnt FROM desi_dr1.zpix WHERE {BASE_WHERE}"
    resp = requests.get(
        TAP_URL,
        params={
            "REQUEST": "doQuery",
            "LANG": "ADQL",
            "FORMAT": "csv",
            "QUERY": count_query,
        },
        timeout=120,
    )
    resp.raise_for_status()
    total = int(pd.read_csv(io.StringIO(resp.text))["cnt"].iloc[0])
    target = min(total, MAX_ROWS)
    print(f"  Total available: {total:,}, fetching up to {target:,}")

    chunks = []
    offset = 0
    while offset < target:
        limit = min(CHUNK_SIZE, target - offset)
        t0 = time.time()
        chunk = fetch_chunk(offset, limit)
        elapsed = time.time() - t0
        chunks.append(chunk)
        print(f"  Chunk {len(chunks)}: {len(chunk):,} rows "
              f"(offset {offset:,}, {elapsed:.1f}s)")
        if len(chunk) < limit:
            break  # no more data
        offset += limit
        time.sleep(1)  # be polite

    df = pd.concat(chunks, ignore_index=True)
    print(f"  Total fetched: {len(df):,} rows")
    return df


def main():
    df = fetch_catalog()

    # Rename columns for clarity
    df = df.rename(columns={
        "mean_fiber_ra": "ra",
        "mean_fiber_dec": "dec",
        "z": "redshift",
        "zerr": "redshift_err",
        "zwarn": "redshift_warn",
    })

    # Ensure numeric types
    for col in ["ra", "dec", "redshift", "redshift_err", "deltachi2", "chi2",
                "coadd_exptime"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in ["coadd_numexp", "coadd_numnight", "coadd_numtile"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int16")

    # Clean string columns
    for col in ["spectype", "subtype"]:
        if col in df.columns:
            df[col] = (
                df[col].astype(str).str.strip()
                .replace({"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA})
            )

    # Drop columns that are constant after filtering
    df = df.drop(columns=["redshift_warn", "survey", "program"], errors="ignore")

    # Sort by targetid for reproducibility
    df = df.sort_values("targetid").reset_index(drop=True)

    # Stats
    n_total = len(df)
    n_galaxy = int((df["spectype"] == "GALAXY").sum())
    n_star = int((df["spectype"] == "STAR").sum())
    n_qso = int((df["spectype"] == "QSO").sum())
    median_z = df["redshift"].median()
    mean_z = df["redshift"].mean()

    print(f"  {n_total:,} sources: {n_galaxy:,} galaxies, {n_star:,} stars, {n_qso:,} QSOs")
    print(f"  Median redshift: {median_z:.4f}, Mean redshift: {mean_z:.4f}")

    check_dataset(
        df, "desi-dr1-redshifts", min_rows=1_000_000,
        expected_columns=["targetid", "ra", "dec", "redshift", "redshift_err",
                          "spectype", "deltachi2"],
        critical_columns=["targetid", "ra", "dec", "redshift"],
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "desi-dr1-redshifts.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "DESI DR1 Bright Galaxy Survey Redshifts"
language:
  - en
description: "Spectroscopic redshifts from the Dark Energy Spectroscopic Instrument (DESI) Data Release 1 — Bright Galaxy Survey subset with reliable measurements (zwarn=0). The largest spectroscopic survey ever conducted."
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - galaxies
  - redshifts
  - desi
  - spectroscopy
  - cosmology
  - astronomy
  - open-data
  - tabular-data
size_categories:
  - 1M<n<10M
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/desi-dr1-redshifts.parquet
    default: true
---

# DESI DR1 Bright Galaxy Survey Redshifts

*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

Spectroscopic redshifts from the [Dark Energy Spectroscopic Instrument](https://www.desi.lbl.gov/)
(DESI) Data Release 1 — the **largest spectroscopic survey ever conducted**.
This dataset contains the **Bright Galaxy Survey (BGS)** subset: **{n_total:,}** sources
with reliable redshift measurements (`zwarn=0`, `main_primary=true`).

## Dataset description

DESI is a robotic fiber-fed spectrograph on the Mayall 4-meter telescope at
Kitt Peak National Observatory, capable of measuring 5,000 spectra simultaneously.
DR1 contains 28.4 million unique spectroscopic redshifts from 14,600+ square degrees.

The Bright Galaxy Survey targets galaxies with r < 19.5 magnitude during bright
lunar conditions. This curated subset includes only the main survey observations
with reliable redshift fits (zero warning flags) and primary measurements
(no duplicates).

**Breakdown by spectral type:**
- **{n_galaxy:,}** galaxies ({100*n_galaxy/n_total:.1f}%)
- **{n_star:,}** stars ({100*n_star/n_total:.1f}%)
- **{n_qso:,}** QSOs ({100*n_qso/n_total:.1f}%)

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `targetid` | int64 | Unique DESI target identifier |
| `ra` | float64 | Right ascension — fiber position (degrees) |
| `dec` | float64 | Declination — fiber position (degrees) |
| `redshift` | float64 | Best-fit spectroscopic redshift |
| `redshift_err` | float64 | Redshift uncertainty |
| `spectype` | string | Spectral classification: GALAXY, STAR, or QSO |
| `subtype` | string | Spectral subtype (e.g., stellar type K, G, F) |
| `deltachi2` | float64 | Chi-squared difference between best and second-best fit |
| `chi2` | float64 | Best-fit chi-squared |
| `coadd_numexp` | int16 | Number of coadded exposures |
| `coadd_numnight` | int16 | Number of observation nights |
| `coadd_numtile` | int16 | Number of observed tiles |
| `coadd_exptime` | float32 | Total coadded exposure time (seconds) |

## Quick stats

- **{n_total:,}** sources with reliable redshifts
- Median redshift: **{median_z:.4f}**
- Mean redshift: **{mean_z:.4f}**
- **{n_galaxy:,}** galaxies, **{n_star:,}** stars, **{n_qso:,}** QSOs
- Sky coverage: ~14,600 square degrees

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/desi-dr1-redshifts", split="train")
df = ds.to_pandas()

# Galaxy redshift distribution
galaxies = df[df["spectype"] == "GALAXY"]
print(f"{{len(galaxies):,}} galaxies, median z = {{galaxies['redshift'].median():.4f}}")

# Redshift histogram
import matplotlib.pyplot as plt
galaxies["redshift"].hist(bins=200, range=(0, 0.6))
plt.xlabel("Redshift")
plt.ylabel("Count")
plt.title("DESI BGS Galaxy Redshift Distribution")

# Sky coverage plot
plt.figure(figsize=(12, 6))
plt.scatter(df["ra"], df["dec"], s=0.01, alpha=0.1)
plt.xlabel("RA (deg)")
plt.ylabel("Dec (deg)")
plt.title("DESI DR1 BGS Sky Coverage")
```

## Data source

All data comes from the [DESI Data Release 1](https://data.desi.lbl.gov/doc/releases/dr1/)
via the [NOIRLab Astro Data Lab](https://datalab.noirlab.edu/) TAP service.

DESI Collaboration (2025). "The DESI Data Release 1." arXiv:2503.14745.

## Related datasets

- [sdss-dr18-spectra](https://huggingface.co/datasets/juliensimon/sdss-dr18-spectra) — SDSS DR18 optical spectroscopy
- [exoplanet-archive](https://huggingface.co/datasets/juliensimon/exoplanet-archive) — NASA Exoplanet Archive

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Citation

```bibtex
@dataset{{desi_dr1_redshifts,
  author = {{Simon, Julien}},
  title = {{DESI DR1 Bright Galaxy Survey Redshifts}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/desi-dr1-redshifts}},
  note = {{Based on DESI DR1 (DESI Collaboration 2025) via NOIRLab Astro Data Lab}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Upload DESI DR1 BGS redshifts: {n_total:,} sources"
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
