#!/usr/bin/env python3
"""Fetch TNO/Centaur physical properties from PDS Small Bodies Node and upload to HF.

Source: PDS Small Bodies Node — TNO-Centaur Diameter/Albedo/Density
compilation (V1.0) with measurements from Spitzer, Herschel, stellar
occultations, and resolved imaging.
"""

import io

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

TAB_URL = "https://sbnarchive.psi.edu/pds4/non_mission/tno-centaur_diam-albedo-density_V1_0/data/tno_centaur_diam_alb_dens.tab"
HF_REPO = "juliensimon/tno-centaur-properties"

# Fixed-width column specs from PDS XML label (0-indexed: loc-1, loc-1+len)
FW_COLS = [
    (0, 7, "asteroid_number"),
    (9, 24, "asteroid_name"),
    (25, 35, "provisional_designation"),
    (36, 43, "semimajor_axis_au"),
    (44, 49, "eccentricity"),
    (50, 54, "inclination_deg"),
    (56, 60, "dynamical_type"),
    (61, 63, "number_of_companions"),
    (64, 69, "absolute_magnitude_mpc"),
    (71, 78, "absolute_magnitude"),
    (80, 87, "absolute_magnitude_uncertainty"),
    (89, 95, "effective_diameter_km"),
    (96, 102, "effective_diameter_error_upper_km"),
    (104, 110, "effective_diameter_error_lower_km"),
    (111, 113, "effective_diameter_code"),
    (115, 121, "primary_diameter_km"),
    (123, 129, "primary_diameter_error_upper_km"),
    (130, 136, "primary_diameter_error_lower_km"),
    (137, 139, "primary_diameter_code"),
    (141, 147, "secondary_diameter_km"),
    (148, 154, "secondary_diameter_error_upper_km"),
    (155, 161, "secondary_diameter_error_lower_km"),
    (162, 164, "secondary_diameter_code"),
    (165, 171, "albedo"),
    (173, 179, "albedo_error_upper"),
    (181, 187, "albedo_error_lower"),
    (188, 190, "albedo_color"),
    (191, 193, "albedo_code"),
    (195, 201, "density_g_cm3"),
    (203, 209, "density_error_upper_g_cm3"),
    (211, 217, "density_error_lower_g_cm3"),
    (219, 221, "density_code"),
    (223, 226, "method_diameter_albedo"),
    (227, 229, "method_density"),
    (231, 235, "reference_code"),
]

COLSPECS = [(s, e) for s, e, _ in FW_COLS]
COLNAMES = [n for _, _, n in FW_COLS]

