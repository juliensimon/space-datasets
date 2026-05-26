#!/usr/bin/env python3
"""Fetch Gaia DR3 QSO Candidates catalog from ESA Gaia Archive and upload to HF."""

import io
import time

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

GAIA_TAP = "https://gea.esac.esa.int/tap-server/tap/sync"
HF_REPO = "juliensimon/gaia-dr3-qso-candidates"
PAGE_SIZE = 500_000

# -- Column mapping --------------------------------------------------------
# Gaia archive returns snake_case column names for this table already
RENAME = {
    # No renames needed — columns already in snake_case
}

# -- Column descriptions for README schema table ---------------------------
COLUMN_DESCRIPTIONS = {
    "source_id": "Gaia DR3 unique source identifier; use for cross-matching with other Gaia tables",
    "astrometric_selection_flag": "Boolean: selected via astrometric criteria (proper motion and parallax consistent with zero, as expected for extragalactic sources)",
    "gaia_crf_source": "Boolean: source used to define the Gaia Celestial Reference Frame (GCRF3); these are the most astrometrically stable QSO candidates",
    "vari_best_class_name": "Best variability classification name from Gaia's variability pipeline (e.g. 'QSO', 'AGN')",
    "vari_best_class_score": "Score/probability of the best variability classification (0-1); higher values indicate more confident classification",
    "fractional_variability_g": "Fractional variability in G-band: excess variance relative to photometric noise; QSOs typically show ~0.05-0.3",
    "structure_function_index": "Power-law index of the structure function; QSOs typically have ~0.3, indicating damped random walk variability",
    "structure_function_index_scatter": "Uncertainty on the structure function power-law index",
    "qso_variability": "Variability-based QSO probability score from the variability module",
    "non_qso_variability": "Non-QSO variability score; high values suggest the source may be a star or other variable type rather than a QSO",
    "vari_agn_membership_score": "AGN membership score from the Gaia variability module; combines multiple variability criteria",
    "classprob_dsc_combmod_quasar": "DSC (Discrete Source Classifier) combined-module quasar probability (0-1); primary classifier output for QSO selection",
    "classprob_dsc_combmod_galaxy": "DSC combined-module galaxy probability (0-1); sources with high galaxy probability may be extended sources",
    "classlabel_dsc": "DSC class label assigned by the Discrete Source Classifier (quasar, galaxy, star, whitedwarf, physicalbinary)",
    "classlabel_dsc_joint": "Joint DSC class label combining spectrophotometric and spectra modules",
    "classlabel_oa": "Online Anomaly Detector class label; identifies photometrically anomalous sources",
    "redshift_qsoc": "Photometric redshift estimate from QSO spectra cross-correlation (QSOC method); valid range ~0 to 6",
    "redshift_qsoc_lower": "Lower 1-sigma uncertainty on the photometric redshift estimate",
    "redshift_qsoc_upper": "Upper 1-sigma uncertainty on the photometric redshift estimate",
    "ccfratio_qsoc": "Cross-correlation function ratio used in the QSOC redshift estimation; quality indicator for the redshift solution",
    "zscore_qsoc": "Z-score of the redshift solution; measures significance of the cross-correlation peak",
    "flags_qsoc": "Quality flags for the QSOC redshift estimate; bitmask encoding reliability of the photometric redshift",
    "n_transits": "Number of Gaia photometric transits used in the variability and morphology analysis",
    "intensity_quasar": "Fitted QSO point-source intensity (flux contribution from the AGN component) in the morphology model",
    "intensity_quasar_error": "Uncertainty on the fitted QSO point-source intensity",
    "intensity_hostgalaxy": "Fitted host galaxy intensity (extended component) in the morphology model",
    "intensity_hostgalaxy_error": "Uncertainty on the host galaxy intensity",
    "radius_hostgalaxy": "Effective radius of the fitted host galaxy Sérsic profile (arcsec)",
    "radius_hostgalaxy_error": "Uncertainty on the host galaxy effective radius (arcsec)",
    "sersic_index": "Sérsic profile index of the host galaxy (n=1: exponential/disk-like, n=4: de Vaucouleurs/elliptical)",
    "sersic_index_error": "Uncertainty on the Sérsic profile index",
    "ellipticity_hostgalaxy": "Host galaxy ellipticity (0=circular, 1=very elongated)",
    "ellipticity_hostgalaxy_error": "Uncertainty on the host galaxy ellipticity",
    "posangle_hostgalaxy": "Position angle of the host galaxy major axis (degrees, North through East)",
    "posangle_hostgalaxy_error": "Uncertainty on the host galaxy major axis position angle (degrees)",
    "host_galaxy_detected": "Boolean: host galaxy morphology was successfully fitted with a Sérsic profile",
    "l2_norm": "L2 norm of the source selection criteria vector; summary statistic of how strongly the source satisfies QSO selection criteria",
    "host_galaxy_flag": "Quality flag for the host galaxy morphology fit; encodes fit convergence and reliability",
    "source_selection_flags": "Bitmask of selection criteria met by this QSO candidate (astrometric, variability, spectral, morphology modules)",
    "high_confidence_qso": "Derived boolean: classprob_dsc_combmod_quasar > 0.5 — high-confidence quasar classification from DSC",
    "has_redshift": "Derived boolean: photometric redshift estimate is available (redshift_qsoc is not null)",
}

