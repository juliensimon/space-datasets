#!/usr/bin/env python3
"""Fetch JWST observation metadata from the MAST CAOM TAP service and upload to HF.

Joins dbo.caomobservation (observation-level metadata: target, proposal, PI,
instrument) with aggregated dbo.caomplane data (time, exposure, wavelength,
filters). Result is one row per JWST observation.
"""

import os

import pandas as pd

from hf_dataset_utils import Pipeline
from mast_tap import fetch_observations, fetch_planes, load_checkpoint, save_checkpoint

HF_REPO = "juliensimon/jwst-observations"
CHECKPOINT_PATH = os.environ.get("JWST_CHECKPOINT", "/tmp/jwst_raw.parquet")

# ── Column descriptions ─────────────────────────────────────────────────
COLUMN_DESCRIPTIONS = {
    "obs_id": "MAST observation identifier (e.g., 'jw01011002001_02101_00001_mirifulong'); encodes proposal, visit, exposure, and detector. Primary key.",
    "proposal_id": "JWST proposal identifier (string, e.g., '1011'); groups related observations by Principal Investigator's program",
    "proposal_pi": "Last name, first initial of the proposal Principal Investigator",
    "proposal_title": "Full title of the JWST observing proposal",
    "proposal_project": "Proposal project code (e.g., 'GO', 'GTO', 'ERS', 'DDT'); GO = General Observer, GTO = Guaranteed Time, ERS = Early Release Science, DDT = Director's Discretionary Time",
    "proposal_keywords": "Science keywords tagged on the proposal (semicolon-separated)",
    "target_name": "Target name as provided by the proposer (may include survey designations, coordinates, or informal names)",
    "target_ra": "Target right ascension in decimal degrees (ICRS). May be 0 for moving or calibration targets.",
    "target_dec": "Target declination in decimal degrees (ICRS). May be 0 for moving or calibration targets.",
    "target_moving": "True if the target is a moving solar system body (asteroid, comet, planet, moon); False for fixed celestial targets",
    "instrument": "Instrument name: NIRCAM, NIRSPEC, NIRISS, MIRI, or FGS (from 'INSTRUMENT/MODE' split)",
    "observation_mode": "Observation mode: IMAGE, SPECTRUM, IFU, SLIT, WFSS, TACQ, etc. (from 'INSTRUMENT/MODE' split)",
    "intent": "Observation intent: 'science' or 'calibration'",
    "obstype": "CAOM observation type code: 'S' (simple), 'C' (composite). Most JWST observations are simple.",
    "observation_start_mjd": "Observation start time as Modified Julian Date (earliest plane). Null if no plane has timing.",
    "observation_end_mjd": "Observation end time as Modified Julian Date (latest plane)",
    "observation_start_date": "Observation start time as ISO-8601 UTC datetime (derived from MJD)",
    "observation_end_date": "Observation end time as ISO-8601 UTC datetime (derived from MJD)",
    "total_exposure_sec": "Sum of on-source exposure times across all planes for this observation, in seconds",
    "wavelength_min_meters": "Minimum wavelength covered across all planes, in meters (e.g., 6.0e-7 = 0.6 microns)",
    "wavelength_max_meters": "Maximum wavelength covered across all planes, in meters",
    "filters": "Semicolon-joined list of distinct bandpass/filter names used across planes (e.g., 'F200W;F356W')",
    "dataproduct_types": "Semicolon-joined list of distinct CAOM data product types: 'image', 'spectrum', 'cube', 'measurements'",
    "max_calibration_level": "Highest CAOM calibration level available for this observation (0 = raw, 1 = telemetry, 2 = calibrated, 3 = science-ready, 4 = higher-order products)",
    "plane_count": "Number of distinct planes (data products at different calibration levels) for this observation",
    "earliest_release_date": "Earliest public release date across planes (ISO-8601); exclusive-access observations become public at this date",
}

DESCRIPTION = """\
The JWST Observation Catalog is a complete index of every observation obtained by NASA/ESA/CSA's James Webb Space Telescope, drawn from the Mikulski Archive for Space Telescopes (MAST). Launched on December 25, 2021 and commissioned in mid-2022, JWST is the most powerful infrared space observatory ever built, operating at the Sun–Earth L2 Lagrange point with a 6.5-meter segmented primary mirror and four science instruments: NIRCam, NIRSpec, NIRISS, MIRI, and the FGS fine guidance sensor.

Each row in this catalog is one JWST observation — a unit of telescope time executing a single exposure sequence with a specific instrument, filter, target, and pointing. Rows include the proposal under which the observation was taken (proposal ID, PI, title, category: GO, GTO, ERS, or DDT), the target (name, coordinates, type, moving/fixed flag, redshift for extragalactic targets), the instrument and observing mode (imaging, slit/slitless spectroscopy, integral field, coronagraphy), timing (start/end MJD and ISO date, total on-source exposure), wavelength coverage (micrometers), filters used, the CAOM data product types produced, and the maximum calibration level available.

This dataset is the canonical source for answering questions like: what has JWST observed near a given RA/Dec? What proposals used the MIRI coronagraph? How much exposure time has been spent on a particular target? When does an exclusive-access dataset become public? It is designed for cross-matching with target catalogs (quasars, exoplanets, galaxies, solar system bodies), for program-level summaries, and for planning cross-facility follow-up observations. It complements the Chandra, eROSITA, Fermi, and other space telescope catalogs in this collection, giving a uniform tabular view of the modern high-energy-to-infrared space observatory fleet.

The catalog is derived from MAST's CAOM (Common Archive Observation Model) tables — specifically `dbo.caomobservation` joined with `dbo.caomplane` — and is refreshed weekly as JWST pipeline products flow through the archive. Calibration and engineering observations are included but are distinguishable via the `intent` column."""

