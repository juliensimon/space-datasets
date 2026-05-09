#!/usr/bin/env python3
"""Fetch Perseverance MEDA weather data from PDS and upload to HF.

Source: PDS Atmospheres Node -- Mars2020 MEDA derived environmental data.
https://pds-atmospheres.nmsu.edu/PDS/data/PDS4/Mars2020/mars2020_meda/data_derived_env/

Incremental: tracks the last-ingested sol and only fetches new sol directories.
"""

import io
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

BASE_URL = "https://pds-atmospheres.nmsu.edu/PDS/data/PDS4/Mars2020/mars2020_meda/data_derived_env"
HF_REPO = "juliensimon/mars-perseverance-weather"
PARQUET_NAME = "meda_weather.parquet"
TIMEOUT = 60
MIN_ROWS = 100
WORKERS = 8  # conservative for PDS server

# CSV types to download per sol (skip ANCILLARY -- rover position, not weather)
CSV_TYPES = ["PS", "RHS", "TIRS"]

# ── Column mapping ───────────────────────────────────────────────────
RENAME_MAP = {
    "SCLK": "sclk",
    "LMST": "lmst",
    "LTST": "ltst",
    "PRESSURE": "pressure_pa",
    "PRESSURE_UNCERTAINTY": "pressure_uncertainty_pa",
    "TRANSDUCER": "transducer",
    "LOCAL_RELATIVE_HUMIDITY": "relative_humidity_pct",
    "LOCAL_RELATIVE_HUMIDITY_UNCERTAINTY": "relative_humidity_uncertainty_pct",
    "HUMIDITY_LOCAL_TEMP": "humidity_sensor_temp_k",
    "HUMIDITY_LOCAL_TEMP_UNCERTAINTY": "humidity_sensor_temp_uncertainty_k",
    "VOLUME_MIXING_RATIO": "volume_mixing_ratio",
    "VOLUME_MIXING_RATIO_UNCERTAINTY": "volume_mixing_ratio_uncertainty",
    "DOWNWARD_LW_IRRADIANCE": "downward_lw_irradiance_wm2",
    "DOWNWARD_LW_IRRADIANCE_UNCERTAINTY": "downward_lw_irradiance_uncertainty_wm2",
    "UPWARD_LW_IRRADIANCE": "upward_lw_irradiance_wm2",
    "UPWARD_LW_UNCERTAINTY": "upward_lw_irradiance_uncertainty_wm2",
    "RSM_HEAD_OUTSIDE_TIRS_UPWARD_LOOKING_FOV": "rsm_head_outside_tirs_up_fov",
    "WHEEL_OUTSIDE_TIRS_DOWNWARD_LOOKING_FOV": "wheel_outside_tirs_down_fov",
    "SUN_OUTSIDE_TIRS_FOV": "sun_outside_tirs_fov",
    "ROVER_LOW_TILT": "rover_low_tilt",
    "TIRS_GROUND_FOOTPRINT_NOT_IN_SHADOW": "tirs_ground_not_in_shadow",
    "ROVER_HGA_OFF": "rover_hga_off",
    "SKYCAM_OFF": "skycam_off",
    "ROVER_STILL": "rover_still",
}

NUMERIC_COLS = [
    "sclk", "pressure_pa", "pressure_uncertainty_pa", "transducer",
    "relative_humidity_pct", "relative_humidity_uncertainty_pct",
    "humidity_sensor_temp_k", "humidity_sensor_temp_uncertainty_k",
    "volume_mixing_ratio", "volume_mixing_ratio_uncertainty",
    "downward_lw_irradiance_wm2", "downward_lw_irradiance_uncertainty_wm2",
    "upward_lw_irradiance_wm2", "upward_lw_irradiance_uncertainty_wm2",
]

