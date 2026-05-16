#!/usr/bin/env python3
"""Fetch the Feng et al. 2018 ICME catalog from VizieR.

Source: VizieR J/ApJ/868/124/table6 — Feng X., Yao S., Li D., Li G., Yan X.
(2018), ApJ 868, 124. 219 Interplanetary Coronal Mass Ejections (ICMEs)
measured by both ACE and WIND from 1998 to 2011, drawn from the Cane &
Richardson (2003) and Richardson & Cane (2010) reference compilations.
Each entry records the shock arrival time, ICME body interval, min/max
solar wind speeds, and the magnetic cloud (MC) flag.
"""

from datetime import datetime, timedelta, timezone

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/feng-icme-catalog"

ADQL = 'SELECT * FROM "J/ApJ/868/124/table6"'

# VizieR returns datetime columns as integer seconds offset from the J2000.0
# epoch. We anchor at 2000-01-01 12:00:00 UTC to invert that mapping.
J2000_EPOCH = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

RENAME = {
    "seq": "sequence_number",
    "cc": "carbon_cold_flag",
    "shock": "shock_seconds_from_j2000",
    "start": "icme_start_seconds_from_j2000",
    "end": "icme_end_seconds_from_j2000",
    "vmin": "v_min_kms",
    "vmax": "v_max_kms",
    "mc?": "is_magnetic_cloud",
}

# Computed datetime columns derived from the *_seconds_from_j2000 raw values
DERIVED_COLUMNS = {
    "shock_arrival_utc": "Shock arrival time at L1 (UTC); the discontinuity that precedes the ICME magnetic structure",
    "icme_start_utc": "ICME body start time at L1 (UTC); flux-rope/sheath interval begins",
    "icme_end_utc": "ICME body end time at L1 (UTC); plasma signatures return to ambient solar wind",
    "shock_to_start_hours": "Hours between shock arrival and ICME body start (positive = shock leads body); the sheath region between shock and flux rope sits in this interval",
    "icme_duration_hours": "Duration of the ICME body from start to end (hours); typical ICMEs last 6-48 hours at 1 au",
}

COLUMN_DESCRIPTIONS = {
    "sequence_number": "Running sequence number in the Feng+ 2018 catalog (1-219)",
    "carbon_cold_flag": "Flag for ICMEs containing carbon-cold (CC) material as identified by Feng+ 2018: '*' = cold material detected, blank = standard ICME",
    **DERIVED_COLUMNS,
    "v_min_kms": "Minimum proton bulk speed measured by ACE/WIND during the ICME body (km/s); typical range 300-600 km/s",
    "v_max_kms": "Maximum proton bulk speed measured during the ICME body (km/s); fast ejecta exceed 1000 km/s",
    "is_magnetic_cloud": "Magnetic cloud (MC) flag: 'Yes' = ICME shows the classic MC signature (smooth, slow rotation of the magnetic field vector and depressed proton beta), 'No' = ICME ejecta without MC structure",
}

DESCRIPTION = """\
Feng et al. 2018 catalog of 219 Interplanetary Coronal Mass Ejections (ICMEs) measured \
in-situ at L1 by ACE and WIND between February 1998 and August 2011 — VizieR J/ApJ/868/124, \
drawn from the Cane & Richardson (2003) and Richardson & Cane (2010) reference compilations.

ICMEs are the in-situ manifestation of coronal mass ejections after multi-day propagation \
through the heliosphere. At L1, an ICME passage is identified by a shock front (sudden density \
and velocity jump), followed hours later by the ICME body — a region of depressed proton \
temperature, low plasma beta, and (for ~half of events) a magnetic-cloud signature with smooth \
rotation of the magnetic field vector. ICMEs are the dominant driver of major non-recurrent \
geomagnetic storms, and their L1 in-situ catalog is the empirical baseline for space-weather \
forecasting model validation.

Each row records the sequence number, ICME shock arrival time at L1, ICME body start and end \
times, minimum and maximum proton bulk speeds during the ICME interval, a magnetic cloud (MC) \
flag, and the Feng+ 2018 carbon-cold (CC) classification — a low-charge-state filament-origin \
diagnostic that this paper introduced. Derived columns convert the integer-seconds-from-J2000 \
raw timestamps to ISO UTC datetimes and compute the shock-to-body delay and ICME body duration.

Use this dataset alongside juliensimon/cdaw-lasco-cme-catalog (the upstream Sun-side LASCO CME \
identifications that drive ICMEs), juliensimon/donki-space-weather-events (NASA's curated \
CME/ICME/storm catalog), juliensimon/omni-solar-wind-parameters (continuous L1 solar wind for \
ICME passage validation), juliensimon/dst-index (geomagnetic storm response), and \
juliensimon/parker-solar-probe-encounters / juliensimon/solar-orbiter-encounters (multi-spacecraft \
ICME tracking).\
"""


def _to_datetime(seconds_from_j2000):
    if pd.isna(seconds_from_j2000):
        return pd.NaT
    return J2000_EPOCH + timedelta(seconds=int(seconds_from_j2000))


