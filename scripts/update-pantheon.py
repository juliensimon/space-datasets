#!/usr/bin/env python3
"""Fetch Pantheon+ Type Ia supernovae dataset and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from validate import check_dataset

DATA_URL = "https://raw.githubusercontent.com/PantheonPlusSH0ES/DataRelease/main/Pantheon%2B_Data/4_DISTANCES_AND_COVAR/Pantheon%2BSH0ES.dat"
HF_REPO = "juliensimon/pantheon-plus-sne-ia"

KEEP_COLS = {
    "CID": "sn_name",
    "IDSURVEY": "survey_id",
    "zHD": "redshift_hd",
    "zHDERR": "redshift_hd_err",
    "zCMB": "redshift_cmb",
    "zCMBERR": "redshift_cmb_err",
    "zHEL": "redshift_helio",
    "zHELERR": "redshift_helio_err",
    "mB": "apparent_mag_b",
    "mBERR": "apparent_mag_b_err",
    "x1": "stretch_x1",
    "x1ERR": "stretch_x1_err",
    "c": "color_c",
    "cERR": "color_c_err",
    "HOST_LOGMASS": "host_log_mass",
    "HOST_LOGMASS_ERR": "host_log_mass_err",
    "FITPROB": "fit_probability",
    "MU_SH0ES": "distance_modulus",
    "MU_SH0ES_ERR_DIAG": "distance_modulus_err",
}

NUMERIC_COLS = [
    "survey_id", "redshift_hd", "redshift_hd_err", "redshift_cmb", "redshift_cmb_err",
    "redshift_helio", "redshift_helio_err", "apparent_mag_b", "apparent_mag_b_err",
    "stretch_x1", "stretch_x1_err", "color_c", "color_c_err",
    "host_log_mass", "host_log_mass_err", "fit_probability",
    "distance_modulus", "distance_modulus_err",
]


def main():
    print("Fetching Pantheon+ Type Ia supernovae dataset...")
    df = pd.read_csv(DATA_URL, sep=r"\s+")
    print(f"  {len(df):,} raw rows")

    # Keep and rename columns
    available = {c: v for c, v in KEEP_COLS.items() if c in df.columns}
    df = df[list(available.keys())].rename(columns=available)

    # Type conversions
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Stats
    n_total = len(df)
    z_min = df["redshift_cmb"].min()
    z_max = df["redshift_cmb"].max()
    z_median = df["redshift_cmb"].median()
    n_surveys = df["survey_id"].nunique()
    mu_min = df["distance_modulus"].min()
    mu_max = df["distance_modulus"].max()

    # Validate
    check_dataset(
        df,
        "pantheon-plus",
        min_rows=1_000,
        expected_columns=["sn_name", "redshift_cmb", "apparent_mag_b", "distance_modulus"],
        critical_columns=["sn_name", "redshift_cmb", "apparent_mag_b", "distance_modulus"],
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "pantheon_plus_sne.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Pantheon+ Type Ia Supernovae"
language:
  - en
description: "Gold standard cosmological dataset: {n_total:,} spectroscopically confirmed Type Ia supernovae from Pantheon+ used to measure H0 and dark energy."
task_categories:
  - tabular-regression
tags:
  - space
  - supernova
  - cosmology
  - hubble-constant
  - dark-energy
  - pantheon
  - open-data
  - tabular-data
size_categories:
  - 1K<n<10K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/pantheon_plus_sne.parquet
    default: true
---

# Pantheon+ Type Ia Supernovae

*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

The gold standard cosmological dataset -- **{n_total:,}** spectroscopically confirmed Type Ia supernovae
from the Pantheon+ analysis, used to measure the Hubble constant (H0) and constrain the dark energy
equation of state. This is the dataset behind the "Hubble tension" debate.

## Dataset description

Pantheon+ combines supernova light curves from {n_surveys} surveys spanning redshifts
{z_min:.4f} to {z_max:.3f}. Each SN Ia is standardized using the SALT2 light-curve fitter,
providing stretch (x1) and color (c) parameters that transform raw apparent magnitudes into
calibrated distance moduli. Combined with Cepheid-calibrated distances from SH0ES, this
dataset yields the most precise local measurement of the Hubble constant.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `sn_name` | string | Supernova identifier (CID) |
| `survey_id` | int64 | Survey identifier |
| `redshift_hd` | float64 | Hubble-diagram redshift (peculiar velocity corrected) |
| `redshift_hd_err` | float64 | Hubble-diagram redshift uncertainty |
| `redshift_cmb` | float64 | CMB-frame redshift |
| `redshift_cmb_err` | float64 | CMB-frame redshift uncertainty |
| `redshift_helio` | float64 | Heliocentric redshift |
| `redshift_helio_err` | float64 | Heliocentric redshift uncertainty |
| `apparent_mag_b` | float64 | Apparent B-band magnitude (SALT2 mB) |
| `apparent_mag_b_err` | float64 | Apparent magnitude uncertainty |
| `stretch_x1` | float64 | SALT2 stretch parameter x1 |
| `stretch_x1_err` | float64 | Stretch uncertainty |
| `color_c` | float64 | SALT2 color parameter c |
| `color_c_err` | float64 | Color uncertainty |
| `host_log_mass` | float64 | Host galaxy log stellar mass (solar masses) |
| `host_log_mass_err` | float64 | Host mass uncertainty |
| `fit_probability` | float64 | SALT2 fit probability |
| `distance_modulus` | float64 | Distance modulus from SH0ES analysis |
| `distance_modulus_err` | float64 | Distance modulus diagonal uncertainty |

## Quick stats

- **{n_total:,}** Type Ia supernovae from **{n_surveys}** surveys
- Redshift range: {z_min:.4f} to {z_max:.3f} (median {z_median:.3f})
- Distance modulus range: {mu_min:.2f} to {mu_max:.2f} mag

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/pantheon-plus-sne-ia", split="train")
df = ds.to_pandas()

# Hubble diagram
import matplotlib.pyplot as plt
import numpy as np

valid = df[df["distance_modulus"] > 0]
plt.errorbar(valid["redshift_cmb"], valid["distance_modulus"],
             yerr=valid["distance_modulus_err"],
             fmt=".", ms=2, alpha=0.5, elinewidth=0.5)
plt.xscale("log")
plt.xlabel("Redshift (CMB frame)")
plt.ylabel("Distance modulus (mag)")
plt.title("Pantheon+ Hubble Diagram")
plt.show()

# Color-stretch distribution
plt.scatter(df["stretch_x1"], df["color_c"], s=2, alpha=0.3)
plt.xlabel("Stretch x1")
plt.ylabel("Color c")
plt.title("SALT2 Parameter Distribution")
plt.show()

# Redshift distribution
df["redshift_cmb"].hist(bins=50)
plt.xlabel("Redshift")
plt.ylabel("Count")
plt.title("Pantheon+ Redshift Distribution")
plt.show()
```

## Data source

Scolnic, D., et al. (2022), *The Pantheon+ Analysis: The Full Dataset and Light-curve Release.*
Astrophysical Journal, 938, 113.

Brout, D., et al. (2022), *The Pantheon+ Analysis: Cosmological Constraints.*
Astrophysical Journal, 938, 110.

Data release: [PantheonPlusSH0ES/DataRelease](https://github.com/PantheonPlusSH0ES/DataRelease)

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/pantheon-plus-sne-ia) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{pantheon_plus_sne,
  author = {{Simon, Julien}},
  title = {{Pantheon+ Type Ia Supernovae}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/pantheon-plus-sne-ia}},
  note = {{Based on Scolnic et al. (2022) and Brout et al. (2022) Pantheon+ data release}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update Pantheon+ SNe Ia: {n_total:,} supernovae"
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
