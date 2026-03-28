#!/usr/bin/env python3
"""Fetch hourly neutron monitor cosmic ray data from NMDB and upload to HF."""

import subprocess
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset

HF_REPO = "juliensimon/neutron-monitor-cosmic-rays"
PARQUET_NAME = "neutron_monitor.parquet"

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
    # Add stations as repeated params
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
    # Find the header line with station names (first non-comment, non-empty line)
    lines = text.splitlines()
    header_line = None
    data_start = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#") or stripped == "":
            continue
        # First non-comment line: check if it looks like a header (no semicolons)
        if ";" not in stripped:
            header_line = stripped
            data_start = i + 1
            break
        else:
            # No header line, data starts here
            data_start = i
            break

    if data_start is None:
        return pd.DataFrame()

    # Extract station names from header
    if header_line:
        station_codes = header_line.split()
    else:
        # Fallback: use our station list
        station_codes = list(STATIONS.keys())

    # Parse data lines
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


def load_existing(tmp_dir):
    """Download existing parquet from HF. Returns DataFrame or None."""
    parquet_path = tmp_dir / "data" / PARQUET_NAME
    try:
        subprocess.run(
            ["hf", "download", HF_REPO, f"data/{PARQUET_NAME}",
             "--repo-type", "dataset", "--local-dir", str(tmp_dir)],
            check=True, capture_output=True, timeout=60,
        )
        if parquet_path.exists():
            df = pd.read_parquet(parquet_path)
            df["datetime"] = pd.to_datetime(df["datetime"])
            print(f"  Loaded existing: {len(df):,} records")
            return df
    except Exception as e:
        print(f"  Could not load existing ({e}), doing full rebuild")
    return None


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


def main():
    print("Fetching neutron monitor cosmic ray data from NMDB...")
    now = datetime.utcnow()

    # Try incremental
    with tempfile.TemporaryDirectory() as probe:
        df_existing = load_existing(Path(probe))

    if df_existing is not None and len(df_existing) > 0:
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
        print("ERROR: No data fetched")
        raise SystemExit(1)

    # Clean up
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values(["datetime", "station"]).reset_index(drop=True)
    df = df.drop_duplicates(subset=["datetime", "station"], keep="last")

    # Remove future rows
    df = df[df["datetime"] <= pd.Timestamp.now(tz=None)]

    # Add station metadata
    df["station_name"] = df["station"].map(STATIONS)

    # Derived columns: daily mean per station
    df["date"] = df["datetime"].dt.date.astype(str)
    daily_mean = df.groupby(["date", "station"])["count_rate"].transform("mean")
    df["daily_mean_count_rate"] = daily_mean.round(3)

    # Percentage deviation from station daily mean
    df["pct_deviation"] = (
        ((df["count_rate"] - df["daily_mean_count_rate"]) / df["daily_mean_count_rate"] * 100)
        .round(3)
    )

    # Drop helper column
    df = df.drop(columns=["date"])

    # Validate
    n_total = len(df)
    check_dataset(
        df,
        dataset_name="neutron-monitor",
        min_rows=400_000,
        expected_columns=["datetime", "station", "count_rate", "station_name",
                          "daily_mean_count_rate", "pct_deviation"],
        critical_columns=["count_rate"],
        max_null_pct=0.10,
            incremental=True)

    # Stats for README
    date_min = df["datetime"].min().strftime("%Y-%m-%d")
    date_max = df["datetime"].max().strftime("%Y-%m-%d")
    n_stations = df["station"].nunique()
    station_list = ", ".join(sorted(df["station"].unique()))
    mean_rate = df["count_rate"].mean()
    min_rate = df["count_rate"].min()
    min_rate_time = df.loc[df["count_rate"].idxmin(), "datetime"].strftime("%Y-%m-%d %H:%M")
    min_rate_station = df.loc[df["count_rate"].idxmin(), "station"]
    null_pct = df["count_rate"].isna().mean() * 100

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / PARQUET_NAME
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet, {n_total:,} records")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Neutron Monitor Cosmic Ray Intensity (Hourly)"
language:
  - en
description: "Hourly cosmic ray intensity from the worldwide neutron monitor network (NMDB) — {n_stations} stations from {date_min} to {date_max}."
task_categories:
  - time-series-forecasting
  - tabular-regression
tags:
  - space
  - cosmic-rays
  - neutron-monitor
  - space-weather
  - open-data
  - tabular-data
  - parquet
