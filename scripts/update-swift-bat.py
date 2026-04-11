#!/usr/bin/env python3
"""Fetch Swift-BAT 157-Month Hard X-Ray Survey from HEASARC and upload to HF."""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import heasarc_query

HF_REPO = "juliensimon/swift-bat-hard-xray-survey"

# ── Source query ─────────────────────────────────────────────────────
ADQL = "SELECT * FROM swbat157m"

# ── Column descriptions for README schema table ──────────────────────
COLUMN_DESCRIPTIONS = {
    "source_number": "Sequential source number in the BAT 157-month catalog",
    "name": "BAT source designation",
    "ra": "Right ascension in decimal degrees (J2000)",
    "dec": "Declination in decimal degrees (J2000)",
    "lii": "Galactic longitude in degrees",
    "bii": "Galactic latitude in degrees",
    "snr": "Signal-to-noise ratio of the hard X-ray detection in the 14-195 keV band",
    "ctrpart_name": "Name of the multi-wavelength counterpart identification",
    "ctrpart_ra": "Right ascension of the counterpart (J2000, degrees)",
    "ctrpart_dec": "Declination of the counterpart (J2000, degrees)",
    "flux": "Time-averaged flux in the 14-195 keV band (erg/cm²/s)",
    "flux_lower": "Lower 1-sigma uncertainty on the 14-195 keV flux (erg/cm²/s)",
    "flux_upper": "Upper 1-sigma uncertainty on the 14-195 keV flux (erg/cm²/s)",
    "spectral_index": "Photon spectral index Γ from power-law fit to the BAT spectrum",
    "spectral_index_lower": "Lower 1-sigma uncertainty on the photon spectral index",
    "spectral_index_upper": "Upper 1-sigma uncertainty on the photon spectral index",
    "chi_squared": "Reduced chi-squared of the spectral fit",
    "redshift": "Source redshift; null for Galactic sources and unidentified sources",
    "log_lx": "Log10 of the hard X-ray luminosity (erg/s); null if no redshift",
    "ctrpart_flag": "Counterpart identification flag (0=no counterpart, 1=associated)",
    "ctrpart_class": "Counterpart classification code",
    "source_type": "Source classification (e.g., AGN, Sy1, Sy2, XRB, CV, cluster)",
    "root_filename": "Root name of the BAT source file used in the analysis",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Catalog of hard X-ray sources detected in the 14–195 keV band by the
Swift Burst Alert Telescope (BAT) over 157 months of all-sky survey observations.
The survey represents over 13 years of continuous monitoring of the hard X-ray sky,
providing positions, fluxes, and spectral parameters for AGN, X-ray binaries,
galaxy clusters, and other high-energy sources sourced from NASA HEASARC.

The Swift-BAT hard X-ray survey is the most sensitive and uniform survey of the sky
in the 14–195 keV energy band. BAT is a coded-aperture instrument aboard the
Neil Gehrels Swift Observatory that continuously monitors the hard X-ray sky.
The 157-month catalog reaches a sensitivity of approximately 8×10⁻¹² erg/cm²/s
over most of the sky, probing the hard X-ray luminosity function down to
Seyfert-level AGN in the local universe.

Hard X-rays penetrate gas and dust that absorb softer X-rays, making BAT uniquely
suited for finding obscured AGN and mapping the local hard X-ray universe. The source
population is dominated by active galactic nuclei — both unobscured (Seyfert 1)
and obscured (Seyfert 2) — because the 14–195 keV band penetrates Compton-thin
absorption (column densities up to N_H ~ 10²⁴ cm⁻²). The BAT AGN sample has been
foundational for measuring the intrinsic fraction of obscured AGN as a function of
luminosity and redshift, directly constraining models of AGN unification and the
cosmic X-ray background.

The spectral parameters — photon indices and fluxes — derived from the time-averaged
BAT spectra provide a clean, absorption-independent measure of intrinsic source
luminosity. Combined with redshifts, these yield hard X-ray luminosities that anchor
the X-ray luminosity function of AGN, a fundamental input to models of supermassive
black hole growth and the synthesis of the cosmic X-ray background.
"""


def main():
    print("Fetching Swift-BAT 157-Month catalog...")
    df = heasarc_query("swbat157m", ADQL)

    # Normalize column names to snake_case
    rename_map = {}
    for col in df.columns:
        new = col.strip().lower().replace(" ", "_").replace("-", "_")
        if new != col:
            rename_map[col] = new
    if rename_map:
        df = df.rename(columns=rename_map)

    # HEASARC text format returns literal "null" strings — replace with NaN
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].replace("null", pd.NA)

    # Sort by SNR descending (brightest sources first)
    if "snr" in df.columns:
        df = df.sort_values("snr", ascending=False).reset_index(drop=True)

    n_total = len(df)
    print(f"  {n_total:,} hard X-ray sources")

    # ── Domain-specific stats for README ─────────────────────────────
    n_with_redshift = int(df["redshift"].notna().sum()) if "redshift" in df.columns else 0
    median_snr = df["snr"].median() if "snr" in df.columns else 0.0
    n_agn = int(df["source_type"].str.contains("AGN|Sy|Seyfert", case=False, na=False).sum()) \
        if "source_type" in df.columns else 0
    n_with_ctrpart = int(df["ctrpart_name"].notna().sum()) if "ctrpart_name" in df.columns else 0

    quick_stats = f"""\
- **{n_total:,}** hard X-ray sources detected in the 14–195 keV band
- **{n_with_redshift:,}** sources with measured redshifts ({n_with_redshift/n_total*100:.0f}% of total)
- **{n_agn:,}** active galactic nuclei (AGN/Seyfert sources)
- **{n_with_ctrpart:,}** sources with multi-wavelength counterpart identifications
- Median detection SNR: **{median_snr:.1f}**
- Survey coverage: 157 months (~13 years) of Swift BAT all-sky monitoring"""

    # ── Custom usage example ─────────────────────────────────────────
    usage = f"""\
```python
from datasets import load_dataset
import matplotlib.pyplot as plt
import numpy as np

ds = load_dataset("{HF_REPO}", split="train")
df = ds.to_pandas()

# All-sky Mollweide map of hard X-ray sources
fig = plt.figure(figsize=(12, 6))
ax = fig.add_subplot(111, projection="mollweide")
ra_rad = np.deg2rad(df["ra"] - 180)
dec_rad = np.deg2rad(df["dec"])
scatter = ax.scatter(ra_rad, dec_rad, c=np.log10(df["snr"].clip(lower=0.1)),
                     s=3, alpha=0.6, cmap="plasma")
plt.colorbar(scatter, ax=ax, label="log10(SNR)")
ax.set_title("Swift-BAT Hard X-Ray Sources (14-195 keV)")
ax.grid(True)
plt.tight_layout()
plt.savefig("swift_bat_skymap.png", dpi=150)
plt.show()

# Top 10 brightest sources
top10 = df.nlargest(10, "snr")[["name", "snr", "flux", "source_type", "redshift"]]
print("\\nTop 10 brightest hard X-ray sources:")
print(top10.to_string(index=False))

# Photon index distribution for AGN
agn = df[df["source_type"].str.contains("Sy|AGN", case=False, na=False)]
plt.figure(figsize=(8, 4))
agn["spectral_index"].dropna().hist(bins=40, edgecolor="k")
plt.xlabel("Photon Index Γ")
plt.ylabel("Count")
plt.title(f"Photon Index Distribution for {{len(agn):,}} BAT AGN")
plt.tight_layout()
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Swift-BAT 157-Month Hard X-Ray Survey",
        description=DESCRIPTION,
        tags=["space", "x-ray", "swift", "nasa", "hard-x-ray", "astronomy",
              "open-data", "tabular-data", "parquet"],
        source_url="https://heasarc.gsfc.nasa.gov/xamin/vo/tap/",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA03519/PIA03519~small.jpg",
            "alt": "Cassiopeia A supernova remnant in X-ray, optical, and infrared light",
            "credit": "NASA/JPL-Caltech/STScI/CXC/SAO",
        },
        related_datasets=[
            "juliensimon/gamma-ray-bursts",
            "juliensimon/pulsar-catalog",
            "juliensimon/erosita-erass1-xray",
        ],
    ) as p:
        numeric_cols = [
            "source_number",
            "ra", "dec", "lii", "bii",
            "snr", "flux", "flux_lower", "flux_upper",
            "ctrpart_ra", "ctrpart_dec",
            "spectral_index", "spectral_index_lower", "spectral_index_upper",
            "chi_squared", "redshift", "log_lx", "ctrpart_flag",
        ]
        df = p.clean(df, numeric=numeric_cols, drop_mostly_null_threshold=0.95)

        # Keep only described columns (drop undescribed HEASARC metadata columns)
        df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

        p.publish(
            df,
            filename="swift-bat.parquet",
            min_rows=1_500,
            expected_columns=["ra", "dec"],
            critical_columns=["ra", "dec"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update swift-bat: {n_total:,} sources",
        )
    print("Done.")


if __name__ == "__main__":
    main()
