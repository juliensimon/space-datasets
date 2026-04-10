#!/usr/bin/env python3
"""Fetch Galactic Wolf-Rayet Stars catalog from VizieR and upload to HF.

Source: Rate & Crowther (2020, MNRAS 493, 1512) — Gaia DR2 distances
and properties for 383 Galactic Wolf-Rayet stars.
VizieR catalog: J/MNRAS/493/1512
"""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from dataset_images import banner_markdown, download_banner
from validate import check_dataset
from vizier_tap import vizier_query


HF_REPO = "juliensimon/wolf-rayet-stars"

# Main table: astrometry, spectral types, distances, Gaia photometry
ADQL_MAIN = 'SELECT * FROM "J/MNRAS/493/1512/table1"'

# Table 6: Ks-band photometry and absolute magnitudes
ADQL_KMAG = 'SELECT * FROM "J/MNRAS/493/1512/table6"'


def main():
    print("Fetching Galactic Wolf-Rayet stars from VizieR...")
    df = vizier_query(ADQL_MAIN)
    print(f"  {len(df):,} Wolf-Rayet stars (main table)")

    df_kmag = vizier_query(ADQL_KMAG)
    print(f"  {len(df_kmag):,} stars with Ks-band photometry")

    # Merge Ks magnitudes onto main table
    kmag_cols = ["WR", "Ksmag", "J-Ks", "H-Ks", "AKs", "KsMAGWR"]
    for col in kmag_cols:
        if col not in df_kmag.columns:
            kmag_cols.remove(col)
    if "WR" in df_kmag.columns:
        df_kmag_sub = df_kmag[kmag_cols].copy()
        df_kmag_sub["WR"] = df_kmag_sub["WR"].astype(str).str.strip()
        df["WR"] = df["WR"].astype(str).str.strip()
        df = df.merge(df_kmag_sub, on="WR", how="left")

    # Drop VizieR internal columns
    for col in ["recno", "More", "SimbadName"]:
        if col in df.columns:
            df = df.drop(columns=[col])

    # Rename columns to snake_case
    rename = {
        "WR": "wr_number",
        "f_WR": "wr_flag",
        "SpType": "spectral_type",
        "Name": "name",
        "RA_ICRS": "ra_deg",
        "DE_ICRS": "dec_deg",
        "plx": "parallax_mas",
        "e_plx": "parallax_error_mas",
        "Dist": "distance_kpc",
        "E_Dist": "distance_upper_error_kpc",
        "e_Dist": "distance_lower_error_kpc",
        "z": "galactic_height_pc",
        "E_z": "galactic_height_upper_error_pc",
        "e_z": "galactic_height_lower_error_pc",
        "Gmag": "gaia_g_mag",
        "BP-RP": "gaia_bp_rp",
        "Excess": "astrometric_excess_noise",
        "logL": "log_luminosity",
        "flag": "error_flag",
        "Ksmag": "ks_mag",
        "J-Ks": "j_ks_color",
        "H-Ks": "h_ks_color",
        "AKs": "ks_extinction",
        "KsMAGWR": "ks_abs_mag",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

    # Convert numerics
    numeric_cols = [
        "ra_deg", "dec_deg", "parallax_mas", "parallax_error_mas",
        "distance_kpc", "distance_upper_error_kpc", "distance_lower_error_kpc",
        "galactic_height_pc", "galactic_height_upper_error_pc",
        "galactic_height_lower_error_pc",
        "gaia_g_mag", "gaia_bp_rp", "astrometric_excess_noise", "log_luminosity",
        "ks_mag", "j_ks_color", "h_ks_color", "ks_extinction", "ks_abs_mag",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Clean string columns
    for col in ["wr_number", "wr_flag", "spectral_type", "name", "error_flag"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
            )

    # Derive WR subtype (WN, WC, WO) from spectral type
    def get_subtype(sp):
        if pd.isna(sp):
            return pd.NA
        sp = str(sp).strip()
        if sp.startswith("WO"):
            return "WO"
        if sp.startswith("WN"):
            return "WN"
        if sp.startswith("WC"):
            return "WC"
        return pd.NA
    df["wr_subtype"] = df["spectral_type"].apply(get_subtype)

    # Derive binary flag from spectral type (contains "+")
    df["is_binary"] = df["spectral_type"].str.contains(r"\+", na=False)

    # Sort by WR number
    df = df.sort_values("wr_number").reset_index(drop=True)

    # Validate — catalog has ~380 known Galactic WR stars
    check_dataset(df, "wolf-rayet", min_rows=350,
        expected_columns=["wr_number", "ra_deg", "dec_deg", "spectral_type"],
        critical_columns=["wr_number", "ra_deg", "dec_deg"])

    # Stats for README
    n_total = len(df)
    n_wn = int((df["wr_subtype"] == "WN").sum())
    n_wc = int((df["wr_subtype"] == "WC").sum())
    n_wo = int((df["wr_subtype"] == "WO").sum())
    n_binary = int(df["is_binary"].sum())
    n_with_distance = int(df["distance_kpc"].notna().sum())
    n_with_luminosity = int(df["log_luminosity"].notna().sum())
    median_dist = df["distance_kpc"].median()

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "wolf_rayet_stars.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        banner_file = download_banner("wolf-rayet", tmp)
        banner_md = banner_markdown("wolf-rayet", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Galactic Wolf-Rayet Stars"
language:
  - en
description: "Catalog of {n_total} Galactic Wolf-Rayet stars with Gaia DR2 astrometry, distances, spectral types, and photometry. Based on Rate & Crowther (2020, MNRAS 493, 1512), sourced via VizieR CDS Strasbourg."
task_categories:
  - tabular-classification
tags:
  - space
  - stars
  - wolf-rayet
  - massive-stars
  - astronomy
  - open-data
  - tabular-data
  - parquet
size_categories:
  - n<1K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/wolf_rayet_stars.parquet
    default: true
---

# Galactic Wolf-Rayet Stars
{banner_md}
*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

Catalog of **{n_total:,}** Galactic Wolf-Rayet stars — massive evolved stars with powerful stellar
winds and broad emission lines. Wolf-Rayet stars represent a brief but spectacular late stage in
the lives of the most massive stars (>25 solar masses), just before they explode as supernovae.

## Dataset description

Wolf-Rayet (WR) stars are among the hottest and most luminous stars known, with surface
temperatures of 30,000-200,000 K and luminosities up to a million times the Sun. Their spectra
are dominated by broad emission lines from helium, nitrogen (WN subtype), carbon (WC subtype),
or oxygen (WO subtype), produced by their extreme stellar winds losing mass at rates of
10^-5 solar masses per year.

This catalog is based on Rate & Crowther (2020), which combined the most complete census of
Galactic WR stars with Gaia DR2 parallaxes to derive distances, luminosities, and spatial
distribution. The dataset includes astrometric positions, spectral classifications, Gaia and
infrared photometry, and distance estimates.

Wolf-Rayet stars represent a fleeting but critical phase in massive star evolution. Stars born with initial masses above roughly 25 solar masses shed their hydrogen envelopes through powerful radiation-driven winds and episodic mass loss, exposing first the products of CNO-cycle hydrogen burning (nitrogen-rich WN phase) and then the products of helium burning (carbon- and oxygen-rich WC/WO phases). This evolutionary sequence — O star to WN to WC to core collapse — lasts only a few hundred thousand years, making WR stars extremely rare: fewer than 700 are known in the entire Milky Way. Their powerful winds, with terminal velocities of 1,000-3,000 km/s, inject enormous mechanical energy and chemically enriched material into the surrounding interstellar medium, sculpting ring nebulae and contributing to Galactic chemical evolution.

The WR population is a key diagnostic of massive star formation and evolution in galaxies. The ratio of WC to WN stars varies with metallicity — higher metallicity environments produce more WC stars because stronger winds strip the envelope more efficiently — making this ratio a test of stellar evolution models and a tracer of metallicity gradients across galactic disks. WR stars in binary systems are of particular interest as likely progenitors of double compact object mergers: a WR star paired with a neutron star or black hole may eventually produce the binary neutron star or black hole mergers detected by LIGO/Virgo. The catalog's combination of spectral classification, photometry, and Gaia-derived distances enables direct comparison of the observed Galactic WR population with predictions from population synthesis models, constraining mass-loss prescriptions and binary interaction physics.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `wr_number` | string | Standard WR catalog number (e.g. "WR 1", "WR 140") from the VIIth Catalog of Galactic Wolf-Rayet Stars; primary identifier used throughout the literature |
| `wr_flag` | string | Flag qualifying the WR designation (e.g. "a" for additions/updates after the main catalog); null for most entries |
| `spectral_type` | string | Full WR spectral classification (e.g. "WN4b", "WC7+O5-8", "WO2"); WN = nitrogen-sequence, WC = carbon-sequence, WO = oxygen-sequence; "+" indicates a spectroscopic binary companion |
| `wr_subtype` | string | Broad WR sequence derived from spectral_type: WN (exposing CNO-cycle products, WN2–WN11), WC (exposing He-burning products, WC4–WC9), WO (most evolved, WO1–WO4); null if spectral type is ambiguous |
| `is_binary` | bool | True if the spectral type contains "+", indicating a detected companion; WR+O binaries are important progenitors of compact object mergers |
| `name` | string | Alternative designation (usually HD number or other catalog ID); null for stars without a common alternative name |
| `ra_deg` | float64 | Right ascension, ICRS at Gaia DR2 reference epoch Ep=2015.5, in decimal degrees (0–360) |
| `dec_deg` | float64 | Declination, ICRS at Ep=2015.5, in decimal degrees (−90 to +90) |
| `parallax_mas` | float64 | Zero-point corrected Gaia DR2 parallax in milliarcseconds; many WR stars have negative or zero parallax due to faintness/crowding — distances are derived via a Bayesian method |
| `parallax_error_mas` | float64 | 1σ uncertainty on Gaia DR2 parallax (mas) |
| `distance_kpc` | float64 | Distance from the Sun in kpc, derived from Gaia DR2 parallax using a Bayesian prior; null for stars where Gaia astrometry is too poor; most Galactic WR stars lie within 10 kpc |
| `distance_upper_error_kpc` | float64 | Asymmetric upper 1σ uncertainty on distance (kpc); distances are often asymmetrically uncertain because negative parallaxes give poorly constrained distances |
| `distance_lower_error_kpc` | float64 | Asymmetric lower 1σ uncertainty on distance (kpc) |
| `galactic_height_pc` | float64 | Perpendicular distance from the Galactic mid-plane in pc, calculated from distance and Galactic latitude; WR stars trace the thin disk, typically |z| < 200 pc |
| `galactic_height_upper_error_pc` | float64 | Upper 1σ uncertainty on Galactic height (pc) |
| `galactic_height_lower_error_pc` | float64 | Lower 1σ uncertainty on Galactic height (pc) |
| `gaia_g_mag` | float64 | Gaia DR2 G-band (330–1050 nm) apparent magnitude; WR stars typically G = 8–18 mag; heavily reddened WR stars may be absent from Gaia |
| `gaia_bp_rp` | float64 | Gaia DR2 BP−RP colour index; WR stars are hot (blue) but often appear red due to interstellar extinction and emission lines; null where BP/RP photometry is unavailable |
| `astrometric_excess_noise` | float64 | Gaia DR2 astrometric excess noise in mas; elevated values indicate binarity, source confusion, or poor astrometric solution |
| `log_luminosity` | float64 | Log bolometric luminosity in solar units log(L/L☉); WR stars: 10⁵–10⁶ L☉ (log L ≈ 5.0–6.0); null for stars without a reliable distance or spectroscopic analysis |
| `error_flag` | string | Quality or error flag from Rate & Crowther (2020) indicating issues with the spectral classification, photometry, or distance; null for clean entries |
| `ks_mag` | float64 | 2MASS Ks-band (2.17 µm) apparent magnitude; near-infrared photometry less affected by interstellar extinction than optical |
| `j_ks_color` | float64 | 2MASS J−Ks colour index; traces near-infrared excess from free-free emission in WR winds; WC stars show strong IR excess |
| `h_ks_color` | float64 | 2MASS H−Ks colour index; additional near-infrared wind emission diagnostic |
| `ks_extinction` | float64 | Ks-band extinction A_Ks in magnitudes, derived from comparison of observed and intrinsic colours; used to compute absolute magnitudes |
| `ks_abs_mag` | float64 | Absolute Ks-band magnitude of the WR star, corrected for extinction; useful for luminosity comparisons independent of optical reddening; null where distance or extinction is unknown |

## Quick stats

- **{n_total:,}** Galactic Wolf-Rayet stars
- **{n_wn}** WN (nitrogen sequence), **{n_wc}** WC (carbon sequence), **{n_wo}** WO (oxygen sequence)
- **{n_binary}** spectroscopic binaries
- **{n_with_distance}** with Gaia-based distance estimates (median {median_dist:.1f} kpc)
- **{n_with_luminosity}** with luminosity measurements

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/wolf-rayet-stars", split="train")
df = ds.to_pandas()

# WN vs WC distribution
print(df["wr_subtype"].value_counts())

# Nearest WR stars
nearest = df.nsmallest(10, "distance_kpc")[["wr_number", "spectral_type", "distance_kpc", "name"]]
print(nearest)

# Luminosity distribution by subtype
import matplotlib.pyplot as plt
for st in ["WN", "WC"]:
    sub = df[df["wr_subtype"] == st].dropna(subset=["log_luminosity"])
    plt.hist(sub["log_luminosity"], bins=15, alpha=0.6, label=st)
plt.xlabel("log(L/L_sun)")
plt.ylabel("Count")
plt.legend()
plt.title("Wolf-Rayet Luminosity Distribution")
```

## Data source

Rate G., Crowther P.A. (2020), "Unlocking Galactic Wolf-Rayet stars with Gaia DR2",
*Monthly Notices of the Royal Astronomical Society*, 493, 1512.
Accessed via [VizieR](https://vizier.cds.unistra.fr/) (J/MNRAS/493/1512), CDS Strasbourg.

## Related datasets

- [ob-stars](https://huggingface.co/datasets/juliensimon/bright-star-catalog) -- OB stellar catalog
- [gcvs-variable-stars](https://huggingface.co/datasets/juliensimon/gcvs-variable-stars) -- General Catalogue of Variable Stars
- [pulsar-catalog](https://huggingface.co/datasets/juliensimon/pulsar-catalog) -- ATNF Pulsar Catalogue

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/wolf-rayet-stars) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{wolf_rayet_stars,
  author = {{Simon, Julien}},
  title = {{Galactic Wolf-Rayet Stars}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/wolf-rayet-stars}},
  note = {{Based on Rate & Crowther (2020, MNRAS 493, 1512) via VizieR CDS Strasbourg}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update Galactic Wolf-Rayet stars: {n_total:,} stars"
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
