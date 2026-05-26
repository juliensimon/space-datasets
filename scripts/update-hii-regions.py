#!/usr/bin/env python3
"""Fetch WISE Catalog of Galactic HII Regions from VizieR and upload to HF.

Source: Anderson et al. (2014, ApJS 212, 1) — WISE mid-infrared census of
Galactic HII regions with radio recombination line velocities.
VizieR catalog: J/ApJS/212/1
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/wise-hii-regions"

# ── Source query ─────────────────────────────────────────────────────
ADQL = 'SELECT * FROM "J/ApJS/212/1/wisecat"'

# ── Column mapping ───────────────────────────────────────────────────
RENAME = {
    "GLON": "glon_deg",
    "GLAT": "glat_deg",
    "RAJ2000": "ra_deg",
    "DEJ2000": "dec_deg",
    "_RA": "ra_deg",
    "_DE": "dec_deg",
    "RA_ICRS": "ra_deg",
    "DE_ICRS": "dec_deg",
    "RAICRS": "ra_deg",
    "DEICRS": "dec_deg",
    "Rad": "radius_arcmin",
    "VLSR": "vlsr_kms",
    "Vl": "vlsr_kms",
    "Name": "name",
    "Qual": "quality",
    "Type": "region_type",
    "Ref": "reference",
    "n_VLSR": "n_vlsr",
    "KDA": "kda_resolution",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "name": "Source designation from the WISE HII region catalog (e.g., 'G012.209-00.102'); encodes Galactic longitude and latitude in the name",
    "glon_deg": "Galactic longitude in decimal degrees (0-360); traces the Galactic plane distribution of star-forming regions",
    "glat_deg": "Galactic latitude in decimal degrees (-90 to +90); HII regions concentrate within a few degrees of the Galactic mid-plane",
    "ra_deg": "Right ascension, ICRS J2000.0, in decimal degrees (0-360)",
    "dec_deg": "Declination, ICRS J2000.0, in decimal degrees (-90 to +90)",
    "radius_arcmin": "Angular radius of the HII region in arcminutes, measured from WISE mid-infrared morphology; physical sizes range from ultra-compact (<0.1 pc) to giant (>50 pc) depending on distance and evolutionary stage",
    "vlsr_kms": "Radial velocity with respect to the Local Standard of Rest in km/s, measured from radio recombination lines (RRLs); enables kinematic distance estimates via the Galactic rotation curve; null for candidates without RRL detection",
    "quality": "Observational quality/classification flag: 'K' = known HII region (confirmed by RRL detection), 'C' = candidate (radio continuum detected, no RRL), 'Q' = radio-quiet candidate (infrared morphology only), 'G' = group member associated with a known region",
    "region_type": "Morphological or physical type classification of the HII region when available",
    "reference": "Literature reference code for the radio recombination line velocity measurement or source identification",
    "n_vlsr": "Number of independent velocity measurements contributing to the adopted VLSR value; higher counts indicate more reliable velocities",
    "kda_resolution": "Kinematic distance ambiguity (KDA) resolution method or flag; for sources inside the solar circle, two kinematic distances are possible (near/far) and additional data (HI absorption, parallax) resolves the ambiguity",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Catalog of Galactic HII regions from the WISE (Wide-field Infrared Survey Explorer) \
mid-infrared survey (Anderson et al. 2014). HII regions are clouds of ionized hydrogen \
surrounding hot young stars, tracing active star formation across the Milky Way disk.

The WISE catalog is the most complete census of Galactic HII regions to date, using \
mid-infrared data at 12 and 22 microns to identify HII region candidates by their \
characteristic thermal dust emission. Radio continuum surveys confirm the presence of \
thermal free-free emission from ionized gas, and radio recombination line (RRL) \
observations provide radial velocities that enable kinematic distance estimates via \
the Galactic rotation curve.

Regions are classified by observational evidence: known HII regions (confirmed by RRL \
detection), candidates (radio continuum but no RRL), radio-quiet candidates (infrared \
morphology only), and group members. The catalog spans the full range of HII region \
evolution from ultra-compact regions deeply embedded in molecular clouds to evolved \
diffuse nebulae, providing a comprehensive view of massive star formation across the \
entire Galactic disk even through the heavy dust extinction that obscures optical \
observations.
"""


def main():
    print("Fetching WISE HII Regions catalog from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} HII regions")

    # Strip whitespace from column names
    df.columns = df.columns.str.strip()

    # Drop VizieR internal columns
    for col in ["recno", "More", "SimbadName"]:
        if col in df.columns:
            df = df.drop(columns=[col])

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

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Sort by galactic longitude
    if "glon_deg" in df.columns:
        df = df.sort_values("glon_deg").reset_index(drop=True)
    else:
        df = df.reset_index(drop=True)

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_with_vlsr = int(df["vlsr_kms"].notna().sum()) if "vlsr_kms" in df.columns else 0
    n_with_radius = int(df["radius_arcmin"].notna().sum()) if "radius_arcmin" in df.columns else 0

    quality_counts = {}
    if "quality" in df.columns:
        quality_counts = df["quality"].value_counts().to_dict()
        print(f"  Quality breakdown: {quality_counts}")

    q_known = quality_counts.get("K", 0)
    q_candidate = quality_counts.get("C", 0)
    q_quiet = quality_counts.get("Q", 0)
    q_group = quality_counts.get("G", 0)

    quick_stats = f"""\
- **{n_total:,}** Galactic HII regions
- **{q_known:,}** known (RRL-confirmed), **{q_candidate:,}** candidates, **{q_quiet:,}** radio-quiet, **{q_group:,}** group members
- **{n_with_vlsr:,}** with radial velocity measurements
- **{n_with_radius:,}** with angular size measurements"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/wise-hii-regions", split="train")
df = ds.to_pandas()

# Galactic distribution
import matplotlib.pyplot as plt
plt.scatter(df["glon_deg"], df["glat_deg"], s=1, alpha=0.3)
plt.xlabel("Galactic Longitude (deg)")
plt.ylabel("Galactic Latitude (deg)")
plt.title("WISE HII Regions - Galactic Distribution")
plt.show()

# Velocity distribution
with_v = df.dropna(subset=["vlsr_kms"])
print(f"{len(with_v):,} HII regions with velocities")
with_v["vlsr_kms"].hist(bins=50)
plt.xlabel("VLSR (km/s)")
plt.title("HII Region Velocity Distribution")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="WISE Catalog of Galactic HII Regions",
        description=DESCRIPTION,
        tags=["space", "hii-region", "star-formation", "milky-way", "wise",
              "infrared", "astronomy", "galactic", "open-data", "tabular-data", "parquet"],
        source_url="https://vizier.cds.unistra.fr/viz-bin/VizieR?-source=J/ApJS/212/1",
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
            "juliensimon/nebula-catalog",
            "juliensimon/pulsar-catalog",
            "juliensimon/open-star-clusters",
            "juliensimon/gaia-dr3-young-stellar-objects",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=["glon_deg", "glat_deg", "ra_deg", "dec_deg",
                      "radius_arcmin", "vlsr_kms"],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="hii_regions.parquet",
            min_rows=5000,
            expected_columns=["glon_deg", "glat_deg"],
            critical_columns=["glon_deg", "glat_deg"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update WISE HII regions: {n_total:,} regions",
        )
    print("Done.")


if __name__ == "__main__":
    main()
