#!/usr/bin/env python3
"""Fetch GALAH DR4 stellar abundances catalog (FITS) and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests
from astropy.table import Table

from validate import check_dataset

FITS_URL = "https://cloud.datacentral.org.au/teamdata/GALAH/public/GALAH_DR4/catalogs/galah_dr4_allstar_240705.fits"
HF_REPO = "juliensimon/galah-dr4-stellar-abundances"

# ── Columns to keep ─────────────────────────────────────────────────────
# Identifiers & position
ID_COLS = [
    "sobject_id", "star_id", "tmass_id", "gaiadr3_source_id",
    "ra", "dec",
]

# Stellar parameters & radial velocity
PARAM_COLS = [
    "teff", "logg", "fe_h", "vmic", "vsini",
    "rv_comp_1", "rv_comp_2",
]

# Signal-to-noise & quality flags
QUALITY_COLS = [
    "snr_px_ccd1", "snr_px_ccd2", "snr_px_ccd3", "snr_px_ccd4",
    "flag_sp", "flag_red",
]

# Elemental abundances [X/Fe] — 31 elements
ABUNDANCE_COLS = [
    "li_fe", "c_fe", "n_fe", "o_fe",
    "na_fe", "al_fe", "k_fe",
    "mg_fe", "si_fe", "ca_fe", "ti_fe",
    "sc_fe", "v_fe", "cr_fe", "mn_fe", "co_fe", "ni_fe", "cu_fe", "zn_fe",
    "rb_fe", "sr_fe", "y_fe", "zr_fe", "mo_fe", "ba_fe", "la_fe", "ce_fe", "nd_fe",
    "ru_fe", "sm_fe", "eu_fe",
]

KEEP_COLS = ID_COLS + PARAM_COLS + QUALITY_COLS + ABUNDANCE_COLS


def main():
    # ── Download FITS ────────────────────────────────────────────────────
    print("Downloading GALAH DR4 allstar FITS catalog (≈723 MB)...")
    with tempfile.NamedTemporaryFile(suffix=".fits") as tmp_fits:
        with requests.get(FITS_URL, timeout=600, stream=True) as resp:
            resp.raise_for_status()
            total = 0
            for chunk in resp.iter_content(chunk_size=8 * 1024 * 1024):
                tmp_fits.write(chunk)
                total += len(chunk)
            tmp_fits.flush()
        print(f"  Downloaded {total / 1024 / 1024:.0f} MB")

        # ── Read FITS into DataFrame ─────────────────────────────────────
        print("Reading FITS table...")
        table = Table.read(tmp_fits.name, hdu=1)

    # Keep only columns that actually exist in the file
    available = [c for c in KEEP_COLS if c in table.colnames]
    missing = set(KEEP_COLS) - set(available)
    if missing:
        print(f"  Note: {len(missing)} requested columns not in FITS: {sorted(missing)}")

    # Filter out any multidimensional columns (can't convert to pandas)
    scalar = [c for c in available if len(table[c].shape) <= 1]
    df = table[scalar].to_pandas()
    print(f"  {len(df):,} stars, {len(df.columns)} columns")

    # ── Rename columns ───────────────────────────────────────────────────
    rename_map = {
        "rv_comp_1": "radial_velocity_kms",
        "rv_comp_2": "radial_velocity_comp2_kms",
        "fe_h": "fe_h_dex",
        "teff": "teff_k",
    }
    rename_map = {k: v for k, v in rename_map.items() if k in df.columns}
    df = df.rename(columns=rename_map)

    # ── Type coercion ────────────────────────────────────────────────────
    # Numeric columns
    numeric = [c for c in df.columns if c not in
               ("sobject_id", "star_id", "tmass_id", "gaiadr3_source_id",
                "flag_sp", "flag_red")]
    for col in numeric:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Integer flag columns
    for col in ("flag_sp", "flag_red"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    # String identifiers
    for col in ("sobject_id", "star_id", "tmass_id", "gaiadr3_source_id"):
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
            df[col] = df[col].replace({"": None, "nan": None})

    # ── Derived columns ──────────────────────────────────────────────────
    # Count how many abundance measurements each star has (non-null)
    abund_cols_in_df = [c for c in ABUNDANCE_COLS if c in df.columns]
    df["n_abundances"] = df[abund_cols_in_df].notna().sum(axis=1).astype("Int64")

    # Mean SNR across the 4 CCDs
    snr_cols = [c for c in ("snr_px_ccd1", "snr_px_ccd2", "snr_px_ccd3", "snr_px_ccd4")
                if c in df.columns]
    if snr_cols:
        df["snr_mean"] = df[snr_cols].mean(axis=1)

    # ── Validation ───────────────────────────────────────────────────────
    rv_col = "radial_velocity_kms" if "radial_velocity_kms" in df.columns else "rv_comp_1"
    check_dataset(
        df, "galah-dr4",
        min_rows=500_000,
        expected_columns=["sobject_id", "ra", "dec", "teff_k", "logg", "fe_h_dex", rv_col],
        critical_columns=["sobject_id", "ra", "dec", "teff_k"],
    )

    # ── Stats for README ─────────────────────────────────────────────────
    n_total = len(df)
    n_rv = int(df[rv_col].notna().sum()) if rv_col in df.columns else 0
    n_abund = int((df["n_abundances"] > 0).sum())
    median_abund = int(df["n_abundances"].median()) if "n_abundances" in df.columns else 0
    median_snr = f"{df['snr_mean'].median():.1f}" if "snr_mean" in df.columns else "N/A"
    n_elements = len(abund_cols_in_df)

    # ── Write parquet & README ───────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "galah_dr4_allstar.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "GALAH DR4 — Stellar Abundances for 917k Stars"
language:
  - en
description: "The fourth data release of the Galactic Archaeology with HERMES survey — radial velocities, stellar parameters, and up to 31 elemental abundances for 917,588 stars."
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - stars
  - spectroscopy
  - galah
  - abundances
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
        path: data/galah_dr4_allstar.parquet
    default: true
---

# GALAH DR4 — Stellar Abundances for 917k Stars

*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

The fourth data release of the GALactic Archaeology with HERMES (GALAH) survey,
providing radial velocities, stellar parameters, and up to 31 elemental abundances
for **{n_total:,}** stars observed with the HERMES spectrograph on the
Anglo-Australian Telescope.

## Dataset description

GALAH DR4 is one of the largest stellar spectroscopic surveys, designed to unravel
the formation and evolution of the Milky Way through chemical tagging. Each star has
high-resolution spectra decomposed into fundamental stellar parameters and individual
elemental abundances spanning light elements, alpha-elements, iron-peak elements,
and neutron-capture elements.

GALAH was specifically designed for chemical tagging -- the idea that stars born in the same molecular cloud retain a unique multi-dimensional chemical fingerprint that persists long after the birth cluster has dispersed. To achieve this, GALAH requires both high spectral resolution (R ~ 28,000) and broad elemental coverage, which the HERMES spectrograph delivers through four non-contiguous optical wavelength channels centered on key spectral features. The four channels capture lines of light elements (Li, C, N, O), alpha-elements (Mg, Si, Ca, Ti), iron-peak elements (Sc, V, Cr, Mn, Fe, Co, Ni, Cu, Zn), and neutron-capture elements (Rb, Sr, Y, Zr, Mo, Ba, La, Ce, Nd, Ru, Sm, Eu), providing up to 31 distinct abundance dimensions per star.

The survey primarily targets FGK-type stars in the magnitude range 12 < V < 14 across the southern sky, sampling a volume that extends from the solar neighborhood out to several kiloparsecs. DR4 represents a major advance over DR3, incorporating improved spectral analysis techniques, better treatment of non-LTE effects for critical elements, and cross-matching with Gaia DR3 for precise astrometric information. The inclusion of both s-process elements (Ba, La, Ce from AGB nucleosynthesis) and r-process elements (Eu from neutron star mergers) makes GALAH uniquely powerful for constraining the sites and timescales of heavy element production in the Milky Way.

When combined with Gaia astrometry, GALAH provides the full chemodynamical phase space (positions, velocities, and multi-element abundances) needed to disentangle the overlapping stellar populations of the Galactic disk, identify accreted satellite debris, and trace the assembly history of the Milky Way. GALAH's target density and chemical detail complement the deeper but infrared-only APOGEE survey, and together they form the backbone of modern Galactic archaeology.

Key properties:
- **{n_rv:,}** stars with radial velocity measurements
- **{n_abund:,}** stars with at least one elemental abundance
- **{n_elements}** elemental abundance columns ([X/Fe])
- Median **{median_abund}** abundances per star
- Median SNR: **{median_snr}** per pixel

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `sobject_id` | string | GALAH observation identifier |
| `star_id` | string | GALAH unique star identifier |
| `tmass_id` | string | 2MASS identifier |
| `gaiadr3_source_id` | string | Gaia DR3 source identifier |
| `ra` | float64 | Right Ascension J2000 (degrees) |
| `dec` | float64 | Declination J2000 (degrees) |
| `teff_k` | float64 | Effective temperature (K) |
| `logg` | float64 | Surface gravity (log cm/s^2) |
| `fe_h_dex` | float64 | Iron abundance [Fe/H] (dex) |
| `vmic` | float64 | Microturbulence velocity (km/s) |
| `vsini` | float64 | Projected rotational velocity (km/s) |
| `radial_velocity_kms` | float64 | Barycentric radial velocity (km/s) |
| `radial_velocity_comp2_kms` | float64 | Binary companion RV (km/s) |
| `snr_px_ccd1`..`snr_px_ccd4` | float64 | Signal-to-noise per pixel (4 CCDs) |
| `snr_mean` | float64 | Mean SNR across all 4 CCDs |
| `flag_sp` | Int64 | Spectroscopic quality flag (0 = best) |
| `flag_red` | Int64 | Reduction pipeline quality flag |
| `li_fe`..`eu_fe` | float64 | Elemental abundances [X/Fe] (dex) — 31 elements |
| `n_abundances` | Int64 | Count of non-null abundance measurements |

### Abundance columns

Light: `li_fe`, `c_fe`, `n_fe`, `o_fe` ·
Odd-Z: `na_fe`, `al_fe`, `k_fe` ·
Alpha: `mg_fe`, `si_fe`, `ca_fe`, `ti_fe` ·
Iron-peak: `sc_fe`, `v_fe`, `cr_fe`, `mn_fe`, `co_fe`, `ni_fe`, `cu_fe`, `zn_fe` ·
s-process: `rb_fe`, `sr_fe`, `y_fe`, `zr_fe`, `mo_fe`, `ba_fe`, `la_fe`, `ce_fe`, `nd_fe` ·
r-process: `ru_fe`, `sm_fe`, `eu_fe`

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/galah-dr4-stellar-abundances", split="train")
df = ds.to_pandas()

# High-quality stars with best spectroscopic flags
best = df[df["flag_sp"] == 0]

# Metal-poor stars
metal_poor = df[df["fe_h_dex"] < -1.0]

# Stars rich in europium (r-process)
eu_rich = df[df["eu_fe"] > 0.5]

# Stars with the most measured abundances
well_measured = df.sort_values("n_abundances", ascending=False).head(1000)

# Kiel diagram (logg vs Teff)
import matplotlib.pyplot as plt
sample = df[df["flag_sp"] == 0].sample(50000)
plt.scatter(sample["teff_k"], sample["logg"], c=sample["fe_h_dex"],
            s=0.1, cmap="coolwarm", vmin=-1.5, vmax=0.5)
plt.gca().invert_xaxis()
plt.gca().invert_yaxis()
plt.xlabel("Teff (K)")
plt.ylabel("log g")
plt.colorbar(label="[Fe/H]")
```

## Data source

[GALAH Survey DR4](https://www.galah-survey.org/dr4/) (Buder et al. 2024).
Observed with the HERMES spectrograph (R ≈ 28,000) on the 3.9m Anglo-Australian
Telescope at Siding Spring Observatory.

## Update schedule

Static dataset — uploaded once from the DR4 release catalog.

## Related datasets

- [gaia-dr3-astrophysical-parameters](https://huggingface.co/datasets/juliensimon/gaia-dr3-astrophysical-parameters) — Gaia DR3 stellar parameters
- [exoplanet-catalog](https://huggingface.co/datasets/juliensimon/exoplanet-catalog) — Confirmed exoplanets
- [pulsar-catalog](https://huggingface.co/datasets/juliensimon/pulsar-catalog) — Pulsar catalog

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/galah-dr4-stellar-abundances) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@article{{buder2024galah,
  author = {{Buder, Sven and others}},
  title = {{The GALAH Survey: Data Release 4}},
  year = {{2024}},
  journal = {{arXiv preprint arXiv:2409.19858}},
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Upload GALAH DR4: {n_total:,} stars, {n_elements} elements"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={len(df)}\n")
    print("Done.")


if __name__ == "__main__":
    main()
