#!/usr/bin/env python3
"""Fetch GCAT launch log and sites, upload to HF."""

import subprocess
import tempfile
from pathlib import Path

import pandas as pd


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

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        data_dir = tmp_dir / "data"
        data_dir.mkdir()
        df.to_parquet(data_dir / "launches.parquet", index=False, engine="pyarrow", compression="zstd")
        sites.to_parquet(data_dir / "sites.parquet", index=False, engine="pyarrow", compression="zstd")

        (tmp_dir / "README.md").write_text(f"""---
license: mit
tags: [space, launches, rockets, gcat]
configs:
  - config_name: launches
    data_files: data/launches.parquet
  - config_name: sites
    data_files: data/sites.parquet
size_categories: [10K<n<100K]
---

# Space Launch Log

![Update Launch Log](https://github.com/juliensimon/space-datasets/actions/workflows/update-launch-log.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['launch-log']&label=updated&color=brightgreen)

Global launch history from [GCAT](https://planet4589.org/space/gcat/). {len(df):,} launches, {len(sites):,} sites. Updated weekly.

## Usage

```python
from datasets import load_dataset
launches = load_dataset("juliensimon/space-launch-log", "launches", split="train")
sites = load_dataset("juliensimon/space-launch-log", "sites", split="train")
```
""")

        print("Uploading to HF...")
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp_dir), ".", "--repo-type", "dataset"],
            check=True,
        )

    print("Done.")


if __name__ == "__main__":
    main()
