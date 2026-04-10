#!/usr/bin/env python3
"""Fetch Geneva-Copenhagen Survey from VizieR and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from dataset_images import banner_markdown, download_banner
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
        "hip_id": ("Int64", "Hipparcos catalog number; primary cross-identifier for GCS stars"),
        "name": ("string", "Common or HD designation where available; null for anonymous entries"),
        "ra_deg": ("float64", "Right ascension, ICRS J2000.0, in decimal degrees (0–360)"),
        "dec_deg": ("float64", "Declination, ICRS J2000.0, in decimal degrees (−90 to +90)"),
        "v_mag": ("float64", "Johnson V-band apparent magnitude; GCS stars span roughly V = 5–9 mag (all stars within ~300 pc)"),
        "b_y": ("float64", "Strömgren b−y photometric index; primary temperature indicator for FGK stars; range ~0.2–0.6 mag"),
        "m1": ("float64", "Strömgren m1 = (v−b)−(b−y) metallicity index; increases with metallicity; used to derive [Fe/H]"),
        "c1": ("float64", "Strömgren c1 = (u−v)−(v−b) luminosity/gravity index; separates main-sequence from evolved stars"),
        "h_beta": ("float64", "Strömgren Hβ photometric index; temperature indicator for A–G stars; range ~2.5–2.7"),
        "teff_k": ("float64", "Effective temperature in Kelvin, derived from Strömgren photometry via infrared flux method calibration (Casagrande 2011); FGK range 4000–7500 K; typical uncertainty ~100 K; null if photometry insufficient"),
        "logg": ("float64", "Log surface gravity in cgs (log cm/s²), from isochrone fitting; main sequence: 4.0–5.0, subgiants: 3.5–4.5; null if stellar parameters undetermined"),
        "fe_h": ("float64", "[Fe/H] iron abundance in dex relative to solar; solar neighbourhood range −1.5 to +0.5; typical uncertainty ~0.1 dex; null for ~5% of stars"),
        "log_age": ("float64", "Median log age in log(yr) from Bayesian isochrone fitting; e.g. log_age=9.7 ≈ 5 Gyr; uncertainty often 0.2–0.5 dex for field stars; null if age poorly constrained"),
        "log_age_lower": ("float64", "Lower 1σ bound on log age (log yr); null where age is unconstrained"),
        "log_age_upper": ("float64", "Upper 1σ bound on log age (log yr); null where age is unconstrained"),
        "age_gyr": ("float64", "Median stellar age in Gyr from isochrone fitting; typical uncertainty 30–50% for individual field stars; null if isochrone placement fails"),
        "u_vel_km_s": ("float64", "Galactocentric U space velocity in km/s (positive toward Galactic centre); thin disk: |U| < 40 km/s; thick disk/halo stars reach |U| > 100 km/s"),
        "v_vel_km_s": ("float64", "Galactocentric V space velocity in km/s (positive in direction of Galactic rotation); thin disk near −20 km/s (asymmetric drift); halo stars strongly negative"),
        "w_vel_km_s": ("float64", "Galactocentric W space velocity in km/s (positive toward North Galactic Pole); thin disk: |W| < 25 km/s"),
        "u_vel_err": ("float64", "1σ uncertainty on U velocity (km/s)"),
        "v_vel_err": ("float64", "1σ uncertainty on V velocity (km/s)"),
        "w_vel_err": ("float64", "1σ uncertainty on W velocity (km/s)"),
        "r_mean_kpc": ("float64", "Time-averaged Galactocentric distance of the stellar orbit in kpc; all GCS stars orbit near 8 kpc"),
        "eccentricity": ("float64", "Orbital eccentricity (0 = circular); thin disk: e < 0.2; thick disk: e ~ 0.3–0.5; halo: e > 0.5"),
        "z_max_kpc": ("float64", "Maximum height above the Galactic plane reached during the orbit (kpc); thin disk < 0.3 kpc; thick disk 0.3–3 kpc"),
        "distance_pc": ("float64", "Hipparcos parallax-based distance in parsecs; all GCS stars within ~300 pc of the Sun"),
        "parallax_mas": ("float64", "Hipparcos parallax in milliarcseconds; typical precision 1–2 mas for these nearby stars"),
        "parallax_err_mas": ("float64", "1σ uncertainty on Hipparcos parallax (mas)"),
        "binary_flag": ("string", "Binary star flag from the catalog — encodes known or suspected multiplicity; null if no binary information"),
        "variable_flag": ("string", "Photometric variability flag; null if variability not detected or not assessed"),
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

        banner_file = download_banner("geneva-copenhagen", tmp)
        banner_md = banner_markdown("geneva-copenhagen", banner_file)

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
  - parquet
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
{banner_md}
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

The GCS is unique among stellar surveys in providing reliable individual stellar ages for a large, volume-complete sample of solar-type stars. Age determination in stellar astrophysics is notoriously difficult -- unlike temperature and metallicity, age cannot be directly measured from a spectrum. The GCS derives ages by placing each star on theoretical isochrones in the HR diagram, using Stromgren photometric indices (b-y, m1, c1, and H-beta) to determine effective temperatures and luminosities with sufficient precision to constrain evolutionary states. The third revision by Casagrande et al. (2011) improved the temperature scale using the infrared flux method calibrated against interferometric angular diameters, significantly reducing systematic errors in the derived ages and metallicities.

The full three-dimensional space velocities (U, V, W) in the GCS are computed from Hipparcos proper motions, trigonometric parallaxes, and ground-based radial velocities. These velocities enable kinematic decomposition of the solar neighborhood into thin disk, thick disk, and halo populations using Toomre diagrams and orbital parameters (eccentricity, maximum height above the Galactic plane, mean Galactocentric radius). The catalog has been central to establishing the age-velocity dispersion relation, which shows that older stellar populations have progressively larger random velocities -- evidence for dynamical heating of the Galactic disk by molecular clouds, spiral arms, and satellite galaxy interactions over billions of years.

The GCS remains a benchmark dataset for testing Galactic chemical evolution models because it provides the age-metallicity relation (AMR) for a well-defined stellar sample. The observed scatter in the AMR at any given age constrains the efficiency of radial mixing (churning) in the Galactic disk and the homogeneity of the interstellar medium from which successive generations of stars formed.

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
- [gaia-dr3-nearby-stars](https://huggingface.co/datasets/juliensimon/cns5-nearby-stars) -- Gaia DR3 nearby stars
- [exoplanets](https://huggingface.co/datasets/juliensimon/nasa-exoplanets) -- NASA Exoplanet Archive

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
