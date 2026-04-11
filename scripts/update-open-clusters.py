#!/usr/bin/env python3
"""Fetch Hunt & Reffert Open Star Clusters from VizieR and upload to HF.

Source: Hunt, E.L. & Reffert, S. (2024), "Improving the open cluster census.
III. Using Gaia DR3", A&A, 686, A42.
VizieR catalog: J/A+A/686/A42
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/open-star-clusters"

ADQL = """\
SELECT * FROM "J/A+A/686/A42/clusters"\
"""

# ── Column mapping ───────────────────────────────────────────────────
# VizieR may return _RA/_DE or RAJ2000/DEJ2000 and various name variants
RENAME = {
    "RA_ICRS": "ra_deg",
    "RAJ2000": "ra_deg",
    "_RA": "ra_deg",
    "DE_ICRS": "dec_deg",
    "DEJ2000": "dec_deg",
    "_DE": "dec_deg",
    "dist50": "distance_pc",
    "Dist": "distance_pc",
    "Plx": "parallax_mas",
    "plx": "parallax_mas",
    "logAge50": "log_age",
    "Age": "log_age",
    "age": "log_age",
    "AV": "extinction_av",
    "Av": "extinction_av",
    "Nmemb": "n_members",
    "nmemb": "n_members",
    "N": "n_members",
    "RV": "radial_velocity_kms",
    "rv": "radial_velocity_kms",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "ra_deg": "ICRS J2000.0 right ascension of the cluster center in degrees (0-360); used for sky pointing and cross-matching with Gaia and other star catalogs",
    "dec_deg": "ICRS J2000.0 declination of the cluster center in degrees (-90 to +90); combined with ra_deg gives the full equatorial position",
    "distance_pc": "Heliocentric distance in parsecs (1 pc = 3.26 ly); typical open cluster range 100-3000 pc; derived from Gaia DR3 parallaxes or main-sequence fitting; null if distance is poorly constrained",
    "parallax_mas": "Mean cluster parallax in milliarcseconds from Gaia DR3; inverse approximately gives distance (1/parallax_mas x 1000 = distance in pc); null if not measured",
    "log_age": "Cluster age as log10(age in years); e.g. 7.0 = 10 Myr, 8.5 = 316 Myr, 9.0 = 1 Gyr; derived from Bayesian isochrone fitting using PARSEC stellar models; null if age is not well constrained",
    "extinction_av": "Line-of-sight visual extinction A_V in magnitudes; amount by which dust dims the cluster in the V-band; young embedded clusters can exceed A_V = 5; null if not measured",
    "n_members": "Number of confirmed or probable cluster members identified from Gaia proper motion and parallax criteria; null if membership study was not performed",
    "radial_velocity_kms": "Mean radial velocity of the cluster in km/s (positive = receding); measured from spectra of member stars; enables full 3D kinematics and Galactic orbit calculation; null for clusters without spectroscopic observations",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
The most comprehensive Gaia-era catalog of open star clusters, from Hunt & Reffert (2024), \
containing thousands of clusters with positions, distances, ages, and membership counts \
derived from Gaia DR3.

Open clusters are gravitationally bound groups of stars that formed together from the same \
molecular cloud. They are key tracers of Galactic structure, stellar evolution, and the \
chemical enrichment history of the Milky Way disk. This catalog represents the most complete \
census of open clusters in the Gaia era, combining automated detection with careful validation.

Open clusters are born when a giant molecular cloud fragments and collapses, producing a \
gravitationally bound group of stars that share the same age, initial chemical composition, \
and distance. This makes them natural laboratories for stellar evolution: by comparing the \
color-magnitude diagram of a cluster to theoretical isochrones, astronomers can determine \
the cluster's age, distance, and reddening simultaneously. The main-sequence turnoff point \
-- the luminosity at which stars are just leaving the hydrogen-burning main sequence -- \
shifts to fainter magnitudes with increasing age, providing a reliable chronometer spanning \
from a few million years (for clusters still embedded in their birth clouds) to several \
billion years (for ancient survivors like NGC 6791).

The Hunt & Reffert (2024) catalog represents a major advance over earlier compilations. \
Using Gaia DR3 astrometry, the authors applied the HDBSCAN clustering algorithm to identify \
overdensities in the five-dimensional space of sky position, parallax, and proper motion, \
then validated each candidate through isochrone fitting. This approach recovers not only the \
well-known clusters from classical catalogs (Dias, MWSC, Kharchenko) but also hundreds of \
previously unknown, sparse, or partially dissolved associations that are invisible in \
two-dimensional sky projections but clearly distinct in astrometric phase space.

Open clusters are the primary tracers of the Milky Way's spiral arm structure, radial \
metallicity gradient, and age-metallicity relation. Young clusters (< 10 Myr) delineate \
the current loci of spiral arms, while intermediate-age and old clusters map the disk's \
dynamical heating and radial migration history.
"""


