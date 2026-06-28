#!/usr/bin/env python3
"""Fetch NORAD SATCAT from CelesTrak and upload to HF."""

import io
import time

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

SATCAT_URL = "https://celestrak.org/pub/satcat.csv"
HF_REPO = "juliensimon/space-track-satcat"

# ── Column mapping ───────────────────────────────────────────────────
RENAME = {
    "OBJECT_NAME": "object_name",
    "OBJECT_ID": "intl_designator",
    "NORAD_CAT_ID": "norad_id",
    "OBJECT_TYPE": "object_type",
    "OPS_STATUS_CODE": "ops_status",
    "OWNER": "owner",
    "LAUNCH_DATE": "launch_date",
    "LAUNCH_SITE": "launch_site",
    "DECAY_DATE": "decay_date",
    "PERIOD": "period_min",
    "INCLINATION": "inclination",
    "APOGEE": "apogee_km",
    "PERIGEE": "perigee_km",
    "RCS": "rcs_m2",
    "DATA_STATUS_CODE": "data_status",
    "ORBIT_CENTER": "orbit_center",
    "ORBIT_TYPE": "orbit_type",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "object_name": "Official name as listed in the NORAD catalog (e.g. 'STARLINK-1234', 'ISS (ZARYA)'); rocket bodies include 'R/B', debris includes 'DEB'",
    "intl_designator": "COSPAR international designator in the format YYYY-NNNX (e.g. '2024-123A'): launch year, sequential launch number within that year, and piece letter (A = primary payload, B = first secondary, etc.); assigned by COSPAR",
    "norad_id": "NORAD catalog number -- sequential integer assigned by the 18th Space Defense Squadron at launch; primary key for cross-referencing with TLE databases",
    "object_type": "Object classification: PAY (payload/spacecraft), R/B (rocket body or upper stage), DEB (fragmentation debris), UNK (unknown/unclassified)",
    "ops_status": "Operational status code from the Space-Track catalog: + (operational), - (non-operational), P (partially operational), B (backup/standby), S (spare), X (extended mission), D (decayed), ? (unknown); null for decayed or historically untracked objects",
    "owner": "ISO 3166-based two-letter country code or special organization code (e.g. 'US', 'RU', 'CN', 'ESA', 'ISS') identifying the launch owner or responsible party",
    "launch_date": "Date the object was launched into orbit (UTC); null for a small number of objects with incomplete catalog records",
    "launch_site": "Encoded launch site identifier (e.g. 'AFETR' = Cape Canaveral, 'TYMSC' = Baikonur, 'TTMTR' = Tanegashima); null if unknown",
    "decay_date": "Date of atmospheric reentry or decay (UTC); null for objects still in orbit -- a non-null value means the object has reentered",
    "period_min": "Current orbital period in minutes; LEO: 88-128 min, MEO: 128-600 min, GEO: ~1436 min (24 h), HEO: highly variable; null for decayed objects",
    "inclination": "Orbital inclination in degrees (0-180); angle between the orbital plane and Earth's equatorial plane; 0 deg = equatorial, 90 deg = polar, >90 deg = retrograde",
    "apogee_km": "Apogee altitude (highest point of orbit) above Earth's surface in km; null for decayed objects or those with incomplete orbital data",
    "perigee_km": "Perigee altitude (lowest point of orbit) above Earth's surface in km; objects with perigee below ~200 km reenter within weeks; null for decayed objects",
    "rcs_m2": "Radar cross-section in m2; proxy for object physical size as observed by surveillance radars; null for objects too small to characterize or where data was not published",
    "data_status": "Catalog data quality flag indicating whether the entry has full orbital data (S = standard, D = no current elements) or is a historical record; null in many cases",
    "orbit_center": "Central gravitational body code (e.g. 'EA' = Earth, 'MO' = Moon); nearly all objects are Earth-orbiting; useful for filtering lunar or Lagrange-point objects",
    "orbit_type": "Orbit regime classification (e.g. 'LEO' = low Earth orbit <2000 km, 'MEO' = medium Earth orbit, 'GEO' = geostationary, 'HEO' = highly elliptical, 'DSO' = deep space); null for many historical objects",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Complete NORAD Satellite Catalog from CelesTrak, tracking every object cataloged \
by the 18th Space Defense Squadron since 1957. Includes active satellites, defunct \
spacecraft, rocket bodies, and debris.

The SATCAT (Satellite Catalog) is the authoritative registry of all artificial \
objects in Earth orbit and beyond. Each entry includes launch metadata, orbital \
parameters, operational status, and physical characteristics. This dataset mirrors \
the full catalog daily from CelesTrak.

The satellite catalog traces its origins to the dawn of the Space Age: the first \
entry is Sputnik 1, launched on October 4, 1957. Every object large enough to be \
tracked by the US Space Surveillance Network (typically >10 cm in LEO, >1 m in GEO) \
receives a NORAD catalog number and an international designator (COSPAR ID). The \
catalog includes not just active satellites but the full historical record of rocket \
upper stages, mission-related debris, and fragments from breakup events.

The operational status codes provide a coarse but useful picture of spacecraft health. \
The radar cross-section (RCS) field, while often approximate, gives insight into \
object size -- critical for collision probability assessments. Orbital parameters \
(period, inclination, apogee, perigee) describe the object's trajectory and are \
updated as new tracking observations are processed.

This dataset underpins a wide range of applications: space traffic management, \
conjunction assessment and collision avoidance, orbital debris population studies, \
launch history analysis, spectrum management, and insurance risk modeling.
"""


def _fetch_with_retry(url, retries=3, timeout=60):
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp
        except Exception as e:
            if attempt == retries:
                raise
            wait = 2 ** attempt
            print(f"  Attempt {attempt} failed ({e}), retrying in {wait}s...")
            time.sleep(wait)


def main():
    print("Fetching SATCAT from CelesTrak...")
    resp = _fetch_with_retry(SATCAT_URL)
    df = pd.read_csv(io.StringIO(resp.text))
    print(f"  {len(df):,} objects")

    # Clean up types
    df["LAUNCH_DATE"] = pd.to_datetime(df["LAUNCH_DATE"], errors="coerce")
    df["DECAY_DATE"] = pd.to_datetime(df["DECAY_DATE"], errors="coerce")
    df["NORAD_CAT_ID"] = df["NORAD_CAT_ID"].astype("int32")
    df["RCS"] = pd.to_numeric(df["RCS"], errors="coerce")

    df = df.rename(columns=RENAME)

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # ── Stats for README ──────────────────────────────────────────────
    n_total = len(df)
    n_payload = int((df["object_type"] == "PAY").sum())
    n_debris = int((df["object_type"] == "DEB").sum())
    n_rocket = int((df["object_type"] == "R/B").sum())
    n_active = int(df["ops_status"].isin(["+", "P", "B", "S", "X"]).sum())
    n_decayed = int(df["decay_date"].notna().sum())
    n_owners = df["owner"].nunique()

    quick_stats = f"""\
- **{n_total:,}** cataloged objects
- **{n_payload:,}** payloads, **{n_debris:,}** debris fragments, **{n_rocket:,}** rocket bodies
- **{n_active:,}** active or partially operational
- **{n_decayed:,}** objects have decayed/reentered
- **{n_owners}** distinct owner codes"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/space-track-satcat", split="train")
df = ds.to_pandas()

