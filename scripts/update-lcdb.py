#!/usr/bin/env python3
"""Fetch Asteroid Lightcurve Database (LCDB) and upload to HF."""

import io
import zipfile

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

HF_REPO = "juliensimon/asteroid-lightcurves-lcdb"

LCDB_URL = "https://minplanobs.org/MPInfo/datazips/LCLIST_PUB_CURRENT.zip"

# ── Fixed-width column specs for lc_summary_pub.txt ─────────────────────────
COLSPECS = [
    (0, 10),    # NUMBER
    (10, 41),   # NAME
    (41, 62),   # DESIG
    (62, 71),   # FAM (family code)
    (71, 73),   # class_source (S)
    (73, 84),   # CLASS (taxonomy)
    (84, 86),   # diameter_source (S)
    (86, 88),   # diameter_flag (F)
    (88, 97),   # DIA. (km)
    (97, 99),   # h_source (S)
    (99, 106),  # H (abs magnitude)
    (106, 109), # binary_flag (B)
    (109, 111), # g_source (S)
    (111, 118), # G
    (118, 125), # G1
    (125, 132), # G2
    (132, 134), # albedo_source (S)
    (134, 136), # albedo_flag (F)
    (136, 143), # ALBEDO
    (143, 145), # period_flag (F)
    (145, 159), # PERIOD (hours)
    (159, 161), # period_desc_source (P)
    (161, 175), # DESC (period description)
    (175, 177), # amplitude_flag (F)
    (177, 182), # AMIN
    (182, 187), # AMAX
    (187, 190), # U (quality code)
    (190, 196), # NOTES
    (196, 200), # BIN (binary type)
    (200, 204), # SAM
    (204, 210), # SurvA
    (210, 214), # NEX
    (214, 218), # PRI
]

RAW_NAMES = [
    "number", "name", "designation", "family", "class_source", "taxonomy",
    "diameter_source", "diameter_flag", "diameter_km", "h_source",
    "abs_magnitude_h", "binary_flag", "g_source", "g_param", "g1_param",
    "g2_param", "albedo_source", "albedo_flag", "albedo", "period_flag",
    "period_h", "period_desc_source", "period_description", "amplitude_flag",
    "amplitude_min", "amplitude_max", "quality_code_u", "notes",
    "binary_type", "sam", "survey_a", "n_entries", "pri",
]

# Columns to keep (drop internal source/flag columns)
KEEP_COLS = [
    "number", "name", "designation", "family", "taxonomy",
    "diameter_km", "abs_magnitude_h", "g_param", "g1_param", "g2_param",
    "albedo", "period_h", "period_flag", "period_description",
    "amplitude_min", "amplitude_max", "quality_code_u", "notes",
    "binary_type",
]

# ── Column descriptions ──────────────────────────────────────────────────────
COLUMN_DESCRIPTIONS = {
    "number": "IAU catalog number (positive integer); null for unnumbered asteroids with only a provisional designation",
    "name": "IAU proper name (e.g., 'Ceres', 'Eros'); null for unnamed objects",
    "designation": "MPC provisional designation (e.g., '2024 YR4'); null for numbered objects without a recorded provisional designation",
    "family": "Dynamical family membership code from the LCDB family list; null if the asteroid is not assigned to a known collisional family",
    "taxonomy": "Spectral taxonomic class (Tholen or Bus-DeMeo system, e.g., S, C, V, Sq); null for asteroids without a published classification",
    "diameter_km": "Estimated effective diameter in km; null for asteroids without a published size estimate; sources vary (IRAS, WISE, radar, occultation)",
    "abs_magnitude_h": "Absolute magnitude H (magnitude at 1 AU, zero phase angle); null for a small fraction of entries",
    "g_param": "IAU HG photometric slope parameter G; typical range 0.0–0.5; null if not published",
    "g1_param": "HG1G2 phase function parameter G1; alternative to G for non-standard phase curves; null if not published",
    "g2_param": "HG1G2 phase function parameter G2; used together with G1; null if not published",
    "albedo": "Geometric albedo (fraction of incident light reflected, 0–1); typical C-type 0.03–0.10, S-type 0.15–0.35; null if not published",
    "period_h": "Best-estimate rotation period in hours; range ~0.0003 h (super-fast rotators) to >1000 h for slow rotators; null if no period has been determined",
    "period_flag": "Qualifier for the period value: > = lower limit only, < = upper limit, S = synodic period, D = double-peaked, U = uncertain; null if no flag",
    "period_description": "Free-text notes on the period determination (e.g., method, caveats); null if none",
    "amplitude_min": "Minimum observed lightcurve amplitude in magnitudes; lower bound across all available apparitions; null if undetermined",
    "amplitude_max": "Maximum observed lightcurve amplitude in magnitudes; >0.9 mag implies axis ratio ≥2.5:1; null if undetermined",
    "quality_code_u": "Lightcurve quality rating U: 1 = tentative/very uncertain, 2 = fair (may be refined), 3 = reliable/unambiguous; suffixes + and - indicate borderline ratings",
    "notes": "Miscellaneous flags and comments from the LCDB; null if none",
    "binary_type": "Binary or multiple system designation: B = confirmed binary, M = confirmed multiple, ? = suspected; null if no binary evidence",
}

