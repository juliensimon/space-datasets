#!/usr/bin/env python3
"""Fetch NEOWISE asteroid diameters/albedos from PDS and upload to HF.

Source: PDS Small Bodies Node — NEOWISE Diameters and Albedos V2.0
Static dataset (uploaded once, no workflow).
"""

import io
import subprocess
import tempfile
import zipfile
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset

ZIP_URL = "https://sbnarchive.psi.edu/pds4/non_mission/neowise_diameters_albedos_V2_0.zip"
HF_REPO = "juliensimon/neowise-asteroid-properties"
MIN_ROWS = 100_000

# Column definitions per CSV file, matching PDS4 XML labels exactly.
# Each table has a slightly different schema; we normalise after loading.
TABLE_DEFS = {
    "neowise_mainbelt.csv": {
        "columns": [
            "asteroid_number", "prov_desig", "mpc_packed_name",
            "absolute_mag", "slope_param", "mean_jd",
            "n_w1", "n_w2", "n_w3", "n_w4", "fit_code",
            "diameter_km", "diameter_err_km", "v_albedo", "v_albedo_err",
            "ir_albedo", "ir_albedo_err", "beaming_param", "beaming_param_err",
            "stacked_flag", "reference", "notes",
        ],
        "population": "main_belt",
    },
    "neowise_neos.csv": {
        "columns": [
            "asteroid_number", "prov_desig", "mpc_packed_name",
            "absolute_mag", "slope_param", "mean_jd",
            "n_w1", "n_w2", "n_w3", "n_w4", "fit_code",
            "diameter_km", "diameter_err_km", "v_albedo", "v_albedo_err",
            "ir_albedo", "ir_albedo_err", "beaming_param", "beaming_param_err",
            "stacked_flag", "reference", "notes",
        ],
        "population": "neo",
    },
    "neowise_hildas.csv": {
        "columns": [
            "asteroid_number", "prov_desig", "mpc_packed_name",
            "absolute_mag", "slope_param", "mean_jd",
            "n_w1", "n_w2", "n_w3", "n_w4", "fit_code",
            "diameter_km", "diameter_err_km", "v_albedo", "v_albedo_err",
            "ir_albedo", "ir_albedo_err", "beaming_param", "beaming_param_err",
            "stacked_flag", "reference", "notes",
        ],
        "population": "hilda",
    },
    "neowise_jupiter_trojans.csv": {
        "columns": [
            "asteroid_number", "prov_desig", "mpc_packed_name",
            "absolute_mag", "slope_param", "mean_jd",
            "n_w1", "n_w2", "n_w3", "n_w4", "fit_code",
            "diameter_km", "diameter_err_km", "v_albedo", "v_albedo_err",
            "ir_albedo", "ir_albedo_err", "beaming_param", "beaming_param_err",
            "stacked_flag", "reference", "notes",
        ],
        "population": "jupiter_trojan",
    },
    "neowise_centaurs.csv": {
        "columns": [
            "asteroid_number", "prov_desig", "comet_desig", "mpc_packed_name",
            "absolute_mag", "slope_param", "mean_jd",
            "n_w1", "n_w2", "n_w3", "n_w4", "fit_code",
            "diameter_km", "diameter_err_km", "v_albedo", "v_albedo_err",
            "ir_albedo", "ir_albedo_err", "beaming_param", "beaming_param_err",
            "stacked_flag", "reference",
        ],
        "population": "centaur",
    },
    "neowise_ambos.csv": {
        "columns": [
            "asteroid_number", "comet_desig", "mpc_packed_name",
            "absolute_mag", "slope_param", "mean_jd",
            "n_w1", "n_w2", "n_w3", "n_w4", "fit_code",
            "diameter_km", "diameter_err_km", "v_albedo", "v_albedo_err",
            "ir_albedo", "ir_albedo_err", "beaming_param", "beaming_param_err",
            "stacked_flag", "reference",
        ],
        "population": "ambiguous",
    },
    "neowise_fixed_diameter_fits.csv": {
        "columns": [
            "asteroid_number", "prov_desig", "mpc_packed_name",
            "absolute_mag", "slope_param", "mean_jd",
            "n_w1", "n_w2", "n_w3", "n_w4", "fit_code",
            "diameter_km", "diameter_err_km", "v_albedo", "v_albedo_err",
            "ir_albedo", "ir_albedo_err", "beaming_param", "beaming_param_err",
            "stacked_flag", "reference", "diameter_reference",
        ],
        "population": "fixed_diameter",
    },
    "neowise_irreg_sat.csv": {
        "columns": [
            "satellite_number", "mpc_packed_name",
            "absolute_mag", "slope_param", "mean_jd",
            "n_w1", "n_w2", "n_w3", "n_w4", "fit_code",
            "diameter_km", "diameter_err_km", "v_albedo", "v_albedo_err",
            "ir_albedo", "ir_albedo_err", "beaming_param", "beaming_param_err",
            "stacked_flag", "reference",
        ],
        "population": "irregular_satellite",
    },
}

