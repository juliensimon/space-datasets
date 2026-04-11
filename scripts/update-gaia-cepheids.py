#!/usr/bin/env python3
"""Fetch Gaia DR3 Cepheid variable star catalog from VizieR and upload to HF."""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/gaia-dr3-cepheids"

ADQL = 'SELECT * FROM "I/358/vcep"'

# ── Column mapping ───────────────────────────────────────────────────
RENAME = {
    "Source": "source_id",
    "RA_ICRS": "ra_deg",
    "DE_ICRS": "dec_deg",
    "PF": "period_fundamental_days",
    "e_PF": "period_fundamental_error",
    "P1O": "period_1st_overtone_days",
    "e_P1O": "period_1st_overtone_error",
    "P2O": "period_2nd_overtone_days",
    "e_P2O": "period_2nd_overtone_error",
    "EpochG": "epoch_g",
    "e_EpochG": "epoch_g_error",
    "EpochBP": "epoch_bp",
    "EpochRP": "epoch_rp",
    "EpochRV": "epoch_rv",
    "Gmagavg": "gaia_g_mag",
    "e_Gmagavg": "gaia_g_mag_error",
    "BPmagavg": "gaia_bp_mag",
    "e_BPmagavg": "gaia_bp_mag_error",
    "RPmagavg": "gaia_rp_mag",
    "e_RPmagavg": "gaia_rp_mag_error",
    "RVavg": "radial_velocity_kms",
    "e_RVavg": "radial_velocity_error_kms",
    "ptpG": "amplitude_g",
    "e_ptpG": "amplitude_g_error",
    "ptpBP": "amplitude_bp",
    "ptpRP": "amplitude_rp",
    "ptpRV": "amplitude_rv",
    "[M/H]": "metallicity",
    "e_[M/H]": "metallicity_error",
    "R21G": "fourier_r21_g",
    "R31G": "fourier_r31_g",
    "phi21G": "fourier_phi21_g",
    "phi31G": "fourier_phi31_g",
    "NclEpG": "n_epochs_g",
    "NclEpBP": "n_epochs_bp",
    "NclEpRP": "n_epochs_rp",
    "NclEpRV": "n_epochs_rv",
    "Class": "cepheid_type",
    "SubClass": "cepheid_subclass",
    "ModeClass": "mode_class",
    "MulModeClass": "multi_mode_class",
    "FundFreq1": "fundamental_freq_1",
    "FundFreq2": "fundamental_freq_2",
    "SolID": "solution_id",
}

