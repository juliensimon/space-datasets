#!/usr/bin/env python3
"""Fetch latest OneWeb (Eutelsat) TLEs from CelesTrak, classify, and upload to HF.

OneWeb operates a LEO broadband constellation at roughly 1,200 km / 87.9 deg near-polar
inclination. Merged with Eutelsat in 2023. This dataset is the third major LEO broadband
player alongside Starlink and Kuiper — critical for honest head-to-head comparisons of
the LEO broadband market beyond the Bezos-vs-Musk duopoly narrative.

Source: CelesTrak GP data (NORAD/18th Space Defense Squadron)
"""

import math
from datetime import datetime, timezone

import pandas as pd
import requests

from hf_dataset_utils import Pipeline
from hf_dataset_utils.upload import write_parquet

CELESTRAK_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP=oneweb&FORMAT=json"
HF_REPO = "juliensimon/oneweb-fleet-data"

MU = 398600.4418
R_EARTH = 6371.0

NOMINAL_ALT = 1200.0  # km, OneWeb Gen1 operational altitude

COLUMN_DAILY_DESCRIPTIONS = {
    "date": "UTC date of the daily snapshot; one row per inclination plane per date",
    "inclination_plane": "Rounded inclination in degrees; OneWeb Gen1 uses ~87.9 deg polar planes",
    "total_count": "Total OneWeb objects in this inclination plane tracked on this date",
    "operational_count": "Satellites within 50 km of the 1,200 km operational altitude",
    "raising_count": "Satellites below operational altitude climbing toward target",
    "deorbiting_count": "Satellites below 600 km with positive mean_motion_dot (controlled deorbit)",
    "mean_altitude_km": "Mean altitude in this inclination plane, kilometres above Earth's surface",
}

DESCRIPTION = """\
Daily health snapshots of the OneWeb (Eutelsat OneWeb) satellite constellation, derived \
from CelesTrak GP (General Perturbations) data. Tracks satellite count and lifecycle \
status across OneWeb's near-polar orbital planes.

OneWeb operates a ~650-satellite first-generation LEO broadband constellation at roughly \
1,200 km altitude and 87.9 degrees inclination. Unlike Starlink's lower 550 km shells, \
OneWeb's higher orbit yields larger per-satellite footprints and longer orbital lifetimes, \
at the cost of higher latency and fewer satellites needed for global coverage. The company \
merged with Eutelsat in 2023 to become Eutelsat OneWeb, creating a combined GEO plus LEO \
operator that targets enterprise and government customers rather than direct-to-consumer \
broadband.

This dataset is designed as the third point of comparison alongside juliensimon/starlink-fleet-data \
and juliensimon/kuiper-fleet-data. Without OneWeb in the picture, a head-to-head chart of the \
LEO broadband race is misleading — OneWeb completed its Gen1 deployment before Kuiper started \
and remains the second-largest operational LEO broadband constellation after Starlink. Status is \
inferred from orbital mechanics alone, bucketed by inclination plane.\
"""


def altitude_from_mean_motion(n: float, ecc: float) -> float:
    if n <= 0:
        return -1.0
    n_rad = n * 2 * math.pi / 86400.0
    a = (MU / (n_rad ** 2)) ** (1.0 / 3.0)
    return a * (1 - ecc) - R_EARTH


def classify_status(alt: float, mm_dot: float) -> str:
    if alt < 600 and mm_dot > 0.0001:
        return "deorbiting"
    if abs(alt - NOMINAL_ALT) <= 50:
        return "operational"
    if alt < NOMINAL_ALT - 50:
        return "raising"
    return "drifting"


