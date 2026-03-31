#!/usr/bin/env python3
"""Fetch IAU Meteor Data Center shower database and upload to HF."""

import os
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset

# IAU MDC data files (year-suffixed)
YEAR = datetime.now().year
BASE_URL = "https://www.ta3.sk/IAUC22DB/MDC2022/Etc"
FULL_URL = f"{BASE_URL}/streamfulldata{YEAR}.txt"
HF_REPO = "juliensimon/iau-meteor-showers"

# Column names matching the header:
# LP  IAUNo  AdNo  Code  s  sub.date  shower_name  activity
# LoSb  LoSe  LoS  Ra  De  dRa  dDe  Vg
# LoR  S_LoR  LaR  theta  phi  Flags
# a  q  e  peri  node  inc  N  Group  CG
# Origin  Remarks  Ote  L-T  References
COLUMNS = [
    "lp", "iau_no", "ad_no", "code", "status_code", "submission_date",
    "shower_name", "activity_type",
    "sol_lon_begin_deg", "sol_lon_end_deg", "sol_lon_peak_deg",
    "ra_deg", "dec_deg", "ra_daily_motion", "dec_daily_motion",
    "geocentric_velocity_kms",
    "sun_centered_ecliptic_lon_deg", "sun_centered_ecliptic_lat_deg",
    "ecliptic_lat_deg", "theta_deg", "phi_deg",
    "flags",
    "semi_major_axis_au", "perihelion_distance_au", "eccentricity",
    "arg_perihelion_deg", "ascending_node_deg", "inclination_deg",
    "n_meteors", "group_no", "cg",
    "parent_body", "remarks", "ote", "lookup_table", "references",
]

STATUS_MAP = {
    1: "established",
    2: "to_be_established",
    0: "working_list",
    -1: "to_be_removed",
    -2: "lack_of_references",
    -3: "too_few_members",
    -4: "duplicate_or_reclassified",
    -5: "misclassification",
    -6: "pro_tempore",
    -7: "removed",
}


def parse_mdc_file(text: str) -> pd.DataFrame:
    """Parse IAU MDC pipe-delimited text into a DataFrame."""
    rows = []
    for line in text.splitlines():
        if not line.startswith('"'):
            continue
        # Fields are pipe-delimited and quoted
        parts = line.split("|")
        # Strip quotes and whitespace from each field
        cleaned = [p.strip('"').strip() for p in parts]
        rows.append(cleaned)

    # Trim or pad rows to match expected column count
    n_cols = len(COLUMNS)
    trimmed = []
    for row in rows:
        if len(row) >= n_cols:
            trimmed.append(row[:n_cols])
        else:
            trimmed.append(row + [""] * (n_cols - len(row)))

    df = pd.DataFrame(trimmed, columns=COLUMNS)
    return df


