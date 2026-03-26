#!/usr/bin/env python3
"""Fetch Gaia DR3 Young Stellar Objects catalog from ESA Gaia Archive and upload to HF."""

import io
import os
import subprocess
import tempfile
import time
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset

GAIA_TAP = "https://gea.esac.esa.int/tap-server/tap/sync"
HF_REPO = "juliensimon/gaia-dr3-young-stellar-objects"
PAGE_SIZE = 500_000


def fetch_gaia_yso():
    """Fetch young stellar objects from Gaia archive with OFFSET pagination."""
    all_dfs = []
    offset = 0
    while True:
        query = (
            f"SELECT * FROM gaiadr3.vari_young_stellar_object "
            f"ORDER BY source_id "
            f"OFFSET {offset}"
        )
        print(f"  Fetching rows {offset:,}–{offset + PAGE_SIZE:,}...")
        resp = requests.post(GAIA_TAP, data={
            "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv",
            "QUERY": query, "MAXREC": PAGE_SIZE,
        }, timeout=600)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text))
        if len(df) == 0:
            break
        all_dfs.append(df)
        print(f"    got {len(df):,} rows")
        offset += len(df)
        if len(df) < PAGE_SIZE:
            break
        time.sleep(2)
    return pd.concat(all_dfs, ignore_index=True)


def main():
    print("Fetching Gaia DR3 Young Stellar Objects from ESA Gaia Archive...")
    df = fetch_gaia_yso()
    print(f"  {len(df):,} raw rows")

    # Gaia archive returns snake_case columns — convert any object columns to numeric
    for col in df.select_dtypes(include=["object"]).columns:
        converted = pd.to_numeric(df[col], errors="coerce")
        # Only convert if most values survived (skip true string columns)
        if converted.notna().sum() > 0.5 * df[col].notna().sum():
            df[col] = converted

    # Integer columns
    int_cols = [
        "number_of_clean_epochs_g", "number_of_clean_epochs_bp",
        "number_of_clean_epochs_rp",
    ]
    for col in int_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int32")

    # Derived: color index
    if "median_mag_bp" in df.columns and "median_mag_rp" in df.columns:
        df["bp_rp"] = df["median_mag_bp"] - df["median_mag_rp"]

    # Sort by source_id
    if "source_id" in df.columns:
        df = df.sort_values("source_id").reset_index(drop=True)

    # Stats
    n_total = len(df)
    classifications = df["best_class_name"].value_counts() if "best_class_name" in df.columns else pd.Series(dtype=int)
    class_summary = ", ".join(f"{k}: {v:,}" for k, v in classifications.head(5).items())
    g_median = df["median_mag_g_fov"].median() if "median_mag_g_fov" in df.columns else float("nan")

    # Validate
    check_dataset(
        df,
        "gaia-yso",
        min_rows=50_000,
        expected_columns=["source_id", "best_class_name"],
        critical_columns=["source_id", "best_class_name"],
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "gaia_dr3_young_stellar_objects.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Gaia DR3 Young Stellar Objects"
language:
  - en
description: "Gaia DR3 young stellar object (YSO) candidates — {n_total:,} pre-main-sequence stars with classification (CTTS, WTTS, HAeBe), variability parameters, and multi-band photometry from ESA Gaia mission."
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - gaia
  - yso
  - young-stars
  - star-formation
  - esa
  - astronomy
  - open-data
  - tabular-data
size_categories:
  - 10K<n<100K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/gaia_dr3_young_stellar_objects.parquet
    default: true
---

# Gaia DR3 Young Stellar Objects

*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

The Gaia DR3 young stellar object (YSO) catalog, containing **{n_total:,}** YSO candidates
identified by the ESA Gaia mission's variability processing pipeline. Each source includes
a YSO classification (Classical T Tauri, Weak-line T Tauri, Herbig Ae/Be, etc.),
variability parameters, photometric amplitudes, and multi-band photometry (G, BP, RP).

## Dataset description

Young stellar objects are pre-main-sequence stars still in the process of forming, often
surrounded by circumstellar disks and exhibiting irregular photometric variability. Gaia's
all-sky photometric survey identified these candidates through automated variability
classification. The `best_class_name` field provides the specific YSO subtype:
- **CTTS** — Classical T Tauri stars (strong accretion)
- **WTTS** — Weak-line T Tauri stars (little/no accretion)
- **HAeBe** — Herbig Ae/Be stars (intermediate-mass pre-main-sequence)
- **FUOR** — FU Orionis variables (episodic accretion outbursts)
- **DIPDIPPER** — Dipper-type variables (disk occultation)

## Key columns

| Column | Type | Description |
|--------|------|-------------|
| `source_id` | int64 | Gaia DR3 unique source identifier |
| `best_class_name` | string | YSO classification (CTTS, WTTS, HAeBe, etc.) |
| `best_class_score` | float64 | Classification confidence score |
| `median_mag_g_fov` | float64 | Median G-band magnitude |
| `median_mag_bp` | float64 | Median BP-band magnitude |
| `median_mag_rp` | float64 | Median RP-band magnitude |
| `bp_rp` | float64 | BP-RP color index (derived) |
| `trimmed_range_mag_g_fov` | float64 | G-band variability amplitude |
| `trimmed_range_mag_bp` | float64 | BP-band variability amplitude |
| `trimmed_range_mag_rp` | float64 | RP-band variability amplitude |
| `std_dev_mag_g_fov` | float64 | G-band magnitude standard deviation |
| `number_of_clean_epochs_g` | Int32 | Number of clean G-band observations |

Full schema includes {len(df.columns)} columns with variability metrics and photometric parameters.

## Quick stats

- **{n_total:,}** YSO candidates
- Median G magnitude: {g_median:.2f}
- Classification breakdown: {class_summary}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/gaia-dr3-young-stellar-objects", split="train")
df = ds.to_pandas()

# Classification distribution
print(df["best_class_name"].value_counts())

# T Tauri stars only
ttauri = df[df["best_class_name"].isin(["CTTS", "WTTS"])]
print(f"T Tauri stars: {{len(ttauri):,}}")

# Color-magnitude diagram
import matplotlib.pyplot as plt
for cls in df["best_class_name"].unique():
    sub = df[df["best_class_name"] == cls]
    plt.scatter(sub["bp_rp"], sub["median_mag_g_fov"], s=1, alpha=0.3, label=cls)
plt.xlabel("BP - RP (mag)")
plt.ylabel("G (mag)")
plt.gca().invert_yaxis()
plt.legend(markerscale=5)
plt.title("Gaia DR3 YSO Color-Magnitude Diagram")
plt.show()
```

## Data source

Gaia Collaboration (2023), *Gaia Data Release 3: variability processing and analysis results.*
European Space Agency. Via ESA Gaia Archive (gaiadr3.vari_young_stellar_object).

## Related datasets

- [Gaia DR3 Eclipsing Binaries](https://huggingface.co/datasets/juliensimon/gaia-dr3-eclipsing-binaries) — Gaia eclipsing binary candidates
- [Gaia DR3 Variable Star Summary](https://huggingface.co/datasets/juliensimon/gaia-dr3-variable-summary) — all Gaia variable star classifications

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Citation

```bibtex
@dataset{{gaia_dr3_young_stellar_objects,
  author = {{Simon, Julien}},
  title = {{Gaia DR3 Young Stellar Objects}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/gaia-dr3-young-stellar-objects}},
  note = {{Based on Gaia DR3 (ESA)}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update Gaia DR3 young stellar objects: {n_total:,} sources"
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
