#!/usr/bin/env python3
"""Fetch RC3 galaxy morphology catalog from VizieR and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from validate import check_dataset
from vizier_tap import vizier_query

HF_REPO = "juliensimon/rc3-galaxy-morphology"

ADQL = """SELECT * FROM "VII/155/rc3" """

RENAME = {
    "RA2000": "ra_deg",
    "RA_ICRS": "ra_deg",
    "RAJ2000": "ra_deg",
    "_RA": "ra_deg",
    "DE2000": "dec_deg",
    "DE_ICRS": "dec_deg",
    "DEJ2000": "dec_deg",
    "_DE": "dec_deg",
    "name": "name",
    "Name": "name",
    "PGC": "pgc_number",
    "T": "morphological_type_t",
    "LC": "luminosity_class",
    "SB": "surface_brightness",
    "BT": "bt_magnitude",
    "e_BT": "e_bt_magnitude",
    "B-V": "b_v_color",
    "U-B": "u_b_color",
    "HRV": "helio_radial_velocity",
    "e_HRV": "e_helio_radial_velocity",
    "logD25": "log_diameter_d25",
    "logR25": "log_axis_ratio_r25",
    "MType": "morphological_type",
}

NUMERIC_COLS = [
    "ra_deg", "dec_deg", "morphological_type_t", "luminosity_class",
    "surface_brightness", "bt_magnitude", "e_bt_magnitude",
    "b_v_color", "u_b_color",
    "helio_radial_velocity", "e_helio_radial_velocity",
    "log_diameter_d25", "log_axis_ratio_r25",
]


def main():
    print("Fetching RC3 galaxy catalog from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} raw rows")

    # Rename columns
    df = df.rename(columns=RENAME)

    # Type conversions
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Clean string columns
    for col in ["name", "morphological_type"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
            )

    # Stats
    n_total = len(df)
    n_with_type = int(df["morphological_type"].notna().sum()) if "morphological_type" in df.columns else 0
    n_with_velocity = int(df["helio_radial_velocity"].notna().sum()) if "helio_radial_velocity" in df.columns else 0
    n_with_mag = int(df["bt_magnitude"].notna().sum()) if "bt_magnitude" in df.columns else 0
    if "morphological_type_t" in df.columns:
        t_min = df["morphological_type_t"].min()
        t_max = df["morphological_type_t"].max()
    else:
        t_min, t_max = 0, 0

    # Validate
    check_dataset(
        df,
        "rc3",
        min_rows=20_000,
        expected_columns=["ra_deg", "dec_deg"],
        critical_columns=["ra_deg", "dec_deg"],
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "rc3_galaxies.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Third Reference Catalogue of Bright Galaxies (RC3)"
language:
  - en
description: "RC3 catalog of {n_total:,} bright galaxies with morphological classifications, photometry, and redshifts."
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - galaxy
  - morphology
  - rc3
  - hubble-type
  - astronomy
  - open-data
size_categories:
  - 10K<n<100K
---

# Third Reference Catalogue of Bright Galaxies (RC3)

The Third Reference Catalogue of Bright Galaxies (RC3), the classic comprehensive catalog of
**{n_total:,}** bright galaxies with Hubble-type morphological classifications, photometry,
diameters, and radial velocities.

## Dataset description

RC3 is the definitive catalog of bright galaxies, compiled by de Vaucouleurs, de Vaucouleurs,
Corwin, Buta, Paturel, and Fouque (1991). It provides homogeneous morphological classifications
on the revised Hubble system (numerical type T from -5 for ellipticals to +10 for irregulars),
total B magnitudes, colors, diameters, axis ratios, luminosity classes, surface brightnesses,
and heliocentric radial velocities. RC3 remains the standard reference for galaxy morphology
and is widely used for training galaxy classification models.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `name` | string | Galaxy name/designation |
| `pgc_number` | string | PGC (Principal Galaxies Catalogue) number |
| `ra_deg` | float64 | Right ascension J2000 (degrees) |
| `dec_deg` | float64 | Declination J2000 (degrees) |
| `morphological_type` | string | Morphological type string (e.g. "SBbc", "E3") |
| `morphological_type_t` | float64 | Numerical Hubble type T (-5=E to +10=Irr) |
| `luminosity_class` | float64 | Luminosity class (van den Bergh system) |
| `surface_brightness` | float64 | Mean surface brightness |
| `bt_magnitude` | float64 | Total apparent B magnitude |
| `e_bt_magnitude` | float64 | Error on B magnitude |
| `b_v_color` | float64 | B-V color index |
| `u_b_color` | float64 | U-B color index |
| `helio_radial_velocity` | float64 | Heliocentric radial velocity (km/s) |
| `e_helio_radial_velocity` | float64 | Error on radial velocity (km/s) |
| `log_diameter_d25` | float64 | Log of isophotal diameter D25 (0.1 arcmin) |
| `log_axis_ratio_r25` | float64 | Log of axis ratio at D25 isophote |

## Quick stats

- **{n_total:,}** bright galaxies
- **{n_with_type:,}** with morphological type
- **{n_with_velocity:,}** with radial velocity
- **{n_with_mag:,}** with B magnitude
- Hubble type T range: {t_min:.0f} to {t_max:.0f}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/rc3-galaxy-morphology", split="train")
df = ds.to_pandas()

# Hubble type distribution
import matplotlib.pyplot as plt
df["morphological_type_t"].dropna().hist(bins=30)
plt.xlabel("Hubble Type T (-5=E, 0=S0/a, 5=Sc, 10=Irr)")
plt.ylabel("Count")
plt.title("RC3 Galaxy Morphological Type Distribution")
plt.show()

# Color-magnitude diagram
valid = df.dropna(subset=["bt_magnitude", "b_v_color"])
plt.scatter(valid["b_v_color"], valid["bt_magnitude"], s=1, alpha=0.3)
plt.gca().invert_yaxis()
plt.xlabel("B-V Color")
plt.ylabel("B magnitude")
plt.title("RC3 Color-Magnitude Diagram")
plt.show()

# Ellipticals vs spirals
ellipticals = df[df["morphological_type_t"] <= -3]
spirals = df[(df["morphological_type_t"] >= 1) & (df["morphological_type_t"] <= 9)]
print(f"Ellipticals (T <= -3): {{len(ellipticals):,}}")
print(f"Spirals (1 <= T <= 9): {{len(spirals):,}}")
```

## Data source

de Vaucouleurs, G., de Vaucouleurs, A., Corwin, H.G. Jr., Buta, R.J., Paturel, G.,
and Fouque, P. (1991), *Third Reference Catalogue of Bright Galaxies (RC3).*
Springer-Verlag, New York. Via [VizieR](https://vizier.cds.unistra.fr/) CDS Strasbourg (VII/155).

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Citation

```bibtex
@dataset{{rc3_galaxy_morphology,
  author = {{Simon, Julien}},
  title = {{Third Reference Catalogue of Bright Galaxies (RC3)}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/rc3-galaxy-morphology}},
  note = {{Based on de Vaucouleurs et al. (1991) via VizieR CDS Strasbourg}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update RC3 galaxy morphology: {n_total:,} galaxies"
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
