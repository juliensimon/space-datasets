#!/usr/bin/env python3
"""Fetch GCAT launch log and sites, upload to HF.

Source: Jonathan McDowell's General Catalog of Artificial Space Objects (GCAT)
https://planet4589.org/space/gcat/
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.banner import banner_markdown as render_banner
from hf_dataset_utils.banner import download_banner
from hf_dataset_utils.github import emit_output
from hf_dataset_utils.readme import _citation_bibtex, _size_category
from hf_dataset_utils.upload import upload_to_hf, write_parquet
from hf_dataset_utils.validation import check_dataset

LAUNCH_URL = "https://planet4589.org/space/gcat/tsv/launch/launch.tsv"
SITES_URL = "https://planet4589.org/space/gcat/tsv/tables/sites.tsv"
HF_REPO = "juliensimon/space-launch-log"

LAUNCH_COLS = [
    "launch_tag", "launch_jd", "launch_date", "lv_type", "variant", "flight_id",
    "flight", "mission", "flight_code", "platform", "launch_site", "launch_pad",
    "ascent_site", "ascent_pad", "apogee", "apogee_flag", "range", "range_flag",
    "destination", "orbital_payload", "agency", "launch_code", "fail_code",
    "group", "category", "lt_cite", "cite", "notes",
]

SITES_COLS = [
    "site", "code", "ucode", "type", "state_code", "start", "stop", "short_name",
    "name", "location", "longitude", "latitude", "error", "parent",
    "short_ename", "ename", "group", "uname",
]

# ── Column descriptions ───────────────────────────────────────────────

LAUNCH_COLUMN_DESCRIPTIONS = {
    "launch_tag": "Unique GCAT launch identifier (e.g. '1957-001', '2026-042'); sequential within each year and used as the primary key across GCAT tables",
    "launch_jd": "Launch time as Julian Date (days since 4713 BC Jan 1.5); enables precise time-of-day calculations and cross-referencing with astronomical ephemerides",
    "launch_date": "Launch date and time in ISO-ish format (YYYY Mon DD HHMM:SS or similar); the human-readable timestamp for the launch event",
    "lv_type": "Launch vehicle type designation (e.g. 'Falcon 9', 'Soyuz-2-1a', 'CZ-5B'); cross-references the GCAT launch vehicles table",
    "variant": "Vehicle variant or block number providing additional specificity beyond lv_type (e.g. 'Block 5', 'FG')",
    "flight_id": "Flight identifier assigned by the launch provider or range (e.g. Falcon 9 booster serial number, mission designator)",
    "flight": "Sequential flight number for the vehicle type or booster",
    "mission": "Mission name or primary payload name (e.g. 'Starlink Group 6-14', 'Mars 2020')",
    "flight_code": "GCAT flight outcome code detailing launch and mission success",
    "platform": "Launch platform type (e.g. fixed pad, mobile launcher, sea platform, air launch)",
    "launch_site": "Launch site code referencing the GCAT sites table; identifies the facility (e.g. 'CC' for Cape Canaveral, 'GIK-5' for Baikonur)",
    "launch_pad": "Specific launch pad within the site (e.g. 'LC39A', 'Pad 1')",
    "ascent_site": "Ascent corridor site if different from the launch site (e.g. for air-launched vehicles); null when same as launch site",
    "ascent_pad": "Ascent corridor pad identifier; null when same as launch pad",
    "apogee": "Achieved apogee altitude in km; for suborbital flights this is the peak altitude; for orbital launches may reflect the initial orbit or be null",
    "apogee_flag": "Qualifier on apogee: '~' approximate, '<' upper bound, '>' lower bound",
    "range": "Downrange distance in km for suborbital flights; null for orbital launches",
    "range_flag": "Qualifier on range: '~' approximate, '<' upper bound, '>' lower bound",
    "destination": "Target orbit or destination (e.g. 'LEO', 'GTO', 'Mars', 'Lunar'); describes the intended final orbit or trajectory",
    "orbital_payload": "Whether the launch carried a payload to orbit: 'Y' for orbital payload, 'N' for suborbital or failed",
    "agency": "Responsible launch agency or operator code (e.g. 'SpaceX', 'Arianespace', 'CASC')",
    "launch_code": "Launch outcome code: first character O = orbital success, S = suborbital success, F = failure, U = unknown",
    "fail_code": "Failure mode details if the launch failed; describes the stage and nature of the failure; null for successful launches",
    "group": "Launch group or campaign identifier linking related launches",
    "category": "Launch category: O = orbital, S = suborbital, D = deep space, M = marginal; high-level classification of the mission type",
    "lt_cite": "Citation source for the launch time data",
    "cite": "General citation or reference source for the launch record",
    "notes": "Additional notes on the launch including anomalies, payload details, or historical context",
}

SITE_COLUMN_DESCRIPTIONS = {
    "site": "GCAT site identifier (e.g. 'KSC', 'GIK-5'); the primary key used in launch records' launch_site column",
    "code": "Short code for the site used in compact references",
    "ucode": "Unicode-safe code for the site",
    "type": "Site type classification: LS = launch site, LP = launch pad, TR = test range, MS = missile site, etc.",
    "state_code": "Country/state code where the site is located (e.g. 'US', 'RU', 'CN', 'FR')",
    "start": "Date the site became operational; null if the activation date is unknown or pre-dates records",
    "stop": "Date the site ceased operations; null if the site is still active or decommission date is unknown",
    "short_name": "Short name for the site in the local language",
    "name": "Full name of the site in the local language (e.g. Cyrillic for Russian sites)",
    "location": "Geographic location description (city, province, country)",
    "longitude": "Site longitude in decimal degrees (WGS-84); east positive; enables geospatial analysis of global launch infrastructure",
    "latitude": "Site latitude in decimal degrees (WGS-84); north positive; launch site latitude constrains achievable orbital inclinations",
    "error": "Estimated position error in the geographic coordinates; null when coordinates are precisely known",
    "parent": "Parent site identifier for pads within larger complexes (e.g. individual pads at Cape Canaveral reference 'CC' as parent)",
    "short_ename": "Short English name for sites where the primary name is not in English",
    "ename": "Full English name for the site",
    "group": "Site group or complex grouping related facilities",
    "uname": "Unicode-encoded full name for sites with non-ASCII characters",
}

# ── Dataset description ──────────────────────────────────────────────

DESCRIPTION = """\
Complete global launch history from Jonathan McDowell's General Catalog of Artificial \
Space Objects (GCAT) at the Harvard-Smithsonian Center for Astrophysics. Every orbital \
and suborbital launch attempt is cataloged with its vehicle type, launch site, mission \
objective, operating agency, and outcome code.

