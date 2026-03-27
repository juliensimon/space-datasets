#!/usr/bin/env python3
"""Fetch 1LHAASO gamma-ray source catalog from VizieR and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from validate import check_dataset
from vizier_tap import vizier_query

HF_REPO = "juliensimon/lhaaso-gamma-ray-sources"

ADQL = """SELECT * FROM "J/ApJS/271/25/catalog" """

RENAME = {
    # Actual VizieR column names from J/ApJS/271/25/catalog
    "1LHAASO": "source_name",
    "f_1LHAASO": "source_name_flag",
    "Comp": "component",
    "f_Comp": "component_flag",
    "RAJ2000": "ra_deg",
    "DEJ2000": "dec_deg",
    "ePos": "pos_error_deg",
    "r39": "extension_deg",
    "e_r39": "extension_error_deg",
    "TS": "significance",
    "N0": "diff_flux_norm",
    "e_N0": "diff_flux_norm_error",
    "Index": "spectral_index",
    "e_Index": "spectral_index_error",
    "TS100": "ts_above_100tev",
    "Assoc": "association",
    "f_Assoc": "association_flag",
    "Sep": "association_separation_deg",
    "SimbadName": "simbad_name",
    # RA/Dec variants (VizieR sometimes uses these)
    "RA_ICRS": "ra_deg",
    "DE_ICRS": "dec_deg",
    "RAICRS": "ra_deg",
    "DEICRS": "dec_deg",
}

NUMERIC_COLS = [
    "ra_deg", "dec_deg",
    "pos_error_deg",
    "extension_deg", "extension_error_deg",
    "significance",
    "diff_flux_norm", "diff_flux_norm_error",
    "spectral_index", "spectral_index_error",
    "ts_above_100tev",
    "association_separation_deg",
]


def main():
    print("Fetching 1LHAASO gamma-ray source catalog from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} raw rows")
    print(f"  Raw columns: {list(df.columns)}")

    # Rename columns (guard for variants)
    rename_map = {k: v for k, v in RENAME.items() if k in df.columns}
    df = df.rename(columns=rename_map)

    # Type conversions
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Clean string columns
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip()
        df[col] = df[col].replace({"nan": None, "": None, "None": None})

    # Derived columns
    if "extension_deg" in df.columns:
        df["is_extended"] = df["extension_deg"].notna() & (df["extension_deg"] > 0)
    if "association" in df.columns:
        df["has_association"] = df["association"].notna()

    # Sort by source name
    if "source_name" in df.columns:
        df = df.sort_values("source_name").reset_index(drop=True)
    elif "ra_deg" in df.columns:
        df = df.sort_values("ra_deg").reset_index(drop=True)

    # Drop recno if present
    df = df.drop(columns=["recno"], errors="ignore")

    # Stats
    n_total = len(df)
    n_km2a = len(df[df["detector"] == "KM2A"]) if "detector" in df.columns else 0
    n_wcda = len(df[df["detector"] == "WCDA"]) if "detector" in df.columns else 0
    n_extended = int(df["is_extended"].sum()) if "is_extended" in df.columns else 0
    n_associated = int(df["has_association"].sum()) if "has_association" in df.columns else 0
    unique_sources = df["source_name"].nunique() if "source_name" in df.columns else n_total

    print(f"  {n_total} entries ({unique_sources} unique sources)")
    print(f"  KM2A: {n_km2a}, WCDA: {n_wcda}")
    print(f"  Extended: {n_extended}, Associated: {n_associated}")

    # Validate
    check_dataset(
        df,
        "lhaaso-gamma-ray-sources",
        min_rows=50,
        expected_columns=["source_name", "ra_deg", "dec_deg", "significance"],
        critical_columns=["source_name", "ra_deg", "dec_deg"],
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "lhaaso_gamma_ray_sources.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.2f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "1LHAASO Gamma-Ray Source Catalog"
language:
  - en
description: "First LHAASO catalog of very-high-energy (VHE) and ultra-high-energy (UHE) gamma-ray sources with {n_total} entries from KM2A and WCDA detectors."
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - gamma-ray
  - lhaaso
  - tev
  - uhe
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
        path: data/lhaaso_gamma_ray_sources.parquet
    default: true
---

# 1LHAASO Gamma-Ray Source Catalog

*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

The first LHAASO (Large High Altitude Air Shower Observatory) catalog of gamma-ray sources detected
at very-high-energy (VHE, >0.1 TeV) and ultra-high-energy (UHE, >100 TeV). Contains **{n_total}** catalog
entries covering **{unique_sources}** unique sources observed with the KM2A and WCDA detectors.

LHAASO, located at 4410 m altitude in Sichuan, China, is the most sensitive UHE gamma-ray observatory
in the Northern Hemisphere.

## Dataset description

The 1LHAASO catalog presents sources detected during the first years of LHAASO operation. Each source
may have separate entries for the KM2A (above ~25 TeV) and WCDA (1--25 TeV) detectors, with independent
spectral measurements. The catalog includes positions, extensions, spectral parameters, and associations
with known sources.

- **{n_km2a}** KM2A entries, **{n_wcda}** WCDA entries
- **{n_extended}** extended sources, **{n_associated}** with known associations

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `source_name` | string | 1LHAASO source designation |
| `detector` | string | Detector: KM2A or WCDA |
| `ra_deg` | float64 | Right ascension J2000 (degrees) |
| `dec_deg` | float64 | Declination J2000 (degrees) |
| `glon_deg` | float64 | Galactic longitude (degrees) |
| `glat_deg` | float64 | Galactic latitude (degrees) |
| `pos_error_deg` | float64 | Position uncertainty (degrees) |
| `extension_deg` | float64 | Source extension (degrees, 0 = point-like) |
| `significance` | float64 | Detection significance (sigma) |
| `spectral_index` | float64 | Power-law spectral index |
| `spectral_index_error` | float64 | Spectral index uncertainty |
| `pivot_energy_tev` | float64 | Pivot energy (TeV) |
| `diff_flux` | float64 | Differential flux at pivot energy |
| `diff_flux_error` | float64 | Differential flux uncertainty |
| `energy_min_tev` | float64 | Minimum energy of fit range (TeV) |
| `energy_max_tev` | float64 | Maximum energy of fit range (TeV) |
| `ts_value` | float64 | Test statistic value |
| `association` | string | Associated known source |
| `source_class` | string | Source classification |
| `is_extended` | bool | True if source has non-zero extension |
| `has_association` | bool | True if associated with a known source |

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/lhaaso-gamma-ray-sources", split="train")
df = ds.to_pandas()

# Sources by detector
print(df["detector"].value_counts())

# UHE sources (KM2A entries above 100 TeV)
km2a = df[df["detector"] == "KM2A"]
print(f"KM2A sources: {{len(km2a)}}")

# Spectral index distribution
import matplotlib.pyplot as plt
df["spectral_index"].dropna().hist(bins=30)
plt.xlabel("Spectral Index")
plt.ylabel("Count")
plt.title("1LHAASO Spectral Index Distribution")
plt.show()

# Sky map in galactic coordinates
plt.scatter(df["glon_deg"], df["glat_deg"], c=df["significance"], cmap="hot", s=20)
plt.colorbar(label="Significance (sigma)")
plt.xlabel("Galactic Longitude (deg)")
plt.ylabel("Galactic Latitude (deg)")
plt.title("1LHAASO Sources in Galactic Coordinates")
plt.show()
```

## Data source

Cao, Z., et al. (2024), *The First LHAASO Catalog of Gamma-Ray Sources.*
The Astrophysical Journal Supplement Series, 271, 25. Via VizieR CDS (J/ApJS/271/25).

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/lhaaso-gamma-ray-sources) and share feedback in the Community tab!

## Citation

```bibtex
@dataset{{lhaaso_gamma_ray_sources,
  author = {{Simon, Julien}},
  title = {{1LHAASO Gamma-Ray Source Catalog}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/lhaaso-gamma-ray-sources}},
  note = {{Based on Cao et al. (2024) via VizieR CDS}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update 1LHAASO gamma-ray source catalog: {n_total} entries"
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
