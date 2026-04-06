#!/usr/bin/env python3
"""Fetch cosmic void catalog from VizieR and upload to HF."""

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


HF_REPO = "juliensimon/cosmic-void-catalog"

# Pan et al. (2012) SDSS DR7 Void Catalog
ADQL = """\
SELECT * FROM "J/MNRAS/421/926/voids"\
"""

# Fallback catalogs if primary table fails
FALLBACK_QUERIES = [
    ('Mao et al. 2017', 'SELECT * FROM "J/ApJ/835/161/table1"'),
    ('Sutter et al. 2012', 'SELECT * FROM "J/ApJ/761/187"'),
]


def fetch_catalog() -> pd.DataFrame:
    """Fetch cosmic void catalog, trying multiple VizieR tables."""
    print("Fetching Pan et al. (2012) SDSS DR7 void catalog from VizieR...")
    try:
        df = vizier_query(ADQL)
        if len(df) >= 100:
            print(f"  Pan et al. (2012): {len(df):,} voids")
            return df
        print(f"  Pan et al. (2012) returned only {len(df)} rows, trying fallback...")
    except Exception as e:
        print(f"  Pan et al. (2012) failed: {e}")

    for name, query in FALLBACK_QUERIES:
        print(f"Trying {name}...")
        try:
            df = vizier_query(query)
            if len(df) >= 50:
                print(f"  {name}: {len(df):,} voids")
                return df
            print(f"  {name} returned only {len(df)} rows")
        except Exception as e:
            print(f"  {name} failed: {e}")

    print("::error::All void catalog sources failed")
    sys.exit(1)


