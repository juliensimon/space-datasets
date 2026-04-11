#!/usr/bin/env python3
"""Fetch HMXB and LMXB catalogs from HEASARC and upload merged X-ray binary catalog to HF.

Source: Liu, van Paradijs & van den Heuvel (2006/2007)
HEASARC tables: hmxbcat, lmxbcat
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import heasarc_query

HF_REPO = "juliensimon/xray-binary-catalog"

HMXB_ADQL = "SELECT * FROM hmxbcat"
LMXB_ADQL = "SELECT * FROM lmxbcat"

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "name": "Primary catalog designation (e.g., '4U 1700-37', 'Cygnus X-1') or IAU X-ray survey name; from HMXB/LMXB catalog column 'Name'",
    "ra": "Right ascension, ICRS J2000.0 (degrees, 0-360)",
    "dec": "Declination, ICRS J2000.0 (degrees, -90 to +90)",
    "lii": "Galactic longitude (degrees, 0-360)",
    "bii": "Galactic latitude (degrees, -90 to +90); LMXBs concentrate toward the Galactic center (|b| < 10 deg)",
    "class": "Sub-class of the binary (e.g., 'Be/X' for Be X-ray binary, 'SFXT' for supergiant fast X-ray transient, 'Atoll' or 'Z' for LMXB X-ray color-color diagram type)",
    "binary_type": "Binary class: 'HMXB' (high-mass donor, typically O/B star >10 Msun) or 'LMXB' (low-mass donor, Roche-lobe overflow, <1 Msun); derived from the source catalog",
    "flux": "Typical X-ray flux in mCrab; 1 Crab ~ 2.4e-8 erg/cm^2/s in 2-10 keV; null if not measured",
    "period": "Neutron-star pulse (spin) period in seconds; null for black hole systems and sources where the period is unknown",
    "orbital_period": "Binary orbital period in days; LMXBs typically 0.2-10 d, HMXBs 1-hundreds of d; null if unknown",
    "optical_counterpart": "Name of the identified optical counterpart star or system",
    "spectral_type": "MK spectral type of the companion (donor) star (e.g., 'O9.7Iab', 'B0Ve', 'K5III'); null if unidentified",
    "vmag": "Visual (V-band) magnitude of the optical counterpart; null if unmeasured or heavily obscured",
    "alt_name": "Alternative source designation from another catalog or common name",
    "time": "Reference epoch of the position or flux measurement (MJD); null if not reported",
    "search_offset_": "Angular offset between the catalog position and the HEASARC search position (arcmin)",
    "type": "HEASARC object type code for the source (e.g., 'XB' for X-ray binary)",
    "x_ray_flux": "X-ray flux in catalog-specific units (typically erg/cm^2/s or mCrab); null if unmeasured",
    "right_ascension": "Right ascension in sexagesimal format (HH MM SS.s); for display/cross-matching",
    "declination": "Declination in sexagesimal format (+-DD MM SS); for display/cross-matching",
    "ref_no": "Sequential reference number in the original Liu et al. (2006/2007) printed catalog",
    "remarks": "Free-text notes on the source (e.g., transient behavior, alternative classifications, special properties)",
    "max_intensity": "Peak observed X-ray intensity in Crab units or mCrab; null if no outburst maximum is recorded",
    "x_ray_range": "Description of the X-ray energy band for the flux measurement (e.g., '2-10 keV')",
    "status": "Source status from the catalog: 'confirmed' X-ray binary, 'candidate', or similar qualifier",
    "obs_type": "Observation mode or instrument type used for the primary flux measurement",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Merged catalog of high-mass and low-mass X-ray binaries from HEASARC (Liu et al. 2006/2007).

X-ray binaries are stellar systems in which a compact object (neutron star or black hole) \
accretes matter from a companion star, producing intense X-ray emission. They are divided \
into two classes based on the mass of the donor star:

High-Mass X-ray Binaries (HMXBs): The donor is a massive O or B star (typically >10 solar \
masses). Accretion occurs via stellar wind or Roche lobe overflow. HMXBs are found in \
star-forming regions and include Be/X-ray binaries (the largest subclass) and supergiant \
X-ray binaries.

Low-Mass X-ray Binaries (LMXBs): The donor is a low-mass star (typically <1 solar mass). \
Accretion proceeds through Roche lobe overflow, forming a bright accretion disk. LMXBs are \
concentrated toward the Galactic center and globular clusters. They include the Z and Atoll \
sources and the soft X-ray transients.

X-ray binaries are natural laboratories for studying accretion physics, strong gravity, and \
the equation of state of ultra-dense matter. Their X-ray variability (pulsations, \
quasi-periodic oscillations, thermonuclear bursts) encodes information about the compact \
object's mass, spin, and magnetic field.
"""


