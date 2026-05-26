#!/usr/bin/env python3
"""Fetch Planck Catalogue of Galactic Cold Clumps (PGCC) from VizieR and upload to HF.

Static dataset — no GitHub Actions workflow.

Source: VizieR J/A+A/594/A28/pgcc
Cite:   Planck Collaboration XXVIII (2016), A&A, 594, A28
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/planck-cold-clumps"

# ── Source query ────────────────────────────────────────────────────
ADQL = 'SELECT * FROM "J/A+A/594/A28/pgcc"'

# ── Column mapping ──────────────────────────────────────────────────
RENAME = {
    "Name": "name",
    "GLON": "glon_deg",
    "GLAT": "glat_deg",
    "RAJ2000": "ra_deg",
    "DEJ2000": "dec_deg",
    "_RA": "ra_deg",
    "_DE": "dec_deg",
    "RA_ICRS": "ra_deg",
    "DE_ICRS": "dec_deg",
    "RAICRS": "ra_deg",
    "DEICRS": "dec_deg",
    "Maj": "major_axis_arcmin",
    "Min": "minor_axis_arcmin",
    "PA": "position_angle_deg",
    "Dist": "distance_pc",
    "e_Dist": "distance_err_pc",
    "SNR857": "snr_857ghz",
    "SNR545": "snr_545ghz",
    "SNR353": "snr_353ghz",
    "S857": "flux_857ghz_mjy",
    "S545": "flux_545ghz_mjy",
    "S353": "flux_353ghz_mjy",
    "e_S857": "flux_857ghz_err_mjy",
    "e_S545": "flux_545ghz_err_mjy",
    "e_S353": "flux_353ghz_err_mjy",
    "S3000": "flux_3000ghz_mjy",
    "e_S3000": "flux_3000ghz_err_mjy",
    "S857bg": "flux_857ghz_bg_mjy",
    "S545bg": "flux_545ghz_bg_mjy",
    "S353bg": "flux_353ghz_bg_mjy",
    "T": "temperature_k",
    "e_T": "temperature_err_k",
    "Tbg": "temperature_bg_k",
    "e_Tbg": "temperature_bg_err_k",
    "beta": "spectral_index",
    "e_beta": "spectral_index_err",
    "betabg": "spectral_index_bg",
    "e_betabg": "spectral_index_bg_err",
    "NH2": "column_density_cm2",
    "e_NH2": "column_density_err_cm2",
    "NH2bg": "column_density_bg_cm2",
    "e_NH2bg": "column_density_bg_err_cm2",
    "FluxType": "flux_type",
    "TType": "temperature_type",
    "FLUX_QUALITY": "flux_quality",
    "TEMP_QUALITY": "temp_quality",
    "DIST_QUALITY": "dist_quality",
}

# ── Column descriptions for README schema table ────────────────────
COLUMN_DESCRIPTIONS = {
    "name": "PGCC catalog designation (e.g. 'PGCC G000.00+00.00'); encodes Galactic coordinates of the clump center; the primary identifier in the Planck cold clump literature",
    "glon_deg": "Galactic longitude (degrees, 0-360); the clump's position projected onto the Galactic plane; clustering along spiral arms is expected",
    "glat_deg": "Galactic latitude (degrees, -90 to +90); most cold clumps are within a few degrees of the Galactic plane (|b| < 5 deg) tracing the thin disk molecular layer",
    "ra_deg": "Right ascension J2000 (degrees, 0-360); equatorial coordinate for cross-matching with other surveys",
    "dec_deg": "Declination J2000 (degrees, -90 to +90); equatorial coordinate for cross-matching with other surveys",
    "major_axis_arcmin": "Major axis FWHM of the clump from elliptical Gaussian fitting (arcmin); typical sizes 5-15 arcmin corresponding to 0.1-1 pc at nearby molecular cloud distances",
    "minor_axis_arcmin": "Minor axis FWHM of the clump (arcmin); the ratio major/minor indicates elongation, potentially tracing filamentary structure in the ISM",
    "position_angle_deg": "Position angle of the major axis (degrees, east of north); the orientation of the clump's elongation on the sky",
    "snr_857ghz": "Signal-to-noise ratio of the clump detection at 857 GHz (350 micron); the primary detection band where cold dust emission peaks",
    "snr_545ghz": "Signal-to-noise ratio at 545 GHz (550 micron); the second Planck submillimeter band used for cold clump detection",
    "snr_353ghz": "Signal-to-noise ratio at 353 GHz (850 micron); the lowest-frequency Planck band used in PGCC detection; traces the Rayleigh-Jeans tail of cold dust emission",
    "flux_857ghz_mjy": "Flux density at 857 GHz (mJy); the strongest submillimeter band for cold dust; combined with other bands to fit dust temperature and spectral index",
    "flux_545ghz_mjy": "Flux density at 545 GHz (mJy); intermediate submillimeter flux used in the modified blackbody SED fit",
    "flux_353ghz_mjy": "Flux density at 353 GHz (mJy); constrains the Rayleigh-Jeans slope of the dust SED",
    "flux_857ghz_err_mjy": "Flux density uncertainty at 857 GHz (mJy)",
    "flux_545ghz_err_mjy": "Flux density uncertainty at 545 GHz (mJy)",
    "flux_353ghz_err_mjy": "Flux density uncertainty at 353 GHz (mJy)",
    "flux_3000ghz_mjy": "Flux density at 3000 GHz / 100 micron (mJy); traces warmer dust; comparing 3000 GHz to 857 GHz flux constrains temperature when available",
    "flux_3000ghz_err_mjy": "Flux density uncertainty at 3000 GHz (mJy)",
    "flux_857ghz_bg_mjy": "Background flux density at 857 GHz (mJy); the local background subtracted from the clump emission to isolate the cold excess",
    "flux_545ghz_bg_mjy": "Background flux density at 545 GHz (mJy); local warm-dust background level",
    "flux_353ghz_bg_mjy": "Background flux density at 353 GHz (mJy); local background at the lowest detection frequency",
    "temperature_k": "Dust temperature of the clump (K); derived from modified blackbody fitting to the 3-band Planck photometry; typical values 6-20 K, with colder clumps more likely to be pre-stellar",
    "temperature_err_k": "1-sigma uncertainty on dust temperature (K)",
    "temperature_bg_k": "Background dust temperature (K); the temperature of the surrounding ISM; clumps are defined as being colder than this background",
    "temperature_bg_err_k": "Uncertainty on background temperature (K)",
    "spectral_index": "Dust spectral emissivity index (beta); controls how steeply emission falls at longer wavelengths; typical values 1.5-2.5; higher beta may indicate grain growth or ice mantles",
    "spectral_index_err": "1-sigma uncertainty on spectral index beta",
    "spectral_index_bg": "Background spectral emissivity index; the beta of the surrounding ISM for comparison with the clump value",
    "spectral_index_bg_err": "Uncertainty on background spectral index",
    "column_density_cm2": "H2 column density (cm^-2); derived from dust emission assuming a gas-to-dust ratio; high values (>10^22 cm^-2) indicate dense cores approaching gravitational instability",
    "column_density_err_cm2": "Uncertainty on H2 column density (cm^-2)",
    "column_density_bg_cm2": "Background H2 column density (cm^-2); the column density of the surrounding ISM",
    "column_density_bg_err_cm2": "Uncertainty on background column density (cm^-2)",
    "distance_pc": "Estimated distance to the clump (pc); derived from kinematic methods or association with known molecular clouds; null for many clumps without distance constraints",
    "distance_err_pc": "Uncertainty on distance estimate (pc)",
    "flux_type": "Flux estimation method flag indicating which photometric extraction method was used for this source",
    "temperature_type": "Temperature estimation method flag indicating which SED fitting approach was applied",
    "flux_quality": "Flux quality flag encoding the reliability of the photometric measurements",
    "temp_quality": "Temperature quality flag encoding the reliability of the SED-derived temperature",
    "dist_quality": "Distance quality flag encoding the reliability of the distance estimate",
}

# ── Dataset description ─────────────────────────────────────────────
DESCRIPTION = """\
The Planck Catalogue of Galactic Cold Clumps (PGCC) -- cold, dense sources in the \
interstellar medium detected by the ESA Planck satellite at submillimeter wavelengths, \
representing potential pre-stellar cores and sites of future star formation.

