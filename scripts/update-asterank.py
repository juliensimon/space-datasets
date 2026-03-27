#!/usr/bin/env python3
"""Fetch Asterank asteroid mining economics data and upload to HF.

Static dataset — ~600K asteroids with estimated mining value, profit,
delta-v, spectral type, and orbital parameters from the Asterank project.
"""

import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset

API_URL = "http://www.asterank.com/api/asterank"
HF_REPO = "juliensimon/asterank-asteroid-mining"
MIN_ROWS = 400_000

# Columns to keep and their clean names
RENAME = {
    "full_name": "full_name",
    "name": "name",
    "pdes": "designation_number",
    "prov_des": "provisional_designation",
    "class": "orbit_class",
    "spec": "spectral_type_smassii",
    "spec_B": "spectral_type_bus",
    "spec_T": "spectral_type_tholen",
    "neo": "is_neo",
    "pha": "is_pha",
    "H": "absolute_magnitude",
    "G": "magnitude_slope",
    "diameter": "diameter_km",
    "diameter_sigma": "diameter_sigma_km",
    "albedo": "albedo",
    "extent": "extent_km",
    "rot_per": "rotation_period_h",
    "GM": "gm_km3_s2",
    "a": "semi_major_axis_au",
    "e": "eccentricity",
    "i": "inclination_deg",
    "om": "ascending_node_deg",
    "w": "argument_perihelion_deg",
    "ma": "mean_anomaly_deg",
    "q": "perihelion_au",
    "ad": "aphelion_au",
    "per_y": "orbital_period_yr",
    "n": "mean_motion_deg_day",
    "t_jup": "tisserand_jupiter",
    "moid": "earth_moid_au",
    "moid_ld": "earth_moid_ld",
    "moid_jup": "jupiter_moid_au",
    "epoch": "epoch_jd",
    "epoch_mjd": "epoch_mjd",
    "epoch_cal": "epoch_cal",
    "equinox": "equinox",
    "orbit_id": "orbit_solution_id",
    "condition_code": "orbit_condition_code",
    "data_arc": "data_arc_days",
    "n_obs_used": "n_obs_used",
    "first_obs": "first_obs_date",
    "last_obs": "last_obs_date",
    "rms": "orbit_rms",
    "price": "estimated_value_usd",
    "profit": "estimated_profit_usd",
    "closeness": "closeness_score",
    "score": "asterank_score",
    "saved": "saved",
    "BV": "color_index_bv",
    "UB": "color_index_ub",
    "spkid": "spkid",
}

# Columns that should be numeric
NUMERIC_COLS = [
    "absolute_magnitude", "magnitude_slope", "diameter_km", "diameter_sigma_km",
    "albedo", "rotation_period_h", "gm_km3_s2",
    "semi_major_axis_au", "eccentricity", "inclination_deg",
    "ascending_node_deg", "argument_perihelion_deg", "mean_anomaly_deg",
    "perihelion_au", "aphelion_au", "orbital_period_yr", "mean_motion_deg_day",
    "tisserand_jupiter", "earth_moid_au", "earth_moid_ld", "jupiter_moid_au",
    "epoch_jd", "epoch_mjd", "epoch_cal",
    "orbit_solution_id", "orbit_condition_code",
    "data_arc_days", "n_obs_used", "orbit_rms",
    "estimated_value_usd", "estimated_profit_usd",
    "closeness_score", "asterank_score", "saved",
    "color_index_bv", "color_index_ub", "spkid",
    "designation_number",
]

EXPECTED_COLS = [
    "full_name", "name", "designation_number", "orbit_class",
    "spectral_type_smassii", "absolute_magnitude",
    "diameter_km", "semi_major_axis_au", "eccentricity", "inclination_deg",
    "earth_moid_au", "estimated_value_usd", "estimated_profit_usd",
    "closeness_score", "asterank_score",
]

CRITICAL_COLS = [
    "full_name", "semi_major_axis_au", "eccentricity",
    "estimated_value_usd", "estimated_profit_usd",
]


