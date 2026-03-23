#!/usr/bin/env python3
"""Fetch NORAD SATCAT from CelesTrak and upload to HF."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

from validate import check_dataset


SATCAT_URL = "https://celestrak.org/pub/satcat.csv"
HF_REPO = "juliensimon/space-track-satcat"


def main():
    print("Fetching SATCAT from CelesTrak...")
    df = pd.read_csv(SATCAT_URL)
    print(f"  {len(df):,} objects")

    # Clean up types
    df["LAUNCH_DATE"] = pd.to_datetime(df["LAUNCH_DATE"], errors="coerce")
    df["DECAY_DATE"] = pd.to_datetime(df["DECAY_DATE"], errors="coerce")
    df["NORAD_CAT_ID"] = df["NORAD_CAT_ID"].astype("int32")
    df["RCS"] = pd.to_numeric(df["RCS"], errors="coerce")

    # Rename for consistency
    df = df.rename(columns={
        "OBJECT_NAME": "object_name",
        "OBJECT_ID": "intl_designator",
        "NORAD_CAT_ID": "norad_id",
        "OBJECT_TYPE": "object_type",
        "OPS_STATUS_CODE": "ops_status",
        "OWNER": "owner",
        "LAUNCH_DATE": "launch_date",
        "LAUNCH_SITE": "launch_site",
        "DECAY_DATE": "decay_date",
        "PERIOD": "period_min",
        "INCLINATION": "inclination",
        "APOGEE": "apogee_km",
        "PERIGEE": "perigee_km",
        "RCS": "rcs_m2",
        "DATA_STATUS_CODE": "data_status",
        "ORBIT_CENTER": "orbit_center",
        "ORBIT_TYPE": "orbit_type",
    })

    check_dataset(df, "satcat", min_rows=60000,
        expected_columns=["object_name", "norad_id", "object_type", "launch_date",
                          "inclination", "apogee_km", "perigee_km"],
        critical_columns=["norad_id", "object_name"])

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "satcat.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        # Compute stats for README
        n_payload = int((df["object_type"] == "PAY").sum())
        n_debris = int((df["object_type"] == "DEB").sum())
        n_rocket = int((df["object_type"] == "R/B").sum())
        n_active = int(df["ops_status"].isin(["+", "P", "B", "S", "X"]).sum())
        n_decayed = int(df["decay_date"].notna().sum())
        n_owners = df["owner"].nunique()

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
task_categories:
  - tabular-classification
tags:
  - space
  - satellite
  - norad
  - celestrak
  - orbital-mechanics
size_categories:
  - 10K<n<100K
---

# NORAD Satellite Catalog (SATCAT)

![Update SATCAT](https://github.com/juliensimon/space-datasets/actions/workflows/update-satcat.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.satcat&label=updated&color=brightgreen)

Complete NORAD Satellite Catalog from [CelesTrak](https://celestrak.org/), tracking every
object cataloged by the 18th Space Defense Squadron since 1957. Currently **{len(df):,}**
objects ({n_payload:,} payloads, {n_debris:,} debris, {n_rocket:,} rocket bodies).

## Dataset description

The SATCAT (Satellite Catalog) is the authoritative registry of all artificial objects
in Earth orbit and beyond — active satellites, defunct spacecraft, rocket bodies, and
debris. Each entry includes launch metadata, orbital parameters, operational status,
and physical characteristics. This dataset mirrors the full catalog daily from CelesTrak.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `object_name` | string | Official name (e.g. "STARLINK-1234", "ISS (ZARYA)") |
| `intl_designator` | string | International designator / COSPAR ID (e.g. "2024-123A") |
| `norad_id` | int32 | NORAD catalog number (unique identifier) |
| `object_type` | string | `PAY` (payload), `R/B` (rocket body), `DEB` (debris), `UNK` (unknown) |
| `ops_status` | string | Operational status code (see below) |
| `owner` | string | Owner/operator country or organization code |
| `launch_date` | datetime | Launch date (UTC) |
| `launch_site` | string | Launch site code (e.g. "AFETR", "TYMSC") |
| `decay_date` | datetime | Reentry/decay date, if applicable |
| `period_min` | float | Orbital period in minutes |
| `inclination` | float | Orbital inclination in degrees |
| `apogee_km` | float | Apogee altitude in km |
| `perigee_km` | float | Perigee altitude in km |
| `rcs_m2` | float | Radar cross-section in m² |
| `data_status` | string | Data quality/status flag |
| `orbit_center` | string | Central body (e.g. "EA" for Earth) |
| `orbit_type` | string | Orbit classification |

### Operational status codes

| Code | Meaning |
|------|---------|
| `+` | Operational |
| `-` | Non-operational |
| `P` | Partially operational |
| `B` | Backup/standby |
| `S` | Spare |
| `X` | Extended mission |
| `D` | Decayed |
| `?` | Unknown |

## Quick stats

- **{len(df):,}** cataloged objects
- **{n_payload:,}** payloads, **{n_debris:,}** debris fragments, **{n_rocket:,}** rocket bodies
- **{n_decayed:,}** objects have decayed/reentered
- **{n_owners}** distinct owner codes

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/space-track-satcat", split="train")
df = ds.to_pandas()

# Active payloads only
active = df[(df["object_type"] == "PAY") & (df["ops_status"] == "+")]
print(f"{{len(active):,}} active payloads")

# Launches per year
df["year"] = df["launch_date"].dt.year
launches_by_year = df.groupby("year")["norad_id"].count()

# Objects by owner
top_owners = df["owner"].value_counts().head(10)

# LEO vs GEO
leo = df[(df["perigee_km"] < 2000) & (df["perigee_km"] > 0)]
geo = df[(df["perigee_km"] > 35000) & (df["apogee_km"] < 36500)]
```

## Data source

All data comes from [CelesTrak](https://celestrak.org/pub/satcat.csv), which mirrors
the official US Space Command SATCAT. CelesTrak is maintained by Dr. T.S. Kelso and
is the standard public source for space situational awareness data.

## Update schedule

Daily at 06:00 UTC via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [starlink-fleet-data](https://huggingface.co/datasets/juliensimon/starlink-fleet-data) — Daily Starlink constellation health snapshots
- [space-launch-log](https://huggingface.co/datasets/juliensimon/space-launch-log) — Global launch history from GCAT
- [starlink-ground-stations](https://huggingface.co/datasets/juliensimon/starlink-ground-stations) — Starlink gateway and PoP locations

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Citation

```bibtex
@dataset{{space_track_satcat,
  author = {{Simon, Julien}},
  title = {{NORAD Satellite Catalog (SATCAT)}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/space-track-satcat}},
  note = {{Based on NORAD/18th Space Defense Squadron data via CelesTrak (Dr. T.S. Kelso)}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update SATCAT: {len(df):,} objects"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={len(df)}\n")
    print("Done.")


if __name__ == "__main__":
    main()
