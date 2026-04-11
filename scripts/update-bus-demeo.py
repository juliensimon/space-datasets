#!/usr/bin/env python3
"""Fetch Bus-DeMeo Asteroid Taxonomy from PDS Small Bodies Node and upload to HF.

Source: DeMeo et al. (2009, Icarus 202, 160) — Bus-DeMeo asteroid taxonomy
based on spectroscopic observations of 371 asteroids covering 0.45-2.45 um.
PDS4 bundle: urn:nasa:pds:ast.bus-demeo.taxonomy::1.0
"""

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

HF_REPO = "juliensimon/bus-demeo-asteroid-taxonomy"

PDS_BASE = (
    "https://sbnarchive.psi.edu/pds4/non_mission/ast.bus-demeo.taxonomy/data"
)
TAX_URL = f"{PDS_BASE}/demeotax.tab"
PC_URL = f"{PDS_BASE}/pcscores.tab"

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "asteroid_number": "IAU catalog number (positive integer); null for unnumbered objects matched by provisional designation only",
    "asteroid_name": "IAU proper name (e.g., 'Ceres', 'Vesta'); null for unnamed asteroids",
    "provisional_designation": "MPC provisional designation (e.g., '2002 AT4'); null if only a catalog number is available",
    "taxonomic_class": "Bus-DeMeo spectral class (e.g., S, C, Sq, Xk, V); 'w' suffix = spectral slope >0.25 um^-1; ':' = uncertain assignment; ~24 classes total",
    "taxonomic_complex": "Broad complex derived from class: S (silicate), C (carbonaceous), X (featureless/metallic), or end-member letter (A/B/D/K/L/O/Q/R/T/V); null if class unrecognised",
    "obs_date": "UTC date of the spectroscopic observation used for classification; null for a small fraction of entries",
    "ref_code": "One-letter literature reference code (a-i) mapping to the source publication; null if not recorded",
    "spectral_slope": "Linear spectral slope fitted to the normalised reflectance spectrum (um^-1); positive = red, negative = blue; used as input to PCA",
    "pc1": "First principal component score from DeMeo et al. (2009) PCA; captures overall spectral slope and is the primary axis separating S- from C-types; null for asteroids lacking full NIR coverage",
    "pc2": "Second principal component score; mainly encodes depth of the 1-um olivine/pyroxene absorption band; null as above",
    "pc3": "Third principal component score; captures subtler spectral curvature, e.g., the 2-um pyroxene band; null as above",
    "pc4": "Fourth principal component score; encodes fine-structure residuals after PC1-3; null as above",
    "pc5": "Fifth principal component score; represents the smallest variance component; null as above",
}

DESCRIPTION = """\
The **Bus-DeMeo taxonomy** is the current standard classification system for asteroids based \
on their visible and near-infrared reflectance spectra (0.45--2.45 um). This dataset contains \
the reference asteroids used to define and validate the taxonomy, each classified into one of \
~24 taxonomic classes grouped into several broad complexes.

The Bus-DeMeo system (DeMeo et al. 2009) extended the earlier Bus taxonomy into the near-infrared, \
using principal component analysis on reflectance spectra to define 24 taxonomic classes. Each class \
corresponds to distinct surface mineralogy: S-complex asteroids are silicate-rich (olivine/pyroxene), \
C-complex are carbonaceous, X-complex have featureless spectra (metal-rich or enstatite), and \
end-member types (V, A, D, K, etc.) have unique spectral signatures.

Asteroid taxonomy provides the critical link between remote spectroscopic observations and surface \
mineralogy. The S-complex, dominated by olivine and pyroxene silicates, is most common in the inner \
main belt (2.0--2.5 AU) and includes the parent bodies of ordinary chondrite meteorites. The C-complex, \
with its low albedo and relatively featureless spectra, dominates the outer belt (beyond 2.7 AU) and \
is associated with carbonaceous chondrite meteorites rich in hydrated minerals and organic compounds.

The principal component scores (PC1--PC5) encode the full spectral shape in a compact form. PC1 \
captures the overall spectral slope, PC2 the depth of the 1-micron absorption band (diagnostic of \
olivine and pyroxene), and higher components capture subtler features like the 2-micron pyroxene \
band and UV dropoff.
"""


def fetch_fixed_width(url: str, colspecs: list, names: list) -> pd.DataFrame:
    """Download a fixed-width PDS4 .tab file and parse it."""
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    from io import StringIO
    return pd.read_fwf(StringIO(resp.text), colspecs=colspecs, names=names)


