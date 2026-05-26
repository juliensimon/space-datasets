#!/usr/bin/env python3
"""Fetch NEO close-approach data from NASA JPL and upload to HF."""

import math
import time

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

CAD_API = "https://ssd-api.jpl.nasa.gov/cad.api"
HF_REPO = "juliensimon/neo-close-approaches"

AU_TO_LD = 389.17  # 1 AU in Lunar Distances

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "designation": "Primary designation of the NEO (e.g. '433', '2024 YR4'); assigned by the Minor Planet Center; numbered objects use their permanent number, unnumbered use provisional designation",
    "orbit_id": "Orbit solution ID used for the close-approach computation; identifies which JPL orbit fit was used; changes when new astrometric observations refine the orbit",
    "close_approach_jd": "Close-approach time in Julian Date (TDB timescale); precise epoch of closest geometric approach to Earth; used for orbital mechanics calculations",
    "close_approach_date": "Close-approach date and time in UTC; derived from the Julian Date for human-readable reference",
    "distance_au": "Nominal closest-approach distance to Earth in astronomical units (AU); 1 AU = 149.6 million km; computed from the best-fit orbit solution",
    "distance_min_au": "Minimum possible approach distance in AU at the 3-sigma confidence level; lower bound accounting for orbital uncertainty; tighter for well-observed objects",
    "distance_max_au": "Maximum possible approach distance in AU at the 3-sigma confidence level; upper bound accounting for orbital uncertainty",
    "distance_ld": "Nominal closest-approach distance in Lunar Distances (1 LD = 384,400 km); more intuitive scale for close approaches; the Moon orbits at 1.0 LD",
    "velocity_relative_kms": "Relative velocity of the NEO with respect to Earth at closest approach in km/s; determines kinetic energy of a potential impact; typical range 5-30 km/s",
    "velocity_infinity_kms": "Hyperbolic excess velocity (v-infinity) in km/s; the NEO's velocity relative to Earth at infinite distance; determines deflection mission requirements",
    "time_uncertainty": "3-sigma uncertainty in the close-approach time (e.g. '< 00:01' or '4_15:23' for days_hours:minutes); reflects how well the orbit is determined; large values indicate poorly constrained predictions",
    "absolute_magnitude": "Absolute magnitude H of the NEO; brightness at 1 AU from both Sun and observer at zero phase angle; proxy for size: H=18 ~ 1 km, H=22 ~ 140 m, H=25 ~ 40 m (size depends on unknown albedo)",
    "diameter_km": "Measured physical diameter in km from thermal IR (WISE/NEOWISE), radar, or occultation; null for the vast majority of NEOs; range from sub-km to tens of km",
    "diameter_sigma_km": "1-sigma uncertainty on the measured diameter in km; null when diameter itself is null",
    "full_name": "Full formatted name/designation including permanent number and name where assigned (e.g. '433 Eros (1898 DQ)'); provides the most complete identification string",
    "estimated_diameter_min_m": "Estimated minimum diameter in meters assuming a bright (albedo=0.25) S-type surface; computed from absolute magnitude when no measured diameter is available; null when measured diameter exists",
    "estimated_diameter_max_m": "Estimated maximum diameter in meters assuming a dark (albedo=0.05) C-type surface; computed from absolute magnitude when no measured diameter is available; null when measured diameter exists",
    "is_pha": "Potentially Hazardous Asteroid flag: True if absolute magnitude H <= 22 (roughly >= 140 m diameter) AND minimum approach distance <= 0.05 AU; these objects warrant continued monitoring",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
All close approaches of Near-Earth Objects (asteroids and comets) to Earth within 0.05 AU \
(~7.5 million km), spanning 1900 to 2100, from NASA JPL CNEOS. Updated daily.

This dataset contains every known close approach of a near-Earth object (NEO) to Earth, \
computed by NASA's Center for Near-Earth Object Studies (CNEOS) at the Jet Propulsion \
Laboratory. The data is recomputed continuously as new observations refine orbit estimates \
and new asteroids are discovered.

Each record includes the closest-approach distance (with 3-sigma uncertainty bounds), \
relative velocity, absolute magnitude, and -- where available -- measured diameter. For \
objects without a measured diameter, estimates derived from absolute magnitude using standard \
albedo assumptions are included.