# Active payloads only
active = df[(df["object_type"] == "PAY") & (df["ops_status"] == "+")]
print(f"{len(active):,} active payloads")

# Launches per year
df["year"] = df["launch_date"].dt.year
launches_by_year = df.groupby("year")["norad_id"].count()

# Objects by owner
top_owners = df["owner"].value_counts().head(10)

# LEO vs GEO
import matplotlib.pyplot as plt
leo = df[(df["perigee_km"] < 2000) & (df["perigee_km"] > 0)]
geo = df[(df["perigee_km"] > 35000) & (df["apogee_km"] < 36500)]
print(f"LEO: {len(leo):,}, GEO: {len(geo):,}")
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="NORAD Satellite Catalog (SATCAT)",
        description=DESCRIPTION,
        tags=["space", "satellite", "norad", "celestrak", "orbital-mechanics",
              "space-track", "open-data", "ssa", "debris", "earth-observation",
              "tabular-data", "parquet"],
        source_url="https://celestrak.org/pub/satcat.csv",
        license="other",
        license_name="celestrak-usage-policy",
        license_link="https://celestrak.org/usage-policy.php",
        update_schedule="Daily at 06:00 UTC via [GitHub Actions](https://github.com/juliensimon/space-datasets).",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994",
        banner={
            "url": "https://images-assets.nasa.gov/image/iss071e439624/iss071e439624~medium.jpg",
            "alt": "An orbital sunrise illuminates the Earth's atmosphere, seen from the ISS",
            "credit": "NASA",
        },
        related_datasets=[
            "juliensimon/starlink-fleet-data",
            "juliensimon/space-launch-log",
            "juliensimon/starlink-ground-stations",
        ],
    ) as p:
        p.publish(
            df,
            filename="satcat.parquet",
            min_rows=60_000,
            expected_columns=[
                "object_name", "norad_id", "object_type", "launch_date",
                "inclination", "apogee_km", "perigee_km",
            ],
            critical_columns=["norad_id", "object_name"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update SATCAT: {n_total:,} objects",
        )
    print("Done.")


if __name__ == "__main__":
    main()
