#!/usr/bin/env python3
"""Fetch Artemis II mission data (trajectory, crew, timeline) and upload to HF.

Trajectory from JPL Horizons API (spacecraft ID -1024, "Integrity Orion EM-2").
Crew, timeline, and payload data from NASA press kit and public sources.
"""

import math
import os
import re
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

from dataset_images import banner_markdown, download_banner
from validate import check_dataset


HF_REPO = "juliensimon/artemis-ii"
HORIZONS_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"

# Mission time bounds (ICPS separation to splashdown)
MISSION_START = "2026-04-02T02:00"
MISSION_END = "2026-04-10T23:50"


# ---------------------------------------------------------------------------
# Trajectory from JPL Horizons
# ---------------------------------------------------------------------------

def fetch_horizons_vectors(center, start, stop, step="10m"):
    """Fetch state vectors from JPL Horizons for Artemis II."""
    params = {
        "format": "text",
        "COMMAND": "'-1024'",
        "MAKE_EPHEM": "YES",
        "EPHEM_TYPE": "VECTORS",
        "CENTER": center,
        "START_TIME": start,
        "STOP_TIME": stop,
        "STEP_SIZE": step,
        "VEC_TABLE": "2",
    }
    resp = requests.get(HORIZONS_URL, params=params, timeout=120)
    resp.raise_for_status()
    return resp.text


def parse_horizons_vectors(text):
    """Parse Horizons vector table into list of dicts."""
    lines = text.splitlines()
    try:
        soe = next(i for i, l in enumerate(lines) if l.strip() == "$$SOE")
        eoe = next(i for i, l in enumerate(lines) if l.strip() == "$$EOE")
    except StopIteration:
        print(f"::error::Horizons did not return ephemeris data. Response:\n{text[:500]}")
        sys.exit(1)
    data_lines = lines[soe + 1:eoe]

    records = []
    i = 0
    while i < len(data_lines):
        # Line 1: JD = A.D. YYYY-Mon-DD HH:MM:SS.SSSS TDB
        m = re.search(r"A\.D\.\s+(\d{4}-\w{3}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+)\s+TDB", data_lines[i])
        if not m:
            i += 1
            continue
        epoch_str = m.group(1)
        # Line 2: X = ... Y = ... Z = ...
        pos = re.findall(r"[XYZ]\s*=\s*([-\dE.+]+)", data_lines[i + 1])
        # Line 3: VX = ... VY = ... VZ = ...
        vel = re.findall(r"V[XYZ]\s*=\s*([-\dE.+]+)", data_lines[i + 2])
        if len(pos) == 3 and len(vel) == 3:
            records.append({
                "epoch_tdb": epoch_str,
                "x_km": float(pos[0]),
                "y_km": float(pos[1]),
                "z_km": float(pos[2]),
                "vx_km_s": float(vel[0]),
                "vy_km_s": float(vel[1]),
                "vz_km_s": float(vel[2]),
            })
        i += 3

    return records


def fetch_trajectory():
    """Fetch geocentric trajectory and compute derived columns."""
    print("  Fetching geocentric vectors from JPL Horizons...")
    geo_text = fetch_horizons_vectors("500@399", MISSION_START, MISSION_END)
    geo_records = parse_horizons_vectors(geo_text)
    print(f"  Geocentric: {len(geo_records)} state vectors")

    print("  Fetching selenocentric vectors...")
    moon_text = fetch_horizons_vectors("500@301", MISSION_START, MISSION_END)
    moon_records = parse_horizons_vectors(moon_text)
    print(f"  Selenocentric: {len(moon_records)} state vectors")

    df = pd.DataFrame(geo_records)
    df["epoch_tdb"] = pd.to_datetime(df["epoch_tdb"], format="%Y-%b-%d %H:%M:%S.%f")

    # Derived: distance from Earth and speed
    df["distance_earth_km"] = (df["x_km"]**2 + df["y_km"]**2 + df["z_km"]**2).apply(math.sqrt)
    df["speed_km_s"] = (df["vx_km_s"]**2 + df["vy_km_s"]**2 + df["vz_km_s"]**2).apply(math.sqrt)

    # Add distance from Moon from selenocentric data
    if len(moon_records) == len(geo_records):
        df_moon = pd.DataFrame(moon_records)
        df["distance_moon_km"] = (
            df_moon["x_km"]**2 + df_moon["y_km"]**2 + df_moon["z_km"]**2
        ).apply(math.sqrt)
    else:
        # Fall back: compute from magnitudes
        df["distance_moon_km"] = pd.NA

    # Mission phase labels
    df["mission_phase"] = "transit_outbound"
    # TLI: ~MET +1d 01h 37m from launch (launch was Apr 1 22:35 UTC)
    tli_time = pd.Timestamp("2026-04-03T00:12")
    lunar_soi_entry = pd.Timestamp("2026-04-06T04:00")
    closest_approach = pd.Timestamp("2026-04-06T23:58")
    lunar_soi_exit = pd.Timestamp("2026-04-07T18:00")
    entry_interface = pd.Timestamp("2026-04-10T23:48")

    df.loc[df["epoch_tdb"] < tli_time, "mission_phase"] = "earth_orbit"
    df.loc[(df["epoch_tdb"] >= tli_time) & (df["epoch_tdb"] < lunar_soi_entry), "mission_phase"] = "transit_outbound"
    df.loc[(df["epoch_tdb"] >= lunar_soi_entry) & (df["epoch_tdb"] < closest_approach), "mission_phase"] = "lunar_approach"
    df.loc[(df["epoch_tdb"] >= closest_approach) & (df["epoch_tdb"] < lunar_soi_exit), "mission_phase"] = "lunar_flyby"
    df.loc[(df["epoch_tdb"] >= lunar_soi_exit) & (df["epoch_tdb"] < entry_interface), "mission_phase"] = "transit_return"
    df.loc[df["epoch_tdb"] >= entry_interface, "mission_phase"] = "entry"

    return df


