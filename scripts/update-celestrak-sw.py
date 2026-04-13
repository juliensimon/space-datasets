#!/usr/bin/env python3
"""Fetch CelesTrak consolidated space weather data and upload to HF.

Source: CelesTrak Space Data (Dr. T.S. Kelso)
Consolidates NOAA SWPC, USAF, and other agencies' data into the de facto
standard input file for SGP4/SDP4 orbit propagation.
"""

import io

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

HF_REPO = "juliensimon/celestrak-space-weather"
SW_URL = "https://celestrak.org/SpaceData/SW-All.csv"

# ── Column descriptions ────────────────────────────────────────────────
COLUMN_DESCRIPTIONS = {
    "date": "Observation date (UTC). Records begin 1957-10-01 and are updated daily.",
    "bsrn": "Bartels Solar Rotation Number: sequential count of 27-day solar rotation periods since 8 Feb 1832 (epoch chosen by Julius Bartels). Used to align geomagnetic records with the solar rotation cycle.",
    "nd": "Day number within the 27-day Bartels rotation (1-27). Together with `bsrn`, provides a compact solar-rotation-relative timestamp.",
    "kp1": "Kp index for the 00-03 UT window. Quasi-logarithmic scale (0.0-9.0) measuring global geomagnetic disturbance; derived from up to 13 mid-latitude magnetometer stations. Values >=5 indicate a geomagnetic storm.",
    "kp2": "Kp index for the 03-06 UT window. See `kp1` for scale description.",
    "kp3": "Kp index for the 06-09 UT window. See `kp1` for scale description.",
    "kp4": "Kp index for the 09-12 UT window. See `kp1` for scale description.",
    "kp5": "Kp index for the 12-15 UT window. See `kp1` for scale description.",
    "kp6": "Kp index for the 15-18 UT window. See `kp1` for scale description.",
    "kp7": "Kp index for the 18-21 UT window. See `kp1` for scale description.",
    "kp8": "Kp index for the 21-24 UT window. See `kp1` for scale description.",
    "kp_sum": "Sum of the eight 3-hourly Kp values for the day (range 0-72). A convenient single-number summary of daily geomagnetic activity used in satellite drag studies.",
    "ap1": "ap index for the 00-03 UT window. Linear-scale equivalent of Kp (range 0-400 nT); more suitable than Kp for numerical averaging and atmospheric drag models such as NRLMSISE-00.",
    "ap2": "ap index for the 03-06 UT window. See `ap1` for scale description.",
    "ap3": "ap index for the 06-09 UT window. See `ap1` for scale description.",
    "ap4": "ap index for the 09-12 UT window. See `ap1` for scale description.",
    "ap5": "ap index for the 12-15 UT window. See `ap1` for scale description.",
    "ap6": "ap index for the 15-18 UT window. See `ap1` for scale description.",
    "ap7": "ap index for the 18-21 UT window. See `ap1` for scale description.",
    "ap8": "ap index for the 21-24 UT window. See `ap1` for scale description.",
    "ap_avg": "Daily mean of the eight 3-hourly ap values (range 0-400 nT). Standard daily geomagnetic activity indicator; required input to the JB2008 atmospheric density model.",
    "cp": "Daily planetary character figure Cp (0.0-2.5, step 0.1). Legacy precursor to the Ap index: 0.0 = extremely quiet, 2.5 = extremely disturbed. Maintained for historical continuity.",
    "c9": "Nine-level conversion of the Cp figure (0-9). Maps the 0.0-2.5 Cp scale to a compact single-digit integer for older data formats.",
    "isn": "International Sunspot Number (daily). Count of sunspots visible on the solar disk; a proxy for solar activity level and the phase of the ~11-year solar cycle. Provided by the Royal Observatory of Belgium.",
    "f10_7_obs": "Observed daily solar radio flux at 10.7 cm wavelength (2800 MHz), in Solar Flux Units (1 SFU = 10^-22 W m^-2 Hz^-1). Measured at the Dominion Radio Astrophysical Observatory, Penticton, Canada. Typical range: 65-300 SFU. Key proxy for solar EUV radiation and required input to atmospheric drag models.",
    "f10_7_adj": "F10.7 flux adjusted to a standard Earth-Sun distance of 1 AU, removing the effect of Earth's elliptical orbit. Use this column for solar cycle studies and model inputs that assume constant Earth-Sun distance.",
    "f10_7_data_type": "Data source qualifier: 'OBS' = direct observatory measurement, 'INT' = interpolated, 'PRE' = predicted. Check this column when using recent values that may not yet be final.",
    "f10_7_obs_center81": "81-day centered average of the observed F10.7 flux (40 days before and after). Smooths short-term variability to reveal the solar cycle trend. Used as the long-term solar activity input in atmospheric models.",
    "f10_7_obs_last81": "81-day trailing average of the observed F10.7 flux (current day plus prior 80 days). Suitable for real-time operations where future data is unavailable.",
    "f10_7_adj_center81": "81-day centered average of the 1-AU adjusted F10.7 flux. Use for solar cycle analysis independent of orbital geometry.",
    "f10_7_adj_last81": "81-day trailing average of the 1-AU adjusted F10.7 flux. Causal (no future data) version of `f10_7_adj_center81`.",
}

