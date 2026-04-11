#!/usr/bin/env python3
"""Fetch NEOWISE asteroid diameters/albedos from PDS and upload to HF.

Source: PDS Small Bodies Node — NEOWISE Diameters and Albedos V2.0
Static dataset (uploaded once, no workflow).
"""

import io
import zipfile

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

ZIP_URL = "https://sbnarchive.psi.edu/pds4/non_mission/neowise_diameters_albedos_V2_0.zip"
HF_REPO = "juliensimon/neowise-asteroid-properties"

# Column definitions per CSV file, matching PDS4 XML labels exactly.
# Each table has a slightly different schema; we normalise after loading.
TABLE_DEFS = {
    "neowise_mainbelt.csv": {
        "columns": [
            "asteroid_number", "prov_desig", "mpc_packed_name",
            "absolute_mag", "slope_param", "mean_jd",
            "n_w1", "n_w2", "n_w3", "n_w4", "fit_code",
            "diameter_km", "diameter_err_km", "v_albedo", "v_albedo_err",
            "ir_albedo", "ir_albedo_err", "beaming_param", "beaming_param_err",
            "stacked_flag", "reference", "notes",
        ],
        "population": "main_belt",
    },
    "neowise_neos.csv": {
        "columns": [
            "asteroid_number", "prov_desig", "mpc_packed_name",
            "absolute_mag", "slope_param", "mean_jd",
            "n_w1", "n_w2", "n_w3", "n_w4", "fit_code",
            "diameter_km", "diameter_err_km", "v_albedo", "v_albedo_err",
            "ir_albedo", "ir_albedo_err", "beaming_param", "beaming_param_err",
            "stacked_flag", "reference", "notes",
        ],
        "population": "neo",
    },
    "neowise_hildas.csv": {
        "columns": [
            "asteroid_number", "prov_desig", "mpc_packed_name",
            "absolute_mag", "slope_param", "mean_jd",
            "n_w1", "n_w2", "n_w3", "n_w4", "fit_code",
            "diameter_km", "diameter_err_km", "v_albedo", "v_albedo_err",
            "ir_albedo", "ir_albedo_err", "beaming_param", "beaming_param_err",
            "stacked_flag", "reference", "notes",
        ],
        "population": "hilda",
    },
    "neowise_jupiter_trojans.csv": {
        "columns": [
            "asteroid_number", "prov_desig", "mpc_packed_name",
            "absolute_mag", "slope_param", "mean_jd",
            "n_w1", "n_w2", "n_w3", "n_w4", "fit_code",
            "diameter_km", "diameter_err_km", "v_albedo", "v_albedo_err",
            "ir_albedo", "ir_albedo_err", "beaming_param", "beaming_param_err",
            "stacked_flag", "reference", "notes",
        ],
        "population": "jupiter_trojan",
    },
    "neowise_centaurs.csv": {
        "columns": [
            "asteroid_number", "prov_desig", "comet_desig", "mpc_packed_name",
            "absolute_mag", "slope_param", "mean_jd",
            "n_w1", "n_w2", "n_w3", "n_w4", "fit_code",
            "diameter_km", "diameter_err_km", "v_albedo", "v_albedo_err",
            "ir_albedo", "ir_albedo_err", "beaming_param", "beaming_param_err",
            "stacked_flag", "reference",
        ],
        "population": "centaur",
    },
    "neowise_ambos.csv": {
        "columns": [
            "asteroid_number", "comet_desig", "mpc_packed_name",
            "absolute_mag", "slope_param", "mean_jd",
            "n_w1", "n_w2", "n_w3", "n_w4", "fit_code",
            "diameter_km", "diameter_err_km", "v_albedo", "v_albedo_err",
            "ir_albedo", "ir_albedo_err", "beaming_param", "beaming_param_err",
            "stacked_flag", "reference",
        ],
        "population": "ambiguous",
    },
    "neowise_fixed_diameter_fits.csv": {
        "columns": [
            "asteroid_number", "prov_desig", "mpc_packed_name",
            "absolute_mag", "slope_param", "mean_jd",
            "n_w1", "n_w2", "n_w3", "n_w4", "fit_code",
            "diameter_km", "diameter_err_km", "v_albedo", "v_albedo_err",
            "ir_albedo", "ir_albedo_err", "beaming_param", "beaming_param_err",
            "stacked_flag", "reference", "diameter_reference",
        ],
        "population": "fixed_diameter",
    },
    "neowise_irreg_sat.csv": {
        "columns": [
            "satellite_number", "mpc_packed_name",
            "absolute_mag", "slope_param", "mean_jd",
            "n_w1", "n_w2", "n_w3", "n_w4", "fit_code",
            "diameter_km", "diameter_err_km", "v_albedo", "v_albedo_err",
            "ir_albedo", "ir_albedo_err", "beaming_param", "beaming_param_err",
            "stacked_flag", "reference",
        ],
        "population": "irregular_satellite",
    },
}

