#!/usr/bin/env python3
"""Fetch NICER observation log from HEASARC and upload to HF.

Source: HEASARC table `nicermastr` — NICER (Neutron star Interior Composition
Explorer) master catalog of pointed observations from the X-ray timing telescope
mounted on the International Space Station. Each row is a single NICER pointing
with target, exposure, status, and proposal metadata.
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import heasarc_query

HF_REPO = "juliensimon/nicer-observations"

ADQL = "SELECT * FROM nicermastr"

COLUMN_DESCRIPTIONS = {
    "name": "Target name as recorded by the NICER observation planning system (e.g. 'PSR_B1937+21', 'Crab', 'Cyg_X-1', '4U_1820-303')",
    "ra": "Right ascension of the target (degrees, J2000, 0-360); zero/null for engineering and calibration pointings",
    "dec": "Declination of the target (degrees, J2000, -90 to +90)",
    "lii": "Galactic longitude of the target (degrees, 0-360)",
    "bii": "Galactic latitude of the target (degrees, -90 to +90)",
    "time": "Observation start time (Modified Julian Date, UTC); MJD 58239.0 corresponds to NICER mission start in 2018",
    "end_time": "Observation end time (Modified Julian Date, UTC)",
    "obsid": "NICER Observation ID — 10-digit identifier (e.g. '6070020809') that uniquely tags raw and reduced data products in the HEASARC archive",
    "target_id": "Numeric target identifier from the NICER target catalog; groups observations of the same astrophysical source",
    "target_ra": "Right ascension of the cataloged target (degrees, J2000); may differ slightly from `ra` for slewing observations",
    "target_dec": "Declination of the cataloged target (degrees, J2000)",
    "exposure": "On-source exposure time in seconds, summed across all active focal plane modules; primary metric for sensitivity",
    "time_awarded": "Total exposure time awarded by the NICER Time Allocation Committee for this observation (seconds)",
    "num_fpm": "Number of focal plane modules (FPMs) returning data for this observation; NICER has 56 detectors organized in 7 modules of 8 FPMs each, with 52 nominally active",
    "processing_status": "Pipeline processing state: 'VALIDATED' (final calibrated data ready for science), 'PROCESSED' (initial pipeline run), 'PENDING' (awaiting processing)",
    "processing_date": "Date the data product was last processed (MJD UTC)",
    "public_date": "Date when the data become public after the proposal proprietary period (MJD UTC); guest observer data are typically proprietary for 1 year",
    "prnb": "Proposal number (4-digit string); ties this observation to its accepted NICER guest observer or director's discretionary time proposal",
    "abstract": "Free-text abstract from the proposal that motivated this observation",
    "subject_category": "Science category assigned by the NICER program (e.g. 'TIMING', 'MAGNETAR', 'BINARY', 'ENG', 'CALIBRATION')",
    "category_code": "Numeric science category code corresponding to subject_category",
    "pi_lname": "Principal investigator last name",
    "pi_fname": "Principal investigator first name",
    "cycle": "NICER observing cycle (integer); cycle 0 was the commissioning and Director's Discretionary Time phase, cycles 1+ are annual guest observer cycles",
    "obs_type": "Observation classification: 'NOR' (normal science), 'ENG' (engineering), 'CAL' (calibration), 'DDT' (Director's Discretionary Time)",
    "title": "Short title of the parent proposal (e.g. 'TIMING WORKING GROUP', 'MAGNETAR WORKING GROUP')",
    "galactic_nh": "Galactic hydrogen column density toward the target (atoms/cm^2); used for spectral fitting",
    "target_class": "Astrophysical target classification (e.g. 'pulsar', 'binary', 'AGN'); may be null for general-purpose targets",
}

DESCRIPTION = """\
Complete NICER observation log from the HEASARC archive — every pointing made by the NICER \
(Neutron star Interior Composition Explorer) X-ray timing telescope mounted on the \
International Space Station since the instrument began science operations in mid-2017.

NICER's distinctive capability is millisecond-precision timing of soft X-ray photons (0.2-12 \
keV) from neutron stars, accreting binaries, magnetars, and the Sun. It has produced the most \
precise equation-of-state constraints on neutron-star matter to date through joint timing and \
spectroscopy of millisecond pulsars such as PSR J0030+0451 and PSR J0740+6620. Each row in \
this dataset is a single NICER pointing characterized by target, sky position, observation \
window, on-source exposure, the number of active focal plane modules, science category, \
principal investigator, and proposal-level metadata.