Galactic cold clumps are cold, dense regions in the interstellar medium (ISM) with dust \
temperatures typically between 6 and 20 K, significantly colder than their surrounding \
environment. These compact structures represent the earliest stages of the star formation \
process -- gravitationally bound or pre-gravitationally bound condensations that may \
eventually collapse to form protostars. Many are candidate pre-stellar cores, the seeds \
from which new stars and planetary systems will emerge.

The PGCC was compiled from the full Planck all-sky survey using a multi-frequency detection \
algorithm that identifies sources colder than their local background in the 857, 545, and \
353 GHz (350, 550, and 850 micron) bands. Planck's all-sky coverage at submillimeter \
wavelengths makes it uniquely suited for this task -- no other observatory has mapped the \
entire sky at these frequencies with comparable sensitivity.

Each PGCC entry includes flux densities at three Planck bands (and 3000 GHz / 100 micron \
where available), dust temperature and spectral emissivity index derived from modified \
blackbody fitting, H2 column density, angular size, and quality flags. The clumps span the \
full range of Galactic environments: from nearby molecular clouds (Taurus, Ophiuchus, \
Orion) at distances of 100-500 pc to distant complexes in the outer Galaxy beyond 5 kpc.

The PGCC is a cornerstone resource for star formation studies, providing targets for \
high-resolution follow-up with ALMA, NOEMA, and JCMT to characterize their internal \
structure, kinematics, and fragmentation.
"""


def main():
    print("Fetching Planck PGCC catalog from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} cold clumps")

    # Strip whitespace from column names
    df.columns = df.columns.str.strip()

    # Drop recno column (VizieR internal)
    if "recno" in df.columns:
        df = df.drop(columns=["recno"])

    df = df.rename(columns={k: v for k, v in RENAME.items() if k in df.columns})

    # Snake-case remaining columns
    already_renamed = set(RENAME.values())
    snake_map = {}
    for col in df.columns:
        if col not in already_renamed:
            snake = col.replace(" ", "_").replace("-", "_").lower()
            if snake != col:
                snake_map[col] = snake
    if snake_map:
        df = df.rename(columns=snake_map)

    # Deduplicate column names (VizieR can return duplicates after rename)
    if df.columns.duplicated().any():
        df = df.loc[:, ~df.columns.duplicated(keep="first")]

    # Convert all numeric columns
    skip_cols = {"name", "flux_type", "temperature_type", "flux_quality",
                 "temp_quality", "dist_quality"}
    for col in df.columns:
        if col not in skip_cols and df[col].dtype == object:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Clean string columns
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip().replace(
            {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
        )

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Sort by name
    if "name" in df.columns:
        df = df.sort_values("name").reset_index(drop=True)

    print(f"  {len(df):,} cold clumps, {len(df.columns)} columns")

    # ── Domain-specific stats for README ────────────────────────────
    n_total = len(df)
    n_with_temp = int(df["temperature_k"].notna().sum()) if "temperature_k" in df.columns else 0
    n_with_nh2 = int(df["column_density_cm2"].notna().sum()) if "column_density_cm2" in df.columns else 0
    n_with_dist = int(df["distance_pc"].notna().sum()) if "distance_pc" in df.columns else 0
    temp_median = df["temperature_k"].median() if "temperature_k" in df.columns and n_with_temp > 0 else 0
    temp_min = df["temperature_k"].min() if "temperature_k" in df.columns and n_with_temp > 0 else 0
    temp_max = df["temperature_k"].max() if "temperature_k" in df.columns and n_with_temp > 0 else 0

    quick_stats = f"""\
