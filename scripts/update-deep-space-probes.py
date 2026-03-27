#!/usr/bin/env python3
"""Fetch merged hourly data for Voyager 1/2 and Pioneer 10/11 from NASA SPDF and upload to HF."""

import datetime
import os
import subprocess
import tempfile
import time
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset

CURRENT_YEAR = datetime.date.today().year

HF_REPO = "juliensimon/deep-space-probes"

BASE = "https://spdf.gsfc.nasa.gov/pub/data"
SOURCES = {
    "voyager_1": {
        "url": f"{BASE}/voyager/voyager1/merged/",
        "pattern": "vy1_{year}.asc",
        "years": range(1977, CURRENT_YEAR + 1),
        "columns": [
            "year", "day_of_year", "hour",
            "heliocentric_distance_au", "hgi_latitude_deg", "hgi_longitude_deg",
            "b_magnitude_avg_nt", "b_magnitude_nt",
            "br_rtn_nt", "bt_rtn_nt", "bn_rtn_nt",
            "flow_speed_kms", "flow_elevation_deg", "flow_azimuth_deg",
            "proton_density_cm3", "proton_temperature_k",
            "flux_h_lecp_0p57_1p78_mev", "flux_h_lecp_3p40_17p6_mev",
            "flux_h_lecp_22p0_31p0_mev",
            "flux_h_crs_3p0_4p6_mev", "flux_h_crs_4p6_6p2_mev",
            "flux_h_crs_6p2_7p7_mev", "flux_h_crs_7p7_12p8_mev",
            "flux_h_crs_12p8_17p9_mev", "flux_h_crs_17p9_30p0_mev",
            "flux_h_crs_30p0_48p0_mev", "flux_h_crs_48p0_56p0_mev",
            "flux_h_crs_74p5_83p7_mev", "flux_h_crs_132p8_154p9_mev",
            "flux_h_crs_154p9_174p9_mev", "flux_h_crs_174p9_187p7_mev",
            "flux_h_crs_187p7_220p5_mev", "flux_h_crs_220p5_270p1_mev",
            "flux_h_crs_270p1_346p0_mev",
        ],
        "fill_values": {
            "heliocentric_distance_au": 999.99,
            "hgi_latitude_deg": 9999.9,
            "hgi_longitude_deg": 9999.9,
            "b_magnitude_avg_nt": 999.999,
            "b_magnitude_nt": 999.999,
            "br_rtn_nt": 999.999,
            "bt_rtn_nt": 999.999,
            "bn_rtn_nt": 999.999,
            "flow_speed_kms": 9999.9,
            "flow_elevation_deg": 9999.9,
            "flow_azimuth_deg": 9999.9,
            "proton_density_cm3": 99.99999,
            "proton_temperature_k": 9999999.0,
        },
        "flux_fill_threshold": 9.9e4,
    },
    "voyager_2": {
        "url": f"{BASE}/voyager/voyager2/merged/",
        "pattern": "vy2_{year}.asc",
        "years": range(1977, CURRENT_YEAR + 1),
        "columns": [
            "year", "day_of_year", "hour",
            "heliocentric_distance_au", "hgi_latitude_deg", "hgi_longitude_deg",
            "b_magnitude_avg_nt", "b_magnitude_nt",
            "br_rtn_nt", "bt_rtn_nt", "bn_rtn_nt",
            "flow_speed_kms", "flow_elevation_deg", "flow_azimuth_deg",
            "proton_density_cm3", "proton_temperature_k",
            "flux_h_lecp_0p52_1p45_mev", "flux_h_lecp_3p04_17p3_mev",
            "flux_h_lecp_22p0_30p0_mev",
            "flux_h_crs_3p0_4p6_mev", "flux_h_crs_4p6_6p2_mev",
            "flux_h_crs_6p2_7p7_mev", "flux_h_crs_7p7_12p8_mev",
            "flux_h_crs_12p8_17p9_mev", "flux_h_crs_17p9_30p0_mev",
            "flux_h_crs_30p0_48p0_mev", "flux_h_crs_48p0_56p0_mev",
            "flux_h_crs_75p9_82p6_mev", "flux_h_crs_130p3_154p2_mev",
            "flux_h_crs_154p2_171p3_mev", "flux_h_crs_171p3_193p6_mev",
            "flux_h_crs_193p6_208p2_mev", "flux_h_crs_208p2_245p7_mev",
            "flux_h_crs_245p7_272p3_mev", "flux_h_crs_272p3_344p0_mev",
            "flux_h_crs_344p0_478p6_mev", "flux_h_crs_478p6_598p7_mev",
        ],
        "fill_values": {
            "heliocentric_distance_au": 999.99,
            "hgi_latitude_deg": 9999.9,
            "hgi_longitude_deg": 9999.9,
            "b_magnitude_avg_nt": 999.999,
            "b_magnitude_nt": 999.999,
            "br_rtn_nt": 999.999,
            "bt_rtn_nt": 999.999,
            "bn_rtn_nt": 999.999,
            "flow_speed_kms": 9999.9,
            "flow_elevation_deg": 9999.9,
            "flow_azimuth_deg": 9999.9,
            "proton_density_cm3": 99.99999,
            "proton_temperature_k": 9999999.0,
        },
        "flux_fill_threshold": 9.9e4,
    },
    "pioneer_10": {
        "url": f"{BASE}/pioneer/pioneer10/merged/coho1hr_magplasma_ascii/",
        "pattern": "p10_{year}.asc",
        "years": range(1972, 1996),
        "columns": [
            "year", "day_of_year", "hour",
            "heliocentric_distance_au", "hgi_latitude_deg", "hgi_longitude_deg",
            "br_rtn_nt", "bt_rtn_nt", "bn_rtn_nt", "b_magnitude_nt",
            "flow_speed_kms", "flow_elevation_deg", "flow_azimuth_deg",
            "proton_density_cm3", "proton_temperature_k",
            "flux_h_crt_3p45_5p15_mev", "flux_h_crt_30p55_56p47_mev",
            "flux_h_crt_120p7_227p3_mev",
        ],
        "fill_values": {
            "heliocentric_distance_au": 999.99,
            "hgi_latitude_deg": 9999.9,
            "hgi_longitude_deg": 9999.9,
            "br_rtn_nt": 999.9999,
            "bt_rtn_nt": 999.9999,
            "bn_rtn_nt": 999.9999,
            "b_magnitude_nt": 999.9999,
            "flow_speed_kms": 9999.9,
            "flow_elevation_deg": 9999.9,
            "flow_azimuth_deg": 9999.9,
            "proton_density_cm3": 999.9999,
            "proton_temperature_k": 9999999.0,
        },
        "flux_fill_threshold": 9.9e6,
    },
    "pioneer_11": {
        "url": f"{BASE}/pioneer/pioneer11/merged/coho1hr_magplasma_ascii/",
        "pattern": "p11_{year}.asc",
        "years": range(1973, 1995),
        "columns": [
            "year", "day_of_year", "hour",
            "heliocentric_distance_au", "hgi_latitude_deg", "hgi_longitude_deg",
            "br_rtn_nt", "bt_rtn_nt", "bn_rtn_nt", "b_magnitude_nt",
            "flow_speed_kms", "flow_elevation_deg", "flow_azimuth_deg",
            "proton_density_cm3", "proton_temperature_k",
            "flux_h_crt_3p45_5p15_mev", "flux_h_crt_30p55_56p47_mev",
            "flux_h_crt_120p7_227p3_mev",
        ],
        "fill_values": {
            "heliocentric_distance_au": 999.99,
            "hgi_latitude_deg": 9999.9,
            "hgi_longitude_deg": 9999.9,
            "br_rtn_nt": 999.9999,
            "bt_rtn_nt": 999.9999,
            "bn_rtn_nt": 999.9999,
            "b_magnitude_nt": 999.9999,
            "flow_speed_kms": 9999.9,
            "flow_elevation_deg": 9999.9,
            "flow_azimuth_deg": 9999.9,
            "proton_density_cm3": 999.9999,
            "proton_temperature_k": 9999999.0,
        },
        "flux_fill_threshold": 9.9e6,
    },
}

