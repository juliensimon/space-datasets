#!/usr/bin/env python3
"""Fetch latest Starlink + GPS TLEs from CelesTrak and upload to HF.

Two configs:
  - starlink: ~7,000+ Starlink satellites
  - gps: ~31 GPS NAVSTAR satellites

Raw .tle files are provided alongside Parquet for SGP4 propagator compatibility.
"""

import time

import pandas as pd
import requests

from hf_dataset_utils import Pipeline, check_dataset, write_parquet
from hf_dataset_utils.banner import banner_markdown as render_banner
from hf_dataset_utils.banner import download_banner
from hf_dataset_utils.github import emit_output
from hf_dataset_utils.readme import _citation_bibtex, _size_category

STARLINK_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=tle"
GPS_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP=gps-ops&FORMAT=tle"
HF_REPO = "juliensimon/starlink-tle-latest"

# ── Column descriptions ─────────────────────────────────────────────────────

COLUMN_DESCRIPTIONS = {
    "name": "Satellite common name from the NORAD catalog (e.g., 'STARLINK-1234', 'NAVSTAR 78 (USA-326)')",
    "line1": "First line of the NORAD TLE format: contains NORAD catalog number, international designator, epoch, first and second derivatives of mean motion, BSTAR drag term, and element set number; parse with the sgp4 library",
    "line2": "Second line of the NORAD TLE format: contains inclination, RAAN, eccentricity, argument of perigee, mean anomaly, mean motion (rev/day), and revolution number at epoch; together with line1 fully defines the satellite's orbit for SGP4 propagation",
}

# ── Dataset description ──────────────────────────────────────────────────────
DESCRIPTION = """\
Latest Two-Line Element (TLE) orbital data for the Starlink and GPS constellations, \
sourced daily from CelesTrak.

Two-Line Element sets (TLEs) are the standard format for representing satellite orbital \
elements, developed by NORAD in the 1960s and still used universally today. Each TLE \
encodes six Keplerian orbital elements plus drag terms in a compact two-line ASCII format \
designed for use with the SGP4/SDP4 analytical propagation model.

This dataset provides daily-fresh TLEs for two critical constellations. The Starlink TLEs \
enable tracking of the largest object population in LEO -- essential for conjunction \
screening, RF interference analysis, and constellation operations research. The GPS TLEs \
cover the NAVSTAR constellation in MEO, which serves as the backbone of the Global \
Positioning System.

Raw .tle files are provided alongside Parquet for maximum compatibility: orbit propagation \
libraries like python-sgp4, orekit, and STK consume the standard three-line TLE format \
directly. Because TLE accuracy degrades rapidly with time (especially for LEO objects \
experiencing variable atmospheric drag), daily updates are essential.\
"""


def fetch_tle(url: str, label: str, retries: int = 3) -> str:
    """Fetch raw TLE text with retry (CelesTrak 500s are common)."""
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            return r.text
        except requests.RequestException as e:
            if attempt < retries - 1:
                wait = 2 ** (attempt + 1)
                print(f"  Retry {attempt + 1}/{retries} for {label} in {wait}s: {e}")
                time.sleep(wait)
            else:
                raise


def parse_tle_text(text: str) -> pd.DataFrame:
    """Parse 3-line TLE blocks into a DataFrame."""
    lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
    rows = []
    for i in range(0, len(lines) - 2, 3):
        name, l1, l2 = lines[i], lines[i + 1], lines[i + 2]
        if l1.startswith("1 ") and l2.startswith("2 "):
            rows.append({"name": name, "line1": l1, "line2": l2})
    return pd.DataFrame(rows)


