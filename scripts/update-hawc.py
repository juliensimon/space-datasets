#!/usr/bin/env python3
"""Fetch 3HWC HAWC TeV gamma-ray source catalog from VizieR and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from validate import check_dataset
from vizier_tap import vizier_query

HF_REPO = "juliensimon/hawc-tev-gamma-ray"

ADQL = """SELECT * FROM "J/ApJ/905/76/sources" """

RENAME = {
    "3HWC": "source_name",
    "f_3HWC": "source_name_flag",
    "RAJ2000": "ra_deg",
    "DEJ2000": "dec_deg",
    "GLON": "glon_deg",
    "GLAT": "glat_deg",
    "ePos": "pos_error_deg",
    "rs": "search_radius_deg",
    "TS": "test_statistic",
    "Sep": "separation_deg",
    "f_TeVCat": "tevcat_flag",
    "TeVCat": "tevcat_name",
    "n_TeVCat": "tevcat_note",
    "F7": "flux_7tev",
    "E_F7": "flux_7tev_err_upper",
    "e_F7": "flux_7tev_err_lower",
    "Ind": "spectral_index",
    "E_Ind": "spectral_index_err_upper",
    "e_Ind": "spectral_index_err_lower",
    "F7sys-u": "flux_7tev_sys_upper",
    "F7sys-l": "flux_7tev_sys_lower",
    "Indsys-u": "spectral_index_sys_upper",
    "Indsys-l": "spectral_index_sys_lower",
    "ER-min": "energy_range_min_tev",
    "ER-max": "energy_range_max_tev",
}

NUMERIC_COLS = [
    "ra_deg", "dec_deg", "glon_deg", "glat_deg", "pos_error_deg",
    "search_radius_deg", "test_statistic", "separation_deg",
    "flux_7tev", "flux_7tev_err_upper", "flux_7tev_err_lower",
    "spectral_index", "spectral_index_err_upper", "spectral_index_err_lower",
    "flux_7tev_sys_upper", "flux_7tev_sys_lower",
    "spectral_index_sys_upper", "spectral_index_sys_lower",
    "energy_range_min_tev", "energy_range_max_tev",
]


def main():
    print("Fetching 3HWC HAWC TeV gamma-ray catalog from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} raw rows")

    # Drop VizieR internal columns
    for col in ["recno", "Seq", "H", "N", "_Simbad_"]:
        if col in df.columns:
            df = df.drop(columns=[col])

    # Rename columns
    df = df.rename(columns=RENAME)

    # Type conversions
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Sort by source name
    df = df.sort_values("source_name").reset_index(drop=True)

    # Stats
    n_total = len(df)
    ts_median = df["test_statistic"].median()
    ra_min, ra_max = df["ra_deg"].min(), df["ra_deg"].max()
    dec_min, dec_max = df["dec_deg"].min(), df["dec_deg"].max()
    n_with_tevcat = int(df["tevcat_name"].notna().sum())

    # Validate
    check_dataset(
        df,
        "hawc-tev-gamma-ray",
        min_rows=40,
        expected_columns=["source_name", "ra_deg", "dec_deg", "flux_7tev", "spectral_index"],
        critical_columns=["source_name", "ra_deg", "dec_deg", "flux_7tev"],
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "hawc_tev_gamma_ray.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_kb = out.stat().st_size / 1024
        print(f"  {size_kb:.1f} KB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "3HWC HAWC TeV Gamma-Ray Source Catalog"
language:
  - en
description: "Third HAWC Catalog of Very-High-Energy Gamma-Ray Sources (3HWC) with {n_total} TeV sources detected over 1,523 days."
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - gamma-ray
  - hawc
  - tev
  - astronomy
  - physics
  - open-data
  - tabular-data
size_categories:
  - n<1K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/hawc_tev_gamma_ray.parquet
    default: true
---

# 3HWC HAWC TeV Gamma-Ray Source Catalog

*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

The Third HAWC Catalog (3HWC) of Very-High-Energy Gamma-Ray Sources, containing **{n_total}** sources
detected by the High Altitude Water Cherenkov (HAWC) Observatory over 1,523 days of observation.
HAWC surveys two-thirds of the sky daily at TeV energies.

## Dataset description

The 3HWC catalog represents the most sensitive survey of the TeV gamma-ray sky by HAWC.
Sources are identified as statistically significant excesses above the cosmic-ray background.
The catalog includes source positions, test statistics, differential fluxes at 7 TeV, and
spectral indices assuming a simple power-law model.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `source_name` | string | 3HWC designation (e.g., 3HWC J0534+220) |
| `source_name_flag` | string | Flag on source name |
| `ra_deg` | float64 | Right ascension J2000 (degrees) |
| `dec_deg` | float64 | Declination J2000 (degrees) |
| `glon_deg` | float64 | Galactic longitude (degrees) |
| `glat_deg` | float64 | Galactic latitude (degrees) |
| `pos_error_deg` | float64 | Positional uncertainty (degrees) |
| `search_radius_deg` | float64 | Search radius used (degrees) |
| `test_statistic` | float64 | Detection test statistic (TS) |
| `separation_deg` | float64 | Separation from nearest TeVCat source (degrees) |
| `tevcat_flag` | string | TeVCat association flag |
| `tevcat_name` | string | Associated TeVCat source name |
| `tevcat_note` | string | Note on TeVCat association |
| `flux_7tev` | float64 | Differential flux at 7 TeV (10^-15 cm^-2 s^-1 TeV^-1) |
| `flux_7tev_err_upper` | float64 | Upper statistical error on flux |
| `flux_7tev_err_lower` | float64 | Lower statistical error on flux |
| `spectral_index` | float64 | Power-law spectral index |
| `spectral_index_err_upper` | float64 | Upper statistical error on index |
| `spectral_index_err_lower` | float64 | Lower statistical error on index |
| `flux_7tev_sys_upper` | float64 | Upper systematic error on flux |
| `flux_7tev_sys_lower` | float64 | Lower systematic error on flux |
| `spectral_index_sys_upper` | float64 | Upper systematic error on index |
| `spectral_index_sys_lower` | float64 | Lower systematic error on index |
| `energy_range_min_tev` | float64 | Minimum energy of analysis range (TeV) |
| `energy_range_max_tev` | float64 | Maximum energy of analysis range (TeV) |

## Quick stats

- **{n_total}** TeV gamma-ray sources
- **{n_with_tevcat}** sources with TeVCat associations
- Median test statistic: {ts_median:.1f}
- Sky coverage: RA {ra_min:.1f}--{ra_max:.1f} deg, Dec {dec_min:.1f}--{dec_max:.1f} deg

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/hawc-tev-gamma-ray", split="train")
df = ds.to_pandas()

# Most significant detections
top = df.nlargest(10, "test_statistic")[["source_name", "test_statistic", "flux_7tev"]]
print(top.to_string(index=False))

# Sky map in galactic coordinates
import matplotlib.pyplot as plt
plt.figure(figsize=(12, 5))
plt.scatter(df["glon_deg"], df["glat_deg"], s=df["test_statistic"] / 5, alpha=0.6)
plt.xlabel("Galactic Longitude (deg)")
plt.ylabel("Galactic Latitude (deg)")
plt.title("3HWC Sources in Galactic Coordinates")
plt.gca().invert_xaxis()
plt.show()

# Spectral index distribution
df["spectral_index"].hist(bins=20)
plt.xlabel("Spectral Index")
plt.ylabel("Count")
plt.title("3HWC Spectral Index Distribution")
plt.show()
```

## Data source

Albert, A. et al. (2020), *3HWC: The Third HAWC Catalog of Very-High-Energy Gamma-Ray Sources.*
The Astrophysical Journal, 905, 76. Via VizieR CDS (J/ApJ/905/76).

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/hawc-tev-gamma-ray) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{hawc_tev_gamma_ray,
  author = {{Simon, Julien}},
  title = {{3HWC HAWC TeV Gamma-Ray Source Catalog}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/hawc-tev-gamma-ray}},
  note = {{Based on Albert et al. (2020) via VizieR CDS}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update 3HWC HAWC catalog: {n_total} sources"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={len(df)}\n")
    print("Done.")


if __name__ == "__main__":
    main()