def main():
    print("Fetching Hunt & Reffert open clusters from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} open clusters")

    # Rename columns
    df = df.rename(columns={k: v for k, v in RENAME.items() if k in df.columns})

    # Snake-case remaining columns
    already_renamed = set(RENAME.values())
    snake_map = {}
    for col in df.columns:
        if col not in already_renamed:
            snake = col.replace(" ", "_").replace("-", "_").lower()
            if snake != col:
                snake_map[col] = snake
    if snake_map:
        df = df.rename(columns=snake_map)

    # Drop VizieR internal columns
    for col in ["recno", "More", "SimbadName"]:
        if col in df.columns:
            df = df.drop(columns=[col])

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_with_rv = int(df["radial_velocity_kms"].notna().sum()) if "radial_velocity_kms" in df.columns else 0
    n_with_age = int(df["log_age"].notna().sum()) if "log_age" in df.columns else 0
    n_nearby = int((df["distance_pc"] < 500).sum()) if "distance_pc" in df.columns else 0
    median_dist = df["distance_pc"].median() if "distance_pc" in df.columns else 0

    quick_stats = f"""\
- **{n_total:,}** open clusters
- **{n_with_age:,}** with age estimates
- **{n_with_rv:,}** with radial velocities
- **{n_nearby:,}** within 500 pc of the Sun
- Median distance: {median_dist:.0f} pc"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/open-star-clusters", split="train")
df = ds.to_pandas()

# Nearby clusters (< 500 pc)
nearby = df[df["distance_pc"] < 500].sort_values("distance_pc")
print(f"{len(nearby):,} clusters within 500 pc")

# Age distribution
import matplotlib.pyplot as plt
df["log_age"].dropna().hist(bins=40)
plt.xlabel("log(Age / yr)")
plt.ylabel("Count")
plt.title("Open Cluster Age Distribution")
plt.show()

# Distance vs age
valid = df.dropna(subset=["distance_pc", "log_age"])
plt.scatter(valid["log_age"], valid["distance_pc"], s=2, alpha=0.4)
plt.xlabel("log(Age / yr)")
plt.ylabel("Distance (pc)")
plt.title("Open Cluster Distance vs Age")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Open Star Clusters (Hunt & Reffert 2024)",
        description=DESCRIPTION,
        tags=["space", "star-cluster", "open-cluster", "gaia", "astronomy",
              "open-data", "tabular-data", "parquet"],
        source_url="https://vizier.cds.unistra.fr/viz-bin/VizieR-3?-source=J/A+A/686/A42",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e000191/GSFC_20171208_Archive_e000191~medium.jpg",
            "alt": "A youthful globular star cluster observed by the Hubble Space Telescope",
            "credit": "NASA/ESA/Hubble",
        },
        related_datasets=[
            "juliensimon/gcvs-variable-stars",
            "juliensimon/pulsar-catalog",
            "juliensimon/globular-star-clusters",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "ra_deg", "dec_deg", "distance_pc", "parallax_mas",
                "log_age", "extinction_av", "n_members", "radial_velocity_kms",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="open_star_clusters.parquet",
            min_rows=5000,
            expected_columns=["ra_deg", "dec_deg"],
            critical_columns=["ra_deg", "dec_deg"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update open star clusters: {n_total:,} clusters",
        )
    print("Done.")


if __name__ == "__main__":
    main()
