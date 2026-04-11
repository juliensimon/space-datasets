#!/usr/bin/env python3
"""Fetch hourly neutron monitor cosmic ray data from NMDB and upload to HF.

Source: Neutron Monitor Database (NMDB) — https://www.nmdb.eu/
Founded under EU FP7 (contract no. 213007).
"""

import sys
import time
from datetime import datetime, timedelta

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

HF_REPO = "juliensimon/neutron-monitor-cosmic-rays"

# Stations: high-latitude, mid-latitude, high-altitude, low-latitude, polar
STATIONS = {
    "OULU": "Oulu, Finland",
    "NEWK": "Newark, USA",
    "JUNG": "Jungfraujoch, Switzerland",
    "ROME": "Rome, Italy",
    "THUL": "Thule, Greenland",
    "APTY": "Apatity, Russia",
}

API_URL = "https://www.nmdb.eu/nest/draw_graph.php"
START_YEAR = 2005  # NMDB reliable coverage starts ~2005

# ── Column descriptions ─────────────────────────────────────────────
COLUMN_DESCRIPTIONS = {
    "datetime": "Observation timestamp (UTC, hourly averages from 1-minute raw counts)",
    "station": "NMDB station code (e.g. 'OULU' for Oulu Finland, 'JUNG' for Jungfraujoch Switzerland); location determines geomagnetic cutoff rigidity and therefore the cosmic ray energy threshold the station is sensitive to",
    "count_rate": "Pressure-corrected and efficiency-corrected cosmic ray neutron count rate in counts per second; decreases during Forbush decreases (CME-driven CR depressions of 1-30%) and spikes during Ground Level Enhancements (GLEs, solar energetic particle events); null when station data are unavailable",
    "station_name": "Human-readable station name and country (e.g. 'Oulu, Finland'); polar stations detect lower-energy cosmic rays (~0.2 GV cutoff) while equatorial stations have higher cutoffs (~15 GV)",
    "daily_mean_count_rate": "24-hour mean count rate for this station on the same calendar day, in counts per second; used as the baseline for pct_deviation calculation",
    "pct_deviation": "Hourly count rate deviation from the daily mean in percent, i.e. (count_rate - daily_mean) / daily_mean x 100; negative values indicate suppressed cosmic ray flux (Forbush decrease); large positive values (>1%) may indicate GLE onset",
}

DESCRIPTION = """\
Hourly cosmic ray intensity measurements from the Neutron Monitor Database (NMDB) -- the worldwide \
network of ground-based cosmic ray detectors. Neutron monitors detect secondary neutrons produced \
when galactic cosmic rays interact with Earth's atmosphere.

The count rate is a proxy for cosmic ray intensity at Earth and is modulated by solar activity \
(11-year cycle), transient solar events (Forbush decreases), and geomagnetic conditions. \
Higher-latitude and higher-altitude stations have lower geomagnetic cutoff rigidity, making them \
more sensitive to lower-energy cosmic rays.

Galactic cosmic rays (GCRs) are relativistic charged particles -- predominantly protons and heavier \
nuclei -- accelerated to GeV-TeV energies by supernova remnant shocks. As they enter the heliosphere, \
their flux is modulated by the solar wind's outward-convecting magnetic field: during solar maximum, \
enhanced magnetic turbulence reduces the count rate at Earth by 15-25% compared to solar minimum. \
On shorter timescales, neutron monitors are the primary ground-based detectors for Forbush decreases \
-- sudden drops in cosmic ray intensity (typically 3-15% over hours) caused by the passage of \
interplanetary CMEs. Ground-level enhancements (GLEs) -- rare but dramatic increases in count rate -- \
signal the arrival of GeV-energy solar energetic particles from the most powerful solar flares."""


# ── Custom fetch/parse functions ─────────────────────────────────────

