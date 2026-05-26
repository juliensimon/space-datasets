#!/usr/bin/env python3
"""Fetch eROSITA eRASS1 X-ray source catalog from VizieR and upload to HF.

Source: Merloni et al. (2024, A&A 682, A34) — first eROSITA All-Sky Survey
VizieR catalog: J/A+A/682/A34
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/erosita-erass1-xray"

# ── Source query ─────────────────────────────────────────────────────
ADQL = 'SELECT * FROM "J/A+A/682/A34/erass1-m"'

# ── Column mapping ───────────────────────────────────────────────────
RENAME = {
    "IAUName": "source_name",
    "RA_ICRS": "ra_deg",
    "DE_ICRS": "dec_deg",
    "GLON": "glon_deg",
    "GLAT": "glat_deg",
    "EXT": "extent_arcsec",
    "posErr": "position_error_arcsec",
    "MJD": "mjd",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "source_name": "eROSITA IAU source designation in the format '1eRASS JHHMMSS.s+DDMMSS'",
    "ra_deg": "Right ascension, ICRS J2000.0 (degrees, 0-360); typical positional accuracy a few arcsec",
    "dec_deg": "Declination, ICRS J2000.0 (degrees, -90 to +90); eROSITA covers the Western Galactic hemisphere",
    "glon_deg": "Galactic longitude (degrees, 0-360)",
    "glat_deg": "Galactic latitude (degrees, -90 to +90)",
    "extent_arcsec": "Source spatial extent in arcsec; 0 for point-like sources; >0 indicates extended emission (galaxy clusters have typical values 10-100 arcsec)",
    "position_error_arcsec": "1-sigma positional uncertainty in arcsec; typically 1-10 arcsec for well-detected sources",
    "mjd": "Modified Julian Date of the eRASS1 observation epoch (MJD = JD - 2400000.5)",
    "is_extended": "True if extent_arcsec > 0; extended sources are predominantly galaxy clusters",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
The largest X-ray source catalog ever compiled -- sources from the first eROSITA All-Sky \
Survey (eRASS1), released January 2024.

The extended ROentgen Survey with an Imaging Telescope Array (eROSITA) aboard the \
Spectrum-Roentgen-Gamma (SRG) satellite performed its first All-Sky Survey (eRASS1) in \
the 0.2--2.3 keV band, detecting approximately 900,000 X-ray sources across the Western \
Galactic hemisphere. This is the largest X-ray source catalog ever produced, comprising \
active galactic nuclei, galaxy clusters, stars, X-ray binaries, and other X-ray-emitting \
objects.

The soft X-ray band (0.2--2.3 keV) surveyed by eROSITA is dominated by emission from hot \
plasmas in galaxy clusters, coronally active stars, and accretion onto compact objects. The \
sheer scale of eRASS1 transforms X-ray astronomy from a regime of targeted observations \
into genuine survey science: the catalog contains roughly four times more sources than the \
cumulative total from all previous X-ray missions combined, including ROSAT, XMM-Newton, \
and Chandra.

Extended sources in this catalog are predominantly galaxy clusters, where the X-ray emission \
traces the intracluster medium heated to tens of millions of kelvin. Point-like sources are \
largely active galactic nuclei powered by supermassive black hole accretion, along with \
stellar coronae and compact binary systems in the Milky Way.
"""


def main():
    print("Fetching eROSITA eRASS1 catalog from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} X-ray sources")

    # Drop VizieR internal columns
    for col in ["recno"]:
        if col in df.columns:
            df = df.drop(columns=[col])

    df = df.rename(columns={k: v for k, v in RENAME.items() if k in df.columns})

    # Derived columns
    df["is_extended"] = df["extent_arcsec"].fillna(0) > 0

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_extended = int(df["is_extended"].sum())
    n_pointlike = n_total - n_extended

    quick_stats = f"""\
- **{n_total:,}** X-ray sources
- **{n_extended:,}** extended sources (galaxy clusters, etc.)
- **{n_pointlike:,}** point-like sources (AGN, stars, etc.)"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/erosita-erass1-xray", split="train")
df = ds.to_pandas()

# Extended sources (galaxy clusters)
clusters = df[df["is_extended"] == True]
print(f"{len(clusters):,} extended sources")

# Sky map
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(12, 6))
ax.scatter(df["ra_deg"], df["dec_deg"], s=0.01, alpha=0.1)
ax.set_xlabel("RA (deg)")
ax.set_ylabel("Dec (deg)")
ax.invert_xaxis()
ax.set_title("eROSITA eRASS1 X-Ray Sky Map")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="eROSITA eRASS1 X-Ray Source Catalog",
        description=DESCRIPTION,
        tags=["space", "x-ray", "erosita", "erass1", "astronomy", "mpe",
              "open-data", "tabular-data", "parquet"],
        source_url="https://vizier.cds.unistra.fr/viz-bin/VizieR?-source=J/A+A/682/A34",
        license="other",
        license_name="vizier-scientific-use",
        license_link="https://cds.unistra.fr/vizier-org/licences_vizier.html",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e002215/GSFC_20171208_Archive_e002215~medium.jpg",
            "alt": "The gamma-ray sky as seen by NASA's Fermi telescope",
            "credit": "NASA/DOE/Fermi LAT Collaboration",
        },
        related_datasets=[
            "juliensimon/fermi-4fgl-dr4",
            "juliensimon/pulsar-catalog",
            "juliensimon/galaxy-clusters",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "ra_deg", "dec_deg", "glon_deg", "glat_deg",
                "extent_arcsec", "position_error_arcsec", "mjd",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="erosita_erass1_xray.parquet",
            min_rows=500_000,
            expected_columns=["source_name", "ra_deg", "dec_deg"],
            critical_columns=["source_name", "ra_deg", "dec_deg"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update eROSITA eRASS1: {n_total:,} X-ray sources",
        )
    print("Done.")


if __name__ == "__main__":
    main()
