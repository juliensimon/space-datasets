#!/usr/bin/env python3
"""Fetch 4XMM Serendipitous Source Catalog (unique sources) from VizieR and upload to HF.

Static dataset — no GitHub Actions workflow.
VizieR currently serves DR12s (slim); will auto-upgrade when VizieR publishes DR14.
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/4xmm-dr14-xray-sources"

# ── Source query ────────────────────────────────────────────────────
ADQL = 'SELECT * FROM "IX/68/xmm4d12s"'

# ── Column mapping ──────────────────────────────────────────────────
RENAME = {
    "4XMM": "iau_name",
    "Source": "source_id",
    "RA_ICRS": "ra_deg",
    "DE_ICRS": "dec_deg",
    "ePos": "pos_error_arcsec",
    "srcML": "src_det_ml",
    "Flux1": "flux_band1",
    "e_Flux1": "flux_band1_err",
    "Flux2": "flux_band2",
    "e_Flux2": "flux_band2_err",
    "Flux3": "flux_band3",
    "e_Flux3": "flux_band3_err",
    "Flux4": "flux_band4",
    "e_Flux4": "flux_band4_err",
    "Flux5": "flux_band5",
    "e_Flux5": "flux_band5_err",
    "Flux8": "flux_total",
    "e_Flux8": "flux_total_err",
    "Flux9": "flux_band9",
    "e_Flux9": "flux_band9_err",
    "HR1": "hardness_ratio_1",
    "e_HR1": "hardness_ratio_1_err",
    "HR2": "hardness_ratio_2",
    "e_HR2": "hardness_ratio_2_err",
    "HR3": "hardness_ratio_3",
    "e_HR3": "hardness_ratio_3_err",
    "HR4": "hardness_ratio_4",
    "e_HR4": "hardness_ratio_4_err",
    "ext": "extent_arcsec",
    "e_ext": "extent_arcsec_err",
    "extML": "extent_ml",
    "Cst": "chi2_constancy",
    "Fvar": "fractional_variability",
    "e_Fvar": "fractional_variability_err",
    "V": "variability_flag",
    "S": "summary_flag",
    "F8min": "flux_total_min",
    "e_F8min": "flux_total_min_err",
    "F8max": "flux_total_max",
    "e_F8max": "flux_total_max_err",
    "MJD0": "mjd_first",
    "MJD1": "mjd_last",
    "Nd": "n_detections",
    "c": "confusion_flag",
    "uIRAP": "irap_flag",
}

# ── Column descriptions for README schema table ────────────────────
COLUMN_DESCRIPTIONS = {
    "iau_name": "IAU source name (e.g. '4XMM J000001.2+635739'); the standard designation encoding the J2000 position; primary cross-reference identifier for X-ray source catalogs",
    "source_id": "Unique numeric source identifier within the 4XMM catalog; used internally for database queries and cross-matching between catalog releases",
    "ra_deg": "Right ascension J2000 (degrees, 0-360); weighted mean position from all detections of this source; typical positional accuracy 1-4 arcsec",
    "dec_deg": "Declination J2000 (degrees, -90 to +90); weighted mean position from all detections",
    "pos_error_arcsec": "1-sigma statistical positional uncertainty (arcsec); combined from individual detection positions; does not include systematic errors (~1 arcsec)",
    "src_det_ml": "Source detection maximum likelihood; higher values indicate more significant detections; typical threshold ML > 6 for catalog inclusion",
    "flux_band1": "Mean flux in band 1: 0.2-0.5 keV (erg/cm2/s); the softest XMM-Newton energy band, sensitive to thermal plasma emission and photoelectric absorption",
    "flux_band1_err": "1-sigma flux uncertainty in band 1 (erg/cm2/s)",
    "flux_band2": "Mean flux in band 2: 0.5-1.0 keV (erg/cm2/s); traces soft X-ray emission from stellar coronae, galaxy cluster gas, and AGN soft excess",
    "flux_band2_err": "1-sigma flux uncertainty in band 2 (erg/cm2/s)",
    "flux_band3": "Mean flux in band 3: 1.0-2.0 keV (erg/cm2/s); the intermediate band sampling the Fe-L complex region of thermal spectra",
    "flux_band3_err": "1-sigma flux uncertainty in band 3 (erg/cm2/s)",
    "flux_band4": "Mean flux in band 4: 2.0-4.5 keV (erg/cm2/s); traces harder emission less affected by absorption; dominated by AGN power-law continuum",
    "flux_band4_err": "1-sigma flux uncertainty in band 4 (erg/cm2/s)",
    "flux_band5": "Mean flux in band 5: 4.5-12.0 keV (erg/cm2/s); the hardest XMM-Newton band, sensitive to heavily absorbed AGN and non-thermal emission",
    "flux_band5_err": "1-sigma flux uncertainty in band 5 (erg/cm2/s)",
    "flux_total": "Mean total-band flux: 0.2-12.0 keV (erg/cm2/s); the primary broadband flux measurement used for luminosity estimates and source ranking",
    "flux_total_err": "1-sigma total-band flux uncertainty (erg/cm2/s)",
    "flux_band9": "Mean flux in band 9: 0.5-4.5 keV (erg/cm2/s); a combined soft+medium band useful for sources with moderate absorption",
    "flux_band9_err": "1-sigma flux uncertainty in band 9 (erg/cm2/s)",
    "hardness_ratio_1": "Hardness ratio HR1 = (B2-B1)/(B2+B1); encodes spectral shape between the two softest bands; positive values indicate harder spectra or absorption",
    "hardness_ratio_1_err": "1-sigma uncertainty on HR1",
    "hardness_ratio_2": "Hardness ratio HR2 = (B3-B2)/(B3+B2); discriminates between thermal and non-thermal spectra in the soft X-ray range",
    "hardness_ratio_2_err": "1-sigma uncertainty on HR2",
    "hardness_ratio_3": "Hardness ratio HR3 = (B4-B3)/(B4+B3); sensitive to intrinsic absorption column and photon index for power-law spectra",
    "hardness_ratio_3_err": "1-sigma uncertainty on HR3",
    "hardness_ratio_4": "Hardness ratio HR4 = (B5-B4)/(B5+B4); traces the hardest spectral shape; extreme values may indicate Compton-thick AGN or non-thermal sources",
    "hardness_ratio_4_err": "1-sigma uncertainty on HR4",
    "extent_arcsec": "Source extent (arcsec); non-zero values indicate spatially resolved emission (galaxy clusters, nearby galaxies, supernova remnants); null for point sources",
    "extent_arcsec_err": "Uncertainty on source extent (arcsec)",
    "extent_ml": "Maximum likelihood of source extent; high values confirm the source is genuinely extended rather than a blended point source",
    "chi2_constancy": "Chi-squared probability of the source being constant across all detections; low values indicate variability between observations",
    "fractional_variability": "Fractional variability amplitude Fvar; measures the intrinsic RMS variability as a fraction of the mean flux; typical AGN values 0.1-0.5",
    "fractional_variability_err": "Uncertainty on fractional variability",
    "variability_flag": "Variability flag indicating whether the source shows significant inter-observation variability; useful for identifying transients and variable AGN",
    "summary_flag": "Summary quality flag (0=good, higher values indicate increasing quality concerns); encodes detection issues, pile-up, and other artifacts",
    "flux_total_min": "Minimum total-band flux across all observations (erg/cm2/s); combined with flux_total_max reveals the dynamic range of variability",
    "flux_total_min_err": "Uncertainty on minimum total-band flux (erg/cm2/s)",
    "flux_total_max": "Maximum total-band flux across all observations (erg/cm2/s); the ratio flux_total_max/flux_total_min quantifies variability amplitude",
    "flux_total_max_err": "Uncertainty on maximum total-band flux (erg/cm2/s)",
    "mjd_first": "Modified Julian Date of the first observation detecting this source; combined with mjd_last gives the temporal baseline for variability studies",
    "mjd_last": "Modified Julian Date of the last observation detecting this source; XMM-Newton has operated since 2000, enabling baselines of up to 20+ years",
    "n_detections": "Number of individual detections of this source across all XMM-Newton observations; multiply-detected sources enable time-domain studies",
    "confusion_flag": "Confusion flag indicating potential source blending or contamination from nearby sources; important for crowded fields near the Galactic plane",
    "irap_flag": "IRAP quality flag from the XMM-Newton SSC pipeline providing additional quality assessment beyond the summary flag",
}

# ── Dataset description ─────────────────────────────────────────────
DESCRIPTION = """\
The 4XMM catalog is the largest X-ray source catalog ever produced, containing unique \
X-ray sources detected serendipitously by the European Space Agency's XMM-Newton observatory.

