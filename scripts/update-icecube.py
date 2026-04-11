#!/usr/bin/env python3
"""Fetch IceCube Neutrino Point Source Catalog from HEASARC and upload to HF.

Source: IceCube Collaboration via NASA HEASARC
HEASARC table: icecubepsc
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import heasarc_query

HF_REPO = "juliensimon/icecube-neutrino-catalog"

ADQL = "SELECT * FROM icecubepsc"

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "name": "Source designation (e.g. 'TXS 0506+056', 'NGC 1068'); typically the name of the astrophysical counterpart",
    "ra": "Best-fit right ascension in degrees (J2000.0 ICRS, 0-360)",
    "dec": "Best-fit declination in degrees (J2000.0 ICRS, -90 to +90); IceCube angular resolution ~0.4 degrees at TeV energies for muon tracks",
    "ra_deg": "Right ascension in degrees (alternate column from HEASARC, same value as ra when both present)",
    "dec_deg": "Declination in degrees (alternate column from HEASARC, same value as dec when both present)",
    "lii": "Galactic longitude in degrees (0-360), derived from equatorial coordinates",
    "bii": "Galactic latitude in degrees (-90 to +90); sources near the Galactic plane (|b| < 10 degrees) have higher atmospheric muon backgrounds",
    "ts": "Test statistic from unbinned maximum-likelihood point source analysis; TS > 25 (~5 sigma) is typical discovery threshold",
    "n_s": "Best-fit number of signal neutrino events attributed to the source above the atmospheric background",
    "flux": "Best-fit neutrino flux normalization at 100 TeV in GeV/cm2/s",
    "flux_err": "1-sigma uncertainty on the flux normalization at 100 TeV in GeV/cm2/s",
    "spectral_index": "Best-fit power-law spectral index of the neutrino energy spectrum (dN/dE proportional to E^-gamma); typical astrophysical: 2.0-2.5",
    "spectral_index_err": "1-sigma uncertainty on the spectral index",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
IceCube Neutrino Point Source Catalog from NASA HEASARC -- point sources of high-energy \
astrophysical neutrinos detected by the IceCube Neutrino Observatory at the South Pole.

The IceCube Neutrino Observatory is a cubic-kilometer particle detector buried in the \
Antarctic ice at the South Pole. It detects high-energy neutrinos from astrophysical \
sources such as active galactic nuclei, blazars, and other extreme cosmic environments.

The point source catalog represents the result of searches for statistically significant \
clustering of neutrino arrival directions above the isotropic atmospheric background. Each \
candidate source is characterized by a test statistic (TS) reflecting the likelihood of a \
genuine astrophysical signal versus the null hypothesis, along with a best-fit number of \
signal events and spectral index. These searches probe hadronic acceleration in jets, \
accretion flows, and shock environments across the sky.

Neutrino point source detection is inherently challenging because the atmospheric neutrino \
background is orders of magnitude larger than the astrophysical signal, and the angular \
resolution of muon track reconstruction in ice (~0.5-1 degree at TeV energies) limits the \
ability to resolve individual sources. Cross-correlation with gamma-ray, X-ray, and radio \
catalogs is a key strategy for identifying astrophysical counterparts.\
"""


def main():
    print("Fetching IceCube Neutrino Point Source Catalog from HEASARC...")
    df = heasarc_query("icecubepsc", ADQL)
    print(f"  {len(df):,} sources fetched")

    # Normalize column names to snake_case
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    # Numeric coercion
    numeric_cols = ["ra", "dec", "lii", "bii", "flux", "flux_err",
                    "spectral_index", "spectral_index_err",
                    "n_s", "ts", "dec_deg", "ra_deg"]

    # Clean string columns
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].astype(str).str.strip().replace(
            {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
        )

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    df = df.reset_index(drop=True)
    n_total = len(df)

    # Stats
    n_with_ts = int(df["ts"].notna().sum()) if "ts" in df.columns else 0
    max_ts = df["ts"].max() if "ts" in df.columns and n_with_ts > 0 else 0

    quick_stats = f"""\
- **{n_total:,}** neutrino point sources
- **{n_with_ts:,}** with test statistic values"""
    if max_ts > 0:
        quick_stats += f"\n- Maximum TS: **{max_ts:.1f}**"

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/icecube-neutrino-catalog", split="train")
df = ds.to_pandas()

# Most significant sources
top = df.nlargest(10, "ts")[["name", "ra", "dec", "ts", "n_s", "flux"]]
print(top)

# Sky map of neutrino sources
import matplotlib.pyplot as plt
plt.scatter(df["ra"], df["dec"], s=5, alpha=0.6, c=df["ts"], cmap="viridis")
plt.colorbar(label="Test Statistic")
plt.xlabel("RA (deg)")
plt.ylabel("Dec (deg)")
plt.title("IceCube Neutrino Point Sources")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="IceCube Neutrino Point Source Catalog",
        description=DESCRIPTION,
        tags=["space", "neutrino", "icecube", "high-energy",
              "astronomy", "open-data", "tabular-data", "parquet"],
        source_url="https://heasarc.gsfc.nasa.gov/W3Browse/all/icecubepsc.html",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e002215/GSFC_20171208_Archive_e002215~medium.jpg",
            "alt": "The gamma-ray sky as seen by NASA's Fermi telescope",
            "credit": "NASA/DOE/Fermi LAT Collaboration",
        },
        related_datasets=[
            "juliensimon/fermi-4fgl-dr4",
            "juliensimon/fermi-4lac-agn-catalog",
            "juliensimon/chandra-x-ray-sources",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[c for c in numeric_cols if c in df.columns],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="icecube_neutrino_catalog.parquet",
            min_rows=100,
            expected_columns=["name", "ra", "dec"],
            critical_columns=["ra", "dec"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update IceCube neutrino catalog: {n_total:,} sources",
        )
    print("Done.")


if __name__ == "__main__":
    main()
