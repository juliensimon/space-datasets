#!/usr/bin/env python3
"""Fetch Gaia DR3 Binary Masses catalog from ESA Gaia Archive and upload to HF."""

import io

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

GAIA_TAP = "https://gea.esac.esa.int/tap-server/tap/sync"
HF_REPO = "juliensimon/gaia-dr3-binary-masses"

# -- Column mapping --------------------------------------------------------
RENAME = {
    "source_id": "source_id",
    "m1": "m1",
    "m1_lower": "m1_lower",
    "m1_upper": "m1_upper",
    "m2": "m2",
    "m2_lower": "m2_lower",
    "m2_upper": "m2_upper",
    "fluxratio": "fluxratio",
    "fluxratio_lower": "fluxratio_lower",
    "fluxratio_upper": "fluxratio_upper",
    "combination_method": "combination_method",
    "m1_ref": "m1_ref",
    "flag": "flag",
}

# -- Column descriptions for README schema table ---------------------------
COLUMN_DESCRIPTIONS = {
    "source_id": "Gaia DR3 source identifier of the primary star; use for cross-matching with other Gaia tables",
    "m1": "Primary star mass in solar masses (M☉), derived from orbital solution",
    "m1_lower": "Lower 1-sigma uncertainty on m1 (M☉)",
    "m1_upper": "Upper 1-sigma uncertainty on m1 (M☉)",
    "m2": "Secondary component mass in solar masses (M☉); may be NaN if only primary mass is determined",
    "m2_lower": "Lower 1-sigma uncertainty on m2 (M☉)",
    "m2_upper": "Upper 1-sigma uncertainty on m2 (M☉)",
    "fluxratio": "Flux ratio of secondary to primary (F2/F1) in Gaia G-band",
    "fluxratio_lower": "Lower uncertainty on flux ratio",
    "fluxratio_upper": "Upper uncertainty on flux ratio",
    "combination_method": "Method used to derive masses: combination of astrometric, spectroscopic, and/or photometric constraints",
    "m1_ref": "Reference for the primary mass estimate (short code)",
    "flag": "Quality/reliability flag for the mass determination",
    "mass_ratio": "Mass ratio q = m2/m1; computed where both masses are available and m1 > 0",
    "m1_uncertainty": "Average 1-sigma uncertainty on m1 = (m1_upper + m1_lower) / 2.0 (M☉)",
}

# -- Dataset description ----------------------------------------------------
DESCRIPTION = """\
The Gaia DR3 binary masses catalog provides physical masses for binary star systems \
derived by the ESA Gaia mission. Masses are determined by combining astrometric \
non-single-star (NSS) solutions with spectroscopic radial velocities and photometric \
constraints, applying Kepler's third law to the orbital solutions.

These are among the most precisely measured stellar masses available from an all-sky \
survey, covering ~195,000 systems with primary masses ranging from ~0.1 to more than \
10 solar masses. The combination_method column indicates which observational constraints \
(astrometry, spectroscopy, photometry) were used for each system.

The dataset is scientifically crucial for calibrating stellar evolution models, \
mass-luminosity relations, and testing stellar structure theory. Direct mass \
measurements from binary systems are the foundation of our understanding of how \
stars form, evolve, and die. Unlike masses estimated from stellar models or \
spectral fitting, these Gaia masses are derived geometrically from orbital dynamics, \
providing model-independent ground truth across a wide range of stellar types.

The flux ratio (F2/F1 in G-band) constrains the luminosity of the secondary star, \
enabling estimates of secondary radius and temperature when combined with the primary's \
known properties. Systems with measured m2 allow direct computation of the mass ratio \
q = m2/m1, a fundamental parameter in binary evolution theory that controls mass transfer \
rates, tidal circularization timescales, and ultimate system fate.
"""


def fetch_gaia_binary_masses():
    """Fetch binary masses from Gaia archive in a single query."""
    query = "SELECT * FROM gaiadr3.binary_masses ORDER BY source_id"
    print("  Fetching gaiadr3.binary_masses...")
    resp = requests.post(
        GAIA_TAP,
        data={
            "REQUEST": "doQuery",
            "LANG": "ADQL",
            "FORMAT": "csv",
            "QUERY": query,
            "MAXREC": 500_000,
        },
        timeout=600,
    )
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    print(f"    got {len(df):,} rows")
    return df