# -- Dataset description ----------------------------------------------------
DESCRIPTION = """\
The Gaia DR3 QSO Candidates catalog contains 6.6 million quasi-stellar object (QSO) and \
active galactic nuclei (AGN) candidates identified by the ESA Gaia mission. This is the \
largest QSO candidate catalog ever compiled, covering the full sky down to G~21 mag.

Candidates were selected using a combination of four independent methods: astrometric \
(proper motion and parallax consistent with zero, as expected for point sources at \
cosmological distances), photometric variability (structure function analysis, fractional \
variability), the Discrete Source Classifier (DSC) which assigns quasar/galaxy/star \
probabilities using spectrophotometric and low-resolution spectra data, and host galaxy \
morphology fitting. The primary selection probability is `classprob_dsc_combmod_quasar`.

For a subset of sources, photometric redshifts (up to z~6) are available via the QSOC \
(QSO Spectra Cross-Correlation) method. Host galaxy morphology parameters (Sérsic profile \
index, effective radius, ellipticity) are provided for sources where an extended component \
was detected. The most astrometrically stable QSO candidates (`gaia_crf_source=True`) \
anchor the Gaia Celestial Reference Frame (GCRF3) to the International Celestial Reference \
Frame (ICRF).

This catalog enables studies of AGN demographics across cosmic time, the large-scale \
distribution of quasars as tracers of cosmic structure, host galaxy properties of AGN at \
low and moderate redshift, and photometric redshift estimation for the high-redshift \
universe. When cross-matched with radio, X-ray, or infrared surveys, the Gaia astrometry \
provides sub-milliarcsecond positions for millions of AGN.
"""


def fetch_gaia_qso():
    """Fetch QSO candidates from Gaia archive with OFFSET pagination."""
    all_dfs = []
    offset = 0
    while True:
        query = (
            f"SELECT * FROM gaiadr3.qso_candidates "
            f"ORDER BY source_id "
            f"OFFSET {offset}"
        )
        print(f"  Fetching rows {offset:,}-{offset + PAGE_SIZE:,}...")
        resp = requests.post(GAIA_TAP, data={
            "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv",
            "QUERY": query, "MAXREC": PAGE_SIZE,
        }, timeout=600)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text))
        if len(df) == 0:
            break
        all_dfs.append(df)
        print(f"    got {len(df):,} rows")
        offset += len(df)
        if len(df) < PAGE_SIZE:
            break
        time.sleep(2)
    return pd.concat(all_dfs, ignore_index=True)


