#!/usr/bin/env python3
"""
Fetch latest Starlink TLEs from CelesTrak, classify, aggregate, and upload to HF.

This is a lightweight daily updater — it fetches the current constellation snapshot,
not historical data. For historical backfill, use the bulk ingestion scripts in
the starlink-viz repo.
"""

import math
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests


CELESTRAK_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=json"
HF_REPO = "juliensimon/starlink-fleet-data"

MU = 398600.4418
R_EARTH = 6371.0

SHELL_NAMES = {
    0: "Shell 1 (33° / 328km)",
    1: "Shell 2 (43° / 340km)",
    2: "Shell 3 (53° / 550km)",
    3: "Shell 4 (70° / 570km)",
    4: "Shell 5 (97.6° / 560km)",
}

# Operational altitude bands per shell [min, max] in km
SHELL_ALT_BANDS = {
    0: (310, 340),
    1: (325, 355),
    2: (540, 560),
    3: (555, 575),
    4: (545, 570),
}


def altitude_from_mean_motion(n: float, ecc: float) -> float:
    if n <= 0:
        return -1.0
    n_rad = n * 2 * math.pi / 86400.0
    a = (MU / (n_rad ** 2)) ** (1.0 / 3.0)
    return a * (1 - ecc) - R_EARTH


def get_shell_id(inc: float) -> int:
    if inc < 38:
        return 0
    if inc < 48:
        return 1
    if inc < 60:
        return 2
    if inc < 80:
        return 3
    return 4


def is_isl_capable(inc: float, launch_year: int) -> bool:
    shell = get_shell_id(inc)
    if shell == 4:
        return launch_year >= 2022
    if shell == 2:
        return launch_year >= 2022
    if shell == 3:
        return launch_year >= 2022
    if shell == 1:
        return launch_year >= 2023
    if shell == 0:
        return launch_year >= 2024
    return False


def main():
    print("Fetching Starlink TLEs from CelesTrak...")
    resp = requests.get(CELESTRAK_URL, timeout=60)
    resp.raise_for_status()
    records = resp.json()
    print(f"  {len(records):,} satellites")

    now = datetime.now(timezone.utc)
    rows = []

    for r in records:
        name = r.get("OBJECT_NAME", "")
        if not name.startswith("STARLINK"):
            continue

        norad_id = r["NORAD_CAT_ID"]
        epoch = datetime.fromisoformat(r["EPOCH"].replace("Z", "+00:00"))
        inc = r["INCLINATION"]
        ecc = r["ECCENTRICITY"]
        mm = r["MEAN_MOTION"]
        alt = altitude_from_mean_motion(mm, ecc)

        if alt < 0 or alt > 2000:
            continue

        intl = r.get("OBJECT_ID", "")
        launch_year = int("20" + intl[:2]) if intl and intl[:2].isdigit() else 0
        if launch_year > 2100:
            launch_year -= 100

        shell_id = get_shell_id(inc)
        band = SHELL_ALT_BANDS.get(shell_id, (0, 0))
        is_operational = band[0] <= alt <= band[1]

        rows.append({
            "norad_id": norad_id,
            "name": name,
            "epoch_utc": epoch,
            "inclination": round(inc, 4),
            "raan": round(r["RA_OF_ASC_NODE"], 4),
            "eccentricity": ecc,
            "mean_motion": mm,
            "mean_motion_dot": r["MEAN_MOTION_DOT"],
            "altitude_km": round(alt, 2),
            "launch_year": launch_year,
            "shell_id": shell_id,
            "shell_name": SHELL_NAMES.get(shell_id, "Unknown"),
            "status": "operational" if is_operational else "unknown",
            "is_isl_capable": is_isl_capable(inc, launch_year),
        })

    df = pd.DataFrame(rows)
    print(f"  {len(df):,} Starlink satellites processed")

    # Build latest_satellites
    df_latest = df.sort_values("epoch_utc").drop_duplicates("norad_id", keep="last")
    df_latest["epoch_ts"] = df_latest["epoch_utc"].astype("int64") // 10**9

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        data_dir = tmp_dir / "data"
        data_dir.mkdir()

        df_latest.to_parquet(
            data_dir / "latest_satellites.parquet",
            index=False, engine="pyarrow", compression="zstd",
        )

        active = len(df_latest[df_latest["status"] == "operational"])
        print(f"  {active:,} operational, {len(df_latest):,} total")

        (tmp_dir / "README.md").write_text(f"""---
license: mit
tags: [space, starlink, satellite, tle, celestrak]
size_categories: [1K<n<10K]
---

# Starlink Fleet Data

![Update Starlink Fleet](https://github.com/juliensimon/space-datasets/actions/workflows/update-starlink.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.starlink&label=updated&color=brightgreen)

Latest Starlink constellation snapshot from [CelesTrak](https://celestrak.org/). {len(df_latest):,} satellites ({active:,} operational). Updated daily.

## Usage

```python
from datasets import load_dataset
ds = load_dataset("juliensimon/starlink-fleet-data", split="train")
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
