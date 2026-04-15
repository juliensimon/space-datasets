#!/usr/bin/env python3
"""Fetch latest Globalstar TLEs from CelesTrak, classify by generation, and upload to HF.

Globalstar operates a LEO satellite-messaging constellation (~1,414 km / 52 deg),
used by Apple to power iPhone emergency/satellite messaging. Fleet has three
generations: Gen1 (1998-2000, mostly retired), Gen1R (2007 replacements),
Gen2 (2010-2013, current operational), and Gen3 (2022+, Apple-funded replacements).

Relevant to the Bezos vs Musk broadband race: Amazon acquired Globalstar in April 2026
for roughly $11B, giving Kuiper/Amazon ownership of the spectrum and the Apple
satellite-messaging partnership.

Source: CelesTrak GP data (NORAD/18th Space Defense Squadron)
"""

import math
from datetime import datetime, timezone

import pandas as pd
import requests

from hf_dataset_utils import Pipeline
from hf_dataset_utils.upload import write_parquet

CELESTRAK_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP=globalstar&FORMAT=json"
HF_REPO = "juliensimon/globalstar-fleet-data"

MU = 398600.4418
R_EARTH = 6371.0

NOMINAL_ALT = 1414.0  # km, Globalstar operational altitude

COLUMN_DAILY_DESCRIPTIONS = {
    "date": "UTC date of the daily snapshot; one row per generation per date",
    "generation": "Hardware generation label: gen1 (1998-2000), gen1r (2007 replacements), gen2 (2010-2013), gen3 (2022+)",
    "total_count": "Total Globalstar objects in this generation tracked on this date",
    "operational_count": "Satellites within 100 km of the 1,414 km operational altitude",
    "graveyard_count": "Satellites boosted above operational altitude (>1,600 km), typically retired Gen1 hardware in graveyard orbit",
    "decaying_count": "Satellites below operational altitude (<1,300 km) with positive mean_motion_dot",
    "mean_altitude_km": "Mean altitude of satellites in this generation, kilometres above Earth's surface",
}

DESCRIPTION = """\
Daily health snapshots of the Globalstar satellite constellation, derived from CelesTrak \
GP (General Perturbations) data. Tracks satellite count, hardware generation, and lifecycle \
status for the full ~85-satellite fleet.

Globalstar operates a LEO satellite-messaging and voice constellation at roughly 1,414 km \
altitude and 52 degrees inclination. Unlike Starlink and Kuiper broadband mega-constellations, \
Globalstar provides low-bandwidth services to handsets and IoT devices. The company achieved \
mainstream visibility through its partnership with Apple, which uses Globalstar satellites to \
power iPhone emergency SOS, satellite messaging, and roadside assistance in areas outside \
cellular coverage.

In April 2026, Amazon announced an approximately $11 billion agreement to acquire Globalstar, \
positioning the constellation as a direct handset-connectivity complement to Amazon's Project \
Kuiper broadband network. This dataset tracks the fleet's operational state through that \
transition and is designed to be analyzed alongside juliensimon/kuiper-fleet-data and \
juliensimon/starlink-fleet-data for a head-to-head view of the Bezos-vs-Musk LEO race.

The fleet spans four hardware generations: Gen1 (1998-2000 launches, mostly retired to \
graveyard orbit), Gen1R (2007 replacement units), Gen2 (2010-2013, current operational core), \
and Gen3 (2022+, first units of the Apple-funded replacement program).\
"""


def altitude_from_mean_motion(n: float, ecc: float) -> float:
    if n <= 0:
        return -1.0
    n_rad = n * 2 * math.pi / 86400.0
    a = (MU / (n_rad ** 2)) ** (1.0 / 3.0)
    return a * (1 - ecc) - R_EARTH


def classify_generation(launch_year: int) -> str:
    if launch_year < 2005:
        return "gen1"
    if launch_year < 2010:
        return "gen1r"
    if launch_year < 2020:
        return "gen2"
    return "gen3"


def classify_status(alt: float, mm_dot: float) -> str:
    if alt > NOMINAL_ALT + 200:
        return "graveyard"
    if alt < NOMINAL_ALT - 100 and mm_dot > 0.0001:
        return "decaying"
    if abs(alt - NOMINAL_ALT) <= 100:
        return "operational"
    return "drifting"


