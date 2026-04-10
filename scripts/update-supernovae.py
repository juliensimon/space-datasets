#!/usr/bin/env python3
"""Fetch the Open Supernova Catalog and upload to HF.

Primary source: GitHub bulk catalog JSON from astrocatalogs/supernovae.
The REST API at api.astrocats.space is unreliable (often returns empty
fields or times out), so we use the static catalog.json from the repo.
"""

import re
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

from dataset_images import banner_markdown, download_banner
from validate import check_dataset

CATALOG_URL = (
    "https://raw.githubusercontent.com/astrocatalogs/supernovae"
    "/master/output/catalog.json"
)
HF_REPO = "juliensimon/open-supernova-catalog"
DATASET_NAME = "supernovae"
MIN_ROWS = 50_000

EXPECTED_COLUMNS = [
    "name", "ra", "dec", "redshift", "claimed_type", "host_galaxy",
    "peak_mag", "discovery_date", "luminosity_distance_mpc", "ebv",
]


def hms_to_deg(hms: str) -> float | None:
    """Convert RA in HH:MM:SS.ss format to decimal degrees."""
    if not hms or not isinstance(hms, str):
        return None
    m = re.match(r"(\d+):(\d+):([\d.]+)", hms.strip())
    if not m:
        return None
    h, mi, s = float(m.group(1)), float(m.group(2)), float(m.group(3))
    return round((h + mi / 60 + s / 3600) * 15, 6)


def dms_to_deg(dms: str) -> float | None:
    """Convert Dec in +DD:MM:SS.ss format to decimal degrees."""
    if not dms or not isinstance(dms, str):
        return None
    m = re.match(r"([+-]?)(\d+):(\d+):([\d.]+)", dms.strip())
    if not m:
        return None
    sign = -1 if m.group(1) == "-" else 1
    d, mi, s = float(m.group(2)), float(m.group(3)), float(m.group(4))
    return round(sign * (d + mi / 60 + s / 3600), 6)


def first_value(entry: dict, key: str) -> str | None:
    """Extract the first 'value' from a catalog field array."""
    field = entry.get(key)
    if not field or not isinstance(field, list) or len(field) == 0:
        return None
    return field[0].get("value")


