#!/usr/bin/env python3
"""Fetch Galaxy Zoo 2 morphological classifications and upload to HF."""

import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset

SOURCE_URL = "https://zooniverse-data.s3.amazonaws.com/galaxy-zoo-2/zoo2MainSpecz.csv.gz"
HF_REPO = "juliensimon/galaxy-zoo-2-morphology"


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
    # Object IDs as int64
    for col in ["specobjid", "dr8objid", "dr7objid"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    # Coordinates
    df["ra"] = pd.to_numeric(df["ra"], errors="coerce")
    df["dec"] = pd.to_numeric(df["dec"], errors="coerce")

    # All vote count, weight, fraction, debiased, flag columns are numeric
    vote_cols = [c for c in df.columns if c.startswith("t0") or c.startswith("t1")]
    for col in vote_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["total_classifications"] = pd.to_numeric(df["total_classifications"], errors="coerce").astype("Int64")
    df["total_votes"] = pd.to_numeric(df["total_votes"], errors="coerce").astype("Int64")

    # ── Derived columns ───────────────────────────────────────────────
    # Dominant morphology from the top-level smooth/features/artifact question
    smooth_col = "t01_smooth_or_features_a01_smooth_debiased"
    features_col = "t01_smooth_or_features_a02_features_or_disk_debiased"
    artifact_col = "t01_smooth_or_features_a03_star_or_artifact_debiased"

    def classify_morphology(row):
        smooth = row.get(smooth_col)
        features = row.get(features_col)
        artifact = row.get(artifact_col)
        vals = {"smooth": smooth, "features_or_disk": features, "star_or_artifact": artifact}
        # Filter out NaN
        valid = {k: v for k, v in vals.items() if pd.notna(v)}
        if not valid:
            return None
        return max(valid, key=valid.get)

    df["dominant_morphology"] = df.apply(classify_morphology, axis=1)

    # Is barred galaxy (from debiased bar probability > 0.5)
    bar_col = "t03_bar_a06_bar_debiased"
    if bar_col in df.columns:
        df["is_barred"] = df[bar_col] > 0.5

    # Is spiral (from debiased spiral probability > 0.5)
    spiral_col = "t04_spiral_a08_spiral_debiased"
    if spiral_col in df.columns:
        df["is_spiral"] = df[spiral_col] > 0.5

    # Is edge-on (from debiased edge-on probability > 0.5)
    edgeon_col = "t02_edgeon_a04_yes_debiased"
    if edgeon_col in df.columns:
        df["is_edge_on"] = df[edgeon_col] > 0.5

    # ── Stats for README ──────────────────────────────────────────────
    n_smooth = int((df["dominant_morphology"] == "smooth").sum())
    n_features = int((df["dominant_morphology"] == "features_or_disk").sum())
    n_barred = int(df["is_barred"].sum()) if "is_barred" in df.columns else 0
    n_spiral = int(df["is_spiral"].sum()) if "is_spiral" in df.columns else 0
    n_edgeon = int(df["is_edge_on"].sum()) if "is_edge_on" in df.columns else 0
    avg_votes = df["total_votes"].mean()

    # ── Validate ──────────────────────────────────────────────────────
    check_dataset(
        df,
        dataset_name="galaxy-zoo-2-morphology",
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
    )

    # ── Write and upload ──────────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "galaxy_zoo_2_morphology.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Galaxy Zoo 2 Morphological Classifications"
language:
  - en
description: "243,500 citizen-science galaxy morphology classifications from Galaxy Zoo 2 with vote fractions and debiased probabilities for spiral, elliptical, bar, bulge, and merger features."
task_categories:
  - tabular-classification
tags:
  - space
  - galaxies
  - morphology
  - citizen-science
  - galaxy-zoo
  - astronomy
  - open-data
  - sdss
  - tabular-data
  - parquet
size_categories:
  - 100K<n<1M
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/galaxy_zoo_2_morphology.parquet
    default: true
---

# Galaxy Zoo 2 Morphological Classifications

*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

**{len(df):,}** citizen-science galaxy morphology classifications from Galaxy Zoo 2,
the largest visual morphological classification project in astronomy. Each galaxy was
classified by multiple volunteers answering a decision tree of questions about shape,
structure, and features.

## Dataset description

Galaxy Zoo 2 asked hundreds of thousands of volunteers to classify galaxy images from
the Sloan Digital Sky Survey (SDSS). This dataset contains the spectroscopic-redshift
sample (Table 5 from Willett et al. 2013): **{len(df):,}** galaxies with vote counts,
vote fractions, weighted fractions, debiased probabilities, and classification flags
for 11 morphological tasks spanning 37 possible answers.

The decision tree covers: smooth vs. featured, edge-on disk, bar presence, spiral
structure, bulge prominence, oddities (ring, lens, disturbed, irregular, merger, dust
lane), roundedness, bulge shape, and spiral arm properties (tightness, count).

## Quick stats

- **{len(df):,}** galaxies classified
- **{n_smooth:,}** classified as smooth/elliptical
- **{n_features:,}** classified as featured/disk
- **{n_spiral:,}** with spiral structure (debiased probability > 0.5)
- **{n_barred:,}** barred galaxies (debiased probability > 0.5)
- **{n_edgeon:,}** edge-on galaxies (debiased probability > 0.5)
- **{avg_votes:.1f}** average votes per galaxy

## Schema

The dataset has {len(df.columns)} columns. Key columns:

| Column | Type | Description |
|--------|------|-------------|
| `specobjid` | int64 | SDSS spectroscopic object ID |
| `dr8objid` | int64 | SDSS DR8 photometric object ID |
| `dr7objid` | int64 | SDSS DR7 photometric object ID |
| `ra` | float64 | Right Ascension (J2000, degrees) |
| `dec` | float64 | Declination (J2000, degrees) |
| `rastring` | string | RA as sexagesimal string |
| `decstring` | string | Dec as sexagesimal string |
| `sample` | string | Sample membership flag |
| `gz2class` | string | Summary morphological class |
| `total_classifications` | int64 | Total number of classifications |
| `total_votes` | int64 | Total number of votes |
| `dominant_morphology` | string | Derived: highest debiased probability (smooth / features_or_disk / star_or_artifact) |
| `is_barred` | bool | Derived: bar debiased probability > 0.5 |
| `is_spiral` | bool | Derived: spiral debiased probability > 0.5 |
| `is_edge_on` | bool | Derived: edge-on debiased probability > 0.5 |

For each of the 11 morphological tasks (t01-t11) and their answers (a01-a37), there are up to 6 columns:

| Suffix | Description |
|--------|-------------|
| `_count` | Raw number of votes for this answer |
| `_weight` | Weighted vote count (correcting for classifier consistency) |
| `_fraction` | Simple vote fraction |
| `_weighted_fraction` | Weighted vote fraction |
| `_debiased` | Debiased probability (corrected for redshift-dependent bias) |
| `_flag` | Classification flag (1 = plurality answer after debiasing) |

## Usage

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
if "t08_odd_feature_a24_merger_debiased" in df.columns:
    mergers = df[df["t08_odd_feature_a24_merger_debiased"] > 0.5]
```

## Data source

[Galaxy Zoo 2](https://data.galaxyzoo.org/) — Willett et al. (2013),
"Galaxy Zoo 2: detailed morphological classifications for 304,122 galaxies from the
Sloan Digital Sky Survey", *MNRAS*, 435, 2835.
[arXiv:1308.3496](https://arxiv.org/abs/1308.3496)

This table is the spectroscopic-redshift subsample (Table 5).

## Related datasets

- [open-ngc](https://huggingface.co/datasets/juliensimon/open-ngc) — NGC/IC galaxy and nebula catalog
- [exoplanets](https://huggingface.co/datasets/juliensimon/exoplanets) — NASA Exoplanet Archive
- [messier-objects](https://huggingface.co/datasets/juliensimon/messier-objects) — Messier catalog of deep-sky objects

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/galaxy-zoo-2-morphology) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{galaxy_zoo_2_morphology,
  author = {{Simon, Julien}},
  title = {{Galaxy Zoo 2 Morphological Classifications}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/galaxy-zoo-2-morphology}},
  note = {{Based on Galaxy Zoo 2 data (Willett et al. 2013, MNRAS 435, 2835)}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Upload Galaxy Zoo 2 morphology: {len(df):,} galaxies"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    print(f"rows={len(df)}")
    print("Done.")


if __name__ == "__main__":
    main()