def main():
    print("Fetching Feng+ 2018 ICME catalog from VizieR J/ApJ/868/124...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} ICMEs fetched")

    df.columns = [c.strip().lower() for c in df.columns]
    df = df.rename(columns=RENAME)

    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip().replace(
            {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
        )

    # Convert raw integer seconds to UTC datetimes
    df["shock_arrival_utc"] = df["shock_seconds_from_j2000"].apply(_to_datetime)
    df["icme_start_utc"] = df["icme_start_seconds_from_j2000"].apply(_to_datetime)
    df["icme_end_utc"] = df["icme_end_seconds_from_j2000"].apply(_to_datetime)

    df["shock_to_start_hours"] = (
        df["icme_start_seconds_from_j2000"] - df["shock_seconds_from_j2000"]
    ) / 3600.0
    df["icme_duration_hours"] = (
        df["icme_end_seconds_from_j2000"] - df["icme_start_seconds_from_j2000"]
    ) / 3600.0

    # Drop the raw seconds columns now that we have datetime equivalents
    df = df.drop(columns=[
        "shock_seconds_from_j2000",
        "icme_start_seconds_from_j2000",
        "icme_end_seconds_from_j2000",
    ])

    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    n_total = len(df)
    n_mc = int((df["is_magnetic_cloud"] == "Yes").sum()) if "is_magnetic_cloud" in df.columns else 0
    n_cc = int((df["carbon_cold_flag"] == "*").sum()) if "carbon_cold_flag" in df.columns else 0

    dur = pd.to_numeric(df["icme_duration_hours"], errors="coerce").dropna()
    dur_line = f"\n- ICME body durations: median **{dur.median():.1f} h**, range **{dur.min():.1f}** to **{dur.max():.1f}** hours" if len(dur) else ""

    speed_line = ""
    if "v_max_kms" in df.columns:
        vmax = pd.to_numeric(df["v_max_kms"], errors="coerce").dropna()
        if len(vmax):
            speed_line = f"\n- Peak ICME speeds: median **{vmax.median():.0f} km/s**, range **{vmax.min():.0f}** to **{vmax.max():.0f}** km/s"

    quick_stats = f"""\
- **{n_total}** Interplanetary Coronal Mass Ejections (ICMEs) measured in-situ at L1 by ACE and WIND
- **{n_mc}** events classified as magnetic clouds (smooth flux-rope structure)
- **{n_cc}** ICMEs containing carbon-cold (CC) material (Feng+ 2018 filament-origin diagnostic){dur_line}{speed_line}
- Catalog covers **1998 February through 2011 August** — spans solar cycle 23 maximum and the cycle 23/24 minimum"""

    usage = """\
```python
from datasets import load_dataset
import matplotlib.pyplot as plt

df = load_dataset("juliensimon/feng-icme-catalog", split="train").to_pandas()
df["icme_start_utc"] = df["icme_start_utc"].astype("datetime64[ns, UTC]")

# Annual ICME count vs solar cycle (cycle 23 max ~2001-2002)
df["year"] = df["icme_start_utc"].dt.year
yearly = df.groupby("year").size()
mc_yearly = df[df["is_magnetic_cloud"] == "Yes"].groupby("year").size()
fig, ax = plt.subplots(figsize=(10, 5))
yearly.plot(ax=ax, label="All ICMEs", marker="o")
mc_yearly.plot(ax=ax, label="Magnetic Clouds", marker="s", color="red")
ax.set_ylabel("Events per year")
ax.set_title("L1 ICME rate vs solar cycle (Feng+ 2018, 1998-2011)")
ax.legend()
plt.tight_layout()
plt.show()

# Magnetic cloud vs non-MC ICMEs: speed distribution
fig, ax = plt.subplots(figsize=(8, 5))
df[df["is_magnetic_cloud"] == "Yes"]["v_max_kms"].hist(
    bins=30, alpha=0.6, label="MC", ax=ax)
df[df["is_magnetic_cloud"] == "No"]["v_max_kms"].hist(
    bins=30, alpha=0.6, label="non-MC", ax=ax)
ax.set_xlabel("Peak ICME speed (km/s)")
ax.legend()
plt.tight_layout()
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="ACE/WIND ICME Catalog (Feng 2018)",
        description=DESCRIPTION,
        tags=["space", "heliophysics", "space-weather", "icme",
              "interplanetary-coronal-mass-ejection", "ace", "wind",
              "magnetic-clouds", "vizier", "open-data",
              "tabular-data", "parquet"],
        source_url="https://cdsarc.cds.unistra.fr/viz-bin/cat/J/ApJ/868/124",
        task_categories=["tabular-classification", "time-series-forecasting"],
        collection_url="https://huggingface.co/collections/juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70",
        banner={
            "url": "https://images-assets.nasa.gov/image/brief-outburst_16760026566_o/brief-outburst_16760026566_o~medium.jpg",
            "alt": "Solar eruption captured by NASA's Solar Dynamics Observatory",
            "credit": "NASA/SDO",
        },
        related_datasets=[
            "juliensimon/cdaw-lasco-cme-catalog",
            "juliensimon/donki-space-weather-events",
            "juliensimon/omni-solar-wind-parameters",
            "juliensimon/dst-index",
            "juliensimon/parker-solar-probe-encounters",
            "juliensimon/solar-orbiter-encounters",
        ],
    ) as p:
        df_clean = p.clean(
            df,
            numeric=[
                "sequence_number", "v_min_kms", "v_max_kms",
                "shock_to_start_hours", "icme_duration_hours",
            ],
        )
        p.publish(
            df_clean,
            filename="feng_icme_catalog.parquet",
            min_rows=200,
            expected_columns=["sequence_number", "icme_start_utc",
                              "icme_end_utc", "is_magnetic_cloud"],
            critical_columns=["sequence_number", "icme_start_utc"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Feng ICME catalog: {n_total} ICMEs",
        )
    print("Done.")


if __name__ == "__main__":
    main()
