#!/usr/bin/env python3
"""Fetch space weather events from NASA DONKI and upload to HF.

Incremental: downloads existing parquet, fetches recent events, merges.
Falls back to full rebuild if no existing data.

Source: NASA CCMC DONKI API (https://ccmc.gsfc.nasa.gov/tools/DONKI/)
"""

import time
from datetime import datetime, timedelta

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

DONKI_BASE = "https://kauai.ccmc.gsfc.nasa.gov/DONKI/WS/get"
HF_REPO = "juliensimon/donki-space-weather-events"
START_YEAR = 2010
OVERLAP_DAYS = 14

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "event_type": "Event category: CME (coronal mass ejection), GST (geomagnetic storm), IPS (interplanetary shock), HSS (high-speed stream), or SEP (solar energetic particle)",
    "activity_id": "Unique DONKI event identifier (e.g. '2024-05-08T22:09:00-CME-001'); primary key for cross-referencing",
    "start_time": "Event start time in UTC; for CMEs this is the first coronagraph appearance, for GSTs the storm onset",
    "source_location": "Solar source location in heliographic coordinates (e.g. 'N23W45'); CME-only, null for other event types",
    "active_region": "NOAA active region number associated with the event (e.g. 13664); CME-only, null for other types",
    "note": "Analyst notes from CCMC space weather forecasters; may contain event details or IPS location info",
    "link": "URL to the DONKI web page for this specific event; useful for accessing additional details and linked analyses",
    "cme_speed_kms": "CME speed in km/s from coronagraph analysis (SOHO/LASCO or STEREO/COR); ranges from ~250 to >3000 km/s; CME-only",
    "cme_half_angle_deg": "CME angular half-width in degrees from coronagraph imagery; halo CMEs have half-angle near 90 degrees; CME-only",
    "cme_latitude": "CME source latitude in degrees from coronagraph analysis; CME-only",
    "cme_longitude": "CME source longitude in degrees from coronagraph analysis; CME-only",
    "cme_type": "CME morphological type: S (slow), C (common), O (occasional), R (rare), ER (extremely rare); CME-only",
    "cme_time_21_5": "Estimated time the CME reaches 21.5 solar radii (roughly 0.1 AU); used for transit-time modeling; CME-only",
    "cme_measurement": "Coronagraph measurement technique used for CME parameter estimation; CME-only",
    "gst_max_kp": "Maximum Kp index recorded during the geomagnetic storm (0-9 scale); Kp >= 5 is a minor storm, >= 7 strong, 9 extreme; GST-only",
    "gst_kp_count": "Number of 3-hour Kp index readings during the storm duration; GST-only",
    "linked_events": "Comma-separated activity IDs of causally linked events; enables Sun-to-Earth chain analysis (e.g. CME -> IPS -> GST)",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Space weather events from NASA's DONKI (Database Of Notifications, Knowledge, \
Information) at the Community Coordinated Modeling Center. Covers coronal mass \
ejections, geomagnetic storms, interplanetary shocks, high-speed streams, and \
solar energetic particles from 2010 to present.

DONKI tracks the chain of space weather events from Sun to Earth. A CME erupts \
from the solar corona at speeds ranging from 250 to over 3,000 km/s, driving an \
interplanetary shock (IPS) ahead of it. When the shock and CME arrive at Earth, \
they compress the magnetosphere and produce a geomagnetic storm (GST) measurable \
via the Kp and Dst indices. High-speed streams (HSS) from coronal holes produce \
recurring disturbances on a ~27-day cadence, while solar energetic particle (SEP) \
events deliver MeV-range protons within minutes to hours of the initiating flare or CME.