# ── Column descriptions ─────────────────────────────────────────────
COLUMN_DESCRIPTIONS = {
    "sclk": "Spacecraft clock tick count (continuous integer, ~1 Hz rate); serves as the primary unique timestamp for merging sensor data",
    "lmst": "Local Mean Solar Time at Jezero Crater (format 'sol HH:MM:SS'); based on a fixed Mars rotation period",
    "ltst": "Local True Solar Time at Jezero Crater (format 'sol HH:MM:SS'); corrected for Mars orbital eccentricity -- differs from LMST by up to ~50 minutes",
    "sol": "Perseverance sol number since landing; sol 0 = Feb 18 2021; each sol ~1.0275 Earth days",
    "pressure_pa": "Atmospheric pressure in Pa at Jezero Crater floor; mean ~750 Pa (0.75% of Earth sea level); seasonal range ~600-900 Pa due to CO2 polar cap condensation/sublimation",
    "pressure_uncertainty_pa": "Pressure sensor measurement uncertainty in Pa (typically <1 Pa)",
    "transducer": "Pressure transducer redundancy identifier (1 or 2); MEDA PS has two sensors for cross-validation",
    "relative_humidity_pct": "Local relative humidity in percent (0-100); peaks near nighttime when temperatures approach frost point; sparse -- null for most daytime readings",
    "relative_humidity_uncertainty_pct": "Humidity measurement uncertainty in percent",
    "humidity_sensor_temp_k": "Temperature of the humidity sensor element in Kelvin; required for humidity calibration",
    "humidity_sensor_temp_uncertainty_k": "Humidity sensor temperature uncertainty in Kelvin",
    "volume_mixing_ratio": "Water vapor volume mixing ratio (mol/mol, dimensionless); Mars typical values 10-300 ppmv depending on season and latitude; null when humidity sensor not active",
    "volume_mixing_ratio_uncertainty": "Water vapor volume mixing ratio uncertainty (mol/mol)",
    "downward_lw_irradiance_wm2": "Downward longwave (thermal IR, 8-50 um) irradiance in W/m2; measures atmospheric thermal emission -- sensitive to dust loading and cloud cover",
    "downward_lw_irradiance_uncertainty_wm2": "Downward LW irradiance measurement uncertainty in W/m2",
    "upward_lw_irradiance_wm2": "Upward longwave irradiance from the surface in W/m2; proxy for ground skin temperature via Stefan-Boltzmann: T_surface = (upward_lw / 5.67e-8)^0.25 K",
    "upward_lw_irradiance_uncertainty_wm2": "Upward LW irradiance measurement uncertainty in W/m2",
    "rsm_head_outside_tirs_up_fov": "Quality flag: True if RSM (Remote Sensing Mast) head is outside TIRS upward-looking field of view",
    "wheel_outside_tirs_down_fov": "Quality flag: True if rover wheel is outside TIRS downward-looking field of view",
    "sun_outside_tirs_fov": "Quality flag: True if Sun is outside TIRS field of view (no direct solar contamination)",
    "rover_low_tilt": "Quality flag: True if rover platform tilt is below threshold for valid TIRS measurements",
    "tirs_ground_not_in_shadow": "Quality flag: True if TIRS ground footprint is not in shadow from rover or mast",
    "rover_hga_off": "Quality flag: True if High Gain Antenna is off (reduces electromagnetic interference)",
    "skycam_off": "Quality flag: True if SkyCam is off (reduces thermal interference with TIRS)",
    "rover_still": "Quality flag: True if rover is stationary (no drive-induced vibration in measurements)",
}

DESCRIPTION = """\
Surface weather measurements from the Mars Environmental Dynamics Analyzer (MEDA) on NASA's \
Perseverance rover in Jezero Crater, Mars. Combines three derived data products from the PDS \
Atmospheres Node: atmospheric pressure (PS), relative humidity (RHS), and thermal infrared \
upward/downward longwave irradiance (TIRS).

Records are merged on spacecraft clock (SCLK) to produce a unified weather timeline, downsampled \
to 1-minute cadence from the original ~1 Hz raw data. This preserves 100% of the time coverage \
while keeping the dataset manageable.

The Martian atmosphere is thin (mean surface pressure around 610 Pa, less than 1% of Earth's) and \
composed predominantly of CO2. Despite its low density, it drives vigorous meteorological phenomena: \
strong diurnal thermal tides produce a regular daily pressure oscillation of several percent, \
seasonal sublimation and condensation of the polar CO2 ice caps cause the global mean pressure to \
vary by roughly 25% over a Martian year, and regional and global dust storms can dramatically alter \
atmospheric opacity and thermal structure.

The thermal infrared measurements from TIRS are particularly valuable because they serve as a proxy \
for ground and near-surface air temperature. Humidity measurements, though sparse and concentrated \
in nighttime hours, constrain the water cycle in equatorial Mars and the exchange of water vapor \
between the regolith and atmosphere."""


