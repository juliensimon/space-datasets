#!/usr/bin/env python3
"""Fetch the Open TDE Catalog (tidal disruption events) and upload to HF.

Primary source: GitHub bulk catalog JSON from astrocatalogs/tidaldisruptions.
The REST API at api.astrocats.space is unreliable (returns empty fields),
so we use the static catalog.json from the repo — same approach as the
Open Supernova Catalog pipeline.
"""

import re

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

CATALOG_URL = (
    "https://raw.githubusercontent.com/astrocatalogs/tidaldisruptions"
    "/master/output/catalog.json"
)
HF_REPO = "juliensimon/otter-tde-catalog"
MIN_ROWS = 80

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "name": "Primary TDE designation (e.g., 'ASASSN-14li', 'AT2019qiz', 'Swift J1644+57'); modern transients use AT prefix until spectroscopically confirmed",
    "aliases": "Comma-separated list of alternative designations from different surveys or reporting telegrams; null if no aliases recorded",
    "ra_hms": "Right ascension of the TDE / host nucleus in sexagesimal format (HH:MM:SS.ss)",
    "dec_dms": "Declination of the TDE / host nucleus in sexagesimal format (+DD:MM:SS.ss)",
    "ra": "Right ascension in decimal degrees (J2000.0 ICRS); range 0-360; null for ~10% of entries lacking coordinates",
    "dec": "Declination in decimal degrees (J2000.0 ICRS); range -90 to +90; null when ra is null",
    "redshift": "Host galaxy spectroscopic redshift; TDE surveys typically probe 0.01 < z < 1; null for ~40% of entries; range ~0.001 (very nearby) to ~1",
    "claimed_type": "Spectroscopic classification: 'TDE' (confirmed), 'TDE?' (candidate), 'TDE-H' (hydrogen-dominated spectrum), 'TDE-He' (helium-dominated), 'TDE-H+He' (mixed), 'TDE-featureless'; null for unclassified candidates",
    "host_galaxy": "Name of the host galaxy where the TDE occurred; TDEs preferentially occur in post-starburst ('E+A') galaxies; null for ~30% of entries",
    "host_ra": "Host galaxy nucleus right ascension in decimal degrees; may differ slightly from TDE position for well-resolved hosts",
    "host_dec": "Host galaxy nucleus declination in decimal degrees",
    "host_offset_arcsec": "Angular offset between the TDE position and the host nucleus in arcseconds; genuine TDEs should be coincident with the nucleus (offset < 1 arcsec for high-z events); null for most entries",
    "peak_mag": "Peak apparent magnitude (filter unspecified, typically optical/UV); null for ~60% of entries",
    "peak_abs_mag": "Peak absolute magnitude; typical TDE: -17 to -21 mag; null for entries lacking redshift or peak apparent magnitude",
    "peak_date": "UTC date of peak brightness; null for events where the light curve peak was not well-constrained",
    "discovery_date": "UTC date the transient was first reported; format YYYY-MM-DD",
    "discovery_year": "Year of discovery; derived from discovery_date; null when discovery_date is unavailable",
    "luminosity_distance_mpc": "Luminosity distance in megaparsecs, computed from redshift; null when redshift is unavailable",
    "velocity_km_s": "Host galaxy recession velocity in km/s (v = cz); null when redshift is unavailable",
    "ebv": "Milky Way line-of-sight dust reddening E(B-V) in magnitudes from the Schlegel/Schlafly dust maps; used to correct observed magnitudes for extinction",
    "instruments": "Instruments or facilities used for observations (e.g., 'ZTF', 'Swift-XRT', 'SDSS'); null for many entries",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
All known tidal disruption events (TDEs) from the Open TDE Catalog — stars \
torn apart by supermassive black holes.

A tidal disruption event (TDE) occurs when a star passes close enough to a \
supermassive black hole to be ripped apart by tidal forces, producing a \
luminous flare visible across the electromagnetic spectrum. The Open TDE \
Catalog aggregates all known TDE candidates with coordinates, redshifts, \
host galaxy identifications, and peak magnitudes.