# ── Dataset description ─────────────────────────────────────────────────
DESCRIPTION = """\
CelesTrak consolidated space weather data -- THE file every orbit propagator needs. \
Daily Kp, Ap, F10.7, and solar/geomagnetic indices used by SGP4/SDP4 propagators, \
atmospheric models (JB2008, NRLMSISE), and conjunction screening.

The CelesTrak space weather file, maintained by Dr. T.S. Kelso, is the de facto standard \
input file for operational orbit determination and propagation in the space surveillance \
community. It consolidates data from multiple agencies -- NOAA SWPC for Kp/Ap indices and \
solar flux, GFZ Potsdam for definitive geomagnetic indices, and the NRC Herzberg Institute \
for F10.7 measurements -- into a single, consistently formatted daily time series. The file \
includes both historical observations and near-term predictions (typically 45 days ahead), \
using the same format conventions expected by legacy Fortran propagators and modern Python/C++ \
SGP4 implementations alike.

For orbit propagation, the key parameters are the daily and 3-hourly Ap indices (which drive \
geomagnetic heating in thermospheric density models) and the F10.7 solar radio flux with its \
81-day running averages (which drive solar EUV heating). The NRLMSISE-00 model, for example, \
requires daily Ap, the 3-hourly Ap for the current and preceding 33 hours, daily F10.7, and \
the 81-day centered average F10.7bar. JB2008 uses additional solar indices (S10.7, M10.7, \
Y10.7) that are available in extended versions of this file. Errors in these space weather \
inputs propagate directly into drag coefficient estimates, making the quality and timeliness \
of this data critical for conjunction assessment and collision avoidance maneuvers.

The dataset spans the full modern era of satellite operations, with the historical record \
reaching back to 1957 (International Geophysical Year). This long baseline captures multiple \
complete solar cycles (cycles 19 through 25), enabling statistical studies of solar cycle \
variability and its impact on the orbital environment.
"""


def main():
    print("Fetching CelesTrak consolidated space weather data...")

    resp = requests.get(SW_URL, timeout=60)
    resp.raise_for_status()

    # Skip comment lines starting with #
    lines = resp.text.splitlines()
    data_lines = [line for line in lines if not line.startswith("#")]
    clean_text = "\n".join(data_lines)

    df = pd.read_csv(io.StringIO(clean_text))
    print(f"  {len(df):,} rows")

    # Rename columns to snake_case
    df.columns = [c.lower().replace(".", "_") for c in df.columns]

    # Ensure date column exists
    if "date" not in df.columns:
        for col in df.columns:
            if "date" in col.lower():
                df = df.rename(columns={col: "date"})
                break

    # Parse date
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")

    # Convert numeric columns
    for col in df.columns:
        if col in ("date", "f10_7_data_type"):
            continue
        if df[col].dtype == object:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    df = df.sort_values("date").reset_index(drop=True)

    # ── Domain-specific stats ────────────────────────────────────────
    n = len(df)
    n_cols = len(df.columns)
    date_min = df["date"].min().strftime("%Y-%m-%d")
    date_max = df["date"].max().strftime("%Y-%m-%d")
    mean_f107 = df["f10_7_obs"].mean() if "f10_7_obs" in df.columns else 0
    max_kpsum = df["kp_sum"].max() if "kp_sum" in df.columns else 0

    quick_stats = f"""\
- **{n:,}** daily records ({date_min} to {date_max})
- **{n_cols}** columns of solar and geomagnetic indices
- Mean F10.7 flux: **{mean_f107:.1f}** SFU
- Max daily Kp sum: **{max_kpsum:.0f}** (scale 0-72)"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/celestrak-space-weather", split="train")
df = ds.to_pandas()

# Recent space weather
print(df.tail(10))

# Plot F10.7 solar flux over time
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(14, 4))
ax.plot(df["date"], df["f10_7_obs"], linewidth=0.5)
ax.set_xlabel("Date")
ax.set_ylabel("F10.7 (SFU)")
ax.set_title("Solar Radio Flux (F10.7)")
plt.show()
```"""

    # Identify numeric columns for clean()
    numeric_cols = [c for c in df.columns
                    if c not in ("date", "f10_7_data_type") and c in COLUMN_DESCRIPTIONS]

    with Pipeline(
        repo=HF_REPO,
        pretty_name="CelesTrak Consolidated Space Weather",
        description=DESCRIPTION,
        tags=["space", "space-weather", "celestrak", "sgp4", "atmospheric-drag",
              "orbit-propagation", "open-data", "tabular-data", "parquet"],
        source_url="https://celestrak.org/SpaceData/",
        task_categories=["tabular-regression", "time-series-forecasting"],
        collection_url="https://huggingface.co/collections/juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70",
        banner={
            "url": "https://images-assets.nasa.gov/image/iss072e159172/iss072e159172~medium.jpg",
            "alt": "Aurora borealis blankets the Earth, seen from the ISS",
            "credit": "NASA",
        },
        related_datasets=[
            "juliensimon/geomagnetic-kp-index",
            "juliensimon/dst-index",
            "juliensimon/solar-wind",
            "juliensimon/f107-solar-flux",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=numeric_cols,
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="celestrak_space_weather.parquet",
            min_rows=20_000,
            expected_columns=["date", "kp1", "ap_avg", "f10_7_obs"],
            critical_columns=["date"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update CelesTrak space weather: {n:,} records",
        )
    print("Done.")


if __name__ == "__main__":
    main()
