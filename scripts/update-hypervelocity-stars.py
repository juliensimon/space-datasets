#!/usr/bin/env python3
"""Fetch the Li et al. 2023 hypervelocity stars catalog from VizieR.

Source: VizieR J/AJ/166/12/table2 — Li, Q.-Z., Huang, Y., Dong, X.-B.,
Zhang, H.-W., Beers, T.C., Yuan, Z. (2023), AJ 166, 12. 52 hypervelocity
star candidates — stars whose total Galactocentric velocity exceeds the
Milky Way escape speed, indicating either a close encounter with the central
supermassive black hole (Sgr A*), dynamical ejection from a binary tidal
disruption, or accretion from a disrupted satellite galaxy.
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/hypervelocity-stars-li2023"

ADQL = 'SELECT * FROM "J/AJ/166/12/table2"'

RENAME = {
    "raj2000": "ra",
    "dej2000": "dec",
    "gaia": "gaia_source_id",
    "pmra": "proper_motion_ra",
    "e_pmra": "proper_motion_ra_uncertainty",
    "pmde": "proper_motion_dec",
    "e_pmde": "proper_motion_dec_uncertainty",
    "vlos": "line_of_sight_velocity_kms",
    "e_vlos": "line_of_sight_velocity_uncertainty_kms",
    "dist": "heliocentric_distance_kpc",
    "e_dist": "heliocentric_distance_uncertainty_kpc",
    "vgsr": "galactocentric_velocity_kms",
    "e_vgsr": "galactocentric_velocity_uncertainty_kms",
    "pub-mw": "p_unbound_mw_potential",
    "pub-m18": "p_unbound_mcmillan2018",
    "pub-d19": "p_unbound_deason2019",
    "pub-bmw": "p_unbound_bmw_potential",
    "pub-w17": "p_unbound_williams2017",
}

COLUMN_DESCRIPTIONS = {
    "name": "Star designation in the Li et al. 2023 catalog (e.g. 'LG-HVS1' to 'LG-HVS52'); LG = LAMOST + Gaia compilation",
    "gaia_source_id": "Gaia DR3 source_id (64-bit integer); links to full Gaia astrometry, photometry, and spectroscopy",
    "ra": "Right ascension (degrees, J2000) from Gaia DR3",
    "dec": "Declination (degrees, J2000) from Gaia DR3",
    "proper_motion_ra": "Proper motion in right ascension (mas/yr) including cos(Dec) factor; from Gaia DR3",
    "proper_motion_ra_uncertainty": "1-sigma uncertainty on the RA proper motion (mas/yr)",
    "proper_motion_dec": "Proper motion in declination (mas/yr) from Gaia DR3",
    "proper_motion_dec_uncertainty": "1-sigma uncertainty on the declination proper motion (mas/yr)",
    "line_of_sight_velocity_kms": "Heliocentric radial (line-of-sight) velocity (km/s) from spectroscopy; combined with proper motion and distance to construct full 3D velocity",
    "line_of_sight_velocity_uncertainty_kms": "1-sigma uncertainty on the line-of-sight velocity (km/s)",
    "heliocentric_distance_kpc": "Heliocentric distance (kpc); typically from spectro-photometric methods or Gaia parallax for nearer objects",
    "heliocentric_distance_uncertainty_kpc": "1-sigma distance uncertainty (kpc); dominates the velocity-budget error for most candidates",
    "galactocentric_velocity_kms": "Total velocity in the Galactic standard of rest frame (km/s); HVS candidates exceed ~530 km/s (the local escape velocity)",
    "galactocentric_velocity_uncertainty_kms": "1-sigma uncertainty on the Galactocentric velocity (km/s); a tight measurement (<10%) is essential to confirm HVS status",
    "p_unbound_mw_potential": "Posterior probability of being gravitationally unbound from the Milky Way using the standard MW potential model (Bovy 2015); >0.5 = likely escaping",
    "p_unbound_mcmillan2018": "Unbound probability using the McMillan 2018 Milky Way potential",
    "p_unbound_deason2019": "Unbound probability using the Deason 2019 Milky Way potential (higher mass)",
    "p_unbound_bmw_potential": "Unbound probability using a baryonic-MW potential variant",
    "p_unbound_williams2017": "Unbound probability using the Williams et al. 2017 Milky Way potential",
}

DESCRIPTION = """\
The Li et al. 2023 catalog of 52 hypervelocity star (HVS) candidates — VizieR J/AJ/166/12 — \
combining LAMOST and Gaia data to identify stars whose total Galactocentric velocity exceeds \
the Milky Way escape speed under multiple plausible mass models.

Hypervelocity stars are rare tracers of extreme dynamical processes: ejection by close \
encounters with the central supermassive black hole (the Hills mechanism), tidal disruption \
of a binary in the Galactic center, dynamical ejection from a dense stellar cluster, or \
accretion of stars from a disrupted dwarf satellite. Confirming HVS status requires very \
precise 6D phase-space measurements (sky position from Gaia, proper motion from Gaia, \
line-of-sight velocity from spectroscopy, and distance from spectro-photometric or parallax \
methods) combined with an adopted Galactic potential model to compute the escape probability.

