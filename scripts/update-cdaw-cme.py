#!/usr/bin/env python3
"""Fetch the SOHO/LASCO CME catalog from NASA CDAW.

Source: NASA CDAW Data Center, https://cdaw.gsfc.nasa.gov/CME_list/.
Universal text export `univ_all.txt` — every coronal mass ejection (CME)
manually identified in SOHO/LASCO C2 and C3 white-light images from 1996
through the current data release. Maintained by the SOHO/LASCO team at the
US Naval Research Laboratory and NASA Goddard.
"""

import re
from datetime import datetime

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

HF_REPO = "juliensimon/cdaw-lasco-cme-catalog"
SOURCE_URL = "https://cdaw.gsfc.nasa.gov/CME_list/UNIVERSAL/text_ver/univ_all.txt"

COLUMN_DESCRIPTIONS = {
    "date_utc": "First-appearance date of the CME in the LASCO C2 field of view (UTC)",
    "time_utc": "First-appearance time (UTC, HH:MM:SS); together with date_utc this is the closest available proxy for CME launch time",
    "datetime_utc": "Combined first-appearance datetime in UTC (date_utc + time_utc)",
    "year": "Calendar year of first appearance (integer, derived from datetime_utc)",
    "central_position_angle_deg": "Central position angle (degrees, 0-360); measured counterclockwise from solar north, marking the angular center of the CME front; null for halo CMEs (full-360 events)",
    "angular_width_deg": "Angular width of the CME in the plane of sky (degrees); width = 360 marks a 'halo CME', which are the most geo-effective and often Earth-directed",
    "linear_speed_kms": "Linear-fit projected speed in the plane of sky (km/s); CMEs span ~50 to >3000 km/s, with the fastest events driving strongest geomagnetic storms",
    "second_order_speed_initial_kms": "Speed (km/s) from a quadratic time-distance fit, evaluated at first appearance",
    "second_order_speed_final_kms": "Speed (km/s) from a quadratic fit at the last observed measurement",
    "second_order_speed_20rs_kms": "Speed (km/s) from a quadratic fit evaluated at 20 solar radii — closer to the constant-speed asymptote in the outer corona",
    "acceleration_ms2": "Plane-of-sky acceleration (m/s^2) from the quadratic fit; positive = accelerating outward, negative = decelerating",
    "mass_g": "Estimated CME mass in grams; an asterisk in the source file (now stripped) marked a poor mass measurement; null where mass is not measured",
    "mass_quality_flag": "True if the source file marked the mass measurement as poor quality (asterisk in the raw catalog)",
    "kinetic_energy_erg": "Estimated CME kinetic energy in erg = mass * (linear_speed)^2 / 2; null where mass is not measured",
    "kinetic_energy_quality_flag": "True if the source file marked the kinetic energy as poor quality",
    "remarks": "Free-text annotation: data-quality notes ('Poor Event', 'Very Poor Event'), instrument coverage ('Only C2', 'Only C3'), and event-curation notes ('Newly inserted on YYYY/MM/DD')",
    "is_halo": "True if the CME is a halo event (width = 360 deg) — most likely to be Earth-directed and geo-effective",
    "is_poor_event": "True if the remarks contain 'Poor Event' or 'Very Poor Event' — measurements should be treated with caution",
}

