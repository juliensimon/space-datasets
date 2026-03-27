#!/usr/bin/env python3
"""Fetch SDSS-based Asteroid Taxonomy from PDS and upload to HF.

Source: PDS Small Bodies Node — SDSS-based Asteroid Taxonomy V1.1
        Carvano et al. (2010), Ivezic et al. (2010)
Static dataset (uploaded once, no workflow).

Two tables are combined:
  - Observation table (107,466 rows): per-observation SDSS reflectances + class
  - Asteroid table (63,468 rows): best classification + orbital elements per asteroid

The observation table is the primary output; orbital elements from the asteroid
table are merged in via asteroid number.
"""

import gc
import io
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset

BASE_URL = "https://sbnarchive.psi.edu/pds3/non_mission/EAR_A_I0035_5_SDSSTAX_V1_1/data"
HF_REPO = "juliensimon/sdss-asteroid-taxonomy"
MIN_ROWS = 50_000

# ── PDS3 fixed-width column specs (from .lbl files) ─────────────────────────
# (name, start_0based, width)

OBS_COLSPECS = [
    ("ast_number",              0,   6),
    ("ast_name",                7,  17),
    ("prov_desig",             24,  11),
    ("tax_class",              36,   2),
    ("score",                  39,   2),
    ("moid",                   44,   7),
    ("bad_flag",               52,   1),
    ("log_refl_u",             55,   5),
    ("log_refl_err_u",         61,   5),
    ("log_refl_g",             68,   5),
    ("log_refl_err_g",         74,   5),
    ("log_refl_r",             81,   5),
    ("log_refl_err_r",         87,   5),
    ("log_refl_i",             94,   5),
    ("log_refl_err_i",        100,   5),
    ("log_refl_z",            107,   5),
    ("log_refl_err_z",        113,   5),
]

AST_COLSPECS = [
    ("ast_number",              0,   6),
    ("ast_name",                7,  17),
    ("prov_desig",             24,  11),
    ("classification",         35,   4),
    ("score_best",             39,   2),
    ("n_class",                43,   1),
    ("method",                 45,   1),
    ("bad_flag_ast",           48,   1),
    ("sequence",               50,   8),
    ("moid_ast",               59,   7),
    ("abs_mag_h",              67,   5),
    ("proper_semimajor_au",    73,   6),
    ("proper_eccentricity",    80,   6),
    ("sin_proper_inclination", 87,   6),
    ("osc_semimajor_au",       94,   7),
    ("osc_eccentricity",      102,   6),
    ("osc_inclination_deg",   110,   7),
]


def _read_pds_table(url: str, colspecs: list[tuple]) -> pd.DataFrame:
    """Download a PDS3 fixed-width table and parse it."""
    print(f"  Downloading {url.rsplit('/', 1)[-1]}...")
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    print(f"    {len(resp.content) / 1024 / 1024:.1f} MB")

    names = [c[0] for c in colspecs]
    specs = [(c[1], c[1] + c[2]) for c in colspecs]  # (start, end) 0-based

    text = resp.text
    del resp
    gc.collect()

    df = pd.read_fwf(
        io.StringIO(text),
        colspecs=specs,
        names=names,
        dtype=str,
    )
    del text
    gc.collect()

    # Strip whitespace from all string columns
    for col in df.columns:
        df[col] = df[col].astype(str).str.strip()
        df[col] = df[col].replace({"nan": None, "": None, "-": None})

    print(f"    {len(df):,} rows")
    return df


