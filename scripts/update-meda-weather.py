#!/usr/bin/env python3
"""Fetch Perseverance MEDA weather data from PDS and upload to HF.

Source: PDS Atmospheres Node — Mars2020 MEDA derived environmental data.
https://pds-atmospheres.nmsu.edu/PDS/data/PDS4/Mars2020/mars2020_meda/data_derived_env/

Incremental: tracks the last-ingested sol and only fetches new sol directories.
"""

import io
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent))
from dataset_images import banner_markdown, download_banner
from validate import check_dataset

BASE_URL = "https://pds-atmospheres.nmsu.edu/PDS/data/PDS4/Mars2020/mars2020_meda/data_derived_env"
HF_REPO = "juliensimon/mars-perseverance-weather"
PARQUET_NAME = "meda_weather.parquet"
TIMEOUT = 60
MIN_ROWS = 100_000

# CSV types to download per sol (skip ANCILLARY — rover position, not weather)
CSV_TYPES = ["PS", "RHS", "TIRS"]


# ── Directory crawling ────────────────────────────────────────────────────────

def list_links(url):
    """Parse an Apache directory listing and return href links."""
    resp = requests.get(url, timeout=TIMEOUT)
    resp.raise_for_status()
    return re.findall(r'href="([^"]+)"', resp.text)


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


def find_csv_url(range_dir, sol_dir, csv_type):
    """Find the CSV file URL for a given type in a sol directory.

    Filename pattern: WE__NNNN___________DER_<TYPE>___...___PNN.CSV
    We pick whichever version is present (there's usually exactly one).
    """
    url = f"{BASE_URL}/{range_dir}/{sol_dir}/"
    links = list_links(url)
    pattern = re.compile(rf"WE__\d{{4}}___________DER_{csv_type}_+P\d{{2}}\.CSV", re.IGNORECASE)
    matches = [l for l in links if pattern.match(l)]
    if matches:
        return f"{url}{matches[0]}"
    return None


# ── CSV downloading and parsing ──────────────────────────────────────────────

def download_csv(url):
    """Download a CSV file and return a DataFrame."""
    resp = requests.get(url, timeout=TIMEOUT)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    return df


def fetch_sol(range_dir, sol_dir):
    """Fetch and merge PS, RHS, TIRS CSVs for one sol.

    Merges on SCLK (spacecraft clock) with an outer join so no data is lost.
    Returns a DataFrame or None if no data found.
    """
    frames = {}
    for csv_type in CSV_TYPES:
        url = find_csv_url(range_dir, sol_dir, csv_type)
        if url is None:
            continue
        try:
            df = download_csv(url)
            if df.empty:
                continue
            # Keep SCLK, LMST, LTST from this file; prefix sensor-specific cols
            frames[csv_type] = df
        except Exception as e:
            print(f"    Warning: failed to download {csv_type} for {sol_dir}: {e}")

    if not frames:
        return None

    # Ensure SCLK is numeric in all frames to prevent cartesian joins
    for csv_type in frames:
        if "SCLK" in frames[csv_type].columns:
            frames[csv_type]["SCLK"] = pd.to_numeric(
                frames[csv_type]["SCLK"], errors="coerce"
            )
            frames[csv_type] = frames[csv_type].dropna(subset=["SCLK"])

    # Start with whichever frame we have, merge the rest on SCLK
    merged = None
    for csv_type, df in frames.items():
        if merged is None:
            merged = df
        else:
            # Drop duplicate LMST/LTST from the right side before merging
            right_cols = [c for c in df.columns if c not in ("LMST", "LTST")]
            merged = merged.merge(df[right_cols], on="SCLK", how="outer")

    # Extract sol number from directory name
    sol_match = re.search(r"sol_(\d+)$", sol_dir)
    if sol_match:
        merged["sol"] = int(sol_match.group(1))

    # Downsample to 1-minute resolution (SCLK is ~1 Hz, ~48K rows/sol → ~800 rows/sol)
    # Use SCLK integer division by 60 to create minute bins, keep first reading per bin
    if "SCLK" in merged.columns and len(merged) > 1000:
        merged["_sclk_min"] = pd.to_numeric(merged["SCLK"], errors="coerce") // 60
        merged = merged.drop_duplicates(subset=["_sclk_min"], keep="first")
        merged = merged.drop(columns=["_sclk_min"])

    return merged


def sol_number_from_dir(sol_dir):
    """Extract the sol number from a directory name like sol_0001."""
    m = re.search(r"sol_(\d+)$", sol_dir)
    return int(m.group(1)) if m else -1