def main():
    print("Fetching HMXB catalog from HEASARC...")
    hmxb = heasarc_query("hmxbcat", HMXB_ADQL)
    hmxb["binary_type"] = "HMXB"
    print(f"  {len(hmxb):,} HMXBs")

    print("Fetching LMXB catalog from HEASARC...")
    lmxb = heasarc_query("lmxbcat", LMXB_ADQL)
    lmxb["binary_type"] = "LMXB"
    print(f"  {len(lmxb):,} LMXBs")

    df = pd.concat([hmxb, lmxb], ignore_index=True)
    print(f"  Merged: {len(hmxb):,} HMXB + {len(lmxb):,} LMXB = {len(df):,} total")

    # Clean empty strings to NaN for string columns
    str_cols = df.select_dtypes(include=["object"]).columns
    for col in str_cols:
        df[col] = df[col].replace(r"^\s*$", pd.NA, regex=True)

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Sort by name
    if "name" in df.columns:
        df = df.sort_values("name").reset_index(drop=True)

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_hmxb = int((df["binary_type"] == "HMXB").sum())
    n_lmxb = int((df["binary_type"] == "LMXB").sum())

    quick_stats = f"""\
- **{n_total:,}** X-ray binaries total
- **{n_hmxb:,}** High-Mass X-ray Binaries (HMXB)
- **{n_lmxb:,}** Low-Mass X-ray Binaries (LMXB)"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/xray-binary-catalog", split="train")
df = ds.to_pandas()

# Count by type
print(df["binary_type"].value_counts())

# HMXBs vs LMXBs
hmxb = df[df["binary_type"] == "HMXB"]
lmxb = df[df["binary_type"] == "LMXB"]
print(f"{len(hmxb):,} HMXBs, {len(lmxb):,} LMXBs")

# Sky distribution
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(12, 6))
for btype, group in df.groupby("binary_type"):
    ax.scatter(group["ra"], group["dec"], s=5, alpha=0.7, label=btype)
ax.set_xlabel("RA (deg)")
ax.set_ylabel("Dec (deg)")
ax.legend()
ax.set_title("X-ray Binary Sky Distribution")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="X-ray Binary Catalog",
        description=DESCRIPTION,
        tags=["space", "x-ray-binary", "hmxb", "lmxb", "x-ray",
              "astronomy", "compact-object", "neutron-star", "black-hole",
              "open-data", "tabular-data", "parquet"],
        source_url="https://heasarc.gsfc.nasa.gov/W3Browse/all/hmxbcat.html",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e000191/GSFC_20171208_Archive_e000191~medium.jpg",
            "alt": "A youthful globular star cluster observed by the Hubble Space Telescope",
            "credit": "NASA/ESA/Hubble",
        },
        related_datasets=[
            "juliensimon/pulsar-catalog",
            "juliensimon/mcgill-magnetar-catalog",
            "juliensimon/chandra-x-ray-sources",
            "juliensimon/gravitational-wave-events",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=["ra", "dec", "flux", "period", "orbital_period"],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="xray-binaries.parquet",
            min_rows=300,
            expected_columns=["name", "ra", "dec", "binary_type"],
            critical_columns=["name", "ra", "dec"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update X-ray binary catalog: {n_total:,} sources",
        )
    print("Done.")


if __name__ == "__main__":
    main()
