#!/usr/bin/env python3
"""Fetch Galaxy Zoo 2 morphological classifications and upload to HF."""

import tempfile

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

SOURCE_URL = "https://zooniverse-data.s3.amazonaws.com/galaxy-zoo-2/zoo2MainSpecz.csv.gz"
HF_REPO = "juliensimon/galaxy-zoo-2-morphology"

# ── Column descriptions for README schema table ─────────────────────
# Key columns — the vote/fraction/debiased/flag columns are described
# generically after the table via the suffix explanation.
COLUMN_DESCRIPTIONS = {
    "specobjid": "SDSS spectroscopic object ID (unique 64-bit integer identifying the specific fiber/plate/MJD observation)",
    "dr8objid": "SDSS DR8 photometric object ID (18-digit integer from the SDSS imaging pipeline; primary cross-match key for photometric catalogs)",
    "dr7objid": "SDSS DR7 photometric object ID; use dr8objid for cross-matching with DR8+ catalogs",
    "ra": "ICRS J2000.0 right ascension of the galaxy center in degrees (0-360)",
    "dec": "ICRS J2000.0 declination of the galaxy center in degrees (-90 to +90)",
    "rastring": "Right ascension in sexagesimal format 'HH:MM:SS.ss' for display purposes",
    "decstring": "Declination in sexagesimal format '+/-DD:MM:SS.s' for display purposes",
    "sample": "GZ2 subsample membership; values include 'original' (main spectroscopic sample) and subsets used for debiasing",
    "gz2class": "Summary morphological class string from the GZ2 decision tree (e.g. 'Sa', 'SBb', 'E', 'Merger'); represents the plurality classification",
    "total_classifications": "Number of distinct classification tasks completed for this galaxy; higher values mean more reliable vote fractions",
    "total_votes": "Total individual votes cast across all tasks for this galaxy; typically 10-70 votes for well-classified objects",
    "dominant_morphology": "Derived: label with the highest t01 debiased probability; one of 'smooth', 'features_or_disk', or 'star_or_artifact'",
    "is_barred": "Derived: True if t03 bar debiased probability > 0.5; applies only to disk galaxies",
    "is_spiral": "Derived: True if t04 spiral debiased probability > 0.5; indicates visible spiral arms after debiasing for redshift effects",
    "is_edge_on": "Derived: True if t02 edge-on debiased probability > 0.5; edge-on disks appear as a thin line with no visible spiral structure",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Citizen-science galaxy morphology classifications from Galaxy Zoo 2, the largest \
visual morphological classification project in astronomy. Each galaxy was classified \
by multiple volunteers answering a decision tree of questions about shape, structure, \
and features.

Galaxy Zoo 2 asked hundreds of thousands of volunteers to classify galaxy images from \
the Sloan Digital Sky Survey (SDSS). This dataset contains the spectroscopic-redshift \
sample (Table 5 from Willett et al. 2013) with vote counts, vote fractions, weighted \
fractions, debiased probabilities, and classification flags for 11 morphological tasks \
spanning 37 possible answers.

The decision tree covers: smooth vs. featured, edge-on disk, bar presence, spiral \
structure, bulge prominence, oddities (ring, lens, disturbed, irregular, merger, dust \
lane), roundedness, bulge shape, and spiral arm properties (tightness, count).

Galaxy morphology is one of the oldest and most fundamental classification problems \
in astronomy, dating back to Edwin Hubble's tuning-fork diagram in 1926. A galaxy's \
visual appearance encodes crucial information about its formation history, dynamical \
state, and stellar populations. Elliptical galaxies are generally old, red, and \
gas-poor systems that formed through major mergers, while spiral galaxies retain \
organized rotation, ongoing star formation, and complex substructure.

Galaxy Zoo 2 represents a landmark in citizen-science astronomy, demonstrating that \
the collective visual pattern recognition of hundreds of thousands of volunteers can \
produce morphological classifications of comparable quality to expert astronomers, \
but at vastly greater scale. The debiased vote fractions correct for the tendency of \
distant, smaller galaxies to appear smoother than they truly are. The dataset is also \
widely used as a benchmark for machine-learning approaches to galaxy classification.
"""


def main():
    print("Fetching Galaxy Zoo 2 morphological classifications...")
    resp = requests.get(SOURCE_URL, timeout=120)
    resp.raise_for_status()

    # Write gzipped CSV to temp file, then read with pandas
    with tempfile.NamedTemporaryFile(suffix=".csv.gz") as tmp_csv:
        tmp_csv.write(resp.content)
        tmp_csv.flush()
        df = pd.read_csv(tmp_csv.name, compression="gzip")

    print(f"  {len(df):,} galaxies, {len(df.columns)} columns")

    # ── Type coercion ─────────────────────────────────────────────────
    for col in ["specobjid", "dr8objid", "dr7objid"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    df["ra"] = pd.to_numeric(df["ra"], errors="coerce")
    df["dec"] = pd.to_numeric(df["dec"], errors="coerce")

    # All vote count, weight, fraction, debiased, flag columns are numeric
    vote_cols = [c for c in df.columns if c.startswith("t0") or c.startswith("t1")]
    for col in vote_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["total_classifications"] = pd.to_numeric(df["total_classifications"], errors="coerce").astype("Int64")
    df["total_votes"] = pd.to_numeric(df["total_votes"], errors="coerce").astype("Int64")

    # ── Derived columns ───────────────────────────────────────────────
    smooth_col = "t01_smooth_or_features_a01_smooth_debiased"
    features_col = "t01_smooth_or_features_a02_features_or_disk_debiased"
    artifact_col = "t01_smooth_or_features_a03_star_or_artifact_debiased"

    def classify_morphology(row):
        smooth = row.get(smooth_col)
        features = row.get(features_col)
        artifact = row.get(artifact_col)
        vals = {"smooth": smooth, "features_or_disk": features, "star_or_artifact": artifact}
        valid = {k: v for k, v in vals.items() if pd.notna(v)}
        if not valid:
            return None
        return max(valid, key=valid.get)

    df["dominant_morphology"] = df.apply(classify_morphology, axis=1)

    bar_col = "t03_bar_a06_bar_debiased"
    if bar_col in df.columns:
        df["is_barred"] = df[bar_col] > 0.5

    spiral_col = "t04_spiral_a08_spiral_debiased"
    if spiral_col in df.columns:
        df["is_spiral"] = df[spiral_col] > 0.5

    edgeon_col = "t02_edgeon_a04_yes_debiased"
    if edgeon_col in df.columns:
        df["is_edge_on"] = df[edgeon_col] > 0.5

    # ── Keep only columns that have descriptions ─────────────────────
    # For Galaxy Zoo, the vote columns (t01-t11) are described generically
    # via the suffix explanation, so we keep them all plus described cols
    described = set(COLUMN_DESCRIPTIONS.keys())
    vote_pattern_cols = [c for c in df.columns if c.startswith("t0") or c.startswith("t1")]
    keep = [c for c in df.columns if c in described or c in vote_pattern_cols]
    df = df[keep]

    # ── Stats for README ──────────────────────────────────────────────
    n_total = len(df)
    n_smooth = int((df["dominant_morphology"] == "smooth").sum())
    n_features = int((df["dominant_morphology"] == "features_or_disk").sum())
    n_barred = int(df["is_barred"].sum()) if "is_barred" in df.columns else 0
    n_spiral = int(df["is_spiral"].sum()) if "is_spiral" in df.columns else 0
    n_edgeon = int(df["is_edge_on"].sum()) if "is_edge_on" in df.columns else 0
    avg_votes = df["total_votes"].mean()

    quick_stats = f"""\
- **{n_total:,}** galaxies classified
- **{n_smooth:,}** classified as smooth/elliptical
- **{n_features:,}** classified as featured/disk
- **{n_spiral:,}** with spiral structure (debiased probability > 0.5)
- **{n_barred:,}** barred galaxies (debiased probability > 0.5)
- **{n_edgeon:,}** edge-on galaxies (debiased probability > 0.5)
- **{avg_votes:.1f}** average votes per galaxy"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/galaxy-zoo-2-morphology", split="train")
df = ds.to_pandas()