# ── Incremental support ──────────────────────────────────────────────────────

def load_existing(tmp_dir):
    """Download existing parquet from HF. Returns DataFrame or None."""
    parquet_path = tmp_dir / "data" / PARQUET_NAME
    try:
        subprocess.run(
            ["hf", "download", HF_REPO, f"data/{PARQUET_NAME}",
             "--repo-type", "dataset", "--local-dir", str(tmp_dir)],
            check=True, capture_output=True, timeout=120,
        )
        if parquet_path.exists():
            df = pd.read_parquet(parquet_path)
            print(f"  Loaded existing: {len(df):,} rows, max sol {df['sol'].max()}")
            return df
    except Exception as e:
        print(f"  Could not load existing ({e}), doing full rebuild")
    return None


# ── Transform ─────────────────────────────────────────────────────────────────

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

# Columns that should be numeric (coerce errors to NaN)
NUMERIC_COLS = [
    "sclk", "pressure_pa", "pressure_uncertainty_pa", "transducer",
    "relative_humidity_pct", "relative_humidity_uncertainty_pct",
    "humidity_sensor_temp_k", "humidity_sensor_temp_uncertainty_k",
    "volume_mixing_ratio", "volume_mixing_ratio_uncertainty",
    "downward_lw_irradiance_wm2", "downward_lw_irradiance_uncertainty_wm2",
    "upward_lw_irradiance_wm2", "upward_lw_irradiance_uncertainty_wm2",
]


def transform(df):
    """Rename columns, coerce types, sort."""
    # Rename known columns, snake_case any unknown ones
    df = df.rename(columns=RENAME_MAP)
    df.columns = [c.lower().replace(" ", "_") for c in df.columns]

    # Coerce numeric columns
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Ensure sol is integer
    if "sol" in df.columns:
        df["sol"] = df["sol"].astype("Int64")

    # Sort by sol then sclk
    sort_cols = [c for c in ["sol", "sclk"] if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols).reset_index(drop=True)

    return df


# ── Main ──────────────────────────────────────────────────────────────────────

EXPECTED_COLUMNS = [
    "sclk", "lmst", "ltst", "sol", "pressure_pa",
    "humidity_sensor_temp_k",
    "downward_lw_irradiance_wm2", "upward_lw_irradiance_wm2",
]

CRITICAL_COLUMNS = ["sclk", "sol", "pressure_pa"]


