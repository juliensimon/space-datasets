#!/usr/bin/env python3
"""Fetch Asteroid Lightcurve Database (LCDB) and upload to HF."""

import io
import subprocess
import tempfile
import zipfile
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset

LCDB_URL = "https://minplanobs.org/MPInfo/datazips/LCLIST_PUB_CURRENT.zip"
HF_REPO = "juliensimon/asteroid-lightcurves-lcdb"
MIN_ROWS = 20_000

# Fixed-width column specs for lc_summary_pub.txt
COLSPECS = [
    (0, 10),    # NUMBER
    (10, 41),   # NAME
    (41, 62),   # DESIG
    (62, 71),   # FAM (family code)
    (71, 73),   # class_source (S)
    (73, 84),   # CLASS (taxonomy)
    (84, 86),   # diameter_source (S)
    (86, 88),   # diameter_flag (F)
    (88, 97),   # DIA. (km)
    (97, 99),   # h_source (S)
    (99, 106),  # H (abs magnitude)
    (106, 109), # binary_flag (B)
    (109, 111), # g_source (S)
    (111, 118), # G
    (118, 125), # G1
    (125, 132), # G2
    (132, 134), # albedo_source (S)
    (134, 136), # albedo_flag (F)
    (136, 143), # ALBEDO
    (143, 145), # period_flag (F)
    (145, 159), # PERIOD (hours)
    (159, 161), # period_desc_source (P)
    (161, 175), # DESC (period description)
    (175, 177), # amplitude_flag (F)
    (177, 182), # AMIN
    (182, 187), # AMAX
    (187, 190), # U (quality code)
    (190, 196), # NOTES
    (196, 200), # BIN (binary type)
    (200, 204), # SAM
    (204, 210), # SurvA
    (210, 214), # NEX
    (214, 218), # PRI
]

RAW_NAMES = [
    "number", "name", "designation", "family", "class_source", "taxonomy",
    "diameter_source", "diameter_flag", "diameter_km", "h_source",
    "abs_magnitude_h", "binary_flag", "g_source", "g_param", "g1_param",
    "g2_param", "albedo_source", "albedo_flag", "albedo", "period_flag",
    "period_h", "period_desc_source", "period_description", "amplitude_flag",
    "amplitude_min", "amplitude_max", "quality_code_u", "notes",
    "binary_type", "sam", "survey_a", "n_entries", "pri",
]

# Columns to keep (drop internal source/flag columns)
KEEP_COLS = [
    "number", "name", "designation", "family", "taxonomy",
    "diameter_km", "abs_magnitude_h", "g_param", "g1_param", "g2_param",
    "albedo", "period_h", "period_flag", "period_description",
    "amplitude_min", "amplitude_max", "quality_code_u", "notes",
    "binary_type",
]

EXPECTED_COLS = [
    "number", "name", "taxonomy", "diameter_km", "abs_magnitude_h",
    "albedo", "period_h", "amplitude_min", "amplitude_max", "quality_code_u",
]


