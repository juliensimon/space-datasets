#!/usr/bin/env python3
"""Fetch MPC comet orbital elements and upload to HF."""

import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset

SOURCE_URL = "https://www.minorplanetcenter.net/iau/MPCORB/CometEls.txt"
HF_REPO = "juliensimon/mpc-comet-elements"


def parse_comet_line(line: str) -> dict | None:
    """Parse one fixed-width line from CometEls.txt.

    Format: MPC Ephemerides and Orbital Elements format.
    Reference: https://www.minorplanetcenter.net/iau/info/CometOrbitFormat.html
    """
    if len(line.strip()) < 100:
        return None

    try:
        # Columns are 1-indexed in the MPC spec; Python slicing is 0-indexed.
        num_str = line[0:4].strip()
        orbit_type = line[4:5].strip()
        packed_desig = line[5:12].strip()

        # Perihelion date components
        peri_year = line[14:18].strip()
        peri_month = line[19:21].strip()
        peri_day = line[22:29].strip()

        perihelion_distance_au = line[30:39].strip()
        eccentricity = line[41:49].strip()

        arg_perihelion_deg = line[51:59].strip()
        lon_asc_node_deg = line[61:69].strip()
        inclination_deg = line[71:79].strip()

        # Epoch (perturbed solutions)
        epoch_year = line[81:85].strip()
        epoch_month = line[85:87].strip()
        epoch_day = line[87:89].strip()

        abs_magnitude_h = line[91:95].strip()
        slope_param_g = line[96:100].strip()

        name = line[102:158].strip()
        reference = line[159:168].strip()

        # Build perihelion date string
        perihelion_date = None
        if peri_year and peri_month and peri_day:
            try:
                perihelion_date = pd.Timestamp(
                    year=int(peri_year),
                    month=int(peri_month),
                    day=int(float(peri_day)),
                )
            except (ValueError, OverflowError):
                pass

        # Build epoch date
        epoch_date = None
        if epoch_year and epoch_month and epoch_day:
            try:
                epoch_date = pd.Timestamp(
                    year=int(epoch_year),
                    month=int(epoch_month),
                    day=int(epoch_day),
                )
            except (ValueError, OverflowError):
                pass

        return {
            "periodic_comet_number": int(num_str) if num_str else None,
            "orbit_type": orbit_type or None,
            "packed_designation": packed_desig or None,
            "perihelion_year": int(peri_year) if peri_year else None,
            "perihelion_month": int(peri_month) if peri_month else None,
            "perihelion_day": float(peri_day) if peri_day else None,
            "perihelion_date": perihelion_date,
            "perihelion_distance_au": float(perihelion_distance_au) if perihelion_distance_au else None,
            "eccentricity": float(eccentricity) if eccentricity else None,
            "arg_perihelion_deg": float(arg_perihelion_deg) if arg_perihelion_deg else None,
            "lon_asc_node_deg": float(lon_asc_node_deg) if lon_asc_node_deg else None,
            "inclination_deg": float(inclination_deg) if inclination_deg else None,
            "epoch_date": epoch_date,
            "absolute_magnitude_h": float(abs_magnitude_h) if abs_magnitude_h else None,
            "slope_parameter_g": float(slope_param_g) if slope_param_g else None,
            "name": name or None,
            "reference": reference or None,
        }
    except (ValueError, IndexError):
        return None


def main():
    print("Fetching MPC comet orbital elements...")
    resp = requests.get(SOURCE_URL, timeout=120)
    resp.raise_for_status()
    text = resp.text

    lines = text.splitlines()
    print(f"  Downloaded {len(lines):,} lines")

    records = []
    for line in lines:
        rec = parse_comet_line(line)
        if rec is not None:
            records.append(rec)

    df = pd.DataFrame(records)
    print(f"  Parsed {len(df):,} comets")

    # Classify orbit type
    orbit_type_map = {"C": "long-period", "P": "periodic", "D": "defunct", "X": "uncertain", "I": "interstellar", "A": "minor-planet"}
    df["orbit_type_name"] = df["orbit_type"].map(orbit_type_map)

    # Derived: is_hyperbolic (eccentricity >= 1)
    df["is_hyperbolic"] = df["eccentricity"] >= 1.0

    # Compute orbital period for elliptical orbits (Kepler's 3rd law)
    # P = a^(3/2) years, where a = q / (1 - e) for e < 1
    def compute_period(row):
        e = row["eccentricity"]
        q = row["perihelion_distance_au"]
        if pd.isna(e) or pd.isna(q) or e >= 1.0:
            return None
        a = q / (1.0 - e)
        return round(a ** 1.5, 2)

    df["orbital_period_years"] = df.apply(compute_period, axis=1)

    # Type coercion
    df["periodic_comet_number"] = df["periodic_comet_number"].astype("Int64")

    expected_cols = [
        "periodic_comet_number", "orbit_type", "packed_designation",
        "perihelion_date", "perihelion_distance_au", "eccentricity",
        "arg_perihelion_deg", "lon_asc_node_deg", "inclination_deg",
        "absolute_magnitude_h", "slope_parameter_g", "name",
    ]
    check_dataset(
        df,
        dataset_name="mpc-comet-elements",
        min_rows=500,
        expected_columns=expected_cols,
        critical_columns=["perihelion_distance_au", "eccentricity", "inclination_deg", "name"],
        max_null_pct=0.05,
    )

    # Stats for README
    n_periodic = int((df["orbit_type"] == "P").sum())
    n_long_period = int((df["orbit_type"] == "C").sum())
    n_hyperbolic = int(df["is_hyperbolic"].sum())
    n_defunct = int((df["orbit_type"] == "D").sum())
    q_min = df["perihelion_distance_au"].min()
    q_max = df["perihelion_distance_au"].max()
    closest = df.loc[df["perihelion_distance_au"].idxmin()]

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "mpc_comet_elements.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "MPC Comet Orbital Elements"
language:
  - en
