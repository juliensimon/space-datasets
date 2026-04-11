#!/usr/bin/env python3
"""Fetch RAVE DR6 stellar parameters from VizieR and upload to HF.

Source: Steinmetz et al. (2020), "The Sixth Data Release of the Radial
Velocity Experiment (RAVE)", AJ, 160, 83.
VizieR catalog: III/283
"""

import re

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/rave-dr6"

ADQL = 'SELECT * FROM "III/283/ravedr6"'

# ── Column mapping ───────────────────────────────────────────────────
RENAME = {
    # Identifiers
    "RAVEID": "rave_id",
    "Target": "rave_id",
    "RAVE_OBS_ID": "rave_id",
    # Coordinates
    "RA_ICRS": "ra_deg",
    "RAJ2000": "ra_deg",
    "RAdeg": "ra_deg",
    "DE_ICRS": "dec_deg",
    "DEJ2000": "dec_deg",
    "DEdeg": "dec_deg",
    # Proper motions
    "pmRA": "pm_ra_mas_yr",
    "pmDE": "pm_dec_mas_yr",
    "e_pmRA": "pm_ra_error_mas_yr",
    "e_pmDE": "pm_dec_error_mas_yr",
    # Parallax
    "plx": "parallax_mas",
    "e_plx": "parallax_error_mas",
    # Radial velocity
    "HRV": "radial_velocity_kms",
    "RV": "radial_velocity_kms",
    "eHRV": "radial_velocity_error_kms",
    "e_HRV": "radial_velocity_error_kms",
    "e_RV": "radial_velocity_error_kms",
    # Stellar parameters
    "Teff_K": "teff_k",
    "Teff": "teff_k",
    "TeffK": "teff_k",
    "e_Teff_K": "teff_error_k",
    "e_Teff": "teff_error_k",
    "logg_K": "logg",
    "logg": "logg",
    "e_logg_K": "logg_error",
    "e_logg": "logg_error",
    "Met_K": "metallicity_fe_h",
    "__Fe_H_": "metallicity_fe_h",
    "_Fe_H_": "metallicity_fe_h",
    "[Fe/H]": "metallicity_fe_h",
    "Met_N_K": "metallicity_fe_h",
    "e_Met_K": "metallicity_error",
    "e__Fe_H_": "metallicity_error",
    "e_Met_N_K": "metallicity_error",
    # Photometry
    "Jmag": "j_mag",
    "Hmag": "h_mag",
    "Kmag": "k_mag",
    "e_Jmag": "j_mag_error",
    "e_Hmag": "h_mag_error",
    "e_Kmag": "k_mag_error",
    "Gmag": "gaia_g_mag",
    "BPmag": "gaia_bp_mag",
    "RPmag": "gaia_rp_mag",
    # Alpha enhancement
    "__a_Fe_": "alpha_fe",
    "_a_Fe_": "alpha_fe",
    "[a/Fe]": "alpha_fe",
    "e__a_Fe_": "alpha_fe_error",
    # Individual abundances
    "__Al_H_": "al_h",
    "__Fe_H_N": "fe_h_n",
    "__Mg_H_": "mg_h",
    "__Ni_H_": "ni_h",
    "__Si_H_": "si_h",
    "__Ti_H_": "ti_h",
    "__O_H_": "o_h",
    # Signal-to-noise
    "SNR_K": "snr",
    "STN": "snr",
    "S_N": "snr",
    "SNR": "snr",
    # Gaia cross-match
    "GaiaDR2": "gaia_dr2_source_id",
    "Source": "gaia_dr2_source_id",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "rave_id": "Unique RAVE observation identifier; format encodes field, fiber, and observation date; one star may have multiple observations with different RAVE IDs",
    "ra_deg": "ICRS right ascension in degrees (0-360) from Gaia DR2 cross-match or original RAVE target coordinates",
    "dec_deg": "ICRS declination in degrees (-90 to +90) from Gaia DR2 cross-match or original RAVE target coordinates",
    "pm_ra_mas_yr": "Proper motion in RA (mu_alpha * cos(delta)) in mas/yr from Gaia DR2; null if no Gaia match",
    "pm_dec_mas_yr": "Proper motion in declination in mas/yr from Gaia DR2; null if no Gaia match",
    "pm_ra_error_mas_yr": "1-sigma uncertainty on pm_ra_mas_yr in mas/yr; null if no Gaia match",
    "pm_dec_error_mas_yr": "1-sigma uncertainty on pm_dec_mas_yr in mas/yr; null if no Gaia match",
    "parallax_mas": "Gaia DR2 parallax in milliarcseconds; null if no Gaia match or poor astrometric solution",
    "parallax_error_mas": "1-sigma uncertainty on parallax in mas; null if parallax is null",
    "radial_velocity_kms": "Heliocentric radial velocity in km/s from RAVE spectra; typical accuracy ~1 km/s; the primary science product of the RAVE survey",
    "radial_velocity_error_kms": "1-sigma uncertainty on radial velocity in km/s; null if RV could not be reliably measured",
    "teff_k": "Effective temperature in Kelvin from the MADERA pipeline; range ~3500-8000 K for the RAVE magnitude range; null if spectral fit failed",
    "teff_error_k": "1-sigma uncertainty on effective temperature in K; null if teff_k is null",
    "logg": "Surface gravity log(g) in dex (cgs); giants ~1-3, dwarfs ~4-5; from MADERA pipeline; null if spectral fit failed",
    "logg_error": "1-sigma uncertainty on log(g) in dex; null if logg is null",
    "metallicity_fe_h": "Overall metallicity [Fe/H] in dex relative to solar; metal-poor stars < -1.0, solar ~0.0, metal-rich > +0.3; null if spectral fit failed",
    "metallicity_error": "1-sigma uncertainty on [Fe/H] in dex; null if metallicity is null",
    "j_mag": "2MASS J-band (1.25 um) apparent magnitude; null if no 2MASS match",
    "h_mag": "2MASS H-band (1.65 um) apparent magnitude; null if no 2MASS match",
    "k_mag": "2MASS Ks-band (2.17 um) apparent magnitude; null if no 2MASS match",
    "j_mag_error": "1-sigma uncertainty on J magnitude; null if j_mag is null",
    "h_mag_error": "1-sigma uncertainty on H magnitude; null if h_mag is null",
    "k_mag_error": "1-sigma uncertainty on Ks magnitude; null if k_mag is null",
    "gaia_g_mag": "Gaia DR2 G-band (330-1050 nm) apparent magnitude; null if no Gaia match",
    "gaia_bp_mag": "Gaia DR2 BP-band (330-680 nm) apparent magnitude; null if no Gaia match",
    "gaia_rp_mag": "Gaia DR2 RP-band (630-1050 nm) apparent magnitude; null if no Gaia match",
    "alpha_fe": "[alpha/Fe] abundance ratio in dex; alpha-enhanced stars (> +0.2) are typically old thick-disk or halo populations; null if not measured",
    "alpha_fe_error": "1-sigma uncertainty on [alpha/Fe] in dex; null if alpha_fe is null",
    "al_h": "[Al/H] aluminum abundance in dex relative to solar; null if not measured from spectrum",
    "fe_h_n": "[Fe/H] metallicity from the N pipeline variant; null if not measured",
    "mg_h": "[Mg/H] magnesium abundance in dex relative to solar; an alpha-element tracer of enrichment by Type II supernovae; null if not measured",
    "ni_h": "[Ni/H] nickel abundance in dex relative to solar; an iron-peak element; null if not measured",
    "si_h": "[Si/H] silicon abundance in dex relative to solar; an alpha-element; null if not measured",
    "ti_h": "[Ti/H] titanium abundance in dex relative to solar; an alpha-element; null if not measured",
    "o_h": "[O/H] oxygen abundance in dex relative to solar; the most abundant metal; null if not measured",
    "snr": "Signal-to-noise ratio per pixel of the RAVE spectrum; higher SNR yields more reliable parameters; typical range 10-100+",
    "gaia_dr2_source_id": "Gaia DR2 source identifier for cross-matching; null if no reliable Gaia match was found",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
The Radial Velocity Experiment (RAVE) Data Release 6 is the final release of this major \
southern-hemisphere stellar spectroscopic survey. It contains over 500,000 spectral observations \
of ~452,000 unique stars, providing radial velocities, stellar atmospheric parameters \
(effective temperature, surface gravity, metallicity), and individual elemental abundances.

RAVE observed stars in the magnitude range 9 < I < 12 using the 6dF multi-object spectrograph \
on the 1.2m UK Schmidt Telescope at the Australian Astronomical Observatory. The survey \
operated from 2003 to 2013, covering the calcium triplet region (8410-8795 A) at a spectral \
resolution of R ~ 7500.

DR6 provides radial velocities with a typical accuracy of ~1 km/s, effective temperatures, \
surface gravities, overall metallicities, and individual abundances for elements including \
Mg, Al, Si, Ti, Fe, and Ni. Stellar parameters were derived using an updated pipeline \
combining the MADERA algorithm with spectro-photometric information from 2MASS and Gaia DR2.

RAVE was one of the pioneering large-scale stellar spectroscopic surveys, conceived in the \
early 2000s to measure radial velocities for hundreds of thousands of stars and thereby map \
the kinematic structure of the Milky Way. Its focus on the calcium triplet region was a \
deliberate choice: these strong absorption lines are detectable even at modest spectral \
resolution and in relatively faint stars, making them ideal for efficient radial velocity \
measurements.

The survey's target selection in the magnitude range 9 < I < 12 means RAVE primarily sampled \
giant stars at distances of 1-3 kpc and nearby dwarf stars within a few hundred parsecs. \
When combined with Gaia astrometry (proper motions and parallaxes), RAVE radial velocities \
complete the six-dimensional phase-space information needed to compute full Galactic orbits, \
enabling dynamical studies of stellar streams, moving groups, and the local dark matter density.
"""


def main():
    print("Fetching RAVE DR6 stellar parameters from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} RAVE DR6 observations")

    # Drop VizieR internal columns
    for col in ["recno", "SimbadName", "More"]:
        if col in df.columns:
            df = df.drop(columns=[col])

    # Rename columns
    df = df.rename(columns={k: v for k, v in RENAME.items() if k in df.columns})

    # Snake_case remaining columns not yet renamed
    def to_snake(name):
        if name == name.lower() and "_" in name:
            return name
        s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
        s = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s)
        s = s.replace("-", "_").replace(" ", "_").lower()
        s = re.sub(r"_+", "_", s).strip("_")
        return s

    df.columns = [to_snake(c) for c in df.columns]

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_with_teff = int(df["teff_k"].notna().sum()) if "teff_k" in df.columns else 0
    n_with_met = int(df["metallicity_fe_h"].notna().sum()) if "metallicity_fe_h" in df.columns else 0
    n_with_rv = int(df["radial_velocity_kms"].notna().sum()) if "radial_velocity_kms" in df.columns else 0
    teff_min = df["teff_k"].min() if "teff_k" in df.columns else 0
    teff_max = df["teff_k"].max() if "teff_k" in df.columns else 0
    met_min = df["metallicity_fe_h"].min() if "metallicity_fe_h" in df.columns else 0
    met_max = df["metallicity_fe_h"].max() if "metallicity_fe_h" in df.columns else 0

    quick_stats = f"""\
- **{n_total:,}** spectral observations
- **{n_with_rv:,}** with radial velocities
- **{n_with_teff:,}** with effective temperature (range: {teff_min:.0f} - {teff_max:.0f} K)
- **{n_with_met:,}** with metallicity ([Fe/H] range: {met_min:.2f} to {met_max:.2f} dex)"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/rave-dr6", split="train")
df = ds.to_pandas()

