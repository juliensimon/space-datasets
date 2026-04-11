#!/usr/bin/env python3
"""Fetch HECATE (Heraklion Extragalactic Catalogue) and upload to HF.

Source: https://hecate.ia.forth.gr/ (Kovlakas et al. 2021, MNRAS, 506, 1896)
The catalog is not available on VizieR TAP, so we download the CSV directly.
"""

import io

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

HF_REPO = "juliensimon/hecate-nearby-galaxies"

HECATE_CSV_URL = "https://hecate.ia.forth.gr/assets/files/HECATE_v1.1.csv"

# ── Column mapping ───────────────────────────────────────────────────
RENAME = {
    # Position
    "RA": "ra_deg",
    "DEC": "dec_deg",
    # Identifiers
    "PGC": "pgc",
    "OBJNAME": "name",
    "ID_NED": "id_ned",
    "ID_2MASS": "id_2mass",
    # Distance
    "D": "distance_mpc",
    "E_D": "distance_mpc_err",
    "NDIST": "n_distances",
    "DMETHOD": "distance_method",
    # Morphology
    "T": "morphological_type",
    "E_T": "morphological_type_err",
    "INCL": "inclination_deg",
    # Radial velocity
    "V": "radial_velocity",
    "E_V": "radial_velocity_err",
    "V_VIR": "radial_velocity_virgo",
    # Size
    "R1": "r1_arcmin",
    "R2": "r2_arcmin",
    "PA": "position_angle",
    # Photometry
    "BT": "b_mag",
    "E_BT": "b_mag_err",
    "J": "j_mag",
    "H": "h_mag",
    "K": "k_mag",
    "E_J": "j_mag_err",
    "E_H": "h_mag_err",
    "E_K": "k_mag_err",
    # Extinction
    "AG": "extinction_g",
    "AI": "extinction_i",
    # Luminosities
    "logL_TIR": "log_l_tir",
    "logL_FIR": "log_l_fir",
    "logL_K": "log_l_k",
    # Star formation rate
    "logSFR_HEC": "log_sfr",
    "FLAG_SFR_HEC": "log_sfr_flag",
    "logSFR_TIR": "log_sfr_tir",
    "logSFR_FIR": "log_sfr_fir",
    # Stellar mass
    "logM_HEC": "log_stellar_mass",
    "logM_GSW": "log_stellar_mass_gsw",
    # Metallicity
    "METAL": "metallicity",
    "FLAG_METAL": "metallicity_flag",
    # Nuclear activity
    "CLASS_SP": "spectral_class",
    "AGN_S17": "agn_satyapal17",
    "AGN_HEC": "activity_class",
    # ML ratio
    "ML_RATIO": "ml_ratio",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "pgc": "Principal Galaxies Catalogue number; unique integer identifier from HyperLEDA; the primary key for cross-matching with other galaxy catalogs",
    "name": "Primary galaxy name from HyperLEDA (e.g., 'NGC0224', 'UGC12345'); typically the most common catalog designation",
    "id_ned": "NASA/IPAC Extragalactic Database (NED) identifier; allows direct lookup in the NED service for additional data and references",
    "id_2mass": "2MASS Extended Source Catalog identifier; links to near-infrared photometry from the Two Micron All Sky Survey",
    "ra_deg": "Right ascension in decimal degrees (J2000.0 ICRS, 0-360); from HyperLEDA homogenized coordinates",
    "dec_deg": "Declination in decimal degrees (J2000.0 ICRS, -90 to +90); from HyperLEDA homogenized coordinates",
    "distance_mpc": "Luminosity distance in megaparsecs; derived from redshift-independent measurements where available, otherwise from Hubble flow with H0 = 70 km/s/Mpc; used for computing absolute magnitudes and physical sizes",
    "distance_mpc_err": "1-sigma uncertainty on distance in Mpc; reflects the measurement method: Cepheid/TRGB distances are precise to ~5%, Hubble-flow estimates to ~15-20%",
    "n_distances": "Number of independent distance measurements available for this galaxy; higher values indicate more robust distance estimates",
    "distance_method": "Primary method used for the adopted distance estimate (e.g., 'Cepheid', 'TRGB', 'SBF', 'TF', 'Hubble'); null when only Hubble-flow distance is available",
    "morphological_type": "Numerical de Vaucouleurs morphological T-type: -5 (elliptical E) through 0 (S0/a) to +10 (irregular Im); negative = early-type, positive = late-type spirals and irregulars",
    "morphological_type_err": "Uncertainty on the morphological T-type classification; typically 1-2 units",
    "inclination_deg": "Galaxy inclination angle in degrees (0 = face-on, 90 = edge-on); derived from the apparent axis ratio and morphological type; important for correcting observed properties for projection effects",
    "radial_velocity": "Heliocentric radial velocity in km/s from HyperLEDA; the raw observed Doppler shift uncorrected for solar motion",
    "radial_velocity_err": "1-sigma uncertainty on heliocentric radial velocity in km/s",
    "radial_velocity_virgo": "Radial velocity corrected for Virgo-centric infall in km/s; accounts for the gravitational pull of the Virgo cluster on the Local Group; more suitable for distance estimation than raw heliocentric velocity",
    "r1_arcmin": "Semi-major axis of the galaxy at the 25 mag/arcsec^2 B-band isophote in arcminutes; the standard optical size measure from HyperLEDA",
    "r2_arcmin": "Semi-minor axis at the 25 mag/arcsec^2 isophote in arcminutes; r2/r1 gives the apparent axis ratio used to derive inclination",
    "position_angle": "Position angle of the galaxy major axis in degrees, measured north through east (0-180); used for orientation in imaging and spectroscopy",
    "b_mag": "Total apparent B-band (Johnson, ~440 nm) magnitude from HyperLEDA; corrected for Galactic extinction and internal absorption; brighter objects have smaller values",
    "b_mag_err": "1-sigma uncertainty on the B-band magnitude",
    "j_mag": "2MASS J-band (~1.25 um) total apparent magnitude; less affected by dust extinction than optical bands",
    "h_mag": "2MASS H-band (~1.65 um) total apparent magnitude",
    "k_mag": "2MASS Ks-band (~2.17 um) total apparent magnitude; closely traces stellar mass and is minimally affected by dust and recent star formation",
    "j_mag_err": "1-sigma uncertainty on J-band magnitude",
    "h_mag_err": "1-sigma uncertainty on H-band magnitude",
    "k_mag_err": "1-sigma uncertainty on Ks-band magnitude",
    "extinction_g": "Galactic extinction in the g-band (mag) from Schlegel/Schlafly dust maps; used to correct observed magnitudes for Milky Way foreground dust",
    "extinction_i": "Galactic extinction in the i-band (mag) from Schlegel/Schlafly dust maps",
    "log_l_tir": "Log10 total infrared luminosity (8-1000 um) in solar luminosities; traces obscured star formation and AGN heating of dust; derived from IRAS fluxes",
    "log_l_fir": "Log10 far-infrared luminosity (40-120 um) in solar luminosities; a more focused tracer of cold dust heated by young stars; from IRAS 60 and 100 um fluxes",
    "log_l_k": "Log10 Ks-band luminosity in solar luminosities; a proxy for total stellar mass since old stars dominate the near-infrared light",
    "log_sfr": "Log10 HECATE star formation rate in solar masses per year; derived from a combination of UV and infrared indicators; the primary SFR estimate in the catalog",
    "log_sfr_flag": "Quality flag for the HECATE SFR estimate; indicates the data sources and methods used in the derivation",
    "log_sfr_tir": "Log10 star formation rate derived from total infrared luminosity alone (M_sun/yr); assumes all TIR emission comes from dust heated by young stars",
    "log_sfr_fir": "Log10 star formation rate derived from far-infrared luminosity alone (M_sun/yr)",
    "log_stellar_mass": "Log10 stellar mass in solar masses from HECATE; derived from Ks-band luminosity and a mass-to-light ratio that depends on morphological type; typical range 7-12",
    "log_stellar_mass_gsw": "Log10 stellar mass from the GALEX-SDSS-WISE Legacy Catalog (GSWLC); derived from UV-optical-IR SED fitting; available only for galaxies in the SDSS footprint",
    "metallicity": "Gas-phase oxygen abundance 12 + log(O/H); solar metallicity is ~8.69; available from emission-line spectroscopy for a subset of galaxies",
    "metallicity_flag": "Quality flag for the metallicity measurement; indicates the calibration method used (e.g., direct T_e, strong-line R23, N2)",
    "spectral_class": "Optical spectral classification from emission-line ratios on the BPT diagram: 'HII' (star-forming), 'Sy' (Seyfert AGN), 'LINER' (low-ionization AGN), 'Comp' (composite); null for galaxies without emission-line spectroscopy",
    "agn_satyapal17": "AGN classification from Satyapal et al. (2017) using mid-infrared color diagnostics from WISE; 'AGN' or null; identifies obscured AGN missed by optical spectroscopy",
    "activity_class": "HECATE nuclear activity classification combining optical and infrared diagnostics; summarizes AGN presence from multiple indicators",
    "ml_ratio": "Ks-band mass-to-light ratio (M/L_K in solar units) adopted for stellar mass estimation; varies with morphological type from ~0.4 (late-type spirals) to ~1.0 (ellipticals)",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
The Heraklion Extragalactic Catalogue (HECATE) is a value-added catalog of galaxies \
within 200 Mpc, designed as a reference for multi-messenger astrophysics and the \
study of the local universe. Published by Kovlakas et al. (2021, MNRAS, 506, 1896), HECATE \
provides homogenised physical properties including stellar masses, star formation rates, \
metallicities, morphological types, and nuclear activity classifications.

HECATE aggregates data from HyperLEDA, 2MASS, IRAS, and other major surveys to provide \
a uniform census of the nearby galaxy population. Each galaxy entry includes positional \
data, distance estimates, photometry in multiple bands, and derived physical properties. \
The catalog is particularly useful for identifying host galaxies of transient events \
(gravitational waves, neutrinos, gamma-ray bursts) and for statistical studies of galaxy \
properties in the local volume.

The local universe within 200 Mpc provides the highest-resolution view of the galaxy \
population and serves as the calibration anchor for cosmological studies at greater \
distances. HECATE is specifically optimized for this volume, drawing on the HyperLEDA \
database for homogenized distances and photometry, and augmenting it with infrared \
luminosities from IRAS, near-infrared magnitudes from 2MASS, and stellar masses derived \
from K-band mass-to-light ratios. The inclusion of nuclear activity classifications \
(Seyfert, LINER, HII, and composite) makes it possible to study how AGN prevalence varies \
with galaxy mass, morphology, and environment in a volume-complete sample.

A key motivation for HECATE is multi-messenger astrophysics. Gravitational-wave detectors \
such as LIGO and Virgo localize merging compact binaries to sky areas of tens to hundreds \
of square degrees, and identifying the host galaxy requires a comprehensive census of all \
galaxies within the relevant distance range. Similarly, high-energy neutrino events detected \
by IceCube and gamma-ray transients from Fermi and Swift require rapid cross-matching \
against known galaxy catalogs to identify electromagnetic counterparts.
"""


def main():
    print("Downloading HECATE v1.1 from hecate.ia.forth.gr...")
    resp = requests.get(HECATE_CSV_URL, timeout=180)
    resp.raise_for_status()
    print(f"  Downloaded {len(resp.content):,} bytes")

    df = pd.read_csv(io.StringIO(resp.text))
    print(f"  {len(df):,} galaxies, {len(df.columns)} columns")

    # Apply only columns that exist
    rename = {k: v for k, v in RENAME.items() if k in df.columns}
    df = df.rename(columns=rename)

    # Drop recno helper column
    if "recno" in df.columns:
        df = df.drop(columns=["recno"])

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Sort by PGC number if available, else by RA
    if "pgc" in df.columns:
        df = df.sort_values("pgc").reset_index(drop=True)
    elif "ra_deg" in df.columns:
        df = df.sort_values("ra_deg").reset_index(drop=True)

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_with_mass = int(df["log_stellar_mass"].notna().sum()) if "log_stellar_mass" in df.columns else 0
    n_with_sfr = int(df["log_sfr"].notna().sum()) if "log_sfr" in df.columns else 0
    n_with_morph = int(df["morphological_type"].notna().sum()) if "morphological_type" in df.columns else 0
    n_with_activity = int(df["activity_class"].notna().sum()) if "activity_class" in df.columns else 0
    median_dist = df["distance_mpc"].median() if "distance_mpc" in df.columns else 0

    quick_stats = f"""\
- **{n_total:,}** galaxies within 200 Mpc
- **{n_with_mass:,}** with stellar mass estimates
- **{n_with_sfr:,}** with star formation rates
- **{n_with_morph:,}** with morphological classifications
- **{n_with_activity:,}** with nuclear activity classifications
- Median distance: **{median_dist:.1f} Mpc**"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/hecate-nearby-galaxies", split="train")
df = ds.to_pandas()