# Columns common to all spacecraft (used for the merged output)
COMMON_COLUMNS = [
    "spacecraft", "datetime",
    "heliocentric_distance_au", "hgi_latitude_deg", "hgi_longitude_deg",
    "b_magnitude_nt", "br_rtn_nt", "bt_rtn_nt", "bn_rtn_nt",
    "flow_speed_kms", "flow_elevation_deg", "flow_azimuth_deg",
    "proton_density_cm3", "proton_temperature_k",
]


def fetch_spacecraft(name, cfg):
    """Download and parse yearly files for one spacecraft."""
    frames = []
    session = requests.Session()
    for year in cfg["years"]:
        url = cfg["url"] + cfg["pattern"].format(year=year)
        try:
            resp = session.get(url, timeout=60)
            resp.raise_for_status()
        except requests.HTTPError as e:
            if resp.status_code == 404:
                print(f"    {name} {year}: not found, skipping")
                continue
            raise
        except requests.RequestException as e:
            print(f"    {name} {year}: error {e}, skipping")
            continue

        # Parse fixed-width whitespace-delimited ASCII
        df = pd.read_csv(
            StringIO(resp.text),
            sep=r"\s+",
            header=None,
            names=cfg["columns"][:],  # use as many names as columns present
        )
        frames.append(df)
        time.sleep(0.3)  # polite delay

    if not frames:
        print(f"  WARNING: no data for {name}")
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    print(f"  {name}: {len(df):,} raw rows ({int(df['year'].min())}-{int(df['year'].max())})")

    # Create datetime from year + day_of_year + hour
    df["datetime"] = pd.to_datetime(
        df["year"].astype(int).astype(str) + "-" +
        df["day_of_year"].astype(int).astype(str) + "-" +
        df["hour"].astype(int).astype(str),
        format="%Y-%j-%H",
        errors="coerce",
    )

    # Replace fill values with NaN for non-flux columns
    for col, fill in cfg["fill_values"].items():
        if col in df.columns:
            df.loc[df[col] >= fill, col] = pd.NA

    # Replace fill values for flux columns (any column starting with "flux_")
    flux_cols = [c for c in df.columns if c.startswith("flux_")]
    threshold = cfg["flux_fill_threshold"]
    for col in flux_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        df.loc[df[col] >= threshold, col] = pd.NA

    # Voyager has b_magnitude_avg_nt; Pioneer does not — add if missing
    if "b_magnitude_avg_nt" not in df.columns:
        df["b_magnitude_avg_nt"] = pd.NA

    df["spacecraft"] = name

    # Drop raw time columns
    df = df.drop(columns=["year", "day_of_year", "hour"], errors="ignore")

    return df