# Metallicity distribution
import matplotlib.pyplot as plt
met = df["metallicity_fe_h"].dropna()
plt.hist(met, bins=100, edgecolor="none")
plt.xlabel("[Fe/H] (dex)")
plt.ylabel("Count")
plt.title("RAVE DR6 Metallicity Distribution")
plt.show()

# HR diagram (Teff vs log g)
valid = df.dropna(subset=["teff_k", "logg"])
plt.figure()
plt.scatter(valid["teff_k"], valid["logg"], s=0.1, alpha=0.3)
plt.gca().invert_xaxis()
plt.gca().invert_yaxis()
plt.xlabel("Teff (K)")
plt.ylabel("log g (dex)")
plt.title("RAVE DR6 Kiel Diagram")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="RAVE DR6 Stellar Parameters",
        description=DESCRIPTION,
        tags=["space", "stars", "stellar", "spectroscopy", "radial-velocity",
              "rave", "astronomy", "open-data", "tabular-data", "parquet"],
        source_url="https://vizier.cds.unistra.fr/viz-bin/VizieR-3?-source=III/283",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e000191/GSFC_20171208_Archive_e000191~medium.jpg",
            "alt": "A youthful globular star cluster observed by the Hubble Space Telescope",
            "credit": "NASA/ESA/Hubble",
        },
        related_datasets=[
            "juliensimon/wolf-rayet-stars",
            "juliensimon/brown-dwarf-catalog",
            "juliensimon/galah-dr4-stellar-abundances",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "ra_deg", "dec_deg",
                "pm_ra_mas_yr", "pm_dec_mas_yr", "pm_ra_error_mas_yr", "pm_dec_error_mas_yr",
                "parallax_mas", "parallax_error_mas",
                "radial_velocity_kms", "radial_velocity_error_kms",
                "teff_k", "teff_error_k",
                "logg", "logg_error",
                "metallicity_fe_h", "metallicity_error",
                "j_mag", "h_mag", "k_mag",
                "j_mag_error", "h_mag_error", "k_mag_error",
                "gaia_g_mag", "gaia_bp_mag", "gaia_rp_mag",
                "alpha_fe", "alpha_fe_error",
                "al_h", "mg_h", "ni_h", "si_h", "ti_h", "o_h",
                "snr",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="rave_dr6.parquet",
            min_rows=400_000,
            expected_columns=["ra_deg", "dec_deg", "radial_velocity_kms"],
            critical_columns=["ra_deg", "dec_deg", "radial_velocity_kms"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update RAVE DR6 stellar parameters: {n_total:,} observations",
        )
    print("Done.")


if __name__ == "__main__":
    main()
