#!/usr/bin/env python3
"""Fetch Catalogue of Nearby Stars (CNS5) from VizieR and upload to HF.

Source: Golovin et al. (2023, A&A 670, A19) — 5th edition, stars within 25 pc.
VizieR catalog: J/A+A/670/A19
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/cns5-nearby-stars"

ADQL = 'SELECT * FROM "J/A+A/670/A19/cns5"'

# ── Column mapping ───────────────────────────────────────────────────
RENAME = {
    "CNS5": "cns5_id",
    "GJ": "gj_name",
    "Comp": "component",
    "NComp": "n_components",
    "P?": "problematic_flag",
    "GJp": "gj_primary",
    "GaiaDR3": "gaia_dr3_id",
    "HIP": "hip_id",
    "RAJ2000": "ra_deg",
    "DEJ2000": "dec_deg",
    "Epoch": "epoch",
    "r_pos": "ref_position",
    "plx": "parallax_mas",
    "e_plx": "parallax_error_mas",
    "r_plx": "ref_parallax",
    "pmRA": "pm_ra_mas_yr",
    "e_pmRA": "pm_ra_error",
    "pmDE": "pm_dec_mas_yr",
    "e_pmDE": "pm_dec_error",
    "r_pmRA": "ref_proper_motion",
    "RV": "radial_velocity_km_s",
    "e_RV": "radial_velocity_error",
    "r_RV": "ref_radial_velocity",
    "Gmag": "g_mag",
    "e_Gmag": "g_mag_error",
    "BPmag": "bp_mag",
    "e_BPmag": "bp_mag_error",
    "RPmag": "rp_mag",
    "e_RPmag": "rp_mag_error",
    "GHIPmag": "g_hip_mag",
    "e_GHIPmag": "g_hip_mag_error",
    "G-RPHIP": "g_rp_hip",
    "e_G-RPHIP": "g_rp_hip_error",
    "Gmagr": "g_mag_resulting",
    "e_Gmagr": "g_mag_resulting_error",
    "(G-RP)r": "g_rp_resulting",
    "e_(G-RP)r": "g_rp_resulting_error",
    "f_(G-RP)r": "g_rp_resulting_flag",
    "Jmag": "j_mag",
    "e_Jmag": "j_mag_error",
    "Hmag": "h_mag",
    "e_Hmag": "h_mag_error",
    "Ksmag": "ks_mag",
    "e_Ksmag": "ks_mag_error",
    "r_Jmag": "ref_2mass",
    "W1mag": "w1_mag",
    "e_W1mag": "w1_mag_error",
    "W2mag": "w2_mag",
    "e_W2mag": "w2_mag_error",
    "W3mag": "w3_mag",
    "e_W3mag": "w3_mag_error",
    "W4mag": "w4_mag",
    "e_W4mag": "w4_mag_error",
    "r_W1mag": "ref_wise",
    "SimbadName": "simbad_name",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "cns5_id": "Sequential designation number in the CNS5 catalog",
    "gj_name": "Standard Gliese-Jahreiss catalog identifier (e.g. 'GJ 832'); the canonical identifier for nearby stars; null for stars added after the original GJ catalog",
    "component": "Component suffix (e.g. 'A', 'B', 'C') distinguishing individual members of binary or multiple star systems; null for single stars",
    "n_components": "Total number of gravitationally bound components in the stellar system; null if multiplicity is unknown",
    "problematic_flag": "Flag indicating a questionable entry (e.g. uncertain parallax, possible non-stellar object); non-zero values warrant caution; null means no issue",
    "gj_primary": "GJ identifier of the primary (brightest) component for systems where this entry is a secondary; null for primaries and single stars",
    "gaia_dr3_id": "Gaia Data Release 3 source identifier; use to cross-match with the full Gaia catalog; null if no Gaia counterpart was matched",
    "hip_id": "ESA Hipparcos mission catalog number; null for stars too faint or not observed by Hipparcos",
    "ra_deg": "ICRS J2000.0 right ascension in decimal degrees (0-360)",
    "dec_deg": "ICRS J2000.0 declination in decimal degrees (-90 to +90)",
    "epoch": "Reference epoch (Julian year, e.g. 2016.0) at which the coordinates and proper motion are valid",
    "ref_position": "Bibliographic reference code for the position measurement",
    "parallax_mas": "Trigonometric parallax in milliarcseconds; distance_pc = 1000 / parallax_mas; typical range for CNS5: 40-768 mas (2.5-25 pc)",
    "parallax_error_mas": "1-sigma uncertainty on the parallax in milliarcseconds",
    "ref_parallax": "Bibliographic reference code for the parallax measurement",
    "pm_ra_mas_yr": "Proper motion in right ascension (includes cos delta factor) in mas/yr; high proper motion (>100 mas/yr) is a hallmark of nearby stars",
    "pm_ra_error": "1-sigma uncertainty on proper motion in RA in mas/yr",
    "pm_dec_mas_yr": "Proper motion in declination in mas/yr; combined with pm_ra_mas_yr for total proper motion",
    "pm_dec_error": "1-sigma uncertainty on proper motion in declination in mas/yr",
    "ref_proper_motion": "Bibliographic reference code for the proper motion measurement",
    "radial_velocity_km_s": "Line-of-sight velocity in km/s; positive = receding, negative = approaching; null if not measured",
    "radial_velocity_error": "1-sigma uncertainty on radial velocity in km/s",
    "ref_radial_velocity": "Bibliographic reference code for the radial velocity measurement",
    "g_mag": "Gaia broad-band G magnitude (~330-1050 nm); null if no Gaia match",
    "g_mag_error": "1-sigma uncertainty on Gaia G magnitude",
    "bp_mag": "Gaia blue photometer BP (~330-680 nm) magnitude; null if no Gaia match",
    "bp_mag_error": "1-sigma uncertainty on Gaia BP magnitude",
    "rp_mag": "Gaia red photometer RP (~630-1050 nm) magnitude; null if no Gaia match",
    "rp_mag_error": "1-sigma uncertainty on Gaia RP magnitude",
    "g_hip_mag": "Hipparcos-era G magnitude; null if not available",
    "g_hip_mag_error": "1-sigma uncertainty on Hipparcos-era G magnitude",
    "g_rp_hip": "Hipparcos-era G-RP color index; null if not available",
    "g_rp_hip_error": "1-sigma uncertainty on Hipparcos-era G-RP color",
    "g_mag_resulting": "Resulting G magnitude combining Gaia and Hipparcos data",
    "g_mag_resulting_error": "1-sigma uncertainty on the resulting G magnitude",
    "g_rp_resulting": "Resulting G-RP color index combining Gaia and Hipparcos data",
    "g_rp_resulting_error": "1-sigma uncertainty on the resulting G-RP color",
    "g_rp_resulting_flag": "Flag for the resulting G-RP color computation method",
    "j_mag": "2MASS J-band (~1.25 um) magnitude; null if not in 2MASS",
    "j_mag_error": "1-sigma uncertainty on 2MASS J magnitude",
    "h_mag": "2MASS H-band (~1.65 um) magnitude; null if not in 2MASS",
    "h_mag_error": "1-sigma uncertainty on 2MASS H magnitude",
    "ks_mag": "2MASS Ks-band (~2.17 um) magnitude; null if not in 2MASS",
    "ks_mag_error": "1-sigma uncertainty on 2MASS Ks magnitude",
    "ref_2mass": "Bibliographic reference code for the 2MASS photometry",
    "w1_mag": "WISE W1-band (~3.4 um) magnitude; null if not in WISE",
    "w1_mag_error": "1-sigma uncertainty on WISE W1 magnitude",
    "w2_mag": "WISE W2-band (~4.6 um) magnitude; null if not in WISE",
    "w2_mag_error": "1-sigma uncertainty on WISE W2 magnitude",
    "w3_mag": "WISE W3-band (~12 um) magnitude; excess emission can indicate a debris disk; null if not in WISE",
    "w3_mag_error": "1-sigma uncertainty on WISE W3 magnitude",
    "w4_mag": "WISE W4-band (~22 um) magnitude; null if not in WISE",
    "w4_mag_error": "1-sigma uncertainty on WISE W4 magnitude",
    "ref_wise": "Bibliographic reference code for the WISE photometry",
    "distance_pc": "Distance from the Sun in parsecs, derived as 1000 / parallax_mas; all entries are within 25 pc by catalog definition",
    "simbad_name": "Primary SIMBAD database identifier for the object; useful for cross-matching with the broader astronomical literature; null if not resolved",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
The fifth edition of the Catalogue of Nearby Stars (CNS5) is a comprehensive census of \
stellar systems within 25 parsecs of the Sun. It provides astrometric, photometric, and \
cross-identification data for the solar neighborhood, compiled from Gaia EDR3, Hipparcos, \
2MASS, and WISE.

The CNS5 (Golovin, Reffert, Just, Jordan, Vani & Jahreiss 2023, A&A 670, A19) extends the \
classic Gliese & Jahreiss nearby-star catalogs using Gaia EDR3 parallaxes as the primary \
distance indicator. It includes all known stars with trigonometric parallax placing them \
within 25 pc, with multi-band photometry (Gaia G/BP/RP, 2MASS JHKs, WISE W1-W4), proper \
motions, and radial velocities where available.

The solar neighborhood within 25 parsecs is the only volume of space where we can obtain a \
truly complete census of the stellar population, down to the faintest brown dwarfs and white \
dwarfs. This completeness is essential for determining the stellar luminosity function and \
the local mass density of the Galactic disk. The 25-parsec sample is dominated by red dwarfs \
(spectral types M0-M9), which account for roughly 75% of all stellar systems in the solar \
neighborhood despite being invisible to the naked eye.

The proper motions and radial velocities in this catalog allow full three-dimensional space \
velocity reconstruction for most entries, enabling kinematic membership analysis of nearby \
moving groups and stellar streams.
"""


