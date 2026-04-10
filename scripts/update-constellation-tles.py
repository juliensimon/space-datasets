#!/usr/bin/env python3
"""Fetch latest TLEs for 18 satellite constellations from CelesTrak and upload to HF.

Uses a single bulk request (GROUP=active, FORMAT=3le) instead of per-constellation
queries. The 3LE format gives raw TLE text with name lines, which we parse into a
DataFrame with NORAD IDs for constellation filtering.

Covers LEO broadband (OneWeb, Kuiper, Qianfan, Hulianwang), LEO comms (Iridium,
Globalstar, ORBCOMM), Earth observation (Planet, Spire), GNSS (GPS, Galileo,
BeiDou, GLONASS, SBAS), and GEO comms (SES, Intelsat, Eutelsat, Telesat).

Starlink is excluded — see update-tle-latest.py for dedicated Starlink TLEs.
"""

import os
import subprocess
import sys
import tempfile
import time
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from dataset_images import banner_markdown, download_banner
from validate import check_dataset

HF_REPO = "juliensimon/constellation-tle-latest"

# Single bulk endpoint — all active satellites in one request (3LE = 3-line TLE text)
BULK_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=3le"
MAX_RETRIES = 3

# Constellation definitions: name patterns used to filter the bulk CSV.
# "patterns" is a list of prefixes matched against OBJECT_NAME (case-insensitive).
# "norad_ids" is an optional set of NORAD catalog numbers for constellations
# where name matching is unreliable (e.g., SBAS with heterogeneous host sats).
CONSTELLATIONS = OrderedDict([
    # LEO Broadband
    ("oneweb",     {"display": "OneWeb",               "operator": "Eutelsat OneWeb",  "orbit": "LEO",     "min_rows": 500,
                    "patterns": ["ONEWEB"]}),
    ("kuiper",     {"display": "Kuiper",               "operator": "Amazon",           "orbit": "LEO",     "min_rows": 2,
                    "patterns": ["KUIPER"]}),
    ("qianfan",    {"display": "Qianfan (G60)",        "operator": "Shanghai Spacecom","orbit": "LEO",     "min_rows": 2,
                    "patterns": ["QIANFAN"]}),
    ("hulianwang", {"display": "Hulianwang (GuoWang)", "operator": "China SatNet",     "orbit": "LEO",     "min_rows": 2,
                    "patterns": ["HULIANWANG"]}),
    # LEO Communications
    ("iridium",    {"display": "Iridium NEXT",         "operator": "Iridium",          "orbit": "LEO",     "min_rows": 60,
                    "patterns": ["IRIDIUM"]}),
    ("globalstar", {"display": "Globalstar",           "operator": "Globalstar",       "orbit": "LEO",     "min_rows": 20,
                    "patterns": ["GLOBALSTAR"]}),
    ("orbcomm",    {"display": "ORBCOMM",              "operator": "ORBCOMM",          "orbit": "LEO",     "min_rows": 15,
                    "patterns": ["ORBCOMM"]}),
    # Earth Observation
    ("planet",     {"display": "Planet Labs",          "operator": "Planet Labs",      "orbit": "LEO",     "min_rows": 100,
                    "patterns": ["FLOCK", "SKYSAT", "PELICAN"]}),
    ("spire",      {"display": "Spire Global",         "operator": "Spire Global",     "orbit": "LEO",     "min_rows": 50,
                    "patterns": ["LEMUR", "SPIRE"]}),
    # GNSS
    ("gps",        {"display": "GPS (NAVSTAR)",        "operator": "USSF",             "orbit": "MEO",     "min_rows": 30,
                    "patterns": ["NAVSTAR"]}),
    ("galileo",    {"display": "Galileo",              "operator": "EU/ESA",           "orbit": "MEO",     "min_rows": 20,
                    "patterns": ["GSAT", "GALILEO"]}),
    ("beidou",     {"display": "BeiDou",               "operator": "CNSA",             "orbit": "MEO/GEO", "min_rows": 40,
                    "patterns": ["BEIDOU"]}),
    ("glonass",    {"display": "GLONASS",              "operator": "Roscosmos",        "orbit": "MEO",     "min_rows": 20,
                    "patterns": ["GLONASS"]}),
    ("sbas",       {"display": "SBAS",                 "operator": "Various",          "orbit": "GEO",     "min_rows": 5,
                    "patterns": ["EGNOS", "GAGAN", "SDCM"],
                    "norad_ids": {
                        # WAAS (US) — hosted on commercial GEO sats, names don't match
                        35491, 38049, 44874,
                        # EGNOS (EU)
                        37718, 44828, 56325,
                        # MSAS (Japan)
                        42622, 42917,
                        # GAGAN (India)
                        38779, 40269,
                        # SDCM (Russia)
                        37372, 39194, 39727,
                        # KASS (Korea)
                        52932,
                    }}),
    # GEO Communications
    ("ses",        {"display": "SES",                  "operator": "SES",              "orbit": "GEO",     "min_rows": 30,
                    "patterns": ["SES-", "ASTRA", "O3B", "NSS-", "AMC-"]}),
    ("intelsat",   {"display": "Intelsat",             "operator": "Intelsat",         "orbit": "GEO",     "min_rows": 30,
                    "patterns": ["INTELSAT"]}),
    ("eutelsat",   {"display": "Eutelsat",             "operator": "Eutelsat",         "orbit": "GEO",     "min_rows": 10,
                    "patterns": ["EUTELSAT"]}),
    ("telesat",    {"display": "Telesat",              "operator": "Telesat",          "orbit": "GEO/LEO", "min_rows": 10,
                    "patterns": ["TELESAT", "TELSTAR"]}),
])


