#!/usr/bin/env python3
"""Fetch ISRO missions data (spacecraft, launchers, customer satellites, centres),
convert to Parquet, and upload to Hugging Face."""

import os
import subprocess
import tempfile
import time
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset

BASE_URL = "https://isro.vercel.app/api"
HF_REPO = "juliensimon/isro-missions"

ENDPOINTS = {
    "spacecraft": ("spacecrafts", "spacecrafts"),
    "launchers": ("launchers", "launchers"),
    "customer_satellites": ("customer_satellites", "customer_satellites"),
    "centres": ("centres", "centres"),
}


def fetch_endpoint(path, key, label):
    """Fetch a single ISRO API endpoint with retries."""
    url = f"{BASE_URL}/{path}"
    print(f"Fetching {label} from {url}...")
    for attempt in range(1, 4):
        try:
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            records = data[key]
            print(f"  {len(records):,} {label}")
            return pd.DataFrame(records)
        except (requests.RequestException, KeyError, ValueError) as exc:
            print(f"  Attempt {attempt} failed: {exc}")
            if attempt < 3:
                time.sleep(2 * attempt)
    raise RuntimeError(f"Failed to fetch {label} after 3 attempts")


def normalize_columns(df):
    """Normalize column names to snake_case."""
    df.columns = (
        df.columns
        .str.strip()
        .str.lower()
        .str.replace(r"[^a-z0-9]+", "_", regex=True)
        .str.strip("_")
    )
    return df


def main():
    # ── Fetch ────────────────────────────────────────────────────────────
    spacecraft = fetch_endpoint("spacecrafts", "spacecrafts", "spacecraft")
    time.sleep(1)
    launchers = fetch_endpoint("launchers", "launchers", "launchers")
    time.sleep(1)
    customer_sats = fetch_endpoint("customer_satellites", "customer_satellites",
                                   "customer satellites")
    time.sleep(1)
    centres = fetch_endpoint("centres", "centres", "centres")

    # ── Transform ────────────────────────────────────────────────────────
    spacecraft = normalize_columns(spacecraft)
    launchers = normalize_columns(launchers)
    customer_sats = normalize_columns(customer_sats)
    centres = normalize_columns(centres)

    # Coerce numeric columns
    if "id" in spacecraft.columns:
        spacecraft["id"] = pd.to_numeric(spacecraft["id"], errors="coerce")
    if "id" in centres.columns:
        centres["id"] = pd.to_numeric(centres["id"], errors="coerce")

    # Customer satellites: coerce mass to numeric, parse launch date
    if "mass" in customer_sats.columns:
        customer_sats["mass_kg"] = pd.to_numeric(
            customer_sats["mass"].str.replace(r"[^\d.]", "", regex=True),
            errors="coerce",
        )
        customer_sats = customer_sats.drop(columns=["mass"])
    if "launch_date" in customer_sats.columns:
        customer_sats["launch_date"] = pd.to_datetime(
            customer_sats["launch_date"], format="%d-%m-%Y", errors="coerce"
        )

    # Strip whitespace from string columns
    for df in [spacecraft, launchers, customer_sats, centres]:
        for col in df.select_dtypes(include="object").columns:
            df[col] = df[col].str.strip()

    # ── Validate ─────────────────────────────────────────────────────────
    check_dataset(spacecraft, "spacecraft", min_rows=50,
                  expected_columns=["id", "name"],
                  critical_columns=["name"])
    check_dataset(launchers, "launchers", min_rows=10,
                  expected_columns=["id"],
                  critical_columns=["id"])
    check_dataset(customer_sats, "customer_satellites", min_rows=30,
                  expected_columns=["id", "country", "launcher"],
                  critical_columns=["id", "country"])
    check_dataset(centres, "centres", min_rows=10,
                  expected_columns=["id", "name", "place", "state"],
                  critical_columns=["name"])

    total_rows = (len(spacecraft) + len(launchers) +
                  len(customer_sats) + len(centres))

    # ── Write parquet + README ───────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        data_dir = tmp_dir / "data"
        data_dir.mkdir()

        spacecraft.to_parquet(data_dir / "spacecraft.parquet", index=False,
                              engine="pyarrow", compression="zstd")
        launchers.to_parquet(data_dir / "launchers.parquet", index=False,
                             engine="pyarrow", compression="zstd")
        customer_sats.to_parquet(data_dir / "customer_satellites.parquet",
                                 index=False, engine="pyarrow",
                                 compression="zstd")
        centres.to_parquet(data_dir / "centres.parquet", index=False,
                           engine="pyarrow", compression="zstd")

        # Stats for README
        n_countries = customer_sats["country"].nunique()
        n_states = centres["state"].nunique() if "state" in centres.columns else 0

        (tmp_dir / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "ISRO Missions Data"
language:
  - en
description: "Indian Space Research Organisation (ISRO) spacecraft, launchers, customer satellites, and research centres. {total_rows:,} records across four tables."
task_categories:
  - tabular-classification
tags:
  - space
  - isro
  - india
  - spacecraft
  - launchers
  - satellites
  - open-data
  - tabular-data
  - parquet
configs:
  - config_name: spacecraft
    data_files:
      - split: train
        path: data/spacecraft.parquet
    default: true
  - config_name: launchers
    data_files:
      - split: train
        path: data/launchers.parquet
  - config_name: customer_satellites
    data_files:
      - split: train
        path: data/customer_satellites.parquet
  - config_name: centres
    data_files:
      - split: train
        path: data/centres.parquet
size_categories:
  - n<1K
---

# ISRO Missions Data

*Part of the [Orbital Mechanics Datasets](https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994) collection on Hugging Face.*

Comprehensive data on the **Indian Space Research Organisation (ISRO)**: **{len(spacecraft):,}** spacecraft,
**{len(launchers):,}** launch vehicles, **{len(customer_sats):,}** customer satellites launched for
**{n_countries}** countries, and **{len(centres):,}** research centres across **{n_states}** Indian states.

## Dataset description

ISRO is India's national space agency, responsible for one of the most cost-effective space programs in the world. Since its founding in 1969, ISRO has developed indigenous launch vehicle families -- the Polar Satellite Launch Vehicle (PSLV), Geosynchronous Satellite Launch Vehicle (GSLV), and the heavy-lift GSLV Mk III (LVM3) -- and built satellite constellations for remote sensing (IRS series), communications (INSAT/GSAT series), and navigation (NavIC/IRNSS). ISRO has achieved landmark interplanetary missions including Chandrayaan-1 (which confirmed water on the Moon), the Mars Orbiter Mission (Mangalyaan, India's first interplanetary probe), Chandrayaan-3 (which successfully landed near the lunar south pole in 2023), and is developing the Gaganyaan crewed spaceflight program.

