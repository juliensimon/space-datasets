#!/usr/bin/env python3
"""Fetch Mars ChemCam MOC oxide compositions from PDS and upload to HF."""

import io
import re
import subprocess
import tempfile
import time
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset

BASE_URL = (
    "https://pds-geosciences.wustl.edu"
    "/msl/msl-m-chemcam-libs-4_5-rdr-v1/mslccm_1xxx/data/moc/"
)
HF_REPO = "juliensimon/mars-chemcam-compositions"

# All known MOC CSV files, ordered by sol range
CSV_FILES = [
    "moc_0000_0089.csv", "moc_0090_0179.csv", "moc_0180_0269.csv",
    "moc_0270_0359.csv", "moc_0360_0449.csv", "moc_0450_0583.csv",
    "moc_0584_0707.csv", "moc_0708_0804.csv", "moc_0805_0938.csv",
    "moc_0939_1062.csv", "moc_1063_1159.csv", "moc_1160_1293.csv",
    "moc_1294_1417.csv", "moc_1418_1514.csv", "moc_1515_1648.csv",
    "moc_1649_1772.csv", "moc_1773_1869.csv", "moc_1870_2003.csv",
    "moc_2004_2127.csv", "moc_2128_2224.csv", "moc_2225_2358.csv",
    "moc_2359_2482.csv", "moc_2483_2579.csv", "moc_2580_2713.csv",
    "moc_2714_2837.csv", "moc_2838_2934.csv", "moc_2935_3068.csv",
    "moc_3069_3192.csv", "moc_3193_3289.csv", "moc_3290_3423.csv",
    "moc_3424_3547.csv", "moc_3548_3644.csv", "moc_3645_3778.csv",
    "moc_3779_3902.csv", "moc_3903_3999.csv", "moc_4000_4133.csv",
    "moc_4134_4257.csv", "moc_4258_4354.csv", "moc_4355_4488.csv",
    "moc_4489_4612.csv",
]

OXIDES = ["SiO2", "TiO2", "Al2O3", "FeOT", "MgO", "CaO", "Na2O", "K2O", "MnO"]

# Columns we want from each CSV (after de-duplicating the +/- columns)
# Raw header: File, Target, SiO2, +/-, SiO2 RMSEP, SiO2_shots_stdev, TiO2, +/-, ...
#             ... Sum of Oxides, Distance (m), Laser Power, Spectrum Total
# Raw CSV columns: File, Target, SiO2, +/-, SiO2 RMSEP, SiO2_shots_stdev, ...
# The "+/-" columns are literal separators — we assign names then drop them.
_RAW_NAMES = ["file", "target"]
for _ox in OXIDES:
    _lo = _ox.lower()
    _RAW_NAMES += [_lo, f"{_lo}_sep", f"{_lo}_rmsep", f"{_lo}_shots_stdev"]
_RAW_NAMES += ["sum_of_oxides", "distance_m", "laser_power", "spectrum_total"]

_SEP_COLS = [f"{ox.lower()}_sep" for ox in OXIDES]  # columns to drop


def parse_sol_range(filename: str) -> tuple[int, int]:
    """Extract (sol_min, sol_max) from a filename like moc_0000_0089.csv."""
    m = re.match(r"moc_(\d+)_(\d+)\.csv", filename)
    if not m:
        raise ValueError(f"Cannot parse sol range from {filename}")
    return int(m.group(1)), int(m.group(2))


def download_csv(filename: str) -> pd.DataFrame:
    """Download one MOC CSV, skip metadata rows, return DataFrame."""
    url = BASE_URL + filename
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()

    # Find the header row (starts with "File,Target,SiO2")
    lines = resp.text.splitlines()
    header_idx = None
    for i, line in enumerate(lines):
        if line.startswith("File,Target,SiO2"):
            header_idx = i
            break
    if header_idx is None:
        raise ValueError(f"Could not find header row in {filename}")

    # Read from the data rows (skip header row, use our own column names)
    data_text = "\n".join(lines[header_idx + 1:])
    if not data_text.strip():
        return pd.DataFrame(columns=[c for c in _RAW_NAMES if c not in _SEP_COLS])

    df = pd.read_csv(
        io.StringIO(data_text),
        header=None,
        names=_RAW_NAMES,
        na_values=["", " "],
    )
    # Drop the literal "+/-" separator columns
    df = df.drop(columns=_SEP_COLS, errors="ignore")

    # Add sol range info from the source filename
    sol_min, sol_max = parse_sol_range(filename)
    df["sol_range_min"] = sol_min
    df["sol_range_max"] = sol_max

    return df