Each row records the Gaia DR3 source_id (for full-context follow-up), J2000 sky position, \
proper motion in both equatorial axes with uncertainties, line-of-sight velocity, \
heliocentric distance, the derived total Galactocentric velocity (V_GSR), and the unbound \
probability evaluated under five independent Milky Way potential models (Bovy 2015, McMillan \
2018, Deason 2019, a baryonic-MW variant, and Williams et al. 2017) — the columns starting \
with 'p_unbound_' let you stress-test how a candidate's HVS classification depends on the \
chosen potential model. Use this dataset alongside juliensimon/gaia-dr3-spectroscopic-binaries \
(binary-ejection candidates), juliensimon/black-hole-catalog (for Sgr A*-context), \
juliensimon/cns5-nearby-stars (the local-stellar comparison sample), and \
juliensimon/galah-dr4-stellar-abundances (abundance-based progenitor diagnostics).\
"""


def main():
    print("Fetching Li 2023 hypervelocity stars catalog from VizieR J/AJ/166/12...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} HVS candidates fetched")

    df.columns = [c.strip().lower() for c in df.columns]
    df = df.rename(columns=RENAME)

    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip().replace(
            {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
        )

    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    n_total = len(df)

    vgsr = pd.to_numeric(df["galactocentric_velocity_kms"], errors="coerce").dropna() if "galactocentric_velocity_kms" in df.columns else pd.Series(dtype=float)
    vgsr_line = f"\n- Galactocentric velocities span **{vgsr.min():.0f}** to **{vgsr.max():.0f}** km/s (local escape speed ~530 km/s)" if len(vgsr) else ""

    confident = 0
    if "p_unbound_mw_potential" in df.columns:
        p = pd.to_numeric(df["p_unbound_mw_potential"], errors="coerce")
        confident = int((p > 0.5).sum())

    dist = pd.to_numeric(df["heliocentric_distance_kpc"], errors="coerce").dropna() if "heliocentric_distance_kpc" in df.columns else pd.Series(dtype=float)
    dist_line = f"\n- Heliocentric distances: **{dist.min():.1f}** to **{dist.max():.1f}** kpc — most HVS lie in the outer Galactic halo" if len(dist) else ""

    quick_stats = f"""\
- **{n_total}** hypervelocity star (HVS) candidates from the Li et al. 2023 LAMOST+Gaia search
- **{confident}** candidates with > 0.5 probability of being gravitationally unbound under the standard Milky Way potential{vgsr_line}{dist_line}
- Each candidate is scored under **5 independent Galactic potential models** to assess robustness of the HVS classification"""

    usage = """\
```python
from datasets import load_dataset
import matplotlib.pyplot as plt

df = load_dataset("juliensimon/hypervelocity-stars-li2023", split="train").to_pandas()

# Compare unbound probabilities across the 5 Galactic potential models
pot_cols = [c for c in df.columns if c.startswith("p_unbound_")]
fig, ax = plt.subplots(figsize=(8, 6))
df[pot_cols].plot(kind="box", ax=ax)
ax.axhline(0.5, color="red", linestyle="--", label="50% unbound threshold")
ax.set_ylabel("P(unbound)")
ax.set_title("HVS unbound probability under 5 MW potential models")
ax.legend()
plt.tight_layout()
plt.show()

# Top-confidence escapers under all 5 models (most robust HVS candidates)
robust = df[df[pot_cols].min(axis=1) > 0.5]
print(f"{len(robust)} stars unbound under all 5 potential models")
print(robust[["name", "galactocentric_velocity_kms", "heliocentric_distance_kpc"]])
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Hypervelocity Stars Catalog (Li 2023)",
        description=DESCRIPTION,
        tags=["space", "astronomy", "stars", "hypervelocity-stars", "galactic-dynamics",
              "milky-way", "gaia", "lamost", "vizier", "open-data",
              "tabular-data", "parquet"],
        source_url="https://cdsarc.cds.unistra.fr/viz-bin/cat/J/AJ/166/12",
        license="other",
        license_name="vizier-scientific-use",
        license_link="https://cds.unistra.fr/vizier-org/licences_vizier.html",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/stellar-catalogs-69c792b1a52ab2757b0eaa57",
        banner={
            "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e000191/GSFC_20171208_Archive_e000191~medium.jpg",
            "alt": "A youthful globular star cluster observed by the Hubble Space Telescope",
            "credit": "NASA/ESA/Hubble",
        },
        related_datasets=[
            "juliensimon/gaia-dr3-spectroscopic-binaries",
            "juliensimon/black-hole-catalog",
            "juliensimon/cns5-nearby-stars",
            "juliensimon/galah-dr4-stellar-abundances",
            "juliensimon/hot-subdwarf-stars",
            "juliensimon/symbiotic-stars-catalog",
        ],
    ) as p:
        df_clean = p.clean(
            df,
            numeric=[
                "ra", "dec",
                "proper_motion_ra", "proper_motion_ra_uncertainty",
                "proper_motion_dec", "proper_motion_dec_uncertainty",
                "line_of_sight_velocity_kms", "line_of_sight_velocity_uncertainty_kms",
                "heliocentric_distance_kpc", "heliocentric_distance_uncertainty_kpc",
                "galactocentric_velocity_kms", "galactocentric_velocity_uncertainty_kms",
                "p_unbound_mw_potential", "p_unbound_mcmillan2018",
                "p_unbound_deason2019", "p_unbound_bmw_potential",
                "p_unbound_williams2017",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df_clean,
            filename="hypervelocity_stars.parquet",
            min_rows=40,
            expected_columns=["name", "galactocentric_velocity_kms",
                              "p_unbound_mw_potential"],
            critical_columns=["name", "ra", "dec"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update hypervelocity stars: {n_total} candidates",
        )
    print("Done.")


if __name__ == "__main__":
    main()
