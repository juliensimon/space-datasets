#!/usr/bin/env python3
"""Fetch latest AST SpaceMobile TLEs from CelesTrak and upload to HF.

AST SpaceMobile builds the BlueBird direct-to-cell satellite constellation, designed to
connect unmodified smartphones directly to LEO satellites. BlueWalker 3 was the 2022
prototype; the first five BlueBird satellites (SpaceMobile-001..005) launched in 2024
on a Falcon 9, and SpaceMobile-006 followed in 2025. AST is notable in the Bezos-vs-Musk
race because Blue Origin's April 2026 New Glenn mission is launching AST SpaceMobile
BlueBird satellites — making AST a customer of both SpaceX (Falcon 9) and Blue Origin.

Source: CelesTrak GP data (NORAD/18th Space Defense Squadron, GROUP=ast)
"""

import math
from datetime import datetime, timezone

import pandas as pd
import requests

from hf_dataset_utils import Pipeline
from hf_dataset_utils.upload import write_parquet

CELESTRAK_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP=ast&FORMAT=json"
HF_REPO = "juliensimon/ast-spacemobile-fleet-data"

MU = 398600.4418
R_EARTH = 6371.0

# BlueBird target operational altitude ~700 km (FCC filing); BlueWalker 3 at ~500 km
NOMINAL_ALT = 700.0

COLUMN_DAILY_DESCRIPTIONS = {
    "date": "UTC date of the daily snapshot; one row per date",
    "total_count": "Total AST SpaceMobile objects tracked on this date (BlueWalker + BlueBird); expected range 1-250 as the constellation grows toward its ~243-satellite FCC-authorized Block-1/2 deployment",
    "bluewalker_count": "Number of BlueWalker prototype satellites on orbit (always 0 or 1; only BlueWalker-3 was launched, in Sept 2022)",
    "bluebird_count": "Number of production BlueBird satellites (SpaceMobile-001..00N); expected range 0-243 per FCC Block-1+Block-2 authorization, first five launched Sept 2024",
    "operational_count": "Satellites within 100 km of the 700 km target operational altitude; expected to approach bluebird_count once each satellite finishes LEOP and orbit raising",
    "mean_altitude_km": "Mean altitude of the fleet above Earth's surface (km); typical range 500-720 — mix of parked/transfer (500 km) and operational (700 km) altitudes",
    "mean_inclination_deg": "Mean orbital inclination of the fleet (degrees); nominal 53° inclination per FCC filing",
}

DESCRIPTION = """\
Daily health snapshots of the AST SpaceMobile BlueBird direct-to-cell satellite \
constellation, derived from CelesTrak GP (General Perturbations) data. Tracks the \
BlueWalker 3 prototype and all production BlueBird satellites as the constellation is \
built out.

AST SpaceMobile is developing a unique LEO constellation designed to provide broadband \
connectivity directly to ordinary unmodified smartphones, without special satellite-phone \
hardware. The BlueBird satellites use unusually large phased-array antennas (up to 700 m2) \
to close the link budget with handset-sized antennas on the ground. The BlueWalker 3 \
prototype launched in 2022, the first five production BlueBirds flew on a Falcon 9 in \
September 2024, and SpaceMobile-006 followed in 2025.

AST is notable in the Bezos-vs-Musk launch race because the company is a customer of \
both providers: the initial BlueBird batch flew on SpaceX Falcon 9, and Blue Origin's \
April 2026 New Glenn mission is launching additional BlueBird satellites. This dataset \
pairs naturally with juliensimon/blue-origin-launches and juliensimon/spacex-launches to \
track how AST's deployment splits between the two launch providers, and with \
juliensimon/starlink-fleet-data to compare direct-to-cell approaches (Starlink DTC vs \
BlueBird) as that market develops.\
"""


def altitude_from_mean_motion(n: float, ecc: float) -> float:
    if n <= 0:
        return -1.0
    n_rad = n * 2 * math.pi / 86400.0
    a = (MU / (n_rad ** 2)) ** (1.0 / 3.0)
    return a * (1 - ecc) - R_EARTH


