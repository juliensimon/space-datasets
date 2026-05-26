#!/usr/bin/env python3
"""Fetch Kepler Eclipsing Binary catalog from VizieR and upload to HF.

Source: Slawson, R.W. et al. (2011, AJ 142, 160) — 2,177 Kepler eclipsing
binaries with orbital periods, morphology parameters, and stellar properties.
VizieR catalog: J/AJ/142/160
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/kepler-eclipsing-binaries"

# Slawson et al. (2011) -- 2,177 Kepler eclipsing binaries
ADQL_MAIN = 'SELECT * FROM "J/AJ/142/160/table3"'

# Kirk et al. (2016) -- updated catalog, fallback if main is too small
ADQL_ALT = 'SELECT * FROM "J/AJ/148/37/table1"'

# ── Column mapping ───────────────────────────────────────────────────
RENAME = {
    "KIC": "kic_id",
    "Per": "period_days",
    "Morph": "morphology",
    "morph": "morphology",
    "Teff": "teff_k",
    "logg": "log_g",
    "Kpmag": "kepler_mag",
    "Kp": "kepler_mag",
    "RA_ICRS": "ra_deg",
    "RAICRS": "ra_deg",
    "RAJ2000": "ra_deg",
    "_RA": "ra_deg",
    "DE_ICRS": "dec_deg",
    "DEICRS": "dec_deg",
    "DEJ2000": "dec_deg",
    "_DE": "dec_deg",
    "BJD0": "epoch_bjd",
    "T0": "epoch_bjd",
    "e_Per": "period_err",
    "Dur1": "duration_primary",
    "Dur2": "duration_secondary",
    "Sep": "separation",
    "Depth1": "depth_primary",
    "Depth2": "depth_secondary",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "kic_id": "Kepler Input Catalog (KIC) identifier for the host star; used to cross-reference Kepler photometry and stellar parameters",
    "period_days": "Orbital period in days derived from eclipse timing; contact binaries: <1 day, detached systems: up to ~1000 days; null if period could not be determined",
    "morphology": "Continuous morphology parameter (0-1) describing light curve shape; 0 = well-detached (two distinct eclipses with flat out-of-eclipse baseline), 1 = contact/over-contact (sinusoidal, stars fill or overflow Roche lobes); intermediate values indicate semi-detached systems",
    "teff_k": "Host star effective temperature in Kelvin from KIC or spectroscopic follow-up; range ~3500-10000 K; null if not available in the catalog",
    "log_g": "Host star log surface gravity in cm/s^2 (cgs); main sequence: 4-5 dex, subgiants: 3-4 dex, giants: <3 dex; used with Teff to classify stellar evolution stage",
    "kepler_mag": "Kepler-band (white-light, ~430-900 nm) apparent magnitude of the system; brighter targets have better photometric precision",
    "ra_deg": "Right ascension in decimal degrees (ICRS J2000.0)",
    "dec_deg": "Declination in decimal degrees (ICRS J2000.0)",
    "epoch_bjd": "Reference epoch of primary eclipse minimum in Barycentric Julian Date (BJD); used as the zero-point for computing eclipse timing residuals",
    "period_err": "Uncertainty on the orbital period in days",
    "duration_primary": "Duration of primary eclipse (deeper minimum) in days",
    "duration_secondary": "Duration of secondary eclipse in days; asymmetry between primary and secondary durations indicates orbital eccentricity",
    "depth_primary": "Primary eclipse depth as fractional flux loss; equals (R2/R1)^2 for a total eclipse; diagnostic of the stellar radius ratio",
    "depth_secondary": "Secondary eclipse depth as fractional flux loss; ratio of primary to secondary depth constrains the temperature ratio of the two components",
    "separation": "Fractional phase separation between primary and secondary eclipses; 0.5 = circular orbit; deviations indicate nonzero eccentricity",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Catalog of eclipsing binary systems identified by the Kepler mission, with orbital \
periods, morphology parameters, and stellar properties.

Eclipsing binaries are pairs of stars whose orbital plane is aligned with our line of \
sight, producing periodic dips in brightness as one star passes in front of the other. \
The Kepler mission's exquisite photometric precision made it ideal for detecting and \
characterizing these systems. This catalog from Slawson et al. (2011) provides the \
definitive Kepler eclipsing binary list with orbital periods, eclipse morphology \
parameters, and derived stellar properties.

Eclipsing binaries are astrophysical laboratories of extraordinary precision. Because the \
geometry of mutual eclipses is tightly constrained by Kepler's laws and photometric \
observations, these systems yield direct, model-independent measurements of stellar masses \
and radii -- the fundamental benchmarks against which all stellar evolution theory is \
calibrated. The morphology parameter quantifies the light curve shape on a continuous scale, \
distinguishing well-detached systems from contact binaries where both stars overflow their \
Roche lobes and share a common envelope.

The Kepler eclipsing binary catalog is a cornerstone of binary star research. Its uniform \
four-year photometric baseline and micro-magnitude precision enabled the discovery of \
systems with period changes, apsidal motion, third-body eclipse timing variations, and \
pulsating components. The catalog also provides a critical training set for machine learning \
classifiers designed to identify eclipsing binaries in TESS, LSST, and other modern surveys.
"""