# Massive galaxies (log stellar mass > 11)
massive = df[df["log_stellar_mass"] > 11]
print(f"{len(massive):,} massive galaxies")

# Star-forming galaxies within 50 Mpc
nearby_sf = df[(df["distance_mpc"] <= 50) & (df["log_sfr"].notna())]
print(f"{len(nearby_sf):,} nearby galaxies with SFR")

# Morphological type distribution
import matplotlib.pyplot as plt
df["morphological_type"].dropna().hist(bins=30)
plt.xlabel("Morphological T-type")
plt.ylabel("Count")
plt.title("HECATE Galaxy Morphology Distribution")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="HECATE Nearby Galaxies",
        description=DESCRIPTION,
        tags=["space", "galaxies", "nearby-galaxies", "stellar-mass",
              "star-formation", "astronomy", "open-data", "tabular-data", "parquet"],
        source_url="https://hecate.ia.forth.gr/",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA12110/PIA12110~small.jpg",
            "alt": "Hubble Deep Field revealing myriad galaxies across cosmic time",
            "credit": "NASA/ESA/STScI",
        },
        related_datasets=[
            "juliensimon/cosmicflows-galaxy-distances",
            "juliensimon/messier-catalog",
            "juliensimon/ngc-ic-catalog",
        ],
    ) as p:
        numeric_cols = [
            "pgc", "ra_deg", "dec_deg",
            "distance_mpc", "distance_mpc_err",
            "log_stellar_mass", "log_stellar_mass_gsw",
            "log_sfr", "log_sfr_tir", "log_sfr_fir",
            "metallicity",
            "morphological_type", "morphological_type_err",
            "b_mag", "b_mag_err", "j_mag", "h_mag", "k_mag",
            "j_mag_err", "h_mag_err", "k_mag_err",
            "log_l_tir", "log_l_fir", "log_l_k",
            "radial_velocity", "radial_velocity_err", "radial_velocity_virgo",
            "r1_arcmin", "r2_arcmin", "position_angle",
            "inclination_deg",
            "extinction_g", "extinction_i",
            "ml_ratio", "n_distances",
        ]
        df = p.clean(
            df,
            numeric=[c for c in numeric_cols if c in df.columns],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="hecate_nearby_galaxies.parquet",
            min_rows=150_000,
            expected_columns=["ra_deg", "dec_deg", "name", "pgc"],
            critical_columns=["ra_deg", "dec_deg"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update HECATE nearby galaxies: {n_total:,} galaxies",
        )
    print("Done.")


if __name__ == "__main__":
    main()