def main():
    print("Fetching AST SpaceMobile TLEs from CelesTrak...")
    resp = requests.get(CELESTRAK_URL, timeout=60)
    resp.raise_for_status()
    records = resp.json()
    print(f"  {len(records):,} satellites")

    now = datetime.now(timezone.utc)
    rows = []

    for r in records:
        name = r.get("OBJECT_NAME", "")

        inc = r["INCLINATION"]
        ecc = r["ECCENTRICITY"]
        mm = r["MEAN_MOTION"]
        alt = altitude_from_mean_motion(mm, ecc)
        if alt < 0 or alt > 2000:
            continue

        is_bluewalker = name.startswith("BLUEWALKER")
        is_bluebird = name.startswith("SPACEMOBILE")
        family = "bluewalker" if is_bluewalker else ("bluebird" if is_bluebird else "other")

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
            "family": family,
            "epoch_utc": epoch,
            "inclination": round(inc, 4),
            "raan": round(r["RA_OF_ASC_NODE"], 4),
            "eccentricity": ecc,
            "mean_motion": mm,
            "altitude_km": round(alt, 2),
            "launch_year": launch_year,
        })

    df = pd.DataFrame(rows)
    print(f"  {len(df):,} AST SpaceMobile satellites processed")

    df_latest = df.sort_values("epoch_utc").drop_duplicates("norad_id", keep="last")

    today = pd.Timestamp(now.strftime("%Y-%m-%d"))
    bluewalker_n = int((df_latest["family"] == "bluewalker").sum())
    bluebird_n = int((df_latest["family"] == "bluebird").sum())
    operational_n = int((df_latest["altitude_km"].sub(NOMINAL_ALT).abs() <= 100).sum())

    df_today = pd.DataFrame([{
        "date": today,
        "total_count": len(df_latest),
        "bluewalker_count": bluewalker_n,
        "bluebird_count": bluebird_n,
        "operational_count": operational_n,
        "mean_altitude_km": round(float(df_latest["altitude_km"].mean()), 2),
        "mean_inclination_deg": round(float(df_latest["inclination"].mean()), 4),
    }])

    with Pipeline(
        repo=HF_REPO,
        pretty_name="AST SpaceMobile BlueBird Fleet Data",
        description=DESCRIPTION,
        tags=["space", "ast-spacemobile", "bluebird", "bluewalker", "satellites",
              "orbital-mechanics", "tle", "constellation", "open-data", "norad",
              "leo", "direct-to-cell", "tabular-data", "parquet"],
        source_url="https://celestrak.org/",
        task_categories=["time-series-forecasting", "tabular-classification"],
        update_schedule="Daily at 09:15 UTC via GitHub Actions",
        collection_url="https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994",
        banner={
            "url": "https://images-assets.nasa.gov/image/iss071e439624/iss071e439624~medium.jpg",
            "alt": "Orbital sunrise illuminating Earth's atmosphere, seen from the ISS",
            "credit": "NASA",
        },
        related_datasets=[
            "juliensimon/blue-origin-launches",
            "juliensimon/spacex-launches",
            "juliensimon/starlink-fleet-data",
            "juliensimon/kuiper-fleet-data",
            "juliensimon/constellation-census",
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

        print(f"  {len(df_latest):,} total ({bluewalker_n} BlueWalker + {bluebird_n} BlueBird)")
        date_range_start = df_daily["date"].min().strftime("%Y-%m-%d")
        date_range_end = df_daily["date"].max().strftime("%Y-%m-%d")

        quick_stats = f"""\
- **{len(df_latest):,}** AST SpaceMobile satellites ({bluewalker_n} BlueWalker + {bluebird_n} BlueBird)
- **{operational_n:,}** near 700 km target operational altitude
- **{len(df_daily):,}** daily snapshot rows ({date_range_start} to {date_range_end})
- Customer of both SpaceX and Blue Origin — pair with [blue-origin-launches](https://huggingface.co/datasets/juliensimon/blue-origin-launches) and [spacex-launches](https://huggingface.co/datasets/juliensimon/spacex-launches)"""

        usage = """\
```python
from datasets import load_dataset

ast = load_dataset("juliensimon/ast-spacemobile-fleet-data", split="train").to_pandas()

# Fleet growth over time
print(ast[["date", "bluewalker_count", "bluebird_count"]].tail(10))
```"""

        p.publish(
            df_daily,
            filename="daily_snapshots.parquet",
            min_rows=1,
            expected_columns=["date", "total_count", "bluebird_count"],
            critical_columns=["date", "total_count"],
            column_descriptions=COLUMN_DAILY_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=(
                f"Update AST SpaceMobile fleet: {len(df_latest):,} satellites "
                f"({bluewalker_n} BlueWalker + {bluebird_n} BlueBird)"
            ),
        )
    print("Done.")


if __name__ == "__main__":
    main()
