#!/usr/bin/env python3
"""Fetch SsODNet asteroid physical properties (ssoBFT) from IMCCE and upload to HF.

Source: IMCCE SsODNet — Solar System Open Database Network
        Best-estimates flat table (ssoBFT) for asteroids and dwarf planets.
Static dataset (uploaded once, no workflow).
"""

import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import requests

from validate import check_dataset

# ssoBFT bulk parquet — ~489 MB, updated regularly by IMCCE
PARQUET_URL = "https://ssp.imcce.fr/data/ssoBFT-latest_Asteroid.parquet"
HF_REPO = "juliensimon/ssodnet-asteroid-properties"
MIN_ROWS = 500_000


def main():
    # ── Download ──────────────────────────────────────────────────────────
    print("Downloading ssoBFT asteroid parquet from IMCCE...")
    resp = requests.get(PARQUET_URL, timeout=600, stream=True)
    resp.raise_for_status()

    # Stream to a temp file (large download)
    tmp_src = Path(tempfile.mktemp(suffix=".parquet"))
    size = 0
    with open(tmp_src, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8 * 1024 * 1024):
            f.write(chunk)
            size += len(chunk)
    print(f"  Downloaded {size / 1024 / 1024:.0f} MB")

    # ── Read and select columns ───────────────────────────────────────────
    # The ssoBFT has 200+ columns with dots in names. We select the most
    # useful physical + identity + orbital summary columns.
    print("Reading parquet and selecting columns...")
    src = pq.ParquetFile(tmp_src)
    all_cols = src.schema.names
    print(f"  Source has {src.metadata.num_rows:,} rows, {len(all_cols)} columns")

    # Define the columns we want (using the dot-separated ssoBFT naming)
    WANTED = {
        # Identity
        "sso_id": "sso_id",
        "sso_number": "sso_number",
        "sso_name": "sso_name",
        "sso_type": "sso_type",
        "sso_class": "sso_class",
        # Orbital summary
        "orbital_elements.semi_major_axis.value": "semi_major_axis_au",
        "orbital_elements.eccentricity.value": "eccentricity",
        "orbital_elements.inclination.value": "inclination_deg",
        "orbital_elements.orbital_period.value": "orbital_period_yr",
        "orbital_elements.periapsis_distance.value": "periapsis_distance_au",
        "orbital_elements.apoapsis_distance.value": "apoapsis_distance_au",
        # Tisserand parameter (Jupiter) — useful for classification
        "tisserand_parameter.Jupiter.value": "tisserand_jupiter",
        # Family
        "family.family_number": "family_number",
        "family.family_name": "family_name",
        "family.family_status": "family_status",
        # Physical properties
        "absolute_magnitude.value": "absolute_magnitude",
        "absolute_magnitude.error.min": "absolute_magnitude_err_min",
        "absolute_magnitude.error.max": "absolute_magnitude_err_max",
        "diameter.value": "diameter_km",
        "diameter.error.min": "diameter_err_min_km",
        "diameter.error.max": "diameter_err_max_km",
        "albedo.value": "albedo",
        "albedo.error.min": "albedo_err_min",
        "albedo.error.max": "albedo_err_max",
        "mass.value": "mass_kg",
        "mass.error.min": "mass_err_min_kg",
        "mass.error.max": "mass_err_max_kg",
        "density.value": "density_g_cm3",
        "density.error.min": "density_err_min_g_cm3",
        "density.error.max": "density_err_max_g_cm3",
        "taxonomy.class": "taxonomy_class",
        "taxonomy.complex": "taxonomy_complex",
        "taxonomy.scheme": "taxonomy_scheme",
        "taxonomy.waverange": "taxonomy_waverange",
        "taxonomy.technique": "taxonomy_technique",
        "thermal_inertia.value": "thermal_inertia",
        "thermal_inertia.error.min": "thermal_inertia_err_min",
        "thermal_inertia.error.max": "thermal_inertia_err_max",
        # Spin / rotation
        "spins.1.period.value": "rotation_period_h",
        "spins.1.period.error.min": "rotation_period_err_min_h",
        "spins.1.period.error.max": "rotation_period_err_max_h",
        # MOID (Earth) — useful for NEO analysis
        "moid.EMB.value": "moid_earth_au",
    }

    # Filter to columns that actually exist in the file
    available = {k: v for k, v in WANTED.items() if k in all_cols}
    missing_cols = set(WANTED) - set(available)
    if missing_cols:
        print(f"  Note: {len(missing_cols)} requested columns not in source: "
              f"{sorted(missing_cols)[:5]}...")

    print(f"  Selecting {len(available)} columns...")
    df = pd.read_parquet(tmp_src, columns=list(available.keys()))
    df = df.rename(columns=available)

    # Clean up temp source file
    tmp_src.unlink(missing_ok=True)

    print(f"  Loaded {len(df):,} rows, {len(df.columns)} columns")

    # ── Type coercion ─────────────────────────────────────────────────────
    # sso_number to nullable int
    if "sso_number" in df.columns:
        df["sso_number"] = pd.to_numeric(df["sso_number"], errors="coerce").astype("Int64")
    if "family_number" in df.columns:
        df["family_number"] = pd.to_numeric(df["family_number"], errors="coerce").astype("Int64")

    # Ensure float columns are float64
    float_cols = [
        "semi_major_axis_au", "eccentricity", "inclination_deg",
        "orbital_period_yr", "periapsis_distance_au", "apoapsis_distance_au",
        "tisserand_jupiter",
        "absolute_magnitude", "absolute_magnitude_err_min", "absolute_magnitude_err_max",
        "diameter_km", "diameter_err_min_km", "diameter_err_max_km",
        "albedo", "albedo_err_min", "albedo_err_max",
        "mass_kg", "mass_err_min_kg", "mass_err_max_kg",
        "density_g_cm3", "density_err_min_g_cm3", "density_err_max_g_cm3",
        "thermal_inertia", "thermal_inertia_err_min", "thermal_inertia_err_max",
        "rotation_period_h", "rotation_period_err_min_h", "rotation_period_err_max_h",
        "moid_earth_au",
    ]
    for col in float_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Strip whitespace from string columns
    str_cols = [
        "sso_id", "sso_name", "sso_type", "sso_class",
        "family_name", "family_status",
        "taxonomy_class", "taxonomy_complex", "taxonomy_scheme",
        "taxonomy_waverange", "taxonomy_technique",
    ]
    for col in str_cols:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace({"nan": None, "": None, "None": None})

    # ── Stats ─────────────────────────────────────────────────────────────
    n_total = len(df)
    n_with_diameter = int(df["diameter_km"].notna().sum()) if "diameter_km" in df.columns else 0
    n_with_albedo = int(df["albedo"].notna().sum()) if "albedo" in df.columns else 0
    n_with_taxonomy = int(df["taxonomy_class"].notna().sum()) if "taxonomy_class" in df.columns else 0
    n_with_mass = int(df["mass_kg"].notna().sum()) if "mass_kg" in df.columns else 0
    n_with_density = int(df["density_g_cm3"].notna().sum()) if "density_g_cm3" in df.columns else 0
    n_with_rotation = int(df["rotation_period_h"].notna().sum()) if "rotation_period_h" in df.columns else 0
    n_families = int(df["family_name"].notna().sum()) if "family_name" in df.columns else 0

    # Class distribution
    class_counts = {}
    if "sso_class" in df.columns:
        class_counts = df["sso_class"].value_counts().head(10).to_dict()

    print(f"\n  {n_total:,} asteroids total")
    print(f"  {n_with_diameter:,} with diameter")
    print(f"  {n_with_albedo:,} with albedo")
    print(f"  {n_with_taxonomy:,} with taxonomy")
    print(f"  {n_with_mass:,} with mass")
    print(f"  {n_with_density:,} with density")
    print(f"  {n_with_rotation:,} with rotation period")
    print(f"  {n_families:,} with family assignment")
    if class_counts:
        print("  Top classes:")
        for cls, cnt in class_counts.items():
            print(f"    {cls}: {cnt:,}")

    # ── Validate ──────────────────────────────────────────────────────────
    check_dataset(
        df,
        dataset_name="ssodnet",
        min_rows=MIN_ROWS,
        expected_columns=[
            "sso_id", "sso_number", "sso_name", "sso_class",
            "semi_major_axis_au", "eccentricity", "inclination_deg",
            "absolute_magnitude", "diameter_km", "albedo",
        ],
        critical_columns=["sso_id", "semi_major_axis_au", "absolute_magnitude"],
        max_null_pct=0.10,
    )

    # ── Write parquet + README ────────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "ssodnet_asteroid_properties.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"\n  {size_mb:.1f} MB parquet written")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "SsODNet Asteroid Physical Properties"
