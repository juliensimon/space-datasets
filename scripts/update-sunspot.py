#!/usr/bin/env python3
"""Fetch SILSO daily sunspot numbers and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from dataset_images import banner_markdown, download_banner
from validate import check_dataset


SILSO_URL = "https://www.sidc.be/SILSO/DATA/SN_d_tot_V2.0.csv"
HF_REPO = "juliensimon/silso-sunspot-number"


def main():
    print("Fetching SILSO daily sunspot numbers...")
    df = pd.read_csv(
        SILSO_URL,
        sep=";",
        header=None,
        names=[
            "year", "month", "day", "decimal_date",
            "sunspot_number", "std_dev", "n_observations", "provisional_flag",
        ],
    )
    print(f"  {len(df):,} raw rows")

    # Filter out rows with day=0 (monthly aggregates mixed in)
    df = df[df["day"] > 0].copy()
    print(f"  {len(df):,} daily rows after filtering day>0")

    # Create proper date column
    df["date"] = pd.to_datetime(
        df[["year", "month", "day"]].rename(columns={"year": "year", "month": "month", "day": "day"}),
        errors="coerce",
    )

    # sunspot_number: -1 means missing → NaN, then convert to Int64
    df["sunspot_number"] = df["sunspot_number"].replace(-1, pd.NA)
    df["sunspot_number"] = pd.to_numeric(df["sunspot_number"], errors="coerce").astype("Int64")

    # Numeric coercion
    for col in ["decimal_date", "std_dev"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["n_observations"] = pd.to_numeric(df["n_observations"], errors="coerce").astype("Int64")

    # provisional_flag: 1 = provisional, 0 = definitive → is_provisional boolean
    df["is_provisional"] = df["provisional_flag"].map({1: True, 0: False})

    # Drop intermediate columns
    df = df.drop(columns=["year", "month", "day", "provisional_flag"])

    # Reorder
    df = df[["date", "decimal_date", "sunspot_number", "std_dev", "n_observations", "is_provisional"]]

    # Sort by date
    df = df.sort_values("date").reset_index(drop=True)

    check_dataset(df, "sunspot", min_rows=50000,
        expected_columns=["date", "sunspot_number", "n_observations", "std_dev", "is_provisional"],
        critical_columns=["date", "sunspot_number"])

    # Stats for README
    n_total = len(df)
    date_min = df["date"].min().strftime("%Y-%m-%d")
    date_max = df["date"].max().strftime("%Y-%m-%d")
    max_sn = int(df["sunspot_number"].max())
    max_sn_date = df.loc[df["sunspot_number"].idxmax(), "date"].strftime("%Y-%m-%d")
    n_provisional = int(df["is_provisional"].sum())

    # Current solar cycle 25 stats (started ~2019-12)
    sc25 = df[df["date"] >= "2019-12-01"]
    sc25_max = int(sc25["sunspot_number"].max()) if len(sc25) > 0 else 0
    sc25_mean = sc25["sunspot_number"].mean()

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "silso_sunspot_number.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        banner_file = download_banner("sunspot", tmp)
        banner_md = banner_markdown("sunspot", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "SILSO Daily Sunspot Number"
language:
  - en
description: "Daily total sunspot numbers from SILSO, the World Data Center for the Sunspot Index at the Royal Observatory of Belgium. The longest continuous scientific observation in history, since 1818."
task_categories:
  - tabular-regression
  - time-series-forecasting
tags:
  - space
  - sun
  - sunspot
  - solar-cycle
  - space-weather
  - silso
  - open-data
  - tabular-data
  - parquet
size_categories:
  - 100K<n<1M
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/silso_sunspot_number.parquet
    default: true
---

# SILSO Daily Sunspot Number
{banner_md}
*Part of the [Space Weather Datasets](https://huggingface.co/collections/juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70) collection on Hugging Face.*

![Update Sunspot](https://github.com/juliensimon/space-datasets/actions/workflows/update-sunspot.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.sunspot&label=updated&color=brightgreen)

Daily total sunspot numbers from the World Data Center SILSO at the Royal Observatory of Belgium.
This is **the longest continuous scientific observation in history**, with systematic daily records
since 1818 and international coordination since 1981. Currently **{n_total:,}** daily records.

## Dataset description

The International Sunspot Number is the primary index of solar activity, tracking the number of
sunspots visible on the solar disk each day. Sunspots are temporary phenomena on the Sun's
photosphere caused by magnetic flux concentrations. Their number follows an approximately 11-year
cycle (the Schwabe cycle) that profoundly affects space weather, satellite operations, radio
communications, and Earth's upper atmosphere.

SILSO (Sunspot Index and Long-term Solar Observations) at the Royal Observatory of Belgium
serves as the World Data Center for sunspot number computation, collecting observations from
a worldwide network of stations.

Sunspots are regions where intense magnetic flux tubes (typically 0.1-0.3 T) emerge through the photosphere, inhibiting convective energy transport and creating dark spots roughly 1000-1500 K cooler than the surrounding ~5800 K surface. They range in size from small pores barely resolvable in modest telescopes to complex active regions spanning over 100,000 km. The daily sunspot number is computed using the Wolf formula (R = k(10g + s), where g is the number of sunspot groups, s is the total number of individual spots, and k is a station-dependent scaling factor), then combined across the observer network into a single international index.

The approximately 11-year Schwabe cycle in sunspot number is the most visible manifestation of the solar magnetic dynamo operating in the Sun's convective zone. At solar minimum, the disk may be spotless for weeks; at maximum, daily counts can exceed 200-300. This cycle drives variations in the total solar irradiance (order 0.1%), extreme ultraviolet flux (factor of 10 or more), solar flare and CME rates, and the overall heliospheric magnetic field strength. These variations have direct consequences for satellite drag (through thermospheric heating), HF radio propagation, radiation exposure for astronauts and polar-route aviation, and the modulation of galactic cosmic ray flux at Earth.

The SILSO Version 2.0 series, released in 2015, recalibrated the entire historical record back to 1818 to correct for discontinuities introduced by changes in the reference observer. This makes it the most homogeneous long-baseline solar activity record available, spanning over 200 years of daily observations and encompassing roughly 19 complete solar cycles -- an invaluable resource for studying long-term solar variability, cycle prediction, and Sun-climate relationships.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `date` | date | Observation date (UTC); SILSO daily records begin 1818-01-01 |
| `decimal_date` | float64 | Fractional year representation of the date (e.g., 2024.5 ≈ July 2 2024); useful for continuous time-series computations |
| `sunspot_number` | Int64 | International Sunspot Number (ISN v2.0) — daily count of sunspots on the solar disk using the Wolf formula (R = k(10g + s)); solar minimum: ~0–10; solar maximum: 150–300+; approximately 11-year cycle; null for days with no observation; v2.0 values are ~1.6× the previous v1.0 series |
| `std_dev` | float64 | Standard deviation of individual station observations around the network mean for that day; larger values indicate disagreement between observers or complex sunspot groups |
| `n_observations` | Int64 | Number of SILSO network observing stations that contributed valid measurements that day; typical range 10–50; lower values (early historical records) reflect fewer contributing observers |
| `is_provisional` | bool | True if the value has not yet been finalized by SILSO (recent ~30 days); provisional values may be revised when additional observer data arrives; False for definitive historical values |

## Quick stats

- **{n_total:,}** daily records ({date_min} to {date_max})
- All-time maximum: **{max_sn}** on {max_sn_date}
- **{n_provisional:,}** provisional values
- Solar Cycle 25 (current): peak so far **{sc25_max}**, mean **{sc25_mean:.1f}**

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/silso-sunspot-number", split="train")
df = ds.to_pandas()

# Plot solar cycles
import matplotlib.pyplot as plt
df["date"] = pd.to_datetime(df["date"])
monthly = df.set_index("date").resample("MS")["sunspot_number"].mean()
monthly.plot(figsize=(14, 4), title="Solar Cycles - Monthly Mean Sunspot Number")
plt.ylabel("Sunspot Number")
plt.show()

# Current solar cycle 25
sc25 = df[df["date"] >= "2019-12-01"]
print(f"Cycle 25 max so far: {{sc25['sunspot_number'].max()}}")

# Compare cycle amplitudes
df["year"] = pd.to_datetime(df["date"]).dt.year
yearly = df.groupby("year")["sunspot_number"].mean()
```

## Data source

[SILSO, World Data Center for the Sunspot Index](https://www.sidc.be/SILSO/),
Royal Observatory of Belgium, Brussels.

## Update schedule

Monthly (1st at 09:00 UTC) via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [solar-flare-index](https://huggingface.co/datasets/juliensimon/solar-flare-events) -- Solar flare observations
- [kp-index](https://huggingface.co/datasets/juliensimon/geomagnetic-kp-index) -- Geomagnetic Kp index
- [dst-index](https://huggingface.co/datasets/juliensimon/dst-index) -- Geomagnetic Dst index

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/silso-sunspot-number) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{silso_sunspot_number,
  author = {{Simon, Julien}},
  title = {{SILSO Daily Sunspot Number}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/silso-sunspot-number}},
  note = {{Based on SILSO data, World Data Center for the Sunspot Index, Royal Observatory of Belgium}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update SILSO sunspot numbers: {n_total:,} records"
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
