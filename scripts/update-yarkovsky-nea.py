#!/usr/bin/env python3
"""Fetch Yarkovsky drift measurements for Near-Earth Asteroids from VizieR.

Source: VizieR J/AJ/159/92/table1 — Greenberg, A.H., Margot, J.-L., Verma, A.K.,
Taylor, P.A., Hodge, S.E. (2020), AJ 159, 92, 'Asteroid 1566 Icarus's Size,
Shape, Orbital History, and Astrometric Bias'. The companion table lists
direct Yarkovsky semimajor-axis drift detections for 247 NEAs obtained from a
homogeneous orbit-fit reanalysis of decades of optical and radar astrometry.
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/yarkovsky-nea-drifts"

ADQL = 'SELECT * FROM "J/AJ/159/92/table1"'

RENAME = {
    "planet": "asteroid_number",
    "name": "name",
    "f_name": "name_flag",
    "a": "semimajor_axis_au",
    "e": "eccentricity",
    "diam": "diameter_km",
    "f_diam": "diameter_flag",
    "no": "n_optical_observations",
    "nr": "n_radar_observations",
    "da/dt-o": "drift_orbit_fit_au_per_myr",
    "e_da/dt-o": "drift_orbit_fit_uncertainty_au_per_myr",
    "p-o": "drift_orbit_fit_pvalue",
    "da/dt-r": "drift_resampled_au_per_myr",
    "e_da/dt-r": "drift_resampled_uncertainty_au_per_myr",
    "p-r": "drift_resampled_pvalue",
    "sy": "drift_significance_sigma",
    "xi": "yarkovsky_efficiency",
    "obs_y-s": "first_observation_year",
    "obs_y-e": "last_observation_year",
}

COLUMN_DESCRIPTIONS = {
    "asteroid_number": "Permanent IAU minor-planet number (e.g. 1566 for Icarus, 1620 for Geographos); only numbered NEAs are included since orbit determination requires long-baseline astrometry",
    "name": "Asteroid name where assigned (e.g. 'Icarus', 'Geographos', 'Bennu'); blank for numbered-but-unnamed objects",
    "name_flag": "Reference flag indicating the source of the name designation",
    "semimajor_axis_au": "Heliocentric semimajor axis (au); osculating orbital element at the epoch of the underlying orbit solution",
    "eccentricity": "Orbital eccentricity (dimensionless, 0 to <1); the population includes the Apollo, Amor, Aten, and Atira NEA classes",
    "diameter_km": "Equivalent spherical diameter (km); compiled from albedo-corrected absolute magnitudes or direct radar/IR measurements where available",
    "diameter_flag": "Reference flag indicating the source of the diameter estimate",
    "n_optical_observations": "Number of optical astrometric observations used in the orbit fit",
    "n_radar_observations": "Number of radar astrometric observations used in the orbit fit; radar measurements anchor the orbit at the 10-meter range-precision level",
    "drift_orbit_fit_au_per_myr": "Yarkovsky semimajor-axis drift rate da/dt from the direct orbit fit (10^-4 au per million years); negative for retrograde rotators (drift inward), positive for prograde (drift outward)",
    "drift_orbit_fit_uncertainty_au_per_myr": "1-sigma uncertainty on the orbit-fit drift rate (10^-4 au/Myr)",
    "drift_orbit_fit_pvalue": "Two-tailed p-value for the orbit-fit drift detection; lower values indicate higher detection significance",
    "drift_resampled_au_per_myr": "Yarkovsky drift rate from the bootstrap-resampled orbit fit (10^-4 au/Myr); cross-check against orbit-fit value to mitigate astrometric bias",
    "drift_resampled_uncertainty_au_per_myr": "1-sigma uncertainty on the resampled drift rate (10^-4 au/Myr)",
    "drift_resampled_pvalue": "Two-tailed p-value for the resampled drift detection",
    "drift_significance_sigma": "Detection significance of the Yarkovsky drift in standard deviations; values >= 3 are considered confident detections",
    "yarkovsky_efficiency": "Empirical Yarkovsky efficiency xi (dimensionless), the ratio of observed drift to the maximum drift achievable by a perfectly absorbing-and-reradiating asteroid of the same size; xi values >> 1 are unphysical and flag candidate non-Yarkovsky perturbations",
    "first_observation_year": "Year of the earliest astrometric observation used in the fit; longer baselines yield more precise drift estimates",
    "last_observation_year": "Year of the latest astrometric observation used in the fit",
}

DESCRIPTION = """\
Direct measurements of the Yarkovsky semimajor-axis drift for 247 Near-Earth Asteroids — VizieR \
J/AJ/159/92 from Greenberg et al. (2020), AJ 159, 92.