def main():
    # ── Fetch ────────────────────────────────────────────────────────────
    print("Downloading Open Supernova Catalog from GitHub...")
    resp = requests.get(CATALOG_URL, timeout=300)
    resp.raise_for_status()
    catalog = resp.json()
    print(f"  {len(catalog):,} entries in catalog")

    # ── Transform ────────────────────────────────────────────────────────
    print("Parsing catalog entries...")
    rows = []
    for entry in catalog:
        ra_str = first_value(entry, "ra")
        dec_str = first_value(entry, "dec")
        rows.append({
            "name": entry.get("name", ""),
            "ra_hms": ra_str,
            "dec_dms": dec_str,
            "ra": hms_to_deg(ra_str),
            "dec": dms_to_deg(dec_str),
            "redshift": first_value(entry, "redshift"),
            "claimed_type": first_value(entry, "claimedtype"),
            "host_galaxy": first_value(entry, "host"),
            "peak_mag": first_value(entry, "maxappmag"),
            "peak_abs_mag": first_value(entry, "maxabsmag"),
            "discovery_date": first_value(entry, "discoverdate"),
            "luminosity_distance_mpc": first_value(entry, "lumdist"),
            "ebv": first_value(entry, "ebv"),
            "discoverer": first_value(entry, "discoverer"),
        })
    del catalog  # free memory

    df = pd.DataFrame(rows)
    del rows

    # Numeric conversions
    for col in ["redshift", "peak_mag", "peak_abs_mag",
                "luminosity_distance_mpc", "ebv"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Parse discovery date (format: YYYY/MM/DD or YYYY/MM or YYYY)
    df["discovery_date"] = df["discovery_date"].str.replace("/", "-", regex=False)
    df["discovery_date"] = pd.to_datetime(df["discovery_date"], errors="coerce")
    df["discovery_year"] = df["discovery_date"].dt.year.astype("Int64")

    # Round floats
    for col in ["ra", "dec", "redshift", "peak_mag", "peak_abs_mag",
                "luminosity_distance_mpc", "ebv"]:
        df[col] = df[col].round(6)

    # Drop entries with no name (shouldn't happen, but be safe)
    df = df[df["name"].str.len() > 0].reset_index(drop=True)

    print(f"  {len(df):,} supernovae after parsing")

    # ── Validate ─────────────────────────────────────────────────────────
    check_dataset(
        df,
        dataset_name=DATASET_NAME,
        min_rows=MIN_ROWS,
        expected_columns=EXPECTED_COLUMNS,
        critical_columns=["name", "ra", "dec", "discovery_date"],
        max_null_pct=0.10,
    )

    # ── Stats for README ─────────────────────────────────────────────────
    n_with_redshift = int(df["redshift"].notna().sum())
    n_with_host = int(df["host_galaxy"].notna().sum())
    n_with_type = int(df["claimed_type"].notna().sum())
    n_with_coords = int(df["ra"].notna().sum())
    type_counts = df["claimed_type"].dropna().value_counts().head(10)
    type_table = "\n".join(
        f"| {t} | {c:,} |" for t, c in type_counts.items()
    )
    year_min = int(df["discovery_year"].min()) if df["discovery_year"].notna().any() else "?"
    year_max = int(df["discovery_year"].max()) if df["discovery_year"].notna().any() else "?"

    # ── Write ────────────────────────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "open_supernova_catalog.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        banner_file = download_banner("supernovae", tmp)
        banner_md = banner_markdown("supernovae", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Open Supernova Catalog"
language:
  - en
description: "All known supernovae with metadata from the Open Supernova Catalog. Updated weekly."
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - supernovae
  - transients
  - astronomy
  - open-data
  - tabular-data
  - parquet
size_categories:
  - 10K<n<100K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/open_supernova_catalog.parquet
    default: true
---

# Open Supernova Catalog
{banner_md}
*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-67c2e994a8b1a76b88ecfe22) collection on Hugging Face.*

![Update Supernovae](https://github.com/juliensimon/space-datasets/actions/workflows/update-supernovae.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.supernovae&label=updated&color=brightgreen)

All **{len(df):,}** known supernovae and supernova candidates from the
[Open Supernova Catalog](https://sne.space), spanning discoveries from
**{year_min}** to **{year_max}**.

## Dataset description

The Open Supernova Catalog (OSC) is a comprehensive, community-maintained
database of all known supernovae and supernova candidates. It aggregates
data from professional surveys (ZTF, ASAS-SN, Pan-STARRS, SDSS), amateur
discoveries, and historical records.

Each record includes sky coordinates, spectroscopic classification,
redshift, host galaxy, peak apparent magnitude, and extinction (E(B-V)).

Supernovae are among the most energetic events in the universe, releasing roughly 10^44 joules of kinetic energy and briefly outshining their entire host galaxy. They divide into two fundamental classes by physical mechanism: thermonuclear supernovae (Type Ia), in which a carbon-oxygen white dwarf is completely disrupted by runaway nuclear burning, and core-collapse supernovae (Types II, Ib, Ic, and their subtypes), in which the iron core of a massive star (>8 solar masses) collapses to form a neutron star or black hole. Type Ia supernovae serve as standardizable candles for measuring cosmological distances, providing the original evidence for the accelerating expansion of the universe and dark energy. Core-collapse supernovae are the primary sites of heavy element nucleosynthesis, enriching the interstellar medium with oxygen, silicon, calcium, and iron-group elements essential for planet formation and life.

The Open Supernova Catalog has become the standard aggregation point for supernova discoveries and metadata, incorporating data from modern time-domain surveys such as the Zwicky Transient Facility (ZTF), the All-Sky Automated Survey for Supernovae (ASAS-SN), Pan-STARRS, and the Asteroid Terrestrial-impact Last Alert System (ATLAS), as well as historical records dating back centuries. The catalog captures the explosion of discovery rates driven by wide-field CCD surveys: from a few dozen supernovae per year in the 1980s to thousands per year in the 2020s. The upcoming Vera C. Rubin Observatory's Legacy Survey of Space and Time (LSST) is expected to discover millions of supernovae, making catalogs like this essential for contextualizing and cross-referencing transient events.

The spectroscopic classification, redshift, and peak magnitude data in this catalog enable population studies of supernova rates as a function of redshift, host galaxy type, and environment. These rates constrain the delay-time distribution of Type Ia progenitors, the initial mass function of massive stars, and the star formation history of the universe.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `name` | string | Primary supernova designation (e.g., "SN 1987A", "SN2011fe", "AT2023bee"); historical SNe use "SN YYYY" format; modern transients use "AT" prefix until spectroscopically confirmed |
| `ra_hms` | string | Right ascension of the supernova in sexagesimal format (HH:MM:SS.ss); for high-z events this is the host galaxy nucleus position |
| `dec_dms` | string | Declination in sexagesimal format (+DD:MM:SS.ss) |
| `ra` | float64 | Right ascension in decimal degrees (J2000.0 ICRS); range 0–360; null for historical events without precise coordinates |
| `dec` | float64 | Declination in decimal degrees (J2000.0 ICRS); range −90 to +90; null when `ra` is null |
| `redshift` | float64 | Spectroscopic or photometric redshift of the host galaxy; range ~0.0001 (SN 1987A) to ~2 (cosmological); null for ~50% of catalog entries lacking a measured redshift |
| `claimed_type` | string | Spectroscopic classification: "Ia" (thermonuclear WD detonation, standardizable candle), "Ib" (stripped-envelope, no H, has He), "Ic" (stripped-envelope, no H or He), "II" (core collapse with H), "IIn" (core collapse with circumstellar interaction), "IIb" (transitional H+He), "SLSN-I/II" (superluminous, 10–100× normal brightness); null for unclassified candidates |
| `host_galaxy` | string | Name of the host galaxy; null for ~20% of entries |
| `peak_mag` | float64 | Peak apparent magnitude (filter unspecified); nearby bright SNe can reach magnitude ~8–10; typical survey-detected SNe: 18–22 mag; null for ~60% of entries |
| `peak_abs_mag` | float64 | Peak absolute magnitude; Type Ia: ~−19.3 mag; core-collapse: −15 to −18 mag; SLSN: −20 to −23 mag; null when redshift or peak apparent magnitude is unavailable |
| `discovery_date` | datetime | UTC date the transient was first reported to the community; format YYYY-MM-DD |
| `discovery_year` | int64 | Year of discovery; derived from `discovery_date`; null when discovery_date is unavailable |
| `luminosity_distance_mpc` | float64 | Luminosity distance in megaparsecs computed from redshift; null when redshift is unavailable |
| `ebv` | float64 | Milky Way line-of-sight dust reddening E(B-V) in magnitudes from the Schlegel/Schlafly dust maps; used to correct observed magnitudes for Galactic extinction |
| `discoverer` | string | Person, team, or survey that first reported the transient (e.g., "ZTF", "ASAS-SN", "Itagaki"); null for many historical entries |

## Quick stats

- **{len(df):,}** supernovae ({year_min}--{year_max})
- **{n_with_coords:,}** with sky coordinates
- **{n_with_redshift:,}** with redshift measurements
- **{n_with_type:,}** with spectroscopic classification
- **{n_with_host:,}** with identified host galaxy

### Top classifications

| Type | Count |
|------|-------|
{type_table}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/open-supernova-catalog", split="train")
df = ds.to_pandas()

# Type Ia supernovae with redshift
ia = df[(df["claimed_type"] == "Ia") & df["redshift"].notna()]

# Nearby supernovae (z < 0.01)
nearby = df[df["redshift"] < 0.01].sort_values("redshift")

# Discoveries per year
per_year = df["discovery_year"].dropna().value_counts().sort_index()

# Supernovae in a sky region (e.g., Virgo cluster area)
virgo = df[
    (df["ra"].between(180, 195)) & (df["dec"].between(5, 20))
]
```

## Data source

[Open Supernova Catalog](https://sne.space) via the
[astrocatalogs/supernovae](https://github.com/astrocatalogs/supernovae)
GitHub repository. The catalog aggregates data from IAU Circulars,
The Astronomer's Telegram, the Transient Name Server (TNS), and
dozens of survey pipelines.

## Update schedule

Weekly (Mondays at 07:00 UTC) via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [grb-catalog](https://huggingface.co/datasets/juliensimon/gamma-ray-bursts) — Gamma-ray burst catalog
- [exoplanet-archive](https://huggingface.co/datasets/juliensimon/nasa-exoplanets) — Confirmed exoplanets
- [quasar-catalog](https://huggingface.co/datasets/juliensimon/quasar-catalog) — Milliquas quasar catalog
- [pulsar-catalog](https://huggingface.co/datasets/juliensimon/pulsar-catalog) — ATNF pulsar catalog

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/open-supernova-catalog) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@article{{open_supernova_catalog,
  author = {{Guillochon, James and Parrent, Jerod and Kelley, Luke Zoltan and Margutti, Raffaella}},
  title = {{An Open Catalog for Supernova Data}},
  journal = {{The Astrophysical Journal}},
  year = {{2017}},
  volume = {{835}},
  number = {{1}},
  pages = {{64}},
  doi = {{10.3847/1538-4357/835/1/64}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update Open Supernova Catalog: {len(df):,} supernovae"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    print(f"rows={len(df)}")
    print("Done.")


if __name__ == "__main__":
    main()