def main():
    print("Fetching SDSS-based Asteroid Taxonomy from PDS...")

    # ── Download both tables ─────────────────────────────────────────────
    obs_df = _read_pds_table(f"{BASE_URL}/sdsstax_obs_table.tab", OBS_COLSPECS)
    ast_df = _read_pds_table(f"{BASE_URL}/sdsstax_ast_table.tab", AST_COLSPECS)

    # ── Type coercion — observation table ────────────────────────────────
    obs_df["ast_number"] = pd.to_numeric(obs_df["ast_number"], errors="coerce").astype("Int64")
    obs_df["score"] = pd.to_numeric(obs_df["score"], errors="coerce").astype("Int64")
    obs_df["bad_flag"] = pd.to_numeric(obs_df["bad_flag"], errors="coerce").astype("Int64")

    float_cols_obs = [
        "log_refl_u", "log_refl_err_u",
        "log_refl_g", "log_refl_err_g",
        "log_refl_r", "log_refl_err_r",
        "log_refl_i", "log_refl_err_i",
        "log_refl_z", "log_refl_err_z",
    ]
    for col in float_cols_obs:
        obs_df[col] = pd.to_numeric(obs_df[col], errors="coerce")

    # ── Type coercion — asteroid table (orbital elements to merge) ───────
    ast_df["ast_number"] = pd.to_numeric(ast_df["ast_number"], errors="coerce").astype("Int64")
    ast_df["score_best"] = pd.to_numeric(ast_df["score_best"], errors="coerce").astype("Int64")
    ast_df["n_class"] = pd.to_numeric(ast_df["n_class"], errors="coerce").astype("Int64")
    ast_df["method"] = pd.to_numeric(ast_df["method"], errors="coerce").astype("Int64")
    ast_df["bad_flag_ast"] = pd.to_numeric(ast_df["bad_flag_ast"], errors="coerce").astype("Int64")

    float_cols_ast = [
        "abs_mag_h", "proper_semimajor_au", "proper_eccentricity",
        "sin_proper_inclination", "osc_semimajor_au",
        "osc_eccentricity", "osc_inclination_deg",
    ]
    for col in float_cols_ast:
        ast_df[col] = pd.to_numeric(ast_df[col], errors="coerce")

    # Replace PDS sentinel: proper elements = 0.0 means no proper elements available
    for col in ["proper_semimajor_au", "proper_eccentricity", "sin_proper_inclination"]:
        ast_df.loc[ast_df[col] == 0.0, col] = None

    # ── Merge orbital elements onto observation table ────────────────────
    merge_cols = [
        "ast_number", "classification", "score_best", "n_class", "method",
        "sequence", "abs_mag_h",
        "proper_semimajor_au", "proper_eccentricity", "sin_proper_inclination",
        "osc_semimajor_au", "osc_eccentricity", "osc_inclination_deg",
    ]
    ast_merge = ast_df[merge_cols].copy()
    del ast_df
    gc.collect()

    # Exclude ast_number == 0 or null from merge to avoid cartesian product
    # (many unnumbered observations would cross-join with many unnumbered asteroids)
    obs_numbered = obs_df[obs_df["ast_number"].notna() & (obs_df["ast_number"] != 0)]
    obs_unnumbered = obs_df[obs_df["ast_number"].isna() | (obs_df["ast_number"] == 0)]
    ast_merge_valid = ast_merge[ast_merge["ast_number"].notna() & (ast_merge["ast_number"] != 0)]
    del obs_df
    gc.collect()

    # Merge only numbered asteroids
    merged_numbered = obs_numbered.merge(ast_merge_valid, on="ast_number", how="left")
    del obs_numbered, ast_merge_valid, ast_merge
    gc.collect()

    # For unnumbered observations, add empty merge columns
    for col in merge_cols:
        if col != "ast_number" and col not in obs_unnumbered.columns:
            obs_unnumbered[col] = None

    df = pd.concat([merged_numbered, obs_unnumbered], ignore_index=True)
    del merged_numbered, obs_unnumbered
    gc.collect()

    # Replace ast_number == 0 with NaN
    df.loc[df["ast_number"] == 0, "ast_number"] = pd.NA

    # Build a human-readable object_id
    def _make_object_id(row):
        if pd.notna(row["ast_number"]) and row["ast_number"] != 0:
            return str(row["ast_number"])
        if pd.notna(row["prov_desig"]):
            return str(row["prov_desig"]).strip()
        if pd.notna(row["ast_name"]):
            return str(row["ast_name"]).strip()
        return None

    df["object_id"] = df.apply(_make_object_id, axis=1)

    # ── Final column ordering ────────────────────────────────────────────
    final_cols = [
        "object_id", "ast_number", "ast_name", "prov_desig",
        "tax_class", "score", "moid", "bad_flag",
        "log_refl_u", "log_refl_err_u",
        "log_refl_g", "log_refl_err_g",
        "log_refl_r", "log_refl_err_r",
        "log_refl_i", "log_refl_err_i",
        "log_refl_z", "log_refl_err_z",
        # From asteroid table merge:
        "classification", "score_best", "n_class", "method", "sequence",
        "abs_mag_h",
        "proper_semimajor_au", "proper_eccentricity", "sin_proper_inclination",
        "osc_semimajor_au", "osc_eccentricity", "osc_inclination_deg",
    ]
    df = df[final_cols]

    # ── Stats ────────────────────────────────────────────────────────────
    n_total = len(df)
    n_asteroids = df["object_id"].nunique()
    n_classes = df["tax_class"].nunique()
    class_counts = df["tax_class"].value_counts()
    top_classes = class_counts.head(5)
    n_with_orbit = int(df["osc_semimajor_au"].notna().sum())

    print(f"\n  {n_total:,} observations of {n_asteroids:,} asteroids")
    print(f"  {n_classes} taxonomic classes")
    for cls, cnt in top_classes.items():
        print(f"    {cls}: {cnt:,}")
    print(f"  {n_with_orbit:,} observations with orbital elements")

    # ── Validate ─────────────────────────────────────────────────────────
    check_dataset(
        df,
        dataset_name="sdss-taxonomy",
        min_rows=MIN_ROWS,
        expected_columns=[
            "object_id", "tax_class", "score", "moid",
            "log_refl_u", "log_refl_g", "log_refl_r", "log_refl_i", "log_refl_z",
        ],
        critical_columns=["object_id", "tax_class", "log_refl_r"],
        max_null_pct=0.10,
    )

    # ── Write parquet + README ───────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "sdss_asteroid_taxonomy.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "SDSS-based Asteroid Taxonomy"
