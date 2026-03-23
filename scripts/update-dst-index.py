#!/usr/bin/env python3
"""Fetch hourly Dst geomagnetic index from WDC Kyoto and upload to HF."""

import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests


# URL patterns: final (1957-2020), provisional (2021-2025), realtime (recent)
DST_SOURCES = [
    ("final", "https://wdc.kugi.kyoto-u.ac.jp/dst_final/{ym6}/dst{ym4}.for.request", 1957, 2020),
    ("provisional", "https://wdc.kugi.kyoto-u.ac.jp/dst_provisional/{ym6}/dst{ym4}.for.request", 2021, 2025),
    ("realtime", "https://wdc.kugi.kyoto-u.ac.jp/dst_realtime/{ym6}/dst{ym4}.for.request", 2026, 2030),
]
HF_REPO = "juliensimon/dst-index"


def parse_dst_wdc(text, quality):
    """Parse WDC-format Dst data. Each line has 24 hourly values + daily mean."""
    records = []
    for line in text.splitlines():
        if not line.startswith("DST"):
            continue
        # Format: DST YYMM*DD QQ X VVV 0 h0 h1 h2 ... h23 mean
        # Positions are fixed-width: values start at col 20, each 4 chars wide
        try:
            yy = int(line[3:5])
            mm = int(line[5:7])
            dd = int(line[8:10])
            # Handle century
            year = 1900 + yy if yy >= 57 else 2000 + yy

            # 24 hourly values start at position 20, 4 chars each
            # Then daily mean at position 116, 4 chars
            values_str = line[20:]
            hourly = []
            for i in range(24):
                val_str = values_str[i * 4:(i + 1) * 4].strip()
                if val_str == "9999" or val_str == "":
                    hourly.append(None)
                else:
                    hourly.append(int(val_str))

            # Daily mean is the last value (position 24)
            mean_str = values_str[96:100].strip()
            daily_mean = int(mean_str) if mean_str and mean_str != "9999" else None

            for hour, dst_val in enumerate(hourly):
                records.append({
                    "datetime": datetime(year, mm, dd, hour),
                    "dst_nt": dst_val,
                    "daily_mean_nt": daily_mean if hour == 0 else None,
                    "quality": quality,
                })
        except (ValueError, IndexError):
            continue
    return records


def main():
    print("Fetching Dst index from WDC Kyoto...")
    all_records = []
    now = datetime.utcnow()

    for quality, url_template, start_year, end_year in DST_SOURCES:
        actual_end = min(end_year, now.year)
        for year in range(start_year, actual_end + 1):
            end_month = now.month if year == now.year else 12
            for month in range(1, end_month + 1):
                ym6 = f"{year}{month:02d}"
                ym4 = f"{year % 100:02d}{month:02d}"
                url = url_template.format(ym6=ym6, ym4=ym4)
                try:
                    resp = requests.get(url, timeout=15)
                    if resp.status_code == 200 and resp.text.startswith("DST"):
                        records = parse_dst_wdc(resp.text, quality)
                        all_records.extend(records)
                except Exception:
                    pass  # Skip months with no data
            print(f"  {quality} {year}: fetched")

    df = pd.DataFrame(all_records)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values("datetime").reset_index(drop=True)

    # Remove future/empty rows
    df = df[df["datetime"] <= pd.Timestamp.now()]

    # Propagate daily mean to all hours of that day
    df["daily_mean_nt"] = df.groupby(df["datetime"].dt.date)["daily_mean_nt"].transform("first")

    # Derived columns
    df["is_storm"] = df["dst_nt"] <= -50
    df["storm_intensity"] = pd.cut(
        df["dst_nt"],
        bins=[-float("inf"), -500, -250, -100, -50, float("inf")],
        labels=["super", "intense", "moderate", "weak", "quiet"],
    )

    print(f"  {len(df):,} hourly records")

    # Stats
    n_total = len(df)
    date_min = df["datetime"].min().strftime("%Y-%m-%d")
    date_max = df["datetime"].max().strftime("%Y-%m-%d")
    n_storm_hours = int(df["is_storm"].sum())
    min_dst = df["dst_nt"].min()
    min_dst_time = df.loc[df["dst_nt"].idxmin(), "datetime"].strftime("%Y-%m-%d %H:%M")
    n_final = int((df["quality"] == "final").sum())
    n_provisional = int((df["quality"] == "provisional").sum())
    n_realtime = int((df["quality"] == "realtime").sum())

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "dst_index.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Dst Geomagnetic Storm Index (Hourly)"
language:
  - en
