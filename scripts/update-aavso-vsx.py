#!/usr/bin/env python3
"""Fetch AAVSO Variable Star Index (VSX) bulk dump and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset

HF_REPO = "juliensimon/aavso-vsx-variable-stars"
SOURCE_URL = "https://vsx.aavso.org/external/vsx_csv.dat.gz"

RENAME = {
    "#OID": "aavso_uid",
    "Name": "name",
    "VarFlag": "var_flag",
    "RAdeg": "ra_deg",
    "DEdeg": "dec_deg",
    "Type": "variable_type",
    "LimitFlagOnMax": "limit_flag_max",
    "MagMax": "mag_max",
    "MaxUncertaintyFlag": "mag_max_uncertainty_flag",
    "MaxPassband": "mag_max_passband",
    "MinIsAmplitude": "min_is_amplitude",
    "LimitFlagOnMin": "limit_flag_min",
    "MagMin": "mag_min",
    "MinUncertaintyFlag": "mag_min_uncertainty_flag",
    "MinPassband": "mag_min_passband",
    "Epoch": "epoch_jd",
    "EpochUncertaintyFlag": "epoch_uncertainty_flag",
    "LimitFlagOnPeriod": "limit_flag_period",
    "Period": "period_days",
    "PeriodUncertaintyFlag": "period_uncertainty_flag",
    "SpectralType": "spectral_type",
}

NUMERIC_COLS = ["ra_deg", "dec_deg", "mag_max", "mag_min", "epoch_jd", "period_days"]

INT_COLS = ["aavso_uid", "var_flag"]


def main():
    print("Downloading AAVSO VSX bulk dump...")
    resp = requests.get(SOURCE_URL, timeout=300, stream=True)
    resp.raise_for_status()

    # Write to temp file then read with pandas (avoids holding full response in memory)
    with tempfile.NamedTemporaryFile(suffix=".csv.gz", delete=False) as f:
        tmp_gz = f.name
        for chunk in resp.iter_content(chunk_size=8 * 1024 * 1024):
            f.write(chunk)
    print(f"  Downloaded {Path(tmp_gz).stat().st_size / 1024 / 1024:.0f} MB")

    print("Reading CSV...")
    df = pd.read_csv(
        tmp_gz,
        compression="gzip",
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )
    Path(tmp_gz).unlink()
    print(f"  {len(df):,} raw rows, {len(df.columns)} columns")

    # Rename columns
    df = df.rename(columns=RENAME)

    # Type conversions — numeric
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Type conversions — integer
    for col in INT_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    # Clean up string columns — replace empty strings with NaN
    str_cols = ["name", "variable_type", "spectral_type", "mag_max_passband",
                "mag_min_passband", "limit_flag_max", "limit_flag_min",
                "limit_flag_period", "mag_max_uncertainty_flag",
                "mag_min_uncertainty_flag", "epoch_uncertainty_flag",
                "period_uncertainty_flag", "min_is_amplitude"]
    for col in str_cols:
        if col in df.columns:
            df[col] = df[col].replace("", pd.NA).astype("string")

    # Strip surrounding quotes from spectral_type (source has e.g. "K")
    if "spectral_type" in df.columns:
        df["spectral_type"] = df["spectral_type"].str.strip('"')
        df["spectral_type"] = df["spectral_type"].replace("", pd.NA)

    # Derived: magnitude range (amplitude)
    df["mag_range"] = (df["mag_min"] - df["mag_max"]).round(3)

    # Sort by RA for spatial locality in parquet
    df = df.sort_values("ra_deg", na_position="last").reset_index(drop=True)

    # Stats
    n_total = len(df)
    n_with_period = int(df["period_days"].notna().sum())
    n_with_type = int(df["variable_type"].notna().sum())
    top_types = df["variable_type"].value_counts().head(10)
    ra_range = (df["ra_deg"].min(), df["ra_deg"].max())
    dec_range = (df["dec_deg"].min(), df["dec_deg"].max())

    print(f"  {n_with_period:,} stars with period, {n_with_type:,} with variable type")

    # Validate
    check_dataset(
        df,
        "aavso-vsx",
        min_rows=1_500_000,
        expected_columns=["aavso_uid", "name", "ra_deg", "dec_deg", "variable_type",
                          "mag_max", "period_days"],
        critical_columns=["aavso_uid", "name", "ra_deg", "dec_deg"],
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "aavso_vsx_variable_stars.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        top_types_md = "\n".join(
            f"| `{t}` | {c:,} |" for t, c in top_types.items()
        )

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "AAVSO Variable Star Index (VSX)"
language:
  - en
description: "AAVSO Variable Star Index (VSX) catalog with {n_total:,} variable stars including types, periods, magnitudes, and spectral classifications."
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - variable-stars
  - aavso
  - vsx
  - astronomy
  - open-data
  - tabular-data
  - parquet
size_categories:
  - 1M<n<10M
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/aavso_vsx_variable_stars.parquet
    default: true
---

# AAVSO Variable Star Index (VSX)

*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

The AAVSO Variable Star Index (VSX) is the most comprehensive catalog of variable stars,
containing **{n_total:,}** entries with variable star classifications, photometric properties,
periods, and spectral types. VSX is maintained by the American Association of Variable Star
Observers and is the standard reference for variable star research.

## Dataset description

VSX aggregates variable star data from hundreds of surveys and catalogs worldwide including
OGLE, ASAS-SN, ZTF, Gaia, and AAVSO observer submissions. Each entry represents a unique
variable or suspected variable star with its variability type, brightness range, period (if
known), epoch, and spectral classification.

Of the {n_total:,} entries, **{n_with_period:,}** have a measured period and
**{n_with_type:,}** have a variability classification.

## Key columns

| Column | Type | Description |
|--------|------|-------------|
| `aavso_uid` | Int64 | AAVSO unique object identifier |
| `name` | string | Primary designation |
| `ra_deg` | float64 | Right ascension J2000 (degrees) |
| `dec_deg` | float64 | Declination J2000 (degrees) |
| `variable_type` | string | Variability type (e.g., EW, SR, RRAB, DSCT) |
| `var_flag` | Int64 | Variability flag (0=confirmed, 1=suspected) |
| `mag_max` | float64 | Maximum brightness (magnitude at max light) |
| `mag_max_passband` | string | Passband for max magnitude |
| `mag_min` | float64 | Minimum brightness / amplitude |
| `mag_min_passband` | string | Passband for min magnitude |
| `min_is_amplitude` | string | Y if mag_min is amplitude, not absolute magnitude |
| `period_days` | float64 | Period in days |
| `epoch_jd` | float64 | Epoch of maximum/minimum (Julian Date) |
| `spectral_type` | string | Spectral classification |
| `mag_range` | float64 | Derived magnitude range (mag_min - mag_max) |

Full schema includes {len(df.columns)} columns with uncertainty flags and limit flags.

## Top variability types

| Type | Count |
|------|-------|
{top_types_md}

## Quick stats

- **{n_total:,}** variable star entries
- **{n_with_period:,}** with measured period ({n_with_period / n_total * 100:.1f}%)
- **{n_with_type:,}** with variability classification ({n_with_type / n_total * 100:.1f}%)
- RA range: {ra_range[0]:.4f} to {ra_range[1]:.4f} degrees
- Dec range: {dec_range[0]:.4f} to {dec_range[1]:.4f} degrees

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/aavso-vsx-variable-stars", split="train")
df = ds.to_pandas()

# Eclipsing binaries with known periods
eclipsing = df[df["variable_type"].str.startswith("E", na=False) & df["period_days"].notna()]
print(f"Eclipsing binaries with periods: {{len(eclipsing):,}}")

# Period-amplitude diagram for RR Lyrae
rrab = df[df["variable_type"] == "RRAB"]
import matplotlib.pyplot as plt
plt.scatter(rrab["period_days"], rrab["mag_range"], s=0.5, alpha=0.3)
plt.xlabel("Period (days)")
plt.ylabel("Amplitude (mag)")
plt.title("RR Lyrae (RRAB) Period-Amplitude Diagram")
plt.show()

# Sky distribution
plt.hexbin(df["ra_deg"], df["dec_deg"], gridsize=200, mincnt=1)
plt.colorbar(label="Star count")
plt.xlabel("RA (deg)")
plt.ylabel("Dec (deg)")
plt.title("VSX Variable Stars Sky Density")
plt.show()
```

## Data source

Watson, C.L., Henden, A.A., & Price, A. (2006), *The International Variable Star Index (VSX).*
Society for Astronomical Sciences 25th Annual Symposium on Telescope Science, p. 47.
Maintained by AAVSO: [https://www.aavso.org/vsx/](https://www.aavso.org/vsx/)

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/aavso-vsx-variable-stars) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{aavso_vsx_variable_stars,
  author = {{Simon, Julien}},
  title = {{AAVSO Variable Star Index (VSX)}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/aavso-vsx-variable-stars}},
  note = {{Based on AAVSO VSX (Watson et al. 2006)}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update AAVSO VSX: {n_total:,} variable stars"
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