def main():
    df = fetch_catalog()

    # Drop recno helper column
    if "recno" in df.columns:
        df = df.drop(columns=["recno"])

    # Drop columns that are >95% null
    null_frac = df.isnull().mean()
    drop_cols = null_frac[null_frac > 0.95].index.tolist()
    if drop_cols:
        print(f"  Dropping {len(drop_cols)} mostly-null columns: {drop_cols}")
        df = df.drop(columns=drop_cols)

    # Rename columns to snake_case (common VizieR void catalog columns)
    rename = {
        "RAJ2000": "ra_deg",
        "DEJ2000": "dec_deg",
        "RAdeg": "ra_deg",
        "DEdeg": "dec_deg",
        "RA": "ra_deg",
        "DE": "dec_deg",
        "z": "redshift",
        "zv": "redshift",
        "Reff": "radius_eff_mpc",
        "Rvoid": "radius_eff_mpc",
        "R": "radius_eff_mpc",
        "Rmax": "radius_max_mpc",
        "Void": "void_id",
        "Name": "void_name",
        "Dens": "density_contrast",
        "DensCon": "density_contrast",
        "delta": "density_contrast",
        "Dist": "distance_mpc",
        "Ngal": "n_galaxies",
        "N": "n_galaxies",
        "GLAT": "glat_deg",
        "GLON": "glon_deg",
        "Vol": "volume_mpc3",
        "Ell": "ellipticity",
    }
    rename = {k: v for k, v in rename.items() if k in df.columns}
    df = df.rename(columns=rename)

    # Lowercase any remaining uppercase column names
    df.columns = [c.lower().replace(" ", "_") if c == c.upper() or any(ch.isupper() for ch in c) else c
                  for c in df.columns]

    # Coerce numeric columns
    numeric_candidates = [
        "ra_deg", "dec_deg", "redshift", "radius_eff_mpc", "radius_max_mpc",
        "density_contrast", "distance_mpc", "n_galaxies", "glat_deg", "glon_deg",
        "volume_mpc3", "ellipticity",
    ]
    for col in numeric_candidates:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Sort by effective radius descending (largest voids first)
    sort_col = None
    for candidate in ["radius_eff_mpc", "radius_max_mpc", "redshift"]:
        if candidate in df.columns:
            sort_col = candidate
            break
    if sort_col:
        df = df.sort_values(sort_col, ascending=False).reset_index(drop=True)
        print(f"  Sorted by {sort_col} descending")

    n_total = len(df)
    print(f"  {n_total:,} cosmic voids total")

    # Build expected columns from what we actually have
    expected = [c for c in ["ra_deg", "dec_deg", "redshift", "radius_eff_mpc"]
                if c in df.columns]
    critical = [c for c in ["ra_deg", "dec_deg"] if c in df.columns]

    check_dataset(df, "cosmic-voids", min_rows=500,
                  expected_columns=expected,
                  critical_columns=critical)

    # Compute stats for README
    median_radius = df["radius_eff_mpc"].median() if "radius_eff_mpc" in df.columns else None
    max_radius = df["radius_eff_mpc"].max() if "radius_eff_mpc" in df.columns else None
    median_z = df["redshift"].median() if "redshift" in df.columns else None
    z_min = df["redshift"].min() if "redshift" in df.columns else None
    z_max = df["redshift"].max() if "redshift" in df.columns else None

    if n_total >= 10000:
        size_cat = "10K<n<100K"
    elif n_total >= 1000:
        size_cat = "1K<n<10K"
    else:
        size_cat = "n<1K"

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "cosmic_voids.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        # Build dynamic stats block
        stats_lines = [f"- **{n_total:,}** cosmic voids"]
        if median_radius is not None:
            stats_lines.append(f"- Median effective radius: **{median_radius:.1f} Mpc**")
        if max_radius is not None:
            stats_lines.append(f"- Largest void radius: **{max_radius:.1f} Mpc**")
        if median_z is not None:
            stats_lines.append(f"- Median redshift: **{median_z:.3f}**")
        if z_min is not None and z_max is not None:
            stats_lines.append(f"- Redshift range: **{z_min:.3f}** to **{z_max:.3f}**")
        stats_block = "\n".join(stats_lines)

        # Build schema table from actual columns
        col_descriptions = {
            "void_id": ("int/string", "Void identifier"),
            "void_name": ("string", "Void name or designation"),
            "ra_deg": ("float", "Right ascension J2000 (degrees)"),
            "dec_deg": ("float", "Declination J2000 (degrees)"),
            "glon_deg": ("float", "Galactic longitude (degrees)"),
            "glat_deg": ("float", "Galactic latitude (degrees)"),
            "redshift": ("float", "Void center redshift"),
            "radius_eff_mpc": ("float", "Effective void radius (Mpc)"),
            "radius_max_mpc": ("float", "Maximum void radius (Mpc)"),
            "density_contrast": ("float", "Central density contrast (delta)"),
            "distance_mpc": ("float", "Comoving distance to void center (Mpc)"),
            "n_galaxies": ("int", "Number of galaxies defining the void"),
            "volume_mpc3": ("float", "Void volume (Mpc^3)"),
            "ellipticity": ("float", "Void ellipticity"),
        }
        schema_lines = ["| Column | Type | Description |", "|--------|------|-------------|"]
        for col in df.columns:
            if col in col_descriptions:
                dtype, desc = col_descriptions[col]
            else:
                dtype = "float" if df[col].dtype.kind == "f" else ("int" if df[col].dtype.kind == "i" else "string")
                desc = col.replace("_", " ").title()
            schema_lines.append(f"| `{col}` | {dtype} | {desc} |")
        schema_block = "\n".join(schema_lines)

        banner_file = download_banner("cosmic-voids", tmp)
        banner_md = banner_markdown("cosmic-voids", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Cosmic Void Catalog"
language:
  - en
description: "Catalog of {n_total:,} cosmic voids from SDSS, with positions, redshifts, radii, and density contrasts. Cosmic voids are vast underdense regions in the large-scale structure of the universe."
task_categories:
  - tabular-classification
tags:
  - space
  - cosmic-void
  - large-scale-structure
  - cosmology
  - sdss
  - astronomy
  - dark-energy
  - open-data
  - tabular-data
  - parquet
size_categories:
  - {size_cat}
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/cosmic_voids.parquet
    default: true
---

# Cosmic Void Catalog
{banner_md}
*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) and [Galaxies & Cosmology](https://huggingface.co/collections/juliensimon/galaxies-cosmology-datasets-6849da7f5e6455f6a7b2afb9) collections on Hugging Face.*

![Update Cosmic Voids](https://github.com/juliensimon/space-datasets/actions/workflows/update-cosmic-voids.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$["cosmic-voids"]&label=updated&color=brightgreen)

Catalog of **{n_total:,}** cosmic voids identified in the Sloan Digital Sky Survey (SDSS),
sourced from VizieR CDS Strasbourg.

## Dataset description

Cosmic voids are vast underdense regions in the large-scale structure of the universe, typically 20-50 Mpc in radius. They occupy the majority of the volume of the universe and are bounded by filaments, walls, and clusters that form the cosmic web. Voids are among the cleanest cosmological laboratories available because their interiors are dominated by dark energy rather than by the complex nonlinear gravitational dynamics that govern overdense regions.

Void properties are powerful probes of fundamental physics. The void size function (abundance as a function of radius) is sensitive to the matter density parameter, sigma_8, and the dark energy equation of state. The Alcock-Paczynski test applied to stacked void shapes constrains the expansion history of the universe. Void lensing profiles measure the matter content of underdense regions and test modified gravity theories, since voids amplify the differences between general relativity and alternative theories such as f(R) gravity. The integrated Sachs-Wolfe (ISW) effect -- the late-time blueshift of CMB photons traversing growing voids -- provides independent evidence for dark energy.

This catalog enables studies of void demographics, spatial distribution, and correlations with other large-scale structure tracers. Cross-matching with galaxy surveys reveals how galaxy properties (color, morphology, star formation rate) depend on large-scale environment, testing the hypothesis that void galaxies evolve differently from their counterparts in denser regions.

## Schema

{schema_block}

## Quick stats

{stats_block}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/cosmic-void-catalog", split="train")
df = ds.to_pandas()

# Void size distribution
import matplotlib.pyplot as plt
if "radius_eff_mpc" in df.columns:
    df["radius_eff_mpc"].dropna().hist(bins=30, edgecolor="black")
    plt.xlabel("Effective Radius (Mpc)")
    plt.ylabel("Count")
    plt.title("Cosmic Void Size Distribution")

# Redshift distribution
if "redshift" in df.columns:
    df["redshift"].dropna().hist(bins=30, edgecolor="black")
    plt.xlabel("Redshift")
    plt.ylabel("Count")
    plt.title("Void Redshift Distribution")

# Sky distribution
plt.figure(figsize=(12, 6))
plt.scatter(df["ra_deg"], df["dec_deg"], s=df.get("radius_eff_mpc", 5)**2 / 50,
            alpha=0.5, c=df.get("redshift"), cmap="viridis")
plt.colorbar(label="Redshift")
plt.xlabel("RA (deg)")
plt.ylabel("Dec (deg)")
plt.title("Cosmic Void Sky Distribution")
```

## Data source

Cosmic void catalog from the Sloan Digital Sky Survey (SDSS),
accessed via [VizieR](https://vizier.cds.unistra.fr/), CDS Strasbourg.

Primary source: Pan D.C., Vogeley M.S., Hoyle F., Choi Y.-Y., Park C., 2012, MNRAS, 421, 926.

## Update schedule

Semi-annual (January and July 1st at 07:30 UTC) via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [desi-dr1-redshifts](https://huggingface.co/datasets/juliensimon/desi-dr1-redshifts) -- DESI DR1 galaxy redshifts
- [galaxy-clusters](https://huggingface.co/datasets/juliensimon/galaxy-clusters) -- Planck SZ galaxy clusters
- [pantheon-plus-sne-ia](https://huggingface.co/datasets/juliensimon/pantheon-plus-sne-ia) -- Pantheon+ Type Ia supernovae
- [planck-sz2-clusters](https://huggingface.co/datasets/juliensimon/planck-sz2-clusters) -- Planck SZ2 cluster catalog

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/cosmic-void-catalog) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{cosmic_void_catalog,
  author = {{Simon, Julien}},
  title = {{Cosmic Void Catalog}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/cosmic-void-catalog}},
  note = {{Based on SDSS void catalogs via VizieR CDS Strasbourg}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update cosmic void catalog: {n_total:,} voids"
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
