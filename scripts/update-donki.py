#!/usr/bin/env python3
"""Fetch space weather events from NASA DONKI and upload to HF."""

import subprocess
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests


DONKI_BASE = "https://kauai.ccmc.gsfc.nasa.gov/DONKI/WS/get"
HF_REPO = "juliensimon/donki-space-weather-events"
START_YEAR = 2010


def fetch_donki(endpoint, start_date, end_date, extra_params=None):
    """Fetch from a DONKI endpoint with date range."""
    params = {"startDate": start_date, "endDate": end_date}
    if extra_params:
        params.update(extra_params)
    resp = requests.get(f"{DONKI_BASE}/{endpoint}", params=params, timeout=120)
    resp.raise_for_status()
    return resp.json()


def fetch_by_year(endpoint, extra_params=None):
    """Fetch all records by year to avoid timeouts."""
    all_records = []
    now = datetime.utcnow()
    for year in range(START_YEAR, now.year + 1):
        end = f"{year}-12-31" if year < now.year else now.strftime("%Y-%m-%d")
        try:
            records = fetch_donki(endpoint, f"{year}-01-01", end, extra_params)
            all_records.extend(records)
            print(f"    {year}: {len(records)} records")
        except Exception as e:
            print(f"    {year}: error - {e}")
        time.sleep(0.5)  # Be polite to the API
    return all_records


def parse_cmes(raw):
    """Parse CME records into flat rows."""
    rows = []
    for cme in raw:
        row = {
            "event_type": "CME",
            "activity_id": cme.get("activityID"),
            "start_time": cme.get("startTime"),
            "source_location": cme.get("sourceLocation") or None,
            "active_region": cme.get("activeRegionNum"),
            "note": cme.get("note"),
            "link": cme.get("link"),
        }
        # Extract best analysis
        analyses = cme.get("cmeAnalyses") or []
        best = next((a for a in analyses if a.get("isMostAccurate")), analyses[0] if analyses else None)
        if best:
            row["cme_speed_kms"] = best.get("speed")
            row["cme_half_angle_deg"] = best.get("halfAngle")
            row["cme_latitude"] = best.get("latitude")
            row["cme_longitude"] = best.get("longitude")
            row["cme_type"] = best.get("type")
            row["cme_time_21_5"] = best.get("time21_5")
            row["cme_measurement"] = best.get("measurementTechnique")

        # Linked events
        linked = cme.get("linkedEvents") or []
        row["linked_events"] = ", ".join(e.get("activityID", "") for e in linked) if linked else None

        rows.append(row)
    return rows


def parse_gsts(raw):
    """Parse geomagnetic storm records."""
    rows = []
    for gst in raw:
        # Extract max Kp from allKpIndex
        kp_list = gst.get("allKpIndex") or []
        max_kp = max((k.get("kpIndex", 0) for k in kp_list), default=None) if kp_list else None
        kp_times = [{"time": k.get("observedTime"), "kp": k.get("kpIndex")} for k in kp_list]

        row = {
            "event_type": "GST",
            "activity_id": gst.get("gstID"),
            "start_time": gst.get("startTime"),
            "link": gst.get("link"),
            "gst_max_kp": max_kp,
            "gst_kp_count": len(kp_list),
        }
        linked = gst.get("linkedEvents") or []
        row["linked_events"] = ", ".join(e.get("activityID", "") for e in linked) if linked else None
        rows.append(row)
    return rows


def parse_simple_events(raw, event_type):
    """Parse simple event types (IPS, HSS, SEP, etc.)."""
    rows = []
    id_key = {
        "IPS": "activityID", "HSS": "hssID", "SEP": "sepID",
        "MPC": "mpcID", "RBE": "rbeID",
    }.get(event_type, "activityID")

    for evt in raw:
        row = {
            "event_type": event_type,
            "activity_id": evt.get(id_key),
            "start_time": evt.get("eventTime") or evt.get("startTime"),
            "link": evt.get("link"),
        }
        if event_type == "IPS":
            row["note"] = evt.get("location")
        linked = evt.get("linkedEvents") or []
        row["linked_events"] = ", ".join(e.get("activityID", "") for e in linked) if linked else None
        rows.append(row)
    return rows


ENDPOINTS = [
    ("CME", "CME", parse_cmes),
    ("GST", "GST", parse_gsts),
    ("IPS", "IPS", lambda raw: parse_simple_events(raw, "IPS")),
    ("HSS", "HSS", lambda raw: parse_simple_events(raw, "HSS")),
    ("SEP", "SEP", lambda raw: parse_simple_events(raw, "SEP")),
]

# How many days to re-fetch for corrections (DONKI backfills events)

OVERLAP_DAYS = 14


def fetch_incremental(start_date, end_date):
    """Fetch all event types for a date range."""
    all_rows = []
    for label, endpoint, parser in ENDPOINTS:
        try:
            raw = fetch_donki(endpoint, start_date, end_date)
            rows = parser(raw)
            all_rows.extend(rows)
            print(f"    {label}: {len(rows)} events")
        except Exception as e:
            print(f"    {label}: error - {e}")
        time.sleep(0.5)
    return all_rows


