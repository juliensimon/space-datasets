#!/usr/bin/env python3
"""Fetch WISE Catalog of Galactic HII Regions from VizieR and upload to HF."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from dataset_images import banner_markdown, download_banner
from validate import check_dataset
from vizier_tap import vizier_query


HF_REPO = "juliensimon/wise-hii-regions"

ADQL = """\
SELECT * FROM "J/ApJS/212/1/wisecat"\
"""


def main():
    print("Fetching WISE HII Regions catalog from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} HII regions")

    # Strip whitespace from column names
    df.columns = df.columns.str.strip()

    # Drop columns that are >95% null
    null_pct = df.isna().mean()
    drop_cols = null_pct[null_pct > 0.95].index.tolist()
    if drop_cols:
        print(f"  Dropping {len(drop_cols)} mostly-null columns: {drop_cols}")
        df = df.drop(columns=drop_cols)

    # Rename known columns to snake_case
    known_renames = {
        "GLON": "glon_deg",
        "GLAT": "glat_deg",
        "RAJ2000": "ra_deg",
        "DEJ2000": "dec_deg",
        "_RA": "ra_deg",
        "_DE": "dec_deg",
        "RA_ICRS": "ra_deg",
        "DE_ICRS": "dec_deg",
        "RAICRS": "ra_deg",
        "DEICRS": "dec_deg",
        "Rad": "radius_arcmin",
        "VLSR": "vlsr_kms",
        "Vl": "vlsr_kms",
        "Name": "name",
        "Qual": "quality",
        "Type": "region_type",
        "Ref": "reference",
        "n_VLSR": "n_vlsr",
        "KDA": "kda_resolution",
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

    # Numeric coercion
    numeric_cols = ["glon_deg", "glat_deg", "ra_deg", "dec_deg",
                    "radius_arcmin", "vlsr_kms"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Sort by galactic longitude
    sort_col = "glon_deg" if "glon_deg" in df.columns else None
    if sort_col:
        df = df.sort_values(sort_col).reset_index(drop=True)
    else:
        df = df.reset_index(drop=True)

    n_total = len(df)
    print(f"  {n_total:,} HII regions after processing")

    # Stats
    n_with_vlsr = int(df["vlsr_kms"].notna().sum()) if "vlsr_kms" in df.columns else 0
    n_with_radius = int(df["radius_arcmin"].notna().sum()) if "radius_arcmin" in df.columns else 0

    # Quality/type breakdown if available
    quality_counts = ""
    if "quality" in df.columns:
        quality_counts = df["quality"].value_counts().to_dict()
        print(f"  Quality breakdown: {quality_counts}")

    check_dataset(df, "hii-regions", min_rows=5000,
        expected_columns=["glon_deg", "glat_deg"],
        critical_columns=["glon_deg", "glat_deg"])

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "hii_regions.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        banner_file = download_banner("hii-regions", tmp)
        banner_md = banner_markdown("hii-regions", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "WISE Catalog of Galactic HII Regions"
language:
  - en
description: "Catalog of {n_total:,} Galactic HII regions identified using WISE mid-infrared data (Anderson et al. 2014). Includes positions, velocities, and angular sizes."
task_categories:
  - tabular-classification
tags:
  - space
  - hii-region
  - star-formation
  - milky-way
  - wise
  - infrared
  - astronomy
  - galactic
  - open-data
  - tabular-data
  - parquet
size_categories:
  - 1K<n<10K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/hii_regions.parquet
    default: true
---

# WISE Catalog of Galactic HII Regions
{banner_md}
*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

![Update HII Regions](https://github.com/juliensimon/space-datasets/actions/workflows/update-hii-regions.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.hii-regions&label=updated&color=brightgreen)

Catalog of **{n_total:,}** Galactic HII regions from the
[WISE Catalog of Galactic HII Regions](https://vizier.cds.unistra.fr/viz-bin/VizieR?-source=J/ApJS/212/1)
(Anderson et al. 2014), sourced via VizieR CDS Strasbourg.

## Dataset description

HII regions are clouds of ionized hydrogen surrounding hot young stars, tracing active star formation in the Milky Way. They are among the most luminous objects in the Galaxy at infrared and radio wavelengths, making them detectable across the entire Galactic disk even through heavy dust extinction that obscures optical observations.

The WISE (Wide-field Infrared Survey Explorer) catalog by Anderson et al. (2014) is the most complete census of Galactic HII regions to date. It uses WISE mid-infrared data to identify HII region candidates by their characteristic 12 and 22 micron emission from heated dust grains, combined with radio continuum surveys to confirm thermal emission and radio recombination line (RRL) observations to measure velocities. The catalog classifies regions into categories based on observational evidence: known HII regions (confirmed by RRL detection), candidate regions (radio continuum detected but no RRL), radio-quiet candidates (infrared morphology only), and group members.

The radial velocity measurements (VLSR) are particularly valuable because they enable kinematic distance estimates via the Galactic rotation curve, mapping the three-dimensional distribution of star formation across the Milky Way. Combined with angular sizes, these data constrain the physical sizes of the ionized nebulae, which in turn reflect the luminosity and spectral type of the exciting stars. This catalog is essential for studies of Galactic structure, the spiral arm pattern, triggered star formation, and the lifecycle of massive stars.

## Quick stats

- **{n_total:,}** HII regions
- **{n_with_vlsr:,}** with radial velocity measurements
- **{n_with_radius:,}** with angular size measurements

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/wise-hii-regions", split="train")
df = ds.to_pandas()

# Galactic distribution
import matplotlib.pyplot as plt
plt.scatter(df["glon_deg"], df["glat_deg"], s=1, alpha=0.3)
plt.xlabel("Galactic Longitude (deg)")
plt.ylabel("Galactic Latitude (deg)")
plt.title("WISE HII Regions - Galactic Distribution")

# Velocity analysis
with_v = df.dropna(subset=["vlsr_kms"])
print(f"{{len(with_v):,}} HII regions with velocities")
with_v["vlsr_kms"].hist(bins=50)
plt.xlabel("VLSR (km/s)")
plt.title("HII Region Velocity Distribution")

# Size distribution
with_r = df.dropna(subset=["radius_arcmin"])
with_r["radius_arcmin"].hist(bins=50, log=True)
plt.xlabel("Angular radius (arcmin)")
plt.title("HII Region Size Distribution")
```

## Data source

Anderson, L. D., Bania, T. M., Balser, D. S., et al. (2014),
"The WISE Catalog of Galactic HII Regions", ApJS, 212, 1.
Accessed via [VizieR](https://vizier.cds.unistra.fr/), CDS Strasbourg.

## Update schedule

Quarterly (Feb/May/Aug/Nov 1st at 09:00 UTC) via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [nebula-catalog](https://huggingface.co/datasets/juliensimon/nebula-catalog) -- Bright nebulae catalog
- [pulsar-catalog](https://huggingface.co/datasets/juliensimon/pulsar-catalog) -- ATNF Pulsar Catalogue
- [open-star-clusters](https://huggingface.co/datasets/juliensimon/open-star-clusters) -- Open cluster catalog
- [gaia-dr3-young-stellar-objects](https://huggingface.co/datasets/juliensimon/gaia-dr3-young-stellar-objects) -- Gaia DR3 YSOs

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/wise-hii-regions) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{wise_hii_regions,
  author = {{Simon, Julien}},
  title = {{WISE Catalog of Galactic HII Regions}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/wise-hii-regions}},
  note = {{Based on Anderson et al. (2014) ApJS 212, 1 via VizieR CDS}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update WISE HII regions: {n_total:,} regions"
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