# Sentinel values used for missing data in the PDS tables
MISSING_SENTINELS = {
    "absolute_mag": -9.99,
    "slope_param": -9.99,
    "v_albedo": -0.999,
    "v_albedo_err": -0.999,
    "ir_albedo": -0.999,
    "ir_albedo_err": -0.999,
    "beaming_param": 0.0,
    "beaming_param_err": 0.0,
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "object_id": "Primary identifier (asteroid number, satellite ID, or provisional designation)",
    "asteroid_number": "IAU asteroid catalog number (null for unnumbered/satellites)",
    "prov_desig": "Provisional designation (null if none)",
    "comet_desig": "Comet designation for dual-nature objects (null if none)",
    "mpc_packed_name": "MPC packed-format designation",
    "population": "Dynamical population: main_belt, neo, hilda, jupiter_trojan, centaur, irregular_satellite, ambiguous, fixed_diameter",
    "absolute_mag": "Absolute H magnitude used as input to thermal fit",
    "slope_param": "G slope parameter for photometric phase correction",
    "mean_jd": "Mean Julian Date of observations used for fitting",
    "n_w1": "Number of W1 (3.4 um) band measurements used",
    "n_w2": "Number of W2 (4.6 um) band measurements used",
    "n_w3": "Number of W3 (12 um) band measurements used",
    "n_w4": "Number of W4 (22 um) band measurements used",
    "fit_code": "4-char code: D=diameter, V=vis albedo, B=beaming/F=FRM, I=IR albedo, -=fixed",
    "diameter_km": "Best-fit effective spherical diameter (km)",
    "diameter_err_km": "1-sigma diameter uncertainty (km)",
    "v_albedo": "Visible geometric albedo (best-fit or assumed)",
    "v_albedo_err": "1-sigma visible albedo uncertainty",
    "ir_albedo": "Infrared geometric albedo (best-fit or assumed)",
    "ir_albedo_err": "1-sigma infrared albedo uncertainty",
    "beaming_param": "NEATM thermal beaming parameter eta",
    "beaming_param_err": "1-sigma beaming parameter uncertainty",
    "stacked_flag": '"S" if fit used co-added images on predicted position',
    "reference": "Short reference code for original publication",
    "notes": "Flags: OrbChange, NoOrb, BrokenLink (null if none)",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Physical properties (diameters, albedos, beaming parameters) of asteroids derived \
from WISE/NEOWISE infrared observations, spanning main-belt asteroids, NEOs, Hildas, \
Jupiter Trojans, Centaurs, irregular satellites, and ambiguous objects.

The WISE (Wide-field Infrared Survey Explorer) and NEOWISE missions observed over \
164,000 minor planets at thermal infrared wavelengths (3.4--22 microns). Thermal \
model fits to these observations yield diameter and albedo estimates that are \
independent of visible-light assumptions. This dataset combines all published \
NEOWISE diameter/albedo tables from the PDS Small Bodies Node (V2.0), covering \
observations from January 2010 through December 2016.

Each record represents a single thermal-model fit for one object. The `fit_code` \
column indicates which parameters were allowed to vary: D=diameter, V=visible albedo, \
B=beaming parameter (or F=fast-rotating model), I=infrared albedo.

Thermal infrared observations fundamentally changed our understanding of asteroid \
sizes. In visible light, an asteroid's brightness depends on both its size and its \
surface reflectivity (albedo), creating a degeneracy that makes size estimation from \
optical data alone unreliable by factors of two or more. At thermal infrared \
wavelengths, brightness is dominated by the object's thermal emission -- essentially \
how much sunlight it absorbs and re-radiates as heat -- which depends primarily on \
its physical cross-section. By fitting the Near-Earth Asteroid Thermal Model (NEATM) \
to multi-band infrared photometry, WISE/NEOWISE broke this size-albedo degeneracy \
for over 164,000 minor planets, producing the largest uniform survey of asteroid \
physical properties ever conducted.

The beaming parameter (eta) in the NEATM captures how thermal radiation is \
distributed across the surface. A perfectly smooth, non-rotating sphere in \
instantaneous thermal equilibrium would have eta = 1. Real asteroids show values \
ranging from about 0.8 to 2.5, reflecting the combined effects of surface roughness, \
thermal inertia, and spin rate.

The visible geometric albedo measurements in this dataset reveal the compositional \
diversity of the asteroid belt. Dark objects (albedo below 0.10) are predominantly \
carbonaceous C-complex asteroids. Bright objects (albedo above 0.15) are typically \
silicaceous S-complex asteroids. The population-level albedo distributions across \
main-belt, NEO, Hilda, Trojan, and Centaur groups encode the thermal and chemical \
gradient of the early solar nebula and subsequent dynamical mixing.
"""


def main():
    # ── Download ──────────────────────────────────────────────────────────
    print("Downloading NEOWISE diameters/albedos from PDS...")
    resp = requests.get(ZIP_URL, timeout=120)
    resp.raise_for_status()
    print(f"  Downloaded {len(resp.content) / 1024 / 1024:.1f} MB")

    # ── Extract and parse each table ──────────────────────────────────────
    frames = []
    zf = zipfile.ZipFile(io.BytesIO(resp.content))

    for csv_name, tdef in TABLE_DEFS.items():
        path = f"neowise_diameters_albedos_V2_0/data/{csv_name}"
        with zf.open(path) as fh:
            df = pd.read_csv(
                fh,
                header=None,
                names=tdef["columns"],
                dtype=str,
                skipinitialspace=True,
            )
        df["population"] = tdef["population"]
        frames.append(df)
        print(f"  {csv_name}: {len(df):,} rows")

    df = pd.concat(frames, ignore_index=True)
    print(f"  Total raw rows: {len(df):,}")

    # ── Normalise identifiers ─────────────────────────────────────────────
    def _make_object_id(row):
        for col in ("asteroid_number", "satellite_number"):
            val = row.get(col)
            if pd.notna(val) and str(val).strip() not in ("", "0"):
                return str(val).strip()
        for col in ("prov_desig", "comet_desig"):
            val = row.get(col)
            if pd.notna(val) and val.strip() not in ("", "-"):
                return val.strip()
        return row.get("mpc_packed_name", "").strip()

    df["object_id"] = df.apply(_make_object_id, axis=1)

    # Strip whitespace from string columns
    for col in ("prov_desig", "comet_desig", "mpc_packed_name",
                "fit_code", "stacked_flag", "reference", "notes",
                "diameter_reference", "satellite_number"):
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace({"nan": None, "": None, "-": None})

    # ── Type coercion ─────────────────────────────────────────────────────
    int_cols = ["asteroid_number", "n_w1", "n_w2", "n_w3", "n_w4"]
    for col in int_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    float_cols = [
        "absolute_mag", "slope_param", "mean_jd",
        "diameter_km", "diameter_err_km",
        "v_albedo", "v_albedo_err",
        "ir_albedo", "ir_albedo_err",
        "beaming_param", "beaming_param_err",
    ]
    for col in float_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Replace PDS sentinel values with NaN
    for col, sentinel in MISSING_SENTINELS.items():
        if col in df.columns:
            df.loc[df[col] == sentinel, col] = None

    # Replace asteroid_number == 0 with NaN (PDS missing constant)
    if "asteroid_number" in df.columns:
        df.loc[df["asteroid_number"] == 0, "asteroid_number"] = pd.NA

    # ── Final column selection (only described columns) ───────────────────
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # ── Stats ─────────────────────────────────────────────────────────────
    n_total = len(df)
    n_with_albedo = int(df["v_albedo"].notna().sum())
    n_populations = df["population"].nunique()
    pop_counts = df["population"].value_counts()
    median_diam = df["diameter_km"].median()
    median_albedo = df["v_albedo"].median()

    print(f"  {n_total:,} objects across {n_populations} populations")
    print(f"  Median diameter: {median_diam:.1f} km")
    print(f"  Median V-albedo: {median_albedo:.3f}")

    quick_stats = f"""\
- **{n_total:,}** objects across **{n_populations}** dynamical populations
- **{int(pop_counts.get('main_belt', 0)):,}** main-belt asteroids
- **{int(pop_counts.get('neo', 0)):,}** near-Earth objects
- **{int(pop_counts.get('jupiter_trojan', 0)):,}** Jupiter Trojans
- **{n_with_albedo:,}** objects with measured visible albedo
- Median diameter: **{median_diam:.1f} km** | Median V-albedo: **{median_albedo:.3f}**"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/neowise-asteroid-properties", split="train")
df = ds.to_pandas()

