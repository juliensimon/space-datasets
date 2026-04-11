#!/usr/bin/env python3
"""Fetch Cosmicflows-4 galaxy distance catalog from VizieR and upload to HF.

Source: Tully R.B., Kourkchi E., Courtois H.M., et al. (2023, ApJ, 944, 94)
VizieR catalog: J/ApJ/944/94
"""

import numpy as np
import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/cosmicflows-galaxy-distances"

# ── Source query ─────────────────────────────────────────────────────
ADQL = 'SELECT * FROM "J/ApJ/944/94/table2"'

# ── Column mapping ───────────────────────────────────────────────────
RENAME = {
    "PGC": "pgc",
    "1PGC": "pgc_primary",
    "T17": "morphological_type",
    "Vcmb": "velocity_cmb",
    "DM": "distance_modulus",
    "e_DM": "distance_modulus_err",
    "DMsnIa": "dm_sn_ia",
    "e_DMsnIa": "dm_sn_ia_err",
    "DMtf": "dm_tully_fisher",
    "e_DMtf": "dm_tully_fisher_err",
    "DMfp": "dm_fundamental_plane",
    "e_DMfp": "dm_fundamental_plane_err",
    "DMsbf": "dm_surface_brightness",
    "e_DMsbf": "dm_surface_brightness_err",
    "DMsnII": "dm_sn_ii",
    "e_DMsnII": "dm_sn_ii_err",
    "DMtrgb": "dm_trgb",
    "e_DMtrgb": "dm_trgb_err",
    "DMceph": "dm_cepheid",
    "e_DMceph": "dm_cepheid_err",
    "DMmas": "dm_maser",
    "e_DMmas": "dm_maser_err",
    "RAJ2000": "ra_deg",
    "DEJ2000": "dec_deg",
    "GLON": "glon_deg",
    "GLAT": "glat_deg",
    "SGL": "sgl_deg",
    "SGB": "sgb_deg",
    "CF3": "in_cf3",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "pgc": "Principal Galaxies Catalog number; the primary cross-catalog galaxy identifier used by HyperLEDA and most modern galaxy databases",
    "pgc_primary": "PGC number of the group primary (for galaxies associated with a brighter host); equals pgc for isolated galaxies",
    "morphological_type": "de Vaucouleurs numerical type T: -5 = elliptical (E), 0 = lenticular (S0), 1-9 = spiral (Sa=1 to Sd=7), 10 = irregular; null if unclassified",
    "velocity_cmb": "Recession velocity in the CMB rest frame in km/s (cz corrected for Local Group and CMB dipole); range ~0 to ~60,000 km/s",
    "distance_modulus": "Best-estimate distance modulus mu = 5*log10(d/10 pc) in mag; range ~25 (nearby) to ~38 (500 Mpc); null if no distance indicator available",
    "distance_modulus_err": "1-sigma uncertainty on the best-estimate distance modulus in mag; ~0.05-0.10 for Cepheids/TRGB, ~0.40 for Tully-Fisher/FP",
    "distance_mpc": "Physical distance in Mpc derived from distance_modulus via d = 10^((mu-25)/5); null if distance_modulus is null",
    "dm_sn_ia": "Distance modulus from Type Ia supernovae standardizable candles in mag; null if no SNe Ia observation for this galaxy",
    "dm_sn_ia_err": "1-sigma uncertainty on the SNe Ia distance modulus in mag; null if dm_sn_ia is null",
    "dm_tully_fisher": "Distance modulus from the Tully-Fisher relation (spiral rotation width vs. luminosity) in mag; ~20% precision; null if not applicable",
    "dm_tully_fisher_err": "1-sigma uncertainty on the Tully-Fisher distance modulus in mag; null if dm_tully_fisher is null",
    "dm_fundamental_plane": "Distance modulus from the fundamental plane of elliptical galaxies (sigma, Re, SB) in mag; ~20% precision; null if not applicable",
    "dm_fundamental_plane_err": "1-sigma uncertainty on the fundamental plane distance modulus in mag; null if dm_fundamental_plane is null",
    "dm_surface_brightness": "Distance modulus from surface brightness fluctuations (SBF) of elliptical/S0 galaxies in mag; null if not applicable",
    "dm_surface_brightness_err": "1-sigma uncertainty on the SBF distance modulus in mag; null if dm_surface_brightness is null",
    "dm_sn_ii": "Distance modulus from Type II supernovae (expanding photosphere method) in mag; null if no SNe II observation",
    "dm_sn_ii_err": "1-sigma uncertainty on the SNe II distance modulus in mag; null if dm_sn_ii is null",
    "dm_trgb": "Distance modulus from the tip of the red giant branch (TRGB) method in mag; ~5% precision; limited to d < ~30 Mpc; null if not measured",
    "dm_trgb_err": "1-sigma uncertainty on the TRGB distance modulus in mag; null if dm_trgb is null",
    "dm_cepheid": "Distance modulus from Cepheid period-luminosity relation in mag; most precise method (~5%); limited to d < ~30 Mpc; null if not measured",
    "dm_cepheid_err": "1-sigma uncertainty on the Cepheid distance modulus in mag; null if dm_cepheid is null",
    "dm_maser": "Distance modulus from megamaser geometric distance (water masers in Keplerian orbits) in mag; highest-precision method; null for most galaxies",
    "dm_maser_err": "1-sigma uncertainty on the maser distance modulus in mag; null if dm_maser is null",
    "ra_deg": "ICRS J2000.0 right ascension in degrees (0-360)",
    "dec_deg": "ICRS J2000.0 declination in degrees (-90 to +90)",
    "glon_deg": "Galactic longitude in degrees (0-360)",
    "glat_deg": "Galactic latitude in degrees (-90 to +90)",
    "sgl_deg": "Supergalactic longitude in degrees (0-360); coordinate system aligned with the local supercluster plane",
    "sgb_deg": "Supergalactic latitude in degrees (-90 to +90); positive toward the north supergalactic pole",
    "in_cf3": "True if this galaxy also appeared in the earlier Cosmicflows-3 catalog; False for galaxies newly added in CF4",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
The Cosmicflows-4 (CF4) catalog is the most comprehensive compilation of galaxy distances \
ever assembled. Published by Tully et al. (2023), it contains distance measurements derived \
from eight independent methods, enabling studies of the cosmic distance ladder, large-scale \
structure, and peculiar velocities of galaxies.

Galaxy distances are fundamental to cosmology. Unlike redshifts, which mix Hubble flow \
with peculiar velocities, direct distance measurements let us map the true 3D distribution \
of matter. CF4 consolidates distances from Type Ia supernovae, the Tully-Fisher relation, \
the fundamental plane, tip of the red giant branch (TRGB), Cepheid period-luminosity, \
surface brightness fluctuations (SBF), Type II supernovae, and maser observations.

Each entry includes the PGC galaxy identifier, coordinates (equatorial, galactic, \
supergalactic), CMB-frame velocity, a best-estimate distance modulus, and individual \
distance moduli from each method where available.

Accurate galaxy distances are the foundation of the extragalactic distance ladder and one \
of the most challenging measurements in observational astronomy. The Hubble constant H0, \
which sets the expansion rate of the universe, can only be determined by measuring both the \
recession velocity and the true distance of galaxies. The current "Hubble tension" -- a \
persistent 4-5 sigma discrepancy between the local measurement of H0 (approximately 73 \
km/s/Mpc from Cepheids and supernovae) and the value inferred from the cosmic microwave \
background (approximately 67 km/s/Mpc from Planck) -- is one of the most important open \
problems in cosmology. Cosmicflows-4 provides the data needed to calibrate and cross-check \
each rung of the distance ladder.

Beyond the Hubble constant, galaxy distances reveal the peculiar velocity field -- the \
deviations from smooth Hubble expansion caused by the gravitational pull of large-scale \
structure. By subtracting the Hubble flow from observed recession velocities, CF4 enables \
the reconstruction of the three-dimensional matter density field, revealing superclusters, \
voids, and the Great Attractor region.
"""


def main():
    print("Fetching Cosmicflows-4 from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} galaxy distances")

    # Drop VizieR internal columns
    for col in ["recno"]:
        if col in df.columns:
            df = df.drop(columns=[col])

    df = df.rename(columns={k: v for k, v in RENAME.items() if k in df.columns})

    # Convert in_cf3 flag to boolean
    if "in_cf3" in df.columns:
        df["in_cf3"] = pd.to_numeric(df["in_cf3"], errors="coerce").fillna(0).astype(int).astype(bool)

    # Derive distance in Mpc from distance modulus: d = 10^((DM - 25) / 5)
    if "distance_modulus" in df.columns:
        df["distance_mpc"] = np.round(10 ** ((df["distance_modulus"] - 25) / 5), 3)

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Sort by PGC number
    if "pgc" in df.columns:
        df = df.sort_values("pgc").reset_index(drop=True)

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_with_tf = int(df["dm_tully_fisher"].notna().sum()) if "dm_tully_fisher" in df.columns else 0
    n_with_snia = int(df["dm_sn_ia"].notna().sum()) if "dm_sn_ia" in df.columns else 0
    n_with_fp = int(df["dm_fundamental_plane"].notna().sum()) if "dm_fundamental_plane" in df.columns else 0
    n_with_trgb = int(df["dm_trgb"].notna().sum()) if "dm_trgb" in df.columns else 0
    n_with_ceph = int(df["dm_cepheid"].notna().sum()) if "dm_cepheid" in df.columns else 0
    n_in_cf3 = int(df["in_cf3"].sum()) if "in_cf3" in df.columns else 0
    median_dist = df["distance_mpc"].median() if "distance_mpc" in df.columns else 0

    quick_stats = f"""\
- **{n_total:,}** galaxy distance measurements
- **{n_with_tf:,}** with Tully-Fisher distances
- **{n_with_fp:,}** with fundamental plane distances
- **{n_with_snia:,}** with Type Ia supernova distances
- **{n_with_trgb:,}** with TRGB distances
- **{n_with_ceph:,}** with Cepheid distances
- **{n_in_cf3:,}** also in Cosmicflows-3
- Median distance: **{median_dist:.1f} Mpc**"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/cosmicflows-galaxy-distances", split="train")
df = ds.to_pandas()