The Yarkovsky effect is a thermal radiation force that slowly modifies an asteroid's orbit: \
sunlight absorbed on the dayside and reradiated from the rotating afternoon side produces a \
small net thrust. Over millions of years this drift accumulates to many millions of kilometers, \
delivering main-belt asteroids onto Earth-crossing orbits, dispersing collisional families, and \
shifting impact-probability calculations for hazardous NEAs (Bennu, Apophis, and 1950 DA are \
the canonical operationally critical cases). Direct detection requires high-precision orbit \
fits over decades of optical astrometry, ideally anchored by radar ranging at multiple \
apparitions; only a few hundred NEAs currently meet this threshold.

Each row in this dataset records one NEA with its orbital elements, diameter, observation \
count (optical + radar), and two independent drift estimates — a direct least-squares orbit \
fit and a bootstrap-resampled fit that cross-checks against systematic astrometric bias — \
together with their uncertainties, p-values, detection significance, and an empirical \
Yarkovsky efficiency parameter that flags physically implausible solutions.

This dataset complements juliensimon/jpl-small-body-database (orbital elements for the full \
small-body population), juliensimon/sentry-impact-risk (NEAs with non-zero Earth impact \
probability where Yarkovsky drift matters most), juliensimon/neowise-asteroid-properties \
(NEOWISE thermal-IR diameters that anchor Yarkovsky efficiency estimates), and \
juliensimon/nesvorny-asteroid-families (Yarkovsky-driven family dispersion).\
"""


def main():
    print("Fetching Yarkovsky NEA drift catalog from VizieR J/AJ/159/92...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} NEAs fetched")

    df.columns = [c.strip().lower() for c in df.columns]
    df = df.rename(columns=RENAME)

    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip().replace(
            {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
        )

    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    n_total = len(df)

    sig = pd.to_numeric(df["drift_significance_sigma"], errors="coerce").dropna() if "drift_significance_sigma" in df.columns else pd.Series(dtype=float)
    n_conf = int((sig >= 3).sum()) if len(sig) else 0
    n_highconf = int((sig >= 5).sum()) if len(sig) else 0

    drift = pd.to_numeric(df["drift_orbit_fit_au_per_myr"], errors="coerce").dropna() if "drift_orbit_fit_au_per_myr" in df.columns else pd.Series(dtype=float)
    n_retrograde = int((drift < 0).sum()) if len(drift) else 0
    n_prograde = int((drift > 0).sum()) if len(drift) else 0

    diam = pd.to_numeric(df["diameter_km"], errors="coerce").dropna() if "diameter_km" in df.columns else pd.Series(dtype=float)
    diam_line = f"\n- Diameter span: **{diam.min():.2f}** to **{diam.max():.1f}** km" if len(diam) else ""

    baseline = ""
    if {"first_observation_year", "last_observation_year"}.issubset(df.columns):
        first = pd.to_numeric(df["first_observation_year"], errors="coerce")
        last = pd.to_numeric(df["last_observation_year"], errors="coerce")
        bl = (last - first).dropna()
        if len(bl):
            baseline = f"\n- Observation baselines extend up to **{int(bl.max())} years** — necessary for unambiguous Yarkovsky detection"

    quick_stats = f"""\
