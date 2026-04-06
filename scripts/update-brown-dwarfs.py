#!/usr/bin/env python3
"""Fetch ultracool/brown dwarf catalog (40 pc sample) from VizieR and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from dataset_images import banner_markdown, download_banner
from validate import check_dataset
from vizier_tap import vizier_query


HF_REPO = "juliensimon/brown-dwarf-catalog"

ADQL = """\
SELECT * FROM "J/A+A/645/A100/40pclist"\
"""


def main():
    print("Fetching ultracool/brown dwarf catalog (40 pc) from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} ultracool dwarfs")

    # Rename key columns -- VizieR may return various RA/DEC variants
    known_renames = {
        "RA_ICRS": "ra_deg",
        "RAICRS": "ra_deg",
        "RAJ2000": "ra_deg",
        "_RA": "ra_deg",
        "DE_ICRS": "dec_deg",
        "DEICRS": "dec_deg",
        "DEJ2000": "dec_deg",
        "_DE": "dec_deg",
        "SpT": "spectral_type",
        "SpType": "spectral_type",
        "SpTy": "spectral_type",
        "Dist": "distance_pc",
        "dist": "distance_pc",
        "Plx": "parallax_mas",
        "plx": "parallax_mas",
        "Jmag": "j_mag",
        "Hmag": "h_mag",
        "Kmag": "k_mag",
        "Ksmag": "ks_mag",
        "Gmag": "g_mag",
        "BPmag": "bp_mag",
        "RPmag": "rp_mag",
        "W1mag": "w1_mag",
        "W2mag": "w2_mag",
        "W3mag": "w3_mag",
        "W4mag": "w4_mag",
        "pmRA": "pm_ra_mas_yr",
        "pmDE": "pm_dec_mas_yr",
        "RV": "radial_velocity_kms",
        "Teff": "teff_k",
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
                "j_mag", "h_mag", "k_mag", "ks_mag", "g_mag", "bp_mag", "rp_mag",
                "w1_mag", "w2_mag", "w3_mag", "w4_mag",
                "pm_ra_mas_yr", "pm_dec_mas_yr", "radial_velocity_kms", "teff_k"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    check_dataset(df, "brown-dwarfs", min_rows=10000,
        expected_columns=["ra_deg", "dec_deg"],
        critical_columns=["ra_deg", "dec_deg"])

    # Stats for README
    n_total = len(df)
    n_with_spt = int(df["spectral_type"].notna().sum()) if "spectral_type" in df.columns else 0
    n_with_dist = int(df["distance_pc"].notna().sum()) if "distance_pc" in df.columns else 0

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "brown_dwarfs.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        banner_file = download_banner("brown-dwarfs", tmp)
        banner_md = banner_markdown("brown-dwarfs", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Ultracool and Brown Dwarf Catalog (40 pc)"
language:
  - en
description: "Ultracool and brown dwarf catalog within 40 pc. JWST-relevant. Sourced via VizieR CDS Strasbourg."
task_categories:
  - tabular-classification
tags:
  - space
  - brown-dwarf
  - ultracool
  - jwst
  - stellar
  - astronomy
  - open-data
  - tabular-data
  - parquet
size_categories:
  - 10K<n<100K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/brown_dwarfs.parquet
    default: true
---

# Ultracool and Brown Dwarf Catalog (40 pc)
{banner_md}
*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

Comprehensive catalog of **{n_total:,}** ultracool and brown dwarfs within 40 parsecs,
highly relevant for JWST atmospheric characterization studies.

## Dataset description

Brown dwarfs are substellar objects too low in mass to sustain hydrogen fusion. Ultracool
dwarfs (spectral types M7 and later) bridge the gap between the lowest-mass stars and
giant planets. This volume-complete 40 pc sample from Sebastian et al. (2021) provides
the most comprehensive census of the solar neighborhood's ultracool population, including
L, T, and Y dwarfs ideal for JWST follow-up.

Brown dwarfs occupy a unique region of parameter space between the coolest hydrogen-burning stars (spectral type ~M9, effective temperatures around 2300 K) and the most massive giant planets (~13 Jupiter masses). They form like stars through gravitational collapse of molecular cloud fragments, but their masses (roughly 13-80 Jupiter masses) are insufficient to sustain stable hydrogen fusion. Instead, they cool monotonically over billions of years, passing through the L, T, and Y spectral classes as their atmospheres transition from dust-dominated (L dwarfs, ~1400-2200 K) to methane-dominated (T dwarfs, ~500-1400 K) to ammonia- and water-ice-dominated (Y dwarfs, below ~500 K). This cooling sequence makes brown dwarfs natural laboratories for studying atmospheric physics under conditions intermediate between stellar photospheres and planetary atmospheres.

A volume-complete sample like this 40 pc census is essential for determining the substellar mass function -- the number of brown dwarfs formed per unit mass interval -- which constrains theories of star and planet formation. The space density of brown dwarfs in the solar neighborhood informs estimates of the total baryonic mass budget of the Galaxy and the frequency of free-floating planetary-mass objects. The 40 pc distance limit ensures that even the faintest known Y dwarfs (absolute magnitudes fainter than 20 in the J-band) are detectable with current infrared surveys such as WISE, 2MASS, and UKIDSS.

JWST has transformed brown dwarf science by resolving molecular absorption features in the mid-infrared (3-28 microns) that are inaccessible from the ground, including water, methane, ammonia, carbon dioxide, and phosphine. The nearby brown dwarfs in this catalog are the highest signal-to-noise targets for JWST atmospheric retrieval studies, providing benchmark objects against which atmospheric models are calibrated before being applied to the much fainter directly imaged exoplanets.

## Quick stats

- **{n_total:,}** ultracool dwarfs within 40 pc
- **{n_with_spt:,}** with spectral type classification
- **{n_with_dist:,}** with distance estimates

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/brown-dwarf-catalog", split="train")
df = ds.to_pandas()

# T and Y dwarfs (coldest brown dwarfs)
if "spectral_type" in df.columns:
    cold = df[df["spectral_type"].str.startswith(("T", "Y"), na=False)]
    print(f"{{len(cold):,}} T/Y dwarfs")

# Nearest brown dwarfs
if "distance_pc" in df.columns:
    nearby = df.dropna(subset=["distance_pc"]).sort_values("distance_pc").head(20)
    print(nearby[["ra_deg", "dec_deg", "distance_pc"]].to_string())
```

## Data source

Sebastian, D. et al. (2021), "The census of the solar neighbourhood ultracool dwarf
volume-complete 40 pc sample", A&A, 645, A100. Accessed via
[VizieR](https://vizier.cds.unistra.fr/), CDS Strasbourg.

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update brown dwarf catalog: {n_total:,} dwarfs"
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
