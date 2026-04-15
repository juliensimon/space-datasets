#!/usr/bin/env python3
"""Fetch latest Amazon Project Kuiper TLEs from CelesTrak, classify, and upload to HF.

Daily snapshot of the Kuiper broadband constellation. Mirrors the Starlink pipeline
but uses a simpler shell model: Kuiper's FCC-authorized design has three shells at
590 km (33 deg), 610 km (42 deg), and 630 km (51.9 deg). As of first deployment
only the 51.9 deg shell is populated.

Source: CelesTrak GP data (NORAD/18th Space Defense Squadron)
"""

import math
import sys
from datetime import datetime, timezone

import pandas as pd
import requests

from hf_dataset_utils import Pipeline
from hf_dataset_utils.upload import write_parquet

CELESTRAK_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP=kuiper&FORMAT=json"
HF_REPO = "juliensimon/kuiper-fleet-data"

MU = 398600.4418
R_EARTH = 6371.0

# Project Kuiper planned shells (from Amazon FCC filings SAT-LOA-20190704-00057)
SHELLS = [
    {"id": 0, "inc_min": 30, "inc_max": 36, "target_alt": 590, "name": "Shell 1 (33 deg / 590km)"},
    {"id": 1, "inc_min": 39, "inc_max": 45, "target_alt": 610, "name": "Shell 2 (42 deg / 610km)"},
    {"id": 2, "inc_min": 48, "inc_max": 55, "target_alt": 630, "name": "Shell 3 (51.9 deg / 630km)"},
]
SHELL_NAMES = {s["id"]: s["name"] for s in SHELLS}

COLUMN_DAILY_DESCRIPTIONS = {
    "date": "UTC date of the daily snapshot; one row per shell per date",
    "shell_id": "Integer shell identifier (0-2); 0=33 deg, 1=42 deg, 2=51.9 deg",
    "shell_name": "Human-readable shell label encoding inclination and target altitude",
    "total_count": "Total Kuiper objects tracked in this shell on this date, all statuses",
    "operational_count": "Satellites within 20 km of the shell's target altitude",
    "raising_count": "Satellites climbing toward target altitude (below target, stable or ascending)",
    "deorbiting_count": "Satellites below 350 km with positive mean_motion_dot (controlled deorbit)",
    "mean_altitude_km": "Mean altitude of satellites in this shell, kilometres above Earth's surface",
}

DESCRIPTION = """\
Daily health snapshots of Amazon's Project Kuiper broadband constellation, derived from \
CelesTrak GP (General Perturbations) data. Tracks satellite count, orbital shell, and \
lifecycle status across the three FCC-authorized Kuiper shells.

Project Kuiper is Amazon's answer to SpaceX Starlink: a low-Earth-orbit broadband \
constellation of 3,236 satellites authorized by the FCC to deliver internet service \
globally via the Leo network integrated with Amazon Web Services. Kuiper launched its \
first production satellites in 2025 and is ramping deployment on Atlas V, Vulcan, Falcon 9, \
and New Glenn rockets. The constellation operates in three inclination shells at altitudes \
between 590 km and 630 km, each hosting multiple orbital planes.

This dataset mirrors the schema of the companion juliensimon/starlink-fleet-data dataset, \
enabling direct side-by-side comparison of the two largest commercial LEO broadband \
constellations. Status is inferred from orbital mechanics alone: satellites within 20 km \
of their shell's target altitude are classified operational; those below are raising or \
deorbiting depending on mean motion derivative.\
"""


def altitude_from_mean_motion(n: float, ecc: float) -> float:
    if n <= 0:
        return -1.0
    n_rad = n * 2 * math.pi / 86400.0
    a = (MU / (n_rad ** 2)) ** (1.0 / 3.0)
    return a * (1 - ecc) - R_EARTH


def get_shell_id(inc: float) -> int:
    for s in SHELLS:
        if s["inc_min"] <= inc <= s["inc_max"]:
            return s["id"]
    return -1


def classify_status(alt: float, shell_id: int, mm_dot: float) -> str:
    if shell_id < 0:
        return "unknown"
    target = SHELLS[shell_id]["target_alt"]
    if abs(alt - target) <= 20:
        return "operational"
    if alt < 350 and mm_dot > 0.0001:
        return "deorbiting"
    if alt < target:
        return "raising"
    return "drifting"