XMM-Newton is ESA's flagship X-ray observatory, launched in 1999 and carrying three \
co-aligned European Photon Imaging Cameras (EPIC) that simultaneously observe the same \
field. Because the EPIC field of view spans approximately 30 arcminutes, every pointed \
observation serendipitously detects dozens to hundreds of X-ray sources beyond the intended \
target. Over more than two decades of operations, this serendipitous survey has built up \
the most comprehensive census of the X-ray sky ever assembled.

This dataset provides the unique-source 'slim' version of the catalog (currently DR12s \
from VizieR), where multiple detections of the same source have been combined into a single \
entry with averaged parameters. For each source, the catalog provides positions, fluxes in \
five standard energy bands (0.2-0.5, 0.5-1.0, 1.0-2.0, 2.0-4.5, 4.5-12.0 keV), hardness \
ratios that encode spectral shape, variability indicators, extent measurements for \
non-point sources, and quality flags.

The scientific reach of 4XMM is extraordinary. X-ray emission traces the most energetic \
processes in the universe: accretion onto black holes and neutron stars, million-degree gas \
in galaxy clusters, coronal activity on stars, and shock-heated plasma in supernova \
remnants. The catalog contains everything from nearby active stars to distant quasars at \
cosmological redshifts. It is a primary resource for identifying counterparts to sources \
detected at other wavelengths, for constructing X-ray luminosity functions, and for \
discovering rare objects such as tidal disruption events, changing-look AGN, and \
ultra-luminous X-ray sources.
"""


def main():
    print("Fetching 4XMM unique sources from VizieR (DR12s slim)...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} unique X-ray sources")

    # Drop VizieR internal recno column
    if "recno" in df.columns:
        df = df.drop(columns=["recno"])

    df = df.rename(columns={k: v for k, v in RENAME.items() if k in df.columns})

    # Also snake_case any remaining columns not yet renamed
    df.columns = [c.lower().replace(" ", "_") for c in df.columns]

    # Convert numeric columns (all non-string columns)
    str_cols = {"iau_name", "variability_flag", "summary_flag",
                "confusion_flag", "irap_flag"}
    for col in df.columns:
        if col not in str_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Clean string columns: strip whitespace, empty -> NaN
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip().replace(
            {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
        )

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Sort by iau_name
    if "iau_name" in df.columns:
        df = df.sort_values("iau_name").reset_index(drop=True)

    print(f"  {len(df):,} sources, {len(df.columns)} columns after cleanup")

    # ── Domain-specific stats for README ────────────────────────────
    n_total = len(df)
    n_multi_det = int((df["n_detections"] > 1).sum()) if "n_detections" in df.columns else 0
    n_extended = int((df["extent_arcsec"] > 0).sum()) if "extent_arcsec" in df.columns else 0
    median_flux = df["flux_total"].median() if "flux_total" in df.columns else 0
    n_with_var = int(df["fractional_variability"].notna().sum()) if "fractional_variability" in df.columns else 0

    quick_stats = f"""\