description: "Hourly Disturbance Storm Time (Dst) index from WDC Kyoto — the standard measure of geomagnetic storm intensity since 1957."
task_categories:
  - time-series-forecasting
  - tabular-regression
tags:
  - space
  - space-weather
  - geomagnetic
  - dst-index
  - wdc-kyoto
  - ring-current
  - magnetosphere
  - open-data
size_categories:
  - 100K<n<1M
---

# Dst Geomagnetic Index (Hourly)

![Update Dst Index](https://github.com/juliensimon/space-datasets/actions/workflows/update-dst-index.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['dst-index']&label=updated&color=brightgreen)

Hourly Disturbance Storm Time (Dst) index from [WDC Kyoto](https://wdc.kugi.kyoto-u.ac.jp/dstdir/),
the standard measure of geomagnetic storm intensity. Covers **{date_min}** to **{date_max}**
with **{n_total:,}** hourly readings.

## Dataset description

The Dst index measures the strength of the ring current — a toroidal electric current flowing
in the magnetosphere. During geomagnetic storms, the ring current intensifies and Dst drops
sharply (e.g. -100 to -500 nT for major storms). This index is the primary metric used by
satellite operators and power grid managers to assess storm severity.

Dst complements the Kp/Ap indices (available in our
[space-weather-indices](https://huggingface.co/datasets/juliensimon/space-weather-indices) dataset)
by providing **hourly** resolution vs. 3-hourly/daily.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `datetime` | datetime | Observation time (UTC, hourly) |
| `dst_nt` | int | Dst value in nanotesla (nT). Negative = disturbed. |
| `daily_mean_nt` | int | Daily mean Dst (nT) |
| `quality` | string | Data quality: "final" (definitive), "provisional", or "realtime" |
| `is_storm` | bool | True if Dst <= -50 nT |
| `storm_intensity` | string | "quiet" (> -50), "weak" (-50 to -100), "moderate" (-100 to -250), "intense" (-250 to -500), "super" (< -500) |

## Quick stats

- **{n_total:,}** hourly readings ({date_min} to {date_max})
- **{n_storm_hours:,}** storm hours (Dst <= -50 nT)
- Deepest storm: **{min_dst} nT** on {min_dst_time}
- Data quality: {n_final:,} final, {n_provisional:,} provisional, {n_realtime:,} realtime

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/dst-index", split="train")
df = ds.to_pandas()

# Major storms (Dst < -100)
major = df[df["dst_nt"] < -100].sort_values("dst_nt")

# Storm frequency by year
df["year"] = df["datetime"].dt.year
storms_per_year = df[df["is_storm"]].groupby("year").size()

# Dst time series around a specific storm
storm = df[(df["datetime"] >= "2024-05-10") & (df["datetime"] <= "2024-05-15")]

# Compare with Kp index (load space-weather-indices dataset)
# Both datasets can be joined on date for cross-analysis
```

## Data source

[WDC for Geomagnetism, Kyoto](https://wdc.kugi.kyoto-u.ac.jp/dstdir/). Three quality tiers:
- **Final** (1957-2020): Definitive, quality-checked values
- **Provisional** (2021-2025): Visually screened but not final
- **Real-time** (recent): Quicklook values, may be revised

## Update schedule

Daily at 13:00 UTC via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [space-weather-indices](https://huggingface.co/datasets/juliensimon/space-weather-indices) — Daily Kp, Ap, F10.7 indices
- [solar-flare-events](https://huggingface.co/datasets/juliensimon/solar-flare-events) — Individual flare detections
- [space-track-tle-history](https://huggingface.co/datasets/juliensimon/space-track-tle-history) — Orbital element history (for drag analysis)

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Citation

If you use this dataset, please cite:

```bibtex
@dataset{{dst_index,
  author = {{Simon, Julien}},
  title = {{Dst Geomagnetic Storm Index (Hourly)}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/dst-index}}
}}
```

### Data source

[WDC for Geomagnetism, Kyoto](https://wdc.kugi.kyoto-u.ac.jp/dstdir/)

## License

MIT (pipeline code). Dst data: free for non-commercial use per WDC Kyoto terms.
""")

        print("Uploading to HF...")
        commit_msg = f"Update Dst index: {n_total:,} hourly readings"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    print("Done.")


if __name__ == "__main__":
    main()
