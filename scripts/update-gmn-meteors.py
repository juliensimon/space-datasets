#!/usr/bin/env python3
"""Fetch meteor trajectory summaries from the Global Meteor Network and upload to HF.

Incremental: downloads existing parquet, fetches new monthly files, merges.
Falls back to full rebuild if no existing data.

Source: GMN monthly trajectory summary files
  https://globalmeteornetwork.org/data/traj_summary_data/monthly/
"""

import io
import re
import time
from datetime import datetime, timezone

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

GMN_MONTHLY_INDEX = "https://globalmeteornetwork.org/data/traj_summary_data/monthly/"
GMN_MONTHLY_BASE = "https://globalmeteornetwork.org/data/traj_summary_data/monthly/"
HF_REPO = "juliensimon/global-meteor-network"

# ── Column descriptions ──────────────────────────────────────────────
COLUMN_DESCRIPTIONS = {
    "datetime_utc": (
        "Peak brightness datetime in UTC (format: YYYY-MM-DD HH:MM:SS.ff); "
        "used as the primary deduplication key; typically accurate to ±0.1 s"
    ),
    "shower_code": (
        "IAU three-letter code for the meteor shower (e.g. 'PER' = Perseids, "
        "'GEM' = Geminids); '...' = sporadic (not associated with any known stream)"
    ),
    "radiant_ra_deg": (
        "Geocentric radiant right ascension J2000.0 (degrees, 0–360); the apparent "
        "sky point from which meteors of this stream diverge, corrected for Earth's "
        "orbital velocity"
    ),
    "radiant_dec_deg": (
        "Geocentric radiant declination J2000.0 (degrees, -90 to +90); together with "
        "ra defines the meteor's approach direction in inertial space"
    ),
    "v_g_kms": (
        "Geocentric velocity at the top of the atmosphere before deceleration (km/s); "
        "range ~11 km/s (Earth-grazing) to ~72 km/s (retrograde head-on); determines "
        "meteor brightness and persistent train likelihood"
    ),
    "a_au": (
        "Orbital semi-major axis of the meteoroid's heliocentric orbit (AU); "
        "NaN/inf for hyperbolic trajectories; Jupiter-family comets: 3-5 AU; "
        "Halley-type: 10-50 AU"
    ),
    "e": (
        "Orbital eccentricity (0 = circular, 1 = parabolic, >1 = hyperbolic); "
        "most shower meteoroids: 0.7–0.99; sporadic: wider range"
    ),
    "i_deg": (
        "Orbital inclination to the ecliptic plane (degrees, 0–180); <90° = prograde "
        "(same direction as planets); >90° = retrograde; Perseids: ~113°, Leonids: ~162°"
    ),
    "peri_deg": (
        "Argument of perihelion of the meteoroid orbit (degrees, 0–360); combined with "
        "node_deg locates the perihelion direction"
    ),
    "node_deg": (
        "Longitude of the ascending node (degrees, 0–360); for Earth-crossing orbits, "
        "approximately equals the solar longitude at the shower's peak activity"
    ),
    "q_au": (
        "Perihelion distance of the meteoroid's orbit (AU); must be ≤ ~1.01 AU for "
        "Earth-crossing; values close to 1.0 AU indicate recent parent-comet ejection"
    ),
    "peak_abs_magnitude": (
        "Absolute magnitude at peak brightness (normalized to 100 km range); lower "
        "values = brighter; scale: -4 (fireball) to +7 (faint); used for mass and "
        "flux estimation"
    ),
    "peak_height_km": (
        "Altitude above sea level at peak brightness (km); typical range 80–110 km; "
        "slower meteors peak higher; depends on velocity and meteoroid composition"
    ),
    "duration_sec": (
        "Total duration of the visible meteor trail in seconds; from first detection "
        "to last; fast meteors: 0.1-0.5 s; fireballs: up to 5-10 s"
    ),
    "n_stations": (
        "Number of GMN cameras that simultaneously detected this meteor; ≥2 required "
        "for trajectory solution; higher values indicate better geometry and orbital accuracy"
    ),
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Individual meteor trajectory solutions from the Global Meteor Network (GMN), \
a worldwide network of 500+ all-sky cameras operated by volunteer astronomers. \
Each row is one detected meteor with orbital elements derived from multi-station \
triangulation.

The GMN was founded in 2018 and has grown to cover all longitudes from Europe, the \
Americas, Australia, and beyond. When at least two cameras simultaneously detect a \
meteor, the geometry of their positions allows triangulation of the atmospheric \
trajectory. Combined with timing, this yields the meteoroid's velocity at the top of \
the atmosphere and — after correction for Earth's gravitational attraction — the \
heliocentric orbit before encounter. The result is a complete set of Keplerian elements \
(a, e, i, ω, Ω, q) that places each detected meteoroid in the Solar System context.

Unlike the IAU Meteor Shower Database which catalogs mean radiant/orbit solutions \
per shower, this dataset contains individual meteor detections with full orbital \
parameters. The majority of detections are sporadic meteors (shower_code = '...') \
with no known parent body; shower members are identified by matching with the IAU \
shower list. The n_stations column provides a quality indicator: two-station solutions \
are the minimum for a valid trajectory, while higher counts improve the accuracy of \
both the radiant and the orbital elements.

This dataset is valuable for: identifying new meteor streams, studying the dynamical \
evolution of meteoroid trails, searching for meteoroids of potential interstellar origin \
(high eccentricity or retrograde orbits), correlating meteor detections with asteroid/comet \
close approaches, and building ML models for meteor source classification.
"""


def list_monthly_files():
    """Fetch directory index and return sorted list of (yyyymm, filename) tuples."""
    resp = requests.get(GMN_MONTHLY_INDEX, timeout=30)
    resp.raise_for_status()
    # Files match: traj_summary_monthly_YYYYMM.txt
    matches = re.findall(r'href="(traj_summary_monthly_(\d{6})\.txt)"', resp.text)
    # matches is list of (filename, yyyymm)
    files = sorted((yyyymm, fname) for fname, yyyymm in matches)
    return files


def parse_gmn_txt(text):
    """Parse a GMN trajectory summary .txt file into a DataFrame.

    The format is semicolon-separated. Lines starting with '#' are comments/headers.
    Column layout (0-indexed):
      0  = trajectory identifier
      1  = Julian date (beginning)
      2  = UTC datetime (beginning, used as datetime_utc)
      3  = IAU shower number
      4  = IAU shower code
      7  = RAgeo (geocentric radiant RA, deg)
      9  = DECgeo (geocentric radiant Dec, deg)
      15 = Vgeo (geocentric velocity, km/s)
      23 = a (semi-major axis, AU)
      25 = e (eccentricity)
      27 = i (inclination, deg)
      29 = peri (argument of perihelion, deg)
      31 = node (longitude of ascending node, deg)
      37 = q (perihelion distance, AU)
      75 = Duration (sec)
      76 = Peak AbsMag
      77 = Peak Height (km)
      84 = Num stat (number of stations)
    """
    # Filter out comment lines (starting with #) and empty lines
    data_lines = [
        line for line in text.splitlines()
        if line.strip() and not line.startswith("#")
    ]
    if not data_lines:
        return pd.DataFrame()

    # Parse semicolon-separated rows
    rows = []
    for line in data_lines:
        parts = [p.strip() for p in line.split(";")]
        if len(parts) < 85:
            continue
        rows.append(parts)

    if not rows:
        return pd.DataFrame()

    # Build DataFrame from selected columns only
    COLS = {
        2: "datetime_utc",
        4: "shower_code",
        7: "radiant_ra_deg",
        9: "radiant_dec_deg",
        15: "v_g_kms",
        23: "a_au",
        25: "e",
        27: "i_deg",
        29: "peri_deg",
        31: "node_deg",
        37: "q_au",
        75: "duration_sec",
        76: "peak_abs_magnitude",
        77: "peak_height_km",
        84: "n_stations",
    }

    data = {}
    for idx, name in COLS.items():
        data[name] = [row[idx] if idx < len(row) else None for row in rows]

    df = pd.DataFrame(data)
    return df


def fetch_monthly(yyyymm):
    """Download and parse one monthly file. Returns DataFrame or None."""
    url = f"{GMN_MONTHLY_BASE}traj_summary_monthly_{yyyymm}.txt"
    try:
        resp = requests.get(url, timeout=120)
        resp.raise_for_status()
        df = parse_gmn_txt(resp.text)
        print(f"    {yyyymm}: {len(df):,} rows")
        return df
    except Exception as exc:
        print(f"    {yyyymm}: error — {exc}")
        return None


def coerce_types(df):
    """Coerce column types."""
    df["datetime_utc"] = pd.to_datetime(df["datetime_utc"], errors="coerce")

    numeric_cols = [
        "radiant_ra_deg", "radiant_dec_deg", "v_g_kms",
        "a_au", "e", "i_deg", "peri_deg", "node_deg", "q_au",
        "duration_sec", "peak_abs_magnitude", "peak_height_km",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "n_stations" in df.columns:
        df["n_stations"] = pd.to_numeric(df["n_stations"], errors="coerce").astype("Int64")

    # Normalise shower_code: strip whitespace; "..." is the GMN sporadic marker
    if "shower_code" in df.columns:
        df["shower_code"] = df["shower_code"].str.strip()

    return df


def yyyymm_from_dt(dt):
    """Return 'YYYYMM' string for a pandas Timestamp."""
    return f"{dt.year:04d}{dt.month:02d}"


# ── Main pipeline ────────────────────────────────────────────────────

def main():
    print("Fetching Global Meteor Network trajectory data...")
    now = datetime.now(timezone.utc)

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Global Meteor Network Trajectory Data",
        description=DESCRIPTION,
        tags=[
            "space", "meteors", "orbital-mechanics", "astronomy",
            "meteor-showers", "open-data", "tabular-data", "parquet",
        ],
        source_url="https://globalmeteornetwork.org/data/",
        task_categories=["tabular-classification", "tabular-regression"],
        update_schedule="Daily at 10:00 UTC",
        collection_url=(
            "https://huggingface.co/collections/juliensimon/"
            "orbital-mechanics-datasets-69c24caca4ab3934c9856994"
        ),
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA17666/PIA17666~small.jpg",
            "alt": "Rosetta spacecraft approaching Comet 67P/Churyumov-Gerasimenko",
            "credit": "NASA/ESA",
        },
        related_datasets=[
            "juliensimon/iau-meteor-showers",
            "juliensimon/fireball-bolide-events",
            "juliensimon/neo-close-approaches",
        ],
    ) as p:
        # ── List available monthly files ─────────────────────────────
        try:
            all_files = list_monthly_files()
            print(f"  Found {len(all_files)} monthly files "
                  f"({all_files[0][0]} to {all_files[-1][0]})")
        except Exception as exc:
            print(f"  Failed to list monthly files: {exc}")
            raise

        # ── Try incremental ──────────────────────────────────────────
        df_existing = p.download_existing("gmn_meteors.parquet")

        if df_existing is not None and len(df_existing) > 0:
            df_existing["datetime_utc"] = pd.to_datetime(
                df_existing["datetime_utc"], errors="coerce"
            )
            max_dt = df_existing["datetime_utc"].max()
            # Fetch the current month and the month of the latest existing record
            # (for overlap/dedup), plus any months strictly after it.
            existing_last_yyyymm = yyyymm_from_dt(max_dt)
            # Include the last covered month to catch late-arriving data
            months_to_fetch = [
                (ym, fn) for ym, fn in all_files
                if ym >= existing_last_yyyymm
            ]
            print(f"  Incremental: existing data through {max_dt.date()}, "
                  f"fetching {len(months_to_fetch)} month(s) "
                  f"({months_to_fetch[0][0]} to {months_to_fetch[-1][0]})")

            dfs_new = []
            for yyyymm, _ in months_to_fetch:
                df_month = fetch_monthly(yyyymm)
                if df_month is not None and not df_month.empty:
                    dfs_new.append(df_month)
                time.sleep(1)

            if dfs_new:
                df_new = pd.concat(dfs_new, ignore_index=True)
                df_new = coerce_types(df_new)
                df = p.merge(
                    df_existing, df_new,
                    dedup_on="datetime_utc",
                    sort_by="datetime_utc",
                )
                net = len(df) - len(df_existing)
                print(f"  Merged: {len(df):,} rows ({net:+,} net)")
            else:
                df = df_existing
                print("  No new data found")
        else:
            # ── Full rebuild: fetch all months ───────────────────────
            print(f"  Full rebuild: fetching {len(all_files)} monthly files...")
            dfs_all = []
            for yyyymm, _ in all_files:
                df_month = fetch_monthly(yyyymm)
                if df_month is not None and not df_month.empty:
                    dfs_all.append(df_month)
                time.sleep(1)

            if not dfs_all:
                raise RuntimeError("No data fetched during full rebuild")

            df = pd.concat(dfs_all, ignore_index=True)
            df = coerce_types(df)
            df = df.drop_duplicates(subset="datetime_utc", keep="last")
            df = df.sort_values("datetime_utc").reset_index(drop=True)
            print(f"  Full rebuild: {len(df):,} rows")

        # ── Keep only described columns ──────────────────────────────
        keep_cols = list(COLUMN_DESCRIPTIONS.keys())
        extra = [c for c in df.columns if c not in keep_cols]
        if extra:
            df = df.drop(columns=extra)
        # Ensure all expected columns exist (may be absent in partial data)
        for col in keep_cols:
            if col not in df.columns:
                df[col] = None

        df = df[keep_cols]  # enforce order

        df = p.clean(
            df,
            numeric=[
                "radiant_ra_deg", "radiant_dec_deg", "v_g_kms",
                "a_au", "e", "i_deg", "peri_deg", "node_deg", "q_au",
                "duration_sec", "peak_abs_magnitude", "peak_height_km",
            ],
        )

        # ── Quick stats ──────────────────────────────────────────────
        n_total = len(df)
        date_min = df["datetime_utc"].min()
        date_max = df["datetime_utc"].max()
        date_min_str = date_min.strftime("%Y-%m-%d") if pd.notna(date_min) else "N/A"
        date_max_str = date_max.strftime("%Y-%m-%d") if pd.notna(date_max) else "N/A"

        n_sporadic = int((df["shower_code"] == "...").sum())
        n_shower = n_total - n_sporadic
        sporadic_pct = 100 * n_sporadic / n_total if n_total else 0

        top5 = (
            df[df["shower_code"] != "..."]["shower_code"]
            .value_counts()
            .head(5)
        )
        top5_str = ", ".join(
            f"{code} ({cnt:,})" for code, cnt in top5.items()
        ) if not top5.empty else "N/A"

        median_vg = df["v_g_kms"].median()
        max_vg = df["v_g_kms"].max()
        median_vg_str = f"{median_vg:.1f}" if pd.notna(median_vg) else "N/A"
        max_vg_str = f"{max_vg:.1f}" if pd.notna(max_vg) else "N/A"

        quick_stats = (
            f"- **{n_total:,}** meteor trajectories ({date_min_str} to {date_max_str})\n"
            f"- **{n_shower:,}** shower meteors ({100 - sporadic_pct:.0f}%) "
            f"and **{n_sporadic:,}** sporadics ({sporadic_pct:.0f}%)\n"
            f"- Top 5 showers by count: {top5_str}\n"
            f"- Median geocentric velocity: **{median_vg_str} km/s**; "
            f"fastest detected: **{max_vg_str} km/s**"
        )

        usage = '''\
```python
from datasets import load_dataset
import pandas as pd

ds = load_dataset("juliensimon/global-meteor-network", split="train")
df = ds.to_pandas()

# Shower vs sporadic breakdown
print(df["shower_code"].value_counts().head(10))

# Velocity distribution by shower
import matplotlib.pyplot as plt
showers = df[df["shower_code"] != "..."]
top = showers["shower_code"].value_counts().head(6).index
showers[showers["shower_code"].isin(top)].boxplot(
    column="v_g_kms", by="shower_code", figsize=(10, 5)
)
plt.suptitle("")
plt.title("Geocentric Velocity Distribution by Meteor Shower")
plt.ylabel("v_g (km/s)")
plt.show()

# Radiant sky map
fig, ax = plt.subplots(figsize=(12, 6))
scatter = ax.scatter(
    df["radiant_ra_deg"], df["radiant_dec_deg"],
    c=df["v_g_kms"], s=0.5, cmap="plasma", alpha=0.3
)
plt.colorbar(scatter, label="v_g (km/s)")
ax.set_xlabel("RA (degrees)")
ax.set_ylabel("Dec (degrees)")
ax.set_title("GMN Meteor Radiants on the Sky")
plt.show()
```'''

        p.publish(
            df,
            filename="gmn_meteors.parquet",
            min_rows=10_000,
            expected_columns=[
                "datetime_utc", "shower_code",
                "radiant_ra_deg", "radiant_dec_deg", "v_g_kms",
            ],
            critical_columns=["datetime_utc", "v_g_kms"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update GMN meteors: {n_total:,} trajectories",
        )

    print("Done.")


if __name__ == "__main__":
    main()
