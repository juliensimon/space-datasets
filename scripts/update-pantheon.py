#!/usr/bin/env python3
"""Fetch Pantheon+ Type Ia supernovae dataset and upload to HF."""

import pandas as pd

from hf_dataset_utils import Pipeline

DATA_URL = "https://raw.githubusercontent.com/PantheonPlusSH0ES/DataRelease/main/Pantheon%2B_Data/4_DISTANCES_AND_COVAR/Pantheon%2BSH0ES.dat"
HF_REPO = "juliensimon/pantheon-plus-sne-ia"

# ── Column mapping ───────────────────────────────────────────────────
KEEP_COLS = {
    "CID": "sn_name",
    "IDSURVEY": "survey_id",
    "zHD": "redshift_hd",
    "zHDERR": "redshift_hd_err",
    "zCMB": "redshift_cmb",
    "zCMBERR": "redshift_cmb_err",
    "zHEL": "redshift_helio",
    "zHELERR": "redshift_helio_err",
    "mB": "apparent_mag_b",
    "mBERR": "apparent_mag_b_err",
    "x1": "stretch_x1",
    "x1ERR": "stretch_x1_err",
    "c": "color_c",
    "cERR": "color_c_err",
    "HOST_LOGMASS": "host_log_mass",
    "HOST_LOGMASS_ERR": "host_log_mass_err",
    "FITPROB": "fit_probability",
    "MU_SH0ES": "distance_modulus",
    "MU_SH0ES_ERR_DIAG": "distance_modulus_err",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "sn_name": "Supernova identifier (CID field from Pantheon+); typically survey-specific designations such as '2001el' or 'SN2011fe'",
    "survey_id": "Integer code identifying the discovery survey; Pantheon+ combines 18 surveys including CfA (1-4), CSP, SDSS, SNLS, PS1, DES, and HST programs; links each SN to its photometric calibration system",
    "redshift_hd": "Hubble-diagram redshift: the CMB-frame redshift further corrected for coherent large-scale peculiar velocity flows; the most cosmologically clean redshift for Hubble diagram fitting; range ~0.001-2.3",
    "redshift_hd_err": "1-sigma uncertainty on the Hubble-diagram redshift, including peculiar velocity uncertainty (~150 km/s = 0.0005 in z at low redshift)",
    "redshift_cmb": "CMB-frame redshift: observed redshift corrected for Earth's motion relative to the CMB dipole (~369 km/s); the cosmologically meaningful redshift for Hubble constant measurements",
    "redshift_cmb_err": "1-sigma uncertainty on the CMB-frame redshift",
    "redshift_helio": "Heliocentric redshift: the raw observed Doppler shift from Earth's rest frame, uncorrected for solar motion; used internally in SALT2 for K-corrections",
    "redshift_helio_err": "1-sigma uncertainty on the heliocentric redshift",
    "apparent_mag_b": "Apparent peak B-band magnitude at maximum light from the SALT2 light-curve fit; the directly observed brightness before standardization; typical range 12-26 mag",
    "apparent_mag_b_err": "1-sigma uncertainty on the SALT2 peak B-band magnitude (mag); includes photon noise and calibration uncertainty",
    "stretch_x1": "SALT2 light-curve stretch parameter: positive x1 = broader/slower/brighter light curve, negative x1 = narrower/faster/dimmer (Phillips relation); typical range x1 in [-3, +3]",
    "stretch_x1_err": "1-sigma uncertainty on the SALT2 stretch parameter x1",
    "color_c": "SALT2 color parameter: B-V color excess at peak relative to fiducial template; positive c = redder (more dust or intrinsically red), negative = bluer; typical range c in [-0.3, +0.5]",
    "color_c_err": "1-sigma uncertainty on the SALT2 color parameter c",
    "host_log_mass": "Log10 host galaxy stellar mass (M_sun) from SED fitting; used for the 'mass step' correction: SNe Ia in hosts with log M > 10 are ~0.06 mag brighter after standardization; null for SNe without host measurements",
    "host_log_mass_err": "1-sigma uncertainty on host galaxy log stellar mass; null when host mass is unavailable",
    "fit_probability": "Probability (0-1) that the SALT2 light-curve fit is acceptable; low values (<0.001) may indicate non-Ia contamination or poor coverage; used as a quality cut",
    "distance_modulus": "Distance modulus mu (mag) from SH0ES/Pantheon+: mu = m_B - M_B + alpha*x1 - beta*c - delta_bias; mu = 5*log10(d/10 pc); typical range 33-46 mag",
    "distance_modulus_err": "Diagonal (statistical) 1-sigma uncertainty on distance modulus (mag); does not include off-diagonal covariance terms; typical ~0.15 mag",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
The gold standard cosmological dataset -- spectroscopically confirmed Type Ia supernovae \
from the Pantheon+ analysis, used to measure the Hubble constant (H0) and constrain the \
dark energy equation of state. This is the dataset behind the "Hubble tension" debate.

Type Ia supernovae are thermonuclear explosions of carbon-oxygen white dwarfs that have \
accreted matter from a companion star until they approach the Chandrasekhar mass limit. \
The resulting detonation produces a characteristic light curve whose peak luminosity, \
after correction for the width-luminosity relation (Phillips relation), is remarkably \
uniform -- making SNe Ia the premier "standardizable candles" for measuring cosmological \
distances. This technique led to the 1998 discovery of the accelerating expansion of \
the universe and the inference of dark energy, earning the 2011 Nobel Prize in Physics.

Pantheon+ combines light curves from 18 different surveys spanning the full history of \
SN Ia observations. The SALT2 light-curve fitter parameterizes each supernova by its \
stretch (x1) and color (c). The Hubble diagram constructed from this dataset -- distance \
modulus versus redshift -- is the most direct observational evidence for the accelerating \
expansion of the universe.
"""


def main():
    print("Fetching Pantheon+ Type Ia supernovae dataset...")
    df = pd.read_csv(DATA_URL, sep=r"\s+")
    print(f"  {len(df):,} raw rows")

    # Keep and rename columns
    available = {c: v for c, v in KEEP_COLS.items() if c in df.columns}
    df = df[list(available.keys())].rename(columns=available)

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    z_min = df["redshift_cmb"].min()
    z_max = df["redshift_cmb"].max()
    z_median = df["redshift_cmb"].median()
    n_surveys = df["survey_id"].nunique()
    mu_min = df["distance_modulus"].min()
    mu_max = df["distance_modulus"].max()

    quick_stats = f"""\
- **{n_total:,}** Type Ia supernovae from **{n_surveys}** surveys
- Redshift range: {z_min:.4f} to {z_max:.3f} (median {z_median:.3f})
- Distance modulus range: {mu_min:.2f} to {mu_max:.2f} mag"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/pantheon-plus-sne-ia", split="train")
df = ds.to_pandas()