# Null sentinels in the PDS data
NULL_SENTINELS = {"-999.9", "-999.90", "-99.999", "-9.999", "-9.99", "-999", "N/A", ""}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "asteroid_number": "Minor Planet Center asteroid number; null for unnumbered objects that only have a provisional designation",
    "asteroid_name": "Official IAU name of the object (e.g. 'Pluto', 'Eris', 'Makemake'); null for unnamed objects identified only by number or provisional designation",
    "provisional_designation": "MPC provisional designation (e.g. '2003 UB313', '1992 QB1'); the discovery designation assigned before an object receives a permanent number and name",
    "semimajor_axis_au": "Orbital semimajor axis in astronomical units (AU); TNOs have a > 30 AU, Centaurs typically 5-30 AU; defines the size and period of the orbit",
    "eccentricity": "Orbital eccentricity (0 = circular, approaching 1 = highly elliptical); scattered disk objects often have e > 0.3, classical KBOs typically e < 0.1",
    "inclination_deg": "Orbital inclination relative to the ecliptic plane (degrees); hot classicals have i > 5 deg, cold classicals i < 5 deg; dynamically important for population classification",
    "dynamical_type": "Dynamical classification code: classical (cubewano), resonant (plutino, twotino), scattered, detached, Centaur, etc.; reveals the object's relationship to Neptune's gravitational influence",
    "number_of_companions": "Number of known satellites or binary companions; binary TNOs are common (~20% of cold classicals) and provide the only direct mass measurements for these objects",
    "absolute_magnitude_mpc": "MPC absolute magnitude H (visual band); brightness at 1 AU from Sun and observer at zero phase angle; used to estimate size when albedo is unknown",
    "absolute_magnitude": "Best-estimate absolute magnitude from the compilation, which may differ from MPC value due to improved photometry or phase corrections",
    "absolute_magnitude_uncertainty": "Uncertainty on the absolute magnitude; reflects photometric measurement errors and phase curve corrections",
    "effective_diameter_km": "Effective diameter in km, treating the object as a sphere of equivalent cross-section; measured via thermal emission (Spitzer/Herschel), stellar occultations, or resolved imaging",
    "effective_diameter_error_upper_km": "Upper 1-sigma uncertainty on effective diameter (km); asymmetric errors arise from thermal model assumptions",
    "effective_diameter_error_lower_km": "Lower 1-sigma uncertainty on effective diameter (km)",
    "effective_diameter_code": "Method/quality code for the effective diameter measurement; indicates the observational technique and reliability",
    "primary_diameter_km": "Diameter of the primary body in a binary/multiple system (km); null for single objects or where primary size is not separately resolved",
    "primary_diameter_error_upper_km": "Upper 1-sigma uncertainty on primary diameter (km)",
    "primary_diameter_error_lower_km": "Lower 1-sigma uncertainty on primary diameter (km)",
    "primary_diameter_code": "Method/quality code for primary diameter measurement",
    "secondary_diameter_km": "Diameter of the secondary (satellite) body in a binary system (km); null for single objects",
    "secondary_diameter_error_upper_km": "Upper 1-sigma uncertainty on secondary diameter (km)",
    "secondary_diameter_error_lower_km": "Lower 1-sigma uncertainty on secondary diameter (km)",
    "secondary_diameter_code": "Method/quality code for secondary diameter measurement",
    "albedo": "Geometric albedo (V-band reflectivity at zero phase angle); ranges from ~0.02 (very dark, carbon-rich surfaces) to >0.8 (bright icy surfaces like Eris); key surface composition diagnostic",
    "albedo_error_upper": "Upper 1-sigma uncertainty on geometric albedo",
    "albedo_error_lower": "Lower 1-sigma uncertainty on geometric albedo",
    "albedo_color": "Photometric band in which the albedo was measured (e.g. 'V' for visual, 'R' for red); important for comparing measurements across studies",
    "albedo_code": "Method/quality code for the albedo measurement",
    "density_g_cm3": "Bulk density in g/cm3; measured only for binary/multiple systems where mass is known from mutual orbits; ranges from ~0.5 (porous ice) to ~2.5 (rock-dominated); key interior structure constraint",
    "density_error_upper_g_cm3": "Upper 1-sigma uncertainty on bulk density (g/cm3)",
    "density_error_lower_g_cm3": "Lower 1-sigma uncertainty on bulk density (g/cm3)",
    "density_code": "Method/quality code for the density measurement",
    "method_diameter_albedo": "Observational method used for diameter/albedo determination (e.g. thermal, occultation, resolved imaging); thermal methods use Spitzer or Herschel far-infrared observations",
    "method_density": "Method used for density determination; typically 'orbit' (mutual orbit of binary components) or 'shape' (from resolved imaging plus mass estimate)",
    "reference_code": "Bibliographic reference code for the measurement; allows tracing each entry back to the original publication",
    "perihelion_au": "Closest approach to the Sun in AU, computed as a*(1-e); Centaurs have perihelia inside Neptune's orbit, TNOs typically beyond 30 AU",
    "aphelion_au": "Farthest distance from the Sun in AU, computed as a*(1+e); extreme scattered disk objects can have aphelia >1000 AU",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Physical property measurements for Trans-Neptunian Objects (TNOs) and Centaurs \
from the PDS Small Bodies Node compilation. Includes diameters, geometric albedos, \
and bulk densities with uncertainties, cross-referenced with orbital elements and \
dynamical classifications.

Trans-Neptunian Objects inhabit the outer reaches of the solar system beyond \
Neptune's orbit (a > 30 AU). They are remnants of the primordial planetesimal disk, \
preserved in cold storage for 4.5 billion years, and represent the least-processed \
material in the solar system. Centaurs are dynamically unstable objects on orbits \
that cross the giant planets, thought to be TNOs in transition toward the inner \
solar system.

Physical characterization of these distant objects is exceptionally challenging. \
Diameters and albedos are measured via thermal emission (Spitzer, Herschel), stellar \
occultations, or resolved imaging (HST, adaptive optics). Density measurements \
require binary or multiple systems where masses can be determined from mutual orbits. \
This dataset compiles measurements from multiple techniques and references, with some \
objects having multiple independent measurements.