def main():
    print("Fetching Kepler eclipsing binaries (Slawson et al.) from VizieR...")
    df = vizier_query(ADQL_MAIN)
    print(f"  Main catalog: {len(df):,} rows")

    # If main catalog is unexpectedly small, try alternate
    if len(df) < 1500:
        print("  Main catalog too small, trying Kirk et al. catalog...")
        df_alt = vizier_query(ADQL_ALT)
        print(f"  Alt catalog: {len(df_alt):,} rows")
        if len(df_alt) > len(df):
            df = df_alt

    rename_map = {k: v for k, v in RENAME.items() if k in df.columns}
    df = df.rename(columns=rename_map)

    # Snake-case remaining columns
    already_renamed = set(rename_map.values())
    snake_map = {}
    for col in df.columns:
        if col not in already_renamed:
            snake = col.replace(" ", "_").replace("-", "_").lower()
            if snake != col:
                snake_map[col] = snake
    if snake_map:
        df = df.rename(columns=snake_map)

    # Drop VizieR internal columns
    for col in ["recno"]:
        if col in df.columns:
            df = df.drop(columns=[col])

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_with_period = int(df["period_days"].notna().sum()) if "period_days" in df.columns else 0
    n_with_teff = int(df["teff_k"].notna().sum()) if "teff_k" in df.columns else 0
    median_period = df["period_days"].median() if "period_days" in df.columns else 0
    n_contact = 0
    if "morphology" in df.columns:
        n_contact = int((df["morphology"] > 0.7).sum())
    n_detached = 0
    if "morphology" in df.columns:
        n_detached = int((df["morphology"] < 0.3).sum())

    quick_stats = f"""\
- **{n_total:,}** eclipsing binaries
- **{n_with_period:,}** with measured orbital periods
- **{n_with_teff:,}** with effective temperature estimates
- Median orbital period: **{median_period:.3f}** days
- **{n_detached:,}** detached systems (morphology < 0.3)
- **{n_contact:,}** contact/over-contact systems (morphology > 0.7)"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/kepler-eclipsing-binaries", split="train")
df = ds.to_pandas()

# Short-period binaries (< 1 day)
short = df[df["period_days"] < 1.0]
print(f"{len(short):,} short-period binaries")

# Period distribution
import matplotlib.pyplot as plt
df["period_days"].dropna().hist(bins=100, log=True)
plt.xlabel("Orbital Period (days)")
plt.ylabel("Count")
plt.title("Kepler EB Period Distribution")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Kepler Eclipsing Binary Catalog",
        description=DESCRIPTION,
        tags=["space", "kepler", "eclipsing-binary", "binary-star", "astronomy",
              "open-data", "tabular-data", "parquet"],
        source_url="https://vizier.cds.unistra.fr/viz-bin/VizieR-3?-source=J/AJ/142/160",
        license="other",
        license_name="vizier-scientific-use",
        license_link="https://cds.unistra.fr/vizier-org/licences_vizier.html",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA21423/PIA21423~small.jpg",
            "alt": "Artist concept of the surface of TRAPPIST-1f exoplanet",
            "credit": "NASA/JPL-Caltech",
        },
        related_datasets=[
            "juliensimon/kepler-transit-timing",
            "juliensimon/gcvs-variable-stars",
            "juliensimon/nasa-exoplanets",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "kic_id", "period_days", "teff_k", "log_g", "kepler_mag",
                "ra_deg", "dec_deg", "epoch_bjd", "period_err",
                "duration_primary", "duration_secondary", "separation",
                "depth_primary", "depth_secondary", "morphology",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="kepler_eclipsing_binaries.parquet",
            min_rows=1500,
            expected_columns=["kic_id", "period_days"],
            critical_columns=["kic_id", "period_days"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Kepler eclipsing binaries: {n_total:,} systems",
        )
    print("Done.")


if __name__ == "__main__":
    main()