def load_existing(tmp_dir):
    """Download existing parquet from HF. Returns DataFrame or None."""
    parquet_path = tmp_dir / "data" / "donki_events.parquet"
    try:
        subprocess.run(
            ["hf", "download", HF_REPO, "data/donki_events.parquet",
             "--repo-type", "dataset", "--local-dir", str(tmp_dir)],
            check=True, capture_output=True, timeout=30,
        )
        if parquet_path.exists():
            df = pd.read_parquet(parquet_path)
            df["start_time"] = pd.to_datetime(df["start_time"])
            print(f"  Loaded existing: {len(df):,} events")
            return df
    except Exception as e:
        print(f"  Could not load existing ({e}), doing full rebuild")
    return None


def main():
    print("Fetching DONKI space weather events...")

    now = datetime.utcnow()

    # Try incremental: load existing, fetch only recent data
    with tempfile.TemporaryDirectory() as probe:
        df_existing = load_existing(Path(probe))

    if df_existing is not None and len(df_existing) > 0:
        # Incremental: fetch from (max_date - overlap) to today
        max_date = df_existing["start_time"].max()
        fetch_from = (max_date - timedelta(days=OVERLAP_DAYS)).strftime("%Y-%m-%d")
        fetch_to = now.strftime("%Y-%m-%d")
        print(f"  Incremental fetch: {fetch_from} to {fetch_to}")

        new_rows = fetch_incremental(fetch_from, fetch_to)
        df_new = pd.DataFrame(new_rows)

        if not df_new.empty:
            df_new["start_time"] = pd.to_datetime(df_new["start_time"], errors="coerce")
            df_new["cme_time_21_5"] = pd.to_datetime(df_new.get("cme_time_21_5"), errors="coerce")
            df_new["active_region"] = pd.to_numeric(df_new.get("active_region"), errors="coerce").astype("Int64")

            # Merge: new records override existing ones (for corrections)
            df = pd.concat([df_existing, df_new], ignore_index=True)
            df = df.drop_duplicates("activity_id", keep="last")
            print(f"  Merged: {len(df):,} events ({len(df) - len(df_existing):+,} net)")
        else:
            df = df_existing
            print("  No new events")
    else:
        # Full rebuild
        print("  Full rebuild from 2010...")
        all_rows = []
        for label, endpoint, parser in ENDPOINTS:
            print(f"  Fetching {label}...")
            raw = fetch_by_year(endpoint)
            rows = parser(raw)
            all_rows.extend(rows)
            print(f"  {len(raw)} {label}s total")

        df = pd.DataFrame(all_rows)
    df["start_time"] = pd.to_datetime(df["start_time"], errors="coerce")
    df["cme_time_21_5"] = pd.to_datetime(df.get("cme_time_21_5"), errors="coerce")
    df["active_region"] = pd.to_numeric(df.get("active_region"), errors="coerce").astype("Int64")
    df = df.sort_values("start_time").reset_index(drop=True)

    # Stats
    n_total = len(df)
    n_cme = int((df["event_type"] == "CME").sum())
    n_gst = int((df["event_type"] == "GST").sum())
    n_ips = int((df["event_type"] == "IPS").sum())
    n_hss = int((df["event_type"] == "HSS").sum())
    n_sep = int((df["event_type"] == "SEP").sum())
    date_min = df["start_time"].min().strftime("%Y-%m-%d")
    date_max = df["start_time"].max().strftime("%Y-%m-%d")
    fastest_cme = df.loc[df["cme_speed_kms"].idxmax()] if "cme_speed_kms" in df.columns else None
    max_kp = df["gst_max_kp"].max() if "gst_max_kp" in df.columns else None

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "donki_events.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        fastest_speed = int(fastest_cme["cme_speed_kms"]) if fastest_cme is not None else "N/A"
        fastest_date = fastest_cme["start_time"].strftime("%Y-%m-%d") if fastest_cme is not None else "N/A"

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "NASA DONKI Space Weather Events"
language:
  - en
description: "Coronal mass ejections, geomagnetic storms, interplanetary shocks, and solar energetic particles from NASA CCMC DONKI (2010-present)."
task_categories:
  - tabular-classification
  - time-series-forecasting
tags:
  - space
  - space-weather
  - cme
  - geomagnetic-storm
  - solar
  - nasa
  - open-data
  - coronal-mass-ejection
  - ccmc
  - donki
  - solar-wind
  - tabular-data
size_categories:
  - 10K<n<100K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/donki_events.parquet
    default: true
---

# DONKI Space Weather Events