def main():
    print("Fetching deep space probe data from NASA SPDF...")

    all_frames = []
    for name, cfg in SOURCES.items():
        print(f"\nDownloading {name}...")
        df = fetch_spacecraft(name, cfg)
        if len(df) > 0:
            all_frames.append(df)

    print("\nMerging all spacecraft data...")
    df = pd.concat(all_frames, ignore_index=True)
    print(f"  {len(df):,} total rows before cleanup")

    # Drop rows with no datetime (bad parse)
    df = df.dropna(subset=["datetime"])

    # Ensure numeric types on common columns
    numeric_cols = [
        "heliocentric_distance_au", "hgi_latitude_deg", "hgi_longitude_deg",
        "b_magnitude_avg_nt", "b_magnitude_nt",
        "br_rtn_nt", "bt_rtn_nt", "bn_rtn_nt",
        "flow_speed_kms", "flow_elevation_deg", "flow_azimuth_deg",
        "proton_density_cm3", "proton_temperature_k",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Keep only common columns + all flux columns + spacecraft + datetime
    flux_cols = sorted([c for c in df.columns if c.startswith("flux_")])
    keep_cols = COMMON_COLUMNS + ["b_magnitude_avg_nt"] + flux_cols
    # Only keep columns that exist
    keep_cols = [c for c in keep_cols if c in df.columns]
    df = df[keep_cols]

    # Sort by spacecraft, datetime
    df = df.sort_values(["spacecraft", "datetime"]).reset_index(drop=True)

    print(f"  {len(df):,} rows after cleanup")

    # Stats per spacecraft
    for sc in sorted(df["spacecraft"].unique()):
        sub = df[df["spacecraft"] == sc]
        date_min = sub["datetime"].min().strftime("%Y-%m-%d")
        date_max = sub["datetime"].max().strftime("%Y-%m-%d")
        dist_max = sub["heliocentric_distance_au"].max()
        print(f"  {sc}: {len(sub):,} rows, {date_min} to {date_max}, max {dist_max:.1f} AU")

    # Validation
    check_dataset(
        df, "deep-space-probes",
        min_rows=1_000_000,
        expected_columns=[
            "spacecraft", "datetime", "heliocentric_distance_au",
            "b_magnitude_nt", "br_rtn_nt", "bt_rtn_nt", "bn_rtn_nt",
            "flow_speed_kms", "proton_density_cm3", "proton_temperature_k",
        ],
        critical_columns=["spacecraft", "datetime", "heliocentric_distance_au"],
    )

    # Stats for README
    n_total = len(df)
    sc_counts = df["spacecraft"].value_counts().to_dict()
    date_min = df["datetime"].min().strftime("%Y-%m-%d")
    date_max = df["datetime"].max().strftime("%Y-%m-%d")
    max_dist_row = df.loc[df["heliocentric_distance_au"].idxmax()]
    max_dist = max_dist_row["heliocentric_distance_au"]
    max_dist_sc = max_dist_row["spacecraft"]

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "deep_space_probes.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        sc_bullets = "\n".join(
            f"- **{sc.replace('_', ' ').title()}**: {sc_counts.get(sc, 0):,} hourly records"
            for sc in ["voyager_1", "voyager_2", "pioneer_10", "pioneer_11"]
        )

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Deep Space Probes — Merged Hourly Data"
language:
  - en
