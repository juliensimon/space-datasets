#!/usr/bin/env python3
"""Fetch substorm onset event lists from SuperMAG and upload to HF."""

import io
import sys
import time

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

HF_REPO = "juliensimon/substorm-onsets"

# SuperMAG substorm lists — no real auth required (any user string works)
BASE_URL = (
    "https://supermag.jhuapl.edu/lib/services/"
    "?service=substorms&downloadtype=substorm_list"
    "&user=space-datasets&fmt=csv"
)

# Each list with its coverage and detection method
LISTS = {
    "newell": {"start": "1976-01-01", "end": "2025-12-31", "method": "SML index (ground magnetometers)"},
    "forsyth": {"start": "1970-01-01", "end": "2025-12-31", "method": "SML/SMU expansion-recovery (ground magnetometers)"},
    "ohtani": {"start": "1970-01-01", "end": "2025-12-31", "method": "SML bay detection (ground magnetometers)"},
    "frey": {"start": "2000-01-01", "end": "2005-12-31", "method": "IMAGE/FUV auroral imaging (space-based)"},
    "liou": {"start": "1996-01-01", "end": "2010-12-31", "method": "Polar UVI auroral imaging (space-based)"},
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "datetime_utc": "UTC timestamp of the substorm onset -- the start of the expansion phase when energy stored in the magnetotail is explosively released; accurate to +/-1-2 minutes for ground-based detections, +/-1 minute for auroral imager detections",
    "mlt_hours": "Magnetic Local Time (MLT) of the onset location (0-24 h, where 0/24 = magnetic midnight, 12 = magnetic noon); midnight-sector onsets (22-02 MLT) are most common",
    "magnetic_latitude_deg": "Magnetic latitude (MLAT) of the onset location in degrees; substorm onsets typically occur at 60-75 deg MLAT within the auroral oval",
    "geographic_longitude_deg": "Geographic (geodetic) longitude of the onset location in degrees (-180 to 180); suitable for plotting on standard world maps",
    "geographic_latitude_deg": "Geographic (geodetic) latitude of the onset location in degrees; use with geographic_longitude_deg for ground-track mapping",
    "source": "Detection algorithm that identified this onset: newell (SML index threshold), forsyth (SME index derivative), ohtani (negative bay in SML), frey (IMAGE satellite UV imager), liou (Polar satellite UV imager)",
    "method": "Human-readable detection method category describing the instrument and technique used by each algorithm",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Magnetospheric substorm onset events from five independent detection algorithms via \
the SuperMAG collaboration. This is the most comprehensive substorm event list available, \
enabling multi-algorithm comparison and consensus studies.

Magnetospheric substorms are fundamental space weather events driven by the solar wind's \
interaction with Earth's magnetic field. During a substorm, magnetic energy stored in the \
magnetotail is explosively released, accelerating charged particles that stream along field \
lines into the polar regions. This produces sudden auroral brightenings along with rapid \
changes in ground-level magnetic fields detected by magnetometer networks worldwide.

Ground-based methods detect substorms through characteristic negative bays in the SML \
(SuperMAG Lower) index -- a measure of the westward auroral electrojet current. Space-based \
methods directly observe the initial auroral brightening using ultraviolet imagers aboard \
the IMAGE and Polar satellites. Each algorithm has different sensitivity and false-positive \
rates, so researchers often require onset confirmation across multiple lists.
"""


def fetch_list(name, info):
    """Fetch a single substorm list from SuperMAG API."""
    url = (
        f"{BASE_URL}"
        f"&start={info['start']}T00:00:00.000Z"
        f"&end={info['end']}T23:59:59.000Z"
        f"&list={name}"
    )
    print(f"  Fetching {name} ({info['start']} to {info['end']})...")
    resp = requests.get(url, timeout=300, headers={"User-Agent": "space-datasets/1.0"})
    resp.raise_for_status()

    text = resp.text.strip()
    if not text or len(text) < 50:
        print(f"    Empty response for {name}")
        return pd.DataFrame()

    df = pd.read_csv(io.StringIO(text))
    if len(df) == 0:
        return df

    df["source"] = name
    df["method"] = info["method"]
    print(f"    {len(df):,} events")
    return df


def main():
    print("Fetching substorm onset lists from SuperMAG...")

    frames = []
    for name, info in LISTS.items():
        try:
            df = fetch_list(name, info)
            if len(df) > 0:
                frames.append(df)
        except Exception as e:
            print(f"    Failed {name}: {e}")
        time.sleep(2)  # Be polite to the API

    if not frames:
        print("::error::No substorm lists fetched")
        sys.exit(1)

    df = pd.concat(frames, ignore_index=True)
    print(f"  {len(df):,} total events from {len(frames)} lists")

    # Normalize column names to snake_case
    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")

    # Rename for consistency
    rename = {
        "date_utc": "datetime_utc",
        "mlt": "mlt_hours",
        "mlat": "magnetic_latitude_deg",
        "glon": "geographic_longitude_deg",
        "glat": "geographic_latitude_deg",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

    # Parse datetime
    if "datetime_utc" in df.columns:
        df["datetime_utc"] = pd.to_datetime(df["datetime_utc"], errors="coerce")

    # Normalize MLT: liou list reports in degrees (0-360), convert to hours (0-24)
    if "mlt_hours" in df.columns:
        mlt = pd.to_numeric(df["mlt_hours"], errors="coerce")
        mask_degrees = mlt > 24
        if mask_degrees.any():
            mlt.loc[mask_degrees] = mlt.loc[mask_degrees] / 15.0
            print(f"  Converted {mask_degrees.sum():,} MLT values from degrees to hours (liou list)")
        df["mlt_hours"] = mlt

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Sort and clean
    df = df.sort_values("datetime_utc").reset_index(drop=True)
    n_before = len(df)
    df = df.dropna(subset=["datetime_utc"]).reset_index(drop=True)
    if n_before - len(df) > 0:
        print(f"  Dropped {n_before - len(df)} rows with invalid datetime")

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    source_counts = df["source"].value_counts().to_dict()
    year_min = df["datetime_utc"].dt.year.min()
    year_max = df["datetime_utc"].dt.year.max()
    n_ground = int(df["source"].isin(["newell", "forsyth", "ohtani"]).sum())
    n_imaging = int(df["source"].isin(["frey", "liou"]).sum())

    source_lines = "\n".join(
        f"- **{name}**: {count:,} events ({LISTS[name]['method']})"
        for name, count in sorted(source_counts.items(), key=lambda x: -x[1])
    )

    quick_stats = f"""\
- **{n_total:,}** total substorm onset events
- **{year_min}--{year_max}** temporal coverage
- **5** independent detection algorithms
- **{n_ground:,}** ground magnetometer detections, **{n_imaging:,}** auroral imaging detections
- By algorithm:
{source_lines}"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/substorm-onsets", split="train")
df = ds.to_pandas()

