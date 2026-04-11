#!/usr/bin/env python3
"""Fetch Planck Second SZ Source Catalog from HEASARC and upload to HF.

Source: Planck Collaboration XXVII (2016, A&A, 594, A27)
HEASARC table: plancksz2
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import heasarc_query

HF_REPO = "juliensimon/planck-sz2-clusters"

ADQL = "SELECT * FROM plancksz2"

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "name": "Planck cluster designation in the format 'PSZ2 GXXX.X+/-XX.X', encoding Galactic longitude and latitude in the name",
    "ra": "ICRS J2000.0 right ascension of the SZ centroid in degrees (0-360)",
    "dec": "ICRS J2000.0 declination of the SZ centroid in degrees (-90 to +90)",
    "lii": "Galactic longitude of the SZ centroid in degrees (0-360)",
    "bii": "Galactic latitude of the SZ centroid in degrees (-90 to +90)",
    "snr": "Planck SZ detection signal-to-noise ratio; catalog threshold is SNR > 4.5; the most massive clusters can reach SNR > 50",
    "redshift": "Cluster spectroscopic or photometric redshift; null for ~30% of Planck clusters that lack optical/NIR confirmation",
    "redshift_err": "1-sigma uncertainty on the redshift; typically < 0.001 for spectroscopic, ~0.01-0.05 for photometric; null if redshift is null",
    "redshift_type": "Redshift measurement type: 'spec' = spectroscopic (precise), 'phot' = photometric (estimated from imaging); null if redshift is null",
    "redshift_source": "Survey or publication providing the redshift measurement (e.g., 'SDSS', 'ACT', 'SPT', 'NED'); null if redshift is null",
    "msz": "SZ-derived cluster mass M_500 in units of 10^14 solar masses; Planck clusters range ~1-15 x 10^14 M_sun; null if Y_5R500 is poorly constrained",
    "msz_err_up": "Upper (positive) 1-sigma uncertainty on msz in units of 10^14 solar masses; null if msz is null",
    "msz_err_low": "Lower (negative) 1-sigma uncertainty on msz in units of 10^14 solar masses; null if msz is null",
    "y5r500": "Integrated Compton y-parameter within 5*R_500 in arcmin^2; dimensionless measure of total ICM thermal energy; low-scatter mass proxy; typical range 1e-4 to 1e-2 arcmin^2",
    "y5r500_err_up": "Upper (positive) 1-sigma uncertainty on y5r500 in arcmin^2; null if y5r500 is null",
    "y5r500_err_low": "Lower (negative) 1-sigma uncertainty on y5r500 in arcmin^2; null if y5r500 is null",
    "theta": "Characteristic angular radius of the cluster as measured by the matched filter, in arcminutes; related to the physical size at the cluster redshift",
    "theta_err_up": "Upper 1-sigma uncertainty on theta in arcminutes; null if theta is null",
    "theta_err_low": "Lower 1-sigma uncertainty on theta in arcminutes; null if theta is null",
    "pipeline_det": "Detection pipeline confirmation flags; encodes which of MMF1, MMF3, and PwS (PowellSnakes) detected the cluster",
    "validation": "External validation status: confirmed, candidate, or spurious based on cross-matching with optical, X-ray, or other SZ surveys",
    "external_name": "Name of the same cluster in an external catalog (e.g., 'Abell 2029', 'RXC J1504.1-0248'); null if no cross-match found",
    "external_class": "Morphological or astrophysical classification from the external cross-matched catalog; null if external_name is null",
    "is_confirmed": "Derived: True if redshift is not null (cluster has a measured distance); False for unconfirmed SZ candidates",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Complete catalog of galaxy clusters detected via the thermal Sunyaev-Zeldovich (SZ) effect \
by the ESA Planck satellite, sourced from NASA HEASARC.

The Sunyaev-Zeldovich (SZ) effect is the inverse Compton scattering of cosmic microwave background \
(CMB) photons by the hot intracluster medium (ICM) of galaxy clusters. As CMB photons pass through \
the ICM (electron temperatures of 10^7-10^8 K), they receive a characteristic energy boost that \
produces a spectral distortion observable at millimeter wavelengths: a decrement below ~217 GHz \
and an increment above. This effect is unique in cosmology because its surface brightness is \
redshift-independent, making it an extraordinarily powerful tool for detecting massive clusters \
at any distance.

The Planck satellite's all-sky survey at nine frequencies (30-857 GHz) provided the first \
uniform all-sky SZ cluster catalog. The PSZ2 catalog represents the largest SZ-selected \
sample of galaxy clusters, detected using three independent methods: two implementations of \
matched multi-frequency filters (MMF1 and MMF3) and PowellSnakes (PwS), a Bayesian detection \
algorithm. Each cluster's integrated Compton parameter Y5R500 quantifies the total thermal \
energy of the ICM and serves as a low-scatter mass proxy through the Y-M scaling relation.

These SZ-selected clusters are essential for constraining cosmological parameters \
(Omega_m, sigma_8), calibrating the cluster mass function, understanding large-scale \
structure formation, and cross-matching with optical, X-ray, and gravitational lensing surveys.
"""


