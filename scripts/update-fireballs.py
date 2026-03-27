#!/usr/bin/env python3
"""Fetch fireball/bolide data from NASA JPL CNEOS and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from jpl_api import jpl_query, jpl_fields_data_to_df
from validate import check_dataset


HF_REPO = "juliensimon/fireball-bolide-events"


def main():
    print("Fetching fireball/bolide events from NASA JPL CNEOS...")
    payload = jpl_query("fireball.api", params={"limit": "9999"})

    df = jpl_fields_data_to_df(payload)
    print(f"  {len(df):,} events")

    # Rename columns to snake_case
    df = df.rename(columns={
        "date": "datetime",
        "energy": "radiated_energy_j",
        "impact-e": "impact_energy_kt",
        "lat": "latitude",
        "lat-dir": "lat_direction",
        "lon": "longitude",
        "lon-dir": "lon_direction",
        "alt": "altitude_km",
        "vel": "velocity_kms",
        "vx": "vx_kms",
        "vy": "vy_kms",
        "vz": "vz_kms",
    })

    # Type conversions
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    for col in ["radiated_energy_j", "impact_energy_kt", "latitude", "longitude",
                "altitude_km", "velocity_kms", "vx_kms", "vy_kms", "vz_kms"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Create signed latitude/longitude
    if "lat_direction" in df.columns:
        df["latitude"] = df.apply(
            lambda r: -r["latitude"] if r["lat_direction"] == "S" else r["latitude"],
            axis=1,
        )
    if "lon_direction" in df.columns:
        df["longitude"] = df.apply(
            lambda r: -r["longitude"] if r["lon_direction"] == "W" else r["longitude"],
            axis=1,
        )

    df = df.sort_values("datetime").reset_index(drop=True)

    check_dataset(df, "fireballs", min_rows=500,
                  expected_columns=["datetime", "latitude", "longitude", "impact_energy_kt"],
                  critical_columns=["datetime", "latitude", "longitude"])

    # Stats for README
    n = len(df)
    date_min = df["datetime"].min().strftime("%Y-%m-%d")
    date_max = df["datetime"].max().strftime("%Y-%m-%d")
    max_energy = df["impact_energy_kt"].max()
    n_with_energy = int(df["impact_energy_kt"].notna().sum())
    n_with_coords = int(df["latitude"].notna().sum())

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "fireball_bolide_events.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_kb = out.stat().st_size / 1024
        print(f"  {size_kb:.0f} KB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Fireball and Bolide Events"
language:
  - en
description: >-
  Atmospheric impact events (fireballs and bolides) detected by US government
  sensors, from NASA JPL CNEOS. Updated weekly.
size_categories:
  - 1K<n<10K
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - fireball
  - bolide
  - meteor
  - impact
  - nasa
  - planetary-defense
  - open-data
  - tabular-data
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/fireball_bolide_events.parquet
---

# Fireball and Bolide Events

*Part of the [Orbital Mechanics Datasets](https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994) collection on Hugging Face.*

![Update Fireballs](https://github.com/juliensimon/space-datasets/actions/workflows/update-fireballs.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.fireballs&label=updated&color=brightgreen)

Atmospheric impact events (fireballs and bolides) detected by US government sensors,
spanning **{date_min}** to **{date_max}**. Currently **{n:,}** recorded events.

## Dataset description

This dataset contains every fireball (bolide) event reported by US government sensors
and published by NASA's Center for Near-Earth Object Studies (CNEOS) at the Jet
Propulsion Laboratory. Each record includes the date/time, geographic coordinates,
altitude, velocity, velocity components, radiated energy, and estimated total
impact energy.

Fireballs are exceptionally bright meteors caused by small asteroids or large
meteoroids entering the atmosphere at high speed. The largest events can release
energy equivalent to tens or hundreds of kilotons of TNT.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `datetime` | datetime | Date and time of peak brightness (UTC) |
| `radiated_energy_j` | float64 | Total radiated energy (joules x10^10) |
| `impact_energy_kt` | float64 | Estimated total impact energy (kilotons of TNT) |
| `latitude` | float64 | Latitude (positive = N, negative = S) |
| `lat_direction` | string | Original latitude direction (N/S) |
| `longitude` | float64 | Longitude (positive = E, negative = W) |
| `lon_direction` | string | Original longitude direction (E/W) |
| `altitude_km` | float64 | Altitude at peak brightness (km) |
| `velocity_kms` | float64 | Velocity at peak brightness (km/s) |
| `vx_kms` | float64 | Velocity component Vx (km/s, ECEF) |
| `vy_kms` | float64 | Velocity component Vy (km/s, ECEF) |
| `vz_kms` | float64 | Velocity component Vz (km/s, ECEF) |

## Quick stats

- **{n:,}** fireball events ({date_min} to {date_max})
- **{n_with_energy}** events with measured impact energy
- **{n_with_coords}** events with geographic coordinates
- Largest impact energy: **{max_energy:.1f} kt**

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/fireball-bolide-events", split="train")
df = ds.to_pandas()

# High-energy events (> 1 kiloton)
big = df[df["impact_energy_kt"] > 1].sort_values("impact_energy_kt", ascending=False)
print(big[["datetime", "impact_energy_kt", "latitude", "longitude"]])

# Plot events on a map
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(12, 6))
coords = df.dropna(subset=["latitude", "longitude"])
ax.scatter(coords["longitude"], coords["latitude"],
           s=coords["impact_energy_kt"].fillna(0.1) * 5, alpha=0.5)
ax.set_xlabel("Longitude")
ax.set_ylabel("Latitude")
ax.set_title("Fireball Events by Location and Energy")
plt.show()
```

## Data source

[NASA JPL Center for Near Earth Object Studies (CNEOS) Fireball API](https://cneos.jpl.nasa.gov/fireballs/).
Data from US government sensors; geographic coordinates and velocity components
may be absent for some events.

## Update schedule

Weekly on Monday at 12:00 UTC via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [neo-close-approaches](https://huggingface.co/datasets/juliensimon/neo-close-approaches) -- NEO close approaches to Earth
- [sentry-impact-risk](https://huggingface.co/datasets/juliensimon/sentry-impact-risk) -- Sentry impact risk assessments

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/fireball-bolide-events) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{fireball_bolide_events,
  author = {{Simon, Julien}},
  title = {{Fireball and Bolide Events}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/fireball-bolide-events}},
  note = {{Based on NASA/JPL Center for Near Earth Object Studies (CNEOS) fireball data}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update fireball/bolide events: {n:,} records"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={n}\n")
    print("Done.")


if __name__ == "__main__":
    main()
