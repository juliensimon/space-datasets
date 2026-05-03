#!/usr/bin/env python3
"""Fetch Gaia DR3 Compact Companion Candidates catalog from ESA Gaia Archive and upload to HF."""

import io

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

GAIA_TAP = "https://gea.esac.esa.int/tap-server/tap/sync"
HF_REPO = "juliensimon/gaia-dr3-compact-companions"

# -- Column mapping --------------------------------------------------------
RENAME = {}  # Gaia archive returns snake_case column names already

# -- Column descriptions for README schema table ---------------------------
COLUMN_DESCRIPTIONS = {
    "source_id": "Gaia DR3 unique source identifier; use for cross-matching with other Gaia tables",
    "period": "Orbital period in days; derived from ellipsoidal variability modeling",
    "period_error": "Uncertainty on the orbital period (days)",
    "t0_g": "Reference epoch (time of maximum in G-band light curve) expressed as BJD - 2455197.5 days",
    "t0_g_error": "Uncertainty on t0_g (days)",
    "t0_bp": "Reference epoch (time of maximum in BP-band light curve) expressed as BJD - 2455197.5 days",
    "t0_bp_error": "Uncertainty on t0_bp (days)",
    "t0_rp": "Reference epoch (time of maximum in RP-band light curve) expressed as BJD - 2455197.5 days",
    "t0_rp_error": "Uncertainty on t0_rp (days)",
    "model_mean_g": "Mean G-band magnitude derived from the fitted ellipsoidal variability model",
    "model_mean_g_error": "Uncertainty on the model mean G magnitude",
    "model_mean_bp": "Mean BP-band magnitude derived from the fitted ellipsoidal variability model",
    "model_mean_bp_error": "Uncertainty on the model mean BP magnitude",
    "model_mean_rp": "Mean RP-band magnitude derived from the fitted ellipsoidal variability model",
    "model_mean_rp_error": "Uncertainty on the model mean RP magnitude",
    "mod_min_mass_ratio": "Minimum companion-to-primary mass ratio (M_companion / M_primary) under median inclination assumption; lower bound on companion mass",
    "mod_min_mass_ratio_one_sigma": "Minimum mass ratio at 1-sigma upper confidence; accounts for inclination uncertainty",
    "mod_min_mass_ratio_three_sigma": "Minimum mass ratio at 3-sigma upper confidence; values > ~0.6 indicate the companion cannot be an ordinary main-sequence star, suggesting a compact object (white dwarf, neutron star, or black hole)",
    "alpha": "Ellipsoidal variability amplitude parameter; measures the degree of tidal deformation of the primary star by the unseen compact companion; higher values indicate stronger tidal distortion",
    "bp_rp": "BP minus RP color index (model_mean_bp - model_mean_rp); traces stellar temperature and reddening",
    "likely_compact": "Boolean flag: True if mod_min_mass_ratio_three_sigma > 0.5, indicating a likely compact (sub-stellar or degenerate) companion",
}

# -- Dataset description ---------------------------------------------------
DESCRIPTION = """\
The Gaia DR3 Compact Companion Candidates catalog contains ~6,300 candidates for binary \
systems where a normal (luminous) star orbits an unseen compact object — a white dwarf, \
neutron star, or black hole. These candidates were identified by the Gaia DR3 variability \
processing pipeline through the detection of ellipsoidal variations in the primary star's \
light curve.

Ellipsoidal variability arises when the primary star is tidally distorted into a prolate \
ellipsoid by the gravitational pull of its compact companion. As the system orbits, the \
projected cross-section of the distorted star changes, producing a characteristic \
double-humped light curve at half the true orbital period. Because the compact companion \
emits negligible light compared to the primary, no eclipse is required — the signal is \
purely photometric, making this technique uniquely sensitive to quiescent (non-accreting) \
compact objects that are invisible to X-ray telescopes.

The minimum mass ratio columns (mod_min_mass_ratio, mod_min_mass_ratio_one_sigma, \
mod_min_mass_ratio_three_sigma) constrain the companion mass assuming a range of orbital \
inclinations. A 3-sigma minimum mass ratio exceeding ~0.6 means the companion is too \
massive to be a main-sequence star at any plausible inclination, strongly suggesting a \
degenerate remnant. The alpha parameter encodes the ellipsoidal amplitude, which depends \
on the tidal distortion strength and therefore on the companion-to-primary mass ratio and \
the orbital separation.

This catalog represents one of the largest systematic searches for quiescent black hole \
and neutron star binaries ever conducted, and directly complements X-ray binary catalogs \
(HMXBs, LMXBs) which only detect systems currently undergoing active accretion. \
Identifying the dormant population is essential for constraining the true space density \
of stellar-mass black holes and the rate of compact object formation from stellar evolution.
"""


def fetch_compact_companions():
    """Fetch compact companion candidates from Gaia archive (single query, ~6,300 rows)."""
    query = (
        "SELECT * FROM gaiadr3.vari_compact_companion "
        "ORDER BY source_id"
    )
    print("  Fetching gaiadr3.vari_compact_companion ...")
    resp = requests.post(
        GAIA_TAP,
        data={
            "REQUEST": "doQuery",
            "LANG": "ADQL",
            "FORMAT": "csv",
            "QUERY": query,
            "MAXREC": 100_000,
        },
        timeout=300,
    )
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    return df


