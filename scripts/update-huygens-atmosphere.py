#!/usr/bin/env python3
"""Fetch Huygens HASI Titan atmospheric profile data from PDS and upload to HF."""

import subprocess
import tempfile
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

from dataset_images import banner_markdown, download_banner
from validate import check_dataset

HF_REPO = "juliensimon/huygens-titan-atmosphere"

PDS_BASE = (
    "https://pds-atmospheres.nmsu.edu/PDS/data/hphasi_0001/DATA/PROFILES/"
)

# Descent phase: surface to ~147 km, 5 columns (time, alt, pressure, temp, density)
DESCENT_URL = PDS_BASE + "HASI_L4_ATMO_PROFILE_DESCEN.TAB"
# Entry phase: ~1400 km to ~157 km, 4 columns (time, alt, pressure, temp — no density)
ENTRY_URL = PDS_BASE + "HASI_L4_ATMO_PROFILE_ENTRY.TAB"
# Velocity profile: full trajectory, 2 columns (time, velocity)
VELOCITY_URL = PDS_BASE + "HASI_L4_VELOCITY_PROFILE.TAB"

# Each PDS file uses instrument-clock milliseconds with a different T0 per phase.
# T0 values derived from PDS label START_TIME and first time_ms value:
#   Entry:   UTC 2005-01-14T09:05:28.878 at time_ms=15835925  → T0 = 04:41:32.953
#   Descent: UTC 2005-01-14T09:11:21.373 at time_ms=60545     → T0 = 09:10:20.828
#   Velocity file spans both phases using the same clock segments.
ENTRY_T0 = pd.Timestamp("2005-01-14T04:41:32.953")
DESCENT_T0 = pd.Timestamp("2005-01-14T09:10:20.828")

