#!/usr/bin/env python3
"""Fetch Milliquas v8 (Million Quasars Catalog) from VizieR and upload to HF.

Source: Flesch (2023, arXiv:2308.01505) — The Million Quasars Catalog v8,
the most comprehensive compilation of quasars, AGN, and blazars.
VizieR catalog: VII/294
"""

import re

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/milliquas"

# ── Source query ─────────────────────────────────────────────────────
ADQL = 'SELECT * FROM "VII/294/catalog"'

# ── Column mapping ───────────────────────────────────────────────────
RENAME = {
    "RA_ICRS": "ra_deg",
    "RAJ2000": "ra_deg",
    "_RA": "ra_deg",
    "DE_ICRS": "dec_deg",
    "DEJ2000": "dec_deg",
    "_DE": "dec_deg",
    "Name": "name",
    "Type": "object_type",
    "Cl": "object_type",
    "z": "redshift",
    "Redshift": "redshift",
    "Rmag": "r_mag",
    "rmag": "r_mag",
    "Bmag": "b_mag",
    "bmag": "b_mag",
    "Ref": "reference",
    "Qpct": "qso_probability_pct",
    "XName": "xray_name",
    "Xname": "xray_name",
    "RName": "radio_name",
    "Rname": "radio_name",
    "R": "r_psf_class",
    "B": "b_psf_class",
    "Comment": "comment",
    "rz": "redshift_ref",
    "rName": "name_ref",
    "Lobe1": "radio_lobe_1",
    "Lobe2": "radio_lobe_2",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "name": "Source designation from the radio or X-ray catalog that first identified the counterpart (e.g., 'SDSS J123456.78+123456.7', '3C 273'); not always the most commonly used name",
    "ra_deg": "Right ascension in decimal degrees (J2000.0 ICRS); range 0-360",
    "dec_deg": "Declination in decimal degrees (J2000.0 ICRS); range -90 to +90",
    "object_type": "Source classification code: 'Q' (type-I quasar), 'A' (AGN/Seyfert), 'B' (BL Lac object), 'N' (narrow-line AGN/Seyfert 2), 'K' (known QSO from literature), 'q' (photometric quasar candidate, not spectroscopically confirmed)",
    "redshift": "Spectroscopic or photometric redshift; the most complete compilation of known QSO redshifts globally; range 0.006 to 7.6+; null for entries lacking a measured redshift",
    "r_mag": "Optical magnitude in the R band (red, ~6500 A); null for radio-selected sources without optical counterpart or magnitude measurement",
    "b_mag": "Optical magnitude in the B band (blue, ~4400 A); null for sources without blue-band photometry",
    "qso_probability_pct": "Probability (0-100%) that the object is a genuine QSO, based on photometric classification; populated for candidate objects; null for spectroscopically confirmed sources",
    "reference": "Milliquas internal reference code pointing to the publication or survey that provided the classification or redshift",
    "radio_name": "Name of the associated radio source from a radio survey (e.g., FIRST, NVSS, VLBI catalog); null if no radio counterpart has been identified",
    "xray_name": "Name of the associated X-ray source (e.g., from ROSAT, Chandra, XMM-Newton); null if no X-ray counterpart has been identified",
    "r_psf_class": "PSF classification flag for the R-band detection; encodes star/galaxy morphological information from photometric catalogs",
    "b_psf_class": "PSF classification flag for the B-band detection; encodes star/galaxy morphological information from photometric catalogs",
    "comment": "Additional remarks or flags on the source entry from the Milliquas compilation",
    "redshift_ref": "Reference code for the source of the redshift measurement; links to the survey or publication that measured z",
    "name_ref": "Reference code for the source name designation; links to the catalog or publication that first identified the object",
    "radio_lobe_1": "Name or position of the first radio lobe associated with this source; populated for double-lobed radio galaxies and quasars",
    "radio_lobe_2": "Name or position of the second radio lobe associated with this source; populated for double-lobed radio galaxies and quasars",
    "is_qso": "True if object_type contains 'Q' (type-I quasar or known QSO); derived convenience flag for filtering confirmed quasars",
    "has_radio": "True if a non-null radio source name is associated with this object; ~15% of catalog entries have radio counterparts",
    "has_xray": "True if a non-null X-ray source name is associated with this object; ~30% of catalog entries have X-ray counterparts",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Milliquas v8 (Flesch 2023) -- the Million Quasars Catalog, the most comprehensive \
compilation of quasars, AGN, and blazars available. Includes type-I QSOs, AGN, blazars, \
and type-II objects with sky positions, redshifts, optical magnitudes, and \
cross-identifications with radio and X-ray surveys.

Quasars are the most luminous persistent objects in the universe, powered by accretion \
onto supermassive black holes with masses ranging from millions to tens of billions of \
solar masses. Because they can be detected at redshifts beyond z = 7, they provide \
direct observational windows into the epoch of reionization and the assembly of the \
first massive galaxies.

A catalog of this scale is indispensable for statistical studies of AGN demographics -- \
how the quasar luminosity function evolves with redshift, what fraction of supermassive \
black holes are actively accreting at a given epoch, and how AGN feedback influences \
galaxy evolution. The inclusion of radio and X-ray cross-identifications allows \
researchers to identify jetted AGN (radio-loud quasars and blazars) and to separate \
radiatively efficient from radiatively inefficient accretion modes. Milliquas provides \
the foundation for selecting spectroscopic targets in next-generation surveys such as \
DESI, 4MOST, and the Vera Rubin Observatory's LSST.
"""


def main():
    print("Fetching Milliquas v8 catalog from VizieR...")
    df = vizier_query(ADQL, timeout=600)
    print(f"  {len(df):,} objects")

    # Drop unwanted columns
    for col in ["recno", "SimbadName", "More"]:
        if col in df.columns:
            df = df.drop(columns=[col])

    # Rename columns
    rename_map = {k: v for k, v in RENAME.items() if k in df.columns}
    df = df.rename(columns=rename_map)

    # Snake_case remaining columns
    def to_snake(col_name):
        s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", col_name)
        s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
        return s.lower().replace("-", "_").replace(" ", "_")

    df.columns = [to_snake(c) if c not in rename_map.values() else c for c in df.columns]

    # Derived columns
    if "object_type" in df.columns:
        df["is_qso"] = df["object_type"].astype(str).str.contains("Q", na=False)
    else:
        df["is_qso"] = False

    if "radio_name" in df.columns:
        df["has_radio"] = df["radio_name"].notna() & (df["radio_name"].astype(str).str.strip() != "")
    else:
        df["has_radio"] = False

    if "xray_name" in df.columns:
        df["has_xray"] = df["xray_name"].notna() & (df["xray_name"].astype(str).str.strip() != "")
    else:
        df["has_xray"] = False

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Sort by name
    if "name" in df.columns:
        df = df.sort_values("name").reset_index(drop=True)

    # ── Domain-specific stats for README ─────────────────────────────
    n = len(df)
    n_qso = int(df["is_qso"].sum())
    n_radio = int(df["has_radio"].sum())
    n_xray = int(df["has_xray"].sum())
    z_min = df["redshift"].min()
    z_max = df["redshift"].max()
    z_median = df["redshift"].median()
    n_with_z = int(df["redshift"].notna().sum())

    print(f"  {n_qso:,} QSOs, {n_radio:,} with radio, {n_xray:,} with X-ray")
    print(f"  Redshift range: {z_min:.3f} - {z_max:.3f}, median {z_median:.3f}")

    quick_stats = f"""\
- **{n:,}** objects total
- **{n_qso:,}** QSOs (type contains "Q")
- **{n_with_z:,}** with measured redshift
- Redshift range: **{z_min:.3f}** to **{z_max:.3f}** (median **{z_median:.3f}**)
- **{n_radio:,}** with radio associations
- **{n_xray:,}** with X-ray associations"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/milliquas", split="train")
df = ds.to_pandas()