- **{n_total:,}** cold clumps across the full Galactic sky
- **{n_with_temp:,}** with measured dust temperature (median {temp_median:.1f} K, range {temp_min:.1f}--{temp_max:.1f} K)
- **{n_with_nh2:,}** with H2 column density estimates
- **{n_with_dist:,}** with distance estimates"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/planck-cold-clumps", split="train")
df = ds.to_pandas()

# Coldest clumps (potential pre-stellar cores)
coldest = df[df["temperature_k"] < 10].sort_values("temperature_k")
print(f"{len(coldest):,} clumps colder than 10 K")

# Clumps with high column density (dense cores)
if "column_density_cm2" in df.columns:
    dense = df[df["column_density_cm2"] > 1e22]
    print(f"{len(dense):,} dense clumps (N_H2 > 10^22 cm^-2)")

# Temperature distribution
import matplotlib.pyplot as plt
df["temperature_k"].dropna().hist(bins=50)
plt.xlabel("Dust Temperature (K)")
plt.ylabel("Count")
plt.title("PGCC Dust Temperature Distribution")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Planck Catalogue of Galactic Cold Clumps",
        description=DESCRIPTION,
        tags=["space", "planck", "esa", "interstellar-medium", "star-formation",
              "astronomy", "open-data", "tabular-data", "parquet"],
        source_url="https://vizier.cds.unistra.fr/viz-bin/VizieR-3?-source=J/A+A/594/A28",
        license="other",
        license_name="cc-by-nc-3.0-igo",
        license_link="https://creativecommons.org/licenses/by-nc/3.0/igo/",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e002215/GSFC_20171208_Archive_e002215~medium.jpg",
            "alt": "The gamma-ray sky as seen by NASA's Fermi telescope",
            "credit": "NASA/DOE/Fermi LAT Collaboration",
        },
        related_datasets=[
            "juliensimon/planck-sz2-clusters",
            "juliensimon/nebula-catalog",
            "juliensimon/wise-hii-regions",
            "juliensimon/gaia-dr3-young-stellar-objects",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "glon_deg", "glat_deg", "ra_deg", "dec_deg",
                "major_axis_arcmin", "minor_axis_arcmin", "position_angle_deg",
                "snr_857ghz", "snr_545ghz", "snr_353ghz",
                "flux_857ghz_mjy", "flux_545ghz_mjy", "flux_353ghz_mjy",
                "flux_857ghz_err_mjy", "flux_545ghz_err_mjy", "flux_353ghz_err_mjy",
                "flux_3000ghz_mjy", "flux_3000ghz_err_mjy",
                "flux_857ghz_bg_mjy", "flux_545ghz_bg_mjy", "flux_353ghz_bg_mjy",
                "temperature_k", "temperature_err_k",
                "temperature_bg_k", "temperature_bg_err_k",
                "spectral_index", "spectral_index_err",
                "spectral_index_bg", "spectral_index_bg_err",
                "column_density_cm2", "column_density_err_cm2",
                "column_density_bg_cm2", "column_density_bg_err_cm2",
                "distance_pc", "distance_err_pc",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="planck_pgcc.parquet",
            min_rows=10000,
            expected_columns=["name", "glon_deg", "glat_deg", "ra_deg", "dec_deg"],
            critical_columns=["name", "glon_deg", "glat_deg", "ra_deg", "dec_deg"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Planck PGCC: {n_total:,} cold clumps",
        )
    print("Done.")


if __name__ == "__main__":
    main()
