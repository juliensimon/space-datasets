#!/usr/bin/env python3
"""Fetch Galileo Probe ASI atmospheric profile from PDS and upload to HF."""

import os
import subprocess
import tempfile
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset

PDS_BASE = "https://pds-atmospheres.nmsu.edu/PDS/data/gp_0001/data/asi/"
HF_REPO = "juliensimon/galileo-jupiter-atmosphere"


def fetch_upper_atmosphere():
    """Fetch upper atmosphere (entry phase) data from upperatm.tab."""
    url = PDS_BASE + "upperatm.tab"
    print(f"  Fetching {url}")
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()

    # Fixed-width whitespace-delimited, 12 columns
    df = pd.read_csv(
        StringIO(resp.text),
        sep=r"\s+",
        header=None,
        names=[
            "time_s", "altitude_km", "pressure_mbar", "temperature_k",
            "density_kg_m3", "mean_molecular_weight_amu", "cp_over_cv",
            "gas_constant_j_kg_k", "velocity_km_s", "flight_path_angle_deg",
            "latitude_deg", "longitude_deg",
        ],
    )
    # Convert pressure from mbar to bar for consistency with descent data
    df["pressure_bar"] = df["pressure_mbar"] / 1000.0
    df["phase"] = "entry"
    print(f"  Upper atmosphere: {len(df)} rows, altitude {df['altitude_km'].min():.1f} to {df['altitude_km'].max():.1f} km")
    return df


def fetch_descent():
    """Fetch descent phase data from descent.tab."""
    url = PDS_BASE + "descent.tab"
    print(f"  Fetching {url}")
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()

    # Fixed-width whitespace-delimited, 8 columns
    df = pd.read_csv(
        StringIO(resp.text),
        sep=r"\s+",
        header=None,
        names=[
            "time_s", "altitude_km", "pressure_bar", "temperature_k",
            "density_kg_m3", "gravity_m_s2", "descent_velocity_m_s",
            "temperature_gradient_k_km",
        ],
    )
    # Replace fill values (-999.99, -999.990) with NaN
    for col in ["descent_velocity_m_s", "temperature_gradient_k_km"]:
        df.loc[df[col] <= -999, col] = pd.NA

    # Replace zero density with NaN (seen in raw data)
    df.loc[df["density_kg_m3"] == 0, "density_kg_m3"] = pd.NA

    df["phase"] = "descent"
    print(f"  Descent: {len(df)} rows, altitude {df['altitude_km'].min():.1f} to {df['altitude_km'].max():.1f} km")
    return df


