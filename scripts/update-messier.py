#!/usr/bin/env python3
"""Fetch the Messier catalog (110 deep-sky objects) from SIMBAD and upload to HF.

Source: SIMBAD astronomical database -- the complete Messier catalog of
galaxies, nebulae, and star clusters visible from the Northern Hemisphere.
"""

import io

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

HF_REPO = "juliensimon/messier-catalog"

SIMBAD_TAP = "https://simbad.u-strasbg.fr/simbad/sim-tap/sync"

ADQL = """SELECT main_id, ra, dec, otype AS object_type,
       galdim_majaxis AS major_axis_arcmin,
       galdim_minaxis AS minor_axis_arcmin
FROM basic
WHERE main_id LIKE 'M  %' OR main_id LIKE 'M %'
ORDER BY main_id"""

MESSIER_TYPES = {
    "GlC": "Globular Cluster",
    "OpC": "Open Cluster",
    "HII": "HII Region",
    "PN": "Planetary Nebula",
    "SNR": "Supernova Remnant",
    "G": "Galaxy",
    "AGN": "Active Galaxy",
    "Sy2": "Seyfert Galaxy",
    "GiG": "Galaxy in Group",
    "GiC": "Galaxy in Cluster",
    "As*": "Stellar Association",
    "Cl*": "Star Cluster",
    "RNe": "Reflection Nebula",
    "DNe": "Dark Nebula",
    "EmO": "Emission Object",
    "ISM": "Interstellar Medium",
    "Rad": "Radio Source",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "messier_id": "Messier catalog designation with space separator (e.g. 'M 1', 'M 110'); used as primary label for the 110 canonical deep-sky objects",
    "messier_number": "Numeric Messier catalog index; range 1-110; all 110 canonical objects included",
    "name": "Primary SIMBAD resolved name (e.g. 'NGC 224' for M31, 'Crab Nebula' for M1); may be an NGC/IC number or common name",
    "ra_deg": "Right ascension in decimal degrees, ICRS J2000.0; range 0-360",
    "dec_deg": "Declination in decimal degrees, ICRS J2000.0; range -90 to +90",
    "object_type": "Raw SIMBAD object type code (e.g. 'GlC' = globular cluster, 'G' = galaxy, 'SNR' = supernova remnant, 'OpC' = open cluster, 'HII' = emission nebula, 'PN' = planetary nebula)",
    "object_category": "Human-readable category derived from SIMBAD type: 'Galaxy', 'Globular Cluster', 'Open Cluster', 'Planetary Nebula', 'Supernova Remnant', etc.",
    "major_axis_arcmin": "Major axis apparent angular size in arcminutes; range ~1 arcmin (M76) to ~95 arcmin (M31 Andromeda Galaxy); null for point-like or unresolved objects",
    "minor_axis_arcmin": "Minor axis apparent angular size in arcminutes; null for circular or point-like objects",
}

# ── Dataset description ────────────────────────────────────────
DESCRIPTION = """\
The complete Messier catalog of 110 deep-sky objects -- galaxies, nebulae, and \
star clusters visible from the Northern Hemisphere. From SIMBAD.

The Messier catalog holds a singular place in the history of astronomy. Charles Messier, an \
18th-century French comet hunter, compiled this list of "nebulous objects" specifically to \
avoid confusing them with comets during his searches. Ironically, the catalog he intended as \
a nuisance list became one of the most celebrated collections in astronomy, encompassing some \
of the most spectacular and scientifically important objects visible from the Northern \
Hemisphere. The 110 entries span nearly every major class of deep-sky object: giant elliptical \
and spiral galaxies, globular and open star clusters, planetary nebulae, supernova remnants, \
and star-forming regions.

Many Messier objects are cornerstones of modern astrophysics. M 31 (the Andromeda Galaxy) is \
the nearest large spiral galaxy to the Milky Way and the object that first demonstrated the \
existence of "island universes" beyond our own Galaxy. M 1 (the Crab Nebula) is the remnant \
of the supernova of 1054 AD and hosts one of the most studied pulsars in the sky. M 87 harbors \
the first black hole ever directly imaged by the Event Horizon Telescope. Globular clusters \
like M 13 and M 3 contain some of the oldest stars in the universe and constrain the age of \
the Milky Way.

Despite its small size, the Messier catalog remains the standard introduction to deep-sky \
observing and is widely used in education, outreach, and the annual "Messier Marathon" -- an \
attempt to observe all 110 objects in a single night near the spring equinox.
"""


