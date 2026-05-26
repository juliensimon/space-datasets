#!/usr/bin/env python3
"""Fetch Gaia DR3 Rotation Modulation catalog from ESA Gaia Archive and upload to HF."""

import io
import time

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

GAIA_TAP = "https://gea.esac.esa.int/tap-server/tap/sync"
HF_REPO = "juliensimon/gaia-dr3-rotation-modulation"
PAGE_SIZE = 500_000

# -- Column mapping --------------------------------------------------------
RENAME = {
    # Gaia archive already returns snake_case for this table; no renames needed.
}

# -- Column descriptions for README schema table ---------------------------
COLUMN_DESCRIPTIONS = {
    "source_id": "Gaia DR3 unique source identifier; use for cross-matching with other Gaia tables",
    "num_segments": "Number of time segments used in the rotation analysis; more segments generally improve period reliability",
    "num_outliers": "Number of photometric outliers excluded from the rotation analysis",
    "best_rotation_period": "Best-estimate stellar rotation period in days; the fundamental scientific output — shorter periods indicate younger, more active stars",
    "best_rotation_period_error": "Formal uncertainty on the best-estimate rotation period (days)",
    "g_unspotted": "Estimated unspotted G-band apparent magnitude (brightness the star would have without starspots)",
    "g_unspotted_error": "Uncertainty on the unspotted G-band magnitude",
    "bp_unspotted": "Estimated unspotted BP-band (330–680 nm) apparent magnitude",
    "bp_unspotted_error": "Uncertainty on the unspotted BP-band magnitude",
    "rp_unspotted": "Estimated unspotted RP-band (630–1050 nm) apparent magnitude",
    "rp_unspotted_error": "Uncertainty on the unspotted RP-band magnitude",
    "max_activity_index_g": "Maximum G-band activity index across all time segments; proxy for spot coverage fraction — larger values indicate more starspot coverage",
    "max_activity_index_g_error": "Uncertainty on the maximum G-band activity index",
    "bp_rp_unspotted": "Unspotted BP-RP color index (bp_unspotted - rp_unspotted); traces stellar temperature — bluer (smaller) values indicate hotter stars",
}

# -- Dataset description ----------------------------------------------------
DESCRIPTION = """\
The Gaia DR3 rotation modulation catalog contains stellar rotation periods derived from \
photometric variability detected by the ESA Gaia mission. Each entry represents a star \
whose periodic brightness variations — caused by dark starspots rotating with the star — \
were detected and modeled by Gaia's variability processing pipeline. The key output is \
`best_rotation_period`: the stellar rotation period in days.

Stellar rotation is one of the most powerful astrophysical diagnostics available. Stars \
spin down as they age through a process called magnetic braking, where stellar winds \
carry away angular momentum. This age-rotation relation (gyrochronology) allows stellar \
ages to be estimated from the rotation period and color alone, complementing classical \
isochrone fitting. Young, active stars rotate rapidly (periods of 1–10 days), while \
middle-aged stars like the Sun rotate slowly (~25 days), and old stars can have periods \
exceeding 50 days.

The `max_activity_index_g` column quantifies the amplitude of brightness modulation due \
to starspots. High activity indices indicate strong magnetic activity, which is directly \
correlated with X-ray and UV emission, flare rates, and thus the radiation environment \
experienced by any orbiting planets. Fast-rotating, active stars are therefore important \
targets for planetary habitability studies.

With approximately 82,000 rotation periods available through the Gaia archive TAP service, \
this is one of the largest all-sky stellar rotation catalogs assembled from a single \
space mission — covering both hemispheres with uniform photometric quality. The unspotted \
magnitudes (g_unspotted, bp_unspotted, rp_unspotted) enable spot-corrected photometry, \
and the per-segment analysis quantifies how rotation periods evolve over the ~34-month \
Gaia observation baseline.
"""


def fetch_gaia_rotation():
    """Fetch rotation modulation catalog from Gaia archive (single query, ~474k rows)."""
    query = (
        "SELECT * FROM gaiadr3.vari_rotation_modulation "
        "ORDER BY source_id"
    )
    print("  Fetching Gaia DR3 vari_rotation_modulation (single query)...")
    resp = requests.post(GAIA_TAP, data={
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv",
        "QUERY": query, "MAXREC": PAGE_SIZE,
    }, timeout=600)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    print(f"    got {len(df):,} rows")
    return df


