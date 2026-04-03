#!/usr/bin/env python3
"""Fetch NASA EVA chronology and upload to HF."""

import io
import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

from dataset_images import banner_markdown, download_banner
from validate import check_dataset

HF_REPO = "juliensimon/nasa-eva-chronology"

NASA_CSV_URL = (
    "https://data.nasa.gov/docs/legacy/"
    "Extra-vehicular_Activity_EVA_-_US_and_Russia/"
    "Extra-vehicular_Activity_EVA_-_US_and_Russia_rows.csv"
)


def parse_duration_minutes(val: str) -> float | None:
    """Convert 'H:MM' duration string to total minutes."""
    if pd.isna(val) or not isinstance(val, str):
        return None
    val = val.strip()
    if not val or ":" not in val:
        return None
    try:
        parts = val.split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, IndexError):
        return None


def main():
    print("Fetching NASA EVA chronology...")
    resp = requests.get(NASA_CSV_URL, timeout=60)
    resp.raise_for_status()

    df = pd.read_csv(io.StringIO(resp.text))
    print(f"  {len(df):,} EVA records")

    # ── Rename columns to snake_case ─────────────────────────────────────
    df.columns = df.columns.str.strip()
    rename_map = {
        "EVA #": "eva_number",
        "Country": "country",
        "Crew": "crew",
        "Vehicle": "vehicle",
        "Date": "date",
        "Duration": "duration",
        "Purpose": "purpose",
    }
    df = df.rename(columns=rename_map)

    # ── Type coercion ────────────────────────────────────────────────────
    df["eva_number"] = pd.to_numeric(df["eva_number"], errors="coerce").astype("Int64")

    # Parse date
    df["date"] = pd.to_datetime(df["date"], format="%m/%d/%Y", errors="coerce")

    # Parse duration H:MM -> total minutes, keep original string too
    df["duration_minutes"] = df["duration"].apply(parse_duration_minutes)
    df["duration"] = df["duration"].astype(str).str.strip().replace(
        {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
    )

    # ── Clean string columns ─────────────────────────────────────────────
    for col in ["crew", "vehicle", "purpose", "country"]:
        if col in df.columns:
            df[col] = (
                df[col]
                .astype(str)
                .str.strip()
                .str.replace(r"\s+", " ", regex=True)
                .replace({"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA})
            )

    # ── Sort by date, then EVA number ────────────────────────────────────
    df = df.sort_values(["date", "eva_number"]).reset_index(drop=True)

    # ── Validate ─────────────────────────────────────────────────────────
    check_dataset(
        df,
        "eva",
        min_rows=200,
        expected_columns=["eva_number", "date", "crew", "vehicle", "duration", "country"],
        critical_columns=["crew", "country", "vehicle"],
    )

    # ── Stats for README ─────────────────────────────────────────────────
    n = len(df)
    n_usa = int((df["country"] == "USA").sum())
    n_russia = int((df["country"] == "Russia").sum())
    date_min = df["date"].min()
    date_max = df["date"].max()
    year_min = date_min.year if pd.notna(date_min) else "?"
    year_max = date_max.year if pd.notna(date_max) else "?"
    total_hours = df["duration_minutes"].sum() / 60
    vehicles = df["vehicle"].dropna().unique()
    n_vehicles = len(vehicles)
    top_vehicles = df["vehicle"].value_counts().head(5)
    top_vehicles_str = ", ".join(f"{v} ({c:,})" for v, c in top_vehicles.items())

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "eva.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_kb = out.stat().st_size / 1024
        print(f"  {size_kb:.0f} KB parquet")

        banner_file = download_banner("eva", tmp)
        banner_md = banner_markdown("eva", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "NASA EVA Chronology"
language:
  - en
description: >-
  Complete chronology of extravehicular activities (spacewalks) by NASA and
  Roscosmos.  {n:,} EVAs from {year_min} to {year_max}, including crew,
  vehicle, duration, and purpose.
size_categories:
  - n<1K
task_categories:
  - tabular-classification
tags:
  - space
  - eva
  - spacewalk
  - nasa
  - iss
  - human-spaceflight
  - open-data
  - tabular-data
  - parquet
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/eva.parquet
---

# NASA EVA Chronology
{banner_md}
*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

Complete chronology of all **{n:,}** extravehicular activities (spacewalks)
performed by NASA and Roscosmos astronauts and cosmonauts, from **{year_min}**
to **{year_max}** -- totalling **{total_hours:,.0f}** crew-hours outside the
spacecraft.

## Dataset description

This dataset contains the official NASA EVA chronology covering every
spacewalk by US and Russian crews.  Each record includes the EVA sequence
number, date, crew members, vehicle (Gemini, Apollo, Skylab, Shuttle, ISS,
etc.), duration in H:MM format plus a computed `duration_minutes` column, and
a free-text description of the purpose and activities.

Extravehicular activity -- spacewalking -- is among the most demanding and dangerous operations in human spaceflight. Every EVA requires hours of pre-breathing pure oxygen to avoid decompression sickness, careful choreography of tasks in microgravity, and constant monitoring of suit pressure, oxygen reserves, and CO2 levels. The first EVA was performed by Alexei Leonov in March 1965 during Voskhod 2, lasting just 12 minutes; today, ISS maintenance EVAs routinely exceed six hours and involve complex hardware installation, thermal blanket repairs, and robotic arm operations.

The chronological record of EVAs traces the evolution of spacesuit technology, from the rudimentary Berkut suit through NASA's Extravehicular Mobility Unit (EMU) to the Orlan series used on the Russian segment of the ISS. The data captures every phase of spacewalking history: the Gemini program's early experiments with working in vacuum, the Apollo lunar surface EVAs, Skylab exterior repairs, Shuttle-era satellite servicing missions (including the iconic Hubble Space Telescope repairs), and the ongoing ISS assembly and maintenance campaign that has consumed thousands of crew-hours.

This dataset supports research into EVA scheduling efficiency, crew workload analysis, the reliability of spacesuit systems, and risk assessment for future lunar and Mars surface operations. The purpose field provides a rich free-text description of activities performed during each EVA, enabling natural language analysis of how spacewalk tasks have shifted from exploration to construction to maintenance over six decades of human spaceflight.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `eva_number` | Int64 | Sequential EVA number |
| `country` | string | Country (USA / Russia) |
| `crew` | string | Crew member(s) |
| `vehicle` | string | Spacecraft or station (Gemini, Apollo, ISS, etc.) |
| `date` | datetime | Date of EVA |
| `duration` | string | Duration in H:MM format |
| `duration_minutes` | float64 | Duration in total minutes |
| `purpose` | string | Free-text description of EVA activities |

## Quick stats

- **{n:,}** EVAs ({n_usa:,} USA, {n_russia:,} Russia)
- **{year_min}** to **{year_max}**
- **{total_hours:,.0f}** total crew-hours
- **{n_vehicles}** vehicles: {top_vehicles_str}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/nasa-eva-chronology", split="train")
df = ds.to_pandas()

# EVAs per vehicle
print(df["vehicle"].value_counts())

# Total spacewalk hours by country
by_country = df.groupby("country")["duration_minutes"].sum() / 60
print(by_country)

# Longest EVAs
longest = df.nlargest(10, "duration_minutes")[["date", "crew", "vehicle", "duration"]]
print(longest)
```

## Data source

NASA Open Data Portal -- Extra-vehicular Activity (EVA) - US and Russia.
[data.nasa.gov](https://data.nasa.gov/dataset/extra-vehicular-activity-eva-us-and-russia)

## Related datasets

- [astronaut-database](https://huggingface.co/datasets/juliensimon/astronaut-database) -- Complete astronaut database
- [launch-log](https://huggingface.co/datasets/juliensimon/space-launch-log) -- McDowell launch log

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/nasa-eva-chronology) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{nasa_eva_chronology,
  author = {{Simon, Julien}},
  title = {{NASA EVA Chronology}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/nasa-eva-chronology}},
  note = {{Based on NASA Open Data Portal EVA dataset}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update NASA EVA chronology: {n:,} records"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={n}\n")
    print("Done.")


if __name__ == "__main__":
    main()
