#!/usr/bin/env python3
"""
Fetch NASA MAVEN Key Parameter (KP) in-situ data from LASP SDC and upload to HF.

MAVEN (Mars Atmosphere and Volatile EvolutioN) has been studying the Martian
upper atmosphere and its interaction with the solar wind since September 2014.
The KP dataset provides time-series measurements from multiple instruments at
4-8 second cadence.

Data source: https://lasp.colorado.edu/maven/sdc/public/data/sci/kp/insitu/
Incremental: downloads existing parquet from HF, fetches new months, merges.
"""

import io
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

from dataset_images import banner_markdown, download_banner
from validate import check_dataset


BASE_URL = "https://lasp.colorado.edu/maven/sdc/public/data/sci/kp/insitu/"
HF_REPO = "juliensimon/nasa-maven-kp-insitu"

# For initial build, start from 2025 to keep GH Actions runtime under 1 hour.
# Each file is ~43 MB text, ~30s download+parse. Future incremental runs extend.
START_YEAR = 2025
START_MONTH = 1

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "space-datasets/1.0 (https://github.com/juliensimon/space-datasets)"})


def list_tab_files(year: int, month: int) -> list[str]:
    """Fetch directory listing for a year/month and return .tab filenames."""
    url = f"{BASE_URL}{year:04d}/{month:02d}/"
    try:
        resp = SESSION.get(url, timeout=60)
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"    WARNING: could not list {url}: {e}")
        return []

    # Parse href links from HTML directory listing
    filenames = re.findall(r'href="(mvn_kp_insitu_[^"]+\.tab)"', resp.text)
    return sorted(set(filenames))


def _extract_column_names(lines: list[str]) -> list[str]:
    """Build column names from the description section of the header.

    Lines 100-337 (approx) have format:
      # Column description    Instrument    Unit    ColNum  Format    Note
    We extract the column number and description to build names like:
      'time', 'lpw_electron_density', 'lpw_electron_density_quality', ...

    Fallback: use generic col_1, col_2, ... col_235.
    """
    names = {}
    for line in lines:
        if not line.startswith("#"):
            continue
        stripped = line[1:].strip()
        # Look for description lines with column numbers (e.g. "  123  F16.8")
        # Format: "# Description    Instrument    Unit    ColNum  Format    Note"
        parts = stripped.split()
        if len(parts) < 3:
            continue
        # Find column number: look for a standalone integer in the range 1-235
        for i, p in enumerate(parts):
            try:
                col_num = int(p)
                if 1 <= col_num <= 235 and i >= 2:
                    # Build name from parts before the column number
                    desc_parts = parts[:i]
                    # Remove instrument/unit parts that come after the description
                    # Keep first meaningful words, snake_case them
                    name = "_".join(desc_parts).lower()
                    # Clean up common patterns
                    name = re.sub(r"[^a-z0-9_]", "_", name)
                    name = re.sub(r"_+", "_", name).strip("_")
                    if name:
                        names[col_num] = name
                    break
            except ValueError:
                continue

    if not names:
        return ["time"] + [f"col_{i}" for i in range(1, 235)]

    # Build ordered list: col 1 is time, then 2-235
    result = ["time"]
    for i in range(2, 236):
        result.append(names.get(i, f"col_{i}"))
    return result


def parse_tab_file(content: str) -> pd.DataFrame | None:
    """Parse a MAVEN KP .tab file (fixed-width text with # header lines).

    The header contains metadata including the line number where data begins.
    Data is whitespace-delimited with 235 columns.
    """
    lines = content.splitlines()

    # Extract data start line from header (line ~8: "#     348   Line on which data begins")
    data_start_line = None
    for line in lines[:20]:
        if "Line on which data begins" in line:
            match = re.search(r"#\s+(\d+)\s+Line on which", line)
            if match:
                data_start_line = int(match.group(1)) - 1  # 0-indexed
                break

    if data_start_line is None:
        # Fallback: find first non-# non-empty line
        for i, line in enumerate(lines):
            if not line.startswith("#") and line.strip():
                data_start_line = i
                break

    if data_start_line is None or data_start_line >= len(lines):
        return None

    # Use generic column names (numbered) — the multi-line header is too
    # complex to parse reliably. Column 1 is time, rest are instrument params.
    data_lines = [l for l in lines[data_start_line:] if l.strip()]
    if not data_lines:
        return None

    data_text = "\n".join(data_lines)
    try:
        df = pd.read_csv(
            io.StringIO(data_text),
            sep=r"\s+",
            header=None,
            na_values=["-9.99999990E+30", "-1.00000000E+31", "NO_DATA", "NaN"],
        )
    except Exception:
        return None

    if df.empty:
        return None

    # Assign column names: col 0 = time, rest = col_2 through col_235
    n_cols = len(df.columns)
    col_names = ["time"] + [f"col_{i+1}" for i in range(1, n_cols)]
    df.columns = col_names[:n_cols]

    return df


