#!/usr/bin/env python3
"""Fetch GRBweb unified multi-instrument GRB catalog and upload to HF.

Source: IceCube GRBweb public Summary_table.txt
Combines data from Fermi, Swift, BATSE, BeppoSAX, IPN, and other instruments.
"""

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

SUMMARY_URL = "https://user-web.icecube.wisc.edu/~grbweb_public/Summary_table.txt"
HF_REPO = "juliensimon/grbweb-unified-grb-catalog"

# Column names from the # header comment in the file
COLUMNS = [
    "grb_name", "grb_name_fermi", "t0_utc", "ra", "dec",
    "pos_error", "t90", "t90_error", "t90_start", "fluence",
    "fluence_error", "redshift", "t100", "gbm_located", "mjd",
]

NUMERIC_COLS = [
    "ra", "dec", "pos_error", "t90", "t90_error", "fluence",
    "fluence_error", "redshift", "t100", "mjd",
]

SENTINEL = "-999"

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "grb_name": "Canonical GRB designation in YYMMDDFFF or YYMMDD format (e.g., 'GRB260326A'); the letter suffix distinguishes multiple events on the same date",
    "grb_name_fermi": "Fermi GBM internal trigger name (e.g., 'GRB260326123'); null if the burst was not detected by Fermi GBM",
    "t0_utc": "Trigger time of day in UTC (HH:MM:SS.sss); combined with trigger_time for the full timestamp",
    "ra": "Best-fit right ascension in degrees (J2000.0 ICRS); localization accuracy varies widely by instrument: Swift XRT ~2 arcsec, Fermi GBM ~1-3 deg, IPN ~0.1-10 deg",
    "dec": "Best-fit declination in degrees (J2000.0 ICRS); range -90 to +90",
    "pos_error": "1-sigma position uncertainty in degrees; Fermi GBM typical: 1-5 deg; Swift: arcseconds; null if only a non-parametric localization is available",
    "t90": "Duration T90 in seconds -- the time interval containing 5%-95% of the total burst fluence; bimodal distribution: short GRBs < 2 s (compact object mergers), long GRBs > 2 s (core-collapse supernovae); null for ~20% of entries",
    "t90_error": "Uncertainty on T90 in seconds (1-sigma); null if T90 was not formally measured with uncertainty",
    "t90_start": "UTC time when the T90 interval begins (i.e., when 5% of total fluence has been accumulated); null for many entries",
    "fluence": "Time-integrated energy flux (fluence) over the burst duration in erg/cm2; instrument-dependent energy band; null for ~40% of entries",
    "fluence_error": "1-sigma uncertainty on fluence in erg/cm2; null when fluence is null",
    "redshift": "Spectroscopic or photometric redshift of the GRB host galaxy; available for only ~15-20% of GRBs; range ~0.01 to >9",
    "t100": "Total burst duration T100 in seconds (full emission episode); always >= T90; null for many entries",
    "gbm_located": "True if Fermi GBM provided the best available localization for this event; False if the localization came from Swift, IPN, or another instrument",
    "mjd": "Modified Julian Date of the trigger (MJD = JD - 2400000.5); MJD epoch: 1858-11-17T00:00:00 UTC",
    "trigger_time": "Trigger time as a UTC datetime object, derived from the MJD column",
    "duration_class": "Derived duration classification: 'short' (T90 < 2 s, associated with neutron star mergers) or 'long' (T90 >= 2 s, associated with core-collapse supernovae); null if T90 is missing",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Unified catalog of gamma-ray bursts detected across multiple space missions, \
sourced from the GRBweb database maintained by the IceCube Collaboration. Combines \
data from Fermi GBM, Swift BAT, BATSE, BeppoSAX, IPN, and other instruments into a \
single deduplicated catalog.

Gamma-ray bursts (GRBs) are the most energetic explosions in the universe. Different \
space missions have detected GRBs since the early 1990s, but each instrument covers \
different energy ranges, sky regions, and time periods. GRBweb unifies detections \
across all major GRB instruments, providing a single cross-referenced catalog with \
consistent columns for position, duration, fluence, and redshift.