def fetch_asterank(max_records=600_000, page_size=1000):
    """Fetch asteroid data from Asterank API with pagination.

    The API caps at 1,000 per request regardless of limit parameter.
    Paginate using offset until we get fewer than page_size results.
    """
    import time as _time
    print(f"Fetching up to {max_records:,} asteroids from Asterank API...")
    all_records = []
    offset = 0
    while offset < max_records:
        resp = requests.get(
            API_URL,
            params={"query": "{}", "limit": str(page_size), "offset": str(offset)},
            timeout=120,
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        all_records.extend(batch)
        offset += len(batch)
        if len(all_records) % 10_000 == 0 or len(batch) < page_size:
            print(f"  {len(all_records):,} records fetched...")
        if len(batch) < page_size:
            break
        _time.sleep(0.3)
    print(f"  Total: {len(all_records):,} records")
    return all_records


def transform(records):
    """Transform raw API records into a clean DataFrame."""
    df = pd.DataFrame(records)
    print(f"  Raw columns: {len(df.columns)}")

    # Drop MongoDB _id field if present
    if "_id" in df.columns:
        df = df.drop(columns=["_id"])

    # Keep only columns we have mappings for, skip missing ones
    available = [c for c in RENAME if c in df.columns]
    df = df[available].rename(columns=RENAME)

    # Convert numeric columns
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Convert boolean-like columns
    if "is_neo" in df.columns:
        df["is_neo"] = df["is_neo"].map({"Y": True, "N": False})
    if "is_pha" in df.columns:
        df["is_pha"] = df["is_pha"].map({"Y": True, "N": False})

    # Convert date columns
    for col in ["first_obs_date", "last_obs_date"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    # Clean string columns — replace empty strings with None
    str_cols = df.select_dtypes(include="object").columns
    for col in str_cols:
        df[col] = df[col].replace("", None)

    # Strip whitespace from name/full_name
    for col in ["full_name", "name", "provisional_designation"]:
        if col in df.columns:
            df[col] = df[col].str.strip()

    # Drop the 'saved' column — internal Asterank field, not useful
    if "saved" in df.columns:
        df = df.drop(columns=["saved"])

    # Sort by estimated value descending (most valuable first)
    df = df.sort_values("estimated_value_usd", ascending=False, na_position="last")
    df = df.reset_index(drop=True)

    return df


def main():
    records = fetch_asterank()
    df = transform(records)

    check_dataset(
        df,
        dataset_name="asterank",
        min_rows=MIN_ROWS,
        expected_columns=EXPECTED_COLS,
        critical_columns=CRITICAL_COLS,
    )

    # Stats for README
    n_total = len(df)
    n_neo = int(df["is_neo"].sum()) if "is_neo" in df.columns else 0
    n_pha = int(df["is_pha"].sum()) if "is_pha" in df.columns else 0
    n_with_diameter = int(df["diameter_km"].notna().sum())
    n_with_spectral = int(df["spectral_type_smassii"].notna().sum())

    top = df.head(1).iloc[0]
    top_name = top["full_name"] or top["name"] or str(top.get("designation_number", "?"))
    top_value = top["estimated_value_usd"]
    top_profit = top["estimated_profit_usd"]

    median_value = df["estimated_value_usd"].median()
    total_value = df["estimated_value_usd"].sum()

    orbit_classes = df["orbit_class"].nunique()

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "asterank_asteroid_mining.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet, {n_total:,} rows")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Asterank Asteroid Mining Economics"
language:
  - en
description: "Mining economics for ~600K asteroids: estimated value, profit, delta-v accessibility, spectral types, and orbital elements from the Asterank project."
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - asteroids
  - mining
  - economics
  - orbital-mechanics
  - open-data
  - tabular-data
size_categories:
  - 100K<n<1M
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/asterank_asteroid_mining.parquet
    default: true
---

# Asterank Asteroid Mining Economics

*Part of the [Orbital Mechanics Datasets](https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994) collection on Hugging Face.*

Economic analysis of **{n_total:,}** asteroids for space mining potential, combining NASA/JPL orbital data
with estimated accessibility and resource value from the [Asterank](https://asterank.com/) project.

## Dataset description

Asterank ranks nearly 600,000 cataloged asteroids by estimated mining profitability. It
combines multiple data sources -- NASA/JPL Small-Body Database orbital elements, spectral
classifications, and published scientific papers on asteroid composition -- to estimate each
asteroid's resource value and the cost of reaching it.

Key economic fields:
- **estimated_value_usd** -- total estimated resource value based on spectral type and size
- **estimated_profit_usd** -- value minus estimated mission cost (delta-v dependent)
- **closeness_score** -- accessibility metric (lower delta-v = higher closeness)
- **asterank_score** -- composite ranking combining value, profit, and accessibility

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `full_name` | string | Full formatted name (e.g. "1 Ceres") |
| `name` | string | IAU name if assigned (e.g. "Ceres") |
| `designation_number` | int | Permanent designation number |
| `provisional_designation` | string | Provisional designation (e.g. "2024 YR4") |
| `orbit_class` | string | Orbital class (MBA, APO, ATE, AMO, etc.) |
| `spectral_type_smassii` | string | SMASS II spectral classification |
| `spectral_type_bus` | string | Bus (Tholen-like) spectral classification |
| `spectral_type_tholen` | string | Tholen spectral classification |
| `is_neo` | bool | Near-Earth Object flag |
| `is_pha` | bool | Potentially Hazardous Asteroid flag |
| `absolute_magnitude` | float64 | Absolute magnitude H |
| `magnitude_slope` | float64 | Magnitude slope parameter G |
| `diameter_km` | float64 | Measured diameter (km) |
| `diameter_sigma_km` | float64 | Diameter uncertainty (km) |
| `albedo` | float64 | Geometric albedo |
| `extent_km` | string | Tri-axial extents (km) |
| `rotation_period_h` | float64 | Rotation period (hours) |
| `gm_km3_s2` | float64 | GM gravitational parameter (km^3/s^2) |
| `semi_major_axis_au` | float64 | Semi-major axis (AU) |
| `eccentricity` | float64 | Orbital eccentricity |
| `inclination_deg` | float64 | Orbital inclination (degrees) |
| `ascending_node_deg` | float64 | Longitude of ascending node (degrees) |
| `argument_perihelion_deg` | float64 | Argument of perihelion (degrees) |
| `mean_anomaly_deg` | float64 | Mean anomaly (degrees) |
| `perihelion_au` | float64 | Perihelion distance (AU) |
| `aphelion_au` | float64 | Aphelion distance (AU) |
| `orbital_period_yr` | float64 | Orbital period (years) |
| `mean_motion_deg_day` | float64 | Mean motion (degrees/day) |
| `tisserand_jupiter` | float64 | Tisserand parameter w.r.t. Jupiter |
| `earth_moid_au` | float64 | Minimum orbit intersection distance to Earth (AU) |
| `earth_moid_ld` | float64 | Earth MOID in Lunar Distances |
| `jupiter_moid_au` | float64 | Minimum orbit intersection distance to Jupiter (AU) |
| `estimated_value_usd` | float64 | Estimated total resource value (USD) |
| `estimated_profit_usd` | float64 | Estimated mining profit (USD) |
| `closeness_score` | float64 | Accessibility score (higher = easier to reach) |
| `asterank_score` | float64 | Composite Asterank ranking score |
| `orbit_condition_code` | float64 | JPL orbit condition code (0=best, 9=worst) |
| `data_arc_days` | float64 | Observation arc length (days) |
| `n_obs_used` | float64 | Number of observations used in orbit fit |
| `first_obs_date` | datetime | Date of first observation |
| `last_obs_date` | datetime | Date of last observation |
| `orbit_rms` | float64 | Orbit fit RMS residual |
| `color_index_bv` | float64 | B-V color index |
| `color_index_ub` | float64 | U-B color index |

## Quick stats

- **{n_total:,}** asteroids ranked by mining economics
- **{n_neo:,}** Near-Earth Objects, **{n_pha:,}** Potentially Hazardous
- **{n_with_diameter:,}** with measured diameters, **{n_with_spectral:,}** with spectral types
- **{orbit_classes}** distinct orbital classes
- Most valuable: **{top_name}** at **${top_value:,.0f}** (profit: ${top_profit:,.0f})
- Median estimated value: **${median_value:,.0f}**
- Total estimated value of all asteroids: **${total_value:,.0f}**

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/asterank-asteroid-mining", split="train")
df = ds.to_pandas()

# Top 20 most profitable asteroids
top_profit = df.nlargest(20, "estimated_profit_usd")[
    ["full_name", "orbit_class", "spectral_type_smassii",
     "estimated_value_usd", "estimated_profit_usd", "earth_moid_au"]
]

# Near-Earth asteroids sorted by profit
neo_mining = df[df["is_neo"] == True].nlargest(50, "estimated_profit_usd")

# Value distribution by orbit class
by_class = df.groupby("orbit_class")["estimated_value_usd"].agg(["count", "median", "sum"])
by_class = by_class.sort_values("sum", ascending=False)

# Accessible targets: low MOID + high profit
accessible = df[
    (df["earth_moid_au"] < 0.1) &
    (df["estimated_profit_usd"] > 1e9)
].sort_values("estimated_profit_usd", ascending=False)
```

## Data source

[Asterank](https://asterank.com/) by Ian Webster, combining data from NASA/JPL Small-Body
Database, spectral survey data, and published asteroid composition models.

## Related datasets

- [neo-close-approaches](https://huggingface.co/datasets/juliensimon/neo-close-approaches) -- NEO close approaches from NASA JPL
- [space-track-satcat](https://huggingface.co/datasets/juliensimon/space-track-satcat) -- Full NORAD satellite catalog
- [space-launch-log](https://huggingface.co/datasets/juliensimon/space-launch-log) -- Global launch history

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/asterank-asteroid-mining) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{asterank_mining,
  author = {{Simon, Julien}},
  title = {{Asterank Asteroid Mining Economics}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/asterank-asteroid-mining}},
  note = {{Based on Asterank (asterank.com) asteroid mining economics data}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Upload Asterank asteroid mining economics: {n_total:,} asteroids"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    print(f"rows={n_total}")
    print("Done.")


if __name__ == "__main__":
    main()
