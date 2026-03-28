#!/usr/bin/env python3
"""Fetch APOGEE DR17 AllStar catalog from VizieR and upload to HF."""

import os
import re
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from validate import check_dataset
from vizier_tap import vizier_query

HF_REPO = "juliensimon/apogee-dr17"

ADQL = 'SELECT * FROM "III/286/catalog"'

# Abundance elements tracked in APOGEE DR17
ABUNDANCE_ELEMENTS = [
    "C", "CI", "N", "O", "Na", "Mg", "Al", "Si", "S",
    "K", "Ca", "Ti", "TiII", "V", "Mn", "Fe", "Co", "Ni", "Ce", "Nd",
]


def main():
    print("Fetching APOGEE DR17 AllStar catalog from VizieR...")
    df = vizier_query(ADQL, timeout=600)
    print(f"  {len(df):,} rows fetched")

    # --- Column renames ---
    # VizieR sanitizes bracket-notation columns like [Fe/H] in various ways.
    # We provide all known variants to be safe.
    rename = {
        # Coordinates
        "RA_ICRS": "ra_deg",
        "RAJ2000": "ra_deg",
        "_RA": "ra_deg",
        "RAdeg": "ra_deg",
        "DE_ICRS": "dec_deg",
        "DEJ2000": "dec_deg",
        "_DE": "dec_deg",
        "DEdeg": "dec_deg",
        # Identifiers
        "APOGEE_ID": "apogee_id",
        "APOGEE-ID": "apogee_id",
        "APOGEE": "apogee_id",
        "ApoID": "apogee_id",
        "Target": "target_id",
        "2MASS": "twomass_id",
        "Gaia": "gaia_source_id",
        "GaiaDR3": "gaia_source_id",
        "GaiaEDR3": "gaia_source_id",
        # Stellar parameters
        "Teff": "teff_k",
        "e_Teff": "teff_error_k",
        "logg": "logg",
        "e_logg": "logg_error",
        "TeffSp": "teff_sp",
        "loggSp": "logg_sp",
        "Vmicro": "vmicro_kms",
        "Vmacro": "vmacro_kms",
        "Vsini": "vsini_kms",
        # Note: [Fe/H] and its Sp/error/flag variants are in the abundance section below
        # Overall metallicity [M/H]
        "[M/H]": "m_h",
        "__M_H_": "m_h",
        "_M_H_": "m_h",
        "e_[M/H]": "m_h_error",
        "e__M_H_": "m_h_error",
        # Alpha enhancement [alpha/M]
        "__a_M_": "alpha_m",
        "_a_M_": "alpha_m",
        "ALPHA_M": "alpha_m",
        "[a/M]": "alpha_m",
        "a_M": "alpha_m",
        "e__a_M_": "alpha_m_error",
        "e_a_M": "alpha_m_error",
        "e_ALPHA_M": "alpha_m_error",
        # Individual abundances [X/Fe] — double-underscore VizieR pattern
        # Individual abundances [X/Fe], [X/Fe]Sp (spectroscopic), e_[X/Fe] (error), f_[X/Fe] (flag)
        "[C/Fe]": "c_fe", "[C/Fe]Sp": "c_fe_sp", "e_[C/Fe]": "c_fe_err", "f_[C/Fe]": "c_fe_flag",
        "[CI/Fe]": "ci_fe", "[CI/Fe]Sp": "ci_fe_sp", "e_[CI/Fe]": "ci_fe_err", "f_[CI/Fe]": "ci_fe_flag",
        "[N/Fe]": "n_fe", "[N/Fe]Sp": "n_fe_sp", "e_[N/Fe]": "n_fe_err", "f_[N/Fe]": "n_fe_flag",
        "[O/Fe]": "o_fe", "[O/Fe]Sp": "o_fe_sp", "e_[O/Fe]": "o_fe_err", "f_[O/Fe]": "o_fe_flag",
        "[Na/Fe]": "na_fe", "[Na/Fe]Sp": "na_fe_sp", "e_[Na/Fe]": "na_fe_err", "f_[Na/Fe]": "na_fe_flag",
        "[Mg/Fe]": "mg_fe", "[Mg/Fe]Sp": "mg_fe_sp", "e_[Mg/Fe]": "mg_fe_err", "f_[Mg/Fe]": "mg_fe_flag",
        "[Al/Fe]": "al_fe", "[Al/Fe]Sp": "al_fe_sp", "e_[Al/Fe]": "al_fe_err", "f_[Al/Fe]": "al_fe_flag",
        "[Si/Fe]": "si_fe", "[Si/Fe]Sp": "si_fe_sp", "e_[Si/Fe]": "si_fe_err", "f_[Si/Fe]": "si_fe_flag",
        "[S/Fe]": "s_fe", "[S/Fe]Sp": "s_fe_sp", "e_[S/Fe]": "s_fe_err", "f_[S/Fe]": "s_fe_flag",
        "[K/Fe]": "k_fe", "[K/Fe]Sp": "k_fe_sp", "e_[K/Fe]": "k_fe_err", "f_[K/Fe]": "k_fe_flag",
        "[Ca/Fe]": "ca_fe", "[Ca/Fe]Sp": "ca_fe_sp", "e_[Ca/Fe]": "ca_fe_err", "f_[Ca/Fe]": "ca_fe_flag",
        "[Ti/Fe]": "ti_fe", "[Ti/Fe]Sp": "ti_fe_sp", "e_[Ti/Fe]": "ti_fe_err", "f_[Ti/Fe]": "ti_fe_flag",
        "[TiII/Fe]": "tiii_fe", "[TiII/Fe]Sp": "tiii_fe_sp", "e_[TiII/Fe]": "tiii_fe_err", "f_[TiII/Fe]": "tiii_fe_flag",
        "[V/Fe]": "v_fe", "[V/Fe]Sp": "v_fe_sp", "e_[V/Fe]": "v_fe_err", "f_[V/Fe]": "v_fe_flag",
        "[Cr/Fe]": "cr_fe", "[Cr/Fe]Sp": "cr_fe_sp", "e_[Cr/Fe]": "cr_fe_err", "f_[Cr/Fe]": "cr_fe_flag",
        "[Mn/Fe]": "mn_fe", "[Mn/Fe]Sp": "mn_fe_sp", "e_[Mn/Fe]": "mn_fe_err", "f_[Mn/Fe]": "mn_fe_flag",
        "[Co/Fe]": "co_fe", "[Co/Fe]Sp": "co_fe_sp", "e_[Co/Fe]": "co_fe_err", "f_[Co/Fe]": "co_fe_flag",
        "[Ni/Fe]": "ni_fe", "[Ni/Fe]Sp": "ni_fe_sp", "e_[Ni/Fe]": "ni_fe_err", "f_[Ni/Fe]": "ni_fe_flag",
        "[Ce/Fe]": "ce_fe", "[Ce/Fe]Sp": "ce_fe_sp", "e_[Ce/Fe]": "ce_fe_err", "f_[Ce/Fe]": "ce_fe_flag",
        "[Fe/H]": "fe_h", "[Fe/H]Sp": "fe_h_sp", "e_[Fe/H]": "fe_h_err", "f_[Fe/H]": "fe_h_flag",
        "[Fe/H]RV": "fe_h_rv",
        # [X/H] variants — VizieR may use these instead of [X/Fe]
        "__C_H_": "c_h", "_C_H_": "c_h", "C_H": "c_h", "[C/H]": "c_h",
        "__N_H_": "n_h", "_N_H_": "n_h", "N_H": "n_h", "[N/H]": "n_h",
        "__O_H_": "o_h", "_O_H_": "o_h", "O_H": "o_h", "[O/H]": "o_h",
        "__Na_H_": "na_h", "_Na_H_": "na_h", "Na_H": "na_h",
        "__Mg_H_": "mg_h", "_Mg_H_": "mg_h", "Mg_H": "mg_h",
        "__Al_H_": "al_h", "_Al_H_": "al_h", "Al_H": "al_h",
        "__Si_H_": "si_h", "_Si_H_": "si_h", "Si_H": "si_h",
        "__S_H_": "s_h", "_S_H_": "s_h", "S_H": "s_h",
        "__K_H_": "k_h", "_K_H_": "k_h", "K_H": "k_h",
        "__Ca_H_": "ca_h", "_Ca_H_": "ca_h", "Ca_H": "ca_h",
        "__Ti_H_": "ti_h", "_Ti_H_": "ti_h", "Ti_H": "ti_h",
        "__V_H_": "v_h", "_V_H_": "v_h", "V_H": "v_h",
        "__Mn_H_": "mn_h", "_Mn_H_": "mn_h", "Mn_H": "mn_h",
        "__Co_H_": "co_h", "_Co_H_": "co_h", "Co_H": "co_h",
        "__Ni_H_": "ni_h", "_Ni_H_": "ni_h", "Ni_H": "ni_h",
        "__Ce_H_": "ce_h", "_Ce_H_": "ce_h", "Ce_H": "ce_h",
        "__Nd_H_": "nd_h", "_Nd_H_": "nd_h", "Nd_H": "nd_h",
        # Radial velocity
        "VHELIO": "radial_velocity_kms",
        "VHELIO_AVG": "radial_velocity_kms",
        "HRV": "radial_velocity_kms",
        "RV": "gaia_radial_velocity_kms",
        "e_VHELIO": "radial_velocity_error_kms",
        "e_VHELIO_AVG": "radial_velocity_error_kms",
        "e_HRV": "radial_velocity_error_kms",
        "e_RV": "gaia_radial_velocity_error_kms",
        "s_HRV": "rv_scatter_kms",
        "VRSCATTER": "rv_scatter_kms",
        "VSCATTER": "rv_scatter_kms",
        # Photometry
        "Jmag": "j_mag",
        "Hmag": "h_mag",
        "Kmag": "k_mag",
        "Ksmag": "k_mag",
        "J": "j_mag",
        "H": "h_mag",
        "K": "k_mag",
        "e_Jmag": "j_mag_error",
        "e_Hmag": "h_mag_error",
        "e_Kmag": "k_mag_error",
        # SNR
        "SNR": "snr",
        "SNR_AVG": "snr",
        # Visit count
        "NVISITS": "n_visits",
        "Nvisits": "n_visits",
        "Nvis": "n_visits",
        # Targeting / flags
        "STARFLAG": "star_flag",
        "ASPCAPFLAG": "aspcap_flag",
        "EXTRATARG": "extra_targ",
        # Proper motion
        "pmRA": "pmra_mas_yr",
        "pmDE": "pmdec_mas_yr",
        "pmGLON": "pm_glon",
        "pmGLAT": "pm_glat",
        # Galactic coords
        "GLON": "glon_deg",
        "GLAT": "glat_deg",
        # Distance / parallax
        "Plx": "parallax_mas",
        "plx": "parallax_mas",
        "e_Plx": "parallax_error_mas",
        "e_plx": "parallax_error_mas",
        "Gmag": "gaia_g_mag",
        "BPmag": "gaia_bp_mag",
        "RPmag": "gaia_rp_mag",
        "rgeo": "distance_geo_pc",
        "rpgeo": "distance_photogeo_pc",
    }

    # Only rename columns that actually exist
    rename_actual = {k: v for k, v in rename.items() if k in df.columns}
    df = df.rename(columns=rename_actual)

    # Drop unwanted columns
    drop_cols = [c for c in ["recno", "SimbadName", "More", "Simbad"] if c in df.columns]
    if drop_cols:
        df = df.drop(columns=drop_cols)
        print(f"  Dropped columns: {drop_cols}")

    # Snake-case any remaining columns not yet renamed
    def to_snake(name):
        # Already snake_case
        if name == name.lower() and "_" in name:
            return name
        s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
        s = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s)
        s = re.sub(r"[-.\s]+", "_", s)
        return s.lower().strip("_")

    df.columns = [to_snake(c) for c in df.columns]

    # --- Numeric conversion ---
    # Abundances, stellar params, photometry, velocities, errors
    abundance_cols = [
        "fe_h", "fe_h_error", "alpha_m", "alpha_m_error",
        "c_fe", "ci_fe", "n_fe", "o_fe", "na_fe", "mg_fe", "al_fe",
        "si_fe", "s_fe", "k_fe", "ca_fe", "ti_fe", "tiii_fe",
        "v_fe", "mn_fe", "co_fe", "ni_fe", "ce_fe", "nd_fe",
        "c_h", "n_h", "o_h", "na_h", "mg_h", "al_h", "si_h",
        "s_h", "k_h", "ca_h", "ti_h", "v_h", "mn_h", "co_h",
        "ni_h", "ce_h", "nd_h",
    ]
    numeric_cols = [
        "ra_deg", "dec_deg", "teff_k", "teff_error_k", "logg", "logg_error",
        "radial_velocity_kms", "radial_velocity_error_kms", "rv_scatter_kms",
        "j_mag", "h_mag", "k_mag", "j_mag_error", "h_mag_error", "k_mag_error",
        "snr", "parallax_mas", "parallax_error_mas",
        "pmra_mas_yr", "pmdec_mas_yr", "glon_deg", "glat_deg",
    ] + abundance_cols

    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Integer columns
    for col in ["n_visits"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    # Sort by APOGEE ID if available
    if "apogee_id" in df.columns:
        df = df.sort_values("apogee_id").reset_index(drop=True)

    # --- Stats ---
    n_total = len(df)
    n_with_teff = int(df["teff_k"].notna().sum()) if "teff_k" in df.columns else 0
    n_with_feh = int(df["fe_h"].notna().sum()) if "fe_h" in df.columns else 0

    teff_min = df["teff_k"].min() if "teff_k" in df.columns else 0
    teff_max = df["teff_k"].max() if "teff_k" in df.columns else 0
    feh_min = df["fe_h"].min() if "fe_h" in df.columns else 0
    feh_max = df["fe_h"].max() if "fe_h" in df.columns else 0

    # Count how many abundance elements have data
    fe_abundance_cols = [c for c in df.columns if c.endswith("_fe") and c != "fe_h"]
    h_abundance_cols = [c for c in df.columns if c.endswith("_h") and c not in ("fe_h", "fe_h_error", "alpha_m")]
    all_abund_cols = fe_abundance_cols + h_abundance_cols
    n_elements = len(set(c.replace("_fe", "").replace("_h", "") for c in all_abund_cols))

    print(f"  {n_total:,} stars total")
    print(f"  {n_with_teff:,} with Teff, {n_with_feh:,} with [Fe/H]")
    print(f"  Teff range: {teff_min:.0f} - {teff_max:.0f} K")
    print(f"  [Fe/H] range: {feh_min:.2f} to {feh_max:.2f} dex")
    print(f"  {n_elements} abundance elements available")

    # --- Validation ---
    check_dataset(df, "apogee-dr17", min_rows=500_000,
        expected_columns=["ra_deg", "dec_deg", "teff_k"],
        critical_columns=["ra_deg", "dec_deg", "teff_k"])

    # --- Build schema table ---
    col_descriptions = {
        "apogee_id": ("string", "APOGEE unique star identifier"),
        "twomass_id": ("string", "2MASS identifier"),
        "gaia_source_id": ("string", "Gaia DR3 source ID"),
        "ra_deg": ("float64", "Right ascension ICRS (degrees)"),
        "dec_deg": ("float64", "Declination ICRS (degrees)"),
        "glon_deg": ("float64", "Galactic longitude (degrees)"),
        "glat_deg": ("float64", "Galactic latitude (degrees)"),
        "teff_k": ("float64", "Effective temperature (K)"),
        "teff_error_k": ("float64", "Teff uncertainty (K)"),
        "logg": ("float64", "Surface gravity log g (dex)"),
        "logg_error": ("float64", "log g uncertainty (dex)"),
        "fe_h": ("float64", "Metallicity [Fe/H] (dex)"),
        "fe_h_error": ("float64", "[Fe/H] uncertainty (dex)"),
        "alpha_m": ("float64", "Alpha enhancement [alpha/M] (dex)"),
        "alpha_m_error": ("float64", "[alpha/M] uncertainty (dex)"),
        "radial_velocity_kms": ("float64", "Heliocentric radial velocity (km/s)"),
        "radial_velocity_error_kms": ("float64", "RV uncertainty (km/s)"),
        "rv_scatter_kms": ("float64", "RV scatter across visits (km/s)"),
        "j_mag": ("float64", "2MASS J magnitude"),
        "h_mag": ("float64", "2MASS H magnitude"),
        "k_mag": ("float64", "2MASS K magnitude"),
        "snr": ("float64", "Combined signal-to-noise ratio"),
        "n_visits": ("Int64", "Number of visits"),
        "pmra_mas_yr": ("float64", "Proper motion in RA (mas/yr)"),
        "pmdec_mas_yr": ("float64", "Proper motion in Dec (mas/yr)"),
        "parallax_mas": ("float64", "Parallax (mas)"),
        "parallax_error_mas": ("float64", "Parallax uncertainty (mas)"),
    }
    # Add abundance columns dynamically
    for col in sorted(fe_abundance_cols):
        elem = col.replace("_fe", "").upper()
        col_descriptions[col] = ("float64", f"[{elem}/Fe] abundance (dex)")
    for col in sorted(h_abundance_cols):
        elem = col.replace("_h", "").upper()
        col_descriptions[col] = ("float64", f"[{elem}/H] abundance (dex)")

    # Deduplicate columns (keep first occurrence)
    df = df.loc[:, ~df.columns.duplicated()]

    schema_rows = ""
    for col in df.columns:
        if col in col_descriptions:
            dtype, desc = col_descriptions[col]
            schema_rows += f"| `{col}` | {dtype} | {desc} |\n"
        else:
            schema_rows += f"| `{col}` | {df[col].dtype} | -- |\n"

    # --- Write parquet and README, upload ---
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "apogee_dr17.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "APOGEE DR17 Stellar Parameters & Abundances"
language:
  - en
description: >-
  APOGEE DR17 AllStar catalog: high-resolution infrared spectroscopic stellar
  parameters and 20+ individual chemical element abundances for ~657K stars.
  The final SDSS-IV APOGEE release and the premier stellar chemical abundance catalog.
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - stars
  - stellar
  - spectroscopy
  - chemical-abundances
  - apogee
  - sdss
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
        path: data/apogee_dr17.parquet
    default: true
---

# APOGEE DR17 Stellar Parameters & Abundances

*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

The APOGEE DR17 AllStar catalog provides high-resolution infrared (H-band)
spectroscopic stellar parameters and **{n_elements}+ individual chemical element
abundances** for **{n_total:,}** stars across the Milky Way. This is the final
data release from SDSS-IV APOGEE and represents the premier stellar chemical
abundance catalog available today.

## Dataset description

The Apache Point Observatory Galactic Evolution Experiment (APOGEE) is a
large-scale, high-resolution (R ~ 22,500), near-infrared (H-band, 1.51-1.70 um)
spectroscopic survey of Milky Way stellar populations. DR17 is the final release
of SDSS-IV, containing the complete APOGEE-2 dataset with observations from both
the Northern (APO 2.5m) and Southern (du Pont 2.5m at LCO) hemispheres.

The ASPCAP pipeline (APOGEE Stellar Parameter and Chemical Abundances Pipeline)
derives effective temperature, surface gravity, metallicity, and individual
elemental abundances by comparing observed spectra against synthetic spectral
libraries. The catalog covers a wide range of stellar types including red giants,
red clump stars, and main-sequence stars across the Galactic disk, bulge, and halo.

## Schema

| Column | Type | Description |
|--------|------|-------------|
{schema_rows}
## Quick stats

- **{n_total:,}** stars total
- **{n_with_teff:,}** with effective temperature
- **{n_with_feh:,}** with [Fe/H] metallicity
- **{n_elements}** individual abundance elements
- Teff range: **{teff_min:.0f}** -- **{teff_max:.0f}** K
- [Fe/H] range: **{feh_min:.2f}** to **{feh_max:.2f}** dex

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/apogee-dr17", split="train")
df = ds.to_pandas()

# Kiel diagram (Teff vs log g)
import matplotlib.pyplot as plt
valid = df.dropna(subset=["teff_k", "logg"])
plt.scatter(valid["teff_k"], valid["logg"], c=valid["fe_h"],
            s=0.1, alpha=0.3, cmap="coolwarm", vmin=-2, vmax=0.5)
plt.gca().invert_xaxis()
plt.gca().invert_yaxis()
plt.xlabel("Teff (K)")
plt.ylabel("log g (dex)")
plt.colorbar(label="[Fe/H]")
plt.title("APOGEE DR17 Kiel Diagram")

# [Mg/Fe] vs [Fe/H] — chemical evolution
if "mg_fe" in df.columns:
    valid = df.dropna(subset=["fe_h", "mg_fe"])
    plt.figure()
    plt.scatter(valid["fe_h"], valid["mg_fe"], s=0.1, alpha=0.2)
    plt.xlabel("[Fe/H] (dex)")
    plt.ylabel("[Mg/Fe] (dex)")
    plt.title("Chemical Evolution: [Mg/Fe] vs [Fe/H]")
```

## Data source

Abdurro'uf et al. (2022), "The Seventeenth Data Release of the Sloan Digital
Sky Surveys: Complete Release of MaNGA, MaStar, and APOGEE-2 Data", ApJS, 259, 35.
Accessed via [VizieR III/286](https://vizier.cds.unistra.fr/viz-bin/VizieR?-source=III/286),
CDS Strasbourg.

## Related datasets

- [rave-dr6](https://huggingface.co/datasets/juliensimon/rave-dr6) -- RAVE DR6 stellar parameters and chemical abundances
- [wolf-rayet-stars](https://huggingface.co/datasets/juliensimon/wolf-rayet-stars) -- Galactic Wolf-Rayet star catalog
- [brown-dwarf-catalog](https://huggingface.co/datasets/juliensimon/brown-dwarf-catalog) -- Brown dwarf catalog

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a heart on the [dataset page](https://huggingface.co/datasets/juliensimon/apogee-dr17) and share feedback in the Community tab! Also consider giving a star to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{apogee_dr17,
  author = {{Simon, Julien}},
  title = {{APOGEE DR17 Stellar Parameters & Abundances}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/apogee-dr17}},
  note = {{Based on Abdurro'uf et al. (2022, ApJS 259 35) via VizieR CDS Strasbourg}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Upload APOGEE DR17: {n_total:,} stars, {n_elements} elements"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={n_total}\n")
    print("Done.")


if __name__ == "__main__":
    main()