# ── Dataset description ──────────────────────────────────────────────────────
DESCRIPTION = """\
The Asteroid Lightcurve Database (LCDB) is the most comprehensive compilation of \
asteroid rotation parameters, maintained by Brian Warner at MinorPlanet.info. \
For each asteroid it provides the best-estimate rotation period (hours), lightcurve \
amplitude range (magnitudes), a reliability quality code (U rating 1–3), taxonomic \
classification, diameter, albedo, and photometric slope parameters.

Asteroid rotation is a direct probe of internal structure, collisional history, and \
non-gravitational physics. The distribution of spin rates reveals a sharp "spin barrier" \
near 2.2 hours for objects larger than about 200 meters: virtually no large asteroids \
rotate faster than this critical period, because centrifugal force would exceed the \
gravitational self-binding force of a rubble-pile body. The handful of super-fast rotators \
below this barrier are either monolithic rocks or very small objects where cohesive forces \
provide sufficient strength. This spin barrier is one of the strongest pieces of evidence \
that most asteroids larger than a few hundred meters are gravitationally bound rubble piles.

Lightcurve amplitude encodes shape information. A spherical object shows no brightness \
variation; an elongated body produces deep dips twice per rotation as its cross-section \
varies. Amplitudes above 1.0 magnitude imply axis ratios of at least 2.5:1, suggesting \
highly elongated or contact-binary morphologies. The binary_type column flags known binary \
and multiple systems, which comprise roughly 15% of near-Earth asteroids and play a key \
role in understanding the YORP spin-up mechanism.

The taxonomic classifications and albedo values enable population-level studies linking \
surface composition to rotational properties. Low-albedo C-complex asteroids tend to have \
longer rotation periods on average than high-albedo S-complex asteroids of the same size, \
reflecting differences in bulk density, internal structure, or collisional evolution \
timescales. These correlations constrain models of how the asteroid belt was assembled \
and dynamically processed over 4.6 billion years of solar system history.
"""