def parse_3le_text(text: str) -> pd.DataFrame:
    """Parse raw 3LE text into a DataFrame with OBJECT_NAME, NORAD_CAT_ID, name, line1, line2."""
    lines = [line.rstrip() for line in text.strip().split("\n") if line.strip()]
    rows = []
    for i in range(0, len(lines) - 2, 3):
        l0, l1, l2 = lines[i], lines[i + 1], lines[i + 2]
        if l1.startswith("1 ") and l2.startswith("2 "):
            name = l0.strip()
            try:
                norad_id = int(l1[2:7])
            except (ValueError, IndexError):
                continue
            rows.append({
                "OBJECT_NAME": name,
                "NORAD_CAT_ID": norad_id,
                "name": name,
                "line1": l1,
                "line2": l2,
            })
    return pd.DataFrame(rows)


def fetch_bulk_catalog() -> pd.DataFrame:
    """Fetch all active satellites from CelesTrak in 3LE format."""
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.get(BULK_URL, timeout=120)
            r.raise_for_status()
            df = parse_3le_text(r.text)
            print(f"  Fetched {len(df):,} satellites from CelesTrak (single request)")
            return df
        except requests.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                wait = 2 ** (attempt + 1)
                print(f"  Retry {attempt + 1}/{MAX_RETRIES} in {wait}s: {e}")
                time.sleep(wait)
            else:
                print(f"::error::Failed to fetch bulk catalog after {MAX_RETRIES} attempts: {e}")
                sys.exit(1)


def match_constellation(row: pd.Series, cdef: dict) -> bool:
    """Check if a satellite row matches a constellation definition."""
    name = str(row.get("OBJECT_NAME", "")).upper()
    norad_ids = cdef.get("norad_ids")
    if norad_ids and int(row.get("NORAD_CAT_ID", 0)) in norad_ids:
        return True
    for prefix in cdef["patterns"]:
        if name.startswith(prefix):
            return True
    return False


