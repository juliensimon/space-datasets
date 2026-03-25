#!/usr/bin/env python3
"""Fetch Corlett (2020) astronaut database from Mendeley and upload to HF."""

import io
import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset


HF_REPO = "juliensimon/astronaut-database"

MENDELEY_URL = "https://data.mendeley.com/public-files/datasets/86tsnnbv2w/files/2a4f0c9c-906e-4b0e-82a0-26886c6bbf62/file_downloaded"


def main():
    print("Fetching astronaut database from Mendeley...")

    resp = requests.get(MENDELEY_URL, timeout=60)
    resp.raise_for_status()

    df = pd.read_csv(io.StringIO(resp.text))
    print(f"  {len(df):,} astronaut records")

    # Rename columns to snake_case
    known_renames = {
        "Name": "name",
        "Nationality": "nationality",
        "Sex": "sex",
        "Year of Birth": "birth_year",
        "Year of Selection": "selection_year",
        "Mission": "mission",
        "Year of Mission": "mission_year",
        "Selection Group": "selection_group",
        "Status": "status",
    }
    rename_map = {k: v for k, v in known_renames.items() if k in df.columns}
    if rename_map:
        df = df.rename(columns=rename_map)

    # Convert numerics
    for col in ["birth_year", "selection_year", "mission_year"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Clean string columns
    for col in ["name", "nationality", "sex", "mission", "selection_group", "status"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
            )

    df = df.sort_values("name").reset_index(drop=True)

    check_dataset(df, "astronauts", min_rows=400,
                  expected_columns=["name", "nationality"],
                  critical_columns=["name", "nationality"])

    # Stats for README
    n = len(df)
    n_unique = int(df["name"].nunique()) if "name" in df.columns else n
    n_nationalities = int(df["nationality"].nunique()) if "nationality" in df.columns else 0
    top_nations = df["nationality"].value_counts().head(5) if "nationality" in df.columns else pd.Series()
    top_nations_str = ", ".join(f"{nat} ({cnt:,})" for nat, cnt in top_nations.items())
    n_female = int((df["sex"] == "Female").sum()) if "sex" in df.columns else 0
    n_male = int((df["sex"] == "Male").sum()) if "sex" in df.columns else 0
    year_min = int(df["mission_year"].min()) if "mission_year" in df.columns else 0
    year_max = int(df["mission_year"].max()) if "mission_year" in df.columns else 0

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "astronauts.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_kb = out.stat().st_size / 1024
        print(f"  {size_kb:.0f} KB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Astronaut Database"
language:
  - en
description: >-
  Complete astronaut database — every person who has been to space.
  {n_unique:,} unique astronauts from {n_nationalities} countries,
  {year_min} to {year_max}.
size_categories:
  - n<1K
task_categories:
  - tabular-classification
tags:
  - space
  - astronaut
  - human-spaceflight
  - missions
  - open-data
  - tabular-data
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/astronauts.parquet
---

# Astronaut Database

*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

Complete database of every person who has been to space — **{n:,}** records covering
**{n_unique:,}** astronauts from **{n_nationalities}** countries, with missions
spanning **{year_min}** to **{year_max}**.

## Dataset description

This dataset contains the comprehensive astronaut database compiled by Corlett (2020),
covering every person who has traveled to space. Each record includes the astronaut's
name, nationality, sex, birth year, selection year and group, mission name, mission year,
and current status. Multiple missions by the same astronaut appear as separate records.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `name` | string | Astronaut name |
| `nationality` | string | Nationality |
| `sex` | string | Sex (Male/Female) |
| `birth_year` | float64 | Year of birth |
| `selection_year` | float64 | Year of selection as astronaut |
| `mission` | string | Mission name |
| `mission_year` | float64 | Year of mission |
| `selection_group` | string | Selection group |
| `status` | string | Current status |

## Quick stats

- **{n:,}** records ({n_unique:,} unique astronauts)
- **{n_nationalities}** nationalities
- **{n_male:,}** male, **{n_female:,}** female
- Missions from **{year_min}** to **{year_max}**
- Top nationalities: {top_nations_str}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/astronaut-database", split="train")
df = ds.to_pandas()

# Astronauts by nationality
print(df["nationality"].value_counts().head(10))

# Female astronauts over time
female = df[df["sex"] == "Female"]
print(f"{{len(female):,}} missions by female astronauts")
print(female.groupby("mission_year").size().tail(10))

# Most-flown astronauts
flights = df.groupby("name").size().sort_values(ascending=False)
print(flights.head(10))
```

## Data source

Corlett, T. (2020). Astronaut database. Mendeley Data, V1,
[doi:10.17632/86tsnnbv2w](https://doi.org/10.17632/86tsnnbv2w).

## Related datasets

- [launch-log](https://huggingface.co/datasets/juliensimon/launch-log) -- McDowell launch log
- [satcat](https://huggingface.co/datasets/juliensimon/satcat) -- Satellite catalog

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Citation

```bibtex
@dataset{{astronaut_database,
  author = {{Simon, Julien}},
  title = {{Astronaut Database}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/astronaut-database}},
  note = {{Based on Corlett (2020), Mendeley Data, doi:10.17632/86tsnnbv2w}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update astronaut database: {n:,} records"
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