def main():
    print(f"Fetching IAU MDC meteor shower data ({YEAR})...")
    resp = requests.get(FULL_URL, timeout=60)
    if resp.status_code == 404:
        # Fall back to previous year if current year file not yet published
        fallback_url = f"{BASE_URL}/streamfulldata{YEAR - 1}.txt"
        print(f"  {YEAR} file not found, trying {YEAR - 1}...")
        resp = requests.get(fallback_url, timeout=60)
    resp.raise_for_status()

    df = parse_mdc_file(resp.text)
    print(f"  {len(df):,} records parsed")

    # ── Numeric coercion ─────────────────────────────────────────────
    int_cols = ["lp", "iau_no"]
    for col in int_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int32")

    df["ad_no"] = pd.to_numeric(df["ad_no"], errors="coerce").astype("Int32")
    df["status_code"] = pd.to_numeric(df["status_code"], errors="coerce").astype("Int16")

    float_cols = [
        "sol_lon_begin_deg", "sol_lon_end_deg", "sol_lon_peak_deg",
        "ra_deg", "dec_deg", "ra_daily_motion", "dec_daily_motion",
        "geocentric_velocity_kms",
        "sun_centered_ecliptic_lon_deg", "sun_centered_ecliptic_lat_deg",
        "ecliptic_lat_deg", "theta_deg", "phi_deg",
        "semi_major_axis_au", "perihelion_distance_au", "eccentricity",
        "arg_perihelion_deg", "ascending_node_deg", "inclination_deg",
    ]
    for col in float_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # N meteors can be a zero-padded integer string
    df["n_meteors"] = pd.to_numeric(df["n_meteors"], errors="coerce").astype("Int32")
    df["group_no"] = pd.to_numeric(df["group_no"], errors="coerce").astype("Int32")

    # ── Derived columns ──────────────────────────────────────────────
    df["status"] = df["status_code"].map(STATUS_MAP).fillna("unknown")
    df["is_established"] = df["status_code"] == 1

    # Clean string columns
    str_cols = ["code", "shower_name", "activity_type", "flags",
                "parent_body", "remarks", "ote", "references"]
    for col in str_cols:
        df[col] = df[col].str.strip()
        # Replace empty strings with NaN
        df[col] = df[col].replace("", pd.NA)

    # Clean up references: strip HTML tags and leading numbering
    df["references"] = (
        df["references"]
        .str.replace(r"<[^>]+>", "", regex=True)  # strip HTML tags
        .str.replace(r"^\d+\]\s*", "", regex=True)  # strip leading "1] "
        .str.strip()
        .replace("", pd.NA)
    )

    # Drop lookup_table column (always the same value)
    df = df.drop(columns=["lookup_table"])

    # ── Sort ─────────────────────────────────────────────────────────
    df = df.sort_values(["iau_no", "ad_no"]).reset_index(drop=True)

    # ── Stats ────────────────────────────────────────────────────────
    n_unique = df["iau_no"].nunique()
    n_established = int(df[df["ad_no"] == 0]["is_established"].sum())
    n_with_parent = int(df["parent_body"].notna().sum())
    top_activity = df["activity_type"].value_counts().head(3)

    print(f"  {n_unique:,} unique showers ({n_established} established)")
    print(f"  {n_with_parent:,} records with identified parent body")

    # ── Validate ─────────────────────────────────────────────────────
    expected = [
        "lp", "iau_no", "ad_no", "code", "status_code", "status",
        "shower_name", "ra_deg", "dec_deg", "geocentric_velocity_kms",
        "semi_major_axis_au", "eccentricity", "inclination_deg",
    ]
    check_dataset(
        df,
        "iau-meteor-showers",
        min_rows=800,
        expected_columns=expected,
        critical_columns=["iau_no", "code", "shower_name", "status"],
    )

    # ── Write & upload ───────────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "iau_meteor_showers.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "IAU Meteor Shower Database"
language:
  - en
description: "Official IAU Meteor Data Center shower database — {n_unique:,} meteor showers with radiant coordinates, geocentric velocities, orbital elements, and parent body identifications."
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - meteors
  - meteor-showers
  - iau
  - orbital-mechanics
  - open-data
  - tabular-data
  - parquet
size_categories:
  - 1K<n<10K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/iau_meteor_showers.parquet
    default: true
---

# IAU Meteor Shower Database

*Part of the [Orbital Mechanics Datasets](https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994) collection on Hugging Face.*

The complete IAU Meteor Data Center shower catalogue: **{len(df):,}** records covering
**{n_unique:,}** uniquely numbered meteor showers. Each record represents one published
analysis of a shower, with radiant coordinates (J2000), geocentric velocity, orbital elements,
activity period, and — where known — the parent body.

## Dataset description

The International Astronomical Union (IAU) Meteor Data Center maintains the authoritative
list of meteor showers. This dataset includes every entry from the MDC shower database:
established showers, working-list candidates, and records flagged for various issues
(insufficient data, duplicates, misclassifications). Multiple records per shower reflect
independent analyses by different research groups.

**{n_established}** showers have the "established" status, verified by the IAU Commission F1.

Meteor showers occur when Earth passes through a stream of debris shed by a comet or, less commonly, an asteroid along its orbit. The radiant -- the apparent point on the sky from which shower meteors diverge -- is determined by the intersection geometry of Earth's orbit with the meteoroid stream. The geocentric velocity depends on the encounter geometry and the stream's own orbital velocity: head-on encounters with retrograde streams (like the Perseids, from comet 109P/Swift-Tuttle) produce fast meteors at 59 km/s, while overtaking encounters with prograde streams (like the Taurids) yield slower meteors near 27 km/s. The radiant position drifts daily as Earth's motion changes the apparent approach direction, captured by the `ra_daily_motion` and `dec_daily_motion` columns.

