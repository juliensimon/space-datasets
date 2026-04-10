#!/usr/bin/env python3
"""Fetch substorm onset event lists from SuperMAG and upload to HF."""

import io
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pandas as pd
import requests

from dataset_images import banner_markdown, download_banner
from validate import check_dataset

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
        # Values > 24 are clearly in degrees — convert to hours
        mask_degrees = mlt > 24
        if mask_degrees.any():
            mlt.loc[mask_degrees] = mlt.loc[mask_degrees] / 15.0
            print(f"  Converted {mask_degrees.sum():,} MLT values from degrees to hours (liou list)")
        df["mlt_hours"] = mlt

    # Type coercions
    for col in ["magnetic_latitude_deg", "geographic_longitude_deg", "geographic_latitude_deg"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Sort by datetime
    df = df.sort_values("datetime_utc").reset_index(drop=True)

    # Drop rows with no datetime (invalid)
    n_before = len(df)
    df = df.dropna(subset=["datetime_utc"]).reset_index(drop=True)
    if n_before - len(df) > 0:
        print(f"  Dropped {n_before - len(df)} rows with invalid datetime")

    # Stats
    n_total = len(df)
    source_counts = df["source"].value_counts().to_dict()
    year_min = df["datetime_utc"].dt.year.min()
    year_max = df["datetime_utc"].dt.year.max()
    n_ground = int(df["source"].isin(["newell", "forsyth", "ohtani"]).sum())
    n_imaging = int(df["source"].isin(["frey", "liou"]).sum())

    # Size category
    if n_total >= 100_000:
        size_cat = "100K<n<1M"
    elif n_total >= 10_000:
        size_cat = "10K<n<100K"
    else:
        size_cat = "1K<n<10K"

    # Validate
    check_dataset(
        df,
        "substorm-onsets",
        min_rows=50_000,
        expected_columns=["datetime_utc", "mlt_hours", "magnetic_latitude_deg", "source"],
        critical_columns=["datetime_utc", "source"],
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "substorm_onsets.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        banner_file = download_banner("substorm-onsets", tmp)
        banner_md = banner_markdown("substorm-onsets", banner_file)

        source_lines = "\n".join(
            f"| `{name}` | {count:,} | {LISTS[name]['method']} |"
            for name, count in sorted(source_counts.items(), key=lambda x: -x[1])
        )

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Substorm Onset Events (SuperMAG)"
language:
  - en
description: "Magnetospheric substorm onset events from 5 detection algorithms via SuperMAG ({n_total:,} events, {year_min}-{year_max})."
task_categories:
  - tabular-classification
  - time-series-forecasting
tags:
  - space
  - space-weather
  - substorm
  - magnetosphere
  - aurora
  - geomagnetic
  - supermag
  - open-data
  - tabular-data
  - parquet
size_categories:
  - {size_cat}
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/substorm_onsets.parquet
    default: true
---

# Substorm Onset Events (SuperMAG)
{banner_md}
*Part of the [Space Weather Datasets](https://huggingface.co/collections/juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70) collection on Hugging Face.*

A consolidated catalog of **{n_total:,}** magnetospheric substorm onset events spanning **{year_min}--{year_max}**, combining five independent detection algorithms from the [SuperMAG](https://supermag.jhuapl.edu/) collaboration. This is the most comprehensive substorm event list available, enabling multi-algorithm comparison and consensus studies.

## Dataset description

Magnetospheric substorms are fundamental space weather events driven by the solar wind's interaction with Earth's magnetic field. During a substorm, magnetic energy stored in the magnetotail is explosively released, accelerating charged particles that stream along field lines into the polar regions. This produces sudden auroral brightenings — the dramatic intensification of the Northern and Southern Lights — along with rapid changes in ground-level magnetic fields detected by magnetometer networks worldwide.

This dataset merges five complementary onset detection methods:

| Source | Events | Detection method |
|--------|-------:|-----------------|
{source_lines}

**Ground-based methods** ({n_ground:,} events) detect substorms through characteristic negative bays in the SML (SuperMAG Lower) index — a measure of the westward auroral electrojet current. **Space-based methods** ({n_imaging:,} events) directly observe the initial auroral brightening using ultraviolet imagers aboard the IMAGE and Polar satellites.

Each algorithm has different sensitivity and false-positive rates, so researchers often require onset confirmation across multiple lists. The `source` column enables filtering by algorithm or finding consensus events where multiple methods agree within a time window.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `datetime_utc` | datetime | UTC timestamp of the substorm onset — the start of the expansion phase when energy stored in the magnetotail is explosively released. Accurate to ±1–2 minutes for ground-based detections; ±1 minute for auroral imager detections. |
| `mlt_hours` | float64 | Magnetic Local Time (MLT) of the onset location (0–24 h, where 0/24 = magnetic midnight, 12 = magnetic noon). MLT is fixed relative to the Sun-Earth axis and rotates with Earth's magnetic field. Midnight-sector onsets (22–02 MLT) are most common. |
| `magnetic_latitude_deg` | float64 | Magnetic latitude (MLAT) of the onset location in degrees. Substorm onsets typically occur at 60–75° MLAT within the auroral oval. Values outside this range may indicate unusual geomagnetic conditions or catalog artifacts. |
| `geographic_longitude_deg` | float64 | Geographic (geodetic) longitude of the onset location in degrees (-180 to 180). Suitable for plotting on standard world maps; differs from magnetic longitude. |
| `geographic_latitude_deg` | float64 | Geographic (geodetic) latitude of the onset location in degrees. Use with `geographic_longitude_deg` for ground-track mapping. Differs from `magnetic_latitude_deg` due to offset between geographic and magnetic poles. |
| `source` | string | Detection algorithm that identified this onset: `newell` (SML index threshold), `forsyth` (SME index derivative), `ohtani` (negative bay in SML), `frey` (IMAGE satellite UV imager), `liou` (Polar satellite UV imager). Each algorithm has different sensitivity and false-positive characteristics. |
| `method` | string | Human-readable detection method category: "Ground magnetometer" (SML/SME index-based methods) or "Auroral imager" (UV camera aboard IMAGE or Polar satellites). Use this column to filter by methodology or compare ground vs. space-based detections. |

## Quick stats

- **{n_total:,}** total substorm onset events
- **{year_min}--{year_max}** temporal coverage
- **5** independent detection algorithms
- **{n_ground:,}** ground magnetometer detections, **{n_imaging:,}** auroral imaging detections

## Usage

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
```

## Data source

SuperMAG substorm onset lists, provided by the Johns Hopkins University Applied Physics Laboratory:
- Newell & Gjerloev (2011), [doi:10.1029/2010JA016141](https://doi.org/10.1029/2010JA016141)
- Forsyth et al. (2015), [doi:10.1002/2015JA021343](https://doi.org/10.1002/2015JA021343)
- Ohtani & Gjerloev (2020), [doi:10.1029/2019JA027680](https://doi.org/10.1029/2019JA027680)
- Frey et al. (2004), [doi:10.1029/2003JA010300](https://doi.org/10.1029/2003JA010300)
- Liou (2010), [doi:10.1016/j.jastp.2009.08.005](https://doi.org/10.1016/j.jastp.2009.08.005)

## Related datasets

- [Dst Index](https://huggingface.co/datasets/juliensimon/dst-index) — Hourly geomagnetic storm index
- [Kp Index](https://huggingface.co/datasets/juliensimon/kp-index) — 3-hourly geomagnetic activity
- [AE Index](https://huggingface.co/datasets/juliensimon/ae-index) — Auroral electrojet indices
- [DONKI Space Weather](https://huggingface.co/datasets/juliensimon/donki) — CMEs, flares, and geomagnetic storms

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/{HF_REPO}) and share feedback in the Community tab! Also consider giving a ⭐ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{substorm_onsets,
  author = {{Simon, Julien}},
  title = {{Substorm Onset Events (SuperMAG)}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/{HF_REPO}}},
  note = {{Consolidated from SuperMAG: Newell, Forsyth, Ohtani, Frey, Liou lists}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update substorm onsets: {n_total:,} events from 5 algorithms"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={len(df)}\n")
    print("Done.")


if __name__ == "__main__":
    main()
