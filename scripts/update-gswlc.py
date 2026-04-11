#!/usr/bin/env python3
"""Fetch GSWLC-X2 galaxy catalog and upload to HF.

GSWLC-2 (GALEX-SDSS-WISE Legacy Catalog) contains ~659K galaxies with
stellar masses, star formation rates, and dust attenuation from
UV+optical+IR SED fitting (Salim et al. 2016, 2018).
"""

import io

import numpy as np
import pandas as pd
import requests

from hf_dataset_utils import Pipeline

SOURCE_URL = "https://salims.pages.iu.edu/gswlc/GSWLC-X2.dat.gz"
HF_REPO = "juliensimon/gswlc-galaxy-properties"

# Column names from Table 2 of the GSWLC-2 documentation
COLUMNS = [
    "objid",           # 1  SDSS photometric object ID
    "glxid",           # 2  GALEX photometric ID
    "plate",           # 3  SDSS spectroscopic plate number
    "mjd",             # 4  SDSS spectroscopic plate date
    "fiber_id",        # 5  SDSS spectroscopic fiber ID
    "ra",              # 6  Right Ascension (deg)
    "dec",             # 7  Declination (deg)
    "redshift",        # 8  Redshift from SDSS
    "chi2_r",          # 9  Reduced chi-squared for SED fit
    "log_mstar",       # 10 log stellar mass (Msun)
    "log_mstar_err",   # 11 Error on log stellar mass
    "log_sfr_sed",     # 12 log SFR from UV/optical SED (Msun/yr)
    "log_sfr_sed_err", # 13 Error on log SFR
    "a_fuv",           # 14 Dust attenuation in rest-frame FUV (mag)
    "a_fuv_err",       # 15 Error on A_FUV
    "a_b",             # 16 Dust attenuation in rest-frame B (mag)
    "a_b_err",         # 17 Error on A_B
    "a_v",             # 18 Dust attenuation in rest-frame V (mag)
    "a_v_err",         # 19 Error on A_V
    "flag_sed",        # 20 SED fitting flag
    "uv_survey",       # 21 UV survey (1=A, 2=M, 3=D)
    "flag_uv",         # 22 UV detection flag
    "flag_midir",      # 23 Mid-IR flag
    "flag_mgs",        # 24 SDSS Main Galaxy Sample flag
]

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "objid": "SDSS photometric object ID (18-digit integer from the SDSS imaging pipeline); primary cross-match key",
    "glxid": "GALEX photometric object ID for UV cross-match; null (originally -99) if no GALEX source within matching radius",
    "plate": "SDSS spectroscopic plate number; combined with mjd and fiber_id uniquely identifies the spectrum",
    "mjd": "Modified Julian Date of the SDSS spectroscopic observation; integer days since 1858-11-17",
    "fiber_id": "SDSS spectroscopic fiber number on the plate (1-1000); combined with plate+mjd locates the spectrum",
    "ra": "ICRS J2000.0 right ascension in degrees (0-360)",
    "dec": "ICRS J2000.0 declination in degrees (-90 to +90)",
    "redshift": "Spectroscopic redshift from SDSS; catalog range 0.01 < z < 0.30",
    "chi2_r": "Reduced chi-squared of the best-fit SED model; values > 5 indicate a poor fit; null for failed fits",
    "log_mstar": "Log10 stellar mass in solar masses from SED fitting; range ~8 to ~12 (i.e., 10^8-10^12 M_sun); null if SED fit failed",
    "log_mstar_err": "1-sigma uncertainty on log_mstar in dex; typically 0.05-0.15 dex; null if log_mstar is null",
    "log_sfr_sed": "Log10 star formation rate from UV+optical SED fit in M_sun/yr; quiescent: < -1, main sequence: 0-3; null if SED fit failed",
    "log_sfr_sed_err": "1-sigma uncertainty on log_sfr_sed in dex; typically 0.1-0.3 dex; null if log_sfr_sed is null",
    "a_fuv": "Dust attenuation in the rest-frame far-UV (FUV ~1528 A) in magnitudes; 0 = transparent, ~5 for heavily obscured starbursts; null if SED fit failed",
    "a_fuv_err": "1-sigma uncertainty on a_fuv in magnitudes; null if a_fuv is null",
    "a_b": "Dust attenuation in the rest-frame B band (~4400 A) in magnitudes; typically 0-2 mag; null if SED fit failed",
    "a_b_err": "1-sigma uncertainty on a_b in magnitudes; null if a_b is null",
    "a_v": "Dust attenuation in the rest-frame V band (~5500 A) in magnitudes; 0 = transparent, 2+ = heavily obscured; null if SED fit failed",
    "a_v_err": "1-sigma uncertainty on a_v in magnitudes; null if a_v is null",
    "flag_sed": "SED fitting quality flag: 0 = good fit; 1 = broad-line AGN (UV contaminated); 2 = poor fit (chi2_r > 30); 5 = missing photometry",
    "uv_survey": "GALEX UV survey depth used: 1 = shallow (AIS, ~100 s), 2 = medium (MIS, ~1500 s), 3 = deep (DIS, ~30000 s)",
    "flag_uv": "UV detection status: 0 = no UV detection, 1 = FUV only detected, 2 = NUV only detected, 3 = both FUV and NUV detected",
    "flag_midir": "WISE mid-IR photometry flag: 0 = no WISE detection, 1 = W3 (12 um) only, 2 = W4 (22 um) only, 5 = AGN contribution corrected",
    "flag_mgs": "SDSS Main Galaxy Sample membership: 1 = in the MGS (r < 17.77, complete flux-limited sample), 0 = outside MGS selection",
    "log_ssfr": "Derived: log10 specific star formation rate = log_sfr_sed - log_mstar in yr^-1; quiescent galaxies: < -11, main-sequence: -9.5 to -10.5; null if either parent column is null",
    "is_star_forming": "Derived: True if log_ssfr > -11 (above the quenching threshold); False for quiescent/passive galaxies",
    "uv_survey_name": "Derived: human-readable UV survey label ('GSWLC-A', 'GSWLC-M', or 'GSWLC-D') mapped from uv_survey",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Physical properties for ~659,000 galaxies derived from UV-to-infrared spectral energy \