The dynamical classification reveals the structure of the trans-Neptunian region: \
classical Kuiper Belt objects (cubewanos), resonant populations (plutinos in 3:2, \
twotinos in 2:1), scattered disk objects, and detached/extreme objects like Sedna.
"""


def main():
    print("Fetching TNO/Centaur properties from PDS Small Bodies Node...")
    resp = requests.get(TAB_URL, timeout=60, headers={"User-Agent": "space-datasets/1.0"})
    resp.raise_for_status()

    # Parse fixed-width file using column positions from PDS XML label
    df = pd.read_fwf(io.StringIO(resp.text), colspecs=COLSPECS, names=COLNAMES, header=None)
    print(f"  {len(df)} rows, {len(df.columns)} columns")

    # Replace null sentinels
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].astype(str).str.strip()
            df[col] = df[col].replace({v: None for v in NULL_SENTINELS})

    # Numeric coercion
    numeric_cols = [
        "asteroid_number", "semimajor_axis_au", "eccentricity", "inclination_deg",
        "number_of_companions",
        "absolute_magnitude_mpc", "absolute_magnitude", "absolute_magnitude_uncertainty",
        "effective_diameter_km", "effective_diameter_error_upper_km", "effective_diameter_error_lower_km",
        "primary_diameter_km", "primary_diameter_error_upper_km", "primary_diameter_error_lower_km",
        "secondary_diameter_km", "secondary_diameter_error_upper_km", "secondary_diameter_error_lower_km",
        "albedo", "albedo_error_upper", "albedo_error_lower",
        "density_g_cm3", "density_error_upper_g_cm3", "density_error_lower_g_cm3",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
            # Replace remaining -999 type sentinels after numeric conversion
            df.loc[df[col] <= -99, col] = None

    # Clean string columns
    for col in ["asteroid_name", "provisional_designation", "dynamical_type",
                "method_diameter_albedo", "method_density",
                "reference_code", "albedo_color", "albedo_code",
                "effective_diameter_code", "primary_diameter_code",
                "secondary_diameter_code", "density_code"]:
        if col in df.columns:
            df[col] = df[col].replace({"nan": None, "None": None, "-999.9": None})

    # Derived: perihelion and aphelion
    if "semimajor_axis_au" in df.columns and "eccentricity" in df.columns:
        df["perihelion_au"] = df["semimajor_axis_au"] * (1 - df["eccentricity"])
        df["aphelion_au"] = df["semimajor_axis_au"] * (1 + df["eccentricity"])

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_unique_objects = df["provisional_designation"].nunique() if "provisional_designation" in df.columns else n_total
    n_with_density = int(df["density_g_cm3"].notna().sum()) if "density_g_cm3" in df.columns else 0
    n_with_diameter = int(df["effective_diameter_km"].notna().sum()) if "effective_diameter_km" in df.columns else 0
    n_with_albedo = int(df["albedo"].notna().sum()) if "albedo" in df.columns else 0
    dyn_types = df["dynamical_type"].value_counts().to_dict() if "dynamical_type" in df.columns else {}
    diam_max = df["effective_diameter_km"].max() if "effective_diameter_km" in df.columns else None

    diam_stat = f"\n- Largest object: **{diam_max:.0f} km** diameter" if diam_max else ""

    quick_stats = f"""\
- **{n_total}** total measurements (~{n_unique_objects} unique objects)
- **{n_with_diameter}** with measured effective diameter
- **{n_with_albedo}** with geometric albedo
- **{n_with_density}** with bulk density{diam_stat}"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/tno-centaur-properties", split="train")
df = ds.to_pandas()

# Diameter vs albedo
import matplotlib.pyplot as plt
valid = df.dropna(subset=["effective_diameter_km", "albedo"])
plt.scatter(valid["effective_diameter_km"], valid["albedo"], alpha=0.5, s=15)
plt.xscale("log")
plt.xlabel("Effective Diameter (km)")
plt.ylabel("Geometric Albedo")
plt.title("TNO/Centaur Size vs Albedo")
plt.show()

# Orbital distribution
plt.scatter(df["semimajor_axis_au"], df["eccentricity"],
            c=df["inclination_deg"], cmap="viridis", alpha=0.5, s=10)
plt.colorbar(label="Inclination (deg)")
plt.xlabel("Semimajor Axis (AU)")
plt.ylabel("Eccentricity")
plt.title("TNO/Centaur Orbital Elements")
plt.show()

# Objects with density measurements
dense = df[df["density_g_cm3"].notna()].drop_duplicates("provisional_designation")
print(f"Objects with density: {len(dense)}")
print(dense[["asteroid_name", "density_g_cm3", "effective_diameter_km"]].to_string())
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="TNO/Centaur Physical Properties (PDS)",
        description=DESCRIPTION,
        tags=["space", "tno", "centaur", "kuiper-belt", "trans-neptunian",
              "planetary-science", "pds", "open-data", "tabular-data", "parquet"],
        source_url="https://sbnarchive.psi.edu/pds4/non_mission/tno-centaur_diam-albedo-density_V1_0/",
        task_categories=["tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA17666/PIA17666~small.jpg",
            "alt": "Rosetta spacecraft approaching Comet 67P/Churyumov-Gerasimenko",
            "credit": "NASA/ESA",
        },
        related_datasets=[
            "juliensimon/sbdb",
            "juliensimon/nesvorny-families",
            "juliensimon/neowise",
            "juliensimon/mpc-comets",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[c for c in numeric_cols if c in df.columns],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="tno_centaur_properties.parquet",
            min_rows=100,
            expected_columns=["semimajor_axis_au", "eccentricity", "inclination_deg"],
            critical_columns=["semimajor_axis_au"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update TNO/Centaur properties: {n_total} measurements",
        )
    print("Done.")


if __name__ == "__main__":
    main()
