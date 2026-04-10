#!/usr/bin/env python3
"""Fetch Hunt & Reffert Open Star Clusters from VizieR and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from dataset_images import banner_markdown, download_banner
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
        "logAge50": "log_age",
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

        banner_file = download_banner("open-clusters", tmp)
        banner_md = banner_markdown("open-clusters", banner_file)

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
  - parquet
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
{banner_md}
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

Open clusters are born when a giant molecular cloud fragments and collapses, producing a
gravitationally bound group of stars that share the same age, initial chemical composition,
and distance. This makes them natural laboratories for stellar evolution: by comparing the
color-magnitude diagram of a cluster to theoretical isochrones, astronomers can determine
the cluster's age, distance, and reddening simultaneously. The main-sequence turnoff point
-- the luminosity at which stars are just leaving the hydrogen-burning main sequence --
shifts to fainter magnitudes with increasing age, providing a reliable chronometer spanning
from a few million years (for clusters still embedded in their birth clouds) to several
billion years (for ancient survivors like NGC 6791).

The Hunt & Reffert (2024) catalog represents a major advance over earlier compilations.
Using Gaia DR3 astrometry, the authors applied the HDBSCAN clustering algorithm to identify
overdensities in the five-dimensional space of sky position, parallax, and proper motion,
then validated each candidate through isochrone fitting. This approach recovers not only the
well-known clusters from classical catalogs (Dias, MWSC, Kharchenko) but also hundreds of
previously unknown, sparse, or partially dissolved associations that are invisible in
two-dimensional sky projections but clearly distinct in astrometric phase space. The ages
in this catalog are derived from Bayesian isochrone fitting using PARSEC stellar models,
with the logarithmic age (log_age) expressed in years.

Open clusters are the primary tracers of the Milky Way's spiral arm structure, radial
metallicity gradient, and age-metallicity relation. Young clusters (< 10 Myr) delineate
the current loci of spiral arms, while intermediate-age and old clusters map the disk's
dynamical heating and radial migration history. The radial velocities available for a
subset of clusters enable full three-dimensional kinematic analysis, including the
determination of the Galactic rotation curve and the identification of kinematic groups
that may share a common origin in the same star-forming complex.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `ra_deg` | float64 | ICRS J2000.0 right ascension of the cluster center in degrees (0–360); used for sky pointing and cross-matching with Gaia and other star catalogs |
| `dec_deg` | float64 | ICRS J2000.0 declination of the cluster center in degrees (-90 to +90); combined with `ra_deg` gives the full equatorial position |
| `distance_pc` | float64 | Heliocentric distance in parsecs (1 pc = 3.26 ly); typical open cluster range 100–3000 pc; derived from Gaia DR3 parallaxes or main-sequence fitting; null if distance is poorly constrained |
| `parallax_mas` | float64 | Mean cluster parallax in milliarcseconds from Gaia DR3; inverse approximately gives distance (1/parallax_mas × 1000 = distance in pc); null if not measured |
| `log_age` | float64 | Cluster age as log10(age in years); e.g. 7.0 = 10 Myr, 8.5 = 316 Myr, 9.0 = 1 Gyr; derived from Bayesian isochrone fitting using PARSEC stellar models; null if age is not well constrained |
| `extinction_av` | float64 | Line-of-sight visual extinction A_V in magnitudes; amount by which dust dims the cluster in the V-band; young embedded clusters can exceed A_V = 5; null if not measured |
| `n_members` | float64 | Number of confirmed or probable cluster members identified from Gaia proper motion and parallax criteria; null if membership study was not performed |
| `radial_velocity_kms` | float64 | Mean radial velocity of the cluster in km/s (positive = receding); measured from spectra of member stars; enables full 3D kinematics and Galactic orbit calculation; null for clusters without spectroscopic observations |

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

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/open-star-clusters) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

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
