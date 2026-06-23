#!/usr/bin/env python3
"""Track the live positions of active deep-space missions via JPL Horizons.

Each day this queries NASA/JPL's Horizons system for the geocentric and
heliocentric geometry of a set of active interplanetary spacecraft, appending one
row per mission per day. Over time this builds a trajectory log: how far each probe
is from the Sun and Earth, where it appears on the sky, and how long its signal
takes to reach us. Append-by-date: idempotent per UTC day.
"""

import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

HF_REPO = "juliensimon/deep-space-missions-tracker"

HORIZONS_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"

# Active interplanetary missions and their Horizons spacecraft IDs, with
# well-documented mission facts for context (agency, launch year, destination).
MISSIONS = {
    "Lucy":            {"id": -49,  "agency": "NASA", "launch_year": 2021, "destination": "Jupiter Trojan asteroids"},
    "Psyche":          {"id": -255, "agency": "NASA", "launch_year": 2023, "destination": "16 Psyche (metal asteroid)"},
    "Juno":            {"id": -61,  "agency": "NASA", "launch_year": 2011, "destination": "Jupiter"},
    "Europa Clipper":  {"id": -159, "agency": "NASA", "launch_year": 2024, "destination": "Europa (moon of Jupiter)"},
    "OSIRIS-APEX":     {"id": -64,  "agency": "NASA", "launch_year": 2016, "destination": "99942 Apophis"},
    "Voyager 1":       {"id": -31,  "agency": "NASA", "launch_year": 1977, "destination": "Interstellar space"},
    "Voyager 2":       {"id": -32,  "agency": "NASA", "launch_year": 1977, "destination": "Interstellar space"},
    "New Horizons":    {"id": -98,  "agency": "NASA", "launch_year": 2006, "destination": "Kuiper Belt"},
    "JUICE":           {"id": -28,  "agency": "ESA",  "launch_year": 2023, "destination": "Jupiter icy moons"},
}

