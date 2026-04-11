#!/usr/bin/env python3
"""Fetch OpenNGC deep-sky catalog from GitHub and upload to HF."""

import pandas as pd

from hf_dataset_utils import Pipeline

NGC_CSV_URL = "https://raw.githubusercontent.com/mattiaverga/OpenNGC/master/database_files/NGC.csv"
HF_REPO = "juliensimon/ngc-ic-catalog"

# Map OpenNGC Type codes to broad categories
_TYPE_TO_CATEGORY = {
    "G": "Galaxy",
    "GGroup": "Galaxy",
    "GPair": "Galaxy",
    "GTrpl": "Galaxy",
    "Gx": "Galaxy",
    "EmN": "Nebula",
    "HII": "Nebula",
    "Neb": "Nebula",
    "PN": "Nebula",
    "RfN": "Nebula",
    "SNR": "Nebula",
    "Cl+N": "Nebula",
    "Nova": "Nebula",
    "OCl": "Star Cluster",
    "GCl": "Star Cluster",
    "*Ass": "Star Cluster",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "name": "Object designation (e.g. 'NGC0001', 'IC1234'); the primary NGC or IC catalog number zero-padded to 4 digits",
    "type": "Morphological type code from OpenNGC classification: G=galaxy, OCl=open cluster, GCl=globular cluster, PN=planetary nebula, EmN=emission nebula, RfN=reflection nebula, SNR=supernova remnant, HII=HII region, Cl+N=cluster+nebula, *Ass=stellar association, Dup=duplicate entry",
    "object_category": "Broad category derived from type code: Galaxy, Nebula, Star Cluster, or Other; simplifies filtering for common use cases",
    "ra": "ICRS J2000.0 right ascension of the object center in sexagesimal (HH:MM:SS.s); suitable for telescope pointing",
    "dec": "ICRS J2000.0 declination of the object center in sexagesimal (+/-DD:MM:SS); suitable for telescope pointing",
    "const": "Standard 3-letter IAU constellation abbreviation (e.g., 'And' for Andromeda, 'Ori' for Orion); 88 possible values",
    "majax": "Angular size of the major axis in arcminutes; null for unresolved objects or those without reliable extent measurements",
    "minax": "Angular size of the minor axis in arcminutes; null for unresolved or circular objects",
    "posang": "Position angle of the major axis in degrees, measured east from north (0-180); null for circular or unresolved objects",
    "b_mag": "Integrated blue-band (B, ~440 nm) magnitude; brighter objects have lower values; typical NGC range 6-16; null for objects without reliable photometry",
    "v_mag": "Integrated visual-band (V, ~550 nm) magnitude; the standard optical brightness measure; typical NGC range 6-16; null for objects without reliable photometry",
    "j_mag": "Integrated near-infrared J-band (~1.25 um) magnitude from 2MASS; null if not measured",
    "h_mag": "Integrated near-infrared H-band (~1.65 um) magnitude from 2MASS; null if not measured",
    "k_mag": "Integrated near-infrared K-band (~2.17 um) magnitude from 2MASS; null if not measured",
    "surfbr": "Mean surface brightness in mag/arcsec^2; measures how spread out the object's light is; useful for observability assessment; null if not available",
    "hubble": "Hubble/de Vaucouleurs morphological classification for galaxies (e.g., 'E2' for elliptical, 'SBbc' for barred spiral); null for non-galaxies",
    "m": "Messier catalog number (e.g., 'M31'); null for objects not in the Messier catalog",
    "ngc": "Cross-referenced NGC number; null for IC-only objects",
    "ic": "Cross-referenced IC number; null for NGC-only objects",
    "common_names": "Well-known popular names (e.g., 'Andromeda Galaxy', 'Orion Nebula'); null for objects without widely-used common names",
    "identifiers": "Additional catalog cross-references (e.g., UGC, MCG, Arp numbers); null if no additional identifiers available",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Complete catalog of deep-sky objects from the OpenNGC project, covering every NGC and IC \
entry -- galaxies, nebulae, star clusters, and more.

The New General Catalogue (NGC) and Index Catalogue (IC) are the standard references for \
deep-sky objects beyond the Messier catalog. This dataset is built from the community-maintained \
OpenNGC database, which provides accurate positions, magnitudes, dimensions, and classifications \
for all NGC/IC entries.

The New General Catalogue was compiled by John Louis Emil Dreyer in 1888, consolidating and \
correcting the observations of William Herschel, his son John Herschel, and other nineteenth-century \
visual observers. The two Index Catalogues (IC I in 1895 and IC II in 1908) extended the NGC with \
additional discoveries. Together, the NGC and IC catalogs defined the standard reference system for \
deep-sky objects for over a century and remain in daily use by professional and amateur astronomers.

The objects span an extraordinary range of astrophysical phenomena: galaxies from nearby dwarfs to \
giant ellipticals, star-forming HII regions, planetary nebulae, supernova remnants, and star clusters \
ranging from young open clusters to ancient globulars. The OpenNGC project has corrected many \
historical errors and added modern multi-band photometry (B, V, J, H, K) enabling quantitative analysis.
"""


def _snake_case(col: str) -> str:
    """Convert column name to snake_case."""
    return col.strip().lower().replace(" ", "_").replace("-", "_")


def main():
    print("Fetching OpenNGC catalog...")
    df = pd.read_csv(NGC_CSV_URL, sep=";")
    print(f"  {len(df):,} objects")

    # Rename columns to snake_case
    df.columns = [_snake_case(c) for c in df.columns]

    # Add broad object_category
    df["object_category"] = df["type"].map(_TYPE_TO_CATEGORY).fillna("Other")

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_galaxies = int((df["object_category"] == "Galaxy").sum())
    n_nebulae = int((df["object_category"] == "Nebula").sum())
    n_clusters = int((df["object_category"] == "Star Cluster").sum())
    n_other = int((df["object_category"] == "Other").sum())
    n_messier = int(df["m"].notna().sum()) if "m" in df.columns else 0
    n_constellations = df["const"].nunique() if "const" in df.columns else 0

    quick_stats = f"""\
- **{n_total:,}** cataloged objects
- **{n_galaxies:,}** galaxies, **{n_nebulae:,}** nebulae, **{n_clusters:,}** star clusters, **{n_other:,}** other
- **{n_messier}** Messier objects cross-referenced
- **{n_constellations}** constellations represented"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/ngc-ic-catalog", split="train")
df = ds.to_pandas()

