#!/usr/bin/env python3
"""Fetch JPL Small-Body Database (all asteroids + comets) and upload to HF."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd
import requests

from dataset_images import banner_markdown, download_banner
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

        banner_file = download_banner("sbdb", tmp)
        banner_md = banner_markdown("sbdb", banner_file)

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
  - parquet
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
{banner_md}
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

The six Keplerian orbital elements in this dataset -- semimajor axis, eccentricity, inclination, longitude of ascending node, argument of perihelion, and mean anomaly -- define each object's instantaneous orbit at the reference epoch. These osculating elements change over time due to gravitational perturbations from the planets, so they represent a snapshot rather than a permanent orbit. The condition code (0 through 9) quantifies how well-determined the orbit is: objects with decades of observations and hundreds of astrometric measurements receive a 0, while single-apparition objects with short arcs may have codes of 7 or higher. The orbit fit RMS indicates the residual scatter between predicted and observed positions, typically a fraction of an arcsecond for well-observed objects.

The physical parameters -- absolute magnitude H, diameter, albedo, and spectral type -- are far sparser than the orbital data. Fewer than 2% of known asteroids have directly measured diameters (primarily from thermal infrared surveys like WISE/NEOWISE, radar observations, or stellar occultations). Absolute magnitude serves as a proxy for size but depends on the unknown albedo: a bright, reflective S-type asteroid and a dark, carbonaceous C-type asteroid with identical H values can differ in diameter by a factor of two or more. The two spectral taxonomy columns (Bus-DeMeo and Tholen systems) encode surface composition information derived from visible and near-infrared reflectance spectroscopy, available for only a few thousand objects.

The Minimum Orbit Intersection Distance (MOID) columns are critical for hazard assessment. Earth MOID measures the closest possible geometric approach between two orbits, independent of where the objects actually are at any given time. An asteroid is classified as a Potentially Hazardous Asteroid (PHA) if its Earth MOID is below 0.05 AU and its absolute magnitude is 22.0 or brighter (roughly 140 meters in diameter assuming typical albedos). The Jupiter MOID is relevant for understanding dynamical evolution, as close encounters with Jupiter are the primary mechanism driving objects from the main belt into near-Earth space.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `spkid` | int64 | JPL SPK kernel ID; primary unique identifier for this body in all JPL systems (e.g. 2000001 = Ceres) |
| `full_name` | string | Full designation including permanent number and name where assigned (e.g. "1 Ceres", "433 Eros", "2024 YR4"); provisional designations follow MPC format |
| `body_type` | string | Body type code: `an` = numbered asteroid, `au` = unnumbered asteroid, `cn` = numbered comet, `cu` = unnumbered comet |
| `neo` | bool | True if orbit comes within 1.3 AU of the Sun (Near-Earth Object); False otherwise; null for some comets |
| `pha` | bool | True if potentially hazardous: absolute magnitude H ≤ 22.0 (roughly ≥140 m diameter) AND Earth MOID ≤ 0.05 AU; False otherwise |
| `orbit_class` | string | Dynamical orbit class: MBA (Main Belt), APO (Apollo, a≥1 AU, q<1.017 AU), AMO (Amor, 1.017<q<1.3 AU), ATE (Aten, a<1 AU), IEO (Atira, Q<0.983 AU), TNO (trans-Neptunian), COM (comet), and others |
| `eccentricity` | float64 | Orbital eccentricity: 0 = circular, <1 = elliptical (all bound asteroids), ≈1 = parabolic, >1 = hyperbolic; main-belt asteroids typically 0.05–0.35 |
| `semi_major_axis_au` | float64 | Semi-major axis in AU: main belt 2.0–3.3, NEAs <2.0, TNOs >30, Jupiter Trojans ≈5.2; null for some long-period comets with open orbits |
| `inclination_deg` | float64 | Orbital inclination relative to the ecliptic plane in degrees (0–180°); main belt 0–30°, retrograde comets >90°; high inclination suggests scattered disk or Oort Cloud origin |
| `ascending_node_deg` | float64 | Longitude of ascending node in degrees (0–360°); angle from vernal equinox to where orbit crosses the ecliptic northward; one of the six Keplerian elements |
| `arg_perihelion_deg` | float64 | Argument of perihelion in degrees (0–360°); angle from ascending node to perihelion point; one of the six Keplerian elements |
| `mean_anomaly_deg` | float64 | Mean anomaly in degrees (0–360°) at the reference epoch; angular position in the orbit assuming uniform angular speed; used with other elements to compute position at any time |
| `epoch_jd` | float64 | Reference epoch of the osculating elements in Julian Date (TDB timescale); typically near the center of the observation arc |
| `period_yr` | float64 | Orbital period in years, derived from semi-major axis via Kepler's third law; null for open (parabolic/hyperbolic) orbits; main belt: 3–6 yr, TNOs: decades |
| `mean_motion_deg_day` | float64 | Mean motion in degrees per day, the average angular speed around the Sun; inversely related to orbital period; main belt: ~0.3–1.0 deg/day |
| `perihelion_time_jd` | float64 | Time of most recent (or predicted next) perihelion passage in Julian Date (TDB); used for comet position predictions and close-approach timing |
| `perihelion_au` | float64 | Perihelion distance in AU (closest approach to the Sun); NEAs have q < 1.3 AU; sungrazing comets q < 0.01 AU; main belt q ≈ 1.5–2.5 AU |
| `aphelion_au` | float64 | Aphelion distance in AU (farthest point from the Sun); null for open orbits; main belt Q ≈ 2.5–4.5 AU; Jupiter-crossing objects Q ≈ 5 AU |
| `absolute_magnitude` | float64 | Absolute magnitude H (brightness at 1 AU from Sun and observer, zero phase angle); size proxy: H=18 ≈ 1 km, H=22 ≈ 140 m, H=25 ≈ 40 m; actual size depends on unknown albedo |
| `diameter_km` | float64 | Physical diameter in km measured from thermal IR (WISE/NEOWISE), radar, or occultation; null for >98% of objects; range from sub-km (most numbered) to 939 km (Ceres) |
| `geometric_albedo` | float64 | Geometric albedo: fraction of sunlight reflected at zero phase angle (0–1); S-type (silicate): 0.15–0.35; C-type (carbonaceous): 0.03–0.10; null for most objects; used with H to estimate diameter |
| `spectral_type_bus` | string | Taxonomic class in the Bus-DeMeo (2009) visible/near-IR reflectance system (e.g. S, C, X, B, D, V); null for objects without spectral observations; available for only ~10,000 objects |
| `spectral_type_tholen` | string | Taxonomic class in the Tholen (1984) ECAS broadband photometry system (e.g. S, C, M, E, R, V, D); older classification; null for most objects |
| `orbit_rms` | float64 | RMS residual of the orbit fit in arcseconds; measures scatter between predicted and observed astrometric positions; typically <0.5" for well-observed objects; higher values suggest a poor fit or unresolved systematic errors |
| `data_arc_days` | int64 | Span of the observation arc in days from first to last used observation; longer arcs produce more reliable orbits; newly discovered objects may have arcs of days; well-studied ones have arcs of decades |
| `n_observations` | int64 | Number of individual astrometric observations used in the orbit solution; more observations generally reduce orbital uncertainty |
| `condition_code` | int64 | JPL orbit uncertainty code 0–9: 0 = well-determined orbit (decades of observations), 9 = very poorly constrained (short arc, few observations); codes ≥7 indicate orbits that may change significantly with new data |
| `moid_au` | float64 | Minimum Orbit Intersection Distance with Earth in AU; the closest possible geometric approach between the two orbits regardless of current positions; <0.05 AU is the PHA threshold; <0.001 AU (~150,000 km) indicates potential close-approach risk |
| `moid_jupiter_au` | float64 | Minimum Orbit Intersection Distance with Jupiter in AU; low values indicate dynamical interaction potential; close encounters with Jupiter are the primary mechanism for injecting main-belt objects into near-Earth space |
| `first_observation` | string | Date of the oldest astrometric observation included in the orbit solution (YYYY-MM-DD) |
| `last_observation` | string | Date of the most recent astrometric observation included in the orbit solution (YYYY-MM-DD) |

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

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/jpl-small-body-database) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

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