DESCRIPTION = """\
The SOHO/LASCO CME Catalog from the NASA CDAW Data Center — every coronal mass ejection \
manually identified in the SOHO Large Angle and Spectrometric Coronagraph (LASCO) C2 and C3 \
white-light coronagraph images from January 1996 through the current data release.

Coronal mass ejections are the largest energy-release events in the heliosphere: ~10^16 g of \
coronal plasma launched at 50-3000 km/s, carrying enough magnetic energy to drive the \
strongest geomagnetic storms when directed at Earth. The CDAW catalog is the canonical \
human-curated CME record used for solar-cycle statistics, space-weather forecasting model \
training, and event-correlation studies with in-situ measurements at L1 (e.g. OMNI, DSCOVR) \
and at planetary missions. Each entry records the CME first-appearance time in the LASCO C2 \
field of view, position angle and angular width on the plane of sky, multiple speed estimates \
(linear and second-order fits), acceleration, estimated mass and kinetic energy, and \
curator-added remarks flagging data quality and instrument coverage.

Halo CMEs (angular_width = 360 degrees) are the operationally critical subset: their full-360 \
appearance in coronagraph images indicates the CME is launched along the Sun-spacecraft line, \
either Earth-directed (driving terrestrial storms) or anti-Earth-directed (back-side events \
detectable only at L1 or planetary spacecraft). The is_halo column flags these directly. The \
is_poor_event flag distills the most common quality concern from the remarks field for filtering.

This dataset complements juliensimon/donki-space-weather-events (NASA DONKI's curated CME \
catalog, used by NOAA SWPC), juliensimon/space-weather-indices (Kp/Ap/F10.7 indices for \
geo-effective response), juliensimon/omni-solar-wind-parameters (in-situ solar wind at L1 for \
CME arrival validation), juliensimon/dst-index (Dst geomagnetic storm intensity), \
juliensimon/solar-flares (the X-ray events typically associated with CME launches), and \
juliensimon/parker-solar-probe-encounters (PSP in-situ CME observations).\
"""


_PLACEHOLDER = re.compile(r"^-+$")


def _to_number(value: str) -> tuple[float | None, bool]:
    """Parse a CDAW numeric cell, stripping the quality asterisk if present."""
    value = value.strip()
    if not value or _PLACEHOLDER.match(value):
        return None, False
    poor = value.endswith("*")
    cleaned = value.rstrip("*").strip()
    try:
        return float(cleaned), poor
    except ValueError:
        return None, poor


def parse_catalog(text: str) -> pd.DataFrame:
    rows = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        # The header lines all start with at least one leading-space block before
        # a non-numeric token. Data lines start with a 4-digit year.
        first_token = line.lstrip().split(" ", 1)[0]
        if not re.match(r"^\d{4}/\d{2}/\d{2}$", first_token):
            continue

        # The first 11 fields are whitespace-separated; remarks (col 12) absorbs the rest.
        parts = line.split(None, 11)
        if len(parts) < 11:
            continue
        remarks = parts[11].strip() if len(parts) > 11 else ""

        date_str, time_str = parts[0], parts[1]
        try:
            dt = datetime.strptime(f"{date_str} {time_str}", "%Y/%m/%d %H:%M:%S")
        except ValueError:
            continue

        cpa_str = parts[2].strip()
        is_halo = cpa_str.lower() == "halo"
        central_pa = None if is_halo else _to_number(cpa_str)[0]

        width = _to_number(parts[3])[0]
        linear_speed = _to_number(parts[4])[0]
        v_initial = _to_number(parts[5])[0]
        v_final = _to_number(parts[6])[0]
        v_20rs = _to_number(parts[7])[0]
        accel = _to_number(parts[8])[0]
        mass, mass_poor = _to_number(parts[9])
        ke, ke_poor = _to_number(parts[10])

        rows.append({
            "date_utc": dt.date(),
            "time_utc": dt.time(),
            "datetime_utc": dt,
            "year": dt.year,
            "central_position_angle_deg": central_pa,
            "angular_width_deg": width,
            "linear_speed_kms": linear_speed,
            "second_order_speed_initial_kms": v_initial,
            "second_order_speed_final_kms": v_final,
            "second_order_speed_20rs_kms": v_20rs,
            "acceleration_ms2": accel,
            "mass_g": mass,
            "mass_quality_flag": mass_poor,
            "kinetic_energy_erg": ke,
            "kinetic_energy_quality_flag": ke_poor,
            "remarks": remarks,
            "is_halo": is_halo or (width is not None and width >= 359.9),
            "is_poor_event": "poor event" in remarks.lower(),
        })

    df = pd.DataFrame(rows)
    df["datetime_utc"] = pd.to_datetime(df["datetime_utc"], utc=True)
    return df