def main():
    print("Fetching Galileo Probe ASI data from PDS Atmospheres Node...")

    upper = fetch_upper_atmosphere()
    descent = fetch_descent()

    # Build unified dataframe with all columns from both phases
    # Common columns: time_s, altitude_km, pressure_bar, temperature_k, density_kg_m3, phase
    # Upper-only: pressure_mbar, mean_molecular_weight_amu, cp_over_cv, gas_constant_j_kg_k,
    #             velocity_km_s, flight_path_angle_deg, latitude_deg, longitude_deg
    # Descent-only: gravity_m_s2, descent_velocity_m_s, temperature_gradient_k_km

    # Add missing columns as float NaN to each before concat (avoids FutureWarning)
    all_cols = sorted(set(upper.columns) | set(descent.columns))
    for col in all_cols:
        if col not in upper.columns:
            upper[col] = float("nan")
        if col not in descent.columns:
            descent[col] = float("nan")

    df = pd.concat([upper, descent], ignore_index=True)

    # Sort by altitude descending (highest altitude first = entry, then descent)
    df = df.sort_values("altitude_km", ascending=False).reset_index(drop=True)

    # Coerce all numeric columns
    numeric_cols = [c for c in df.columns if c not in ("phase",)]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Reorder columns for clarity
    col_order = [
        "phase", "time_s", "altitude_km", "pressure_bar", "pressure_mbar",
        "temperature_k", "density_kg_m3",
        "mean_molecular_weight_amu", "cp_over_cv", "gas_constant_j_kg_k",
        "gravity_m_s2", "descent_velocity_m_s", "temperature_gradient_k_km",
        "velocity_km_s", "flight_path_angle_deg", "latitude_deg", "longitude_deg",
    ]
    col_order = [c for c in col_order if c in df.columns]
    df = df[col_order]

    print(f"\nCombined profile: {len(df)} rows")
    print(f"  Altitude range: {df['altitude_km'].min():.1f} to {df['altitude_km'].max():.1f} km (above 1-bar level)")
    print(f"  Pressure range: {df['pressure_bar'].min():.6g} to {df['pressure_bar'].max():.4f} bar")
    print(f"  Temperature range: {df['temperature_k'].min():.1f} to {df['temperature_k'].max():.1f} K")

    n_entry = int((df["phase"] == "entry").sum())
    n_descent = int((df["phase"] == "descent").sum())
    alt_min = df["altitude_km"].min()
    alt_max = df["altitude_km"].max()
    p_min = df["pressure_bar"].min()
    p_max = df["pressure_bar"].max()
    t_min = df["temperature_k"].min()
    t_max = df["temperature_k"].max()

    # Validation
    check_dataset(
        df, "galileo-jupiter-atmosphere",
        min_rows=50,
        expected_columns=[
            "phase", "time_s", "altitude_km", "pressure_bar",
            "temperature_k", "density_kg_m3",
        ],
        critical_columns=["altitude_km", "pressure_bar", "temperature_k", "density_kg_m3"],
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "galileo_jupiter_atmosphere.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_kb = out.stat().st_size / 1024
        print(f"  {size_kb:.1f} KB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Galileo Probe Jupiter Atmospheric Profile"
language:
  - en
description: "Jupiter atmospheric profile from the Galileo Probe descent (Dec 7, 1995) — temperature, pressure, and density from the stratosphere to ~24 bar."
task_categories:
  - tabular-regression
tags:
  - space
  - jupiter
  - galileo
  - atmosphere
  - nasa
  - planetary-science
  - probe
  - descent
  - open-data
  - tabular-data
  - parquet
size_categories:
  - n<1K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/galileo_jupiter_atmosphere.parquet
    default: true
---

# Galileo Probe Jupiter Atmospheric Profile

*Part of the [Space Probe & Mission Datasets](https://huggingface.co/collections/juliensimon/space-probe-and-mission-datasets-69c3fe82d410a42b1e313167) collection on Hugging Face.*

Jupiter atmospheric structure measured by the Galileo Probe Atmospheric Structure Instrument (ASI)
during entry and descent on **December 7, 1995**. The probe entered Jupiter's atmosphere at
6.5 degrees north planetocentric latitude and measured conditions from the stratosphere
(~1000 km altitude) down to the ~22 bar pressure level (~130 km below the 1-bar reference).

Currently **{len(df):,}** measurements: **{n_entry}** from the entry phase (upper atmosphere)
and **{n_descent}** from the parachute descent phase.

## Dataset description

The Galileo Probe was the first (and so far only) spacecraft to directly sample a giant planet's
atmosphere. Released from the Galileo orbiter, it entered Jupiter's atmosphere at ~47 km/s and
deployed a parachute at ~23 km above the 1-bar level. The Atmospheric Structure Instrument (ASI)
measured temperature, pressure, and density throughout the entry and descent phases.

The **entry phase** covers the upper atmosphere (stratosphere and upper troposphere, ~1000 km down
to ~23 km altitude) where measurements are derived from probe deceleration. The **descent phase**
covers the lower troposphere (~17 km down to ~-133 km, i.e., from 0.4 bar to ~22 bar) using
direct temperature and pressure sensors under parachute.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `phase` | string | Measurement phase: "entry" (upper atmosphere) or "descent" (lower atmosphere) |
| `time_s` | float64 | Time from minor frame 0 (seconds) |
| `altitude_km` | float64 | Altitude above the 1-bar pressure level (km; negative = below 1-bar) |
| `pressure_bar` | float64 | Ambient atmospheric pressure (bar) |
| `pressure_mbar` | float64 | Ambient atmospheric pressure (millibar) — entry phase only |
| `temperature_k` | float64 | Atmospheric temperature (Kelvin) |
| `density_kg_m3` | float64 | Atmospheric mass density (kg/m^3) |
| `mean_molecular_weight_amu` | float64 | Mean molecular weight (AMU) — entry phase only |
| `cp_over_cv` | float64 | Ratio of specific heats — entry phase only |
| `gas_constant_j_kg_k` | float64 | Specific gas constant R (J/kg/K) — entry phase only |
| `gravity_m_s2` | float64 | Local gravitational acceleration (m/s^2) — descent phase only |
| `descent_velocity_m_s` | float64 | Probe descent velocity (m/s) — descent phase only |
| `temperature_gradient_k_km` | float64 | Temperature lapse rate dT/dz (K/km) — descent phase only |
| `velocity_km_s` | float64 | Probe velocity relative to atmosphere (km/s) — entry phase only |
| `flight_path_angle_deg` | float64 | Flight path angle relative to atmosphere (degrees) — entry phase only |
| `latitude_deg` | float64 | Planetocentric latitude (degrees) — entry phase only |
| `longitude_deg` | float64 | System III west longitude (degrees) — entry phase only |

## Quick stats

- **{len(df):,}** atmospheric measurements (entry + descent)
- Altitude range: **{alt_max:.0f} km** to **{alt_min:.0f} km** (above 1-bar level)
- Pressure range: **{p_min:.2e} bar** to **{p_max:.2f} bar**
- Temperature range: **{t_min:.0f} K** to **{t_max:.0f} K**
- Date: December 7, 1995

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/galileo-jupiter-atmosphere", split="train")
df = ds.to_pandas()

# Full temperature profile
import matplotlib.pyplot as plt
plt.plot(df["temperature_k"], df["altitude_km"])
plt.xlabel("Temperature (K)")
plt.ylabel("Altitude above 1-bar (km)")
plt.title("Jupiter Temperature Profile — Galileo Probe")
plt.grid(True)
plt.show()

# Descent phase only — pressure vs temperature
descent = df[df["phase"] == "descent"]
plt.semilogy(descent["temperature_k"], descent["pressure_bar"])
plt.xlabel("Temperature (K)")
plt.ylabel("Pressure (bar)")
plt.gca().invert_yaxis()
plt.title("Jupiter T-P Profile (Descent Phase)")
plt.show()

# Entry phase — upper atmosphere density
entry = df[df["phase"] == "entry"]
plt.semilogy(entry["density_kg_m3"], entry["altitude_km"])
plt.xlabel("Density (kg/m^3)")
plt.ylabel("Altitude (km)")
plt.title("Jupiter Upper Atmosphere Density")
plt.show()
```

## Data source

[NASA PDS Atmospheres Node — Galileo Probe ASI](https://pds-atmospheres.nmsu.edu/PDS/data/gp_0001/data/asi/).
Data from the Atmospheric Structure Instrument (ASI) on the Galileo Probe, archived by the
Planetary Data System. Reference: Seiff et al. (1998), "Thermal structure of Jupiter's atmosphere
near the edge of a 5-micron hot spot in the north equatorial belt",
*J. Geophys. Res.*, 103(E10), 22857-22889.

## Update schedule

Static dataset (one-time upload). The Galileo Probe entered Jupiter on December 7, 1995.

## Related datasets

- [deep-space-probes](https://huggingface.co/datasets/juliensimon/deep-space-probes) — Voyager 1/2 and Pioneer 10/11 merged hourly data
- [jupiter-magnetosphere](https://huggingface.co/datasets/juliensimon/jupiter-magnetosphere) — Juno magnetometer data at Jupiter

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/galileo-jupiter-atmosphere) and share feedback in the Community tab! Also consider giving a ⭐ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{galileo_jupiter_atmosphere,
  author = {{Simon, Julien}},
  title = {{Galileo Probe Jupiter Atmospheric Profile}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/galileo-jupiter-atmosphere}},
  note = {{Based on NASA/PDS Galileo Probe Atmospheric Structure Instrument (ASI) data. Original PI: A. Seiff (NASA Ames)}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Upload Galileo Probe Jupiter atmosphere: {len(df):,} records"
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