# ---------------------------------------------------------------------------
# Static mission data
# ---------------------------------------------------------------------------

def build_crew_df():
    return pd.DataFrame([
        {"name": "Reid Wiseman", "role": "Commander", "agency": "NASA",
         "nationality": "American", "birth_date": "1975-11-11",
         "birth_place": "Baltimore, MD", "selection_year": 2009,
         "military_rank": "Captain, USN",
         "previous_missions": "Expedition 41 (2014)",
         "previous_flight_days": 165, "eva_count": 0, "eva_hours": 0.0,
         "notable": "Chief of Astronaut Office 2020-2022"},
        {"name": "Victor Glover", "role": "Pilot", "agency": "NASA",
         "nationality": "American", "birth_date": "1976-04-30",
         "birth_place": "Pomona, CA", "selection_year": 2013,
         "military_rank": "Captain, USN",
         "previous_missions": "SpaceX Crew-1 / Expedition 64-65 (2020-2021)",
         "previous_flight_days": 167, "eva_count": 4, "eva_hours": 26.1,
         "notable": "First African American on ISS long-duration crew"},
        {"name": "Christina Koch", "role": "Mission Specialist 1", "agency": "NASA",
         "nationality": "American", "birth_date": "1979-01-29",
         "birth_place": "Grand Rapids, MI", "selection_year": 2013,
         "military_rank": None,
         "previous_missions": "Expeditions 59/60/61 (2019-2020)",
         "previous_flight_days": 328, "eva_count": 6, "eva_hours": 42.0,
         "notable": "Record for longest single spaceflight by a woman; first all-female EVA"},
        {"name": "Jeremy Hansen", "role": "Mission Specialist 2", "agency": "CSA",
         "nationality": "Canadian", "birth_date": "1976-01-27",
         "birth_place": "London, Ontario, Canada", "selection_year": 2009,
         "military_rank": "Colonel, RCAF",
         "previous_missions": None,
         "previous_flight_days": 0, "eva_count": 0, "eva_hours": 0.0,
         "notable": "First Canadian to fly beyond low Earth orbit"},
    ])


