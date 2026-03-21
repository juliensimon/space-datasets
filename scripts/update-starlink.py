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
# Synced from starlink-viz src/lib/config.ts SHELL_ALT_BANDS
SHELL_ALT_BANDS = {
    0: (460, 570),   # 33° — not yet launched, wide band
    1: (460, 570),   # 43° — Gen1 at 480-490 + 540-560 km
    2: (460, 570),   # 53° — Gen1 at 480-490 + 540-560 km
    3: (460, 910),   # 70° — wide range, some at ~880-900 km
    4: (460, 600),   # 97.6° — observed 550-590 km
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


def classify_status(
    alt: float, inc: float, ecc: float,
    epoch_age_hours: float, mm_dot: float,
) -> str:
    """Single-snapshot status classification.

    Without altitude history, we use mean_motion_dot (orbital decay rate)
    as a proxy for raising vs deorbiting:
      mm_dot > 0  →  orbit shrinking (natural drag or active deorbit)
      mm_dot < 0  →  orbit growing (active raising via thrust)

    Starlink deployment: satellites are inserted at a parking orbit
    (often ~300-530km) then raise to their operational altitude using
    ion thrusters. Shells 1-2 (33°/43°) operate at ~330-350km but are
    deployed at ~490-530km and lower down. All other shells raise up.
    """
    shell_id = get_shell_id(inc)
    band = SHELL_ALT_BANDS.get(shell_id, (0, 0))
    min_alt, max_alt = band

    # Decayed: very low or stale epoch + low altitude
    if alt < 150:
        return "decayed"
    if epoch_age_hours > 336 and alt < 250:  # 14 days stale + low
        return "decayed"

    # Anomalous: high eccentricity
    if ecc > 0.005:
        return "anomalous"

    # Operational: within shell altitude band
    if min_alt <= alt <= max_alt:
        return "operational"

    # Above the band — in parking/drift orbit, lowering to operational alt
    # (common for Shells 1-2 which operate at ~330-350km but deploy at ~490-530km)
    if alt > max_alt:
        # mm_dot > 0 means orbit shrinking → actively lowering to operational alt
        if mm_dot > 0:
            return "raising"
        # mm_dot ~ 0 or slightly negative: just deployed, not yet maneuvering
        return "raising"

    # Below the band — raising or deorbiting?
    if alt < min_alt:
        # mm_dot < 0 means orbit is growing = raising
        if mm_dot < -0.0001:
            return "raising"
        # Actively deorbiting: strong positive mm_dot or very low altitude
        if mm_dot > 0.01 or alt < 300:
            return "deorbiting"
        # Close to band (within 20km), unclear direction
        if alt >= min_alt - 20:
            return "raising"
        return "raising"  # below band, assume still raising

    return "unknown"


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
        epoch_str = r["EPOCH"]
        if epoch_str.endswith("Z"):
            epoch_str = epoch_str[:-1] + "+00:00"
        epoch = datetime.fromisoformat(epoch_str)
        if epoch.tzinfo is None:
            epoch = epoch.replace(tzinfo=timezone.utc)
        inc = r["INCLINATION"]
        ecc = r["ECCENTRICITY"]
        mm = r["MEAN_MOTION"]
        alt = altitude_from_mean_motion(mm, ecc)

        if alt < 0 or alt > 2000:
            continue

        intl = r.get("OBJECT_ID", "")
        # OBJECT_ID is COSPAR format: "2024-123A" (4-digit year)
        launch_year = int(intl[:4]) if intl and intl[:4].isdigit() else 0

        shell_id = get_shell_id(inc)
        mm_dot = r["MEAN_MOTION_DOT"]
        epoch_age_hours = (now - epoch).total_seconds() / 3600

        status = classify_status(alt, inc, ecc, epoch_age_hours, mm_dot)

        rows.append({
            "norad_id": norad_id,
            "name": name,
            "epoch_utc": epoch,
            "inclination": round(inc, 4),
            "raan": round(r["RA_OF_ASC_NODE"], 4),
            "eccentricity": ecc,
            "mean_motion": mm,
            "mean_motion_dot": mm_dot,
            "altitude_km": round(alt, 2),
            "launch_year": launch_year,
            "shell_id": shell_id,
            "shell_name": SHELL_NAMES.get(shell_id, "Unknown"),
            "status": status,
            "is_isl_capable": is_isl_capable(inc, launch_year),
        })

    df = pd.DataFrame(rows)
    print(f"  {len(df):,} Starlink satellites processed")

    # Build latest_satellites
    df_latest = df.sort_values("epoch_utc").drop_duplicates("norad_id", keep="last")
    df_latest["epoch_ts"] = df_latest["epoch_utc"].astype("int64") // 10**9

    # Build daily_snapshots: per-shell aggregates for today
    today = pd.Timestamp(now.strftime("%Y-%m-%d"))
    daily_rows = []
    for sid in sorted(df_latest["shell_id"].unique()):
        shell = df_latest[df_latest["shell_id"] == sid]
        daily_rows.append({
            "date": today,
            "shell_id": int(sid),
            "shell_name": SHELL_NAMES.get(int(sid), "Unknown"),
            "total_count": len(shell),
            "operational_count": int((shell["status"] == "operational").sum()),
            "raising_count": int((shell["status"] == "raising").sum()),
            "deorbiting_count": int((shell["status"] == "deorbiting").sum()),
            "isl_operational_count": int(shell["is_isl_capable"].sum()),
            "new_launches": 0,
        })
    df_today = pd.DataFrame(daily_rows)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        data_dir = tmp_dir / "data"
        data_dir.mkdir()

        # Download existing daily_snapshots and append today
        daily_path = data_dir / "daily_snapshots.parquet"
        try:
            subprocess.run(
                ["hf", "download", HF_REPO, "data/daily_snapshots.parquet",
                 "--repo-type", "dataset", "--local-dir", str(tmp_dir)],
                check=True, capture_output=True, timeout=30,
            )
            if daily_path.exists():
                df_existing = pd.read_parquet(daily_path)
                # Remove any existing rows for today (idempotent re-runs)
                df_existing["date"] = pd.to_datetime(df_existing["date"])
                df_existing = df_existing[df_existing["date"] != today]
                df_daily = pd.concat([df_existing, df_today], ignore_index=True)
                print(f"  daily_snapshots: appended {today} ({len(df_daily):,} total rows)")
            else:
                df_daily = df_today
                print(f"  daily_snapshots: created with {today}")
        except Exception as e:
            print(f"  daily_snapshots: could not fetch existing ({e}), starting fresh")
            df_daily = df_today

        df_daily.to_parquet(daily_path, index=False, engine="pyarrow", compression="zstd")

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
