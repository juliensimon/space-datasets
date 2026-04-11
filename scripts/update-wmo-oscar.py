#!/usr/bin/env python3
"""Fetch WMO OSCAR satellite and instrument data, upload to HF.

Two configs:
  - satellites: Earth observation satellite missions with orbit and physical specs
  - instruments: Earth observation instruments cataloged in OSCAR

Source: WMO OSCAR/Space (Observing Systems Capability Analysis and Review Tool),
the authoritative international reference for satellite-based Earth observation.
"""

import pandas as pd
import requests

from hf_dataset_utils import Pipeline, check_dataset, write_parquet
from hf_dataset_utils.banner import banner_markdown as render_banner
from hf_dataset_utils.banner import download_banner
from hf_dataset_utils.github import emit_output
from hf_dataset_utils.readme import _citation_bibtex, _size_category

SATELLITES_URL = "https://space.oscar.wmo.int/satellites"
INSTRUMENTS_URL = "https://space.oscar.wmo.int/instruments"
HF_REPO = "juliensimon/wmo-oscar-satellites"
HEADERS = {"Accept": "application/json"}
TIMEOUT = 60

# ── Column descriptions ─────────────────────────────────────────────────────

SAT_COLUMN_DESCRIPTIONS = {
    "id": "WMO OSCAR internal satellite identifier; unique integer",
    "acronym": "Satellite acronym used in OSCAR and the wider Earth observation community (e.g., 'Sentinel-1A', 'GOES-16', 'Meteosat-12')",
    "name": "Full official satellite name as registered with WMO",
    "programme": "Satellite programme name (e.g., 'Copernicus', 'GOES', 'JPSS')",
    "lead_agency": "Acronym of the lead space agency responsible for the mission (e.g., 'ESA', 'NASA', 'CMA', 'ISRO')",
    "status": "Current operational status: 'Operational', 'Planned', 'Inactive', 'Prototype', or 'Being developed'",
    "orbit_type": "Full orbit type name (e.g., 'Sun-synchronous', 'Geostationary', 'Non-sun-synchronous', 'Drifting')",
    "orbit_type_abbr": "Abbreviated orbit type code used in OSCAR (e.g., 'SSO', 'GEO')",
    "launch_date": "Actual or planned launch date in ISO 8601 format (YYYY-MM-DD); null if unknown",
    "eol_date": "Actual or expected end-of-life date; null for operational or planned satellites without a scheduled decommission",
    "launch_year": "Year of launch extracted from launch_date; null if launch date is unknown",
    "launch_month": "Month of launch (1-12); null if launch date is unknown or only year is provided",
    "launch_day": "Day of launch (1-31); null if launch date is unknown or only year/month provided",
    "eol_year": "Year of end-of-life; null if satellite is operational or EOL date is unknown",
    "eol_month": "Month of end-of-life (1-12); null if EOL date is unknown",
    "eol_day": "Day of end-of-life (1-31); null if EOL date is unknown",
    "mass_kg": "Total satellite mass at launch in kilograms; null if not reported by the agency",
    "dry_mass_kg": "Satellite mass without fuel in kilograms; null for most entries",
    "power_w": "Electrical power generation capacity in watts; null for most entries",
    "altitude_km": "Nominal orbital altitude in kilometers; ~800 km for sun-synchronous LEO, ~35,786 km for GEO",
    "longitude": "Assigned geostationary longitude in degrees; null for non-GEO satellites",
    "inclination": "Orbital inclination in degrees; ~98 deg for sun-synchronous, 0 deg for geostationary",
    "equator_crossing_time": "Local solar time of the ascending/descending equator crossing (e.g., '13:30'); critical for sun-synchronous orbits",
    "ascending_descending": "Whether the equator crossing time refers to the ascending or descending node pass",
    "wigos_station_id": "WMO Integrated Global Observing System station identifier; links satellite to WMO observing network",
    "instrument_acronyms": "Comma-separated list of instrument acronyms onboard the satellite (e.g., 'AVHRR/3,AMSU-A,MHS')",
    "instrument_count": "Number of distinct instruments carried by the satellite; derived from instrument_acronyms",
    "slug": "URL slug for the satellite's page on space.oscar.wmo.int",
}

