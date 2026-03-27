#!/usr/bin/env python3
"""Fetch General Catalogue of Variable Stars from VizieR and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from validate import check_dataset
from vizier_tap import vizier_query


HF_REPO = "juliensimon/gcvs-variable-stars"

ADQL = """\
SELECT GCVS, RAJ2000, DEJ2000, VarType, magMax, l_Min1, Min1, \
Period, Epoch, SpType \
FROM "B/gcvs/gcvs_cat"\
"""


def main():
    print("Fetching GCVS from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} variable stars")

    # Rename columns
    df = df.rename(columns={
        "GCVS": "gcvs_name",
        "RAJ2000": "ra_deg",
        "DEJ2000": "dec_deg",
        "VarType": "variable_type",
        "magMax": "magnitude_max",
        "Min1": "magnitude_min",
        "l_Min1": "magnitude_min_flag",
        "Period": "period_days",
        "Epoch": "epoch_jd",
        "SpType": "spectral_type",
    })

    # Convert numerics
    for col in ["ra_deg", "dec_deg", "magnitude_max", "magnitude_min", "period_days", "epoch_jd"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Clean string columns: strip whitespace, empty → NaN
    for col in ["gcvs_name", "variable_type", "magnitude_min_flag", "spectral_type"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
            )

    # Sort by name
    df = df.sort_values("gcvs_name").reset_index(drop=True)

    check_dataset(df, "gcvs", min_rows=40000,
        expected_columns=["gcvs_name", "ra_deg", "dec_deg", "variable_type"],
        critical_columns=["gcvs_name", "ra_deg", "dec_deg"])

    # Stats for README
    n_total = len(df)
    n_with_period = int(df["period_days"].notna().sum())
    n_with_spectral = int(df["spectral_type"].notna().sum())
    n_types = int(df["variable_type"].nunique())
    top_types = df["variable_type"].value_counts().head(5)
    top_types_str = ", ".join(f"{t} ({c:,})" for t, c in top_types.items())

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "gcvs_variable_stars.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "General Catalogue of Variable Stars (GCVS)"
language:
  - en
description: "The canonical catalog of variable stars maintained since 1948 by the Sternberg Astronomical Institute, Moscow. Sourced via VizieR CDS Strasbourg."
task_categories:
  - tabular-classification
tags:
  - space
  - variable-star
  - astronomy
  - gcvs
  - stellar
  - open-data
  - tabular-data
size_categories:
  - 10K<n<100K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/gcvs_variable_stars.parquet
    default: true
---

# General Catalogue of Variable Stars (GCVS)

*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

![Update GCVS](https://github.com/juliensimon/space-datasets/actions/workflows/update-gcvs.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.gcvs&label=updated&color=brightgreen)

The General Catalogue of Variable Stars (GCVS) is **the** canonical reference catalog of variable
stars, maintained since 1948 by the Sternberg Astronomical Institute at Moscow State University.
Currently **{n_total:,}** variable stars with {n_types} variability types.

## Dataset description

Variable stars are stars whose brightness changes over time, either due to intrinsic physical
processes (pulsation, eruption, rotation) or extrinsic geometry (eclipsing binaries). The GCVS
is the internationally recognized authority for variable star designations and classifications.
It has been compiled and updated for over 75 years, serving as the foundation for stellar
variability research.

Each entry includes the GCVS designation, coordinates, variability type, magnitude range,
period, epoch of maximum, and spectral type where known.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `gcvs_name` | string | GCVS designation (e.g. "R And", "delta Cep") |
| `ra_deg` | float64 | Right ascension J2000 (degrees) |
| `dec_deg` | float64 | Declination J2000 (degrees) |
| `variable_type` | string | Variability type (e.g. M, SR, EA, DCEP, RR) |
| `magnitude_max` | float64 | Maximum brightness (mag, lower = brighter) |
| `magnitude_min_flag` | string | Flag on minimum magnitude (e.g. "(" for amplitude) |
| `magnitude_min` | float64 | Minimum brightness (mag) |
| `period_days` | float64 | Period in days |
| `epoch_jd` | float64 | Epoch of maximum/minimum (Julian Date) |
| `spectral_type` | string | Spectral type |

## Quick stats

- **{n_total:,}** variable stars
- **{n_types}** variability types
- **{n_with_period:,}** with known period
- **{n_with_spectral:,}** with spectral type
- Top types: {top_types_str}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/gcvs-variable-stars", split="train")
df = ds.to_pandas()

# Cepheid variables (standard candles for distance measurement)
cepheids = df[df["variable_type"].str.startswith("DCEP", na=False)]
print(f"{{len(cepheids):,}} classical Cepheids")

# Eclipsing binaries
eclipsing = df[df["variable_type"].str.startswith("E", na=False)]
print(f"{{len(eclipsing):,}} eclipsing binaries")

# Period-luminosity distribution
import matplotlib.pyplot as plt
valid = df.dropna(subset=["period_days", "magnitude_max"])
valid = valid[valid["period_days"] > 0]
plt.scatter(valid["period_days"], valid["magnitude_max"], s=0.5, alpha=0.3)
plt.xscale("log")
plt.gca().invert_yaxis()
plt.xlabel("Period (days)")
plt.ylabel("Magnitude (max brightness)")
plt.title("GCVS Period vs Magnitude")
```

## Data source

[General Catalogue of Variable Stars](https://www.sai.msu.su/gcvs/gcvs/)
(Samus' N.N., Kazarovets E.V., Durlevich O.V., Kireeva N.N., Pastukhova E.N., 2017,
Astronomy Reports, 61, 80), accessed via [VizieR](https://vizier.cds.unistra.fr/), CDS Strasbourg.

## Update schedule

Quarterly (1st of the month at 08:00 UTC) via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [pulsar-catalog](https://huggingface.co/datasets/juliensimon/pulsar-catalog) -- ATNF Pulsar Catalogue
- [messier-catalog](https://huggingface.co/datasets/juliensimon/messier-catalog) -- Messier deep-sky objects
- [ngc-ic-catalog](https://huggingface.co/datasets/juliensimon/ngc-ic-catalog) -- NGC/IC deep-sky catalog

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/gcvs-variable-stars) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{gcvs_variable_stars,
  author = {{Simon, Julien}},
  title = {{General Catalogue of Variable Stars (GCVS)}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/gcvs-variable-stars}},
  note = {{Based on GCVS (Samus' et al. 2017) via VizieR CDS Strasbourg}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update GCVS variable stars: {n_total:,} stars"
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
