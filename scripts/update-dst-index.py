#!/usr/bin/env python3
"""Fetch hourly Dst geomagnetic index from WDC Kyoto and upload to HF.

Source: World Data Center for Geomagnetism, Kyoto
https://wdc.kugi.kyoto-u.ac.jp/dstdir/
"""

import re
import sys
import time
from datetime import datetime

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

HF_REPO = "juliensimon/dst-index"

# URL patterns: final (1957-2020), provisional (2021-2025), realtime (recent)
DST_SOURCES = [
    ("final", "https://wdc.kugi.kyoto-u.ac.jp/dst_final/{ym6}/dst{ym4}.for.request", 1957, 2020),
    ("provisional", "https://wdc.kugi.kyoto-u.ac.jp/dst_provisional/{ym6}/dst{ym4}.for.request", 2021, 2025),
    ("realtime", "https://wdc.kugi.kyoto-u.ac.jp/dst_realtime/{ym6}/dst{ym4}.for.request", 2026, 2030),
]

DST_HTML_BASES = {
    "final": "https://wdc.kugi.kyoto-u.ac.jp/dst_final/{ym6}/index.html",
    "provisional": "https://wdc.kugi.kyoto-u.ac.jp/dst_provisional/{ym6}/index.html",
    "realtime": "https://wdc.kugi.kyoto-u.ac.jp/dst_realtime/{ym6}/index.html",
}

# ── Column descriptions ─────────────────────────────────────────────
COLUMN_DESCRIPTIONS = {
    "datetime": "Hour-averaged timestamp (UTC); Dst has been reported at 1-hour cadence since 1957",
    "dst_nt": "Disturbance Storm Time index in nT -- measures ring current injection at mid-latitudes; negative values indicate ring current enhancement; quiet: -20 to 0 nT, minor storm: -30 to -50 nT, moderate: -50 to -100 nT, intense: < -100 nT, extreme: < -250 nT",
    "daily_mean_nt": "24-hour mean Dst (nT) for the calendar day containing this record; smooths over short-duration spikes to represent overall storm level",
    "quality": "Data quality flag: 'final' (definitive WDC-processed values), 'provisional' (recent months, pending full processing), or 'realtime' (near-real-time, subject to revision)",
    "is_storm": "True if Dst <= -50 nT, the conventional threshold for a geomagnetic storm",
    "storm_intensity": "Derived storm severity: 'quiet' (> -50 nT), 'weak' (-50 to -100 nT), 'moderate' (-100 to -250 nT), 'intense' (-250 to -500 nT), 'super' (< -500 nT, extremely rare; Carrington 1859 estimated at -850 nT)",
}

DESCRIPTION = """\
Hourly Disturbance Storm Time (Dst) index from WDC Kyoto -- the standard measure \
of geomagnetic storm intensity since 1957.

The Dst index measures the strength of the ring current -- a toroidal electric current flowing \
in the magnetosphere. During geomagnetic storms, the ring current intensifies and Dst drops \
sharply (e.g. -100 to -500 nT for major storms). This index is the primary metric used by \
satellite operators and power grid managers to assess storm severity.

Dst complements the Kp/Ap indices by providing hourly resolution vs. 3-hourly/daily. \
The ring current is a toroidal band of 10-200 keV ions (primarily H+ and O+) trapped in the inner \
magnetosphere at geocentric distances of 3-8 Earth radii. During quiet times, the ring current \
produces a modest depression of the surface magnetic field (Dst around -20 to +10 nT). When a CME \
or high-speed stream arrives with sustained southward interplanetary magnetic field (Bz < 0), \
enhanced convection electric fields inject fresh particles from the plasma sheet into the ring \
current, causing Dst to plunge rapidly during the storm main phase.

Dst is derived from the horizontal field component (H) at four low-latitude magnetometer stations: \
Hermanus (South Africa), Kakioka (Japan), Honolulu (Hawaii), and San Juan (Puerto Rico). The hourly \
cadence resolves the storm main phase (typically 6-12 hours of rapid decrease) and the recovery phase \
(1-7 days of gradual return to baseline). The Dst index has direct applications in satellite operations: \
empirical models relate Dst excursions to increased satellite surface charging, single-event upset rates \
in electronics, and thermospheric density enhancements that accelerate orbital decay."""


# ── Custom fetch/parse functions (domain-specific) ───────────────────

def parse_dst_wdc(text, quality):
    """Parse WDC-format Dst data. Each line has 24 hourly values + daily mean."""
    records = []
    for line in text.splitlines():
        if not line.startswith("DST"):
            continue
        try:
            yy = int(line[3:5])
            mm = int(line[5:7])
            dd = int(line[8:10])
            year = 1900 + yy if yy >= 57 else 2000 + yy

            values_str = line[20:]
            hourly = []
            for i in range(24):
                val_str = values_str[i * 4:(i + 1) * 4].strip()
                if val_str == "9999" or val_str == "":
                    hourly.append(None)
                else:
                    hourly.append(int(val_str))

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


def parse_dst_html(html, year, month, quality):
    """Parse Dst data from WDC Kyoto HTML index page (<pre class="data"> block)."""
    m = re.search(r'<pre class="data">(.*?)</pre>', html, re.DOTALL)
    if not m:
        return []
    records = []
    for line in m.group(1).splitlines():
        line = line.rstrip()
        if not line or not line.strip():
            continue
        stripped = line.strip()
        if not stripped[0].isdigit():
            continue
        parts = line.split()
        if len(parts) < 25:
            continue
        try:
            dd = int(parts[0])
            if dd < 1 or dd > 31:
                continue
            hourly = []
            for i in range(1, 25):
                val = int(parts[i])
                hourly.append(None if val == 9999 else val)
            for hour, dst_val in enumerate(hourly):
                records.append({
                    "datetime": datetime(year, month, dd, hour),
                    "dst_nt": dst_val,
                    "daily_mean_nt": None,
                    "quality": quality,
                })
        except (ValueError, IndexError):
            continue
    return records


