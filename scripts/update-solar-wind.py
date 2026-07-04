#!/usr/bin/env python3
"""Fetch real-time solar wind data from NOAA SWPC and upload to HF.

Merges plasma (density, speed, temperature) and magnetometer (Bt, Bx/By/Bz GSM)
data from the DSCOVR/ACE L1 monitors. Incremental: appends 7-day rolling window
to existing dataset.
"""

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

HF_REPO = "juliensimon/solar-wind"

PLASMA_URL = "https://services.swpc.noaa.gov/products/solar-wind/plasma-3-day.json"
MAG_URL = "https://services.swpc.noaa.gov/products/solar-wind/mag-3-day.json"
# NOAA retired 7-day and 2-hour; fall back to 1-day window (same format, same columns)
PLASMA_URL_SHORT = "https://services.swpc.noaa.gov/products/solar-wind/plasma-1-day.json"
MAG_URL_SHORT = "https://services.swpc.noaa.gov/products/solar-wind/mag-1-day.json"

# ── Column descriptions ─────────────────────────────────────────────
COLUMN_DESCRIPTIONS = {
    "time_tag": "Measurement timestamp from DSCOVR/ACE at the L1 Lagrange point (UTC, ~1-minute cadence)",
    "density": "Solar wind proton number density in protons/cm3; typical quiet-time range 3-10 p/cm3; high density combined with high speed increases dynamic pressure, compressing the magnetosphere",
    "speed": "Solar wind bulk velocity in km/s; typical 350-800 km/s; coronal hole streams reach 600-800 km/s; CME-driven shocks can exceed 1500 km/s",
    "temperature": "Solar wind proton temperature in Kelvin; typical ~10^5 K; abnormally low values (~10^4 K) suggest passage of a magnetic cloud",
    "bt": "Total IMF magnitude in nT — sqrt(Bx^2 + By^2 + Bz^2); typical 2-10 nT; elevated during CME passage",
    "bx_gsm": "IMF Bx component in Geocentric Solar Magnetospheric (GSM) coordinates in nT; typical range +/-20 nT; sun-Earth direction component",
    "by_gsm": "IMF By component in GSM coordinates in nT; typical range +/-20 nT; controls asymmetric magnetospheric convection and field-aligned currents",
    "bz_gsm": "IMF Bz component in GSM coordinates in nT — the primary geomagnetic storm driver; sustained southward (negative) Bz enables dayside magnetic reconnection; < -10 nT drives moderate storms, < -30 nT drives severe storms; typical range +/-20 nT",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Real-time solar wind plasma and magnetic field measurements from the DSCOVR and ACE \
spacecraft at the L1 Lagrange point, via NOAA SWPC. Updated daily.

The solar wind is a continuous stream of charged particles flowing from the Sun. \
Its speed, density, and magnetic field orientation (especially Bz) are the primary \
drivers of geomagnetic storms. When Bz turns strongly southward (negative), it \
couples with Earth's magnetosphere and can trigger storms that affect satellites, \
power grids, and GPS.

This dataset is the missing link in the Sun-to-Earth causal chain: \
solar flare -> CME -> solar wind -> Dst/Kp storm -> orbital drag.

The measurements come from the DSCOVR (Deep Space Climate Observatory) and ACE \
(Advanced Composition Explorer) spacecraft orbiting the Sun-Earth L1 Lagrange point, \
approximately 1.5 million km upstream of Earth. At this vantage point, the instruments \
sample the solar wind roughly 15-60 minutes before it reaches the magnetopause, providing \
a critical lead time for geomagnetic storm prediction. DSCOVR's Faraday Cup measures the \
bulk plasma properties (proton density, speed, and temperature), while its fluxgate \
magnetometer measures the interplanetary magnetic field (IMF) vector in Geocentric Solar \
Magnetospheric (GSM) coordinates.

The Bz component of the IMF in GSM coordinates is the single most important parameter for \
geomagnetic coupling. When Bz is strongly southward (negative), the IMF opposes Earth's \
northward magnetic field at the dayside magnetopause, enabling magnetic reconnection that \
transfers solar wind energy into the magnetosphere. Sustained Bz below -10 nT typically \
produces moderate geomagnetic storms (Kp 6-7, Dst below -100 nT), while extreme events \
with Bz below -30 nT can trigger severe storms affecting power grids and satellite operations.

Typical quiet-time solar wind conditions show speeds of 300-450 km/s and densities of \
3-10 protons/cm^3. Coronal hole high-speed streams elevate speeds to 600-800 km/s, while \
interplanetary CMEs can drive transient speeds above 1,000 km/s with enhanced magnetic fields."""


def _get_sw_json(primary_url, fallback_url, label):
    """Fetch solar wind JSON; fall back to shorter window if primary is 404."""
    resp = requests.get(primary_url, timeout=60)
    if resp.status_code == 404:
        print(f"  {label}: {primary_url} returned 404, using 1-day fallback")
        resp = requests.get(fallback_url, timeout=60)
    resp.raise_for_status()
    raw = resp.json()
    # Format: first row is header, rest are data rows
    return pd.DataFrame(raw[1:], columns=raw[0])


def fetch_solar_wind():
    """Fetch and merge plasma + magnetometer data from SWPC."""
    print("  Fetching plasma data...")
    df_plasma = _get_sw_json(PLASMA_URL, PLASMA_URL_SHORT, "plasma")

    print("  Fetching magnetometer data...")
    df_mag = _get_sw_json(MAG_URL, MAG_URL_SHORT, "mag")

    # Parse time_tag
    df_plasma["time_tag"] = pd.to_datetime(df_plasma["time_tag"])
    df_mag["time_tag"] = pd.to_datetime(df_mag["time_tag"])

    # Convert numeric columns
    for col in ["density", "speed", "temperature"]:
        df_plasma[col] = pd.to_numeric(df_plasma[col], errors="coerce")
    for col in ["bt", "bx_gsm", "by_gsm", "bz_gsm"]:
        df_mag[col] = pd.to_numeric(df_mag[col], errors="coerce")

    # Keep only the columns we want from mag
    df_mag = df_mag[["time_tag", "bt", "bx_gsm", "by_gsm", "bz_gsm"]]

    # Merge on time_tag (outer join to keep all timestamps)
    df = pd.merge(df_plasma, df_mag, on="time_tag", how="outer")
    df = df.sort_values("time_tag").reset_index(drop=True)

    print(f"  {len(df):,} readings ({len(df_plasma):,} plasma, {len(df_mag):,} mag)")
    return df


def main():
    print("Fetching solar wind data from NOAA SWPC...")

    df_new = fetch_solar_wind()

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Real-Time Solar Wind (DSCOVR/ACE)",
        description=DESCRIPTION,
        tags=["space", "space-weather", "solar-wind", "dscovr", "ace", "noaa",
              "magnetosphere", "bz", "geomagnetic", "open-data", "tabular-data", "parquet"],
        source_url="https://www.swpc.noaa.gov/products/real-time-solar-wind",
        task_categories=["time-series-forecasting", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70",
        banner={"url": "https://images-assets.nasa.gov/image/iss072e159172/iss072e159172~medium.jpg",
                "alt": "Aurora borealis blankets the Earth, seen from the ISS",
                "credit": "NASA"},
        update_schedule="Daily at 15:00 UTC",
        related_datasets=[
            "juliensimon/dst-index",
            "juliensimon/donki-space-weather-events",
            "juliensimon/solar-flare-events",
            "juliensimon/space-weather-indices",
        ],
    ) as p:
        df_existing = p.download_existing("solar_wind.parquet")

        if df_existing is not None and len(df_existing) > 0:
            df_existing["time_tag"] = pd.to_datetime(df_existing["time_tag"])
            df = p.merge(df_existing, df_new, dedup_on="time_tag", sort_by="time_tag")
            print(f"  Merged: {len(df):,} readings ({len(df) - len(df_existing):+,} net new)")
        else:
            df = df_new

        df = p.clean(df, numeric=["density", "speed", "temperature",
                                   "bt", "bx_gsm", "by_gsm", "bz_gsm"])

        # Stats
        n = len(df)
        date_min = df["time_tag"].min().strftime("%Y-%m-%d")
        date_max = df["time_tag"].max().strftime("%Y-%m-%d")
        avg_speed = df["speed"].mean()
        max_speed = df["speed"].max()
        min_bz = df["bz_gsm"].min()
        n_southward = int((df["bz_gsm"] < 0).sum())

        quick_stats = f"""\
- **{n:,}** readings ({date_min} to {date_max})
- Average speed: **{avg_speed:.0f} km/s**, max: **{max_speed:.0f} km/s**
- Minimum Bz: **{min_bz:.1f} nT** ({n_southward:,} southward readings)"""

        usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/solar-wind", split="train")
df = ds.to_pandas()

# Solar wind speed time series
import matplotlib.pyplot as plt

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 6), sharex=True)
ax1.plot(df["time_tag"], df["speed"], linewidth=0.5)
ax1.set_ylabel("Speed (km/s)")
ax1.set_title("Solar Wind Speed")

ax2.plot(df["time_tag"], df["bz_gsm"], linewidth=0.5, color="red")
ax2.axhline(0, color="gray", linestyle="--", alpha=0.5)
ax2.set_ylabel("Bz GSM (nT)")
ax2.set_title("IMF Bz (southward = storm driver)")
plt.tight_layout()
plt.show()

# Bz southward events (storm drivers)
southward = df[df["bz_gsm"] < -5]
print(f"{len(southward)} readings with Bz < -5 nT")
```"""

        p.publish(
            df,
            filename="solar_wind.parquet",
            min_rows=5000,
            expected_columns=["time_tag", "density", "speed", "temperature",
                              "bt", "bz_gsm"],
            critical_columns=["time_tag", "speed"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update solar wind: {n:,} readings",
        )
    print("Done.")


if __name__ == "__main__":
    main()