def main():
    print("Downloading LCDB zip...")
    resp = requests.get(LCDB_URL, timeout=120)
    resp.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        summary = [n for n in zf.namelist() if "lc_summary_pub" in n.lower()]
        if not summary:
            raise RuntimeError(f"lc_summary_pub.txt not found in zip: {zf.namelist()}")
        print(f"  Extracting {summary[0]}...")
        raw = zf.read(summary[0]).decode("latin-1")

    # Parse fixed-width file (skip 5 header lines: title, date, blank, header, dashes)
    df = pd.read_fwf(
        io.StringIO(raw),
        colspecs=COLSPECS,
        names=RAW_NAMES,
        skiprows=5,
    )
    print(f"  {len(df):,} raw rows")

    # --- Clean number column: strip trailing *, convert to nullable int ---
    df["number"] = (
        df["number"]
        .astype(str)
        .str.strip()
        .str.rstrip("*")
        .str.strip()
    )
    df["number"] = pd.to_numeric(df["number"], errors="coerce").astype("Int64")
    # Number=0 means unnumbered; convert to null
    df.loc[df["number"] == 0, "number"] = pd.NA

    # --- Clean family code to nullable int ---
    df["family"] = pd.to_numeric(df["family"], errors="coerce").astype("Int64")

    # Drop internal source/flag columns, keep useful ones
    df = df[KEEP_COLS].copy()

    # --- Rounding (after numeric cleanup via p.clean) ---
    # Applied after p.clean() processes numeric columns

    # ── Stats for README ─────────────────────────────────────────────────────
    # Compute on raw numeric values (before p.clean, to preserve identical stats)
    for col in ["diameter_km", "abs_magnitude_h", "g_param", "g1_param",
                "g2_param", "albedo", "period_h", "amplitude_min", "amplitude_max"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Round floats
    df["diameter_km"] = df["diameter_km"].round(3)
    df["abs_magnitude_h"] = df["abs_magnitude_h"].round(2)
    df["albedo"] = df["albedo"].round(4)
    df["period_h"] = df["period_h"].round(5)
    df["amplitude_min"] = df["amplitude_min"].round(3)
    df["amplitude_max"] = df["amplitude_max"].round(3)

    n_total = len(df)
    n_with_period = int(df["period_h"].notna().sum())
    n_with_diameter = int(df["diameter_km"].notna().sum())
    n_with_albedo = int(df["albedo"].notna().sum())
    n_high_quality = int(df["quality_code_u"].isin(["3", "3-"]).sum())
    n_binary = int(df["binary_type"].notna().sum())
    n_taxonomies = int(df["taxonomy"].nunique())
    fastest = df.loc[df["period_h"].idxmin()] if n_with_period else None
    median_period = df["period_h"].median()

    quick_stats = f"""\
- **{n_total:,}** asteroids
- **{n_with_period:,}** with measured rotation periods (median {median_period:.2f} h)
- **{n_high_quality:,}** with high-quality periods (U = 3 or 3-)
- **{n_with_diameter:,}** with known diameters
- **{n_with_albedo:,}** with measured albedos
- **{n_binary:,}** binary/multiple systems
- **{n_taxonomies}** distinct taxonomic classes
- Fastest rotator: **{fastest['name'] or fastest['designation']}** at **{fastest['period_h']:.5f}** hours"""

    usage = """\
```python
from datasets import load_dataset
import matplotlib.pyplot as plt

ds = load_dataset("juliensimon/asteroid-lightcurves-lcdb", split="train")
df = ds.to_pandas()

# Well-established rotation periods only (U >= 3)
reliable = df[df["quality_code_u"].isin(["3", "3-"])]

# Fast rotators (period < 2.2 h = spin barrier)
fast = df[(df["period_h"] < 2.2) & (df["quality_code_u"].isin(["3", "3-", "2+", "2"]))]

# S-type asteroids with known diameters and periods
s_type = df[
    (df["taxonomy"].str.startswith("S", na=False))
    & (df["diameter_km"].notna())
    & (df["period_h"].notna())
]

# Period vs diameter scatter — visualize the spin barrier
sub = df[(df["period_h"].notna()) & (df["diameter_km"].notna()) & (df["diameter_km"] > 0)]
plt.figure(figsize=(10, 7))
plt.scatter(sub["diameter_km"], sub["period_h"], s=1, alpha=0.3, color="steelblue")
plt.axhline(2.2, color="red", linestyle="--", linewidth=1.2, label="Spin barrier (2.2 h)")
plt.xscale("log")
plt.yscale("log")
plt.xlabel("Diameter (km)")
plt.ylabel("Period (hours)")
plt.title("Asteroid Spin Rate vs Size — LCDB")
plt.legend()
plt.tight_layout()
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Asteroid Lightcurve Database (LCDB)",
        description=DESCRIPTION,
        tags=["space", "asteroids", "lightcurves", "rotation", "orbital-mechanics",
              "open-data", "tabular-data", "parquet"],
        source_url="https://minplanobs.org/mpinfo/php/lcdb.php",
        task_categories=["tabular-classification", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA17666/PIA17666~small.jpg",
            "alt": "Rosetta spacecraft approaching Comet 67P/Churyumov-Gerasimenko",
            "credit": "NASA/ESA",
        },
        related_datasets=[
            "juliensimon/neo-close-approaches",
            "juliensimon/jpl-small-body-database",
            "juliensimon/nhats-accessible-asteroids",
        ],
    ) as p:
        df = p.clean(
            df,
            strings=["name", "designation", "taxonomy", "period_description",
                      "notes", "binary_type", "period_flag"],
        )
        p.publish(
            df,
            filename="asteroid_lightcurves_lcdb.parquet",
            min_rows=20_000,
            expected_columns=[
                "number", "name", "taxonomy", "diameter_km", "abs_magnitude_h",
                "albedo", "period_h", "amplitude_min", "amplitude_max", "quality_code_u",
            ],
            critical_columns=["period_h", "quality_code_u", "abs_magnitude_h"],
            max_null_pct=0.10,
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update LCDB: {n_total:,} asteroids",
        )
    print("Done.")


if __name__ == "__main__":
    main()
