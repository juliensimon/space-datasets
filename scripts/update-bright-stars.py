#!/usr/bin/env python3
"""Fetch Bright Star Catalogue (BSC5) from VizieR and upload to HF.

Source: Hoffleit & Warren (1991), 5th Revised Edition.
VizieR catalog: V/50
"""

import re

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/bright-star-catalog"

ADQL = 'SELECT * FROM "V/50/catalog"'

# ── Column mapping ───────────────────────────────────────────────────
RENAME = {
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

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "hr_number": "Harvard Revised (Yale BSC) catalog number — the primary identifier for this catalog, stable since 1908; range 1-9110",
    "name": "Traditional common name (e.g. 'Sirius', 'Vega', 'Rigel'); null for the ~90% of entries without an established proper name",
    "hd_number": "Henry Draper Catalogue number; enables cross-matching with spectroscopic and photometric surveys that use HD identifiers; null if not assigned",
    "ra_deg": "Right ascension in the ICRS J2000.0 frame, decimal degrees (0-360)",
    "dec_deg": "Declination in the ICRS J2000.0 frame, decimal degrees (-90 to +90)",
    "v_mag": "Johnson V-band visual magnitude; brightest entries: Sirius -1.46, Canopus -0.72; catalog is complete to V ~ 6.5 (naked-eye limit)",
    "b_v_color": "Johnson B-V color index; proxy for surface temperature: -0.3 = hot blue O/B star, 0.0 = white A-star (Vega), 0.65 = solar-type G2V, 1.6 = cool red M-giant; null if B photometry unavailable",
    "u_b_color": "Johnson U-B color index; sensitive to UV excess from hot stars and emission features; null if U photometry unavailable",
    "r_i_color": "Cousins R-I color index; useful for cool-star classification and interstellar reddening estimates; null if R/I photometry unavailable",
    "spectral_type": "Full MK spectral classification (e.g. 'A1V' = Sirius, 'M2Ib' = Betelgeuse); letter codes temperature class (O-M, hottest to coolest), Roman numeral codes luminosity class (I = supergiant, III = giant, V = main-sequence dwarf)",
    "spectral_class": "Single temperature-class letter extracted from spectral_type (O, B, A, F, G, K, M); useful for population statistics and color grouping",
    "pm_ra_arcsec_yr": "Proper motion in right ascension (arcsec/yr, includes cos delta factor); null for very distant stars where motion is below measurement threshold",
    "pm_dec_arcsec_yr": "Proper motion in declination (arcsec/yr); null if not measured",
    "radial_velocity_kms": "Line-of-sight velocity relative to the Solar System barycenter (km/s); positive = receding; null if no spectroscopic measurement available",
    "rotational_velocity_kms": "Projected equatorial rotation speed v sin i (km/s); reflects true spin speed modulated by unknown inclination angle i; null for most cool stars and giants",
    "parallax_mas": "Trigonometric parallax in milliarcseconds (pre-Hipparcos ground-based values); distance_pc ~ 1000 / parallax_mas; null for distant supergiants where ground-based parallax is unreliable",
    "variable_name": "Variable star designation (e.g. 'alpha Ori' for Betelgeuse); non-null only for confirmed or suspected variables",
    "is_variable": "True if the star is listed as a known or suspected variable in BSC5; derived from variable_name being present",
    "multiplicity_flag": "One or more single-letter codes from the BSC multiplicity catalog (e.g. 'D' = double, 'V' = visual binary, 'S' = spectroscopic binary); null if no multiplicity noted",
    "is_multiple": "True if multiplicity_flag is non-null, indicating the star is in a binary or higher-order multiple system",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
The Bright Star Catalogue (BSC5, 5th Revised Edition) containing every naked-eye star \
brighter than visual magnitude ~6.5 with UBVRI photometry, MK spectral types, proper motions, \
radial and rotational velocities, and multiplicity information.

The Bright Star Catalogue (Hoffleit & Warren, 1991) is THE standard reference for naked-eye \
stars. Originally compiled at Yale University Observatory, the 5th Revised Edition contains \
9,110 entries covering every star visible to the unaided eye from the entire sky. It includes \
Harvard Revised (HR) photometry numbers, Henry Draper (HD) numbers, UBVRI broadband photometry, \
MK spectral classification, proper motions, trigonometric parallaxes, radial velocities, \
rotational velocities (v sin i), and flags for variability and multiplicity.

The BSC5 occupies a unique niche among stellar catalogs: it is magnitude-complete to V ~ 6.5, \
meaning it contains essentially every star the human eye can see under ideal conditions. This \
completeness makes it invaluable for statistical studies of the solar neighborhood's stellar \
population. The catalog spans the full range of spectral types from hot O and B stars to cool \
M giants, including main-sequence dwarfs, subgiants, giants, supergiants, and white dwarfs. \
Its UBVRI photometry enables construction of color-magnitude and color-color diagrams, while \
MK spectral classifications provide independent temperature and luminosity class determinations.

Despite its relatively modest size compared to modern survey catalogs containing billions of \
stars, the BSC5 remains widely used in observational astronomy, spacecraft attitude determination, \
planetarium software, and educational contexts. Many entries carry common star names (Sirius, \
Betelgeuse, Vega) alongside their HR and HD numbers, bridging traditional naked-eye astronomy \
with the modern catalog system.
"""


def main():
    print("Fetching Bright Star Catalogue from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} stars")

    # Drop unwanted columns
    for col in ["recno", "SimbadName", "More"]:
        if col in df.columns:
            df = df.drop(columns=[col])

    rename_map = {k: v for k, v in RENAME.items() if k in df.columns}
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

    if "variable_name" in df.columns:
        df["is_variable"] = df["variable_name"].notna()
    else:
        df["is_variable"] = False

    if "multiplicity_flag" in df.columns:
        df["is_multiple"] = df["multiplicity_flag"].notna()
    else:
        df["is_multiple"] = False

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Sort by HR number
    if "hr_number" in df.columns:
        df = df.sort_values("hr_number").reset_index(drop=True)

    # ── Domain-specific stats for README ─────────────────────────────
    n = len(df)
    brightest = df["v_mag"].min() if "v_mag" in df.columns else None
    faintest = df["v_mag"].max() if "v_mag" in df.columns else None
    n_variable = int(df["is_variable"].sum())
    n_multiple = int(df["is_multiple"].sum())

    class_counts = {}
    if "spectral_class" in df.columns:
        vc = df["spectral_class"].value_counts()
        for c in ["O", "B", "A", "F", "G", "K", "M"]:
            class_counts[c] = int(vc.get(c, 0))

    class_lines = "\n".join(
        f"- **{c}**: {class_counts.get(c, 0):,}" for c in ["O", "B", "A", "F", "G", "K", "M"]
    )

    quick_stats = f"""\
- **{n:,}** stars total
- Brightest: **{brightest:.2f}** mag / Faintest: **{faintest:.2f}** mag
- **{n_variable:,}** variable stars, **{n_multiple:,}** multiple systems

### By spectral class

{class_lines}"""

    usage = """\
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
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Bright Star Catalogue (BSC5)",
        description=DESCRIPTION,
        tags=["space", "stars", "bright-stars", "stellar", "naked-eye", "bsc5",
              "yale", "astronomy", "open-data", "tabular-data", "parquet"],
        source_url="https://vizier.cds.unistra.fr/viz-bin/VizieR-3?-source=V/50/catalog",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e000191/GSFC_20171208_Archive_e000191~medium.jpg",
            "alt": "A youthful globular star cluster observed by the Hubble Space Telescope",
            "credit": "NASA/ESA/Hubble",
        },
        related_datasets=[
            "juliensimon/wolf-rayet-stars",
            "juliensimon/brown-dwarf-catalog",
            "juliensimon/hipparcos-catalog",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "ra_deg", "dec_deg", "v_mag", "b_v_color", "u_b_color", "r_i_color",
                "pm_ra_arcsec_yr", "pm_dec_arcsec_yr", "radial_velocity_kms",
                "rotational_velocity_kms", "parallax_mas",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="bright_stars.parquet",
            min_rows=8000,
            expected_columns=["hr_number", "ra_deg", "dec_deg", "v_mag"],
            critical_columns=["ra_deg", "dec_deg", "v_mag"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update bright star catalog: {n:,} stars",
        )
    print("Done.")


if __name__ == "__main__":
    main()
