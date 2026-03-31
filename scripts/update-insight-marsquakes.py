#!/usr/bin/env python3
"""Fetch InSight Marsquake Catalog from IRIS and upload to HF."""

import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset


IRIS_URL = "http://service.iris.edu/irisws/mars-event/1/query"
HF_REPO = "juliensimon/insight-marsquake-catalog"

# Event type classification hierarchy (MQS quality tiers)
EVENT_TYPE_TIERS = {
    "LOW_FREQUENCY": "LF",
    "BROADBAND": "BB",
    "2.4_HZ": "2.4Hz",
    "HIGH_FREQUENCY": "HF",
    "VERY_HIGH_FREQUENCY": "VF",
    "SUPER_HIGH_FREQUENCY": "SF",
}


def main():
    print("Fetching InSight marsquake catalog from IRIS...")
    resp = requests.get(IRIS_URL, params={"format": "text"}, timeout=60)
    resp.raise_for_status()

    # Parse pipe-separated text
    df = pd.read_csv(io.StringIO(resp.text), sep="|", dtype=str)

    # Strip whitespace from column names and all string values
    df.columns = df.columns.str.strip()
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].str.strip()

    print(f"  {len(df):,} events fetched, {len(df.columns)} columns")

    # snake_case column names: lowercase, replace non-alphanumeric with underscores
    df.columns = (
        df.columns.str.lower()
        .str.replace(r"[^a-z0-9]+", "_", regex=True)
        .str.strip("_")
    )
    # Actual columns after conversion:
    # eventid, time, latitude, longitude, depth_km, author, catalog,
    # contributor, contributorid, magtype, magnitude, magauthor,
    # eventlocationname, eventtype

    # Rename for clarity
    df = df.rename(columns={
        "eventid": "event_id",
        "time": "event_time",
        "contributorid": "contributor_id",
        "magtype": "mag_type",
        "magauthor": "mag_author",
        "eventlocationname": "event_location_name",
        "eventtype": "event_type",
    })

    # Coerce numeric columns
    for col in ["latitude", "longitude", "depth_km", "magnitude"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Parse datetime column
    if "event_time" in df.columns:
        df["event_time"] = pd.to_datetime(df["event_time"], errors="coerce")

    # Derived column: short event type label
    if "event_type" in df.columns:
        df["event_type_short"] = df["event_type"].map(EVENT_TYPE_TIERS)

    # Sort by event time
    if "event_time" in df.columns:
        df = df.sort_values("event_time", ascending=True).reset_index(drop=True)

    print(f"  {len(df):,} marsquakes total")

    check_dataset(
        df, "insight-marsquake-catalog", min_rows=500,
        expected_columns=["event_id", "event_time", "latitude", "longitude",
                          "magnitude", "event_type"],
        critical_columns=["event_id", "event_time"],
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "insight_marsquakes.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        # Compute stats for README
        n_total = len(df)
        n_with_magnitude = int(df["magnitude"].notna().sum())
        n_with_location = int(
            (df["latitude"].notna() & df["longitude"].notna()).sum()
        )

        if "event_time" in df.columns:
            date_min = df["event_time"].min()
            date_max = df["event_time"].max()
            date_range = f"{date_min:%Y-%m-%d} to {date_max:%Y-%m-%d}"
        else:
            date_range = "N/A"

        if "event_type" in df.columns:
            n_types = df["event_type"].nunique()
            type_counts = df["event_type"].value_counts()
        else:
            n_types = 0
            type_counts = pd.Series(dtype=int)

        # Size category
        if n_total < 1000:
            size_cat = "n<1K"
        elif n_total < 10000:
            size_cat = "1K<n<10K"
        else:
            size_cat = "10K<n<100K"

        # Strongest event
        mag_valid = df[df["magnitude"].notna()]
        if len(mag_valid) > 0:
            strongest_idx = mag_valid["magnitude"].idxmax()
            strongest_id = df.loc[strongest_idx, "event_id"]
            strongest_mag = df.loc[strongest_idx, "magnitude"]
            strongest_line = f"Strongest event: **{strongest_id}** (magnitude {strongest_mag:.1f})"
        else:
            strongest_line = ""

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "InSight Marsquake Catalog"
language:
  - en
description: "Complete catalog of ~1,400 marsquakes detected by NASA InSight's SEIS seismometer on Mars (2019-2022). Final v14 release."
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - mars
  - insight
  - marsquake
  - seismology
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
        path: data/insight_marsquakes.parquet
    default: true
---

# InSight Marsquake Catalog

*Part of the [Space Probe and Mission Datasets](https://huggingface.co/collections/juliensimon/space-probe-and-mission-datasets-69c3fe82d410a42b1e313167) collection on Hugging Face.*

Complete catalog of marsquakes detected by NASA InSight's SEIS seismometer on Mars,
sourced from the IRIS Mars Event Service. Currently **{n_total:,}** seismic events.

## Dataset description

NASA's InSight lander operated on Mars from November 2018 to December 2022,
deploying the SEIS (Seismic Experiment for Interior Structure) seismometer —
the first seismometer successfully placed on another planet. Over the course
of the mission, SEIS detected over 1,300 marsquakes, revealing the internal
structure of Mars for the first time.

This dataset contains the complete MQS catalog, including event times,
locations (where determinable), magnitudes, and event type classifications
ranging from low-frequency broadband events to super-high-frequency signals.

Before InSight, the interior structure of Mars was almost entirely unconstrained by direct observation. The SEIS seismometer changed this by detecting marsquakes whose seismic waves traveled through the planet's interior, enabling the first direct measurements of the Martian crust, mantle, and core. Analysis of the marsquake catalog revealed that Mars has a relatively thick crust (24-72 km depending on model assumptions), a mantle with a lithosphere extending to roughly 500 km depth, and a liquid iron-alloy core with a radius of approximately 1,830 km — larger and less dense than previously expected, implying a significant fraction of light elements dissolved in the core.

The event type classifications in this catalog reflect distinct seismic source mechanisms on Mars. Low-frequency (LF) and broadband (BB) events are analogous to tectonic earthquakes, generated by stress release along faults, and tend to originate in the Cerberus Fossae region east of the lander — a zone of geologically recent volcanism and faulting. High-frequency (HF), very-high-frequency (VF), and super-high-frequency (SF) events are thought to originate in the shallow crust and may include thermal cracking of near-surface rocks. The 2.4 Hz resonance events have a characteristic spectral peak whose origin remains debated but may relate to site-specific geological structure beneath the lander.

The temporal distribution of marsquakes across the catalog shows strong seasonal modulation, with higher detection rates during the northern hemisphere winter when wind noise was lowest, as well as genuine variations in seismic activity. The largest event detected — a magnitude 4.7 marsquake on sol 1222 (May 4, 2022) — produced surface waves that circled the planet multiple times, providing the strongest constraints on crustal structure. This catalog is the foundational dataset for Martian seismology and will remain the primary reference until a future seismic network is deployed on Mars.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `event_id` | string | MQS event identifier (e.g. "mqs2022wrzi") |
| `event_time` | datetime | Origin time of the seismic event (UTC) |
| `latitude` | float64 | Event latitude on Mars (degrees, null if undetermined) |
| `longitude` | float64 | Event longitude on Mars (degrees, null if undetermined) |
| `depth_km` | float64 | Event depth in km (null if undetermined) |
| `author` | string | Author of the event origin |
| `catalog` | string | Source catalog identifier |
| `contributor` | string | Contributing agency |
| `contributor_id` | string | InSight sol-based event name (e.g. "S1415a") |
| `mag_type` | string | Magnitude type (MW, MbS, etc.) |
| `magnitude` | float64 | Event magnitude |
| `mag_author` | string | Author of the magnitude estimate |
| `event_location_name` | string | Named region on Mars (e.g. "Elysium Southwest") |
| `event_type` | string | MQS event type classification (BROADBAND, LOW_FREQUENCY, etc.) |
| `event_type_short` | string | Short event type label (BB, LF, HF, VF, SF, 2.4Hz) |

## Quick stats

- **{n_total:,}** seismic events
- **{n_with_magnitude:,}** with magnitude estimates
- **{n_with_location:,}** with location estimates
- **{n_types}** distinct event type classifications
- Date range: **{date_range}**
- {strongest_line}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/insight-marsquake-catalog", split="train")
df = ds.to_pandas()

# Events with known locations
located = df[df["latitude"].notna()]
print(f"{{len(located):,}} events with determined locations")

# Strongest marsquakes
strongest = df.nlargest(10, "magnitude")[["event_time", "magnitude", "event_type", "latitude", "longitude"]]

# Events by type
by_type = df["event_type"].value_counts()

# Events per year
df["year"] = df["event_time"].dt.year
by_year = df.groupby("year").size()
```

## Data source

[IRIS Mars Event Service](http://service.iris.edu/irisws/mars-event/1/) —
the official distribution point for the InSight Marsquake Service (MQS) catalog,
maintained by the InSight Mars SEIS Data Service at IRIS.

## Update schedule

Static dataset (InSight mission ended December 2022). No automatic updates.

## Related datasets

- [mars-craters-robbins](https://huggingface.co/datasets/juliensimon/mars-craters-robbins) — Mars crater database
- [mars-chemcam-compositions](https://huggingface.co/datasets/juliensimon/mars-chemcam-compositions) — Curiosity ChemCam rock compositions
- [mars-perseverance-weather](https://huggingface.co/datasets/juliensimon/mars-perseverance-weather) — Perseverance MEDA weather data
- [deep-space-probes](https://huggingface.co/datasets/juliensimon/deep-space-probes) — Active deep space probe catalog

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/insight-marsquake-catalog) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{insight_marsquake_catalog,
  author = {{Simon, Julien}},
  title = {{InSight Marsquake Catalog}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/insight-marsquake-catalog}},
  note = {{Based on NASA InSight SEIS marsquake catalog via IRIS Mars Event Service}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Upload InSight marsquake catalog: {n_total:,} events"
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