def main():
    # Fetch
    print("Fetching Starlink TLEs...")
    starlink_text = fetch_tle(STARLINK_URL, "starlink")
    starlink_df = parse_tle_text(starlink_text)
    print(f"  {len(starlink_df):,} Starlink satellites")

    print("Fetching GPS TLEs...")
    gps_text = fetch_tle(GPS_URL, "gps")
    gps_df = parse_tle_text(gps_text)
    print(f"  {len(gps_df):,} GPS satellites")

    # Keep only described columns
    starlink_df = starlink_df[[c for c in starlink_df.columns if c in COLUMN_DESCRIPTIONS]]
    gps_df = gps_df[[c for c in gps_df.columns if c in COLUMN_DESCRIPTIONS]]

    # Validate
    check_dataset(starlink_df, "tle-latest-starlink", min_rows=6000,
                  expected_columns=["name", "line1", "line2"],
                  critical_columns=["name", "line1", "line2"])
    check_dataset(gps_df, "tle-latest-gps", min_rows=30,
                  expected_columns=["name", "line1", "line2"],
                  critical_columns=["name", "line1", "line2"])

    total = len(starlink_df) + len(gps_df)

    # ── Schema helper ────────────────────────────────────────────────
    def _schema(descs):
        lines = ["| Column | Type | Description |", "|--------|------|-------------|"]
        for col, desc in descs.items():
            lines.append(f"| `{col}` | -- | {desc} |")
        return "\n".join(lines)

    quick_stats = f"""\
- **{len(starlink_df):,}** Starlink satellites
- **{len(gps_df):,}** GPS NAVSTAR satellites
- **{total:,}** total TLEs"""

    usage = f"""\
```python
from datasets import load_dataset

# Starlink TLEs
ds = load_dataset("{HF_REPO}", "starlink", split="train")

# GPS TLEs
ds = load_dataset("{HF_REPO}", "gps", split="train")

# Use with sgp4 library
from sgp4.api import Satrec
sat = Satrec.twoline2rv(ds[0]["line1"], ds[0]["line2"])

# Compare constellation sizes with matplotlib
import matplotlib.pyplot as plt
sizes = {{"Starlink": {len(starlink_df):,}, "GPS": {len(gps_df):,}}}
plt.bar(sizes.keys(), sizes.values())
plt.ylabel("Satellites")
plt.title("TLE Count by Constellation")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Latest Starlink & GPS TLEs",
        description=DESCRIPTION,
        tags=["space", "satellite", "starlink", "gps", "tle", "orbital-mechanics",
              "celestrak", "sgp4", "open-data", "tabular-data", "parquet"],
        source_url="https://celestrak.org/",
        license="other",
        license_name="celestrak-usage-policy",
        license_link="https://celestrak.org/usage-policy.php",
        collection_url="https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994",
        banner={
            "url": "https://images-assets.nasa.gov/image/iss071e439624/iss071e439624~medium.jpg",
            "alt": "An orbital sunrise illuminates the Earth's atmosphere, seen from the ISS",
            "credit": "NASA",
        },
    ) as p:
        # Write parquet + raw .tle files
        write_parquet(starlink_df, p.data_dir / "starlink.parquet")
        write_parquet(gps_df, p.data_dir / "gps.parquet")
        (p.data_dir / "starlink.tle").write_text(starlink_text)
        (p.data_dir / "gps.tle").write_text(gps_text)

        # Banner
        banner_file = download_banner(p.banner["url"], p.tmp_dir)
        banner_md = render_banner(
            p.banner["alt"], p.banner["credit"],
            filename=banner_file,
        ) if banner_file else ""

        readme = f"""---
license: cc-by-4.0
pretty_name: "Latest Starlink & GPS TLEs"
language:
  - en
description: "Latest Two-Line Element sets for Starlink and GPS constellations, updated daily from CelesTrak."
task_categories:
  - tabular-regression
tags:
  - space
  - satellite
  - starlink
  - gps
  - tle
  - orbital-mechanics
  - celestrak
  - sgp4
  - open-data
  - tabular-data
  - parquet
size_categories:
  - {_size_category(total)}
configs:
  - config_name: starlink
    data_files:
      - split: train
        path: data/starlink.parquet
    default: true
  - config_name: gps
    data_files:
      - split: train
        path: data/gps.parquet
---

# Latest Starlink & GPS TLEs
{banner_md}
*Part of the [Orbital Mechanics Datasets](https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994) collection on Hugging Face.*

## Dataset description

{DESCRIPTION}

## Raw TLE files

- [`data/starlink.tle`](https://huggingface.co/datasets/{HF_REPO}/resolve/main/data/starlink.tle) -- raw TLE text
- [`data/gps.tle`](https://huggingface.co/datasets/{HF_REPO}/resolve/main/data/gps.tle) -- raw TLE text

## Schema (Parquet)

{_schema(COLUMN_DESCRIPTIONS)}

## Quick stats

{quick_stats}

## Usage

{usage}

## Data source

[CelesTrak](https://celestrak.org/) (Dr. T.S. Kelso), mirroring NORAD/18th Space Defense Squadron data.

## Update schedule

Daily at 05:00 UTC via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [juliensimon/space-track-tle-history](https://huggingface.co/datasets/juliensimon/space-track-tle-history) -- 238M historical TLEs (1959-present)
- [juliensimon/starlink-fleet-data](https://huggingface.co/datasets/juliensimon/starlink-fleet-data) -- Daily Starlink constellation health snapshots
- [juliensimon/space-track-satcat](https://huggingface.co/datasets/juliensimon/space-track-satcat) -- Full NORAD satellite catalog

## Citation

{_citation_bibtex(HF_REPO, "Latest Starlink & GPS TLEs")}

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
"""
        (p.tmp_dir / "README.md").write_text(readme)

        # Upload
        from hf_dataset_utils import upload_to_hf
        commit_msg = f"Update TLE latest: {len(starlink_df):,} Starlink + {len(gps_df):,} GPS"
        upload_to_hf(HF_REPO, p.tmp_dir, commit_msg)
        emit_output(rows=total)

    print("Done.")


if __name__ == "__main__":
    main()