# Elliptical galaxies (smooth, debiased probability > 0.8)
ellipticals = df[df["t01_smooth_or_features_a01_smooth_debiased"] > 0.8]

# Barred spiral galaxies
barred_spirals = df[df["is_barred"] & df["is_spiral"]]

# Edge-on disks
edge_on = df[df["is_edge_on"]]

# Distribution of morphological classes
print(df["gz2class"].value_counts().head(10))

# Merger candidates (odd feature = merger, debiased > 0.5)
import matplotlib.pyplot as plt
morph = df["dominant_morphology"].value_counts()
morph.plot.bar()
plt.ylabel("Count")
plt.title("Galaxy Zoo 2 Morphology Distribution")
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Galaxy Zoo 2 Morphological Classifications",
        description=DESCRIPTION,
        tags=["space", "galaxies", "morphology", "citizen-science", "galaxy-zoo",
              "astronomy", "open-data", "sdss", "tabular-data", "parquet"],
        source_url="https://data.galaxyzoo.org/",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA12110/PIA12110~small.jpg",
            "alt": "Hubble Deep Field revealing myriad galaxies across cosmic time",
            "credit": "NASA/ESA/STScI",
        },
        related_datasets=[
            "juliensimon/ngc-ic-catalog",
            "juliensimon/nasa-exoplanets",
            "juliensimon/messier-catalog",
        ],
    ) as p:
        p.publish(
            df,
            filename="galaxy_zoo_2_morphology.parquet",
            min_rows=200_000,
            expected_columns=[
                "specobjid", "dr8objid", "ra", "dec", "gz2class",
                "total_classifications", "total_votes",
                "t01_smooth_or_features_a01_smooth_debiased",
                "t01_smooth_or_features_a02_features_or_disk_debiased",
                "t03_bar_a06_bar_debiased",
                "t04_spiral_a08_spiral_debiased",
                "dominant_morphology",
            ],
            critical_columns=["ra", "dec", "specobjid", "total_votes"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Upload Galaxy Zoo 2 morphology: {n_total:,} galaxies",
        )
    print("Done.")


if __name__ == "__main__":
    main()