def main():
    print("Fetching Gaia DR3 Compact Companion Candidates from ESA Gaia Archive...")
    df = fetch_compact_companions()
    print(f"  {len(df):,} raw rows, columns: {list(df.columns)}")

    # Drop internal/solution columns
    for col in ["solution_id"]:
        if col in df.columns:
            df = df.drop(columns=[col])

    # Drop array/harmonic columns — they are stored as opaque strings in TAP CSV
    # and are not needed for the key science use cases (period, mass ratio, alpha)
    harmonic_cols = [c for c in df.columns if "harmonic_model_params" in c]
    if harmonic_cols:
        print(f"  Dropping harmonic array columns: {harmonic_cols}")
        df = df.drop(columns=harmonic_cols)

    # Rename (snake_case already returned by Gaia archive — no-op dict)
    df = df.rename(columns=RENAME)

    # Type conversions: ensure numeric types for float columns
    numeric_cols = [
        "period", "period_error",
        "t0_g", "t0_g_error",
        "t0_bp", "t0_bp_error",
        "t0_rp", "t0_rp_error",
        "model_mean_g", "model_mean_g_error",
        "model_mean_bp", "model_mean_bp_error",
        "model_mean_rp", "model_mean_rp_error",
        "mod_min_mass_ratio", "mod_min_mass_ratio_one_sigma",
        "mod_min_mass_ratio_three_sigma",
        "alpha",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # source_id as Int64 (nullable integer — avoids float conversion for large IDs)
    if "source_id" in df.columns:
        df["source_id"] = pd.to_numeric(df["source_id"], errors="coerce").astype("Int64")

    # Derived: BP-RP color index
    if "model_mean_bp" in df.columns and "model_mean_rp" in df.columns:
        df["bp_rp"] = df["model_mean_bp"] - df["model_mean_rp"]

    # Derived: likely compact companion flag
    if "mod_min_mass_ratio_three_sigma" in df.columns:
        df["likely_compact"] = df["mod_min_mass_ratio_three_sigma"] > 0.5

    # Keep only described columns (preserves column order & filters unknowns)
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Sort by source_id
    if "source_id" in df.columns:
        df = df.sort_values("source_id").reset_index(drop=True)

    # -- Quick stats --------------------------------------------------------
    n_total = len(df)
    n_likely = int(df["likely_compact"].sum()) if "likely_compact" in df.columns else 0
    period_median = df["period"].median() if "period" in df.columns else float("nan")
    period_min = df["period"].min() if "period" in df.columns else float("nan")
    period_max = df["period"].max() if "period" in df.columns else float("nan")
    mass_ratio_median = (
        df["mod_min_mass_ratio"].median()
        if "mod_min_mass_ratio" in df.columns
        else float("nan")
    )

    print(f"  {n_total:,} candidates, {n_likely:,} likely compact")
    print(f"  Median period: {period_median:.4f} days  ({period_min:.4f} – {period_max:.4f})")
    print(f"  Median min mass ratio: {mass_ratio_median:.4f}")

    quick_stats = f"""\
- **{n_total:,}** compact companion candidates
- **{n_likely:,}** likely compact objects (3-sigma mass ratio > 0.5)
- Median orbital period: {period_median:.4f} days (range: {period_min:.3f} – {period_max:.1f} days)
- Median minimum mass ratio: {mass_ratio_median:.4f}"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/gaia-dr3-compact-companions", split="train")
df = ds.to_pandas()

# Likely compact companions (neutron star / black hole candidates)
compact = df[df["likely_compact"] == True]
print(f"Likely compact companions: {len(compact):,}")

# Period vs mass ratio scatter (highlight compact candidates)
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(10, 6))
mask = df["likely_compact"]
ax.scatter(df.loc[~mask, "period"], df.loc[~mask, "mod_min_mass_ratio_three_sigma"],
           s=5, alpha=0.4, label="Other", color="steelblue")
ax.scatter(df.loc[mask, "period"], df.loc[mask, "mod_min_mass_ratio_three_sigma"],
           s=10, alpha=0.7, label="Likely compact", color="crimson")
ax.set_xlabel("Period (days)")
ax.set_ylabel("Min mass ratio (3σ)")
ax.set_xscale("log")
ax.legend()
plt.title("Gaia DR3 Compact Companion Candidates")
plt.show()

# Period histogram
df["period"].hist(bins=100, log=True)
plt.xlabel("Period (days)")
plt.ylabel("Count")
plt.title("Orbital Period Distribution")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Gaia DR3 Compact Companion Candidates",
        description=DESCRIPTION,
        tags=[
            "space", "gaia", "compact-objects", "black-holes", "neutron-stars",
            "variable-stars", "esa", "astronomy", "open-data", "tabular-data", "parquet",
        ],
        source_url="https://gea.esac.esa.int/archive/",
        task_categories=["tabular-classification", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA16695/PIA16695~small.jpg",
            "alt": "Artist's concept of a black hole binary system",
            "credit": "NASA/JPL-Caltech",
        },
        related_datasets=[
            "juliensimon/gaia-dr3-eclipsing-binaries",
            "juliensimon/gaia-dr3-spectroscopic-binaries",
            "juliensimon/black-hole-catalog",
            "juliensimon/xray-binaries",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "period", "period_error",
                "t0_g", "t0_g_error",
                "t0_bp", "t0_bp_error",
                "t0_rp", "t0_rp_error",
                "model_mean_g", "model_mean_g_error",
                "model_mean_bp", "model_mean_bp_error",
                "model_mean_rp", "model_mean_rp_error",
                "mod_min_mass_ratio", "mod_min_mass_ratio_one_sigma",
                "mod_min_mass_ratio_three_sigma",
                "alpha", "bp_rp",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="gaia_dr3_compact_companions.parquet",
            min_rows=5_000,
            expected_columns=["source_id", "period", "mod_min_mass_ratio"],
            critical_columns=["source_id", "period"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Gaia DR3 compact companion candidates: {n_total:,} sources",
        )
    print("Done.")


if __name__ == "__main__":
    main()
