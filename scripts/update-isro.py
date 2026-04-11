#!/usr/bin/env python3
"""Fetch ISRO missions data (spacecraft, launchers, customer satellites, centres),
convert to Parquet, and upload to Hugging Face.

Source: ISRO API (isro.vercel.app) -- community-maintained open API for ISRO data.
Four configs: spacecraft, launchers, customer_satellites, centres.
"""

import time

import pandas as pd
import requests

from hf_dataset_utils import Pipeline
from hf_dataset_utils.banner import banner_markdown as render_banner
from hf_dataset_utils.banner import download_banner
from hf_dataset_utils.github import emit_output
from hf_dataset_utils.readme import _size_category, _citation_bibtex
from hf_dataset_utils.upload import upload_to_hf, write_parquet
from hf_dataset_utils.validation import check_dataset

BASE_URL = "https://isro.vercel.app/api"
HF_REPO = "juliensimon/isro-missions"

# ── Column descriptions ─────────────────────────────────────────────
SPACECRAFT_DESCRIPTIONS = {
    "id": "Unique numeric identifier for the ISRO spacecraft in the API database",
    "name": "Spacecraft name (e.g. 'Aryabhata', 'INSAT-1A', 'Chandrayaan-1', 'Mangalyaan'); ISRO's spacecraft catalog spans from 1975 to present",
}

LAUNCHER_DESCRIPTIONS = {
    "id": "Launcher mission identifier (e.g. 'PSLV-C2', 'GSLV-F05', 'LVM3-M4'); encodes vehicle family and flight number",
}

CUSTOMER_SAT_DESCRIPTIONS = {
    "id": "Customer satellite name or identifier as assigned by the satellite owner or operator",
    "country": "Country of the customer who contracted ISRO for the launch; ISRO's PSLV has launched satellites for dozens of countries worldwide",
    "launch_date": "Date when the satellite was launched by an ISRO launch vehicle; parsed from DD-MM-YYYY format",
    "mass_kg": "Satellite mass in kilograms at launch; extracted from source string and coerced to numeric",
    "launcher": "ISRO launch vehicle used for this satellite (e.g. 'PSLV-C2', 'GSLV Mk III'); PSLV is the most prolific commercial launcher",
}

