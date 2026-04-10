#!/usr/bin/env python3
"""Fetch Hipparcos main catalog from VizieR and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from dataset_images import banner_markdown, download_banner
from validate import check_dataset
from vizier_tap import vizier_query


HF_REPO = "juliensimon/hipparcos-catalog"

ADQL = """\
SELECT * FROM "I/239/hip_main"\
"""


def main():
    print("Fetching Hipparcos catalog from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} stars")

    # Rename columns — VizieR may return RA_ICRS or RAJ2000
    known_renames = {
        "HIP": "hip_id",
        "RAICRS": "ra_deg",
        "RA_ICRS": "ra_deg",
        "RAJ2000": "ra_deg",
        "DEICRS": "dec_deg",
        "DE_ICRS": "dec_deg",
        "DEJ2000": "dec_deg",
        "Vmag": "v_magnitude",
        "Plx": "parallax_mas",
        "e_Plx": "parallax_error_mas",
        "pmRA": "proper_motion_ra_mas_yr",
        "pmDE": "proper_motion_dec_mas_yr",
        "B-V": "color_bv",
        "SpType": "spectral_type",
    }
    rename_map = {k: v for k, v in known_renames.items() if k in df.columns}
    if rename_map:
        df = df.rename(columns=rename_map)

    # Convert numerics
    for col in ["ra_deg", "dec_deg", "v_magnitude", "parallax_mas",
                "parallax_error_mas", "proper_motion_ra_mas_yr",
                "proper_motion_dec_mas_yr", "color_bv"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "hip_id" in df.columns:
        df["hip_id"] = pd.to_numeric(df["hip_id"], errors="coerce").astype("Int64")

    # Derive distance from parallax (where parallax > 0)
    if "parallax_mas" in df.columns:
        mask = df["parallax_mas"] > 0
        df.loc[mask, "distance_pc"] = 1000.0 / df.loc[mask, "parallax_mas"]

    # Clean spectral type
    if "spectral_type" in df.columns:
        df["spectral_type"] = df["spectral_type"].astype(str).str.strip().replace(
            {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
        )

    df = df.sort_values("hip_id").reset_index(drop=True)

    check_dataset(df, "hipparcos", min_rows=100000,
                  expected_columns=["ra_deg", "dec_deg"],
                  critical_columns=["ra_deg", "dec_deg"])

    # Stats for README
    n = len(df)
    n_with_parallax = int(df["parallax_mas"].notna().sum()) if "parallax_mas" in df.columns else 0
    n_with_distance = int(df["distance_pc"].notna().sum()) if "distance_pc" in df.columns else 0
    n_with_spectral = int(df["spectral_type"].notna().sum()) if "spectral_type" in df.columns else 0
    median_vmag = df["v_magnitude"].median() if "v_magnitude" in df.columns else None

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "hipparcos.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        banner_file = download_banner("hipparcos", tmp)
        banner_md = banner_markdown("hipparcos", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Hipparcos Star Catalog"
language:
  - en
description: >-
  ESA Hipparcos astrometry mission catalog — {n:,} brightest stars with precise
  positions, parallaxes, and proper motions. Sourced via VizieR CDS Strasbourg.
size_categories:
  - 100K<n<1M
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - hipparcos
  - star
  - astrometry
  - parallax
  - astronomy
  - open-data
  - tabular-data
  - parquet
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/hipparcos.parquet
---

# Hipparcos Star Catalog
{banner_md}
*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

The ESA Hipparcos space astrometry mission catalog containing **{n:,}** of the brightest
stars in the sky with precise positions, parallaxes, and proper motions.

## Dataset description

The Hipparcos satellite (1989-1993) was ESA's pioneering space astrometry mission. It measured
the positions, parallaxes, and proper motions of 118,218 stars with unprecedented precision,
creating the first high-accuracy stellar reference frame from space. Hipparcos parallaxes
remain the gold standard for nearby star distances and are the foundation for the cosmic
distance ladder.

Hipparcos achieved milliarcsecond-level astrometry — a factor of 100 improvement over ground-based catalogs — by observing from above Earth's atmosphere, which eliminates the turbulent seeing that limits ground-based parallax measurements. The mission's key deliverable, trigonometric parallax, provides the most direct and model-independent method of measuring stellar distances: a star at 1 parsec subtends a parallax of 1 arcsecond, and distance in parsecs is simply 1/parallax. With typical parallax uncertainties of 1 mas, Hipparcos yielded distances accurate to 10% out to about 100 pc, encompassing the solar neighborhood and enabling definitive calibration of the main sequence, giant branch, and key standard candles such as Cepheid variables and RR Lyrae stars.

The scientific legacy of Hipparcos extends far beyond simple distance measurement. Proper motions from the catalog revealed the kinematic structure of nearby stellar streams and moving groups, constraining the dynamics of the Galactic disk. Combined with radial velocities, Hipparcos data enabled full three-dimensional space velocity determinations for thousands of stars, providing the first precise map of the local velocity field. The catalog's photometric data (Hp band, along with Tycho B_T and V_T) established luminosity calibrations for spectral types across the HR diagram. Although Gaia has since surpassed Hipparcos in depth and precision by orders of magnitude, the Hipparcos catalog retains enduring value: it provides an independent epoch (J1991.25) for long-baseline proper motion studies, and its bright-star astrometry remains a benchmark for validating Gaia's solutions at the bright end where CCD saturation effects become significant.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `hip_id` | int64 | Hipparcos Input Catalog identifier; integer in range 1–120404; the standard cross-reference identifier for stars brighter than ~12 mag observed by the Hipparcos satellite (1989–1993); still widely used to cross-match with Gaia and Tycho-2 |
| `ra_deg` | float64 | Right ascension in degrees, ICRS at reference epoch J1991.25 (the astrometric midpoint of the Hipparcos mission, not J2000.0); range 0–360; differs from J2000.0 by a small proper-motion correction that grows with stellar velocity |
| `dec_deg` | float64 | Declination in degrees, ICRS at reference epoch J1991.25; range −90 to +90; positive north of the celestial equator |
| `v_magnitude` | float64 | Johnson V-band apparent magnitude; higher values are fainter; catalog covers roughly V = 2–12.4 mag; null for stars with only Hp-band photometry |
| `parallax_mas` | float64 | Trigonometric parallax in milliarcseconds; convert to distance via distance_pc = 1000 / parallax_mas; Hipparcos precision ~1 mas (cf. Gaia ~0.02 mas); negative values are physically meaningful measurement noise for distant stars where the true parallax is near zero |
| `parallax_error_mas` | float64 | 1-sigma formal uncertainty on the parallax in milliarcseconds; stars where parallax_error_mas > 0.5 × parallax_mas have uncertain distances (signal-to-noise < 2); use with caution for distance-dependent analyses |
| `proper_motion_ra_mas_yr` | float64 | Proper motion in right ascension in milliarcseconds per year, with the cos(dec) factor already applied so this is the true angular rate on the sky (not the coordinate rate); positive = eastward motion |
| `proper_motion_dec_mas_yr` | float64 | Proper motion in declination in milliarcseconds per year; positive = northward motion; combined with proper_motion_ra_mas_yr gives the full tangential velocity vector on the sky |
| `color_bv` | float64 | Johnson B−V color index in magnitudes; more positive values indicate redder, cooler stars (e.g. B−V ≈ −0.3 for hot O/B stars, +1.5 for cool M giants); null for stars lacking B-band photometry |
| `spectral_type` | string | MK (Morgan–Keenan) spectral classification from catalog cross-references, e.g. "G2V" (Sun-like), "K0III" (red giant); encodes temperature class (O B A F G K M), luminosity class (I–V), and sometimes peculiarity flags; null for ~30% of stars, especially fainter objects |
| `distance_pc` | float64 | Heliocentric distance in parsecs, derived as 1000 / parallax_mas; null when parallax_mas ≤ 0 (unphysical noise-dominated measurements); treat values with large parallax_error_mas as highly uncertain |

## Quick stats

- **{n:,}** stars
- **{n_with_parallax:,}** with measured parallax
- **{n_with_distance:,}** with derived distance
- **{n_with_spectral:,}** with spectral type
- Median V magnitude: **{median_vmag:.1f}**

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/hipparcos-catalog", split="train")
df = ds.to_pandas()

# Nearest stars (within 10 parsecs)
nearby = df[df["distance_pc"] < 10].sort_values("distance_pc")
print(nearby[["hip_id", "v_magnitude", "distance_pc", "spectral_type"]])

# HR diagram
import matplotlib.pyplot as plt
valid = df.dropna(subset=["color_bv", "v_magnitude"])
plt.scatter(valid["color_bv"], valid["v_magnitude"], s=0.1, alpha=0.3)
plt.gca().invert_yaxis()
plt.xlabel("B-V Color Index")
plt.ylabel("V Magnitude")
plt.title("Hipparcos HR Diagram")
```

## Data source

ESA Hipparcos and Tycho Catalogues (Perryman et al. 1997, A&A 323, L49).
Accessed via [VizieR](https://vizier.cds.unistra.fr/), CDS Strasbourg.

## Related datasets

- [gcvs-variable-stars](https://huggingface.co/datasets/juliensimon/gcvs-variable-stars) -- General Catalogue of Variable Stars
- [open-star-clusters](https://huggingface.co/datasets/juliensimon/open-star-clusters) -- Open Star Clusters
- [pulsar-catalog](https://huggingface.co/datasets/juliensimon/pulsar-catalog) -- ATNF Pulsar Catalogue

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/hipparcos-catalog) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{hipparcos_catalog,
  author = {{Simon, Julien}},
  title = {{Hipparcos Star Catalog}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/hipparcos-catalog}},
  note = {{Based on ESA Hipparcos Catalogue (Perryman et al. 1997) via VizieR CDS Strasbourg}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update Hipparcos catalog: {n:,} stars"
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