def main():
    print("Downloading LCDB zip...")
    resp = requests.get(LCDB_URL, timeout=120)
    resp.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        # Find the summary file
        summary = [n for n in zf.namelist() if "lc_summary_pub" in n.lower()]
        if not summary:
            raise RuntimeError(f"lc_summary_pub.txt not found in zip: {zf.namelist()}")
        print(f"  Extracting {summary[0]}...")
        raw = zf.read(summary[0]).decode("latin-1")

    # Parse fixed-width file (skip 5 header lines: title, date, blank, header, dashes)
    df = pd.read_fwf(
        io.StringIO(raw),
        colspecs=COLSPECS,
        names=RAW_NAMES,
        skiprows=5,
    )
    print(f"  {len(df):,} raw rows")

    # --- Clean number column: strip trailing *, convert to nullable int ---
    df["number"] = (
        df["number"]
        .astype(str)
        .str.strip()
        .str.rstrip("*")
        .str.strip()
    )
    df["number"] = pd.to_numeric(df["number"], errors="coerce").astype("Int64")
    # Number=0 means unnumbered; convert to null
    df.loc[df["number"] == 0, "number"] = pd.NA

    # --- Clean family code to nullable int ---
    df["family"] = pd.to_numeric(df["family"], errors="coerce").astype("Int64")

    # --- Clean string columns ---
    for col in ["name", "designation", "taxonomy", "period_description",
                "notes", "binary_type", "period_flag"]:
        df[col] = df[col].astype(str).str.strip().replace({"nan": None, "": None})

    # Drop internal source/flag columns, keep useful ones
    df = df[KEEP_COLS].copy()

    # --- Numeric cleanup ---
    for col in ["diameter_km", "abs_magnitude_h", "g_param", "g1_param",
                "g2_param", "albedo", "period_h", "amplitude_min",
                "amplitude_max"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Round floats
    df["diameter_km"] = df["diameter_km"].round(3)
    df["abs_magnitude_h"] = df["abs_magnitude_h"].round(2)
    df["albedo"] = df["albedo"].round(4)
    df["period_h"] = df["period_h"].round(5)
    df["amplitude_min"] = df["amplitude_min"].round(3)
    df["amplitude_max"] = df["amplitude_max"].round(3)

    # --- Validate ---
    check_dataset(
        df,
        dataset_name="lcdb",
        min_rows=MIN_ROWS,
        expected_columns=EXPECTED_COLS,
        critical_columns=["period_h", "quality_code_u", "abs_magnitude_h"],
        max_null_pct=0.10,
    )

    # --- Stats for README ---
    n_with_period = int(df["period_h"].notna().sum())
    n_with_diameter = int(df["diameter_km"].notna().sum())
    n_with_albedo = int(df["albedo"].notna().sum())
    n_high_quality = int(df["quality_code_u"].isin(["3", "3-"]).sum())
    n_binary = int(df["binary_type"].notna().sum())
    n_taxonomies = int(df["taxonomy"].nunique())
    fastest = df.loc[df["period_h"].idxmin()] if n_with_period else None
    median_period = df["period_h"].median()

    parquet_name = "asteroid_lightcurves_lcdb.parquet"

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / parquet_name
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet, {len(df):,} rows")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Asteroid Lightcurve Database (LCDB)"
language:
  - en
description: "Rotation periods, lightcurve amplitudes, diameters, albedos, and taxonomies for ~{len(df) // 1000}K asteroids from the Asteroid Lightcurve Database (LCDB)."
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - asteroids
  - lightcurves
  - rotation
  - orbital-mechanics
  - open-data
  - tabular-data
size_categories:
  - 10K<n<100K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/{parquet_name}
    default: true
---

# Asteroid Lightcurve Database (LCDB)

*Part of the [Orbital Mechanics Datasets](https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994) collection on Hugging Face.*

Rotation periods, lightcurve amplitudes, and physical properties for **{len(df):,}** asteroids
from the Asteroid Lightcurve Database (LCDB) maintained by Brian Warner at
[MinorPlanet.info](https://minplanobs.org/mpinfo/php/lcdb.php).

## Dataset description

The LCDB is the most comprehensive compilation of asteroid rotation parameters. For each
asteroid, the database provides the best-estimate rotation period (hours), lightcurve
amplitude range (magnitudes), a quality code (U rating 1--3 indicating reliability),
taxonomic classification, diameter, albedo, and slope parameters. The U rating system is:

| U | Meaning |
|---|---------|
| 1 | Tentative, based on fragmentary data |
| 2 | Reasonably secure, may be refined |
| 3 | Unambiguous, well-established |

Suffixes `+` and `-` indicate borderline ratings. A `period_flag` of `>` means
the true period may be longer; `S` indicates a synodic period.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `number` | Int64 | IAU asteroid number (null if unnumbered) |
| `name` | string | Asteroid name (e.g., "Ceres", "Eros") |
| `designation` | string | Provisional designation (e.g., "2024 YR4") |
| `family` | Int64 | Dynamical family code |
| `taxonomy` | string | Taxonomic class (Tholen/Bus-DeMeo, e.g., S, C, V) |
| `diameter_km` | float64 | Diameter in km |
| `abs_magnitude_h` | float64 | Absolute magnitude H |
| `g_param` | float64 | Slope parameter G |
| `g1_param` | float64 | Phase function parameter G1 |
| `g2_param` | float64 | Phase function parameter G2 |
| `albedo` | float64 | Geometric albedo |
| `period_h` | float64 | Rotation period in hours |
| `period_flag` | string | Period qualifier: `>` (lower limit), `S` (synodic), `<`, `D`, `U` |
| `period_description` | string | Additional period notes |
| `amplitude_min` | float64 | Minimum lightcurve amplitude (mag) |
| `amplitude_max` | float64 | Maximum lightcurve amplitude (mag) |
| `quality_code_u` | string | U quality rating: 1, 1+, 2-, 2, 2+, 3-, 3 |
| `notes` | string | Additional notes |
| `binary_type` | string | Binary/multiple system indicator: B (binary), M (multiple), ? (suspected) |

## Quick stats

- **{len(df):,}** asteroids
- **{n_with_period:,}** with measured rotation periods (median {median_period:.2f} h)
- **{n_high_quality:,}** with high-quality periods (U = 3 or 3-)
- **{n_with_diameter:,}** with known diameters
- **{n_with_albedo:,}** with measured albedos
- **{n_binary:,}** binary/multiple systems
- **{n_taxonomies}** distinct taxonomic classes
- Fastest rotator: **{fastest['name'] or fastest['designation']}** at **{fastest['period_h']:.5f}** hours

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/asteroid-lightcurves-lcdb", split="train")
df = ds.to_pandas()

# Well-established rotation periods only (U >= 3)
reliable = df[df["quality_code_u"].isin(["3", "3-"])]

# Fast rotators (period < 2.2 h = spin barrier)
fast = df[(df["period_h"] < 2.2) & (df["quality_code_u"].isin(["3", "3-", "2+", "2"]))]

# S-type asteroids with known diameters and periods
s_type = df[
    (df["taxonomy"].str.startswith("S", na=False))
    & (df["diameter_km"].notna())
    & (df["period_h"].notna())
]

# Period vs diameter scatter
import matplotlib.pyplot as plt
sub = df[(df["period_h"].notna()) & (df["diameter_km"].notna()) & (df["diameter_km"] > 0)]
plt.scatter(sub["diameter_km"], sub["period_h"], s=1, alpha=0.3)
plt.xscale("log"); plt.yscale("log")
plt.xlabel("Diameter (km)"); plt.ylabel("Period (hours)")
plt.title("Asteroid Spin Rate vs Size")
plt.show()
```

## Data source

[Asteroid Lightcurve Database (LCDB)](https://minplanobs.org/mpinfo/php/lcdb.php)
by Brian D. Warner, Alan W. Harris, and Josef Durech.

> Warner, B.D., Harris, A.W., and Pravec, P. (2009). Icarus 202, 134-146.

## Related datasets

- [neo-close-approaches](https://huggingface.co/datasets/juliensimon/neo-close-approaches) -- NEO close approaches from NASA JPL
- [sbdb-asteroids-comets](https://huggingface.co/datasets/juliensimon/sbdb-asteroids-comets) -- JPL Small-Body Database
- [nhats-accessible-asteroids](https://huggingface.co/datasets/juliensimon/nhats-accessible-asteroids) -- Human-accessible NEOs

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Citation

```bibtex
@dataset{{asteroid_lightcurves_lcdb,
  author = {{Simon, Julien}},
  title = {{Asteroid Lightcurve Database (LCDB)}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/asteroid-lightcurves-lcdb}},
  note = {{Based on the Asteroid Lightcurve Database (LCDB) by Warner, Harris, and Durech}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Upload LCDB: {len(df):,} asteroids"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    print(f"Done. {len(df):,} rows uploaded.")


if __name__ == "__main__":
    main()
