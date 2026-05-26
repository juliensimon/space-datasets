#!/usr/bin/env python3
"""Fetch Gaia DR3 White Dwarf candidates (Gentile Fusillo+ 2021) from VizieR and upload to HF."""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/gaia-dr3-white-dwarfs"

# Gentile Fusillo+ 2021 (MNRAS 508, 3877): THE definitive Gaia DR3 WD catalog
ADQL = 'SELECT * FROM "J/MNRAS/508/3877/maincat"'

# ── Column mapping ───────────────────────────────────────────────────
RENAME = {
    "WDJname": "wdj_name",
    "WDJ": "wdj_name",
    "Source": "source_id",
    "GaiaEDR3": "source_id",
    "GaiaDR2": "source_id_dr2",
    "EDR3Name": "edr3_name",
    "RA_ICRS": "ra_deg",
    "DE_ICRS": "dec_deg",
    "Plx": "parallax_mas",
    "e_Plx": "parallax_error_mas",
    "pmRA": "pmra_mas_yr",
    "e_pmRA": "pmra_error_mas_yr",
    "pmDE": "pmdec_mas_yr",
    "e_pmDE": "pmdec_error_mas_yr",
    "Gmag": "g_mag",
    "e_Gmag": "g_mag_error",
    "BPmag": "bp_mag",
    "e_BPmag": "bp_mag_error",
    "RPmag": "rp_mag",
    "e_RPmag": "rp_mag_error",
    "BP-RP": "bp_rp",
    "Pwd": "prob_wd",
    "Teff": "teff_k",
    "e_Teff": "teff_error_k",
    "logg": "log_g",
    "e_logg": "log_g_error",
    "Mass": "mass_msun",
    "e_Mass": "mass_error_msun",
    "chi2": "chi2",
    "Grv": "radial_velocity_km_s",
    "e_Grv": "radial_velocity_error_km_s",
    "RUWE": "ruwe",
    "GAbsmag": "g_abs_mag",
    "Dist": "distance_pc",
    "e_Dist": "distance_error_pc",
    "AG": "extinction_g",
    "E_BP-RP_": "ebp_rp",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "wdj_name": "White Dwarf J designation, a unique identifier encoding the J2000 position of the source",
    "source_id": "Gaia DR3 unique source identifier (64-bit integer as string); stable within the Gaia DR3 data release",
    "source_id_dr2": "Gaia DR2 source identifier for cross-matching with earlier data releases; null where no DR2 counterpart exists",
    "edr3_name": "Gaia EDR3 designation string; alternative identifier format",
    "ra_deg": "Right ascension, ICRS at Gaia reference epoch, in decimal degrees (0-360)",
    "dec_deg": "Declination, ICRS at Gaia reference epoch, in decimal degrees (-90 to +90)",
    "parallax_mas": "Gaia parallax in milliarcseconds; essential for distance determination and absolute magnitude calculation",
    "parallax_error_mas": "1-sigma uncertainty on Gaia parallax (mas)",
    "pmra_mas_yr": "Proper motion in right ascension (mas/yr), includes cos(dec) factor; traces the star's tangential velocity",
    "pmra_error_mas_yr": "1-sigma uncertainty on proper motion in RA (mas/yr)",
    "pmdec_mas_yr": "Proper motion in declination (mas/yr)",
    "pmdec_error_mas_yr": "1-sigma uncertainty on proper motion in Dec (mas/yr)",
    "g_mag": "Mean Gaia G-band (330-1050 nm) apparent magnitude; white dwarfs typically G = 12-21 mag",
    "g_mag_error": "Uncertainty on mean G-band magnitude",
    "bp_mag": "Mean Gaia BP-band (330-680 nm) apparent magnitude; null for faint stars with poor BP photometry",
    "bp_mag_error": "Uncertainty on mean BP-band magnitude",
    "rp_mag": "Mean Gaia RP-band (640-1050 nm) apparent magnitude; null for faint stars with poor RP photometry",
    "rp_mag_error": "Uncertainty on mean RP-band magnitude",
    "bp_rp": "Gaia BP-RP colour index; encodes surface temperature -- bluer (lower) values indicate hotter white dwarfs",
    "prob_wd": "Probability of being a white dwarf (0-1), assigned by a random forest classifier trained on spectroscopically confirmed WDs; Pwd > 0.75 is commonly used as a high-confidence threshold",
    "teff_k": "Effective temperature in Kelvin, derived by fitting Gaia photometry and parallax to WD atmosphere models; range typically 4,000-100,000 K",
    "teff_error_k": "1-sigma uncertainty on effective temperature (K)",
    "log_g": "Surface gravity in log(cm/s^2), derived from atmosphere model fits; WDs have log g ~ 7-9, compared to ~4.4 for the Sun",
    "log_g_error": "1-sigma uncertainty on log surface gravity",
    "mass_msun": "Stellar mass in solar masses, derived from log g and Teff using mass-radius relations; WD mass distribution peaks near 0.6 Msun",
    "mass_error_msun": "1-sigma uncertainty on mass (solar masses)",
    "chi2": "Chi-squared goodness-of-fit from the atmosphere model fitting; high values may indicate poor fits or unusual objects",
    "radial_velocity_km_s": "Gaia radial velocity in km/s; available only for brighter WDs with sufficient spectral signal",
    "radial_velocity_error_km_s": "Uncertainty on radial velocity (km/s)",
    "ruwe": "Renormalized unit weight error from Gaia astrometry; values > 1.4 suggest binarity, source confusion, or poor astrometric solution",
    "g_abs_mag": "Absolute G-band magnitude, derived from apparent magnitude and parallax; WDs typically M_G = 10-16 mag",
    "distance_pc": "Distance in parsecs, derived from Gaia parallax using a Bayesian prior",
    "distance_error_pc": "Uncertainty on distance (parsecs)",
    "extinction_g": "Interstellar extinction in the G band (magnitudes); used to correct apparent magnitudes for dust",
    "ebp_rp": "Colour excess E(BP-RP) due to interstellar reddening; used to correct colours for dust",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
The definitive Gaia DR3 white dwarf catalog from Gentile Fusillo et al. (2021), containing \
high-confidence white dwarf candidates identified from ESA Gaia astrometry and photometry. \
Each source includes a WD probability score, atmospheric parameters (effective temperature, \
surface gravity), mass estimates, and multi-band photometry.

White dwarfs are the dense stellar remnants left after low- and intermediate-mass stars \
exhaust their nuclear fuel. They represent the final evolutionary stage of over 95% of all \
stars. This catalog was constructed by selecting Gaia DR3 sources in the white dwarf region \
of the Hertzsprung-Russell diagram and assigning each a probability of being a genuine WD \
(prob_wd) using a random forest classifier trained on spectroscopically confirmed samples.

Atmospheric parameters (Teff, log g) and masses were derived by fitting Gaia photometry \
and parallaxes to hydrogen-atmosphere (DA) and helium-atmosphere (DB) white dwarf models.

White dwarfs are remarkably compact objects, packing roughly the mass of the Sun into a \
volume comparable to the Earth. Their interiors are supported against gravitational collapse \
not by nuclear fusion but by electron degeneracy pressure -- a quantum mechanical effect that \
sets a theoretical upper mass limit near 1.4 solar masses (the Chandrasekhar limit). The \
mass distribution of white dwarfs peaks sharply near 0.6 solar masses, reflecting the \
initial-to-final mass relation that maps a main-sequence progenitor of several solar masses \
down to a compact remnant through extensive mass loss on the asymptotic giant branch.

Because white dwarfs cool predictably over billions of years -- radiating away their \
residual thermal energy with well-understood physics -- they serve as cosmic chronometers. \
The white dwarf luminosity function (the number of white dwarfs per luminosity bin) encodes \
the age of the Galactic disk: the faint end cutoff corresponds to the oldest, coolest white \
dwarfs and provides an independent age estimate of 8-10 Gyr for the thin disk.
"""


def main():
    print("Fetching Gaia DR3 White Dwarfs (Gentile Fusillo+ 2021) from VizieR...")
    df = vizier_query(ADQL, timeout=600)
    print(f"  {len(df):,} raw rows")

    # Drop VizieR internal recno
    if "recno" in df.columns:
        df = df.drop(columns=["recno"])

    df = df.rename(columns={k: v for k, v in RENAME.items() if k in df.columns})

    # Convert source_id to string (Gaia source IDs are 64-bit ints)
    if "source_id" in df.columns:
        df["source_id"] = df["source_id"].astype(str).str.strip()

    # Clean string columns
    for col in ["wdj_name"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
            )

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Sort by source_id
    if "source_id" in df.columns:
        df = df.sort_values("source_id").reset_index(drop=True)

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    g_median = df["g_mag"].median() if "g_mag" in df.columns else float("nan")
    teff_median = df["teff_k"].median() if "teff_k" in df.columns else float("nan")
    mass_median = df["mass_msun"].median() if "mass_msun" in df.columns else float("nan")
    pwd_median = df["prob_wd"].median() if "prob_wd" in df.columns else float("nan")
    n_high_prob = int((df["prob_wd"] > 0.75).sum()) if "prob_wd" in df.columns else 0

    quick_stats = f"""\
- **{n_total:,}** white dwarf candidates
- **{n_high_prob:,}** with Pwd > 0.75 (high confidence)
- Median G magnitude: {g_median:.2f}
- Median Teff: {teff_median:,.0f} K
- Median mass: {mass_median:.2f} Msun
- Median Pwd: {pwd_median:.3f}"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/gaia-dr3-white-dwarfs", split="train")
df = ds.to_pandas()

