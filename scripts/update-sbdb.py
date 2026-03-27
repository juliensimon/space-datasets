#!/usr/bin/env python3
"""Fetch JPL Small-Body Database (all asteroids + comets) and upload to HF."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset


SBDB_API = "https://ssd-api.jpl.nasa.gov/sbdb_query.api"
HF_REPO = "juliensimon/jpl-small-body-database"

# Fields to request — covers orbital elements, physical parameters, and metadata

FIELDS = ",".join([
    "spkid", "full_name", "kind", "neo", "pha", "class",
    "e", "a", "i", "om", "w", "ma", "epoch", "per", "n", "tp", "q", "ad",
    "H", "diameter", "albedo", "spec_B", "spec_T",
    "rms", "data_arc", "n_obs_used", "condition_code",
    "moid", "moid_jup",
    "first_obs", "last_obs",
])


def fetch_small_bodies(kind: str) -> pd.DataFrame:
    """Fetch all small bodies of a given kind (a=asteroids, c=comets)."""
    label = "asteroids" if kind == "a" else "comets"
    print(f"  Fetching {label}...")

    resp = requests.get(SBDB_API, params={
        "fields": FIELDS,
        "sb-kind": kind,
        "full-prec": "false",
    }, timeout=600)
    resp.raise_for_status()

    payload = resp.json()
    df = pd.DataFrame(payload["data"], columns=payload["fields"])
    print(f"    {len(df):,} {label}")
    return df


def main():
    print("Fetching JPL Small-Body Database...")

    # Fetch asteroids and comets separately (API requires sb-kind filter)
    df_ast = fetch_small_bodies("a")
    df_com = fetch_small_bodies("c")
    df = pd.concat([df_ast, df_com], ignore_index=True)
    print(f"  Total: {len(df):,} small bodies")

    # Type conversions
    for col in ["e", "a", "i", "om", "w", "ma", "epoch", "per", "n", "tp",
                "q", "ad", "H", "diameter", "albedo", "rms", "moid", "moid_jup"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ["spkid", "data_arc", "n_obs_used", "condition_code"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    df["neo"] = df["neo"].map({"Y": True, "N": False})
    df["pha"] = df["pha"].map({"Y": True, "N": False})

    # Rename to descriptive snake_case
    df = df.rename(columns={
        "full_name": "full_name",
        "kind": "body_type",
        "class": "orbit_class",
        "e": "eccentricity",
        "a": "semi_major_axis_au",
        "i": "inclination_deg",
        "om": "ascending_node_deg",
        "w": "arg_perihelion_deg",
        "ma": "mean_anomaly_deg",
        "epoch": "epoch_jd",
        "per": "period_yr",
        "n": "mean_motion_deg_day",
        "tp": "perihelion_time_jd",
        "q": "perihelion_au",
        "ad": "aphelion_au",
        "H": "absolute_magnitude",
        "diameter": "diameter_km",
        "albedo": "geometric_albedo",
        "spec_B": "spectral_type_bus",
        "spec_T": "spectral_type_tholen",
        "rms": "orbit_rms",
        "data_arc": "data_arc_days",
        "n_obs_used": "n_observations",
        "moid": "moid_au",
        "moid_jup": "moid_jupiter_au",
        "first_obs": "first_observation",
        "last_obs": "last_observation",
    })

    # Clean string columns
    for col in ["full_name", "body_type", "orbit_class", "spectral_type_bus",
                "spectral_type_tholen"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
            )

    df = df.sort_values("spkid").reset_index(drop=True)

    # Stats
    n_total = len(df)
    n_ast = int((df["body_type"] == "an").sum() + (df["body_type"] == "au").sum()) if "body_type" in df.columns else len(df_ast)
    n_com = n_total - n_ast
    n_neo = int(df["neo"].sum()) if "neo" in df.columns else 0
    n_pha = int(df["pha"].sum()) if "pha" in df.columns else 0
    n_with_diameter = int(df["diameter_km"].notna().sum())
    n_with_albedo = int(df["geometric_albedo"].notna().sum())
    n_with_spectral = int(df["spectral_type_bus"].notna().sum() + df["spectral_type_tholen"].notna().sum())

    check_dataset(df, "sbdb", min_rows=1_200_000,
        expected_columns=["spkid", "full_name", "eccentricity", "semi_major_axis_au",
                          "inclination_deg", "absolute_magnitude", "neo", "pha"],
        critical_columns=["spkid", "eccentricity", "semi_major_axis_au"])

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "small_bodies.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "JPL Small-Body Database"
language:
  - en
description: "Complete catalog of all known asteroids and comets — {n_total:,} small bodies with orbital elements, physical parameters, and discovery metadata. Updated daily from NASA JPL."
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - asteroid
  - comet
  - orbital-mechanics
  - nasa
  - jpl
  - neo
  - near-earth-object
  - potentially-hazardous-asteroid
  - planetary-defense
  - open-data
  - tabular-data
size_categories:
  - 1M<n<10M
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/small_bodies.parquet
    default: true
---

# JPL Small-Body Database

*Part of the [Orbital Mechanics Datasets](https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994) collection on Hugging Face.*

![Update SBDB](https://github.com/juliensimon/space-datasets/actions/workflows/update-sbdb.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.sbdb&label=updated&color=brightgreen)

The complete catalog of every known small body in the Solar System — **{n_total:,}** asteroids
and comets with full orbital elements, physical parameters, and discovery metadata from
NASA's Jet Propulsion Laboratory.

## Dataset description

The JPL Small-Body Database (SBDB) is the authoritative source for orbital and physical
data on all known asteroids, comets, and other small bodies. It is maintained by the
Solar System Dynamics group at NASA's Jet Propulsion Laboratory and continuously updated
as new observations refine orbit solutions and new objects are discovered.

This dataset includes orbital elements (osculating Keplerian elements at a reference epoch),
physical properties (absolute magnitude, diameter, albedo, spectral type where measured),
and metadata (observation arc, number of observations, orbit uncertainty). It covers
numbered and unnumbered asteroids, periodic and non-periodic comets.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `spkid` | int64 | SPK-ID (unique JPL identifier) |
| `full_name` | string | Full designation (e.g. "1 Ceres", "433 Eros") |
| `body_type` | string | Body type code |
| `neo` | bool | Near-Earth Object flag |
| `pha` | bool | Potentially Hazardous Asteroid flag |
| `orbit_class` | string | Orbit classification (e.g. MBA, APO, AMO, ATE, COM) |
| `eccentricity` | float64 | Orbital eccentricity |
| `semi_major_axis_au` | float64 | Semi-major axis (AU) |
| `inclination_deg` | float64 | Orbital inclination (degrees) |
| `ascending_node_deg` | float64 | Longitude of ascending node (degrees) |
| `arg_perihelion_deg` | float64 | Argument of perihelion (degrees) |
| `mean_anomaly_deg` | float64 | Mean anomaly (degrees) |
| `epoch_jd` | float64 | Epoch of osculation (Julian Date, TDB) |
| `period_yr` | float64 | Orbital period (years) |
| `mean_motion_deg_day` | float64 | Mean motion (degrees/day) |
| `perihelion_time_jd` | float64 | Time of perihelion passage (JD, TDB) |
| `perihelion_au` | float64 | Perihelion distance (AU) |
| `aphelion_au` | float64 | Aphelion distance (AU) |
| `absolute_magnitude` | float64 | Absolute magnitude H |
| `diameter_km` | float64 | Diameter (km, null if unmeasured) |
| `geometric_albedo` | float64 | Geometric albedo (null if unmeasured) |
| `spectral_type_bus` | string | Bus-DeMeo spectral taxonomy |
| `spectral_type_tholen` | string | Tholen spectral taxonomy |
| `orbit_rms` | float64 | Orbit fit RMS residual |
| `data_arc_days` | int64 | Observation arc length (days) |
| `n_observations` | int64 | Number of observations used in orbit solution |
| `condition_code` | int64 | Orbit condition code (0=well-determined to 9=poorly) |
| `moid_au` | float64 | Minimum Orbit Intersection Distance with Earth (AU) |
| `moid_jupiter_au` | float64 | MOID with Jupiter (AU) |
| `first_observation` | string | Date of first observation |
| `last_observation` | string | Date of most recent observation |

## Quick stats

- **{n_total:,}** small bodies ({n_ast:,} asteroids, {n_com:,} comets)
- **{n_neo:,}** near-Earth objects (NEOs)
- **{n_pha:,}** potentially hazardous asteroids (PHAs)
- **{n_with_diameter:,}** with measured diameters
- **{n_with_albedo:,}** with measured albedos

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/jpl-small-body-database", split="train")
df = ds.to_pandas()

# Near-Earth Objects
neos = df[df["neo"] == True]
print(f"{{len(neos):,}} NEOs")

# Potentially Hazardous Asteroids close to Earth
phas = df[(df["pha"] == True) & (df["moid_au"] < 0.01)]

# Main Belt asteroids by orbit class
mba = df[df["orbit_class"] == "MBA"]
print(f"{{len(mba):,}} Main Belt asteroids")

# Orbital element distribution
import matplotlib.pyplot as plt
fig, axes = plt.subplots(1, 3, figsize=(15, 4))
axes[0].hist(df["semi_major_axis_au"].dropna().clip(0, 6), bins=200)
axes[0].set_xlabel("Semi-major axis (AU)")
axes[1].hist(df["eccentricity"].dropna(), bins=100)
axes[1].set_xlabel("Eccentricity")
axes[2].hist(df["inclination_deg"].dropna().clip(0, 60), bins=100)
axes[2].set_xlabel("Inclination (deg)")
plt.tight_layout()
```

## Data source

[NASA JPL Small-Body Database Query API](https://ssd-api.jpl.nasa.gov/doc/sbdb_query.html).
Maintained by the Solar System Dynamics group at JPL.

## Update schedule

Daily at 08:00 UTC via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [neo-close-approaches](https://huggingface.co/datasets/juliensimon/neo-close-approaches) — NEO close approach predictions
- [sentry-impact-risk](https://huggingface.co/datasets/juliensimon/sentry-impact-risk) — Earth impact risk assessment
- [fireball-bolide-events](https://huggingface.co/datasets/juliensimon/fireball-bolide-events) — Atmospheric impact events
- [space-track-satcat](https://huggingface.co/datasets/juliensimon/space-track-satcat) — NORAD satellite catalog

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/jpl-small-body-database) and share feedback in the Community tab!

## Citation

```bibtex
@dataset{{jpl_sbdb,
  author = {{Simon, Julien}},
  title = {{JPL Small-Body Database}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/jpl-small-body-database}},
  note = {{Based on NASA/JPL Small-Body Database (SSD)}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update JPL SBDB: {n_total:,} small bodies"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={n_total}\n")
    print("Done.")


if __name__ == "__main__":
    main()
