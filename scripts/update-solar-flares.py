#!/usr/bin/env python3
"""Fetch solar flare events from GOES-16 (NCEI) + SWPC daily report and upload to HF."""

import re
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests

try:
    import netCDF4 as nc
except ImportError:
    nc = None


NCEI_BASE = "https://data.ngdc.noaa.gov/platforms/solar-space-observing-satellites/goes/goes16/l2/data/xrsf-l2-flsum_science/"
SWPC_EVENTS = "https://services.swpc.noaa.gov/text/solar-geophysical-event-reports.txt"
HF_REPO = "juliensimon/solar-flare-events"

EPOCH = datetime(2000, 1, 1, 12, 0, 0)


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
    # Format: Event# +/-  Begin  Max   End  Obs Q Type Loc/Frq  Particulars  Reg#
    # Example: 2260 +     0024   0029  0035  G18  5   XRA  1-8A  C3.2  2.5E-03  4392
    parts = line.split()
    if len(parts) < 11:
        return None

    try:
        # Find XRA position to anchor parsing
        xra_idx = parts.index("XRA")
        # Begin/Max/End are 3 fields before the observatory
        # Work backwards from XRA: parts[xra_idx-3] = Obs, parts[xra_idx-4] = End, etc.
        # Actually, the fields before XRA are: Begin Max End Obs Quality XRA
        # So: Obs = parts[xra_idx-2], Quality = parts[xra_idx-1]... no.
        # Format is fixed-width. Let's use column positions instead.
    except ValueError:
        return None

    # Fixed-width columns from the SWPC format
    try:
        begin = line[14:18].strip()
        max_t = line[21:25].strip()
        end = line[30:34].strip()

        # Particulars: class and flux after the Loc/Frq column
        after_xra = line[line.index("XRA") + 3:].strip()
        # Format: "1-8A      C3.2    2.5E-03   4392"
        match = re.search(r"([ABCMX]\d+\.?\d*)\s+([\d.E+-]+)", after_xra)
        if not match:
            return None

        goes_class = match.group(1)
        peak_flux = float(match.group(2))

        # Parse times
        year = int(date_str[:4])
        month = int(date_str[4:6])
        day = int(date_str[6:8])

        def parse_hhmm(hhmm):
            if not hhmm or hhmm == "////" or not hhmm.replace("A", "").isdigit():
                return None
            h = int(hhmm[:2]) if len(hhmm) == 4 else int(hhmm[0])
            m = int(hhmm[-2:])
            return datetime(year, month, day, h, m)

        # Extract region number (last numeric field)
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

    # Extract date from header
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


def load_existing_flares(tmp_dir):
    """Download existing flare parquet from HF. Returns DataFrame or None."""
    parquet_path = tmp_dir / "data" / "solar_flare_events.parquet"
    try:
        subprocess.run(
            ["hf", "download", HF_REPO, "data/solar_flare_events.parquet",
             "--repo-type", "dataset", "--local-dir", str(tmp_dir)],
            check=True, capture_output=True, timeout=30,
        )
        if parquet_path.exists():
            df = pd.read_parquet(parquet_path)
            print(f"  Loaded existing: {len(df):,} flares")
            return df
    except Exception as e:
        print(f"  Could not load existing ({e}), doing full rebuild")
    return None


def ncei_file_changed():
    """Check if the NCEI NetCDF file has been updated (HEAD request)."""
    print("  Checking if NCEI file has changed...")
    resp = requests.get(NCEI_BASE, timeout=30)
    resp.raise_for_status()
    match = re.search(r'href="(sci_xrsf-l2-flsum_g16_[^"]+\.nc)"', resp.text)
    if not match:
        return True, None  # Can't determine, assume changed
    filename = match.group(1)
    url = NCEI_BASE + filename

    head = requests.head(url, timeout=15)
    content_length = head.headers.get("Content-Length", "")
    last_modified = head.headers.get("Last-Modified", "")
    print(f"  NCEI file: {filename} ({content_length} bytes, modified: {last_modified})")
    return True, filename  # We return the filename; caller decides via size check


def main():
    print("Fetching solar flare events...")

    # Try incremental: load existing, skip NCEI if unchanged
    with tempfile.TemporaryDirectory() as probe:
        df_existing = load_existing_flares(Path(probe))

    if df_existing is not None and len(df_existing) > 0:
        # Incremental: skip NCEI download, just append SWPC daily
        print("  Incremental mode: reusing existing NCEI data, appending SWPC daily")
        swpc_df = fetch_swpc_daily_flares()

        ncei_end = df_existing["peak_time"].max()
        # Remove any previous SWPC-sourced flares (satellite == GOES-18) to replace with fresh
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

        # Periodically do a full NCEI refresh (every 7 days, or if FULL_REBUILD env var set)
        import os
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

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "solar_flare_events.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Solar Flare Events (GOES X-ray)"
language:
  - en