def main():
    print("Fetching Kuiper TLEs from CelesTrak...")
    resp = requests.get(CELESTRAK_URL, timeout=60)
    resp.raise_for_status()
    records = resp.json()
    print(f"  {len(records):,} satellites")

    now = datetime.now(timezone.utc)
    rows = []

    for r in records:
        name = r.get("OBJECT_NAME", "")
        if not name.startswith("KUIPER"):
            continue

        inc = r["INCLINATION"]
        ecc = r["ECCENTRICITY"]
        mm = r["MEAN_MOTION"]
        alt = altitude_from_mean_motion(mm, ecc)
        if alt < 0 or alt > 2000:
            continue

        shell_id = get_shell_id(inc)
        mm_dot = r["MEAN_MOTION_DOT"]
        status = classify_status(alt, shell_id, mm_dot)

        epoch_str = r["EPOCH"]
        if epoch_str.endswith("Z"):
            epoch_str = epoch_str[:-1] + "+00:00"
        epoch = datetime.fromisoformat(epoch_str)
        if epoch.tzinfo is None:
            epoch = epoch.replace(tzinfo=timezone.utc)

        intl = r.get("OBJECT_ID", "")
        launch_year = int(intl[:4]) if intl and intl[:4].isdigit() else 0

        rows.append({
            "norad_id": r["NORAD_CAT_ID"],
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
        })

    df = pd.DataFrame(rows)
    print(f"  {len(df):,} Kuiper satellites processed")

    df_latest = df.sort_values("epoch_utc").drop_duplicates("norad_id", keep="last")

    # Build today's per-shell daily snapshot
    today = pd.Timestamp(now.strftime("%Y-%m-%d"))
    daily_rows = []
    observed_shells = sorted(s for s in df_latest["shell_id"].unique() if s >= 0)
    for sid in observed_shells:
        shell = df_latest[df_latest["shell_id"] == sid]
        daily_rows.append({
            "date": today,
            "shell_id": int(sid),
            "shell_name": SHELL_NAMES.get(int(sid), "Unknown"),
            "total_count": len(shell),
            "operational_count": int((shell["status"] == "operational").sum()),
            "raising_count": int((shell["status"] == "raising").sum()),
            "deorbiting_count": int((shell["status"] == "deorbiting").sum()),
            "mean_altitude_km": round(float(shell["altitude_km"].mean()), 2),
        })
    df_today = pd.DataFrame(daily_rows)

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Kuiper Constellation Fleet Data",
        description=DESCRIPTION,
        tags=["space", "kuiper", "amazon", "satellites", "orbital-mechanics", "tle",
              "constellation", "open-data", "norad", "leo",
              "broadband", "tabular-data", "parquet"],
        source_url="https://celestrak.org/",
        task_categories=["time-series-forecasting", "tabular-classification"],
        update_schedule="Daily at 08:15 UTC via GitHub Actions",
        collection_url="https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994",
        banner={
            "url": "https://images-assets.nasa.gov/image/iss071e439624/iss071e439624~medium.jpg",
            "alt": "Orbital sunrise illuminating Earth's atmosphere, seen from the ISS",
            "credit": "NASA",
        },
        related_datasets=[
            "juliensimon/starlink-fleet-data",
            "juliensimon/constellation-census",
            "juliensimon/space-track-tle-history",
            "juliensimon/space-track-satcat",
            "juliensimon/space-launch-log",
        ],
    ) as p:
        # First-run safe: if no existing file, start from today's snapshot
        df_existing_daily = p.download_existing("daily_snapshots.parquet")
        if df_existing_daily is None or len(df_existing_daily) == 0:
            print("  No existing daily_snapshots.parquet -- initializing dataset")
            df_daily = df_today.copy()
        else:
            df_existing_daily["date"] = pd.to_datetime(df_existing_daily["date"])
            df_daily = p.append_by_date(df_existing_daily, df_today, date_col="date", min_existing=1)
        print(f"  daily_snapshots: {len(df_daily):,} total rows")

        write_parquet(df_daily, p.data_dir / "daily_snapshots.parquet")

        total = len(df_latest)
        active = int((df_latest["status"] == "operational").sum())
        raising = int((df_latest["status"] == "raising").sum())
        deorbiting = int((df_latest["status"] == "deorbiting").sum())
        print(f"  {active:,} operational, {total:,} total")

        date_range_start = df_daily["date"].min().strftime("%Y-%m-%d")
        date_range_end = df_daily["date"].max().strftime("%Y-%m-%d")

        quick_stats = f"""\
- **{total:,}** Kuiper satellites tracked
- **{active:,}** operational, **{raising:,}** raising, **{deorbiting:,}** deorbiting
- **{len(df_daily):,}** daily snapshot rows ({date_range_start} to {date_range_end})
- Companion to [juliensimon/starlink-fleet-data](https://huggingface.co/datasets/juliensimon/starlink-fleet-data) for head-to-head LEO broadband analysis"""

        usage = """\
```python
from datasets import load_dataset

kuiper = load_dataset("juliensimon/kuiper-fleet-data", split="train").to_pandas()
starlink = load_dataset("juliensimon/starlink-fleet-data", "daily_snapshots", split="train").to_pandas()

# Head-to-head operational growth
k = kuiper.groupby("date")["operational_count"].sum().rename("kuiper")
s = starlink.groupby("date")["operational_count"].sum().rename("starlink")
print(k.join(s, how="outer").tail(10))
```"""

        p.publish(
            df_daily,
            filename="daily_snapshots.parquet",
            min_rows=1,
            expected_columns=["date", "shell_id", "total_count", "operational_count"],
            critical_columns=["date", "shell_id", "total_count"],
            column_descriptions=COLUMN_DAILY_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=(
                f"Update Kuiper fleet: {total:,} satellites "
                f"({active:,} operational, {raising:,} raising)"
            ),
        )
    print("Done.")


if __name__ == "__main__":
    main()
