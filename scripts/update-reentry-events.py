#!/usr/bin/env python3
"""Derive reentry events from CelesTrak SATCAT and upload to HF."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

from validate import check_dataset

SATCAT_URL = "https://celestrak.org/pub/satcat.csv"
HF_REPO = "juliensimon/reentry-events"


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

    check_dataset(df, "reentry-events", min_rows=20_000,
        expected_columns=["norad_id", "object_name", "object_type",
                          "launch_date", "decay_date", "decay_year",
                          "days_in_orbit"],
        critical_columns=["norad_id", "object_name", "decay_date"])

    # Compute stats for README
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

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "reentry-events.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Reentry Events"
language:
  - en
description: "Catalog of {n_total:,} objects that have reentered Earth's atmosphere, derived from the NORAD SATCAT via CelesTrak. Includes launch and decay dates, orbital parameters, and time in orbit. Updated daily."
task_categories:
  - tabular-classification
tags:
  - space
  - reentry
  - orbital-mechanics
  - satellites
  - debris
  - open-data
  - tabular-data
size_categories:
  - 10K<n<100K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/reentry-events.parquet
    default: true
---

# Reentry Events

*Part of the [Orbital Mechanics Datasets](https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994) collection on Hugging Face.*

![Update Reentry Events](https://github.com/juliensimon/space-datasets/actions/workflows/update-reentry-events.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.reentry-events&label=updated&color=brightgreen)

Catalog of **{n_total:,}** objects that have reentered Earth's atmosphere, derived from the
NORAD Satellite Catalog (SATCAT) via [CelesTrak](https://celestrak.org/). An object is
considered reentered when its DECAY_DATE is recorded in the SATCAT. Covers reentries
from {year_min} to {year_max}.

## Dataset description

Every object launched into Earth orbit eventually returns -- whether through natural orbital
decay, controlled deorbits, or breakup. This dataset catalogs every object in the NORAD
SATCAT that has a recorded decay date, providing a comprehensive history of atmospheric
reentries. It includes payloads, rocket bodies, and debris, with derived fields like
time spent in orbit and decay year for trend analysis.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `norad_id` | int32 | NORAD catalog number (unique identifier) |
| `object_name` | string | Official name (e.g. "COSMOS 1234 DEB") |
| `object_type` | string | `PAY` (payload), `R/B` (rocket body), `DEB` (debris), `UNK` (unknown) |
| `country_code` | string | Owner/operator country or organization code |
| `launch_date` | datetime | Launch date (UTC) |
| `decay_date` | datetime | Date of atmospheric reentry (UTC) |
| `period_min` | float | Last recorded orbital period in minutes |
| `inclination_deg` | float | Last recorded orbital inclination in degrees |
| `apogee_km` | float | Last recorded apogee altitude in km |
| `perigee_km` | float | Last recorded perigee altitude in km |
| `rcs_size` | string | Radar cross-section size category (SMALL, MEDIUM, LARGE) |
| `days_in_orbit` | int | Days between launch and decay |
| `decay_year` | int32 | Year of reentry (for grouping/filtering) |

## Quick stats

- **{n_total:,}** reentered objects
- **{n_payload:,}** payloads, **{n_debris:,}** debris fragments, **{n_rocket:,}** rocket bodies
- Median time in orbit: **{median_days:,}** days
- Reentries span **{year_min}** to **{year_max}**
- Top countries: {top_countries_str}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/reentry-events", split="train")
df = ds.to_pandas()

# Reentries per year
reentries_by_year = df.groupby("decay_year")["norad_id"].count()
reentries_by_year.tail(10)

# Longest-lived objects
longest = df.nlargest(10, "days_in_orbit")[["object_name", "days_in_orbit", "launch_date", "decay_date"]]

# Reentries by object type
df["object_type"].value_counts()

# Recent reentries (last 30 days)
import pandas as pd
recent = df[df["decay_date"] > pd.Timestamp.now() - pd.Timedelta(days=30)]
```

## Data source

Derived from the [CelesTrak SATCAT](https://celestrak.org/pub/satcat.csv), which mirrors
the official US Space Command catalog maintained by the 18th Space Defense Squadron.
Objects with a recorded DECAY_DATE are extracted as reentry events.

## Update schedule

Daily at 07:15 UTC via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [space-track-satcat](https://huggingface.co/datasets/juliensimon/space-track-satcat) -- Full NORAD satellite catalog
- [space-launch-log](https://huggingface.co/datasets/juliensimon/space-launch-log) -- Global launch history from GCAT
- [tle-history](https://huggingface.co/datasets/juliensimon/tle-history) -- Historical two-line element sets

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Citation

```bibtex
@dataset{{reentry_events,
  author = {{Simon, Julien}},
  title = {{Reentry Events}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/reentry-events}},
  note = {{Derived from NORAD SATCAT via CelesTrak (Dr. T.S. Kelso)}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update reentry events: {n_total:,} objects"
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