# High-redshift quasars (z > 4)
high_z = df[df["redshift"] > 4].sort_values("redshift", ascending=False)
print(f"{len(high_z):,} quasars with z > 4")

# Redshift distribution
import matplotlib.pyplot as plt
df["redshift"].dropna().hist(bins=200, range=(0, 7))
plt.xlabel("Redshift")
plt.ylabel("Count")
plt.title("Milliquas Redshift Distribution")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Milliquas -- Million Quasars Catalog v8",
        description=DESCRIPTION,
        tags=["space", "quasars", "agn", "blazars", "active-galaxies",
              "astronomy", "open-data", "tabular-data", "parquet"],
        source_url="https://vizier.cds.unistra.fr/viz-bin/VizieR?-source=VII/294",
        license="other",
        license_name="vizier-scientific-use",
        license_link="https://cds.unistra.fr/vizier-org/licences_vizier.html",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA12110/PIA12110~small.jpg",
            "alt": "Hubble Deep Field revealing myriad galaxies across cosmic time",
            "credit": "NASA/ESA/STScI",
        },
        related_datasets=[
            "juliensimon/quasar-catalog",
            "juliensimon/galaxy-clusters",
            "juliensimon/gravitational-lenses",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=["ra_deg", "dec_deg", "redshift", "r_mag", "b_mag",
                      "qso_probability_pct"],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="milliquas.parquet",
            min_rows=800000,
            expected_columns=["ra_deg", "dec_deg", "redshift"],
            critical_columns=["ra_deg", "dec_deg"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Milliquas v8: {n:,} quasars/AGN",
        )
    print("Done.")


if __name__ == "__main__":
    main()