language:
  - en
description: "Physical and orbital properties for {n_total:,} asteroids from IMCCE SsODNet — diameters, albedos, taxonomy, masses, densities, and rotation periods compiled from published literature."
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - asteroids
  - physical-properties
  - imcce
  - orbital-mechanics
  - open-data
  - tabular-data
size_categories:
  - 1M<n<10M
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/ssodnet_asteroid_properties.parquet
    default: true
---

# SsODNet Asteroid Physical Properties

*Part of the [Orbital Mechanics Datasets](https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994) collection on Hugging Face.*

Physical and dynamical properties of **{n_total:,}** asteroids and dwarf planets from the
IMCCE (Paris Observatory) Solar System Open Database Network (SsODNet). This is the most
comprehensive asteroid characterization catalog available, compiling best estimates from
thousands of published studies.

## Dataset description

SsODNet aggregates physical property measurements from the astronomical literature into
a single, curated "best estimates" flat table (ssoBFT). For each asteroid, IMCCE selects
the most reliable published value for each property using a transparent ranking scheme.
Properties include diameters, albedos, taxonomic classifications, masses, densities,
rotation periods, and thermal inertia — alongside orbital elements and dynamical family
memberships.

The fill factor varies by property: orbital elements are available for nearly all objects,
while physical measurements like mass ({n_with_mass:,} objects) and density
({n_with_density:,} objects) are known for far fewer.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `sso_id` | string | SsODNet unique identifier |
| `sso_number` | Int64 | IAU asteroid catalog number (null for unnumbered) |
| `sso_name` | string | IAU name (null if unnamed) |
| `sso_type` | string | Object type (Asteroid, Dwarf Planet, etc.) |
| `sso_class` | string | Dynamical class (MB, NEA, Trojan, Centaur, KBO, etc.) |
| `semi_major_axis_au` | float64 | Orbital semi-major axis (AU) |
| `eccentricity` | float64 | Orbital eccentricity |
| `inclination_deg` | float64 | Orbital inclination (degrees) |
| `orbital_period_yr` | float64 | Orbital period (years) |
| `periapsis_distance_au` | float64 | Perihelion distance (AU) |
| `apoapsis_distance_au` | float64 | Aphelion distance (AU) |
| `tisserand_jupiter` | float64 | Tisserand parameter w.r.t. Jupiter |
| `family_number` | Int64 | Dynamical family number |
| `family_name` | string | Dynamical family name |
| `family_status` | string | Family membership status |
| `absolute_magnitude` | float64 | Absolute magnitude H (best estimate) |
| `absolute_magnitude_err_min` | float64 | H magnitude lower error bound |
| `absolute_magnitude_err_max` | float64 | H magnitude upper error bound |
| `diameter_km` | float64 | Effective diameter (km, best estimate) |
| `diameter_err_min_km` | float64 | Diameter lower error bound (km) |
| `diameter_err_max_km` | float64 | Diameter upper error bound (km) |
| `albedo` | float64 | Geometric albedo (best estimate) |
| `albedo_err_min` | float64 | Albedo lower error bound |
| `albedo_err_max` | float64 | Albedo upper error bound |
| `mass_kg` | float64 | Mass (kg, best estimate) |
| `mass_err_min_kg` | float64 | Mass lower error bound (kg) |
| `mass_err_max_kg` | float64 | Mass upper error bound (kg) |
| `density_g_cm3` | float64 | Bulk density (g/cm3, best estimate) |
| `density_err_min_g_cm3` | float64 | Density lower error bound (g/cm3) |
| `density_err_max_g_cm3` | float64 | Density upper error bound (g/cm3) |
| `taxonomy_class` | string | Taxonomic class (e.g., S, C, X, V) |
| `taxonomy_complex` | string | Taxonomic complex (e.g., S-complex, C-complex) |
| `taxonomy_scheme` | string | Classification scheme (Bus-DeMeo, Tholen, etc.) |
| `taxonomy_waverange` | string | Wavelength range used for classification |
| `taxonomy_technique` | string | Technique used for classification |
| `thermal_inertia` | float64 | Thermal inertia (J m-2 s-0.5 K-1) |
| `thermal_inertia_err_min` | float64 | Thermal inertia lower error bound |
| `thermal_inertia_err_max` | float64 | Thermal inertia upper error bound |
| `rotation_period_h` | float64 | Rotation period (hours, best estimate) |
| `rotation_period_err_min_h` | float64 | Rotation period lower error bound (hours) |
| `rotation_period_err_max_h` | float64 | Rotation period upper error bound (hours) |
| `moid_earth_au` | float64 | Minimum orbit intersection distance with Earth (AU) |

