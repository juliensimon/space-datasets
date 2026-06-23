#!/usr/bin/env python3
"""Fetch the NOAA SWPC OVATION aurora nowcast and upload aggregates to HF.

OVATION Prime publishes a global grid (~65k cells) giving the probability of
visible aurora over the next ~30 minutes. Storing every cell daily would add
tens of millions of rows per year, so this pipeline reduces each snapshot to a
handful of per-hemisphere activity aggregates, producing a compact daily-growing
auroral-activity time series. Incremental: one row per snapshot, deduped on the
observation time.
"""

import time

import numpy as np
import pandas as pd
import requests

from hf_dataset_utils import Pipeline

HF_REPO = "juliensimon/aurora-forecast"

OVATION_URL = "https://services.swpc.noaa.gov/json/ovation_aurora_latest.json"

# Grid cells with >= this aurora probability (%) are counted as "active".
ACTIVE_THRESHOLD = 10

# ── Column descriptions ───────────────────────────────────────────────
COLUMN_DESCRIPTIONS = {
    "observation_time": "UTC timestamp of the solar-wind/satellite observations that seed this OVATION nowcast.",
    "forecast_time": "UTC valid time of the nowcast, roughly 30-40 minutes after the observation time (the lead time for aurora to respond).",
    "north_total_power": "Sum of aurora probability (%) over all Northern-Hemisphere grid cells. A unitless index proportional to total Northern auroral activity; rises sharply during geomagnetic storms.",
    "north_max_intensity": "Peak aurora probability (%) in any Northern-Hemisphere cell (0-100). 100 means visible aurora is essentially certain somewhere in the north.",
    "north_active_cells": f"Number of Northern-Hemisphere grid cells (0 to ~32,000, up to half the ~65k-cell global grid) with aurora probability >= {ACTIVE_THRESHOLD}%, a proxy for the spatial extent (area) of the northern auroral oval.",
    "south_total_power": "Sum of aurora probability (%) over all Southern-Hemisphere grid cells. Unitless index proportional to total Southern (aurora australis) activity.",
    "south_max_intensity": "Peak aurora probability (%) in any Southern-Hemisphere cell (0-100).",
    "south_active_cells": f"Number of Southern-Hemisphere grid cells (0 to ~32,000, up to half the ~65k-cell global grid) with aurora probability >= {ACTIVE_THRESHOLD}%, a proxy for the area of the southern auroral oval.",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
A compact daily time series of global auroral activity derived from NOAA SWPC's \
OVATION Prime aurora nowcast. Updated daily, growing incrementally.

OVATION Prime is an empirical model that converts real-time solar-wind and \
geomagnetic conditions into the probability of seeing the aurora across a global \
grid of roughly 65,000 cells, with a lead time of about 30-40 minutes. It is the \
model behind NOAA's public "aurora forecast" maps. The raw product is a dense \
spatial grid; this dataset reduces each snapshot to per-hemisphere summary metrics \
so that long-term trends in auroral activity can be tracked in a single tidy table.

For each daily snapshot the pipeline records, separately for the Northern and \
Southern hemispheres, the total integrated aurora probability (an index of overall \
activity), the peak cell probability, and the number of "active" cells above a 10% \
threshold (a proxy for the area of the auroral oval). These aggregates rise and fall \
with geomagnetic storms and closely track indices such as Kp and Dst, making the \
dataset useful for studying aurora visibility, comparing hemispheres, and connecting \
solar-wind drivers to auroral response. Because the source is a short-lead nowcast \
rather than an observation, values reflect modeled probability, not confirmed \
sightings."""


def fetch_ovation():
    """Fetch the latest OVATION grid and reduce it to one per-hemisphere summary row."""
    print("  Fetching OVATION aurora nowcast from SWPC...")
    for attempt in range(3):
        try:
            resp = requests.get(OVATION_URL, timeout=30)
            resp.raise_for_status()
            break
        except requests.RequestException as exc:
            if attempt == 2:
                raise
            wait = 2 ** attempt
            print(f"  Retry {attempt + 1}/2 after {wait}s: {exc}")
            time.sleep(wait)
    data = resp.json()

    arr = np.array(data["coordinates"], dtype=float)  # columns: lon, lat, aurora %
    lat, val = arr[:, 1], arr[:, 2]
    north, south = val[lat > 0], val[lat < 0]

    row = {
        "observation_time": pd.to_datetime(data["Observation Time"]),
        "forecast_time": pd.to_datetime(data["Forecast Time"]),
        "north_total_power": float(north.sum()),
        "north_max_intensity": float(north.max()),
        "north_active_cells": int((north >= ACTIVE_THRESHOLD).sum()),
        "south_total_power": float(south.sum()),
        "south_max_intensity": float(south.max()),
        "south_active_cells": int((south >= ACTIVE_THRESHOLD).sum()),
    }
    print(f"  Snapshot {row['observation_time']}: "
          f"N power {row['north_total_power']:.0f}, S power {row['south_total_power']:.0f}")
    return pd.DataFrame([row])


def main():
    print("Fetching aurora nowcast from NOAA SWPC OVATION...")

    df_new = fetch_ovation()

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Aurora Forecast (OVATION Nowcast)",
        description=DESCRIPTION,
        tags=["space", "space-weather", "aurora", "ovation", "noaa",
              "magnetosphere", "open-data", "tabular-data", "parquet"],
        source_url="https://www.swpc.noaa.gov/products/aurora-30-minute-forecast",
        task_categories=["time-series-forecasting"],
        collection_url="https://huggingface.co/collections/juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70",
        banner={"url": "https://images-assets.nasa.gov/image/iss072e159172/iss072e159172~medium.jpg",
                "alt": "Aurora borealis blankets the Earth, seen from the ISS",
                "credit": "NASA"},
        update_schedule="Daily at 16:25 UTC",
        related_datasets=[
            "juliensimon/geomagnetic-kp-index",
            "juliensimon/dst-index",
            "juliensimon/substorm-onsets",
            "juliensimon/donki-space-weather-events",
            "juliensimon/solar-wind",
        ],
    ) as p:
        df_existing = p.download_existing("aurora_forecast.parquet")

        if df_existing is not None and len(df_existing) > 0:
            df_existing["observation_time"] = pd.to_datetime(df_existing["observation_time"])
            df = p.merge(df_existing, df_new, dedup_on="observation_time",
                         sort_by="observation_time")
            print(f"  Merged: {len(df):,} snapshots ({len(df) - len(df_existing):+,} net new)")
        else:
            df = df_new

        df = p.clean(
            df,
            numeric=["north_total_power", "north_max_intensity",
                     "south_total_power", "south_max_intensity"],
            integer=["north_active_cells", "south_active_cells"],
        )

        # ── Stats ────────────────────────────────────────────────────
        n = len(df)
        date_min = df["observation_time"].min().strftime("%Y-%m-%d")
        date_max = df["observation_time"].max().strftime("%Y-%m-%d")
        peak_n = df["north_total_power"].max()
        peak_s = df["south_total_power"].max()

        quick_stats = f"""\
- **{n:,}** daily auroral snapshots ({date_min} to {date_max})
- Peak Northern activity index: **{peak_n:,.0f}**
- Peak Southern activity index: **{peak_s:,.0f}**"""

        usage = """\
```python
from datasets import load_dataset
import matplotlib.pyplot as plt

ds = load_dataset("juliensimon/aurora-forecast", split="train")
df = ds.to_pandas().sort_values("observation_time")

# Northern vs Southern auroral activity over time
fig, ax = plt.subplots(figsize=(12, 4))
ax.plot(df["observation_time"], df["north_total_power"], label="North")
ax.plot(df["observation_time"], df["south_total_power"], label="South")
ax.set_ylabel("Integrated aurora probability (activity index)")
ax.set_title("Global Auroral Activity (OVATION nowcast)")
ax.legend()
plt.tight_layout()
plt.show()
```"""

        p.publish(
            df,
            filename="aurora_forecast.parquet",
            min_rows=1,
            expected_columns=["observation_time", "north_total_power", "south_total_power"],
            critical_columns=["observation_time"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update aurora forecast: {n:,} snapshots",
        )
    print("Done.")


if __name__ == "__main__":
    main()