def fetch_nmdb(start_dt, end_dt):
    """Fetch hourly corrected count rates from NMDB for all stations."""
    params = {
        "formchk": "1",
        "output": "ascii",
        "tresolution": "60",
        "date_choice": "bydate",
        "start_year": start_dt.strftime("%Y"),
        "start_month": start_dt.strftime("%m"),
        "start_day": start_dt.strftime("%d"),
        "start_hour": "00",
        "start_min": "00",
        "end_year": end_dt.strftime("%Y"),
        "end_month": end_dt.strftime("%m"),
        "end_day": end_dt.strftime("%d"),
        "end_hour": "23",
        "end_min": "59",
    }
    station_params = "&".join(f"stations[]={s}" for s in STATIONS)
    url = f"{API_URL}?{station_params}"

    print(f"  Fetching {start_dt.date()} to {end_dt.date()} ...")
    resp = requests.get(url, params=params, timeout=120)
    resp.raise_for_status()

    text = resp.text
    if "no data available" in text.lower():
        print("  No data returned from NMDB")
        return pd.DataFrame()

    return parse_nmdb_ascii(text)


def parse_nmdb_ascii(text):
    """Parse NMDB ASCII response into a long-format DataFrame."""
    lines = text.splitlines()
    header_line = None
    data_start = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#") or stripped == "":
            continue
        if ";" not in stripped:
            header_line = stripped
            data_start = i + 1
            break
        else:
            data_start = i
            break

    if data_start is None:
        return pd.DataFrame()

    station_codes = header_line.split() if header_line else list(STATIONS.keys())

    records = []
    for line in lines[data_start:]:
        stripped = line.strip()
        if stripped == "" or stripped.startswith("#"):
            continue
        parts = stripped.split(";")
        if len(parts) < 2:
            continue
        try:
            timestamp = parts[0].strip()
            dt = pd.Timestamp(timestamp)
            values = {}
            for j, code in enumerate(station_codes):
                if j + 1 < len(parts):
                    val_str = parts[j + 1].strip()
                    if val_str == "" or val_str == "null":
                        values[code] = None
                    else:
                        values[code] = float(val_str)
                else:
                    values[code] = None
            for code, val in values.items():
                records.append({
                    "datetime": dt,
                    "station": code,
                    "count_rate": val,
                })
        except (ValueError, IndexError):
            continue

    return pd.DataFrame(records)


def fetch_full():
    """Full rebuild: fetch year by year from START_YEAR to now."""
    now = datetime.utcnow()
    all_dfs = []

    for year in range(START_YEAR, now.year + 1):
        start_dt = datetime(year, 1, 1)
        end_dt = datetime(year, 12, 31) if year < now.year else now
        df_year = fetch_nmdb(start_dt, end_dt)
        if not df_year.empty:
            all_dfs.append(df_year)
            print(f"    {year}: {len(df_year):,} records")
        time.sleep(2)  # Be polite to NMDB

    if all_dfs:
        return pd.concat(all_dfs, ignore_index=True)
    return pd.DataFrame()


def fetch_incremental(days=14):
    """Fetch the last N days of data."""
    now = datetime.utcnow()
    start_dt = now - timedelta(days=days)
    return fetch_nmdb(start_dt, now)


# ── Main ─────────────────────────────────────────────────────────────