description: "Individual solar flare detections from NOAA GOES-16 X-ray sensors (2017-present) with class, peak flux, and timing."
task_categories:
  - tabular-classification
  - time-series-forecasting
tags:
  - space
  - solar-flare
  - goes
  - space-weather
  - noaa
  - open-data
  - goes-16
  - x-ray
  - ncei
  - solar-activity
  - tabular-data
size_categories:
  - 10K<n<100K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/solar_flare_events.parquet
    default: true
---

# Solar Flare Events

*Part of the [Space Weather Datasets](https://huggingface.co/collections/juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70) collection on Hugging Face.*

![Update Solar Flares](https://github.com/juliensimon/space-datasets/actions/workflows/update-solar-flares.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['solar-flares']&label=updated&color=brightgreen)

Individual solar flare detections from GOES X-ray sensors, spanning **{date_min}** to
**{date_max}**. Currently **{n_total:,}** flare events from GOES-16, supplemented with
near-real-time detections from NOAA SWPC.

## Dataset description

Solar flares are sudden bursts of electromagnetic radiation from the Sun. They are
classified by peak X-ray flux in the 1-8 Angstrom band: **B** (< 10⁻⁶ W/m²),
**C** (10⁻⁶), **M** (10⁻⁵), and **X** (10⁻⁴ W/m²). M and X-class flares can
cause radio blackouts, GPS errors, satellite anomalies, and geomagnetic storms
that increase atmospheric drag on LEO satellites.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `start_time` | datetime | Flare start time (UTC) |
| `peak_time` | datetime | Flare peak time (UTC) |
| `end_time` | datetime | Flare end time (UTC) |
| `goes_class` | string | GOES class (e.g. "B3.7", "C1.6", "M5.1", "X1.0") |
| `goes_class_letter` | string | Class letter: B, C, M, or X |
| `peak_flux_wm2` | float64 | Peak X-ray flux in 1-8A band (W/m²) |
| `active_region` | int | NOAA active region number (when available) |
| `satellite` | string | Source satellite (GOES-16, GOES-18) |

## Quick stats

- **{n_total:,}** flare events ({date_min} to {date_max})
- **{n_c:,}** C-class, **{n_m:,}** M-class, **{n_x:,}** X-class flares
- Strongest flare: **{strongest_class}** on {strongest_date}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/solar-flare-events", split="train")
df = ds.to_pandas()

# M and X class flares only
major = df[df["goes_class_letter"].isin(["M", "X"])]

# Flare frequency over time
df["month"] = df["start_time"].dt.to_period("M")
monthly = df.groupby("month").size()

# X-class flares by active region
x_flares = df[df["goes_class_letter"] == "X"]
x_flares["active_region"].value_counts().head(10)

# Flare duration
df["duration_min"] = (df["end_time"] - df["start_time"]).dt.total_seconds() / 60
```

## Data sources

- **Bulk data**: [NCEI GOES-16 XRS Flare Summary](https://data.ngdc.noaa.gov/platforms/solar-space-observing-satellites/goes/goes16/l2/data/xrsf-l2-flsum_science/) (science-quality, 2017-present)
- **Daily supplement**: [NOAA SWPC Event Reports](https://www.swpc.noaa.gov/products/solar-and-geophysical-event-reports) (near-real-time)

Pre-2017 backfill from earlier GOES satellites is planned for a future update.

## Update schedule

Daily at 12:00 UTC via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [space-weather-indices](https://huggingface.co/datasets/juliensimon/space-weather-indices) — Daily Kp, Ap, F10.7 indices
- [space-track-satcat](https://huggingface.co/datasets/juliensimon/space-track-satcat) — Full NORAD satellite catalog
- [neo-close-approaches](https://huggingface.co/datasets/juliensimon/neo-close-approaches) — Near-Earth object approaches

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Citation

```bibtex
@dataset{{solar_flares,
  author = {{Simon, Julien}},
  title = {{Solar Flares}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/solar-flare-events}},
  note = {{Based on NOAA/SWPC GOES X-ray flux data}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update solar flare events: {n_total:,} flares"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    print("Done.")


if __name__ == "__main__":
    main()