description: "Orbital elements for all known comets from the Minor Planet Center. Includes perihelion distance, eccentricity, orbital angles, magnitude, and classification."
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - comets
  - orbits
  - mpc
  - orbital-mechanics
  - open-data
  - tabular-data
  - parquet
size_categories:
  - n<1K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/mpc_comet_elements.parquet
    default: true
---

# MPC Comet Orbital Elements

*Part of the [Orbital Mechanics Datasets](https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994) collection on Hugging Face.*

Orbital elements for **{len(df):,}** known comets published by the
[Minor Planet Center](https://www.minorplanetcenter.net/) (MPC).
Covers periodic, long-period, defunct, and interstellar objects.

## Dataset description

The MPC maintains the authoritative catalogue of comet orbits, updated as new
observations refine existing solutions and new comets are discovered. Each record
contains the six Keplerian orbital elements (perihelion distance, eccentricity,
argument of perihelion, longitude of the ascending node, inclination, and
perihelion date), plus absolute magnitude and slope parameter.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `periodic_comet_number` | Int64 | IAU periodic comet number (null for non-periodic) |
| `orbit_type` | string | MPC orbit type code: C (long-period), P (periodic), D (defunct), X (uncertain), I (interstellar), A (minor-planet-like) |
| `orbit_type_name` | string | Human-readable orbit type |
| `packed_designation` | string | MPC packed provisional designation |
| `perihelion_year` | int | Year of perihelion passage |
| `perihelion_month` | int | Month of perihelion passage |
| `perihelion_day` | float | Day of perihelion passage (TT) |
| `perihelion_date` | datetime | Perihelion passage date (truncated to day) |
| `perihelion_distance_au` | float64 | Perihelion distance (AU) |
| `eccentricity` | float64 | Orbital eccentricity |
| `arg_perihelion_deg` | float64 | Argument of perihelion, J2000.0 (degrees) |
| `lon_asc_node_deg` | float64 | Longitude of the ascending node, J2000.0 (degrees) |
| `inclination_deg` | float64 | Inclination to ecliptic, J2000.0 (degrees) |
| `epoch_date` | datetime | Epoch of osculating elements (perturbed solutions) |
| `absolute_magnitude_h` | float64 | Absolute (total) magnitude parameter H |
| `slope_parameter_g` | float64 | Photometric slope parameter G |
| `orbital_period_years` | float64 | Orbital period in years (Kepler's 3rd law, null for hyperbolic) |
| `is_hyperbolic` | bool | True if eccentricity >= 1.0 |
| `name` | string | Comet name / designation |
| `reference` | string | MPC reference for the orbit solution |

## Quick stats

- **{len(df):,}** comets total
- **{n_periodic:,}** periodic (P), **{n_long_period:,}** long-period (C), **{n_defunct:,}** defunct (D)
- **{n_hyperbolic:,}** on hyperbolic orbits (eccentricity >= 1)
- Perihelion distances range from **{q_min:.4f}** to **{q_max:.1f}** AU
- Closest perihelion: **{closest['name']}** at **{closest['perihelion_distance_au']:.6f}** AU

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/mpc-comet-elements", split="train")
df = ds.to_pandas()

# All periodic comets
periodic = df[df["orbit_type"] == "P"].sort_values("perihelion_distance_au")

# Hyperbolic / interstellar visitors
hyperbolic = df[df["is_hyperbolic"]].sort_values("eccentricity", ascending=False)

# Sun-grazing comets (perihelion < 0.05 AU)
sungrazers = df[df["perihelion_distance_au"] < 0.05]

# Distribution of inclinations
df["inclination_deg"].hist(bins=50)
```

## Data source

[Minor Planet Center — Comet Orbital Elements](https://www.minorplanetcenter.net/iau/MPCORB/CometEls.txt).
Format documentation: [Comet Orbit Format](https://www.minorplanetcenter.net/iau/info/CometOrbitFormat.html).

## Update schedule

Rebuilt monthly (static dataset).

## Related datasets

- [neo-close-approaches](https://huggingface.co/datasets/juliensimon/neo-close-approaches) — NEO close approaches from NASA JPL
- [mpc-asteroid-orbits](https://huggingface.co/datasets/juliensimon/mpc-asteroid-orbits) — MPC asteroid orbital elements

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/mpc-comet-elements) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{mpc_comet_elements,
  author = {{Simon, Julien}},
  title = {{MPC Comet Orbital Elements}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/mpc-comet-elements}},
  note = {{Based on data from the IAU Minor Planet Center}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update MPC comet elements: {len(df):,} comets"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    print(f"rows={len(df)}")
    print("Done.")


if __name__ == "__main__":
    main()
