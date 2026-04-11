#!/usr/bin/env python3
"""Fetch Fermi LAT Third Pulsar Catalog (3PC) from HEASARC and upload to HF.

Source: Smith, D.A. et al. (2023), ApJ, 958, 191
HEASARC table: fermilpsc
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import heasarc_query

HF_REPO = "juliensimon/fermi-3pc-gamma-ray-pulsars"

ADQL = "SELECT * FROM fermilpsc"

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "name": "Pulsar name (e.g. J0030+0451); standard IAU designation",
    "ra": "Right ascension (degrees, J2000, 0-360)",
    "dec": "Declination (degrees, J2000, -90 to +90)",
    "lii": "Galactic longitude (degrees, 0-360)",
    "bii": "Galactic latitude (degrees, -90 to +90)",
    "period": "Spin period (seconds); millisecond pulsars have P < 0.03 s",
    "period_dot": "Period derivative (s/s); measures spin-down rate and constrains magnetic field strength",
    "edot": "Spin-down luminosity (erg/s); total rotational energy loss rate, key indicator of pulsar energetics",
    "distance": "Distance estimate (kpc); from dispersion measure or parallax",
    "flux_100": "Photon flux above 100 MeV (ph/cm2/s)",
    "energy_flux_100": "Energy flux above 100 MeV (erg/cm2/s)",
    "spectral_index": "Photon spectral index from power-law or exponential cutoff fit",
    "cutoff_energy": "Spectral cutoff energy (MeV); characteristic of outer magnetosphere emission",
    "significance": "Detection significance (sigma) from LAT likelihood analysis",
    "assoc_name": "Associated source name from multiwavelength counterpart matching",
    "binary_flag": "Binary pulsar flag; indicates whether pulsar is in a binary system",
    "type": "Pulsar type classification (e.g. MSP, young, radio-quiet)",
    "age": "Characteristic age (yr); derived from P / (2 * Pdot)",
    "bsurf": "Surface magnetic field (Gauss); derived from P and Pdot",
    "class": "Source classification label in the 3PC catalog",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Gamma-ray pulsars detected by the Fermi Large Area Telescope, including spin parameters, \
fluxes, and spectral properties from the Third Pulsar Catalog (3PC).

Pulsars are rapidly rotating, highly magnetized neutron stars that emit beams of \
electromagnetic radiation. When these beams sweep across Earth, they produce periodic \
pulses observed across the spectrum from radio to gamma rays. The Fermi LAT Third Pulsar \
Catalog (3PC) is the definitive census of pulsars detected at GeV gamma-ray energies.

Gamma-ray pulsars fall into two broad populations: millisecond pulsars (MSPs), old neutron \
stars spun up to periods of 1-30 ms by accretion from a binary companion, and young pulsars, \
recently formed neutron stars with strong magnetic fields and periods of 30 ms to several \
seconds. The Fermi LAT is uniquely suited for pulsar studies because gamma rays probe the \
magnetospheric emission regions directly, providing constraints on pulsar emission geometry \
and plasma physics that are inaccessible at other wavelengths.

The 3PC catalog includes spin parameters (period, period derivative), derived quantities \
(spin-down luminosity, characteristic age, surface magnetic field), spectral properties \
(spectral index, cutoff energy), and flux measurements for each detected pulsar.\
"""


def main():
    print("Fetching Fermi 3PC catalog from HEASARC...")
    df = heasarc_query("fermilpsc", ADQL)
    print(f"  {len(df):,} pulsars fetched")

    # Normalize column names
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    # Coerce numeric columns (skip known string columns)
    string_cols = {"name", "assoc_name", "class", "type", "binary_flag"}
    numeric_cols = [c for c in df.columns if c not in string_cols]

    # Clean string columns
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip().replace(
            {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
        )

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    n_total = len(df)

    # Pulsar type breakdown
    n_msp = 0
    n_young = 0
    type_col = None
    for candidate in ("type", "class", "psr_type"):
        if candidate in df.columns:
            type_col = candidate
            break
    if type_col:
        type_vals = df[type_col].dropna().str.upper()
        n_msp = int(type_vals.str.contains("MSP|MILLISECOND", na=False).sum())
        n_young = int(type_vals.str.contains("YOUNG|YNG", na=False).sum())

    # Period stats
    period_line = ""
    if "period" in df.columns:
        p = df["period"].dropna()
        if len(p) > 0:
            period_line = f"\n- Period range: **{p.min():.6f}** to **{p.max():.3f}** seconds"

    quick_stats = f"- **{n_total:,}** gamma-ray pulsars"
    if n_msp or n_young:
        quick_stats += f"\n- **{n_msp:,}** millisecond pulsars, **{n_young:,}** young pulsars"
    quick_stats += period_line

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/fermi-3pc-gamma-ray-pulsars", split="train")
df = ds.to_pandas()

# Overview
print(f"{len(df):,} gamma-ray pulsars")

# Period distribution
import matplotlib.pyplot as plt
import numpy as np
p = df["period"].dropna()
plt.hist(np.log10(p), bins=50)
plt.xlabel("log10(Period / s)")
plt.ylabel("Count")
plt.title("Gamma-Ray Pulsar Period Distribution")
plt.show()

# Spin-down luminosity vs period
mask = df["period"].notna() & df["edot"].notna()
plt.scatter(df.loc[mask, "period"], df.loc[mask, "edot"], s=5, alpha=0.6)
plt.xscale("log")
plt.yscale("log")
plt.xlabel("Period (s)")
plt.ylabel("Edot (erg/s)")
plt.title("Spin-Down Luminosity vs Period")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Fermi LAT Third Pulsar Catalog (3PC)",
        description=DESCRIPTION,
        tags=["space", "fermi", "nasa", "pulsar", "gamma-ray", "high-energy",
              "astronomy", "open-data", "tabular-data", "parquet"],
        source_url="https://heasarc.gsfc.nasa.gov/W3Browse/fermi/fermilpsc.html",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/physics-datasets-69c2d4682d37dfdb77447bd7",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA03519/PIA03519~small.jpg",
            "alt": "Cassiopeia A supernova remnant in X-ray, optical, and infrared light",
            "credit": "NASA/JPL-Caltech/STScI/CXC/SAO",
        },
        related_datasets=[
            "juliensimon/pulsar-catalog",
            "juliensimon/fermi-4fgl-dr4",
            "juliensimon/fermi-3fhl-hard-gamma-ray",
            "juliensimon/fermi-4lac-agn-catalog",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[c for c in numeric_cols if c in df.columns],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="fermi-3pc.parquet",
            min_rows=200,
            expected_columns=["name", "ra", "dec", "period"],
            critical_columns=["name", "ra", "dec"],
            warn_all_nulls=0.90,
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Fermi 3PC catalog: {n_total:,} gamma-ray pulsars",
        )
    print("Done.")


if __name__ == "__main__":
    main()
