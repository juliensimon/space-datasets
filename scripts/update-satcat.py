#!/usr/bin/env python3
"""Fetch NORAD SATCAT from CelesTrak and upload to HF."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

from validate import check_dataset


SATCAT_URL = "https://celestrak.org/pub/satcat.csv"
HF_REPO = "juliensimon/space-track-satcat"


def main():
    print("Fetching SATCAT from CelesTrak...")
    df = pd.read_csv(SATCAT_URL)
    print(f"  {len(df):,} objects")

    # Clean up types
    df["LAUNCH_DATE"] = pd.to_datetime(df["LAUNCH_DATE"], errors="coerce")
    df["DECAY_DATE"] = pd.to_datetime(df["DECAY_DATE"], errors="coerce")
    df["NORAD_CAT_ID"] = df["NORAD_CAT_ID"].astype("int32")
    df["RCS"] = pd.to_numeric(df["RCS"], errors="coerce")

    # Rename for consistency
    df = df.rename(columns={
        "OBJECT_NAME": "object_name",
        "OBJECT_ID": "intl_designator",
        "NORAD_CAT_ID": "norad_id",
        "OBJECT_TYPE": "object_type",
        "OPS_STATUS_CODE": "ops_status",
        "OWNER": "owner",
        "LAUNCH_DATE": "launch_date",
        "LAUNCH_SITE": "launch_site",
        "DECAY_DATE": "decay_date",
        "PERIOD": "period_min",
        "INCLINATION": "inclination",
        "APOGEE": "apogee_km",
        "PERIGEE": "perigee_km",
        "RCS": "rcs_m2",
        "DATA_STATUS_CODE": "data_status",
        "ORBIT_CENTER": "orbit_center",
        "ORBIT_TYPE": "orbit_type",
    })

    check_dataset(df, "satcat", min_rows=60000,
        expected_columns=["object_name", "norad_id", "object_type", "launch_date",
                          "inclination", "apogee_km", "perigee_km"],
        critical_columns=["norad_id", "object_name"])

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "satcat.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: mit
tags: [space, satellite, norad, celestrak]
size_categories: [10K<n<100K]
---

# NORAD SATCAT

![Update SATCAT](https://github.com/juliensimon/space-datasets/actions/workflows/update-satcat.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.satcat&label=updated&color=brightgreen)

Complete NORAD Satellite Catalog from [CelesTrak](https://celestrak.org/pub/satcat.csv). {len(df):,} objects. Updated daily.

## Usage

```python
from datasets import load_dataset
ds = load_dataset("juliensimon/space-track-satcat", split="train")
```
""")

        print("Uploading to HF...")
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".", "--repo-type", "dataset"],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={len(df)}\n")
    print("Done.")


if __name__ == "__main__":
    main()