def main():
    print("Fetching Gaia DR3 Rotation Modulation from ESA Gaia Archive...")
    df = fetch_gaia_rotation()
    print(f"  {len(df):,} raw rows, columns: {list(df.columns)}")

    # Drop internal columns
    for col in ["solution_id", "recno"]:
        if col in df.columns:
            df = df.drop(columns=[col])

    # Type conversions — object columns to numeric where possible
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Integer columns
    for col in ["num_segments", "num_outliers"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int32")

    # Derived: unspotted color index
    if "bp_unspotted" in df.columns and "rp_unspotted" in df.columns:
        df["bp_rp_unspotted"] = df["bp_unspotted"] - df["rp_unspotted"]

    # Sort by source_id
    if "source_id" in df.columns:
        df = df.sort_values("source_id").reset_index(drop=True)

    # Print column list before null filtering
    print(f"  Columns before null filter: {list(df.columns)}")

    # Quick stats (before null filtering to use all available data)
    n_total = len(df)
    period_median = df["best_rotation_period"].median() if "best_rotation_period" in df.columns else float("nan")
    fast_rotators_frac = (
        (df["best_rotation_period"] < 10).sum() / n_total
        if "best_rotation_period" in df.columns else float("nan")
    )
    activity_median = df["max_activity_index_g"].median() if "max_activity_index_g" in df.columns else float("nan")

    quick_stats = f"""\
- **{n_total:,}** stars with measured rotation periods
- Median rotation period: {period_median:.2f} days
- Fraction with period < 10 days (fast rotators): {fast_rotators_frac:.1%}
- Median G-band activity index: {activity_median:.4f}"""

    usage = """\
```python
from datasets import load_dataset
import matplotlib.pyplot as plt
import numpy as np

ds = load_dataset("juliensimon/gaia-dr3-rotation-modulation", split="train")
df = ds.to_pandas()

# Rotation period histogram (log scale)
fig, ax = plt.subplots(figsize=(10, 6))
ax.hist(df["best_rotation_period"].dropna(), bins=200, log=True, color="steelblue", alpha=0.8)
ax.set_xscale("log")
ax.set_xlabel("Rotation Period (days)")
ax.set_ylabel("Number of Stars")
ax.set_title("Gaia DR3 Stellar Rotation Period Distribution")
plt.tight_layout()
plt.show()

# Activity index vs rotation period (gyrochronology diagram)
mask = df["best_rotation_period"].notna() & df["max_activity_index_g"].notna()
plt.figure(figsize=(10, 6))
plt.hexbin(
    np.log10(df.loc[mask, "best_rotation_period"]),
    df.loc[mask, "max_activity_index_g"],
    gridsize=100, mincnt=1, cmap="hot"
)
plt.colorbar(label="Count")
plt.xlabel("log10(Rotation Period [days])")
plt.ylabel("Max G Activity Index")
plt.title("Stellar Activity vs Rotation Period")
plt.show()

# Fast rotators (young stars)
fast = df[df["best_rotation_period"] < 5]
print(f"Stars with P < 5 days: {len(fast):,}")
print(f"Median activity index (fast rotators): {fast['max_activity_index_g'].median():.4f}")
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Gaia DR3 Stellar Rotation Periods",
        description=DESCRIPTION,
        tags=["space", "gaia", "stellar-rotation", "variable-stars", "stellar-activity",
              "esa", "astronomy", "open-data", "tabular-data", "parquet"],
        source_url="https://gea.esac.esa.int/archive/",
        license="other",
        license_name="cc-by-nc-3.0-igo",
        license_link="https://creativecommons.org/licenses/by-nc/3.0/igo/",
        task_categories=["tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e002172/GSFC_20171208_Archive_e002172~small.jpg",
            "alt": "Stellar activity and sunspots observed by NASA",
            "credit": "NASA/GSFC",
        },
        related_datasets=[
            "juliensimon/gaia-dr3-young-stellar-objects",
            "juliensimon/gaia-dr3-eclipsing-binaries",
            "juliensimon/aavso-vsx-variable-stars",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "best_rotation_period", "best_rotation_period_error",
                "g_unspotted", "g_unspotted_error",
                "bp_unspotted", "bp_unspotted_error",
                "rp_unspotted", "rp_unspotted_error",
                "max_activity_index_g", "max_activity_index_g_error",
                "bp_rp_unspotted",
            ],
            drop_mostly_null_threshold=0.95,
        )

        # Drop any remaining segments_* columns (array-like strings that break parquet)
        segments_cols = [c for c in df.columns if c.startswith("segments_")]
        if segments_cols:
            print(f"  Dropping remaining segments_* columns: {segments_cols}")
            df = df.drop(columns=segments_cols)

        # Keep only described columns (filter to known schema)
        df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

        print(f"  Final columns ({len(df.columns)}): {list(df.columns)}")

        p.publish(
            df,
            filename="gaia_dr3_rotation_modulation.parquet",
            min_rows=70_000,
            expected_columns=["source_id", "best_rotation_period", "max_activity_index_g"],
            critical_columns=["source_id", "best_rotation_period"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Add Gaia DR3 rotation modulation: {n_total:,} sources",
        )
    print("Done.")


if __name__ == "__main__":
    main()
