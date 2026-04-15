#!/usr/bin/env python3
"""Fetch Blue Origin launch history from The Space Devs Launch Library 2 API.

Complete launch manifest (past and upcoming) for Blue Origin rockets — primarily
New Shepard (suborbital tourism/research) and New Glenn (orbital heavy lift).
Relevant to the Bezos vs Musk race: companion dataset to juliensimon/spacex-launches
enables direct cadence comparison.

Source: The Space Devs Launch Library 2 (https://ll.thespacedevs.com)
"""

import time
from datetime import datetime, timezone

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

LL2_URL = "https://ll.thespacedevs.com/2.2.0/launch/"
AGENCY_ID = 141  # Blue Origin
HF_REPO = "juliensimon/blue-origin-launches"

COLUMN_DESCRIPTIONS = {
    "launch_id": "The Space Devs UUID for the launch",
    "name": "Launch display name (e.g. 'New Shepard | NS-20', 'New Glenn | Blue Moon MK1')",
    "mission_name": "Mission identifier assigned by Blue Origin (NS-NN for New Shepard, NG-NN for New Glenn)",
    "rocket": "Launch vehicle configuration name (New Shepard, New Glenn)",
    "net_utc": "No Earlier Than launch time (UTC). For completed launches this is the actual liftoff time; for upcoming it is the target",
    "window_start_utc": "Start of the launch window (UTC)",
    "window_end_utc": "End of the launch window (UTC)",
    "status": "Launch status: 'Launch Successful', 'Launch Failure', 'Partial Failure', 'Go for Launch', 'To Be Determined', 'To Be Confirmed', etc.",
    "status_abbrev": "Short status code: 'Success', 'Failure', 'Go', 'TBD', 'TBC', 'Hold'",
    "mission_type": "Mission category (Test Flight, Tourism, Science, Dedicated Rideshare, Lunar Transfer, etc.)",
    "mission_description": "Free-text description of the mission objective",
    "orbit": "Target orbit abbreviation (SO=Suborbital, LEO, GTO, TLI, etc.) where applicable",
    "pad_name": "Launch pad name",
    "pad_location": "Launch complex / site name",
    "pad_country": "Launch pad country code (USA, etc.)",
    "pad_latitude": "Launch pad geodetic latitude (deg)",
    "pad_longitude": "Launch pad geodetic longitude (deg)",
    "year": "Launch year (integer, derived from net_utc)",
}

DESCRIPTION = """\
Complete Blue Origin launch manifest — past and upcoming missions flown or planned \
by Jeff Bezos's space company, sourced from The Space Devs Launch Library 2 API.

Covers New Shepard (suborbital reusable vehicle used for research and crewed space tourism) \
and New Glenn (heavy-lift reusable orbital rocket that first flew in 2025). Each row captures \
mission identifier, vehicle, launch time, status, pad location, target orbit, and a free-text \
mission description. Includes the full history from the NS-1 development flight in April 2015 \
through the current manifest of confirmed upcoming New Glenn customer missions.

This dataset is designed as a direct counterpart to juliensimon/spacex-launches, enabling \
head-to-head comparison of Blue Origin and SpaceX launch cadence, success rates, and vehicle \
usage over time. It is particularly useful for tracking the accelerating New Glenn flight rate \
as Blue Origin ramps production, the company's growing share of NASA science missions such as \
the twin-satellite Mars launch in November 2025, and the competitive dynamics with SpaceX in \
the Artemis lunar lander program.\
"""


def fetch_all_launches():
    """Paginate through all Blue Origin launches from Launch Library 2."""
    all_results = []
    url = f"{LL2_URL}?lsp__id={AGENCY_ID}&limit=25&mode=detailed"
    while url:
        print(f"  Fetching: {url}")
        resp = requests.get(url, timeout=180)
        resp.raise_for_status()
        data = resp.json()
        all_results.extend(data["results"])
        url = data.get("next")
        if url:
            time.sleep(2)  # be polite to the API
    return all_results