*Part of the [Space Weather Datasets](https://huggingface.co/collections/juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70) collection on Hugging Face.*

![Update DONKI](https://github.com/juliensimon/space-datasets/actions/workflows/update-donki.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.donki&label=updated&color=brightgreen)

Space weather events from NASA's [DONKI](https://kauai.ccmc.gsfc.nasa.gov/DONKI/) (Database Of
Notifications, Knowledge, Information) at the Community Coordinated Modeling Center. Covers
**{date_min}** to **{date_max}** with **{n_total:,}** events.

## Dataset description

DONKI tracks the chain of space weather events from Sun to Earth:

1. **CME** (Coronal Mass Ejection) — eruption of magnetized plasma from the Sun
2. **IPS** (Interplanetary Shock) — shock wave propagating through solar wind
3. **GST** (Geomagnetic Storm) — disturbance in Earth's magnetosphere
4. **HSS** (High Speed Stream) — fast solar wind from coronal holes
5. **SEP** (Solar Energetic Particle) — high-energy particles from solar events

Events are **cross-linked** via the `linked_events` column, enabling causal chain analysis
(e.g., which CME caused which geomagnetic storm).

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `event_type` | string | CME, GST, IPS, HSS, or SEP |
| `activity_id` | string | Unique event identifier |
| `start_time` | datetime | Event start time (UTC) |
| `source_location` | string | Solar source location (CME only, e.g. "N23W45") |
| `active_region` | int | NOAA active region number (CME only) |
| `note` | string | Analyst notes |
| `link` | string | DONKI web page for this event |
| `cme_speed_kms` | float | CME speed in km/s (CME only) |
| `cme_half_angle_deg` | float | CME half-angle in degrees (CME only) |
| `cme_latitude` | float | CME latitude (CME only) |
| `cme_longitude` | float | CME longitude (CME only) |
| `cme_type` | string | CME type: S (slow), C (common), O (occasional), R (rare), ER (extremely rare) |
| `cme_time_21_5` | datetime | Time CME reaches 21.5 solar radii (CME only) |
| `cme_measurement` | string | Measurement technique (CME only) |
| `gst_max_kp` | float | Maximum Kp index during storm (GST only) |
| `gst_kp_count` | int | Number of Kp readings during storm (GST only) |
| `linked_events` | string | Comma-separated IDs of linked events (causal chain) |

## Quick stats

- **{n_total:,}** events ({date_min} to {date_max})
- **{n_cme:,}** CMEs, **{n_gst:,}** geomagnetic storms, **{n_ips:,}** interplanetary shocks
- **{n_hss:,}** high speed streams, **{n_sep:,}** solar energetic particle events
- Fastest CME: **{fastest_speed} km/s** on {fastest_date}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/donki-space-weather-events", split="train")
df = ds.to_pandas()

# Fast CMEs (potential Earth-directed storms)
fast_cmes = df[(df["event_type"] == "CME") & (df["cme_speed_kms"] > 1000)]

# Geomagnetic storms with linked CMEs
storms = df[df["event_type"] == "GST"]
storms_with_cme = storms[storms["linked_events"].str.contains("CME", na=False)]

# CME speed distribution
cmes = df[df["event_type"] == "CME"]
cmes["cme_speed_kms"].hist(bins=50)

# Event frequency by type and year
df["year"] = df["start_time"].dt.year
df.groupby(["year", "event_type"]).size().unstack().plot()

# Causal chain: find all events linked to a specific CME
cme_id = "2024-05-08T22:09:00-CME-001"
chain = df[df["linked_events"].str.contains(cme_id, na=False)]
```

## Data source

[NASA CCMC DONKI API](https://ccmc.gsfc.nasa.gov/tools/DONKI/). Events are catalogued by
space weather analysts at the Community Coordinated Modeling Center (CCMC) using data from
SOHO, STEREO, SDO, and ground-based observatories.

## Update schedule

Daily at 14:00 UTC via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [solar-flare-events](https://huggingface.co/datasets/juliensimon/solar-flare-events) — GOES X-ray flare detections
- [space-weather-indices](https://huggingface.co/datasets/juliensimon/space-weather-indices) — Daily Kp, Ap, F10.7
- [dst-index](https://huggingface.co/datasets/juliensimon/dst-index) — Hourly Dst geomagnetic index
- [neo-close-approaches](https://huggingface.co/datasets/juliensimon/neo-close-approaches) — Near-Earth object approaches

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/donki-space-weather-events) and share feedback in the Community tab!

## Citation

If you use this dataset, please cite:

```bibtex
@dataset{{donki_space_weather_events,
  author = {{Simon, Julien}},
  title = {{NASA DONKI Space Weather Events}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/donki-space-weather-events}}
}}
```

### Data source

[NASA CCMC DONKI API](https://ccmc.gsfc.nasa.gov/tools/DONKI/)

## License

MIT
""")

        print("Uploading to HF...")
        commit_msg = f"Update DONKI events: {n_total:,} events ({n_cme:,} CMEs, {n_gst:,} storms)"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    print("Done.")


if __name__ == "__main__":
    main()