- **{n_total:,}** unique X-ray sources
- **{n_multi_det:,}** sources with multiple detections
- **{n_extended:,}** spatially extended sources
- **{n_with_var:,}** with measured fractional variability
- Median total-band flux: **{median_flux:.2e}** erg/cm2/s"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/4xmm-dr14-xray-sources", split="train")
df = ds.to_pandas()

# Brightest sources by total-band flux
brightest = df.nlargest(10, "flux_total")[["iau_name", "ra_deg", "dec_deg", "flux_total"]]
print(brightest)

# Sources detected multiple times (variability studies)
multi = df[df["n_detections"] > 5]
print(f"{len(multi):,} sources with >5 detections")

# Hardness ratio diagram (X-ray color-color)
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(8, 8))
ax.scatter(df["hardness_ratio_1"], df["hardness_ratio_2"],
           s=0.5, alpha=0.1, c="navy")
ax.set_xlabel("HR1 (bands 1-2)")
ax.set_ylabel("HR2 (bands 2-3)")
ax.set_title("4XMM X-ray Color-Color Diagram")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="4XMM-DR14 Serendipitous X-ray Source Catalog",
        description=DESCRIPTION,
        tags=["space", "x-ray", "xmm-newton", "esa", "serendipitous-survey",
              "high-energy", "astronomy", "open-data", "tabular-data", "parquet"],
        source_url="https://vizier.cds.unistra.fr/viz-bin/VizieR-3?-source=IX/68",
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
            "juliensimon/chandra-x-ray-sources",
            "juliensimon/erosita-erass1-xray",
            "juliensimon/swift-bat-hard-xray-survey",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "ra_deg", "dec_deg", "pos_error_arcsec", "src_det_ml",
                "flux_band1", "flux_band1_err", "flux_band2", "flux_band2_err",
                "flux_band3", "flux_band3_err", "flux_band4", "flux_band4_err",
                "flux_band5", "flux_band5_err", "flux_total", "flux_total_err",
                "flux_band9", "flux_band9_err",
                "hardness_ratio_1", "hardness_ratio_1_err",
                "hardness_ratio_2", "hardness_ratio_2_err",
                "hardness_ratio_3", "hardness_ratio_3_err",
                "hardness_ratio_4", "hardness_ratio_4_err",
                "extent_arcsec", "extent_arcsec_err", "extent_ml",
                "chi2_constancy", "fractional_variability", "fractional_variability_err",
                "flux_total_min", "flux_total_min_err",
                "flux_total_max", "flux_total_max_err",
                "mjd_first", "mjd_last", "n_detections",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="4xmm_dr14_xray_sources.parquet",
            min_rows=500000,
            expected_columns=["iau_name", "ra_deg", "dec_deg"],
            critical_columns=["iau_name", "ra_deg", "dec_deg"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Upload 4XMM-DR14 X-ray sources: {n_total:,} unique sources",
        )
    print("Done.")


if __name__ == "__main__":
    main()
