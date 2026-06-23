#!/usr/bin/env python3
"""Fetch GOES X-ray flux from NOAA SWPC and upload to HF.

The GOES X-Ray Sensor (XRS) measures solar soft X-ray irradiance in two bands
at 1-minute cadence. The 0.1-0.8 nm ("long") band defines the standard A/B/C/M/X
solar flare classification. Incremental: appends the recent 7-day window to the
existing dataset.
"""

import time

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

HF_REPO = "juliensimon/goes-xray-flux"

# Primary operational GOES satellite, 7-day rolling window, 1-minute cadence.
XRAY_URL = "https://services.swpc.noaa.gov/json/goes/primary/xrays-7-day.json"

# ── Column descriptions ───────────────────────────────────────────────
COLUMN_DESCRIPTIONS = {
    "datetime": "Observation timestamp (UTC), 1-minute cadence. The GOES X-Ray Sensor (XRS) integrates over each minute.",
    "satellite": "GOES satellite number providing the measurement (e.g. 16, 18). NOAA designates one spacecraft as the primary X-ray source; the number can change when the primary is reassigned.",
    "flux_short": "Solar X-ray irradiance in the 0.05-0.4 nm ('short') band, in W/m^2. Electron-contamination corrected science-quality flux. The harder short band responds to the hottest flare plasma and rises earlier in impulsive events.",
    "flux_long": "Solar X-ray irradiance in the 0.1-0.8 nm ('long') band, in W/m^2. This is the band used for the standard solar flare classification. Electron-contamination corrected science-quality flux.",
    "flare_class": "Solar flare magnitude class derived from the long-band peak flux: A (<1e-7 W/m^2), B (1e-7-1e-6), C (1e-6-1e-5), M (1e-5-1e-4), X (>=1e-4). Each letter is a 10x step. M- and X-class flares can drive radio blackouts and radiation storms.",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Solar soft X-ray flux from the GOES X-Ray Sensor (XRS), the operational backbone \
of solar flare monitoring. Updated daily from NOAA SWPC, growing incrementally at \
1-minute cadence.

The GOES (Geostationary Operational Environmental Satellite) X-Ray Sensor measures \
the Sun's soft X-ray irradiance in two wavelength bands: a "short" 0.05-0.4 nm band \
and a "long" 0.1-0.8 nm band. The long band is the international standard for solar \
flare classification: the A/B/C/M/X scale is defined directly from its peak flux, \
with each letter marking a tenfold increase in intensity. A C1.0 flare corresponds to \
1e-6 W/m^2, an M1.0 to 1e-5 W/m^2, and an X1.0 to 1e-4 W/m^2.

X-ray flux is the earliest and most direct space-weather signature of a solar flare. \
Because soft X-rays travel at the speed of light, they arrive ~8 minutes after the \
flare and immediately ionize Earth's dayside ionosphere, causing sudden ionospheric \
disturbances and shortwave (HF) radio blackouts. Operationally, the GOES XRS time \
series is what space-weather forecasters watch in real time to issue flare alerts and \
R-scale radio-blackout warnings. This dataset complements event-level flare catalogs \
by preserving the underlying continuous flux from which those events are derived."""


def fetch_xray():
    """Fetch the 7-day GOES X-ray window from SWPC and pivot to one row per minute."""
    print("  Fetching GOES X-ray flux from SWPC...")
    for attempt in range(3):
        try:
            resp = requests.get(XRAY_URL, timeout=30)
            resp.raise_for_status()
            break
        except requests.RequestException as exc:
            if attempt == 2:
                raise
            wait = 2 ** attempt
            print(f"  Retry {attempt + 1}/2 after {wait}s: {exc}")
            time.sleep(wait)
    raw = resp.json()

    df = pd.DataFrame(raw)
    df["time_tag"] = pd.to_datetime(df["time_tag"])

    # Split the two energy bands and join into a wide, one-row-per-minute frame.
    short = (df[df["energy"] == "0.05-0.4nm"][["time_tag", "satellite", "flux"]]
             .rename(columns={"flux": "flux_short"}))
    long_ = (df[df["energy"] == "0.1-0.8nm"][["time_tag", "flux"]]
             .rename(columns={"flux": "flux_long"}))
    wide = short.merge(long_, on="time_tag", how="outer").rename(columns={"time_tag": "datetime"})

    for col in ["flux_short", "flux_long"]:
        wide[col] = pd.to_numeric(wide[col], errors="coerce")
    wide["satellite"] = pd.to_numeric(wide["satellite"], errors="coerce").astype("Int64")

    # Flare classification from the long-band flux.
    wide["flare_class"] = pd.cut(
        wide["flux_long"],
        bins=[-float("inf"), 1e-7, 1e-6, 1e-5, 1e-4, float("inf")],
        labels=["A", "B", "C", "M", "X"],
    )

    wide = wide.sort_values("datetime").reset_index(drop=True)
    print(f"  {len(wide):,} minute readings")
    return wide


def main():
    print("Fetching GOES X-ray flux from NOAA SWPC...")

    df_new = fetch_xray()

    with Pipeline(
        repo=HF_REPO,
        pretty_name="GOES Solar X-Ray Flux (1-Minute)",
        description=DESCRIPTION,
        tags=["space", "space-weather", "solar-flares", "goes", "noaa",
              "x-ray", "sun", "open-data", "tabular-data", "parquet"],
        source_url="https://www.swpc.noaa.gov/products/goes-x-ray-flux",
        task_categories=["time-series-forecasting", "tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70",
        banner={"url": "https://images-assets.nasa.gov/image/brief-outburst_16760026566_o/brief-outburst_16760026566_o~medium.jpg",
                "alt": "A solar eruption captured by NASA's Solar Dynamics Observatory",
                "credit": "NASA/SDO"},
        update_schedule="Daily at 16:10 UTC",
        related_datasets=[
            "juliensimon/solar-flare-events",
            "juliensimon/solar-radio-bursts",
            "juliensimon/donki-space-weather-events",
            "juliensimon/f107-solar-flux",
            "juliensimon/silso-sunspot-number",
        ],
    ) as p:
        df_existing = p.download_existing("goes_xray.parquet")

        if df_existing is not None and len(df_existing) > 0:
            df_existing["datetime"] = pd.to_datetime(df_existing["datetime"])
            df = p.merge(df_existing, df_new, dedup_on="datetime", sort_by="datetime")
            print(f"  Merged: {len(df):,} readings ({len(df) - len(df_existing):+,} net new)")
        else:
            df = df_new

        df = p.clean(df, numeric=["flux_short", "flux_long"], integer=["satellite"],
                     strings=["flare_class"])

        # ── Stats ────────────────────────────────────────────────────
        n = len(df)
        date_min = df["datetime"].min().strftime("%Y-%m-%d")
        date_max = df["datetime"].max().strftime("%Y-%m-%d")
        peak_flux = df["flux_long"].max()
        n_m = int(df["flare_class"].isin(["M", "X"]).sum())
        n_x = int((df["flare_class"] == "X").sum())

        quick_stats = f"""\
- **{n:,}** 1-minute readings ({date_min} to {date_max})
- Peak long-band flux: **{peak_flux:.2e}** W/m^2
- **{n_m:,}** minutes at M-class or above, **{n_x:,}** at X-class"""

        usage = """\
```python
from datasets import load_dataset
import matplotlib.pyplot as plt

ds = load_dataset("juliensimon/goes-xray-flux", split="train")
df = ds.to_pandas().sort_values("datetime")

# Classic GOES X-ray plot: long-band flux on a log scale with flare-class bands
fig, ax = plt.subplots(figsize=(12, 4))
ax.plot(df["datetime"], df["flux_long"], linewidth=0.5)
ax.set_yscale("log")
for level, label in [(1e-6, "C"), (1e-5, "M"), (1e-4, "X")]:
    ax.axhline(level, color="red", linestyle="--", alpha=0.4)
    ax.text(df["datetime"].iloc[0], level, f" {label}", va="bottom", color="red")
ax.set_ylabel("0.1-0.8 nm flux (W/m^2)")
ax.set_title("GOES Solar X-Ray Flux")
plt.tight_layout()
plt.show()

# Largest flares in the record
print(df.nlargest(10, "flux_long")[["datetime", "flux_long", "flare_class"]])
```"""

        p.publish(
            df,
            filename="goes_xray.parquet",
            min_rows=100,
            expected_columns=["datetime", "flux_long", "flare_class"],
            critical_columns=["datetime", "flux_long"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update GOES X-ray flux: {n:,} readings",
        )
    print("Done.")


if __name__ == "__main__":
    main()