# Events per algorithm
print(df["source"].value_counts())

# Annual substorm rate by algorithm
import matplotlib.pyplot as plt
df["year"] = df["datetime_utc"].dt.year
df.groupby(["year", "source"]).size().unstack().plot(figsize=(12, 5))
plt.ylabel("Substorm onsets per year")
plt.title("Annual Substorm Rate by Detection Algorithm")
plt.show()

# MLT distribution — substorms peak near midnight
df["mlt_hours"].hist(bins=48, alpha=0.7)
plt.xlabel("Magnetic Local Time (hours)")
plt.ylabel("Count")
plt.title("Substorm Onset MLT Distribution")
plt.show()

# Find consensus events (multiple algorithms within 10 minutes)
from datetime import timedelta
newell = df[df["source"] == "newell"]["datetime_utc"]
ohtani = df[df["source"] == "ohtani"]["datetime_utc"]
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Substorm Onset Events (SuperMAG)",
        description=DESCRIPTION,
        tags=["space", "space-weather", "substorm", "magnetosphere", "aurora",
              "geomagnetic", "supermag", "open-data", "tabular-data", "parquet"],
        source_url="https://supermag.jhuapl.edu/substorms/",
        task_categories=["tabular-classification", "time-series-forecasting"],
        collection_url="https://huggingface.co/collections/juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70",
        banner={
            "url": "https://images-assets.nasa.gov/image/iss072e159172/iss072e159172~medium.jpg",
            "alt": "Aurora borealis blankets the Earth, seen from the ISS",
            "credit": "NASA",
        },
        related_datasets=[
            "juliensimon/dst-index",
            "juliensimon/geomagnetic-kp-index",
            "juliensimon/auroral-electrojet-index",
            "juliensimon/donki-space-weather-events",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=["mlt_hours", "magnetic_latitude_deg",
                      "geographic_longitude_deg", "geographic_latitude_deg"],
        )
        p.publish(
            df,
            filename="substorm_onsets.parquet",
            min_rows=50000,
            expected_columns=["datetime_utc", "mlt_hours", "magnetic_latitude_deg", "source"],
            critical_columns=["datetime_utc", "source"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update substorm onsets: {n_total:,} events from 5 algorithms",
        )
    print("Done.")


if __name__ == "__main__":
    main()
