#!/usr/bin/env python3
"""Fetch ICRF3 Celestial Reference Frame from VizieR and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from dataset_images import banner_markdown, download_banner
from validate import check_dataset
from vizier_tap import vizier_query


HF_REPO = "juliensimon/icrf3-reference-frame"

ADQL = """\
SELECT * FROM "J/ApJS/242/5/table2"\
"""


def main():
    print("Fetching ICRF3 sources from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} ICRF3 sources")

    # Rename key columns
    df = df.rename(columns={
        "IERS": "iers_name",
        "_RA": "ra_deg",
        "_DE": "dec_deg",
    })

    # Snake-case remaining columns
    rename_map = {}
    for col in df.columns:
        if col not in ["iers_name", "ra_deg", "dec_deg"]:
            snake = col.replace(" ", "_").replace("-", "_").lower()
            if snake != col:
                rename_map[col] = snake
    if rename_map:
        df = df.rename(columns=rename_map)

    # Convert numerics
    for col in ["ra_deg", "dec_deg"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Clean string columns
    for col in ["iers_name"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
            )

    check_dataset(df, "icrf3", min_rows=3000,
        expected_columns=["iers_name", "ra_deg", "dec_deg"],
        critical_columns=["iers_name", "ra_deg", "dec_deg"])

    # Stats for README
    n_total = len(df)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "icrf3_reference_frame.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        banner_file = download_banner("icrf3", tmp)
        banner_md = banner_markdown("icrf3", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "ICRF3 Celestial Reference Frame"
language:
  - en
description: "The third International Celestial Reference Frame (ICRF3) — the fundamental coordinate reference frame for astronomy, defined by extragalactic radio sources observed by VLBI."
task_categories:
  - tabular-classification
tags:
  - space
  - icrf
  - reference-frame
  - astrometry
  - quasar
  - vlbi
  - open-data
  - tabular-data
  - parquet
size_categories:
  - 1K<n<10K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/icrf3_reference_frame.parquet
    default: true
---

# ICRF3 Celestial Reference Frame
{banner_md}
*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

The third International Celestial Reference Frame (ICRF3) is **the** fundamental coordinate
reference frame for astronomy, adopted by the International Astronomical Union in 2018.
It is defined by **4,588** extragalactic radio sources (primarily quasars) observed by
Very Long Baseline Interferometry (VLBI). This dataset contains **{n_total:,}** sources
with variability and structure parameters from the defining catalog.

## Dataset description

The ICRF is the realization of the International Celestial Reference System (ICRS) at
radio wavelengths. ICRF3 is based on nearly 40 years of VLBI observations and provides
the most accurate positions of extragalactic objects, with median positional uncertainties
of ~30 microarcseconds for the defining sources. These sources serve as the fixed reference
points against which all other celestial positions are measured.

The ICRF is conceptually the modern replacement for the FK5 optical fundamental star catalog. While FK5 was limited by the proper motions and parallaxes of nearby stars, the ICRF uses extremely distant quasars whose apparent motions are negligible, providing a quasi-inertial reference frame tied to the large-scale structure of the universe. VLBI observations at centimeter wavelengths achieve angular resolution of fractions of a milliarcsecond, enabling position determinations at the microarcsecond level for the best-observed sources. ICRF3 incorporates observations at S/X-band (2.3/8.4 GHz), K-band (24 GHz), and X/Ka-band (8.4/32 GHz), providing the first multi-frequency celestial reference frame.

The 4,588 ICRF3 sources are classified into three tiers: 303 defining sources with the most stable positions and minimal source structure, 688 special-handling sources that require careful treatment due to extended jet structure, and the remainder as non-defining sources that densify the reference frame. Source structure -- the extended radio jets that cause apparent position shifts depending on observing frequency and array orientation -- is the dominant systematic error in VLBI astrometry. This dataset includes structure index parameters that quantify each source's compactness and positional stability, which is critical for selecting calibrators for VLBI observations and for space geodesy applications including Earth orientation monitoring and spacecraft navigation.

ICRF3 is the authoritative astrometric reference for missions such as Gaia, which ties its optical reference frame to the ICRF through quasars observed in both radio and optical wavelengths. Differences between the Gaia optical positions and ICRF3 radio positions of the same quasars reveal physical offsets between the optical photocenters and radio cores, providing unique constraints on AGN jet physics and accretion disk structure.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `iers_name` | string | Official IERS source designation in B1950 sexagesimal format (HHMM+DDd, e.g. "0002-478"); this is the authoritative name used in geodetic VLBI scheduling, Earth orientation monitoring, and spacecraft navigation — do not confuse with J2000 designations used in optical catalogs |
| `ra_deg` | float64 | Right ascension of the extragalactic radio source in degrees, ICRS J2000.0 epoch; range 0–360; defining sources carry positional accuracies of ~30 microarcseconds, making these the most precisely located objects in the sky; based on multi-decade VLBI observations, not optical positions |
| `dec_deg` | float64 | Declination of the extragalactic radio source in degrees, ICRS J2000.0; range −90 to +90; positive north of celestial equator; southern hemisphere coverage is sparser due to fewer southern VLBI stations |

Additional columns from the catalog are included with snake_case names.

## Quick stats

- **{n_total:,}** ICRF3 sources

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/icrf3-reference-frame", split="train")
df = ds.to_pandas()

# All-sky distribution
print(f"{{len(df):,}} ICRF3 reference sources")
print(f"RA range: {{df['ra_deg'].min():.2f}} to {{df['ra_deg'].max():.2f}} deg")
print(f"Dec range: {{df['dec_deg'].min():.2f}} to {{df['dec_deg'].max():.2f}} deg")
```

## Data source

Xu, M.H., Anderson, J.M., Heinkelmann, R., et al. (2019), "Structure Effects for
3417 Celestial Reference Frame Radio Sources", ApJS, 242, 5.
Accessed via [VizieR](https://vizier.cds.unistra.fr/), CDS Strasbourg.

## Related datasets

- [pulsar-catalog](https://huggingface.co/datasets/juliensimon/pulsar-catalog) -- ATNF Pulsar Catalogue
- [open-star-clusters](https://huggingface.co/datasets/juliensimon/open-star-clusters) -- Open Star Clusters

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/icrf3-reference-frame) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{icrf3_reference_frame,
  author = {{Simon, Julien}},
  title = {{ICRF3 Celestial Reference Frame}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/icrf3-reference-frame}},
  note = {{Based on Xu et al. (2019), ApJS, 242, 5 via VizieR CDS Strasbourg}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update ICRF3 reference frame: {n_total:,} sources"
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