description: "Merged hourly magnetic field, solar wind plasma, and energetic particle data from Voyager 1, Voyager 2, Pioneer 10, and Pioneer 11. Spans 1972 to present, from 1 AU to 160+ AU."
task_categories:
  - tabular-regression
  - time-series-forecasting
tags:
  - space
  - heliophysics
  - voyager
  - pioneer
  - solar-wind
  - magnetic-field
  - deep-space
  - nasa
  - spdf
  - interstellar
  - open-data
  - tabular-data
size_categories:
  - 1M<n<10M
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/deep_space_probes.parquet
    default: true
---

# Deep Space Probes — Merged Hourly Data

*Part of the [Space Weather Datasets](https://huggingface.co/collections/juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70) collection on Hugging Face.*

![Update Deep Space Probes](https://github.com/juliensimon/space-datasets/actions/workflows/update-deep-space-probes.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.deep-space-probes&label=updated&color=brightgreen)

Merged hourly magnetic field, solar wind plasma, and energetic particle measurements from humanity's
four most distant spacecraft: **Voyager 1**, **Voyager 2**, **Pioneer 10**, and **Pioneer 11**.
Currently **{n_total:,}** hourly records spanning **{date_min}** to **{date_max}**, reaching
**{max_dist:.1f} AU** from the Sun ({max_dist_sc.replace('_', ' ').title()}).

## Dataset description

This dataset combines the COHO (COordinated Heliospheric Observations) merged hourly data files
from NASA's Space Physics Data Facility (SPDF) for the four deep-space probes that have traveled
beyond the outer planets. The data covers the entire mission durations:

{sc_bullets}

Each record includes spacecraft position (heliocentric distance, HGI latitude/longitude),
interplanetary magnetic field components (RTN coordinates), solar wind plasma parameters
(flow speed, proton density, temperature), and energetic particle fluxes at multiple
energy channels from the LECP, CRS, and CRT instruments.

Voyager 1 crossed the heliopause (~121 AU) in August 2012 and Voyager 2 (~119 AU) in November 2018,
making this dataset unique in spanning the transition from the heliosphere to interstellar space.

## Schema (common columns)

| Column | Type | Description |
|--------|------|-------------|
| `spacecraft` | string | Spacecraft identifier (voyager_1, voyager_2, pioneer_10, pioneer_11) |
| `datetime` | datetime | Observation timestamp (UTC, hourly cadence) |
| `heliocentric_distance_au` | float64 | Distance from the Sun (AU) |
| `hgi_latitude_deg` | float64 | Heliographic Inertial latitude (degrees) |
| `hgi_longitude_deg` | float64 | Heliographic Inertial longitude (degrees) |
| `b_magnitude_avg_nt` | float64 | Average magnetic field magnitude 1/N SUM |B| (nT) — Voyager only |
| `b_magnitude_nt` | float64 | Magnetic field magnitude sqrt(Br^2+Bt^2+Bn^2) (nT) |
| `br_rtn_nt` | float64 | Radial magnetic field component, RTN (nT) |
| `bt_rtn_nt` | float64 | Tangential magnetic field component, RTN (nT) |
| `bn_rtn_nt` | float64 | Normal magnetic field component, RTN (nT) |
| `flow_speed_kms` | float64 | Proton bulk flow speed (km/s) |
| `flow_elevation_deg` | float64 | Flow velocity elevation angle (degrees) |
| `flow_azimuth_deg` | float64 | Flow velocity azimuth angle (degrees) |
| `proton_density_cm3` | float64 | Proton number density (particles/cm^3) |
| `proton_temperature_k` | float64 | Proton temperature (Kelvin) |

Additional spacecraft-specific flux columns (energetic particle differential flux in 1/(cm^2 s sr MeV))
are included with names like `flux_h_lecp_*_mev`, `flux_h_crs_*_mev`, and `flux_h_crt_*_mev`.

## Quick stats

- **{n_total:,}** hourly records ({date_min} to {date_max})
- **4 spacecraft**: Voyager 1 & 2, Pioneer 10 & 11
- Maximum heliocentric distance: **{max_dist:.1f} AU** ({max_dist_sc.replace('_', ' ').title()})
- Covers heliosphere, heliosheath, and interstellar space

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/deep-space-probes", split="train")
df = ds.to_pandas()

# Voyager 1 in interstellar space (beyond heliopause at ~121 AU)
v1_interstellar = df[
    (df["spacecraft"] == "voyager_1") &
    (df["heliocentric_distance_au"] > 121)
]

# Compare solar wind speed across all probes
for sc in df["spacecraft"].unique():
    sub = df[df["spacecraft"] == sc].dropna(subset=["flow_speed_kms"])
    print(f"{{sc}}: mean flow speed = {{sub['flow_speed_kms'].mean():.0f}} km/s")

# Magnetic field decay with distance
import matplotlib.pyplot as plt
v1 = df[df["spacecraft"] == "voyager_1"].dropna(subset=["b_magnitude_nt"])
plt.scatter(v1["heliocentric_distance_au"], v1["b_magnitude_nt"], s=0.1, alpha=0.3)
plt.xlabel("Distance (AU)")
plt.ylabel("|B| (nT)")
plt.yscale("log")
plt.title("Voyager 1: Magnetic Field vs Distance")
plt.show()

# Pioneer 10 complete mission timeline
p10 = df[df["spacecraft"] == "pioneer_10"]
print(f"Pioneer 10: {{p10['datetime'].min()}} to {{p10['datetime'].max()}}")
print(f"  Distance range: {{p10['heliocentric_distance_au'].min():.1f}} - {{p10['heliocentric_distance_au'].max():.1f}} AU")
```

## Data source

[NASA Space Physics Data Facility (SPDF)](https://spdf.gsfc.nasa.gov/) — COordinated Heliospheric
Observations (COHO) merged hourly data files:

- Voyager 1: `spdf.gsfc.nasa.gov/pub/data/voyager/voyager1/merged/`
- Voyager 2: `spdf.gsfc.nasa.gov/pub/data/voyager/voyager2/merged/`
- Pioneer 10: `spdf.gsfc.nasa.gov/pub/data/pioneer/pioneer10/merged/coho1hr_magplasma_ascii/`
- Pioneer 11: `spdf.gsfc.nasa.gov/pub/data/pioneer/pioneer11/merged/coho1hr_magplasma_ascii/`

## Update schedule

Monthly (1st at 07:00 UTC) via [GitHub Actions](https://github.com/juliensimon/space-datasets).
Voyager data is still being collected; Pioneer missions ended in the 1990s.

## Related datasets

- [solar-wind-plasma](https://huggingface.co/datasets/juliensimon/solar-wind-plasma) — Near-Earth solar wind from DSCOVR/ACE
- [dst-index](https://huggingface.co/datasets/juliensimon/dst-index) — Geomagnetic Dst index
- [kp-index](https://huggingface.co/datasets/juliensimon/kp-index) — Geomagnetic Kp index

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/deep-space-probes) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{deep_space_probes,
  author = {{Simon, Julien}},
  title = {{Deep Space Probes — Merged Hourly Data}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/deep-space-probes}},
  note = {{Based on NASA/SPDF COHO merged hourly data for Voyager 1, Voyager 2, Pioneer 10, and Pioneer 11}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update deep space probes: {n_total:,} records"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={n_total}\n")
    print("Done.")


if __name__ == "__main__":
    main()
