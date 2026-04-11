#!/usr/bin/env python3
"""Fetch ICRF3 Celestial Reference Frame from VizieR and upload to HF.

Source: Xu et al. (2019), "Structure Effects for 3417 Celestial Reference
Frame Radio Sources", ApJS, 242, 5.
VizieR catalog: J/ApJS/242/5
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/icrf3-reference-frame"

# ── Source query ─────────────────────────────────────────────────────
ADQL = 'SELECT * FROM "J/ApJS/242/5/table2"'

# ── Column mapping ───────────────────────────────────────────────────
RENAME = {
    "IERS": "iers_name",
    "_RA": "ra_deg",
    "_DE": "dec_deg",
    "CARMS-N": "closure_amplitude_rms_n",
    "CARMS-B": "closure_amplitude_rms_b",
    "CARMS-U": "closure_amplitude_rms_u",
    "Namp": "n_closure_amplitude",
    "CPRMS-N": "closure_phase_rms_n_deg",
    "CPRMS-B": "closure_phase_rms_b_deg",
    "CPRMS-U": "closure_phase_rms_u_deg",
    "Npha": "n_closure_phase",
    "Nses": "n_sessions",
    "Nobs": "n_observations",
    "F-ICRF2": "flag_icrf2",
    "F-ICRF3": "flag_icrf3",
    "ICRF2": "icrf2_structure_index",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "iers_name": "Official IERS source designation in B1950 sexagesimal format (HHMM+DDd, e.g. '0002-478'); this is the authoritative name used in geodetic VLBI scheduling, Earth orientation monitoring, and spacecraft navigation",
    "ra_deg": "Right ascension of the extragalactic radio source in degrees, ICRS J2000.0 epoch; range 0-360; defining sources carry positional accuracies of ~30 microarcseconds",
    "dec_deg": "Declination of the extragalactic radio source in degrees, ICRS J2000.0; range -90 to +90; southern hemisphere coverage is sparser due to fewer southern VLBI stations",
    "closure_amplitude_rms_n": "RMS of closure amplitude residuals for narrow-field VLBI imaging (dimensionless); measures source compactness — lower values indicate more point-like sources with more stable astrometric positions",
    "closure_amplitude_rms_b": "RMS of closure amplitude residuals for broad-field imaging (dimensionless); sensitive to extended jet structure on longer baselines",
    "closure_amplitude_rms_u": "RMS of closure amplitude residuals for uniform weighting (dimensionless); intermediate sensitivity between narrow and broad-field",
    "n_closure_amplitude": "Number of closure amplitude measurements used in the structure analysis; more measurements yield more reliable structure diagnostics",
    "closure_phase_rms_n_deg": "RMS of closure phase residuals for narrow-field imaging in degrees; closure phase is immune to antenna-based errors, making it a robust measure of source asymmetry",
    "closure_phase_rms_b_deg": "RMS of closure phase residuals for broad-field imaging in degrees; elevated values indicate resolved jet structure",
    "closure_phase_rms_u_deg": "RMS of closure phase residuals for uniform weighting in degrees",
    "n_closure_phase": "Number of closure phase measurements used in the structure analysis",
    "n_sessions": "Number of VLBI observing sessions in which this source was observed; well-observed sources have hundreds of sessions over decades",
    "n_observations": "Total number of individual VLBI observations (delay measurements) across all sessions; high counts indicate heavily-used calibrator sources",
    "flag_icrf2": "Source classification flag in ICRF2: 'D' = defining, 'N' = non-defining, 'S' = special handling; null if not in ICRF2",
    "flag_icrf3": "Source classification flag in ICRF3: 'D' = defining (303 sources with the most stable positions), 'S' = special handling (688 sources with extended structure); null for non-defining sources",
    "icrf2_structure_index": "Source structure index from ICRF2 (1-4 scale); 1 = very compact, 4 = highly extended; used for calibrator selection in VLBI observations",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
The third International Celestial Reference Frame (ICRF3) is the fundamental coordinate \
reference frame for astronomy, adopted by the International Astronomical Union in 2018. \
It is defined by extragalactic radio sources (primarily quasars) observed by Very Long \
Baseline Interferometry (VLBI). This dataset contains structure parameters from Xu et al. \
(2019) that quantify each source's compactness and positional stability.

The ICRF is the realization of the International Celestial Reference System (ICRS) at \
radio wavelengths. ICRF3 is based on nearly 40 years of VLBI observations and provides \
the most accurate positions of extragalactic objects, with median positional uncertainties \
of ~30 microarcseconds for the defining sources.

The ICRF is conceptually the modern replacement for the FK5 optical fundamental star \
catalog. While FK5 was limited by the proper motions and parallaxes of nearby stars, the \
ICRF uses extremely distant quasars whose apparent motions are negligible, providing a \
quasi-inertial reference frame tied to the large-scale structure of the universe. Source \
structure — the extended radio jets that cause apparent position shifts — is the dominant \
systematic error in VLBI astrometry. This dataset includes structure index parameters \
that quantify each source's compactness, which is critical for selecting calibrators for \
VLBI observations and for space geodesy applications.
"""