This dataset captures four dimensions of ISRO's space program: the full catalog of ISRO-built spacecraft, the complete roster of launch vehicles from early SLV-3 experimental flights through modern PSLV and GSLV missions, customer satellites launched by ISRO for international clients (a major commercial activity, with PSLV having launched satellites for dozens of countries), and the network of ISRO research centres and facilities distributed across India.

## Configs

### `spacecraft` -- {len(spacecraft):,} ISRO spacecraft

Every spacecraft built and launched by ISRO.

| Column | Type | Description |
|--------|------|-------------|
| `id` | int | Unique spacecraft identifier |
| `name` | string | Spacecraft name (e.g., Aryabhata, INSAT-1A, Chandrayaan-1) |

### `launchers` -- {len(launchers):,} launch vehicles

ISRO launch vehicle missions (SLV, ASLV, PSLV, GSLV variants).

| Column | Type | Description |
|--------|------|-------------|
| `id` | string | Launcher mission identifier (e.g., PSLV-C2, GSLV-F05) |

### `customer_satellites` -- {len(customer_sats):,} customer satellites

Satellites launched by ISRO for international customers.

| Column | Type | Description |
|--------|------|-------------|
| `id` | string | Satellite name/identifier |
| `country` | string | Customer country |
| `launch_date` | date | Launch date |
| `mass_kg` | float | Satellite mass in kilograms |
| `launcher` | string | ISRO launcher used (e.g., PSLV-C2) |

### `centres` -- {len(centres):,} ISRO centres

ISRO research centres and facilities across India.

| Column | Type | Description |
|--------|------|-------------|
| `id` | int | Centre identifier |
| `name` | string | Centre name |
| `place` | string | City/location |
| `state` | string | Indian state |

## Quick stats

- **{len(spacecraft):,}** ISRO spacecraft from Aryabhata (1975) to present
- **{len(launchers):,}** launch vehicle missions (SLV, ASLV, PSLV, GSLV, LVM3)
- **{len(customer_sats):,}** customer satellites for **{n_countries}** countries
- **{len(centres):,}** research centres across **{n_states}** Indian states

## Usage

```python
from datasets import load_dataset

spacecraft = load_dataset("juliensimon/isro-missions", "spacecraft", split="train")
launchers = load_dataset("juliensimon/isro-missions", "launchers", split="train")
customer_sats = load_dataset("juliensimon/isro-missions", "customer_satellites", split="train")
centres = load_dataset("juliensimon/isro-missions", "centres", split="train")

# List all ISRO spacecraft
sdf = spacecraft.to_pandas()
print(sdf[["id", "name"]].to_string(index=False))

# Customer satellites by country
cdf = customer_sats.to_pandas()
print(cdf.groupby("country").size().sort_values(ascending=False).head(10))

# PSLV missions
ldf = launchers.to_pandas()
pslv = ldf[ldf["id"].str.startswith("PSLV")]
print(f"{{len(pslv)}} PSLV missions")
```

## Data source

[ISRO API](https://isro.vercel.app/) -- community-maintained open API for ISRO spacecraft,
launchers, and mission data. Based on publicly available ISRO records.

## Update schedule

Static dataset -- rebuilt manually when the source API is updated.

## Related datasets

- [space-missions](https://huggingface.co/datasets/juliensimon/space-missions) -- Global space mission history
- [spacecraft](https://huggingface.co/datasets/juliensimon/spacecraft) -- Spacecraft database
- [gcat-satellite-catalog](https://huggingface.co/datasets/juliensimon/gcat-satellite-catalog) -- GCAT satellite catalog
- [space-agencies](https://huggingface.co/datasets/juliensimon/space-agencies) -- Space agency data

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/isro-missions) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{isro_missions,
  author = {{Simon, Julien}},
  title = {{ISRO Missions Data}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/isro-missions}},
  note = {{Based on community ISRO API (isro.vercel.app)}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = (f"Update ISRO missions: {len(spacecraft):,} spacecraft, "
                      f"{len(launchers):,} launchers, "
                      f"{len(customer_sats):,} customer satellites, "
                      f"{len(centres):,} centres")
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp_dir), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={total_rows}\n")
    print(f"Done. {total_rows:,} total rows.")


if __name__ == "__main__":
    main()