def main():
    print("Fetching ChemCam MOC oxide compositions from PDS Geosciences...")
    print(f"  {len(CSV_FILES)} CSV files to download")

    frames = []
    for i, csv_file in enumerate(CSV_FILES):
        print(f"  [{i + 1}/{len(CSV_FILES)}] {csv_file}...", end=" ", flush=True)
        df = download_csv(csv_file)
        print(f"{len(df)} rows")
        frames.append(df)
        if i < len(CSV_FILES) - 1:
            time.sleep(0.5)  # Be polite to the PDS server

    df = pd.concat(frames, ignore_index=True)
    print(f"  Total: {len(df):,} rows")

    # Drop completely empty rows
    df = df.dropna(subset=["target"], how="all").reset_index(drop=True)

    # Coerce oxide columns to float
    float_cols = []
    for oxide in OXIDES:
        o = oxide.lower()
        float_cols += [o, f"{o}_rmsep", f"{o}_shots_stdev"]
    float_cols += ["sum_of_oxides", "distance_m"]

    for col in float_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Sort by sol range then target name
    df = df.sort_values(["sol_range_min", "target", "file"]).reset_index(drop=True)

    # Compute some stats for the README
    n_targets = df["target"].nunique()
    sol_min = int(df["sol_range_min"].min())
    sol_max = int(df["sol_range_max"].max())
    sio2_mean = df["sio2"].mean()
    feot_mean = df["feot"].mean()

    # Expected columns for validation (oxide value columns + key metadata)
    expected = ["file", "target", "sol_range_min", "sol_range_max",
                "sum_of_oxides", "distance_m"]
    for oxide in OXIDES:
        expected.append(oxide.lower())

    check_dataset(
        df,
        dataset_name="chemcam",
        min_rows=3_000,
        expected_columns=expected,
        critical_columns=[o.lower() for o in OXIDES],
        max_null_pct=0.05,
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "mars_chemcam_compositions.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Mars ChemCam LIBS Oxide Compositions"
language:
  - en
description: "Major oxide compositions of Mars surface targets analyzed by the ChemCam LIBS instrument on the Curiosity rover, from the PDS Geosciences Node."
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - mars
  - curiosity
  - chemcam
  - geochemistry
  - nasa
  - planetary-science
  - open-data
  - tabular-data
  - parquet
size_categories:
  - 1K<n<10K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/mars_chemcam_compositions.parquet
    default: true
---

# Mars ChemCam LIBS Oxide Compositions

*Part of the [Planetary Science Datasets](https://huggingface.co/collections/juliensimon/planetary-science-datasets-68228b04b65e1f3b9e57a76b) collection on Hugging Face.*

Major oxide compositions of Mars surface rock and soil targets analyzed by the
Chemistry and Camera (ChemCam) Laser-Induced Breakdown Spectroscopy (LIBS)
instrument aboard the Curiosity rover. Currently **{len(df):,}** individual
point analyses across **{n_targets:,}** named targets, spanning sols
**{sol_min}** to **{sol_max}**.

## Dataset description

ChemCam fires a focused laser pulse at rock and soil targets up to ~7 meters
away, creating a plasma whose emission spectrum reveals elemental composition.
The Major Oxide Compositions (MOC) data product provides predicted weight
percentages for nine major oxides (SiO2, TiO2, Al2O3, FeOT, MgO, CaO,
Na2O, K2O, MnO) derived from the LIBS spectra using a combined PLS+ICA
multivariate model.

Each row represents a single LIBS analysis point. Multiple points are
typically measured per target to characterize compositional variability.
Uncertainty estimates (RMSEP and shot-to-shot standard deviation) are
provided for each oxide.

Laser-Induced Breakdown Spectroscopy (LIBS) is a technique where a focused pulsed laser ablates a small amount of material from a target surface, generating a high-temperature plasma whose optical emission lines reveal the elemental composition. ChemCam was the first LIBS instrument deployed on another planet and has been operating on Curiosity since its landing in Gale Crater in August 2012. The ability to analyze rocks and soils remotely — without requiring the rover to drive to and physically contact each target — has dramatically increased the pace of geochemical exploration, enabling thousands of analyses across Curiosity's multi-kilometer traverse from the crater floor up through the sedimentary strata of Mount Sharp (Aeolis Mons).

The major oxide compositions in this dataset provide a window into the igneous, sedimentary, and alteration history of the Martian crust. The mean SiO2 content of typical Martian basaltic targets falls near 45-50 wt%, consistent with the tholeiitic basalt composition expected for Mars. However, ChemCam has also identified several unexpected lithologies along the traverse, including high-silica compositions (>60 wt% SiO2) interpreted as evolved igneous rocks or silica-enriched diagenetic features, high-manganese-oxide coatings suggesting oxidizing aqueous conditions, and alkali-rich compositions that have no direct terrestrial analog. The iron content (reported as total FeO) is a key discriminant between mafic and felsic compositions and varies substantially across different geological units.

The stratigraphic context of these measurements is central to understanding the habitability history of Gale Crater. As Curiosity ascends Mount Sharp, it traverses a sequence of sedimentary layers deposited in lacustrine, fluvial, and aeolian environments — the geochemical record preserved in this dataset tracks the evolving chemistry of those environments over geological time. Variations in MgO, CaO, and alkali element ratios across stratigraphic boundaries constrain changes in sediment provenance, water-rock interaction intensity, and diagenetic overprinting. This makes the ChemCam MOC dataset one of the most detailed geochemical transects ever measured on another planet.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `file` | string | Source spectrum filename |
| `target` | string | Named target on the Martian surface |
| `sio2` | float64 | Silicon dioxide (wt%) |
| `sio2_rmsep` | float64 | SiO2 RMSEP uncertainty from calibration model |
| `sio2_shots_stdev` | float64 | SiO2 shot-to-shot standard deviation |
| `tio2` | float64 | Titanium dioxide (wt%) |
| `tio2_rmsep` | float64 | TiO2 RMSEP uncertainty from calibration model |
| `tio2_shots_stdev` | float64 | TiO2 shot-to-shot standard deviation |
| `al2o3` | float64 | Aluminum oxide (wt%) |
| `al2o3_rmsep` | float64 | Al2O3 RMSEP uncertainty from calibration model |
| `al2o3_shots_stdev` | float64 | Al2O3 shot-to-shot standard deviation |
| `feot` | float64 | Total iron as FeO (wt%) |
| `feot_rmsep` | float64 | FeOT RMSEP uncertainty from calibration model |
| `feot_shots_stdev` | float64 | FeOT shot-to-shot standard deviation |
| `mgo` | float64 | Magnesium oxide (wt%) |
| `mgo_rmsep` | float64 | MgO RMSEP uncertainty from calibration model |
| `mgo_shots_stdev` | float64 | MgO shot-to-shot standard deviation |
| `cao` | float64 | Calcium oxide (wt%) |
| `cao_rmsep` | float64 | CaO RMSEP uncertainty from calibration model |
| `cao_shots_stdev` | float64 | CaO shot-to-shot standard deviation |
| `na2o` | float64 | Sodium oxide (wt%) |
| `na2o_rmsep` | float64 | Na2O RMSEP uncertainty from calibration model |
| `na2o_shots_stdev` | float64 | Na2O shot-to-shot standard deviation |
| `k2o` | float64 | Potassium oxide (wt%) |
| `k2o_rmsep` | float64 | K2O RMSEP uncertainty from calibration model |
| `k2o_shots_stdev` | float64 | K2O shot-to-shot standard deviation |
| `mno` | float64 | Manganese oxide (wt%) |
| `mno_rmsep` | float64 | MnO RMSEP uncertainty from calibration model |
| `mno_shots_stdev` | float64 | MnO shot-to-shot standard deviation |
| `sum_of_oxides` | float64 | Sum of all oxide compositions (wt%) |
| `distance_m` | float64 | Distance from rover to target (meters) |
| `laser_power` | string | Laser power settings |
| `spectrum_total` | string | Total spectrum intensity |
| `sol_range_min` | int64 | Start of sol range for this data file |
| `sol_range_max` | int64 | End of sol range for this data file |

## Quick stats

- **{len(df):,}** LIBS point analyses across **{n_targets:,}** targets
- Sols **{sol_min}** to **{sol_max}** of Curiosity's traverse
- Mean SiO2: **{sio2_mean:.1f} wt%** | Mean FeOT: **{feot_mean:.1f} wt%**

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/mars-chemcam-compositions", split="train")
df = ds.to_pandas()

# Average oxide composition per target
target_avg = df.groupby("target")[
    ["sio2", "tio2", "al2o3", "feot", "mgo", "cao", "na2o", "k2o"]
].mean()

# High-silica targets (possible felsic rocks)
felsic = target_avg[target_avg["sio2"] > 60].sort_values("sio2", ascending=False)

# Iron-rich targets
iron_rich = df[df["feot"] > 25].sort_values("feot", ascending=False)

# Composition variability within a single target
target_std = df.groupby("target")[["sio2", "feot", "mgo"]].std()
```

## Data source

[PDS Geosciences Node — MSL ChemCam LIBS RDR](https://pds-geosciences.wustl.edu/msl/msl-m-chemcam-libs-4_5-rdr-v1/mslccm_1xxx/data/moc/),
Washington University in St. Louis. Major Oxide Compositions (MOC) derived
using the combined PLS+ICA multivariate model (sPDL Tool v2.5).

## Related datasets

- [mars-craters](https://huggingface.co/datasets/juliensimon/mars-craters) — Robbins Mars crater catalog
- [neo-close-approaches](https://huggingface.co/datasets/juliensimon/neo-close-approaches) — Near-Earth object approaches
- [small-body-database](https://huggingface.co/datasets/juliensimon/small-body-database) — JPL small body orbital parameters

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/mars-chemcam-compositions) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{mars_chemcam_compositions,
  author = {{Simon, Julien}},
  title = {{Mars ChemCam LIBS Oxide Compositions}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/mars-chemcam-compositions}},
  note = {{Based on MSL ChemCam LIBS MOC data from the PDS Geosciences Node}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update Mars ChemCam compositions: {len(df):,} records"
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