def main():
    print("Fetching Gaia DR3 Binary Masses from ESA Gaia Archive...")
    df = fetch_gaia_binary_masses()
    print(f"  {len(df):,} raw rows")

    # Rename columns (already snake_case from Gaia archive)
    df = df.rename(columns=RENAME)

    # Type conversions -- object columns to numeric
    for col in df.select_dtypes(include=["object"]).columns:
        if col not in ("combination_method", "m1_ref", "flag"):
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Numeric columns
    for col in ["m1", "m1_lower", "m1_upper", "m2", "m2_lower", "m2_upper",
                "fluxratio", "fluxratio_lower", "fluxratio_upper"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Derived: mass ratio q = m2 / m1
    if "m2" in df.columns and "m1" in df.columns:
        df["mass_ratio"] = df["m2"] / df["m1"].replace(0, float("nan"))

    # Derived: average m1 uncertainty
    if "m1_upper" in df.columns and "m1_lower" in df.columns:
        df["m1_uncertainty"] = (df["m1_upper"] + df["m1_lower"]) / 2.0

    # Drop internal/VizieR columns not in COLUMN_DESCRIPTIONS
    for col in ["recno"]:
        if col in df.columns:
            df = df.drop(columns=[col])

    # Keep only described columns (in defined order)
    keep = [c for c in COLUMN_DESCRIPTIONS if c in df.columns]
    df = df[keep]

    # Sort by source_id
    if "source_id" in df.columns:
        df = df.sort_values("source_id").reset_index(drop=True)

    # Stats
    n_total = len(df)
    m1_median = df["m1"].median() if "m1" in df.columns else float("nan")
    m2_valid = df["m2"].dropna() if "m2" in df.columns else pd.Series(dtype=float)
    m2_median = m2_valid.median() if len(m2_valid) > 0 else float("nan")
    n_with_m2 = len(m2_valid)
    mr_valid = df["mass_ratio"].dropna() if "mass_ratio" in df.columns else pd.Series(dtype=float)
    mr_median = mr_valid.median() if len(mr_valid) > 0 else float("nan")

    quick_stats = f"""\
- **{n_total:,}** binary star systems
- Median primary mass (m1): {m1_median:.3f} M☉
- Median secondary mass (m2): {m2_median:.3f} M☉ (where available)
- Systems with measured m2: {n_with_m2:,} ({100*n_with_m2/n_total:.1f}%)
- Median mass ratio (m2/m1): {mr_median:.3f}"""

    usage = """\
```python
from datasets import load_dataset
import matplotlib.pyplot as plt

ds = load_dataset("juliensimon/gaia-dr3-binary-masses", split="train")
df = ds.to_pandas()

# Primary mass distribution
df["m1"].clip(upper=5).hist(bins=100, log=True)
plt.xlabel("Primary mass m1 (M☉)")
plt.ylabel("Count")
plt.title("Gaia DR3 Binary Star Primary Mass Distribution")
plt.show()

# m1 vs m2 scatter (systems with both measured)
has_m2 = df.dropna(subset=["m1", "m2"])
plt.hexbin(has_m2["m1"], has_m2["m2"], gridsize=80, mincnt=1, cmap="viridis")
plt.colorbar(label="Count")
plt.xlabel("Primary mass m1 (M☉)")
plt.ylabel("Secondary mass m2 (M☉)")
plt.title("Gaia DR3 Binary Mass Pairs")
plt.show()

# Mass ratio distribution
df["mass_ratio"].clip(0, 2).hist(bins=100)
plt.xlabel("Mass ratio q = m2/m1")
plt.ylabel("Count")
plt.title("Binary Mass Ratio Distribution")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Gaia DR3 Binary Masses",
        description=DESCRIPTION,
        tags=["space", "gaia", "binary-stars", "stellar-masses", "esa",
              "astronomy", "open-data", "tabular-data", "parquet"],
        source_url="https://gea.esac.esa.int/archive/",
        license="other",
        license_name="cc-by-nc-3.0-igo",
        license_link="https://creativecommons.org/licenses/by-nc/3.0/igo/",
        task_categories=["tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA03606/PIA03606~small.jpg",
            "alt": "Stellar field showing binary star systems",
            "credit": "NASA/JPL-Caltech",
        },
        related_datasets=[
            "juliensimon/gaia-dr3-spectroscopic-binaries",
            "juliensimon/gaia-dr3-eclipsing-binaries",
            "juliensimon/wds",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "m1", "m1_lower", "m1_upper",
                "m2", "m2_lower", "m2_upper",
                "fluxratio", "fluxratio_lower", "fluxratio_upper",
                "mass_ratio", "m1_uncertainty",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="gaia_dr3_binary_masses.parquet",
            min_rows=150_000,
            expected_columns=["source_id", "m1", "combination_method"],
            critical_columns=["source_id", "m1"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Gaia DR3 binary masses: {n_total:,} sources",
        )
    print("Done.")


if __name__ == "__main__":
    main()