distribution (SED) fitting. GSWLC-2 (GALEX-SDSS-WISE Legacy Catalog 2) combines ultraviolet \
photometry from GALEX, optical photometry from SDSS, and mid-infrared photometry from WISE to \
estimate stellar masses, star formation rates, and dust attenuation for galaxies at redshifts \
0.01 < z < 0.30.

The GSWLC is the definitive catalog for physical properties of low-redshift galaxies, covering \
~90% of the SDSS spectroscopic footprint. Version 2 (Salim et al. 2018) incorporates WISE \
mid-IR photometry to better constrain dust-obscured star formation. Physical properties are \
derived using the CIGALE SED fitting code with Bayesian estimation.

Understanding how galaxies form stars and build up their stellar mass is one of the central \
questions in extragalactic astronomy. The star formation rate and stellar mass are linked \
through the star formation main sequence. GSWLC provides the definitive measurement of these \
quantities for the low-redshift galaxy population, with the critical advantage that mid-infrared \
photometry from WISE captures dust-reprocessed emission missed by UV and optical observations.

This catalog is the standard reference for calibrating star formation rate indicators, studying \
the quenching of star formation in massive galaxies, and constructing volume-limited galaxy \
samples. The specific star formation rate (sSFR) cleanly separates the star-forming blue cloud \
from the quiescent red sequence, making GSWLC a natural training set for galaxy classification.
"""


def main():
    print("Fetching GSWLC-X2 catalog...")
    resp = requests.get(SOURCE_URL, timeout=300)
    resp.raise_for_status()

    # The server may auto-decompress gzip; detect which case we're in
    raw = resp.content
    compression = "gzip" if raw[:2] == b"\x1f\x8b" else None

    df = pd.read_csv(
        io.BytesIO(raw),
        compression=compression,
        sep=r"\s+",
        header=None,
        names=COLUMNS,
        dtype=str,  # read all as string first, coerce below
    )
    print(f"  {len(df):,} galaxies, {len(df.columns)} columns")

    # ── Type coercion ─────────────────────────────────────────────────
    # IDs
    for col in ["objid", "glxid", "plate", "mjd", "fiber_id"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    # Coordinates and redshift
    for col in ["ra", "dec", "redshift"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # SED fitting results (continuous)
    float_cols = [
        "chi2_r",
        "log_mstar", "log_mstar_err",
        "log_sfr_sed", "log_sfr_sed_err",
        "a_fuv", "a_fuv_err",
        "a_b", "a_b_err",
        "a_v", "a_v_err",
    ]
    for col in float_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Flags (integer)
    for col in ["flag_sed", "uv_survey", "flag_uv", "flag_midir", "flag_mgs"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    # ── Handle missing values (-99 -> NaN) ────────────────────────────
    sentinel_cols = [
        "log_mstar", "log_mstar_err",
        "log_sfr_sed", "log_sfr_sed_err",
        "a_fuv", "a_fuv_err",
        "a_b", "a_b_err",
        "a_v", "a_v_err",
        "chi2_r",
    ]
    for col in sentinel_cols:
        df.loc[df[col] == -99, col] = np.nan

    # GLXID -99 means no GALEX match
    df.loc[df["glxid"] == -99, "glxid"] = pd.NA

    # ── Derived columns ───────────────────────────────────────────────
    # Specific SFR (sSFR = SFR / M*) in log space
    mask = df["log_sfr_sed"].notna() & df["log_mstar"].notna()
    df["log_ssfr"] = np.nan
    df.loc[mask, "log_ssfr"] = df.loc[mask, "log_sfr_sed"] - df.loc[mask, "log_mstar"]

    # Star-forming vs quiescent classification (log sSFR > -11 is star-forming)
    df["is_star_forming"] = df["log_ssfr"] > -11.0

    # UV survey label
    uv_survey_map = {1: "GSWLC-A", 2: "GSWLC-M", 3: "GSWLC-D"}
    df["uv_survey_name"] = df["uv_survey"].map(uv_survey_map)

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # ── Domain-specific stats for README ──────────────────────────────
    valid_mass = df["log_mstar"].notna()
    valid_sfr = df["log_sfr_sed"].notna()
    n_star_forming = int(df["is_star_forming"].sum())
    n_quiescent = int((~df["is_star_forming"] & valid_mass).sum())
    median_mass = df.loc[valid_mass, "log_mstar"].median()
    median_z = df["redshift"].median()

    quick_stats = f"""\