This dataset complements juliensimon/fermi-3pc-gamma-ray-pulsars for the same neutron-star \
population at GeV energies, juliensimon/swift-bat-survey and juliensimon/chandra-x-ray-sources \
for X-ray cross-mission searches, juliensimon/magnetars for the magnetar science category, \
and juliensimon/xray-binaries for the high-mass and low-mass X-ray binary populations that \
dominate NICER's timing program.\
"""


def main():
    print("Fetching NICER observation log from HEASARC...")
    df = heasarc_query("nicermastr", ADQL)
    print(f"  {len(df):,} observations fetched")

    df.columns = [c.strip().lower() for c in df.columns]

    string_cols = {
        "name", "obsid", "processing_status", "abstract", "subject_category",
        "pi_lname", "pi_fname", "obs_type", "title", "target_class",
    }
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip().replace(
            {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA, "NULL": pd.NA}
        )

    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    n_total = len(df)
    n_validated = int((df["processing_status"] == "VALIDATED").sum()) if "processing_status" in df.columns else 0
    total_exposure_s = float(df["exposure"].sum(skipna=True)) if "exposure" in df.columns else 0.0
    total_exposure_ms = total_exposure_s / 1_000_000
    n_targets = int(df["target_id"].dropna().nunique()) if "target_id" in df.columns else 0
    n_cycles = int(df["cycle"].dropna().nunique()) if "cycle" in df.columns else 0

    cat_lines = ""
    if "subject_category" in df.columns:
        top_cats = df["subject_category"].dropna().value_counts().head(5)
        cat_lines = "\n- Top science categories: " + ", ".join(
            f"**{cat}** ({n:,})" for cat, n in top_cats.items()
        )

    quick_stats = f"""\
- **{n_total:,}** NICER pointings since mission start in 2018
- **{n_validated:,}** observations with fully validated calibrated data (processing_status = VALIDATED)
- **{total_exposure_ms:.2f} Ms** total cumulative on-source exposure across all FPMs
- **{n_targets:,}** distinct astrophysical targets across **{n_cycles}** observing cycles{cat_lines}"""

    usage = """\
```python
from datasets import load_dataset
import matplotlib.pyplot as plt

ds = load_dataset("juliensimon/nicer-observations", split="train").to_pandas()

# Total exposure per target — find NICER's most-observed sources
top = (ds.dropna(subset=["target_id"])
         .groupby(["target_id", "name"])
         .agg(total_ks=("exposure", lambda s: s.sum() / 1000),
              n_obs=("obsid", "count"))
         .sort_values("total_ks", ascending=False)
         .head(20))
print(top)

# Distribution of observations by science category
ax = ds["subject_category"].value_counts().head(10).plot(kind="barh")
ax.set_xlabel("Number of NICER observations")
ax.set_title("NICER observation volume by science category")
plt.tight_layout()
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="NICER Observation Log",
        description=DESCRIPTION,
        tags=["space", "astronomy", "x-ray", "nicer", "neutron-stars", "pulsars",
              "iss", "nasa", "heasarc", "timing", "open-data", "tabular-data", "parquet"],
        source_url="https://heasarc.gsfc.nasa.gov/W3Browse/all/nicermastr.html",
        task_categories=["tabular-classification"],
        update_schedule="Quarterly",
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA21085/PIA21085~small.jpg",
            "alt": "Pulsar artist concept — NICER's primary science target",
            "credit": "NASA/JPL-Caltech",
        },
        related_datasets=[
            "juliensimon/fermi-3pc-gamma-ray-pulsars",
            "juliensimon/swift-bat-hard-xray-survey",
            "juliensimon/chandra-x-ray-sources",
            "juliensimon/mcgill-magnetar-catalog",
            "juliensimon/xray-binary-catalog",
            "juliensimon/pulsar-glitch-catalog",
        ],
    ) as p:
        df_clean = p.clean(
            df,
            numeric=[
                "ra", "dec", "lii", "bii", "time", "end_time",
                "target_id", "target_ra", "target_dec",
                "exposure", "time_awarded", "num_fpm",
                "processing_date", "public_date",
                "category_code", "cycle", "galactic_nh",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df_clean,
            filename="nicer_observations.parquet",
            min_rows=50_000,
            expected_columns=["name", "obsid", "ra", "dec", "exposure"],
            critical_columns=["obsid", "name"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update NICER observations: {n_total:,} pointings ({total_exposure_ms:.1f} Ms exposure)",
        )
    print("Done.")


if __name__ == "__main__":
    main()