language:
  - en
description: "Compositional taxonomy for {n_total:,} SDSS observations of {n_asteroids:,} asteroids, with ugriz reflectances and orbital elements."
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - asteroids
  - taxonomy
  - composition
  - sdss
  - orbital-mechanics
  - open-data
  - tabular-data
size_categories:
  - 100K<n<1M
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/sdss_asteroid_taxonomy.parquet
    default: true
---

# SDSS-based Asteroid Taxonomy

*Part of the [Orbital Mechanics Datasets](https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994) collection on Hugging Face.*

Compositional taxonomy for **{n_total:,}** SDSS photometric observations of **{n_asteroids:,}**
asteroids, classified using the scheme of Carvano et al. (2010). Each observation includes
SDSS u'g'r'i'z' log-reflectances, a taxonomic class assignment, and a probability score.
Orbital elements from the asteroid catalog are merged in for asteroids with known orbits.

## Dataset description

The Sloan Digital Sky Survey (SDSS) Moving Object Catalog observed over 100,000 asteroids
in five photometric bands (u', g', r', i', z') between 1998 and 2007. Carvano et al. (2010)
developed a probabilistic taxonomic classification scheme based on SDSS colors, assigning
each observation to one of nine primary compositional classes inspired by the Bus taxonomy:

- **V** — Basaltic (V-type)
- **O** — Olivine-rich (O-type)
- **Q** — Ordinary chondrite-like (Q-type)
- **S** — Silicaceous (S-complex)
- **A** — Strongly reddened (A-type)
- **L** — Moderately reddened (L-type)
- **D** — Very red, organic-rich (D-type)
- **X** — Degenerate featureless (X-complex)
- **C** — Carbon-rich, featureless (C-complex)

When an observation falls near a class boundary, a two-letter compound class is assigned
(e.g., SQ, CX, LS) indicating ambiguity between the two types. Each observation receives
a probability score (0--100) for the assigned class.

The `classification` column gives the best overall class per asteroid (from the asteroid
summary table), chosen as either the most frequent or highest-scoring class across all
SDSS observations of that object.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `object_id` | string | Primary identifier (asteroid number or provisional designation) |
| `ast_number` | Int64 | IAU asteroid catalog number (null for unnumbered) |
| `ast_name` | string | IAU asteroid name (null if unnamed) |
| `prov_desig` | string | Provisional designation at discovery |
| `tax_class` | string | Taxonomic class for this observation (C/S/V/Q/D/L/X/A/O or compound e.g. SQ/CX) |
| `score` | Int64 | Probability score for assigned class (0-100) |
| `moid` | string | Unique SDSS moving-object observation ID |
| `bad_flag` | Int64 | 1 if any magnitude uncertainty exceeds 3rd quartile |
| `log_refl_u` | float64 | Log reflectance, SDSS u' band |
| `log_refl_err_u` | float64 | Uncertainty of u' log reflectance |
| `log_refl_g` | float64 | Log reflectance, SDSS g' band (reference = 1.0) |
| `log_refl_err_g` | float64 | Uncertainty of g' log reflectance |
| `log_refl_r` | float64 | Log reflectance, SDSS r' band |
| `log_refl_err_r` | float64 | Uncertainty of r' log reflectance |
| `log_refl_i` | float64 | Log reflectance, SDSS i' band |
| `log_refl_err_i` | float64 | Uncertainty of i' log reflectance |
| `log_refl_z` | float64 | Log reflectance, SDSS z' band |
| `log_refl_err_z` | float64 | Uncertainty of z' log reflectance |
| `classification` | string | Best overall class for this asteroid (most frequent or highest score) |
| `score_best` | Int64 | Probability score for best classification |
| `n_class` | Int64 | Number of classified SDSS observations for this asteroid |
| `method` | Int64 | 1 = most frequent class chosen, 0 = highest score chosen |
| `sequence` | string | Sequence of per-observation class assignments |
| `abs_mag_h` | float64 | Absolute magnitude H from SDSS MOC |
| `proper_semimajor_au` | float64 | Proper semi-major axis (AU), null if unavailable |
| `proper_eccentricity` | float64 | Proper eccentricity, null if unavailable |
| `sin_proper_inclination` | float64 | Sine of proper inclination, null if unavailable |
| `osc_semimajor_au` | float64 | Osculating semi-major axis (AU) |
| `osc_eccentricity` | float64 | Osculating eccentricity |
| `osc_inclination_deg` | float64 | Osculating inclination (degrees) |

## Quick stats

- **{n_total:,}** observations of **{n_asteroids:,}** unique asteroids
- **{n_classes}** taxonomic classes
- Top classes: {', '.join(f'**{cls}** ({cnt:,})' for cls, cnt in top_classes.items())}
- **{n_with_orbit:,}** observations with orbital elements

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/sdss-asteroid-taxonomy", split="train")
df = ds.to_pandas()

# Class distribution
df["tax_class"].value_counts().plot.bar()

# Taxonomic composition vs semi-major axis (main belt structure)
import matplotlib.pyplot as plt
belt = df[df["osc_semimajor_au"].between(2.0, 3.5)]
for cls in ["S", "C", "X", "V"]:
    subset = belt[belt["tax_class"] == cls]
    plt.hist(subset["osc_semimajor_au"], bins=100, alpha=0.5, label=cls, density=True)
plt.xlabel("Semi-major axis (AU)")
plt.legend()

# High-confidence V-type (basaltic) asteroids
vesta_family = df[(df["tax_class"] == "V") & (df["score"] > 80)]

# SDSS color-color diagram
plt.scatter(df["log_refl_r"] - df["log_refl_i"],
            df["log_refl_g"] - df["log_refl_r"],
            c=df["tax_class"].astype("category").cat.codes, s=0.2, alpha=0.3)
```

## Data source

[PDS Small Bodies Node — SDSS-based Asteroid Taxonomy V1.1](https://sbn.psi.edu/pds/resource/sdsstax.html)

Based on SDSS Moving Object Catalog observations (1998-2007).
See Carvano et al. (2010) and Ivezic et al. (2010).

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/sdss-asteroid-taxonomy) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{sdss_asteroid_taxonomy,
  author = {{Simon, Julien}},
  title = {{SDSS-based Asteroid Taxonomy}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/sdss-asteroid-taxonomy}},
  note = {{Based on Carvano et al. (2010) SDSS taxonomy from the PDS Small Bodies Node}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Upload SDSS asteroid taxonomy: {n_total:,} observations of {n_asteroids:,} asteroids"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    print(f"rows={n_total}")
    print("Done.")


if __name__ == "__main__":
    main()