def main():
    print(f"Fetching CDAW SOHO/LASCO CME catalog from {SOURCE_URL}...")
    resp = requests.get(SOURCE_URL, timeout=180)
    resp.raise_for_status()
    df = parse_catalog(resp.text)
    print(f"  {len(df):,} CMEs parsed")

    n_total = len(df)
    n_halo = int(df["is_halo"].sum())
    n_poor = int(df["is_poor_event"].sum())
    speed = df["linear_speed_kms"].dropna()
    fastest = float(speed.max()) if len(speed) else 0.0
    median_speed = float(speed.median()) if len(speed) else 0.0
    span_years = int(df["year"].max() - df["year"].min()) + 1 if len(df) else 0

    quick_stats = f"""\
- **{n_total:,}** coronal mass ejections manually identified in SOHO/LASCO C2 and C3 images
- **{n_halo:,}** halo CMEs (angular width = 360 deg) — the geo-effective Earth-directed subset
- Median linear speed: **{median_speed:.0f} km/s** | fastest recorded: **{fastest:.0f} km/s**
- Catalog spans **{span_years} years** across two solar cycles and counting (1996+)
- **{n_poor:,}** events flagged by curators as 'Poor Event' or 'Very Poor Event' — exclude from statistical analyses"""

    usage = """\
```python
from datasets import load_dataset
import matplotlib.pyplot as plt

df = load_dataset("juliensimon/cdaw-lasco-cme-catalog", split="train").to_pandas()
df["datetime_utc"] = df["datetime_utc"].astype("datetime64[ns, UTC]")

# Annual CME counts traces the solar cycle (peak ~2000 and ~2014)
yearly = df.groupby("year").size()
halo_yearly = df[df["is_halo"]].groupby("year").size()
fig, ax = plt.subplots(figsize=(11, 5))
yearly.plot(ax=ax, label="All CMEs")
halo_yearly.plot(ax=ax, label="Halo CMEs", color="red")
ax.set_ylabel("CMEs per year")
ax.set_title("SOHO/LASCO CME rate vs solar cycle (1996+)")
ax.legend()
plt.tight_layout()
plt.show()

# Fastest 10 halo CMEs — the operationally most significant events
fast_halo = (df[df["is_halo"] & ~df["is_poor_event"]]
             .nlargest(10, "linear_speed_kms")
             [["datetime_utc", "linear_speed_kms", "angular_width_deg", "remarks"]])
print(fast_halo)
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="SOHO/LASCO Coronal Mass Ejection Catalog (CDAW)",
        description=DESCRIPTION,
        tags=["space", "heliophysics", "space-weather", "cme", "coronal-mass-ejection",
              "soho", "lasco", "nasa", "cdaw", "open-data",
              "tabular-data", "parquet"],
        source_url=SOURCE_URL,
        task_categories=["tabular-classification", "time-series-forecasting"],
        update_schedule="Weekly",
        collection_url="https://huggingface.co/collections/juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70",
        banner={
            "url": "https://images-assets.nasa.gov/image/brief-outburst_16760026566_o/brief-outburst_16760026566_o~medium.jpg",
            "alt": "Solar eruption captured by NASA's Solar Dynamics Observatory",
            "credit": "NASA/SDO",
        },
        related_datasets=[
            "juliensimon/donki-space-weather-events",
            "juliensimon/space-weather-indices",
            "juliensimon/omni-solar-wind-parameters",
            "juliensimon/dst-index",
            "juliensimon/solar-flare-events",
            "juliensimon/parker-solar-probe-encounters",
        ],
    ) as p:
        df_clean = p.clean(
            df,
            numeric=[
                "central_position_angle_deg", "angular_width_deg",
                "linear_speed_kms",
                "second_order_speed_initial_kms",
                "second_order_speed_final_kms",
                "second_order_speed_20rs_kms",
                "acceleration_ms2",
                "mass_g", "kinetic_energy_erg",
                "year",
            ],
        )
        p.publish(
            df_clean,
            filename="cdaw_lasco_cme_catalog.parquet",
            min_rows=20_000,
            expected_columns=["datetime_utc", "angular_width_deg",
                              "linear_speed_kms", "is_halo"],
            critical_columns=["datetime_utc"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update CDAW LASCO CME catalog: {n_total:,} events",
        )
    print("Done.")


if __name__ == "__main__":
    main()