def main():
    print("Fetching Gaia DR3 QSO Candidates from ESA Gaia Archive...")
    df = fetch_gaia_qso()
    print(f"  {len(df):,} raw rows")

    # Drop internal columns
    for col in ["solution_id", "morph_params_corr_vec", "recno"]:
        if col in df.columns:
            df = df.drop(columns=[col])
            print(f"  Dropped column: {col}")

    # Rename columns if needed
    df = df.rename(columns=RENAME)

    # Boolean columns — Gaia TAP returns "T"/"F" (not "true"/"false")
    _bool_map = {"true": True, "false": False, "t": True, "f": False, "1": True, "0": False}
    for col in ["astrometric_selection_flag", "gaia_crf_source", "host_galaxy_detected"]:
        if col in df.columns:
            if df[col].dtype == object:
                df[col] = df[col].astype(str).str.strip().str.lower().map(_bool_map).astype("boolean")
            else:
                df[col] = df[col].astype("boolean")

    # Integer columns
    for col in ["flags_qsoc", "n_transits", "host_galaxy_flag", "source_selection_flags"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int32")

    # Derived columns
    if "classprob_dsc_combmod_quasar" in df.columns:
        df["high_confidence_qso"] = (df["classprob_dsc_combmod_quasar"] > 0.5).astype("boolean")

    if "redshift_qsoc" in df.columns:
        df["has_redshift"] = df["redshift_qsoc"].notna()

    # Sort by source_id
    if "source_id" in df.columns:
        df = df.sort_values("source_id").reset_index(drop=True)

    # Stats
    n_total = len(df)
    n_high_conf = int(df["high_confidence_qso"].sum()) if "high_confidence_qso" in df.columns else 0
    n_with_redshift = int(df["has_redshift"].sum()) if "has_redshift" in df.columns else 0
    median_z = df["redshift_qsoc"].dropna().median() if "redshift_qsoc" in df.columns else float("nan")
    n_crf = int(df["gaia_crf_source"].sum()) if "gaia_crf_source" in df.columns else 0

    quick_stats = f"""\
- **{n_total:,}** total QSO/AGN candidates
- **{n_high_conf:,}** high-confidence QSOs (classprob_dsc_combmod_quasar > 0.5)
- **{n_with_redshift:,}** sources with photometric redshift estimate
- Median photometric redshift (where available): {median_z:.3f}
- **{n_crf:,}** Gaia Celestial Reference Frame sources"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/gaia-dr3-qso-candidates", split="train")
df = ds.to_pandas()

# High-confidence QSO candidates
high_conf = df[df["high_confidence_qso"]]
print(f"High-confidence QSOs: {len(high_conf):,}")

# Redshift distribution for high-confidence QSOs
import matplotlib.pyplot as plt
z_df = high_conf.dropna(subset=["redshift_qsoc"])
z_df["redshift_qsoc"].hist(bins=100)
plt.xlabel("Photometric redshift")
plt.ylabel("Count")
plt.title("Gaia DR3 QSO Candidate Redshift Distribution")
plt.show()

# DSC quasar probability vs fractional variability
import matplotlib.pyplot as plt
sample = df.dropna(subset=["classprob_dsc_combmod_quasar", "fractional_variability_g"]).sample(50000)
plt.hexbin(sample["classprob_dsc_combmod_quasar"], sample["fractional_variability_g"],
           gridsize=100, mincnt=1, cmap="viridis")
plt.colorbar(label="Count")
plt.xlabel("DSC Quasar Probability")
plt.ylabel("Fractional Variability (G-band)")
plt.title("QSO Classification vs Variability")
plt.show()

# DSC class label distribution
print(df["classlabel_dsc"].value_counts())

# Gaia CRF sources (most stable astrometric reference QSOs)
crf = df[df["gaia_crf_source"] == True]
print(f"Gaia CRF anchor sources: {len(crf):,}")
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Gaia DR3 QSO Candidates",
        description=DESCRIPTION,
        tags=["space", "gaia", "quasars", "agn", "extragalactic", "redshift", "esa",
              "astronomy", "open-data", "tabular-data", "parquet"],
        source_url="https://gea.esac.esa.int/archive/",
        license="other",
        license_name="cc-by-nc-3.0-igo",
        license_link="https://creativecommons.org/licenses/by-nc/3.0/igo/",
        task_categories=["tabular-classification", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA15415/PIA15415~small.jpg",
            "alt": "Quasar and active galactic nucleus",
            "credit": "NASA/ESA/Hubble",
        },
        related_datasets=[
            "juliensimon/quasars",
            "juliensimon/milliquas",
            "juliensimon/fermi-4lac-agn-catalog",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "vari_best_class_score", "fractional_variability_g",
                "structure_function_index", "structure_function_index_scatter",
                "qso_variability", "non_qso_variability", "vari_agn_membership_score",
                "classprob_dsc_combmod_quasar", "classprob_dsc_combmod_galaxy",
                "redshift_qsoc", "redshift_qsoc_lower", "redshift_qsoc_upper",
                "ccfratio_qsoc", "zscore_qsoc",
                "intensity_quasar", "intensity_quasar_error",
                "intensity_hostgalaxy", "intensity_hostgalaxy_error",
                "radius_hostgalaxy", "radius_hostgalaxy_error",
                "sersic_index", "sersic_index_error",
                "ellipticity_hostgalaxy", "ellipticity_hostgalaxy_error",
                "posangle_hostgalaxy", "posangle_hostgalaxy_error",
                "l2_norm",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="gaia_dr3_qso_candidates.parquet",
            min_rows=6_000_000,
            expected_columns=["source_id", "classprob_dsc_combmod_quasar", "high_confidence_qso"],
            critical_columns=["source_id", "classprob_dsc_combmod_quasar"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Gaia DR3 QSO candidates: {n_total:,} sources",
        )
    print("Done.")


if __name__ == "__main__":
    main()