def build_timeline_df():
    """Mission timeline from NASA press kit and launch blog."""
    events = [
        # Terminal countdown
        ("T-00:10:00", "terminal_countdown", "Ground Launch Sequencer initiates terminal count"),
        ("T-00:08:00", "terminal_countdown", "Crew Access Arm retract"),
        ("T-00:04:00", "terminal_countdown", "Core stage APU start; LOX terminate replenish"),
        ("T-00:00:33", "terminal_countdown", "Go for automated launch sequencer"),
        ("T-00:00:06", "terminal_countdown", "RS-25 engine start sequence"),
        # Ascent
        ("T+00:00:00", "ascent", "Booster ignition and liftoff"),
        ("T+00:00:07", "ascent", "SLS clears launch tower; roll/pitch maneuver"),
        ("T+00:00:56", "ascent", "SLS reaches supersonic speed"),
        ("T+00:01:10", "ascent", "Maximum dynamic pressure (Max-Q)"),
        ("T+00:02:08", "ascent", "Solid Rocket Booster separation"),
        ("T+00:03:13", "ascent", "Launch Abort System jettison"),
        ("T+00:03:18", "ascent", "Spacecraft adapter fairing separation"),
        ("T+00:08:02", "ascent", "Core stage main engine cutoff (MECO)"),
        ("T+00:08:14", "ascent", "Core stage / ICPS separation"),
        # Earth orbit
        ("T+00:20:00", "earth_orbit", "Orion solar array deployment"),
        ("T+00:49:00", "earth_orbit", "Perigee raise maneuver"),
        ("T+01:47:57", "earth_orbit", "Apogee raise burn to high Earth orbit"),
        ("T+03:24:15", "earth_orbit", "Orion separates from ICPS; proximity ops begin"),
        ("T+04:35:00", "earth_orbit", "Proximity operations conclude"),
        ("T+04:52:00", "earth_orbit", "Orion upper stage separation burn"),
        ("T+05:00:00", "earth_orbit", "ICPS disposal burn"),
        ("T+05:04:00", "earth_orbit", "CubeSat deployment begins"),
        ("T+13:44:00", "earth_orbit", "Perigee raise burn (end of Flight Day 1)"),
        # Transit outbound
        ("T+1d 01:37", "transit_outbound", "Translunar injection (TLI) burn"),
        ("T+1d 23:25", "transit_outbound", "Outbound trajectory correction burn"),
        ("T+2d 02:05", "transit_outbound", "Crew CPR demonstration in microgravity"),
        ("T+2d 05:25", "transit_outbound", "Deep Space Network communications test"),
        ("T+3d 00:12", "transit_outbound", "Trajectory correction burn #2"),
        ("T+3d 20:30", "transit_outbound", "Rapid spacesuit donning/pressurization demo"),
        ("T+4d 05:23", "transit_outbound", "Trajectory correction burn #3"),
        ("T+4d 06:59", "transit_outbound", "Orion enters lunar sphere of influence"),
        # Lunar flyby
        ("T+4d 22:00", "lunar_flyby", "Lunar flyby observation begins"),
        ("T+5d 01:23", "lunar_flyby", "Closest approach to the Moon"),
        ("T+5d 01:26", "lunar_flyby", "Maximum distance from Earth"),
        # Transit return
        ("T+5d 19:47", "transit_return", "Orion exits lunar sphere of influence"),
        ("T+5d 21:10", "transit_return", "Lunar flyby science debrief"),
        ("T+6d 04:23", "transit_return", "Return trajectory correction burn #1"),
        ("T+7d 01:50", "transit_return", "Radiation shielding demonstration"),
        ("T+7d 04:20", "transit_return", "Manual piloting demonstration"),
        ("T+7d 23:15", "transit_return", "Orthostatic intolerance garment assessment"),
        ("T+8d 04:33", "transit_return", "Return trajectory correction burn #2"),
        ("T+8d 20:33", "transit_return", "Return trajectory correction burn #3"),
        # Entry and splashdown
        ("T+8d 22:30", "entry", "Entry checklist begins; crew dons entry suits"),
        ("T+9d 01:13", "entry", "Crew/service module separation"),
        ("T+9d 01:16", "entry", "Crew module raise burn"),
        ("T+9d 01:33", "entry", "Entry interface (400,000 ft altitude)"),
        ("T+9d 01:46", "entry", "Splashdown in Pacific Ocean"),
    ]
    df = pd.DataFrame(events, columns=["met", "phase", "event"])
    return df


