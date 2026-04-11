#!/usr/bin/env python3
"""Fetch Hipparcos main catalog from VizieR and upload to HF."""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/hipparcos-catalog"

# ── Source query ─────────────────────────────────────────────────────
ADQL = """SELECT * FROM "I/239/hip_main" """

# ── Column mapping ───────────────────────────────────────────────────
# VizieR may return RA_ICRS, RAICRS, or RAJ2000 — keep conditional rename
KNOWN_RENAMES = {
    "HIP": "hip_id",
    "RAICRS": "ra_deg",
    "RA_ICRS": "ra_deg",
    "RAJ2000": "ra_deg",
    "DEICRS": "dec_deg",
    "DE_ICRS": "dec_deg",
    "DEJ2000": "dec_deg",
    "Vmag": "v_magnitude",
    "Plx": "parallax_mas",
    "e_Plx": "parallax_error_mas",
    "pmRA": "proper_motion_ra_mas_yr",
    "pmDE": "proper_motion_dec_mas_yr",
    "B-V": "color_bv",
    "SpType": "spectral_type",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "hip_id": "Hipparcos Input Catalog identifier; integer in range 1–120404; the standard cross-reference identifier for stars brighter than ~12 mag observed by the Hipparcos satellite (1989–1993); still widely used to cross-match with Gaia and Tycho-2",
    "ra_deg": "Right ascension in degrees, ICRS at reference epoch J1991.25 (the astrometric midpoint of the Hipparcos mission, not J2000.0); range 0–360; differs from J2000.0 by a small proper-motion correction that grows with stellar velocity",
    "dec_deg": "Declination in degrees, ICRS at reference epoch J1991.25; range −90 to +90; positive north of the celestial equator",
    "v_magnitude": "Johnson V-band apparent magnitude; higher values are fainter; catalog covers roughly V = 2–12.4 mag; null for stars with only Hp-band photometry",
    "parallax_mas": "Trigonometric parallax in milliarcseconds; convert to distance via distance_pc = 1000 / parallax_mas; Hipparcos precision ~1 mas (cf. Gaia ~0.02 mas); negative values are physically meaningful measurement noise for distant stars where the true parallax is near zero",
    "parallax_error_mas": "1-sigma formal uncertainty on the parallax in milliarcseconds; stars where parallax_error_mas > 0.5 × parallax_mas have uncertain distances (signal-to-noise < 2); use with caution for distance-dependent analyses",
    "proper_motion_ra_mas_yr": "Proper motion in right ascension in milliarcseconds per year, with the cos(dec) factor already applied so this is the true angular rate on the sky (not the coordinate rate); positive = eastward motion",
    "proper_motion_dec_mas_yr": "Proper motion in declination in milliarcseconds per year; positive = northward motion; combined with proper_motion_ra_mas_yr gives the full tangential velocity vector on the sky",
    "color_bv": "Johnson B−V color index in magnitudes; more positive values indicate redder, cooler stars (e.g. B−V ≈ −0.3 for hot O/B stars, +1.5 for cool M giants); null for stars lacking B-band photometry",
    "spectral_type": "MK (Morgan–Keenan) spectral classification from catalog cross-references, e.g. 'G2V' (Sun-like), 'K0III' (red giant); encodes temperature class (O B A F G K M), luminosity class (I–V), and sometimes peculiarity flags; null for ~30% of stars, especially fainter objects",
    "distance_pc": "Heliocentric distance in parsecs, derived as 1000 / parallax_mas; null when parallax_mas ≤ 0 (unphysical noise-dominated measurements); treat values with large parallax_error_mas as highly uncertain",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
The ESA Hipparcos space astrometry mission catalog containing 118,218 of the \
brightest stars in the sky with precise positions, parallaxes, and proper motions.

The Hipparcos satellite (1989–1993) was ESA's pioneering space astrometry mission. \
It measured the positions, parallaxes, and proper motions of stars with unprecedented \
precision, creating the first high-accuracy stellar reference frame from space. \
Hipparcos parallaxes remain the gold standard for nearby star distances and are the \
foundation for the cosmic distance ladder.

Hipparcos achieved milliarcsecond-level astrometry — a factor of 100 improvement over \
ground-based catalogs — by observing from above Earth's atmosphere. The mission's key \
deliverable, trigonometric parallax, provides the most direct and model-independent \
method of measuring stellar distances: a star at 1 parsec subtends a parallax of \
1 arcsecond, and distance in parsecs is simply 1/parallax. With typical parallax \
uncertainties of 1 mas, Hipparcos yielded distances accurate to 10% out to about 100 pc.

The scientific legacy of Hipparcos extends far beyond simple distance measurement. \
Proper motions from the catalog revealed the kinematic structure of nearby stellar \
streams and moving groups. Combined with radial velocities, Hipparcos data enabled \
full three-dimensional space velocity determinations for thousands of stars. Although \
Gaia has since surpassed Hipparcos in depth and precision, the catalog retains enduring \
value: it provides an independent epoch (J1991.25) for long-baseline proper motion studies, \
and its bright-star astrometry benchmarks Gaia solutions at the bright end.
"""


def main():
    print("Fetching Hipparcos catalog from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} stars fetched")

    # Rename columns — VizieR may return RA_ICRS, RAICRS, or RAJ2000
    rename_map = {k: v for k, v in KNOWN_RENAMES.items() if k in df.columns}
    if rename_map:
        df = df.rename(columns=rename_map)

    # Derive distance from parallax (where parallax > 0)
    if "parallax_mas" in df.columns:
        mask = df["parallax_mas"] > 0
        df.loc[mask, "distance_pc"] = 1000.0 / df.loc[mask, "parallax_mas"]

    # Clean spectral type strings
    if "spectral_type" in df.columns:
        df["spectral_type"] = df["spectral_type"].astype(str).str.strip().replace(
            {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
        )

    # Keep only described columns (drop raw VizieR columns without descriptions)
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    df = df.sort_values("hip_id").reset_index(drop=True)

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_with_parallax = int(df["parallax_mas"].notna().sum()) if "parallax_mas" in df.columns else 0
    n_with_distance = int(df["distance_pc"].notna().sum()) if "distance_pc" in df.columns else 0
    n_with_spectral = int(df["spectral_type"].notna().sum()) if "spectral_type" in df.columns else 0
    median_vmag = df["v_magnitude"].median() if "v_magnitude" in df.columns else None

    quick_stats = f"""\
- **{n_total:,}** stars
- **{n_with_parallax:,}** with measured parallax
- **{n_with_distance:,}** with derived distance (parallax > 0)
- **{n_with_spectral:,}** with spectral type classification
- Median V magnitude: **{median_vmag:.1f}**"""

    # ── Custom usage example (HR diagram) ────────────────────────────
    usage = """\
```python
from datasets import load_dataset
import matplotlib.pyplot as plt

ds = load_dataset("juliensimon/hipparcos-catalog", split="train")
df = ds.to_pandas()

# Hertzsprung-Russell diagram: color vs. absolute magnitude
# Compute absolute magnitude from distance modulus: M = V - 5*log10(d/10)
import numpy as np
valid = df.dropna(subset=["color_bv", "v_magnitude", "distance_pc"])
valid = valid[valid["distance_pc"] > 0]
valid["abs_mag"] = valid["v_magnitude"] - 5 * np.log10(valid["distance_pc"] / 10)

plt.figure(figsize=(8, 10))
plt.scatter(valid["color_bv"], valid["abs_mag"], s=0.2, alpha=0.3, c="steelblue")
plt.gca().invert_yaxis()
plt.xlabel("B-V Color Index (bluer ← → redder)")
plt.ylabel("Absolute Magnitude Mv (brighter ↑)")
plt.title("Hipparcos HR Diagram")
plt.tight_layout()
plt.show()

# Nearest stars within 10 parsecs
nearby = df[df["distance_pc"] < 10].sort_values("distance_pc")
print(nearby[["hip_id", "v_magnitude", "distance_pc", "spectral_type"]].head(20))
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Hipparcos Star Catalog",
        description=DESCRIPTION,
        tags=["space", "hipparcos", "star", "astrometry", "parallax", "astronomy",
              "open-data", "tabular-data", "parquet"],
        source_url="https://vizier.cds.unistra.fr/viz-bin/VizieR-3?-source=I/239/hip_main",
        task_categories=["tabular-classification", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e000191/GSFC_20171208_Archive_e000191~medium.jpg",
            "alt": "A youthful globular star cluster observed by the Hubble Space Telescope",
            "credit": "NASA/ESA/Hubble",
        },
        related_datasets=[
            "juliensimon/gcvs-variable-stars",
            "juliensimon/open-star-clusters",
            "juliensimon/pulsar-catalog",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=["ra_deg", "dec_deg", "v_magnitude", "parallax_mas",
                     "parallax_error_mas", "proper_motion_ra_mas_yr",
                     "proper_motion_dec_mas_yr", "color_bv"],
            integer={"hip_id": "Int64"},
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="hipparcos.parquet",
            min_rows=100000,
            expected_columns=["ra_deg", "dec_deg"],
            critical_columns=["ra_deg", "dec_deg"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Hipparcos catalog: {n_total:,} stars",
        )
    print("Done.")


if __name__ == "__main__":
    main()
