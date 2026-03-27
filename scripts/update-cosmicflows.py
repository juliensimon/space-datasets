#!/usr/bin/env python3
"""Fetch Cosmicflows-4 galaxy distance catalog from VizieR and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from validate import check_dataset
from vizier_tap import vizier_query


HF_REPO = "juliensimon/cosmicflows-galaxy-distances"

ADQL = """\
SELECT * FROM "J/ApJ/944/94/table2"\
"""


def main():
    print("Fetching Cosmicflows-4 from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} galaxy distances")

    # Rename columns to snake_case
    rename = {
        "PGC": "pgc",
        "1PGC": "pgc_primary",
        "T17": "morphological_type",
        "Vcmb": "velocity_cmb",
        "DM": "distance_modulus",
        "e_DM": "distance_modulus_err",
        "DMsnIa": "dm_sn_ia",
        "e_DMsnIa": "dm_sn_ia_err",
        "DMtf": "dm_tully_fisher",
        "e_DMtf": "dm_tully_fisher_err",
        "DMfp": "dm_fundamental_plane",
        "e_DMfp": "dm_fundamental_plane_err",
        "DMsbf": "dm_surface_brightness",
        "e_DMsbf": "dm_surface_brightness_err",
        "DMsnII": "dm_sn_ii",
        "e_DMsnII": "dm_sn_ii_err",
        "DMtrgb": "dm_trgb",
        "e_DMtrgb": "dm_trgb_err",
        "DMceph": "dm_cepheid",
        "e_DMceph": "dm_cepheid_err",
        "DMmas": "dm_maser",
        "e_DMmas": "dm_maser_err",
        "RAJ2000": "ra_deg",
        "DEJ2000": "dec_deg",
        "GLON": "glon_deg",
        "GLAT": "glat_deg",
        "SGL": "sgl_deg",
        "SGB": "sgb_deg",
        "CF3": "in_cf3",
    }
    # Apply only columns that exist (VizieR names can vary)
    rename = {k: v for k, v in rename.items() if k in df.columns}
    df = df.rename(columns=rename)

    # Drop recno helper column
    if "recno" in df.columns:
        df = df.drop(columns=["recno"])

    # Coerce numeric columns
    numeric_cols = [
        "pgc", "pgc_primary", "morphological_type", "velocity_cmb",
        "distance_modulus", "distance_modulus_err",
        "dm_sn_ia", "dm_sn_ia_err",
        "dm_tully_fisher", "dm_tully_fisher_err",
        "dm_fundamental_plane", "dm_fundamental_plane_err",
        "dm_surface_brightness", "dm_surface_brightness_err",
        "dm_sn_ii", "dm_sn_ii_err",
        "dm_trgb", "dm_trgb_err",
        "dm_cepheid", "dm_cepheid_err",
        "dm_maser", "dm_maser_err",
        "ra_deg", "dec_deg",
        "glon_deg", "glat_deg",
        "sgl_deg", "sgb_deg",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Convert in_cf3 flag to boolean
    if "in_cf3" in df.columns:
        df["in_cf3"] = pd.to_numeric(df["in_cf3"], errors="coerce").fillna(0).astype(int).astype(bool)

    # Derive distance in Mpc from distance modulus: d = 10^((DM - 25) / 5)
    if "distance_modulus" in df.columns:
        df["distance_mpc"] = np.round(10 ** ((df["distance_modulus"] - 25) / 5), 3)

    # Sort by PGC number
    if "pgc" in df.columns:
        df = df.sort_values("pgc").reset_index(drop=True)

    check_dataset(df, "cosmicflows", min_rows=40_000,
        expected_columns=["pgc", "ra_deg", "dec_deg", "distance_modulus", "velocity_cmb"],
        critical_columns=["pgc", "ra_deg", "dec_deg", "distance_modulus"])

    # Stats for README
    n_total = len(df)
    n_with_tf = int(df["dm_tully_fisher"].notna().sum()) if "dm_tully_fisher" in df.columns else 0
    n_with_snia = int(df["dm_sn_ia"].notna().sum()) if "dm_sn_ia" in df.columns else 0
    n_with_fp = int(df["dm_fundamental_plane"].notna().sum()) if "dm_fundamental_plane" in df.columns else 0
    n_with_trgb = int(df["dm_trgb"].notna().sum()) if "dm_trgb" in df.columns else 0
    n_with_ceph = int(df["dm_cepheid"].notna().sum()) if "dm_cepheid" in df.columns else 0
    n_in_cf3 = int(df["in_cf3"].sum()) if "in_cf3" in df.columns else 0
    median_dist = df["distance_mpc"].median() if "distance_mpc" in df.columns else 0

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "cosmicflows_galaxy_distances.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Cosmicflows-4 Galaxy Distances"
language:
  - en
description: "The Cosmicflows-4 catalog of galaxy distances: {n_total:,} distance measurements from 8 methods (Tully-Fisher, SNe Ia, fundamental plane, TRGB, Cepheids, masers, SNe II, SBF). Sourced via VizieR CDS Strasbourg."
task_categories:
  - tabular-classification
tags:
  - space
  - galaxies
  - distances
  - cosmology
  - astronomy
  - open-data
  - tabular-data
size_categories:
  - 10K<n<100K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/cosmicflows_galaxy_distances.parquet
    default: true
---

# Cosmicflows-4 Galaxy Distances

*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

The Cosmicflows-4 (CF4) catalog is the most comprehensive compilation of galaxy distances
ever assembled. Published by Tully et al. (2023), it contains **{n_total:,}** distance
measurements derived from eight independent methods, enabling studies of the cosmic
distance ladder, large-scale structure, and peculiar velocities of galaxies.

## Dataset description

Galaxy distances are fundamental to cosmology. Unlike redshifts, which mix Hubble flow
with peculiar velocities, direct distance measurements let us map the true 3D distribution
of matter. CF4 consolidates distances from Type Ia supernovae, the Tully-Fisher relation,
the fundamental plane, tip of the red giant branch (TRGB), Cepheid period-luminosity,
surface brightness fluctuations (SBF), Type II supernovae, and maser observations.

Each entry includes the PGC galaxy identifier, coordinates (equatorial, galactic,
supergalactic), CMB-frame velocity, a best-estimate distance modulus, and individual
distance moduli from each method where available.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `pgc` | int | PGC galaxy number |
| `pgc_primary` | int | Primary PGC number (for grouped galaxies) |
| `morphological_type` | float | Morphological type code (de Vaucouleurs T) |
| `velocity_cmb` | float | Velocity in CMB frame (km/s) |
| `distance_modulus` | float | Best-estimate distance modulus (mag) |
| `distance_modulus_err` | float | Uncertainty on distance modulus (mag) |
| `distance_mpc` | float | Distance in Mpc (derived from distance modulus) |
| `dm_sn_ia` | float | Distance modulus from Type Ia supernovae |
| `dm_sn_ia_err` | float | Uncertainty on SNe Ia distance modulus |
| `dm_tully_fisher` | float | Distance modulus from Tully-Fisher relation |
| `dm_tully_fisher_err` | float | Uncertainty on Tully-Fisher distance modulus |
| `dm_fundamental_plane` | float | Distance modulus from fundamental plane |
| `dm_fundamental_plane_err` | float | Uncertainty on fundamental plane DM |
| `dm_surface_brightness` | float | Distance modulus from surface brightness fluctuations |
| `dm_surface_brightness_err` | float | Uncertainty on SBF distance modulus |
| `dm_sn_ii` | float | Distance modulus from Type II supernovae |
| `dm_sn_ii_err` | float | Uncertainty on SNe II distance modulus |
| `dm_trgb` | float | Distance modulus from tip of red giant branch |
| `dm_trgb_err` | float | Uncertainty on TRGB distance modulus |
| `dm_cepheid` | float | Distance modulus from Cepheid variables |
| `dm_cepheid_err` | float | Uncertainty on Cepheid distance modulus |
| `dm_maser` | float | Distance modulus from maser observations |
| `dm_maser_err` | float | Uncertainty on maser distance modulus |
| `ra_deg` | float | Right ascension J2000 (degrees) |
| `dec_deg` | float | Declination J2000 (degrees) |
| `glon_deg` | float | Galactic longitude (degrees) |
| `glat_deg` | float | Galactic latitude (degrees) |
| `sgl_deg` | float | Supergalactic longitude (degrees) |
| `sgb_deg` | float | Supergalactic latitude (degrees) |
| `in_cf3` | bool | Present in Cosmicflows-3 catalog |

## Quick stats

- **{n_total:,}** galaxy distance measurements
- **{n_with_tf:,}** with Tully-Fisher distances
- **{n_with_fp:,}** with fundamental plane distances
- **{n_with_snia:,}** with Type Ia supernova distances
- **{n_with_trgb:,}** with TRGB distances
- **{n_with_ceph:,}** with Cepheid distances
- **{n_in_cf3:,}** also in Cosmicflows-3
- Median distance: **{median_dist:.1f} Mpc**

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/cosmicflows-galaxy-distances", split="train")
df = ds.to_pandas()

# Galaxies within 100 Mpc (local universe)
local = df[df["distance_mpc"] <= 100]
print(f"{{len(local):,}} galaxies within 100 Mpc")

# Galaxies with Cepheid-calibrated distances
cepheids = df[df["dm_cepheid"].notna()]
print(f"{{len(cepheids):,}} with Cepheid distances")

# Sky distribution in supergalactic coordinates
import matplotlib.pyplot as plt
plt.scatter(df["sgl_deg"], df["sgb_deg"], s=0.2, alpha=0.3, c=df["distance_mpc"],
            cmap="viridis", vmax=200)
plt.colorbar(label="Distance (Mpc)")
plt.xlabel("Supergalactic Longitude")
plt.ylabel("Supergalactic Latitude")
plt.title("Cosmicflows-4: Galaxy Distance Map")
```

## Data source

[Cosmicflows-4](https://vizier.cds.unistra.fr/viz-bin/VizieR?-source=J/ApJ/944/94)
(Tully R.B., Kourkchi E., Courtois H.M., et al., 2023, ApJ, 944, 94),
accessed via [VizieR](https://vizier.cds.unistra.fr/), CDS Strasbourg.

## Update schedule

Static dataset (fixed catalog release). No scheduled updates.

## Related datasets

- [messier-catalog](https://huggingface.co/datasets/juliensimon/messier-catalog) -- Messier deep-sky objects
- [ngc-ic-catalog](https://huggingface.co/datasets/juliensimon/ngc-ic-catalog) -- NGC/IC deep-sky catalog
- [exoplanet-catalog](https://huggingface.co/datasets/juliensimon/exoplanet-catalog) -- NASA Exoplanet Archive

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/cosmicflows-galaxy-distances) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{cosmicflows_galaxy_distances,
  author = {{Simon, Julien}},
  title = {{Cosmicflows-4 Galaxy Distances}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/cosmicflows-galaxy-distances}},
  note = {{Based on Cosmicflows-4 (Tully et al. 2023, ApJ, 944, 94) via VizieR CDS Strasbourg}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update Cosmicflows-4 galaxy distances: {n_total:,} galaxies"
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
