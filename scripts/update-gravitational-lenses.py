#!/usr/bin/env python3
"""Fetch the Strong Gravitational Lens Catalog (lenscat) and upload to HF.

Source: lenscat project — comprehensive catalog of confirmed and probable
strong gravitational lenses from dozens of surveys and publications.
https://github.com/lenscat/lenscat
"""

import io

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

DATA_URL = "https://raw.githubusercontent.com/lenscat/lenscat/main/lenscat/data/catalog.csv"
HF_REPO = "juliensimon/gravitational-lenses"

# ── Column mapping ───────────────────────────────────────────────────
RENAME_COLS = {
    "name": "name",
    "RA [deg]": "ra_deg",
    "DEC [deg]": "dec_deg",
    "zlens": "lens_redshift",
    "type": "lens_type",
    "grading": "grading",
    "ref": "reference",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "name": "Lens system designation (e.g. 'SL2SJ021411-040502', 'SDSS J1148+1930'); follows naming conventions from the discovery survey",
    "ra_deg": "Right ascension of the lens center, ICRS J2000.0 (degrees, 0-360)",
    "dec_deg": "Declination of the lens center, ICRS J2000.0 (degrees, -90 to +90)",
    "lens_redshift": "Spectroscopic redshift of the lensing object (galaxy or cluster); null if not measured; typical range 0.1-1.0 for galaxy lenses, 0.2-0.8 for cluster lenses",
    "lens_type": "Morphological type of the lensing mass: 'galaxy' (Einstein rings/arcs, image separation 0.5-3 arcsec) or 'cluster' (multiple arcs, separation 10-60 arcsec)",
    "grading": "Lens confidence level: 'confident' = spectroscopically confirmed or unambiguous; 'probable' = morphologically selected but not yet confirmed",
    "reference": "Discovery or catalog reference as NASA ADS bibcode or URL; links to the publication that first reported this lens system",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
A comprehensive catalog of confirmed and probable strong gravitational lenses \
compiled by the lenscat project. Covers both galaxy-scale and cluster-scale \
lenses drawn from dozens of surveys and publications.

Strong gravitational lensing occurs when a massive foreground object (a galaxy or galaxy \
cluster) bends the light of a background source so severely that multiple images, arcs, or \
Einstein rings are produced. This catalog consolidates discoveries from major surveys \
including SDSS, DES, HSC, CLASH, RELICS, and many others into a single machine-readable table.

Gravitational lensing is one of the most striking predictions of general relativity: the \
curvature of spacetime around a massive object deflects the paths of photons from background \
sources, acting as a natural telescope. In the strong lensing regime, the deflection is large \
enough to produce multiple resolved images, giant luminous arcs, or complete Einstein rings. \
The geometry of these configurations depends on the mass distribution of the lens, the distances \
involved, and the cosmological model, making strong lenses powerful tools for measuring galaxy \
and cluster masses, constraining the Hubble constant through time-delay cosmography, and probing \
the substructure of dark matter halos.

Galaxy-scale lenses, which dominate this catalog by number, typically involve a massive elliptical \
galaxy deflecting the light of a more distant galaxy or quasar. Cluster-scale lenses produce much \
larger image separations and can magnify background galaxies by factors of 10-100, enabling the \
study of intrinsically faint, high-redshift galaxies that would otherwise be undetectable.
"""


def clean_redshift(val):
    """Parse redshift values, stripping trailing '?' and converting
    placeholder strings ('-', 'measured', 'observed', 'not measured') to NaN."""
    if not isinstance(val, str):
        return val
    val = val.strip().rstrip("?")
    if val in ("-", "measured", "observed", "not measured", ""):
        return None
    try:
        return float(val)
    except ValueError:
        return None


def main():
    print("Fetching Strong Gravitational Lens Catalog (lenscat)...")
    resp = requests.get(DATA_URL, timeout=60)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    print(f"  {len(df):,} raw rows, {len(df.columns)} columns")

    # Rename columns to snake_case
    df = df.rename(columns=RENAME_COLS)

    # Clean redshift column before numeric coercion
    df["lens_redshift"] = df["lens_redshift"].apply(clean_redshift)

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Sort by RA
    df = df.sort_values("ra_deg", na_position="last").reset_index(drop=True)

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_galaxy = int((df["lens_type"] == "galaxy").sum())
    n_cluster = int((df["lens_type"] == "cluster").sum())
    n_confident = int((df["grading"] == "confident").sum())
    n_probable = int((df["grading"] == "probable").sum())
    n_has_redshift = int(df["lens_redshift"].notna().sum())
    z_min = df["lens_redshift"].min()
    z_max = df["lens_redshift"].max()
    z_median = df["lens_redshift"].median()

    quick_stats = f"""\
- **{n_total:,}** strong gravitational lenses
- **{n_galaxy:,}** galaxy-scale lenses, **{n_cluster:,}** cluster-scale lenses
- **{n_confident:,}** confident, **{n_probable:,}** probable
- **{n_has_redshift:,}** lenses with measured redshifts (range {z_min:.3f} -- {z_max:.3f}, median {z_median:.3f})"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/gravitational-lenses", split="train")
df = ds.to_pandas()

# Sky distribution
import matplotlib.pyplot as plt
plt.scatter(df["ra_deg"], df["dec_deg"], s=0.2, alpha=0.3)
plt.xlabel("RA (deg)")
plt.ylabel("Dec (deg)")
plt.title("Strong Gravitational Lenses -- Sky Distribution")
plt.gca().invert_xaxis()
plt.show()

# Redshift distribution
df["lens_redshift"].dropna().hist(bins=60)
plt.xlabel("Lens Redshift")
plt.ylabel("Count")
plt.title("Lens Redshift Distribution")
plt.show()

# Galaxy vs cluster breakdown
df["lens_type"].value_counts().plot.bar()
plt.title("Lens Type Distribution")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Strong Gravitational Lens Catalog",
        description=DESCRIPTION,
        tags=["space", "gravitational-lensing", "astronomy", "cosmology",
              "open-data", "tabular-data", "parquet"],
        source_url="https://github.com/lenscat/lenscat",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA12110/PIA12110~small.jpg",
            "alt": "Hubble Deep Field revealing myriad galaxies across cosmic time",
            "credit": "NASA/ESA/STScI",
        },
    ) as p:
        df = p.clean(
            df,
            numeric=["ra_deg", "dec_deg", "lens_redshift"],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="gravitational_lenses.parquet",
            min_rows=25_000,
            expected_columns=["name", "ra_deg", "dec_deg", "lens_type", "grading"],
            critical_columns=["name", "ra_deg", "dec_deg"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update gravitational lenses: {n_total:,} lenses",
        )
    print("Done.")


if __name__ == "__main__":
    main()
