#!/usr/bin/env python3
"""Fetch solar radio burst events from HEASARC and upload to HF."""

import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset


TAP_URL = "https://heasarc.gsfc.nasa.gov/xamin/vo/tap/sync"
HF_REPO = "juliensimon/solar-radio-bursts"

ADQL = "SELECT * FROM solarburst ORDER BY start_date"


def fetch_catalog() -> pd.DataFrame:
    """Try CSV first, fall back to JSON, then pipe-delimited text."""
    # Attempt 1: CSV
    print("Fetching solar radio bursts from HEASARC (CSV)...")
    resp = requests.get(TAP_URL, params={
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": ADQL,
    }, timeout=120)
    resp.raise_for_status()

    if not resp.text.strip().startswith("<?xml"):
        try:
            df = pd.read_csv(io.StringIO(resp.text))
            if len(df) > 100:
                print(f"  CSV parse OK: {len(df):,} rows")
                return df
        except Exception as e:
            print(f"  CSV parse failed: {e}")
    else:
        print("  CSV not supported (got XML/VOTable response)")

    # Attempt 2: JSON
    print("Retrying with FORMAT=json...")
    resp = requests.get(TAP_URL, params={
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "json", "QUERY": ADQL,
    }, timeout=120)
    resp.raise_for_status()

    try:
        data = resp.json()
        if "data" in data and "metadata" in data:
            cols = [m["name"] for m in data["metadata"]]
            df = pd.DataFrame(data["data"], columns=cols)
        else:
            df = pd.DataFrame(data)
        if len(df) > 100:
            print(f"  JSON parse OK: {len(df):,} rows")
            return df
    except Exception as e:
        print(f"  JSON parse failed: {e}")

    # Attempt 3: pipe-delimited text
    print("Retrying with FORMAT=text...")
    resp = requests.get(TAP_URL, params={
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "text", "QUERY": ADQL,
    }, timeout=120)
    resp.raise_for_status()

    lines = [l for l in resp.text.strip().splitlines() if l.strip() and not l.startswith("-")]
    if len(lines) >= 2:
        header = [c.strip() for c in lines[0].split("|")]
        rows = []
        for line in lines[1:]:
            rows.append([c.strip() for c in line.split("|")])
        df = pd.DataFrame(rows, columns=header)
        df = df.loc[:, df.columns != ""]
        print(f"  Text parse OK: {len(df):,} rows")
        return df

    print("::error::All fetch formats failed")
    sys.exit(1)


def main():
    df = fetch_catalog()

    # Convert numerics where appropriate
    for col in ["start_date", "end_date", "frequency", "intensity"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Clean string columns
    for col in ["type", "observatory", "source_name"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
            )

    # Sort by start_date if available
    if "start_date" in df.columns:
        df = df.sort_values("start_date").reset_index(drop=True)

    print(f"  {len(df):,} solar radio burst events")

    check_dataset(df, "solar-radio", min_rows=5000,
        expected_columns=["start_date", "frequency", "type"],
        critical_columns=["start_date"])

    # Stats for README
    n_total = len(df)
    n_types = int(df["type"].nunique()) if "type" in df.columns else 0
    top_types = df["type"].value_counts().head(5) if "type" in df.columns else pd.Series()
    top_types_str = ", ".join(f"{t} ({c:,})" for t, c in top_types.items())

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "solar_radio_bursts.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Solar Radio Burst Events"
language:
  - en
description: "Catalog of solar radio burst events (Type II, III, IV, V) from NOAA NCEI via HEASARC. Updated weekly."
task_categories:
  - tabular-classification
tags:
  - space
  - solar
  - radio-burst
  - type-ii
  - type-iii
  - space-weather
  - open-data
size_categories:
  - 1K<n<100K
---

# Solar Radio Burst Events

![Update Solar Radio](https://github.com/juliensimon/space-datasets/actions/workflows/update-solar-radio.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.solar-radio&label=updated&color=brightgreen)

Catalog of solar radio burst events, currently **{n_total:,}** events. Solar radio bursts
are intense bursts of radio emission from the Sun, classified into types (I through V)
based on their spectral characteristics and physical origin.

## Dataset description

Solar radio bursts are produced by energetic electrons accelerated during solar flares
and coronal mass ejections. They are important indicators of space weather activity:

- **Type II** bursts: slow-drifting, associated with CME-driven shocks
- **Type III** bursts: fast-drifting, caused by electron beams along open field lines
- **Type IV** bursts: broadband continuum, associated with post-flare loops
- **Type V** bursts: short-duration continuum following Type III

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `start_date` | float64 | Event start time |
| `end_date` | float64 | Event end time |
| `frequency` | float64 | Observation frequency |
| `intensity` | float64 | Burst intensity |
| `type` | string | Burst type classification (II, III, IV, V) |

Additional columns from the HEASARC catalog are included.

## Quick stats

- **{n_total:,}** radio burst events
- **{n_types}** burst type classifications
- Top types: {top_types_str}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/solar-radio-bursts", split="train")
df = ds.to_pandas()

# Type III bursts (most common)
type_iii = df[df["type"].str.contains("III", na=False)]
print(f"{{len(type_iii):,}} Type III bursts")

# Burst type distribution
print(df["type"].value_counts())
```

## Data source

NOAA National Centers for Environmental Information (NCEI) solar radio burst catalog,
accessed via [NASA HEASARC](https://heasarc.gsfc.nasa.gov/) TAP service.

## Update schedule

Weekly (Monday at 19:00 UTC) via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [solar-flare-index](https://huggingface.co/datasets/juliensimon/solar-flare-index) -- Solar flare observations
- [donki](https://huggingface.co/datasets/juliensimon/donki) -- NASA DONKI space weather events

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Citation

```bibtex
@dataset{{solar_radio_bursts,
  author = {{Simon, Julien}},
  title = {{Solar Radio Burst Events}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/solar-radio-bursts}},
  note = {{Based on NOAA NCEI solar radio burst catalog via NASA HEASARC}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update solar radio bursts: {n_total:,} events"
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