def mjd_to_iso(mjd_series: pd.Series) -> pd.Series:
    """Convert MJD (float) to ISO-8601 UTC string. MJD 0 = 1858-11-17."""
    mjd = pd.to_numeric(mjd_series, errors="coerce")
    mjd_epoch = pd.Timestamp("1858-11-17", tz="UTC")
    dt = mjd_epoch + pd.to_timedelta(mjd, unit="D")
    return dt.dt.strftime("%Y-%m-%dT%H:%M:%SZ").where(mjd.notna(), pd.NA)


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    print("JWST Observation Catalog pipeline")

    df = load_checkpoint(CHECKPOINT_PATH)
    if df is not None:
        print("  Skipping MAST fetch — using checkpoint")
    else:
        df = _fetch_and_aggregate()
        save_checkpoint(CHECKPOINT_PATH, df)

    _transform_and_publish(df)


def _fetch_and_aggregate() -> pd.DataFrame:
    print("  Fetching caomobservation (observation-level metadata)...")
    obs = fetch_observations("JWST")
    print(f"  observations: {len(obs):,}")

    print("  Fetching caomplane (timing + wavelength per plane)...")
    planes = fetch_planes("JWST")
    print(f"  planes: {len(planes):,}")

    # ── Aggregate planes to one row per observation ─────────────────────
    print("  Aggregating planes per observation...")
    for c in ["timmin", "timmax", "timexposure", "enrmin", "enrmax",
              "calibrationlevel"]:
        planes[c] = pd.to_numeric(planes[c], errors="coerce")

    def _join_unique(s: pd.Series) -> str | None:
        vals = sorted({v for v in s.dropna() if v})
        return ";".join(vals) if vals else None

    agg = planes.groupby("observationuuid", sort=False).agg(
        observation_start_mjd=("timmin", "min"),
        observation_end_mjd=("timmax", "max"),
        total_exposure_sec=("timexposure", "sum"),
        wavelength_min_meters=("enrmin", "min"),
        wavelength_max_meters=("enrmax", "max"),
        filters=("enrbandpassname", _join_unique),
        dataproduct_types=("dataproducttype", _join_unique),
        max_calibration_level=("calibrationlevel", "max"),
        plane_count=("id", "count"),
        earliest_release_date=("releasedate", "min"),
    ).reset_index()

    # ── Merge observation + plane aggregate ─────────────────────────────
    return obs.merge(agg, left_on="id", right_on="observationuuid", how="left")


