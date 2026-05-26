#!/usr/bin/env python3
"""Fetch ultracool/brown dwarf catalog (40 pc sample) from VizieR and upload to HF.

Source: Sebastian et al. (2021, A&A 645, A100) — volume-complete 40 pc sample.
VizieR catalog: J/A+A/645/A100
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/brown-dwarf-catalog"

ADQL = 'SELECT * FROM "J/A+A/645/A100/40pclist"'

# ── Column mapping ───────────────────────────────────────────────────
RENAME = {
    "RA_ICRS": "ra_deg",
    "RAICRS": "ra_deg",
    "RAJ2000": "ra_deg",
    "_RA": "ra_deg",
    "DE_ICRS": "dec_deg",
    "DEICRS": "dec_deg",
    "DEJ2000": "dec_deg",
    "_DE": "dec_deg",
    "SpT": "spectral_type",
    "SpType": "spectral_type",
    "SpTy": "spectral_type",
    "Dist": "distance_pc",
    "dist": "distance_pc",
    "Plx": "parallax_mas",
    "plx": "parallax_mas",
    "Jmag": "j_mag",
    "Hmag": "h_mag",
    "Kmag": "k_mag",
    "Ksmag": "ks_mag",
    "Gmag": "g_mag",
    "BPmag": "bp_mag",
    "RPmag": "rp_mag",
    "W1mag": "w1_mag",
    "W2mag": "w2_mag",
    "W3mag": "w3_mag",
    "W4mag": "w4_mag",
    "pmRA": "pm_ra_mas_yr",
    "pmDE": "pm_dec_mas_yr",
    "RV": "radial_velocity_kms",
    "Teff": "teff_k",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "ra_deg": "Right ascension in the ICRS J2000.0 frame, decimal degrees (0-360)",
    "dec_deg": "Declination in the ICRS J2000.0 frame, decimal degrees (-90 to +90)",
    "spectral_type": "Spectral type classification (e.g. 'M7', 'L2', 'T6', 'Y0'); M7+ are ultracool dwarfs; L/T/Y types are brown dwarfs of decreasing temperature; null if not classified",
    "spectral_class": "Single spectral class letter (M, L, T, Y) extracted from spectral_type; useful for population statistics across the brown dwarf cooling sequence",
    "distance_pc": "Distance from the Sun in parsecs; all entries are within 40 pc by catalog definition; null if parallax is unavailable",
    "parallax_mas": "Trigonometric parallax in milliarcseconds; distance_pc ~ 1000 / parallax_mas; null if not measured",
    "j_mag": "2MASS J-band (1.25 um) apparent magnitude; primary detection band for L dwarfs; null if not in 2MASS",
    "h_mag": "2MASS H-band (1.65 um) apparent magnitude; null if not in 2MASS",
    "k_mag": "2MASS K-band (2.17 um) apparent magnitude; null if not in 2MASS",
    "ks_mag": "2MASS Ks-band (2.17 um) apparent magnitude; alternative K-band measurement; null if not in 2MASS",
    "g_mag": "Gaia G-band (330-1050 nm) apparent magnitude; only available for brighter ultracool dwarfs; null for faint T/Y dwarfs",
    "bp_mag": "Gaia BP-band (330-680 nm) magnitude; null for most brown dwarfs (too faint in blue)",
    "rp_mag": "Gaia RP-band (630-1050 nm) magnitude; null for faint brown dwarfs",
    "w1_mag": "WISE W1-band (3.4 um) magnitude; sensitive to cool photospheres; primary detection band for T/Y dwarfs",
    "w2_mag": "WISE W2-band (4.6 um) magnitude; W1-W2 color is a powerful T/Y dwarf diagnostic",
    "w3_mag": "WISE W3-band (12 um) magnitude; null if too faint or confused",
    "w4_mag": "WISE W4-band (22 um) magnitude; null for most brown dwarfs",
    "pm_ra_mas_yr": "Proper motion in right ascension (includes cos delta factor) in mas/yr; high proper motion is a hallmark of nearby ultracool dwarfs",
    "pm_dec_mas_yr": "Proper motion in declination in mas/yr; combined with pm_ra gives total proper motion",
    "radial_velocity_kms": "Line-of-sight velocity in km/s; positive = receding; null for most faint brown dwarfs without spectroscopic RV measurements",
    "teff_k": "Effective temperature in Kelvin; L dwarfs: ~1400-2200 K, T dwarfs: ~500-1400 K, Y dwarfs: <500 K; null if not determined",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Comprehensive catalog of ultracool and brown dwarfs within 40 parsecs, highly relevant \
for JWST atmospheric characterization studies.

Brown dwarfs are substellar objects too low in mass to sustain hydrogen fusion. Ultracool \
dwarfs (spectral types M7 and later) bridge the gap between the lowest-mass stars and \
giant planets. This volume-complete 40 pc sample from Sebastian et al. (2021) provides \
the most comprehensive census of the solar neighborhood's ultracool population, including \
L, T, and Y dwarfs ideal for JWST follow-up.

Brown dwarfs occupy a unique region of parameter space between the coolest hydrogen-burning \
stars (spectral type ~M9, effective temperatures around 2300 K) and the most massive giant \
planets (~13 Jupiter masses). They form like stars through gravitational collapse of molecular \
cloud fragments, but their masses (roughly 13-80 Jupiter masses) are insufficient to sustain \
stable hydrogen fusion. Instead, they cool monotonically over billions of years, passing through \
the L, T, and Y spectral classes as their atmospheres transition from dust-dominated (L dwarfs, \
~1400-2200 K) to methane-dominated (T dwarfs, ~500-1400 K) to ammonia- and water-ice-dominated \
(Y dwarfs, below ~500 K).

JWST has transformed brown dwarf science by resolving molecular absorption features in the \
mid-infrared (3-28 microns) that are inaccessible from the ground, including water, methane, \
ammonia, carbon dioxide, and phosphine. The nearby brown dwarfs in this catalog are the \
highest signal-to-noise targets for JWST atmospheric retrieval studies.
"""


