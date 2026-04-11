#!/usr/bin/env python3
"""Fetch SsODNet asteroid physical properties (ssoBFT) from IMCCE and upload to HF.

Source: IMCCE SsODNet — Solar System Open Database Network
        Best-estimates flat table (ssoBFT) for asteroids and dwarf planets.
Static dataset (uploaded once, no workflow).
"""

import tempfile
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import requests

from hf_dataset_utils import Pipeline

# ssoBFT bulk parquet — ~489 MB, updated regularly by IMCCE
PARQUET_URL = "https://ssp.imcce.fr/data/ssoBFT-latest_Asteroid.parquet"
HF_REPO = "juliensimon/ssodnet-asteroid-properties"

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
    # Tisserand parameter (Jupiter)
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
    # MOID (Earth)
    "moid.EMB.value": "moid_earth_au",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "sso_id": "SsODNet internal stable identifier (e.g., '1' for Ceres); permanent across catalog updates and used as the primary key for cross-referencing within SsODNet services",
    "sso_number": "IAU Minor Planet Center catalog number assigned after orbit determination; null for unnumbered objects whose orbits are not yet sufficiently constrained",
    "sso_name": "IAU-approved proper name (e.g., 'Ceres', 'Vesta'); null for the majority of objects that have a number but no name",
    "sso_type": "Broad object type: Asteroid, Dwarf Planet, etc.",
    "sso_class": "Dynamical orbital class: MB=Main Belt, NEA=Near-Earth Asteroid, Trojan=Jupiter Trojan, Centaur=Centaur object, KBO=Kuiper Belt Object, etc.",
    "semi_major_axis_au": "Orbital semi-major axis in AU; defines the orbit size and mean distance from the Sun; main-belt asteroids typically 2.0-3.3 AU, NEAs <1.3 AU, KBOs >30 AU",
    "eccentricity": "Orbital eccentricity (0 = circular, <1 = elliptical); main-belt asteroids: 0.0-0.3; near-Earth objects can reach 0.9+",
    "inclination_deg": "Orbital inclination relative to the ecliptic plane in degrees (0-180 deg); main-belt asteroids: typically 0-30 deg",
    "orbital_period_yr": "Time to complete one full orbit around the Sun, in years; derived from semi-major axis via Kepler's third law",
    "periapsis_distance_au": "Closest approach distance to the Sun (perihelion) in AU; NEAs with perihelion <1.3 AU can cross Earth's orbit",
    "apoapsis_distance_au": "Farthest distance from the Sun (aphelion) in AU",
    "tisserand_jupiter": "Tisserand parameter with respect to Jupiter -- a near-conserved quantity used to distinguish asteroid (>3.0) from Jupiter-family comet (<3.0) orbits",
    "family_number": "Numeric identifier of the Hirayama dynamical family; null for objects not assigned to any family",
    "family_name": "Name of the Hirayama dynamical family (e.g., 'Vesta', 'Koronis', 'Flora'); families are remnants of ancient collisional disruptions; null for non-family members",
    "family_status": "Membership confidence or role within the family (e.g., 'core', 'halo'); null for non-family members",
    "absolute_magnitude": "Absolute magnitude H -- brightness the asteroid would have at 1 AU from both Sun and observer at zero phase angle; proxy for size when albedo is unknown",
    "absolute_magnitude_err_min": "Lower (negative) uncertainty bound on H magnitude",
    "absolute_magnitude_err_max": "Upper (positive) uncertainty bound on H magnitude",
    "diameter_km": "Effective sphere-equivalent diameter in km (best estimate); null if not yet measured; ranges from sub-km NEAs to ~940 km (Ceres)",
    "diameter_err_min_km": "Lower uncertainty bound on diameter (km)",
    "diameter_err_max_km": "Upper uncertainty bound on diameter (km)",
    "albedo": "Geometric albedo (0-1); dark primitive C-type asteroids ~0.03-0.09, stony S-type ~0.15-0.30, bright E-type/icy bodies up to 1.0; null for most objects where thermal data are unavailable",
    "albedo_err_min": "Lower uncertainty bound on geometric albedo",
    "albedo_err_max": "Upper uncertainty bound on geometric albedo",
    "mass_kg": "Total mass in kg (best estimate); null for most objects -- only measurable via spacecraft flyby, mutual orbit of binary pairs, or gravitational deflection",
    "mass_err_min_kg": "Lower uncertainty bound on mass (kg)",
    "mass_err_max_kg": "Upper uncertainty bound on mass (kg)",
    "density_g_cm3": "Bulk density in g/cm3 (best estimate); metallic M-types ~4-7 g/cm3, stony S-types ~2.5-3.5 g/cm3, porous rubble-pile C-types often <1.5 g/cm3",
    "density_err_min_g_cm3": "Lower uncertainty bound on bulk density (g/cm3)",
    "density_err_max_g_cm3": "Upper uncertainty bound on bulk density (g/cm3)",
    "taxonomy_class": "Spectral taxonomic class letter(s) (e.g., S, C, X, V, B, D); C=carbonaceous, S=silicaceous/stony, X=metallic or enstatite, V=basaltic; null for unclassified objects",
    "taxonomy_complex": "Broader taxonomic grouping (e.g., 'C-complex', 'S-complex', 'X-complex'); aggregates related classes that share spectral characteristics",
    "taxonomy_scheme": "Classification scheme used (e.g., Bus-DeMeo=visible+NIR, Tholen=visible only, SMASS)",
    "taxonomy_waverange": "Wavelength range of the spectrum used for classification (e.g., 'Vis', 'NIR', 'Vis+NIR')",
    "taxonomy_technique": "Observational technique used (e.g., spectroscopy, photometry/color indices)",
    "thermal_inertia": "Thermal inertia in SI units (J m-2 s-0.5 K-1); low values (~10-50) indicate fine regolith, high values (~500+) indicate bare rock; null for most objects",
    "thermal_inertia_err_min": "Lower uncertainty bound on thermal inertia",
    "thermal_inertia_err_max": "Upper uncertainty bound on thermal inertia",
    "rotation_period_h": "Sidereal rotation period in hours (best estimate); null if not measured; most main-belt asteroids: 4-20 h",
    "rotation_period_err_min_h": "Lower uncertainty bound on rotation period (hours)",
    "rotation_period_err_max_h": "Upper uncertainty bound on rotation period (hours)",
    "moid_earth_au": "Minimum Orbit Intersection Distance with Earth in AU; objects with MOID <0.05 AU and H <22 are classified as Potentially Hazardous Asteroids (PHAs)",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Physical and dynamical properties of asteroids and dwarf planets from the IMCCE \