size_categories:
  - 100K<n<1M
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/{PARQUET_NAME}
    default: true
---

# Neutron Monitor Cosmic Ray Intensity (Hourly)

*Part of the [Space Weather Datasets](https://huggingface.co/collections/juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70) collection on Hugging Face.*

![Update Neutron Monitor](https://github.com/juliensimon/space-datasets/actions/workflows/update-neutron-monitor.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['neutron-monitor']&label=updated&color=brightgreen)

Hourly cosmic ray intensity measurements from the [Neutron Monitor Database (NMDB)](https://www.nmdb.eu/),
the worldwide network of ground-based cosmic ray detectors. Covers **{date_min}** to **{date_max}**
with **{n_total:,}** hourly readings across **{n_stations} stations**.

## Dataset description

Neutron monitors detect secondary neutrons produced when galactic cosmic rays interact with Earth's
atmosphere. The count rate is a proxy for cosmic ray intensity at Earth and is modulated by solar
activity (11-year cycle), transient solar events (Forbush decreases), and geomagnetic conditions.

Higher-latitude and higher-altitude stations have lower geomagnetic cutoff rigidity, making them
more sensitive to lower-energy cosmic rays. This dataset includes stations spanning a range of
latitudes and altitudes for cross-comparison.

## Stations

| Code | Location |
|------|----------|
| OULU | Oulu, Finland |
| NEWK | Newark, USA |
| JUNG | Jungfraujoch, Switzerland |
| ROME | Rome, Italy |
| THUL | Thule, Greenland |
| APTY | Apatity, Russia |

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `datetime` | datetime | Observation time (UTC, hourly) |
| `station` | string | Station code (e.g. OULU, JUNG) |
| `count_rate` | float | Corrected count rate (pressure-corrected, efficiency-corrected) |
| `station_name` | string | Station name and location |
| `daily_mean_count_rate` | float | Daily mean count rate for this station |
| `pct_deviation` | float | Hourly deviation from daily mean (%) |

## Quick stats

- **{n_total:,}** hourly readings ({date_min} to {date_max})
- **{n_stations}** stations: {station_list}
- Mean count rate: **{mean_rate:.1f}**
- Minimum count rate: **{min_rate:.1f}** ({min_rate_station}, {min_rate_time})
- Missing values: {null_pct:.1f}%

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/neutron-monitor-cosmic-rays", split="train")
df = ds.to_pandas()

# Compare stations
import pandas as pd
pivot = df.pivot_table(index="datetime", columns="station", values="count_rate")

# Detect Forbush decreases (sudden drops in cosmic ray intensity)
oulu = df[df["station"] == "OULU"].set_index("datetime")["count_rate"]
daily = oulu.resample("1D").mean()
forbush = daily[daily.pct_change() < -0.03]  # >3% daily drop

# Solar cycle modulation
df["year"] = df["datetime"].dt.year
yearly = df.groupby(["year", "station"])["count_rate"].mean().unstack()
```

## Data source

[Neutron Monitor Database (NMDB)](https://www.nmdb.eu/) — founded under the EU's FP7 programme
(contract no. 213007). Data are the property of individual station PIs and are free for
non-commercial use.

## Update schedule

Daily at 14:30 UTC via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [dst-index](https://huggingface.co/datasets/juliensimon/dst-index) — Dst geomagnetic storm index
- [space-weather-indices](https://huggingface.co/datasets/juliensimon/space-weather-indices) — Daily Kp, Ap, F10.7
- [solar-flare-events](https://huggingface.co/datasets/juliensimon/solar-flare-events) — Individual flare detections

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/neutron-monitor-cosmic-rays) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

If you use this dataset, please cite:

```bibtex
@dataset{{neutron_monitor_cosmic_rays,
  author = {{Simon, Julien}},
  title = {{Neutron Monitor Cosmic Ray Intensity (Hourly)}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/neutron-monitor-cosmic-rays}}
}}
```

### Data source

[NMDB](https://www.nmdb.eu/) — Neutron Monitor Database

## License

MIT (pipeline code). Neutron monitor data: free for non-commercial use per NMDB/individual station terms.
""")

        print("Uploading to HF...")
        commit_msg = f"Update neutron monitor: {n_total:,} hourly readings"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    print(f"rows={n_total}")
    print("Done.")


if __name__ == "__main__":
    main()
