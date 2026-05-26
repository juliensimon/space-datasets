#!/usr/bin/env python3
"""Fetch Holczer et al. 2016 Kepler Transit Timing Catalog from VizieR and upload to HF.

Source: Holczer T. et al. (2016, ApJS 225, 9) — 295,187 transit times for
2,599 Kepler Objects of Interest (KOIs), with O-C residuals, durations, and depths.
VizieR catalog: J/ApJS/225/9
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/kepler-transit-timing"

# Table 3: individual TTV, TDV, TPV changes per transit (295K rows)
ADQL = 'SELECT * FROM "J/ApJS/225/9/table3"'

# ── Column mapping ───────────────────────────────────────────────────
RENAME = {
    "KOI": "koi",
    "N": "transit_number",
    "Ntr": "transit_number",
    "ntr": "transit_number",
    "tn": "t_obs_bjd",
    "Tobs": "t_obs_bjd",
    "tobs": "t_obs_bjd",
    "e_Tobs": "t_obs_err",
    "e_tobs": "t_obs_err",
    "O-C": "o_c",
    "o_c": "o_c",
    "e_O-C": "o_c_err",
    "e_o_c": "o_c_err",
    "f_O-C": "o_c_flag",
    "TDV": "tdv",
    "e_TDV": "tdv_err",
    "f_TDV": "tdv_flag",
    "TPV": "tpv",
    "e_TPV": "tpv_err",
    "f_TPV": "tpv_flag",
    "Out": "outlier",
    "Over": "overlap",
    "Dur": "duration_hr",
    "dur": "duration_hr",
    "e_Dur": "duration_err",
    "e_dur": "duration_err",
    "Depth": "depth_ppm",
    "depth": "depth_ppm",
    "e_Depth": "depth_err",
    "e_depth": "depth_err",
    "OC": "o_c",
    "e_OC": "o_c_err",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "koi": "Kepler Object of Interest number (e.g. 137.01); the integer part identifies the host star in the KIC, the decimal suffix distinguishes multiple candidates around the same star",
    "transit_number": "Sequential index of this individual transit event for the given KOI, starting from 0 at the reference epoch; enables reconstruction of the full timing series",
    "t_obs_bjd": "Observed mid-transit time in Barycentric Julian Date offset: BJD_TDB - 2454833.0; the reference epoch (0.0) corresponds to 2009 January 1, the start of Kepler science operations",
    "t_obs_err": "1-sigma uncertainty on the observed mid-transit time in days; typical values 0.001-0.01 days (~1-15 min); larger for shallow or noisy transits",
    "o_c": "Observed minus computed (O-C) transit timing residual in days relative to the best-fit linear ephemeris; nonzero values indicate transit timing variations (TTVs) caused by gravitational perturbations from other bodies; null if transit was not cleanly isolated",
    "o_c_err": "1-sigma uncertainty on the O-C residual in days; propagated from the mid-time fit uncertainty",
    "o_c_flag": "Quality flag for the O-C measurement; non-null values indicate problematic transits (e.g. gaps, stellar activity, overlapping transits)",
    "duration_hr": "Transit duration in hours from first to last contact; sensitive to orbital inclination and impact parameter; typical Kepler transit durations 1-15 hours",
    "duration_err": "1-sigma uncertainty on transit duration in hours",
    "depth_ppm": "Transit depth in parts per million (flux decrease); equals (Rp/R_star)^2 x 10^6 for a central transit; Earth-Sun: ~84 ppm, Jupiter-Sun: ~10,000 ppm",
    "depth_err": "1-sigma uncertainty on transit depth in ppm",
    "tdv": "Transit duration variation — deviation of this transit's duration from the mean duration in hours; nonzero TDV can indicate orbital precession or a changing impact parameter",
    "tdv_err": "1-sigma uncertainty on the transit duration variation in hours",
    "tdv_flag": "Quality flag for the TDV measurement; non-null indicates problematic data",
    "tpv": "Transit profile variation — deviation of the transit shape parameter from its mean value; sensitive to changing impact parameter or stellar limb-darkening variations",
    "tpv_err": "1-sigma uncertainty on the transit profile variation",
    "tpv_flag": "Quality flag for the TPV measurement; non-null indicates problematic data",
    "outlier": "Flag marking this transit as a photometric outlier (e.g. stellar flare, cosmic ray, data gap); flagged transits are excluded from TTV analyses",
    "overlap": "Flag indicating this transit overlaps temporally with another transit of a different KOI around the same star; can bias timing measurements in compact multi-planet systems",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Transit timing catalog from Holczer et al. (2016), containing individual transit mid-times \
for Kepler Objects of Interest (KOIs). Each record includes the observed mid-transit time, \
observed-minus-computed (O-C) residual, transit duration, and transit depth with uncertainties.

Transit timing variations (TTVs) occur when gravitational interactions between planets in a \
multi-planet system cause measurable deviations from a strictly periodic transit schedule. \
Holczer et al. (2016) performed a uniform analysis of all Kepler long-cadence light curves \
to extract individual transit times, producing the most comprehensive Kepler TTV catalog. \
The O-C residuals reveal planetary interactions, orbital eccentricities, and the presence \
of additional non-transiting planets.

Transit timing variations are one of the most powerful tools for characterizing multi-planet \
systems. In a system with only one planet, transits occur at perfectly regular intervals set \
by the orbital period. When a second planet is present, its gravitational pull perturbs the \
transiting planet's orbit, causing each transit to arrive slightly early or late. The \
amplitude and pattern of these O-C residuals encode the mass, orbital period, and eccentricity \
of the perturbing body -- even if that body never transits the star itself.

This dataset is widely used for dynamical mass measurements via N-body fitting, studies of \
orbital resonance and migration history, and statistical analyses of multi-planet system \
architectures. It also serves as a benchmark for testing TTV extraction algorithms and for \
training machine learning models to detect weak dynamical signals in photometric time series.
"""


