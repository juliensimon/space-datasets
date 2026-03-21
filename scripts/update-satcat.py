#!/usr/bin/env python3
"""Fetch NORAD SATCAT from CelesTrak and upload to HF."""

import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd


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

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "satcat.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        print("Uploading to HF...")
        subprocess.run(
            ["hf", "upload", HF_REPO, str(out), "data/satcat.parquet",
             "--repo-type", "dataset"],
            check=True,
        )

    print("Done.")


if __name__ == "__main__":
    main()
