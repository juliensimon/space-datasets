#!/usr/bin/env python3
"""Fetch Rocket Lab launch history from The Space Devs Launch Library 2 API.

Complete launch manifest (past and upcoming) for Rocket Lab — primarily Electron
(operational small-lift rocket since 2017, ~70+ flights to LEO and SSO) with the
forthcoming Neutron medium-lift vehicle. Companion to juliensimon/spacex-launches,
juliensimon/blue-origin-launches, and juliensimon/ula-launches for cross-provider
cadence and success-rate analysis.

Source: The Space Devs Launch Library 2 (https://ll.thespacedevs.com), agency id 147.
"""

import sys
import time
from datetime import datetime, timezone

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

LL2_URL = "https://ll.thespacedevs.com/2.2.0/launch/"
AGENCY_ID = 147  # Rocket Lab
HF_REPO = "juliensimon/rocket-lab-launches"

COLUMN_DESCRIPTIONS = {
    "launch_id": "The Space Devs UUID for the launch",
    "name": "Launch display name (e.g. 'Electron | Capstone', 'Neutron | Escapade')",
    "mission_name": "Mission identifier or customer-facing name (e.g. 'It\'s a Test', 'Still Testing', 'There And Back Again', 'CAPSTONE')",
    "rocket": "Launch vehicle configuration name (Electron, Neutron, HASTE for hypersonic test variant)",
    "net_utc": "No Earlier Than launch time (UTC). For completed launches this is the actual liftoff time; for upcoming it is the target",
    "window_start_utc": "Start of the launch window (UTC)",
    "window_end_utc": "End of the launch window (UTC)",
    "status": "Launch status: 'Launch Successful', 'Launch Failure', 'Partial Failure', 'Go for Launch', 'To Be Determined', 'To Be Confirmed', etc.",
    "status_abbrev": "Short status code: 'Success', 'Failure', 'Go', 'TBD', 'TBC', 'Hold'",
    "mission_type": "Mission category (Communications, Earth Science, Astrophysics, Technology, Government/Top Secret, Lunar, Resupply, etc.)",
    "mission_description": "Free-text description of the mission objective and customer payload",
    "orbit": "Target orbit abbreviation (LEO=Low Earth Orbit, SSO=Sun-Synchronous Orbit, GTO=Geostationary Transfer Orbit, TLI=Trans-Lunar Injection, MEO, etc.) where applicable",
    "pad_name": "Launch pad name (e.g. 'Rocket Lab Launch Complex 1B', 'LC-2')",
    "pad_location": "Launch complex / site name (e.g. 'Mahia Peninsula, New Zealand', 'Mid-Atlantic Regional Spaceport, Wallops Island, VA')",
    "pad_country": "Launch pad country code (NZL for Mahia, USA for Wallops)",
    "pad_latitude": "Launch pad geodetic latitude (deg)",
    "pad_longitude": "Launch pad geodetic longitude (deg)",
    "year": "Launch year (integer, derived from net_utc)",
}

DESCRIPTION = """\
Complete Rocket Lab launch manifest — past and upcoming missions flown or planned by Peter Beck's \
small-launch company, sourced from The Space Devs Launch Library 2 API.

Covers Electron (small-lift two-stage rocket using Rutherford 3D-printed engines, operational since \
2017 from Mahia Peninsula in New Zealand and from LC-2 at Wallops Island, Virginia) and the \
forthcoming Neutron medium-lift partially reusable rocket. Each row captures mission identifier, \
vehicle, launch time, status, pad location, target orbit, and a free-text mission description. \
Includes the full Electron history from the May 2017 'It\'s a Test' debut through the current \
manifest of confirmed upcoming Electron and Neutron customer missions.

This dataset is designed as a counterpart to juliensimon/spacex-launches, juliensimon/blue-origin-launches, \
and juliensimon/ula-launches, enabling head-to-head comparison of launch cadence, success rates, and \
vehicle utilization across the major commercial-launch providers. Particularly useful for tracking \
the small-launch market segment that Electron pioneered, the rapid expansion of NASA Earth-science \
and NRO smallsat constellation contracts, and the upcoming Neutron entry into the medium-lift market \
positioning Rocket Lab against SpaceX Falcon 9.\
"""


def _safe_float(v):
    try:
        return float(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None


def fetch_all_launches():
    """Paginate through all Rocket Lab launches from Launch Library 2."""
    all_results = []
    url = f"{LL2_URL}?lsp__id={AGENCY_ID}&limit=25&mode=detailed"
    while url:
        print(f"  Fetching: {url}")
        for attempt in range(4):
            try:
                resp = requests.get(url, timeout=180)
                resp.raise_for_status()
                break
            except Exception as e:
                if attempt == 3:
                    raise
                wait = 15 * (2 ** attempt)
                print(f"    HTTP error (attempt {attempt + 1}/4): {e}; retry in {wait}s")
                time.sleep(wait)
        data = resp.json()
        all_results.extend(data.get("results", []))
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
        "pad_latitude": _safe_float(pad.get("latitude")),
        "pad_longitude": _safe_float(pad.get("longitude")),
        "year": net.year if net else None,
    }


