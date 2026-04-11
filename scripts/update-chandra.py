#!/usr/bin/env python3
"""Fetch Chandra Source Catalog (CSC 2.1) from HEASARC and upload to HF."""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import heasarc_query

HF_REPO = "juliensimon/chandra-x-ray-sources"
ADQL = "SELECT * FROM chanmaster"

NUMERIC_COLS = [
    "ra", "dec", "lii", "bii", "exposure",
]

COLUMN_DESCRIPTIONS = {
    "name": "Chandra observation target name or source designation",
    "ra": "ICRS right ascension in degrees; sub-arcsecond accuracy from Chandra's 0.5\" resolution",
    "dec": "ICRS declination in degrees",
    "lii": "Galactic longitude in degrees",
    "bii": "Galactic latitude in degrees",
    "obsid": "Chandra observation identifier (unique per pointing)",
    "detector": "Instrument detector used: ACIS-I, ACIS-S, HRC-I, or HRC-S",
    "grating": "Grating configuration: NONE, LETG, or HETG",
    "exposure": "Exposure time in kiloseconds",
    "cycle": "Chandra observing cycle number (proposal cycle)",
    "type": "Observation type: GO (guest observer), GTO (guaranteed time), DDT (director's discretionary), CAL (calibration)",
    "category": "Science category assigned to the observation (e.g., AGN, SNR, STARS)",
    "pi": "Principal investigator last name",
    "proposal": "Proposal title for the observation",
    "sequence_number": "Chandra sequence number for the observation",
    "data_mode": "Telemetry mode used (e.g., FAINT, VFAINT, CC33_FAINT)",
    "status": "Observation status: archived, observed, or scheduled",
    "public_date": "Date when the observation data became publicly available",
    "time": "Observation start time",
    "x_ra_dec": "Unit vector X component of the pointing direction",
    "y_ra_dec": "Unit vector Y component of the pointing direction",
    "z_ra_dec": "Unit vector Z component of the pointing direction",
    "row": "HEASARC internal row identifier",
}

DESCRIPTION = """\
The Chandra Source Catalog (CSC 2.1) is the definitive catalog of X-ray sources detected by NASA's Chandra X-Ray Observatory, the most powerful X-ray telescope ever built.

The Chandra X-Ray Observatory, launched in 1999, provides the sharpest X-ray images ever achieved, with sub-arcsecond angular resolution. The Chandra Source Catalog is a comprehensive catalog of all X-ray sources detected in Chandra observations, including positions, multi-band photometry (soft, medium, hard, broad, wide bands), hardness ratios for spectral characterization, variability flags, and source extent measurements.

CSC 2.1 covers roughly 560 square degrees of sky and includes sources from over 15,000 individual Chandra observations. The catalog is essential for multi-wavelength studies of active galactic nuclei, X-ray binaries, supernova remnants, galaxy clusters, and stellar coronae.

Chandra's angular resolution of approximately 0.5 arcseconds is achieved by its four nested pairs of grazing-incidence Wolter Type-I mirrors. This resolution makes the Chandra Source Catalog uniquely powerful: it resolves individual X-ray sources in crowded fields such as the Galactic center, globular clusters, and nearby galaxies where other X-ray telescopes would see only confused blends."""


def main():
    print("Fetching Chandra Source Catalog from HEASARC...")
    df = heasarc_query("chanmaster", ADQL)

    # Normalize column names to snake_case
    df.columns = (
        df.columns.str.strip()
        .str.lower()
        .str.replace(r"[^a-z0-9_]", "_", regex=True)
        .str.replace(r"_+", "_", regex=True)
        .str.strip("_")
    )

    # Sort by exposure descending (longest observations first)
    if "exposure" in df.columns:
        df = df.sort_values("exposure", ascending=False, na_position="last").reset_index(drop=True)

    # Domain stats
    n_total = len(df)
    n_detectors = df["detector"].nunique() if "detector" in df.columns else 0
    median_exp = df["exposure"].median() if "exposure" in df.columns else None

    exp_line = f"\n- Median exposure: **{median_exp:.1f}** ks" if median_exp is not None else ""
    det_line = f"\n- Instruments: **{n_detectors}** detector configurations" if n_detectors else ""

    quick_stats = f"- **{n_total:,}** Chandra observations in the master catalog{exp_line}{det_line}"

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/chandra-x-ray-sources", split="train")
df = ds.to_pandas()

# Longest observations
top = df.nlargest(10, "exposure")[["name", "ra", "dec", "exposure", "detector"]]
print(top.to_string())

# Sky coverage map
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(12, 6))
ax.scatter(df["ra"], df["dec"], s=0.1, alpha=0.2)
ax.set_xlabel("RA (deg)")
ax.set_ylabel("Dec (deg)")
ax.invert_xaxis()
ax.set_title("Chandra Observation Pointings")
plt.tight_layout()
plt.show()

# Detector usage breakdown
df["detector"].value_counts().plot.bar()
plt.title("Chandra Detector Usage")
plt.show()
```"""

    # Identify numeric columns present in df
    numeric_present = [c for c in NUMERIC_COLS if c in df.columns]

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Chandra X-Ray Source Catalog",
        description=DESCRIPTION,
        tags=["space", "x-ray", "chandra", "nasa", "astronomy", "open-data", "tabular-data", "parquet"],
        source_url="https://cxc.cfa.harvard.edu/csc/",
        task_categories=["tabular-classification", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e002215/GSFC_20171208_Archive_e002215~medium.jpg",
            "alt": "The gamma-ray sky as seen by NASA's Fermi telescope",
            "credit": "NASA/DOE/Fermi LAT Collaboration",
        },
        related_datasets=[
            "juliensimon/erosita-erass1-xray",
            "juliensimon/fermi-4fgl-dr4",
            "juliensimon/pulsar-catalog",
        ],
    ) as p:
        df = p.clean(df, numeric=numeric_present, drop_mostly_null_threshold=0.95)
        # Also clean remaining string columns
        str_cols = list(df.select_dtypes(include=["object"]).columns)
        if str_cols:
            df = p.clean(df, strings=str_cols)

        # Keep only described columns (drop undescribed HEASARC metadata columns)
        df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

        p.publish(
            df,
            filename="chandra_x_ray_sources.parquet",
            min_rows=20_000,
            expected_columns=["ra", "dec"],
            critical_columns=["ra", "dec"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Chandra X-ray sources: {n_total:,} sources",
        )
    print("Done.")


if __name__ == "__main__":
    main()
