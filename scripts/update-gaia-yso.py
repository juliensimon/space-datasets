#!/usr/bin/env python3
"""Fetch Gaia DR3 Young Stellar Objects catalog from ESA Gaia Archive and upload to HF.

YSO candidates are identified by joining gaiadr3.vari_classifier_result (best_class_name = 'YSO')
with gaiadr3.vari_summary (variability statistics) and gaiadr3.gaia_source (astrometry/photometry).
~79K sources total, paginated via TOP + source_id > last_id.
"""

import io
import time

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

GAIA_TAP = "https://gea.esac.esa.int/tap-server/tap/sync"
HF_REPO = "juliensimon/gaia-dr3-young-stellar-objects"
PAGE_SIZE = 50_000

# Columns to select from the three-way join
COLUMNS = """
c.source_id, c.best_class_name, c.best_class_score,
g.ra, g.dec, g.l, g.b,
g.parallax, g.parallax_error, g.pmra, g.pmdec,
g.phot_g_mean_mag, g.phot_bp_mean_mag, g.phot_rp_mean_mag,
s.mean_mag_g_fov, s.mean_mag_bp, s.mean_mag_rp,
s.median_mag_g_fov, s.median_mag_bp, s.median_mag_rp,
s.std_dev_mag_g_fov, s.std_dev_mag_bp, s.std_dev_mag_rp,
s.trimmed_range_mag_g_fov, s.trimmed_range_mag_bp, s.trimmed_range_mag_rp,
s.range_mag_g_fov, s.range_mag_bp, s.range_mag_rp,
s.min_mag_g_fov, s.max_mag_g_fov,
s.num_selected_g_fov, s.num_selected_bp, s.num_selected_rp,
s.skewness_mag_g_fov, s.kurtosis_mag_g_fov,
s.mad_mag_g_fov, s.abbe_mag_g_fov, s.iqr_mag_g_fov
""".strip()

FROM_CLAUSE = (
    "FROM gaiadr3.vari_classifier_result c "
    "JOIN gaiadr3.vari_summary s ON c.source_id = s.source_id "
    "JOIN gaiadr3.gaia_source g ON c.source_id = g.source_id"
)

# -- Column descriptions for README schema table ---------------------------
COLUMN_DESCRIPTIONS = {
    "source_id": "Gaia DR3 unique source identifier; use for cross-matching with other Gaia tables and external catalogs",
    "best_class_name": "Classification label from Gaia variability classifier (always 'YSO' in this dataset)",
    "best_class_score": "Classification confidence score (0-1); higher values indicate greater confidence that the source is a genuine YSO",
    "ra": "Right ascension in the ICRS frame at epoch J2016.0, decimal degrees (0-360)",
    "dec": "Declination in the ICRS frame at epoch J2016.0, decimal degrees (-90 to +90)",
    "l": "Galactic longitude in decimal degrees (0-360); useful for identifying star-forming regions along the Galactic plane",
    "b": "Galactic latitude in decimal degrees (-90 to +90); most YSOs cluster near b=0 in molecular cloud complexes",
    "parallax": "Trigonometric parallax in milliarcseconds (mas); convert to distance via d_pc = 1000/parallax_mas for nearby sources",
    "parallax_error": "1-sigma uncertainty on parallax in milliarcseconds",
    "pmra": "Proper motion in right ascension (mas/yr, includes cos(dec) factor); traces stellar kinematics and group membership",
    "pmdec": "Proper motion in declination (mas/yr); combined with pmra reveals co-moving groups of young stars",
    "phot_g_mean_mag": "Mean G-band (330-1050 nm) apparent magnitude from the Gaia catalog photometry",
    "phot_bp_mean_mag": "Mean BP-band (330-680 nm) apparent magnitude from the Gaia catalog photometry",
    "phot_rp_mean_mag": "Mean RP-band (630-1050 nm) apparent magnitude from the Gaia catalog photometry",
    "mean_mag_g_fov": "Mean G-band magnitude from the variability time series (field-of-view transits)",
    "mean_mag_bp": "Mean BP-band magnitude from the variability time series",
    "mean_mag_rp": "Mean RP-band magnitude from the variability time series",
    "median_mag_g_fov": "Median G-band magnitude from the variability time series; more robust to outliers than the mean",
    "median_mag_bp": "Median BP-band magnitude from the variability time series",
    "median_mag_rp": "Median RP-band magnitude from the variability time series",
    "std_dev_mag_g_fov": "Standard deviation of G-band magnitude; measures overall photometric variability amplitude",
    "std_dev_mag_bp": "Standard deviation of BP-band magnitude",
    "std_dev_mag_rp": "Standard deviation of RP-band magnitude",
    "trimmed_range_mag_g_fov": "5th-to-95th percentile range in G-band magnitude; robust variability amplitude less sensitive to outliers",
    "trimmed_range_mag_bp": "5th-to-95th percentile range in BP-band magnitude",
    "trimmed_range_mag_rp": "5th-to-95th percentile range in RP-band magnitude",
    "range_mag_g_fov": "Full range (max - min) of G-band magnitude; sensitive to extreme events like accretion bursts or eclipses",
    "range_mag_bp": "Full range of BP-band magnitude",
    "range_mag_rp": "Full range of RP-band magnitude",
    "min_mag_g_fov": "Minimum (brightest) G-band magnitude observed in the time series",
    "max_mag_g_fov": "Maximum (faintest) G-band magnitude observed in the time series",
    "num_selected_g_fov": "Number of G-band field-of-view transits used in the variability analysis",
    "num_selected_bp": "Number of BP-band observations used in the variability analysis",
    "num_selected_rp": "Number of RP-band observations used in the variability analysis",
    "skewness_mag_g_fov": "Skewness of the G-band magnitude distribution; negative values indicate fading events (dips), positive values indicate brightening events",
    "kurtosis_mag_g_fov": "Kurtosis of the G-band magnitude distribution; high values indicate rare extreme brightness changes (flares, deep dips)",
    "mad_mag_g_fov": "Median absolute deviation of G-band magnitude; robust measure of variability less affected by extreme outliers",
    "abbe_mag_g_fov": "Abbe value for G-band magnitudes; measures smoothness of the time series (low values = smooth/correlated, high = noisy/uncorrelated)",
    "iqr_mag_g_fov": "Interquartile range of G-band magnitude; the 25th-to-75th percentile spread",
    "bp_rp": "BP-RP color index (phot_bp_mean_mag - phot_rp_mean_mag); YSOs are typically red (large BP-RP) due to cool temperatures and circumstellar reddening",
}

