#!/usr/bin/env python3
"""Fetch NOAA/NCEI Solar Proton Events list and upload to HF.

Source: NOAA NCEI Solar Proton Events Affecting the Earth Environment
https://www.ngdc.noaa.gov/stp/space-weather/interplanetary-data/solar-proton-events/
Static dataset (no workflow).
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

from validate import check_dataset

SOURCE_URL = (
    "https://www.ngdc.noaa.gov/stp/space-weather/interplanetary-data/"
    "solar-proton-events/SEP%20page%20code.html"
)
HF_REPO = "juliensimon/solar-proton-events"


def parse_datetime(s):
    """Parse datetime strings like '1976 04/30 2120' or '2025 11/10 1125'."""
    if not s or not isinstance(s, str):
        return pd.NaT
    s = s.strip()
    if not s or s.lower() in ("n/a", "", "-"):
        return pd.NaT
    # Expected format: YYYY MM/DD HHMM
    m = re.match(r"(\d{4})\s+(\d{1,2})/(\d{1,2})\s+(\d{3,4})", s)
    if not m:
        return pd.NaT
    year, month, day, hhmm = m.groups()
    hhmm = hhmm.zfill(4)
    hour, minute = int(hhmm[:2]), int(hhmm[2:])
    try:
        return pd.Timestamp(int(year), int(month), int(day), hour, minute)
    except (ValueError, OverflowError):
        return pd.NaT


def parse_flux(s):
    """Parse proton flux like '12', '1,000', '37,000'."""
    if not s or not isinstance(s, str):
        return None
    s = s.strip().replace(",", "")
    if not s or s.lower() in ("n/a", "-"):
        return None
    try:
        return int(s)
    except ValueError:
        try:
            return float(s)
        except ValueError:
            return None


def parse_flare_info(s):
    """Parse flare maximum field like 'X2/2B 4/30 2114' or 'X1.2/2B 11/10 0919'.

    Returns (flare_class, flare_optical).
    """
    if not s or not isinstance(s, str):
        return None, None
    s = s.strip()
    if not s or s.lower() in ("n/a", "-", ""):
        return None, None
    # Extract flare class (e.g. X2, M5, X1.2) and optical class (e.g. 2B, 3B)
    m = re.match(r"([XMCB]\d+\.?\d*)\s*/\s*(\S+)", s)
    if m:
        return m.group(1), m.group(2)
    # Just flare class, no optical
    m = re.match(r"([XMCB]\d+\.?\d*)", s)
    if m:
        return m.group(1), None
    return None, None


def clean_str(s):
    """Clean a string field, returning None for N/A-like values."""
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    if s.lower() in ("n/a", "-", ""):
        return None
    return s


def main():
    print("Fetching NOAA/NCEI Solar Proton Events list...")
    resp = requests.get(SOURCE_URL, timeout=120)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table", id="myTable")
    if table is None:
        # Fallback: first table
        table = soup.find("table")
    if table is None:
        raise RuntimeError("No table found on the page")

    rows = []
    tbody = table.find("tbody", recursive=False)
    trs = tbody.find_all("tr") if tbody else table.find_all("tr")[1:]
    for tr in trs:
        cells = [re.sub(r"\s+", " ", td.get_text(strip=True)) for td in tr.find_all("td")]
        if len(cells) < 6:
            continue
        rows.append(cells)

    print(f"  Parsed {len(rows)} rows from HTML table")

    records = []
    for cells in rows:
        begin_dt = parse_datetime(cells[0])
        max_dt = parse_datetime(cells[1])
        flux = parse_flux(cells[2])
        region = clean_str(cells[3])
        location = clean_str(cells[4])
        flare_raw = clean_str(cells[5])
        flare_class, flare_optical = parse_flare_info(cells[5])
        type_ii = clean_str(cells[6]) if len(cells) > 6 else None
        type_iv = clean_str(cells[7]) if len(cells) > 7 else None
        cme_speed = clean_str(cells[8]) if len(cells) > 8 else None

        # Parse CME speed as integer where possible
        cme_speed_val = None
        if cme_speed:
            m = re.search(r"(\d+)", cme_speed.replace(",", ""))
            if m:
                cme_speed_val = int(m.group(1))

        records.append({
            "start_datetime": begin_dt,
            "peak_datetime": max_dt,
            "peak_flux_pfu": flux,
            "region_number": region,
            "location": location,
            "flare_class": flare_class,
            "flare_optical": flare_optical,
            "type_ii_radio": type_ii is not None and type_ii.lower() not in ("no",),
            "type_iv_radio": type_iv is not None and type_iv.lower() not in ("no",),
            "cme_speed_km_s": cme_speed_val,
        })

    df = pd.DataFrame(records)

    # Coerce types
    df["peak_flux_pfu"] = pd.to_numeric(df["peak_flux_pfu"], errors="coerce").astype("Int64")
    df["cme_speed_km_s"] = pd.to_numeric(df["cme_speed_km_s"], errors="coerce").astype("Int64")
    df["start_datetime"] = pd.to_datetime(df["start_datetime"], errors="coerce")
    df["peak_datetime"] = pd.to_datetime(df["peak_datetime"], errors="coerce")

    # Drop rows with no start datetime (garbage rows)
    df = df.dropna(subset=["start_datetime"]).reset_index(drop=True)
    df = df.sort_values("start_datetime").reset_index(drop=True)

    print(f"  {len(df):,} events after cleaning")

    check_dataset(
        df, "solar-proton-events", min_rows=200,
        expected_columns=[
            "start_datetime", "peak_datetime", "peak_flux_pfu",
            "flare_class", "location",
        ],
        critical_columns=["start_datetime", "peak_flux_pfu"],
    )

    # Stats for README
    n = len(df)
    date_min = df["start_datetime"].min().strftime("%Y-%m-%d")
    date_max = df["start_datetime"].max().strftime("%Y-%m-%d")
    flux_max = df["peak_flux_pfu"].max()
    flux_median = df["peak_flux_pfu"].median()
    flare_counts = df["flare_class"].dropna().str[0].value_counts().to_dict()
    flare_lines = "\n".join(
        f"  - {k}-class: **{v:,}**" for k, v in sorted(flare_counts.items())
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "solar_proton_events.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_kb = out.stat().st_size / 1024
        print(f"  {size_kb:.0f} KB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Solar Proton Events"
language:
  - en
description: >-
  Solar proton events (SPEs) affecting the Earth environment from 1976 to present,
  compiled by NOAA's Space Weather Prediction Center. Includes peak proton flux,
  associated flare class, location, and CME data.
size_categories:
  - n<1K
task_categories:
  - tabular-classification
tags:
  - space
  - solar
  - protons
  - radiation
  - space-weather
  - noaa
  - open-data
  - tabular-data
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/solar_proton_events.parquet
---

# Solar Proton Events

*Part of the [Space Weather Datasets](https://huggingface.co/collections/juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70) collection on Hugging Face.*

Solar proton events (SPEs) affecting the Earth environment from **{date_min}** to
**{date_max}**. Currently **{n:,}** events where the >10 MeV proton flux exceeded
10 particle flux units (pfu) as measured by GOES spacecraft at geosynchronous orbit.

## Dataset description

Solar proton events occur when protons are accelerated to high energies by solar
flares or coronal mass ejections (CMEs). When these energetic particles reach Earth,
they can disrupt satellite electronics, increase radiation doses for astronauts and
high-altitude aviation, degrade HF radio communications, and affect GPS accuracy.

This dataset covers the complete NOAA record from 1976 onward, including:

- **Proton flux**: peak >10 MeV flux in particle flux units (pfu)
- **Associated flares**: X-ray class (X, M, C, B) and optical classification
- **Source location**: heliographic coordinates of the associated flare
- **Radio emissions**: Type II and Type IV radio burst associations
- **CME speed**: linear speed of associated coronal mass ejection (km/s)

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `start_datetime` | datetime | Event start time (UTC) |
| `peak_datetime` | datetime | Time of peak >10 MeV flux (UTC) |
| `peak_flux_pfu` | int | Peak proton flux >10 MeV (particle flux units) |
| `region_number` | string | NOAA active region number |
| `location` | string | Heliographic coordinates of associated flare |
| `flare_class` | string | X-ray flare class (e.g., X5, M7, C3) |
| `flare_optical` | string | Optical flare classification (e.g., 2B, 3B) |
| `type_ii_radio` | bool | Type II radio emission observed |
| `type_iv_radio` | bool | Type IV radio emission observed |
| `cme_speed_km_s` | int | CME linear speed (km/s), where available |

## Quick stats

- **{n:,}** events ({date_min} to {date_max})
- Peak flux range: 10 to **{flux_max:,}** pfu (median: {flux_median:,.0f} pfu)
- Associated flares by X-ray class:
{flare_lines}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/solar-proton-events", split="train")
df = ds.to_pandas()

# Largest proton events
top = df.nlargest(10, "peak_flux_pfu")
print(top[["start_datetime", "peak_flux_pfu", "flare_class", "location"]])

# Events with X-class flares
x_class = df[df["flare_class"].str.startswith("X", na=False)]
print(f"X-class associated events: {{len(x_class)}}")
```

## Data source

[NOAA NCEI Solar Proton Events](https://www.ngdc.noaa.gov/stp/space-weather/interplanetary-data/solar-proton-events/)
compiled by the Space Weather Prediction Center.

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/solar-proton-events) and share feedback in the Community tab!

## Citation

```bibtex
@dataset{{solar_proton_events,
  author = {{Simon, Julien}},
  title = {{Solar Proton Events}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/solar-proton-events}},
  note = {{Based on NOAA NCEI Solar Proton Events data}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Upload solar proton events: {n:,} records"
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