def main():
    print("Fetching neutron monitor cosmic ray data from NMDB...")
    now = datetime.utcnow()

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Neutron Monitor Cosmic Ray Intensity (Hourly)",
        description=DESCRIPTION,
        tags=["space", "cosmic-rays", "neutron-monitor", "space-weather",
              "open-data", "tabular-data", "parquet"],
        source_url="https://www.nmdb.eu/",
        task_categories=["time-series-forecasting", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70",
        banner={"url": "https://images-assets.nasa.gov/image/iss072e159172/iss072e159172~medium.jpg",
                "alt": "Aurora borealis blankets the Earth, seen from the ISS",
                "credit": "NASA"},
        update_schedule="Daily at 14:30 UTC",
        related_datasets=[
            "juliensimon/dst-index",
            "juliensimon/space-weather-indices",
            "juliensimon/solar-flare-events",
        ],
    ) as p:
        # Try incremental
        df_existing = p.download_existing("neutron_monitor.parquet")

        if df_existing is not None and len(df_existing) > 0:
            df_existing["datetime"] = pd.to_datetime(df_existing["datetime"])
            print("  Incremental mode: fetching last 14 days")
            df_new = fetch_incremental(days=14)
            if not df_new.empty:
                cutoff = df_new["datetime"].min()
                df_kept = df_existing[df_existing["datetime"] < cutoff]
                df = pd.concat([df_kept, df_new], ignore_index=True)
                print(f"  Merged: {len(df):,} records (kept {len(df_kept):,} + {len(df_new):,} new)")
            else:
                df = df_existing
                print("  No new data, using existing")
        else:
            print(f"  Full rebuild from {START_YEAR}...")
            df = fetch_full()

        if df.empty:
            print("::error::No neutron monitor data retrieved")
            sys.exit(1)

        # Clean up
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.sort_values(["datetime", "station"]).reset_index(drop=True)
        df = df.drop_duplicates(subset=["datetime", "station"], keep="last")

        # Remove future rows
        df = df[df["datetime"] <= pd.Timestamp.now(tz=None)]

        # Add station metadata
        df["station_name"] = df["station"].map(STATIONS).fillna(df["station"])

        # Derived columns: daily mean per station
        df["date"] = df["datetime"].dt.date.astype(str)
        daily_mean = df.groupby(["date", "station"])["count_rate"].transform("mean")
        df["daily_mean_count_rate"] = daily_mean.round(3)

        # Percentage deviation from station daily mean
        df["pct_deviation"] = (
            ((df["count_rate"] - df["daily_mean_count_rate"]) / df["daily_mean_count_rate"] * 100)
            .round(3)
        )
        df = df.drop(columns=["date"])

        df = p.clean(df, numeric=["count_rate", "daily_mean_count_rate", "pct_deviation"])

        # Keep only described columns
        df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

        # Stats
        n_total = len(df)
        date_min = df["datetime"].min().strftime("%Y-%m-%d")
        date_max = df["datetime"].max().strftime("%Y-%m-%d")
        n_stations = df["station"].nunique()
        station_list = ", ".join(sorted(df["station"].unique()))
        mean_rate = df["count_rate"].mean()
        min_rate = df["count_rate"].min()
        min_rate_time = df.loc[df["count_rate"].idxmin(), "datetime"].strftime("%Y-%m-%d %H:%M")
        min_rate_station = df.loc[df["count_rate"].idxmin(), "station"]
        null_pct = df["count_rate"].isna().mean() * 100

        quick_stats = f"""\
- **{n_total:,}** hourly readings ({date_min} to {date_max})
- **{n_stations}** stations: {station_list}
- Mean count rate: **{mean_rate:.1f}**
- Minimum count rate: **{min_rate:.1f}** ({min_rate_station}, {min_rate_time})
- Missing values: {null_pct:.1f}%"""

        usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/neutron-monitor-cosmic-rays", split="train")
df = ds.to_pandas()

# Compare stations
import matplotlib.pyplot as plt

pivot = df.pivot_table(index="datetime", columns="station", values="count_rate")
pivot.resample("1M").mean().plot(figsize=(12, 5))
plt.title("Monthly Mean Cosmic Ray Intensity by Station")
plt.ylabel("Count Rate")
plt.tight_layout()
plt.show()

# Detect Forbush decreases (sudden drops in cosmic ray intensity)
oulu = df[df["station"] == "OULU"].set_index("datetime")["count_rate"]
daily = oulu.resample("1D").mean()
forbush = daily[daily.pct_change() < -0.03]  # >3% daily drop

# Solar cycle modulation
df["year"] = df["datetime"].dt.year
yearly = df.groupby(["year", "station"])["count_rate"].mean().unstack()
yearly.plot(figsize=(10, 5))
plt.title("Annual Mean Count Rate (Solar Cycle Modulation)")
plt.show()
```"""

        p.publish(
            df,
            filename="neutron_monitor.parquet",
            min_rows=400_000,
            max_null_pct=0.10,
            expected_columns=["datetime", "station", "count_rate", "station_name",
                              "daily_mean_count_rate", "pct_deviation"],
            critical_columns=["count_rate"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update neutron monitor: {n_total:,} hourly readings",
        )
    print("Done.")


if __name__ == "__main__":
    main()