## Quick stats

- **{n_total:,}** asteroids and dwarf planets
- **{n_with_diameter:,}** with measured diameter
- **{n_with_albedo:,}** with measured albedo
- **{n_with_taxonomy:,}** with taxonomic classification
- **{n_with_mass:,}** with mass estimate
- **{n_with_density:,}** with density estimate
- **{n_with_rotation:,}** with rotation period
- **{n_families:,}** with dynamical family assignment

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/ssodnet-asteroid-properties", split="train")
df = ds.to_pandas()

# Taxonomy distribution
df["taxonomy_class"].value_counts().head(10)

# Large asteroids with known density
dense = df[df["density_g_cm3"].notna() & (df["diameter_km"] > 100)]
dense[["sso_name", "diameter_km", "density_g_cm3", "taxonomy_class"]].sort_values(
    "diameter_km", ascending=False
)

# Near-Earth asteroids sorted by MOID
neas = df[df["sso_class"] == "NEA"].sort_values("moid_earth_au")
neas[["sso_name", "diameter_km", "moid_earth_au", "albedo"]].head(20)

# Diameter vs albedo by taxonomy
import matplotlib.pyplot as plt
sample = df.dropna(subset=["diameter_km", "albedo", "taxonomy_complex"])
for cpx, grp in sample.groupby("taxonomy_complex"):
    plt.scatter(grp["diameter_km"], grp["albedo"], s=1, alpha=0.4, label=cpx)
plt.xscale("log")
plt.xlabel("Diameter (km)")
plt.ylabel("Albedo")
plt.legend(fontsize=7)
```

## Data source

[IMCCE SsODNet — Solar System Open Database Network](https://ssp.imcce.fr/webservices/ssodnet/)

The ssoBFT (Best Flat Table) compiles best estimates of physical and dynamical properties
for all known asteroids and dwarf planets. Data originates from thousands of peer-reviewed
publications, curated by IMCCE (Paris Observatory). See Berthier et al. (2023),
"SsODNet: The Solar System Open Database Network",
[A&A 671, A151](https://doi.org/10.1051/0004-6361/202244878).

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/ssodnet-asteroid-properties) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{ssodnet_asteroid_properties,
  author = {{Simon, Julien}},
  title = {{SsODNet Asteroid Physical Properties}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/ssodnet-asteroid-properties}},
  note = {{Based on IMCCE SsODNet ssoBFT, Berthier et al. (2023)}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Upload SsODNet asteroid properties: {n_total:,} objects"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    print(f"rows={n_total}")
    print("Done.")


if __name__ == "__main__":
    main()
