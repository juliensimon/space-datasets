#!/usr/bin/env python3
"""Fetch solar radio burst events from NOAA SWPC and upload to HF.

NOAA SWPC edited_events.json covers ~30 days of events. This pipeline uses
incremental mode: download existing parquet from HF, fetch recent events,
merge and deduplicate.
"""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

from dataset_images import banner_markdown, download_banner
from validate import check_dataset


SWPC_URL = "https://services.swpc.noaa.gov/json/edited_events.json"
HF_REPO = "juliensimon/solar-radio-bursts"
RADIO_TYPES = {"RSP", "RBR", "RNS"}


def fetch_swpc_radio_events() -> pd.DataFrame:
    """Fetch solar radio burst events from NOAA SWPC."""
    print("  Fetching NOAA SWPC edited events...")
    resp = requests.get(SWPC_URL, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    print(f"  Total SWPC events: {len(data)}")

    # Filter to radio event types only
    radio = [e for e in data if e.get("type", "") in RADIO_TYPES]
    if not radio:
        print("  No radio events in response")
        return pd.DataFrame()

    df = pd.DataFrame(radio)
    print(f"  Radio events: {len(df)}")
    return df


def normalize_radio_df(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize SWPC radio events to a clean schema."""
    col_map = {
        "begin_datetime": "start_date",
        "end_datetime": "end_date",
        "max_datetime": "max_date",
    }
    df = df.rename(columns=col_map)

    # Parse datetimes
    for col in ["start_date", "end_date", "max_date"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    # Map SWPC type codes to descriptive names
    type_map = {"RSP": "spectral_sweep", "RBR": "fixed_freq_burst", "RNS": "noise_storm"}
    df["type"] = df["type"].map(type_map).fillna(df["type"])

    # For RSP events, particulars1 has the Roman numeral burst classification (e.g., "III/2")
    if "particulars1" in df.columns:
        df["burst_class"] = df["particulars1"].where(
            df["type"] == "spectral_sweep", other=pd.NA
        )

    # Keep useful columns, drop SWPC-internal fields
    keep = [
        "start_date", "end_date", "max_date", "type", "frequency",
        "observatory", "quality", "burst_class", "region",
        "particulars1", "particulars2", "particulars3",
    ]
    keep = [c for c in keep if c in df.columns]
    df = df[keep]

    # Clean strings
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].astype(str).str.strip().replace(
            {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA, "none": pd.NA}
        )

    return df


def load_existing(tmp_dir: Path) -> pd.DataFrame | None:
    """Download existing parquet from HF. Returns DataFrame or None."""
    parquet_path = tmp_dir / "data" / "solar_radio_bursts.parquet"
    try:
        subprocess.run(
            ["hf", "download", HF_REPO, "data/solar_radio_bursts.parquet",
             "--repo-type", "dataset", "--local-dir", str(tmp_dir)],
            check=True, capture_output=True, timeout=30,
        )
        if parquet_path.exists():
            df = pd.read_parquet(parquet_path)
            df["start_date"] = pd.to_datetime(df["start_date"])
            print(f"  Loaded existing: {len(df):,} events")
            return df
    except Exception as e:
        print(f"  Could not load existing ({e}), starting fresh")
    return None


def main():
    print("Fetching solar radio burst events...")

    df_new = fetch_swpc_radio_events()
    if df_new.empty:
        print("::error::No radio events retrieved from SWPC")
        raise SystemExit(1)
    df_new = normalize_radio_df(df_new)

    # Try incremental merge
    with tempfile.TemporaryDirectory() as probe:
        df_existing = load_existing(Path(probe))

    if df_existing is not None and len(df_existing) > 0:
        # Merge: concat and deduplicate on (start_date, frequency, observatory)
        dedup_cols = ["start_date", "frequency", "observatory"]
        dedup_cols = [c for c in dedup_cols if c in df_new.columns and c in df_existing.columns]

        # Align columns — existing data may have extra or missing columns
        for col in df_new.columns:
            if col not in df_existing.columns:
                df_existing[col] = pd.NA
        for col in df_existing.columns:
            if col not in df_new.columns:
                df_new[col] = pd.NA

        df = pd.concat([df_existing, df_new], ignore_index=True)
        if dedup_cols:
            df = df.drop_duplicates(subset=dedup_cols, keep="last")
        print(f"  Merged: {len(df):,} events (kept {len(df_existing):,} + {len(df_new):,} new, deduped)")
    else:
        df = df_new

    df = df.sort_values("start_date").reset_index(drop=True)
    print(f"  {len(df):,} solar radio burst events")

    check_dataset(df, "solar-radio", min_rows=10,
                  expected_columns=["start_date", "type", "frequency"],
                  critical_columns=["start_date"])

    # Stats for README
    n_total = len(df)
    date_min = df["start_date"].min().strftime("%Y-%m-%d")
    date_max = df["start_date"].max().strftime("%Y-%m-%d")
    n_types = int(df["type"].nunique()) if "type" in df.columns else 0
    top_types = df["type"].value_counts().head(5) if "type" in df.columns else pd.Series()
    top_types_str = ", ".join(f"{t} ({c:,})" for t, c in top_types.items())

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "solar_radio_bursts.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        banner_file = download_banner("solar-radio", tmp)
        banner_md = banner_markdown("solar-radio", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Solar Radio Burst Events"
language:
  - en
description: "Catalog of solar radio burst events (spectral sweeps, fixed-frequency bursts, noise storms) from NOAA SWPC. Updated daily with incremental merge."
task_categories:
  - tabular-classification
tags:
  - space
  - solar
  - radio-burst
  - type-ii
  - type-iii
  - space-weather
  - noaa
  - swpc
  - open-data
  - tabular-data
  - parquet
size_categories:
  - 1K<n<100K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/solar_radio_bursts.parquet
    default: true
---

# Solar Radio Burst Events
{banner_md}
*Part of the [Space Weather Datasets](https://huggingface.co/collections/juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70) collection on Hugging Face.*

![Update Solar Radio](https://github.com/juliensimon/space-datasets/actions/workflows/update-solar-radio.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.solar-radio&label=updated&color=brightgreen)

Catalog of solar radio burst events, currently **{n_total:,}** events spanning **{date_min}** to **{date_max}**. Solar radio bursts are intense bursts of radio emission from the Sun, classified by their spectral characteristics and physical origin.

## Dataset description

Solar radio bursts are produced by energetic electrons accelerated during solar flares and coronal mass ejections. They are important indicators of space weather activity:

- **Spectral sweeps (RSP)** — frequency-drifting bursts including Type II (CME shocks), III (electron beams), IV (post-flare continuum), V (short continuum)
- **Fixed-frequency bursts (RBR)** — discrete bursts at a single frequency
- **Noise storms (RNS)** — sustained broadband emission from active regions

The physics behind these emissions is coherent plasma radiation. When energetic electrons stream through the solar corona, they excite Langmuir waves at the local plasma frequency, which then convert into electromagnetic radiation at the fundamental and second harmonic. Because the plasma frequency depends on electron density — which decreases with altitude in the corona — Type III bursts exhibit a characteristic fast frequency drift as the electron beam propagates outward along open magnetic field lines.

Solar radio bursts are among the earliest detectable signatures of eruptive solar activity, often preceding the arrival of energetic particles and geomagnetic disturbances at Earth by minutes to days. Monitoring them is therefore critical for operational space weather forecasting.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `start_date` | datetime | UTC time when the radio burst began |
| `end_date` | datetime | UTC time when the radio burst ended; null if event was still in progress at report time |
| `max_date` | datetime | UTC time of maximum radio flux intensity; null for noise storms where peak is ill-defined |
| `type` | string | SWPC event type mapped to descriptive label: "spectral_sweep" (RSP — frequency-drifting burst including Type II/III/IV/V), "fixed_freq_burst" (RBR — discrete burst at a single frequency), "noise_storm" (RNS — sustained broadband emission from active regions) |
| `frequency` | string | Observing frequency or frequency range in MHz (e.g., "245" or "025-180"); Type III bursts can drift from >100 MHz to <10 MHz in seconds as electron beams propagate outward |
| `observatory` | string | SWPC station code reporting the event (e.g., "SGD", "LEA", "BOU"); multiple observatories may report the same event independently |
| `quality` | string | SWPC data quality flag indicating analyst confidence in the event classification (e.g., "Good", "Poor"); null if not assigned |
| `burst_class` | string | Roman numeral subtype for spectral sweep events (e.g., "III/2", "II", "IV"); Roman numeral indicates burst type (I=noise storm enhancement, II=slow-drift shock, III=fast electron beam, IV=continuum, V=post-III continuum); null for fixed-frequency bursts and noise storms |
| `region` | string | NOAA active region number causally associated with the burst; null if no active region link was established |

## Quick stats

- **{n_total:,}** radio burst events ({date_min} to {date_max})
- **{n_types}** event type classifications
- Top types: {top_types_str}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/solar-radio-bursts", split="train")
df = ds.to_pandas()

# Spectral sweep events (includes Type II, III, IV, V)
sweeps = df[df["type"] == "spectral_sweep"]
print(f"{{len(sweeps):,}} spectral sweep events")

# Type III bursts specifically
type_iii = sweeps[sweeps["burst_class"].str.contains("III", na=False)]

# Event type distribution
print(df["type"].value_counts())
```

## Data source

[NOAA Space Weather Prediction Center (SWPC)](https://www.swpc.noaa.gov/) edited events feed. The SWPC endpoint provides a rolling ~30-day window; this dataset accumulates historical events via daily incremental updates.

## Update schedule

Daily at 19:00 UTC via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [solar-flare-index](https://huggingface.co/datasets/juliensimon/solar-flare-events) — Solar flare observations
- [donki-space-weather-events](https://huggingface.co/datasets/juliensimon/donki-space-weather-events) — NASA DONKI space weather events
- [space-weather-indices](https://huggingface.co/datasets/juliensimon/space-weather-indices) — Daily Kp, Ap, F10.7 indices

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/solar-radio-bursts) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{solar_radio_bursts,
  author = {{Simon, Julien}},
  title = {{Solar Radio Burst Events}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/solar-radio-bursts}},
  note = {{Based on NOAA SWPC edited events data}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update solar radio bursts: {n_total:,} events"
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
