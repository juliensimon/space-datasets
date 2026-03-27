#!/usr/bin/env python3
"""Fetch Geneva-Copenhagen Survey from VizieR and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from validate import check_dataset
from vizier_tap import vizier_query


HF_REPO = "juliensimon/geneva-copenhagen-stellar-survey"

ADQL = 'SELECT * FROM "V/130/gcs3"'


def main():
    print("Fetching Geneva-Copenhagen Survey from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} stars")

    # Rename columns — use variants for VizieR naming inconsistencies
    rename = {
        # Identifiers
        "HIP": "hip_id",
        "Name": "name",
        # Coordinates
        "RAJ2000": "ra_deg",
        "RAICRS": "ra_deg",
        "RA_ICRS": "ra_deg",
        "_RA": "ra_deg",
        "DEJ2000": "dec_deg",
        "DEICRS": "dec_deg",
        "DE_ICRS": "dec_deg",
        "_DE": "dec_deg",
        # Photometry
        "Vmag": "v_mag",
        "b-y": "b_y",
        "m1": "m1",
        "c1": "c1",
        "Beta": "h_beta",
        # Stellar parameters
        "Teff": "teff_k",
        "logg": "logg",
        "__Fe_H_": "fe_h",
        "_Fe_H_": "fe_h",
        "Fe_H": "fe_h",
        "[Fe/H]": "fe_h",
        # Ages
        "logAge": "log_age",
        "logAge50": "log_age",
        "logAgeL": "log_age_lower",
        "logAgeU": "log_age_upper",
        "Age": "age_gyr",
        # Kinematics
        "U": "u_vel_km_s",
        "V": "v_vel_km_s",
        "W": "w_vel_km_s",
        "e_U": "u_vel_err",
        "e_V": "v_vel_err",
        "e_W": "w_vel_err",
        # Orbital parameters
        "Rmean": "r_mean_kpc",
        "e": "eccentricity",
        "ecc": "eccentricity",
        "Zmax": "z_max_kpc",
        # Distance / parallax
        "Dist": "distance_pc",
        "plx": "parallax_mas",
        "Plx": "parallax_mas",
        "e_Plx": "parallax_err_mas",
        "e_plx": "parallax_err_mas",
        # Binary / variability flags
        "Bin": "binary_flag",
        "Var": "variable_flag",
    }
    # Only rename columns that actually exist
    rename_actual = {k: v for k, v in rename.items() if k in df.columns}
    df = df.rename(columns=rename_actual)

    # Convert numeric columns
    numeric_cols = [
        "ra_deg", "dec_deg", "v_mag", "b_y", "m1", "c1", "h_beta",
        "teff_k", "logg", "fe_h", "log_age", "log_age_lower", "log_age_upper",
        "age_gyr", "u_vel_km_s", "v_vel_km_s", "w_vel_km_s",
        "u_vel_err", "v_vel_err", "w_vel_err",
        "r_mean_kpc", "eccentricity", "z_max_kpc",
        "distance_pc", "parallax_mas", "parallax_err_mas",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Clean string columns
    string_cols = ["name", "binary_flag", "variable_flag"]
    for col in string_cols:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
            )

    # Convert HIP ID to integer where possible
    if "hip_id" in df.columns:
        df["hip_id"] = pd.to_numeric(df["hip_id"], errors="coerce").astype("Int64")

    # Sort by HIP ID
    if "hip_id" in df.columns:
        df = df.sort_values("hip_id").reset_index(drop=True)

    check_dataset(df, "geneva-copenhagen", min_rows=12_000,
        expected_columns=["ra_deg", "dec_deg"],
        critical_columns=["ra_deg", "dec_deg"])

    # Stats for README
    n_total = len(df)
    n_with_teff = int(df["teff_k"].notna().sum()) if "teff_k" in df.columns else 0
    n_with_feh = int(df["fe_h"].notna().sum()) if "fe_h" in df.columns else 0
    n_with_age = int(df["log_age"].notna().sum()) if "log_age" in df.columns else 0
    n_with_uvw = 0
    if all(c in df.columns for c in ["u_vel_km_s", "v_vel_km_s", "w_vel_km_s"]):
        n_with_uvw = int(df[["u_vel_km_s", "v_vel_km_s", "w_vel_km_s"]].notna().all(axis=1).sum())

    # Build column table for README from actual columns
    col_descriptions = {
        "hip_id": ("Int64", "Hipparcos identifier"),
        "name": ("string", "Star name"),
        "ra_deg": ("float64", "Right ascension J2000 (degrees)"),
        "dec_deg": ("float64", "Declination J2000 (degrees)"),
        "v_mag": ("float64", "Visual magnitude"),
        "b_y": ("float64", "Stromgren b-y color index"),
        "m1": ("float64", "Stromgren m1 metallicity index"),
        "c1": ("float64", "Stromgren c1 luminosity index"),
        "h_beta": ("float64", "H-beta index"),
        "teff_k": ("float64", "Effective temperature (K)"),
        "logg": ("float64", "Surface gravity log g (dex)"),
        "fe_h": ("float64", "Metallicity [Fe/H] (dex)"),
        "log_age": ("float64", "Log age (log yr), median"),
        "log_age_lower": ("float64", "Log age lower bound"),
        "log_age_upper": ("float64", "Log age upper bound"),
        "age_gyr": ("float64", "Age (Gyr)"),
        "u_vel_km_s": ("float64", "U space velocity (km/s, toward Galactic center)"),
        "v_vel_km_s": ("float64", "V space velocity (km/s, toward Galactic rotation)"),
        "w_vel_km_s": ("float64", "W space velocity (km/s, toward North Galactic Pole)"),
        "u_vel_err": ("float64", "U velocity uncertainty (km/s)"),
        "v_vel_err": ("float64", "V velocity uncertainty (km/s)"),
        "w_vel_err": ("float64", "W velocity uncertainty (km/s)"),
        "r_mean_kpc": ("float64", "Mean Galactocentric distance (kpc)"),
        "eccentricity": ("float64", "Orbital eccentricity"),
        "z_max_kpc": ("float64", "Maximum height above Galactic plane (kpc)"),
        "distance_pc": ("float64", "Distance (pc)"),
        "parallax_mas": ("float64", "Parallax (mas)"),
        "parallax_err_mas": ("float64", "Parallax uncertainty (mas)"),
        "binary_flag": ("string", "Binary star flag"),
        "variable_flag": ("string", "Variability flag"),
    }
    schema_rows = ""
    for col in df.columns:
        if col in col_descriptions:
            dtype, desc = col_descriptions[col]
            schema_rows += f"| `{col}` | {dtype} | {desc} |\n"
        elif col != "recno":
            schema_rows += f"| `{col}` | {df[col].dtype} | — |\n"

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "geneva_copenhagen_survey.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Geneva-Copenhagen Survey of Solar Neighbourhood"
language:
  - en
description: "Geneva-Copenhagen Survey of F and G dwarf stars in the solar neighbourhood: ages, metallicities, and Galactic kinematics for 16,682 stars. Sourced via VizieR CDS Strasbourg."
task_categories:
  - tabular-classification
tags:
  - space
  - stars
  - stellar-ages
  - kinematics
  - astronomy
  - open-data
  - tabular-data
size_categories:
  - 10K<n<100K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/geneva_copenhagen_survey.parquet
    default: true
---

# Geneva-Copenhagen Survey of Solar Neighbourhood

*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

The Geneva-Copenhagen Survey (GCS) is a comprehensive catalog of **{n_total:,}** F and G dwarf
stars in the solar neighbourhood, providing ages, metallicities, and full 3D space velocities.
It is one of the most widely used datasets for studying the chemical and dynamical evolution
of the Milky Way disk.

## Dataset description

The GCS combines Stromgren photometry, Hipparcos astrometry, and radial velocities to derive
fundamental stellar parameters. The third revision (Casagrande et al. 2011) provides improved
effective temperatures based on the infrared flux method and re-derived ages, metallicities,
and kinematics. This catalog is essential for studies of the age-metallicity relation,
Galactic chemical evolution, and stellar population kinematics in the solar neighbourhood.

## Schema

| Column | Type | Description |
|--------|------|-------------|
{schema_rows}
## Quick stats

- **{n_total:,}** solar neighbourhood F/G dwarf stars
- **{n_with_teff:,}** with effective temperature
- **{n_with_feh:,}** with metallicity [Fe/H]
- **{n_with_age:,}** with age estimate
- **{n_with_uvw:,}** with full UVW space velocities

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/geneva-copenhagen-stellar-survey", split="train")
df = ds.to_pandas()

# Age-metallicity relation
import matplotlib.pyplot as plt
valid = df.dropna(subset=["fe_h", "log_age"])
plt.scatter(valid["log_age"], valid["fe_h"], s=0.5, alpha=0.3)
plt.xlabel("Log Age (log yr)")
plt.ylabel("[Fe/H] (dex)")
plt.title("Age-Metallicity Relation (GCS)")

# Toomre diagram (kinematic populations)
valid = df.dropna(subset=["u_vel_km_s", "v_vel_km_s", "w_vel_km_s"])
v_total = (valid["u_vel_km_s"]**2 + valid["w_vel_km_s"]**2)**0.5
plt.figure()
plt.scatter(valid["v_vel_km_s"], v_total, s=0.5, alpha=0.3)
plt.xlabel("V (km/s)")
plt.ylabel("(U² + W²)^0.5 (km/s)")
plt.title("Toomre Diagram (GCS)")
```

## Data source

[Geneva-Copenhagen Survey III](https://ui.adsabs.harvard.edu/abs/2011A%26A...530A.138C/abstract)
(Casagrande L., Schoenrich R., Asplund M., et al., 2011, A&A, 530, A138),
accessed via [VizieR](https://vizier.cds.unistra.fr/), CDS Strasbourg.

## Related datasets

- [hipparcos-catalog](https://huggingface.co/datasets/juliensimon/hipparcos-catalog) -- Hipparcos astrometric catalog
- [gaia-dr3-nearby-stars](https://huggingface.co/datasets/juliensimon/gaia-dr3-nearby-stars) -- Gaia DR3 nearby stars
- [exoplanets](https://huggingface.co/datasets/juliensimon/exoplanets) -- NASA Exoplanet Archive

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/geneva-copenhagen-stellar-survey) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{geneva_copenhagen_survey,
  author = {{Simon, Julien}},
  title = {{Geneva-Copenhagen Survey of Solar Neighbourhood}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/geneva-copenhagen-stellar-survey}},
  note = {{Based on Casagrande et al. (2011, A&A 530 A138) via VizieR CDS Strasbourg}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Upload Geneva-Copenhagen Survey: {n_total:,} stars"
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