# All galaxies
galaxies = df[df["object_category"] == "Galaxy"]
print(f"{len(galaxies):,} galaxies")

# Messier objects
messier = df[df["m"].notna()]
print(f"{len(messier)} Messier objects")

# Brightest objects by V-mag
brightest = df.dropna(subset=["v_mag"]).nsmallest(20, "v_mag")

# Objects per constellation
import matplotlib.pyplot as plt
by_const = df["const"].value_counts().head(15)
by_const.plot.barh()
plt.xlabel("Number of Objects")
plt.ylabel("Constellation")
plt.title("NGC/IC Objects per Constellation (Top 15)")
plt.tight_layout()
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="NGC/IC Deep-Sky Object Catalog",
        description=DESCRIPTION,
        license="cc-by-sa-4.0",
        tags=["space", "ngc", "ic", "deep-sky", "nebula", "galaxy",
              "star-cluster", "astronomy", "open-data", "messier",
              "tabular-data", "parquet"],
        source_url="https://github.com/mattiaverga/OpenNGC",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA12110/PIA12110~small.jpg",
            "alt": "Hubble Deep Field revealing myriad galaxies across cosmic time",
            "credit": "NASA/ESA/STScI",
        },
        related_datasets=[
            "juliensimon/messier-catalog",
            "juliensimon/hecate-nearby-galaxies",
            "juliensimon/nebula-catalog",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=["majax", "minax", "posang", "b_mag", "v_mag",
                     "j_mag", "h_mag", "k_mag", "surfbr"],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="ngc_ic_catalog.parquet",
            min_rows=10_000,
            expected_columns=["name", "type", "ra", "dec", "const", "object_category"],
            critical_columns=["name", "type"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update NGC/IC catalog: {n_total:,} objects",
        )
    print("Done.")


if __name__ == "__main__":
    main()