def main():
    print("Fetching ultracool/brown dwarf catalog (40 pc) from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} ultracool dwarfs")

    # Drop VizieR internal columns
    for col in ["recno", "SimbadName", "More"]:
        if col in df.columns:
            df = df.drop(columns=[col])

    rename_map = {k: v for k, v in RENAME.items() if k in df.columns}
    if rename_map:
        df = df.rename(columns=rename_map)

    # Snake-case remaining columns
    already_renamed = set(rename_map.values())
    snake_map = {}
    for col in df.columns:
        if col not in already_renamed:
            snake = col.replace(" ", "_").replace("-", "_").lower()
            if snake != col:
                snake_map[col] = snake
    if snake_map:
        df = df.rename(columns=snake_map)

    # Derive spectral class (M, L, T, Y) from spectral type
    def get_spectral_class(sp):
        if pd.isna(sp):
            return pd.NA
        s = str(sp).strip()
        if s and s[0] in {"M", "L", "T", "Y"}:
            return s[0]
        return pd.NA

    if "spectral_type" in df.columns:
        df["spectral_class"] = df["spectral_type"].apply(get_spectral_class)

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_with_spt = int(df["spectral_type"].notna().sum()) if "spectral_type" in df.columns else 0
    n_with_dist = int(df["distance_pc"].notna().sum()) if "distance_pc" in df.columns else 0
    n_with_teff = int(df["teff_k"].notna().sum()) if "teff_k" in df.columns else 0

    class_counts = {}
    if "spectral_class" in df.columns:
        vc = df["spectral_class"].value_counts()
        for c in ["M", "L", "T", "Y"]:
            class_counts[c] = int(vc.get(c, 0))

    class_lines = "\n".join(
        f"- **{c}**: {class_counts.get(c, 0):,}" for c in ["M", "L", "T", "Y"]
    )

    quick_stats = f"""\
- **{n_total:,}** ultracool dwarfs within 40 pc
- **{n_with_spt:,}** with spectral type classification
- **{n_with_dist:,}** with distance estimates
- **{n_with_teff:,}** with effective temperature

### By spectral class

{class_lines}"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/brown-dwarf-catalog", split="train")
df = ds.to_pandas()

# T and Y dwarfs (coldest brown dwarfs)
if "spectral_class" in df.columns:
    cold = df[df["spectral_class"].isin(["T", "Y"])]
    print(f"{len(cold):,} T/Y dwarfs")

# Nearest brown dwarfs
if "distance_pc" in df.columns:
    nearby = df.dropna(subset=["distance_pc"]).nsmallest(20, "distance_pc")
    print(nearby[["ra_deg", "dec_deg", "distance_pc", "spectral_type"]])

# Color-magnitude diagram (J vs J-K)
import matplotlib.pyplot as plt
valid = df.dropna(subset=["j_mag", "k_mag", "parallax_mas"])
valid = valid[valid["parallax_mas"] > 0]
valid["abs_j"] = valid["j_mag"] + 5 * (1 + valid["parallax_mas"].apply(
    lambda p: __import__('math').log10(p / 1000)))
valid["j_k"] = valid["j_mag"] - valid["k_mag"]
plt.scatter(valid["j_k"], valid["abs_j"], s=5, alpha=0.5)
plt.gca().invert_yaxis()
plt.xlabel("J - K (mag)")
plt.ylabel("Absolute J (mag)")
plt.title("Brown Dwarf Color-Magnitude Diagram")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Ultracool and Brown Dwarf Catalog (40 pc)",
        description=DESCRIPTION,
        tags=["space", "brown-dwarf", "ultracool", "jwst", "stellar",
              "astronomy", "open-data", "tabular-data", "parquet"],
        source_url="https://vizier.cds.unistra.fr/viz-bin/VizieR-3?-source=J/A+A/645/A100",
        license="other",
        license_name="vizier-scientific-use",
        license_link="https://cds.unistra.fr/vizier-org/licences_vizier.html",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e000191/GSFC_20171208_Archive_e000191~medium.jpg",
            "alt": "A youthful globular star cluster observed by the Hubble Space Telescope",
            "credit": "NASA/ESA/Hubble",
        },
        related_datasets=[
            "juliensimon/bright-star-catalog",
            "juliensimon/cns5-nearby-stars",
            "juliensimon/hipparcos-catalog",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "ra_deg", "dec_deg", "distance_pc", "parallax_mas",
                "j_mag", "h_mag", "k_mag", "ks_mag", "g_mag", "bp_mag", "rp_mag",
                "w1_mag", "w2_mag", "w3_mag", "w4_mag",
                "pm_ra_mas_yr", "pm_dec_mas_yr", "radial_velocity_kms", "teff_k",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="brown_dwarfs.parquet",
            min_rows=10000,
            expected_columns=["ra_deg", "dec_deg", "spectral_type"],
            critical_columns=["ra_deg", "dec_deg"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update brown dwarf catalog: {n_total:,} dwarfs",
        )
    print("Done.")


if __name__ == "__main__":
    main()
