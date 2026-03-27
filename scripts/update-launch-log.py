#!/usr/bin/env python3
"""Fetch GCAT launch log and sites, upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from validate import check_dataset


LAUNCH_URL = "https://planet4589.org/space/gcat/tsv/launch/launch.tsv"
SITES_URL = "https://planet4589.org/space/gcat/tsv/tables/sites.tsv"
HF_REPO = "juliensimon/space-launch-log"

LAUNCH_COLS = [
    "launch_tag", "launch_jd", "launch_date", "lv_type", "variant", "flight_id",
    "flight", "mission", "flight_code", "platform", "launch_site", "launch_pad",
    "ascent_site", "ascent_pad", "apogee", "apogee_flag", "range", "range_flag",
    "destination", "orbital_payload", "agency", "launch_code", "fail_code",
    "group", "category", "lt_cite", "cite", "notes",
]

SITES_COLS = [
    "site", "code", "ucode", "type", "state_code", "start", "stop", "short_name",
    "name", "location", "longitude", "latitude", "error", "parent",
    "short_ename", "ename", "group", "uname",
]


def main():
    print("Fetching GCAT launch log...")
    df = pd.read_csv(LAUNCH_URL, sep="\t", comment="#", names=LAUNCH_COLS, low_memory=False)
    df["launch_jd"] = pd.to_numeric(df["launch_jd"], errors="coerce")
    df["apogee"] = pd.to_numeric(df["apogee"], errors="coerce")
    df["range"] = pd.to_numeric(df["range"], errors="coerce")
    print(f"  {len(df):,} launches")

    print("Fetching GCAT sites...")
    sites = pd.read_csv(SITES_URL, sep="\t", comment="#", names=SITES_COLS, low_memory=False)
    sites["longitude"] = pd.to_numeric(sites["longitude"], errors="coerce")
    sites["latitude"] = pd.to_numeric(sites["latitude"], errors="coerce")
    print(f"  {len(sites):,} sites")

    check_dataset(df, "launches", min_rows=70000,
        expected_columns=["launch_tag", "launch_date", "lv_type", "launch_site"],
        critical_columns=["launch_tag"])
    check_dataset(sites, "sites", min_rows=600,
        expected_columns=["site", "name", "longitude", "latitude"],
        critical_columns=["longitude", "latitude"])

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        data_dir = tmp_dir / "data"
        data_dir.mkdir()
        df.to_parquet(data_dir / "launches.parquet", index=False, engine="pyarrow", compression="zstd")
        sites.to_parquet(data_dir / "sites.parquet", index=False, engine="pyarrow", compression="zstd")

        # Compute stats for README
        n_orbital = int(df["launch_code"].str[0].eq("O").sum()) if "launch_code" in df.columns else 0
        n_suborbital = int(df["launch_code"].str[0].eq("S").sum()) if "launch_code" in df.columns else 0
        n_agencies = df["agency"].nunique()
        first_year = df["launch_date"].str[:4].min() if "launch_date" in df.columns else "1957"
        latest_year = df["launch_date"].str[:4].max() if "launch_date" in df.columns else "2026"
        n_site_types = sites["type"].nunique() if "type" in sites.columns else 0

        (tmp_dir / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Global Space Launch Log"
language:
  - en
description: "Every orbital launch attempt since 1957 from Jonathan McDowell's GCAT, with vehicles, sites, and outcomes. Updated weekly."
task_categories:
  - tabular-classification
  - time-series-forecasting
tags:
  - space
  - launches
  - rockets
  - gcat
  - orbital-mechanics
  - open-data
  - spaceflight
  - nasa
  - launch-vehicle
  - tabular-data
configs:
  - config_name: launches
    data_files:
      - split: train
        path: data/launches.parquet
  - config_name: sites
    data_files:
      - split: train
        path: data/sites.parquet
size_categories:
  - 10K<n<100K
---

# Space Launch Log

*Part of the [Orbital Mechanics Datasets](https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994) collection on Hugging Face.*

![Update Launch Log](https://github.com/juliensimon/space-datasets/actions/workflows/update-launch-log.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['launch-log']&label=updated&color=brightgreen)

Complete global launch history from [GCAT](https://planet4589.org/space/gcat/)
(General Catalog of Artificial Space Objects), maintained by Jonathan McDowell.
Currently **{len(df):,}** launches ({n_orbital:,} orbital, {n_suborbital:,} suborbital)
from **{len(sites):,}** sites, spanning {first_year}–{latest_year}.

## Configs

### `launches` — {len(df):,} launch records

Every known launch attempt — orbital, suborbital, and failed — from {first_year} to present.

| Column | Type | Description |
|--------|------|-------------|
| `launch_tag` | string | Unique GCAT launch identifier |
| `launch_jd` | float | Launch time as Julian Date |
| `launch_date` | string | Launch date (ISO-ish format) |
| `lv_type` | string | Launch vehicle type (e.g. "Falcon 9") |
| `variant` | string | Vehicle variant |
| `flight_id` | string | Flight identifier |
| `flight` | string | Flight number |
| `mission` | string | Mission name |
| `flight_code` | string | Flight code |
| `platform` | string | Launch platform |
| `launch_site` | string | Launch site code |
| `launch_pad` | string | Launch pad identifier |
| `ascent_site` | string | Ascent site (if different from launch) |
| `ascent_pad` | string | Ascent pad |
| `apogee` | float | Apogee altitude in km |
| `apogee_flag` | string | Apogee qualifier flag |
| `range` | float | Range in km |
| `range_flag` | string | Range qualifier flag |
| `destination` | string | Target orbit/destination |
| `orbital_payload` | string | Whether payload reached orbit |
| `agency` | string | Responsible agency/operator |
| `launch_code` | string | Launch outcome code |
| `fail_code` | string | Failure details (if applicable) |
| `group` | string | Launch group |
| `category` | string | `O` (orbital), `S` (suborbital), etc. |
| `lt_cite` | string | Launch time citation |
| `cite` | string | General citation |
| `notes` | string | Additional notes |

### `sites` — {len(sites):,} launch sites

Launch facilities, pads, and test ranges worldwide.

| Column | Type | Description |
|--------|------|-------------|
| `site` | string | Site identifier |
| `code` | string | Short code |
| `ucode` | string | Unicode code |
| `type` | string | Site type |
| `state_code` | string | Country/state code |
| `start` | string | First operational date |
| `stop` | string | Last operational date |
| `short_name` | string | Short name |
| `name` | string | Full name |
| `location` | string | Geographic location description |
| `longitude` | float | Longitude (WGS-84) |
| `latitude` | float | Latitude (WGS-84) |
| `error` | string | Position error estimate |
| `parent` | string | Parent site (for pads within complexes) |
| `short_ename` | string | Short English name |
| `ename` | string | Full English name |
| `group` | string | Site group |
| `uname` | string | Unicode name |

## Quick stats

- **{len(df):,}** launches ({n_orbital:,} orbital, {n_suborbital:,} suborbital)
- **{n_agencies}** distinct agencies/operators
- **{len(sites):,}** launch sites
- Coverage: **{first_year}–{latest_year}**

## Usage

```python
from datasets import load_dataset

launches = load_dataset("juliensimon/space-launch-log", "launches", split="train")
sites = load_dataset("juliensimon/space-launch-log", "sites", split="train")

df = launches.to_pandas()

# Launches per year
df["year"] = df["launch_date"].str[:4]
print(df["year"].value_counts().sort_index().tail(10))

# Most-used launch vehicles
print(df["lv_type"].value_counts().head(10))

# Orbital launches only (launch_code starts with O)
orbital = df[df["launch_code"].str[0] == "O"]

# Join with site coordinates
sites_df = sites.to_pandas()
df_geo = df.merge(sites_df[["code", "latitude", "longitude"]],
                  left_on="launch_site", right_on="code", how="left")
```

## Data source

[GCAT](https://planet4589.org/space/gcat/) (General Catalog of Artificial Space Objects)
by Jonathan McDowell, Harvard-Smithsonian Center for Astrophysics. GCAT is the most
comprehensive public catalog of space launches and is widely used in the spaceflight
research community.

## Update schedule

Weekly on Mondays at 07:00 UTC via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [starlink-fleet-data](https://huggingface.co/datasets/juliensimon/starlink-fleet-data) — Daily Starlink constellation health snapshots
- [space-track-satcat](https://huggingface.co/datasets/juliensimon/space-track-satcat) — NORAD satellite catalog
- [starlink-ground-stations](https://huggingface.co/datasets/juliensimon/starlink-ground-stations) — Starlink gateway and PoP locations

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/space-launch-log) and share feedback in the Community tab!

## Citation

```bibtex
@dataset{{space_launch_log,
  author = {{Simon, Julien}},
  title = {{Space Launch Log}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/space-launch-log}},
  note = {{Based on GCAT (General Catalog of Artificial Space Objects) by Jonathan McDowell, Harvard-Smithsonian Center for Astrophysics}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update launch log: {len(df):,} launches, {len(sites):,} sites"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp_dir), ".",
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