- **{n_total}** Near-Earth Asteroids with direct Yarkovsky drift measurements
- **{n_conf}** confident detections at >= 3 sigma (**{n_highconf}** at >= 5 sigma)
- **{n_retrograde}** retrograde rotators (inward-drifting) + **{n_prograde}** prograde rotators (outward-drifting){diam_line}{baseline}"""

    usage = """\
```python
from datasets import load_dataset
import matplotlib.pyplot as plt

df = load_dataset("juliensimon/yarkovsky-nea-drifts", split="train").to_pandas()

# Drift rate vs diameter — Yarkovsky scales as 1/diameter for spherical bodies
mask = (df["diameter_km"].notna()
        & df["drift_orbit_fit_au_per_myr"].notna()
        & (df["drift_significance_sigma"] >= 3))
fig, ax = plt.subplots(figsize=(8, 6))
ax.errorbar(df.loc[mask, "diameter_km"],
            df.loc[mask, "drift_orbit_fit_au_per_myr"],
            yerr=df.loc[mask, "drift_orbit_fit_uncertainty_au_per_myr"],
            fmt="o", alpha=0.6)
ax.axhline(0, color="grey", linestyle="--")
ax.set_xscale("log")
ax.set_xlabel("Diameter (km)")
ax.set_ylabel("da/dt (10$^{-4}$ au / Myr)")
ax.set_title("Yarkovsky drift inversely scales with NEA size")
plt.tight_layout()
plt.show()

# Highest-confidence inward drifters — most relevant to long-term impact risk
top = df[df["drift_significance_sigma"] >= 5].nsmallest(15, "drift_orbit_fit_au_per_myr")
print(top[["asteroid_number", "name", "diameter_km",
           "drift_orbit_fit_au_per_myr", "drift_significance_sigma"]])
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Yarkovsky Drift Catalog for Near-Earth Asteroids",
        description=DESCRIPTION,
        tags=["space", "astronomy", "asteroids", "near-earth-asteroids", "neas",
              "yarkovsky-effect", "planetary-defense", "orbital-mechanics",
              "vizier", "open-data", "tabular-data", "parquet"],
        source_url="https://cdsarc.cds.unistra.fr/viz-bin/cat/J/AJ/159/92",
        license="other",
        license_name="vizier-scientific-use",
        license_link="https://cds.unistra.fr/vizier-org/licences_vizier.html",
        task_categories=["tabular-classification", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/asteroids-and-small-bodies-69c792b1e0240f3bf1235c66",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA25329/PIA25329~small.jpg",
            "alt": "NASA's DART spacecraft approaching the Didymos asteroid system",
            "credit": "NASA/Johns Hopkins APL",
        },
        related_datasets=[
            "juliensimon/jpl-small-body-database",
            "juliensimon/sentry-impact-risk",
            "juliensimon/neowise-asteroid-properties",
            "juliensimon/nesvorny-asteroid-families",
            "juliensimon/asteroid-lightcurves-lcdb",
            "juliensimon/bus-demeo-asteroid-taxonomy",
        ],
    ) as p:
        df_clean = p.clean(
            df,
            numeric=[
                "asteroid_number", "semimajor_axis_au", "eccentricity",
                "diameter_km", "n_optical_observations", "n_radar_observations",
                "drift_orbit_fit_au_per_myr", "drift_orbit_fit_uncertainty_au_per_myr",
                "drift_orbit_fit_pvalue",
                "drift_resampled_au_per_myr", "drift_resampled_uncertainty_au_per_myr",
                "drift_resampled_pvalue",
                "drift_significance_sigma", "yarkovsky_efficiency",
                "first_observation_year", "last_observation_year",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df_clean,
            filename="yarkovsky_nea_drifts.parquet",
            min_rows=200,
            expected_columns=["asteroid_number", "drift_orbit_fit_au_per_myr",
                              "drift_significance_sigma"],
            critical_columns=["asteroid_number"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Yarkovsky NEA drifts: {n_total} measurements",
        )
    print("Done.")


if __name__ == "__main__":
    main()
