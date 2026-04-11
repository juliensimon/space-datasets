#!/usr/bin/env python3
"""Fetch solar flare events from GOES-16 (NCEI) + SWPC daily report and upload to HF.

Incremental: downloads existing data from HF. In normal mode, reuses NCEI bulk data
and appends SWPC daily flares. Set FULL_REBUILD=1 to re-download the NCEI NetCDF.
"""

import os
import re
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from hf_dataset_utils import Pipeline

try:
    import netCDF4 as nc
except ImportError:
    nc = None

NCEI_BASE = "https://data.ngdc.noaa.gov/platforms/solar-space-observing-satellites/goes/goes16/l2/data/xrsf-l2-flsum_science/"
SWPC_EVENTS = "https://services.swpc.noaa.gov/text/solar-geophysical-event-reports.txt"
HF_REPO = "juliensimon/solar-flare-events"

EPOCH = datetime(2000, 1, 1, 12, 0, 0)

# ── Column descriptions ─────────────────────────────────────────────
COLUMN_DESCRIPTIONS = {
    "start_time": "UTC time when GOES X-ray flux first rises above background threshold; marks onset of the impulsive phase",
    "peak_time": "UTC time of maximum X-ray flux in the 1-8 A band; the reference instant used to assign the flare class",
    "end_time": "UTC time when X-ray flux returns to pre-flare background; duration from start to end is typically minutes for impulsive events, hours for long-duration events (LDEs) associated with CMEs",
    "goes_class": "Full NOAA flare classification (e.g. 'B3.7', 'C1.6', 'M5.1', 'X1.0'); letter sets the decade, number is the multiplier (M5.2 = 5.2 x 10^-5 W/m2)",
    "goes_class_letter": "NOAA flare class letter: 'A' (background, 10^-8 W/m2), 'B' (10^-7), 'C' (10^-6, minor), 'M' (10^-5, moderate, may cause radio blackouts at HF), 'X' (>= 10^-4, major, can cause HF blackouts, radiation storms, CMEs)",
    "peak_flux_wm2": "Peak GOES X-ray flux in the 1-8 A band in W/m2; ranges from ~10^-8 (quiet sun) to ~10^-3 (extreme X-class); the numeric value that defines the full goes_class",
    "active_region": "NOAA Active Region number of the source sunspot group (e.g. 12673); null when no source region is identified (e.g. behind-the-limb or spotless events)",
    "satellite": "GOES satellite that recorded the event: 'GOES-16' (primary since 2017) or 'GOES-18' (primary from 2022)",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Individual solar flare detections from GOES X-ray sensors (2017-present) with class, \
peak flux, and timing. Updated daily.

Solar flares are sudden bursts of electromagnetic radiation from the Sun. They are \
classified by peak X-ray flux in the 1-8 Angstrom band: B (< 10^-6 W/m2), \
C (10^-6), M (10^-5), and X (10^-4 W/m2). M and X-class flares can cause radio \
blackouts, GPS errors, satellite anomalies, and geomagnetic storms that increase \
atmospheric drag on LEO satellites.

Solar flares originate in magnetically complex active regions where stressed field \
lines reconnect explosively, converting stored magnetic energy into thermal radiation, \
accelerated particles, and bulk plasma motion in a matter of minutes. The GOES X-Ray \
Sensor (XRS) measures the Sun-integrated soft X-ray flux in two broadband channels \
(0.5-4 A and 1-8 A), with the 1-8 A band used for the standard classification system. \
The classification is logarithmic: an X1.0 flare has 10 times the peak flux of an M1.0 \
flare. Within each letter class, the numeric suffix scales linearly.

The timing profile of a flare -- start, peak, and end -- encodes physically meaningful \
information. The impulsive phase (start to peak) typically lasts 5-20 minutes and \
corresponds to the primary energy release via magnetic reconnection. The gradual phase \
(peak to end) can extend for hours as post-flare loops cool. Short-duration impulsive \
flares tend to be confined events, while long-duration events (LDEs) are more often \
associated with coronal mass ejections and solar energetic particle events."""


def fetch_ncei_flares():
    """Download and parse the GOES-16 mission-length NetCDF flare summary."""
    if nc is None:
        raise RuntimeError("netCDF4 is required: pip install netCDF4")

    # Discover the current filename
    print("  Discovering NCEI flare summary file...")
    resp = requests.get(NCEI_BASE, timeout=30)
    resp.raise_for_status()
    match = re.search(r'href="(sci_xrsf-l2-flsum_g16_[^"]+\.nc)"', resp.text)
    if not match:
        raise RuntimeError(f"Could not find NetCDF file at {NCEI_BASE}")
    filename = match.group(1)
    url = NCEI_BASE + filename
    print(f"  Downloading {filename}...")

    # Download to temp file
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    tmp_nc = Path(tempfile.mktemp(suffix=".nc"))
    tmp_nc.write_bytes(resp.content)
    print(f"  {len(resp.content) / 1024 / 1024:.1f} MB downloaded")

    # Parse NetCDF
    ds = nc.Dataset(str(tmp_nc))
    times = ds.variables["time"][:]
    statuses = ds.variables["status"][:]
    flare_ids = ds.variables["flare_id"][:]
    classes = ds.variables["flare_class"][:]
    fluxes = ds.variables["xrsb_flux"][:]
    ds.close()
    tmp_nc.unlink()

    # Pivot: one row per flare, extracting start/peak/end times and peak flux
    records = {}
    for i in range(len(flare_ids)):
        fid = int(flare_ids[i])
        t = EPOCH + timedelta(seconds=float(times[i]))
        status = statuses[i]
        flux = float(fluxes[i]) if not np.ma.is_masked(fluxes[i]) else None

        if fid not in records:
            records[fid] = {"flare_id": fid, "satellite": "GOES-16"}

        rec = records[fid]
        if status == "EVENT_START":
            rec["start_time"] = t
        elif status == "EVENT_PEAK":
            rec["peak_time"] = t
            rec["peak_flux_wm2"] = flux
            cls = classes[i].strip()
            if cls:
                rec["goes_class"] = cls
        elif status == "EVENT_END":
            rec["end_time"] = t

    df = pd.DataFrame(records.values())
    # Extract class letter
    df["goes_class_letter"] = df["goes_class"].str.extract(r"^([ABCMX])", expand=False)
    print(f"  {len(df):,} flares from NCEI (GOES-16)")
    return df


def parse_swpc_xra_line(line, date_str):
    """Parse a single XRA line from SWPC event report."""
    parts = line.split()
    if len(parts) < 11:
        return None

    try:
        parts.index("XRA")
    except ValueError:
        return None

    # Fixed-width columns from the SWPC format
    try:
        begin = line[14:18].strip()
        max_t = line[21:25].strip()
        end = line[30:34].strip()

        after_xra = line[line.index("XRA") + 3:].strip()
        match = re.search(r"([ABCMX]\d+\.?\d*)\s+([\d.E+-]+)", after_xra)
        if not match:
            return None

        goes_class = match.group(1)
        peak_flux = float(match.group(2))

        year = int(date_str[:4])
        month = int(date_str[4:6])
        day = int(date_str[6:8])

        def parse_hhmm(hhmm):
            if not hhmm or hhmm == "////" or not hhmm.replace("A", "").isdigit():
                return None
            h = int(hhmm[:2]) if len(hhmm) == 4 else int(hhmm[0])
            m = int(hhmm[-2:])
            return datetime(year, month, day, h, m)

        reg_match = re.search(r"(\d{4})\s*$", after_xra)
        active_region = int(reg_match.group(1)) if reg_match else None

        return {
            "start_time": parse_hhmm(begin),
            "peak_time": parse_hhmm(max_t),
            "end_time": parse_hhmm(end),
            "goes_class": goes_class,
            "goes_class_letter": goes_class[0],
            "peak_flux_wm2": peak_flux,
            "active_region": active_region,
            "satellite": "GOES-18",
        }
    except (ValueError, IndexError):
        return None


def fetch_swpc_daily_flares():
    """Fetch and parse today's SWPC event report for XRA (X-ray flare) events."""
    print("  Fetching SWPC daily event report...")
    resp = requests.get(SWPC_EVENTS, timeout=30)
    resp.raise_for_status()
    lines = resp.text.splitlines()

    date_str = None
    for line in lines:
        match = re.search(r":Date:\s+(\d{4})\s+(\d{2})\s+(\d{2})", line)
        if match:
            date_str = match.group(1) + match.group(2) + match.group(3)
            break

    if not date_str:
        print("  Could not parse date from SWPC report")
        return pd.DataFrame()

    records = []
    for line in lines:
        if "XRA" in line and not line.startswith("#"):
            rec = parse_swpc_xra_line(line, date_str)
            if rec:
                records.append(rec)

    df = pd.DataFrame(records) if records else pd.DataFrame()
    print(f"  {len(df)} flares from SWPC daily report ({date_str})")
    return df


def main():
    print("Fetching solar flare events...")

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Solar Flare Events (GOES X-ray)",
        description=DESCRIPTION,
        tags=["space", "solar-flare", "goes", "space-weather", "noaa",
              "goes-16", "x-ray", "ncei", "solar-activity",
              "open-data", "tabular-data", "parquet"],
        source_url="https://data.ngdc.noaa.gov/platforms/solar-space-observing-satellites/goes/goes16/l2/data/xrsf-l2-flsum_science/",
        task_categories=["tabular-classification", "time-series-forecasting"],
        collection_url="https://huggingface.co/collections/juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70",
        banner={"url": "https://images-assets.nasa.gov/image/brief-outburst_16760026566_o/brief-outburst_16760026566_o~medium.jpg",
                "alt": "A solar eruption captured by NASA's Solar Dynamics Observatory",
                "credit": "NASA/SDO"},
        update_schedule="Daily at 12:00 UTC",
        related_datasets=[
            "juliensimon/space-weather-indices",
            "juliensimon/donki-space-weather-events",
            "juliensimon/solar-wind",
        ],
    ) as p:
        df_existing = p.download_existing("solar_flare_events.parquet")

        if df_existing is not None and len(df_existing) > 0:
            # Incremental: skip NCEI download, just append SWPC daily
            print("  Incremental mode: reusing existing NCEI data, appending SWPC daily")
            swpc_df = fetch_swpc_daily_flares()

            # Remove any previous SWPC-sourced flares to replace with fresh
            df_ncei_only = df_existing[df_existing["satellite"] != "GOES-18"]

            if not swpc_df.empty:
                new_flares = swpc_df[swpc_df["peak_time"] > df_ncei_only["peak_time"].max()]
                if not new_flares.empty:
                    print(f"  Adding {len(new_flares)} recent flares from SWPC")
                    df = pd.concat([df_ncei_only, new_flares], ignore_index=True)
                else:
                    df = df_ncei_only
                    print("  No new SWPC flares")
            else:
                df = df_ncei_only

            # Periodically do a full NCEI refresh if requested
            if os.environ.get("FULL_REBUILD"):
                print("  FULL_REBUILD requested, fetching NCEI...")
                ncei_df = fetch_ncei_flares()
                swpc_df2 = fetch_swpc_daily_flares()
                if not swpc_df2.empty and not ncei_df.empty:
                    new_flares = swpc_df2[swpc_df2["peak_time"] > ncei_df["peak_time"].max()]
                    if not new_flares.empty:
                        df = pd.concat([ncei_df, new_flares], ignore_index=True)
                    else:
                        df = ncei_df
                else:
                    df = ncei_df
        else:
            # Full rebuild
            print("  Full rebuild: downloading NCEI NetCDF...")
            ncei_df = fetch_ncei_flares()
            swpc_df = fetch_swpc_daily_flares()

            if not swpc_df.empty and not ncei_df.empty:
                ncei_end = ncei_df["peak_time"].max()
                new_flares = swpc_df[swpc_df["peak_time"] > ncei_end]
                if not new_flares.empty:
                    print(f"  Adding {len(new_flares)} recent flares from SWPC")
                    df = pd.concat([ncei_df, new_flares], ignore_index=True)
                else:
                    df = ncei_df
            else:
                df = ncei_df

        # Clean up
        df = df.sort_values("start_time").reset_index(drop=True)
        df = df.drop(columns=["flare_id"], errors="ignore")

        # Ensure proper types
        for col in ["start_time", "peak_time", "end_time"]:
            df[col] = pd.to_datetime(df[col], errors="coerce")
        df["peak_flux_wm2"] = pd.to_numeric(df["peak_flux_wm2"], errors="coerce")
        if "active_region" in df.columns:
            df["active_region"] = pd.to_numeric(df["active_region"], errors="coerce").astype("Int64")
        else:
            df["active_region"] = pd.array([pd.NA] * len(df), dtype="Int64")

        # Keep only described columns
        df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

        df = p.clean(df, numeric=["peak_flux_wm2"],
                     integer=["active_region"],
                     strings=["goes_class", "goes_class_letter", "satellite"])

        # Stats
        n_total = len(df)
        n_c = int((df["goes_class_letter"] == "C").sum())
        n_m = int((df["goes_class_letter"] == "M").sum())
        n_x = int((df["goes_class_letter"] == "X").sum())
        date_min = df["start_time"].min().strftime("%Y-%m-%d")
        date_max = df["start_time"].max().strftime("%Y-%m-%d")

        strongest = df.loc[df["peak_flux_wm2"].idxmax()]
        strongest_class = strongest["goes_class"]
        strongest_date = strongest["peak_time"].strftime("%Y-%m-%d %H:%M")

        quick_stats = f"""\
- **{n_total:,}** flare events ({date_min} to {date_max})
- **{n_c:,}** C-class, **{n_m:,}** M-class, **{n_x:,}** X-class flares
- Strongest flare: **{strongest_class}** on {strongest_date}"""

        usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/solar-flare-events", split="train")
df = ds.to_pandas()

# M and X class flares only
major = df[df["goes_class_letter"].isin(["M", "X"])]

# Flare frequency over time
import matplotlib.pyplot as plt

df["month"] = df["start_time"].dt.to_period("M")
monthly = df.groupby("month").size()
monthly.plot(figsize=(12, 4), title="Monthly Flare Count")
plt.ylabel("Flares")
plt.tight_layout()
plt.show()

# X-class flares by active region
x_flares = df[df["goes_class_letter"] == "X"]
x_flares["active_region"].value_counts().head(10)

# Flare duration distribution
df["duration_min"] = (df["end_time"] - df["start_time"]).dt.total_seconds() / 60
df["duration_min"].hist(bins=50)
plt.xlabel("Duration (minutes)")
plt.title("Flare Duration Distribution")
plt.show()
```"""

        p.publish(
            df,
            filename="solar_flare_events.parquet",
            min_rows=5000,
            expected_columns=["start_time", "peak_time", "goes_class"],
            critical_columns=["start_time", "goes_class"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update solar flare events: {n_total:,} flares",
        )
    print("Done.")


if __name__ == "__main__":
    main()
