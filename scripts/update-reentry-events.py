#!/usr/bin/env python3
"""Derive reentry events from CelesTrak SATCAT and upload to HF."""

import pandas as pd

from hf_dataset_utils import Pipeline

SATCAT_URL = "https://celestrak.org/pub/satcat.csv"
HF_REPO = "juliensimon/reentry-events"

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "norad_id": "NORAD catalog number -- sequential integer assigned by the 18th Space Defense Squadron at launch; primary key for cross-referencing with TLE databases and the SATCAT",
    "object_name": "Official name as listed in the NORAD catalog (e.g. 'COSMOS 1234 DEB'); rocket bodies typically include 'R/B' and debris fragments include 'DEB' in the name",
    "object_type": "Object classification: 'PAY' (payload/spacecraft), 'R/B' (rocket body or upper stage), 'DEB' (fragmentation debris), 'UNK' (unknown/unclassified)",
    "country_code": "Two- or three-letter country or organization code (e.g. 'US', 'CIS', 'PRC', 'ISS' for ISS-associated objects) identifying the launch owner as assigned in the SATCAT",
    "launch_date": "Date the object was launched into orbit (UTC); null for a small number of objects with incomplete catalog entries",
    "decay_date": "Date the object reentered Earth's atmosphere (UTC); for uncontrolled reentries this is the date radar tracking was lost; for controlled reentries it is the planned impact date",
    "period_min": "Last recorded orbital period in minutes before reentry; LEO objects typically 88-128 min; null if no orbital period was recorded in the final catalog entry",
    "inclination_deg": "Last recorded orbital inclination in degrees (0-180); the angle between the orbital plane and the equatorial plane; polar orbits ~90 deg, equatorial ~0 deg",
    "apogee_km": "Last recorded apogee (highest point) altitude above Earth's surface in km; null if not recorded; typically low and declining for objects near reentry",
    "perigee_km": "Last recorded perigee (lowest point) altitude above Earth's surface in km; null if not recorded; objects with perigee below ~200 km reenter within days to weeks",
    "rcs": "Radar cross-section in m-squared; proxy for object size used by space surveillance radars; null for many objects where RCS was not published or was too small to measure reliably",
    "days_in_orbit": "Number of days between launch and reentry (decay_date minus launch_date); null if either date is missing; ranges from 0 (immediate reentry) to tens of thousands of days",
    "decay_year": "Calendar year of reentry; derived from decay_date for efficient grouping and time-series analysis",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Catalog of objects that have reentered Earth's atmosphere, derived from the NORAD \
Satellite Catalog (SATCAT) via CelesTrak. Includes launch and decay dates, orbital \
parameters, and time in orbit.

Every object launched into Earth orbit eventually returns -- whether through natural \
orbital decay, controlled deorbits, or breakup. This dataset catalogs every object \
in the NORAD SATCAT that has a recorded decay date, providing a comprehensive history \
of atmospheric reentries including payloads, rocket bodies, and debris.

