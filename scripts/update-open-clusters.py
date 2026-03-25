#!/usr/bin/env python3
"""Fetch Hunt & Reffert Open Star Clusters from VizieR and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from validate import check_dataset
from vizier_tap import vizier_query


HF_REPO = "juliensimon/open-star-clusters"

ADQL = """\
SELECT * FROM "J/A+A/686/A42/clusters"\
"""


def main():
    print("Fetching Hunt & Reffert open clusters from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} open clusters")

    # Rename key columns -- VizieR may return _RA/_DE or RAJ2000/DEJ2000
    # and Dist or d for distance, etc. Guard all lookups.
    known_renames = {
        "RA_ICRS": "ra_deg",
        "RAJ2000": "ra_deg",
        "_RA": "ra_deg",
        "DE_ICRS": "dec_deg",
        "DEJ2000": "dec_deg",
        "_DE": "dec_deg",
        "dist50": "distance_pc",
        "Dist": "distance_pc",
        "Plx": "parallax_mas",
        "plx": "parallax_mas",
        "Age": "log_age",
        "age": "log_age",
        "AV": "extinction_av",
        "Av": "extinction_av",
        "Nmemb": "n_members",
        "nmemb": "n_members",
        "N": "n_members",
        "RV": "radial_velocity_kms",
        "rv": "radial_velocity_kms",
    }
    rename_map = {k: v for k, v in known_renames.items() if k in df.columns}
    if rename_map:
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

    # Convert numerics
    for col in ["ra_deg", "dec_deg", "distance_pc", "parallax_mas",
                "log_age", "extinction_av", "n_members", "radial_velocity_kms"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    check_dataset(df, "open-clusters", min_rows=5000,
        expected_columns=["ra_deg", "dec_deg"],
        critical_columns=["ra_deg", "dec_deg"])

    # Stats for README
    n_total = len(df)
    n_with_rv = int(df["radial_velocity_kms"].notna().sum()) if "radial_velocity_kms" in df.columns else 0
    n_with_age = int(df["log_age"].notna().sum()) if "log_age" in df.columns else 0

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "open_star_clusters.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Open Star Clusters (Hunt & Reffert 2024)"
language:
  - en
description: "The most comprehensive Gaia-era catalog of open star clusters from Hunt & Reffert (2024). Sourced via VizieR CDS Strasbourg."
task_categories:
  - tabular-classification
tags:
  - space
  - star-cluster
  - open-cluster
  - gaia
  - astronomy
  - open-data
  - tabular-data
size_categories:
  - 1K<n<10K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/open_star_clusters.parquet
    default: true
---

# Open Star Clusters (Hunt & Reffert 2024)

*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

The most comprehensive Gaia-era catalog of open star clusters, containing **{n_total:,}** clusters
with positions, distances, ages, and membership counts derived from Gaia DR3.

## Dataset description

Open clusters are gravitationally bound groups of stars that formed together from the same
molecular cloud. They are key tracers of Galactic structure, stellar evolution, and the
chemical enrichment history of the Milky Way disk. This catalog from Hunt & Reffert (2024)
represents the most complete census of open clusters in the Gaia era, combining automated
detection with careful validation.

Each entry includes sky coordinates, distance, parallax, age, extinction, number of members,
and radial velocity where available.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `ra_deg` | float64 | Right ascension J2000 (degrees) |
| `dec_deg` | float64 | Declination J2000 (degrees) |
| `distance_pc` | float64 | Distance (parsecs) |
| `parallax_mas` | float64 | Parallax (milliarcseconds) |
| `log_age` | float64 | Logarithmic age (log10 years) |
| `extinction_av` | float64 | Visual extinction A_V (mag) |
| `n_members` | float64 | Number of identified members |
| `radial_velocity_kms` | float64 | Radial velocity (km/s) |

## Quick stats

- **{n_total:,}** open clusters
- **{n_with_age:,}** with age estimates
- **{n_with_rv:,}** with radial velocities

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/open-star-clusters", split="train")
df = ds.to_pandas()

# Nearby clusters (< 500 pc)
nearby = df[df["distance_pc"] < 500].sort_values("distance_pc")
print(f"{{len(nearby):,}} clusters within 500 pc")

# Young clusters (< 10 Myr)
young = df[df["log_age"] < 7.0]
print(f"{{len(young):,}} clusters younger than 10 Myr")
```

## Data source

Hunt, E.L. & Reffert, S. (2024), "Improving the open cluster census. III. Using Gaia DR3",
A&A, 686, A42. Accessed via [VizieR](https://vizier.cds.unistra.fr/), CDS Strasbourg.

## Related datasets

- [gcvs-variable-stars](https://huggingface.co/datasets/juliensimon/gcvs-variable-stars) -- General Catalogue of Variable Stars
- [pulsar-catalog](https://huggingface.co/datasets/juliensimon/pulsar-catalog) -- ATNF Pulsar Catalogue

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Citation

```bibtex
@dataset{{open_star_clusters,
  author = {{Simon, Julien}},
  title = {{Open Star Clusters (Hunt & Reffert 2024)}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/open-star-clusters}},
  note = {{Based on Hunt & Reffert (2024), A&A, 686, A42 via VizieR CDS Strasbourg}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update open star clusters: {n_total:,} clusters"
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
