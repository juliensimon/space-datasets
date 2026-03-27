#!/usr/bin/env python3
"""Fetch Catalogue of Nearby Stars (CNS5) from VizieR and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from validate import check_dataset
from vizier_tap import vizier_query


HF_REPO = "juliensimon/cns5-nearby-stars"

ADQL = 'SELECT * FROM "J/A+A/670/A19/cns5"'


def main():
    print("Fetching CNS5 from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} nearby stars")

    # Rename columns to snake_case
    df = df.rename(columns={
        "CNS5": "cns5_id",
        "GJ": "gj_name",
        "Comp": "component",
        "NComp": "n_components",
        "P?": "problematic_flag",
        "GJp": "gj_primary",
        "GaiaDR3": "gaia_dr3_id",
        "HIP": "hip_id",
        "RAJ2000": "ra_deg",
        "DEJ2000": "dec_deg",
        "Epoch": "epoch",
        "r_pos": "ref_position",
        "plx": "parallax_mas",
        "e_plx": "parallax_error_mas",
        "r_plx": "ref_parallax",
        "pmRA": "pm_ra_mas_yr",
        "e_pmRA": "pm_ra_error",
        "pmDE": "pm_dec_mas_yr",
        "e_pmDE": "pm_dec_error",
        "r_pmRA": "ref_proper_motion",
        "RV": "radial_velocity_km_s",
        "e_RV": "radial_velocity_error",
        "r_RV": "ref_radial_velocity",
        "Gmag": "g_mag",
        "e_Gmag": "g_mag_error",
        "BPmag": "bp_mag",
        "e_BPmag": "bp_mag_error",
        "RPmag": "rp_mag",
        "e_RPmag": "rp_mag_error",
        "GHIPmag": "g_hip_mag",
        "e_GHIPmag": "g_hip_mag_error",
        "G-RPHIP": "g_rp_hip",
        "e_G-RPHIP": "g_rp_hip_error",
        "Gmagr": "g_mag_resulting",
        "e_Gmagr": "g_mag_resulting_error",
        "(G-RP)r": "g_rp_resulting",
        "e_(G-RP)r": "g_rp_resulting_error",
        "f_(G-RP)r": "g_rp_resulting_flag",
        "Jmag": "j_mag",
        "e_Jmag": "j_mag_error",
        "Hmag": "h_mag",
        "e_Hmag": "h_mag_error",
        "Ksmag": "ks_mag",
        "e_Ksmag": "ks_mag_error",
        "r_Jmag": "ref_2mass",
        "W1mag": "w1_mag",
        "e_W1mag": "w1_mag_error",
        "W2mag": "w2_mag",
        "e_W2mag": "w2_mag_error",
        "W3mag": "w3_mag",
        "e_W3mag": "w3_mag_error",
        "W4mag": "w4_mag",
        "e_W4mag": "w4_mag_error",
        "r_W1mag": "ref_wise",
        "SimbadName": "simbad_name",
    })

    # Drop recno (VizieR internal)
    df = df.drop(columns=["recno"], errors="ignore")

    # Convert numeric columns
    numeric_cols = [
        "cns5_id", "n_components", "problematic_flag",
        "gaia_dr3_id", "hip_id",
        "ra_deg", "dec_deg", "epoch",
        "parallax_mas", "parallax_error_mas",
        "pm_ra_mas_yr", "pm_ra_error", "pm_dec_mas_yr", "pm_dec_error",
        "radial_velocity_km_s", "radial_velocity_error",
        "g_mag", "g_mag_error", "bp_mag", "bp_mag_error",
        "rp_mag", "rp_mag_error",
        "g_hip_mag", "g_hip_mag_error",
        "g_rp_hip", "g_rp_hip_error",
        "g_mag_resulting", "g_mag_resulting_error",
        "g_rp_resulting", "g_rp_resulting_error",
        "g_rp_resulting_flag",
        "j_mag", "j_mag_error", "h_mag", "h_mag_error",
        "ks_mag", "ks_mag_error",
        "w1_mag", "w1_mag_error", "w2_mag", "w2_mag_error",
        "w3_mag", "w3_mag_error", "w4_mag", "w4_mag_error",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Clean string columns
    str_cols = [
        "gj_name", "component", "gj_primary",
        "ref_position", "ref_parallax", "ref_proper_motion",
        "ref_radial_velocity", "ref_2mass", "ref_wise",
        "simbad_name",
    ]
    for col in str_cols:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
            )

    # Compute distance in parsecs from parallax
    mask = df["parallax_mas"].notna() & (df["parallax_mas"] > 0)
    df["distance_pc"] = pd.NA
    df.loc[mask, "distance_pc"] = 1000.0 / df.loc[mask, "parallax_mas"]

    # Sort by CNS5 ID
    df = df.sort_values("cns5_id").reset_index(drop=True)

    check_dataset(df, "cns5", min_rows=4_000,
        expected_columns=["cns5_id", "ra_deg", "dec_deg", "parallax_mas", "distance_pc"],
        critical_columns=["cns5_id", "ra_deg", "dec_deg"])

    # Stats for README
    n_total = len(df)
    n_with_rv = int(df["radial_velocity_km_s"].notna().sum())
    n_with_simbad = int(df["simbad_name"].notna().sum())
    n_with_gaia = int(df["gaia_dr3_id"].notna().sum())
    median_dist = df["distance_pc"].median()
    min_dist = df["distance_pc"].min()

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "cns5_nearby_stars.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Catalogue of Nearby Stars (CNS5)"
language:
  - en
description: "The fifth edition of the Catalogue of Nearby Stars within 25 parsecs (Golovin+ 2023), with astrometry, photometry, and cross-identifiers. Sourced via VizieR CDS Strasbourg."
task_categories:
  - tabular-classification
tags:
  - space
  - stars
  - solar-neighborhood
  - nearby-stars
  - astronomy
  - open-data
  - tabular-data
size_categories:
  - 1K<n<10K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/cns5_nearby_stars.parquet
    default: true
---

# Catalogue of Nearby Stars (CNS5)

*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

The fifth edition of the Catalogue of Nearby Stars (CNS5) is a comprehensive census of **{n_total:,}**
stellar systems within 25 parsecs of the Sun. It provides astrometric, photometric, and
cross-identification data for the solar neighborhood, compiled from Gaia EDR3, Hipparcos, 2MASS,
and WISE.

## Dataset description

Understanding the stellar population of the solar neighborhood is fundamental to astrophysics.
The CNS5 (Golovin, Reffert, Just, Jordan, Vani & Jahreiss 2023, A&A 670, A19) extends the classic
Gliese & Jahreiss nearby-star catalogs using Gaia EDR3 parallaxes as the primary distance
indicator. It includes all known stars with trigonometric parallax placing them within 25 pc,
with multi-band photometry (Gaia G/BP/RP, 2MASS JHKs, WISE W1-W4), proper motions, and radial
velocities where available.

Each entry includes coordinates, parallax (and derived distance), proper motion, radial velocity,
Gaia and infrared magnitudes, and cross-identifiers (Gliese-Jahreiss, Hipparcos, Gaia DR3, SIMBAD).

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `cns5_id` | int | CNS5 designation number |
| `gj_name` | string | Gliese-Jahreiss identifier |
| `component` | string | Component suffix for binary/multiple systems |
| `n_components` | float64 | Number of components in the system |
| `problematic_flag` | float64 | Problematic entry flag |
| `gj_primary` | string | GJ number of the primary component |
| `gaia_dr3_id` | int64 | Gaia EDR3 source identifier |
| `hip_id` | float64 | Hipparcos identifier |
| `ra_deg` | float64 | Right ascension J2000 (degrees) |
| `dec_deg` | float64 | Declination J2000 (degrees) |
| `epoch` | float64 | Reference epoch for coordinates |
| `parallax_mas` | float64 | Trigonometric parallax (mas) |
| `parallax_error_mas` | float64 | Parallax uncertainty (mas) |
| `pm_ra_mas_yr` | float64 | Proper motion in RA (mas/yr) |
| `pm_dec_mas_yr` | float64 | Proper motion in Dec (mas/yr) |
| `radial_velocity_km_s` | float64 | Radial velocity (km/s) |
| `g_mag` | float64 | Gaia G magnitude |
| `bp_mag` | float64 | Gaia BP magnitude |
| `rp_mag` | float64 | Gaia RP magnitude |
| `j_mag` | float64 | 2MASS J magnitude |
| `h_mag` | float64 | 2MASS H magnitude |
| `ks_mag` | float64 | 2MASS Ks magnitude |
| `w1_mag` | float64 | WISE W1 magnitude |
| `w2_mag` | float64 | WISE W2 magnitude |
| `w3_mag` | float64 | WISE W3 magnitude |
| `w4_mag` | float64 | WISE W4 magnitude |
| `distance_pc` | float64 | Distance in parsecs (derived from parallax) |
| `simbad_name` | string | SIMBAD object name |

*Plus error columns and reference columns — {len(df.columns)} columns total.*

## Quick stats

- **{n_total:,}** stellar entries within 25 pc
- **{n_with_gaia:,}** with Gaia DR3 cross-match
- **{n_with_rv:,}** with radial velocity
- **{n_with_simbad:,}** with SIMBAD identification
- Median distance: **{median_dist:.1f} pc**, nearest: **{min_dist:.2f} pc**

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/cns5-nearby-stars", split="train")
df = ds.to_pandas()

# Stars within 5 parsecs (the immediate solar neighborhood)
nearby = df[df["distance_pc"] <= 5].sort_values("distance_pc")
print(f"{{len(nearby)}} stars within 5 pc")
print(nearby[["simbad_name", "distance_pc", "g_mag"]].head(10))

# Distribution of stellar distances
import matplotlib.pyplot as plt
df["distance_pc"].dropna().hist(bins=50)
plt.xlabel("Distance (pc)")
plt.ylabel("Count")
plt.title("CNS5: Distribution of Nearby Star Distances")

# Color-magnitude diagram
valid = df.dropna(subset=["bp_mag", "rp_mag", "g_mag", "parallax_mas"])
valid["abs_g"] = valid["g_mag"] + 5 * (1 + valid["parallax_mas"].apply(lambda p: __import__('math').log10(p / 1000)))
valid["bp_rp"] = valid["bp_mag"] - valid["rp_mag"]
plt.scatter(valid["bp_rp"], valid["abs_g"], s=0.3, alpha=0.4)
plt.gca().invert_yaxis()
plt.xlabel("BP - RP (mag)")
plt.ylabel("Absolute G (mag)")
plt.title("CNS5 HR Diagram")
```

## Data source

[Catalogue of Nearby Stars (CNS5)](https://vizier.cds.unistra.fr/viz-bin/VizieR?-source=J/A+A/670/A19)
(Golovin A., Reffert S., Just A., Jordan S., Vani A., Jahreiss H., 2023, A&A, 670, A19),
accessed via [VizieR](https://vizier.cds.unistra.fr/), CDS Strasbourg.

## Related datasets

- [hipparcos](https://huggingface.co/datasets/juliensimon/hipparcos) -- Hipparcos main catalog
- [brown-dwarfs](https://huggingface.co/datasets/juliensimon/brown-dwarfs) -- Brown dwarfs within 40 pc
- [open-clusters](https://huggingface.co/datasets/juliensimon/open-clusters) -- Open star clusters

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/cns5-nearby-stars) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{cns5_nearby_stars,
  author = {{Simon, Julien}},
  title = {{Catalogue of Nearby Stars (CNS5)}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/cns5-nearby-stars}},
  note = {{Based on CNS5 (Golovin et al. 2023, A&A 670, A19) via VizieR CDS Strasbourg}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Upload CNS5 nearby stars: {n_total:,} entries"
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