def flatten_launch(r):
    rocket = (r.get("rocket") or {}).get("configuration") or {}
    mission = r.get("mission") or {}
    orbit = (mission.get("orbit") or {}) or {}
    pad = r.get("pad") or {}
    location = pad.get("location") or {}
    status = r.get("status") or {}

    def parse_ts(v):
        if not v:
            return None
        if v.endswith("Z"):
            v = v[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(v)
        except ValueError:
            return None

    net = parse_ts(r.get("net"))

    return {
        "launch_id": r.get("id"),
        "name": r.get("name"),
        "mission_name": mission.get("name"),
        "rocket": rocket.get("name"),
        "net_utc": net,
        "window_start_utc": parse_ts(r.get("window_start")),
        "window_end_utc": parse_ts(r.get("window_end")),
        "status": status.get("name"),
        "status_abbrev": status.get("abbrev"),
        "mission_type": mission.get("type"),
        "mission_description": mission.get("description"),
        "orbit": orbit.get("abbrev"),
        "pad_name": pad.get("name"),
        "pad_location": location.get("name"),
        "pad_country": pad.get("country_code"),
        "pad_latitude": float(pad["latitude"]) if pad.get("latitude") else None,
        "pad_longitude": float(pad["longitude"]) if pad.get("longitude") else None,
        "year": net.year if net else None,
    }


def main():
    print("Fetching Blue Origin launches from The Space Devs Launch Library 2...")
    launches = fetch_all_launches()
    print(f"  {len(launches):,} launches fetched")

    rows = [flatten_launch(r) for r in launches]
    df = pd.DataFrame(rows)
    df = df.sort_values("net_utc", ascending=True, na_position="last").reset_index(drop=True)

    now = datetime.now(timezone.utc)
    past = df[df["net_utc"].notna() & (df["net_utc"] < now)]
    success = past[past["status_abbrev"] == "Success"]
    upcoming = df[df["net_utc"].notna() & (df["net_utc"] >= now)]

    new_shepard = df[df["rocket"] == "New Shepard"]
    new_glenn = df[df["rocket"] == "New Glenn"]

    success_rate = (len(success) / len(past) * 100.0) if len(past) else 0.0

    print(f"  {len(past):,} past, {len(upcoming):,} upcoming")
    print(f"  {len(new_shepard):,} New Shepard, {len(new_glenn):,} New Glenn")
    print(f"  Success rate (past): {success_rate:.1f}%")

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Blue Origin Launch Log",
        description=DESCRIPTION,
        tags=["space", "blue-origin", "new-shepard", "new-glenn", "launches",
              "space-launch", "rockets", "bezos", "open-data", "suborbital",
              "orbital", "commercial-spaceflight", "tabular-data", "parquet"],
        source_url="https://ll.thespacedevs.com/2.2.0/launch/",
        task_categories=["tabular-classification", "time-series-forecasting"],
        update_schedule="Daily at 08:45 UTC via GitHub Actions",
        collection_url="https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994",
        banner={
            "url": "https://images-assets.nasa.gov/image/iss071e439624/iss071e439624~medium.jpg",
            "alt": "Orbital sunrise illuminating Earth's atmosphere, seen from the ISS",
            "credit": "NASA",
        },
        related_datasets=[
            "juliensimon/spacex-launches",
            "juliensimon/space-launch-log",
            "juliensimon/kuiper-fleet-data",
            "juliensimon/starlink-fleet-data",
            "juliensimon/launch-vehicles",
        ],
    ) as p:
        quick_stats = f"""\
- **{len(df):,}** Blue Origin launches ({len(past):,} past, {len(upcoming):,} upcoming)
- **{len(new_shepard):,}** New Shepard + **{len(new_glenn):,}** New Glenn flights tracked
- **{success_rate:.1f}%** success rate across completed missions
- Manifest spans **{int(df['year'].min())}** through **{int(df['year'].max())}**"""

        usage = """\
```python
from datasets import load_dataset

bo = load_dataset("juliensimon/blue-origin-launches", split="train").to_pandas()
sx = load_dataset("juliensimon/spacex-launches", split="train").to_pandas()

# Head-to-head annual cadence
bo_year = bo.groupby("year").size().rename("blue_origin")
# (SpaceX dataset has its own year column — adapt as needed)
print(bo_year.tail(10))

# New Glenn flight manifest
ng = bo[bo["rocket"] == "New Glenn"].sort_values("net_utc")
print(ng[["mission_name", "net_utc", "status", "orbit"]])
```"""

        p.publish(
            df,
            filename="blue_origin_launches.parquet",
            min_rows=40,
            expected_columns=["launch_id", "name", "rocket", "net_utc", "status"],
            critical_columns=["launch_id", "name", "rocket"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=(
                f"Update Blue Origin launches: {len(df):,} missions "
                f"({len(past):,} past, {len(upcoming):,} upcoming, "
                f"{success_rate:.0f}% success)"
            ),
        )
    print("Done.")


if __name__ == "__main__":
    main()