def main():
    print("Fetching Kepler Transit Timing Catalog (Holczer et al. 2016) from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} raw rows")

    rename_map = {k: v for k, v in RENAME.items() if k in df.columns}
    df = df.rename(columns=rename_map)

    # Snake-case any remaining columns
    already_renamed = set(rename_map.values())
    snake_map = {}
    for col in df.columns:
        if col not in already_renamed:
            snake = col.replace(" ", "_").replace("-", "_").lower()
            if snake != col:
                snake_map[col] = snake
    if snake_map:
        df = df.rename(columns=snake_map)

    # Drop VizieR internal columns
    for col in ["recno"]:
        if col in df.columns:
            df = df.drop(columns=[col])

    # Integer columns
    if "transit_number" in df.columns:
        df["transit_number"] = pd.to_numeric(df["transit_number"], errors="coerce").astype("Int32")

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Sort by KOI then transit number
    sort_cols = [c for c in ["koi", "transit_number"] if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols).reset_index(drop=True)

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_kois = int(df["koi"].nunique()) if "koi" in df.columns else 0
    median_oc = df["o_c"].median() if "o_c" in df.columns else float("nan")
    median_depth = df["depth_ppm"].median() if "depth_ppm" in df.columns else float("nan")
    median_dur = df["duration_hr"].median() if "duration_hr" in df.columns else float("nan")

    print(f"  {n_total:,} transits across {n_kois:,} KOIs")

    quick_stats = f"""\
- **{n_total:,}** individual transit times
- **{n_kois:,}** unique KOIs
- Median O-C residual: **{median_oc:.4f}** days
- Median transit depth: **{median_depth:.0f}** ppm
- Median transit duration: **{median_dur:.2f}** hours"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/kepler-transit-timing", split="train")
df = ds.to_pandas()

# TTVs for a specific KOI
koi_137 = df[df["koi"] == 137.01].sort_values("transit_number")
print(f"KOI 137.01: {len(koi_137)} transits")

# Plot O-C diagram
import matplotlib.pyplot as plt
plt.errorbar(koi_137["transit_number"], koi_137["o_c"],
             yerr=koi_137["o_c_err"], fmt=".", ms=3)
plt.xlabel("Transit number")
plt.ylabel("O-C (days)")
plt.title("KOI 137.01 Transit Timing Variations")
plt.show()

# KOIs with the strongest TTVs (largest O-C scatter)
ttv_rms = df.groupby("koi")["o_c"].std().sort_values(ascending=False)
print("Top 10 TTV candidates:")
print(ttv_rms.head(10))
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Kepler Transit Timing Catalog",
        description=DESCRIPTION,
        tags=["space", "exoplanets", "kepler", "transit-timing", "ttv",
              "astronomy", "open-data", "tabular-data", "parquet"],
        source_url="https://vizier.cds.unistra.fr/viz-bin/VizieR-3?-source=J/ApJS/225/9",
        license="other",
        license_name="vizier-scientific-use",
        license_link="https://cds.unistra.fr/vizier-org/licences_vizier.html",
        task_categories=["tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA21423/PIA21423~small.jpg",
            "alt": "Artist concept of the surface of TRAPPIST-1f exoplanet",
            "credit": "NASA/JPL-Caltech",
        },
        related_datasets=[
            "juliensimon/kepler-eclipsing-binaries",
            "juliensimon/nasa-exoplanets",
            "juliensimon/tess-toi-candidates",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "koi", "t_obs_bjd", "t_obs_err",
                "o_c", "o_c_err", "duration_hr", "duration_err",
                "depth_ppm", "depth_err",
                "tdv", "tdv_err", "tpv", "tpv_err",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="kepler_transit_timing.parquet",
            min_rows=200_000,
            expected_columns=["koi", "transit_number", "t_obs_bjd", "o_c"],
            critical_columns=["koi", "t_obs_bjd"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Kepler transit timing: {n_total:,} transits, {n_kois:,} KOIs",
        )
    print("Done.")


if __name__ == "__main__":
    main()
