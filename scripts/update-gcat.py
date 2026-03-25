#!/usr/bin/env python3
"""Fetch GCAT launch vehicles, engines, and stages, upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from validate import check_dataset


LV_URL = "https://planet4589.org/space/gcat/tsv/tables/lv.tsv"
ENGINES_URL = "https://planet4589.org/space/gcat/tsv/tables/engines.tsv"
STAGES_URL = "https://planet4589.org/space/gcat/tsv/tables/stages.tsv"
HF_REPO = "juliensimon/gcat-launch-vehicles"

LV_COLS = [
    "lv_name", "lv_family", "lv_manufacturer", "lv_variant", "lv_alias",
    "lv_min_stage", "lv_max_stage", "length_m", "length_flag", "diameter_m",
    "diameter_flag", "launch_mass_t", "mass_flag", "leo_capacity_kg",
    "gto_capacity_kg", "to_thrust_kn", "class", "apogee_km", "range",
]

ENGINE_COLS = [
    "name", "manufacturer", "family", "alt_name", "oxidizer", "fuel",
    "mass_kg", "mass_flag", "impulse", "impulse_flag", "thrust_kn",
    "thrust_flag", "isp_s", "isp_flag", "duration_s", "duration_flag",
    "chambers", "date", "usage", "group",
]

STAGE_COLS = [
    "stage_name", "stage_family", "stage_manufacturer", "stage_alt_name",
    "length_m", "diameter_m", "launch_mass_t", "dry_mass_kg", "thrust_kn",
    "duration_s", "engine", "n_engines",
]


def _fetch_tsv(url, col_names, label):
    """Fetch a GCAT TSV, assign column names, clean up."""
    print(f"Fetching {label}...")
    df = pd.read_csv(url, sep="\t", comment="#", names=col_names,
                     low_memory=False, skipinitialspace=True)
    # Strip whitespace from string columns
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].str.strip()
    # Replace GCAT dash placeholder with NaN
    df.replace("-", pd.NA, inplace=True)
    print(f"  {len(df):,} {label}")
    return df


def _coerce_numeric(df, columns):
    """Coerce columns to numeric, ignoring errors."""
    for col in columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")


def main():
    # ── Fetch ────────────────────────────────────────────────────────────
    vehicles = _fetch_tsv(LV_URL, LV_COLS, "launch vehicles")
    engines = _fetch_tsv(ENGINES_URL, ENGINE_COLS, "engines")
    stages = _fetch_tsv(STAGES_URL, STAGE_COLS, "stages")

    # ── Transform: coerce numeric columns ────────────────────────────────
    _coerce_numeric(vehicles, [
        "lv_min_stage", "lv_max_stage", "length_m", "diameter_m",
        "launch_mass_t", "leo_capacity_kg", "gto_capacity_kg",
        "to_thrust_kn", "apogee_km",
    ])
    _coerce_numeric(engines, [
        "mass_kg", "impulse", "thrust_kn", "isp_s", "duration_s", "chambers",
    ])
    _coerce_numeric(stages, [
        "length_m", "diameter_m", "launch_mass_t", "dry_mass_kg",
        "thrust_kn", "duration_s", "n_engines",
    ])

    # ── Validate ─────────────────────────────────────────────────────────
    total_rows = len(vehicles) + len(engines) + len(stages)

    check_dataset(vehicles, "vehicles", min_rows=500,
                  expected_columns=["lv_name", "lv_family", "lv_manufacturer", "class"],
                  critical_columns=["lv_name"])
    check_dataset(engines, "engines", min_rows=500,
                  expected_columns=["name", "manufacturer", "thrust_kn", "isp_s"],
                  critical_columns=["name"])
    check_dataset(stages, "stages", min_rows=500,
                  expected_columns=["stage_name", "stage_family", "engine", "n_engines"],
                  critical_columns=["stage_name"])

    # ── Write parquet + README ───────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        data_dir = tmp_dir / "data"
        data_dir.mkdir()
        vehicles.to_parquet(data_dir / "vehicles.parquet", index=False,
                            engine="pyarrow", compression="zstd")
        engines.to_parquet(data_dir / "engines.parquet", index=False,
                           engine="pyarrow", compression="zstd")
        stages.to_parquet(data_dir / "stages.parquet", index=False,
                          engine="pyarrow", compression="zstd")

        # Stats for README
        n_families = vehicles["lv_family"].nunique()
        n_manufacturers = vehicles["lv_manufacturer"].nunique()
        n_engine_groups = engines["group"].nunique() if "group" in engines.columns else 0

        (tmp_dir / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "GCAT Launch Vehicles and Engines"
language:
  - en
description: "Launch vehicle specs, rocket engines, and stage data from Jonathan McDowell's General Catalog of Artificial Space Objects (GCAT). {total_rows:,} records across three tables."
task_categories:
  - tabular-classification
tags:
  - space
  - rockets
  - launch-vehicles
  - engines
  - orbital-mechanics
  - open-data
  - gcat
  - tabular-data
configs:
  - config_name: vehicles
    data_files:
      - split: train
        path: data/vehicles.parquet
    default: true
  - config_name: engines
    data_files:
      - split: train
        path: data/engines.parquet
  - config_name: stages
    data_files:
      - split: train
        path: data/stages.parquet
size_categories:
  - 1K<n<10K
---

# GCAT Launch Vehicles and Engines

*Part of the [Orbital Mechanics Datasets](https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994) collection on Hugging Face.*

Launch vehicle specifications, rocket engines, and vehicle stages from
[GCAT](https://planet4589.org/space/gcat/) (General Catalog of Artificial Space Objects),
maintained by Jonathan McDowell at the Harvard-Smithsonian Center for Astrophysics.

Currently **{len(vehicles):,}** launch vehicles, **{len(engines):,}** engines, and
**{len(stages):,}** stages ({total_rows:,} records total).

## Configs

### `vehicles` — {len(vehicles):,} launch vehicles

Every known launch vehicle variant with physical specifications.

| Column | Type | Description |
|--------|------|-------------|
| `lv_name` | string | Launch vehicle name |
| `lv_family` | string | Vehicle family (e.g. "Falcon", "Soyuz") |
| `lv_manufacturer` | string | Manufacturer code |
| `lv_variant` | string | Variant designation |
| `lv_alias` | string | Alternative name |
| `lv_min_stage` | int | Minimum number of stages |
| `lv_max_stage` | int | Maximum number of stages |
| `length_m` | float | Vehicle length in meters |
| `length_flag` | string | Length qualifier flag |
| `diameter_m` | float | Vehicle diameter in meters |
| `diameter_flag` | string | Diameter qualifier flag |
| `launch_mass_t` | float | Launch mass in tonnes |
| `mass_flag` | string | Mass qualifier flag |
| `leo_capacity_kg` | float | LEO payload capacity in kg |
| `gto_capacity_kg` | float | GTO payload capacity in kg |
| `to_thrust_kn` | float | Takeoff thrust in kN |
| `class` | string | Vehicle class (O=orbital, R=research, etc.) |
| `apogee_km` | float | Design apogee in km |
| `range` | string | Range |

### `engines` — {len(engines):,} rocket engines

Rocket engine specifications including propellants, thrust, and specific impulse.

| Column | Type | Description |
|--------|------|-------------|
| `name` | string | Engine name |
| `manufacturer` | string | Manufacturer code |
| `family` | string | Engine family |
| `alt_name` | string | Alternative name |
| `oxidizer` | string | Oxidizer type |
| `fuel` | string | Fuel type |
| `mass_kg` | float | Engine mass in kg |
| `mass_flag` | string | Mass qualifier flag |
| `impulse` | float | Total impulse |
| `impulse_flag` | string | Impulse qualifier flag |
| `thrust_kn` | float | Thrust in kN |
| `thrust_flag` | string | Thrust qualifier flag |
| `isp_s` | float | Specific impulse in seconds |
| `isp_flag` | string | ISP qualifier flag |
| `duration_s` | float | Burn duration in seconds |
| `duration_flag` | string | Duration qualifier flag |
| `chambers` | float | Number of chambers |
| `date` | string | First use date |
| `usage` | string | Vehicle usage |
| `group` | string | Propellant group (Solid, Liquid, Hybrid, etc.) |

### `stages` — {len(stages):,} vehicle stages

Individual stage specifications for launch vehicles.

| Column | Type | Description |
|--------|------|-------------|
| `stage_name` | string | Stage name |
| `stage_family` | string | Stage family |
| `stage_manufacturer` | string | Manufacturer code |
| `stage_alt_name` | string | Alternative name |
| `length_m` | float | Stage length in meters |
| `diameter_m` | float | Stage diameter in meters |
| `launch_mass_t` | float | Stage mass at launch in tonnes |
| `dry_mass_kg` | float | Dry mass in kg |
| `thrust_kn` | float | Stage thrust in kN |
| `duration_s` | float | Burn duration in seconds |
| `engine` | string | Engine name |
| `n_engines` | float | Number of engines |

## Quick stats

- **{len(vehicles):,}** launch vehicle variants across **{n_families}** families
- **{len(engines):,}** engines from **{n_manufacturers}** manufacturers
- **{len(stages):,}** stage configurations
- **{n_engine_groups}** propellant groups (solid, liquid, hybrid, etc.)

## Usage

```python
from datasets import load_dataset

vehicles = load_dataset("juliensimon/gcat-launch-vehicles", "vehicles", split="train")
engines = load_dataset("juliensimon/gcat-launch-vehicles", "engines", split="train")
stages = load_dataset("juliensimon/gcat-launch-vehicles", "stages", split="train")

vdf = vehicles.to_pandas()

# Largest launch vehicles by mass
print(vdf.nlargest(10, "launch_mass_t")[["lv_name", "launch_mass_t", "leo_capacity_kg"]])

# Engines by specific impulse
edf = engines.to_pandas()
print(edf.nlargest(10, "isp_s")[["name", "fuel", "oxidizer", "isp_s", "thrust_kn"]])

# Orbital-class vehicles only
orbital = vdf[vdf["class"] == "O"]
print(f"{{len(orbital)}} orbital-class vehicles")
```

## Data source

[GCAT](https://planet4589.org/space/gcat/) (General Catalog of Artificial Space Objects)
by Jonathan McDowell, Harvard-Smithsonian Center for Astrophysics. GCAT is the most
comprehensive public catalog of space objects and launch vehicles, widely used in the
spaceflight research community.

## Update schedule

Static dataset — rebuilt manually when GCAT is updated (approximately monthly).

## Related datasets

- [space-launch-log](https://huggingface.co/datasets/juliensimon/space-launch-log) — Complete global launch history from GCAT
- [space-track-satcat](https://huggingface.co/datasets/juliensimon/space-track-satcat) — NORAD satellite catalog
- [starlink-fleet-data](https://huggingface.co/datasets/juliensimon/starlink-fleet-data) — Daily Starlink constellation snapshots

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Citation

```bibtex
@dataset{{gcat_launch_vehicles,
  author = {{Simon, Julien}},
  title = {{GCAT Launch Vehicles and Engines}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/gcat-launch-vehicles}},
  note = {{Based on GCAT by Jonathan McDowell, Harvard-Smithsonian Center for Astrophysics}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = (f"Update GCAT launch vehicles: {len(vehicles):,} vehicles, "
                      f"{len(engines):,} engines, {len(stages):,} stages")
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp_dir), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={total_rows}\n")
    print(f"Done. {total_rows:,} total rows.")


if __name__ == "__main__":
    main()