def extract_tle_text(group_df: pd.DataFrame) -> str:
    """Build raw 3-line TLE text from parsed DataFrame."""
    lines = []
    for _, row in group_df.iterrows():
        lines.extend([row["name"], row["line1"], row["line2"]])
    return "\n".join(lines) + "\n" if lines else ""


def build_readme(results: dict, banner_md: str, snapshot_time: str) -> str:
    """Generate HF dataset README with 18-constellation coverage."""
    total = sum(len(df) for df, _ in results.values())
    n_constellations = len(results)

    # Build configs YAML
    configs_yaml = ""
    for i, cid in enumerate(results):
        default_line = "\n    default: true" if i == 0 else ""
        configs_yaml += f"""  - config_name: {cid}
    data_files:
      - split: train
        path: data/{cid}.parquet{default_line}
"""

    # Build summary table rows
    table_rows = ""
    for cid, (df, _) in results.items():
        cdef = CONSTELLATIONS[cid]
        table_rows += f"| {cdef['display']} | {cdef['operator']} | {cdef['orbit']} | {len(df):,} |\n"

    # Category summaries
    leo_count = sum(len(df) for cid, (df, _) in results.items()
                    if CONSTELLATIONS[cid]["orbit"] == "LEO")
    meo_count = sum(len(df) for cid, (df, _) in results.items()
                    if CONSTELLATIONS[cid]["orbit"] in ("MEO", "MEO/GEO"))
    geo_count = sum(len(df) for cid, (df, _) in results.items()
                    if CONSTELLATIONS[cid]["orbit"] in ("GEO", "GEO/LEO"))

    # Raw TLE file list
    tle_links = ""
    for cid in results:
        display = CONSTELLATIONS[cid]["display"]
        tle_links += f"- [`data/{cid}.tle`](https://huggingface.co/datasets/{HF_REPO}/resolve/main/data/{cid}.tle) — {display}\n"

    return f"""---
license: cc-by-4.0
pretty_name: "Constellation TLEs — 18 Satellite Constellations"
language:
  - en
description: >-
  Daily TLE snapshots for 18 satellite constellations ({total:,} satellites) from
  CelesTrak. Covers GNSS, LEO broadband, GEO comms, and Earth observation fleets.
task_categories:
  - tabular-regression
tags:
  - space
  - open-data
  - tabular-data
  - parquet
  - satellite
  - tle
  - orbital-mechanics
  - celestrak
  - sgp4
  - gnss
  - gps
  - galileo
  - beidou
  - glonass
  - oneweb
  - iridium
  - constellation
size_categories:
  - 1K<n<10K
configs:
{configs_yaml}---

# Constellation TLEs — 18 Satellite Constellations
{banner_md}
*Part of the [Orbital Mechanics Datasets](https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994) collection on Hugging Face.*

![Update Constellation TLEs](https://github.com/juliensimon/space-datasets/actions/workflows/update-constellation-tles.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['constellation-tles']&label=updated&color=brightgreen)

Daily Two-Line Element (TLE) snapshots for **{n_constellations}** satellite constellations
totaling **{total:,}** satellites, sourced from [CelesTrak](https://celestrak.org/).
Each constellation is available as a separate config for independent loading.

## Constellations

| Constellation | Operator | Orbit | Satellites |
|---------------|----------|-------|----------:|
{table_rows}
**Total: {total:,} satellites** — {leo_count:,} LEO, {meo_count:,} MEO, {geo_count:,} GEO

## Dataset description

Two-Line Element sets (TLEs) are the standard format for representing satellite orbital
elements, developed by NORAD and used universally with the SGP4/SDP4 propagation model.
This dataset provides daily-fresh TLEs for every major non-Starlink constellation in orbit,
organized by operator for easy access.

The collection spans four categories:

**GNSS navigation** (GPS, Galileo, BeiDou, GLONASS, SBAS) — the backbone of global
positioning in MEO/GEO, critical for timing applications, geodesy, and as reference
orbits for propagation model validation.

**LEO broadband** (OneWeb, Kuiper, Qianfan, Hulianwang) — the next wave of
mega-constellations competing with Starlink. OneWeb is fully deployed at 1,200 km;
Amazon's Kuiper and China's Qianfan/Hulianwang are in early deployment phases.

**LEO communications and IoT** (Iridium NEXT, Globalstar, ORBCOMM) — established
mobile satellite service providers operating in low Earth orbit.

**Earth observation** (Planet Labs, Spire Global) — the largest commercial imaging
and weather monitoring fleets, operating in sun-synchronous orbits.

**GEO communications** (SES, Intelsat, Eutelsat, Telesat) — legacy geostationary
operators providing broadcast, broadband, and government services from 35,786 km.

Raw `.tle` files are provided alongside Parquet for maximum compatibility: orbit
propagation libraries like `python-sgp4`, `orekit`, and STK consume the standard
three-line TLE format directly. Because TLE accuracy degrades rapidly (especially
for LEO objects), daily updates are essential for operational applications.

Starlink TLEs are published separately in
[starlink-tle-latest](https://huggingface.co/datasets/juliensimon/starlink-tle-latest)
due to the constellation's size (7,000+ satellites).

## Raw TLE files

For applications that consume standard 3-line TLE format (e.g., SGP4 propagators):

{tle_links}
## Schema (all configs)

| Column | Type | Description |
|--------|------|-------------|
| `norad_cat_id` | int32 | NORAD catalog number — unique integer assigned by US Space Command to every tracked object |
| `name` | string | Satellite name as listed in Space-Track (e.g., "STARLINK-1234", "ONEWEB-0012", "NAVSTAR 78") |
| `constellation` | string | Constellation identifier (e.g., "starlink", "oneweb", "planet", "galileo"); one Parquet file per constellation |
| `line1` | string | TLE line 1 (69 characters): satellite number, classification, epoch, first/second derivative of mean motion, BSTAR drag term, element set number |
| `line2` | string | TLE line 2 (69 characters): inclination, RAAN, eccentricity, argument of perigee, mean anomaly, mean motion (rev/day); use with SGP4 propagator |
| `epoch_utc` | datetime | TLE reference epoch in UTC; elements are most accurate within ±1–2 days of this time |

## Quick stats

- **{total:,}** satellites across **{n_constellations}** constellations
- **{leo_count:,}** LEO + **{meo_count:,}** MEO + **{geo_count:,}** GEO
- Snapshot: {snapshot_time}

## Usage

```python
from datasets import load_dataset

# Load a specific constellation
gps = load_dataset("{HF_REPO}", "gps", split="train")
oneweb = load_dataset("{HF_REPO}", "oneweb", split="train")
galileo = load_dataset("{HF_REPO}", "galileo", split="train")

# Use with sgp4 library for orbit propagation
from sgp4.api import Satrec
sat = Satrec.twoline2rv(gps[0]["line1"], gps[0]["line2"])

# Load all GNSS constellations
import pandas as pd
gnss = pd.concat([
    load_dataset("{HF_REPO}", c, split="train").to_pandas()
    for c in ["gps", "galileo", "beidou", "glonass", "sbas"]
])
print(f"{{len(gnss)}} GNSS satellites")

# Compare constellation sizes
for config in ["oneweb", "iridium", "planet", "spire"]:
    ds = load_dataset("{HF_REPO}", config, split="train")
    print(f"{{config}}: {{len(ds)}} satellites")
```

## Data source

[CelesTrak](https://celestrak.org/) (Dr. T.S. Kelso), mirroring NORAD/18th Space
Defense Squadron data. No authentication required.

## Update schedule

Daily at 05:30 UTC via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [starlink-tle-latest](https://huggingface.co/datasets/juliensimon/starlink-tle-latest) — Daily Starlink + GPS TLEs (dedicated dataset for the largest constellation)
- [space-track-tle-history](https://huggingface.co/datasets/juliensimon/space-track-tle-history) — 238M+ historical TLEs for every cataloged object (1959–present)
- [constellation-census](https://huggingface.co/datasets/juliensimon/constellation-census) — Parsed orbital elements with status classification for all constellations
- [space-track-satcat](https://huggingface.co/datasets/juliensimon/space-track-satcat) — Complete NORAD satellite catalog (68K+ objects)
- [ucs-satellite-database](https://huggingface.co/datasets/juliensimon/ucs-satellite-database) — Active satellites with purpose, operator, and orbit metadata

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/{HF_REPO}) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{constellation_tle_latest,
  author = {{Simon, Julien}},
  title = {{Constellation TLEs — 18 Satellite Constellations}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/{HF_REPO}}},
  note = {{Based on NORAD data via CelesTrak (Dr. T.S. Kelso)}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
"""


