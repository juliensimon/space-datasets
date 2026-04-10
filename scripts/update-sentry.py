#!/usr/bin/env python3
"""Fetch Sentry impact risk data from NASA JPL CNEOS and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from jpl_api import jpl_query
from dataset_images import banner_markdown, download_banner
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

        banner_file = download_banner("sentry", tmp)
        banner_md = banner_markdown("sentry", banner_file)

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
  - parquet
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/sentry_impact_risk.parquet
---

# NASA Sentry: Earth Impact Risk Assessment
{banner_md}
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

The Sentry system works by propagating each asteroid's orbit forward in time while sampling the uncertainty region -- the cloud of possible positions and velocities consistent with the available observations. When any of these virtual asteroids pass close enough to Earth that an impact geometry exists, it registers as a potential impact event. The cumulative impact probability is the fraction of all sampled orbits that result in a collision, typically an extremely small number (most entries are below 1 in 10 million). Objects routinely enter and leave the Sentry watchlist as new observations refine their orbits: additional astrometry usually shrinks the uncertainty region enough to exclude all impact trajectories, removing the object from the list entirely.

The Palermo Scale provides the key metric for assessing whether an impact scenario merits attention. It is defined as the logarithm of the ratio between the calculated impact probability and the background impact frequency for objects of similar energy. A Palermo Scale value of 0 means the event is exactly as likely as the average random impact risk; negative values (the vast majority) indicate risk below the background level. Only a Palermo Scale above -2 is generally considered noteworthy by the planetary defense community. The Torino Scale, by contrast, is designed for public communication: it combines impact probability and kinetic energy into a single integer from 0 (no hazard) to 10 (certain collision, globally catastrophic). Historically, only a handful of objects have ever briefly exceeded Torino 1.

Understanding this dataset requires appreciating that the presence of an object on the Sentry list does not mean an impact is expected -- it means an impact cannot yet be ruled out. The most common outcome, by far, is that follow-up observations eliminate the risk entirely. The dataset therefore captures a snapshot of current orbital uncertainty as much as it captures genuine hazard, making it valuable for studying how observation quality, data arc length, and orbit determination methods affect impact probability assessments.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `designation` | string | Asteroid designation: either a permanent number (e.g. "29075") for numbered asteroids, or a provisional MPC designation (e.g. "2024 YR4") for unnumbered ones |
| `full_name` | string | Full formatted name combining number (if assigned) and provisional designation or name (e.g. "29075 (1950 DA)", "2024 YR4") |
| `impact_probability` | float64 | Total cumulative probability of at least one Earth impact across all monitored years, summed over all virtual impactor solutions; typically 10⁻⁷ to 10⁻¹; the vast majority of entries are below 1 in 10,000 |
| `palermo_scale_cum` | float64 | Cumulative Palermo Scale: logarithm of the ratio of cumulative impact probability to the background impact frequency for objects of equivalent energy; PS=0 equals background risk; PS>-2 merits attention by planetary defense community; dataset is sorted by this column descending |
| `palermo_scale_max` | float64 | Maximum Palermo Scale over any single impact solution in the monitored time window; less conservative than the cumulative value; useful for identifying the single most hazardous potential impact date |
| `torino_scale` | float64 | Maximum Torino Scale integer (0–10) across all impact solutions; public communication metric combining probability and kinetic energy: 0 = no hazard, 1 = routine monitoring, 4–7 = threatening, 10 = certain global catastrophe; historically only a few objects have briefly exceeded 1 |
| `n_potential_impacts` | float64 | Count of distinct impact geometries (virtual impactors) identified by Sentry's orbital sampling; a larger number reflects broader orbital uncertainty, not necessarily higher probability |
| `year_range_min` | Int64 | Earliest calendar year in which an impact solution exists; the first year where the object's uncertain orbit intersects Earth's orbit |
| `year_range_max` | Int64 | Latest calendar year in which an impact solution exists; Sentry monitors orbits forward up to ~100 years |
| `last_observation` | datetime | UTC date of the most recent astrometric observation incorporated into the orbit solution; more recent observations typically reduce impact probability |
| `last_observation_jd` | float64 | Same as `last_observation` expressed as a Julian Date (TDB timescale) |
| `diameter_km` | float64 | Estimated diameter in km derived from absolute magnitude assuming a geometric albedo of 0.154; null if H is unavailable; range in this table is typically 0.01–10 km |
| `absolute_magnitude` | float64 | Absolute magnitude H; proxy for size: H=18 ≈ 1 km, H=22 ≈ 140 m, H=25 ≈ 40 m; actual diameter depends on unknown albedo; null for some objects |
| `v_infinity_kms` | float64 | Hyperbolic excess speed (v∞) at Earth encounter in km/s; combined with Earth's gravity well this yields the actual impact speed (typically 11–30 km/s); determines kinetic energy: higher v∞ means more destructive impact for the same mass |

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
