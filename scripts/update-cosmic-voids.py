#!/usr/bin/env python3
"""Fetch cosmic void catalog from VizieR and upload to HF.

Source: Pan D.C., Vogeley M.S., Hoyle F., Choi Y.-Y., Park C. (2012, MNRAS, 421, 926)
VizieR catalog: J/MNRAS/421/926
"""

import sys

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/cosmic-void-catalog"

# ── Source queries ───────────────────────────────────────────────────
ADQL = 'SELECT * FROM "J/MNRAS/421/926/voids"'

FALLBACK_QUERIES = [
    ("Mao et al. 2017", 'SELECT * FROM "J/ApJ/835/161/table1"'),
    ("Sutter et al. 2012", 'SELECT * FROM "J/ApJ/761/187"'),
]

# ── Column mapping ───────────────────────────────────────────────────
RENAME = {
    "RAJ2000": "ra_deg",
    "DEJ2000": "dec_deg",
    "RAdeg": "ra_deg",
    "DEdeg": "dec_deg",
    "RA": "ra_deg",
    "DE": "dec_deg",
    "z": "redshift",
    "zv": "redshift",
    "Reff": "radius_eff_mpc",
    "Rvoid": "radius_eff_mpc",
    "R": "radius_eff_mpc",
    "Rmax": "radius_max_mpc",
    "Void": "void_id",
    "Name": "void_name",
    "Dens": "density_contrast",
    "DensCon": "density_contrast",
    "delta": "density_contrast",
    "Dist": "distance_mpc",
    "Ngal": "n_galaxies",
    "N": "n_galaxies",
    "GLAT": "glat_deg",
    "GLON": "glon_deg",
    "Vol": "volume_mpc3",
    "Ell": "ellipticity",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "void_id": "Catalog-assigned void identifier; integer index or string label depending on the source catalog",
    "void_name": "Void name or designation from the originating catalog; null if unnamed",
    "ra_deg": "ICRS J2000.0 right ascension of the void center in degrees (0-360)",
    "dec_deg": "ICRS J2000.0 declination of the void center in degrees (-90 to +90)",
    "glon_deg": "Galactic longitude of the void center in degrees (0-360)",
    "glat_deg": "Galactic latitude of the void center in degrees (-90 to +90)",
    "redshift": "Redshift of the void center; survey range typically 0.02 < z < 0.5",
    "radius_eff_mpc": "Effective (spherically-equivalent) void radius in Mpc; typical range 10-100 Mpc",
    "radius_max_mpc": "Maximum extent of the void from center to the most distant wall galaxy, in Mpc",
    "density_contrast": "Relative underdensity delta = (rho - rho_bar) / rho_bar; voids have delta < 0, typically -0.8 to -0.9 at center",
    "distance_mpc": "Comoving distance from the observer to the void center in Mpc",
    "n_galaxies": "Number of tracer galaxies used to define the void boundary; higher counts indicate better-constrained voids",
    "volume_mpc3": "Effective volume of the void in Mpc^3; scales as ~(4/3)*pi*radius_eff_mpc^3",
    "ellipticity": "Void shape ellipticity (0 = perfectly spherical, >0 = elongated); derived from the eigenvalues of the inertia tensor",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Catalog of cosmic voids identified in the Sloan Digital Sky Survey (SDSS). Cosmic voids \
are vast underdense regions in the large-scale structure of the universe, typically 20-50 \
Mpc in radius. They occupy the majority of the volume of the universe and are bounded by \
filaments, walls, and clusters that form the cosmic web.

Void properties are powerful probes of fundamental physics. The void size function \
(abundance as a function of radius) is sensitive to the matter density parameter, sigma_8, \
and the dark energy equation of state. The Alcock-Paczynski test applied to stacked void \
shapes constrains the expansion history of the universe. Void lensing profiles measure the \
matter content of underdense regions and test modified gravity theories, since voids amplify \
the differences between general relativity and alternative theories such as f(R) gravity.

This catalog enables studies of void demographics, spatial distribution, and correlations \
with other large-scale structure tracers. Cross-matching with galaxy surveys reveals how \
galaxy properties (color, morphology, star formation rate) depend on large-scale environment.
"""


def fetch_catalog() -> pd.DataFrame:
    """Fetch cosmic void catalog, trying multiple VizieR tables."""
    print("Fetching Pan et al. (2012) SDSS DR7 void catalog from VizieR...")
    try:
        df = vizier_query(ADQL)
        if len(df) >= 100:
            print(f"  Pan et al. (2012): {len(df):,} voids")
            return df
        print(f"  Pan et al. (2012) returned only {len(df)} rows, trying fallback...")
    except Exception as e:
        print(f"  Pan et al. (2012) failed: {e}")

    for name, query in FALLBACK_QUERIES:
        print(f"Trying {name}...")
        try:
            df = vizier_query(query)
            if len(df) >= 50:
                print(f"  {name}: {len(df):,} voids")
                return df
            print(f"  {name} returned only {len(df)} rows")
        except Exception as e:
            print(f"  {name} failed: {e}")

    print("::error::All void catalog sources failed")
    sys.exit(1)


def main():
    df = fetch_catalog()

    # Drop VizieR internal columns
    if "recno" in df.columns:
        df = df.drop(columns=["recno"])

    df = df.rename(columns={k: v for k, v in RENAME.items() if k in df.columns})

    # Lowercase any remaining uppercase column names
    df.columns = [
        c.lower().replace(" ", "_")
        if c == c.upper() or any(ch.isupper() for ch in c)
        else c
        for c in df.columns
    ]

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Sort by effective radius descending (largest voids first)
    sort_col = None
    for candidate in ["radius_eff_mpc", "radius_max_mpc", "redshift"]:
        if candidate in df.columns:
            sort_col = candidate
            break
    if sort_col:
        df = df.sort_values(sort_col, ascending=False).reset_index(drop=True)
        print(f"  Sorted by {sort_col} descending")

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    median_radius = df["radius_eff_mpc"].median() if "radius_eff_mpc" in df.columns else None
    max_radius = df["radius_eff_mpc"].max() if "radius_eff_mpc" in df.columns else None
    median_z = df["redshift"].median() if "redshift" in df.columns else None
    z_min = df["redshift"].min() if "redshift" in df.columns else None
    z_max = df["redshift"].max() if "redshift" in df.columns else None

    stats_lines = [f"- **{n_total:,}** cosmic voids"]
    if median_radius is not None:
        stats_lines.append(f"- Median effective radius: **{median_radius:.1f} Mpc**")
    if max_radius is not None:
        stats_lines.append(f"- Largest void radius: **{max_radius:.1f} Mpc**")
    if median_z is not None:
        stats_lines.append(f"- Median redshift: **{median_z:.3f}**")
    if z_min is not None and z_max is not None:
        stats_lines.append(f"- Redshift range: **{z_min:.3f}** to **{z_max:.3f}**")
    quick_stats = "\n".join(stats_lines)

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/cosmic-void-catalog", split="train")
df = ds.to_pandas()

# Void size distribution
import matplotlib.pyplot as plt
if "radius_eff_mpc" in df.columns:
    df["radius_eff_mpc"].dropna().hist(bins=30, edgecolor="black")
    plt.xlabel("Effective Radius (Mpc)")
    plt.ylabel("Count")
    plt.title("Cosmic Void Size Distribution")
    plt.show()

# Sky distribution sized by radius
plt.figure(figsize=(12, 6))
plt.scatter(df["ra_deg"], df["dec_deg"], s=df.get("radius_eff_mpc", 5)**2 / 50,
            alpha=0.5, c=df.get("redshift"), cmap="viridis")
plt.colorbar(label="Redshift")
plt.xlabel("RA (deg)")
plt.ylabel("Dec (deg)")
plt.title("Cosmic Void Sky Distribution")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Cosmic Void Catalog",
        description=DESCRIPTION,
        tags=["space", "cosmic-void", "large-scale-structure", "cosmology",
              "sdss", "astronomy", "dark-energy", "open-data", "tabular-data", "parquet"],
        source_url="https://vizier.cds.unistra.fr/viz-bin/VizieR?-source=J/MNRAS/421/926",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA12110/PIA12110~small.jpg",
            "alt": "Hubble Deep Field revealing myriad galaxies across cosmic time",
            "credit": "NASA/ESA/STScI",
        },
        related_datasets=[
            "juliensimon/desi-dr1-redshifts",
            "juliensimon/galaxy-clusters",
            "juliensimon/pantheon-plus-sne-ia",
            "juliensimon/planck-sz2-clusters",
        ],
    ) as p:
        numeric_candidates = [
            "ra_deg", "dec_deg", "redshift", "radius_eff_mpc", "radius_max_mpc",
            "density_contrast", "distance_mpc", "n_galaxies", "glat_deg", "glon_deg",
            "volume_mpc3", "ellipticity",
        ]
        df = p.clean(
            df,
            numeric=[c for c in numeric_candidates if c in df.columns],
            drop_mostly_null_threshold=0.95,
        )
        # Build expected columns from what we actually have
        expected = [c for c in ["ra_deg", "dec_deg", "redshift", "radius_eff_mpc"]
                    if c in df.columns]
        critical = [c for c in ["ra_deg", "dec_deg"] if c in df.columns]
        p.publish(
            df,
            filename="cosmic_voids.parquet",
            min_rows=500,
            expected_columns=expected,
            critical_columns=critical,
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update cosmic void catalog: {n_total:,} voids",
        )
    print("Done.")


if __name__ == "__main__":
    main()