DROP_COLS = ["recno", "SimbadName", "More", "_RA_icrs", "_DE_icrs"]

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "source_id": "Gaia DR3 unique source identifier (64-bit integer as string); stable within the Gaia DR3 data release",
    "ra_deg": "Right ascension, ICRS at Gaia reference epoch, in decimal degrees (0-360)",
    "dec_deg": "Declination, ICRS at Gaia reference epoch, in decimal degrees (-90 to +90)",
    "period_fundamental_days": "Fundamental-mode pulsation period in days; classical Cepheids typically 1-100 days; null if no fundamental mode detected",
    "period_fundamental_error": "Uncertainty on the fundamental-mode period (days)",
    "period_1st_overtone_days": "First-overtone pulsation period in days; typically shorter than the fundamental period by a factor ~0.71",
    "period_1st_overtone_error": "Uncertainty on the first-overtone period (days)",
    "period_2nd_overtone_days": "Second-overtone pulsation period in days; rare, found in multi-mode pulsators",
    "period_2nd_overtone_error": "Uncertainty on the second-overtone period (days)",
    "epoch_g": "Reference epoch of maximum light in G band (Barycentric Julian Date)",
    "epoch_g_error": "Uncertainty on the G-band reference epoch",
    "epoch_bp": "Reference epoch of maximum light in BP band (BJD)",
    "epoch_rp": "Reference epoch of maximum light in RP band (BJD)",
    "epoch_rv": "Reference epoch for radial velocity maximum (BJD); null if no RV data",
    "gaia_g_mag": "Intensity-averaged mean Gaia G-band magnitude; Cepheids typically 4-18 mag depending on distance",
    "gaia_g_mag_error": "Uncertainty on mean G-band magnitude",
    "gaia_bp_mag": "Intensity-averaged mean Gaia BP-band (330-680 nm) magnitude",
    "gaia_bp_mag_error": "Uncertainty on mean BP-band magnitude",
    "gaia_rp_mag": "Intensity-averaged mean Gaia RP-band (640-1050 nm) magnitude",
    "gaia_rp_mag_error": "Uncertainty on mean RP-band magnitude",
    "radial_velocity_kms": "Mean radial velocity in km/s from Gaia RVS; null for faint stars below the RVS limit (~G_RVS < 12)",
    "radial_velocity_error_kms": "Uncertainty on mean radial velocity (km/s)",
    "amplitude_g": "Peak-to-peak light curve amplitude in G band (mag); classical Cepheids typically 0.2-1.5 mag",
    "amplitude_g_error": "Uncertainty on G-band amplitude",
    "amplitude_bp": "Peak-to-peak light curve amplitude in BP band (mag)",
    "amplitude_rp": "Peak-to-peak light curve amplitude in RP band (mag)",
    "amplitude_rv": "Peak-to-peak radial velocity amplitude (km/s); null if no RV data",
    "metallicity": "Photometric metallicity [M/H] in dex, derived from light curve Fourier parameters; null where light curve quality is insufficient",
    "metallicity_error": "Uncertainty on photometric metallicity (dex)",
    "fourier_r21_g": "Fourier amplitude ratio R21 = A2/A1 in G band; diagnostic for pulsation mode and Cepheid subtype",
    "fourier_r31_g": "Fourier amplitude ratio R31 = A3/A1 in G band",
    "fourier_phi21_g": "Fourier phase difference phi21 in G band (radians); used for metallicity estimation",
    "fourier_phi31_g": "Fourier phase difference phi31 in G band (radians); encodes light curve shape",
    "n_epochs_g": "Number of G-band observations used in the light curve fit",
    "n_epochs_bp": "Number of BP-band observations used",
    "n_epochs_rp": "Number of RP-band observations used",
    "n_epochs_rv": "Number of radial velocity observations used; null if no RV data",
    "cepheid_type": "Cepheid class: DCEP (classical/delta Cepheid), T2CEP (Type II), ACEP (anomalous); primary classification",
    "cepheid_subclass": "Detailed subclass within the main type (e.g. BL_Her, W_Vir, RV_Tau for Type II Cepheids)",
    "mode_class": "Pulsation mode classification: FUNDAMENTAL, FIRST_OVERTONE, or MULTI",
    "multi_mode_class": "Multi-mode classification for double- or triple-mode pulsators; null for single-mode stars",
    "fundamental_freq_1": "First fundamentalized frequency (1/days); used for period-luminosity relation calibration",
    "fundamental_freq_2": "Second fundamentalized frequency (1/days); null for single-mode pulsators",
    "solution_id": "Gaia variability pipeline solution identifier",
    "is_classical": "True if the Cepheid type contains 'DCEP', indicating a classical/fundamental-mode Cepheid; classical Cepheids are key distance indicators",
    "period_best_days": "Best available period: fundamental-mode period if available, otherwise first-overtone period; convenience column for period-luminosity analysis",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
The Gaia Data Release 3 catalog of Cepheid variable stars of all types -- classical \
(fundamental mode), Type II, and anomalous Cepheids. Cepheids are among the most \
important standard candles for calibrating the cosmic distance ladder, with their \
well-known period-luminosity relation enabling precise distance measurements across \
the Local Group and beyond.

This dataset contains Cepheids identified and characterized by the Gaia DR3 variability \
processing pipeline. Each object includes pulsation periods, multi-band photometric \
parameters (G, BP, RP), light curve amplitudes, classifications, and Fourier decomposition \
parameters.

The three major Cepheid families occupy distinct regions of the instability strip. Classical \
Cepheids (DCEP) are young, massive (3-12 solar masses) supergiants with periods from about 1 \
to over 100 days, concentrated in the thin disk and spiral arms. Type II Cepheids (T2CEP) \
are old, low-mass stars in the bulge, thick disk, and halo. Anomalous Cepheids (ACEP) are \
intermediate in luminosity and are thought to arise from mass transfer in binary systems.

