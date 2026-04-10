#!/usr/bin/env python3
"""Fetch F10.7 Solar Radio Flux data from LASP LISIRD and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

from dataset_images import banner_markdown, download_banner
from validate import check_dataset


LISIRD_URL = "https://lasp.colorado.edu/lisird/latis/dap/penticton_radio_flux.csv"
HF_REPO = "juliensimon/f107-solar-flux"


def main():
    print("Fetching F10.7 Solar Radio Flux from LASP LISIRD...")
    resp = requests.get(LISIRD_URL, timeout=120)
    resp.raise_for_status()

    df = pd.read_csv(pd.io.common.StringIO(resp.text))
    print(f"  {len(df):,} rows, columns: {list(df.columns)}")

    # The LISIRD CSV columns include units in their names, e.g.:
    #   "time (Julian Date)", "observed_flux (solar flux unit (SFU))", etc.
    # Match both with-units and without-units variants.
    time_col = None
    for col in df.columns:
        cl = col.strip().lower()
        if cl.startswith("time"):
            time_col = col
            break

    # Convert time column: Julian Date -> datetime
    if time_col is not None:
        if "julian" in time_col.lower():
            df["date"] = pd.to_datetime(
                df[time_col].astype(float), unit="D", origin="julian", errors="coerce"
            )
        else:
            df["date"] = pd.to_datetime(df[time_col], errors="coerce")
        if time_col != "date":
            df = df.drop(columns=[time_col])

    # Rename flux columns -- match actual names with units
    rename_map = {}
    for col in df.columns:
        cl = col.strip().lower()
        if cl.startswith("observed_flux"):
            rename_map[col] = "observed_flux_sfu"
        elif cl.startswith("adjusted_flux"):
            rename_map[col] = "adjusted_flux_sfu"
        elif cl.startswith("absolute_flux"):
            rename_map[col] = "absolute_flux_sfu"

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

        banner_file = download_banner("f107", tmp)
        banner_md = banner_markdown("f107", banner_file)

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
  - tabular-data
  - parquet
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/f107_solar_flux.parquet
---

# F10.7 Solar Radio Flux (Penticton)
{banner_md}
*Part of the [Space Weather Datasets](https://huggingface.co/collections/juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70) collection on Hugging Face.*

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

The F10.7 index originates from thermal bremsstrahlung and gyroresonance emission in the solar corona and chromosphere, primarily above active regions. Unlike direct EUV measurements -- which require space-based instruments and have only been available since the 1990s -- the 10.7 cm wavelength penetrates Earth's atmosphere, allowing ground-based observation. The measurement has been made at local noon at the Dominion Radio Astrophysical Observatory (DRAO) in Penticton, British Columbia since 1947, first with the original Covington antenna and now with modernized flux monitors. This unbroken 75+ year record makes F10.7 the longest continuous solar activity proxy available, surpassed in length only by the sunspot number (which has lower physical fidelity for EUV modeling).

Three variants are provided: the observed flux (as measured), the adjusted flux (corrected to 1 AU to remove the ~3.3% variation from Earth's orbital eccentricity), and the absolute flux (tied to the calibration scale). For atmospheric modeling, the adjusted value is standard. Most density models also require the 81-day centered average (F10.7bar), which smooths out the 27-day solar rotation modulation and better represents the background EUV irradiance level. The combination of daily F10.7 and F10.7bar captures both the slowly-varying solar cycle baseline and the shorter-term active region contributions to thermospheric heating.

During solar maximum, F10.7 can exceed 300 SFU for extended periods, increasing thermospheric density at 400 km by a factor of 10-20 compared to deep solar minimum (~65 SFU). This has enormous practical consequences: Starlink satellites at 550 km experienced unexpected orbital decay during the February 2022 geomagnetic storm, and ISS reboost frequency scales directly with F10.7 levels. Accurate F10.7 forecasting is therefore essential for constellation management, collision avoidance, and re-entry prediction.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `date` | datetime | Observation date (UTC); Penticton, Canada measurements continuous since 1947 |
| `observed_flux_sfu` | float64 | Daily solar radio flux at 10.7 cm (2800 MHz) measured at local noon in Solar Flux Units (1 SFU = 10⁻²² W/m²/Hz); quiet sun: 65–70 SFU; solar maximum: 200–300+ SFU; required input to atmospheric drag models |
| `adjusted_flux_sfu` | float64 | F10.7 flux corrected to 1 AU from the Sun, removing the ~3.3% variation caused by Earth's orbital eccentricity; preferred value for solar cycle analysis and most operational models |
| `absolute_flux_sfu` | float64 | F10.7 tied to the primary calibration scale (slightly differs from observed due to gain corrections); null for early historical records |

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

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/f107-solar-flux) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

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
