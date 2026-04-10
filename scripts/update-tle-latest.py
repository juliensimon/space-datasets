#!/usr/bin/env python3
"""Fetch latest Starlink + GPS TLEs from CelesTrak and upload to HF."""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pandas as pd
import requests

from dataset_images import banner_markdown, download_banner
from validate import check_dataset

STARLINK_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=tle"
GPS_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP=gps-ops&FORMAT=tle"
HF_REPO = "juliensimon/starlink-tle-latest"


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

    # Validate
    check_dataset(starlink_df, "tle-latest-starlink", min_rows=6000,
                  expected_columns=["name", "line1", "line2"],
                  critical_columns=["name", "line1", "line2"])
    check_dataset(gps_df, "tle-latest-gps", min_rows=30,
                  expected_columns=["name", "line1", "line2"],
                  critical_columns=["name", "line1", "line2"])

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        # Write raw .tle files (byte-identical to CelesTrak for direct app consumption)
        (data_dir / "starlink.tle").write_text(starlink_text)
        (data_dir / "gps.tle").write_text(gps_text)

        # Write parquet for data science consumers
        starlink_df.to_parquet(data_dir / "starlink.parquet", index=False,
                               engine="pyarrow", compression="zstd")
        gps_df.to_parquet(data_dir / "gps.parquet", index=False,
                          engine="pyarrow", compression="zstd")

        total = len(starlink_df) + len(gps_df)

        banner_file = download_banner("tle-latest", tmp)
        banner_md = banner_markdown("tle-latest", banner_file)

        (tmp / "README.md").write_text(f"""---
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
  - 1K<n<10K
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

![Update TLE Latest](https://github.com/juliensimon/space-datasets/actions/workflows/update-tle-latest.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.tle-latest&label=updated&color=brightgreen)

Latest Two-Line Element (TLE) orbital data for the **Starlink** ({len(starlink_df):,} satellites) and
**GPS** ({len(gps_df):,} satellites) constellations, sourced daily from
[CelesTrak](https://celestrak.org/).

## Dataset description

Two-Line Element sets (TLEs) are the standard format for representing satellite orbital elements, developed by NORAD in the 1960s and still used universally today. Each TLE encodes six Keplerian orbital elements plus drag terms in a compact two-line ASCII format designed for use with the SGP4/SDP4 analytical propagation model. When fed into an SGP4 propagator, a TLE can predict a satellite's position and velocity for several days forward or backward from its epoch, with accuracy typically within a few kilometers for well-tracked objects.

This dataset provides daily-fresh TLEs for two critical constellations. The Starlink TLEs enable tracking of the largest object population in LEO -- essential for conjunction screening, RF interference analysis, and constellation operations research. The GPS TLEs cover the NAVSTAR constellation in MEO, which serves as the backbone of the Global Positioning System used by billions of devices worldwide. GPS orbital elements are particularly important for precision timing applications, geodetic surveys, and as reference orbits for validating propagation models.

The raw `.tle` files are provided alongside Parquet for maximum compatibility: orbit propagation libraries like `python-sgp4`, `orekit`, and STK consume the standard three-line TLE format directly. The Parquet format is better suited for bulk analysis, filtering, and integration with data science workflows. Because TLE accuracy degrades rapidly with time (especially for LEO objects experiencing variable atmospheric drag), daily updates are essential for any operational application.

## Raw TLE files

For applications that consume standard 3-line TLE format (e.g., SGP4 propagators):

- [`data/starlink.tle`](https://huggingface.co/datasets/{HF_REPO}/resolve/main/data/starlink.tle) — raw TLE text
- [`data/gps.tle`](https://huggingface.co/datasets/{HF_REPO}/resolve/main/data/gps.tle) — raw TLE text

## Schema (Parquet)

| Column | Type | Description |
|--------|------|-------------|
| `name` | string | Satellite common name from the NORAD catalog (e.g., "STARLINK-1234", "NAVSTAR 78 (USA-326)") |
| `line1` | string | First line of the NORAD TLE format: contains NORAD catalog number, international designator, epoch, first and second derivatives of mean motion, BSTAR drag term, and element set number; parse with the `sgp4` library |
| `line2` | string | Second line of the NORAD TLE format: contains inclination, RAAN, eccentricity, argument of perigee, mean anomaly, mean motion (rev/day), and revolution number at epoch; together with `line1` fully defines the satellite's orbit for SGP4 propagation |

## Usage

```python
from datasets import load_dataset

# Starlink TLEs
ds = load_dataset("{HF_REPO}", "starlink", split="train")

# GPS TLEs
ds = load_dataset("{HF_REPO}", "gps", split="train")

# Use with sgp4 library
from sgp4.api import Satrec
sat = Satrec.twoline2rv(ds[0]["line1"], ds[0]["line2"])
```

## Data source

[CelesTrak](https://celestrak.org/) (Dr. T.S. Kelso), mirroring NORAD/18th Space Defense Squadron data.

## Update schedule

Daily at 05:00 UTC via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [space-track-tle-history](https://huggingface.co/datasets/juliensimon/space-track-tle-history) — 238M historical TLEs (1959–present)
- [starlink-fleet-data](https://huggingface.co/datasets/juliensimon/starlink-fleet-data) — Daily Starlink constellation health snapshots
- [space-track-satcat](https://huggingface.co/datasets/juliensimon/space-track-satcat) — Full NORAD satellite catalog

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/starlink-tle-latest) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{starlink_tle_latest,
  author = {{Simon, Julien}},
  title = {{Latest Starlink & GPS TLEs}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/{HF_REPO}}},
  note = {{Based on NORAD data via CelesTrak (Dr. T.S. Kelso)}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update TLE latest: {len(starlink_df):,} Starlink + {len(gps_df):,} GPS"
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
