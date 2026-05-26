#!/usr/bin/env python3
"""Fetch ULA (United Launch Alliance) launch history from The Space Devs Launch Library 2.

Complete manifest of United Launch Alliance flights — Atlas V, Delta IV, Delta II,
Delta IV Heavy, and Vulcan Centaur. ULA is the legacy EELV incumbent formed by the 2006
Boeing-Lockheed joint venture and remains the primary launch provider for Amazon's
Project Kuiper deployment (Atlas V + Vulcan), making it a key third party in the
Bezos-vs-Musk race.

Source: The Space Devs Launch Library 2 (https://ll.thespacedevs.com)
"""

import time
from datetime import datetime, timezone

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

LL2_URL = "https://ll.thespacedevs.com/2.2.0/launch/"
AGENCY_ID = 124  # United Launch Alliance
HF_REPO = "juliensimon/ula-launches"

COLUMN_DESCRIPTIONS = {
    "launch_id": "The Space Devs UUID for the launch",
    "name": "Launch display name (e.g. 'Atlas V 551 | Juno', 'Vulcan VC2S | USSF-106')",
    "mission_name": "Mission identifier or customer designation",
    "rocket": "Launch vehicle configuration name (Atlas V, Delta IV, Delta IV Heavy, Delta II, Vulcan Centaur)",
    "net_utc": "No Earlier Than launch time (UTC). For completed launches this is the actual liftoff time; for upcoming it is the target",
    "window_start_utc": "Start of the launch window (UTC)",
    "window_end_utc": "End of the launch window (UTC)",
    "status": "Launch status: 'Launch Successful', 'Launch Failure', 'Partial Failure', 'Go for Launch', 'To Be Determined', 'To Be Confirmed', etc.",
    "status_abbrev": "Short status code: 'Success', 'Failure', 'Go', 'TBD', 'TBC', 'Hold'",
    "mission_type": "Mission category (Communications, Earth Science, Navigation, Dedicated Rideshare, Planetary Science, etc.)",
    "mission_description": "Free-text description of the mission objective",
    "orbit": "Target orbit abbreviation (LEO, GTO, GEO, TLI, HCO, etc.) where applicable",
    "pad_name": "Launch pad name",
    "pad_location": "Launch complex / site name",
    "pad_country": "Launch pad country code (USA, etc.)",
    "pad_latitude": "Launch pad geodetic latitude (deg)",
    "pad_longitude": "Launch pad geodetic longitude (deg)",
    "year": "Launch year (integer, derived from net_utc)",
}

DESCRIPTION = """\
Complete United Launch Alliance (ULA) launch manifest — past and upcoming flights of \
Atlas V, Delta II, Delta IV, Delta IV Heavy, and Vulcan Centaur — sourced from The Space \
Devs Launch Library 2 API.

ULA is the Boeing-Lockheed Martin joint venture formed in 2006 to consolidate US national \
security space launches under a single EELV (Evolved Expendable Launch Vehicle) provider. \
For nearly a decade ULA enjoyed a monopoly on high-value national security payloads before \
SpaceX's Falcon 9 broke into the market. ULA retired its Delta family in favor of Vulcan \
Centaur, which flew its first flight in 2024 and is now ramping to take over both national \
security and commercial missions.

In the context of the Bezos-vs-Musk launch race, ULA is the decisive third party: Amazon \
has booked 38 Vulcan Centaur flights and 9 Atlas V flights to deploy its Project Kuiper \
broadband constellation, meaning ULA — not Blue Origin — is doing the bulk of the early \
Kuiper lift. This dataset enables direct cadence comparison with juliensimon/spacex-launches \
and juliensimon/blue-origin-launches, and is essential for understanding how Amazon is \
actually closing the gap with Starlink in orbit.\
"""