INST_COLUMN_DESCRIPTIONS = {
    "id": "WMO OSCAR internal instrument identifier; unique integer",
    "acronym": "Instrument acronym (e.g., 'MODIS', 'AVHRR/3', 'AMSU-A', 'SAR-C'); used across the Earth observation community",
    "full_name": "Full instrument name describing its measurement principle (e.g., 'Moderate Resolution Imaging Spectroradiometer')",
    "agency": "Acronym of the space agency that developed the instrument",
    "classification": "WMO instrument classification describing measurement type (e.g., 'Imaging radar (SAR)', 'Multi-purpose imaging VIS/IR radiometer', 'GNSS radio-occultation sounder')",
    "satellite_acronyms": "Comma-separated list of satellites carrying this instrument; links to the satellites config",
    "satellite_count": "Number of distinct satellite platforms carrying or planned to carry this instrument",
    "earliest_launch_year": "Earliest launch year among all host satellites; indicates when this instrument class first flew",
    "latest_eol_year": "Latest end-of-life year among all host satellites; indicates the latest planned operation of this instrument class",
    "slug": "URL slug for the instrument's page on space.oscar.wmo.int",
}

# ── Dataset description ──────────────────────────────────────────────────────
DESCRIPTION = """\
The most comprehensive international database of Earth observation satellites and \
instruments, maintained by the World Meteorological Organization (WMO) through their \
OSCAR/Space portal (Observing Systems Capability Analysis and Review Tool).

Unlike catalogs that focus on a single agency (e.g., NASA, ESA), OSCAR provides truly \
global coverage of the full Earth observation satellite constellation -- from major programs \
like Sentinel, Landsat, and GOES to missions operated by ISRO, CMA, JAXA, KARI, Roscosmos, \
and dozens of smaller agencies. It is used by WMO member states for gap analysis, mission \
planning, and coordination of the Global Observing System.

This dataset is particularly valuable for constellation analysis (mapping global coverage \
by orbit type, status, and agency), instrument gap analysis (identifying which measurement \
capabilities exist or are missing), mission planning (cross-referencing platforms with \
instrument payloads), and historical trend analysis (tracking the growth of the Earth \
observation fleet over time).\
"""


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
    df["launch_date"] = pd.to_datetime(
        df["launch_date"], format="%Y-%m-%d", errors="coerce"
    )
    df["eol_date"] = pd.to_datetime(
        df["eol_date"].astype(str).str.split(" ").str[0],
        format="%Y-%m-%d", errors="coerce",
    )

    for col in ["mass_kg", "dry_mass_kg", "power_w", "altitude_km",
                "launch_year", "eol_year", "launch_month", "launch_day",
                "eol_month", "eol_day"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Replace 0 mass/power with NaN (source uses 0 for unknown)
    for col in ["mass_kg", "dry_mass_kg", "power_w"]:
        df.loc[df[col] == 0, col] = pd.NA

    for col in ["longitude", "inclination"]:
        df[col] = df[col].replace("", pd.NA)
        df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].str.strip()
        df[col] = df[col].replace("", pd.NA)

    for col in ["launch_year", "eol_year"]:
        df.loc[df[col] == 0, col] = pd.NA
    for col in ["launch_month", "launch_day", "eol_month", "eol_day"]:
        df.loc[df[col] == 0, col] = pd.NA

    # Keep only described columns
    df = df[[c for c in df.columns if c in SAT_COLUMN_DESCRIPTIONS]]
    return df


