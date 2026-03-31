#!/usr/bin/env python3
"""Fetch GSWLC-X2 galaxy catalog and upload to HF.

GSWLC-2 (GALEX-SDSS-WISE Legacy Catalog) contains ~659K galaxies with
stellar masses, star formation rates, and dust attenuation from
UV+optical+IR SED fitting (Salim et al. 2016, 2018).
"""

import io
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from validate import check_dataset

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


def main():
    print("Fetching GSWLC-X2 catalog...")
    resp = requests.get(SOURCE_URL, timeout=300)
    resp.raise_for_status()

    # The server sets Content-Encoding: x-gzip, so `requests` auto-decompresses
    # the response. resp.content is already plain text, not gzip bytes.
    # Detect which case we're in by checking the gzip magic number.
    raw = resp.content
    if raw[:2] == b"\x1f\x8b":
        compression = "gzip"
    else:
        compression = None

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
    df["objid"] = pd.to_numeric(df["objid"], errors="coerce").astype("Int64")
    df["glxid"] = pd.to_numeric(df["glxid"], errors="coerce").astype("Int64")
    df["plate"] = pd.to_numeric(df["plate"], errors="coerce").astype("Int64")
    df["mjd"] = pd.to_numeric(df["mjd"], errors="coerce").astype("Int64")
    df["fiber_id"] = pd.to_numeric(df["fiber_id"], errors="coerce").astype("Int64")

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

    # ── Handle missing values (-99 → NaN) ────────────────────────────
    # Per documentation: missing values are listed as -99
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

    # ── Stats for README ──────────────────────────────────────────────
    valid_mass = df["log_mstar"].notna()
    valid_sfr = df["log_sfr_sed"].notna()
    n_star_forming = int(df["is_star_forming"].sum())
    n_quiescent = int((~df["is_star_forming"] & valid_mass).sum())
    median_mass = df.loc[valid_mass, "log_mstar"].median()
    median_z = df["redshift"].median()

    # ── Validate ──────────────────────────────────────────────────────
    check_dataset(
        df,
        dataset_name="gswlc-galaxy-properties",
        min_rows=500_000,
        expected_columns=[
            "objid", "ra", "dec", "redshift",
            "log_mstar", "log_sfr_sed", "log_ssfr",
            "a_fuv", "a_v",
            "flag_sed", "uv_survey", "flag_uv",
            "is_star_forming",
        ],
        critical_columns=["ra", "dec", "redshift", "objid"],
    )

    # ── Write and upload ──────────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "gswlc_galaxy_properties.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "GSWLC-2 Galaxy Properties"
language:
  - en
description: "659K galaxies with stellar masses, star formation rates, and dust attenuation from UV+optical+IR SED fitting of GALEX, SDSS, and WISE photometry."
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - galaxies
  - stellar-mass
  - star-formation
  - sdss
  - galex
  - wise
  - astronomy
  - open-data
  - tabular-data
  - parquet
size_categories:
  - 100K<n<1M
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/gswlc_galaxy_properties.parquet
    default: true
---

# GSWLC-2 Galaxy Properties

*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

**{len(df):,}** galaxies with physical properties derived from UV-to-infrared spectral energy distribution (SED) fitting. GSWLC-2 (GALEX-SDSS-WISE Legacy Catalog 2) combines ultraviolet photometry from GALEX, optical photometry from SDSS, and mid-infrared photometry from WISE to estimate stellar masses, star formation rates, and dust attenuation for galaxies at redshifts 0.01 < z < 0.30.

## Dataset description

The GSWLC is the definitive catalog for physical properties of low-redshift galaxies, covering ~90% of the SDSS spectroscopic footprint. Version 2 (Salim et al. 2018) incorporates WISE mid-IR photometry to better constrain dust-obscured star formation. The "X" variant (GSWLC-X2) is the master catalog that selects the deepest available UV observation for each galaxy from the A (shallow), M (medium), and D (deep) sub-catalogs.

Physical properties are derived using the CIGALE SED fitting code with Bayesian estimation of stellar mass, star formation rate, and dust attenuation.

Understanding how galaxies form stars and build up their stellar mass is one of the central questions in extragalactic astronomy. The star formation rate and stellar mass of a galaxy are linked through a remarkably tight correlation known as the star formation main sequence, whose slope, normalization, and scatter encode the physics of gas accretion, feedback, and quenching. GSWLC provides the definitive measurement of these quantities for the low-redshift galaxy population, with the critical advantage that mid-infrared photometry from WISE captures dust-reprocessed emission that would otherwise be missed by UV and optical observations alone.

Dust attenuation is one of the largest systematic uncertainties in galaxy SED modeling. Dust grains absorb ultraviolet and optical photons from young stars and re-emit the energy in the far-infrared, meaning that purely optical surveys systematically underestimate star formation rates in dusty galaxies. By jointly fitting the UV (GALEX), optical (SDSS), and mid-IR (WISE) photometry, GSWLC-2 breaks the age-dust-metallicity degeneracy that plagues single-band analyses and delivers attenuation curves alongside physical properties. The A_FUV values in this catalog directly quantify how much UV light each galaxy has lost to dust.