def main():
    snapshot_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    print(f"Fetching TLEs for {len(CONSTELLATIONS)} constellations from CelesTrak...")
    catalog = fetch_bulk_catalog()

    # Verify expected columns
    required = {"OBJECT_NAME", "NORAD_CAT_ID", "name", "line1", "line2"}
    missing = required - set(catalog.columns)
    if missing:
        print(f"::error::Catalog missing expected columns: {missing}")
        print(f"  Available columns: {list(catalog.columns)}")
        sys.exit(1)

    # Filter into per-constellation groups
    results = {}  # constellation_id -> (DataFrame, raw_tle_text)
    assigned = set()  # track NORAD IDs already assigned to avoid double-counting

    for cid, cdef in CONSTELLATIONS.items():
        mask = catalog.apply(lambda row: match_constellation(row, cdef), axis=1)
        group_df = catalog[mask & ~catalog["NORAD_CAT_ID"].isin(assigned)]

        if len(group_df) == 0:
            print(f"  {cid:15s} — SKIPPED (no matches in bulk catalog)")
            continue

        assigned.update(group_df["NORAD_CAT_ID"].tolist())

        tle_text = extract_tle_text(group_df)
        df = group_df[["name", "line1", "line2"]].reset_index(drop=True)

        if len(df) == 0:
            print(f"  {cid:15s} — SKIPPED (0 valid TLEs)")
            continue

        if len(df) < cdef["min_rows"]:
            print(f"  {cid:15s} {len(df):6,} sats  WARNING: below min {cdef['min_rows']}")
        else:
            print(f"  {cid:15s} {len(df):6,} sats")

        results[cid] = (df, tle_text)

    if len(results) < 10:
        print(f"::error::Only {len(results)}/18 constellations matched — aborting")
        sys.exit(1)

    total = sum(len(df) for df, _ in results.values())
    print(f"\nTotal: {total:,} satellites across {len(results)} constellations")

    # Validate combined dataset
    combined = pd.concat([df for df, _ in results.values()], ignore_index=True)
    check_dataset(combined, "constellation-tles", min_rows=1000,
                  expected_columns=["name", "line1", "line2"],
                  critical_columns=["name", "line1", "line2"],
                  warn_all_nulls=0.90)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        # Write per-constellation parquet + raw .tle files
        for cid, (df, raw) in results.items():
            df.to_parquet(data_dir / f"{cid}.parquet", index=False,
                          engine="pyarrow", compression="zstd")
            (data_dir / f"{cid}.tle").write_text(raw)

        # Generate README
        banner_file = download_banner("constellation-tles", tmp)
        banner_md = banner_markdown("constellation-tles", banner_file)
        readme = build_readme(results, banner_md, snapshot_time)
        (tmp / "README.md").write_text(readme)

        # Upload
        print("Uploading to HF...")
        commit_msg = (
            f"Update constellation TLEs: {total:,} satellites "
            f"across {len(results)} constellations"
        )
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={total}\n")
    print("Done.")


if __name__ == "__main__":
    main()
