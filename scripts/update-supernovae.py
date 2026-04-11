#!/usr/bin/env python3
"""Fetch the Open Supernova Catalog and upload to HF.

Primary source: GitHub bulk catalog JSON from astrocatalogs/supernovae.
The REST API at api.astrocats.space is unreliable (often returns empty
fields or times out), so we use the static catalog.json from the repo.
"""

import re

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

CATALOG_URL = (
    "https://raw.githubusercontent.com/astrocatalogs/supernovae"
    "/master/output/catalog.json"
)
HF_REPO = "juliensimon/open-supernova-catalog"

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "name": "Primary supernova designation (e.g., 'SN 1987A', 'SN2011fe', 'AT2023bee'); historical SNe use 'SN YYYY' format; modern transients use 'AT' prefix until spectroscopically confirmed",
    "ra_hms": "Right ascension in sexagesimal format (HH:MM:SS.ss); for high-z events this is the host galaxy nucleus position",
    "dec_dms": "Declination in sexagesimal format (+DD:MM:SS.ss)",
    "ra": "Right ascension in decimal degrees (J2000.0 ICRS, 0-360); null for historical events without precise coordinates",
    "dec": "Declination in decimal degrees (J2000.0 ICRS, -90 to +90); null when ra is null",
    "redshift": "Spectroscopic or photometric redshift of the host galaxy; range ~0.0001 (SN 1987A) to ~2 (cosmological); null for ~50% of catalog entries",
    "claimed_type": "Spectroscopic classification: 'Ia' (thermonuclear WD detonation), 'Ib' (stripped-envelope, no H, has He), 'Ic' (stripped-envelope, no H or He), 'II' (core collapse with H), 'IIn' (with circumstellar interaction), 'IIb' (transitional), 'SLSN-I/II' (superluminous); null for unclassified candidates",
    "host_galaxy": "Name of the host galaxy; null for ~20% of entries",
    "peak_mag": "Peak apparent magnitude (filter unspecified); nearby bright SNe can reach mag ~8-10; typical survey-detected: 18-22 mag; null for ~60% of entries",
    "peak_abs_mag": "Peak absolute magnitude; Type Ia: ~-19.3; core-collapse: -15 to -18; SLSN: -20 to -23; null when redshift or peak apparent magnitude is unavailable",
    "discovery_date": "UTC date the transient was first reported; format YYYY-MM-DD",
    "discovery_year": "Year of discovery derived from discovery_date; null when discovery_date is unavailable",
    "luminosity_distance_mpc": "Luminosity distance in megaparsecs computed from redshift; null when redshift is unavailable",
    "ebv": "Milky Way line-of-sight dust reddening E(B-V) in magnitudes from Schlegel/Schlafly dust maps; used to correct observed magnitudes for Galactic extinction",
    "discoverer": "Person, team, or survey that first reported the transient (e.g., 'ZTF', 'ASAS-SN', 'Itagaki'); null for many historical entries",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
All known supernovae and supernova candidates from the Open Supernova Catalog, spanning \
discoveries from the earliest historical records to the modern survey era.

The Open Supernova Catalog (OSC) is a comprehensive, community-maintained database \
aggregating data from professional surveys (ZTF, ASAS-SN, Pan-STARRS, SDSS), amateur \
discoveries, and historical records. Each record includes sky coordinates, spectroscopic \
classification, redshift, host galaxy, peak apparent magnitude, and extinction E(B-V).

Supernovae are among the most energetic events in the universe, releasing roughly 10^44 \
joules of kinetic energy and briefly outshining their entire host galaxy. They divide into \
two fundamental classes: thermonuclear supernovae (Type Ia), in which a carbon-oxygen white \
dwarf is disrupted by runaway nuclear burning, and core-collapse supernovae (Types II, Ib, \
Ic), in which the iron core of a massive star (>8 solar masses) collapses to form a neutron \
star or black hole. Type Ia supernovae serve as standardizable candles for measuring \
cosmological distances, providing the original evidence for dark energy.
"""


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

    # Drop entries with no name
    df = df[df["name"].str.len() > 0].reset_index(drop=True)

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    print(f"  {len(df):,} supernovae after parsing")

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
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

    quick_stats = f"""\
- **{n_total:,}** supernovae ({year_min}--{year_max})
- **{n_with_coords:,}** with sky coordinates
- **{n_with_redshift:,}** with redshift measurements
- **{n_with_type:,}** with spectroscopic classification
- **{n_with_host:,}** with identified host galaxy

### Top classifications

| Type | Count |
|------|-------|
{type_table}"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/open-supernova-catalog", split="train")
df = ds.to_pandas()

# Type Ia supernovae with redshift
ia = df[(df["claimed_type"] == "Ia") & df["redshift"].notna()]

# Nearby supernovae (z < 0.01)
nearby = df[df["redshift"] < 0.01].sort_values("redshift")

# Discoveries per year
import matplotlib.pyplot as plt
per_year = df["discovery_year"].dropna().value_counts().sort_index()
per_year.plot()
plt.xlabel("Year")
plt.ylabel("Discoveries")
plt.title("Supernova Discoveries per Year")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Open Supernova Catalog",
        description=DESCRIPTION,
        tags=["space", "supernovae", "transients", "astronomy",
              "open-data", "tabular-data", "parquet"],
        source_url="https://github.com/astrocatalogs/supernovae",
        task_categories=["tabular-classification", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA03606/PIA03606~small.jpg",
            "alt": "The Crab Nebula, remnant of a supernova explosion",
            "credit": "NASA/ESA/Hubble",
        },
        related_datasets=[
            "juliensimon/pantheon-plus-sne-ia",
            "juliensimon/supernova-remnants",
            "juliensimon/gamma-ray-bursts",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=["ra", "dec", "redshift", "peak_mag", "peak_abs_mag",
                     "luminosity_distance_mpc", "ebv"],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="open_supernova_catalog.parquet",
            min_rows=50_000,
            expected_columns=["name", "ra", "dec", "redshift", "claimed_type",
                             "host_galaxy", "peak_mag", "discovery_date",
                             "luminosity_distance_mpc", "ebv"],
            critical_columns=["name", "ra", "dec", "discovery_date"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Open Supernova Catalog: {n_total:,} supernovae",
        )
    print("Done.")


if __name__ == "__main__":
    main()