This catalog is the standard reference for calibrating star formation rate indicators, studying the quenching of star formation in massive galaxies, and constructing volume-limited galaxy samples for environmental studies. The specific star formation rate (sSFR) cleanly separates the star-forming blue cloud from the quiescent red sequence, making GSWLC a natural training set for galaxy classification problems in machine learning.

## Quick stats

- **{len(df):,}** galaxies in the catalog
- **{valid_mass.sum():,}** with valid stellar mass estimates
- **{valid_sfr.sum():,}** with valid SFR estimates
- **{n_star_forming:,}** classified as star-forming (log sSFR > -11)
- **{n_quiescent:,}** classified as quiescent
- Median stellar mass: **10^{{{median_mass:.2f}}}** solar masses
- Median redshift: **{median_z:.4f}**

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `objid` | int64 | SDSS photometric object ID |
| `glxid` | int64 | GALEX photometric ID (null if no UV match) |
| `plate` | int64 | SDSS spectroscopic plate number |
| `mjd` | int64 | SDSS spectroscopic plate date (MJD) |
| `fiber_id` | int64 | SDSS spectroscopic fiber ID |
| `ra` | float64 | Right Ascension (J2000, degrees) |
| `dec` | float64 | Declination (J2000, degrees) |
| `redshift` | float64 | Spectroscopic redshift from SDSS |
| `chi2_r` | float64 | Reduced chi-squared of SED fit |
| `log_mstar` | float64 | Log stellar mass (solar masses) |
| `log_mstar_err` | float64 | Error on log stellar mass |
| `log_sfr_sed` | float64 | Log UV/optical SFR (solar masses/yr) |
| `log_sfr_sed_err` | float64 | Error on log SFR |
| `a_fuv` | float64 | Dust attenuation in rest-frame FUV (mag) |
| `a_fuv_err` | float64 | Error on A_FUV |
| `a_b` | float64 | Dust attenuation in rest-frame B band (mag) |
| `a_b_err` | float64 | Error on A_B |
| `a_v` | float64 | Dust attenuation in rest-frame V band (mag) |
| `a_v_err` | float64 | Error on A_V |
| `flag_sed` | int64 | SED fitting flag (0=OK, 1=broad-line, 2=chi2>30, 5=missing photometry) |
| `uv_survey` | int64 | UV survey depth (1=shallow/A, 2=medium/M, 3=deep/D) |
| `flag_uv` | int64 | UV detection flag (0=none, 1=FUV only, 2=NUV only, 3=both) |
| `flag_midir` | int64 | Mid-IR flag (0=none, 1=12um, 2=22um, 5=AGN-corrected) |
| `flag_mgs` | int64 | SDSS Main Galaxy Sample flag (0=no, 1=yes) |
| `log_ssfr` | float64 | Derived: log specific SFR (log SFR - log M*, yr^-1) |
| `is_star_forming` | bool | Derived: log sSFR > -11 |
| `uv_survey_name` | string | Derived: human-readable UV survey name |

## Usage

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

# Dusty galaxies (high FUV attenuation)
dusty = df[df["a_fuv"] > 3.0]

# Cross-match with SDSS using objid
```

## Data source

[GSWLC-2](https://salims.pages.iu.edu/gswlc/) — Salim et al. (2016, 2018).

- Salim et al. (2016), "GALEX-SDSS-WISE Legacy Catalog (GSWLC): Star Formation Rates, Stellar Masses, and Dust Attenuations of 700,000 Low-Redshift Galaxies", *ApJS*, 227, 2. [arXiv:1610.00712](https://arxiv.org/abs/1610.00712)
- Salim et al. (2018), "Dust Attenuation Curves in the Local Universe: Demographics and New Laws for Star-forming Galaxies and High-redshift Analogs", *ApJ*, 859, 11. [arXiv:1804.05850](https://arxiv.org/abs/1804.05850)

## Related datasets

- [galaxy-zoo-2-morphology](https://huggingface.co/datasets/juliensimon/galaxy-zoo-2-morphology) — Galaxy Zoo 2 visual morphological classifications
- [open-ngc](https://huggingface.co/datasets/juliensimon/open-ngc) — NGC/IC galaxy and nebula catalog

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Citation

```bibtex
@dataset{{gswlc_galaxy_properties,
  author = {{Simon, Julien}},
  title = {{GSWLC-2 Galaxy Properties}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/gswlc-galaxy-properties}},
  note = {{Based on GSWLC-2 data (Salim et al. 2016, ApJS 227, 2; Salim et al. 2018, ApJ 859, 11)}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Upload GSWLC-2 galaxy properties: {len(df):,} galaxies"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    print(f"rows={len(df)}")
    print("Done.")


if __name__ == "__main__":
    main()