The challenge of GRB astronomy has always been fragmentation: CGRO/BATSE (1991-2000) \
detected over 2,700 bursts but could not localize them precisely. BeppoSAX (1996-2002) \
provided the first arcminute X-ray localizations enabling the redshift revolution. \
Swift (2004-present) added rapid autonomous slewing and arcsecond localizations. Fermi \
GBM (2008-present) restored near all-sky coverage with superior spectral capabilities. \
GRBweb solves fragmentation by cross-matching triggers across missions and presenting \
a unified record for each burst.
"""


def fetch_summary() -> pd.DataFrame:
    """Download the GRBweb summary table and parse into a DataFrame."""
    print("Fetching GRBweb Summary_table.txt ...")
    resp = requests.get(SUMMARY_URL, timeout=120)
    resp.raise_for_status()

    rows = []
    for line in resp.text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 15:
            print(f"  Skipping malformed line ({len(parts)} fields): {line[:80]}")
            continue
        rows.append(parts)

    print(f"  Parsed {len(rows):,} data rows")
    df = pd.DataFrame(rows, columns=COLUMNS)
    return df


def transform(df: pd.DataFrame) -> pd.DataFrame:
    """Clean types, replace sentinels, derive columns."""
    # Replace -999 sentinel with NaN
    df = df.replace(SENTINEL, pd.NA)
    df = df.replace("None", pd.NA)

    # Coerce numeric columns
    for col in NUMERIC_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Convert MJD to datetime (MJD epoch: 1858-11-17T00:00:00)
    mjd_epoch = pd.Timestamp("1858-11-17")
    df["trigger_time"] = mjd_epoch + pd.to_timedelta(df["mjd"], unit="D")

    # Boolean for GBM located
    df["gbm_located"] = df["gbm_located"].map({"True": True, "False": False})

    # Clean GRB name -- strip trailing asterisk (marks updated entries)
    df["grb_name"] = df["grb_name"].str.rstrip("*")

    # Duration class based on T90
    df["duration_class"] = df["t90"].apply(
        lambda x: "short" if pd.notna(x) and x < 2.0
        else ("long" if pd.notna(x) else None)
    )

    # Sort by trigger_time descending (newest first)
    df = df.sort_values("trigger_time", ascending=False).reset_index(drop=True)

    return df


def main():
    df = fetch_summary()
    df = transform(df)

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    n_total = len(df)
    print(f"  {n_total:,} GRBs total")

    # ── Domain-specific stats for README ─────────────────────────────
    n_short = int((df["duration_class"] == "short").sum())
    n_long = int((df["duration_class"] == "long").sum())
    n_with_z = int(df["redshift"].notna().sum())
    n_gbm = int(df["gbm_located"].sum())
    date_min = df["trigger_time"].min()
    date_max = df["trigger_time"].max()
    date_range = f"{date_min:%Y-%m-%d} to {date_max:%Y-%m-%d}"

    brightest_idx = df["fluence"].idxmax()
    brightest_name = df.loc[brightest_idx, "grb_name"] if pd.notna(brightest_idx) else "N/A"
    brightest_fluence = df.loc[brightest_idx, "fluence"] if pd.notna(brightest_idx) else 0

    quick_stats = f"""\
- **{n_total:,}** gamma-ray bursts from multiple instruments
- **{n_short:,}** short GRBs, **{n_long:,}** long GRBs
- **{n_with_z:,}** with measured redshift
- **{n_gbm:,}** with Fermi GBM localization
- Date range: **{date_range}**
- Brightest burst: **{brightest_name}** (fluence {brightest_fluence:.2e} erg/cm^2)"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/grbweb-unified-grb-catalog", split="train")
df = ds.to_pandas()

# Short vs long GRBs
short = df[df["duration_class"] == "short"]
long = df[df["duration_class"] == "long"]
print(f"{len(short):,} short, {len(long):,} long GRBs")

# GRBs with measured redshift
z_known = df[df["redshift"].notna()]
print(f"{len(z_known):,} GRBs with redshift (z_max={z_known['redshift'].max():.2f})")

# T90 distribution
import matplotlib.pyplot as plt
df["t90"].dropna().apply(lambda x: max(x, 1e-3)).hist(bins=50, log=True)
plt.xlabel("T90 (s)")
plt.title("GRB Duration Distribution (GRBweb)")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="GRBweb Unified Multi-Instrument GRB Catalog",
        description=DESCRIPTION,
        tags=["space", "grb", "gamma-ray-bursts", "multi-instrument",
              "astronomy", "open-data", "tabular-data", "parquet"],
        source_url="https://user-web.icecube.wisc.edu/~grbweb_public/",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA03519/PIA03519~small.jpg",
            "alt": "Cassiopeia A supernova remnant in X-ray, optical, and infrared light",
            "credit": "NASA/JPL-Caltech/STScI/CXC/SAO",
        },
        related_datasets=[
            "juliensimon/gamma-ray-bursts",
            "juliensimon/fermi-4fgl-dr4",
            "juliensimon/neo-close-approaches",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "ra", "dec", "pos_error", "t90", "t90_error",
                "fluence", "fluence_error", "redshift", "t100", "mjd",
            ],
        )
        p.publish(
            df,
            filename="grbweb.parquet",
            min_rows=2000,
            expected_columns=["grb_name", "trigger_time", "ra", "dec",
                              "t90", "fluence", "redshift"],
            critical_columns=["grb_name", "trigger_time"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update GRBweb catalog: {n_total:,} GRBs",
        )
    print("Done.")


if __name__ == "__main__":
    main()
