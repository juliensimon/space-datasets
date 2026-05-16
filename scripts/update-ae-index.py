#!/usr/bin/env python3
"""Fetch hourly AE/AU/AL/AO auroral electrojet indices from WDC Kyoto and upload to HF."""

import re
import sys
import time
from datetime import datetime, timezone

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

# Config
AE_DATA_DIR = "https://wdc.kugi.kyoto-u.ac.jp/ae_realtime/data_dir"
AE_INDICES = ["ae", "al", "ao", "au"]
AE_START_YEAR = 2021
HF_REPO = "juliensimon/auroral-electrojet-index"


# ── Custom WDC parsers (domain-specific, not library-replaceable) ────

def parse_ae_data_file(text, index_name):
    """Parse a WDC minute-resolution AE data file.

    Format: each line is one hour with 60 minute values + 1 hourly mean.
    The first ~14 chars are header (index code + date + hour), followed by
    a quality tag and 61 numeric values (60 minutes + hourly mean).
    We extract the hourly mean (last value on each line).
    """
    records = []
    col_map = {"ae": "ae_index", "au": "au_index",
               "al": "al_index", "ao": "ao_index"}
    col = col_map.get(index_name)
    if not col:
        return []

    for line in text.splitlines():
        line = line.rstrip()
        if len(line) < 40:
            continue

        try:
            # Use regex to find date pattern YYMMDDEHHXX in first 30 chars
            # Works regardless of whether fields are space-separated or run together
            m = re.search(r'(\d{2})(\d{2})(\d{2})E(\d{2})', line[:30])
            if not m:
                continue

            yy = int(m.group(1))
            mm = int(m.group(2))
            dd = int(m.group(3))
            hh = int(m.group(4))
            year = 1900 + yy if yy >= 57 else 2000 + yy

            # Validate date components
            if not (1 <= mm <= 12 and 1 <= dd <= 31 and 0 <= hh <= 23):
                continue

            # The hourly mean is the last numeric value on the line
            parts = line.split()
            mean_str = parts[-1].strip()
            if mean_str in ("9999", "99999", ""):
                val = None
            else:
                val = int(mean_str)

            records.append({
                "datetime": datetime(year, mm, dd, hh),
                col: val,
            })
        except (ValueError, IndexError):
            continue

    return records


def fetch_day(year, month, day):
    """Fetch all 4 AE indices for a single day from data_dir."""
    records = {}  # keyed by (year, month, day, hour)
    yy = year % 100
    date_str = f"{yy:02d}{month:02d}{day:02d}"

    for idx in AE_INDICES:
        url = f"{AE_DATA_DIR}/{year}/{month:02d}/{day:02d}/{idx}{date_str}"
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code != 200:
                continue
            parsed = parse_ae_data_file(resp.text, idx)
            for rec in parsed:
                key = (rec["datetime"].year, rec["datetime"].month,
                       rec["datetime"].day, rec["datetime"].hour)
                if key not in records:
                    records[key] = {
                        "datetime": rec["datetime"],
                        "ae_index": None, "au_index": None,
                        "al_index": None, "ao_index": None,
                        "quality": "realtime",
                    }
                # Merge index value
                for col in ("ae_index", "au_index", "al_index", "ao_index"):
                    if col in rec and rec[col] is not None:
                        records[key][col] = rec[col]
        except Exception:
            continue

    return list(records.values())


def list_days(year, month):
    """List available day directories for a year/month."""
    url = f"{AE_DATA_DIR}/{year}/{month:02d}/"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return []
        days = re.findall(r'href="(\d{2})/"', resp.text)
        return [int(d) for d in sorted(set(days))]
    except Exception:
        return []


# ── Column descriptions ──────────────────────────────────────
COLUMN_DESCRIPTIONS = {
    "datetime": "Timestamp of 1-minute measurement averaged to hourly cadence (UTC); coverage starts 2021",
    "ae_index": "Auroral Electrojet index in nT — range of H-component variation (AU - AL); quiet: <200, substorm: >300, active: >500 nT",
    "au_index": "Auroral Upper index in nT — eastward electrojet intensity; typically 0-1000 nT",
    "al_index": "Auroral Lower index in nT — westward electrojet intensity; typically 0 to -2000 nT; strongly negative = substorm",
    "ao_index": "Auroral Overall index in nT — (AU + AL) / 2; substorm activity proxy",
    "quality": "Data quality: 'provisional' (pending processing) or 'realtime' (near-real-time, subject to revision)",
    "is_active": "True if AE >= 500 nT, indicating active auroral substorm conditions",
    "activity_level": "Derived category: quiet (<100), moderate (100-300), active (300-500), minor_storm (500-1000), major_storm (>1000 nT)",
}

DESCRIPTION = """\
Hourly Auroral Electrojet indices from WDC Kyoto — measures auroral zone magnetic activity driven by magnetospheric substorms.

The AE index measures auroral zone magnetic activity caused by enhanced ionospheric currents flowing in the auroral oval. It is derived from geomagnetic variations at 10-13 stations along the auroral zone. The AE family includes four indices:

- **AE** (Auroral Electrojet): overall auroral activity (AU - AL)
- **AU** (Auroral Upper): measures eastward electrojet intensity
- **AL** (Auroral Lower): measures westward electrojet intensity
- **AO** (Auroral Origin): baseline level (AU + AL) / 2

AE complements the Dst index (ring current) by specifically tracking substorm-driven auroral activity, which is critical for high-latitude communications and power grids."""


