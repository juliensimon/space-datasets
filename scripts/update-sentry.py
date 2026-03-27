#!/usr/bin/env python3
"""Fetch Sentry impact risk data from NASA JPL CNEOS and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from jpl_api import jpl_query
from validate import check_dataset


HF_REPO = "juliensimon/sentry-impact-risk"


def main():
    print("Fetching Sentry impact risk data from NASA JPL CNEOS...")
    payload = jpl_query("sentry.api")

    df = pd.DataFrame(payload["data"])
    print(f"  {len(df):,} objects")

    # Rename columns to snake_case
    df = df.rename(columns={
        "des": "designation",
        "fullname": "full_name",
        "ip": "impact_probability",
        "ps_cum": "palermo_scale_cum",
        "ps_max": "palermo_scale_max",
        "ts_max": "torino_scale",
        "n_imp": "n_potential_impacts",
        "last_obs": "last_observation",
        "last_obs_jd": "last_observation_jd",
        "diameter": "diameter_km",
        "h": "absolute_magnitude",
        "v_inf": "v_infinity_kms",
    })

    # Parse range field (e.g. "2029-2113") into year_range_min / year_range_max
    if "range" in df.columns:
        range_split = df["range"].str.split("-", n=1, expand=True)
        df["year_range_min"] = pd.to_numeric(range_split[0], errors="coerce").astype("Int64")
        df["year_range_max"] = pd.to_numeric(range_split[1], errors="coerce").astype("Int64")
        df = df.drop(columns=["range"])

    # Type conversions
    for col in ["impact_probability", "palermo_scale_cum", "palermo_scale_max",
                "torino_scale", "n_potential_impacts", "diameter_km",
                "absolute_magnitude", "v_infinity_kms", "last_observation_jd"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "last_observation" in df.columns:
        df["last_observation"] = pd.to_datetime(df["last_observation"], errors="coerce")

    df = df.sort_values("palermo_scale_cum", ascending=False).reset_index(drop=True)

    check_dataset(df, "sentry", min_rows=100,
                  expected_columns=["designation", "impact_probability",
                                    "palermo_scale_cum", "torino_scale"],
                  critical_columns=["designation", "impact_probability"])

    # Stats for README
    n = len(df)
    max_palermo = df["palermo_scale_cum"].max()
    max_torino = int(df["torino_scale"].max())
    closest_year = int(df["year_range_min"].min()) if "year_range_min" in df.columns else "N/A"
    highest_ip = df.loc[df["impact_probability"].idxmax()]

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "sentry_impact_risk.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_kb = out.stat().st_size / 1024
        print(f"  {size_kb:.0f} KB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "NASA Sentry: Earth Impact Risk Assessment"
language:
  - en
description: >-
  Near-Earth objects with non-zero Earth impact probability from NASA JPL
  Sentry system. Updated daily.
size_categories:
  - n<1K
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - asteroid
  - impact
  - sentry
  - planetary-defense
  - nasa
  - near-earth-object
  - open-data
  - tabular-data
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/sentry_impact_risk.parquet
---

# NASA Sentry: Earth Impact Risk Assessment

*Part of the [Orbital Mechanics Datasets](https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994) collection on Hugging Face.*

![Update Sentry](https://github.com/juliensimon/space-datasets/actions/workflows/update-sentry.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.sentry&label=updated&color=brightgreen)

Near-Earth objects with non-zero Earth impact probability, as assessed by NASA's
Sentry impact monitoring system. Currently **{n:,}** objects under watch.

## Dataset description

The Sentry system, operated by NASA's Center for Near-Earth Object Studies (CNEOS)
at the Jet Propulsion Laboratory, continuously monitors the most current asteroid
catalog for possibilities of future Earth impact. Objects are listed when their
orbits bring them close enough that an impact cannot be ruled out.

Each record includes the cumulative and maximum Palermo Scale rating (a logarithmic
measure comparing the impact probability to the background risk), the Torino Scale
rating (an integer 0-10 for public communication), the number of potential impact
scenarios, estimated diameter, and the year range of possible impacts.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `designation` | string | Primary designation (e.g. "29075", "2024 YR4") |
| `full_name` | string | Full formatted name |
| `impact_probability` | float64 | Cumulative impact probability |
| `palermo_scale_cum` | float64 | Cumulative Palermo Scale value |
| `palermo_scale_max` | float64 | Maximum Palermo Scale value (single event) |
| `torino_scale` | float64 | Maximum Torino Scale value (0-10) |
| `n_potential_impacts` | float64 | Number of potential impact scenarios |
| `year_range_min` | Int64 | Earliest year of potential impact |
| `year_range_max` | Int64 | Latest year of potential impact |
| `last_observation` | datetime | Date of last astrometric observation |
| `last_observation_jd` | float64 | Last observation (Julian Date) |
| `diameter_km` | float64 | Estimated diameter (km) |
| `absolute_magnitude` | float64 | Absolute magnitude H |
| `v_infinity_kms` | float64 | V-infinity at impact (km/s) |

## Quick stats

- **{n:,}** objects with non-zero impact probability
- Highest cumulative Palermo Scale: **{max_palermo:.2f}**
- Maximum Torino Scale: **{max_torino}**
- Closest potential impact year: **{closest_year}**
- Highest impact probability: **{highest_ip['designation']}** ({highest_ip['impact_probability']:.2e})

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/sentry-impact-risk", split="train")
df = ds.to_pandas()

# Objects ranked by Palermo Scale (most hazardous first)
print(df[["designation", "palermo_scale_cum", "torino_scale",
          "impact_probability", "diameter_km"]].head(10))

# Objects with Torino Scale > 0
elevated = df[df["torino_scale"] > 0]
print(f"{{len(elevated)}} objects with elevated Torino Scale")

# Large objects (> 100m) with upcoming potential impacts
large = df[(df["diameter_km"] > 0.1) & (df["year_range_min"] <= 2050)]
print(large[["designation", "diameter_km", "year_range_min", "impact_probability"]])
```

## Data source

[NASA JPL Center for Near Earth Object Studies (CNEOS) Sentry System](https://cneos.jpl.nasa.gov/sentry/).
Impact probabilities are continuously refined as new astrometric observations
improve orbit solutions.

## Update schedule

Daily at 11:00 UTC via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [neo-close-approaches](https://huggingface.co/datasets/juliensimon/neo-close-approaches) -- NEO close approaches to Earth
- [fireball-bolide-events](https://huggingface.co/datasets/juliensimon/fireball-bolide-events) -- Fireball/bolide atmospheric impacts

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/sentry-impact-risk) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{sentry_impact_risk,
  author = {{Simon, Julien}},
  title = {{NASA Sentry: Earth Impact Risk Assessment}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/sentry-impact-risk}},
  note = {{Based on NASA/JPL Center for Near Earth Object Studies (CNEOS) Sentry system data}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update Sentry impact risk: {n:,} objects"
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
