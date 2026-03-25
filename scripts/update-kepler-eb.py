#!/usr/bin/env python3
"""Fetch Kepler Eclipsing Binary catalog from VizieR and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from validate import check_dataset
from vizier_tap import vizier_query


HF_REPO = "juliensimon/kepler-eclipsing-binaries"

# Slawson et al. (2011) -- 2,177 Kepler eclipsing binaries
ADQL_MAIN = """\
SELECT * FROM "J/AJ/142/160/table3"\
"""

# Kirk et al. (2016) -- updated catalog, fallback if main is too small
ADQL_ALT = """\
SELECT * FROM "J/AJ/148/37/table1"\
"""


def main():
    print("Fetching Kepler eclipsing binaries (Slawson et al.) from VizieR...")
    df = vizier_query(ADQL_MAIN)
    print(f"  Main catalog: {len(df):,} rows")

    # If main catalog is unexpectedly small, try alternate
    if len(df) < 1500:
        print("  Main catalog too small, trying Kirk et al. catalog...")
        df_alt = vizier_query(ADQL_ALT)
        print(f"  Alt catalog: {len(df_alt):,} rows")
        if len(df_alt) > len(df):
            df = df_alt

    # Rename key columns
    known_renames = {
        "KIC": "kic_id",
        "Per": "period_days",
        "Morph": "morphology",
        "morph": "morphology",
        "Teff": "teff_k",
        "logg": "log_g",
        "Kpmag": "kepler_mag",
        "Kp": "kepler_mag",
        "RA_ICRS": "ra_deg",
        "RAICRS": "ra_deg",
        "RAJ2000": "ra_deg",
        "_RA": "ra_deg",
        "DE_ICRS": "dec_deg",
        "DEICRS": "dec_deg",
        "DEJ2000": "dec_deg",
        "_DE": "dec_deg",
        "BJD0": "epoch_bjd",
        "T0": "epoch_bjd",
        "e_Per": "period_err",
        "Dur1": "duration_primary",
        "Dur2": "duration_secondary",
        "Sep": "separation",
        "Depth1": "depth_primary",
        "Depth2": "depth_secondary",
    }
    rename_map = {k: v for k, v in known_renames.items() if k in df.columns}
    if rename_map:
        df = df.rename(columns=rename_map)

    # Snake-case remaining columns
    already_renamed = set(rename_map.values())
    snake_map = {}
    for col in df.columns:
        if col not in already_renamed:
            snake = col.replace(" ", "_").replace("-", "_").lower()
            if snake != col:
                snake_map[col] = snake
    if snake_map:
        df = df.rename(columns=snake_map)

    # Convert numerics
    for col in ["kic_id", "period_days", "teff_k", "log_g", "kepler_mag",
                "ra_deg", "dec_deg", "epoch_bjd", "period_err",
                "duration_primary", "duration_secondary", "separation",
                "depth_primary", "depth_secondary", "morphology"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    check_dataset(df, "kepler-eb", min_rows=1500,
        expected_columns=["kic_id"],
        critical_columns=["kic_id", "period_days"])

    # Stats for README
    n_total = len(df)
    n_with_period = int(df["period_days"].notna().sum()) if "period_days" in df.columns else 0
    n_with_teff = int(df["teff_k"].notna().sum()) if "teff_k" in df.columns else 0
    median_period = df["period_days"].median() if "period_days" in df.columns else 0

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "kepler_eclipsing_binaries.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Kepler Eclipsing Binary Catalog"
language:
  - en
description: "Kepler mission eclipsing binary catalog. Sourced via VizieR CDS Strasbourg."
task_categories:
  - tabular-classification
tags:
  - space
  - kepler
  - eclipsing-binary
  - binary-star
  - astronomy
  - open-data
size_categories:
  - 1K<n<10K
---

# Kepler Eclipsing Binary Catalog

Catalog of **{n_total:,}** eclipsing binary systems identified by the Kepler mission,
with orbital periods, morphology parameters, and stellar properties.

## Dataset description

Eclipsing binaries are pairs of stars whose orbital plane is aligned with our line of
sight, producing periodic dips in brightness as one star passes in front of the other.
The Kepler mission's exquisite photometric precision made it ideal for detecting and
characterizing these systems. This catalog from Slawson et al. (2011) provides the
definitive Kepler eclipsing binary list with orbital periods, eclipse morphology
parameters, and derived stellar properties.

## Quick stats

- **{n_total:,}** eclipsing binaries
- **{n_with_period:,}** with measured orbital periods
- **{n_with_teff:,}** with effective temperature estimates
- Median orbital period: **{median_period:.3f}** days

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/kepler-eclipsing-binaries", split="train")
df = ds.to_pandas()

# Short-period binaries (< 1 day)
if "period_days" in df.columns:
    short = df[df["period_days"] < 1.0]
    print(f"{{len(short):,}} short-period binaries")

# Period distribution
import matplotlib.pyplot as plt
if "period_days" in df.columns:
    df["period_days"].dropna().hist(bins=100, log=True)
    plt.xlabel("Orbital Period (days)")
    plt.ylabel("Count")
    plt.title("Kepler EB Period Distribution")
```

## Data source

Slawson, R.W. et al. (2011), "Kepler Eclipsing Binary Stars. II. 2165 Eclipsing
Binaries in the Second Data Release", AJ, 142, 160. Accessed via
[VizieR](https://vizier.cds.unistra.fr/), CDS Strasbourg.

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update Kepler eclipsing binaries: {n_total:,} systems"
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
