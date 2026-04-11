#!/usr/bin/env python3
"""Fetch NASA NHATS human-accessible asteroids and upload to HF."""

import pandas as pd

from hf_dataset_utils import Pipeline
from jpl_api import jpl_query

HF_REPO = "juliensimon/nhats-accessible-asteroids"

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "designation": "Primary MPC asteroid designation (e.g., '2021 PH27', '1999 AO10')",
    "full_name": "Full formatted name/designation including any IAU proper name",
    "n_viable_trajectories": "Total number of viable round-trip trajectory opportunities found by NHATS, counting all launch dates and mission profiles; higher = more scheduling flexibility",
    "observation_magnitude": "Observed visual magnitude at the time of discovery or most recent apparition; null when not available; fainter (larger) values indicate smaller or more distant objects",
    "orbit_condition_code": "MPC orbit uncertainty metric (0-9); 0 = well-determined multi-opposition orbit, 9 = very poorly constrained single-opposition arc; affects reliability of accessibility predictions",
    "max_diameter_m": "Estimated upper bound on effective diameter in meters, derived from absolute magnitude H and assumed minimum albedo; null when H magnitude is unavailable",
    "min_diameter_m": "Estimated lower bound on effective diameter in meters, derived from absolute magnitude H and assumed maximum albedo; null when H magnitude is unavailable",
    "min_delta_v_kms": "Minimum total delta-v (Earth departure + outbound transfer + return) for any viable round-trip trajectory in km/s; <6 km/s = energetically comparable to reaching the lunar surface; NHATS search limit is 12 km/s",
    "min_mission_duration_days": "Minimum total round-trip mission duration in days across all viable trajectories; NHATS search limit is 450 days; shorter durations preferred for crewed missions due to life support and radiation constraints",
    "obs_flag": "Observation flag from NHATS indicating whether the object is currently observable or has upcoming observing opportunities",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Near-Earth asteroids accessible for human space flight missions, from NASA JPL's \
NHATS study. Includes delta-v requirements and trajectory counts.

The NHATS study identifies near-Earth asteroids that could be reached by crewed \
spacecraft with relatively low delta-v (velocity change) requirements. These are \
potential targets for human exploration missions, sample return, and in-situ resource \
utilisation (ISRU).

Each asteroid in this dataset has at least one viable round-trip trajectory with \
total delta-v under 12 km/s, total mission duration under 450 days, and stay time \
of at least 8 days. The dataset is continuously updated as new asteroids are \
discovered and orbits are refined.

The delta-v requirement is the single most important metric for mission feasibility \
in space exploration. Unlike terrestrial travel where distance dominates cost, \
spaceflight cost scales with the velocity change needed to match orbits with a target. \
A round-trip delta-v under 6 km/s -- comparable to what is needed to reach the lunar \
surface and return -- makes an asteroid reachable with existing or near-term \
propulsion technology. The most accessible targets in this dataset have delta-v \
requirements below 5 km/s, making them energetically easier to reach than the Moon \
despite being millions of kilometers away.

Mission duration and the number of viable trajectories provide complementary \
selection criteria. A target with thousands of viable trajectories offers scheduling \
flexibility -- crucial for mission planning that must account for launch window \
constraints, spacecraft readiness, and orbital mechanics.

These asteroids are also prime candidates for in-situ resource utilization (ISRU) -- \
extracting water, metals, and volatiles from asteroid material to support deep-space \
operations. The combination of low delta-v accessibility and potential resource \
richness makes NHATS targets central to long-term plans for a sustained human \
presence beyond low Earth orbit.
"""


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

    # Rename columns
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

    df = df.rename(columns=rename_map)

    # Drop original nested columns if extracted
    for col in ["min_dv", "min_dur"]:
        if col in df.columns:
            df = df.drop(columns=[col])

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    df = df.reset_index(drop=True)

    # ── Domain-specific stats for README ─────────────────────────────
    n = len(df)
    mean_dv = df["min_delta_v_kms"].mean() if "min_delta_v_kms" in df.columns else 0
    min_dv = df["min_delta_v_kms"].min() if "min_delta_v_kms" in df.columns else 0
    n_low_dv = int((df["min_delta_v_kms"] < 6).sum()) if "min_delta_v_kms" in df.columns else 0

    quick_stats = f"""\
- **{n:,}** accessible asteroids
- Mean minimum delta-v: **{mean_dv:.2f}** km/s
- Lowest delta-v target: **{min_dv:.2f}** km/s
- **{n_low_dv}** targets with delta-v < 6 km/s"""

    usage = """\
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
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="NASA NHATS Near-Earth Accessible Asteroids",
        description=DESCRIPTION,
        tags=["space", "asteroid", "nhats", "nasa", "human-exploration",
              "delta-v", "open-data", "tabular-data", "parquet"],
        source_url="https://cneos.jpl.nasa.gov/nhats/",
        task_categories=["tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA17666/PIA17666~small.jpg",
            "alt": "Rosetta spacecraft approaching Comet 67P/Churyumov-Gerasimenko",
            "credit": "NASA/ESA",
        },
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "n_viable_trajectories", "observation_magnitude", "orbit_condition_code",
                "max_diameter_m", "min_diameter_m", "min_delta_v_kms",
                "min_mission_duration_days",
            ],
        )
        p.publish(
            df,
            filename="nhats_accessible_asteroids.parquet",
            min_rows=2000,
            expected_columns=["designation", "min_delta_v_kms", "n_viable_trajectories"],
            critical_columns=["designation", "min_delta_v_kms"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update NHATS accessible asteroids: {n:,} records",
        )
    print("Done.")


if __name__ == "__main__":
    main()