The orbital elements of each shower constrain the identity of its parent body. Established parent-shower associations are well-determined for major showers (e.g., 1P/Halley for the Eta Aquariids and Orionids, 21P/Giacobini-Zinner for the Draconids), but many working-list showers lack confirmed parents. The solar longitude at peak activity provides a more precise timing reference than calendar date, as it accounts for the irregularities of Earth's elliptical orbit. Multiple records per IAU shower number reflect independent analyses using different observational techniques (visual, video, radar), each contributing orbital element solutions with varying precision and sample sizes recorded in the `n_meteors` column.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `lp` | int32 | Sequential record number |
| `iau_no` | int32 | IAU shower number (unique per shower) |
| `ad_no` | int32 | Additional solution number (0 = primary, 1+ = alternate analyses) |
| `code` | string | Three-letter IAU code (e.g. PER, GEM, LEO) |
| `status_code` | int16 | Numeric status flag (1=established, 0=working list, negative=issues) |
| `status` | string | Human-readable status label |
| `is_established` | bool | True if shower has IAU established status |
| `submission_date` | string | Date submitted to MDC |
| `shower_name` | string | Full shower name-designation |
| `activity_type` | string | Activity pattern (annual, variable, etc.) |
| `sol_lon_begin_deg` | float64 | Solar longitude at activity start (deg) |
| `sol_lon_end_deg` | float64 | Solar longitude at activity end (deg) |
| `sol_lon_peak_deg` | float64 | Solar longitude at peak (deg) |
| `ra_deg` | float64 | Right ascension of radiant (deg, J2000) |
| `dec_deg` | float64 | Declination of radiant (deg, J2000) |
| `ra_daily_motion` | float64 | Daily motion in RA (deg/day) |
| `dec_daily_motion` | float64 | Daily motion in Dec (deg/day) |
| `geocentric_velocity_kms` | float64 | Geocentric velocity (km/s) |
| `sun_centered_ecliptic_lon_deg` | float64 | Sun-centered ecliptic longitude of radiant (deg) |
| `sun_centered_ecliptic_lat_deg` | float64 | Sun-centered ecliptic latitude of radiant (deg) |
| `ecliptic_lat_deg` | float64 | Ecliptic latitude of radiant (deg) |
| `theta_deg` | float64 | Angular distance parameter theta (deg) |
| `phi_deg` | float64 | Angular distance parameter phi (deg) |
| `flags` | string | Data quality/validation flags |
| `semi_major_axis_au` | float64 | Orbital semi-major axis (AU) |
| `perihelion_distance_au` | float64 | Perihelion distance (AU) |
| `eccentricity` | float64 | Orbital eccentricity |
| `arg_perihelion_deg` | float64 | Argument of perihelion (deg) |
| `ascending_node_deg` | float64 | Longitude of ascending node (deg) |
| `inclination_deg` | float64 | Orbital inclination (deg) |
| `n_meteors` | int32 | Number of meteors in the analysis |
| `group_no` | int32 | Shower group number |
| `cg` | string | Shower complex/group code |
| `parent_body` | string | Identified parent body (comet or asteroid) |
| `remarks` | string | Additional notes |
| `ote` | string | OTE classification flag |
| `references` | string | Literature reference |

## Quick stats

- **{len(df):,}** records across **{n_unique:,}** unique showers
- **{n_established}** IAU-established showers
- **{n_with_parent:,}** records with identified parent body

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/iau-meteor-showers", split="train")
df = ds.to_pandas()

# All established showers (primary record only)
established = df[(df["is_established"] == True) & (df["ad_no"] == 0)]

# Major annual showers sorted by geocentric velocity
majors = established[established["activity_type"] == "annual"].sort_values(
    "geocentric_velocity_kms", ascending=False
)

# Showers with known parent bodies
with_parent = df[df["parent_body"].notna()][["shower_name", "parent_body", "iau_no"]].drop_duplicates("iau_no")

# Orbital elements of the Perseids (all analyses)
perseids = df[df["code"] == "PER"][["references", "semi_major_axis_au", "eccentricity", "inclination_deg"]]
```

## Data source

[IAU Meteor Data Center](https://www.ta3.sk/IAUC22DB/MDC2022/),
maintained by the IAU Commission F1 (Meteors, Meteoroids and Interplanetary Dust).
Reference: Jopek T.J., Kanamori T., "IAU Meteor Data Center — the shower database"
(Planetary and Space Science, 2019).

## Update schedule

Static dataset — rebuilt manually when the IAU MDC publishes annual updates.

## Related datasets

- [neo-close-approaches](https://huggingface.co/datasets/juliensimon/neo-close-approaches) — Near-Earth object close approaches from NASA JPL
- [fireball-events](https://huggingface.co/datasets/juliensimon/fireball-events) — NASA/JPL fireball and bolide events

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/iau-meteor-showers) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{iau_meteor_showers,
  author = {{Simon, Julien}},
  title = {{IAU Meteor Shower Database}},
  year = {{{YEAR}}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/iau-meteor-showers}},
  note = {{Based on IAU Meteor Data Center shower database, maintained by IAU Commission F1}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update IAU meteor showers: {len(df):,} records, {n_unique:,} showers"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    # Emit row count for CI
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={len(df)}\n")

    print(f"Done. {len(df):,} rows uploaded.")


if __name__ == "__main__":
    main()
