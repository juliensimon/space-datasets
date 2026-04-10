#!/usr/bin/env python3
"""Fetch Bus-DeMeo Asteroid Taxonomy from PDS Small Bodies Node and upload to HF.

Source: DeMeo et al. (2009, Icarus 202, 160) — Bus-DeMeo asteroid taxonomy
based on spectroscopic observations of 371 asteroids covering 0.45-2.45 μm.
PDS4 bundle: urn:nasa:pds:ast.bus-demeo.taxonomy::1.0
"""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

from dataset_images import banner_markdown, download_banner
from validate import check_dataset


HF_REPO = "juliensimon/bus-demeo-asteroid-taxonomy"

PDS_BASE = (
    "https://sbnarchive.psi.edu/pds4/non_mission/ast.bus-demeo.taxonomy/data"
)
TAX_URL = f"{PDS_BASE}/demeotax.tab"
PC_URL = f"{PDS_BASE}/pcscores.tab"


def fetch_fixed_width(url: str, colspecs: list, names: list) -> pd.DataFrame:
    """Download a fixed-width PDS4 .tab file and parse it."""
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    from io import StringIO
    return pd.read_fwf(StringIO(resp.text), colspecs=colspecs, names=names)


def main():
    print("Fetching Bus-DeMeo asteroid taxonomy from PDS...")

    # ── Taxonomy table (demeotax.tab) ─────────────────────────────────
    # Fixed-width: 7 + 1 + 17 + 1 + 10 + 1 + 3 + 1 + 10 + 1 + 3
    # Columns:  AST_NUMBER(1-7) AST_NAME(9-25) PROV_DESIG(27-36)
    #           BUS_DEMEO_CLASS(38-40) OBS_DATE(42-51) REF_CODE(53-55)
    tax_colspecs = [(0, 7), (8, 25), (26, 36), (37, 40), (41, 51), (52, 55)]
    tax_names = [
        "asteroid_number", "asteroid_name", "provisional_designation",
        "taxonomic_class", "obs_date", "ref_code",
    ]
    df_tax = fetch_fixed_width(TAX_URL, tax_colspecs, tax_names)
    print(f"  {len(df_tax):,} asteroid classifications")

    # ── Principal component scores (pcscores.tab) ─────────────────────
    # Fixed-width: AST_NUMBER(1-6) PROV_DESIG(8-17) SLOPE(19-25)
    #              PC1(27-33) PC2(35-41) PC3(43-49) PC4(51-57) PC5(59-65)
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
    # Some asteroids are unnumbered (number=0) and must be matched by
    # provisional designation instead.  Split into numbered/unnumbered,
    # merge each group with the appropriate key, then recombine.
    pc_cols = ["spectral_slope", "pc1", "pc2", "pc3", "pc4", "pc5"]

    # Clean provisional designations for matching
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
        c = str(cls).rstrip("w").rstrip(":")  # remove slope flag / uncertain
        # S-complex
        if c in ("S", "Sa", "Sq", "Sr", "Sv", "Sk", "Sl"):
            return "S"
        # C-complex
        if c in ("C", "Cb", "Cg", "Cgh", "Ch"):
            return "C"
        # X-complex
        if c in ("X", "Xc", "Xe", "Xk", "Xn"):
            return "X"
        # End-member types
        if c in ("A", "B", "D", "K", "L", "O", "Q", "R", "T", "V"):
            return c
        return pd.NA

    df["taxonomic_complex"] = df["taxonomic_class"].apply(get_complex)

    # ── Sort by asteroid number ───────────────────────────────────────
    df = df.sort_values("asteroid_number").reset_index(drop=True)

    # ── Validate ──────────────────────────────────────────────────────
    check_dataset(
        df, "bus-demeo", min_rows=300,
        expected_columns=[
            "asteroid_number", "taxonomic_class", "spectral_slope",
            "pc1", "pc2",
        ],
        critical_columns=["asteroid_number", "taxonomic_class"],
    )

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

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "bus_demeo_asteroid_taxonomy.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.2f} MB parquet")

        banner_file = download_banner("bus-demeo", tmp)
        banner_md = banner_markdown("bus-demeo", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Bus-DeMeo Asteroid Taxonomy"
language:
  - en
description: "Reference set of {n_total} asteroids with Bus-DeMeo spectroscopic taxonomic classifications, principal component scores, and spectral slopes. The standard taxonomy for asteroid composition studies, covering 24 classes based on visible and near-infrared reflectance spectra (0.45-2.45 um)."
task_categories:
  - tabular-classification
tags:
  - space
  - asteroids
  - taxonomy
  - spectroscopy
  - composition
  - orbital-mechanics
  - open-data
  - tabular-data
  - parquet
size_categories:
  - n<1K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/bus_demeo_asteroid_taxonomy.parquet
    default: true
---

# Bus-DeMeo Asteroid Taxonomy
{banner_md}
*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

The **Bus-DeMeo taxonomy** is the current standard classification system for asteroids based on
their visible and near-infrared reflectance spectra (0.45--2.45 um). This dataset contains the
**{n_total:,}** reference asteroids used to define and validate the taxonomy, each classified
into one of **{n_classes}** taxonomic classes grouped into **{n_complexes}** complexes.

## Dataset description

The Bus-DeMeo system (DeMeo et al. 2009) extended the earlier Bus taxonomy into the near-infrared,
using principal component analysis on reflectance spectra to define 24 taxonomic classes. Each class
corresponds to distinct surface mineralogy: S-complex asteroids are silicate-rich (olivine/pyroxene),
C-complex are carbonaceous, X-complex have featureless spectra (metal-rich or enstatite), and
end-member types (V, A, D, K, etc.) have unique spectral signatures.

This dataset is the reference classification set -- the {n_total} asteroids whose spectra were
used to define and validate the taxonomy. It includes the taxonomic class, observation date,
spectral slope, and the five principal component scores from the PCA decomposition.

Asteroid taxonomy provides the critical link between remote spectroscopic observations and surface mineralogy. The S-complex, dominated by olivine and pyroxene silicates, is most common in the inner main belt (2.0--2.5 AU) and includes the parent bodies of ordinary chondrite meteorites. The C-complex, with its low albedo and relatively featureless spectra, dominates the outer belt (beyond 2.7 AU) and is associated with carbonaceous chondrite meteorites rich in hydrated minerals and organic compounds. The X-complex encompasses spectrally degenerate objects whose flat, featureless reflectance can indicate metallic iron-nickel surfaces (M-type), enstatite-rich compositions (E-type), or primitive organic-rich material (P-type), which cannot be distinguished by reflectance alone.

The principal component scores (PC1--PC5) in this dataset encode the full spectral shape in a compact form. PC1 captures the overall spectral slope, PC2 the depth of the 1-micron absorption band (diagnostic of olivine and pyroxene), and higher components capture subtler features like the 2-micron pyroxene band and UV dropoff. This PCA decomposition enables quantitative comparison between asteroids and is widely used in machine learning applications for automated taxonomic classification of newly observed objects.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `asteroid_number` | int | IAU catalog number (positive integer); null for unnumbered objects matched by provisional designation only |
| `asteroid_name` | string | IAU proper name (e.g., "Ceres", "Vesta"); null for unnamed asteroids |
| `provisional_designation` | string | MPC provisional designation (e.g., "2002 AT4"); null if only a catalog number is available |
| `taxonomic_class` | string | Bus-DeMeo spectral class (e.g., S, C, Sq, Xk, V); 'w' suffix = spectral slope >0.25 µm⁻¹; ':' = uncertain assignment; ~24 classes total |
| `taxonomic_complex` | string | Broad complex derived from class: S (silicate), C (carbonaceous), X (featureless/metallic), or end-member letter (A/B/D/K/L/O/Q/R/T/V); null if class unrecognised |
| `obs_date` | date | UTC date of the spectroscopic observation used for classification; null for a small fraction of entries |
| `ref_code` | string | One-letter literature reference code (a–i) mapping to the source publication; null if not recorded |
| `spectral_slope` | float64 | Linear spectral slope fitted to the normalised reflectance spectrum (µm⁻¹); positive = red, negative = blue; used as input to PCA |
| `pc1` | float64 | First principal component score from DeMeo et al. (2009) PCA; captures overall spectral slope and is the primary axis separating S- from C-types; null for asteroids lacking full NIR coverage |
| `pc2` | float64 | Second principal component score; mainly encodes depth of the 1-µm olivine/pyroxene absorption band; null as above |
| `pc3` | float64 | Third principal component score; captures subtler spectral curvature, e.g., the 2-µm pyroxene band; null as above |
| `pc4` | float64 | Fourth principal component score; encodes fine-structure residuals after PC1–3; null as above |
| `pc5` | float64 | Fifth principal component score; represents the smallest variance component; null as above |

## Quick stats

- **{n_total:,}** asteroids in the reference taxonomy set
- **{n_classes}** distinct taxonomic classes, **{n_complexes}** broad complexes
- Most common classes: {top_str}
- **{n_named}** with IAU names, **{n_with_pc}** with principal component scores

## Usage

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
```

## Data source

DeMeo F.E., Binzel R.P., Slivan S.M., Bus S.J. (2009), "An extension of the Bus asteroid
taxonomy into the near-infrared", *Icarus*, 202, 160--180.
Accessed via [PDS Small Bodies Node](https://sbn.psi.edu/pds/resource/busdemeotax.html)
(urn:nasa:pds:ast.bus-demeo.taxonomy::1.0).

## Related datasets

- [neo-close-approaches](https://huggingface.co/datasets/juliensimon/neo-close-approaches) -- Near-Earth Object close approaches
- [asteroid-sbdb](https://huggingface.co/datasets/juliensimon/jpl-small-body-database) -- JPL Small-Body Database
- [meteorite-landings](https://huggingface.co/datasets/juliensimon/meteorite-landings) -- Meteorite Landings

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/bus-demeo-asteroid-taxonomy) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{bus_demeo_asteroid_taxonomy,
  author = {{Simon, Julien}},
  title = {{Bus-DeMeo Asteroid Taxonomy}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/bus-demeo-asteroid-taxonomy}},
  note = {{Based on DeMeo et al. (2009, Icarus 202, 160) via PDS Small Bodies Node}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update Bus-DeMeo asteroid taxonomy: {n_total:,} asteroids"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={len(df)}\n")
    print("Done.")


if __name__ == "__main__":
    main()