# Sentinel values used for missing data in the PDS tables
MISSING_SENTINELS = {
    "absolute_mag": -9.99,
    "slope_param": -9.99,
    "v_albedo": -0.999,
    "v_albedo_err": -0.999,
    "ir_albedo": -0.999,
    "ir_albedo_err": -0.999,
    "beaming_param": 0.0,
    "beaming_param_err": 0.0,
}


def main():
    # ── Download ──────────────────────────────────────────────────────────
    print("Downloading NEOWISE diameters/albedos from PDS...")
    resp = requests.get(ZIP_URL, timeout=120)
    resp.raise_for_status()
    print(f"  Downloaded {len(resp.content) / 1024 / 1024:.1f} MB")

    # ── Extract and parse each table ──────────────────────────────────────
    frames = []
    zf = zipfile.ZipFile(io.BytesIO(resp.content))

    for csv_name, tdef in TABLE_DEFS.items():
        path = f"neowise_diameters_albedos_V2_0/data/{csv_name}"
        with zf.open(path) as fh:
            df = pd.read_csv(
                fh,
                header=None,
                names=tdef["columns"],
                dtype=str,
                skipinitialspace=True,
            )
        df["population"] = tdef["population"]
        frames.append(df)
        print(f"  {csv_name}: {len(df):,} rows")

    df = pd.concat(frames, ignore_index=True)
    print(f"  Total raw rows: {len(df):,}")

    # ── Normalise identifiers ─────────────────────────────────────────────
    # Build a single object_id from asteroid_number / satellite_number / prov_desig / comet_desig
    def _make_object_id(row):
        # Prefer asteroid number > satellite number > provisional > comet designation
        for col in ("asteroid_number", "satellite_number"):
            val = row.get(col)
            if pd.notna(val) and str(val).strip() not in ("", "0"):
                return str(val).strip()
        for col in ("prov_desig", "comet_desig"):
            val = row.get(col)
            if pd.notna(val) and val.strip() not in ("", "-"):
                return val.strip()
        return row.get("mpc_packed_name", "").strip()

    df["object_id"] = df.apply(_make_object_id, axis=1)

    # Strip whitespace from string columns
    for col in ("prov_desig", "comet_desig", "mpc_packed_name",
                "fit_code", "stacked_flag", "reference", "notes",
                "diameter_reference", "satellite_number"):
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace({"nan": None, "": None, "-": None})

    # ── Type coercion ─────────────────────────────────────────────────────
    int_cols = ["asteroid_number", "n_w1", "n_w2", "n_w3", "n_w4"]
    for col in int_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    float_cols = [
        "absolute_mag", "slope_param", "mean_jd",
        "diameter_km", "diameter_err_km",
        "v_albedo", "v_albedo_err",
        "ir_albedo", "ir_albedo_err",
        "beaming_param", "beaming_param_err",
    ]
    for col in float_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Replace PDS sentinel values with NaN
    for col, sentinel in MISSING_SENTINELS.items():
        if col in df.columns:
            df.loc[df[col] == sentinel, col] = None

    # Replace asteroid_number == 0 with NaN (PDS missing constant)
    if "asteroid_number" in df.columns:
        df.loc[df["asteroid_number"] == 0, "asteroid_number"] = pd.NA

    # ── Final column selection ────────────────────────────────────────────
    final_cols = [
        "object_id", "asteroid_number", "prov_desig", "comet_desig",
        "mpc_packed_name", "population",
        "absolute_mag", "slope_param", "mean_jd",
        "n_w1", "n_w2", "n_w3", "n_w4", "fit_code",
        "diameter_km", "diameter_err_km",
        "v_albedo", "v_albedo_err",
        "ir_albedo", "ir_albedo_err",
        "beaming_param", "beaming_param_err",
        "stacked_flag", "reference", "notes",
    ]
    # Only keep columns that exist (some tables lack certain columns)
    final_cols = [c for c in final_cols if c in df.columns]
    df = df[final_cols]

    # ── Stats ─────────────────────────────────────────────────────────────
    n_total = len(df)
    n_with_albedo = int(df["v_albedo"].notna().sum())
    n_populations = df["population"].nunique()
    pop_counts = df["population"].value_counts()
    median_diam = df["diameter_km"].median()
    median_albedo = df["v_albedo"].median()

    print(f"  {n_total:,} objects across {n_populations} populations")
    print(f"  Median diameter: {median_diam:.1f} km")
    print(f"  Median V-albedo: {median_albedo:.3f}")
    for pop, count in pop_counts.items():
        print(f"    {pop}: {count:,}")

    # ── Validate ──────────────────────────────────────────────────────────
    check_dataset(
        df,
        dataset_name="neowise",
        min_rows=MIN_ROWS,
        expected_columns=[
            "object_id", "population", "diameter_km", "v_albedo",
            "absolute_mag", "beaming_param",
        ],
        critical_columns=["object_id", "diameter_km", "v_albedo"],
        max_null_pct=0.10,
    )

    # ── Write parquet + README ────────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "neowise_asteroid_properties.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "NEOWISE Asteroid Diameters and Albedos"
