#!/usr/bin/env python3
"""Fetch Planck PSZ2 Galaxy Cluster Catalog from HEASARC and upload to HF.

Source: Planck Collaboration XXVII (2016, A&A, 594, A27)
HEASARC table: plancksz2
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import heasarc_query

HF_REPO = "juliensimon/galaxy-clusters"

ADQL = """\
SELECT name, ra, dec, lii, bii, redshift, redshift_source_name, mass_sz,
  mass_sz_pos_err, mass_sz_neg_err, y5r500, y5r500_error, snr,
  det_pipeline_codes
FROM plancksz2 ORDER BY name\
"""

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "name": "Planck cluster designation in the format 'PSZ2 GXXX.X+/-XX.X' (Galactic longitude and latitude encoded in the name)",
    "ra": "ICRS J2000.0 right ascension of the cluster center in degrees (0-360)",
    "dec": "ICRS J2000.0 declination of the cluster center in degrees (-90 to +90)",
    "lii": "Galactic longitude of the cluster center in degrees (0-360)",
    "bii": "Galactic latitude of the cluster center in degrees (-90 to +90)",
    "redshift": "Cluster spectroscopic or photometric redshift; null for ~30% of Planck clusters lacking optical confirmation",
    "redshift_source_name": "Survey or reference providing the redshift (e.g., 'SDSS', 'ACT', 'SPT'); null if redshift is null",
    "mass_sz": "SZ-derived cluster mass M_SZ in units of 10^14 solar masses; Planck clusters range ~1-15; null if Y_5R500 is unavailable",
    "mass_sz_pos_err": "Upper (positive) 1-sigma uncertainty on mass_sz in units of 10^14 solar masses; null if mass_sz is null",
    "mass_sz_neg_err": "Lower (negative) 1-sigma uncertainty on mass_sz in units of 10^14 solar masses; null if mass_sz is null",
    "y5r500": "Integrated Compton y-parameter measured within 5*R_500 in arcmin^2; dimensionless measure of total ICM thermal energy; low-scatter mass proxy; typical range 1e-4 to 1e-2 arcmin^2",
    "y5r500_error": "1-sigma uncertainty on Y_5R500 in arcmin^2; null if y5r500 is null",
    "snr": "Planck detection signal-to-noise ratio; catalog threshold SNR > 4.5; most massive clusters can reach SNR > 50",
    "det_pipeline_codes": "Bitmask or code string indicating which of the three detection pipelines confirmed this cluster: MMF1, MMF3, PwS (PowellSnakes)",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Galaxy clusters detected by the Planck satellite via the Sunyaev-Zeldovich effect, \
with mass, redshift, and signal-to-noise measurements sourced from NASA HEASARC.

Galaxy clusters are the largest gravitationally bound structures in the universe. The \
Planck satellite detected them through the thermal Sunyaev-Zeldovich effect: hot \
intracluster gas distorts the cosmic microwave background spectrum. The PSZ2 catalog is \
the second and final Planck SZ source catalog, based on the full mission data.

Galaxy clusters occupy a unique position in cosmology: they sit at the intersection of \
structure formation theory and observational cosmology. As the most massive virialized \
objects in the universe, their abundance as a function of mass and redshift is exquisitely \
sensitive to the matter density parameter, the amplitude of density fluctuations (sigma_8), \
and the dark energy equation of state. Counting clusters at different epochs therefore \
provides independent constraints on cosmological parameters complementary to those from \
the CMB power spectrum, baryon acoustic oscillations, and Type Ia supernovae.

The thermal Sunyaev-Zeldovich effect exploited by Planck arises when CMB photons \
inverse-Compton scatter off the hot electrons in the intracluster medium, which can reach \
temperatures of 10^7 to 10^8 K. This produces a characteristic spectral distortion that \
is independent of redshift, making SZ surveys uniquely capable of detecting massive \
clusters at any distance. The integrated SZ signal (Y_5R500) is tightly correlated with \
total cluster mass, providing a nearly mass-limited sample essential for cluster cosmology.
"""


def main():
    print("Fetching Planck PSZ2 galaxy clusters from HEASARC...")
    df = heasarc_query("plancksz2", ADQL)
    print(f"  {len(df):,} clusters fetched")

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_with_z = int(df["redshift"].notna().sum()) if "redshift" in df.columns else 0
    z_median = df["redshift"].median() if "redshift" in df.columns and n_with_z > 0 else 0
    z_max = df["redshift"].max() if "redshift" in df.columns else 0
    snr_median = df["snr"].median() if "snr" in df.columns else 0
    mass_median = df["mass_sz"].median() if "mass_sz" in df.columns else 0

    quick_stats = f"""\
- **{n_total:,}** galaxy clusters from the Planck PSZ2 catalog
- **{n_with_z:,}** with measured redshift (median z = {z_median:.3f}, max z = {z_max:.3f})
- Median detection SNR: **{snr_median:.1f}**
- Median SZ mass: **{mass_median:.2f}** x 10^14 M_sun"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/galaxy-clusters", split="train")
df = ds.to_pandas()

# Redshift distribution
z = df["redshift"].dropna()
print(f"{len(z):,} clusters with redshift, median z = {z.median():.3f}")

# Most massive clusters
top = df.nlargest(10, "mass_sz")[["name", "redshift", "mass_sz", "snr"]]
print(top)

# Sky map in Galactic coordinates
import matplotlib.pyplot as plt
plt.scatter(df["lii"], df["bii"], c=df["snr"], s=3, cmap="viridis")
plt.colorbar(label="SNR")
plt.xlabel("Galactic longitude (deg)")
plt.ylabel("Galactic latitude (deg)")
plt.title("Planck PSZ2 Galaxy Clusters")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Planck PSZ2 Galaxy Cluster Catalog",
        description=DESCRIPTION,
        tags=["space", "galaxy-cluster", "planck", "sz-effect", "cosmology",
              "astronomy", "open-data", "tabular-data", "parquet"],
        source_url="https://heasarc.gsfc.nasa.gov/W3Browse/all/plancksz2.html",
        task_categories=["tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA12110/PIA12110~small.jpg",
            "alt": "Hubble Deep Field revealing myriad galaxies across cosmic time",
            "credit": "NASA/ESA/STScI",
        },
        related_datasets=[
            "juliensimon/planck-sz2-clusters",
            "juliensimon/desi-dr1-redshifts",
            "juliensimon/pantheon-plus-sne-ia",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "ra", "dec", "lii", "bii", "redshift", "mass_sz",
                "mass_sz_pos_err", "mass_sz_neg_err", "y5r500",
                "y5r500_error", "snr",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="galaxy_clusters.parquet",
            min_rows=1000,
            expected_columns=["name", "ra", "dec", "snr"],
            critical_columns=["name", "ra", "dec"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update galaxy cluster catalog: {n_total:,} clusters",
        )
    print("Done.")


if __name__ == "__main__":
    main()