# Threshold to distinguish entry-clock vs descent-clock rows (entry times > 10M ms)
CLOCK_BOUNDARY_MS = 10_000_000


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

    # ── Convert instrument clock to UTC before merging ────────────────
    df_descent["utc_time"] = clock_to_utc(
        pd.to_numeric(df_descent["time_ms"], errors="coerce")
    )
    df_entry["utc_time"] = clock_to_utc(
        pd.to_numeric(df_entry["time_ms"], errors="coerce")
    )
    df_velocity["utc_time"] = clock_to_utc(
        pd.to_numeric(df_velocity["time_ms"], errors="coerce")
    )

    # ── Merge entry + descent on UTC ──────────────────────────────────
    df = pd.concat([df_entry, df_descent], ignore_index=True)
    df = df.sort_values("utc_time").reset_index(drop=True)
    print(f"  {len(df):,} combined atmospheric rows (entry + descent)")

    # ── Merge velocity by nearest UTC time ────────────────────────────
    df_vel_sorted = df_velocity[["utc_time", "velocity_m_s"]].sort_values("utc_time")
    df = pd.merge_asof(
        df.sort_values("utc_time"),
        df_vel_sorted,
        on="utc_time",
        direction="nearest",
        tolerance=pd.Timedelta(seconds=5),
    )
    print(f"  {df['velocity_m_s'].notna().sum():,} rows matched with velocity")

    # ── Type coercion ─────────────────────────────────────────────────
    for col in ["altitude_m", "pressure_pa", "temperature_k",
                "density_kg_m3", "velocity_m_s"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # ── Derived columns ───────────────────────────────────────────────
    # Mission elapsed time in seconds from entry interface (first UTC)
    t0_mission = df["utc_time"].min()
    df["mission_elapsed_time_s"] = (
        (df["utc_time"] - t0_mission).dt.total_seconds().round(3)
    )

    # Altitude in km for convenience
    df["altitude_km"] = (df["altitude_m"] / 1000.0).round(3)

    # Pressure in hPa (mbar) for convenience
    df["pressure_hpa"] = (df["pressure_pa"] / 100.0).round(6)

    # ── Column order ──────────────────────────────────────────────────
    df = df[[
        "utc_time", "mission_elapsed_time_s", "phase",
        "altitude_m", "altitude_km",
        "pressure_pa", "pressure_hpa",
        "temperature_k",
        "density_kg_m3",
        "velocity_m_s",
    ]]

    # ── Drop rows with no valid measurement ───────────────────────────
    df = df.dropna(subset=["altitude_m", "temperature_k"], how="any")
    df = df.sort_values("utc_time").reset_index(drop=True)
    print(f"  {len(df):,} rows after cleanup")

    # ── Stats ─────────────────────────────────────────────────────────
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

    print(f"  Altitude range: {alt_min:.1f} - {alt_max:.1f} km")
    print(f"  Temperature range: {temp_min:.1f} - {temp_max:.1f} K")
    print(f"  Surface conditions: {press_surface:.1f} hPa, {temp_surface:.1f} K")

    # ── Determine size category ───────────────────────────────────────
    n = len(df)
    if n < 1000:
        size_cat = "n<1K"
    elif n < 10_000:
        size_cat = "1K<n<10K"
    else:
        size_cat = "10K<n<100K"

    # ── Validation ────────────────────────────────────────────────────
    check_dataset(
        df, "huygens-titan-atmosphere",
        min_rows=50,
        expected_columns=[
            "utc_time", "mission_elapsed_time_s", "phase",
            "altitude_m", "altitude_km",
            "pressure_pa", "pressure_hpa",
            "temperature_k", "density_kg_m3",
            "velocity_m_s",
        ],
        critical_columns=[
            "utc_time", "altitude_m", "temperature_k", "pressure_pa",
        ],
    )

    # ── Write parquet + README ────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "huygens_titan_atmosphere.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.2f} MB parquet")

        banner_file = download_banner("huygens-atmosphere", tmp)
        banner_md = banner_markdown("huygens-atmosphere", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Huygens Probe — Titan Atmospheric Profile"
language:
  - en
description: "Titan atmospheric profile from the Huygens Probe descent (Jan 14, 2005) — temperature, pressure, and density from 1,400 km altitude to the surface."
task_categories:
  - tabular-regression
tags:
  - space
  - titan
  - huygens
  - cassini
  - atmosphere
  - esa
  - planetary-science
  - probe
  - descent
  - saturn
  - open-data
  - tabular-data
  - parquet
size_categories:
  - {size_cat}
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/huygens_titan_atmosphere.parquet
    default: true
---

# Huygens Probe — Titan Atmospheric Profile
{banner_md}
*Part of the [Space Probe and Mission Datasets](https://huggingface.co/collections/juliensimon/space-probe-and-mission-datasets-69c3fe82d410a42b1e313167) collection on Hugging Face.*

Titan atmospheric profile measured by the Huygens Atmospheric Structure Instrument (HASI)
during descent on **January 14, 2005** ({time_start}--{time_end} UTC). Currently **{n:,}** measurements
spanning **{alt_min:.1f}** to **{alt_max:.1f} km** altitude — the only in-situ atmospheric profile
ever taken of Titan.

## Dataset description

On January 14, 2005, the ESA Huygens probe separated from the Cassini orbiter and descended
through Titan's atmosphere for approximately {duration_min:.0f} minutes, from atmospheric entry
at ~1,400 km altitude to touchdown on the surface. The Huygens Atmospheric Structure
Instrument (HASI) measured pressure, temperature, and density throughout the descent.

The dataset combines two mission phases:

- **Entry phase** ({n_entry:,} measurements): Upper atmosphere ({alt_max:.0f} km down to ~157 km), where
  pressure and temperature were derived from accelerometer deceleration data. Density was not
  directly measured during this phase.
- **Descent phase** ({n_descent:,} measurements): Lower atmosphere (~147 km to the surface at {alt_min:.1f} km),
  where direct pressure/temperature sensors provided measurements after parachute deployment.
  Density was computed from pressure and temperature.

Vertical velocity from the trajectory reconstruction is merged for each measurement point.

Titan is the only moon in the solar system with a substantial atmosphere — a dense nitrogen-methane envelope with a surface pressure of approximately 1.5 bar, roughly 50% greater than Earth's sea-level pressure. The Huygens descent through this atmosphere revealed a complex thermal structure including a well-defined tropopause near 44 km altitude (at roughly 70 K), a stratosphere warmed by methane and haze absorption, and a troposphere with a nearly constant lapse rate. The temperature profile confirmed theoretical predictions of a methane hydrological cycle, with conditions permitting methane condensation and rainfall in the lower troposphere — a cycle subsequently confirmed by Cassini's detection of methane lakes at Titan's poles.

The atmospheric density measurements from the descent phase enabled direct determination of the mean molecular weight and composition of Titan's lower atmosphere, complementing mass spectrometer results from the GCMS instrument. The transition between the entry phase (where density was inferred from deceleration) and the descent phase (where direct sensors operated under parachute) provides a complete atmospheric profile spanning nearly three orders of magnitude in pressure. This profile remains the only ground-truth calibration point for remote sensing retrievals of Titan's atmospheric state and is fundamental to atmospheric modeling, aerosol microphysics studies, and planning for future Titan missions such as NASA's Dragonfly rotorcraft.

Surface conditions at landing: **{press_surface:.1f} hPa** pressure, **{temp_surface:.1f} K** temperature.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `utc_time` | datetime | Measurement timestamp (UTC) |
| `mission_elapsed_time_s` | float64 | Seconds since atmospheric entry (T0 = {time_start} UTC) |
| `phase` | string | Mission phase: "entry" (upper atmosphere) or "descent" (parachute phase) |
| `altitude_m` | float64 | Altitude above surface (meters) |
| `altitude_km` | float64 | Altitude above surface (kilometers) |
| `pressure_pa` | float64 | Atmospheric pressure (Pascals) |
| `pressure_hpa` | float64 | Atmospheric pressure (hectopascals / millibars) |
| `temperature_k` | float64 | Atmospheric temperature (Kelvin) |
| `density_kg_m3` | float64 | Atmospheric density (kg/m^3) — null during entry phase |
| `velocity_m_s` | float64 | Probe vertical velocity (m/s) |

## Quick stats

- **{n:,}** atmospheric measurements ({n_entry:,} entry + {n_descent:,} descent)
- Altitude range: **{alt_min:.1f}** to **{alt_max:.1f} km**
- Temperature range: **{temp_min:.1f}** to **{temp_max:.1f} K**
- Surface conditions: **{press_surface:.1f} hPa**, **{temp_surface:.1f} K**
- Duration: **{duration_min:.0f} minutes** of atmospheric profiling

## Usage

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

# Entry vs descent phase
entry = df[df["phase"] == "entry"]
descent = df[df["phase"] == "descent"]
print(f"Entry: {{len(entry)}} pts, {{entry['altitude_km'].min():.0f}}-{{entry['altitude_km'].max():.0f}} km")
print(f"Descent: {{len(descent)}} pts, {{descent['altitude_km'].min():.0f}}-{{descent['altitude_km'].max():.0f}} km")

# Pressure-temperature diagram
plt.semilogy(df["temperature_k"], df["pressure_hpa"])
plt.xlabel("Temperature (K)")
plt.ylabel("Pressure (hPa)")
plt.gca().invert_yaxis()
plt.title("Titan P-T Profile")
plt.show()
```

## Data source

[NASA PDS Atmospheres Node — Huygens HASI Archive](https://pds-atmospheres.nmsu.edu/data_and_services/atmospheres_data/Huygens/HASI.html)
(Volume `hphasi_0001`, Level 4 calibrated profiles).

Original instrument paper: Fulchignoni, M. et al., "In situ measurements of the physical
characteristics of Titan's environment," *Nature*, 438, 785--791 (2005).

## Related datasets

- [cassini-saturn-observations](https://huggingface.co/datasets/juliensimon/cassini-saturn-observations) — Cassini orbiter observation log
- [deep-space-probes](https://huggingface.co/datasets/juliensimon/deep-space-probes) — Voyager & Pioneer merged hourly data
- [mars-perseverance-weather](https://huggingface.co/datasets/juliensimon/mars-perseverance-weather) — Mars atmospheric measurements

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/huygens-titan-atmosphere) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{huygens_titan_atmosphere,
  author = {{Simon, Julien}},
  title = {{Huygens Probe — Titan Atmospheric Profile}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/huygens-titan-atmosphere}},
  note = {{Based on ESA/NASA Huygens HASI Level 4 calibrated atmospheric profiles from the PDS Atmospheres Node}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Upload Huygens Titan atmosphere: {n:,} measurements"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    print(f"Done. {n:,} rows uploaded.")


if __name__ == "__main__":
    main()
