#!/usr/bin/env python3
"""Fetch Holczer et al. 2016 Kepler Transit Timing Catalog from VizieR and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from validate import check_dataset
from vizier_tap import vizier_query


HF_REPO = "juliensimon/kepler-transit-timing"

# Holczer et al. (2016), ApJS 225, 9 — 295,187 transit times for 2,599 KOIs
# Table 3: individual TTV, TDV, TPV changes per transit (295K rows)
ADQL = """\
SELECT * FROM "J/ApJS/225/9/table3"\
"""


def main():
    print("Fetching Kepler Transit Timing Catalog (Holczer et al. 2016) from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} raw rows")

    # Rename columns — use variants since VizieR names may differ
    known_renames = {
        "KOI": "koi",
        "N": "transit_number",
        "Ntr": "transit_number",
        "ntr": "transit_number",
        "tn": "t_obs_bjd",
        "Tobs": "t_obs_bjd",
        "tobs": "t_obs_bjd",
        "e_Tobs": "t_obs_err",
        "e_tobs": "t_obs_err",
        "O-C": "o_c",
        "o_c": "o_c",
        "e_O-C": "o_c_err",
        "e_o_c": "o_c_err",
        "f_O-C": "o_c_flag",
        "TDV": "tdv",
        "e_TDV": "tdv_err",
        "f_TDV": "tdv_flag",
        "TPV": "tpv",
        "e_TPV": "tpv_err",
        "f_TPV": "tpv_flag",
        "Out": "outlier",
        "Over": "overlap",
        "Dur": "duration_hr",
        "dur": "duration_hr",
        "e_Dur": "duration_err",
        "e_dur": "duration_err",
        "Depth": "depth_ppm",
        "depth": "depth_ppm",
        "e_Depth": "depth_err",
        "e_depth": "depth_err",
        "OC": "o_c",
        "e_OC": "o_c_err",
    }
    rename_map = {k: v for k, v in known_renames.items() if k in df.columns}
    if rename_map:
        df = df.rename(columns=rename_map)

    # Snake-case any remaining columns
    already_renamed = set(rename_map.values())
    snake_map = {}
    for col in df.columns:
        if col not in already_renamed:
            snake = col.replace(" ", "_").replace("-", "_").lower()
            if snake != col:
                snake_map[col] = snake
    if snake_map:
        df = df.rename(columns=snake_map)

    # Drop recno (VizieR internal)
    if "recno" in df.columns:
        df = df.drop(columns=["recno"])

    # Convert numerics
    for col in ["koi", "transit_number", "t_obs_bjd", "t_obs_err",
                "o_c", "o_c_err", "duration_hr", "duration_err",
                "depth_ppm", "depth_err"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Integer columns
    for col in ["transit_number"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int32")

    # Sort by KOI then transit number
    sort_cols = [c for c in ["koi", "transit_number"] if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols).reset_index(drop=True)

    # Stats
    n_total = len(df)
    n_kois = df["koi"].nunique() if "koi" in df.columns else 0
    median_oc = df["o_c"].median() if "o_c" in df.columns else float("nan")
    median_depth = df["depth_ppm"].median() if "depth_ppm" in df.columns else float("nan")
    median_dur = df["duration_hr"].median() if "duration_hr" in df.columns else float("nan")

    print(f"  {n_total:,} transits across {n_kois:,} KOIs")

    check_dataset(
        df,
        "kepler-ttv",
        min_rows=200_000,
        expected_columns=["koi", "transit_number", "t_obs_bjd", "o_c"],
        critical_columns=["koi", "t_obs_bjd"],
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "kepler_transit_timing.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Kepler Transit Timing Catalog"
language:
  - en
description: "Holczer et al. (2016) Kepler transit timing catalog — {n_total:,} individual transit times for {n_kois:,} Kepler Objects of Interest (KOIs), with O-C residuals, durations, and depths."
task_categories:
  - tabular-regression
tags:
  - space
  - exoplanets
  - kepler
  - transit-timing
  - ttv
  - astronomy
  - open-data
  - tabular-data
size_categories:
  - 100K<n<1M
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/kepler_transit_timing.parquet
    default: true
---

# Kepler Transit Timing Catalog

*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

Transit timing catalog from Holczer et al. (2016), containing **{n_total:,}** individual transit
mid-times for **{n_kois:,}** Kepler Objects of Interest (KOIs). Each record includes the
observed mid-transit time, observed-minus-computed (O-C) residual, transit duration, and
transit depth with uncertainties.

## Dataset description

Transit timing variations (TTVs) occur when gravitational interactions between planets in a
multi-planet system cause measurable deviations from a strictly periodic transit schedule.
Holczer et al. (2016) performed a uniform analysis of all Kepler long-cadence light curves
to extract individual transit times, producing the most comprehensive Kepler TTV catalog.
The O-C (observed minus computed) residuals reveal planetary interactions, orbital
eccentricities, and the presence of additional non-transiting planets.

## Key columns

| Column | Type | Description |
|--------|------|-------------|
| `koi` | float64 | Kepler Object of Interest number |
| `transit_number` | Int32 | Sequential transit number for this KOI |
| `t_obs_bjd` | float64 | Observed mid-transit time (BJD - 2454833) |
| `t_obs_err` | float64 | Uncertainty on mid-transit time (days) |
| `o_c` | float64 | Observed minus computed residual (days) |
| `o_c_err` | float64 | Uncertainty on O-C residual (days) |
| `duration_hr` | float64 | Transit duration (hours) |
| `duration_err` | float64 | Uncertainty on transit duration (hours) |
| `depth_ppm` | float64 | Transit depth (ppm) |
| `depth_err` | float64 | Uncertainty on transit depth (ppm) |

## Quick stats

- **{n_total:,}** individual transit times
- **{n_kois:,}** unique KOIs
- Median O-C residual: **{median_oc:.4f}** days
- Median transit depth: **{median_depth:.0f}** ppm
- Median transit duration: **{median_dur:.2f}** hours

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/kepler-transit-timing", split="train")
df = ds.to_pandas()

# TTVs for a specific KOI
koi_137 = df[df["koi"] == 137.01].sort_values("transit_number")
print(f"KOI 137.01: {{len(koi_137)}} transits")

# Plot O-C diagram
import matplotlib.pyplot as plt
plt.errorbar(koi_137["transit_number"], koi_137["o_c"],
             yerr=koi_137["o_c_err"], fmt=".", ms=3)
plt.xlabel("Transit number")
plt.ylabel("O-C (days)")
plt.title("KOI 137.01 Transit Timing Variations")
plt.show()

# KOIs with the strongest TTVs (largest O-C scatter)
ttv_rms = df.groupby("koi")["o_c"].std().sort_values(ascending=False)
print("Top 10 TTV candidates:")
print(ttv_rms.head(10))
```

## Data source

Holczer, T. et al. (2016), "Transit Timing Observations from Kepler. IX. Catalog of
Transit Timing Measurements of the Long-Cadence Data", ApJS, 225, 9. Accessed via
[VizieR](https://vizier.cds.unistra.fr/), CDS Strasbourg (J/ApJS/225/9).

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/kepler-transit-timing) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{kepler_transit_timing,
  author = {{Simon, Julien}},
  title = {{Kepler Transit Timing Catalog}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/kepler-transit-timing}},
  note = {{Based on Holczer et al. (2016) ApJS 225, 9, via VizieR CDS}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Upload Kepler transit timing: {n_total:,} transits, {n_kois:,} KOIs"
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