DONKI is uniquely valuable because it preserves the causal linkages between these \
phenomena via the linked_events field. Unlike raw index time series, DONKI records \
which specific CME triggered which geomagnetic storm, making it possible to study \
transit times, geoeffectiveness as a function of CME speed and direction, and the \
statistical reliability of CME arrival forecasts.\
"""


# ── Fetch helpers (kept from original) ───────────────────────────────

def fetch_donki(endpoint, start_date, end_date, extra_params=None):
    """Fetch from a DONKI endpoint with date range."""
    params = {"startDate": start_date, "endDate": end_date}
    if extra_params:
        params.update(extra_params)
    resp = requests.get(f"{DONKI_BASE}/{endpoint}", params=params, timeout=120)
    resp.raise_for_status()
    return resp.json()


def fetch_by_year(endpoint, extra_params=None):
    """Fetch all records by year to avoid timeouts."""
    all_records = []
    now = datetime.utcnow()
    for year in range(START_YEAR, now.year + 1):
        end = f"{year}-12-31" if year < now.year else now.strftime("%Y-%m-%d")
        try:
            records = fetch_donki(endpoint, f"{year}-01-01", end, extra_params)
            all_records.extend(records)
            print(f"    {year}: {len(records)} records")
        except Exception as e:
            print(f"    {year}: error - {e}")
        time.sleep(0.5)
    return all_records


def parse_cmes(raw):
    """Parse CME records into flat rows."""
    rows = []
    for cme in raw:
        row = {
            "event_type": "CME",
            "activity_id": cme.get("activityID"),
            "start_time": cme.get("startTime"),
            "source_location": cme.get("sourceLocation") or None,
            "active_region": cme.get("activeRegionNum"),
            "note": cme.get("note"),
            "link": cme.get("link"),
        }
        analyses = cme.get("cmeAnalyses") or []
        best = next((a for a in analyses if a.get("isMostAccurate")), analyses[0] if analyses else None)
        if best:
            row["cme_speed_kms"] = best.get("speed")
            row["cme_half_angle_deg"] = best.get("halfAngle")
            row["cme_latitude"] = best.get("latitude")
            row["cme_longitude"] = best.get("longitude")
            row["cme_type"] = best.get("type")
            row["cme_time_21_5"] = best.get("time21_5")
            row["cme_measurement"] = best.get("measurementTechnique")
        linked = cme.get("linkedEvents") or []
        row["linked_events"] = ", ".join(e.get("activityID", "") for e in linked) if linked else None
        rows.append(row)
    return rows


def parse_gsts(raw):
    """Parse geomagnetic storm records."""
    rows = []
    for gst in raw:
        kp_list = gst.get("allKpIndex") or []
        max_kp = max((k.get("kpIndex", 0) for k in kp_list), default=None) if kp_list else None
        row = {
            "event_type": "GST",
            "activity_id": gst.get("gstID"),
            "start_time": gst.get("startTime"),
            "link": gst.get("link"),
            "gst_max_kp": max_kp,
            "gst_kp_count": len(kp_list),
        }
        linked = gst.get("linkedEvents") or []
        row["linked_events"] = ", ".join(e.get("activityID", "") for e in linked) if linked else None
        rows.append(row)
    return rows


def parse_simple_events(raw, event_type):
    """Parse simple event types (IPS, HSS, SEP, etc.)."""
    rows = []
    id_key = {
        "IPS": "activityID", "HSS": "hssID", "SEP": "sepID",
        "MPC": "mpcID", "RBE": "rbeID",
    }.get(event_type, "activityID")

    for evt in raw:
        row = {
            "event_type": event_type,
            "activity_id": evt.get(id_key),
            "start_time": evt.get("eventTime") or evt.get("startTime"),
            "link": evt.get("link"),
        }
        if event_type == "IPS":
            row["note"] = evt.get("location")
        linked = evt.get("linkedEvents") or []
        row["linked_events"] = ", ".join(e.get("activityID", "") for e in linked) if linked else None
        rows.append(row)
    return rows


ENDPOINTS = [
    ("CME", "CME", parse_cmes),
    ("GST", "GST", parse_gsts),
    ("IPS", "IPS", lambda raw: parse_simple_events(raw, "IPS")),
    ("HSS", "HSS", lambda raw: parse_simple_events(raw, "HSS")),
    ("SEP", "SEP", lambda raw: parse_simple_events(raw, "SEP")),
]


def fetch_incremental(start_date, end_date):
    """Fetch all event types for a date range."""
    all_rows = []
    for label, endpoint, parser in ENDPOINTS:
        try:
            raw = fetch_donki(endpoint, start_date, end_date)
            rows = parser(raw)
            all_rows.extend(rows)
            print(f"    {label}: {len(rows)} events")
        except Exception as e:
            print(f"    {label}: error - {e}")
        time.sleep(0.5)
    return all_rows


def coerce_types(df):
    """Apply type coercion to DONKI DataFrame."""
    df["start_time"] = pd.to_datetime(df["start_time"], errors="coerce")
    df["cme_time_21_5"] = pd.to_datetime(df.get("cme_time_21_5"), errors="coerce")
    df["active_region"] = pd.to_numeric(df.get("active_region"), errors="coerce").astype("Int64")
    return df


# ── Main pipeline ────────────────────────────────────────────────────

def main():
    print("Fetching DONKI space weather events...")
    now = datetime.utcnow()

    with Pipeline(
        repo=HF_REPO,
        pretty_name="NASA DONKI Space Weather Events",
        description=DESCRIPTION,
        tags=["space", "space-weather", "cme", "geomagnetic-storm", "solar",
              "nasa", "open-data", "coronal-mass-ejection", "ccmc", "donki",
              "solar-wind", "tabular-data", "parquet"],
        source_url="https://ccmc.gsfc.nasa.gov/tools/DONKI/",
        task_categories=["tabular-classification", "time-series-forecasting"],
        update_schedule="Daily at 14:00 UTC via GitHub Actions",
        collection_url="https://huggingface.co/collections/juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70",
        banner={
            "url": "https://images-assets.nasa.gov/image/iss072e159172/iss072e159172~medium.jpg",
            "alt": "Aurora borealis blankets the Earth, seen from the ISS",
            "credit": "NASA",
        },
        related_datasets=[
            "juliensimon/solar-flare-events",
            "juliensimon/space-weather-indices",
            "juliensimon/dst-index",
            "juliensimon/neo-close-approaches",
        ],
    ) as p:
        # Try incremental
        df_existing = p.download_existing("donki_events.parquet")

        if df_existing is not None and len(df_existing) > 0:
            df_existing["start_time"] = pd.to_datetime(df_existing["start_time"])
            max_date = df_existing["start_time"].max()
            fetch_from = (max_date - timedelta(days=OVERLAP_DAYS)).strftime("%Y-%m-%d")
            fetch_to = now.strftime("%Y-%m-%d")
            print(f"  Incremental fetch: {fetch_from} to {fetch_to}")

            new_rows = fetch_incremental(fetch_from, fetch_to)
            df_new = pd.DataFrame(new_rows)

            if not df_new.empty:
                df_new = coerce_types(df_new)
                df = p.merge(df_existing, df_new, dedup_on="activity_id", sort_by="start_time")
                print(f"  Merged: {len(df):,} events ({len(df) - len(df_existing):+,} net)")
            else:
                df = df_existing
                print("  No new events")
        else:
            # Full rebuild
            print("  Full rebuild from 2010...")
            all_rows = []
            for label, endpoint, parser in ENDPOINTS:
                print(f"  Fetching {label}...")
                raw = fetch_by_year(endpoint)
                rows = parser(raw)
                all_rows.extend(rows)
                print(f"  {len(raw)} {label}s total")
            df = pd.DataFrame(all_rows)

        df = coerce_types(df)
        df = df.sort_values("start_time").reset_index(drop=True)

        # Keep only described columns
        df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

        df = p.clean(
            df,
            numeric=["cme_speed_kms", "cme_half_angle_deg", "cme_latitude",
                      "cme_longitude", "gst_max_kp", "gst_kp_count"],
        )

        # ── Stats for README ────────────────────────────────────────
        n_total = len(df)
        n_cme = int((df["event_type"] == "CME").sum())
        n_gst = int((df["event_type"] == "GST").sum())
        n_ips = int((df["event_type"] == "IPS").sum())
        n_hss = int((df["event_type"] == "HSS").sum())
        n_sep = int((df["event_type"] == "SEP").sum())
        date_min = df["start_time"].min().strftime("%Y-%m-%d")
        date_max = df["start_time"].max().strftime("%Y-%m-%d")

        fastest_speed = "N/A"
        fastest_date = "N/A"
        if "cme_speed_kms" in df.columns and df["cme_speed_kms"].notna().any():
            idx = df["cme_speed_kms"].idxmax()
            fastest_speed = int(df.loc[idx, "cme_speed_kms"])
            fastest_date = df.loc[idx, "start_time"].strftime("%Y-%m-%d")

        quick_stats = f"""\
