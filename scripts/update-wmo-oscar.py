#!/usr/bin/env python3
"""Fetch WMO OSCAR satellite and instrument data, upload to HF."""

import os
import re
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset

SATELLITES_URL = "https://space.oscar.wmo.int/satellites"
INSTRUMENTS_URL = "https://space.oscar.wmo.int/instruments"
HF_REPO = "juliensimon/wmo-oscar-satellites"
HEADERS = {"Accept": "application/json"}
TIMEOUT = 60


def _snake_case(name):
    """Convert CamelCase or mixed-case to snake_case."""
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    return s.lower()


def fetch_satellites():
    """Fetch all satellites from WMO OSCAR API."""
    print("Fetching satellites...")
    resp = requests.get(SATELLITES_URL, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    print(f"  API returned {data['status']['totalresults']} satellites")

    rows = []
    for item in data["data"]:
        sat = item["Satellite"]
        prog = item["Satelliteprogramme"]
        agency = item["Leadagency"]
        status = item["Satellitestatus"]
        orbit = item["Orbittype"]

        rows.append({
            "id": sat["id"],
            "acronym": sat["acronym"],
            "name": sat["name"],
            "programme": prog.get("name"),
            "lead_agency": agency.get("acronym"),
            "status": status.get("name"),
            "orbit_type": orbit.get("name"),
            "orbit_type_abbr": orbit.get("acronym"),
            "launch_date": sat.get("launchdate"),
            "eol_date": sat.get("eoldate"),
            "launch_year": sat.get("launch_year"),
            "launch_month": sat.get("launch_month"),
            "launch_day": sat.get("launch_day"),
            "eol_year": sat.get("eol_year"),
            "eol_month": sat.get("eol_month"),
            "eol_day": sat.get("eol_day"),
            "mass_kg": sat.get("mass"),
            "dry_mass_kg": sat.get("drymass"),
            "power_w": sat.get("power"),
            "altitude_km": sat.get("altitude"),
            "longitude": sat.get("longitude"),
            "inclination": sat.get("inclination"),
            "equator_crossing_time": sat.get("ect"),
            "ascending_descending": sat.get("ascdesc"),
            "wigos_station_id": sat.get("WIGOS_Station_Identifier"),
            "instrument_acronyms": sat.get("instrumentacronyms"),
            "instrument_count": (
                len(sat["instrumentacronyms"].split(","))
                if sat.get("instrumentacronyms")
                else 0
            ),
            "slug": sat.get("slug"),
        })

    df = pd.DataFrame(rows)
    print(f"  {len(df):,} satellites parsed")
    return df


def fetch_instruments():
    """Fetch all instruments from WMO OSCAR API."""
    print("Fetching instruments...")
    resp = requests.get(INSTRUMENTS_URL, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    print(f"  API returned {data['status']['totalresults']} instruments")

    rows = []
    for item in data["data"]:
        inst = item["Instrument"]
        agency = item["Spaceagency"]
        classification = item["Instrumentclassification"]
        extra = item["Extra"]

        rows.append({
            "id": inst["id"],
            "acronym": inst["acronym"],
            "full_name": inst.get("fullname"),
            "agency": agency.get("acronym"),
            "classification": classification.get("name"),
            "satellite_acronyms": extra.get("satacronyms"),
            "satellite_count": (
                len(extra["satacronyms"].split(","))
                if extra.get("satacronyms")
                else 0
            ),
            "earliest_launch_year": extra.get("launchdate") or None,
            "latest_eol_year": extra.get("eoldate") or None,
            "slug": inst.get("slug"),
        })

    df = pd.DataFrame(rows)
    print(f"  {len(df):,} instruments parsed")
    return df


def transform_satellites(df):
    """Clean and coerce satellite data types."""
    # Parse launch_date (ISO format YYYY-MM-DD)
    df["launch_date"] = pd.to_datetime(
        df["launch_date"], format="%Y-%m-%d", errors="coerce"
    )
    # eol_date has mixed formats (some include time " HH:MM:SS")
    df["eol_date"] = pd.to_datetime(
        df["eol_date"].astype(str).str.split(" ").str[0],
        format="%Y-%m-%d", errors="coerce",
    )

    # Coerce numeric columns
    for col in ["mass_kg", "dry_mass_kg", "power_w", "altitude_km",
                "launch_year", "eol_year", "launch_month", "launch_day",
                "eol_month", "eol_day"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Replace 0 mass/power with NaN (source uses 0 for unknown)
    for col in ["mass_kg", "dry_mass_kg", "power_w"]:
        df.loc[df[col] == 0, col] = pd.NA

    # Coerce longitude/inclination (may have empty strings)
    for col in ["longitude", "inclination"]:
        df[col] = df[col].replace("", pd.NA)
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Clean string columns
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].str.strip()
        df[col] = df[col].replace("", pd.NA)

    # Replace year 0 with NaN
    for col in ["launch_year", "eol_year"]:
        df.loc[df[col] == 0, col] = pd.NA
    for col in ["launch_month", "launch_day", "eol_month", "eol_day"]:
        df.loc[df[col] == 0, col] = pd.NA

    return df


def transform_instruments(df):
    """Clean and coerce instrument data types."""
    # Replace 0 years with NaN
    for col in ["earliest_launch_year", "latest_eol_year"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        df.loc[df[col] == 0, col] = pd.NA

    # Clean string columns
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].str.strip()
        df[col] = df[col].replace("", pd.NA)

    return df


def main():
    # ── Fetch ────────────────────────────────────────────────────────────
    satellites = fetch_satellites()
    instruments = fetch_instruments()

    # ── Transform ────────────────────────────────────────────────────────
    satellites = transform_satellites(satellites)
    instruments = transform_instruments(instruments)

    total_rows = len(satellites) + len(instruments)

    # ── Validate ─────────────────────────────────────────────────────────
    check_dataset(
        satellites, "satellites", min_rows=400,
        expected_columns=["acronym", "name", "lead_agency", "status",
                          "orbit_type", "mass_kg"],
        critical_columns=["acronym", "name", "status"],
    )
    check_dataset(
        instruments, "instruments", min_rows=400,
        expected_columns=["acronym", "full_name", "agency", "classification"],
        critical_columns=["acronym", "agency"],
    )

    # ── Stats for README ─────────────────────────────────────────────────
    n_agencies = satellites["lead_agency"].nunique()
    n_operational = len(satellites[satellites["status"] == "Operational"])
    n_planned = len(satellites[satellites["status"] == "Planned"])
    n_orbit_types = satellites["orbit_type"].dropna().nunique()
    n_inst_classes = instruments["classification"].nunique()

    # Top agencies by satellite count
    top_agencies = (
        satellites["lead_agency"]
        .value_counts()
        .head(10)
        .to_dict()
    )
    agency_list = ", ".join(
        f"{a} ({c})" for a, c in top_agencies.items()
    )

    # Size category
    max_count = max(len(satellites), len(instruments))
    if max_count < 1000:
        size_cat = "n<1K"
    elif max_count < 10000:
        size_cat = "1K<n<10K"
    else:
        size_cat = "10K<n<100K"

    # ── Write parquet + README ───────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        data_dir = tmp_dir / "data"
        data_dir.mkdir()

        satellites.to_parquet(
            data_dir / "satellites.parquet",
            index=False, engine="pyarrow", compression="zstd",
        )
        instruments.to_parquet(
            data_dir / "instruments.parquet",
            index=False, engine="pyarrow", compression="zstd",
        )

        (tmp_dir / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "WMO OSCAR Satellite Database"
language:
  - en
description: "International Earth observation satellite database from WMO OSCAR. {len(satellites):,} satellites and {len(instruments):,} instruments from {n_agencies} space agencies worldwide."
task_categories:
  - tabular-classification
tags:
  - space
  - satellites
  - earth-observation
  - wmo
  - oscar
  - international
  - remote-sensing
  - open-data
  - tabular-data
  - parquet
configs:
  - config_name: satellites
    data_files:
      - split: train
        path: data/satellites.parquet
    default: true
  - config_name: instruments
    data_files:
      - split: train
        path: data/instruments.parquet
size_categories:
  - {size_cat}
---

# WMO OSCAR Satellite Database

*Part of the [Orbital Mechanics Datasets](https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994) collection on Hugging Face.*

The most comprehensive international database of Earth observation satellites and instruments, maintained by the World Meteorological Organization (WMO) through their
[OSCAR/Space](https://space.oscar.wmo.int/) portal (Observing Systems Capability Analysis and Review Tool).
Currently **{len(satellites):,}** satellites and **{len(instruments):,}** instruments from **{n_agencies}** space agencies worldwide.

Unlike catalogs that focus on a single agency (e.g., NASA, ESA), OSCAR provides truly global coverage of the full Earth observation satellite constellation -- from major programs like Sentinel, Landsat, and GOES to missions operated by ISRO, CMA, JAXA, KARI, Roscosmos, and dozens of smaller agencies.

## Dataset description

WMO OSCAR/Space is the authoritative reference for operational meteorological and Earth observation satellites. It is used by WMO member states for gap analysis, mission planning, and coordination of the Global Observing System. Every satellite entry includes its operational status, orbit parameters, launch/end-of-life dates, physical specifications (mass, power), and a list of onboard instruments. The instrument catalog covers {n_inst_classes} distinct instrument classes, from moderate-resolution optical imagers and SAR to GNSS radio-occultation sounders and space lidars.

This dataset is particularly valuable for:
- **Constellation analysis**: mapping global Earth observation coverage by orbit type, status, and agency
- **Instrument gap analysis**: identifying which measurement capabilities exist, are planned, or are missing
- **Mission planning**: cross-referencing satellite platforms with their instrument payloads
- **International cooperation studies**: analyzing which agencies collaborate on which programs
- **Historical trend analysis**: tracking the growth of the Earth observation fleet over time

## Configs

### `satellites` -- {len(satellites):,} satellite missions

Every satellite in the WMO OSCAR database with orbit and physical specifications.

| Column | Type | Description |
|--------|------|-------------|
| `id` | int | WMO OSCAR satellite ID |
| `acronym` | string | Satellite acronym (e.g., "Sentinel-1A") |
| `name` | string | Full satellite name |
| `programme` | string | Satellite programme name |
| `lead_agency` | string | Lead space agency acronym |
| `status` | string | Operational status (Operational, Planned, Inactive, etc.) |
| `orbit_type` | string | Orbit type (Sunsynchronous, Geostationary, etc.) |
| `orbit_type_abbr` | string | Orbit type abbreviation |
| `launch_date` | datetime | Launch date |
| `eol_date` | datetime | End-of-life date |
| `launch_year` | int | Launch year |
| `launch_month` | int | Launch month |
| `launch_day` | int | Launch day |
| `eol_year` | int | End-of-life year |
| `eol_month` | int | End-of-life month |
| `eol_day` | int | End-of-life day |
| `mass_kg` | float | Total mass in kg |
| `dry_mass_kg` | float | Dry mass in kg |
| `power_w` | float | Power in watts |
| `altitude_km` | float | Orbital altitude in km |
| `longitude` | float | Longitude (geostationary satellites) |
| `inclination` | float | Orbital inclination in degrees |
| `equator_crossing_time` | string | Local equator crossing time |
| `ascending_descending` | string | Ascending/descending node |
| `wigos_station_id` | string | WMO WIGOS station identifier |
| `instrument_acronyms` | string | Comma-separated instrument acronyms |
| `instrument_count` | int | Number of instruments onboard |
| `slug` | string | URL slug on OSCAR |

### `instruments` -- {len(instruments):,} instruments

Every Earth observation instrument cataloged in OSCAR.

| Column | Type | Description |
|--------|------|-------------|
| `id` | int | WMO OSCAR instrument ID |
| `acronym` | string | Instrument acronym |
| `full_name` | string | Full instrument name |
| `agency` | string | Developing agency acronym |
| `classification` | string | Instrument classification (e.g., "Imaging radar (SAR)") |
| `satellite_acronyms` | string | Comma-separated host satellite acronyms |
| `satellite_count` | int | Number of host satellites |
| `earliest_launch_year` | int | Earliest launch year among host satellites |
| `latest_eol_year` | int | Latest end-of-life year among host satellites |
| `slug` | string | URL slug on OSCAR |

## Quick stats

- **{len(satellites):,}** satellites from **{n_agencies}** agencies across **{n_orbit_types}** orbit types
- **{n_operational}** currently operational, **{n_planned}** planned
- **{len(instruments):,}** instruments in **{n_inst_classes}** classification categories
- Top agencies: {agency_list}

## Usage

```python
from datasets import load_dataset

sats = load_dataset("juliensimon/wmo-oscar-satellites", "satellites", split="train")
insts = load_dataset("juliensimon/wmo-oscar-satellites", "instruments", split="train")

sdf = sats.to_pandas()

# Operational satellites by agency
print(sdf[sdf["status"] == "Operational"]["lead_agency"].value_counts().head(10))

# Satellites by orbit type
print(sdf["orbit_type"].value_counts())

# Heaviest satellites
print(sdf.nlargest(10, "mass_kg")[["acronym", "name", "lead_agency", "mass_kg"]])

# Instruments by classification
idf = insts.to_pandas()
print(idf["classification"].value_counts())

# SAR instruments and their host satellites
sar = idf[idf["classification"] == "Imaging radar (SAR)"]
print(sar[["acronym", "full_name", "agency", "satellite_acronyms"]])
```

## Data source

[WMO OSCAR/Space](https://space.oscar.wmo.int/) (Observing Systems Capability Analysis and Review Tool),
maintained by the World Meteorological Organization. OSCAR is the international reference for
satellite-based Earth observation capabilities, used by 193 WMO member states for mission planning
and gap analysis.

## Update schedule

Static dataset -- rebuilt manually when significant updates occur (approximately quarterly).

## Related datasets

- [gcat-satellite-catalog](https://huggingface.co/datasets/juliensimon/gcat-satellite-catalog) -- GCAT general catalog of artificial space objects
- [ucs-satellite-database](https://huggingface.co/datasets/juliensimon/ucs-satellite-database) -- Union of Concerned Scientists active satellite database
- [space-track-satcat](https://huggingface.co/datasets/juliensimon/space-track-satcat) -- NORAD satellite catalog from Space-Track

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/wmo-oscar-satellites) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{wmo_oscar_satellites,
  author = {{Simon, Julien}},
  title = {{WMO OSCAR Satellite Database}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/wmo-oscar-satellites}},
  note = {{Based on WMO OSCAR/Space, World Meteorological Organization}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = (f"Update WMO OSCAR: {len(satellites):,} satellites, "
                      f"{len(instruments):,} instruments")
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp_dir), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={total_rows}\n")
    print(f"Done. {total_rows:,} total rows "
          f"({len(satellites):,} satellites, {len(instruments):,} instruments).")


if __name__ == "__main__":
    main()
