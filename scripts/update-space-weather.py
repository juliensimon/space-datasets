#!/usr/bin/env python3
"""Fetch space weather indices from CelesTrak and upload to HF."""

import pandas as pd

from hf_dataset_utils import Pipeline

SW_URL = "https://celestrak.org/SpaceData/SW-All.csv"
HF_REPO = "juliensimon/space-weather-indices"

# NOAA Kp-based storm scale thresholds (max 3-hourly Kp in a day)
STORM_THRESHOLDS = [(9, "G5"), (8, "G4"), (7, "G3"), (6, "G2"), (5, "G1")]

# ── Column mapping ───────────────────────────────────────────────────
KP_MAP = {f"KP{i}": f"kp_{h:02d}00" for i, h in enumerate([0, 3, 6, 9, 12, 15, 18, 21], 1)}
AP_MAP = {f"AP{i}": f"ap_{h:02d}00" for i, h in enumerate([0, 3, 6, 9, 12, 15, 18, 21], 1)}

RENAME = {
    "DATE": "date",
    "BSRN": "bartels_rotation",
    "ND": "bartels_day",
    **KP_MAP,
    "KP_SUM": "kp_sum",
    **AP_MAP,
    "AP_AVG": "ap_avg",
    "CP": "cp",
    "C9": "c9",
    "ISN": "sunspot_number",
    "F10.7_OBS": "f107_obs",
    "F10.7_ADJ": "f107_adj",
    "F10.7_DATA_TYPE": "f107_data_type",
    "F10.7_OBS_CENTER81": "f107_obs_center81",
    "F10.7_OBS_LAST81": "f107_obs_last81",
    "F10.7_ADJ_CENTER81": "f107_adj_center81",
    "F10.7_ADJ_LAST81": "f107_adj_last81",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "date": "Observation date in UTC",
    "bartels_rotation": "Bartels Solar Rotation Number -- a 27-day cycle count since 1832, used to align solar data with the Sun's synodic rotation period as seen from Earth",
    "bartels_day": "Day within the current Bartels rotation cycle (1-27)",
    "kp_0000": "3-hourly Kp geomagnetic index for the 00:00-03:00 UT interval (quasi-logarithmic, 0-9 scale); measures planetary-scale magnetic field disturbances",
    "kp_0300": "3-hourly Kp geomagnetic index for the 03:00-06:00 UT interval",
    "kp_0600": "3-hourly Kp geomagnetic index for the 06:00-09:00 UT interval",
    "kp_0900": "3-hourly Kp geomagnetic index for the 09:00-12:00 UT interval",
    "kp_1200": "3-hourly Kp geomagnetic index for the 12:00-15:00 UT interval",
    "kp_1500": "3-hourly Kp geomagnetic index for the 15:00-18:00 UT interval",
    "kp_1800": "3-hourly Kp geomagnetic index for the 18:00-21:00 UT interval",
    "kp_2100": "3-hourly Kp geomagnetic index for the 21:00-24:00 UT interval",
    "kp_sum": "Sum of the eight daily 3-hourly Kp values (0-72); daily aggregate measure of geomagnetic activity",
    "ap_0000": "3-hourly Ap index for the 00:00-03:00 UT interval -- linearized equivalent of Kp in nanotesla units; used as input to atmospheric density models (NRLMSISE-00, JB2008)",
    "ap_0300": "3-hourly Ap index for the 03:00-06:00 UT interval",
    "ap_0600": "3-hourly Ap index for the 06:00-09:00 UT interval",
    "ap_0900": "3-hourly Ap index for the 09:00-12:00 UT interval",
    "ap_1200": "3-hourly Ap index for the 12:00-15:00 UT interval",
    "ap_1500": "3-hourly Ap index for the 15:00-18:00 UT interval",
    "ap_1800": "3-hourly Ap index for the 18:00-21:00 UT interval",
    "ap_2100": "3-hourly Ap index for the 21:00-24:00 UT interval",
    "ap_avg": "Daily average Ap index; geomagnetic storm threshold at Ap >= 50; key input for satellite drag models",
    "cp": "Daily Character Figure Cp (0.0-2.5) -- a qualitative measure of the overall level of geomagnetic disturbance for the day",
    "c9": "Converted Cp on a 0-9 integer scale; derived from Cp for easier comparison with Kp",
    "sunspot_number": "International Sunspot Number (ISN) -- daily count of sunspot groups and individual spots; primary indicator of the ~11-year solar activity cycle",
    "f107_obs": "Observed 10.7 cm (2800 MHz) solar radio flux in solar flux units (SFU, 1 SFU = 10^-22 W/m2/Hz); measured at Penticton, Canada; primary proxy for solar EUV radiation that heats the thermosphere",
    "f107_adj": "F10.7 solar radio flux adjusted to 1 AU distance; removes the effect of Earth's orbital eccentricity for physical comparisons",
    "f107_data_type": "Data source flag: OBS (observed), INT (interpolated from observations), PRD (predicted), PRM (predicted monthly mean)",
    "f107_obs_center81": "81-day centered running average of observed F10.7; smooths the 27-day solar rotation modulation to represent background EUV irradiance level",
    "f107_obs_last81": "81-day trailing (last 81 days) running average of observed F10.7; available in near-real-time unlike the centered average",
    "f107_adj_center81": "81-day centered running average of 1-AU-adjusted F10.7",
    "f107_adj_last81": "81-day trailing running average of 1-AU-adjusted F10.7",
    "is_storm": "True when daily average Ap >= 50, indicating a geomagnetic storm day; storms cause elevated satellite drag, GPS errors, and power grid disturbances",
    "storm_level": "NOAA G-scale classification based on maximum 3-hourly Kp: G1 (Kp=5, minor), G2 (Kp=6, moderate), G3 (Kp=7, strong), G4 (Kp=8, severe), G5 (Kp=9, extreme); null for non-storm days",
    "data_type": "Simplified data type: 'observed' (OBS/INT -- based on measurements) or 'predicted' (PRD/PRM -- forecast values)",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Daily geomagnetic and solar activity indices since 1957 from NOAA SWPC via CelesTrak. \
Includes Kp/Ap geomagnetic indices, F10.7 solar radio flux, and international sunspot numbers.

These indices together form the essential parameter set for characterizing the state of the \
heliosphere and its coupling to the terrestrial environment. The Kp index (quasi-logarithmic, \
0-9 scale, 3-hourly) captures planetary-scale geomagnetic disturbances driven by solar \
wind-magnetosphere interactions, while the Ap index (its linearized daily equivalent in \
nanotesla) serves as the standard geomagnetic input to atmospheric density models. The F10.7 \
solar radio flux (measured daily at 2800 MHz in Penticton, Canada) is the primary proxy for \
solar extreme ultraviolet (EUV) radiation that heats the thermosphere -- the atmospheric \
layer where most satellites experience drag.

For operational space weather applications, this dataset provides the complete set of inputs \
required by the major atmospheric density models: NRLMSISE-00 (F10.7, F10.7bar, Ap), \
JB2008 (F10.7 plus supplementary indices), and DTM (F10.7, Kp). The storm classification \
(G1-G5) derived from Kp thresholds is the same scale used in NOAA space weather alerts.
"""


def classify_storm(row):
    """Classify geomagnetic storm level from max Kp value."""
    kp_cols = [c for c in row.index if c.startswith("kp_") and c != "kp_sum"]
    kp_max = row[kp_cols].max()
    if pd.isna(kp_max):
        return None
    for threshold, level in STORM_THRESHOLDS:
        if kp_max >= threshold:
            return level
    return None


def main():
    print("Fetching space weather indices from CelesTrak...")
    df = pd.read_csv(SW_URL)
    print(f"  {len(df):,} daily records")

    # Type conversions
    df["DATE"] = pd.to_datetime(df["DATE"], errors="coerce")

    numeric_cols = [c for c in df.columns if c != "DATE" and c != "F10.7_DATA_TYPE"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.rename(columns=RENAME)

    # Derived columns
    df["is_storm"] = df["ap_avg"] >= 50
    df["storm_level"] = df.apply(classify_storm, axis=1)
    df["data_type"] = df["f107_data_type"].map({
        "OBS": "observed", "INT": "observed",
        "PRD": "predicted", "PRM": "predicted",
    })

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # ── Domain-specific stats for README ─────────────────────────────
    observed = df[df["data_type"] == "observed"]
    n_observed = len(observed)
    n_predicted = len(df) - n_observed
    n_storms = int(df["is_storm"].sum())
    n_g3_plus = int(df["storm_level"].isin(["G3", "G4", "G5"]).sum())
    date_min = df["date"].min().strftime("%Y-%m-%d")
    date_max_obs = observed["date"].max().strftime("%Y-%m-%d")
    max_ap = observed["ap_avg"].max()
    max_ap_date = observed.loc[observed["ap_avg"].idxmax(), "date"].strftime("%Y-%m-%d")

    quick_stats = f"""\
- **{n_observed:,}** observed days ({date_min} to {date_max_obs})
- **{n_storms:,}** geomagnetic storm days (Ap >= 50)
- **{n_g3_plus:,}** severe storms (G3+)
- Strongest storm: Ap={max_ap:.0f} on {max_ap_date}"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/space-weather-indices", split="train")
df = ds.to_pandas()

