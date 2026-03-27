#!/usr/bin/env python3
"""Fetch HECATE (Heraklion Extragalactic Catalogue) from VizieR and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from validate import check_dataset
from vizier_tap import vizier_query


HF_REPO = "juliensimon/hecate-nearby-galaxies"

ADQL = """\
SELECT * FROM "J/MNRAS/506/1896"\
"""


def main():
    print("Fetching HECATE from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} galaxies")

    # Rename columns to snake_case
    rename = {
        # Position
        "RAJ2000": "ra_deg",
        "RA_ICRS": "ra_deg",
        "RAICRS": "ra_deg",
        "DEJ2000": "dec_deg",
        "DE_ICRS": "dec_deg",
        "DEICRS": "dec_deg",
        # Identifiers
        "PGC": "pgc",
        "Name": "name",
        "objname": "name",
        # Distance
        "D": "distance_mpc",
        "Dist": "distance_mpc",
        "D_Mpc_": "distance_mpc",
        "e_D": "distance_mpc_err",
        "e_Dist": "distance_mpc_err",
        # Stellar mass
        "logM_": "log_stellar_mass",
        "logM*": "log_stellar_mass",
        "logMstar": "log_stellar_mass",
        "e_logM_": "log_stellar_mass_err",
        "e_logMstar": "log_stellar_mass_err",
        # Star formation rate
        "logSFR": "log_sfr",
        "e_logSFR": "log_sfr_err",
        # Metallicity
        "Z_": "metallicity",
        "12_logO_H_": "metallicity_12logoh",
        "Met": "metallicity",
        # Morphology
        "T": "morphological_type",
        "TT": "morphological_type",
        "t": "morphological_type",
        # Nuclear activity
        "Act": "activity_class",
        "AGN": "activity_class",
        # Magnitudes
        "Bmag": "b_mag",
        "BT": "b_mag",
        "BTmag": "b_mag",
        "Kmag": "k_mag",
        "Kt": "k_mag",
        "K2M": "k_mag",
        # HI mass
        "logMHI": "log_hi_mass",
        "e_logMHI": "log_hi_mass_err",
        # Group membership
        "Gr": "group_id",
        "Group": "group_id",
        # Radial velocity
        "cz": "radial_velocity",
        "RV": "radial_velocity",
        "HRV": "radial_velocity",
        # Size
        "R1": "r1_arcmin",
        "R2": "r2_arcmin",
        "a": "semimajor_arcmin",
        # Axis ratio / inclination
        "b_a": "axis_ratio",
        "i": "inclination_deg",
        # Galactic coordinates
        "GLON": "glon_deg",
        "GLAT": "glat_deg",
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

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "HECATE Nearby Galaxies"
language:
  - en
description: "HECATE (Heraklion Extragalactic Catalogue): {n_total:,} galaxies within 200 Mpc with stellar masses, star formation rates, metallicity, morphology, and nuclear activity. Sourced via VizieR CDS Strasbourg."
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

[HECATE](https://vizier.cds.unistra.fr/viz-bin/VizieR?-source=J/MNRAS/506/1896)
(Kovlakas K., Zezas A., Andrews J.J., et al., 2021, MNRAS, 506, 1896),
accessed via [VizieR](https://vizier.cds.unistra.fr/), CDS Strasbourg.

## Update schedule

Static dataset (fixed catalog release). No scheduled updates.

## Related datasets

- [cosmicflows-galaxy-distances](https://huggingface.co/datasets/juliensimon/cosmicflows-galaxy-distances) -- Cosmicflows-4 galaxy distances
- [messier-catalog](https://huggingface.co/datasets/juliensimon/messier-catalog) -- Messier deep-sky objects
- [ngc-ic-catalog](https://huggingface.co/datasets/juliensimon/ngc-ic-catalog) -- NGC/IC deep-sky catalog

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/hecate-nearby-galaxies) and share feedback in the Community tab!

## Citation

```bibtex
@dataset{{hecate_nearby_galaxies,
  author = {{Simon, Julien}},
  title = {{HECATE Nearby Galaxies}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/hecate-nearby-galaxies}},
  note = {{Based on HECATE (Kovlakas et al. 2021, MNRAS, 506, 1896) via VizieR CDS Strasbourg}}
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
