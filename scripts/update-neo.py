#!/usr/bin/env python3
"""Fetch NEO close-approach data from NASA JPL and upload to HF."""

import math
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests


CAD_API = "https://ssd-api.jpl.nasa.gov/cad.api"
HF_REPO = "juliensimon/neo-close-approaches"

AU_TO_LD = 389.17  # 1 AU in Lunar Distances


def estimate_diameter_m(h_mag, albedo):
    """Estimate diameter in meters from absolute magnitude and albedo."""
    if pd.isna(h_mag):
        return None
    return 1329_000 / math.sqrt(albedo) * 10 ** (-h_mag / 5)


def main():
    print("Fetching NEO close approaches from NASA JPL...")
    resp = requests.get(CAD_API, params={
        "date-min": "1900-01-01",
        "date-max": "2100-01-01",
        "dist-max": "0.05",
        "diameter": "true",
        "fullname": "true",
    }, timeout=120)
    resp.raise_for_status()
    payload = resp.json()

    df = pd.DataFrame(payload["data"], columns=payload["fields"])
    print(f"  {len(df):,} close approaches")

    # Type conversions
    for col in ["dist", "dist_min", "dist_max", "v_rel", "v_inf", "h"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["jd"] = pd.to_numeric(df["jd"], errors="coerce")
    df["cd"] = pd.to_datetime(df["cd"], format="%Y-%b-%d %H:%M", errors="coerce")
    df["diameter"] = pd.to_numeric(df["diameter"], errors="coerce")
    df["diameter_sigma"] = pd.to_numeric(df["diameter_sigma"], errors="coerce")

    # Rename
    df = df.rename(columns={
        "des": "designation",
        "jd": "close_approach_jd",
        "cd": "close_approach_date",
        "dist": "distance_au",
        "dist_min": "distance_min_au",
        "dist_max": "distance_max_au",
        "v_rel": "velocity_relative_kms",
        "v_inf": "velocity_infinity_kms",
        "t_sigma_f": "time_uncertainty",
        "h": "absolute_magnitude",
        "diameter": "diameter_km",
        "diameter_sigma": "diameter_sigma_km",
        "fullname": "full_name",
    })

    # Derived columns
    df["distance_ld"] = (df["distance_au"] * AU_TO_LD).round(4)
    df["estimated_diameter_min_m"] = df.apply(
        lambda r: estimate_diameter_m(r["absolute_magnitude"], 0.25)
        if pd.isna(r["diameter_km"]) else None, axis=1
    )
    df["estimated_diameter_max_m"] = df.apply(
        lambda r: estimate_diameter_m(r["absolute_magnitude"], 0.05)
        if pd.isna(r["diameter_km"]) else None, axis=1
    )
    df["is_pha"] = (df["absolute_magnitude"] <= 22) & (df["distance_min_au"] <= 0.05)

    # Round floats for cleaner parquet
    for col in ["distance_au", "distance_min_au", "distance_max_au",
                "velocity_relative_kms", "velocity_infinity_kms",
                "diameter_km", "diameter_sigma_km"]:
        df[col] = df[col].round(6)
    for col in ["estimated_diameter_min_m", "estimated_diameter_max_m"]:
        df[col] = df[col].round(1)

    n_past = int((df["close_approach_date"] <= pd.Timestamp.now()).sum())
    n_future = len(df) - n_past
    n_pha = int(df["is_pha"].sum())
    n_with_diameter = int(df["diameter_km"].notna().sum())
    year_min = int(df["close_approach_date"].dt.year.min())
    year_max = int(df["close_approach_date"].dt.year.max())
    closest = df.loc[df["distance_au"].idxmin()]

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "neo_close_approaches.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - asteroid
  - neo
  - planetary-defense
  - nasa
  - near-earth-object
size_categories:
  - 10K<n<100K
---

# Near-Earth Object Close Approaches

![Update NEO Close Approaches](https://github.com/juliensimon/space-datasets/actions/workflows/update-neo.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.neo&label=updated&color=brightgreen)

All close approaches of Near-Earth Objects (asteroids and comets) to Earth within 0.05 AU
(~7.5 million km), spanning **{year_min}** to **{year_max}**. Currently **{len(df):,}** recorded approaches
({n_past:,} past, {n_future:,} future predictions).

## Dataset description

This dataset contains every known close approach of a near-Earth object (NEO) to Earth,
computed by NASA's Center for Near-Earth Object Studies (CNEOS) at the Jet Propulsion
Laboratory. The data is recomputed continuously as new observations refine orbit
estimates and new asteroids are discovered.

Each record includes the closest-approach distance (with 3-sigma uncertainty bounds),
relative velocity, absolute magnitude, and — where available — measured diameter.
For objects without a measured diameter, we include estimates derived from
absolute magnitude using standard albedo assumptions.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `designation` | string | Primary designation (e.g. "433", "2024 YR4") |
| `orbit_id` | string | Orbit solution ID used for computation |
| `close_approach_jd` | float64 | Close-approach time (Julian Date, TDB) |
| `close_approach_date` | datetime | Close-approach date/time (UTC) |
| `distance_au` | float64 | Nominal approach distance (AU) |
| `distance_min_au` | float64 | Minimum possible distance, 3-sigma (AU) |
| `distance_max_au` | float64 | Maximum possible distance, 3-sigma (AU) |
| `distance_ld` | float64 | Nominal approach distance (Lunar Distances) |
| `velocity_relative_kms` | float64 | Velocity relative to Earth (km/s) |
| `velocity_infinity_kms` | float64 | V-infinity / hyperbolic excess velocity (km/s) |
| `time_uncertainty` | string | 3-sigma time uncertainty (e.g. "< 00:01" or "4_15:23") |
| `absolute_magnitude` | float64 | Absolute magnitude H (brightness proxy for size) |
| `diameter_km` | float64 | Measured diameter in km (null if unknown) |
| `diameter_sigma_km` | float64 | Diameter 1-sigma uncertainty in km |
| `full_name` | string | Full formatted name/designation |
| `estimated_diameter_min_m` | float64 | Estimated diameter (m) assuming albedo 0.25 (bright) |
| `estimated_diameter_max_m` | float64 | Estimated diameter (m) assuming albedo 0.05 (dark) |
| `is_pha` | bool | Potentially Hazardous Asteroid flag (H <= 22 and distance <= 0.05 AU) |

## Quick stats

- **{len(df):,}** close approaches ({year_min}--{year_max})
- **{n_pha:,}** involving Potentially Hazardous Asteroids
- **{n_with_diameter:,}** objects with measured diameters
- Closest recorded approach: **{closest['full_name'].strip()}** at **{closest['distance_ld']:.2f} LD** ({closest['distance_au']:.6f} AU)

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/neo-close-approaches", split="train")
df = ds.to_pandas()

# Upcoming close approaches sorted by distance
upcoming = df[df["close_approach_date"] > "2025-01-01"].sort_values("distance_au")

# Potentially hazardous approaches
pha = df[df["is_pha"] == True].sort_values("distance_au")

# Large objects (estimated > 100m) passing within 10 Lunar Distances
big_close = df[
    (df["estimated_diameter_max_m"] > 100) &
    (df["distance_ld"] < 10)
]

# Approaches per decade
df["decade"] = (df["close_approach_date"].dt.year // 10) * 10
by_decade = df.groupby("decade").size()
```

## Data source

[NASA JPL CNEOS SBDB Close-Approach Data API](https://ssd-api.jpl.nasa.gov/doc/cad.html).
Orbits are continuously refined as new astrometric observations are collected by surveys
like Catalina Sky Survey, Pan-STARRS, and ATLAS.

## Update schedule

Daily at 10:00 UTC via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [space-track-satcat](https://huggingface.co/datasets/juliensimon/space-track-satcat) — Full NORAD satellite catalog
- [space-track-tle-history](https://huggingface.co/datasets/juliensimon/space-track-tle-history) — 232M historical TLE records
- [space-launch-log](https://huggingface.co/datasets/juliensimon/space-launch-log) — Global launch history from GCAT
- [starlink-fleet-data](https://huggingface.co/datasets/juliensimon/starlink-fleet-data) — Daily Starlink constellation snapshots

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update NEO close approaches: {len(df):,} records"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    print("Done.")


if __name__ == "__main__":
    main()
