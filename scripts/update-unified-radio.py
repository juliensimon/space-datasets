#!/usr/bin/env python3
"""Fetch SPECFIND v3 unified radio catalog from VizieR and upload to HF.

Source: Stein, Vollmer et al. (2024) — SPECFIND v3 cross-matches radio sources
across 50+ surveys including NVSS, FIRST, SUMSS, TGSS, GLEAM, and others.
Each row is a source measurement at a specific frequency with fitted spectral
parameters. VizieR catalog: VIII/104
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/unified-radio-catalog"

# ── Source query ────────────────────────────────────────────────────
ADQL = """SELECT * FROM "VIII/104/spectra" """

# ── Column mapping ──────────────────────────────────────────────────
RENAME = {
    "Seq": "source_id",
    "Name": "source_name",
    "N": "n_frequencies",
    "a": "spectral_index",
    "b": "spectral_intercept",
    "nu": "frequency_mhz",
    "S(nu)": "flux_density_mjy",
    "e_S(nu)": "flux_density_error_mjy",
    "RAJ2000": "ra_deg",
    "DEJ2000": "dec_deg",
    "dFlux": "flux_residual_pct",
    "dRA": "ra_offset_arcsec",
    "dDE": "dec_offset_arcsec",
    "beam": "beam_arcsec",
}

# ── Column descriptions for README schema table ────────────────────
COLUMN_DESCRIPTIONS = {
    "source_id": "Unique integer identifier grouping cross-matched detections of the same physical radio source across multiple surveys; all rows sharing a source_id are positionally associated",
    "source_name": "Survey-specific source designation (e.g. 'NVSS J123456+654321'); the prefix encodes which survey contributed this particular measurement",
    "n_frequencies": "Number of distinct frequency measurements available for this source; higher counts yield more reliable spectral fits; sources with n >= 3 have well-constrained power-law spectra",
    "spectral_index": "Fitted power-law spectral index (a) where S(nu) ~ nu^a; typical synchrotron sources have a ~ -0.7; flat-spectrum AGN cores have a ~ 0; same value for all rows of a given source_id",
    "spectral_intercept": "Fitted spectral intercept (b) in log S = a*log(nu) + b; encodes the overall flux normalization of the power-law fit; same value for all rows of a given source_id",
    "frequency_mhz": "Observation frequency of this particular measurement in MHz; ranges from ~10 MHz to ~31 GHz across all contributing surveys",
    "flux_density_mjy": "Flux density at this frequency in mJy; the measured brightness of the source in the contributing survey",
    "flux_density_error_mjy": "1-sigma uncertainty on flux density in mJy; propagated from the original survey catalog",
    "ra_deg": "Right ascension J2000 in degrees (0-360) from the contributing survey; may differ slightly between surveys due to resolution and astrometric calibration differences",
    "dec_deg": "Declination J2000 in degrees (-90 to +90) from the contributing survey",
    "flux_residual_pct": "Residual of this measurement from the fitted power-law spectrum as a percentage; large residuals indicate spectral curvature or variability not captured by a simple power law",
    "ra_offset_arcsec": "Offset in right ascension from the mean source position in arcseconds; reflects positional scatter across surveys with different angular resolutions",
    "dec_offset_arcsec": "Offset in declination from the mean source position in arcseconds",
    "beam_arcsec": "Angular resolution (beam FWHM) of the contributing survey in arcseconds; ranges from ~5 arcsec (FIRST) to ~300 arcsec (low-frequency surveys)",
    "survey": "Survey name extracted from the source designation prefix; identifies which radio survey contributed this measurement (e.g. NVSS, FIRST, SUMSS, TGSS, GLEAM)",
    "frequency_band": "Frequency band classification: VLF (<100 MHz), low (100-500 MHz), mid (500-2000 MHz), high (2-8 GHz), SHF (>8 GHz); derived from frequency_mhz",
}

# ── Dataset description ─────────────────────────────────────────────
DESCRIPTION = """\
The SPECFIND v3 unified radio source catalog, cross-matching radio source \
measurements from 50+ surveys spanning ~10 MHz to ~31 GHz. SPECFIND positionally \
cross-identifies radio sources across major surveys including NVSS, FIRST, SUMSS, \
TGSS, GLEAM, and dozens of others, then fits power-law radio spectra.

SPECFIND (Vollmer et al. 2005, updated Stein et al. 2024) is the largest positional \
cross-identification of radio continuum catalogs. Each row represents a source \
detection at a specific frequency, grouped by a unique source identifier. For sources \
detected in multiple surveys, SPECFIND fits a power-law spectrum S(nu) = 10^b * nu^a, \
where a is the spectral index and b is the intercept.