# -- Dataset description ----------------------------------------------------
DESCRIPTION = """\
Gaia DR3 young stellar object (YSO) candidates identified by the ESA Gaia mission's \
variability classification pipeline. Each source includes a YSO classification confidence \
score, variability statistics (amplitudes, standard deviations, skewness, kurtosis), \
astrometry (positions, parallax, proper motions), and multi-band photometry (G, BP, RP).

Young stellar objects are pre-main-sequence stars still in the process of forming, often \
surrounded by circumstellar disks and exhibiting irregular photometric variability. Gaia's \
all-sky photometric survey identified these candidates through automated variability \
classification. The best_class_score field gives the classifier's confidence for the YSO \
label (higher = more confident).

This dataset joins three Gaia DR3 tables: vari_classifier_result (YSO classification and \
confidence score), vari_summary (variability statistics), and gaia_source (astrometry and \
catalog photometry).

Young stellar objects span a broad evolutionary sequence from deeply embedded protostars \
(Class 0/I) still accreting from their natal envelopes, through classical T Tauri stars \
(Class II) with optically thick circumstellar disks, to weak-lined T Tauri stars (Class III) \
whose disks have largely dissipated. Their photometric variability arises from multiple \
physical mechanisms operating simultaneously: hot spots at the base of magnetospheric \
accretion columns produce periodic modulation tied to the stellar rotation period; variable \
accretion rates cause irregular flickering on timescales of hours to weeks; disk warps and \
orbiting dust structures create quasi-periodic extinction dips; and powerful magnetic \
reconnection events drive flares with amplitudes of several magnitudes in extreme cases.

Because Gaia operates at optical wavelengths, this catalog is most complete for the more \
evolved, less embedded YSO populations (Class II and III) and is naturally biased against \
the youngest, most heavily obscured protostars. Nevertheless, the combination of precise Gaia \
astrometry (parallaxes and proper motions) with the variability metrics makes this catalog \
uniquely powerful for identifying co-moving groups of young stars and mapping the \
three-dimensional structure of nearby star-forming regions.
"""


def fetch_gaia_yso():
    """Fetch YSO candidates via paginated JOIN across classifier, summary, and source tables."""
    all_dfs = []
    last_id = 0
    page = 0
    while True:
        query = (
            f"SELECT TOP {PAGE_SIZE} {COLUMNS} "
            f"{FROM_CLAUSE} "
            f"WHERE c.best_class_name = 'YSO' AND c.source_id > {last_id} "
            f"ORDER BY c.source_id"
        )
        page += 1
        print(f"  Page {page}: fetching up to {PAGE_SIZE:,} rows (source_id > {last_id})...")
        resp = requests.post(GAIA_TAP, data={
            "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv",
            "QUERY": query,
        }, timeout=600)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text))
        if len(df) == 0:
            break
        all_dfs.append(df)
        last_id = int(df["source_id"].max())
        print(f"    got {len(df):,} rows (last source_id: {last_id})")
        if len(df) < PAGE_SIZE:
            break
        time.sleep(2)
    return pd.concat(all_dfs, ignore_index=True)


