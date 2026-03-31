#!/usr/bin/env python3
"""Fetch Washington Double Star Catalog from VizieR and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from validate import check_dataset
from vizier_tap import vizier_query


HF_REPO = "juliensimon/wds-double-stars"

ADQL = """\
SELECT * FROM "B/wds/wds"\
"""


def main():
    print("Fetching Washington Double Star Catalog from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} double star systems")

    # Rename columns — VizieR may return RAJ2000 or RA_ICRS
    known_renames = {
        "WDS": "wds_id",
        "RAJ2000": "ra_deg",
        "RA_ICRS": "ra_deg",
        "DEJ2000": "dec_deg",
        "DE_ICRS": "dec_deg",
        "Comp": "components",
        "Obs1": "first_observation_year",
        "Obs2": "last_observation_year",
        "Nobs": "n_observations",
        "pa1": "position_angle_first",
        "pa2": "position_angle_last",
        "sep1": "separation_first_arcsec",
        "sep2": "separation_last_arcsec",
        "mag1": "magnitude_primary",
        "mag2": "magnitude_secondary",
        "SpType": "spectral_type",
        "Disc": "discoverer_code",
    }
    rename_map = {k: v for k, v in known_renames.items() if k in df.columns}
    if rename_map:
        df = df.rename(columns=rename_map)

    # Convert numerics
    for col in ["ra_deg", "dec_deg", "first_observation_year", "last_observation_year",
                "n_observations", "position_angle_first", "position_angle_last",
                "separation_first_arcsec", "separation_last_arcsec",
                "magnitude_primary", "magnitude_secondary"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Clean string columns
    for col in ["wds_id", "components", "spectral_type", "discoverer_code"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
            )

    df = df.sort_values("wds_id").reset_index(drop=True)

    check_dataset(df, "wds", min_rows=150000,
                  expected_columns=["ra_deg", "dec_deg"],
                  critical_columns=["ra_deg", "dec_deg"])

    # Stats for README
    n = len(df)
    n_with_sep = int(df["separation_last_arcsec"].notna().sum()) if "separation_last_arcsec" in df.columns else 0
    n_with_spectral = int(df["spectral_type"].notna().sum()) if "spectral_type" in df.columns else 0
    obs_span_min = int(df["first_observation_year"].min()) if "first_observation_year" in df.columns else 0
    obs_span_max = int(df["last_observation_year"].max()) if "last_observation_year" in df.columns else 0

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "wds_double_stars.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Washington Double Star Catalog"
language:
  - en
description: >-
  The Washington Double Star Catalog (WDS) — the world reference catalog for visual
  double and multiple stars. {n:,} systems. Sourced via VizieR CDS Strasbourg.
size_categories:
  - 100K<n<1M
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - double-star
  - binary
  - wds
  - usno
  - astrometry
  - astronomy
  - open-data
  - tabular-data
  - parquet
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/wds_double_stars.parquet
---

# Washington Double Star Catalog

*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

![Update WDS](https://github.com/juliensimon/space-datasets/actions/workflows/update-wds.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.wds&label=updated&color=brightgreen)

The Washington Double Star Catalog (WDS) is **THE** world reference catalog for visual double
and multiple star systems, maintained by the US Naval Observatory. Currently **{n:,}** systems
with observations spanning {obs_span_min} to {obs_span_max}.

## Dataset description

The WDS is the principal database of astrometric double and multiple star information. It
contains positions, magnitudes, spectral types, proper motions, and astrometric measurements
(position angles and separations) for each system. The catalog is actively maintained and
regularly updated as new observations are published.

Double stars are essential for determining stellar masses -- the most fundamental property
of a star -- and for testing stellar evolution models.

The WDS traces its lineage back to Sherburne Wesley Burnham's catalog of 1906 and has been
continuously maintained at the US Naval Observatory for over a century, incorporating
astrometric measurements from visual micrometry, speckle interferometry, adaptive optics,
long-baseline optical interferometry, and space-based observations (Hipparcos, Gaia). The
catalog includes both gravitationally bound physical pairs (true binaries) and optical
doubles -- chance alignments of unrelated stars along the same line of sight. Distinguishing
between the two requires common proper motion analysis or, ideally, measurement of orbital
curvature over a sufficient arc of the orbit.

For physical binaries with well-determined orbits, the combination of angular separation,
orbital period, and parallax yields dynamical masses through Kepler's third law. These
direct mass measurements are the gold standard for calibrating the mass-luminosity relation
and testing stellar structure models across spectral types from O-type supergiants to
late M-dwarfs. The position angle and separation measurements recorded at the first and
last epochs in this catalog encode information about orbital motion: systems showing
significant changes in these quantities over the observing baseline are strong candidates
for orbit determination, while those with negligible change may be either very long-period
binaries or optical pairs.

The WDS encompasses an enormous diversity of systems, from pairs separated by fractions
of an arcsecond -- resolvable only by interferometric techniques -- to wide common proper
motion companions separated by arcminutes or more. Wide binaries (separations > 1000 AU)
are particularly interesting as probes of the Galactic gravitational potential, since their
weakly bound orbits are sensitive to perturbations from passing stars, giant molecular
clouds, and the Galactic tidal field. Hierarchical multiple systems (triples, quadruples,
and higher-order multiples) recorded in the WDS provide constraints on star formation
theories and the dynamical stability of few-body stellar configurations.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `wds_id` | string | WDS designation (based on J2000 coordinates) |
| `ra_deg` | float64 | Right ascension J2000 (degrees) |
| `dec_deg` | float64 | Declination J2000 (degrees) |
| `components` | string | Component designation (e.g. AB, AC) |
| `first_observation_year` | float64 | Year of first observation |
| `last_observation_year` | float64 | Year of last observation |
| `n_observations` | float64 | Number of observations |
| `position_angle_first` | float64 | Position angle at first observation (degrees) |
| `position_angle_last` | float64 | Position angle at last observation (degrees) |
| `separation_first_arcsec` | float64 | Separation at first observation (arcsec) |
| `separation_last_arcsec` | float64 | Separation at last observation (arcsec) |
| `magnitude_primary` | float64 | Magnitude of primary component |
| `magnitude_secondary` | float64 | Magnitude of secondary component |
| `spectral_type` | string | Spectral type |
| `discoverer_code` | string | Discoverer code and number |

## Quick stats

- **{n:,}** double/multiple star systems
- Observations spanning **{obs_span_min}** to **{obs_span_max}**
- **{n_with_sep:,}** with measured separation
- **{n_with_spectral:,}** with spectral type

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/wds-double-stars", split="train")
df = ds.to_pandas()

# Systems with large separation change (orbital motion)
has_both = df.dropna(subset=["separation_first_arcsec", "separation_last_arcsec"])
has_both["sep_change"] = abs(has_both["separation_last_arcsec"] - has_both["separation_first_arcsec"])
movers = has_both.nlargest(20, "sep_change")
print(movers[["wds_id", "separation_first_arcsec", "separation_last_arcsec", "sep_change"]])

# Bright pairs
bright = df[(df["magnitude_primary"] < 6) & (df["magnitude_secondary"] < 8)]
print(f"{{len(bright):,}} naked-eye double stars")
```

## Update frequency

Updated **weekly on Monday at 17:00 UTC** via GitHub Actions.

## Data source

Mason, B.D. et al., The Washington Double Star Catalog,
[US Naval Observatory](https://www.usno.navy.mil/USNO/astrometry/optical-IR-prod/wds/WDS).
Accessed via [VizieR](https://vizier.cds.unistra.fr/), CDS Strasbourg.

## Related datasets

- [hipparcos-catalog](https://huggingface.co/datasets/juliensimon/hipparcos-catalog) -- Hipparcos star catalog
- [gcvs-variable-stars](https://huggingface.co/datasets/juliensimon/gcvs-variable-stars) -- Variable stars
- [open-star-clusters](https://huggingface.co/datasets/juliensimon/open-star-clusters) -- Open star clusters

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/wds-double-stars) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{wds_double_stars,
  author = {{Simon, Julien}},
  title = {{Washington Double Star Catalog}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/wds-double-stars}},
  note = {{Based on Mason et al., US Naval Observatory WDS via VizieR CDS Strasbourg}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update WDS double stars: {n:,} systems"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={n}\n")
    print("Done.")


if __name__ == "__main__":
    main()
