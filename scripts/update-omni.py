#!/usr/bin/env python3
"""Fetch OMNI hourly merged solar wind & geomagnetic index data from NASA GSFC and upload to HF."""

import os
import subprocess
import tempfile
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset

HF_REPO = "juliensimon/omni-solar-wind-parameters"
DATA_URL = "https://spdf.gsfc.nasa.gov/pub/data/omni/low_res_omni/omni2_all_years.dat"

# ── Column definitions (55 columns, fixed-width whitespace-delimited) ────────
COLUMNS = [
    "year",                          # 1
    "day_of_year",                   # 2
    "hour",                          # 3
    "bartels_rotation_number",       # 4
    "imf_spacecraft_id",             # 5
    "sw_plasma_spacecraft_id",       # 6
    "n_imf_points",                  # 7
    "n_plasma_points",               # 8
    "b_magnitude_avg_nt",            # 9  |B| 1/N SUM |B|
    "b_magnitude_vector_nt",         # 10 magnitude of avg field vector
    "b_lat_angle_gse_deg",           # 11
    "b_lon_angle_gse_deg",           # 12
    "bx_gse_nt",                     # 13 Bx GSE (= Bx GSM)
    "by_gse_nt",                     # 14
    "bz_gse_nt",                     # 15
    "by_gsm_nt",                     # 16
    "bz_gsm_nt",                     # 17
    "sigma_b_magnitude_nt",          # 18
    "sigma_b_vector_nt",             # 19
    "sigma_bx_nt",                   # 20
    "sigma_by_nt",                   # 21
    "sigma_bz_nt",                   # 22
    "proton_temperature_k",          # 23
    "proton_density_cm3",            # 24
    "flow_speed_kms",                # 25
    "flow_lon_angle_deg",            # 26
    "flow_lat_angle_deg",            # 27
    "alpha_proton_ratio",            # 28
    "flow_pressure_npa",             # 29
    "sigma_t_k",                     # 30
    "sigma_n_cm3",                   # 31
    "sigma_v_kms",                   # 32
    "sigma_phi_v_deg",               # 33
    "sigma_theta_v_deg",             # 34
    "sigma_alpha_proton_ratio",      # 35
    "electric_field_mvpm",           # 36
    "plasma_beta",                   # 37
    "alfven_mach_number",            # 38
    "kp_index",                      # 39
    "sunspot_number",                # 40
    "dst_index_nt",                  # 41
    "ae_index_nt",                   # 42
    "proton_flux_gt1mev",            # 43
    "proton_flux_gt2mev",            # 44
    "proton_flux_gt4mev",            # 45
    "proton_flux_gt10mev",           # 46
    "proton_flux_gt30mev",           # 47
    "proton_flux_gt60mev",           # 48
    "flux_flag",                     # 49
    "ap_index_nt",                   # 50
    "f107_index_sfu",                # 51
    "pc_n_index",                    # 52
    "al_index_nt",                   # 53
    "au_index_nt",                   # 54
    "magnetosonic_mach_number",      # 55
]

# Fill values per column — values at or above these thresholds are NaN
FILL_VALUES = {
    "bartels_rotation_number": 9999,
    "imf_spacecraft_id": 99,
    "sw_plasma_spacecraft_id": 99,
    "n_imf_points": 999,
    "n_plasma_points": 999,
    "b_magnitude_avg_nt": 999.9,
    "b_magnitude_vector_nt": 999.9,
    "b_lat_angle_gse_deg": 999.9,
    "b_lon_angle_gse_deg": 999.9,
    "bx_gse_nt": 999.9,
    "by_gse_nt": 999.9,
    "bz_gse_nt": 999.9,
    "by_gsm_nt": 999.9,
    "bz_gsm_nt": 999.9,
    "sigma_b_magnitude_nt": 999.9,
    "sigma_b_vector_nt": 999.9,
    "sigma_bx_nt": 999.9,
    "sigma_by_nt": 999.9,
    "sigma_bz_nt": 999.9,
    "proton_temperature_k": 9999999.0,
    "proton_density_cm3": 999.9,
    "flow_speed_kms": 9999.0,
    "flow_lon_angle_deg": 999.9,
    "flow_lat_angle_deg": 999.9,
    "alpha_proton_ratio": 9.999,
    "flow_pressure_npa": 99.99,
    "sigma_t_k": 9999999.0,
    "sigma_n_cm3": 999.9,
    "sigma_v_kms": 9999.0,
    "sigma_phi_v_deg": 999.9,
    "sigma_theta_v_deg": 999.9,
    "sigma_alpha_proton_ratio": 9.999,
    "electric_field_mvpm": 999.99,
    "plasma_beta": 999.99,
    "alfven_mach_number": 999.9,
    "kp_index": 99,
    "sunspot_number": 999,
    "dst_index_nt": 99999,
    "ae_index_nt": 9999,
    "proton_flux_gt1mev": 999999.99,
    "proton_flux_gt2mev": 99999.99,
    "proton_flux_gt4mev": 99999.99,
    "proton_flux_gt10mev": 99999.99,
    "proton_flux_gt30mev": 99999.99,
    "proton_flux_gt60mev": 99999.99,
    "ap_index_nt": 999,
    "f107_index_sfu": 999.9,
    "pc_n_index": 999.9,
    "al_index_nt": 99999,
    "au_index_nt": 99999,
    "magnetosonic_mach_number": 99.9,
}