def main():
    print("Fetching Messier catalog from SIMBAD...")

    resp = requests.get(SIMBAD_TAP, params={
        "REQUEST": "doQuery",
        "LANG": "ADQL",
        "FORMAT": "csv",
        "QUERY": ADQL,
    }, timeout=60)
    resp.raise_for_status()

    df = pd.read_csv(io.StringIO(resp.text))
    print(f"  {len(df)} raw objects from SIMBAD")

    df = df.rename(columns={
        "main_id": "name",
        "ra": "ra_deg",
        "dec": "dec_deg",
        "object_type": "object_type",
        "major_axis_arcmin": "major_axis_arcmin",
        "minor_axis_arcmin": "minor_axis_arcmin",
    })

    # Filter to actual Messier objects (M 1 through M 110)
    df["messier_number"] = df["name"].str.extract(r'^M\s+(\d+)$').astype(float)
    df = df[df["messier_number"].notna() & (df["messier_number"] <= 110)]
    df["messier_number"] = df["messier_number"].astype(int)
    df["messier_id"] = "M " + df["messier_number"].astype(str)

    # Map object types to readable names
    df["object_category"] = df["object_type"].map(MESSIER_TYPES).fillna(df["object_type"])

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    df = df.sort_values("messier_number").reset_index(drop=True)

    # ── Domain-specific stats for README ─────────────────────────────
    n = len(df)
    n_galaxy = int(df["object_category"].str.contains("Galaxy", na=False).sum())
    n_cluster = int(df["object_category"].str.contains("Cluster", na=False).sum())
    n_nebula = int(df["object_category"].str.contains("Nebula|HII|SNR", na=False, regex=True).sum())

    quick_stats = f"""\
- **{n}** Messier objects
- **{n_galaxy}** galaxies, **{n_cluster}** star clusters, **{n_nebula}** nebulae/remnants"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/messier-catalog", split="train")
df = ds.to_pandas()

# Galaxies only
galaxies = df[df["object_category"].str.contains("Galaxy", na=False)]
print(f"{len(galaxies)} galaxies in the Messier catalog")

# Objects by category
print(df["object_category"].value_counts())

# Sky map of Messier objects
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(10, 5), subplot_kw={"projection": "aitoff"})
import numpy as np
ra_rad = np.deg2rad(df["ra_deg"] - 180)
dec_rad = np.deg2rad(df["dec_deg"])
ax.scatter(ra_rad, dec_rad, s=20, alpha=0.8)
ax.set_title("Messier Objects on the Sky")
ax.grid(True)
plt.tight_layout()
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Messier Catalog",
        description=DESCRIPTION,
        tags=["space", "open-data", "astronomy", "messier", "deep-sky",
              "galaxy", "nebula", "star-cluster", "simbad", "tabular-data", "parquet"],
        source_url="https://simbad.u-strasbg.fr/",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e000191/GSFC_20171208_Archive_e000191~medium.jpg",
            "alt": "Star cluster observed by Hubble",
            "credit": "NASA/ESA/Hubble",
        },
        related_datasets=[
            "juliensimon/ngc-ic-catalog",
            "juliensimon/quasar-catalog",
            "juliensimon/black-hole-catalog",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=["ra_deg", "dec_deg", "major_axis_arcmin", "minor_axis_arcmin"],
            strings=["name", "messier_id", "object_type", "object_category"],
        )
        all_null = [c for c in df.columns if df[c].isna().all()]
        if all_null:
            print(f"  Dropping fully-null columns: {all_null}")
            df = df.drop(columns=all_null)

        p.publish(
            df,
            filename="messier.parquet",
            min_rows=80,
            expected_columns=["messier_id", "name", "ra_deg", "dec_deg", "object_type"],
            critical_columns=["messier_id", "name"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Messier catalog: {n} objects",
        )
    print("Done.")


if __name__ == "__main__":
    main()