# Only observed data (exclude predictions)
observed = df[df["data_type"] == "observed"]

# Geomagnetic storms
storms = df[df["is_storm"] == True].sort_values("ap_avg", ascending=False)

# Solar cycle visualization
import matplotlib.pyplot as plt
df["year"] = df["date"].dt.year
yearly_ssn = df.groupby("year")["sunspot_number"].mean()
yearly_ssn.plot(figsize=(12, 4))
plt.ylabel("Mean Sunspot Number")
plt.title("Solar Cycle from Daily Sunspot Numbers")
plt.show()

# F10.7 flux trend (drives atmospheric drag)
df.set_index("date")[["f107_adj"]].rolling(81).mean().plot()
plt.ylabel("F10.7 (SFU)")
plt.title("81-day Running Mean F10.7 Solar Flux")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Space Weather Indices (Kp, Ap, F10.7)",
        description=DESCRIPTION,
        tags=["space", "space-weather", "geomagnetic", "solar", "noaa",
              "celestrak", "open-data", "kp-index", "f10.7", "sunspot",
              "solar-cycle", "swpc", "tabular-data", "parquet"],
        source_url="https://celestrak.org/SpaceData/",
        update_schedule="Daily at 11:00 UTC via GitHub Actions",
        task_categories=["tabular-regression", "time-series-forecasting"],
        collection_url="https://huggingface.co/collections/juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70",
        banner={
            "url": "https://images-assets.nasa.gov/image/iss072e159172/iss072e159172~medium.jpg",
            "alt": "Aurora borealis blankets the Earth, seen from the ISS",
            "credit": "NASA",
        },
        related_datasets=[
            "juliensimon/solar-flare-events",
            "juliensimon/space-track-satcat",
            "juliensimon/space-track-tle-history",
            "juliensimon/neo-close-approaches",
        ],
    ) as p:
        df = p.clean(df)
        p.publish(
            df,
            filename="space_weather_indices.parquet",
            min_rows=20000,
            expected_columns=["date", "kp_sum", "ap_avg", "f107_obs", "sunspot_number"],
            critical_columns=["date", "ap_avg"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update space weather indices: {n_observed:,} observed days",
        )
    print("Done.")


if __name__ == "__main__":
    main()
