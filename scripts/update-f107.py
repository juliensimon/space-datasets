#!/usr/bin/env python3
"""Fetch F10.7 Solar Radio Flux data from LASP LISIRD and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset


LISIRD_URL = "https://lasp.colorado.edu/lisird/latis/dap/penticton_radio_flux.csv"
HF_REPO = "juliensimon/f107-solar-flux"


def main():
    print("Fetching F10.7 Solar Radio Flux from LASP LISIRD...")
    resp = requests.get(LISIRD_URL, timeout=120)
    resp.raise_for_status()

    df = pd.read_csv(pd.io.common.StringIO(resp.text))
    print(f"  {len(df):,} rows, columns: {list(df.columns)}")

    # Parse time as datetime
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], errors="coerce")

    # Rename columns
    rename_map = {}
    if "time" in df.columns:
        rename_map["time"] = "date"
    if "observed_flux" in df.columns:
        rename_map["observed_flux"] = "observed_flux_sfu"
    if "adjusted_flux" in df.columns:
        rename_map["adjusted_flux"] = "adjusted_flux_sfu"
    if "absolute_flux" in df.columns:
        rename_map["absolute_flux"] = "absolute_flux_sfu"

    df = df.rename(columns=rename_map)

    # Convert numeric columns
    for col in ["observed_flux_sfu", "adjusted_flux_sfu", "absolute_flux_sfu"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "date" in df.columns:
        df = df.sort_values("date").reset_index(drop=True)

    check_dataset(df, "f107", min_rows=20000,
                  expected_columns=["date", "observed_flux_sfu"],
                  critical_columns=["date", "observed_flux_sfu"])

    # Stats for README
    n = len(df)
    date_min = df["date"].min().strftime("%Y-%m-%d") if "date" in df.columns else "N/A"
    date_max = df["date"].max().strftime("%Y-%m-%d") if "date" in df.columns else "N/A"
    mean_flux = df["observed_flux_sfu"].mean() if "observed_flux_sfu" in df.columns else 0
    max_flux = df["observed_flux_sfu"].max() if "observed_flux_sfu" in df.columns else 0

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "f107_solar_flux.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_kb = out.stat().st_size / 1024
        print(f"  {size_kb:.0f} KB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "F10.7 Solar Radio Flux (Penticton)"
language:
  - en
description: >-
  Daily F10.7 cm solar radio flux measurements from the Dominion Radio
  Astrophysical Observatory in Penticton, BC. The primary proxy for solar EUV
  radiation. Updated daily.
size_categories:
  - 10K<n<100K
task_categories:
  - tabular-regression
tags:
  - space
  - solar
  - f10.7
  - space-weather
  - ionosphere
  - atmospheric-drag
  - open-data
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/f107_solar_flux.parquet
---

# F10.7 Solar Radio Flux (Penticton)

![Update F10.7](https://github.com/juliensimon/space-datasets/actions/workflows/update-f107.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.f107&label=updated&color=brightgreen)

Daily F10.7 cm (2800 MHz) solar radio flux measurements from Penticton, spanning
**{date_min}** to **{date_max}**. Currently **{n:,}** daily records.

## Dataset description

The F10.7 solar radio flux is THE primary proxy for solar extreme ultraviolet (EUV)
radiation. It has been measured continuously since 1947, making it one of the longest
running solar activity indices. It is used in:

- **Atmospheric density models**: NRLMSISE-00, JB2008, and DTM rely on F10.7 to
  compute thermospheric density, which directly affects satellite drag
- **Orbit propagation**: accurate drag modelling requires F10.7 as input, making it
  essential for conjunction assessment and re-entry prediction
- **Ionospheric models**: F10.7 drives ionospheric electron density models used
  for GPS/GNSS correction and HF radio propagation
- **Solar cycle monitoring**: F10.7 tracks the 11-year solar cycle and is used
  in long-term space environment forecasting

Values are measured in Solar Flux Units (SFU), where 1 SFU = 10^-22 W/m^2/Hz.
Quiet-Sun values are around 65-70 SFU; solar maximum can exceed 300 SFU.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `date` | datetime | Observation date (UTC) |
| `observed_flux_sfu` | float64 | Observed flux at local noon (SFU) |
| `adjusted_flux_sfu` | float64 | Flux adjusted to 1 AU distance (SFU) |
| `absolute_flux_sfu` | float64 | Absolute flux calibration (SFU) |

## Quick stats

- **{n:,}** daily observations ({date_min} to {date_max})
- Mean observed flux: **{mean_flux:.1f}** SFU
- Peak observed flux: **{max_flux:.1f}** SFU

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/f107-solar-flux", split="train")
df = ds.to_pandas()

# Recent solar activity
recent = df[df["date"] > "2024-01-01"].sort_values("date")
print(recent[["date", "observed_flux_sfu", "adjusted_flux_sfu"]])

# Solar cycle plot
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(14, 5))
ax.plot(df["date"], df["observed_flux_sfu"], linewidth=0.3, alpha=0.5)
ax.set_xlabel("Date")
ax.set_ylabel("F10.7 (SFU)")
ax.set_title("F10.7 Solar Radio Flux")
plt.show()
```

## Data source

[NRC Herzberg / DRAO Penticton](https://www.spaceweather.gc.ca/forecast-prevision/solar-solaire/solarflux/sx-5-en.php),
via [LASP LISIRD](https://lasp.colorado.edu/lisird/data/penticton_radio_flux/).

## Update schedule

Daily at 14:00 UTC via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Citation

```bibtex
@dataset{{f107_solar_flux,
  author = {{Simon, Julien}},
  title = {{F10.7 Solar Radio Flux (Penticton)}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/f107-solar-flux}},
  note = {{Based on NRC Herzberg / DRAO Penticton F10.7 measurements via LASP LISIRD}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update F10.7 solar flux: {n:,} records"
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