McDowell, an astrophysicist at the Harvard-Smithsonian Center for Astrophysics, \
cross-references official government records, regulatory filings, tracking data, and \
open-source intelligence to maintain a launch log that frequently corrects errors in \
official databases. GCAT distinguishes between orbital and suborbital attempts, records \
partial failures where payloads reached unintended orbits, and assigns standardized \
vehicle designations across different naming conventions.

The companion sites table provides geographic coordinates and operational history for \
every launch facility worldwide, from Cape Canaveral and Baikonur to mobile sea-launch \
platforms. When joined with the launch records, it enables geospatial analysis of global \
launch infrastructure and its expansion over seven decades.
"""


def _schema_section(title, descriptions):
    """Generate a markdown schema table from column descriptions dict."""
    lines = [f"### {title}", "", "| Column | Description |", "|--------|-------------|"]
    for col, desc in descriptions.items():
        lines.append(f"| `{col}` | {desc} |")
    return "\n".join(lines)


def main():
    # ── Fetch ────────────────────────────────────────────────────────────
    print("Fetching GCAT launch log...")
    df = pd.read_csv(LAUNCH_URL, sep="\t", comment="#", names=LAUNCH_COLS, low_memory=False)
    df["launch_jd"] = pd.to_numeric(df["launch_jd"], errors="coerce")
    df["apogee"] = pd.to_numeric(df["apogee"], errors="coerce")
    df["range"] = pd.to_numeric(df["range"], errors="coerce")
    print(f"  {len(df):,} launches")

    print("Fetching GCAT sites...")
    sites = pd.read_csv(SITES_URL, sep="\t", comment="#", names=SITES_COLS, low_memory=False)
    sites["longitude"] = pd.to_numeric(sites["longitude"], errors="coerce")
    sites["latitude"] = pd.to_numeric(sites["latitude"], errors="coerce")
    print(f"  {len(sites):,} sites")

    # ── Keep only described columns ──────────────────────────────────────
    df = df[[c for c in df.columns if c in LAUNCH_COLUMN_DESCRIPTIONS]]
    sites = sites[[c for c in sites.columns if c in SITE_COLUMN_DESCRIPTIONS]]

    # ── Validate ─────────────────────────────────────────────────────────
    check_dataset(df, "launches", min_rows=70000,
                  expected_columns=["launch_tag", "launch_date", "lv_type", "launch_site"],
                  critical_columns=["launch_tag"])
    check_dataset(sites, "sites", min_rows=600,
                  expected_columns=["site", "name", "longitude", "latitude"],
                  critical_columns=["longitude", "latitude"])

    # ── Stats for README ─────────────────────────────────────────────────
    total_rows = len(df) + len(sites)
    n_orbital = int(df["launch_code"].str[0].eq("O").sum()) if "launch_code" in df.columns else 0
    n_suborbital = int(df["launch_code"].str[0].eq("S").sum()) if "launch_code" in df.columns else 0
    n_agencies = df["agency"].nunique()
    first_year = df["launch_date"].str[:4].min() if "launch_date" in df.columns else "1957"
    latest_year = df["launch_date"].str[:4].max() if "launch_date" in df.columns else "2026"
    top_vehicles = df["lv_type"].value_counts().head(5)

    quick_stats = f"""\