def _transform_and_publish(df: pd.DataFrame) -> None:
    # ── Rename + type coerce ────────────────────────────────────────────
    rename = {
        "observationid": "obs_id",
        "prpid": "proposal_id",
        "prppi": "proposal_pi",
        "prptitle": "proposal_title",
        "prpproject": "proposal_project",
        "prpkeywords": "proposal_keywords",
        "trgname": "target_name",
        "trgposra": "target_ra",
        "trgposdec": "target_dec",
        "trgmoving": "target_moving",
    }
    df = df.rename(columns=rename)

    # Split insname ("NIRCAM/IMAGE") into instrument + mode
    ins = df["insname"].fillna("").astype(str).str.split("/", n=1, expand=True)
    df["instrument"] = ins[0].replace("", pd.NA)
    df["observation_mode"] = ins[1].replace("", pd.NA) if ins.shape[1] > 1 else pd.NA

    # target_moving: "True"/"False"/"1"/"0"/None → bool
    def _to_bool(v):
        if pd.isna(v):
            return False
        s = str(v).strip().lower()
        return s in ("true", "1", "t", "yes")
    df["target_moving"] = df["target_moving"].map(_to_bool).astype(bool)

    # Derived ISO dates
    df["observation_start_date"] = mjd_to_iso(df["observation_start_mjd"])
    df["observation_end_date"] = mjd_to_iso(df["observation_end_mjd"])

    # Earliest release date — MAST returns MJD; convert to ISO-8601
    df["earliest_release_date"] = mjd_to_iso(df["earliest_release_date"])

    # Sort by start date descending (newest first)
    df = df.sort_values("observation_start_mjd", ascending=False, na_position="last").reset_index(drop=True)

    # ── Stats for README ────────────────────────────────────────────────
    n_total = len(df)
    n_science = int((df["intent"] == "science").sum())
    n_cal = int((df["intent"] == "calibration").sum())
    n_proposals = df["proposal_id"].nunique()
    total_exp_hours = df["total_exposure_sec"].sum() / 3600
    earliest = df["observation_start_date"].dropna().min()
    latest = df["observation_start_date"].dropna().max()

    quick_stats = f"""\
- **{n_total:,}** JWST observations
- **{n_science:,}** science, **{n_cal:,}** calibration
- **{n_proposals:,}** distinct proposals
- **{total_exp_hours:,.0f}** total on-source exposure hours
- Date range: **{earliest[:10] if earliest else '?'}** to **{latest[:10] if latest else '?'}**"""

    usage = f"""\
```python
from datasets import load_dataset

ds = load_dataset("{HF_REPO}", split="train")
df = ds.to_pandas()

# Science observations only
sci = df[df["intent"] == "science"]

# All NIRCam imaging on a specific target (cone search ~5 arcmin)
import numpy as np
target_ra, target_dec = 189.998, 62.183  # Hubble Deep Field North
sep = np.hypot(sci["target_ra"] - target_ra, sci["target_dec"] - target_dec)
nearby_nircam = sci[(sep < 0.08) & (sci["instrument"] == "NIRCAM") & (sci["observation_mode"] == "IMAGE")]
print(f"Found {{len(nearby_nircam)}} NIRCam images near HDF-N")

# Instrument usage over time
import matplotlib.pyplot as plt
sci["start_date"] = __import__("pandas").to_datetime(sci["observation_start_date"])
sci.groupby([sci["start_date"].dt.to_period("M"), "instrument"]).size().unstack().plot.area(figsize=(12, 5))
plt.ylabel("Observations per month")
plt.title("JWST instrument usage over time")
plt.show()

# Sky coverage (equatorial)
sky = sci[(sci["target_ra"] > 0) | (sci["target_dec"] != 0)]
plt.figure(figsize=(12, 6))
plt.scatter(sky["target_ra"], sky["target_dec"], s=0.5, alpha=0.3)
plt.xlabel("RA (deg)"); plt.ylabel("Dec (deg)")
plt.gca().invert_xaxis()
plt.title("JWST target sky distribution")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="JWST Observation Catalog",
        description=DESCRIPTION,
        tags=["space", "jwst", "james-webb", "nasa", "esa", "astronomy",
              "telescope", "infrared", "open-data", "tabular-data", "parquet"],
        source_url="https://archive.stsci.edu/",
        task_categories=["tabular-classification"],
        update_schedule="Weekly (Monday at 13:00 UTC) via [GitHub Actions](https://github.com/juliensimon/space-datasets).",
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e000354/GSFC_20171208_Archive_e000354~small.jpg",
            "alt": "The James Webb Space Telescope's primary mirror fully deployed in the clean room at NASA Goddard",
            "credit": "NASA/Desiree Stover",
        },
        related_datasets=[
            "juliensimon/chandra-x-ray-sources",
            "juliensimon/erosita-erass1-xray",
            "juliensimon/4xmm-dr14-xray-sources",
            "juliensimon/nasa-exoplanets",
            "juliensimon/quasar-catalog",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "target_ra", "target_dec",
                "observation_start_mjd", "observation_end_mjd",
                "total_exposure_sec", "wavelength_min_meters",
                "wavelength_max_meters",
            ],
            integer=["plane_count", "max_calibration_level"],
            strings=[
                "obs_id", "proposal_id", "proposal_pi", "proposal_title",
                "proposal_project", "proposal_keywords", "target_name",
                "instrument", "observation_mode", "intent",
                "obstype", "filters", "dataproduct_types",
                "observation_start_date", "observation_end_date",
                "earliest_release_date",
            ],
        )

        # Keep only described columns
        df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

        # Drop any fully-null columns (MAST sometimes has empty metadata fields
        # for JWST; we'd rather ship without them than fail validation)
        all_null = [c for c in df.columns if df[c].isna().all()]
        if all_null:
            print(f"  Warning: dropping fully-null columns: {all_null}")
            df = df.drop(columns=all_null)

        p.publish(
            df,
            filename="jwst_observations.parquet",
            min_rows=500_000,
            expected_columns=["obs_id", "proposal_id", "target_name",
                              "instrument", "intent"],
            critical_columns=["obs_id", "instrument", "intent"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update JWST observations: {n_total:,} observations",
        )
    print("Done.")


if __name__ == "__main__":
    main()