- **{len(df):,}** galaxies in the catalog
- **{valid_mass.sum():,}** with valid stellar mass estimates
- **{valid_sfr.sum():,}** with valid SFR estimates
- **{n_star_forming:,}** classified as star-forming (log sSFR > -11)
- **{n_quiescent:,}** classified as quiescent
- Median stellar mass: **10^{median_mass:.2f}** solar masses
- Median redshift: **{median_z:.4f}**"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/gswlc-galaxy-properties", split="train")
df = ds.to_pandas()

# Star-forming galaxies
sf = df[df["is_star_forming"]]

# Massive quiescent galaxies
massive_quiescent = df[(df["log_mstar"] > 11) & (~df["is_star_forming"])]

# Star formation main sequence
import matplotlib.pyplot as plt
valid = df[df["log_sfr_sed"].notna() & df["log_mstar"].notna()]
plt.hexbin(valid["log_mstar"], valid["log_sfr_sed"], gridsize=100, mincnt=1)
plt.xlabel("log M* (Msun)")
plt.ylabel("log SFR (Msun/yr)")
plt.title("Star Formation Main Sequence")
plt.colorbar(label="Count")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="GSWLC-2 Galaxy Properties",
        description=DESCRIPTION,
        tags=["space", "galaxies", "stellar-mass", "star-formation",
              "sdss", "galex", "wise", "astronomy",
              "open-data", "tabular-data", "parquet"],
        source_url="https://salims.pages.iu.edu/gswlc/",
        task_categories=["tabular-classification", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA12110/PIA12110~small.jpg",
            "alt": "Hubble Deep Field revealing myriad galaxies across cosmic time",
            "credit": "NASA/ESA/STScI",
        },
        related_datasets=[
            "juliensimon/galaxy-zoo-2-morphology",
            "juliensimon/ngc-ic-catalog",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=["ra", "dec", "redshift", "chi2_r",
                      "log_mstar", "log_mstar_err",
                      "log_sfr_sed", "log_sfr_sed_err",
                      "a_fuv", "a_fuv_err", "a_b", "a_b_err",
                      "a_v", "a_v_err", "log_ssfr"],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="gswlc_galaxy_properties.parquet",
            min_rows=500_000,
            expected_columns=[
                "objid", "ra", "dec", "redshift",
                "log_mstar", "log_sfr_sed", "log_ssfr",
                "a_fuv", "a_v", "flag_sed", "uv_survey",
                "flag_uv", "is_star_forming",
            ],
            critical_columns=["ra", "dec", "redshift", "objid"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Upload GSWLC-2 galaxy properties: {len(df):,} galaxies",
        )
    print("Done.")


if __name__ == "__main__":
    main()