def main():
    print("Fetching Planck SZ2 catalog from HEASARC...")
    df = heasarc_query("plancksz2", ADQL)
    print(f"  {len(df):,} galaxy clusters fetched")

    # Derived column: is_confirmed (has a measured redshift)
    if "redshift" in df.columns:
        df["is_confirmed"] = df["redshift"].notna()
    elif "validation" in df.columns:
        df["is_confirmed"] = df["validation"].astype(str).str.strip().str.len() > 0
    else:
        df["is_confirmed"] = False

    # Sort by SNR descending
    if "snr" in df.columns:
        df = df.sort_values("snr", ascending=False).reset_index(drop=True)

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_confirmed = int(df["is_confirmed"].sum())
    n_unconfirmed = n_total - n_confirmed
    snr_max = df["snr"].max() if "snr" in df.columns else 0
    snr_median = df["snr"].median() if "snr" in df.columns else 0
    n_with_redshift = int(df["redshift"].notna().sum()) if "redshift" in df.columns else 0
    z_median = df["redshift"].median() if "redshift" in df.columns and n_with_redshift > 0 else 0

    highest_snr_idx = df["snr"].idxmax() if "snr" in df.columns else None
    highest_snr_name = df.loc[highest_snr_idx, "name"] if highest_snr_idx is not None else "N/A"
    highest_snr_val = df.loc[highest_snr_idx, "snr"] if highest_snr_idx is not None else 0

    quick_stats = f"""\
- **{n_total:,}** galaxy clusters detected via the SZ effect
- **{n_confirmed:,}** confirmed with measured redshifts (median z = {z_median:.3f})
- **{n_unconfirmed:,}** unconfirmed SZ candidates
- Highest SNR: **{highest_snr_name}** (SNR = {highest_snr_val:.1f})
- Median SNR: **{snr_median:.1f}**, Max SNR: **{snr_max:.1f}**"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/planck-sz2-clusters", split="train")
df = ds.to_pandas()

# Confirmed clusters with redshifts
confirmed = df[df["is_confirmed"]]
print(f"{len(confirmed):,} clusters with measured redshifts")

# Highest SNR detections
top = df.nlargest(10, "snr")[["name", "snr", "redshift", "msz"]]
print(top)

# Redshift distribution
import matplotlib.pyplot as plt
df["redshift"].dropna().hist(bins=50)
plt.xlabel("Redshift")
plt.ylabel("Count")
plt.title("Planck SZ2 Cluster Redshift Distribution")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Planck Second Sunyaev-Zeldovich Source Catalog (PSZ2)",
        description=DESCRIPTION,
        tags=["space", "planck", "sunyaev-zeldovich", "galaxy-cluster", "cmb",
              "esa", "cosmology", "astronomy", "open-data", "tabular-data", "parquet"],
        source_url="https://heasarc.gsfc.nasa.gov/W3Browse/all/plancksz2.html",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA12110/PIA12110~small.jpg",
            "alt": "Hubble Deep Field revealing myriad galaxies across cosmic time",
            "credit": "NASA/ESA/STScI",
        },
        related_datasets=[
            "juliensimon/galaxy-clusters",
            "juliensimon/desi-dr1-redshifts",
            "juliensimon/pantheon-plus-sne-ia",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "ra", "dec", "lii", "bii", "redshift", "redshift_err",
                "snr", "msz", "msz_err_up", "msz_err_low",
                "y5r500", "y5r500_err_up", "y5r500_err_low",
                "theta", "theta_err_up", "theta_err_low",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="planck_sz2.parquet",
            min_rows=1000,
            expected_columns=["name", "ra", "dec", "snr"],
            critical_columns=["name", "ra", "dec"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Planck SZ2 catalog: {n_total:,} clusters",
        )
    print("Done.")


if __name__ == "__main__":
    main()
