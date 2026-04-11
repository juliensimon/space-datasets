#!/usr/bin/env python3
"""Fetch IERS Earth Orientation Parameters and upload to HF.

Source: IERS finals2000A series from the Earth Orientation Centre.
Includes polar motion, UT1-UTC, length of day, and nutation offsets.
"""

import io

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

IERS_URL = "https://datacenter.iers.org/data/csv/finals2000A.data.csv"
HF_REPO = "juliensimon/iers-earth-orientation"

# ── Column mapping ───────────────────────────────────────────────────
RENAME_RULES = {
    "mjd": "mjd",
    "x_pole": "x_pole_arcsec", "x": "x_pole_arcsec", "x_arcsec": "x_pole_arcsec",
    "y_pole": "y_pole_arcsec", "y": "y_pole_arcsec", "y_arcsec": "y_pole_arcsec",
    "sigma_x_pole": "sigma_x_pole_arcsec",
    "sigma_y_pole": "sigma_y_pole_arcsec",
    "ut1-utc": "ut1_utc_sec", "ut1_utc": "ut1_utc_sec",
    "sigma_ut1-utc": "sigma_ut1_utc_sec",
    "lod": "lod_ms",
    "dx": "dx_mas",
    "dy": "dy_mas",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "date": "Calendar date in UTC of the EOP measurement; daily cadence from 1962-01-01 to present; values after the last bulletin date are IERS short-term predictions, not observations",
    "mjd": "Modified Julian Date = Julian Date - 2400000.5; a compact decimal day count used throughout astronomy and geodesy; J2000.0 corresponds to MJD 51544.5; enables direct arithmetic on time differences without calendar conversions",
    "x_pole_arcsec": "x-component of polar motion in arcseconds; eastward offset of Earth's instantaneous rotation pole from the IERS Reference Pole along the Greenwich meridian; typical range +/-0.5 arcsec; a 1 mas error causes ~3 cm surface positioning error",
    "y_pole_arcsec": "y-component of polar motion in arcseconds; offset of Earth's rotation pole along the 90 deg W meridian; required together with x_pole_arcsec to transform between celestial (ICRF) and terrestrial (ITRF) coordinate frames",
    "sigma_x_pole_arcsec": "1-sigma formal uncertainty on x_pole_arcsec; reflects quality of the combined VLBI/SLR/GPS solution; typically 0.01-0.1 mas for modern observations",
    "sigma_y_pole_arcsec": "1-sigma formal uncertainty on y_pole_arcsec; same origin and magnitude as sigma_x_pole_arcsec",
    "ut1_utc_sec": "Difference UT1 - UTC in seconds; UT1 tracks Earth's actual rotational angle while UTC uses fixed SI seconds; bounded to +/-0.9 s by periodic leap-second insertions; essential for sidereal time and spacecraft antenna pointing calculations",
    "sigma_ut1_utc_sec": "1-sigma formal uncertainty on ut1_utc_sec; typically sub-millisecond for recent observations",
    "lod_ms": "Excess length of day above 86400 SI seconds, in milliseconds; positive = Earth rotating slower than nominal; reflects the instantaneous time derivative of UT1-UTC; driven mainly by atmospheric angular momentum exchange on sub-annual timescales",
    "dx_mas": "Celestial pole offset dX in milliarcseconds; observed deviation of the celestial intermediate pole from the IAU 2000/2006 precession-nutation model along the X axis; corrects for unpredictable fluid-core free nutation with ~430-day period",
    "dy_mas": "Celestial pole offset dY in milliarcseconds; observed deviation along the Y axis complementing dX; together dX and dY provide the residual nutation corrections needed for the highest-precision celestial mechanics and VLBI analysis",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Earth Orientation Parameters (EOP) from the IERS finals2000A series. Includes \
polar motion, UT1-UTC, length of day, and nutation offsets. Updated daily.

Earth Orientation Parameters describe the irregularities in Earth's rotation and \
the motion of its poles. These parameters are essential for transforming between \
celestial and terrestrial reference frames, which is critical for satellite operations, \
GPS/GNSS positioning, telescope and antenna tracking, deep-space navigation, and geodesy.

The IERS finals2000A series combines observed values (from VLBI, SLR, GPS) with \
predictions extending ~1 year into the future.

Earth's rotation is not uniform. The planet's spin axis wanders relative to both the \
crust (polar motion) and the celestial reference frame (precession and nutation), while \
the rotation rate itself fluctuates on timescales from hours to millennia. Polar motion \
consists of two main components: the Chandler wobble (a free oscillation with a period \
of approximately 433 days and amplitude of 0.1-0.2 arcseconds, equivalent to 3-6 meters \
at the pole) and an annual oscillation driven by seasonal redistribution of atmospheric \
and oceanic mass. Superimposed on these is a secular drift of the pole toward roughly \
80 degrees W longitude at about 10 cm/year, driven by post-glacial rebound of the mantle.

The UT1-UTC difference tracks the accumulated departure of Earth's rotational angle from \
atomic time. Earth's rotation is gradually slowing due to tidal dissipation (primarily \
lunar tides in the oceans), causing UT1 to drift behind UTC at an average rate of roughly \
2 milliseconds per day. This secular trend is punctuated by irregular decadal fluctuations \
attributed to core-mantle coupling, and by shorter-period variations from atmospheric \
angular momentum exchange. When |UT1-UTC| approaches 0.9 seconds, the IERS directs the \
insertion of a leap second.
"""


def main():
    print("Fetching IERS Earth Orientation Parameters...")
    resp = requests.get(IERS_URL, timeout=120)
    resp.raise_for_status()

    # IERS CSV uses semicolons as separator
    try:
        df = pd.read_csv(io.StringIO(resp.text), sep=';')
    except Exception:
        df = pd.read_csv(io.StringIO(resp.text))

    print(f"  {len(df):,} rows, columns: {list(df.columns)[:10]}...")

    # Create date column from Year/Month/Day if present
    year_col = [c for c in df.columns if c.strip().lower() == 'year']
    month_col = [c for c in df.columns if c.strip().lower() == 'month']
    day_col = [c for c in df.columns if c.strip().lower() == 'day']

    if year_col and month_col and day_col:
        df["date"] = pd.to_datetime(
            df[year_col[0]].astype(int).astype(str) + "-" +
            df[month_col[0]].astype(int).astype(str).str.zfill(2) + "-" +
            df[day_col[0]].astype(int).astype(str).str.zfill(2),
            errors="coerce",
        )

    # Build rename mapping (guard all column accesses)
    rename_map = {}
    for col in df.columns:
        cl = col.strip().lower()
        if cl in RENAME_RULES:
            rename_map[col] = RENAME_RULES[cl]

    if rename_map:
        df = df.rename(columns=rename_map)

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    df = df.sort_values("date").reset_index(drop=True) if "date" in df.columns else df

    # ── Domain-specific stats for README ─────────────────────────────
    n = len(df)
    date_min = df["date"].min().strftime("%Y-%m-%d") if "date" in df.columns else "N/A"
    date_max = df["date"].max().strftime("%Y-%m-%d") if "date" in df.columns else "N/A"
    ut1_range = ""
    if "ut1_utc_sec" in df.columns:
        recent = df[df["date"] > "2020-01-01"] if "date" in df.columns else df
        ut1_min = recent["ut1_utc_sec"].min()
        ut1_max = recent["ut1_utc_sec"].max()
        ut1_range = f"\n- UT1-UTC range (since 2020): {ut1_min:.4f} to {ut1_max:.4f} s"

    quick_stats = f"""\
- **{n:,}** daily records ({date_min} to {date_max}){ut1_range}"""

    usage = f"""\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/iers-earth-orientation", split="train")
df = ds.to_pandas()

# Recent UT1-UTC values
recent = df[df["date"] > "2025-01-01"].sort_values("date")
print(recent[["date", "ut1_utc_sec", "x_pole_arcsec", "y_pole_arcsec"]])

# Polar motion scatter plot
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(8, 8))
ax.scatter(df["x_pole_arcsec"], df["y_pole_arcsec"], s=0.5, alpha=0.3)
ax.set_xlabel("x pole (arcsec)")
ax.set_ylabel("y pole (arcsec)")
ax.set_title("Polar Motion")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="IERS Earth Orientation Parameters",
        description=DESCRIPTION,
        tags=["space", "earth-orientation", "iers", "geodesy", "ut1",
              "polar-motion", "open-data", "tabular-data", "parquet"],
        source_url="https://www.iers.org/",
        update_schedule="Daily at 13:00 UTC via [GitHub Actions](https://github.com/juliensimon/space-datasets).",
        task_categories=["tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70",
        banner={
            "url": "https://images-assets.nasa.gov/image/iss072e159172/iss072e159172~medium.jpg",
            "alt": "Aurora borealis blankets the Earth, seen from the ISS",
            "credit": "NASA",
        },
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "mjd", "x_pole_arcsec", "y_pole_arcsec",
                "sigma_x_pole_arcsec", "sigma_y_pole_arcsec",
                "ut1_utc_sec", "sigma_ut1_utc_sec",
                "lod_ms", "dx_mas", "dy_mas",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="iers_earth_orientation.parquet",
            min_rows=10000,
            expected_columns=["date", "x_pole_arcsec", "y_pole_arcsec", "ut1_utc_sec"],
            critical_columns=["date", "x_pole_arcsec", "y_pole_arcsec"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update IERS EOP: {n:,} records",
        )
    print("Done.")


if __name__ == "__main__":
    main()
