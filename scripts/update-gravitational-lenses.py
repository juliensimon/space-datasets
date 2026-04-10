#!/usr/bin/env python3
"""Fetch the Strong Gravitational Lens Catalog (lenscat) and upload to HF."""

import io
import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

from dataset_images import banner_markdown, download_banner
from validate import check_dataset

DATA_URL = "https://raw.githubusercontent.com/lenscat/lenscat/main/lenscat/data/catalog.csv"
HF_REPO = "juliensimon/gravitational-lenses"

RENAME_COLS = {
    "name": "name",
    "RA [deg]": "ra_deg",
    "DEC [deg]": "dec_deg",
    "zlens": "lens_redshift",
    "type": "lens_type",
    "grading": "grading",
    "ref": "reference",
}

NUMERIC_COLS = ["ra_deg", "dec_deg", "lens_redshift"]


def clean_redshift(val):
    """Parse redshift values, stripping trailing '?' and converting
    placeholder strings ('-', 'measured', 'observed', 'not measured') to NaN."""
    if not isinstance(val, str):
        return val
    val = val.strip().rstrip("?")
    if val in ("-", "measured", "observed", "not measured", ""):
        return None
    try:
        return float(val)
    except ValueError:
        return None


def main():
    print("Fetching Strong Gravitational Lens Catalog (lenscat)...")
    resp = requests.get(DATA_URL, timeout=60)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    print(f"  {len(df):,} raw rows, {len(df.columns)} columns")

    # Rename columns to snake_case
    df = df.rename(columns=RENAME_COLS)

    # Clean redshift column before numeric coercion
    df["lens_redshift"] = df["lens_redshift"].apply(clean_redshift)

    # Coerce numeric columns
    for col in NUMERIC_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Sort by RA
    df = df.sort_values("ra_deg", na_position="last").reset_index(drop=True)

    # Stats
    n_total = len(df)
    n_galaxy = int((df["lens_type"] == "galaxy").sum())
    n_cluster = int((df["lens_type"] == "cluster").sum())
    n_confident = int((df["grading"] == "confident").sum())
    n_probable = int((df["grading"] == "probable").sum())
    n_has_redshift = int(df["lens_redshift"].notna().sum())
    z_min = df["lens_redshift"].min()
    z_max = df["lens_redshift"].max()
    z_median = df["lens_redshift"].median()

    # Validate
    check_dataset(
        df,
        "gravitational-lenses",
        min_rows=25_000,
        expected_columns=["name", "ra_deg", "dec_deg", "lens_type", "grading"],
        critical_columns=["name", "ra_deg", "dec_deg"],
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "gravitational_lenses.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        banner_file = download_banner("gravitational-lenses", tmp)
        banner_md = banner_markdown("gravitational-lenses", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Strong Gravitational Lens Catalog"
language:
  - en
description: "{n_total:,} strong gravitational lenses from the lenscat catalog, including galaxies and galaxy clusters with coordinates, redshifts, and confidence gradings."
task_categories:
  - tabular-classification
tags:
  - space
  - gravitational-lensing
  - astronomy
  - cosmology
  - open-data
  - tabular-data
  - parquet
size_categories:
  - 10K<n<100K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/gravitational_lenses.parquet
    default: true
---

# Strong Gravitational Lens Catalog
{banner_md}
*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

A comprehensive catalog of **{n_total:,}** confirmed and probable strong gravitational lenses
compiled by the [lenscat](https://github.com/lenscat/lenscat) project. Covers both galaxy-scale
and cluster-scale lenses drawn from dozens of surveys and publications.

## Dataset description

Strong gravitational lensing occurs when a massive foreground object (a galaxy or galaxy cluster)
bends the light of a background source so severely that multiple images, arcs, or Einstein rings
are produced. This catalog consolidates discoveries from major surveys including SDSS, DES,
HSC, CLASH, RELICS, and many others into a single machine-readable table.

Each entry records the lens name, sky coordinates, lens redshift (when measured), morphological
type (galaxy or cluster), a confidence grading, and a literature reference.

Gravitational lensing is one of the most striking predictions of general relativity: the curvature of spacetime around a massive object deflects the paths of photons from background sources, acting as a natural telescope. In the strong lensing regime, the deflection is large enough to produce multiple resolved images, giant luminous arcs, or complete Einstein rings. The geometry of these configurations depends on the mass distribution of the lens, the distances involved, and the cosmological model, making strong lenses powerful tools for measuring galaxy and cluster masses, constraining the Hubble constant through time-delay cosmography, and probing the substructure of dark matter halos.

Galaxy-scale lenses, which dominate this catalog by number, typically involve a massive elliptical galaxy deflecting the light of a more distant galaxy or quasar. The image separations are on the order of 1-2 arcseconds, and the Einstein radius directly constrains the total projected mass within it. Cluster-scale lenses produce much larger image separations (tens of arcseconds to arcminutes) and can magnify background galaxies by factors of 10-100, enabling the study of intrinsically faint, high-redshift galaxies that would otherwise be undetectable. Some of the most distant galaxies known were discovered behind massive lensing clusters.

The number of known strong lenses has grown dramatically in recent years thanks to systematic searches in wide-field imaging surveys (DES, HSC, KiDS) and machine-learning algorithms trained to identify lensing features. This catalog consolidates these discoveries into a uniform format. The coming decade will see an explosion in lens discoveries from Euclid, the Vera Rubin Observatory, and the Roman Space Telescope, potentially increasing the known population from tens of thousands to hundreds of thousands of systems.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `name` | string | Lens system designation (e.g. "SL2SJ021411-040502", "SDSS J1148+1930") |
| `ra_deg` | float64 | Right ascension of the lens center, ICRS J2000.0 (degrees, 0–360) |
| `dec_deg` | float64 | Declination of the lens center, ICRS J2000.0 (degrees, -90 to +90) |
| `lens_redshift` | float64 | Spectroscopic redshift of the lensing object (galaxy or cluster); null if not measured; typical range 0.1–1.0 |
| `lens_type` | string | Morphological type of the lensing mass: "galaxy" (Einstein rings/arcs, image separation 0.5–3 arcsec) or "cluster" (multiple arcs, separation 10–60 arcsec) |
| `grading` | string | Lens confidence level: "confident" = spectroscopically confirmed or unambiguous; "probable" = morphologically selected but not yet confirmed |
| `reference` | string | Discovery or catalog reference as NASA ADS bibcode or URL |

## Quick stats

- **{n_total:,}** strong gravitational lenses
- **{n_galaxy:,}** galaxy-scale lenses, **{n_cluster:,}** cluster-scale lenses
- **{n_confident:,}** confident, **{n_probable:,}** probable
- **{n_has_redshift:,}** lenses with measured redshifts (range {z_min:.3f} -- {z_max:.3f}, median {z_median:.3f})

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/gravitational-lenses", split="train")
df = ds.to_pandas()

# Sky distribution
import matplotlib.pyplot as plt
plt.scatter(df["ra_deg"], df["dec_deg"], s=0.2, alpha=0.3)
plt.xlabel("RA (deg)")
plt.ylabel("Dec (deg)")
plt.title("Strong Gravitational Lenses -- Sky Distribution")
plt.gca().invert_xaxis()
plt.show()

# Redshift distribution
df["lens_redshift"].dropna().hist(bins=60)
plt.xlabel("Lens Redshift")
plt.ylabel("Count")
plt.title("Lens Redshift Distribution")
plt.show()

# Galaxy vs cluster breakdown
df["lens_type"].value_counts().plot.bar()
plt.title("Lens Type Distribution")
plt.show()

# Confident vs probable by type
df.groupby(["lens_type", "grading"]).size().unstack().plot.bar()
plt.title("Grading by Lens Type")
plt.show()
```

## Data source

Compiled by the [lenscat](https://github.com/lenscat/lenscat) project, which consolidates
strong lens discoveries from the literature into a single catalog. See the project repository
for the full list of contributing surveys and references.

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/gravitational-lenses) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{gravitational_lenses,
  author = {{Simon, Julien}},
  title = {{Strong Gravitational Lens Catalog}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/gravitational-lenses}},
  note = {{Based on the lenscat project (https://github.com/lenscat/lenscat)}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update gravitational lenses: {n_total:,} lenses"
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
