#!/usr/bin/env python3
"""Fetch Galileo Probe ASI atmospheric profile from PDS and upload to HF.

Source: NASA PDS Atmospheres Node — Galileo Probe ASI
Reference: Seiff et al. (1998), J. Geophys. Res., 103(E10), 22857-22889.
"""

from io import StringIO

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

PDS_BASE = "https://pds-atmospheres.nmsu.edu/PDS/data/gp_0001/data/asi/"
HF_REPO = "juliensimon/galileo-jupiter-atmosphere"

# ── Column descriptions ─────────────────────────────────────────────
COLUMN_DESCRIPTIONS = {
    "phase": "Measurement phase: 'entry' (upper atmosphere, derived from probe deceleration) or 'descent' (lower atmosphere, direct sensors under parachute)",
    "time_s": "Time from minor frame 0 (seconds); instrument clock reference",
    "altitude_km": "Altitude above the 1-bar pressure level (km; negative values = below 1-bar reference level)",
    "pressure_bar": "Ambient atmospheric pressure (bar); ranges from ~1e-10 bar in the upper atmosphere to ~22 bar at deepest measurement",
    "pressure_mbar": "Ambient atmospheric pressure (millibar); entry phase only, null during descent",
    "temperature_k": "Atmospheric temperature (Kelvin); ranges from ~110 K at the tropopause to ~900 K in the thermosphere and ~430 K at the deepest point",
    "density_kg_m3": "Atmospheric mass density (kg/m^3); derived from deceleration (entry) or pressure/temperature (descent)",
    "mean_molecular_weight_amu": "Mean molecular weight (atomic mass units); entry phase only, primarily H2/He mixture (~2.22 AMU)",
    "cp_over_cv": "Ratio of specific heats (gamma = Cp/Cv); entry phase only, ~1.4 for H2-dominated atmosphere",
    "gas_constant_j_kg_k": "Specific gas constant R (J/kg/K); entry phase only",
    "gravity_m_s2": "Local gravitational acceleration (m/s^2); descent phase only, ~24.8 m/s^2 at 1-bar level",
    "descent_velocity_m_s": "Probe descent velocity (m/s); descent phase only, decreasing as parachute slows probe",
    "temperature_gradient_k_km": "Temperature lapse rate dT/dz (K/km); descent phase only, deviations from dry adiabat indicate condensation",
    "velocity_km_s": "Probe velocity relative to atmosphere (km/s); entry phase only, decelerating from ~47 km/s",
    "flight_path_angle_deg": "Flight path angle relative to local horizontal (degrees); entry phase only",
    "latitude_deg": "Planetocentric latitude (degrees); entry phase only, probe entered near 6.5 deg N",
    "longitude_deg": "System III west longitude (degrees); entry phase only",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Jupiter atmospheric structure measured by the Galileo Probe Atmospheric Structure \
Instrument (ASI) during entry and descent on December 7, 1995. The probe entered \
Jupiter's atmosphere at 6.5 degrees north planetocentric latitude and measured \
conditions from the stratosphere (~1000 km altitude) down to the ~22 bar pressure \
level (~130 km below the 1-bar reference).

The Galileo Probe was the first (and so far only) spacecraft to directly sample a \
giant planet's atmosphere. Released from the Galileo orbiter, it entered Jupiter's \
atmosphere at ~47 km/s and deployed a parachute at ~23 km above the 1-bar level. \
The ASI measured temperature, pressure, and density throughout the entry and descent phases.

The entry phase covers the upper atmosphere (stratosphere and upper troposphere, \
~1000 km down to ~23 km altitude) where measurements are derived from probe \
deceleration. The descent phase covers the lower troposphere (~17 km down to ~-133 km) \
using direct sensors under parachute.

Jupiter's atmosphere is composed primarily of hydrogen (~86%) and helium (~13%) by \
volume. The probe found that heavy elements were enriched by a factor of 2-4 relative \
to solar composition. The helium abundance was measured at ~0.234 by mass fraction, \
significantly depleted relative to the protosolar value, confirming that helium has \
been raining out into Jupiter's deep interior.

The probe entered a 5-micron hot spot, a region of anomalously low cloud opacity in \
Jupiter's North Equatorial Belt. The temperature profile revealed the expected transition \
from the radiatively controlled stratosphere through the tropopause (near 110 K at ~100 mbar) \
into the convective troposphere, where temperatures increased along a nearly dry adiabatic gradient.
"""


def fetch_upper_atmosphere():
    """Fetch upper atmosphere (entry phase) data from upperatm.tab."""
    url = PDS_BASE + "upperatm.tab"
    print(f"  Fetching {url}")
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()

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
    for col in ["descent_velocity_m_s", "temperature_gradient_k_km"]:
        df.loc[df[col] <= -999, col] = pd.NA
    df.loc[df["density_kg_m3"] == 0, "density_kg_m3"] = pd.NA
    df["phase"] = "descent"
    print(f"  Descent: {len(df)} rows, altitude {df['altitude_km'].min():.1f} to {df['altitude_km'].max():.1f} km")
    return df


def main():
    print("Fetching Galileo Probe ASI data from PDS Atmospheres Node...")

    upper = fetch_upper_atmosphere()
    descent = fetch_descent()

    # Add missing columns as NaN to each before concat
    all_cols = sorted(set(upper.columns) | set(descent.columns))
    for col in all_cols:
        if col not in upper.columns:
            upper[col] = float("nan")
        if col not in descent.columns:
            descent[col] = float("nan")

    df = pd.concat([upper, descent], ignore_index=True)
    df = df.sort_values("altitude_km", ascending=False).reset_index(drop=True)

    # Reorder columns
    col_order = [
        "phase", "time_s", "altitude_km", "pressure_bar", "pressure_mbar",
        "temperature_k", "density_kg_m3",
        "mean_molecular_weight_amu", "cp_over_cv", "gas_constant_j_kg_k",
        "gravity_m_s2", "descent_velocity_m_s", "temperature_gradient_k_km",
        "velocity_km_s", "flight_path_angle_deg", "latitude_deg", "longitude_deg",
    ]
    col_order = [c for c in col_order if c in df.columns]
    df = df[col_order]

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    print(f"\nCombined profile: {len(df)} rows")

    # ── Stats ────────────────────────────────────────────────────────
    n_entry = int((df["phase"] == "entry").sum())
    n_descent = int((df["phase"] == "descent").sum())
    alt_min = df["altitude_km"].min()
    alt_max = df["altitude_km"].max()
    p_min = df["pressure_bar"].min()
    p_max = df["pressure_bar"].max()
    t_min = df["temperature_k"].min()
    t_max = df["temperature_k"].max()

    quick_stats = f"""\
- **{len(df):,}** atmospheric measurements ({n_entry} entry + {n_descent} descent)
- Altitude range: **{alt_max:.0f} km** to **{alt_min:.0f} km** (above 1-bar level)
- Pressure range: **{p_min:.2e} bar** to **{p_max:.2f} bar**
- Temperature range: **{t_min:.0f} K** to **{t_max:.0f} K**
- Date: December 7, 1995"""

    usage = """\
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
```"""

    numeric_cols = [c for c in df.columns if c != "phase"]

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Galileo Probe Jupiter Atmospheric Profile",
        description=DESCRIPTION,
        tags=["space", "jupiter", "galileo", "atmosphere", "nasa",
              "planetary-science", "probe", "descent",
              "open-data", "tabular-data", "parquet"],
        source_url="https://pds-atmospheres.nmsu.edu/PDS/data/gp_0001/data/asi/",
        task_categories=["tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/space-probe-and-mission-datasets-69c3fe82d410a42b1e313167",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA00600/PIA00600~small.jpg",
            "alt": "Jupiter's Great Red Spot and the Galilean satellites",
            "credit": "NASA/JPL-Caltech",
        },
        related_datasets=[
            "juliensimon/deep-space-probes",
            "juliensimon/huygens-titan-atmosphere",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=numeric_cols,
        )
        p.publish(
            df,
            filename="galileo_jupiter_atmosphere.parquet",
            min_rows=50,
            expected_columns=[
                "phase", "time_s", "altitude_km", "pressure_bar",
                "temperature_k", "density_kg_m3",
            ],
            critical_columns=["altitude_km", "pressure_bar", "temperature_k", "density_kg_m3"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Galileo Probe Jupiter atmosphere: {len(df):,} records",
        )
    print("Done.")


if __name__ == "__main__":
    main()
