#!/usr/bin/env python3
"""Fetch Huygens HASI Titan atmospheric profile data from PDS and upload to HF.

Source: NASA PDS Atmospheres Node — Huygens HASI Level 4 calibrated profiles
Reference: Fulchignoni et al. (2005), Nature 438, 785-791.
"""

from io import StringIO

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

HF_REPO = "juliensimon/huygens-titan-atmosphere"

PDS_BASE = (
    "https://pds-atmospheres.nmsu.edu/PDS/data/hphasi_0001/DATA/PROFILES/"
)

DESCENT_URL = PDS_BASE + "HASI_L4_ATMO_PROFILE_DESCEN.TAB"
ENTRY_URL = PDS_BASE + "HASI_L4_ATMO_PROFILE_ENTRY.TAB"
VELOCITY_URL = PDS_BASE + "HASI_L4_VELOCITY_PROFILE.TAB"

# T0 values derived from PDS label START_TIME and first time_ms value
ENTRY_T0 = pd.Timestamp("2005-01-14T04:41:32.953")
DESCENT_T0 = pd.Timestamp("2005-01-14T09:10:20.828")
CLOCK_BOUNDARY_MS = 10_000_000

# ── Column descriptions ─────────────────────────────────────────────
COLUMN_DESCRIPTIONS = {
    "utc_time": "Measurement timestamp (UTC); derived from instrument clock using phase-appropriate T0 offsets",
    "mission_elapsed_time_s": "Seconds since atmospheric entry; T0 corresponds to first entry measurement",
    "phase": "Mission phase: 'entry' (upper atmosphere, derived from deceleration) or 'descent' (parachute phase, direct sensors)",
    "altitude_m": "Altitude above Titan's surface (meters); ranges from ~1,400,000 m at entry to ~0 m at landing",
    "altitude_km": "Altitude above Titan's surface (kilometers); derived from altitude_m for convenience",
    "pressure_pa": "Atmospheric pressure (Pascals); ranges from near-vacuum at entry to ~147,000 Pa at surface (~1.47 bar)",
    "pressure_hpa": "Atmospheric pressure (hectopascals / millibars); derived from pressure_pa for convenience",
    "temperature_k": "Atmospheric temperature (Kelvin); ranges from ~70 K at the tropopause to ~94 K at the surface",
    "density_kg_m3": "Atmospheric density (kg/m^3); null during entry phase where density was not directly measured",
    "velocity_m_s": "Probe vertical velocity (m/s); merged from trajectory reconstruction, matched by nearest UTC time",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Titan atmospheric profile measured by the Huygens Atmospheric Structure Instrument \
(HASI) during descent on January 14, 2005 — the only in-situ atmospheric profile \
ever taken of Titan.

On January 14, 2005, the ESA Huygens probe separated from the Cassini orbiter and \
descended through Titan's atmosphere, from atmospheric entry at ~1,400 km altitude to \
touchdown on the surface. The HASI measured pressure, temperature, and density throughout.

The dataset combines two mission phases: the entry phase (upper atmosphere, where \
pressure and temperature were derived from accelerometer deceleration data) and the \
descent phase (lower atmosphere, where direct pressure/temperature sensors provided \
measurements after parachute deployment). Vertical velocity from trajectory \
reconstruction is merged for each measurement point.

Titan is the only moon in the solar system with a substantial atmosphere — a dense \
nitrogen-methane envelope with a surface pressure of approximately 1.5 bar, roughly \
50% greater than Earth's sea-level pressure. The Huygens descent revealed a complex \
thermal structure including a well-defined tropopause near 44 km altitude (~70 K), a \
stratosphere warmed by methane and haze absorption, and a troposphere with a nearly \
constant lapse rate. The temperature profile confirmed theoretical predictions of a \
methane hydrological cycle. This profile remains the only ground-truth calibration \
point for remote sensing retrievals of Titan's atmospheric state.
"""


def fetch_tab(url, columns, timeout=60):
    """Download a PDS .TAB file and parse as semicolon-delimited."""
    print(f"  Fetching {url.split('/')[-1]}...")
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    df = pd.read_csv(
        StringIO(resp.text),
        sep=";",
        header=None,
        names=columns,
        skipinitialspace=True,
        index_col=False,
    )
    print(f"    {len(df):,} rows")
    return df


def clock_to_utc(time_ms):
    """Convert instrument-clock milliseconds to UTC using phase-appropriate T0."""
    utc = pd.Series(pd.NaT, index=time_ms.index)
    entry_mask = time_ms >= CLOCK_BOUNDARY_MS
    descent_mask = ~entry_mask

    if entry_mask.any():
        utc[entry_mask] = ENTRY_T0 + pd.to_timedelta(
            time_ms[entry_mask], unit="ms"
        )
    if descent_mask.any():
        utc[descent_mask] = DESCENT_T0 + pd.to_timedelta(
            time_ms[descent_mask], unit="ms"
        )
    return utc


def main():
    print("Fetching Huygens HASI atmospheric profile from PDS...")

    # ── Fetch all three profile tables ────────────────────────────────
    df_descent = fetch_tab(
        DESCENT_URL,
        ["time_ms", "altitude_m", "pressure_pa", "temperature_k", "density_kg_m3"],
    )
    df_descent["phase"] = "descent"

    df_entry = fetch_tab(
        ENTRY_URL,
        ["time_ms", "altitude_m", "pressure_pa", "temperature_k"],
    )
    df_entry["phase"] = "entry"

    df_velocity = fetch_tab(
        VELOCITY_URL,
        ["time_ms", "velocity_m_s"],
    )

    # ── Convert instrument clock to UTC ──────────────────────────────
    df_descent["utc_time"] = clock_to_utc(
        pd.to_numeric(df_descent["time_ms"], errors="coerce")
    )
    df_entry["utc_time"] = clock_to_utc(
        pd.to_numeric(df_entry["time_ms"], errors="coerce")
    )
    df_velocity["utc_time"] = clock_to_utc(
        pd.to_numeric(df_velocity["time_ms"], errors="coerce")
    )

    # ── Merge entry + descent ────────────────────────────────────────
    df = pd.concat([df_entry, df_descent], ignore_index=True)
    df = df.sort_values("utc_time").reset_index(drop=True)
    print(f"  {len(df):,} combined atmospheric rows")

    # ── Merge velocity by nearest UTC time ───────────────────────────
    df_vel_sorted = df_velocity[["utc_time", "velocity_m_s"]].sort_values("utc_time")
    df = pd.merge_asof(
        df.sort_values("utc_time"),
        df_vel_sorted,
        on="utc_time",
        direction="nearest",
        tolerance=pd.Timedelta(seconds=5),
    )
    print(f"  {df['velocity_m_s'].notna().sum():,} rows matched with velocity")

    # ── Derived columns ──────────────────────────────────────────────
    t0_mission = df["utc_time"].min()
    df["mission_elapsed_time_s"] = (
        (df["utc_time"] - t0_mission).dt.total_seconds().round(3)
    )
    df["altitude_km"] = (df["altitude_m"] / 1000.0).round(3)
    df["pressure_hpa"] = (df["pressure_pa"] / 100.0).round(6)

    # ── Column order ─────────────────────────────────────────────────
    df = df[[
        "utc_time", "mission_elapsed_time_s", "phase",
        "altitude_m", "altitude_km",
        "pressure_pa", "pressure_hpa",
        "temperature_k",
        "density_kg_m3",
        "velocity_m_s",
    ]]

    # Drop rows with no valid measurement
    df = df.dropna(subset=["altitude_m", "temperature_k"], how="any")
    df = df.sort_values("utc_time").reset_index(drop=True)
    print(f"  {len(df):,} rows after cleanup")

    # ── Stats ────────────────────────────────────────────────────────
    n_entry = int((df["phase"] == "entry").sum())
    n_descent = int((df["phase"] == "descent").sum())
    alt_max = df["altitude_km"].max()
    alt_min = df["altitude_km"].min()
    temp_min = df["temperature_k"].min()
    temp_max = df["temperature_k"].max()
    press_surface = df.loc[df["altitude_m"].idxmin(), "pressure_hpa"]
    temp_surface = df.loc[df["altitude_m"].idxmin(), "temperature_k"]
    time_start = df["utc_time"].min().strftime("%H:%M:%S")
    time_end = df["utc_time"].max().strftime("%H:%M:%S")
    duration_min = (
        df["mission_elapsed_time_s"].max() - df["mission_elapsed_time_s"].min()
    ) / 60
    n = len(df)

    quick_stats = f"""\
- **{n:,}** atmospheric measurements ({n_entry:,} entry + {n_descent:,} descent)
- Altitude range: **{alt_min:.1f}** to **{alt_max:.1f} km**
- Temperature range: **{temp_min:.1f}** to **{temp_max:.1f} K**
- Surface conditions: **{press_surface:.1f} hPa**, **{temp_surface:.1f} K**
- Duration: **{duration_min:.0f} minutes** ({time_start}--{time_end} UTC)"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/huygens-titan-atmosphere", split="train")
df = ds.to_pandas()