# Albedo distribution by population
df.groupby("population")["v_albedo"].describe()

# Large dark asteroids (low albedo, big diameter)
dark_big = df[(df["v_albedo"] < 0.05) & (df["diameter_km"] > 100)]

# NEOs with measured properties
neos = df[df["population"] == "neo"].sort_values("diameter_km", ascending=False)

# Diameter vs albedo scatter
import matplotlib.pyplot as plt
sample = df.dropna(subset=["diameter_km", "v_albedo"])
plt.scatter(sample["diameter_km"], sample["v_albedo"], s=0.5, alpha=0.3)
plt.xscale("log")
plt.xlabel("Diameter (km)")
plt.ylabel("Visible Albedo")
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="NEOWISE Asteroid Diameters and Albedos",
        description=DESCRIPTION,
        tags=["space", "asteroids", "neowise", "wise", "nasa",
              "orbital-mechanics", "open-data", "tabular-data", "parquet"],
        source_url="https://sbnarchive.psi.edu/pds4/non_mission/neowise_diameters_albedos_V2_0.zip",
        task_categories=["tabular-classification", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA17666/PIA17666~small.jpg",
            "alt": "Rosetta spacecraft approaching Comet 67P/Churyumov-Gerasimenko",
            "credit": "NASA/ESA",
        },
    ) as p:
        df = p.clean(
            df,
            numeric=float_cols,
            integer=["asteroid_number", "n_w1", "n_w2", "n_w3", "n_w4"],
        )
        p.publish(
            df,
            filename="neowise_asteroid_properties.parquet",
            min_rows=100_000,
            expected_columns=[
                "object_id", "population", "diameter_km", "v_albedo",
                "absolute_mag", "beaming_param",
            ],
            critical_columns=["object_id", "diameter_km", "v_albedo"],
            max_null_pct=0.10,
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Upload NEOWISE asteroid properties: {n_total:,} objects",
        )
    print("Done.")


if __name__ == "__main__":
    main()
