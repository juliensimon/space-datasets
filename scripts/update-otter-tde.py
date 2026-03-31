#!/usr/bin/env python3
"""Fetch the Open TDE Catalog (tidal disruption events) and upload to HF.

Primary source: GitHub bulk catalog JSON from astrocatalogs/tidaldisruptions.
The REST API at api.astrocats.space is unreliable (returns empty fields),
so we use the static catalog.json from the repo — same approach as the
Open Supernova Catalog pipeline.
"""

import re
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset

CATALOG_URL = (
    "https://raw.githubusercontent.com/astrocatalogs/tidaldisruptions"
    "/master/output/catalog.json"
)
HF_REPO = "juliensimon/otter-tde-catalog"
DATASET_NAME = "otter-tde"
MIN_ROWS = 80


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
    print("Downloading Open TDE Catalog from GitHub...")
    resp = requests.get(CATALOG_URL, timeout=120)
    resp.raise_for_status()
    catalog = resp.json()
    print(f"  {len(catalog):,} entries in raw catalog")

    # ── Transform ────────────────────────────────────────────────────────
    print("Parsing catalog entries...")
    rows = []
    for entry in catalog:
        name = entry.get("name", "")
        # Skip the bogus "---" entry (aggregate dump of recent transients)
        if not name or name == "---":
            continue

        ra_str = first_value(entry, "ra")
        dec_str = first_value(entry, "dec")

        # Clean HTML entities from host names (e.g., &#8209; non-breaking hyphen)
        host = first_value(entry, "host")
        if host:
            host = host.replace("&#8209;", "-").replace("&#8211;", "-")

        rows.append({
            "name": name,
            "aliases": ", ".join(
                a["value"] for a in entry.get("alias", [])
                if a.get("value") and a["value"] != name
            ) or None,
            "ra_hms": ra_str,
            "dec_dms": dec_str,
            "ra": hms_to_deg(ra_str),
            "dec": dms_to_deg(dec_str),
            "redshift": first_value(entry, "redshift"),
            "claimed_type": first_value(entry, "claimedtype"),
            "host_galaxy": host,
            "host_ra": hms_to_deg(first_value(entry, "hostra")),
            "host_dec": dms_to_deg(first_value(entry, "hostdec")),
            "host_offset_arcsec": first_value(entry, "hostoffsetang"),
            "peak_mag": first_value(entry, "maxappmag"),
            "peak_abs_mag": first_value(entry, "maxabsmag"),
            "peak_date": first_value(entry, "maxdate"),
            "discovery_date": first_value(entry, "discoverdate"),
            "luminosity_distance_mpc": first_value(entry, "lumdist"),
            "velocity_km_s": first_value(entry, "velocity"),
            "ebv": first_value(entry, "ebv"),
            "instruments": entry.get("instruments") if isinstance(entry.get("instruments"), str) else None,
        })
    del catalog

    df = pd.DataFrame(rows)
    del rows

    # Numeric conversions
    for col in ["redshift", "peak_mag", "peak_abs_mag",
                "luminosity_distance_mpc", "velocity_km_s",
                "ebv", "host_offset_arcsec"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Parse discovery date (format: YYYY/MM/DD or YYYY/MM or YYYY)
    df["discovery_date"] = df["discovery_date"].str.replace("/", "-", regex=False)
    df["discovery_date"] = pd.to_datetime(df["discovery_date"], errors="coerce")
    df["discovery_year"] = df["discovery_date"].dt.year.astype("Int64")

    # Parse peak date
    df["peak_date"] = df["peak_date"].str.replace("/", "-", regex=False)
    df["peak_date"] = pd.to_datetime(df["peak_date"], errors="coerce")

    # Round floats
    for col in ["ra", "dec", "host_ra", "host_dec", "redshift",
                "peak_mag", "peak_abs_mag", "luminosity_distance_mpc",
                "velocity_km_s", "ebv", "host_offset_arcsec"]:
        if col in df.columns:
            df[col] = df[col].round(6)

    # Drop entries with no name
    df = df[df["name"].str.len() > 0].reset_index(drop=True)

    print(f"  {len(df):,} tidal disruption events after parsing")

    # ── Validate ─────────────────────────────────────────────────────────
    check_dataset(
        df,
        dataset_name=DATASET_NAME,
        min_rows=MIN_ROWS,
        expected_columns=EXPECTED_COLUMNS,
        critical_columns=["name"],
        max_null_pct=0.30,
    )

    # ── Stats for README ─────────────────────────────────────────────────
    n_with_redshift = int(df["redshift"].notna().sum())
    n_with_host = int(df["host_galaxy"].notna().sum())
    n_with_type = int(df["claimed_type"].notna().sum())
    n_with_coords = int(df["ra"].notna().sum())
    n_with_peak = int(df["peak_mag"].notna().sum())

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

        out = data_dir / "otter_tde_catalog.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.2f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "OTTER TDE Catalog"
language:
  - en
description: "Tidal disruption events (TDEs) from the Open TDE Catalog — stars torn apart by black holes."
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - tidal-disruption
  - black-holes
  - transients
  - astronomy
  - open-data
  - tabular-data
  - parquet
size_categories:
  - n<1K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/otter_tde_catalog.parquet
    default: true
---

# OTTER TDE Catalog

*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-67c2e994a8b1a76b88ecfe22) collection on Hugging Face.*