def fetch_month(url_template, year, month, quality, retries=3):
    """Fetch a single month from WDC Kyoto with retries.

    Tries .for.request file first, falls back to HTML index page.
    """
    ym6 = f"{year}{month:02d}"
    ym4 = f"{year % 100:02d}{month:02d}"
    url = url_template.format(ym6=ym6, ym4=ym4)
    for attempt in range(retries):
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code == 200 and resp.text.startswith("DST"):
                return parse_dst_wdc(resp.text, quality)
            if resp.status_code == 404:
                break
        except Exception:
            pass
        if attempt < retries - 1:
            time.sleep(2 ** attempt)

    html_template = DST_HTML_BASES.get(quality)
    if html_template:
        html_url = html_template.format(ym6=ym6)
        for attempt in range(retries):
            try:
                resp = requests.get(html_url, timeout=15)
                if resp.status_code == 200:
                    records = parse_dst_html(resp.text, year, month, quality)
                    if records:
                        return records
                if resp.status_code == 404:
                    return []
            except Exception:
                pass
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    return []


def fetch_months(url_template, year, months, quality):
    """Fetch specific months from WDC Kyoto."""
    records = []
    for month in months:
        records.extend(fetch_month(url_template, year, month, quality))
    return records


# ── Main ─────────────────────────────────────────────────────────────

def main():
    print("Fetching Dst index from WDC Kyoto...")
    now = datetime.utcnow()

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Dst Geomagnetic Storm Index (Hourly)",
        description=DESCRIPTION,
        tags=["space", "space-weather", "geomagnetic", "dst-index", "wdc-kyoto",
              "ring-current", "magnetosphere", "open-data", "tabular-data", "parquet"],
        source_url="https://wdc.kugi.kyoto-u.ac.jp/dstdir/",
        task_categories=["time-series-forecasting", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70",
        banner={"url": "https://images-assets.nasa.gov/image/iss072e159172/iss072e159172~medium.jpg",
                "alt": "Aurora borealis blankets the Earth, seen from the ISS",
                "credit": "NASA"},
        update_schedule="Daily at 13:00 UTC",
        related_datasets=[
            "juliensimon/space-weather-indices",
            "juliensimon/solar-flare-events",
            "juliensimon/geomagnetic-kp-index",
        ],
    ) as p:
        # Try incremental
        df_existing = p.download_existing("dst_index.parquet")

        if df_existing is not None and len(df_existing) >= 400_000:
            df_existing["datetime"] = pd.to_datetime(df_existing["datetime"])
            print("  Incremental mode: fetching recent months only")
            new_records = []

            # Realtime: all months of current year
            rt_template = DST_SOURCES[2][1]
            rt_months = list(range(1, now.month + 1))
            new_records.extend(fetch_months(rt_template, now.year, rt_months, "realtime"))
            print(f"  Realtime {now.year}: {len(new_records)} records ({len(rt_months)} months)")

            # Provisional: re-fetch last 2 months of previous year (corrections)
            prov_template = DST_SOURCES[1][1]
            prov_year = now.year - 1
            prov_months = [11, 12]
            prov_records = fetch_months(prov_template, prov_year, prov_months, "provisional")
            new_records.extend(prov_records)
            print(f"  Provisional {prov_year} (Nov-Dec): {len(prov_records)} records")

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
            print("  Full rebuild from 1957...")
            all_records = []
            for quality, url_template, start_year, end_year in DST_SOURCES:
                actual_end = min(end_year, now.year)
                for year in range(start_year, actual_end + 1):
                    end_month = now.month if year == now.year else 12
                    months = list(range(1, end_month + 1))
                    all_records.extend(fetch_months(url_template, year, months, quality))
                    print(f"  {quality} {year}: fetched")
            df = pd.DataFrame(all_records)

        if df.empty:
            print("::error::No Dst data retrieved")
            sys.exit(1)

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

        df = p.clean(df, numeric=["dst_nt", "daily_mean_nt"])

        # Keep only described columns
        df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

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

        quick_stats = f"""\
- **{n_total:,}** hourly readings ({date_min} to {date_max})
- **{n_storm_hours:,}** storm hours (Dst <= -50 nT)
- Deepest storm: **{min_dst} nT** on {min_dst_time}
- Data quality: {n_final:,} final, {n_provisional:,} provisional, {n_realtime:,} realtime"""

        usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/dst-index", split="train")
df = ds.to_pandas()

# Major storms (Dst < -100)
major = df[df["dst_nt"] < -100].sort_values("dst_nt")

# Storm frequency by year
import matplotlib.pyplot as plt

df["year"] = df["datetime"].dt.year
storms_per_year = df[df["is_storm"]].groupby("year").size()
storms_per_year.plot.bar(figsize=(12, 4))
plt.title("Geomagnetic Storm Hours per Year")
plt.ylabel("Hours with Dst <= -50 nT")
plt.tight_layout()
plt.show()

# Dst time series around a specific storm
storm = df[(df["datetime"] >= "2024-05-10") & (df["datetime"] <= "2024-05-15")]
storm.plot(x="datetime", y="dst_nt", title="May 2024 Storm")
plt.show()
```"""

        p.publish(
            df,
            filename="dst_index.parquet",
            min_rows=400_000,
            expected_columns=["datetime", "dst_nt", "quality"],
            critical_columns=["datetime", "dst_nt"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Dst index: {n_total:,} hourly readings",
        )
    print("Done.")


if __name__ == "__main__":
    main()
