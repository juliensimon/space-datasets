#!/usr/bin/env python3
"""Fetch Milliquas v8 (Million Quasars Catalog) from VizieR and upload to HF."""

import os
import re
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from dataset_images import banner_markdown, download_banner
from validate import check_dataset
from vizier_tap import vizier_query

HF_REPO = "juliensimon/milliquas"

ADQL = """\
SELECT * FROM "VII/294/catalog"\
"""


def main():
    print("Fetching Milliquas v8 catalog from VizieR...")
    df = vizier_query(ADQL, timeout=600)
    print(f"  {len(df):,} objects")

    # --- Column renames ---
    known_renames = {
        "RA_ICRS": "ra_deg",
        "RAJ2000": "ra_deg",
        "_RA": "ra_deg",
        "DE_ICRS": "dec_deg",
        "DEJ2000": "dec_deg",
        "_DE": "dec_deg",
        "Name": "name",
        "Type": "object_type",
        "Cl": "object_type",
        "z": "redshift",
        "Redshift": "redshift",
        "Rmag": "r_mag",
        "rmag": "r_mag",
        "Bmag": "b_mag",
        "bmag": "b_mag",
        "Ref": "reference",
        "Qpct": "qso_probability_pct",
        "XName": "xray_name",
        "Xname": "xray_name",
        "RName": "radio_name",
        "Rname": "radio_name",
        "R": "r_psf_class",
        "B": "b_psf_class",
        "Comment": "comment",
        "rz": "redshift_ref",
        "rName": "name_ref",
        "Lobe1": "radio_lobe_1",
        "Lobe2": "radio_lobe_2",
    }
    rename_map = {k: v for k, v in known_renames.items() if k in df.columns}
    if rename_map:
        df = df.rename(columns=rename_map)

    # Drop unwanted columns
    for col in ["recno", "SimbadName", "More"]:
        if col in df.columns:
            df = df.drop(columns=[col])

    # Snake_case remaining columns
    def to_snake(name):
        s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
        s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
        return s.lower().replace("-", "_").replace(" ", "_")

    df.columns = [to_snake(c) if c not in rename_map.values() else c for c in df.columns]

    # --- Numeric conversion ---
    for col in ["ra_deg", "dec_deg", "redshift", "r_mag", "b_mag", "qso_probability_pct"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # --- Derived columns ---
    if "object_type" in df.columns:
        df["is_qso"] = df["object_type"].astype(str).str.contains("Q", na=False)
    else:
        df["is_qso"] = False

    if "radio_name" in df.columns:
        df["has_radio"] = df["radio_name"].notna() & (df["radio_name"].astype(str).str.strip() != "")
    else:
        df["has_radio"] = False

    if "xray_name" in df.columns:
        df["has_xray"] = df["xray_name"].notna() & (df["xray_name"].astype(str).str.strip() != "")
    else:
        df["has_xray"] = False

    # Sort by name
    if "name" in df.columns:
        df = df.sort_values("name").reset_index(drop=True)

    # --- Validation ---
    check_dataset(df, "milliquas", min_rows=800000,
                  expected_columns=["ra_deg", "dec_deg", "redshift"],
                  critical_columns=["ra_deg", "dec_deg"])

    # --- Stats ---
    n = len(df)
    n_qso = int(df["is_qso"].sum())
    n_radio = int(df["has_radio"].sum())
    n_xray = int(df["has_xray"].sum())
    z_min = df["redshift"].min()
    z_max = df["redshift"].max()
    z_median = df["redshift"].median()
    n_with_z = int(df["redshift"].notna().sum())

    print(f"  {n_qso:,} QSOs, {n_radio:,} with radio, {n_xray:,} with X-ray")
    print(f"  Redshift range: {z_min:.3f} - {z_max:.3f}, median {z_median:.3f}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "milliquas.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        banner_file = download_banner("milliquas", tmp)
        banner_md = banner_markdown("milliquas", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Milliquas — Million Quasars Catalog v8"
language:
  - en
description: >-
  Milliquas v8 — the Million Quasars Catalog containing {n:,} quasars, AGN,
  and blazars with positions, redshifts, magnitudes, and radio/X-ray associations.
  The most comprehensive quasar/AGN compilation available.
size_categories:
  - 1M<n<10M
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - quasars
  - agn
  - blazars
  - active-galaxies
  - astronomy
  - open-data
  - tabular-data
  - parquet
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/milliquas.parquet
---

# Milliquas — Million Quasars Catalog v8
{banner_md}
*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

The Million Quasars (Milliquas) v8 catalog — **{n:,}** quasars, AGN, and blazars,
the most comprehensive compilation of its kind. Includes **{n_qso:,}** type-I QSOs/AGN
with positions, redshifts, optical magnitudes, and radio/X-ray associations.

## Dataset description

Milliquas v8 (Flesch 2023) is a compendium of over 1 million quasars and active galactic
nuclei drawn from the literature and major surveys (SDSS, 2QZ, 6QZ, LAMOST, etc.).
It includes type-I QSOs, AGN, blazars, and type-II objects, each with sky position,
redshift, optical magnitudes, and cross-identifications with radio and X-ray surveys.
This catalog is widely used for quasar target selection, AGN demographics, and
cross-matching with multi-wavelength surveys.

Quasars are the most luminous persistent objects in the universe, powered by accretion onto supermassive black holes with masses ranging from millions to tens of billions of solar masses. Because they can be detected at redshifts beyond z = 7, they provide direct observational windows into the epoch of reionization and the assembly of the first massive galaxies. The broad emission lines produced in their accretion-disk winds encode information about black hole mass and accretion rate, while narrow absorption features imprinted by intervening gas trace the large-scale distribution of baryonic matter along the line of sight.

A catalog of this scale is indispensable for statistical studies of AGN demographics -- how the quasar luminosity function evolves with redshift, what fraction of supermassive black holes are actively accreting at a given epoch, and how AGN feedback influences galaxy evolution. The inclusion of radio and X-ray cross-identifications allows researchers to identify jetted AGN (radio-loud quasars and blazars) and to separate radiatively efficient from radiatively inefficient accretion modes. Milliquas also provides the foundation for selecting spectroscopic targets in next-generation surveys such as DESI, 4MOST, and the Vera Rubin Observatory's LSST.

The QSO probability percentages included for candidate objects make this catalog particularly valuable for probabilistic classification pipelines and for estimating contamination rates in photometric quasar samples. Combined with photometric redshifts and multi-band magnitudes, these data support both traditional statistical analyses and modern machine-learning approaches to AGN identification.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `name` | string | Source designation from the radio or X-ray catalog that first identified the counterpart (e.g., "SDSS J123456.78+123456.7", "3C 273"); not always the most commonly used name |
| `ra_deg` | float64 | Right ascension in decimal degrees (J2000.0 ICRS); range 0–360 |
| `dec_deg` | float64 | Declination in decimal degrees (J2000.0 ICRS); range −90 to +90 |
| `object_type` | string | Source classification code: "Q" (type-I quasar, L_bol > 10¹² L☉), "A" (AGN/Seyfert, lower luminosity), "B" (BL Lac object, featureless spectrum), "N" (narrow-line AGN/Seyfert 2), "K" (known QSO from literature, not re-classified), "q" (photometric quasar candidate, not spectroscopically confirmed) |
| `redshift` | float64 | Spectroscopic or photometric redshift; the most complete compilation of known QSO redshifts globally; range 0.006 to 7.6+; null for ~30% of entries lacking a measured redshift |
| `r_mag` | float64 | Optical magnitude in the R band (red, ~6500 Å); null for radio-selected sources without optical counterpart or magnitude measurement |
| `b_mag` | float64 | Optical magnitude in the B band (blue, ~4400 Å); null for sources without blue-band photometry |
| `qso_probability_pct` | float64 | Probability (0–100%) that the object is a genuine QSO, based on photometric classification; populated for candidate objects; null for spectroscopically confirmed sources |
| `reference` | string | Milliquas internal reference code pointing to the publication or survey that provided the classification or redshift |
| `radio_name` | string | Name of the associated radio source from a radio survey (e.g., FIRST, NVSS, VLBI catalog); null if no radio counterpart has been identified |
| `xray_name` | string | Name of the associated X-ray source (e.g., from ROSAT, Chandra, XMM-Newton); null if no X-ray counterpart has been identified |
| `is_qso` | bool | True if `object_type` contains the letter "Q" (type-I quasar or known QSO); derived convenience flag |
| `has_radio` | bool | True if a non-null radio source name is associated with this object; ~15% of catalog entries have radio counterparts |
| `has_xray` | bool | True if a non-null X-ray source name is associated with this object; ~30% of catalog entries have X-ray counterparts |

## Quick stats

- **{n:,}** objects total
- **{n_qso:,}** QSOs (type contains "Q")
- **{n_with_z:,}** with measured redshift
- Redshift range: **{z_min:.3f}** to **{z_max:.3f}** (median **{z_median:.3f}**)
- **{n_radio:,}** with radio associations
- **{n_xray:,}** with X-ray associations

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/milliquas", split="train")
df = ds.to_pandas()

# High-redshift quasars (z > 4)
high_z = df[df["redshift"] > 4].sort_values("redshift", ascending=False)
print(f"{{len(high_z):,}} quasars with z > 4")

# Redshift distribution
import matplotlib.pyplot as plt
df["redshift"].dropna().hist(bins=200, range=(0, 7))
plt.xlabel("Redshift")
plt.ylabel("Count")
plt.title("Milliquas Redshift Distribution")
```

## Data source

Flesch, E.W. (2023), "The Million Quasars (Milliquas) v8 catalogue", arXiv:2308.01505.
Accessed via [VizieR](https://vizier.cds.unistra.fr/) catalog VII/294, CDS Strasbourg.

## Related datasets

- [quasar-catalog](https://huggingface.co/datasets/juliensimon/quasar-catalog) — SIMBAD Quasar & AGN Catalog
- [galaxy-cluster-catalog](https://huggingface.co/datasets/juliensimon/galaxy-clusters) — Galaxy Cluster Catalog
- [gravitational-lenses](https://huggingface.co/datasets/juliensimon/gravitational-lenses) — Gravitational Lens Catalog

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/milliquas) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{milliquas,
  author = {{Simon, Julien}},
  title = {{Milliquas — Million Quasars Catalog v8}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/milliquas}},
  note = {{Based on Milliquas v8 (Flesch 2023, arXiv:2308.01505) via VizieR CDS Strasbourg}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update Milliquas v8: {n:,} quasars/AGN"
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