# ── Column descriptions ───────────────────────────────────────────────
COLUMN_DESCRIPTIONS = {
    "date": "UTC date of the ephemeris snapshot (00:00 UT geometry).",
    "mission": "Common name of the spacecraft.",
    "spacecraft_id": "JPL Horizons spacecraft identifier (a negative integer; e.g. -31 for Voyager 1).",
    "agency": "Operating space agency (NASA or ESA).",
    "launch_year": "Calendar year the spacecraft launched.",
    "destination": "Primary mission target or regime.",
    "ra_deg": "Astrometric right ascension of the spacecraft as seen from Earth's center, ICRF frame, in degrees (0-360).",
    "dec_deg": "Astrometric declination as seen from Earth's center, ICRF frame, in degrees (-90 to +90).",
    "sun_distance_au": "Heliocentric distance: distance from the spacecraft to the Sun, in astronomical units (1 AU = ~149.6 million km).",
    "earth_distance_au": "Geocentric distance: distance from the spacecraft to Earth, in astronomical units. Drives signal strength and round-trip light time.",
    "sun_range_rate_kms": "Rate of change of the heliocentric distance, in km/s. Positive means receding from the Sun, negative means approaching.",
    "earth_range_rate_kms": "Rate of change of the Earth distance, in km/s. Positive means receding from Earth.",
    "light_time_min": "One-way light travel time from the spacecraft to Earth, in minutes. The signal delay for commands and telemetry.",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
A daily-updating log of where humanity's active deep-space missions are right now, \
computed from NASA/JPL's Horizons ephemeris system. Updated daily, growing one row \
per mission per day.

The dataset tracks a fleet of interplanetary spacecraft -- the Voyagers in \
interstellar space, New Horizons in the Kuiper Belt, Juno at Jupiter, the asteroid \
explorers Lucy, Psyche, and OSIRIS-APEX, and the Jupiter-bound Europa Clipper and \
JUICE. For each spacecraft and each day it records the heliocentric distance \
(distance from the Sun), the geocentric distance (distance from Earth), the sky \
position (right ascension and declination), the radial velocities, and the one-way \
light travel time to Earth.

Together these quantities turn abstract mission status into something tangible: you \
can watch the Voyagers' light-time stretch past 20 hours, see Lucy's distance swing \
as it loops out to the Jupiter Trojans, or compare how far each probe has traveled \
from the Sun. The geometry is authoritative -- Horizons is the same system mission \
navigators and observatories use -- so the dataset is suitable for plotting \
trajectories, computing communication delays, planning ground-based observations, \
and teaching orbital mechanics. The Horizons ephemerides themselves are computed by \
JPL (a US Government facility); the included mission facts are drawn from public \
mission documentation."""


def fetch_mission(name, info, day):
    """Query Horizons for one spacecraft's geometry on `day`; return a row dict or None."""
    params = {
        "format": "json",
        "COMMAND": f"'{info['id']}'",
        "OBJ_DATA": "'NO'",
        "MAKE_EPHEM": "'YES'",
        "EPHEM_TYPE": "'OBSERVER'",
        "CENTER": "'500@399'",
        "START_TIME": f"'{day:%Y-%m-%d}'",
        "STOP_TIME": f"'{(day + timedelta(days=1)):%Y-%m-%d}'",
        "STEP_SIZE": "'1 d'",
        "QUANTITIES": "'1,19,20,21'",
        "CSV_FORMAT": "'YES'",
        "ANG_FORMAT": "'DEG'",
    }
    result = None
    for attempt in range(3):
        try:
            resp = requests.get(HORIZONS_URL, params=params, timeout=45)
            resp.raise_for_status()
            result = resp.json().get("result", "")
            break
        except requests.RequestException as exc:
            if attempt == 2:
                print(f"  WARNING: could not fetch {name} ({info['id']}) after retries: {exc}")
                return None
            time.sleep(2 ** attempt)

    try:
        block = result.split("$$SOE")[1].split("$$EOE")[0].strip().splitlines()
        # CSV cols: date, solar-flag, lunar-flag, RA, DEC, r, rdot, delta, deldot, LT
        p = [c.strip() for c in block[0].split(",")]
        return {
            "date": pd.Timestamp(day).normalize(),
            "mission": name,
            "spacecraft_id": info["id"],
            "agency": info["agency"],
            "launch_year": info["launch_year"],
            "destination": info["destination"],
            "ra_deg": float(p[3]),
            "dec_deg": float(p[4]),
            "sun_distance_au": float(p[5]),
            "earth_distance_au": float(p[7]),
            "sun_range_rate_kms": float(p[6]),
            "earth_range_rate_kms": float(p[8]),
            "light_time_min": float(p[9]),
        }
    except Exception as exc:
        print(f"  WARNING: could not parse Horizons ephemeris for {name} ({info['id']}): {exc}")
        return None


def main():
    print("Tracking active deep-space missions via JPL Horizons...")
    day = datetime.now(timezone.utc).date()

    rows = [r for r in (fetch_mission(n, i, day) for n, i in MISSIONS.items()) if r]
    df_today = pd.DataFrame(rows)
    print(f"  Retrieved {len(df_today)}/{len(MISSIONS)} missions for {day}")

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Deep-Space Missions Tracker",
        description=DESCRIPTION,
        tags=["space", "deep-space", "spacecraft", "ephemeris", "jpl-horizons",
              "solar-system", "open-data", "tabular-data", "parquet"],
        source_url="https://ssd.jpl.nasa.gov/horizons/",
        task_categories=["time-series-forecasting"],
        collection_url="https://huggingface.co/collections/juliensimon/space-probe-and-mission-datasets-69c3fe82d410a42b1e313167",
        banner={"url": "https://images-assets.nasa.gov/image/PIA14111/PIA14111~small.jpg",
                "alt": "Voyager spacecraft in interstellar space (artist concept)",
                "credit": "NASA/JPL-Caltech"},
        update_schedule="Daily at 16:55 UTC",
        related_datasets=[
            "juliensimon/deep-space-probes",
            "juliensimon/space-missions",
            "juliensimon/parker-solar-probe-encounters",
            "juliensimon/solar-orbiter-encounters",
            "juliensimon/spacecraft-database",
        ],
    ) as p:
        df_existing = p.download_existing("missions_tracker.parquet")

        if df_existing is None or len(df_existing) == 0:
            df = df_today.copy()  # first run: seed from today
        else:
            df_existing["date"] = pd.to_datetime(df_existing["date"])
            df = p.append_by_date(df_existing, df_today, date_col="date", min_existing=1)
            print(f"  Appended: {len(df):,} total rows ({len(df) - len(df_existing):+,} net new)")

        df = p.clean(
            df,
            numeric=["ra_deg", "dec_deg", "sun_distance_au", "earth_distance_au",
                     "sun_range_rate_kms", "earth_range_rate_kms", "light_time_min"],
            integer=["spacecraft_id", "launch_year"],
            strings=["mission", "agency", "destination"],
        )

        # ── Stats ────────────────────────────────────────────────────
        n = len(df)
        n_days = df["date"].nunique()
        latest = df[df["date"] == df["date"].max()]
        farthest = latest.loc[latest["earth_distance_au"].idxmax()]

        quick_stats = f"""\
- **{n:,}** position records across **{len(MISSIONS)}** missions and **{n_days}** day(s)
- Most distant today: **{farthest['mission']}** at **{farthest['earth_distance_au']:.1f} AU** from Earth
- That signal takes **{farthest['light_time_min'] / 60:.1f} hours** to reach us"""

        usage = """\
```python
from datasets import load_dataset
import matplotlib.pyplot as plt

ds = load_dataset("juliensimon/deep-space-missions-tracker", split="train")
df = ds.to_pandas()

# Current distance of each mission from the Sun
latest = df[df["date"] == df["date"].max()].sort_values("sun_distance_au")
fig, ax = plt.subplots(figsize=(9, 5))
ax.barh(latest["mission"], latest["sun_distance_au"])
ax.set_xlabel("Distance from the Sun (AU)")
ax.set_title("Active Deep-Space Missions: Heliocentric Distance")
plt.tight_layout()
plt.show()

# Track one mission's Earth distance over time
voyager = df[df["mission"] == "Voyager 1"].sort_values("date")
plt.plot(voyager["date"], voyager["light_time_min"] / 60)
plt.ylabel("One-way light time (hours)")
plt.title("Voyager 1 signal delay")
plt.show()
```"""

        p.publish(
            df,
            filename="missions_tracker.parquet",
            min_rows=5,
            expected_columns=["date", "mission", "sun_distance_au", "earth_distance_au"],
            critical_columns=["date", "mission", "earth_distance_au"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update deep-space missions tracker: {n:,} rows",
        )
    print("Done.")


if __name__ == "__main__":
    main()
