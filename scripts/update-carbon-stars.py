#!/usr/bin/env python3
"""Fetch Galactic Carbon Stars (GCCS) catalog from VizieR and upload to HF.

Source: Alksnis, A. et al. (2001), "A catalogue of Galactic carbon stars",
Baltic Astronomy, 10, 1. VizieR catalog: III/227.
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from validate import check_dataset
from vizier_tap import vizier_query


HF_REPO = "juliensimon/carbon-stars"
ADQL = 'SELECT * FROM "III/227/catalog"'


def main():
    print("Fetching Galactic Carbon Stars (GCCS) from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} carbon stars fetched")

    # Drop VizieR internal columns
    for col in ["recno", "SimbadName", "More"]:
        if col in df.columns:
            df = df.drop(columns=[col])

    # Rename columns — generous dict with VizieR variants
    rename = {
        "RA_ICRS": "ra_deg",
        "RAJ2000": "ra_deg",
        "_RA": "ra_deg",
        "DE_ICRS": "dec_deg",
        "DEJ2000": "dec_deg",
        "_DE": "dec_deg",
        "GCCS": "gccs_number",
        "Seq": "gccs_number",
        "GCGCS": "gccs_number",
        "Name": "name",
        "ID": "name",
        "SpType": "spectral_type",
        "SpT": "spectral_type",
        "Vmag": "v_mag",
        "Imag": "i_mag",
        "Jmag": "j_mag",
        "Hmag": "h_mag",
        "Kmag": "k_mag",
        "Ksmag": "k_mag",
        "pmRA": "pm_ra_mas_yr",
        "pmDE": "pm_dec_mas_yr",
        "Type": "carbon_type",
        "CType": "carbon_type",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

    # Snake_case remaining columns not yet renamed
    def to_snake(name):
        s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
        s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
        return s.lower().replace("-", "_").replace(" ", "_")

    df.columns = [to_snake(c) if c not in rename.values() else c for c in df.columns]

    # Numeric conversion
    numeric_cols = [
        "ra_deg", "dec_deg", "v_mag", "i_mag", "j_mag", "h_mag", "k_mag",
        "pm_ra_mas_yr", "pm_dec_mas_yr",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Clean string columns
    for col in ["name", "spectral_type", "carbon_type"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
            )

    # Derived: broad carbon classification from carbon_type or spectral_type
    def classify_carbon(row):
        for field in ["carbon_type", "spectral_type"]:
            val = row.get(field)
            if pd.isna(val):
                continue
            val = str(val).strip()
            for prefix in ["C-Hd", "C-H", "C-J", "C-N", "C-R"]:
                if prefix in val:
                    return prefix
        return pd.NA

    df["carbon_class"] = df.apply(classify_carbon, axis=1)

    # Derived: has IR photometry
    has_j = df["j_mag"].notna() if "j_mag" in df.columns else pd.Series(False, index=df.index)
    has_k = df["k_mag"].notna() if "k_mag" in df.columns else pd.Series(False, index=df.index)
    df["has_ir_photometry"] = has_j | has_k

    # Sort by GCCS number if available
    if "gccs_number" in df.columns:
        df["gccs_number"] = pd.to_numeric(df["gccs_number"], errors="coerce")
        df = df.sort_values("gccs_number").reset_index(drop=True)
    else:
        df = df.sort_values("ra_deg").reset_index(drop=True)

    # Validate
    check_dataset(df, "carbon-stars", min_rows=5000,
        expected_columns=["ra_deg", "dec_deg"],
        critical_columns=["ra_deg", "dec_deg"])

    # Stats for README
    n_total = len(df)

    type_counts = df["carbon_class"].value_counts()
    type_breakdown = ", ".join(f"**{int(v):,}** {k}" for k, v in type_counts.items())
    if not type_breakdown:
        type_breakdown = "classification not available"

    n_with_ir = int(df["has_ir_photometry"].sum())

    v_valid = df["v_mag"].dropna()
    v_range = f"{v_valid.min():.1f}–{v_valid.max():.1f}" if len(v_valid) > 0 else "N/A"

    k_valid = df["k_mag"].dropna() if "k_mag" in df.columns else pd.Series(dtype=float)
    k_range = f"{k_valid.min():.1f}–{k_valid.max():.1f}" if len(k_valid) > 0 else "N/A"

    print(f"  {n_total:,} carbon stars total")
    print(f"  Type breakdown: {type_breakdown}")
    print(f"  {n_with_ir:,} with IR photometry")
    print(f"  V mag range: {v_range}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "carbon_stars.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Galactic Carbon Stars (GCCS)"
language:
  - en
description: "Catalog of {n_total:,} Galactic carbon stars from the General Catalogue of Galactic Cool Carbon Stars (GCCS, 3rd Edition, Alksnis et al. 2001). Includes positions, magnitudes, spectral types, and identifications for carbon-rich AGB stars. Sourced via VizieR CDS Strasbourg."
task_categories:
  - tabular-classification
tags:
  - space
  - stars
  - carbon-stars
  - agb
  - evolved-stars
  - spectroscopy
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
        path: data/carbon_stars.parquet
    default: true
---

# Galactic Carbon Stars (GCCS)

*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

Catalog of **{n_total:,}** Galactic carbon stars from the General Catalogue of Galactic Cool
Carbon Stars (GCCS, 3rd Edition). Carbon stars are evolved red giant branch / asymptotic giant
branch (AGB) stars whose atmospheres are enriched in carbon from internal nucleosynthesis
(dredge-up episodes). Their distinctive molecular bands (C2, CN, CH) make them important
tracers of stellar evolution and galactic structure.

## Dataset description

The Stephenson GCCS (3rd Edition, Alksnis et al. 2001) is the definitive reference catalog of
Galactic cool carbon stars, containing 6,891 entries with equatorial positions, visual and
infrared magnitudes, spectral types, and cross-identifications. Carbon stars are classified
into several subtypes based on their spectra:

- **C-N** — classical (cool) carbon stars on the AGB, the most common type
- **C-R** — warm carbon giants, possibly formed through binary mergers
- **C-J** — carbon stars with strong 13C isotope features
- **C-H** — high-velocity (halo) carbon stars, often CH stars
- **C-Hd** — hydrogen-deficient carbon stars (R CrB type)

Carbon stars occupy a pivotal role in stellar evolution and galactic chemical enrichment. The defining characteristic — a C/O ratio greater than unity in the stellar atmosphere — arises primarily through the third dredge-up process on the asymptotic giant branch (AGB), where convective mixing carries freshly synthesized carbon-12 from the helium-burning shell to the surface. This nucleosynthetic pathway is one of the principal channels by which carbon, a key element for life, is returned to the interstellar medium. AGB carbon stars also produce significant quantities of s-process elements (barium, strontium, zirconium) through slow neutron capture, making them important contributors to the chemical evolution of galaxies.

As luminous infrared sources (M_bol typically -3 to -6), carbon stars are detectable at large distances and serve as excellent tracers of intermediate-age stellar populations (1-4 Gyr) and Galactic structure. Their strong molecular absorption bands — particularly C_2, CN, and SiC — give them extremely red colors, making them easy to identify photometrically. In external galaxies, carbon star luminosity functions have been used as distance indicators. Within the Milky Way, the spatial distribution of carbon stars maps the disk and halo populations: the cool C-N giants trace the thin and thick disk, while the C-H and C-R subtypes include high-velocity halo members that are likely the products of mass transfer in binary systems rather than intrinsic dredge-up. The catalog's spectral subtype classifications thus encode both evolutionary state and population membership.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `gccs_number` | int | GCCS catalog sequence number |
| `name` | string | Star identification / name |
| `ra_deg` | float64 | Right ascension (degrees) |
| `dec_deg` | float64 | Declination (degrees) |
| `spectral_type` | string | MK spectral type |
| `carbon_type` | string | Carbon star type classification |
| `carbon_class` | string | Broad carbon class (C-N, C-R, C-J, C-H, C-Hd) |
| `v_mag` | float64 | Visual (V-band) magnitude |
| `i_mag` | float64 | I-band magnitude |
| `j_mag` | float64 | J-band magnitude (2MASS) |
| `h_mag` | float64 | H-band magnitude (2MASS) |
| `k_mag` | float64 | K-band magnitude (2MASS) |
| `pm_ra_mas_yr` | float64 | Proper motion in RA (mas/yr) |
| `pm_dec_mas_yr` | float64 | Proper motion in Dec (mas/yr) |
| `has_ir_photometry` | bool | True if J or K magnitude available |

## Quick stats

- **{n_total:,}** Galactic carbon stars
- Type breakdown: {type_breakdown}
- **{n_with_ir:,}** with infrared photometry (J or K band)
- V magnitude range: {v_range}
- K magnitude range: {k_range}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/carbon-stars", split="train")
df = ds.to_pandas()

# Carbon type distribution
print(df["carbon_class"].value_counts())

# Stars with IR photometry
ir = df[df["has_ir_photometry"]]
print(f"{{len(ir):,}} stars with IR photometry")

# Sky distribution
import matplotlib.pyplot as plt
plt.scatter(df["ra_deg"], df["dec_deg"], s=0.5, alpha=0.3)
plt.xlabel("RA (deg)")
plt.ylabel("Dec (deg)")
plt.title("Galactic Carbon Stars — Sky Distribution")
plt.gca().invert_xaxis()
```

## Data source

Alksnis, A., Balklavs, A., Dzervitis, U., Eglitis, I., Paupers, O. & Pundure, I. (2001),
"A catalogue of Galactic carbon stars", *Baltic Astronomy*, 10, 1.
Accessed via [VizieR](https://vizier.cds.unistra.fr/) (III/227), CDS Strasbourg.

## Related datasets

- [wolf-rayet-stars](https://huggingface.co/datasets/juliensimon/wolf-rayet-stars) — Galactic Wolf-Rayet Stars
- [brown-dwarf-catalog](https://huggingface.co/datasets/juliensimon/brown-dwarf-catalog) — Brown Dwarf Catalog
- [gcvs-variable-stars](https://huggingface.co/datasets/juliensimon/gcvs-variable-stars) — General Catalogue of Variable Stars

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/carbon-stars) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{carbon_stars,
  author = {{Simon, Julien}},
  title = {{Galactic Carbon Stars (GCCS)}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/carbon-stars}},
  note = {{Based on Alksnis et al. (2001), Baltic Astronomy 10, 1 — VizieR III/227}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update Galactic Carbon Stars (GCCS): {n_total:,} stars"
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