def main():
    print("Fetching AE index from WDC Kyoto...")
    now = datetime.now(timezone.utc)

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Auroral Electrojet (AE) Index",
        description=DESCRIPTION,
        tags=["space", "geomagnetic", "auroral-electrojet", "ae-index", "space-weather",
              "kyoto", "open-data", "tabular-data", "parquet"],
        source_url="https://wdc.kugi.kyoto-u.ac.jp/aeasy/",
        task_categories=["time-series-forecasting", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70",
        banner={"url": "https://images-assets.nasa.gov/image/iss072e159172/iss072e159172~medium.jpg",
                "alt": "Aurora borealis blankets the Earth, seen from the ISS",
                "credit": "NASA"},
        update_schedule="Daily at 19:00 UTC",
        related_datasets=["juliensimon/dst-index", "juliensimon/space-weather-indices", "juliensimon/geomagnetic-kp-index"],
    ) as p:
        # Try incremental
        df_existing = p.download_existing("ae_index.parquet")

        if df_existing is not None and len(df_existing) > 0:
            df_existing["datetime"] = pd.to_datetime(df_existing["datetime"])
            print("  Incremental mode: fetching recent data only")
            new_records = []

            for day in list_days(now.year, now.month):
                new_records.extend(fetch_day(now.year, now.month, day))
            print(f"  {now.year}/{now.month:02d}: {len(new_records)} records")

            prev_year, prev_month = (now.year, now.month - 1) if now.month > 1 else (now.year - 1, 12)
            prev_count = len(new_records)
            for day in list_days(prev_year, prev_month):
                new_records.extend(fetch_day(prev_year, prev_month, day))
            print(f"  {prev_year}/{prev_month:02d}: {len(new_records) - prev_count} records")

            df_new = pd.DataFrame(new_records)
            if not df_new.empty:
                df_new["datetime"] = pd.to_datetime(df_new["datetime"])
                cutoff = df_new["datetime"].min()
                df_kept = df_existing[df_existing["datetime"] < cutoff]
                df = pd.concat([df_kept, df_new], ignore_index=True)
                print(f"  Merged: {len(df):,} records (kept {len(df_kept):,} + {len(df_new):,} new)")
            else:
                df = df_existing
                print("  No new data")
        else:
            # Full rebuild
            print(f"  Full rebuild from {AE_START_YEAR}...")
            all_records = []
            for year in range(AE_START_YEAR, now.year + 1):
                end_month = now.month if year == now.year else 12
                for month in range(1, end_month + 1):
                    days = list_days(year, month)
                    for day in days:
                        all_records.extend(fetch_day(year, month, day))
                    time.sleep(0.3)
                print(f"  {year}: {len(all_records):,} records so far")
            df = pd.DataFrame(all_records)

            # WDC Kyoto may be unreachable (IP allowlist). Fall back to HF copy.
            if df.empty:
                print("  WDC returned no data — trying HF existing dataset as fallback...")
                df_fallback = p.download_existing("ae_index.parquet")
                if df_fallback is not None and len(df_fallback) > 0:
                    df_fallback["datetime"] = pd.to_datetime(df_fallback["datetime"])
                    df = df_fallback
                    print(f"  Using {len(df):,} rows from HF as fallback (WDC unreachable)")

        if df.empty:
            print("::error::No AE data retrieved")
            sys.exit(1)

        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.sort_values("datetime").reset_index(drop=True)
        df = df[df["datetime"] <= pd.Timestamp.now()]

        # Derived columns
        df = p.clean(df, numeric=["ae_index", "au_index", "al_index", "ao_index"])
        if "ae_index" in df.columns:
            df["is_active"] = df["ae_index"] >= 500
            df["activity_level"] = pd.cut(
                df["ae_index"],
                bins=[-float("inf"), 100, 300, 500, 1000, float("inf")],
                labels=["quiet", "moderate", "active", "minor_storm", "major_storm"],
            )

        # Stats
        n_total = len(df)
        date_min = df["datetime"].min().strftime("%Y-%m-%d")
        date_max = df["datetime"].max().strftime("%Y-%m-%d")
        n_active = int(df["is_active"].sum()) if "is_active" in df.columns else 0
        max_ae = df["ae_index"].max() if "ae_index" in df.columns else None

        quick_stats = f"""\
- **{n_total:,}** hourly readings ({date_min} to {date_max})
- **{n_active:,}** active hours (AE >= 500 nT)
- Peak AE: **{max_ae} nT**"""

        usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/auroral-electrojet-index", split="train")
df = ds.to_pandas()

# AE/AL time series during a geomagnetic storm
import matplotlib.pyplot as plt

storm = df[(df["datetime"] >= "2024-05-10") & (df["datetime"] <= "2024-05-15")]
fig, ax = plt.subplots(figsize=(12, 4))
ax.plot(storm["datetime"], storm["ae_index"], label="AE", color="red")
ax.plot(storm["datetime"], storm["al_index"], label="AL", color="blue")
ax.axhline(500, color="gray", linestyle="--", alpha=0.5, label="Active threshold")
ax.legend()
ax.set_ylabel("nT")
ax.set_title("Auroral Electrojet during May 2024 Geomagnetic Storm")
plt.tight_layout()
plt.show()

# Activity distribution
df["activity_level"].value_counts().plot.bar()
plt.title("AE Activity Level Distribution")
plt.show()
```"""

        # Drop entirely-null optional columns (ao_index is not always
        # available in WDC Kyoto realtime; prevents hard-fail in check_dataset)
        all_null_cols = [c for c in df.columns if df[c].isna().all()]
        if all_null_cols:
            print(f"  Dropping entirely-null columns: {all_null_cols}")
            df = df.drop(columns=all_null_cols)

        p.publish(
            df,
            filename="ae_index.parquet",
            min_rows=30_000,
            expected_columns=["datetime", "ae_index"],
            critical_columns=["datetime", "ae_index"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update AE index: {n_total:,} hourly readings",
        )
    print("Done.")


if __name__ == "__main__":
    main()