# ── Directory crawling ───────────────────────────────────────────────

def list_links(url):
    """Parse an Apache directory listing and return href links, with 3 retries."""
    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=TIMEOUT)
            resp.raise_for_status()
            return re.findall(r'href="([^"]+)"', resp.text)
        except Exception as exc:
            if attempt == 2:
                raise
            print(f"    list_links attempt {attempt + 1}/3 failed ({exc}), retrying...")
            time.sleep(5 * (attempt + 1))
    return []  # unreachable, but satisfies type checkers


def discover_sol_range_dirs():
    """Return sorted list of sol-range directory names (e.g. sol_0000_0089)."""
    links = list_links(BASE_URL + "/")
    dirs = [l.strip("/") for l in links if l.startswith("sol_") and l.endswith("/")]
    return sorted(dirs)


def discover_sol_dirs(range_dir):
    """Return sorted list of individual sol directory names within a range dir."""
    url = f"{BASE_URL}/{range_dir}/"
    links = list_links(url)
    dirs = [l.strip("/") for l in links if l.startswith("sol_") and l.endswith("/")]
    return sorted(dirs)


# ── CSV downloading and parsing ──────────────────────────────────────

def fetch_sol(range_dir, sol_dir):
    """Fetch and merge PS, RHS, TIRS CSVs for one sol.

    Uses a single directory listing to resolve all CSV URLs, then downloads
    each file. Called concurrently from a ThreadPoolExecutor.
    """
    dir_url = f"{BASE_URL}/{range_dir}/{sol_dir}/"
    try:
        links = list_links(dir_url)
    except Exception:
        return None

    frames = {}
    for csv_type in CSV_TYPES:
        pattern = re.compile(rf"WE__\d{{4}}___________DER_{csv_type}_+P\d{{2}}\.CSV", re.IGNORECASE)
        matches = [l for l in links if pattern.match(l)]
        if not matches:
            continue
        try:
            resp = requests.get(f"{dir_url}{matches[0]}", timeout=TIMEOUT)
            resp.raise_for_status()
            df = pd.read_csv(io.StringIO(resp.text))
            if not df.empty:
                frames[csv_type] = df
        except Exception:
            pass

    if not frames:
        return None

    # Ensure SCLK is numeric in all frames
    for csv_type in frames:
        if "SCLK" in frames[csv_type].columns:
            frames[csv_type]["SCLK"] = pd.to_numeric(
                frames[csv_type]["SCLK"], errors="coerce"
            )
            frames[csv_type] = frames[csv_type].dropna(subset=["SCLK"])

    # Merge on SCLK
    merged = None
    for csv_type, df in frames.items():
        if merged is None:
            merged = df
        else:
            right_cols = [c for c in df.columns if c not in ("LMST", "LTST")]
            merged = merged.merge(df[right_cols], on="SCLK", how="outer")

    sol_match = re.search(r"sol_(\d+)$", sol_dir)
    if sol_match:
        merged["sol"] = int(sol_match.group(1))

    if "SCLK" in merged.columns and len(merged) > 1000:
        merged["_sclk_min"] = pd.to_numeric(merged["SCLK"], errors="coerce") // 60
        merged = merged.drop_duplicates(subset=["_sclk_min"], keep="first")
        merged = merged.drop(columns=["_sclk_min"])

    return merged


