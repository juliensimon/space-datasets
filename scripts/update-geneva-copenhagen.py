#!/usr/bin/env python3
"""Fetch Geneva-Copenhagen Survey from VizieR and upload to HF.

Source: Casagrande L. et al. (2011, A&A 530, A138) — ages, metallicities,
and Galactic kinematics for F and G dwarf stars in the solar neighbourhood.
VizieR catalog: V/130/gcs3
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/geneva-copenhagen-stellar-survey"

ADQL = 'SELECT * FROM "V/130/gcs3"'

# ── Column mapping ───────────────────────────────────────────────────
RENAME = {
    # Identifiers
    "HIP": "hip_id",
    "Name": "name",
    # Coordinates
    "RAJ2000": "ra_deg",
    "RAICRS": "ra_deg",
    "RA_ICRS": "ra_deg",
    "_RA": "ra_deg",
    "DEJ2000": "dec_deg",
    "DEICRS": "dec_deg",
    "DE_ICRS": "dec_deg",
    "_DE": "dec_deg",
    # Photometry
    "Vmag": "v_mag",
    "b-y": "b_y",
    "m1": "m1",
    "c1": "c1",
    "Beta": "h_beta",
    # Stellar parameters
    "Teff": "teff_k",
    "logg": "logg",
    "__Fe_H_": "fe_h",
    "_Fe_H_": "fe_h",
    "Fe_H": "fe_h",
    "[Fe/H]": "fe_h",
    # Ages
    "logAge": "log_age",
    "logAge50": "log_age",
    "logAgeL": "log_age_lower",
    "logAgeU": "log_age_upper",
    "Age": "age_gyr",
    # Kinematics
    "U": "u_vel_km_s",
    "V": "v_vel_km_s",
    "W": "w_vel_km_s",
    "e_U": "u_vel_err",
    "e_V": "v_vel_err",
    "e_W": "w_vel_err",
    # Orbital parameters
    "Rmean": "r_mean_kpc",
    "e": "eccentricity",
    "ecc": "eccentricity",
    "Zmax": "z_max_kpc",
    # Distance / parallax
    "Dist": "distance_pc",
    "plx": "parallax_mas",
    "Plx": "parallax_mas",
    "e_Plx": "parallax_err_mas",
    "e_plx": "parallax_err_mas",
    # Binary / variability flags
    "Bin": "binary_flag",
    "Var": "variable_flag",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "hip_id": "Hipparcos catalog number; primary cross-identifier for GCS stars",
    "name": "Common or HD designation where available; null for anonymous entries",
    "ra_deg": "Right ascension, ICRS J2000.0, in decimal degrees (0-360)",
    "dec_deg": "Declination, ICRS J2000.0, in decimal degrees (-90 to +90)",
    "v_mag": "Johnson V-band apparent magnitude; GCS stars span roughly V = 5-9 mag (all stars within ~300 pc)",
    "b_y": "Stromgren b-y photometric index; primary temperature indicator for FGK stars; range ~0.2-0.6 mag",
    "m1": "Stromgren m1 = (v-b)-(b-y) metallicity index; increases with metallicity; used to derive [Fe/H]",
    "c1": "Stromgren c1 = (u-v)-(v-b) luminosity/gravity index; separates main-sequence from evolved stars",
    "h_beta": "Stromgren H-beta photometric index; temperature indicator for A-G stars; range ~2.5-2.7",
    "teff_k": "Effective temperature in Kelvin, derived from Stromgren photometry via infrared flux method calibration (Casagrande 2011); FGK range 4000-7500 K; typical uncertainty ~100 K; null if photometry insufficient",
    "logg": "Log surface gravity in cgs (log cm/s^2), from isochrone fitting; main sequence: 4.0-5.0, subgiants: 3.5-4.5; null if stellar parameters undetermined",
    "fe_h": "[Fe/H] iron abundance in dex relative to solar; solar neighbourhood range -1.5 to +0.5; typical uncertainty ~0.1 dex; null for ~5% of stars",
    "log_age": "Median log age in log(yr) from Bayesian isochrone fitting; e.g. log_age=9.7 = 5 Gyr; uncertainty often 0.2-0.5 dex for field stars; null if age poorly constrained",
    "log_age_lower": "Lower 1-sigma bound on log age (log yr); null where age is unconstrained",
    "log_age_upper": "Upper 1-sigma bound on log age (log yr); null where age is unconstrained",
    "age_gyr": "Median stellar age in Gyr from isochrone fitting; typical uncertainty 30-50% for individual field stars; null if isochrone placement fails",
    "u_vel_km_s": "Galactocentric U space velocity in km/s (positive toward Galactic centre); thin disk: |U| < 40 km/s; thick disk/halo stars reach |U| > 100 km/s",
    "v_vel_km_s": "Galactocentric V space velocity in km/s (positive in direction of Galactic rotation); thin disk near -20 km/s (asymmetric drift); halo stars strongly negative",
    "w_vel_km_s": "Galactocentric W space velocity in km/s (positive toward North Galactic Pole); thin disk: |W| < 25 km/s",
    "u_vel_err": "1-sigma uncertainty on U velocity (km/s)",
    "v_vel_err": "1-sigma uncertainty on V velocity (km/s)",
    "w_vel_err": "1-sigma uncertainty on W velocity (km/s)",
    "r_mean_kpc": "Time-averaged Galactocentric distance of the stellar orbit in kpc; all GCS stars orbit near 8 kpc",
    "eccentricity": "Orbital eccentricity (0 = circular); thin disk: e < 0.2; thick disk: e ~ 0.3-0.5; halo: e > 0.5",
    "z_max_kpc": "Maximum height above the Galactic plane reached during the orbit (kpc); thin disk < 0.3 kpc; thick disk 0.3-3 kpc",
    "distance_pc": "Hipparcos parallax-based distance in parsecs; all GCS stars within ~300 pc of the Sun",
    "parallax_mas": "Hipparcos parallax in milliarcseconds; typical precision 1-2 mas for these nearby stars",
    "parallax_err_mas": "1-sigma uncertainty on Hipparcos parallax (mas)",
    "binary_flag": "Binary star flag from the catalog — encodes known or suspected multiplicity; null if no binary information",
    "variable_flag": "Photometric variability flag; null if variability not detected or not assessed",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
The Geneva-Copenhagen Survey (GCS) is a comprehensive catalog of F and G dwarf stars in \
the solar neighbourhood, providing ages, metallicities, and full 3D space velocities. It \
is one of the most widely used datasets for studying the chemical and dynamical evolution \
of the Milky Way disk.

The GCS combines Stromgren photometry, Hipparcos astrometry, and radial velocities to derive \
fundamental stellar parameters. The third revision (Casagrande et al. 2011) provides improved \
effective temperatures based on the infrared flux method and re-derived ages, metallicities, \
and kinematics. This catalog is essential for studies of the age-metallicity relation, \
Galactic chemical evolution, and stellar population kinematics in the solar neighbourhood.

The GCS is unique among stellar surveys in providing reliable individual stellar ages for a \
large, volume-complete sample of solar-type stars. Age determination in stellar astrophysics \
is notoriously difficult -- unlike temperature and metallicity, age cannot be directly \
measured from a spectrum. The GCS derives ages by placing each star on theoretical isochrones \
in the HR diagram, using Stromgren photometric indices to determine effective temperatures and \
luminosities with sufficient precision to constrain evolutionary states.

The full three-dimensional space velocities (U, V, W) enable kinematic decomposition of the \
solar neighborhood into thin disk, thick disk, and halo populations using Toomre diagrams \
and orbital parameters. The catalog has been central to establishing the age-velocity \
dispersion relation, which shows that older stellar populations have progressively larger \
random velocities -- evidence for dynamical heating of the Galactic disk over billions of years.
"""