# Columns to drop from final output (metadata, not useful for analysis)
DROP_COLUMNS = [
    "imf_spacecraft_id",
    "sw_plasma_spacecraft_id",
    "n_imf_points",
    "n_plasma_points",
    "flux_flag",
]


def main():
    print("Fetching OMNI hourly data from NASA GSFC...")
    resp = requests.get(DATA_URL, timeout=300)
    resp.raise_for_status()
    print(f"  Downloaded {len(resp.content) / 1024 / 1024:.1f} MB")

    # Parse fixed-width whitespace-delimited ASCII
    df = pd.read_csv(
        StringIO(resp.text),
        sep=r"\s+",
        header=None,
        names=COLUMNS,
        dtype=float,
    )
    print(f"  {len(df):,} raw rows ({int(df['year'].min())}-{int(df['year'].max())})")

    # Create datetime from year + day_of_year + hour
    df["datetime"] = pd.to_datetime(
        df["year"].astype(int).astype(str) + "-" +
        df["day_of_year"].astype(int).astype(str) + "-" +
        df["hour"].astype(int).astype(str),
        format="%Y-%j-%H",
        errors="coerce",
    )

    # Replace fill values with NaN
    for col, fill in FILL_VALUES.items():
        if col in df.columns:
            df.loc[df[col] >= fill, col] = pd.NA

    # Drop raw time columns and metadata columns
    df = df.drop(columns=["year", "day_of_year", "hour"] + DROP_COLUMNS, errors="ignore")

    # Move datetime to first column
    cols = ["datetime"] + [c for c in df.columns if c != "datetime"]
    df = df[cols]

    # Drop rows with no datetime
    df = df.dropna(subset=["datetime"])

    # Ensure numeric types
    for col in df.columns:
        if col != "datetime":
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Sort by datetime
    df = df.sort_values("datetime").reset_index(drop=True)

    n_total = len(df)
    date_min = df["datetime"].min().strftime("%Y-%m-%d")
    date_max = df["datetime"].max().strftime("%Y-%m-%d")
    print(f"  {n_total:,} rows after cleanup ({date_min} to {date_max})")

    # Coverage stats
    for col in ["b_magnitude_avg_nt", "bz_gsm_nt", "flow_speed_kms", "proton_density_cm3",
                 "dst_index_nt", "kp_index", "plasma_beta", "alfven_mach_number"]:
        pct = (1 - df[col].isna().mean()) * 100
        print(f"    {col}: {pct:.1f}% coverage")

    # Validation
    check_dataset(
        df, "omni",
        min_rows=400_000,
        expected_columns=[
            "datetime", "b_magnitude_avg_nt", "bx_gse_nt", "by_gse_nt", "bz_gse_nt",
            "by_gsm_nt", "bz_gsm_nt", "flow_speed_kms", "proton_density_cm3",
            "proton_temperature_k", "flow_pressure_npa", "plasma_beta",
            "alfven_mach_number", "magnetosonic_mach_number",
            "kp_index", "dst_index_nt", "ae_index_nt", "ap_index_nt",
            "f107_index_sfu", "sunspot_number",
        ],
        critical_columns=["datetime"],
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "omni_solar_wind_parameters.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "OMNI Hourly Solar Wind Parameters"
language:
  - en
description: "Merged hourly solar wind magnetic field, plasma parameters, and geomagnetic indices from NASA GSFC OMNI dataset. Near-Earth data from multiple spacecraft, 1963 to present."
task_categories:
  - tabular-regression
  - time-series-forecasting
tags:
  - space
  - solar-wind
  - imf
  - magnetic-field
  - space-weather
  - nasa
  - open-data
  - tabular-data
  - parquet
size_categories:
  - 100K<n<1M
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/omni_solar_wind_parameters.parquet
    default: true
---

# OMNI Hourly Solar Wind Parameters

*Part of the [Space Weather Datasets](https://huggingface.co/collections/juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70) collection on Hugging Face.*

![Update OMNI](https://github.com/juliensimon/space-datasets/actions/workflows/update-omni.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.omni&label=updated&color=brightgreen)

Merged hourly near-Earth solar wind magnetic field, plasma, and energetic particle parameters combined
with geomagnetic and solar activity indices. Currently **{n_total:,}** hourly records spanning
**{date_min}** to **{date_max}**. The master bridge dataset for space weather analysis — it
time-aligns IMF, solar wind, and geomagnetic response in a single file.

## Dataset description

The OMNI dataset from NASA's Goddard Space Flight Center merges solar wind observations from
multiple spacecraft (IMP 8, ACE, Wind, DSCOVR, and others) into a single consistent hourly time
series at Earth's bow shock nose. It combines interplanetary magnetic field (IMF) components,
solar wind plasma parameters, energetic particle fluxes, and geomagnetic activity indices —
making it the standard reference dataset for space weather correlation studies.

Key parameter groups:
- **IMF**: field magnitude, Bx/By/Bz in GSE and GSM coordinates, field direction angles
- **Solar wind plasma**: proton density, temperature, bulk flow speed and direction, alpha/proton ratio
- **Derived quantities**: flow pressure, plasma beta, electric field, Alfven and magnetosonic Mach numbers
- **Geomagnetic indices**: Kp, Dst, AE, AL, AU, ap, PC(N)
- **Solar indices**: F10.7 radio flux, sunspot number
- **Energetic particles**: proton fluxes at >1, >2, >4, >10, >30, >60 MeV

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `datetime` | datetime | Observation timestamp (UTC, hourly cadence) |
| `bartels_rotation_number` | float64 | Bartels solar rotation number |
| `b_magnitude_avg_nt` | float64 | Average IMF magnitude 1/N SUM |B| (nT) |
| `b_magnitude_vector_nt` | float64 | Magnitude of average field vector (nT) |
| `b_lat_angle_gse_deg` | float64 | Latitude angle of average field vector, GSE (deg) |
| `b_lon_angle_gse_deg` | float64 | Longitude angle of average field vector, GSE (deg) |
| `bx_gse_nt` | float64 | IMF Bx component, GSE/GSM (nT) |
| `by_gse_nt` | float64 | IMF By component, GSE (nT) |
| `bz_gse_nt` | float64 | IMF Bz component, GSE (nT) |
| `by_gsm_nt` | float64 | IMF By component, GSM (nT) |
| `bz_gsm_nt` | float64 | IMF Bz component, GSM (nT) |
| `sigma_b_magnitude_nt` | float64 | RMS std dev of |B| (nT) |
| `sigma_b_vector_nt` | float64 | RMS std dev of field vector (nT) |
| `sigma_bx_nt` | float64 | RMS std dev of Bx, GSE (nT) |
| `sigma_by_nt` | float64 | RMS std dev of By, GSE (nT) |
| `sigma_bz_nt` | float64 | RMS std dev of Bz, GSE (nT) |
| `proton_temperature_k` | float64 | Proton temperature (K) |
| `proton_density_cm3` | float64 | Proton number density (N/cm^3) |
| `flow_speed_kms` | float64 | Plasma bulk flow speed (km/s) |
| `flow_lon_angle_deg` | float64 | Flow longitude angle, quasi-GSE (deg) |
| `flow_lat_angle_deg` | float64 | Flow latitude angle, GSE (deg) |
| `alpha_proton_ratio` | float64 | Alpha-to-proton density ratio Na/Np |
| `flow_pressure_npa` | float64 | Flow (ram) pressure (nPa) |
| `sigma_t_k` | float64 | Sigma of proton temperature (K) |
| `sigma_n_cm3` | float64 | Sigma of proton density (N/cm^3) |
| `sigma_v_kms` | float64 | Sigma of flow speed (km/s) |
| `sigma_phi_v_deg` | float64 | Sigma of flow longitude (deg) |
| `sigma_theta_v_deg` | float64 | Sigma of flow latitude (deg) |
| `sigma_alpha_proton_ratio` | float64 | Sigma of Na/Np |
| `electric_field_mvpm` | float64 | Electric field -V*Bz (mV/m) |
| `plasma_beta` | float64 | Plasma beta (ratio of thermal to magnetic pressure) |
| `alfven_mach_number` | float64 | Alfven Mach number |
| `kp_index` | float64 | Planetary geomagnetic Kp index (0-90 scale, multiply by 0.1) |
| `sunspot_number` | float64 | International sunspot number (v2) |
| `dst_index_nt` | float64 | Disturbance Storm Time index (nT) |
| `ae_index_nt` | float64 | Auroral Electrojet AE index (nT) |
| `proton_flux_gt1mev` | float64 | Energetic proton flux >1 MeV (1/cm^2 s sr) |
| `proton_flux_gt2mev` | float64 | Energetic proton flux >2 MeV |
| `proton_flux_gt4mev` | float64 | Energetic proton flux >4 MeV |
| `proton_flux_gt10mev` | float64 | Energetic proton flux >10 MeV |
| `proton_flux_gt30mev` | float64 | Energetic proton flux >30 MeV |
| `proton_flux_gt60mev` | float64 | Energetic proton flux >60 MeV |
| `ap_index_nt` | float64 | Geomagnetic ap index (nT) |
| `f107_index_sfu` | float64 | F10.7 solar radio flux (SFU) |
| `pc_n_index` | float64 | Polar Cap (North) PC(N) index |
| `al_index_nt` | float64 | Auroral Electrojet AL index (nT) |
| `au_index_nt` | float64 | Auroral Electrojet AU index (nT) |
| `magnetosonic_mach_number` | float64 | Magnetosonic Mach number |

## Quick stats

- **{n_total:,}** hourly records ({date_min} to {date_max})
- **55 original parameters** spanning IMF, solar wind, geomagnetic indices, and energetic particles
- Standard reference dataset for solar wind — magnetosphere coupling studies

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/omni-solar-wind-parameters", split="train")
df = ds.to_pandas()

# Southward IMF (Bz < 0) and geomagnetic storms (Dst < -50)
storms = df[(df["bz_gsm_nt"] < -5) & (df["dst_index_nt"] < -50)]
print(f"Storm hours with strong southward IMF: {{len(storms):,}}")

# Solar wind speed distribution
print(df["flow_speed_kms"].describe())

# Correlation between IMF Bz and Dst
corr = df[["bz_gsm_nt", "dst_index_nt"]].dropna().corr()
print(f"Bz-Dst correlation: {{corr.iloc[0, 1]:.3f}}")

# Plasma beta vs Alfven Mach number
import matplotlib.pyplot as plt
sub = df[["plasma_beta", "alfven_mach_number"]].dropna()
plt.scatter(sub["plasma_beta"], sub["alfven_mach_number"], s=0.1, alpha=0.1)
plt.xlabel("Plasma Beta")
plt.ylabel("Alfven Mach Number")
plt.xscale("log")
plt.yscale("log")
plt.title("OMNI: Plasma Beta vs Alfven Mach Number")
plt.show()
```

## Data source

[NASA/GSFC Space Physics Data Facility (SPDF)](https://omniweb.gsfc.nasa.gov/) — OMNI 2 hourly dataset.
Source file: `spdf.gsfc.nasa.gov/pub/data/omni/low_res_omni/omni2_all_years.dat`
Format docs: `spdf.gsfc.nasa.gov/pub/data/omni/low_res_omni/omni2.text`

## Update schedule

Daily at 16:30 UTC via [GitHub Actions](https://github.com/juliensimon/space-datasets).
The full dataset is re-downloaded each run (~100 MB ASCII).

## Related datasets

- [solar-wind-plasma](https://huggingface.co/datasets/juliensimon/solar-wind-plasma) — Near-Earth solar wind from DSCOVR/ACE (1-minute resolution)
- [dst-index](https://huggingface.co/datasets/juliensimon/dst-index) — Geomagnetic Dst index
- [kp-index](https://huggingface.co/datasets/juliensimon/kp-index) — Geomagnetic Kp index
- [ae-index](https://huggingface.co/datasets/juliensimon/ae-index) — Auroral Electrojet AE index
- [f107-index](https://huggingface.co/datasets/juliensimon/f107-index) — F10.7 solar radio flux

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/omni-solar-wind-parameters) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{omni_solar_wind,
  author = {{Simon, Julien}},
  title = {{OMNI Hourly Solar Wind Parameters}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/omni-solar-wind-parameters}},
  note = {{Based on NASA/GSFC OMNI 2 hourly merged solar wind and geomagnetic index data}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update OMNI solar wind parameters: {n_total:,} records"
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