Gaia's contribution to Cepheid science is transformative. Gaia DR3 provides trigonometric \
parallaxes for thousands of Cepheids, enabling a purely geometric calibration of the \
period-luminosity relation and tightening the first rung of the cosmic distance ladder. The \
Fourier decomposition parameters (R21, R31, phi21, phi31) encode the detailed shape of each \
star's light curve and serve as diagnostics for pulsation modes and Cepheid subtypes.
"""


def main():
    print("Fetching Gaia DR3 Cepheid catalog from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} Cepheids fetched")

    # Drop unwanted columns
    for col in DROP_COLS:
        if col in df.columns:
            df = df.drop(columns=[col])

    # Rename columns
    df = df.rename(columns=RENAME)

    # Clean string columns
    for col in ["source_id", "cepheid_type", "cepheid_subclass", "mode_class",
                "multi_mode_class", "solution_id"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
            )

    # Derived column: is_classical (DCEP = classical/fundamental mode Cepheids)
    if "cepheid_type" in df.columns:
        df["is_classical"] = df["cepheid_type"].str.upper().str.contains(
            r"DCEP", na=False
        )

    # Compute best period (fundamental if available, else 1st overtone)
    if "period_fundamental_days" in df.columns:
        df["period_best_days"] = df["period_fundamental_days"].fillna(
            df.get("period_1st_overtone_days", pd.Series(dtype="float64"))
        )
    elif "period_1st_overtone_days" in df.columns:
        df["period_best_days"] = df["period_1st_overtone_days"]

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Sort by source_id
    sort_col = "source_id" if "source_id" in df.columns else "ra_deg"
    df = df.sort_values(sort_col).reset_index(drop=True)

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_classical = int(df["is_classical"].sum()) if "is_classical" in df.columns else 0

    period_col = "period_best_days" if "period_best_days" in df.columns else "period_fundamental_days"
    period_min = df[period_col].min() if period_col in df.columns else 0
    period_max = df[period_col].max() if period_col in df.columns else 0
    period_median = df[period_col].median() if period_col in df.columns else 0

    n_with_rv = int(df["radial_velocity_kms"].notna().sum()) if "radial_velocity_kms" in df.columns else 0
    n_with_metallicity = int(df["metallicity"].notna().sum()) if "metallicity" in df.columns else 0

    quick_stats = f"""\
- **{n_total:,}** Cepheid variables
- **{n_classical:,}** classical Cepheids (DCEP types)
- Period range: **{period_min:.4f}** to **{period_max:.2f}** days (median {period_median:.4f})
- **{n_with_rv:,}** with radial velocity measurements
- **{n_with_metallicity:,}** with metallicity estimates"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/gaia-dr3-cepheids", split="train")
df = ds.to_pandas()

# Period-luminosity (Leavitt) relation
import matplotlib.pyplot as plt
valid = df.dropna(subset=["period_best_days", "gaia_g_mag"])
plt.scatter(valid["period_best_days"], valid["gaia_g_mag"], s=0.5, alpha=0.3)
plt.xscale("log")
plt.gca().invert_yaxis()
plt.xlabel("Period (days)")
plt.ylabel("G magnitude")
plt.title("Gaia DR3 Cepheid Period-Luminosity Relation")
plt.show()

# Classical vs Type II Cepheids
classical = df[df["is_classical"] == True]
other = df[df["is_classical"] == False]
print(f"{len(classical):,} classical, {len(other):,} other types")
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Gaia DR3 Cepheid Variables",
        description=DESCRIPTION,
        tags=["space", "stars", "cepheids", "variable-stars", "distance-ladder",
              "gaia", "esa", "astronomy", "open-data", "tabular-data", "parquet"],
        source_url="https://vizier.cds.unistra.fr/viz-bin/VizieR-3?-source=I/358/vcep",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA03606/PIA03606~small.jpg",
            "alt": "The Crab Nebula, a supernova remnant",
            "credit": "NASA/ESA/Hubble",
        },
        related_datasets=[
            "juliensimon/gaia-dr3-rrlyrae",
            "juliensimon/gcvs-variable-stars",
            "juliensimon/gaia-dr3-eclipsing-binaries",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "ra_deg", "dec_deg", "period_fundamental_days", "period_fundamental_error",
                "period_1st_overtone_days", "period_1st_overtone_error",
                "period_2nd_overtone_days", "period_2nd_overtone_error",
                "gaia_g_mag", "gaia_g_mag_error", "gaia_bp_mag", "gaia_bp_mag_error",
                "gaia_rp_mag", "gaia_rp_mag_error", "radial_velocity_kms",
                "radial_velocity_error_kms", "amplitude_g", "amplitude_g_error",
                "amplitude_bp", "amplitude_rp", "amplitude_rv",
                "metallicity", "metallicity_error",
                "fourier_r21_g", "fourier_r31_g", "fourier_phi21_g", "fourier_phi31_g",
                "fundamental_freq_1", "fundamental_freq_2",
                "epoch_g", "epoch_g_error", "epoch_bp", "epoch_rp", "epoch_rv",
                "n_epochs_g", "n_epochs_bp", "n_epochs_rp", "n_epochs_rv",
                "period_best_days",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="gaia_cepheids.parquet",
            min_rows=10_000,
            expected_columns=["source_id", "ra_deg", "dec_deg", "cepheid_type"],
            critical_columns=["source_id", "ra_deg", "dec_deg"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Gaia DR3 Cepheids: {n_total:,} variables",
        )
    print("Done.")


if __name__ == "__main__":
    main()