def main():
    print("Fetching CNS5 from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} nearby stars")

    # Drop VizieR internal column
    df = df.drop(columns=["recno"], errors="ignore")

    df = df.rename(columns={k: v for k, v in RENAME.items() if k in df.columns})

    # Clean string columns
    str_cols = [
        "gj_name", "component", "gj_primary",
        "ref_position", "ref_parallax", "ref_proper_motion",
        "ref_radial_velocity", "ref_2mass", "ref_wise",
        "simbad_name",
    ]
    for col in str_cols:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
            )

    # Compute distance in parsecs from parallax
    mask = df["parallax_mas"].notna() & (df["parallax_mas"] > 0)
    df["distance_pc"] = pd.NA
    df.loc[mask, "distance_pc"] = 1000.0 / df.loc[mask, "parallax_mas"]

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Sort by CNS5 ID
    df = df.sort_values("cns5_id").reset_index(drop=True)

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_with_rv = int(df["radial_velocity_km_s"].notna().sum())
    n_with_simbad = int(df["simbad_name"].notna().sum())
    n_with_gaia = int(df["gaia_dr3_id"].notna().sum())
    median_dist = df["distance_pc"].median()
    min_dist = df["distance_pc"].min()

    quick_stats = f"""\
- **{n_total:,}** stellar entries within 25 pc
- **{n_with_gaia:,}** with Gaia DR3 cross-match
- **{n_with_rv:,}** with radial velocity
- **{n_with_simbad:,}** with SIMBAD identification
- Median distance: **{median_dist:.1f} pc**, nearest: **{min_dist:.2f} pc**"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/cns5-nearby-stars", split="train")
df = ds.to_pandas()

# Stars within 5 parsecs (the immediate solar neighborhood)
nearby = df[df["distance_pc"] <= 5].sort_values("distance_pc")
print(f"{len(nearby)} stars within 5 pc")
print(nearby[["simbad_name", "distance_pc", "g_mag"]].head(10))

# Distribution of stellar distances
import matplotlib.pyplot as plt
df["distance_pc"].dropna().hist(bins=50)
plt.xlabel("Distance (pc)")
plt.ylabel("Count")
plt.title("CNS5: Distribution of Nearby Star Distances")

# Color-magnitude diagram
valid = df.dropna(subset=["bp_mag", "rp_mag", "g_mag", "parallax_mas"])
valid = valid[valid["parallax_mas"] > 0]
valid["abs_g"] = valid["g_mag"] + 5 * (1 + valid["parallax_mas"].apply(
    lambda p: __import__('math').log10(p / 1000)))
valid["bp_rp"] = valid["bp_mag"] - valid["rp_mag"]
plt.figure()
plt.scatter(valid["bp_rp"], valid["abs_g"], s=0.3, alpha=0.4)
plt.gca().invert_yaxis()
plt.xlabel("BP - RP (mag)")
plt.ylabel("Absolute G (mag)")
plt.title("CNS5 HR Diagram")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Catalogue of Nearby Stars (CNS5)",
        description=DESCRIPTION,
        tags=["space", "stars", "solar-neighborhood", "nearby-stars",
              "astronomy", "open-data", "tabular-data", "parquet"],
        source_url="https://vizier.cds.unistra.fr/viz-bin/VizieR?-source=J/A+A/670/A19",
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
            "juliensimon/hipparcos-catalog",
            "juliensimon/brown-dwarf-catalog",
            "juliensimon/open-star-clusters",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "cns5_id", "n_components", "problematic_flag",
                "gaia_dr3_id", "hip_id",
                "ra_deg", "dec_deg", "epoch",
                "parallax_mas", "parallax_error_mas",
                "pm_ra_mas_yr", "pm_ra_error", "pm_dec_mas_yr", "pm_dec_error",
                "radial_velocity_km_s", "radial_velocity_error",
                "g_mag", "g_mag_error", "bp_mag", "bp_mag_error",
                "rp_mag", "rp_mag_error",
                "g_hip_mag", "g_hip_mag_error",
                "g_rp_hip", "g_rp_hip_error",
                "g_mag_resulting", "g_mag_resulting_error",
                "g_rp_resulting", "g_rp_resulting_error",
                "g_rp_resulting_flag",
                "j_mag", "j_mag_error", "h_mag", "h_mag_error",
                "ks_mag", "ks_mag_error",
                "w1_mag", "w1_mag_error", "w2_mag", "w2_mag_error",
                "w3_mag", "w3_mag_error", "w4_mag", "w4_mag_error",
                "distance_pc",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="cns5_nearby_stars.parquet",
            min_rows=4000,
            expected_columns=["cns5_id", "ra_deg", "dec_deg", "parallax_mas", "distance_pc"],
            critical_columns=["cns5_id", "ra_deg", "dec_deg"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Upload CNS5 nearby stars: {n_total:,} entries",
        )
    print("Done.")


if __name__ == "__main__":
    main()