CENTRES_DESCRIPTIONS = {
    "id": "Unique numeric identifier for the ISRO centre in the API database",
    "name": "Full name of the ISRO centre or facility (e.g. 'Vikram Sarabhai Space Centre', 'ISRO Satellite Centre')",
    "place": "City or location where the centre is situated (e.g. 'Thiruvananthapuram', 'Bengaluru', 'Sriharikota')",
    "state": "Indian state where the centre is located (e.g. 'Kerala', 'Karnataka', 'Andhra Pradesh')",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Comprehensive data on the Indian Space Research Organisation (ISRO): spacecraft, launch \
vehicles, customer satellites launched for international clients, and research centres across \
India. ISRO is India's national space agency, responsible for one of the most cost-effective \
space programs in the world.

Since its founding in 1969, ISRO has developed indigenous launch vehicle families -- PSLV, \
GSLV, and LVM3 -- and built satellite constellations for remote sensing (IRS series), \
communications (INSAT/GSAT series), and navigation (NavIC/IRNSS). Landmark missions include \
Chandrayaan-1 (confirmed water on the Moon), Mars Orbiter Mission (India's first interplanetary \
probe), and Chandrayaan-3 (successful lunar south pole landing in 2023).
"""


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
    # ── Fetch ────────────────────────────────────────────────────────
    spacecraft = fetch_endpoint("spacecrafts", "spacecrafts", "spacecraft")
    time.sleep(1)
    launchers = fetch_endpoint("launchers", "launchers", "launchers")
    time.sleep(1)
    customer_sats = fetch_endpoint("customer_satellites", "customer_satellites",
                                   "customer satellites")
    time.sleep(1)
    centres = fetch_endpoint("centres", "centres", "centres")

    # ── Transform ────────────────────────────────────────────────────
    spacecraft = normalize_columns(spacecraft)
    launchers = normalize_columns(launchers)
    customer_sats = normalize_columns(customer_sats)
    centres = normalize_columns(centres)

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

    # Keep only described columns per config
    spacecraft = spacecraft[[c for c in spacecraft.columns if c in SPACECRAFT_DESCRIPTIONS]]
    launchers = launchers[[c for c in launchers.columns if c in LAUNCHER_DESCRIPTIONS]]
    customer_sats = customer_sats[[c for c in customer_sats.columns if c in CUSTOMER_SAT_DESCRIPTIONS]]
    centres = centres[[c for c in centres.columns if c in CENTRES_DESCRIPTIONS]]

    # ── Validate ─────────────────────────────────────────────────────
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

    # ── Stats ────────────────────────────────────────────────────────
    n_countries = customer_sats["country"].nunique()
    n_states = centres["state"].nunique() if "state" in centres.columns else 0

    # ── Build multi-config dataset using Pipeline context ────────────
    with Pipeline(
        repo=HF_REPO,
        pretty_name="ISRO Missions Data",
        description="",  # custom README below
        tags=[],
        source_url="https://isro.vercel.app/",
        collection_url="https://huggingface.co/collections/juliensimon/space-probe-and-mission-datasets-69c3fe82d410a42b1e313167",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA14111/PIA14111~small.jpg",
            "alt": "Voyager spacecraft artist concept",
            "credit": "NASA/JPL-Caltech",
        },
    ) as p:
        # Write all 4 parquet configs
        write_parquet(spacecraft, p.data_dir / "spacecraft.parquet")
        write_parquet(launchers, p.data_dir / "launchers.parquet")
        write_parquet(customer_sats, p.data_dir / "customer_satellites.parquet")
        write_parquet(centres, p.data_dir / "centres.parquet")

        # Banner
        banner_file = download_banner(p.banner["url"], p.tmp_dir)
        banner_md = render_banner(
            p.banner["alt"], p.banner["credit"],
            filename=banner_file,
        ) if banner_file else ""

        # Schema helpers
        def _schema(descs):
            lines = ["| Column | Type | Description |", "|--------|------|-------------|"]
            for col, desc in descs.items():
                lines.append(f"| `{col}` | -- | {desc} |")
            return "\n".join(lines)

        readme = f"""---
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
size_categories:
  - {_size_category(total_rows)}
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
---

# ISRO Missions Data
{banner_md}
*Part of a [dataset collection](https://huggingface.co/collections/juliensimon/space-probe-and-mission-datasets-69c3fe82d410a42b1e313167) on Hugging Face.*

## Dataset description

{DESCRIPTION}

## Configs

This dataset has four configs (tables):

### `spacecraft` -- {len(spacecraft):,} ISRO spacecraft

{_schema(SPACECRAFT_DESCRIPTIONS)}

### `launchers` -- {len(launchers):,} launch vehicles

{_schema(LAUNCHER_DESCRIPTIONS)}

### `customer_satellites` -- {len(customer_sats):,} customer satellites

{_schema(CUSTOMER_SAT_DESCRIPTIONS)}

### `centres` -- {len(centres):,} ISRO centres

{_schema(CENTRES_DESCRIPTIONS)}

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

# Customer satellites by country
import matplotlib.pyplot as plt
cdf = customer_sats.to_pandas()
top = cdf.groupby("country").size().sort_values(ascending=False).head(10)
top.plot(kind="barh")
plt.title("Top 10 Countries by ISRO-Launched Satellites")
plt.xlabel("Number of Satellites")
plt.tight_layout()
plt.show()

# PSLV missions
ldf = launchers.to_pandas()
pslv = ldf[ldf["id"].str.startswith("PSLV")]
print(f"{{len(pslv)}} PSLV missions")
```

## Data source

[ISRO API](https://isro.vercel.app/) -- community-maintained open API for ISRO spacecraft,
launchers, and mission data. Based on publicly available ISRO records.

## Related datasets

- [juliensimon/space-missions](https://huggingface.co/datasets/juliensimon/space-missions)
- [juliensimon/spacecraft-database](https://huggingface.co/datasets/juliensimon/spacecraft-database)
- [juliensimon/gcat-satellite-catalog](https://huggingface.co/datasets/juliensimon/gcat-satellite-catalog)
- [juliensimon/space-agency-database](https://huggingface.co/datasets/juliensimon/space-agency-database)

## Citation

{_citation_bibtex(HF_REPO, "ISRO Missions Data")}

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
"""
        (p.tmp_dir / "README.md").write_text(readme)

        # Upload
        upload_to_hf(
            HF_REPO, p.tmp_dir,
            f"Update ISRO missions: {len(spacecraft):,} spacecraft, "
            f"{len(launchers):,} launchers, "
            f"{len(customer_sats):,} customer satellites, "
            f"{len(centres):,} centres",
        )

    emit_output(rows=total_rows)
    print(f"Done. {total_rows:,} total rows.")


if __name__ == "__main__":
    main()