language:
  - en
description: "Physical properties (diameters, albedos, beaming parameters) for {n_total:,} asteroids from WISE/NEOWISE infrared observations."
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - asteroids
  - neowise
  - wise
  - nasa
  - orbital-mechanics
  - open-data
  - tabular-data
size_categories:
  - 100K<n<1M
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/neowise_asteroid_properties.parquet
    default: true
---

# NEOWISE Asteroid Diameters and Albedos

*Part of the [Orbital Mechanics Datasets](https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994) collection on Hugging Face.*

Physical properties of **{n_total:,}** asteroids derived from WISE/NEOWISE infrared observations,
spanning main-belt asteroids, NEOs, Hildas, Jupiter Trojans, Centaurs, irregular satellites,
and ambiguous objects. Includes effective spherical diameters, visible and infrared geometric
albedos, and NEATM thermal beaming parameters.

## Dataset description

The WISE (Wide-field Infrared Survey Explorer) and NEOWISE missions observed over 164,000
minor planets at thermal infrared wavelengths (3.4--22 microns). Thermal model fits to these
observations yield diameter and albedo estimates that are independent of visible-light
assumptions. This dataset combines all published NEOWISE diameter/albedo tables from the
PDS Small Bodies Node (V2.0), covering observations from January 2010 through December 2016.

