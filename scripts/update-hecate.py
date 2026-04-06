#!/usr/bin/env python3
"""Fetch HECATE (Heraklion Extragalactic Catalogue) and upload to HF.

Source: https://hecate.ia.forth.gr/ (Kovlakas et al. 2021, MNRAS, 506, 1896)
The catalog is not available on VizieR TAP, so we download the CSV directly.
"""

import io
import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

from dataset_images import banner_markdown, download_banner
from validate import check_dataset


HF_REPO = "juliensimon/hecate-nearby-galaxies"

HECATE_CSV_URL = "https://hecate.ia.forth.gr/assets/files/HECATE_v1.1.csv"


def main():
    print("Downloading HECATE v1.1 from hecate.ia.forth.gr...")
    resp = requests.get(HECATE_CSV_URL, timeout=180)
    resp.raise_for_status()
    print(f"  Downloaded {len(resp.content):,} bytes")

    df = pd.read_csv(io.StringIO(resp.text))
    print(f"  {len(df):,} galaxies, {len(df.columns)} columns")

    # Rename columns to snake_case (matching actual HECATE v1.1 column names)
    rename = {
        # Position
        "RA": "ra_deg",
        "DEC": "dec_deg",
        # Identifiers
        "PGC": "pgc",
        "OBJNAME": "name",
        "ID_NED": "id_ned",
        "ID_2MASS": "id_2mass",
        # Distance
        "D": "distance_mpc",
        "E_D": "distance_mpc_err",
        "NDIST": "n_distances",
        "DMETHOD": "distance_method",
        # Morphology
        "T": "morphological_type",
        "E_T": "morphological_type_err",
        "INCL": "inclination_deg",
        # Radial velocity
        "V": "radial_velocity",
        "E_V": "radial_velocity_err",
        "V_VIR": "radial_velocity_virgo",
        # Size
        "R1": "r1_arcmin",
        "R2": "r2_arcmin",
        "PA": "position_angle",
        # Photometry
        "BT": "b_mag",
        "E_BT": "b_mag_err",
        "J": "j_mag",
        "H": "h_mag",
        "K": "k_mag",
        "E_J": "j_mag_err",
        "E_H": "h_mag_err",
        "E_K": "k_mag_err",
        # Extinction
        "AG": "extinction_g",
        "AI": "extinction_i",
        # Luminosities
        "logL_TIR": "log_l_tir",
        "logL_FIR": "log_l_fir",
        "logL_K": "log_l_k",
        # Star formation rate
        "logSFR_HEC": "log_sfr",
        "FLAG_SFR_HEC": "log_sfr_flag",
        "logSFR_TIR": "log_sfr_tir",
        "logSFR_FIR": "log_sfr_fir",
        # Stellar mass
        "logM_HEC": "log_stellar_mass",
        "logM_GSW": "log_stellar_mass_gsw",
        # Metallicity
        "METAL": "metallicity",
        "FLAG_METAL": "metallicity_flag",
        # Nuclear activity
        "CLASS_SP": "spectral_class",
        "AGN_S17": "agn_satyapal17",
        "AGN_HEC": "activity_class",
        # ML ratio
        "ML_RATIO": "ml_ratio",
    }
    # Apply only columns that exist
    rename = {k: v for k, v in rename.items() if k in df.columns}
    df = df.rename(columns=rename)

    # Drop recno helper column
    if "recno" in df.columns:
        df = df.drop(columns=["recno"])

    # Coerce numeric columns
    numeric_cols = [
        "pgc", "ra_deg", "dec_deg",
        "distance_mpc", "distance_mpc_err",
        "log_stellar_mass", "log_stellar_mass_err",
        "log_sfr", "log_sfr_err",
        "metallicity", "metallicity_12logoh",
        "morphological_type",
        "b_mag", "k_mag",
        "log_hi_mass", "log_hi_mass_err",
        "group_id",
        "radial_velocity",
        "r1_arcmin", "r2_arcmin", "semimajor_arcmin",
        "axis_ratio", "inclination_deg",
        "glon_deg", "glat_deg",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Sort by PGC number if available, else by RA
    if "pgc" in df.columns:
        df = df.sort_values("pgc").reset_index(drop=True)
    elif "ra_deg" in df.columns:
        df = df.sort_values("ra_deg").reset_index(drop=True)

    check_dataset(df, "hecate", min_rows=150_000,
        expected_columns=["ra_deg", "dec_deg"],
        critical_columns=["ra_deg", "dec_deg"])

    # Stats for README
    n_total = len(df)
    n_with_mass = int(df["log_stellar_mass"].notna().sum()) if "log_stellar_mass" in df.columns else 0
    n_with_sfr = int(df["log_sfr"].notna().sum()) if "log_sfr" in df.columns else 0
    n_with_morph = int(df["morphological_type"].notna().sum()) if "morphological_type" in df.columns else 0
    n_with_hi = int(df["log_hi_mass"].notna().sum()) if "log_hi_mass" in df.columns else 0
    n_with_activity = int(df["activity_class"].notna().sum()) if "activity_class" in df.columns else 0
    median_dist = df["distance_mpc"].median() if "distance_mpc" in df.columns else 0

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "hecate_nearby_galaxies.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        banner_file = download_banner("hecate", tmp)
        banner_md = banner_markdown("hecate", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "HECATE Nearby Galaxies"
language:
  - en
description: "HECATE (Heraklion Extragalactic Catalogue): {n_total:,} galaxies within 200 Mpc with stellar masses, star formation rates, metallicity, morphology, and nuclear activity. Sourced from hecate.ia.forth.gr."
task_categories:
  - tabular-classification
tags:
  - space
  - galaxies
  - nearby-galaxies
  - stellar-mass
  - star-formation
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
        path: data/hecate_nearby_galaxies.parquet
    default: true
---

# HECATE Nearby Galaxies
{banner_md}
*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

The Heraklion Extragalactic Catalogue (HECATE) is a value-added catalog of **{n_total:,}**
galaxies within 200 Mpc, designed as a reference for multi-messenger astrophysics and the
study of the local universe. Published by Kovlakas et al. (2021, MNRAS, 506, 1896), HECATE
provides homogenised physical properties including stellar masses, star formation rates,
metallicities, morphological types, and nuclear activity classifications.

## Dataset description

HECATE aggregates data from HyperLEDA, 2MASS, IRAS, and other major surveys to provide
a uniform census of the nearby galaxy population. Each galaxy entry includes positional
data, distance estimates, photometry in multiple bands, and derived physical properties.
The catalog is particularly useful for identifying host galaxies of transient events
(gravitational waves, neutrinos, gamma-ray bursts) and for statistical studies of galaxy
properties in the local volume.

The local universe within 200 Mpc provides the highest-resolution view of the galaxy population and serves as the calibration anchor for cosmological studies at greater distances. HECATE is specifically optimized for this volume, drawing on the HyperLEDA database for homogenized distances and photometry, and augmenting it with infrared luminosities from IRAS, near-infrared magnitudes from 2MASS, and stellar masses derived from K-band mass-to-light ratios. The inclusion of nuclear activity classifications (Seyfert, LINER, HII, and composite) makes it possible to study how AGN prevalence varies with galaxy mass, morphology, and environment in a volume-complete sample.

A key motivation for HECATE is multi-messenger astrophysics. Gravitational-wave detectors such as LIGO and Virgo localize merging compact binaries to sky areas of tens to hundreds of square degrees, and identifying the host galaxy requires a comprehensive census of all galaxies within the relevant distance range. Similarly, high-energy neutrino events detected by IceCube and gamma-ray transients from Fermi and Swift require rapid cross-matching against known galaxy catalogs to identify electromagnetic counterparts. HECATE provides the galaxy stellar mass, star formation rate, and morphological type needed to rank candidate host galaxies by their likelihood of hosting different types of transient events.

The catalog also supports studies of galaxy scaling relations in the nearby universe, including the stellar mass--metallicity relation, the star formation main sequence, and the correlation between morphological type and gas content. With HI mass measurements available for a substantial fraction of entries, HECATE enables investigations of the cold gas reservoir and its relationship to star formation efficiency across the Hubble sequence.

## Quick stats

- **{n_total:,}** galaxies within 200 Mpc
- **{n_with_mass:,}** with stellar mass estimates
- **{n_with_sfr:,}** with star formation rates
- **{n_with_morph:,}** with morphological classifications
- **{n_with_hi:,}** with HI mass measurements
- **{n_with_activity:,}** with nuclear activity classifications
- Median distance: **{median_dist:.1f} Mpc**

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/hecate-nearby-galaxies", split="train")
df = ds.to_pandas()

# Massive galaxies (log stellar mass > 11)
massive = df[df["log_stellar_mass"] > 11]
print(f"{{len(massive):,}} massive galaxies")

# Star-forming galaxies within 50 Mpc
nearby_sf = df[(df["distance_mpc"] <= 50) & (df["log_sfr"].notna())]
print(f"{{len(nearby_sf):,}} nearby galaxies with SFR")

# Morphological type distribution
import matplotlib.pyplot as plt
df["morphological_type"].dropna().hist(bins=30)
plt.xlabel("Morphological T-type")
plt.ylabel("Count")
plt.title("HECATE Galaxy Morphology Distribution")
```

## Data source

[HECATE](https://hecate.ia.forth.gr/) v1.1
(Kovlakas K., Zezas A., Andrews J.J., et al., 2021, MNRAS, 506, 1896),
downloaded directly from the authors' website at the Institute of Astrophysics, FORTH.

## Update schedule

Static dataset (fixed catalog release). No scheduled updates.

## Related datasets

- [cosmicflows-galaxy-distances](https://huggingface.co/datasets/juliensimon/cosmicflows-galaxy-distances) -- Cosmicflows-4 galaxy distances
- [messier-catalog](https://huggingface.co/datasets/juliensimon/messier-catalog) -- Messier deep-sky objects
- [ngc-ic-catalog](https://huggingface.co/datasets/juliensimon/ngc-ic-catalog) -- NGC/IC deep-sky catalog

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Citation

```bibtex
@dataset{{hecate_nearby_galaxies,
  author = {{Simon, Julien}},
  title = {{HECATE Nearby Galaxies}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/hecate-nearby-galaxies}},
  note = {{Based on HECATE v1.1 (Kovlakas et al. 2021, MNRAS, 506, 1896) from hecate.ia.forth.gr}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update HECATE nearby galaxies: {n_total:,} galaxies"
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
