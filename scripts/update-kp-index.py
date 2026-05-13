#!/usr/bin/env python3
"""Fetch geomagnetic Kp index from NOAA SWPC and upload to HF.

Kp is a 3-hourly index (0-9) measuring geomagnetic disturbance. Incremental:
appends recent SWPC data to existing dataset.
"""

import time

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

HF_REPO = "juliensimon/geomagnetic-kp-index"

KP_URL = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"

# ── Column descriptions ───────────────────────────────────────────────
COLUMN_DESCRIPTIONS = {
    "datetime": "Start timestamp of the 3-hour observation window (UTC). Kp is reported at 00, 03, 06, 09, 12, 15, 18, and 21 UT each day — 8 readings per day.",
    "kp_value": "Planetary K-index (Kp), a quasi-logarithmic scale (0.0-9.0) measuring global geomagnetic disturbance. Derived from standardized magnetometer readings at up to 13 mid-latitude observatories worldwide. Values >=5 indicate a geomagnetic storm; >=7 indicate a severe storm capable of disrupting power grids and satellites.",
    "ap_running": "Running 24-hour average of the ap index, the linear-scale equivalent of Kp (range 0-400 nT). More mathematically convenient than Kp for averaging and modeling. Used as a required input to atmospheric drag models such as NRLMSISE-00 and JB2008.",
    "station_count": "Number of geomagnetic observatories that contributed data for this 3-hour window (maximum 13). Counts below ~5 reduce index reliability; null or low counts are common for historical records before 1960.",
    "storm_level": "NOAA geomagnetic storm scale: quiet (Kp<5), G1 (Kp=5, minor), G2 (Kp=6, moderate), G3 (Kp=7, strong), G4 (Kp=8, severe), G5 (Kp=9, extreme). G3+ events can cause HF radio blackouts, GPS degradation, and increased satellite drag.",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
3-hourly geomagnetic Kp index from NOAA SWPC, measuring planetary magnetic \
disturbance on a 0-9 scale. Updated daily, growing incrementally.

The Kp index is a quasi-logarithmic scale (0-9) that quantifies geomagnetic \
disturbance based on magnetometer readings from 13 ground stations worldwide. \
It is the basis for the NOAA G-scale storm classification: quiet (Kp 0-4), \
G1 minor (Kp=5), G2 moderate (Kp=6), G3 strong (Kp=7), G4 severe (Kp=8), \
G5 extreme (Kp=9).

The Kp index was introduced by Julius Bartels in 1949 and remains one of the most \
widely used geomagnetic activity measures in space physics and space operations. It \
is computed every 3 hours from the maximum deviation of the horizontal magnetic field \
component at each of 13 subauroral magnetometer stations, after removing the quiet-day \
baseline variation. The conversion from linear nanotesla deviations to the quasi-logarithmic \
K scale means that each unit step represents roughly a doubling of disturbance amplitude: \
K=5 corresponds to about 70 nT variation, while K=9 corresponds to over 500 nT.

Operationally, Kp is the primary input to the NOAA G-scale storm classification used by \
satellite operators, power grid managers, and aviation authorities. The associated Ap index \
(a linearized daily average derived from Kp) is a required input for NRLMSISE-00 and JB2008 \
thermospheric density models, which drive satellite drag computation. During a G3 storm \
(Kp=7), atmospheric drag at 400 km altitude can increase by a factor of 2-3, causing \
significant orbital decay for LEO assets including the ISS and Starlink satellites."""


def fetch_kp():
    """Fetch recent Kp data from NOAA SWPC (30-day rolling window, 3 retries)."""
    print("  Fetching Kp data from SWPC...")
    for attempt in range(3):
        try:
            resp = requests.get(KP_URL, timeout=30)
            resp.raise_for_status()
            break
        except requests.RequestException as exc:
            if attempt == 2:
                raise
            wait = 2 ** attempt
            print(f"  Retry {attempt + 1}/2 after {wait}s: {exc}")
            time.sleep(wait)
    raw = resp.json()

    # First row is header: ["time_tag", "Kp", "Kp_fraction", "a_running", "station_count"]
    header = raw[0]
    rows = raw[1:]
    df = pd.DataFrame(rows, columns=header)

    df["time_tag"] = pd.to_datetime(df["time_tag"])
    df = df.rename(columns={
        "time_tag": "datetime",
        "Kp": "kp_value",
        "a_running": "ap_running",
        "station_count": "station_count",
    })

    for col in ["kp_value", "ap_running", "station_count"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Storm classification
    df["storm_level"] = pd.cut(
        df["kp_value"],
        bins=[-float("inf"), 4, 5, 6, 7, 8, float("inf")],
        labels=["quiet", "G1-minor", "G2-moderate", "G3-strong", "G4-severe", "G5-extreme"],
    )

    # Drop undescribed columns (e.g. Kp_fraction)
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    df = df.sort_values("datetime").reset_index(drop=True)
    print(f"  {len(df):,} readings")
    return df


def main():
    print("Fetching Kp index from NOAA SWPC...")

    df_new = fetch_kp()

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Geomagnetic Kp Index (3-Hourly)",
        description=DESCRIPTION,
        tags=["space", "space-weather", "kp-index", "geomagnetic", "noaa",
              "magnetosphere", "aurora", "open-data", "tabular-data", "parquet"],
        source_url="https://www.swpc.noaa.gov/products/planetary-k-index",
        task_categories=["time-series-forecasting", "tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70",
        banner={"url": "https://images-assets.nasa.gov/image/iss072e159172/iss072e159172~medium.jpg",
                "alt": "Aurora borealis blankets the Earth, seen from the ISS",
                "credit": "NASA"},
        update_schedule="Daily at 15:30 UTC",
        related_datasets=[
            "juliensimon/dst-index",
            "juliensimon/solar-wind",
            "juliensimon/space-weather-indices",
            "juliensimon/donki-space-weather-events",
        ],
    ) as p:
        df_existing = p.download_existing("kp_index.parquet")

        if df_existing is not None and len(df_existing) > 0:
            df_existing["datetime"] = pd.to_datetime(df_existing["datetime"])
            df = p.merge(df_existing, df_new, dedup_on="datetime", sort_by="datetime")
            print(f"  Merged: {len(df):,} readings ({len(df) - len(df_existing):+,} net new)")
        else:
            df = df_new

        df = p.clean(df, numeric=["kp_value", "ap_running", "station_count"],
                     strings=["storm_level"])

        # Stats
        n = len(df)
        date_min = df["datetime"].min().strftime("%Y-%m-%d")
        date_max = df["datetime"].max().strftime("%Y-%m-%d")
        max_kp = df["kp_value"].max()
        n_storm = int((df["kp_value"] >= 5).sum())
        avg_kp = df["kp_value"].mean()

        quick_stats = f"""\
- **{n:,}** readings ({date_min} to {date_max})
- Average Kp: **{avg_kp:.1f}**, Maximum: **{max_kp:.1f}**
- **{n_storm}** storm-level readings (Kp >= 5)"""

        usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/geomagnetic-kp-index", split="train")
df = ds.to_pandas()

# Storm events
storms = df[df["kp_value"] >= 5]
print(f"{len(storms)} storm readings")

# Kp time series
import matplotlib.pyplot as plt

fig, ax = plt.subplots(figsize=(12, 4))
ax.plot(df["datetime"], df["kp_value"], linewidth=0.5)
ax.axhline(5, color="red", linestyle="--", alpha=0.5, label="Storm threshold (Kp>=5)")
ax.set_ylabel("Kp Index")
ax.set_title("Geomagnetic Kp Index")
ax.legend()
plt.tight_layout()
plt.show()

# Storm level distribution
df["storm_level"].value_counts().plot.bar()
plt.title("Kp Storm Level Distribution")
plt.show()
```"""

        p.publish(
            df,
            filename="kp_index.parquet",
            min_rows=50,
            expected_columns=["datetime", "kp_value", "storm_level"],
            critical_columns=["datetime", "kp_value"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Kp index: {n:,} readings",
        )
    print("Done.")


if __name__ == "__main__":
    main()
