#!/usr/bin/env python3
"""Fetch Bright Star Catalogue (BSC5) from VizieR and upload to HF."""

import os
import re
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from dataset_images import banner_markdown, download_banner
from validate import check_dataset
from vizier_tap import vizier_query

HF_REPO = "juliensimon/bright-star-catalog"

ADQL = 'SELECT * FROM "V/50/catalog"'


def main():
    print("Fetching Bright Star Catalogue from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} stars")

    # Drop unwanted columns
    for col in ["recno", "SimbadName", "More"]:
        if col in df.columns:
            df = df.drop(columns=[col])

    # Rename columns — VizieR may return different variants
    known_renames = {
        "HR": "hr_number",
        "RA_ICRS": "ra_deg",
        "RAJ2000": "ra_deg",
        "_RA": "ra_deg",
        "RAICRS": "ra_deg",
        "DE_ICRS": "dec_deg",
        "DEJ2000": "dec_deg",
        "_DE": "dec_deg",
        "DEICRS": "dec_deg",
        "Name": "name",
        "HD": "hd_number",
        "SpType": "spectral_type",
        "SpT": "spectral_type",
        "Vmag": "v_mag",
        "B-V": "b_v_color",
        "B_V": "b_v_color",
        "U-B": "u_b_color",
        "U_B": "u_b_color",
        "R-I": "r_i_color",
        "R_I": "r_i_color",
        "pmRA": "pm_ra_arcsec_yr",
        "pmDE": "pm_dec_arcsec_yr",
        "RadVel": "radial_velocity_kms",
        "RV": "radial_velocity_kms",
        "RotVel": "rotational_velocity_kms",
        "vsini": "rotational_velocity_kms",
        "Plx": "parallax_mas",
        "plx": "parallax_mas",
        "MultCat": "multiplicity_flag",
        "VarID": "variable_name",
        "VarName": "variable_name",
    }
    rename_map = {k: v for k, v in known_renames.items() if k in df.columns}
    if rename_map:
        df = df.rename(columns=rename_map)

    # Snake_case remaining columns not yet renamed
    renamed_vals = set(rename_map.values())
    new_cols = {}
    for col in df.columns:
        if col not in renamed_vals:
            snake = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", col)
            snake = re.sub(r"[^a-zA-Z0-9]+", "_", snake).strip("_").lower()
            if snake != col:
                new_cols[col] = snake
    if new_cols:
        df = df.rename(columns=new_cols)

    # Numeric conversion
    numeric_cols = [
        "ra_deg", "dec_deg", "v_mag", "b_v_color", "u_b_color", "r_i_color",
        "pm_ra_arcsec_yr", "pm_dec_arcsec_yr", "radial_velocity_kms",
        "rotational_velocity_kms", "parallax_mas",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "hr_number" in df.columns:
        df["hr_number"] = pd.to_numeric(df["hr_number"], errors="coerce").astype("Int64")
    if "hd_number" in df.columns:
        df["hd_number"] = pd.to_numeric(df["hd_number"], errors="coerce").astype("Int64")

    # Clean string columns
    for col in ["spectral_type", "multiplicity_flag", "variable_name", "name"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
            )

    # Derived columns
    # spectral_class: extract first letter from spectral_type (O, B, A, F, G, K, M)
    valid_classes = {"O", "B", "A", "F", "G", "K", "M"}
    if "spectral_type" in df.columns:
        def extract_class(sp):
            if pd.isna(sp):
                return pd.NA
            s = str(sp).strip()
            if s and s[0] in valid_classes:
                return s[0]
            return pd.NA
        df["spectral_class"] = df["spectral_type"].apply(extract_class)

    # is_variable: True if variable_name is not null
    if "variable_name" in df.columns:
        df["is_variable"] = df["variable_name"].notna()
    else:
        df["is_variable"] = False

    # is_multiple: True if multiplicity_flag is not null/empty
    if "multiplicity_flag" in df.columns:
        df["is_multiple"] = df["multiplicity_flag"].notna()
    else:
        df["is_multiple"] = False

    # Sort by HR number
    if "hr_number" in df.columns:
        df = df.sort_values("hr_number").reset_index(drop=True)

    check_dataset(df, "bright-stars", min_rows=8000,
                  expected_columns=["ra_deg", "dec_deg", "v_mag"],
                  critical_columns=["ra_deg", "dec_deg", "v_mag"])

    # Stats for README
    n = len(df)
    brightest = df["v_mag"].min() if "v_mag" in df.columns else None
    faintest = df["v_mag"].max() if "v_mag" in df.columns else None
    n_variable = int(df["is_variable"].sum())
    n_multiple = int(df["is_multiple"].sum())

    # Spectral class breakdown
    class_counts = {}
    if "spectral_class" in df.columns:
        vc = df["spectral_class"].value_counts()
        for c in ["O", "B", "A", "F", "G", "K", "M"]:
            class_counts[c] = int(vc.get(c, 0))

    class_lines = "\n".join(
        f"- **{c}**: {class_counts.get(c, 0):,}" for c in ["O", "B", "A", "F", "G", "K", "M"]
    )

    print(f"  Brightest: {brightest}, Faintest: {faintest}")
    print(f"  Variables: {n_variable:,}, Multiples: {n_multiple:,}")
    for c in ["O", "B", "A", "F", "G", "K", "M"]:
        print(f"  {c}: {class_counts.get(c, 0):,}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "bright_stars.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        banner_file = download_banner("bright-stars", tmp)
        banner_md = banner_markdown("bright-stars", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Bright Star Catalogue (BSC5)"
language:
  - en
description: >-
  Bright Star Catalogue (BSC5, 5th Revised Edition) — {n:,} naked-eye stars
  (magnitude <= 6.5) with UBVRI photometry, MK spectral types, proper motions,
  parallax, radial and rotational velocities, and multiplicity information.
  Sourced via VizieR V/50.
size_categories:
  - 1K<n<10K
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - stars
  - bright-stars
  - stellar
  - naked-eye
  - bsc5
  - yale
  - astronomy
  - open-data
  - tabular-data
  - parquet
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/bright_stars.parquet
    default: true
---

# Bright Star Catalogue (BSC5)
{banner_md}
*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

The Bright Star Catalogue (BSC5, 5th Revised Edition) containing **{n:,}** naked-eye stars
brighter than visual magnitude ~6.5 with UBVRI photometry, MK spectral types, proper motions,
radial and rotational velocities, and multiplicity information.

## Dataset description

The Bright Star Catalogue (Hoffleit & Warren, 1991) is THE standard reference for naked-eye
stars. Originally compiled at Yale University Observatory, the 5th Revised Edition contains
9,110 entries covering every star visible to the unaided eye from the entire sky. It includes
Harvard Revised (HR) photometry numbers, Henry Draper (HD) numbers, UBVRI broadband photometry,
MK spectral classification, proper motions, trigonometric parallaxes, radial velocities,
rotational velocities (v sin i), and flags for variability and multiplicity.

The BSC5 occupies a unique niche among stellar catalogs: it is magnitude-complete to V ~ 6.5, meaning it contains essentially every star the human eye can see under ideal conditions. This completeness makes it invaluable for statistical studies of the solar neighborhood's stellar population. The catalog spans the full range of spectral types from hot O and B stars to cool M giants, including main-sequence dwarfs, subgiants, giants, supergiants, and white dwarfs. Its UBVRI photometry enables construction of color-magnitude and color-color diagrams, while MK spectral classifications provide independent temperature and luminosity class determinations. The rotational velocity (v sin i) data, available for a large fraction of entries, supports studies of stellar angular momentum evolution across spectral types.

Despite its relatively modest size compared to modern survey catalogs containing billions of stars, the BSC5 remains widely used in observational astronomy, spacecraft attitude determination, planetarium software, and educational contexts. Many entries carry common star names (Sirius, Betelgeuse, Vega) alongside their HR and HD numbers, bridging traditional naked-eye astronomy with the modern catalog system. The multiplicity and variability flags identify binary and multiple star systems as well as known variable stars, making the catalog a practical starting point for targeted follow-up observations. For bright-star science — where saturation limits modern CCD surveys — the BSC5 photometry and spectroscopy remain authoritative reference data.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `hr_number` | int64 | Harvard Revised (Yale BSC) catalog number — the primary identifier for this catalog, stable since 1908; range 1–9110 |
| `name` | string | Traditional common name (e.g. "Sirius", "Vega", "Rigel"); null for the ~90% of entries without an established proper name |
| `hd_number` | int64 | Henry Draper Catalogue number; enables cross-matching with spectroscopic and photometric surveys that use HD identifiers; null if not assigned |
| `ra_deg` | float64 | Right ascension in the ICRS J2000.0 frame, decimal degrees (0–360) |
| `dec_deg` | float64 | Declination in the ICRS J2000.0 frame, decimal degrees (−90 to +90) |
| `v_mag` | float64 | Johnson V-band visual magnitude; brightest entries: Sirius −1.46, Canopus −0.72; catalog is complete to V ≈ 6.5 (naked-eye limit) |
| `b_v_color` | float64 | Johnson B−V color index; proxy for surface temperature: −0.3 = hot blue O/B star, 0.0 = white A-star (Vega), 0.65 = solar-type G2V, 1.6 = cool red M-giant; null if B photometry unavailable |
| `u_b_color` | float64 | Johnson U−B color index; sensitive to UV excess from hot stars and emission features; null if U photometry unavailable |
| `r_i_color` | float64 | Cousins R−I color index; useful for cool-star classification and interstellar reddening estimates; null if R/I photometry unavailable |
| `spectral_type` | string | Full MK spectral classification (e.g. "A1V" = Sirius, "M2Ib" = Betelgeuse); letter codes temperature class (O–M, hottest to coolest), Roman numeral codes luminosity class (I = supergiant, III = giant, V = main-sequence dwarf) |
| `spectral_class` | string | Single temperature-class letter extracted from `spectral_type` (O, B, A, F, G, K, M); useful for population statistics and color grouping |
| `pm_ra_arcsec_yr` | float64 | Proper motion in right ascension (arcsec/yr, includes cos δ factor); null for very distant stars where motion is below measurement threshold |
| `pm_dec_arcsec_yr` | float64 | Proper motion in declination (arcsec/yr); null if not measured |
| `radial_velocity_kms` | float64 | Line-of-sight velocity relative to the Solar System barycenter (km/s); positive = receding; null if no spectroscopic measurement available |
| `rotational_velocity_kms` | float64 | Projected equatorial rotation speed v sin i (km/s); reflects true spin speed modulated by unknown inclination angle i; null for most cool stars and giants |
| `parallax_mas` | float64 | Trigonometric parallax in milliarcseconds (pre-Hipparcos ground-based values); distance_pc ≈ 1000 / parallax_mas; null for distant supergiants where ground-based parallax is unreliable |
| `variable_name` | string | Variable star designation (e.g. "alpha Ori" for Betelgeuse); non-null only for confirmed or suspected variables |
| `is_variable` | bool | True if the star is listed as a known or suspected variable in BSC5; derived from `variable_name` being present |
| `multiplicity_flag` | string | One or more single-letter codes from the BSC multiplicity catalog (e.g. "D" = double, "V" = visual binary, "S" = spectroscopic binary); null if no multiplicity noted |
| `is_multiple` | bool | True if `multiplicity_flag` is non-null, indicating the star is in a binary or higher-order multiple system |

## Quick stats

- **{n:,}** stars total
- Brightest: **{brightest:.2f}** mag / Faintest: **{faintest:.2f}** mag
- **{n_variable:,}** variable stars, **{n_multiple:,}** multiple systems

### By spectral class

{class_lines}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/bright-star-catalog", split="train")
df = ds.to_pandas()

# Brightest stars
bright = df.nsmallest(20, "v_mag")
print(bright[["hr_number", "name", "v_mag", "spectral_type"]])

# Color-magnitude diagram
import matplotlib.pyplot as plt
valid = df.dropna(subset=["b_v_color", "v_mag"])
plt.scatter(valid["b_v_color"], valid["v_mag"], s=1, alpha=0.5)
plt.gca().invert_yaxis()
plt.xlabel("B-V Color Index")
plt.ylabel("V Magnitude")
plt.title("Bright Star Catalogue: Color-Magnitude Diagram")

# Spectral class distribution
df["spectral_class"].value_counts().sort_index().plot(kind="bar")
plt.title("Stars by Spectral Class")
```

## Data source

Hoffleit, D. & Warren, W.H. Jr. (1991), "The Bright Star Catalogue, 5th Revised Ed.",
Yale University Observatory. Accessed via
[VizieR V/50](https://vizier.cds.unistra.fr/viz-bin/VizieR-3?-source=V/50/catalog),
CDS Strasbourg.

## Related datasets

- [wolf-rayet-stars](https://huggingface.co/datasets/juliensimon/wolf-rayet-stars) -- Wolf-Rayet Star Catalogue
- [brown-dwarf-catalog](https://huggingface.co/datasets/juliensimon/brown-dwarf-catalog) -- Brown Dwarf Catalog
- [hipparcos-catalog](https://huggingface.co/datasets/juliensimon/hipparcos-catalog) -- Hipparcos Star Catalog

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/bright-star-catalog) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{bright_star_catalog,
  author = {{Simon, Julien}},
  title = {{Bright Star Catalogue (BSC5)}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/bright-star-catalog}},
  note = {{Based on Bright Star Catalogue 5th Rev. Ed. (Hoffleit & Warren 1991) via VizieR V/50}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update bright star catalog: {n:,} stars"
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
