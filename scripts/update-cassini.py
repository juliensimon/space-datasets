#!/usr/bin/env python3
"""Fetch Cassini Saturn observation master schedule and upload to HF."""

import io
import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset


CSV_URL = "https://pds-atmospheres.nmsu.edu/data_and_services/atmospheres_data/Cassini_PDS3/logs/master%20as%20planned%209-15-18.csv"
HF_REPO = "juliensimon/cassini-saturn-observations"

COLUMN_RENAME = {
    "Start time (UTC)": "start_time_utc",
    "Duration": "duration",
    "Date": "date",
    "Team": "team",
    "SPASS Type": "spass_type",
    "Target": "target",
    "Request Name": "request_name",
    "Library Definition": "library_definition",
    "Title": "title",
    "Description": "description",
}

EXPECTED_COLUMNS = list(COLUMN_RENAME.values())


def main():
    print("Fetching Cassini observation master schedule...")
    resp = requests.get(CSV_URL, timeout=120)
    resp.raise_for_status()

    # Skip first 2 rows (title + blank), use row 3 as headers
    df = pd.read_csv(io.StringIO(resp.text), skiprows=2, low_memory=False)
    print(f"  {len(df):,} raw rows")

    # Clean up trailing commas — drop fully unnamed columns
    df = df.loc[:, ~df.columns.str.startswith("Unnamed")]

    # Strip whitespace from column names (e.g., "Date " → "Date")
    df.columns = df.columns.str.strip()

    # Drop rows that are all-NaN
    df = df.dropna(how="all").reset_index(drop=True)

    # Rename columns to snake_case
    df = df.rename(columns=COLUMN_RENAME)

    # Parse start_time_utc — format is YYYY-DDDTHH:MM:SS (day-of-year)
    df["start_time_utc"] = pd.to_datetime(
        df["start_time_utc"], format="%Y-%jT%H:%M:%S", errors="coerce"
    )

    # Sort by start_time_utc
    df = df.sort_values("start_time_utc").reset_index(drop=True)

    print(f"  {len(df):,} rows after cleanup")

    check_dataset(
        df,
        "cassini",
        min_rows=50_000,
        expected_columns=EXPECTED_COLUMNS,
        critical_columns=["start_time_utc", "target", "team"],
    )

    n = len(df)
    n_targets = df["target"].nunique()
    n_teams = df["team"].nunique()
    valid_times = df["start_time_utc"].dropna()
    year_min = int(valid_times.dt.year.min()) if len(valid_times) > 0 else 2004
    year_max = int(valid_times.dt.year.max()) if len(valid_times) > 0 else 2017
    top_target = df["target"].value_counts().index[0]

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        data_dir = tmp_dir / "data"
        data_dir.mkdir()

        out = data_dir / "cassini_observations.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp_dir / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Cassini Saturn Observations"
language:
  - en
description: >-
  Complete Cassini mission observation master schedule — {n:,} planned observations
  of Saturn, its rings, and moons ({year_min}--{year_max}). From NASA PDS Atmospheres Node.
size_categories:
  - 10K<n<100K
task_categories:
  - tabular-classification
tags:
  - open-data
  - space
  - saturn
  - cassini
  - nasa
  - planetary-science
  - pds
  - tabular-data
  - parquet
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/cassini_observations.parquet
    default: true
---

# Cassini Saturn Observations