def main():
    print("Fetching OneWeb TLEs from CelesTrak...")
    resp = requests.get(CELESTRAK_URL, timeout=60)
    resp.raise_for_status()
    records = resp.json()
    print(f"  {len(records):,} satellites")

    now = datetime.now(timezone.utc)
    rows = []

    for r in records:
        name = r.get("OBJECT_NAME", "")
        if not name.startswith("ONEWEB"):
            continue

        inc = r["INCLINATION"]
        ecc = r["ECCENTRICITY"]
        mm = r["MEAN_MOTION"]
        alt = altitude_from_mean_motion(mm, ecc)
        if alt < 0 or alt > 2000:
            continue

        mm_dot = r["MEAN_MOTION_DOT"]
        status = classify_status(alt, mm_dot)

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
            "inclination_plane": round(inc, 0),
            "raan": round(r["RA_OF_ASC_NODE"], 4),
            "eccentricity": ecc,
            "mean_motion": mm,
            "mean_motion_dot": mm_dot,
            "altitude_km": round(alt, 2),
            "launch_year": launch_year,
            "status": status,
        })

    df = pd.DataFrame(rows)
    print(f"  {len(df):,} OneWeb satellites processed")

    df_latest = df.sort_values("epoch_utc").drop_duplicates("norad_id", keep="last")

    today = pd.Timestamp(now.strftime("%Y-%m-%d"))
    daily_rows = []
    for plane in sorted(df_latest["inclination_plane"].unique()):
        g = df_latest[df_latest["inclination_plane"] == plane]
        daily_rows.append({
            "date": today,
            "inclination_plane": float(plane),
            "total_count": len(g),
            "operational_count": int((g["status"] == "operational").sum()),
            "raising_count": int((g["status"] == "raising").sum()),
            "deorbiting_count": int((g["status"] == "deorbiting").sum()),
            "mean_altitude_km": round(float(g["altitude_km"].mean()), 2),
        })
    df_today = pd.DataFrame(daily_rows)

    with Pipeline(
        repo=HF_REPO,
        pretty_name="OneWeb Constellation Fleet Data",
        description=DESCRIPTION,
        tags=["space", "oneweb", "eutelsat", "satellites", "orbital-mechanics", "tle",
              "constellation", "open-data", "norad", "leo", "broadband",
              "tabular-data", "parquet"],
        source_url="https://celestrak.org/",
        license="other",
        license_name="celestrak-usage-policy",
        license_link="https://celestrak.org/usage-policy.php",
        task_categories=["time-series-forecasting", "tabular-classification"],
        update_schedule="Daily at 09:00 UTC via GitHub Actions",
        collection_url="https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994",
        banner={
            "url": "https://images-assets.nasa.gov/image/iss071e439624/iss071e439624~medium.jpg",
            "alt": "Orbital sunrise illuminating Earth's atmosphere, seen from the ISS",
            "credit": "NASA",
        },
        related_datasets=[
            "juliensimon/starlink-fleet-data",
            "juliensimon/kuiper-fleet-data",
            "juliensimon/globalstar-fleet-data",
            "juliensimon/constellation-census",
            "juliensimon/space-track-tle-history",
        ],
    ) as p:
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
- **{total:,}** OneWeb satellites tracked across {len(daily_rows)} inclination planes
- **{active:,}** operational, **{raising:,}** raising, **{deorbiting:,}** deorbiting
- **{len(df_daily):,}** daily snapshot rows ({date_range_start} to {date_range_end})
- Third point of comparison for [juliensimon/starlink-fleet-data](https://huggingface.co/datasets/juliensimon/starlink-fleet-data) vs [juliensimon/kuiper-fleet-data](https://huggingface.co/datasets/juliensimon/kuiper-fleet-data)"""

        usage = """\
```python
from datasets import load_dataset

ow = load_dataset("juliensimon/oneweb-fleet-data", split="train").to_pandas()
sx = load_dataset("juliensimon/starlink-fleet-data", "daily_snapshots", split="train").to_pandas()
ku = load_dataset("juliensimon/kuiper-fleet-data", split="train").to_pandas()

# LEO broadband race: operational satellites over time
ow_ops = ow.groupby("date")["operational_count"].sum().rename("oneweb")
sx_ops = sx.groupby("date")["operational_count"].sum().rename("starlink")
ku_ops = ku.groupby("date")["operational_count"].sum().rename("kuiper")
print(ow_ops.to_frame().join([sx_ops, ku_ops], how="outer").tail(10))
```"""

        p.publish(
            df_daily,
            filename="daily_snapshots.parquet",
            min_rows=1,
            expected_columns=["date", "inclination_plane", "total_count", "operational_count"],
            critical_columns=["date", "inclination_plane", "total_count"],
            column_descriptions=COLUMN_DAILY_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=(
                f"Update OneWeb fleet: {total:,} satellites "
                f"({active:,} operational, {raising:,} raising)"
            ),
        )
    print("Done.")


if __name__ == "__main__":
    main()