# High-confidence white dwarfs
high_conf = df[df["prob_wd"] > 0.75]
print(f"High-confidence WDs: {len(high_conf):,}")

# HR diagram
import matplotlib.pyplot as plt
valid = df.dropna(subset=["bp_rp", "g_abs_mag"])
plt.hexbin(valid["bp_rp"], valid["g_abs_mag"], gridsize=200, mincnt=1, cmap="hot")
plt.colorbar(label="Count")
plt.xlabel("BP - RP (mag)")
plt.ylabel("Absolute G (mag)")
plt.gca().invert_yaxis()
plt.title("Gaia DR3 White Dwarf HR Diagram")
plt.show()

# Mass distribution
df["mass_msun"].dropna().hist(bins=100)
plt.xlabel("Mass (solar masses)")
plt.ylabel("Count")
plt.title("White Dwarf Mass Distribution")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Gaia DR3 White Dwarfs",
        description=DESCRIPTION,
        tags=["space", "gaia", "white-dwarfs", "stars", "esa", "astronomy",
              "open-data", "tabular-data", "parquet"],
        source_url="https://vizier.cds.unistra.fr/viz-bin/VizieR-3?-source=J/MNRAS/508/3877",
        license="other",
        license_name="cc-by-nc-3.0-igo",
        license_link="https://creativecommons.org/licenses/by-nc/3.0/igo/",
        task_categories=["tabular-classification", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e000191/GSFC_20171208_Archive_e000191~medium.jpg",
            "alt": "A youthful globular star cluster observed by the Hubble Space Telescope",
            "credit": "NASA/ESA/Hubble",
        },
        related_datasets=[
            "juliensimon/gaia-dr3-eclipsing-binaries",
            "juliensimon/gcvs-variable-stars",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "ra_deg", "dec_deg", "parallax_mas", "parallax_error_mas",
                "pmra_mas_yr", "pmra_error_mas_yr", "pmdec_mas_yr", "pmdec_error_mas_yr",
                "g_mag", "g_mag_error", "bp_mag", "bp_mag_error", "rp_mag", "rp_mag_error",
                "bp_rp", "prob_wd", "teff_k", "teff_error_k", "log_g", "log_g_error",
                "mass_msun", "mass_error_msun", "chi2", "radial_velocity_km_s",
                "radial_velocity_error_km_s", "ruwe", "g_abs_mag",
                "distance_pc", "distance_error_pc", "extinction_g", "ebp_rp",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="gaia_dr3_white_dwarfs.parquet",
            min_rows=250_000,
            expected_columns=["source_id", "ra_deg", "dec_deg", "prob_wd"],
            critical_columns=["source_id", "ra_deg", "dec_deg"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Gaia DR3 white dwarfs: {n_total:,} sources",
        )
    print("Done.")


if __name__ == "__main__":
    main()