Atmospheric reentry is governed by the interplay between altitude, ballistic coefficient, \
and solar activity. Objects in low orbits (below ~400 km) experience enough atmospheric \
drag to decay within months or years, while those at 800+ km can persist for centuries. \
Solar maxima heat and expand the upper atmosphere, dramatically increasing drag on LEO \
objects. Controlled reentries of large objects target uninhabited ocean areas (the \
'spacecraft cemetery' in the South Pacific), while uncontrolled reentries carry a small \
but nonzero risk of surviving debris reaching populated areas.
"""


def main():
    print("Fetching SATCAT from CelesTrak...")
    df = pd.read_csv(SATCAT_URL)
    print(f"  {len(df):,} total objects")

    # Parse dates
    df["LAUNCH_DATE"] = pd.to_datetime(df["LAUNCH_DATE"], errors="coerce")
    df["DECAY_DATE"] = pd.to_datetime(df["DECAY_DATE"], errors="coerce")

    # Filter to objects that have reentered (DECAY_DATE is set)
    df = df[df["DECAY_DATE"].notna()].copy()
    print(f"  {len(df):,} reentered objects")

    # Select and rename columns
    df = df[["NORAD_CAT_ID", "OBJECT_NAME", "OBJECT_TYPE", "OWNER",
             "LAUNCH_DATE", "DECAY_DATE", "PERIOD", "INCLINATION",
             "APOGEE", "PERIGEE", "RCS"]].copy()

    df = df.rename(columns={
        "NORAD_CAT_ID": "norad_id",
        "OBJECT_NAME": "object_name",
        "OBJECT_TYPE": "object_type",
        "OWNER": "country_code",
        "LAUNCH_DATE": "launch_date",
        "DECAY_DATE": "decay_date",
        "PERIOD": "period_min",
        "INCLINATION": "inclination_deg",
        "APOGEE": "apogee_km",
        "PERIGEE": "perigee_km",
        "RCS": "rcs",
    })

    # Type coercion
    df["norad_id"] = df["norad_id"].astype("int32")
    for col in ["period_min", "inclination_deg", "apogee_km", "perigee_km"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Derived columns
    df["days_in_orbit"] = (df["decay_date"] - df["launch_date"]).dt.days
    df["decay_year"] = df["decay_date"].dt.year.astype("Int32")

    # Sort by decay date descending (most recent reentries first)
    df = df.sort_values("decay_date", ascending=False).reset_index(drop=True)

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # ── Compute stats for README ─────────────────────────────────────────
    n_total = len(df)
    n_payload = int((df["object_type"] == "PAY").sum())
    n_debris = int((df["object_type"] == "DEB").sum())
    n_rocket = int((df["object_type"] == "R/B").sum())
    median_days = int(df["days_in_orbit"].median()) if df["days_in_orbit"].notna().any() else 0
    year_min = int(df["decay_year"].min()) if df["decay_year"].notna().any() else 0
    year_max = int(df["decay_year"].max()) if df["decay_year"].notna().any() else 0
    top_countries = df["country_code"].value_counts().head(5)
    top_countries_str = ", ".join(
        f"{code} ({count:,})" for code, count in top_countries.items()
    )

    quick_stats = f"""\
- **{n_total:,}** reentered objects
- **{n_payload:,}** payloads, **{n_debris:,}** debris fragments, **{n_rocket:,}** rocket bodies
- Median time in orbit: **{median_days:,}** days
- Reentries span **{year_min}** to **{year_max}**
- Top countries: {top_countries_str}"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/reentry-events", split="train")
df = ds.to_pandas()

# Reentries per year
reentries_by_year = df.groupby("decay_year")["norad_id"].count()
print(reentries_by_year.tail(10))

# Longest-lived objects
longest = df.nlargest(10, "days_in_orbit")[["object_name", "days_in_orbit", "launch_date", "decay_date"]]
print(longest)

# Reentry trend over recent decades
import matplotlib.pyplot as plt
yearly = df[df["decay_year"] >= 1970].groupby("decay_year")["norad_id"].count()
yearly.plot(kind="bar", figsize=(14, 5), edgecolor="black", width=0.8)
plt.xlabel("Year")
plt.ylabel("Reentries")
plt.title("Annual Atmospheric Reentries")
plt.tight_layout()
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Reentry Events",
        description=DESCRIPTION,
        tags=["space", "reentry", "orbital-mechanics", "satellites",
              "debris", "open-data", "tabular-data", "parquet"],
        source_url="https://celestrak.org/pub/satcat.csv",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994",
        banner={
            "url": "https://images-assets.nasa.gov/image/iss071e439624/iss071e439624~medium.jpg",
            "alt": "An orbital sunrise illuminates the Earth's atmosphere, seen from the ISS",
            "credit": "NASA",
        },
        related_datasets=[
            "juliensimon/space-track-satcat",
            "juliensimon/space-launch-log",
            "juliensimon/space-track-tle-history",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=["norad_id", "period_min", "inclination_deg",
                     "apogee_km", "perigee_km", "rcs", "days_in_orbit"],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="reentry_events.parquet",
            min_rows=20_000,
            expected_columns=["norad_id", "object_name", "object_type",
                              "launch_date", "decay_date", "decay_year",
                              "days_in_orbit"],
            critical_columns=["norad_id", "object_name", "decay_date"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update reentry events: {n_total:,} objects",
        )
    print("Done.")


if __name__ == "__main__":
    main()