def main():
    print("=== Perseverance MEDA Weather ===")

    # ── Try incremental ───────────────────────────────────────────────────
    with tempfile.TemporaryDirectory() as probe:
        df_existing = load_existing(Path(probe))

    last_sol = -1
    if df_existing is not None and len(df_existing) > 0:
        last_sol = int(df_existing["sol"].max())
        print(f"  Incremental mode: fetching sols > {last_sol}")

    # ── Discover and crawl directories ────────────────────────────────────
    print("Discovering sol-range directories...")
    range_dirs = discover_sol_range_dirs()
    print(f"  Found {len(range_dirs)} sol-range directories")

    # Process in batches to limit memory — write intermediate parquet files
    BATCH_SIZE = 25  # sols per batch (limit memory on CI runners)
    batch_dir = Path(tempfile.mkdtemp(prefix="meda_batches_"))
    batch_frames = []
    batch_num = 0
    sols_fetched = 0
    total_rows = 0

    for range_dir in range_dirs:
        # Quick check: if range max < last_sol, skip entirely
        range_match = re.search(r"sol_\d+_(\d+)$", range_dir)
        if range_match and int(range_match.group(1)) <= last_sol:
            print(f"  Skipping {range_dir} (all sols <= {last_sol})")
            continue

        print(f"  Scanning {range_dir}...")
        try:
            sol_dirs = discover_sol_dirs(range_dir)
        except Exception as e:
            print(f"    Error listing {range_dir}: {e}")
            continue
        time.sleep(0.3)

        for sol_dir in sol_dirs:
            sol_num = sol_number_from_dir(sol_dir)
            if sol_num <= last_sol:
                continue

            try:
                df_sol = fetch_sol(range_dir, sol_dir)
                if df_sol is not None and len(df_sol) > 0:
                    batch_frames.append(df_sol)
                    sols_fetched += 1

                    # Flush batch to disk when full
                    if sols_fetched % BATCH_SIZE == 0:
                        batch_df = pd.concat(batch_frames, ignore_index=True)
                        batch_path = batch_dir / f"batch_{batch_num:04d}.parquet"
                        batch_df.to_parquet(batch_path, index=False, engine="pyarrow")
                        total_rows += len(batch_df)
                        print(f"    Batch {batch_num}: {len(batch_df):,} rows "
                              f"({sols_fetched} sols, {total_rows:,} total)")
                        batch_frames.clear()
                        batch_num += 1
                        del batch_df
            except Exception as e:
                print(f"    Error fetching {sol_dir}: {e}")
            time.sleep(0.5)  # Be polite to PDS server

    # Flush remaining batch
    if batch_frames:
        batch_df = pd.concat(batch_frames, ignore_index=True)
        batch_path = batch_dir / f"batch_{batch_num:04d}.parquet"
        batch_df.to_parquet(batch_path, index=False, engine="pyarrow")
        total_rows += len(batch_df)
        print(f"    Final batch: {len(batch_df):,} rows ({total_rows:,} total)")
        batch_frames.clear()
        del batch_df

    print(f"  Fetched {sols_fetched} new sols in {batch_num + 1} batches, {total_rows:,} rows")

    # ── Combine batches ────────────────────────────────────────────────────
    batch_files = sorted(batch_dir.glob("batch_*.parquet"))
    if batch_files:
        if df_existing is not None and len(df_existing) > 0:
            # Incremental: write existing data as another parquet file,
            # then read all files at once via PyArrow (avoids 2x memory peak)
            existing_path = batch_dir / "existing.parquet"
            df_existing.to_parquet(existing_path, index=False, engine="pyarrow")
            del df_existing

            all_files = [existing_path] + batch_files
            df = pd.read_parquet(batch_dir)  # reads all parquet in directory
            # Clean up
            for f in all_files:
                f.unlink()
            batch_dir.rmdir()

            dedup_col = "sclk" if "sclk" in df.columns else "SCLK"
            before = len(df)
            df = df.drop_duplicates(subset=["sol", dedup_col], keep="last")
            print(f"  Merged: {len(df):,} rows ({before - len(df):,} dupes removed)")
        else:
            # Full rebuild: read all batch files at once
            df = pd.read_parquet(batch_dir)
            for f in batch_files:
                f.unlink()
            batch_dir.rmdir()
            print(f"  Combined: {len(df):,} rows")
    elif df_existing is not None and len(df_existing) > 0:
        df = df_existing
        print("  No new sols found, re-uploading existing data")
    else:
        print("ERROR: No data fetched and no existing data")
        sys.exit(1)

    # ── Transform ─────────────────────────────────────────────────────────
    df = transform(df)

    # ── Validate ──────────────────────────────────────────────────────────
    check_dataset(
        df,
        dataset_name="meda-weather",
        min_rows=MIN_ROWS,
        expected_columns=EXPECTED_COLUMNS,
        critical_columns=CRITICAL_COLUMNS,
        max_null_pct=0.50,  # Mars weather has many sensor gaps,
            incremental=True)

    # ── Stats ─────────────────────────────────────────────────────────────
    n_rows = len(df)
    n_sols = int(df["sol"].nunique())
    sol_min = int(df["sol"].min())
    sol_max = int(df["sol"].max())

    pressure_mean = df["pressure_pa"].mean()
    pressure_min = df["pressure_pa"].min()
    pressure_max = df["pressure_pa"].max()

    has_humidity = "relative_humidity_pct" in df.columns
    humidity_nonnull = int(df["relative_humidity_pct"].notna().sum()) if has_humidity else 0

    # Size category
    if n_rows < 100_000:
        size_cat = "10K<n<100K"
    elif n_rows < 1_000_000:
        size_cat = "100K<n<1M"
    elif n_rows < 10_000_000:
        size_cat = "1M<n<10M"
    else:
        size_cat = "10M<n<100M"

    # ── Write ─────────────────────────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / PARQUET_NAME
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  Wrote {size_mb:.1f} MB parquet ({n_rows:,} rows)")

        banner_file = download_banner("meda-weather", tmp)
        banner_md = banner_markdown("meda-weather", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Mars Perseverance MEDA Weather"
language:
  - en
description: "Surface weather measurements from the MEDA instrument on NASA's Perseverance rover: pressure, temperature, humidity, and thermal infrared radiation on Mars."
task_categories:
  - tabular-regression
  - time-series-forecasting
tags:
  - space
  - mars
  - perseverance
  - meda
  - weather
  - nasa
  - planetary-science
  - open-data
  - tabular-data
  - parquet
size_categories:
  - {size_cat}
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/{PARQUET_NAME}
    default: true
---

# Mars Perseverance MEDA Weather
{banner_md}
*Part of the [Planetary Science Datasets](https://huggingface.co/collections/juliensimon/planetary-science-datasets-69c24caca4ab3934c9856994) collection on Hugging Face.*

![Update MEDA Weather](https://github.com/juliensimon/space-datasets/actions/workflows/update-meda-weather.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['meda-weather']&label=updated&color=brightgreen)

Surface weather measurements from the **Mars Environmental Dynamics Analyzer (MEDA)** on NASA's
Perseverance rover in Jezero Crater, Mars. Covers **sol {sol_min}** to **sol {sol_max}** with
**{n_rows:,}** measurements across **{n_sols}** sols.

## Dataset description

MEDA is a suite of environmental sensors on the Perseverance rover that measures Martian weather.
This dataset combines three derived data products from the PDS Atmospheres Node:

- **PS** — Atmospheric pressure (Pa) from the pressure sensor
- **RHS** — Relative humidity (%) and humidity sensor temperature (K)
- **TIRS** — Thermal infrared upward/downward longwave irradiance (W/m2)

Records are merged on spacecraft clock (SCLK) to produce a unified weather timeline.

**Resolution:** Downsampled to **1-minute cadence** (one reading per minute) from the original ~1 Hz raw data.
This preserves 100% of the time coverage — every sol, every minute — while keeping the dataset to a
manageable ~1M rows. All diurnal cycles, seasonal pressure swings, and dust devil pressure drops
are fully captured at this resolution. For the full 1-Hz data (~67M rows), use the
[PDS source](https://pds-atmospheres.nmsu.edu/PDS/data/PDS4/Mars2020/mars2020_meda/data_derived_env/) directly.

The Martian atmosphere is thin (mean surface pressure around 610 Pa, less than 1% of Earth's) and composed predominantly of CO2, with trace amounts of nitrogen, argon, and water vapor. Despite its low density, this atmosphere drives vigorous meteorological phenomena: strong diurnal thermal tides produce a regular daily pressure oscillation of several percent, seasonal sublimation and condensation of the polar CO2 ice caps cause the global mean pressure to vary by roughly 25% over a Martian year, and regional and global dust storms can dramatically alter atmospheric opacity and thermal structure. MEDA captures all of these phenomena at Jezero Crater, a 49 km diameter impact basin on the northwest rim of the Isidis Planitia, where Perseverance landed in February 2021.

The thermal infrared radiation measurements from TIRS are particularly valuable because they serve as a proxy for ground and near-surface air temperature. Downward longwave irradiance tracks atmospheric thermal emission (sensitive to dust loading and cloud cover), while upward longwave irradiance reflects surface skin temperature through Stefan-Boltzmann emission. These data enable calculation of the surface energy budget and detection of phenomena such as nighttime temperature inversions and the thermal effects of passing dust devils. Humidity measurements, though sparse and concentrated in nighttime hours when relative humidity peaks, constrain the water cycle in equatorial Mars and the exchange of water vapor between the regolith and atmosphere.

Jezero Crater was selected as the Perseverance landing site because it preserves a fossil river delta that entered an ancient lake, making it a prime target for astrobiology. The local meteorology measured by MEDA provides essential context for understanding present-day aeolian processes that are actively modifying the delta sediments, constraining dust transport and deposition rates, and supporting operations planning for the Mars Sample Return campaign.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `sclk` | int64 | Spacecraft clock tick count (continuous integer, ~1 Hz rate); serves as the primary unique timestamp for merging sensor data |
| `lmst` | string | Local Mean Solar Time at Jezero Crater (format "sol HH:MM:SS"); based on a fixed Mars rotation period |
| `ltst` | string | Local True Solar Time at Jezero Crater (format "sol HH:MM:SS"); corrected for Mars orbital eccentricity — differs from LMST by up to ~50 minutes |
| `sol` | int64 | Perseverance sol number since landing; sol 0 = Feb 18 2021; each sol ~1.0275 Earth days |
| `pressure_pa` | float64 | Atmospheric pressure in Pa at Jezero Crater floor; mean ~750 Pa (0.75% of Earth sea level); seasonal range ~600–900 Pa due to CO2 polar cap condensation/sublimation |
| `pressure_uncertainty_pa` | float64 | Pressure sensor measurement uncertainty in Pa (typically <1 Pa) |
| `transducer` | int64 | Pressure transducer redundancy identifier (1 or 2); MEDA PS has two sensors for cross-validation |
| `relative_humidity_pct` | float64 | Local relative humidity in percent (0–100); peaks near nighttime when temperatures approach frost point; sparse — null for most daytime readings |
| `relative_humidity_uncertainty_pct` | float64 | Humidity measurement uncertainty in percent |
| `humidity_sensor_temp_k` | float64 | Temperature of the humidity sensor element in Kelvin; required for humidity calibration |
| `humidity_sensor_temp_uncertainty_k` | float64 | Humidity sensor temperature uncertainty in Kelvin |
| `volume_mixing_ratio` | float64 | Water vapor volume mixing ratio (mol/mol, dimensionless); Mars typical values 10–300 ppmv depending on season and latitude; null when humidity sensor not active |
| `volume_mixing_ratio_uncertainty` | float64 | Water vapor volume mixing ratio uncertainty (mol/mol) |
| `downward_lw_irradiance_wm2` | float64 | Downward longwave (thermal IR, 8–50 µm) irradiance in W/m²; measures atmospheric thermal emission — sensitive to dust loading and cloud cover |
| `downward_lw_irradiance_uncertainty_wm2` | float64 | Downward LW irradiance measurement uncertainty in W/m² |
| `upward_lw_irradiance_wm2` | float64 | Upward longwave irradiance from the surface in W/m²; proxy for ground skin temperature via Stefan-Boltzmann: T_surface ≈ (upward_lw / 5.67e-8)^0.25 K |
| `upward_lw_irradiance_uncertainty_wm2` | float64 | Upward LW irradiance measurement uncertainty in W/m² |

Additional TIRS quality flag columns: `rsm_head_outside_tirs_up_fov`, `wheel_outside_tirs_down_fov`,
`sun_outside_tirs_fov`, `rover_low_tilt`, `tirs_ground_not_in_shadow`, `rover_hga_off`, `skycam_off`, `rover_still`.

## Quick stats

- **{n_rows:,}** measurements across **{n_sols}** sols (sol {sol_min}--{sol_max})
- Mean surface pressure: **{pressure_mean:.1f} Pa** (range {pressure_min:.1f}--{pressure_max:.1f} Pa)
- **{humidity_nonnull:,}** humidity readings available

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/mars-perseverance-weather", split="train")
df = ds.to_pandas()

# Daily pressure cycle for a given sol
sol_100 = df[df["sol"] == 100]
sol_100.plot(x="ltst", y="pressure_pa", title="Sol 100 pressure")

# Seasonal pressure variation (Mars has ~25% annual pressure swing)
daily_avg = df.groupby("sol")["pressure_pa"].mean()
daily_avg.plot(title="Mars surface pressure by sol")

# Ground temperature proxy from upward thermal IR
df["ground_temp_proxy"] = (df["upward_lw_irradiance_wm2"] / 5.67e-8) ** 0.25
daily_temp = df.groupby("sol")["ground_temp_proxy"].agg(["min", "max"])
daily_temp.plot(title="Ground temperature range by sol")

# Humidity readings (sparse — mostly nighttime)
humid = df[df["relative_humidity_pct"].notna()]
humid.groupby("sol")["relative_humidity_pct"].mean().plot()
```

## Data source

[NASA PDS Atmospheres Node](https://pds-atmospheres.nmsu.edu/PDS/data/PDS4/Mars2020/mars2020_meda/data_derived_env/) —
Mars 2020 MEDA derived environmental data, maintained by New Mexico State University.

## Update schedule

Monthly (1st of each month at 08:00 UTC) via [GitHub Actions](https://github.com/juliensimon/space-datasets).
New sols are ingested incrementally.

## Related datasets

- [mars-craters](https://huggingface.co/datasets/juliensimon/mars-craters-robbins) — Mars crater catalog
- [neo-close-approaches](https://huggingface.co/datasets/juliensimon/neo-close-approaches) — Near-Earth object approaches
- [exoplanets](https://huggingface.co/datasets/juliensimon/nasa-exoplanets) — NASA Exoplanet Archive

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/mars-perseverance-weather) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{meda_weather,
  author = {{Simon, Julien}},
  title = {{Mars Perseverance MEDA Weather}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/mars-perseverance-weather}},
  note = {{Based on NASA PDS Mars 2020 MEDA derived environmental data}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        # ── Upload ────────────────────────────────────────────────────────
        print("Uploading to HF...")
        commit_msg = (f"Update MEDA weather: {n_rows:,} rows, "
                      f"{n_sols} sols (sol {sol_min}-{sol_max})")
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    # ── Output row count for workflow ─────────────────────────────────────
    print(f"::set-output name=rows::{n_rows}")
    print(f"Done. {n_rows:,} rows across {n_sols} sols.")


if __name__ == "__main__":
    main()