def sol_number_from_dir(sol_dir):
    """Extract the sol number from a directory name like sol_0001."""
    m = re.search(r"sol_(\d+)$", sol_dir)
    return int(m.group(1)) if m else -1


# ── Transform ────────────────────────────────────────────────────────

def transform(df):
    """Rename columns, coerce types, sort."""
    df = df.rename(columns=RENAME_MAP)
    df.columns = [c.lower().replace(" ", "_") for c in df.columns]

    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "sol" in df.columns:
        df["sol"] = df["sol"].astype("Int64")

    sort_cols = [c for c in ["sol", "sclk"] if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols).reset_index(drop=True)

    return df


# ── Lightweight last-sol lookup ──────────────────────────────────────

def get_last_sol() -> int:
    """Return max(sol) from the HF dataset statistics API — no parquet download."""
    url = "https://datasets-server.huggingface.co/statistics"
    params = {"dataset": HF_REPO, "config": "default", "split": "train"}
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        for col in resp.json().get("statistics", []):
            if col.get("column_name") == "sol":
                return int(col["column_statistics"]["max"])
    except Exception as e:
        print(f"  Could not query HF statistics API ({e})")
    return -1


# ── Main ─────────────────────────────────────────────────────────────

EXPECTED_COLUMNS = [
    "sclk", "lmst", "ltst", "sol", "pressure_pa",
    "downward_lw_irradiance_wm2", "upward_lw_irradiance_wm2",
]

CRITICAL_COLUMNS = ["sclk", "sol", "pressure_pa"]


def main():
    print("=== Perseverance MEDA Weather ===")

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Mars Perseverance MEDA Weather",
        description=DESCRIPTION,
        tags=["space", "mars", "perseverance", "meda", "weather", "nasa",
              "planetary-science", "open-data", "tabular-data", "parquet"],
        source_url="https://pds-atmospheres.nmsu.edu/PDS/data/PDS4/Mars2020/mars2020_meda/data_derived_env/",
        task_categories=["tabular-regression", "time-series-forecasting"],
        collection_url="https://huggingface.co/collections/juliensimon/space-probe-and-mission-datasets-69c3fe82d410a42b1e313167",
        banner={"url": "https://images-assets.nasa.gov/image/PIA19808/PIA19808~small.jpg",
                "alt": "NASA's Curiosity rover on the surface of Mars",
                "credit": "NASA/JPL-Caltech/MSSS"},
        update_schedule="Monthly (1st of each month at 08:00 UTC)",
        related_datasets=[
            "juliensimon/mars-craters-robbins",
            "juliensimon/neo-close-approaches",
            "juliensimon/nasa-exoplanets",
        ],
    ) as p:
        # ── Determine last ingested sol (no parquet download) ────────
        last_sol = get_last_sol()
        if last_sol >= 0:
            print(f"  Incremental mode: fetching sols > {last_sol}")
        else:
            print("  No existing sol info — fetching all available sols")

        # ── Phase 1: discover which range dirs need scanning ─────────
        print("Discovering sol-range directories...")
        try:
            range_dirs = discover_sol_range_dirs()
        except Exception as e:
            print(f"  ERROR: Could not list PDS directories: {e}")
            range_dirs = []
        print(f"  Found {len(range_dirs)} sol-range directories")

        range_dirs_to_scan = [
            rd for rd in range_dirs
            if not (re.search(r"sol_\d+_(\d+)$", rd) and
                    int(re.search(r"sol_\d+_(\d+)$", rd).group(1)) <= last_sol)
        ]
        skipped = len(range_dirs) - len(range_dirs_to_scan)
        print(f"  Skipping {skipped} fully-ingested range dirs; scanning {len(range_dirs_to_scan)}")

        # ── Phase 2: parallel discovery of sol dirs within each range ─
        def _discover_range(rd):
            try:
                return rd, discover_sol_dirs(rd)
            except Exception as e:
                print(f"    Error listing {rd}: {e}")
                return rd, []

        sols_to_fetch = []
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            for rd, sol_dirs in ex.map(_discover_range, range_dirs_to_scan):
                for sol_dir in sol_dirs:
                    if sol_number_from_dir(sol_dir) > last_sol:
                        sols_to_fetch.append((rd, sol_dir))

        print(f"  {len(sols_to_fetch)} sols to fetch")

        # ── Phase 3: parallel sol fetching ───────────────────────────
        new_frames = []
        sols_fetched = 0

        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futures = {ex.submit(fetch_sol, rd, sd): sd for rd, sd in sols_to_fetch}
            for future in as_completed(futures):
                sol_dir = futures[future]
                try:
                    df_sol = future.result()
                    if df_sol is not None and len(df_sol) > 0:
                        new_frames.append(df_sol)
                        sols_fetched += 1
                        if sols_fetched % 25 == 0:
                            print(f"    {sols_fetched}/{len(sols_to_fetch)} sols fetched...")
                except Exception as e:
                    print(f"    Error fetching {sol_dir}: {e}")

        print(f"  Fetched {sols_fetched} new sols")

        # ── Combine new sols ─────────────────────────────────────────
        if not new_frames:
            print("  No new sols found — nothing to publish")
            sys.exit(0)

        df = pd.concat(new_frames, ignore_index=True)
        print(f"  Combined: {len(df):,} rows from {sols_fetched} new sols")

        # ── Transform ────────────────────────────────────────────────
        df = transform(df)

        df = p.clean(df, numeric=NUMERIC_COLS, drop_mostly_null_threshold=0.95)

        # Keep only described columns
        df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

        # ── Stats ────────────────────────────────────────────────────
        n_rows = len(df)
        n_sols = int(df["sol"].nunique())
        sol_min = int(df["sol"].min())
        sol_max = int(df["sol"].max())

        pressure_mean = df["pressure_pa"].mean()
        pressure_min = df["pressure_pa"].min()
        pressure_max = df["pressure_pa"].max()

        has_humidity = "relative_humidity_pct" in df.columns
        humidity_nonnull = int(df["relative_humidity_pct"].notna().sum()) if has_humidity else 0

        quick_stats = f"""\
- **{n_rows:,}** measurements across **{n_sols}** sols (sol {sol_min}--{sol_max})
- Mean surface pressure: **{pressure_mean:.1f} Pa** (range {pressure_min:.1f}--{pressure_max:.1f} Pa)
- **{humidity_nonnull:,}** humidity readings available"""

        usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/mars-perseverance-weather", split="train")