def main():
    print("Fetching Gaia DR3 Young Stellar Objects from ESA Gaia Archive...")
    df = fetch_gaia_yso()
    print(f"  {len(df):,} raw rows")

    # Convert object columns to numeric where appropriate
    for col in df.select_dtypes(include=["object"]).columns:
        if col == "best_class_name":
            continue
        converted = pd.to_numeric(df[col], errors="coerce")
        if converted.notna().sum() > 0.5 * df[col].notna().sum():
            df[col] = converted

    # Integer columns
    for col in ["num_selected_g_fov", "num_selected_bp", "num_selected_rp"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int32")

    # Derived: BP-RP color index from catalog photometry
    if "phot_bp_mean_mag" in df.columns and "phot_rp_mean_mag" in df.columns:
        df["bp_rp"] = df["phot_bp_mean_mag"] - df["phot_rp_mean_mag"]

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Sort by source_id
    if "source_id" in df.columns:
        df = df.sort_values("source_id").reset_index(drop=True)

    # Stats
    n_total = len(df)
    g_median = df["median_mag_g_fov"].median() if "median_mag_g_fov" in df.columns else float("nan")
    score_median = df["best_class_score"].median() if "best_class_score" in df.columns else float("nan")
    n_high_conf = int((df["best_class_score"] > 0.5).sum()) if "best_class_score" in df.columns else 0

    quick_stats = f"""\
- **{n_total:,}** YSO candidates
- **{n_high_conf:,}** with classification score > 0.5
- Median G magnitude: {g_median:.2f}
- Median classification score: {score_median:.3f}"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/gaia-dr3-young-stellar-objects", split="train")
df = ds.to_pandas()

# Classification score distribution
print(df["best_class_score"].describe())

# High-confidence YSOs (score > 0.5)
confident = df[df["best_class_score"] > 0.5]
print(f"High-confidence YSOs: {len(confident):,}")

# Color-magnitude diagram
import matplotlib.pyplot as plt
plt.scatter(df["bp_rp"], df["phot_g_mean_mag"], s=1, alpha=0.3,
            c=df["best_class_score"], cmap="viridis")
plt.colorbar(label="Classification score")
plt.xlabel("BP - RP (mag)")
plt.ylabel("G (mag)")
plt.gca().invert_yaxis()
plt.title("Gaia DR3 YSO Color-Magnitude Diagram")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Gaia DR3 Young Stellar Objects",
        description=DESCRIPTION,
        tags=["space", "gaia", "yso", "young-stars", "star-formation",
              "esa", "astronomy", "open-data", "tabular-data", "parquet"],
        source_url="https://gea.esac.esa.int/archive/",
        license="other",
        license_name="cc-by-nc-3.0-igo",
        license_link="https://creativecommons.org/licenses/by-nc/3.0/igo/",
        task_categories=["tabular-classification", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e000191/GSFC_20171208_Archive_e000191~medium.jpg",
            "alt": "A youthful globular star cluster observed by the Hubble Space Telescope",
            "credit": "NASA/ESA/Hubble",
        },
        related_datasets=[
            "juliensimon/gaia-dr3-eclipsing-binaries",
            "juliensimon/gcvs-variable-stars",
            "juliensimon/aavso-vsx-variable-stars",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "ra", "dec", "l", "b", "parallax", "parallax_error",
                "pmra", "pmdec", "best_class_score",
                "phot_g_mean_mag", "phot_bp_mean_mag", "phot_rp_mean_mag",
                "mean_mag_g_fov", "mean_mag_bp", "mean_mag_rp",
                "median_mag_g_fov", "median_mag_bp", "median_mag_rp",
                "std_dev_mag_g_fov", "std_dev_mag_bp", "std_dev_mag_rp",
                "trimmed_range_mag_g_fov", "trimmed_range_mag_bp", "trimmed_range_mag_rp",
                "range_mag_g_fov", "range_mag_bp", "range_mag_rp",
                "min_mag_g_fov", "max_mag_g_fov",
                "skewness_mag_g_fov", "kurtosis_mag_g_fov",
                "mad_mag_g_fov", "abbe_mag_g_fov", "iqr_mag_g_fov",
                "bp_rp",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="gaia_dr3_young_stellar_objects.parquet",
            min_rows=50_000,
            expected_columns=["source_id", "best_class_name", "best_class_score",
                              "ra", "dec", "median_mag_g_fov", "parallax"],
            critical_columns=["source_id", "best_class_name"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Gaia DR3 young stellar objects: {n_total:,} sources",
        )
    print("Done.")


if __name__ == "__main__":
    main()