def main():
    print("Fetching Globalstar TLEs from CelesTrak...")
    resp = requests.get(CELESTRAK_URL, timeout=60)
    resp.raise_for_status()
    records = resp.json()
    print(f"  {len(records):,} satellites")

    now = datetime.now(timezone.utc)
    rows = []

    for r in records:
        name = r.get("OBJECT_NAME", "")
        if not name.startswith("GLOBALSTAR"):
            continue

        inc = r["INCLINATION"]
        ecc = r["ECCENTRICITY"]
        mm = r["MEAN_MOTION"]
        alt = altitude_from_mean_motion(mm, ecc)
        if alt < 0 or alt > 3000:
            continue

        mm_dot = r["MEAN_MOTION_DOT"]
        intl = r.get("OBJECT_ID", "")
        launch_year = int(intl[:4]) if intl and intl[:4].isdigit() else 0
        generation = classify_generation(launch_year)
        status = classify_status(alt, mm_dot)

        epoch_str = r["EPOCH"]
        if epoch_str.endswith("Z"):
            epoch_str = epoch_str[:-1] + "+00:00"
        epoch = datetime.fromisoformat(epoch_str)
        if epoch.tzinfo is None:
            epoch = epoch.replace(tzinfo=timezone.utc)

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
            "generation": generation,
            "status": status,
        })

    df = pd.DataFrame(rows)
    print(f"  {len(df):,} Globalstar satellites processed")

    df_latest = df.sort_values("epoch_utc").drop_duplicates("norad_id", keep="last")

    today = pd.Timestamp(now.strftime("%Y-%m-%d"))
    daily_rows = []
    for gen in sorted(df_latest["generation"].unique()):
        g = df_latest[df_latest["generation"] == gen]
        daily_rows.append({
            "date": today,
            "generation": gen,
            "total_count": len(g),
            "operational_count": int((g["status"] == "operational").sum()),
            "graveyard_count": int((g["status"] == "graveyard").sum()),
            "decaying_count": int((g["status"] == "decaying").sum()),
            "mean_altitude_km": round(float(g["altitude_km"].mean()), 2),
        })
    df_today = pd.DataFrame(daily_rows)

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Globalstar Constellation Fleet Data",
        description=DESCRIPTION,
        tags=["space", "globalstar", "amazon", "apple", "satellites", "orbital-mechanics",
              "tle", "constellation", "open-data", "norad", "leo", "satellite-messaging",
              "iot", "tabular-data", "parquet"],
        source_url="https://celestrak.org/",
        task_categories=["time-series-forecasting", "tabular-classification"],
        update_schedule="Daily at 08:30 UTC via GitHub Actions",
        collection_url="https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994",
        banner={
            "url": "https://images-assets.nasa.gov/image/iss071e439624/iss071e439624~medium.jpg",
            "alt": "Orbital sunrise illuminating Earth's atmosphere, seen from the ISS",
            "credit": "NASA",
        },
        related_datasets=[
            "juliensimon/kuiper-fleet-data",
            "juliensimon/starlink-fleet-data",
            "juliensimon/constellation-census",
            "juliensimon/space-track-tle-history",
            "juliensimon/space-track-satcat",
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
        graveyard = int((df_latest["status"] == "graveyard").sum())
        decaying = int((df_latest["status"] == "decaying").sum())
        print(f"  {active:,} operational, {graveyard:,} graveyard, {total:,} total")

        date_range_start = df_daily["date"].min().strftime("%Y-%m-%d")
        date_range_end = df_daily["date"].max().strftime("%Y-%m-%d")

        quick_stats = f"""\
- **{total:,}** Globalstar satellites tracked across 4 generations
- **{active:,}** operational, **{graveyard:,}** in graveyard orbit, **{decaying:,}** decaying
- **{len(df_daily):,}** daily snapshot rows ({date_range_start} to {date_range_end})
- Acquired by Amazon in April 2026 as a complement to [juliensimon/kuiper-fleet-data](https://huggingface.co/datasets/juliensimon/kuiper-fleet-data)"""

        usage = """\
```python
from datasets import load_dataset

gs = load_dataset("juliensimon/globalstar-fleet-data", split="train").to_pandas()

# Fleet composition by generation
print(gs.groupby("generation")[["total_count", "operational_count"]].sum())

# Operational satellites over time
print(gs.groupby("date")["operational_count"].sum().tail(10))
```"""

        p.publish(
            df_daily,
            filename="daily_snapshots.parquet",
            min_rows=1,
            expected_columns=["date", "generation", "total_count", "operational_count"],
            critical_columns=["date", "generation", "total_count"],
            column_descriptions=COLUMN_DAILY_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=(
                f"Update Globalstar fleet: {total:,} satellites "
                f"({active:,} operational, {graveyard:,} graveyard)"
            ),
        )
    print("Done.")


if __name__ == "__main__":
    main()