Tidal disruption events provide a unique laboratory for studying supermassive \
black holes (SMBHs) that are otherwise quiescent and therefore undetectable. \
When a star on a low-angular-momentum orbit enters the tidal radius of an \
SMBH, the differential gravitational force across the star exceeds its \
self-gravity, shredding it into a stream of debris. Roughly half of this \
material becomes bound and accretes onto the black hole, producing a luminous \
flare that peaks in the UV/optical for lower-mass black holes (10^6--10^7 \
solar masses) and in the soft X-ray band for more massive ones. The light \
curve rise time, peak luminosity, and late-time decay rate (classically \
predicted to follow a t^(-5/3) power law) encode the black hole mass, the \
stellar mass and structure, and the orbital geometry.

The spectroscopic classification of TDEs into hydrogen-rich (TDE-H), \
helium-rich (TDE-He), and mixed subtypes reflects the composition of the \
disrupted star and the complex reprocessing of emission in the debris stream \
and outflows. Relativistic TDEs -- such as Swift J1644+57 -- launch powerful \
jets detectable at radio through hard X-ray wavelengths, providing probes of \
jet formation physics analogous to active galactic nuclei but in a \
time-resolved, 'clean' environment. The host galaxy properties (mass, \
morphology, nuclear activity) are critical for understanding the SMBH \
occupation fraction and the stellar dynamics that deliver stars to disruption \
orbits, with TDEs preferentially occurring in post-starburst ('E+A') \
galaxies for reasons that remain actively debated.
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

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    print(f"  {len(df):,} tidal disruption events after parsing")

    # ── Domain-specific stats for README ─────────────────────────────
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

    quick_stats = f"""\
- **{len(df):,}** tidal disruption events ({year_min}--{year_max})
- **{n_with_coords:,}** with sky coordinates
- **{n_with_redshift:,}** with redshift measurements
- **{n_with_type:,}** with spectroscopic classification
- **{n_with_host:,}** with identified host galaxy
- **{n_with_peak:,}** with peak magnitude

### Classifications

| Type | Count |
|------|-------|
{type_table}"""

    usage = """\
```python
from datasets import load_dataset
import matplotlib.pyplot as plt

ds = load_dataset("juliensimon/otter-tde-catalog", split="train")
df = ds.to_pandas()

# All confirmed TDEs
confirmed = df[df["claimed_type"] == "TDE"]

# TDEs with redshift
with_z = df[df["redshift"].notna()].sort_values("redshift")

# Nearby TDEs (z < 0.05)
nearby = df[df["redshift"] < 0.05].sort_values("redshift")

# Discoveries per year
per_year = df["discovery_year"].dropna().value_counts().sort_index()
plt.figure(figsize=(10, 5))
plt.bar(per_year.index, per_year.values, color="steelblue")
plt.xlabel("Year")
plt.ylabel("Number of TDEs discovered")
plt.title("TDE Discoveries per Year")
plt.tight_layout()
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="OTTER TDE Catalog",
        description=DESCRIPTION,
        tags=["space", "tidal-disruption", "black-holes", "transients",
              "astronomy", "open-data", "tabular-data", "parquet"],
        source_url="https://github.com/astrocatalogs/tidaldisruptions",
        task_categories=["tabular-classification", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-67c2e994a8b1a76b88ecfe22",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA03606/PIA03606~small.jpg",
            "alt": "The Crab Nebula, a supernova remnant",
            "credit": "NASA/ESA/Hubble",
        },
        related_datasets=[
            "juliensimon/open-supernova-catalog",
            "juliensimon/gamma-ray-bursts",
            "juliensimon/nasa-exoplanets",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=["redshift", "peak_mag", "peak_abs_mag",
                     "luminosity_distance_mpc", "velocity_km_s",
                     "ebv", "host_offset_arcsec",
                     "ra", "dec", "host_ra", "host_dec"],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="otter_tde_catalog.parquet",
            min_rows=MIN_ROWS,
            expected_columns=["name", "ra", "dec", "redshift", "claimed_type",
                              "host_galaxy", "peak_mag", "discovery_date",
                              "luminosity_distance_mpc", "ebv"],
            critical_columns=["name"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update OTTER TDE Catalog: {len(df):,} tidal disruption events",
        )
    print("Done.")


if __name__ == "__main__":
    main()