*Part of the [Planetary Science Datasets](https://huggingface.co/collections/juliensimon/planetary-science-datasets-69c24cb6dfc9bf82d6b2edf1) collection on Hugging Face.*

The complete **Cassini mission** observation master schedule — **{n:,}** planned science
observations spanning **{year_min}** to **{year_max}**. Cassini orbited Saturn for 13 years,
studying the planet, its rings, and its moons before its planned destruction in
Saturn's atmosphere on September 15, 2017.

## Dataset description

The Cassini-Huygens mission was one of the most ambitious planetary exploration endeavors ever undertaken. A joint NASA/ESA/ASI project, Cassini spent 13 years in orbit around Saturn, completing 294 orbits and 127 close flybys of Titan, along with numerous encounters with Enceladus, Rhea, Dione, and other Saturnian moons. The spacecraft carried 12 science instruments spanning imaging, spectroscopy, radar, magnetometry, and particle detection, operated by dedicated science teams (identified as CIRS, ISS, UVIS, VIMS, CAPS, MAG, RADAR, RPWS, and others in this observation schedule).

Among Cassini's landmark discoveries were the active water-ice geysers erupting from Enceladus's south polar tiger stripe fractures — revealing a subsurface ocean with hydrothermal activity and the potential for habitability — and the detailed characterization of Titan's methane hydrological cycle through RADAR mapping of surface lakes and seas. Cassini also observed the hexagonal jet stream at Saturn's north pole, tracked the evolution of a massive northern hemisphere storm in 2010-2011, measured Saturn's internal rotation period through ring seismology, and discovered seven new moons. The mission's Grand Finale in 2017 sent the spacecraft between Saturn's innermost ring and the planet's atmosphere, providing the closest-ever measurements of Saturn's gravity field and magnetic field.

This observation master schedule documents every planned science activity across the entire mission, making it possible to reconstruct which targets were observed, by which instrument teams, and when. The schedule is essential for cross-referencing with archival data products in the NASA PDS, enabling researchers to identify and retrieve specific observations of interest for Saturn system science.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `start_time_utc` | datetime | Observation start time (UTC) |
| `duration` | string | Planned duration of observation |
| `date` | string | Date string from the original schedule |
| `team` | string | Science team responsible (e.g. CIRS, ISS, UVIS, VIMS) |
| `spass_type` | string | SPASS observation type |
| `target` | string | Observation target (e.g. SATURN, TITAN, ENCELADUS, RINGS) |
| `request_name` | string | Internal request identifier |
| `library_definition` | string | Library definition reference |
| `title` | string | Observation title |
| `description` | string | Detailed description of the observation |

## Quick stats

- **{n:,}** planned observations ({year_min}--{year_max})
- **{n_targets}** distinct targets (most observed: {top_target})
- **{n_teams}** science teams

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/cassini-saturn-observations", split="train")
df = ds.to_pandas()

# Observations by target
df["target"].value_counts().head(10)

# Titan flybys
titan = df[df["target"] == "TITAN"].sort_values("start_time_utc")

# Observations by science team
df["team"].value_counts()

# Timeline of observations per year
df["year"] = df["start_time_utc"].dt.year
df.groupby("year").size().plot(kind="bar")
```

## Data source

[NASA PDS Atmospheres Node — Cassini Master Schedule](https://pds-atmospheres.nmsu.edu/data_and_services/atmospheres_data/Cassini_PDS3/logs/).
The Cassini mission ended September 15, 2017; this is a static/archival dataset.

## Update frequency

Static dataset (Cassini mission ended 2017). No scheduled updates.

## Related datasets

- [mars-craters](https://huggingface.co/datasets/juliensimon/mars-craters) — Martian impact craters
- [lunar-craters](https://huggingface.co/datasets/juliensimon/lunar-craters) — Lunar impact craters
- [exoplanet-archive](https://huggingface.co/datasets/juliensimon/exoplanet-archive) — Confirmed exoplanets

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/cassini-saturn-observations) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{cassini_observations,
  author = {{Simon, Julien}},
  title = {{Cassini Saturn Observations}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/cassini-saturn-observations}},
  note = {{Based on Cassini mission master schedule from NASA PDS Atmospheres Node}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp_dir), ".",
             "--repo-type", "dataset",
             "--commit-message", f"Upload Cassini observations: {n:,} records"],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={n}\n")
    print("Done.")


if __name__ == "__main__":
    main()