# Galaxies within 100 Mpc (local universe)
local = df[df["distance_mpc"] <= 100]
print(f"{len(local):,} galaxies within 100 Mpc")

# Galaxies with Cepheid-calibrated distances
cepheids = df[df["dm_cepheid"].notna()]
print(f"{len(cepheids):,} with Cepheid distances")

# Sky distribution in supergalactic coordinates
import matplotlib.pyplot as plt
plt.scatter(df["sgl_deg"], df["sgb_deg"], s=0.2, alpha=0.3, c=df["distance_mpc"],
            cmap="viridis", vmax=200)
plt.colorbar(label="Distance (Mpc)")
plt.xlabel("Supergalactic Longitude")
plt.ylabel("Supergalactic Latitude")
plt.title("Cosmicflows-4: Galaxy Distance Map")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Cosmicflows-4 Galaxy Distances",
        description=DESCRIPTION,
        tags=["space", "galaxies", "distances", "cosmology", "astronomy",
              "open-data", "tabular-data", "parquet"],
        source_url="https://vizier.cds.unistra.fr/viz-bin/VizieR?-source=J/ApJ/944/94",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA12110/PIA12110~small.jpg",
            "alt": "Hubble Deep Field revealing myriad galaxies across cosmic time",
            "credit": "NASA/ESA/STScI",
        },
        related_datasets=[
            "juliensimon/messier-catalog",
            "juliensimon/ngc-ic-catalog",
            "juliensimon/nasa-exoplanets",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "pgc", "pgc_primary", "morphological_type", "velocity_cmb",
                "distance_modulus", "distance_modulus_err",
                "dm_sn_ia", "dm_sn_ia_err",
                "dm_tully_fisher", "dm_tully_fisher_err",
                "dm_fundamental_plane", "dm_fundamental_plane_err",
                "dm_surface_brightness", "dm_surface_brightness_err",
                "dm_sn_ii", "dm_sn_ii_err",
                "dm_trgb", "dm_trgb_err",
                "dm_cepheid", "dm_cepheid_err",
                "dm_maser", "dm_maser_err",
                "ra_deg", "dec_deg",
                "glon_deg", "glat_deg",
                "sgl_deg", "sgb_deg",
                "distance_mpc",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="cosmicflows_galaxy_distances.parquet",
            min_rows=40_000,
            expected_columns=["pgc", "ra_deg", "dec_deg", "distance_modulus", "velocity_cmb"],
            critical_columns=["pgc", "ra_deg", "dec_deg", "distance_modulus"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Cosmicflows-4 galaxy distances: {n_total:,} galaxies",
        )
    print("Done.")


if __name__ == "__main__":
    main()