# Temperature profile
import matplotlib.pyplot as plt
plt.plot(df["temperature_k"], df["altitude_km"])
plt.xlabel("Temperature (K)")
plt.ylabel("Altitude (km)")
plt.title("Titan Atmospheric Temperature Profile")
plt.show()

# Pressure-temperature diagram
plt.semilogy(df["temperature_k"], df["pressure_hpa"])
plt.xlabel("Temperature (K)")
plt.ylabel("Pressure (hPa)")
plt.gca().invert_yaxis()
plt.title("Titan P-T Profile")
plt.show()

# Entry vs descent
entry = df[df["phase"] == "entry"]
descent = df[df["phase"] == "descent"]
print(f"Entry: {len(entry)} pts, {entry['altitude_km'].min():.0f}-{entry['altitude_km'].max():.0f} km")
print(f"Descent: {len(descent)} pts, {descent['altitude_km'].min():.0f}-{descent['altitude_km'].max():.0f} km")
```"""

    numeric_cols = [
        "mission_elapsed_time_s", "altitude_m", "altitude_km",
        "pressure_pa", "pressure_hpa", "temperature_k",
        "density_kg_m3", "velocity_m_s",
    ]

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Huygens Probe — Titan Atmospheric Profile",
        description=DESCRIPTION,
        tags=["space", "titan", "huygens", "cassini", "atmosphere", "esa",
              "planetary-science", "probe", "descent", "saturn",
              "open-data", "tabular-data", "parquet"],
        source_url="https://pds-atmospheres.nmsu.edu/data_and_services/atmospheres_data/Huygens/HASI.html",
        task_categories=["tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/space-probe-and-mission-datasets-69c3fe82d410a42b1e313167",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA06193/PIA06193~small.jpg",
            "alt": "Saturn and its rings, captured by the Cassini spacecraft",
            "credit": "NASA/JPL-Caltech/SSI",
        },
        related_datasets=[
            "juliensimon/cassini-saturn-observations",
            "juliensimon/deep-space-probes",
            "juliensimon/galileo-jupiter-atmosphere",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=numeric_cols,
        )
        p.publish(
            df,
            filename="huygens_titan_atmosphere.parquet",
            min_rows=50,
            expected_columns=[
                "utc_time", "mission_elapsed_time_s", "phase",
                "altitude_m", "altitude_km",
                "pressure_pa", "pressure_hpa",
                "temperature_k", "density_kg_m3",
                "velocity_m_s",
            ],
            critical_columns=["utc_time", "altitude_m", "temperature_k", "pressure_pa"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Huygens Titan atmosphere: {n:,} measurements",
        )
    print("Done.")


if __name__ == "__main__":
    main()