All **{len(df):,}** known tidal disruption events (TDEs) from the
[Open TDE Catalog](https://github.com/astrocatalogs/tidaldisruptions),
spanning discoveries from **{year_min}** to **{year_max}**.

## Dataset description

A tidal disruption event (TDE) occurs when a star passes close enough to a
supermassive black hole to be ripped apart by tidal forces, producing a
luminous flare visible across the electromagnetic spectrum. The Open TDE
Catalog aggregates all known TDE candidates with coordinates, redshifts,
host galaxy identifications, and peak magnitudes.

Each record includes sky coordinates, spectroscopic classification,
redshift, host galaxy, peak apparent and absolute magnitude, and
Milky Way extinction (E(B-V)).

Tidal disruption events provide a unique laboratory for studying supermassive black holes (SMBHs) that are otherwise quiescent and therefore undetectable. When a star on a low-angular-momentum orbit enters the tidal radius of an SMBH, the differential gravitational force across the star exceeds its self-gravity, shredding it into a stream of debris. Roughly half of this material becomes bound and accretes onto the black hole, producing a luminous flare that peaks in the UV/optical for lower-mass black holes (10^6--10^7 solar masses) and in the soft X-ray band for more massive ones. The light curve rise time, peak luminosity, and late-time decay rate (classically predicted to follow a t^(-5/3) power law) encode the black hole mass, the stellar mass and structure, and the orbital geometry.

The spectroscopic classification of TDEs into hydrogen-rich (TDE-H), helium-rich (TDE-He), and mixed subtypes reflects the composition of the disrupted star and the complex reprocessing of emission in the debris stream and outflows. Relativistic TDEs -- such as Swift J1644+57 -- launch powerful jets detectable at radio through hard X-ray wavelengths, providing probes of jet formation physics analogous to active galactic nuclei but in a time-resolved, "clean" environment. The host galaxy properties (mass, morphology, nuclear activity) are critical for understanding the SMBH occupation fraction and the stellar dynamics that deliver stars to disruption orbits, with TDEs preferentially occurring in post-starburst ("E+A") galaxies for reasons that remain actively debated.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `name` | string | Primary name (e.g., "ASASSN-14li", "Swift J1644+57") |
| `aliases` | string | Alternative designations (comma-separated) |
| `ra_hms` | string | Right ascension in HH:MM:SS.ss format |
| `dec_dms` | string | Declination in +DD:MM:SS.ss format |
| `ra` | float64 | Right ascension in decimal degrees |
| `dec` | float64 | Declination in decimal degrees |
| `redshift` | float64 | Spectroscopic redshift |
| `claimed_type` | string | Classification (TDE, TDE?, TDE-H, TDE-He, etc.) |
| `host_galaxy` | string | Host galaxy name |
| `host_ra` | float64 | Host galaxy RA in decimal degrees |
| `host_dec` | float64 | Host galaxy Dec in decimal degrees |
| `host_offset_arcsec` | float64 | Angular offset from host nucleus (arcsec) |
| `peak_mag` | float64 | Peak apparent magnitude |
| `peak_abs_mag` | float64 | Peak absolute magnitude |
| `peak_date` | datetime | Date of peak brightness |
| `discovery_date` | datetime | Date of discovery |
| `discovery_year` | int64 | Year of discovery |
| `luminosity_distance_mpc` | float64 | Luminosity distance in Mpc |
| `velocity_km_s` | float64 | Recession velocity in km/s |
| `ebv` | float64 | Milky Way E(B-V) extinction |
| `instruments` | string | Instruments used for observations |

## Quick stats

- **{len(df):,}** tidal disruption events ({year_min}--{year_max})
- **{n_with_coords:,}** with sky coordinates
- **{n_with_redshift:,}** with redshift measurements
- **{n_with_type:,}** with spectroscopic classification
- **{n_with_host:,}** with identified host galaxy
- **{n_with_peak:,}** with peak magnitude

### Classifications

| Type | Count |
|------|-------|
{type_table}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/otter-tde-catalog", split="train")
df = ds.to_pandas()

# All confirmed TDEs
confirmed = df[df["claimed_type"] == "TDE"]

# TDEs with redshift
with_z = df[df["redshift"].notna()].sort_values("redshift")

# Nearby TDEs (z < 0.05)
nearby = df[df["redshift"] < 0.05].sort_values("redshift")

# TDEs with peak magnitude
bright = df[df["peak_mag"].notna()].sort_values("peak_mag")

# Discoveries per year
per_year = df["discovery_year"].dropna().value_counts().sort_index()
```

## Data source

[Open TDE Catalog](https://github.com/astrocatalogs/tidaldisruptions) via
the [astrocatalogs](https://github.com/astrocatalogs) GitHub organization.
The catalog aggregates data from ASAS-SN, ZTF, Swift, XMM-Newton, SDSS,
and the astronomical literature.

## Related datasets

- [open-supernova-catalog](https://huggingface.co/datasets/juliensimon/open-supernova-catalog) — Open Supernova Catalog
- [grb-catalog](https://huggingface.co/datasets/juliensimon/grb-catalog) — Gamma-ray burst catalog
- [exoplanet-archive](https://huggingface.co/datasets/juliensimon/exoplanet-archive) — Confirmed exoplanets

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

Static dataset — uploaded manually (only ~30 new TDEs per year).

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/otter-tde-catalog) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@article{{open_tde_catalog,
  author = {{Guillochon, James and Parrent, Jerod and Kelley, Luke Zoltan and Margutti, Raffaella}},
  title = {{An Open Catalog for Supernova Data}},
  journal = {{The Astrophysical Journal}},
  year = {{2017}},
  volume = {{835}},
  number = {{1}},
  pages = {{64}},
  doi = {{10.3847/1538-4357/835/1/64}},
  note = {{The TDE catalog uses the same astrocatalogs infrastructure}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update OTTER TDE Catalog: {len(df):,} tidal disruption events"
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
