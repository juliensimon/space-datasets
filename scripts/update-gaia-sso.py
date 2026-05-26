#!/usr/bin/env python3
"""Fetch Gaia DR3 Solar System Objects catalog from ESA Gaia Archive and upload to HF."""

import io

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

GAIA_TAP = "https://gea.esac.esa.int/tap-server/tap/sync"
HF_REPO = "juliensimon/gaia-dr3-solar-system-objects"

# -- Column mapping --------------------------------------------------------
RENAME = {}  # Gaia archive returns snake_case columns already

# -- Column descriptions for README schema table ---------------------------
COLUMN_DESCRIPTIONS = {
    "source_id": "Gaia DR3 unique source identifier; use for cross-matching with other Gaia tables",
    "num_of_obs": "Number of Gaia field-of-view transits (observations) used for this solar system object",
    "number_mp": "Official IAU minor planet number; null for unnumbered/provisional objects",
    "denomination": "Name or provisional designation of the solar system object (e.g. 'Ceres', '2010 AB12')",
    "num_of_spectra": "Number of low-resolution reflectance spectra available from the Gaia RP spectrometer",
    "has_spectra": "True if at least one RP reflectance spectrum is available for this object",
    "is_numbered": "True if the object has an official IAU minor planet number (number_mp is not null)",
}

# -- Dataset description ----------------------------------------------------
DESCRIPTION = """\
The Gaia DR3 Solar System Objects (SSO) catalog contains over 158,000 solar system objects \
observed by ESA's Gaia mission during its third data release. The sample is dominated by \
main-belt asteroids but also includes Jupiter Trojans, near-Earth asteroids, trans-Neptunian \
objects, and comets.

For each object, Gaia collected precise astrometry across multiple field-of-view transits and, \
for a subset, obtained low-resolution reflectance spectra through the RP (Red Photometer) \
spectrometer covering roughly 374-1034 nm. This uniform all-sky survey provides a homogeneous \
photometric and spectroscopic dataset that complements ground-based catalogs such as the \
JPL Small-Body Database and the LCDB asteroid lightcurve database.

The `denomination` column links each Gaia source to the standard IAU asteroid database, \
enabling cross-matching with orbital element catalogs, taxonomic classifications, and \
physical property compilations. The `number_mp` field distinguishes officially numbered \
asteroids (those with well-determined orbits) from provisional or newly discovered objects. \
The `num_of_spectra` column identifies which objects have reflectance spectra available in \
the companion `gaiadr3.sso_reflectance_spectrum` table, enabling compositional and taxonomic \
studies across the entire main belt and beyond.

This catalog is particularly valuable for population-level studies of the asteroid belt, \
statistical comparisons of spectral classes, and astrometric refinement using Gaia's \
sub-milliarcsecond precision.
"""


def fetch_gaia_sso():
    """Fetch solar system objects from Gaia archive (single query, ~158K rows)."""
    query = "SELECT * FROM gaiadr3.sso_source ORDER BY source_id"
    print("  Fetching gaiadr3.sso_source (single query)...")
    resp = requests.post(
        GAIA_TAP,
        data={
            "REQUEST": "doQuery",
            "LANG": "ADQL",
            "FORMAT": "csv",
            "QUERY": query,
            "MAXREC": 500_000,
        },
        timeout=600,
    )
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    print(f"    got {len(df):,} rows")
    return df


def main():
    print("Fetching Gaia DR3 Solar System Objects from ESA Gaia Archive...")
    df = fetch_gaia_sso()
    print(f"  {len(df):,} raw rows")

    # Drop internal Gaia processing column
    for col in ["solution_id"]:
        if col in df.columns:
            df = df.drop(columns=[col])

    # Rename if needed (archive returns snake_case already)
    df = df.rename(columns=RENAME)

    # Type conversions -- integer columns
    for col in ["num_of_obs", "number_mp", "num_of_spectra"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    # Derived columns
    if "num_of_spectra" in df.columns:
        df["has_spectra"] = df["num_of_spectra"] > 0

    if "number_mp" in df.columns:
        df["is_numbered"] = df["number_mp"].notna()

    # Sort by source_id
    if "source_id" in df.columns:
        df = df.sort_values("source_id").reset_index(drop=True)

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Stats
    n_total = len(df)
    n_with_spectra = int(df["has_spectra"].sum()) if "has_spectra" in df.columns else 0
    n_numbered = int(df["is_numbered"].sum()) if "is_numbered" in df.columns else 0
    n_unnumbered = n_total - n_numbered
    median_obs = df["num_of_obs"].median() if "num_of_obs" in df.columns else float("nan")

    quick_stats = f"""\
- **{n_total:,}** solar system objects observed by Gaia
- **{n_with_spectra:,}** objects with RP reflectance spectra ({100*n_with_spectra/n_total:.1f}%)
- **{n_numbered:,}** officially numbered minor planets / **{n_unnumbered:,}** unnumbered
- Median number of Gaia transits per object: {median_obs:.0f}"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/gaia-dr3-solar-system-objects", split="train")
df = ds.to_pandas()

# Objects with reflectance spectra
spectra_df = df[df["has_spectra"]]
print(f"Objects with RP spectra: {len(spectra_df):,}")

# Distribution of transit counts
import matplotlib.pyplot as plt
df["num_of_obs"].clip(upper=100).hist(bins=50, log=True)
plt.xlabel("Number of Gaia transits")
plt.ylabel("Count")
plt.title("Gaia DR3 SSO: Transit count distribution")
plt.show()

# Numbered vs unnumbered breakdown
counts = df["is_numbered"].value_counts()
counts.index = ["Numbered", "Unnumbered"]
counts.plot.pie(autopct="%1.1f%%", title="IAU-numbered vs provisional objects")
plt.show()

# Cross-match with JPL SBDB by denomination
import pandas as pd
sbdb = load_dataset("juliensimon/jpl-small-body-database", split="train").to_pandas()
merged = df.merge(sbdb, left_on="denomination", right_on="full_name", how="inner")
print(f"Matched {len(merged):,} objects with JPL SBDB")
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Gaia DR3 Solar System Objects",
        description=DESCRIPTION,
        tags=["space", "gaia", "solar-system", "asteroids", "small-bodies", "esa",
              "astronomy", "open-data", "tabular-data", "parquet"],
        source_url="https://gea.esac.esa.int/archive/",
        license="other",
        license_name="cc-by-nc-3.0-igo",
        license_link="https://creativecommons.org/licenses/by-nc/3.0/igo/",
        task_categories=["tabular-classification", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA00568/PIA00568~small.jpg",
            "alt": "Asteroid 243 Ida and its moon Dactyl, imaged by NASA's Galileo spacecraft",
            "credit": "NASA/JPL",
        },
        related_datasets=[
            "juliensimon/jpl-small-body-database",
            "juliensimon/neo",
            "juliensimon/asteroid-lightcurves-lcdb",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=["num_of_obs", "number_mp", "num_of_spectra"],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="gaia_dr3_solar_system_objects.parquet",
            min_rows=100_000,
            expected_columns=["source_id", "num_of_obs", "denomination"],
            critical_columns=["source_id", "denomination"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Gaia DR3 solar system objects: {n_total:,} sources",
        )
    print("Done.")


if __name__ == "__main__":
    main()