The radio spectrum of a source encodes fundamental information about its emission \
mechanism. Synchrotron radiation from relativistic electrons in magnetic fields \
produces a power-law spectrum S(nu) proportional to nu^alpha, where alpha is the \
spectral index. Typical values range from alpha ~ -0.7 for optically thin synchrotron \
(radio lobes, supernova remnants) to alpha ~ 0 or positive for self-absorbed compact \
sources (AGN cores, young radio sources). By fitting spectra across multiple \
frequencies, SPECFIND enables systematic classification of radio source populations \
and identification of unusual spectral shapes.

This unified catalog is a natural starting point for multi-frequency radio population \
studies, spectral index mapping of extended sources, and identification of sources \
with anomalous radio spectra.
"""


def main():
    print("Fetching SPECFIND v3 unified radio catalog from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} raw rows")

    # Rename columns
    df = df.rename(columns={k: v for k, v in RENAME.items() if k in df.columns})

    # Integer columns
    for col in ["source_id", "n_frequencies"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int32")

    # Derive survey name from source_name prefix
    if "source_name" in df.columns:
        df["survey"] = df["source_name"].str.extract(r"^([A-Za-z0-9\[\]]+)", expand=False)

    # Derive frequency band label
    if "frequency_mhz" in df.columns:
        df["frequency_band"] = pd.cut(
            pd.to_numeric(df["frequency_mhz"], errors="coerce"),
            bins=[0, 100, 500, 2000, 8000, 1e9],
            labels=["VLF", "low", "mid", "high", "SHF"],
            right=False,
        )

    # Sort by source_id, then frequency
    sort_cols = []
    if "source_id" in df.columns:
        sort_cols.append("source_id")
    if "frequency_mhz" in df.columns:
        sort_cols.append("frequency_mhz")
    if sort_cols:
        df = df.sort_values(sort_cols).reset_index(drop=True)

    # Drop VizieR internal columns
    for col in ["recno"]:
        if col in df.columns:
            df = df.drop(columns=[col])

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_sources = df["source_id"].nunique() if "source_id" in df.columns else 0
    n_surveys = df["survey"].nunique() if "survey" in df.columns else 0
    freq_min = df["frequency_mhz"].min() if "frequency_mhz" in df.columns else 0
    freq_max = df["frequency_mhz"].max() if "frequency_mhz" in df.columns else 0
    median_flux = df["flux_density_mjy"].median() if "flux_density_mjy" in df.columns else 0
    median_si = df["spectral_index"].median() if "spectral_index" in df.columns else 0

    quick_stats = f"""\
- **{n_total:,}** total source measurements
- **{n_sources:,}** unique radio sources
- **{n_surveys}** contributing surveys
- Frequency range: {freq_min:.0f} to {freq_max:.0f} MHz
- Median flux density: {median_flux:.1f} mJy
- Median spectral index: {median_si:.2f}"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/unified-radio-catalog", split="train")
df = ds.to_pandas()

# Group by source to see multi-frequency data
source = df[df["source_id"] == df["source_id"].iloc[0]]
print(f"Source {source['source_name'].iloc[0]}: {len(source)} frequencies")

# Spectral index distribution
import matplotlib.pyplot as plt
si = df.drop_duplicates("source_id")["spectral_index"].dropna()
si.clip(-3, 3).hist(bins=200)
plt.xlabel("Spectral index")
plt.ylabel("Count")
plt.title("Radio Source Spectral Index Distribution")
plt.axvline(-0.7, color="red", linestyle="--", label="Typical synchrotron")
plt.legend()
plt.show()

# Survey contribution
print(df["survey"].value_counts().head(10))
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Unified Radio Catalog (SPECFIND v3)",
        description=DESCRIPTION,
        tags=["space", "radio", "nvss", "first", "sumss", "astronomy",
              "open-data", "tabular-data", "parquet"],
        source_url="https://vizier.cds.unistra.fr/viz-bin/VizieR-3?-source=VIII/104",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA13277/PIA13277~small.jpg",
            "alt": "Deep Space Network antenna at Goldstone",
            "credit": "NASA/JPL-Caltech",
        },
        related_datasets=[
            "juliensimon/nvss-radio-catalog",
            "juliensimon/first-radio-catalog",
            "juliensimon/vlass-radio-sources",
            "juliensimon/sumss-radio-catalog",
            "juliensimon/tgss-radio-catalog",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "spectral_index", "spectral_intercept",
                "frequency_mhz", "flux_density_mjy", "flux_density_error_mjy",
                "ra_deg", "dec_deg",
                "flux_residual_pct", "ra_offset_arcsec", "dec_offset_arcsec",
                "beam_arcsec",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="unified_radio_catalog.parquet",
            min_rows=1_500_000,
            expected_columns=["source_name", "ra_deg", "dec_deg", "frequency_mhz", "flux_density_mjy"],
            critical_columns=["source_name", "ra_deg", "dec_deg", "flux_density_mjy"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update unified radio catalog: {n_total:,} measurements, {n_sources:,} sources",
        )
    print("Done.")


if __name__ == "__main__":
    main()