def fetch_all_launches():
    """Paginate through all ULA launches from Launch Library 2.

    LL2 mode=detailed with limit=100 times out; limit=25 with timeout=180 is reliable.
    """
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
            time.sleep(2)
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
    print("Fetching ULA launches from The Space Devs Launch Library 2...")
    launches = fetch_all_launches()
    print(f"  {len(launches):,} launches fetched")

    rows = [flatten_launch(r) for r in launches]
    df = pd.DataFrame(rows)
    df = df.sort_values("net_utc", ascending=True, na_position="last").reset_index(drop=True)

    now = datetime.now(timezone.utc)
    past = df[df["net_utc"].notna() & (df["net_utc"] < now)]
    success = past[past["status_abbrev"] == "Success"]
    upcoming = df[df["net_utc"].notna() & (df["net_utc"] >= now)]

    vehicle_counts = df["rocket"].value_counts().to_dict()
    success_rate = (len(success) / len(past) * 100.0) if len(past) else 0.0

    print(f"  {len(past):,} past, {len(upcoming):,} upcoming")
    print(f"  Vehicles: {vehicle_counts}")
    print(f"  Success rate (past): {success_rate:.1f}%")

    with Pipeline(
        repo=HF_REPO,
        pretty_name="ULA Launch Log",
        description=DESCRIPTION,
        tags=["space", "ula", "united-launch-alliance", "atlas-v", "vulcan-centaur",
              "delta-iv", "launches", "space-launch", "rockets", "eelv", "open-data",
              "commercial-spaceflight", "tabular-data", "parquet"],
        source_url="https://ll.thespacedevs.com/2.2.0/launch/",
        license="other",
        license_name="the-space-devs-terms",
        license_link="https://thespacedevs.com/llapi",
        task_categories=["tabular-classification", "time-series-forecasting"],
        update_schedule="Daily at 09:30 UTC via GitHub Actions",
        collection_url="https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994",
        banner={
            "url": "https://images-assets.nasa.gov/image/iss071e439624/iss071e439624~medium.jpg",
            "alt": "Orbital sunrise illuminating Earth's atmosphere, seen from the ISS",
            "credit": "NASA",
        },
        related_datasets=[
            "juliensimon/spacex-launches",
            "juliensimon/blue-origin-launches",
            "juliensimon/space-launch-log",
            "juliensimon/kuiper-fleet-data",
            "juliensimon/launch-vehicles",
        ],
    ) as p:
        top_vehicles = ", ".join(f"{v}: {n}" for v, n in sorted(vehicle_counts.items(), key=lambda x: -x[1])[:4] if v)
        quick_stats = f"""\
- **{len(df):,}** ULA launches ({len(past):,} past, {len(upcoming):,} upcoming)
- **{success_rate:.1f}%** success rate across completed missions
- Vehicles tracked: {top_vehicles}
- Primary launch provider for [juliensimon/kuiper-fleet-data](https://huggingface.co/datasets/juliensimon/kuiper-fleet-data) deployment"""

        usage = """\
```python
from datasets import load_dataset

ula = load_dataset("juliensimon/ula-launches", split="train").to_pandas()
sx = load_dataset("juliensimon/spacex-launches", split="train").to_pandas()

# Head-to-head annual cadence (ULA vs SpaceX)
ula_year = ula.groupby("year").size().rename("ula")
print(ula_year.tail(10))

# Kuiper deployment flights only
kuiper = ula[ula["mission_description"].str.contains("Kuiper", na=False, case=False)]
print(kuiper[["net_utc", "rocket", "mission_name", "status"]].head(20))
```"""

        p.publish(
            df,
            filename="ula_launches.parquet",
            min_rows=150,
            expected_columns=["launch_id", "name", "rocket", "net_utc", "status"],
            critical_columns=["launch_id", "name", "rocket"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=(
                f"Update ULA launches: {len(df):,} missions "
                f"({len(past):,} past, {len(upcoming):,} upcoming, "
                f"{success_rate:.0f}% success)"
            ),
        )
    print("Done.")


if __name__ == "__main__":
    main()