def main():
    print("Fetching ICRF3 sources from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} ICRF3 sources")

    # Drop VizieR internal columns
    for col in ["recno", "SimbadName"]:
        if col in df.columns:
            df = df.drop(columns=[col])

    df = df.rename(columns={k: v for k, v in RENAME.items() if k in df.columns})

    # Clean string columns
    for col in ["iers_name", "flag_icrf2", "flag_icrf3"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
            )

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_defining = int((df["flag_icrf3"] == "D").sum()) if "flag_icrf3" in df.columns else 0
    n_special = int((df["flag_icrf3"] == "S").sum()) if "flag_icrf3" in df.columns else 0
    median_sessions = int(df["n_sessions"].median()) if "n_sessions" in df.columns else 0
    max_obs = int(df["n_observations"].max()) if "n_observations" in df.columns else 0

    quick_stats = f"""\
- **{n_total:,}** ICRF3 radio sources
- **{n_defining}** defining sources (highest positional stability)
- **{n_special}** special-handling sources (extended jet structure)
- Median observing sessions per source: **{median_sessions}**
- Most-observed source: **{max_obs:,}** individual VLBI measurements"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/icrf3-reference-frame", split="train")
df = ds.to_pandas()

# Defining sources — the foundation of the celestial reference frame
defining = df[df["flag_icrf3"] == "D"]
print(f"{len(defining)} ICRF3 defining sources")

# Sky distribution of defining vs. non-defining sources
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(12, 6))
other = df[df["flag_icrf3"] != "D"]
ax.scatter(other["ra_deg"], other["dec_deg"], s=1, alpha=0.3, label="Non-defining")
ax.scatter(defining["ra_deg"], defining["dec_deg"], s=5, c="red", label="Defining")
ax.set_xlabel("RA (deg)")
ax.set_ylabel("Dec (deg)")
ax.invert_xaxis()
ax.legend()
ax.set_title("ICRF3 All-Sky Distribution")
plt.tight_layout()
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="ICRF3 Celestial Reference Frame",
        description=DESCRIPTION,
        tags=["space", "icrf", "reference-frame", "astrometry", "quasar",
              "vlbi", "open-data", "tabular-data", "parquet"],
        source_url="https://vizier.cds.unistra.fr/viz-bin/VizieR-3?-source=J/ApJS/242/5",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e002215/GSFC_20171208_Archive_e002215~medium.jpg",
            "alt": "The gamma-ray sky as seen by NASA's Fermi telescope",
            "credit": "NASA/DOE/Fermi LAT Collaboration",
        },
        related_datasets=[
            "juliensimon/pulsar-catalog",
            "juliensimon/open-star-clusters",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=["ra_deg", "dec_deg",
                     "closure_amplitude_rms_n", "closure_amplitude_rms_b",
                     "closure_amplitude_rms_u",
                     "closure_phase_rms_n_deg", "closure_phase_rms_b_deg",
                     "closure_phase_rms_u_deg"],
            integer={"n_closure_amplitude": "Int64", "n_closure_phase": "Int64",
                     "n_sessions": "Int64", "n_observations": "Int64",
                     "icrf2_structure_index": "Int64"},
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="icrf3_reference_frame.parquet",
            min_rows=3000,
            expected_columns=["iers_name", "ra_deg", "dec_deg"],
            critical_columns=["iers_name", "ra_deg", "dec_deg"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update ICRF3 reference frame: {n_total:,} sources",
        )
    print("Done.")


if __name__ == "__main__":
    main()