def transform_instruments(df):
    """Clean and coerce instrument data types."""
    for col in ["earliest_launch_year", "latest_eol_year"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        df.loc[df[col] == 0, col] = pd.NA

    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].str.strip()
        df[col] = df[col].replace("", pd.NA)

    # Keep only described columns
    df = df[[c for c in df.columns if c in INST_COLUMN_DESCRIPTIONS]]
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

    top_agencies = satellites["lead_agency"].value_counts().head(10).to_dict()
    agency_list = ", ".join(f"{a} ({c})" for a, c in top_agencies.items())

    # Schema helper
    def _schema(descs):
        lines = ["| Column | Type | Description |", "|--------|------|-------------|"]
        for col, desc in descs.items():
            lines.append(f"| `{col}` | -- | {desc} |")
        return "\n".join(lines)

    quick_stats = f"""\
- **{len(satellites):,}** satellites from **{n_agencies}** agencies across **{n_orbit_types}** orbit types
- **{n_operational}** currently operational, **{n_planned}** planned
- **{len(instruments):,}** instruments in **{n_inst_classes}** classification categories
- Top agencies: {agency_list}"""

    usage = f"""\
```python
from datasets import load_dataset

sats = load_dataset("{HF_REPO}", "satellites", split="train")
insts = load_dataset("{HF_REPO}", "instruments", split="train")

sdf = sats.to_pandas()

# Operational satellites by agency
print(sdf[sdf["status"] == "Operational"]["lead_agency"].value_counts().head(10))

# Satellites by orbit type
print(sdf["orbit_type"].value_counts())

# Heaviest satellites
print(sdf.nlargest(10, "mass_kg")[["acronym", "name", "lead_agency", "mass_kg"]])

# Status distribution with matplotlib
import matplotlib.pyplot as plt
sdf["status"].value_counts().plot.bar()
plt.ylabel("Count")
plt.title("Satellites by Status")
plt.tight_layout()
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="WMO OSCAR Satellite Database",
        description=DESCRIPTION,
        tags=["space", "satellites", "earth-observation", "wmo", "oscar",
              "international", "remote-sensing", "open-data", "tabular-data", "parquet"],
        source_url="https://space.oscar.wmo.int/",
        collection_url="https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994",
        banner={
            "url": "https://images-assets.nasa.gov/image/iss071e439624/iss071e439624~medium.jpg",
            "alt": "An orbital sunrise illuminates the Earth's atmosphere, seen from the ISS",
            "credit": "NASA",
        },
    ) as p:
        write_parquet(satellites, p.data_dir / "satellites.parquet")
        write_parquet(instruments, p.data_dir / "instruments.parquet")

        # Banner
        banner_file = download_banner(p.banner["url"], p.tmp_dir)
        banner_md = render_banner(
            p.banner["alt"], p.banner["credit"],
            filename=banner_file,
        ) if banner_file else ""

        readme = f"""---
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
  - {_size_category(max(len(satellites), len(instruments)))}
---

# WMO OSCAR Satellite Database
{banner_md}
*Part of the [Orbital Mechanics Datasets](https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994) collection on Hugging Face.*

## Dataset description

{DESCRIPTION}

## Configs

### `satellites` -- {len(satellites):,} satellite missions

{_schema(SAT_COLUMN_DESCRIPTIONS)}

### `instruments` -- {len(instruments):,} instruments

{_schema(INST_COLUMN_DESCRIPTIONS)}

## Quick stats

{quick_stats}

## Usage

{usage}

## Data source

[WMO OSCAR/Space](https://space.oscar.wmo.int/) (Observing Systems Capability Analysis
and Review Tool), maintained by the World Meteorological Organization.

## Related datasets

- [juliensimon/gcat-satellite-catalog](https://huggingface.co/datasets/juliensimon/gcat-satellite-catalog) -- GCAT general catalog of artificial space objects
- [juliensimon/ucs-satellite-database](https://huggingface.co/datasets/juliensimon/ucs-satellite-database) -- Union of Concerned Scientists active satellite database
- [juliensimon/space-track-satcat](https://huggingface.co/datasets/juliensimon/space-track-satcat) -- NORAD satellite catalog from Space-Track

## Citation

{_citation_bibtex(HF_REPO, "WMO OSCAR Satellite Database")}

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
"""
        (p.tmp_dir / "README.md").write_text(readme)

        # Upload
        from hf_dataset_utils import upload_to_hf
        commit_msg = (f"Update WMO OSCAR: {len(satellites):,} satellites, "
                      f"{len(instruments):,} instruments")
        upload_to_hf(HF_REPO, p.tmp_dir, commit_msg)
        emit_output(rows=total_rows)

    print(f"Done. {total_rows:,} total rows "
          f"({len(satellites):,} satellites, {len(instruments):,} instruments).")


if __name__ == "__main__":
    main()