def main():
    print("Fetching Bus-DeMeo asteroid taxonomy from PDS...")

    # ── Taxonomy table (demeotax.tab) ─────────────────────────────────
    tax_colspecs = [(0, 7), (8, 25), (26, 36), (37, 40), (41, 51), (52, 55)]
    tax_names = [
        "asteroid_number", "asteroid_name", "provisional_designation",
        "taxonomic_class", "obs_date", "ref_code",
    ]
    df_tax = fetch_fixed_width(TAX_URL, tax_colspecs, tax_names)
    print(f"  {len(df_tax):,} asteroid classifications")

    # ── Principal component scores (pcscores.tab) ─────────────────────
    pc_colspecs = [
        (0, 6), (7, 17), (18, 25), (26, 33), (34, 41),
        (42, 49), (50, 57), (58, 65),
    ]
    pc_names = [
        "asteroid_number", "provisional_designation",
        "spectral_slope", "pc1", "pc2", "pc3", "pc4", "pc5",
    ]
    df_pc = fetch_fixed_width(PC_URL, pc_colspecs, pc_names)
    print(f"  {len(df_pc):,} principal component scores")

    # ── Merge taxonomy + PC scores ───────────────────────────────────
    pc_cols = ["spectral_slope", "pc1", "pc2", "pc3", "pc4", "pc5"]

    for frame in (df_tax, df_pc):
        frame["provisional_designation"] = (
            frame["provisional_designation"].astype(str).str.strip()
        )

    numbered_tax = df_tax[df_tax["asteroid_number"] > 0].copy()
    unnumbered_tax = df_tax[df_tax["asteroid_number"] == 0].copy()

    numbered_pc = df_pc[df_pc["asteroid_number"] > 0][
        ["asteroid_number"] + pc_cols
    ]
    unnumbered_pc = df_pc[df_pc["asteroid_number"] == 0][
        ["provisional_designation"] + pc_cols
    ]

    df_num = numbered_tax.merge(numbered_pc, on="asteroid_number", how="left")
    df_unnum = unnumbered_tax.merge(
        unnumbered_pc, on="provisional_designation", how="left"
    )
    df = pd.concat([df_num, df_unnum], ignore_index=True)

    # ── Clean string columns ──────────────────────────────────────────
    for col in ["asteroid_name", "provisional_designation", "taxonomic_class",
                "ref_code"]:
        df[col] = (
            df[col].astype(str).str.strip()
            .replace({"": pd.NA, "-": pd.NA, "None": pd.NA, "nan": pd.NA})
        )

    # ── Parse observation date ────────────────────────────────────────
    df["obs_date"] = pd.to_datetime(df["obs_date"], errors="coerce")

    # ── Convert numerics ──────────────────────────────────────────────
    for col in ["spectral_slope", "pc1", "pc2", "pc3", "pc4", "pc5"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["asteroid_number"] = pd.to_numeric(
        df["asteroid_number"], errors="coerce"
    ).astype("Int64")

    # ── Derive broad taxonomic complex (S/C/X/end-member) ─────────────
    def get_complex(cls):
        if pd.isna(cls):
            return pd.NA
        c = str(cls).rstrip("w").rstrip(":")
        if c in ("S", "Sa", "Sq", "Sr", "Sv", "Sk", "Sl"):
            return "S"
        if c in ("C", "Cb", "Cg", "Cgh", "Ch"):
            return "C"
        if c in ("X", "Xc", "Xe", "Xk", "Xn"):
            return "X"
        if c in ("A", "B", "D", "K", "L", "O", "Q", "R", "T", "V"):
            return c
        return pd.NA

    df["taxonomic_complex"] = df["taxonomic_class"].apply(get_complex)

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    df = df.sort_values("asteroid_number").reset_index(drop=True)

    # ── Stats for README ──────────────────────────────────────────────
    n_total = len(df)
    n_classes = df["taxonomic_class"].nunique()
    n_complexes = df["taxonomic_complex"].nunique()
    top_classes = (
        df["taxonomic_class"]
        .value_counts()
        .head(5)
        .to_dict()
    )
    top_str = ", ".join(f"{k} ({v})" for k, v in top_classes.items())
    n_named = int(df["asteroid_name"].notna().sum())
    n_with_pc = int(df["pc1"].notna().sum())

    quick_stats = f"""\
- **{n_total:,}** asteroids in the reference taxonomy set
- **{n_classes}** distinct taxonomic classes, **{n_complexes}** broad complexes
- Most common classes: {top_str}
- **{n_named}** with IAU names, **{n_with_pc}** with principal component scores"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/bus-demeo-asteroid-taxonomy", split="train")
df = ds.to_pandas()

# Class distribution
print(df["taxonomic_class"].value_counts())

# Complex distribution
print(df["taxonomic_complex"].value_counts())

# PC1 vs PC2 scatter plot colored by complex
import matplotlib.pyplot as plt
for cpx in ["S", "C", "X", "V"]:
    sub = df[df["taxonomic_complex"] == cpx].dropna(subset=["pc1", "pc2"])
    plt.scatter(sub["pc1"], sub["pc2"], label=cpx, alpha=0.6, s=15)
plt.xlabel("PC1")
plt.ylabel("PC2")
plt.legend()
plt.title("Bus-DeMeo Taxonomy: PC1 vs PC2 by Complex")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Bus-DeMeo Asteroid Taxonomy",
        description=DESCRIPTION,
        tags=["space", "asteroids", "taxonomy", "spectroscopy", "composition",
              "orbital-mechanics", "open-data", "tabular-data", "parquet"],
        source_url="https://sbn.psi.edu/pds/resource/busdemeotax.html",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA17666/PIA17666~small.jpg",
            "alt": "Rosetta spacecraft approaching Comet 67P/Churyumov-Gerasimenko",
            "credit": "NASA/ESA",
        },
        related_datasets=[
            "juliensimon/neo-close-approaches",
            "juliensimon/jpl-small-body-database",
            "juliensimon/asterank-asteroid-mining",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=["spectral_slope", "pc1", "pc2", "pc3", "pc4", "pc5"],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="bus_demeo_asteroid_taxonomy.parquet",
            min_rows=300,
            expected_columns=[
                "asteroid_number", "taxonomic_class", "spectral_slope",
                "pc1", "pc2",
            ],
            critical_columns=["asteroid_number", "taxonomic_class"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Bus-DeMeo asteroid taxonomy: {n_total:,} asteroids",
        )
    print("Done.")


if __name__ == "__main__":
    main()