(Paris Observatory) Solar System Open Database Network (SsODNet). This is the most \
comprehensive asteroid characterization catalog available, compiling best estimates \
from thousands of published studies.

SsODNet aggregates physical property measurements from the astronomical literature \
into a single, curated "best estimates" flat table (ssoBFT). For each asteroid, IMCCE \
selects the most reliable published value for each property using a transparent \
ranking scheme. Properties include diameters, albedos, taxonomic classifications, \
masses, densities, rotation periods, and thermal inertia -- alongside orbital \
elements and dynamical family memberships.

The physical properties reveal the extraordinary diversity of the small body \
population. Diameters range from sub-kilometer near-Earth asteroids to dwarf planets \
like Ceres (940 km). Albedos span two orders of magnitude, from coal-dark C-type \
surfaces (albedo ~0.03) to highly reflective icy objects (albedo >0.5). Bulk \
densities constrain internal structure: metallic M-types exceed 5 g/cm3, stony \
S-types cluster around 2.5-3.5 g/cm3, and porous rubble-pile C-types often fall \
below 1.5 g/cm3.

Dynamical family membership connects individual asteroids to their collisional \
history. The Tisserand parameter with respect to Jupiter serves as a dynamical \
discriminant: values below 3.0 indicate Jupiter-family comet-like orbits, while \
main-belt asteroids typically have values above 3.0.
"""


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
    print("Reading parquet and selecting columns...")
    src = pq.ParquetFile(tmp_src)
    all_cols = src.schema.names
    print(f"  Source has {src.metadata.num_rows:,} rows, {len(all_cols)} columns")

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
    if "sso_number" in df.columns:
        df["sso_number"] = pd.to_numeric(df["sso_number"], errors="coerce").astype("Int64")
    if "family_number" in df.columns:
        df["family_number"] = pd.to_numeric(df["family_number"], errors="coerce").astype("Int64")

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

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # ── Stats ─────────────────────────────────────────────────────────────
    n_total = len(df)
    n_with_diameter = int(df["diameter_km"].notna().sum()) if "diameter_km" in df.columns else 0
    n_with_albedo = int(df["albedo"].notna().sum()) if "albedo" in df.columns else 0
    n_with_taxonomy = int(df["taxonomy_class"].notna().sum()) if "taxonomy_class" in df.columns else 0
    n_with_mass = int(df["mass_kg"].notna().sum()) if "mass_kg" in df.columns else 0
    n_with_density = int(df["density_g_cm3"].notna().sum()) if "density_g_cm3" in df.columns else 0
    n_with_rotation = int(df["rotation_period_h"].notna().sum()) if "rotation_period_h" in df.columns else 0
    n_families = int(df["family_name"].notna().sum()) if "family_name" in df.columns else 0

    print(f"\n  {n_total:,} asteroids total")
    print(f"  {n_with_diameter:,} with diameter")
    print(f"  {n_with_albedo:,} with albedo")
    print(f"  {n_with_taxonomy:,} with taxonomy")

    quick_stats = f"""\
- **{n_total:,}** asteroids and dwarf planets
- **{n_with_diameter:,}** with measured diameter
- **{n_with_albedo:,}** with measured albedo
- **{n_with_taxonomy:,}** with taxonomic classification
- **{n_with_mass:,}** with mass estimate
- **{n_with_density:,}** with density estimate
- **{n_with_rotation:,}** with rotation period
- **{n_families:,}** with dynamical family assignment"""

    usage = """\
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
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="SsODNet Asteroid Physical Properties",
        description=DESCRIPTION,
        tags=["space", "asteroids", "physical-properties", "imcce",
              "orbital-mechanics", "open-data", "tabular-data", "parquet"],
        source_url="https://ssp.imcce.fr/webservices/ssodnet/",
        task_categories=["tabular-classification", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA17666/PIA17666~small.jpg",
            "alt": "Rosetta spacecraft approaching Comet 67P/Churyumov-Gerasimenko",
            "credit": "NASA/ESA",
        },
    ) as p:
        p.publish(
            df,
            filename="ssodnet_asteroid_properties.parquet",
            min_rows=500_000,
            expected_columns=[
                "sso_id", "sso_number", "sso_name", "sso_class",
                "semi_major_axis_au", "eccentricity", "inclination_deg",
                "absolute_magnitude", "diameter_km", "albedo",
            ],
            critical_columns=["sso_id", "semi_major_axis_au", "absolute_magnitude"],
            max_null_pct=0.10,
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Upload SsODNet asteroid properties: {n_total:,} objects",
        )
    print("Done.")


if __name__ == "__main__":
    main()