# Hubble diagram
import matplotlib.pyplot as plt
import numpy as np

valid = df[df["distance_modulus"] > 0]
plt.errorbar(valid["redshift_cmb"], valid["distance_modulus"],
             yerr=valid["distance_modulus_err"],
             fmt=".", ms=2, alpha=0.5, elinewidth=0.5)
plt.xscale("log")
plt.xlabel("Redshift (CMB frame)")
plt.ylabel("Distance modulus (mag)")
plt.title("Pantheon+ Hubble Diagram")
plt.show()

# Color-stretch distribution
plt.scatter(df["stretch_x1"], df["color_c"], s=2, alpha=0.3)
plt.xlabel("Stretch x1")
plt.ylabel("Color c")
plt.title("SALT2 Parameter Distribution")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Pantheon+ Type Ia Supernovae",
        description=DESCRIPTION,
        tags=["space", "supernova", "cosmology", "hubble-constant",
              "dark-energy", "pantheon", "open-data", "tabular-data", "parquet"],
        source_url="https://github.com/PantheonPlusSH0ES/DataRelease",
        task_categories=["tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA12110/PIA12110~small.jpg",
            "alt": "Hubble Deep Field revealing myriad galaxies across cosmic time",
            "credit": "NASA/ESA/STScI",
        },
        related_datasets=[
            "juliensimon/open-supernova-catalog",
            "juliensimon/cosmicflows-galaxy-distances",
            "juliensimon/desi-dr1-redshifts",
        ],
    ) as p:
        numeric_cols = [
            "survey_id", "redshift_hd", "redshift_hd_err",
            "redshift_cmb", "redshift_cmb_err",
            "redshift_helio", "redshift_helio_err",
            "apparent_mag_b", "apparent_mag_b_err",
            "stretch_x1", "stretch_x1_err",
            "color_c", "color_c_err",
            "host_log_mass", "host_log_mass_err",
            "fit_probability",
            "distance_modulus", "distance_modulus_err",
        ]
        df = p.clean(
            df,
            numeric=[c for c in numeric_cols if c in df.columns],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="pantheon_plus_sne.parquet",
            min_rows=1_000,
            expected_columns=["sn_name", "redshift_cmb", "apparent_mag_b", "distance_modulus"],
            critical_columns=["sn_name", "redshift_cmb", "apparent_mag_b", "distance_modulus"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Pantheon+ SNe Ia: {n_total:,} supernovae",
        )
    print("Done.")


if __name__ == "__main__":
    main()
