#!/usr/bin/env python3
"""Fetch DESI DR1 Bright Galaxy Survey redshifts from NOIRLab and upload to HF.

Source: Dark Energy Spectroscopic Instrument Data Release 1
DESI Collaboration (2025), arXiv:2503.14745
https://data.desi.lbl.gov/doc/releases/dr1/
"""

import io
import sys
import time

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

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

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "targetid": "DESI unique 64-bit integer target identifier; encodes sky location and targeting program",
    "ra": "Right ascension of the fiber center, ICRS J2000.0 (degrees, 0-360)",
    "dec": "Declination of the fiber center, ICRS J2000.0 (degrees, -90 to +90)",
    "redshift": "Best-fit spectroscopic redshift; galaxies/QSOs: 0.05-3.5; stars near 0; null if fit failed",
    "redshift_err": "1-sigma uncertainty on the spectroscopic redshift; large values indicate unreliable fits",
    "spectype": "Primary spectral classification: 'GALAXY', 'STAR', or 'QSO' (quasar); determined by Redrock template fitting",
    "subtype": "Detailed sub-classification: for galaxies 'ELG' (emission-line), 'LRG' (luminous red), 'BGS' (bright galaxy survey); for stars the MK spectral type; null if not classified",
    "deltachi2": "Delta-chi-squared between best and second-best spectral template fit; higher values indicate more reliable redshift (deltachi2 > 25 recommended)",
    "chi2": "Best-fit chi-squared of the redshift solution; used with deltachi2 to assess fit quality",
    "coadd_numexp": "Number of individual exposures co-added to produce the spectrum",
    "coadd_numnight": "Number of distinct observation nights contributing to the coadd",
    "coadd_numtile": "Number of DESI focal-plane tiles contributing to the coadd",
    "coadd_exptime": "Total effective exposure time of the co-added spectrum (seconds)",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Spectroscopic redshifts from the Dark Energy Spectroscopic Instrument (DESI) Data Release 1 \
-- the largest spectroscopic survey ever conducted. This dataset contains the Bright Galaxy \
Survey (BGS) subset with reliable redshift measurements (zwarn=0, main_primary=true).

DESI is a robotic fiber-fed spectrograph on the Mayall 4-meter telescope at Kitt Peak National \
Observatory, capable of measuring 5,000 spectra simultaneously. DR1 contains 28.4 million \
unique spectroscopic redshifts from 14,600+ square degrees.

The Bright Galaxy Survey targets galaxies with r < 19.5 magnitude during bright lunar \
conditions. DESI represents a transformative leap in our ability to map the three-dimensional \
structure of the universe. By measuring precise spectroscopic redshifts for tens of millions of \
galaxies and quasars, DESI constructs a detailed map of the cosmic web. The primary science \
goal is to measure the baryon acoustic oscillation (BAO) scale at multiple redshifts, providing \
a standard ruler that constrains the expansion history of the universe and the nature of dark energy.

The spectral classifications (GALAXY, STAR, QSO) are determined by the Redrock template-fitting \
pipeline. Objects with zwarn=0 have passed all quality checks, making this a high-purity sample \
suitable for cosmological analyses.
"""


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

    # Clean string columns
    for col in ["spectype", "subtype"]:
        if col in df.columns:
            df[col] = (
                df[col].astype(str).str.strip()
                .replace({"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA})
            )

    # Drop columns that are constant after filtering
    df = df.drop(columns=["redshift_warn", "survey", "program"], errors="ignore")

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Sort by targetid for reproducibility
    df = df.sort_values("targetid").reset_index(drop=True)

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_galaxy = int((df["spectype"] == "GALAXY").sum())
    n_star = int((df["spectype"] == "STAR").sum())
    n_qso = int((df["spectype"] == "QSO").sum())
    median_z = df["redshift"].median()
    mean_z = df["redshift"].mean()

    print(f"  {n_total:,} sources: {n_galaxy:,} galaxies, {n_star:,} stars, {n_qso:,} QSOs")
    print(f"  Median redshift: {median_z:.4f}, Mean redshift: {mean_z:.4f}")

    quick_stats = f"""\
- **{n_total:,}** sources with reliable redshifts
- Median redshift: **{median_z:.4f}**
- Mean redshift: **{mean_z:.4f}**
- **{n_galaxy:,}** galaxies, **{n_star:,}** stars, **{n_qso:,}** QSOs
- Sky coverage: ~14,600 square degrees"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/desi-dr1-redshifts", split="train")
df = ds.to_pandas()

# Galaxy redshift distribution
galaxies = df[df["spectype"] == "GALAXY"]
print(f"{len(galaxies):,} galaxies, median z = {galaxies['redshift'].median():.4f}")

# Redshift histogram
import matplotlib.pyplot as plt
galaxies["redshift"].hist(bins=200, range=(0, 0.6))
plt.xlabel("Redshift")
plt.ylabel("Count")
plt.title("DESI BGS Galaxy Redshift Distribution")
plt.show()

# Sky coverage plot
plt.figure(figsize=(12, 6))
plt.scatter(df["ra"], df["dec"], s=0.01, alpha=0.1)
plt.xlabel("RA (deg)")
plt.ylabel("Dec (deg)")
plt.title("DESI DR1 BGS Sky Coverage")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="DESI DR1 Bright Galaxy Survey Redshifts",
        description=DESCRIPTION,
        tags=["space", "galaxies", "redshifts", "desi", "spectroscopy",
              "cosmology", "astronomy", "open-data", "tabular-data", "parquet"],
        source_url="https://data.desi.lbl.gov/doc/releases/dr1/",
        task_categories=["tabular-classification", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA12110/PIA12110~small.jpg",
            "alt": "Hubble Deep Field revealing myriad galaxies across cosmic time",
            "credit": "NASA/ESA/STScI",
        },
    ) as p:
        # Coerce integer columns to Int16 before clean (library only does Int64)
        for col in ["coadd_numexp", "coadd_numnight", "coadd_numtile"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int16")

        df = p.clean(
            df,
            numeric=["ra", "dec", "redshift", "redshift_err", "deltachi2",
                      "chi2", "coadd_exptime"],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="desi_dr1_redshifts.parquet",
            min_rows=1_000_000,
            expected_columns=["targetid", "ra", "dec", "redshift", "redshift_err",
                              "spectype", "deltachi2"],
            critical_columns=["targetid", "ra", "dec", "redshift"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Upload DESI DR1 BGS redshifts: {n_total:,} sources",
        )
    print("Done.")


if __name__ == "__main__":
    main()