- **{len(df):,}** launches ({n_orbital:,} orbital, {n_suborbital:,} suborbital)
- **{n_agencies}** distinct agencies/operators
- **{len(sites):,}** launch sites
- Coverage: **{first_year}--{latest_year}**
- Top vehicles: {', '.join(f'{v} ({c:,})' for v, c in top_vehicles.items())}"""

    usage = """\
```python
from datasets import load_dataset

launches = load_dataset("juliensimon/space-launch-log", "launches", split="train")
sites = load_dataset("juliensimon/space-launch-log", "sites", split="train")

df = launches.to_pandas()

# Launches per year
import matplotlib.pyplot as plt
df["year"] = df["launch_date"].str[:4].astype(float)
yearly = df.groupby("year").size()
plt.bar(yearly.index, yearly.values, width=0.8)
plt.xlabel("Year")
plt.ylabel("Launches")
plt.title("Global Launch Cadence")
plt.show()

# Most-used launch vehicles
print(df["lv_type"].value_counts().head(10))

# Join with site coordinates for geospatial analysis
sites_df = sites.to_pandas()
df_geo = df.merge(sites_df[["code", "latitude", "longitude"]],
                  left_on="launch_site", right_on="code", how="left")
```"""

    # ── Build multi-config dataset ───────────────────────────────────────
    with Pipeline(
        repo=HF_REPO,
        pretty_name="Global Space Launch Log",
        description="",  # custom README below
        tags=[],
        source_url="https://planet4589.org/space/gcat/",
        collection_url="https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994",
        banner={
            "url": "https://images-assets.nasa.gov/image/iss071e439624/iss071e439624~medium.jpg",
            "alt": "An orbital sunrise illuminates the Earth's atmosphere, seen from the ISS",
            "credit": "NASA",
        },
    ) as p:
        write_parquet(df, p.data_dir / "launches.parquet")
        write_parquet(sites, p.data_dir / "sites.parquet")

        # Banner
        banner_file = download_banner(p.banner["url"], p.tmp_dir)
        banner_md = render_banner(
            p.banner["alt"], p.banner["credit"], filename=banner_file,
        ) if banner_file else ""

        launch_schema = _schema_section("Launches schema", LAUNCH_COLUMN_DESCRIPTIONS)
        site_schema = _schema_section("Sites schema", SITE_COLUMN_DESCRIPTIONS)

        readme = f"""---
license: cc-by-4.0
pretty_name: "Global Space Launch Log"
language:
  - en
description: "Every orbital launch attempt since 1957 from GCAT, with vehicles, sites, and outcomes."
task_categories:
  - tabular-classification
  - time-series-forecasting
tags:
  - space
  - launches
  - rockets
  - gcat
  - orbital-mechanics
  - open-data
  - spaceflight
  - launch-vehicle
  - tabular-data
  - parquet
size_categories:
  - {_size_category(total_rows)}
configs:
  - config_name: launches
    data_files:
      - split: train
        path: data/launches.parquet
    default: true
  - config_name: sites
    data_files:
      - split: train
        path: data/sites.parquet
---

# Space Launch Log
{banner_md}
*Part of a [dataset collection](https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994) on Hugging Face.*

![Update Launch Log](https://github.com/juliensimon/space-datasets/actions/workflows/update-launch-log.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['launch-log']&label=updated&color=brightgreen)

## Dataset description

{DESCRIPTION}

## Configs

| Config | Records | Description |
|--------|---------|-------------|
| `launches` | **{len(df):,}** | Every known launch attempt -- orbital, suborbital, and failed -- from {first_year} to present |
| `sites` | **{len(sites):,}** | Launch facilities, pads, and test ranges worldwide |

{launch_schema}

{site_schema}

## Quick stats

{quick_stats}

## Usage

{usage}

## Data source

[GCAT](https://planet4589.org/space/gcat/) (General Catalog of Artificial Space Objects)
by Jonathan McDowell, Harvard-Smithsonian Center for Astrophysics.

## Update schedule

Weekly on Mondays at 07:00 UTC via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [juliensimon/starlink-fleet-data](https://huggingface.co/datasets/juliensimon/starlink-fleet-data)
- [juliensimon/space-track-satcat](https://huggingface.co/datasets/juliensimon/space-track-satcat)
- [juliensimon/starlink-ground-stations](https://huggingface.co/datasets/juliensimon/starlink-ground-stations)

## Citation

{_citation_bibtex(HF_REPO, "Global Space Launch Log")}

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
"""
        (p.tmp_dir / "README.md").write_text(readme)

        upload_to_hf(
            HF_REPO, p.tmp_dir,
            f"Update launch log: {len(df):,} launches, {len(sites):,} sites",
        )

    emit_output(rows=len(df))
    print("Done.")


if __name__ == "__main__":
    main()