df = ds.to_pandas()

# Daily pressure cycle for a given sol
sol_100 = df[df["sol"] == 100]
sol_100.plot(x="ltst", y="pressure_pa", title="Sol 100 pressure")

# Seasonal pressure variation (Mars has ~25% annual pressure swing)
import matplotlib.pyplot as plt

daily_avg = df.groupby("sol")["pressure_pa"].mean()
daily_avg.plot(title="Mars surface pressure by sol", figsize=(12, 4))
plt.ylabel("Pressure (Pa)")
plt.tight_layout()
plt.show()

# Ground temperature proxy from upward thermal IR
df["ground_temp_proxy"] = (df["upward_lw_irradiance_wm2"] / 5.67e-8) ** 0.25
daily_temp = df.groupby("sol")["ground_temp_proxy"].agg(["min", "max"])
daily_temp.plot(title="Ground temperature range by sol")
plt.show()
```"""

        p.publish(
            df,
            # Monthly shard: never overwrites existing historical parquet
            filename=f"meda_weather_{datetime.utcnow().strftime('%Y_%m')}.parquet",
            min_rows=MIN_ROWS,
            max_null_pct=0.50,
            expected_columns=EXPECTED_COLUMNS,
            critical_columns=CRITICAL_COLUMNS,
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Add MEDA weather shard: {n_rows:,} rows, sols {sol_min}-{sol_max}",
        )
    print(f"Done. {n_rows:,} rows, sols {sol_min}-{sol_max}.")


if __name__ == "__main__":
    main()