def download_and_parse(year: int, month: int, filename: str) -> pd.DataFrame | None:
    """Download a single .tab file and parse it."""
    url = f"{BASE_URL}{year:04d}/{month:02d}/{filename}"
    try:
        resp = SESSION.get(url, timeout=120)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"    WARNING: failed to download {filename}: {e}")
        return None

    return parse_tab_file(resp.text)


def clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename columns to snake_case and apply type coercion."""
    # Normalize column names: lowercase, replace spaces/special chars with underscore
    new_cols = {}
    for col in df.columns:
        clean = col.strip().lower()
        clean = re.sub(r"[^a-z0-9_]", "_", clean)
        clean = re.sub(r"_+", "_", clean).strip("_")
        new_cols[col] = clean
    df = df.rename(columns=new_cols)

    # Handle duplicate column names by appending suffix
    seen = {}
    final_cols = []
    for col in df.columns:
        if col in seen:
            seen[col] += 1
            final_cols.append(f"{col}_{seen[col]}")
        else:
            seen[col] = 0
            final_cols.append(col)
    df.columns = final_cols

    # Convert time column to datetime
    time_col = None
    for candidate in ["time", "time_utc", "timetag"]:
        if candidate in df.columns:
            time_col = candidate
            break

    if time_col:
        df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
        if time_col != "time":
            df = df.rename(columns={time_col: "time"})

    # Numeric coercion for all non-time, non-string columns
    for col in df.columns:
        if col == "time":
            continue
        if df[col].dtype == object:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def load_existing(tmp_dir: Path) -> pd.DataFrame | None:
    """Download existing parquet from HF. Returns DataFrame or None."""
    parquet_path = tmp_dir / "data" / "maven_kp_insitu.parquet"
    try:
        subprocess.run(
            ["hf", "download", HF_REPO, "data/maven_kp_insitu.parquet",
             "--repo-type", "dataset", "--local-dir", str(tmp_dir)],
            check=True, capture_output=True, timeout=120,
        )
        if parquet_path.exists():
            df = pd.read_parquet(parquet_path)
            if "time" in df.columns:
                df["time"] = pd.to_datetime(df["time"])
            print(f"  Loaded existing: {len(df):,} rows")
            return df
    except Exception as e:
        print(f"  Could not load existing ({e}), doing full rebuild")
    return None


def generate_months(start_year: int, start_month: int, end_year: int, end_month: int):
    """Generate (year, month) tuples in range."""
    y, m = start_year, start_month
    while (y, m) <= (end_year, end_month):
        yield y, m
        m += 1
        if m > 12:
            m = 1
            y += 1


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=None,
                        help="Fetch only this single year (e.g. --year 2020)")
    args = parser.parse_args()

    print("Fetching NASA MAVEN KP in-situ data...")

    yesterday = date.today() - timedelta(days=1)

    # Try incremental: load existing data
    with tempfile.TemporaryDirectory() as probe:
        df_existing = load_existing(Path(probe))

    if args.year:
        # Single-year mode: fetch one year, merge with existing
        fetch_start_year = args.year
        fetch_start_month = 1
        fetch_end_year = args.year
        fetch_end_month = 12
        print(f"  Single-year mode: fetching {args.year}")
    elif df_existing is not None and len(df_existing) > 0:
        # Incremental: fetch from the month of the last data point
        max_time = df_existing["time"].max()
        fetch_start_year = max_time.year
        fetch_start_month = max_time.month
        fetch_end_year = yesterday.year
        fetch_end_month = yesterday.month
        print(f"  Incremental from {fetch_start_year}-{fetch_start_month:02d}")
    else:
        # Full rebuild from START_YEAR
        df_existing = None
        fetch_start_year = START_YEAR
        fetch_start_month = START_MONTH
        fetch_end_year = yesterday.year
        fetch_end_month = yesterday.month
        print(f"  Full rebuild from {fetch_start_year}-{fetch_start_month:02d}")

    # Fetch new data month by month
    all_new = []
    total_files = 0

    for year, month in generate_months(fetch_start_year, fetch_start_month,
                                       fetch_end_year, fetch_end_month):
        print(f"  {year}-{month:02d}...", end="", flush=True)
        filenames = list_tab_files(year, month)
        if not filenames:
            print(" no files")
            time.sleep(1)
            continue

        print(f" {len(filenames)} files", end="", flush=True)
        month_rows = 0
        for fname in filenames:
            df_file = download_and_parse(year, month, fname)
            if df_file is not None and not df_file.empty:
                df_file = clean_columns(df_file)
                all_new.append(df_file)
                month_rows += len(df_file)
                total_files += 1
            time.sleep(0.5)

        print(f" -> {month_rows:,} rows")
        time.sleep(1)

    print(f"  Downloaded {total_files} files")

    if all_new:
        df_new = pd.concat(all_new, ignore_index=True)
        print(f"  New data: {len(df_new):,} rows")
    else:
        df_new = pd.DataFrame()
        print("  No new data downloaded")

    # Merge with existing
    if df_existing is not None and not df_new.empty:
        # Align columns: new data may have different columns than existing
        df = pd.concat([df_existing, df_new], ignore_index=True)
        if "time" in df.columns:
            df = df.drop_duplicates(subset=["time"], keep="last")
        print(f"  Merged: {len(df):,} rows")
    elif df_existing is not None:
        df = df_existing
        print(f"  No new data, using existing: {len(df):,} rows")
    elif not df_new.empty:
        df = df_new
        print(f"  First build: {len(df):,} rows")
    else:
        print("::error::No data available")
        sys.exit(1)

    # Sort by time
    if "time" in df.columns:
        df = df.sort_values("time").reset_index(drop=True)

    n_total = len(df)
    n_cols = len(df.columns)

    # Compute stats
    time_min = df["time"].min().strftime("%Y-%m-%d") if "time" in df.columns else "N/A"
    time_max = df["time"].max().strftime("%Y-%m-%d") if "time" in df.columns else "N/A"

    # Size category
    if n_total >= 100_000_000:
        size_cat = "100M<n<1B"
    elif n_total >= 10_000_000:
        size_cat = "10M<n<100M"
    elif n_total >= 1_000_000:
        size_cat = "1M<n<10M"
    else:
        size_cat = "100K<n<1M"

    # Drop all-null and >80% null columns (MAVEN has ~30 instrument columns
    # that are empty depending on orbit phase and instrument availability)
    before = len(df.columns)
    for col in list(df.columns):
        if col == "time":
            continue
        null_pct = df[col].isna().mean()
        if null_pct > 0.80 or null_pct == 1.0:
            df = df.drop(columns=[col])
    dropped = before - len(df.columns)
    if dropped:
        print(f"  Dropped {dropped} columns (>80% null or all-null)")

    # Validate
    expected_cols = ["time"]
    critical_cols = ["time"]
    check_dataset(df, "maven", min_rows=1_000_000,
                  expected_columns=expected_cols,
                  critical_columns=critical_cols,
                  incremental=True)

    # Write and upload
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "maven_kp_insitu.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  Parquet: {size_mb:.1f} MB, {n_total:,} rows, {n_cols} columns")

        banner_file = download_banner("maven", tmp)
        banner_md = banner_markdown("maven", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "NASA MAVEN Key Parameters (In-Situ)"
language:
  - en
description: "Time-series measurements from NASA's MAVEN Mars orbiter — solar wind, magnetic field, ion composition, neutral gas, and spacecraft ephemeris at 4-8 second cadence (2014-present)."
task_categories:
  - time-series-forecasting
tags:
  - space
  - mars
  - maven
  - atmosphere
  - solar-wind
  - magnetosphere
  - planetary-science
  - nasa
  - open-data
  - tabular-data
  - parquet
size_categories:
  - {size_cat}
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/maven_kp_insitu.parquet
    default: true
---

# NASA MAVEN Key Parameters (In-Situ)
{banner_md}
*Part of the [Solar System Datasets](https://huggingface.co/collections/juliensimon/solar-system-datasets-67dbfa3057e38241e7ea2aee) and [Planetary Science Datasets](https://huggingface.co/collections/juliensimon/planetary-science-datasets-69c24cb17e3db14fc30f0716) collections on Hugging Face.*

![Update MAVEN](https://github.com/juliensimon/space-datasets/actions/workflows/update-maven.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.maven&label=updated&color=brightgreen)

MAVEN (Mars Atmosphere and Volatile EvolutioN) is a NASA Mars orbiter that has been studying the Martian upper atmosphere and its interaction with the solar wind since September 2014. The mission investigates how Mars lost its early atmosphere and water to space — a process driven by solar wind stripping in the absence of a global magnetic field. MAVEN's key parameter (KP) dataset provides time-series measurements from multiple instruments at 4-8 second cadence: solar wind density, velocity, and temperature (SWIA/SWEA), magnetic field components (MAG), ion composition and energy spectra (STATIC), solar energetic particles (SEP), neutral gas composition (NGIMS), and electron density/temperature (LPW). Combined with spacecraft ephemeris (altitude, latitude, longitude, solar zenith angle), this dataset enables studies of atmospheric escape rates, ionospheric variability, and solar wind-magnetosphere coupling at Mars across a full solar cycle.

## Dataset description

Currently **{n_total:,}** rows spanning **{time_min}** to **{time_max}** with **{n_cols}** columns.

The MAVEN KP in-situ dataset captures simultaneous measurements from all onboard instruments at a unified time cadence. Each row represents a single time step with columns from:

- **LPW** (Langmuir Probe and Waves): electron density and temperature in the ionosphere
- **SWIA** (Solar Wind Ion Analyzer): solar wind proton density, velocity, and temperature
- **SWEA** (Solar Wind Electron Analyzer): electron energy spectra and pitch angle distributions
- **STATIC** (Suprathermal and Thermal Ion Composition): ion mass/charge composition and energy spectra
- **SEP** (Solar Energetic Particle): high-energy particle fluxes from solar events
- **NGIMS** (Neutral Gas and Ion Mass Spectrometer): neutral and ion densities in the upper atmosphere
- **MAG** (Magnetometer): magnetic field vector components
- **Spacecraft ephemeris**: altitude, latitude, longitude, solar zenith angle, orbit number

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/nasa-maven-kp-insitu", split="train")
df = ds.to_pandas()

# Filter by altitude for ionospheric studies (< 500 km)
# Column names vary — check df.columns for available fields
print(df.columns.tolist())
print(df.describe())
```

## Data source

[LASP SDC](https://lasp.colorado.edu/maven/sdc/public/data/sci/kp/insitu/) — NASA MAVEN Science Data Center at the Laboratory for Atmospheric and Space Physics, University of Colorado Boulder.

## Update schedule

Quarterly via [GitHub Actions](https://github.com/juliensimon/space-datasets). LASP publishes KP data with a ~6-8 month lag.

## Related datasets

- [esa-exomars-tgo-observations](https://huggingface.co/datasets/juliensimon/esa-exomars-tgo-observations) — ESA ExoMars TGO observation catalog
- [esa-mars-express-observations](https://huggingface.co/datasets/juliensimon/esa-mars-express-observations) — ESA Mars Express observation catalog
- [meda-weather](https://huggingface.co/datasets/juliensimon/meda-weather) — Mars surface weather from Perseverance rover
- [solar-wind](https://huggingface.co/datasets/juliensimon/solar-wind) — Real-time solar wind data from L1 monitors

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/nasa-maven-kp-insitu) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{maven_kp_insitu,
  author = {{Simon, Julien}},
  title = {{NASA MAVEN Key Parameters (In-Situ)}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/nasa-maven-kp-insitu}},
  note = {{Based on NASA MAVEN KP data from LASP SDC}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update MAVEN KP in-situ: {n_total:,} rows ({time_min} to {time_max})"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={n_total}\n")
    print("Done.")


if __name__ == "__main__":
    main()