def main():
    print("Fetching Rocket Lab launches from The Space Devs Launch Library 2...")
    launches = fetch_all_launches()
    print(f"  {len(launches):,} launches fetched")
    if not launches:
        print("::error::LL2 returned 0 results for Rocket Lab (API may be down)")
        sys.exit(1)

    rows = [flatten_launch(r) for r in launches]
    df = pd.DataFrame(rows)
    df = df.sort_values("net_utc", ascending=True, na_position="last").reset_index(drop=True)

    now = datetime.now(timezone.utc)
    past = df[df["net_utc"].notna() & (df["net_utc"] < now)]
    success = past[past["status_abbrev"] == "Success"]
    upcoming = df[df["net_utc"].notna() & (df["net_utc"] >= now)]

    electron = df[df["rocket"] == "Electron"]
    neutron = df[df["rocket"] == "Neutron"]
    haste = df[df["rocket"] == "HASTE"]

    success_rate = (len(success) / len(past) * 100.0) if len(past) else 0.0

    print(f"  {len(past):,} past, {len(upcoming):,} upcoming")
    print(f"  {len(electron):,} Electron, {len(neutron):,} Neutron, {len(haste):,} HASTE")
    print(f"  Success rate (past): {success_rate:.1f}%")

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Rocket Lab Launch Log",
        description=DESCRIPTION,
        tags=["space", "rocket-lab", "electron", "neutron", "launches",
              "space-launch", "rockets", "smallsat", "open-data",
              "commercial-spaceflight", "tabular-data", "parquet"],
        source_url="https://ll.thespacedevs.com/2.2.0/launch/",
        task_categories=["tabular-classification", "time-series-forecasting"],
        update_schedule="Daily at 09:15 UTC via GitHub Actions",
        collection_url="https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994",
        banner={
            "url": "https://images-assets.nasa.gov/image/iss071e439624/iss071e439624~medium.jpg",
            "alt": "Orbital sunrise illuminating Earth's atmosphere, seen from the ISS",
            "credit": "NASA",
        },
        related_datasets=[
            "juliensimon/spacex-launches",
            "juliensimon/blue-origin-launches",
            "juliensimon/ula-launches",
            "juliensimon/space-launch-log",
            "juliensimon/launch-vehicles",
        ],
    ) as p:
        quick_stats = f"""\
- **{len(df):,}** Rocket Lab launches ({len(past):,} past, {len(upcoming):,} upcoming)
- **{len(electron):,}** Electron + **{len(neutron):,}** Neutron + **{len(haste):,}** HASTE flights tracked
- **{success_rate:.1f}%** success rate across completed missions
- Manifest spans **{int(df['year'].dropna().min())}** through **{int(df['year'].dropna().max())}**"""

        usage = """\
```python
from datasets import load_dataset

rl = load_dataset("juliensimon/rocket-lab-launches", split="train").to_pandas()
sx = load_dataset("juliensimon/spacex-launches", split="train").to_pandas()

# Annual cadence by rocket family
print(rl.groupby(["year", "rocket"]).size().unstack(fill_value=0).tail(10))

# Electron success rate by year
import numpy as np
electron = rl[rl["rocket"] == "Electron"]
electron_done = electron[electron["status_abbrev"].isin(["Success", "Failure", "Partial Failure"])]
yearly = electron_done.groupby("year").apply(
    lambda g: 100 * (g["status_abbrev"] == "Success").mean()
).rename("electron_success_pct")
print(yearly)

# Confirmed upcoming Neutron manifest
neutron = rl[rl["rocket"] == "Neutron"].sort_values("net_utc")
print(neutron[["mission_name", "net_utc", "status", "orbit", "pad_location"]])
```"""

        _REQUIRED = {"launch_id", "name", "rocket", "net_utc", "status"}
        all_null = [c for c in df.columns if df[c].isna().all() and c not in _REQUIRED]
        if all_null:
            print(f"  Dropping fully-null optional columns: {all_null}")
            df = df.drop(columns=all_null)
        p.publish(
            df,
            filename="rocket_lab_launches.parquet",
            min_rows=40,
            expected_columns=["launch_id", "name", "rocket", "net_utc", "status"],
            critical_columns=["launch_id", "name", "rocket"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=(
                f"Update Rocket Lab launches: {len(df):,} missions "
                f"({len(past):,} past, {len(upcoming):,} upcoming, "
                f"{success_rate:.0f}% success)"
            ),
        )
    print("Done.")


if __name__ == "__main__":
    main()