Near-Earth objects are asteroids and comets whose orbits bring them within 1.3 AU of the Sun, \
placing them on trajectories that can intersect Earth's path. Close approaches within 0.05 AU \
(~19.5 lunar distances) are of particular interest for planetary defense. At these distances, \
gravitational perturbations from Earth can significantly alter an object's future orbit.

The distinction between past and predicted future approaches is scientifically important. \
Historical approaches are constrained by astrometric observations and have well-determined \
parameters. Future predictions depend on orbit propagation and degrade in accuracy over time, \
especially for small objects with short observation arcs or those subject to non-gravitational \
forces like the Yarkovsky effect.
"""


def estimate_diameter_m(h_mag, albedo):
    """Estimate diameter in meters from absolute magnitude and albedo."""
    if pd.isna(h_mag):
        return None
    return 1329_000 / math.sqrt(albedo) * 10 ** (-h_mag / 5)


def main():
    print("Fetching NEO close approaches from NASA JPL...")
    for attempt in range(4):
        try:
            resp = requests.get(CAD_API, params={
                "date-min": "1900-01-01",
                "date-max": "2100-01-01",
                "dist-max": "0.05",
                "diameter": "true",
                "fullname": "true",
            }, timeout=120)
            resp.raise_for_status()
            break
        except Exception as e:
            if attempt == 3:
                raise
            wait = 15 * (2 ** attempt)
            print(f"  JPL API attempt {attempt + 1}/4 failed ({e}), retry in {wait}s")
            time.sleep(wait)
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

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_past = int((df["close_approach_date"] <= pd.Timestamp.now()).sum())
    n_future = n_total - n_past
    n_pha = int(df["is_pha"].sum())
    n_with_diameter = int(df["diameter_km"].notna().sum())
    year_min = int(df["close_approach_date"].dt.year.min())
    year_max = int(df["close_approach_date"].dt.year.max())
    closest = df.loc[df["distance_au"].idxmin()]

    quick_stats = f"""\
- **{n_total:,}** close approaches ({year_min}--{year_max})
- **{n_past:,}** past, **{n_future:,}** future predictions
- **{n_pha:,}** involving Potentially Hazardous Asteroids
- **{n_with_diameter:,}** objects with measured diameters
- Closest recorded approach: **{closest['full_name'].strip()}** at **{closest['distance_ld']:.2f} LD** ({closest['distance_au']:.6f} AU)"""

    usage = """\
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
import matplotlib.pyplot as plt
df["decade"] = (df["close_approach_date"].dt.year // 10) * 10
by_decade = df.groupby("decade").size()
by_decade.plot(kind="bar")
plt.xlabel("Decade")
plt.ylabel("Number of close approaches")
plt.title("NEO Close Approaches per Decade")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Near-Earth Object Close Approaches",
        description=DESCRIPTION,
        tags=["space", "asteroid", "neo", "planetary-defense", "nasa",
              "near-earth-object", "open-data", "jpl", "cneos",
              "potentially-hazardous-asteroid", "tabular-data", "parquet"],
        source_url="https://ssd-api.jpl.nasa.gov/doc/cad.html",
        task_categories=["tabular-classification", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA25329/PIA25329~small.jpg",
            "alt": "NASA's DART spacecraft approaching the Didymos asteroid system",
            "credit": "NASA/Johns Hopkins APL",
        },
        related_datasets=[
            "juliensimon/sentry-impact-risk",
            "juliensimon/fireball-bolide-events",
            "juliensimon/jpl-small-body-database",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "close_approach_jd", "distance_au", "distance_min_au", "distance_max_au",
                "distance_ld", "velocity_relative_kms", "velocity_infinity_kms",
                "absolute_magnitude", "diameter_km", "diameter_sigma_km",
                "estimated_diameter_min_m", "estimated_diameter_max_m",
            ],
        )
        p.publish(
            df,
            filename="neo_close_approaches.parquet",
            min_rows=10000,
            expected_columns=["designation", "close_approach_date", "distance_au",
                              "velocity_relative_kms", "absolute_magnitude"],
            critical_columns=["designation", "close_approach_date", "distance_au"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update NEO close approaches: {n_total:,} records",
        )
    print("Done.")


if __name__ == "__main__":
    main()