def build_payloads_df():
    return pd.DataFrame([
        {"name": "TACHELES", "type": "CubeSat", "provider_country": "Germany",
         "provider_agency": "DLR", "mass_kg": 4.0,
         "objective": "Measure radiation environment in deep space transit"},
        {"name": "K-RadCube", "type": "CubeSat", "provider_country": "South Korea",
         "provider_agency": "KARI/KASA", "mass_kg": 3.0,
         "objective": "Monitor space radiation with compact dosimeter and particle detector"},
        {"name": "SHMS", "type": "CubeSat", "provider_country": "Saudi Arabia",
         "provider_agency": "KACST/SSC", "mass_kg": 4.0,
         "objective": "Monitor spacecraft cabin environment and microbial contamination"},
        {"name": "ATENEA", "type": "CubeSat", "provider_country": "Argentina",
         "provider_agency": "CONAE", "mass_kg": 3.0,
         "objective": "Test Argentine-built components and telecom in deep space"},
        {"name": "Proximity Ops Demo", "type": "experiment", "provider_country": "USA",
         "provider_agency": "NASA", "mass_kg": None,
         "objective": "Manual piloting of Orion around ICPS to simulate future docking"},
        {"name": "Laser Comm (O2O)", "type": "experiment", "provider_country": "USA",
         "provider_agency": "NASA", "mass_kg": None,
         "objective": "Test infrared optical communications for higher data rates"},
        {"name": "Radiation Shielding Demo", "type": "experiment", "provider_country": "USA",
         "provider_agency": "NASA", "mass_kg": None,
         "objective": "Test crew radiation shelter configuration and effectiveness"},
        {"name": "Manual Piloting Demo", "type": "experiment", "provider_country": "USA",
         "provider_agency": "NASA", "mass_kg": None,
         "objective": "Evaluate spacecraft manual control beyond low Earth orbit"},
    ])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Building Artemis II mission dataset...")

    # Trajectory
    df_traj = fetch_trajectory()
    check_dataset(df_traj, "artemis-ii", min_rows=500,
                  expected_columns=["epoch_tdb", "x_km", "y_km", "z_km",
                                    "distance_earth_km", "distance_moon_km"],
                  critical_columns=["epoch_tdb", "x_km"])

    # Static tables
    df_crew = build_crew_df()
    df_timeline = build_timeline_df()
    df_payloads = build_payloads_df()

    # Stats
    n_vectors = len(df_traj)
    date_min = df_traj["epoch_tdb"].min().strftime("%Y-%m-%d %H:%M")
    date_max = df_traj["epoch_tdb"].max().strftime("%Y-%m-%d %H:%M")
    max_earth_dist = df_traj["distance_earth_km"].max()
    min_moon_dist = df_traj["distance_moon_km"].min()
    max_speed = df_traj["speed_km_s"].max()
    closest_approach_time = df_traj.loc[df_traj["distance_moon_km"].idxmin(), "epoch_tdb"]

    print(f"  Trajectory: {n_vectors} vectors ({date_min} to {date_max})")
    print(f"  Max distance from Earth: {max_earth_dist:,.0f} km")
    print(f"  Closest lunar approach: {min_moon_dist:,.0f} km at {closest_approach_time}")
    print(f"  Max speed: {max_speed:.2f} km/s")
    print(f"  Timeline: {len(df_timeline)} events")
    print(f"  Crew: {len(df_crew)} members")
    print(f"  Payloads: {len(df_payloads)} items")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        df_traj.to_parquet(data_dir / "trajectory.parquet", index=False,
                           engine="pyarrow", compression="zstd")
        df_crew.to_parquet(data_dir / "crew.parquet", index=False,
                           engine="pyarrow", compression="zstd")
        df_timeline.to_parquet(data_dir / "timeline.parquet", index=False,
                               engine="pyarrow", compression="zstd")
        df_payloads.to_parquet(data_dir / "payloads.parquet", index=False,
                               engine="pyarrow", compression="zstd")

        banner_file = download_banner("artemis-ii", tmp)
        banner_md = banner_markdown("artemis-ii", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Artemis II Mission Data"
language:
  - en
description: "NASA Artemis II crewed lunar flyby mission: trajectory state vectors from JPL Horizons, crew manifest, mission timeline, and payload inventory."
task_categories:
  - time-series-forecasting
  - tabular-regression
tags:
  - space
  - artemis
  - nasa
  - moon
  - lunar
  - orion
  - trajectory
  - orbital-mechanics
  - sls
  - deep-space
  - open-data
  - tabular-data
  - parquet
size_categories:
  - 1K<n<10K
configs:
  - config_name: trajectory
    data_files:
      - split: train
        path: data/trajectory.parquet
    default: true
  - config_name: crew
    data_files:
      - split: train
        path: data/crew.parquet
  - config_name: timeline
    data_files:
      - split: train
        path: data/timeline.parquet
  - config_name: payloads
    data_files:
      - split: train
        path: data/payloads.parquet
---

# Artemis II Mission Data
{banner_md}
*Part of the [Space Probe & Mission Datasets](https://huggingface.co/collections/juliensimon/space-probe-and-mission-datasets-69c3fe82d410a42b1e313167) collection on Hugging Face.*

![Update Artemis II](https://github.com/juliensimon/space-datasets/actions/workflows/update-artemis-ii.yml/badge.svg)

Comprehensive dataset for NASA's **Artemis II** mission — the first crewed flight beyond low Earth orbit since Apollo 17 (1972). Covers the ~10-day crewed lunar flyby aboard the Orion spacecraft *Integrity*, launched April 1, 2026 on SLS Block 1.

## Configs

This dataset has four configs (tables):

| Config | Records | Description |
|--------|---------|-------------|
| `trajectory` | **{n_vectors:,}** | State vectors at 10-min intervals (position, velocity, distances) |
| `timeline` | **{len(df_timeline)}** | Mission events from terminal countdown through splashdown |
| `crew` | **{len(df_crew)}** | Crew manifest with biographical data |
| `payloads` | **{len(df_payloads)}** | CubeSats and onboard experiments |

## Trajectory schema

Geocentric J2000 ecliptic state vectors from [JPL Horizons](https://ssd.jpl.nasa.gov/horizons/) (spacecraft ID `-1024`).

| Column | Type | Description |
|--------|------|-------------|
| `epoch_tdb` | datetime | Epoch in Barycentric Dynamical Time (TDB) |
| `x_km` | float | Geocentric X position (km, J2000 ecliptic) |
| `y_km` | float | Geocentric Y position (km) |
| `z_km` | float | Geocentric Z position (km) |
| `vx_km_s` | float | X velocity (km/s) |
| `vy_km_s` | float | Y velocity (km/s) |
| `vz_km_s` | float | Z velocity (km/s) |
| `distance_earth_km` | float | Distance from Earth center (km) |
| `speed_km_s` | float | Orbital speed (km/s) |
| `distance_moon_km` | float | Distance from Moon center (km) |
| `mission_phase` | string | Phase: earth_orbit, transit_outbound, lunar_approach, lunar_flyby, transit_return, entry |

## Quick stats

- **{n_vectors:,}** trajectory vectors ({date_min} to {date_max} TDB)
- Maximum distance from Earth: **{max_earth_dist:,.0f} km** ({max_earth_dist / 1.609:.0f} statute miles)
- Closest lunar approach: **{min_moon_dist:,.0f} km** at {closest_approach_time.strftime("%Y-%m-%d %H:%M")} TDB
- Maximum speed: **{max_speed:.2f} km/s** ({max_speed * 3600:.0f} km/h)
- Crew: **4** (3 NASA + 1 CSA) — first crewed mission beyond LEO in 54 years
- CubeSats: **4** secondary payloads from Germany, South Korea, Saudi Arabia, Argentina

## Usage

```python
from datasets import load_dataset

# Trajectory data (default config)
ds = load_dataset("juliensimon/artemis-ii", split="train")
df = ds.to_pandas()

# Plot distance from Moon over time
import matplotlib.pyplot as plt
plt.figure(figsize=(12, 4))
plt.plot(df["epoch_tdb"], df["distance_moon_km"])
plt.xlabel("Time (TDB)")
plt.ylabel("Distance from Moon (km)")
plt.title("Artemis II — Distance to Moon")
plt.tight_layout()
plt.show()

# Find closest lunar approach
idx = df["distance_moon_km"].idxmin()
print(f"Closest approach: {{df.loc[idx, 'distance_moon_km']:,.0f}} km at {{df.loc[idx, 'epoch_tdb']}}")

# Load other configs
crew = load_dataset("juliensimon/artemis-ii", "crew", split="train").to_pandas()
timeline = load_dataset("juliensimon/artemis-ii", "timeline", split="train").to_pandas()
payloads = load_dataset("juliensimon/artemis-ii", "payloads", split="train").to_pandas()
```

## Data source

- **Trajectory:** [JPL Horizons](https://ssd.jpl.nasa.gov/horizons/) — spacecraft `-1024` ("Integrity Orion EM-2"), geocentric and selenocentric vectors
- **Timeline & crew:** [NASA Artemis II Press Kit](https://www.nasa.gov/wp-content/uploads/2026/01/artemis-ii-press-kit.pdf) and [launch blog](https://www.nasa.gov/blogs/missions/2026/04/01/live-artemis-ii-launch-day-updates/)
- **Payload data:** NASA, DLR, KARI, KACST, CONAE public announcements

## Update schedule

Updated during the mission as JPL Horizons trajectory data is refined. Will switch to as-flown ephemeris after splashdown.

## Related datasets

- [space-track-tle-history](https://huggingface.co/datasets/juliensimon/space-track-tle-history) — Orbital element history for tracked objects
- [donki-space-weather-events](https://huggingface.co/datasets/juliensimon/donki-space-weather-events) — Space weather events (relevant for crew radiation exposure)
- [dst-index](https://huggingface.co/datasets/juliensimon/dst-index) — Geomagnetic storm index

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/artemis-ii) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{artemis_ii,
  author = {{Simon, Julien}},
  title = {{Artemis II Mission Data}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/artemis-ii}},
  note = {{Trajectory from JPL Horizons; mission data from NASA press kit}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", f"Update Artemis II: {n_vectors:,} trajectory vectors, "
             f"{len(df_timeline)} events, {len(df_crew)} crew"],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={n_vectors}\n")
    print("Done.")


if __name__ == "__main__":
    main()