def main():
    print("Fetching Geneva-Copenhagen Survey from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} stars")

    # Only rename columns that actually exist
    rename_actual = {k: v for k, v in RENAME.items() if k in df.columns}
    df = df.rename(columns=rename_actual)

    # Clean string columns
    for col in ["name", "binary_flag", "variable_flag"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
            )

    # Convert HIP ID to integer where possible
    if "hip_id" in df.columns:
        df["hip_id"] = pd.to_numeric(df["hip_id"], errors="coerce").astype("Int64")

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Sort by HIP ID
    if "hip_id" in df.columns:
        df = df.sort_values("hip_id").reset_index(drop=True)

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_with_teff = int(df["teff_k"].notna().sum()) if "teff_k" in df.columns else 0
    n_with_feh = int(df["fe_h"].notna().sum()) if "fe_h" in df.columns else 0
    n_with_age = int(df["log_age"].notna().sum()) if "log_age" in df.columns else 0
    n_with_uvw = 0
    if all(c in df.columns for c in ["u_vel_km_s", "v_vel_km_s", "w_vel_km_s"]):
        n_with_uvw = int(df[["u_vel_km_s", "v_vel_km_s", "w_vel_km_s"]].notna().all(axis=1).sum())

    quick_stats = f"""\
- **{n_total:,}** solar neighbourhood F/G dwarf stars
- **{n_with_teff:,}** with effective temperature
- **{n_with_feh:,}** with metallicity [Fe/H]
- **{n_with_age:,}** with age estimate
- **{n_with_uvw:,}** with full UVW space velocities"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/geneva-copenhagen-stellar-survey", split="train")
df = ds.to_pandas()

# Age-metallicity relation
import matplotlib.pyplot as plt
valid = df.dropna(subset=["fe_h", "log_age"])
plt.scatter(valid["log_age"], valid["fe_h"], s=0.5, alpha=0.3)
plt.xlabel("Log Age (log yr)")
plt.ylabel("[Fe/H] (dex)")
plt.title("Age-Metallicity Relation (GCS)")

# Toomre diagram (kinematic populations)
valid = df.dropna(subset=["u_vel_km_s", "v_vel_km_s", "w_vel_km_s"])
v_total = (valid["u_vel_km_s"]**2 + valid["w_vel_km_s"]**2)**0.5
plt.figure()
plt.scatter(valid["v_vel_km_s"], v_total, s=0.5, alpha=0.3)
plt.xlabel("V (km/s)")
plt.ylabel("(U^2 + W^2)^0.5 (km/s)")
plt.title("Toomre Diagram (GCS)")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Geneva-Copenhagen Survey of Solar Neighbourhood",
        description=DESCRIPTION,
        tags=["space", "stars", "stellar-ages", "kinematics", "astronomy",
              "open-data", "tabular-data", "parquet"],
        source_url="https://vizier.cds.unistra.fr/viz-bin/VizieR-3?-source=V/130/gcs3",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e000191/GSFC_20171208_Archive_e000191~medium.jpg",
            "alt": "A youthful globular star cluster observed by the Hubble Space Telescope",
            "credit": "NASA/ESA/Hubble",
        },
        related_datasets=[
            "juliensimon/hipparcos-catalog",
            "juliensimon/cns5-nearby-stars",
            "juliensimon/nasa-exoplanets",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "ra_deg", "dec_deg", "v_mag", "b_y", "m1", "c1", "h_beta",
                "teff_k", "logg", "fe_h", "log_age", "log_age_lower", "log_age_upper",
                "age_gyr", "u_vel_km_s", "v_vel_km_s", "w_vel_km_s",
                "u_vel_err", "v_vel_err", "w_vel_err",
                "r_mean_kpc", "eccentricity", "z_max_kpc",
                "distance_pc", "parallax_mas", "parallax_err_mas",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="geneva_copenhagen_survey.parquet",
            min_rows=12_000,
            expected_columns=["ra_deg", "dec_deg"],
            critical_columns=["ra_deg", "dec_deg"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Geneva-Copenhagen Survey: {n_total:,} stars",
        )
    print("Done.")


if __name__ == "__main__":
    main()
