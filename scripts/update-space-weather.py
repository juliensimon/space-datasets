#!/usr/bin/env python3
"""Fetch space weather indices from CelesTrak and upload to HF."""

import subprocess
import tempfile
from pathlib import Path

import pandas as pd


SW_URL = "https://celestrak.org/SpaceData/SW-All.csv"
HF_REPO = "juliensimon/space-weather-indices"

# NOAA Kp-based storm scale thresholds (max 3-hourly Kp in a day)

STORM_THRESHOLDS = [(9, "G5"), (8, "G4"), (7, "G3"), (6, "G2"), (5, "G1")]


def classify_storm(row):
    """Classify geomagnetic storm level from max Kp value."""
    kp_cols = [c for c in row.index if c.startswith("kp_") and c != "kp_sum"]
    kp_max = row[kp_cols].max()
    if pd.isna(kp_max):
        return None
    for threshold, level in STORM_THRESHOLDS:
        if kp_max >= threshold:
            return level
    return None


def main():
    print("Fetching space weather indices from CelesTrak...")
    df = pd.read_csv(SW_URL)
    print(f"  {len(df):,} daily records")

    # Type conversions
    df["DATE"] = pd.to_datetime(df["DATE"], errors="coerce")

    numeric_cols = [c for c in df.columns if c != "DATE" and c != "F10.7_DATA_TYPE"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Rename columns
    kp_map = {f"KP{i}": f"kp_{h:02d}00" for i, h in enumerate([0, 3, 6, 9, 12, 15, 18, 21], 1)}
    ap_map = {f"AP{i}": f"ap_{h:02d}00" for i, h in enumerate([0, 3, 6, 9, 12, 15, 18, 21], 1)}

    rename = {
        "DATE": "date",
        "BSRN": "bartels_rotation",
        "ND": "bartels_day",
        **kp_map,
        "KP_SUM": "kp_sum",
        **ap_map,
        "AP_AVG": "ap_avg",
        "CP": "cp",
        "C9": "c9",
        "ISN": "sunspot_number",
        "F10.7_OBS": "f107_obs",
        "F10.7_ADJ": "f107_adj",
        "F10.7_DATA_TYPE": "f107_data_type",
        "F10.7_OBS_CENTER81": "f107_obs_center81",
        "F10.7_OBS_LAST81": "f107_obs_last81",
        "F10.7_ADJ_CENTER81": "f107_adj_center81",
        "F10.7_ADJ_LAST81": "f107_adj_last81",
    }
    df = df.rename(columns=rename)

    # Derived columns
    df["is_storm"] = df["ap_avg"] >= 50
    df["storm_level"] = df.apply(classify_storm, axis=1)
    df["data_type"] = df["f107_data_type"].map({
        "OBS": "observed", "INT": "observed",
        "PRD": "predicted", "PRM": "predicted",
    })

    # Stats
    observed = df[df["data_type"] == "observed"]
    n_observed = len(observed)
    n_predicted = len(df) - n_observed
    n_storms = int(df["is_storm"].sum())
    n_g3_plus = int(df["storm_level"].isin(["G3", "G4", "G5"]).sum())
    date_min = df["date"].min().strftime("%Y-%m-%d")
    date_max_obs = observed["date"].max().strftime("%Y-%m-%d")
    max_ap = observed["ap_avg"].max()
    max_ap_date = observed.loc[observed["ap_avg"].idxmax(), "date"].strftime("%Y-%m-%d")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "space_weather_indices.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        banner_file = download_banner("space-weather", tmp)
        banner_md = banner_markdown("space-weather", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Space Weather Indices (Kp, Ap, F10.7)"
language:
  - en
description: "Daily geomagnetic and solar activity indices since 1957 from NOAA SWPC via CelesTrak — Kp, Ap, F10.7 flux, sunspot numbers."
task_categories:
  - tabular-regression
  - time-series-forecasting
tags:
  - space
  - space-weather
  - geomagnetic
  - solar
  - noaa
  - celestrak
  - open-data
  - kp-index
  - f10.7
  - sunspot
  - solar-cycle
  - swpc
  - tabular-data
  - parquet
size_categories:
  - 10K<n<100K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/space_weather_indices.parquet
    default: true
---

# Space Weather Indices
{banner_md}
*Part of the [Space Weather Datasets](https://huggingface.co/collections/juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70) collection on Hugging Face.*

![Update Space Weather](https://github.com/juliensimon/space-datasets/actions/workflows/update-space-weather.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['space-weather']&label=updated&color=brightgreen)

Daily geomagnetic and solar indices from [CelesTrak](https://celestrak.org/SpaceData/),
which mirrors NOAA Space Weather Prediction Center data. Covers **{date_min}** to present
with **{n_observed:,}** observed days plus **{n_predicted:,}** days of predictions/forecasts.

## Dataset description

This dataset contains the fundamental indices used to characterize space weather conditions:

- **Kp/Ap indices** — Planetary geomagnetic activity (3-hourly and daily). Higher values indicate
  stronger geomagnetic storms that cause satellite drag, GPS errors, and power grid disturbances.
- **F10.7 solar radio flux** — Proxy for solar EUV radiation that heats the upper atmosphere,
  directly affecting satellite drag and orbital decay rates.
- **International Sunspot Number** — Long-running indicator of solar activity cycle.

These indices together form the essential parameter set for characterizing the state of the heliosphere and its coupling to the terrestrial environment. The Kp index (quasi-logarithmic, 0-9 scale, 3-hourly) captures planetary-scale geomagnetic disturbances driven by solar wind-magnetosphere interactions, while the Ap index (its linearized daily equivalent in nanotesla) serves as the standard geomagnetic input to atmospheric density models. The F10.7 solar radio flux (measured daily at 2800 MHz in Penticton, Canada) is the primary proxy for solar extreme ultraviolet (EUV) radiation that heats the thermosphere -- the atmospheric layer where most satellites experience drag. The international sunspot number, recorded since 1749, provides the longest available record of solar activity and is used for solar cycle phase identification and long-term trend analysis.

The physical connections between these indices reflect the chain of solar-terrestrial coupling. Solar active regions produce both elevated F10.7 emission (from coronal gyroresonance above sunspot magnetic fields) and eruptive events (flares, CMEs) that ultimately drive Kp/Ap disturbances days later. During solar maximum, F10.7 values typically range from 150-250 SFU and Kp regularly reaches 5-7 during CME-driven storms; during solar minimum, F10.7 drops to 65-70 SFU and Kp rarely exceeds 3. The 81-day running averages of F10.7 (provided as centered and trailing variants) smooth out the 27-day solar rotation modulation and represent the background EUV irradiance level that determines the baseline thermospheric density.

For operational space weather applications, this dataset provides the complete set of inputs required by the major atmospheric density models: NRLMSISE-00 (F10.7, F10.7bar, Ap), JB2008 (F10.7 plus supplementary indices), and DTM (F10.7, Kp). These models are embedded in every operational orbit determination system worldwide, from the 18th Space Defense Squadron's high-accuracy catalog to commercial conjunction screening services. The storm classification (G1-G5) derived from Kp thresholds is the same scale used in NOAA space weather alerts that trigger operational responses by satellite operators, power utilities, and airlines.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `date` | datetime | Observation date |
| `bartels_rotation` | int | Bartels Solar Rotation Number (27-day cycle since 1832) |
| `bartels_day` | int | Day within Bartels cycle (1-27) |
| `kp_0000`–`kp_2100` | float | 3-hourly Kp index for each UT interval |
| `kp_sum` | float | Sum of eight daily Kp values |
| `ap_0000`–`ap_2100` | int | 3-hourly Ap index for each UT interval |
| `ap_avg` | float | Daily average Ap index |
| `cp` | float | Daily Character Figure (0-2.5) |
| `c9` | int | Converted Cp (0-9 scale) |
| `sunspot_number` | int | International Sunspot Number |
| `f107_obs` | float | Observed 10.7cm solar radio flux (sfu) |
| `f107_adj` | float | F10.7 adjusted to 1 AU |
| `f107_data_type` | string | Source: OBS (observed), INT (interpolated), PRD/PRM (predicted) |
| `f107_obs_center81` | float | 81-day centered average (observed) |
| `f107_obs_last81` | float | 81-day trailing average (observed) |
| `f107_adj_center81` | float | 81-day centered average (adjusted) |
| `f107_adj_last81` | float | 81-day trailing average (adjusted) |
| `is_storm` | bool | Geomagnetic storm flag (daily Ap >= 50) |
| `storm_level` | string | NOAA G-scale: G1 (minor) to G5 (extreme), based on max Kp |
| `data_type` | string | "observed" or "predicted" |

## Quick stats

- **{n_observed:,}** observed days ({date_min} to {date_max_obs})
- **{n_storms:,}** geomagnetic storm days (Ap >= 50)
- **{n_g3_plus:,}** severe storms (G3+)
- Strongest storm: Ap={max_ap:.0f} on {max_ap_date}

## Usage

```python
from dataset_images import banner_markdown, download_banner
from datasets import load_dataset

ds = load_dataset("juliensimon/space-weather-indices", split="train")
df = ds.to_pandas()

# Only observed data (exclude predictions)
observed = df[df["data_type"] == "observed"]

# Geomagnetic storms
storms = df[df["is_storm"] == True].sort_values("ap_avg", ascending=False)

# Solar cycle visualization
df["year"] = df["date"].dt.year
yearly_ssn = df.groupby("year")["sunspot_number"].mean()

# F10.7 flux trend (drives atmospheric drag)
df.set_index("date")[["f107_adj"]].rolling(81).mean().plot()

# Storm frequency by solar cycle phase
df["cycle_phase"] = df["sunspot_number"].rolling(365).mean()
```

## Data source

[CelesTrak Space Weather Data](https://celestrak.org/SpaceData/), maintained by Dr. T.S. Kelso,
mirroring NOAA SWPC and GFZ Potsdam geomagnetic indices. The original indices are produced by the
International Service of Geomagnetic Indices (ISGI) and NOAA Space Weather Prediction Center.

## Update schedule

Daily at 11:00 UTC via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [solar-flare-events](https://huggingface.co/datasets/juliensimon/solar-flare-events) — Individual solar flare detections from GOES
- [space-track-satcat](https://huggingface.co/datasets/juliensimon/space-track-satcat) — Full NORAD satellite catalog
- [space-track-tle-history](https://huggingface.co/datasets/juliensimon/space-track-tle-history) — 232M historical TLE records
- [neo-close-approaches](https://huggingface.co/datasets/juliensimon/neo-close-approaches) — Near-Earth object approaches

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/space-weather-indices) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{space_weather,
  author = {{Simon, Julien}},
  title = {{Space Weather Indices}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/space-weather-indices}},
  note = {{Based on NOAA/SWPC space weather data}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update space weather indices: {n_observed:,} observed days"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    print("Done.")


if __name__ == "__main__":
    main()
