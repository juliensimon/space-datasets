#!/usr/bin/env python3
"""Fetch cosmic ray spectra from CRDB and upload to HF."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import crdb
import pandas as pd

from validate import check_dataset


HF_REPO = "juliensimon/crdb-cosmic-ray-spectra"

RENAME_MAP = {
    "quantity": "particle",
    "exp": "experiment",
    "exp_type": "experiment_type",
    "sub_exp": "sub_experiment",
    "e": "energy_gev_n",
    "e_bin_lo": "energy_bin_lo_gev_n",
    "e_bin_hi": "energy_bin_hi_gev_n",
    "value": "flux",
    "err_sta_lo": "stat_error_lo",
    "err_sta_hi": "stat_error_hi",
    "err_sys_lo": "sys_error_lo",
    "err_sys_hi": "sys_error_hi",
    "e_relerr": "energy_relative_error",
    "is_upper_limit": "is_upper_limit",
    "phi": "solar_modulation_mv",
    "ads": "ads_bibcode",
    "e_type": "energy_type",
    "datetime": "observation_period",
    "distance": "distance_au",
}


def main():
    print("Fetching cosmic ray spectra from CRDB...")

    # Query major particle species separately (CRDB doesn't support "*")
    particles = [
        "H", "He", "C", "N", "O", "Ne", "Mg", "Si", "Fe",
        "e-", "e+", "p-bar",
        "B/C", "Be/B", "Be/C",
        "Li", "Be", "B", "F", "Na", "Al", "P", "S", "Cl", "Ar",
        "K", "Ca", "Ti", "V", "Cr", "Mn", "Co", "Ni",
    ]
    all_dfs = []
    for p in particles:
        try:
            tab = crdb.query(p, energy_type="EKN")
            # Flatten multidimensional recarray fields
            rows = []
            for rec in tab:
                row = {}
                for name in tab.dtype.names:
                    val = rec[name]
                    if hasattr(val, '__len__') and not isinstance(val, str) and len(val) == 2:
                        row[f"{name}_lo"] = val[0]
                        row[f"{name}_hi"] = val[1]
                    else:
                        row[name] = val
                rows.append(row)
            df_p = pd.DataFrame(rows)
            print(f"  {p}: {len(df_p):,} rows")
            all_dfs.append(df_p)
        except Exception as e:
            print(f"  {p}: skipped ({e})")

    if not all_dfs:
        print("::error::No data fetched from CRDB")
        sys.exit(1)

    df = pd.concat(all_dfs, ignore_index=True)
    df = df.drop_duplicates()
    print(f"  Total: {len(df):,} unique rows, {len(df.columns)} columns")

    # Rename columns to snake_case
    rename = {k: v for k, v in RENAME_MAP.items() if k in df.columns}
    df = df.rename(columns=rename)

    # Coerce numeric columns
    for col in ["energy_min_gev_n", "energy_max_gev_n", "flux",
                "error_low", "error_high"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Clean string columns
    for col in ["particle", "experiment", "sub_exp", "reference", "ads_url"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
            )

    # Convert is_usable to bool
    if "is_usable" in df.columns:
        df["is_usable"] = df["is_usable"].astype(bool)

    df = df.reset_index(drop=True)

    n_total = len(df)
    n_particles = df["particle"].nunique() if "particle" in df.columns else 0
    n_experiments = df["experiment"].nunique() if "experiment" in df.columns else 0
    print(f"  {n_total:,} measurements, {n_particles} particle types, {n_experiments} experiments")

    check_dataset(df, "crdb", min_rows=5000,
                  expected_columns=["particle", "experiment", "energy_gev_n", "flux"])

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "crdb_cosmic_ray_spectra.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Cosmic Ray Database (CRDB)"
language:
  - en
description: "Cosmic Ray Database — ALL cosmic ray measurements from 131 experiments and 504 papers. Energy spectra, flux measurements, and metadata for every published cosmic ray observation."
task_categories:
  - tabular-regression
tags:
  - physics
  - cosmic-ray
  - crdb
  - high-energy
  - particle
  - open-data
  - tabular-data
size_categories:
  - 100K<n<1M
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/crdb_cosmic_ray_spectra.parquet
    default: true
---

# Cosmic Ray Database (CRDB)

*Part of the [Physics Datasets](https://huggingface.co/collections/juliensimon/physics-datasets-69c2d4682d37dfdb77447bd7) collection on Hugging Face.*

![Update CRDB](https://github.com/juliensimon/space-datasets/actions/workflows/update-crdb.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.crdb&label=updated&color=brightgreen)

Complete cosmic ray spectral database from [CRDB](https://lpsc.in2p3.fr/crdb/) —
**{n_total:,}** measurements across **{n_particles}** particle types from
**{n_experiments}** experiments.

## Dataset description

The Cosmic Ray Database (CRDB) compiles all published cosmic ray measurements,
including energy spectra and flux data from ground-based detectors, balloon
experiments, and space missions. It is the reference database for cosmic ray
physics, maintained by D. Maurin et al. at LPSC Grenoble.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `particle` | string | Particle/nucleus type (e.g. "H", "He", "e-") |
| `experiment` | string | Experiment name (e.g. "AMS-02", "PAMELA") |
| `sub_exp` | string | Sub-experiment or detector |
| `energy_min_gev_n` | float | Energy bin lower edge (GeV/n) |
| `energy_max_gev_n` | float | Energy bin upper edge (GeV/n) |
| `flux` | float | Measured flux |
| `error_low` | float | Lower error on flux |
| `error_high` | float | Upper error on flux |
| `reference` | string | Publication reference |
| `ads_url` | string | ADS bibliographic URL |
| `is_usable` | bool | Whether the data point is recommended for use |

## Quick stats

- **{n_total:,}** measurements
- **{n_particles}** particle types
- **{n_experiments}** experiments

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/crdb-cosmic-ray-spectra", split="train")
df = ds.to_pandas()

# Proton spectrum from AMS-02
ams02_p = df[(df["particle"] == "H") & (df["experiment"] == "AMS-02")]
print(f"{{len(ams02_p):,}} AMS-02 proton data points")

# All experiments for a given particle
import matplotlib.pyplot as plt
protons = df[df["particle"] == "H"]
for exp, grp in protons.groupby("experiment"):
    e_mid = (grp["energy_min_gev_n"] + grp["energy_max_gev_n"]) / 2
    plt.scatter(e_mid, grp["flux"], s=1, label=exp, alpha=0.5)
plt.xscale("log"); plt.yscale("log")
plt.xlabel("Energy (GeV/n)"); plt.ylabel("Flux")
plt.title("Proton Cosmic Ray Spectrum")
```

## Data source

[CRDB — Cosmic Ray DataBase](https://lpsc.in2p3.fr/crdb/) (Maurin et al.)

All data retrieved via the `crdb` Python package.

## Update schedule

Quarterly (1st of Jan/Apr/Jul/Oct at 06:00 UTC) via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [juliensimon/auger-cosmic-rays](https://huggingface.co/datasets/juliensimon/auger-cosmic-rays) — Pierre Auger Observatory events

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/crdb-cosmic-ray-spectra) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{crdb_cosmic_ray_spectra,
  author = {{Simon, Julien}},
  title = {{Cosmic Ray Database (CRDB)}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/crdb-cosmic-ray-spectra}},
  note = {{Based on CRDB (Maurin et al.) via lpsc.in2p3.fr/crdb}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update CRDB cosmic ray spectra: {n_total:,} measurements"
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
