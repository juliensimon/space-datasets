#!/usr/bin/env python3
"""Fetch NASA NHATS human-accessible asteroids and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from jpl_api import jpl_query
from validate import check_dataset


HF_REPO = "juliensimon/nhats-accessible-asteroids"


def main():
    print("Fetching NASA NHATS accessible asteroids...")
    payload = jpl_query("nhats.api")
    data = payload["data"]
    print(f"  {len(data):,} asteroids")

    df = pd.DataFrame(data)

    # Extract nested min_dv and min_dur values
    if "min_dv" in df.columns:
        df["min_delta_v_kms"] = df["min_dv"].apply(
            lambda x: x.get("dv") if isinstance(x, dict) else None
        )
    if "min_dur" in df.columns:
        df["min_mission_duration_days"] = df["min_dur"].apply(
            lambda x: x.get("dur") if isinstance(x, dict) else None
        )

    # Rename columns (guard all accesses)
    rename_map = {}
    if "des" in df.columns:
        rename_map["des"] = "designation"
    if "fullname" in df.columns:
        rename_map["fullname"] = "full_name"
    if "n_via_traj" in df.columns:
        rename_map["n_via_traj"] = "n_viable_trajectories"
    if "obs_mag" in df.columns:
        rename_map["obs_mag"] = "observation_magnitude"
    if "occ" in df.columns:
        rename_map["occ"] = "orbit_condition_code"
    if "max_size" in df.columns:
        rename_map["max_size"] = "max_diameter_m"
    if "min_size" in df.columns:
        rename_map["min_size"] = "min_diameter_m"
    if "obs_flag" in df.columns:
        rename_map["obs_flag"] = "obs_flag"

    df = df.rename(columns=rename_map)

    # Drop original nested columns if extracted
    for col in ["min_dv", "min_dur"]:
        if col in df.columns:
            df = df.drop(columns=[col])

    # Convert numeric columns
    for col in ["n_viable_trajectories", "observation_magnitude", "orbit_condition_code",
                "max_diameter_m", "min_diameter_m", "min_delta_v_kms",
                "min_mission_duration_days"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.reset_index(drop=True)

    check_dataset(df, "nhats", min_rows=2000,
                  expected_columns=["designation", "min_delta_v_kms", "n_viable_trajectories"],
                  critical_columns=["designation", "min_delta_v_kms"])

    # Stats for README
    n = len(df)
    mean_dv = df["min_delta_v_kms"].mean() if "min_delta_v_kms" in df.columns else 0
    min_dv = df["min_delta_v_kms"].min() if "min_delta_v_kms" in df.columns else 0
    n_low_dv = int((df["min_delta_v_kms"] < 6).sum()) if "min_delta_v_kms" in df.columns else 0

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "nhats_accessible_asteroids.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_kb = out.stat().st_size / 1024
        print(f"  {size_kb:.0f} KB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "NASA NHATS Near-Earth Accessible Asteroids"
language:
  - en
description: >-
  Near-Earth asteroids accessible for human space flight missions, from NASA JPL's
  NHATS study. Includes delta-v requirements and trajectory counts. Updated daily.
size_categories:
  - 1K<n<10K
task_categories:
  - tabular-regression
tags:
  - space
  - asteroid
  - nhats
  - nasa
  - human-exploration
  - delta-v
  - open-data
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/nhats_accessible_asteroids.parquet
---

# NASA NHATS Near-Earth Accessible Asteroids

![Update NHATS](https://github.com/juliensimon/space-datasets/actions/workflows/update-nhats.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.nhats&label=updated&color=brightgreen)

Near-Earth asteroids accessible for human missions, currently **{n:,}** objects from
NASA JPL's Near-Earth Object Human Space Flight Accessible Targets Study (NHATS).

## Dataset description

The NHATS study identifies near-Earth asteroids that could be reached by crewed
spacecraft with relatively low delta-v (velocity change) requirements. These are
potential targets for human exploration missions, sample return, and in-situ resource
utilisation (ISRU).

Each asteroid in this dataset has at least one viable round-trip trajectory with
total delta-v under 12 km/s, total mission duration under 450 days, and stay time
of at least 8 days. The dataset is continuously updated as new asteroids are
discovered and orbits are refined.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `designation` | string | Primary asteroid designation |
| `full_name` | string | Full formatted name/designation |
| `n_viable_trajectories` | int64 | Number of viable round-trip trajectories |
| `observation_magnitude` | float64 | Observed visual magnitude |
| `orbit_condition_code` | int64 | Orbit condition code (0=well-determined to 9=poorly) |
| `max_diameter_m` | float64 | Estimated maximum diameter (meters) |
| `min_diameter_m` | float64 | Estimated minimum diameter (meters) |
| `min_delta_v_kms` | float64 | Minimum total delta-v for round trip (km/s) |
| `min_mission_duration_days` | float64 | Minimum total mission duration (days) |

## Quick stats

- **{n:,}** accessible asteroids
- Mean minimum delta-v: **{mean_dv:.2f}** km/s
- Lowest delta-v target: **{min_dv:.2f}** km/s
- **{n_low_dv}** targets with delta-v < 6 km/s

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/nhats-accessible-asteroids", split="train")
df = ds.to_pandas()

# Easiest targets to reach
easy = df.nsmallest(20, "min_delta_v_kms")
print(easy[["designation", "min_delta_v_kms", "min_mission_duration_days", "n_viable_trajectories"]])

# Targets with many trajectory options
flexible = df.nlargest(20, "n_viable_trajectories")
print(flexible[["designation", "n_viable_trajectories", "min_delta_v_kms"]])

# Delta-v distribution
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(10, 5))
ax.hist(df["min_delta_v_kms"].dropna(), bins=50)
ax.set_xlabel("Min delta-v (km/s)")
ax.set_ylabel("Count")
ax.set_title("NHATS Asteroid Delta-v Distribution")
plt.show()
```

## Data source

[NASA JPL Near-Earth Object Human Space Flight Accessible Targets Study (NHATS)](https://cneos.jpl.nasa.gov/nhats/).

## Update schedule

Daily at 16:00 UTC via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Citation

```bibtex
@dataset{{nhats_accessible_asteroids,
  author = {{Simon, Julien}},
  title = {{NASA NHATS Near-Earth Accessible Asteroids}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/nhats-accessible-asteroids}},
  note = {{Based on NASA/JPL NHATS (Near-Earth Object Human Space Flight Accessible Targets Study)}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update NHATS accessible asteroids: {n:,} records"
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