- **{n_total:,}** events ({date_min} to {date_max})
- **{n_cme:,}** CMEs, **{n_gst:,}** geomagnetic storms, **{n_ips:,}** interplanetary shocks
- **{n_hss:,}** high speed streams, **{n_sep:,}** solar energetic particle events
- Fastest CME: **{fastest_speed} km/s** on {fastest_date}"""

        usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/donki-space-weather-events", split="train")
df = ds.to_pandas()

# Fast CMEs (potential Earth-directed storms)
fast_cmes = df[(df["event_type"] == "CME") & (df["cme_speed_kms"] > 1000)]

# Geomagnetic storms with linked CMEs
storms = df[df["event_type"] == "GST"]
storms_with_cme = storms[storms["linked_events"].str.contains("CME", na=False)]

# CME speed distribution
import matplotlib.pyplot as plt
cmes = df[df["event_type"] == "CME"]
cmes["cme_speed_kms"].hist(bins=50)
plt.xlabel("CME Speed (km/s)")
plt.ylabel("Count")
plt.title("DONKI CME Speed Distribution")
plt.show()

# Event frequency by type and year
df["year"] = df["start_time"].dt.year
df.groupby(["year", "event_type"]).size().unstack().plot()
plt.title("DONKI Events by Type and Year")
plt.show()
```"""

        p.publish(
            df,
            filename="donki_events.parquet",
            min_rows=5000,
            expected_columns=["activity_id", "event_type", "start_time"],
            critical_columns=["activity_id", "start_time"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update DONKI events: {n_total:,} events ({n_cme:,} CMEs, {n_gst:,} storms)",
        )
    print("Done.")


if __name__ == "__main__":
    main()