Each record represents a single thermal-model fit for one object. The `fit_code` column
indicates which parameters were allowed to vary: D=diameter, V=visible albedo, B=beaming
parameter (or F=fast-rotating model), I=infrared albedo.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `object_id` | string | Primary identifier (asteroid number, satellite ID, or provisional designation) |
| `asteroid_number` | Int64 | IAU asteroid catalog number (null for unnumbered/satellites) |
| `prov_desig` | string | Provisional designation (null if none) |
| `comet_desig` | string | Comet designation for dual-nature objects (null if none) |
| `mpc_packed_name` | string | MPC packed-format designation |
| `population` | string | Dynamical population: main_belt, neo, hilda, jupiter_trojan, centaur, irregular_satellite, ambiguous, fixed_diameter |
| `absolute_mag` | float64 | Absolute H magnitude used as input to thermal fit |
| `slope_param` | float64 | G slope parameter for photometric phase correction |
| `mean_jd` | float64 | Mean Julian Date of observations used for fitting |
| `n_w1` | Int64 | Number of W1 (3.4 um) band measurements used |
| `n_w2` | Int64 | Number of W2 (4.6 um) band measurements used |
| `n_w3` | Int64 | Number of W3 (12 um) band measurements used |
| `n_w4` | Int64 | Number of W4 (22 um) band measurements used |
| `fit_code` | string | 4-char code: D=diameter, V=vis albedo, B=beaming/F=FRM, I=IR albedo, -=fixed |
| `diameter_km` | float64 | Best-fit effective spherical diameter (km) |
| `diameter_err_km` | float64 | 1-sigma diameter uncertainty (km) |
| `v_albedo` | float64 | Visible geometric albedo (best-fit or assumed) |
| `v_albedo_err` | float64 | 1-sigma visible albedo uncertainty |
| `ir_albedo` | float64 | Infrared geometric albedo (best-fit or assumed) |
| `ir_albedo_err` | float64 | 1-sigma infrared albedo uncertainty |
| `beaming_param` | float64 | NEATM thermal beaming parameter eta |
| `beaming_param_err` | float64 | 1-sigma beaming parameter uncertainty |
| `stacked_flag` | string | "S" if fit used co-added images on predicted position |
| `reference` | string | Short reference code for original publication |
| `notes` | string | Flags: OrbChange, NoOrb, BrokenLink (null if none) |

## Quick stats

- **{n_total:,}** objects across **{n_populations}** dynamical populations
- **{int(pop_counts.get('main_belt', 0)):,}** main-belt asteroids
- **{int(pop_counts.get('neo', 0)):,}** near-Earth objects
- **{int(pop_counts.get('jupiter_trojan', 0)):,}** Jupiter Trojans
- **{n_with_albedo:,}** objects with measured visible albedo
- Median diameter: **{median_diam:.1f} km** | Median V-albedo: **{median_albedo:.3f}**

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/neowise-asteroid-properties", split="train")
df = ds.to_pandas()

# Albedo distribution by population
df.groupby("population")["v_albedo"].describe()

# Large dark asteroids (low albedo, big diameter)
dark_big = df[(df["v_albedo"] < 0.05) & (df["diameter_km"] > 100)]

# NEOs with measured properties
neos = df[df["population"] == "neo"].sort_values("diameter_km", ascending=False)

# Diameter vs albedo scatter
import matplotlib.pyplot as plt
sample = df.dropna(subset=["diameter_km", "v_albedo"])
plt.scatter(sample["diameter_km"], sample["v_albedo"], s=0.5, alpha=0.3)
plt.xscale("log")
plt.xlabel("Diameter (km)")
plt.ylabel("Visible Albedo")
```

## Data source

[PDS Small Bodies Node — NEOWISE Diameters and Albedos V2.0](https://sbnarchive.psi.edu/pds4/non_mission/neowise_diameters_albedos_V2_0.zip)

Based on observations by the Wide-field Infrared Survey Explorer (WISE) and its NEOWISE
reactivation mission. See Mainzer et al. (2011), Masiero et al. (2011, 2014, 2017),
Grav et al. (2012), Bauer et al. (2013), Nugent et al. (2015, 2016).

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Citation

```bibtex
@dataset{{neowise_asteroid_properties,
  author = {{Simon, Julien}},
  title = {{NEOWISE Asteroid Diameters and Albedos}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/neowise-asteroid-properties}},
  note = {{Based on WISE/NEOWISE data from the PDS Small Bodies Node, Mainzer et al.}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Upload NEOWISE asteroid properties: {n_total:,} objects"
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
