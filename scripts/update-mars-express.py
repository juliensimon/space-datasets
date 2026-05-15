#!/usr/bin/env python3
"""Fetch ESA Mars Express observation catalog from PSA EPN-TAP and upload to HF.

Source: ESA Planetary Science Archive — EPN-TAP service.
Mars Express has been studying Mars since December 2003 with 8 instruments.
"""

import io
import sys
import time

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

TAP_URL = "https://psa.esa.int/psa-tap/tap/sync"
HF_REPO = "juliensimon/esa-mars-express-observations"

# Mars Express instruments in order of expected catalog size
INSTRUMENTS = [
    "ASPERA-3",
    "HRSC",
    "VMC",
    "MaRS",
    "PFS",
    "SPICAM",
    "MARSIS",
    "OMEGA",
]

PAGE_SIZE = 500_000

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "granule_uid": "Unique observation/granule identifier in the PSA archive; primary key for each data product",
    "granule_gid": "Group identifier linking related granules from the same instrument sequence or observation campaign",
    "obs_id": "Observation ID assigned by the instrument team; format varies by instrument",
    "dataproduct_type": "EPN-TAP data product type: 'sp' (spectrum), 'im' (image), 'pr' (profile), 'cu' (cube), 'vo' (visibility/occultation)",
    "target_name": "Target body name: primarily 'Mars', also 'Phobos', 'Deimos', or 'Solar Wind' for ASPERA-3 plasma measurements",
    "target_class": "EPN-TAP target class: 'planet', 'satellite' (for Phobos/Deimos), or 'interplanetary_medium'",
    "instrument_host_name": "Always 'Mars Express' -- the ESA spacecraft that has been orbiting Mars since December 2003",
    "instrument_name": "Instrument name: HRSC (stereo camera, ~10 m/pixel), MARSIS (subsurface radar), OMEGA (mineralogy spectrometer 0.4-5 um), PFS (Fourier spectrometer), SPICAM (UV/IR spectrometer), ASPERA-3 (plasma analyzer), MaRS (radio science), VMC (visual monitoring camera)",
    "measurement_type": "Physical quantity measured (e.g. 'phot.flux.density', 'phys.electron', 'pos.distance'); follows IVOA Unified Content Descriptors",
    "processing_level": "Data processing level: '2' (calibrated), '3' (derived), '5' (partially processed) per PDS4 standard",
    "time_min": "Observation start time as Julian Date (days since Jan 1 4713 BC noon); Mars Express arrived at JD ~2452998 (Dec 2003)",
    "time_max": "Observation end time as Julian Date; observation durations range from seconds (VMC images) to hours (MARSIS passes)",
    "time_sampling_step_min": "Minimum time sampling interval within the observation in days; null for single-point measurements",
    "time_sampling_step_max": "Maximum time sampling interval within the observation in days",
    "time_exp_min": "Minimum exposure or integration time in days; relevant for imaging instruments (HRSC, VMC)",
    "time_exp_max": "Maximum exposure or integration time in days",
    "spectral_range_min": "Lower bound of spectral coverage in Hz; null for non-spectral instruments like VMC",
    "spectral_range_max": "Upper bound of spectral coverage in Hz",
    "spectral_sampling_step_min": "Minimum spectral sampling step in Hz",
    "spectral_sampling_step_max": "Maximum spectral sampling step in Hz",
    "spectral_resolution_min": "Minimum spectral resolving power (dimensionless ratio)",
    "spectral_resolution_max": "Maximum spectral resolving power",
    "c1min": "Spatial coordinate 1 lower bound: longitude in degrees (0-360 E) for Mars surface observations",
    "c1max": "Spatial coordinate 1 upper bound: longitude in degrees (0-360 E)",
    "c2min": "Spatial coordinate 2 lower bound: latitude in degrees (-90 to +90) for Mars surface observations",
    "c2max": "Spatial coordinate 2 upper bound: latitude in degrees",
    "c3min": "Spatial coordinate 3 lower bound: altitude or radial distance in km where applicable",
    "c3max": "Spatial coordinate 3 upper bound in km",
    "c1_resol_min": "Minimum spatial resolution in coordinate 1 (degrees longitude)",
    "c1_resol_max": "Maximum spatial resolution in coordinate 1",
    "c2_resol_min": "Minimum spatial resolution in coordinate 2 (degrees latitude)",
    "c2_resol_max": "Maximum spatial resolution in coordinate 2",
    "c3_resol_min": "Minimum spatial resolution in coordinate 3 (km)",
    "c3_resol_max": "Maximum spatial resolution in coordinate 3",
    "s_region_lon_min": "Minimum longitude of the spatial footprint region in degrees",
    "s_region_lon_max": "Maximum longitude of the spatial footprint region in degrees",
    "s_region_lat_min": "Minimum latitude of the spatial footprint region in degrees",
    "s_region_lat_max": "Maximum latitude of the spatial footprint region in degrees",
    "incidence_min": "Minimum solar incidence angle in degrees (0 = subsolar point, 90 = terminator)",
    "incidence_max": "Maximum solar incidence angle in degrees",
    "emergence_min": "Minimum emergence (emission) angle in degrees (0 = nadir viewing)",
    "emergence_max": "Maximum emergence angle in degrees",
    "phase_min": "Minimum phase angle in degrees (Sun-target-observer geometry)",
    "phase_max": "Maximum phase angle in degrees",
    "ra_min": "Minimum right ascension of the observation pointing in degrees (celestial coordinates)",
    "ra_max": "Maximum right ascension in degrees",
    "dec_min": "Minimum declination of the observation pointing in degrees",
    "dec_max": "Maximum declination in degrees",
    "solar_longitude_min": "Minimum Mars solar longitude (Ls) in degrees; tracks Martian seasons: 0 = northern spring equinox, 90 = summer solstice, 270 = winter solstice",
    "solar_longitude_max": "Maximum Mars solar longitude (Ls) in degrees",
    "sun_distance_min": "Minimum Sun-Mars distance during observation in AU",
    "sun_distance_max": "Maximum Sun-Mars distance in AU",
    "target_distance_min": "Minimum spacecraft-to-target distance in km during observation",
    "target_distance_max": "Maximum spacecraft-to-target distance in km",
    "subsolar_longitude_min": "Minimum sub-solar longitude on Mars surface in degrees",
    "subsolar_longitude_max": "Maximum sub-solar longitude in degrees",
    "subsolar_latitude_min": "Minimum sub-solar latitude on Mars surface in degrees",
    "subsolar_latitude_max": "Maximum sub-solar latitude in degrees",
    "subobserver_longitude_min": "Minimum sub-observer (sub-spacecraft) longitude on Mars in degrees",
    "subobserver_longitude_max": "Maximum sub-observer longitude in degrees",
    "subobserver_latitude_min": "Minimum sub-observer latitude on Mars in degrees",
    "subobserver_latitude_max": "Maximum sub-observer latitude in degrees",
    "local_time_min": "Minimum local solar time at the observation footprint in hours (0-24)",
    "local_time_max": "Maximum local solar time in hours",
    "creation_date": "ISO 8601 date when this data product was created or archived in the PSA",
    "modification_date": "ISO 8601 date when this data product was last modified in the PSA",
    "release_date": "ISO 8601 date when this data product was publicly released",
    "service_title": "Title of the TAP service providing this record",
    "access_url": "Direct URL to retrieve the data product from the ESA Planetary Science Archive",
    "access_format": "MIME type of the data product (e.g. 'application/x-pds4' for PDS4, 'application/fits' for FITS files)",
    "thumbnail_url": "URL of a thumbnail preview image for this observation; null for non-imaging data products",
    "bib_reference": "Bibliographic reference or DOI for the instrument paper or data description document",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Complete observation metadata catalog from the ESA Mars Express mission -- one of the \
longest-running and most scientifically productive Mars orbiters. Mars Express entered \
Mars orbit in December 2003 and carries a suite of 8 instruments: HRSC (high-resolution \
stereo camera), MARSIS (subsurface radar sounder), OMEGA (mineralogy spectrometer), PFS \
(planetary Fourier spectrometer), SPICAM (UV/IR spectrometer), ASPERA-3 (plasma analyzer), \
MaRS (radio science experiment), and VMC (visual monitoring camera).

This dataset contains the full observation metadata from the ESA Planetary Science Archive \
(PSA), conforming to the EPN-TAP standard. Each row represents one observation or data \
granule, with timing, spatial coverage, instrument parameters, and access URLs.

HRSC has produced the most complete high-resolution stereo topographic map of Mars. MARSIS \
detected reflections consistent with liquid water beneath the south polar layered deposits. \
OMEGA mapped global mineralogy including phyllosilicates and sulfates constraining climatic \
history. The 20+ year temporal baseline captures multiple complete Martian years of atmospheric \
monitoring, seasonal polar cap evolution, dust storm cycles, and surface changes.
"""


def _tap_csv(query: str, retries: int = 4) -> pd.DataFrame:
    """PSA TAP query using CSV format with exponential-backoff retry."""
    for attempt in range(retries):
        try:
            resp = requests.get(TAP_URL, params={
                "REQUEST": "doQuery", "LANG": "ADQL",
                "FORMAT": "csv", "QUERY": query,
            }, timeout=600)
            resp.raise_for_status()
            text = resp.text.strip()
            if text.startswith("<"):
                raise ValueError(f"TAP returned XML instead of CSV: {text[:200]}")
            return pd.read_csv(io.StringIO(text))
        except Exception as e:
            if attempt < retries - 1:
                wait = 20 * (2 ** attempt)
                print(f"    TAP error (attempt {attempt + 1}/{retries}): {e}; retry in {wait}s")
                time.sleep(wait)
            else:
                raise
    return pd.DataFrame()  # unreachable


def fetch_count() -> int:
    """Sanity-check: fetch total row count."""
    query = ("SELECT COUNT(*) AS n FROM epn_core "
             "WHERE instrument_host_name = 'Mars Express'")
    print("Checking total row count...")
    df = _tap_csv(query)
    n = int(df["n"].iloc[0])
    print(f"  Total rows in catalog: {n:,}")
    return n


def fetch_instrument(instrument: str) -> pd.DataFrame:
    """Fetch all rows for one instrument using granule_uid pagination with CSV."""
    print(f"  Fetching {instrument}...")
    all_dfs = []
    last_id = ""
    page = 0

    while True:
        query = (
            f"SELECT TOP {PAGE_SIZE} * FROM epn_core "
            f"WHERE instrument_host_name = 'Mars Express' "
            f"AND instrument_name = '{instrument}' "
            f"AND granule_uid > '{last_id}' "
            f"ORDER BY granule_uid"
        )
        df_page = _tap_csv(query)

        if df_page.empty:
            break

        all_dfs.append(df_page)
        page += 1
        print(f"    Page {page}: {len(df_page):,} rows")

        if len(df_page) < PAGE_SIZE:
            break

        last_id = str(df_page["granule_uid"].iloc[-1])
        time.sleep(1)

    if not all_dfs:
        print(f"    WARNING: No rows for {instrument}")
        return pd.DataFrame()

    df = pd.concat(all_dfs, ignore_index=True)
    print(f"    {instrument} total: {len(df):,} rows")
    return df


def main():
    print("Fetching ESA Mars Express observation catalog...")

    # Verify expected size
    fetch_count()

    # Fetch per instrument, then concatenate
    dfs = []
    for inst in INSTRUMENTS:
        df_inst = fetch_instrument(inst)
        if len(df_inst) > 0:
            dfs.append(df_inst)
        time.sleep(2)

    if not dfs:
        print("::error::No data fetched")
        sys.exit(1)

    df = pd.concat(dfs, ignore_index=True)
    print(f"  Total fetched: {len(df):,} rows")

    # ── Column cleanup ────────────────────────────────────────────────
    df.columns = [c.strip().lower() for c in df.columns]

    # Sort by observation start time
    df = df.sort_values("time_min", na_position="last").reset_index(drop=True)

    # ── Stats ─────────────────────────────────────────────────────────
    n_total = len(df)
    n_instruments = df["instrument_name"].nunique()
    instruments_summary = df["instrument_name"].value_counts().head(8).to_dict()
    n_targets = df["target_name"].nunique() if "target_name" in df.columns else 0
    time_range_min = df["time_min"].min()
    time_range_max = df["time_max"].max()

    print(f"  {n_total:,} observations across {n_instruments} instruments")
    for inst, count in instruments_summary.items():
        print(f"    {inst}: {count:,}")

    # Keep only described columns (drop undescribed EPN-TAP internal fields)
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    inst_lines = "\n".join(
        f"- **{inst}**: {count:,} observations"
        for inst, count in instruments_summary.items()
    )

    quick_stats = f"""\
- **{n_total:,}** total observations
- **{n_instruments}** instruments
- **{n_targets}** distinct targets
- Time span: JD {time_range_min:.1f} -- {time_range_max:.1f}

### Instruments

{inst_lines}"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/esa-mars-express-observations", split="train")
df = ds.to_pandas()

# Observations per instrument
print(df["instrument_name"].value_counts())

# HRSC images
hrsc = df[df["instrument_name"] == "HRSC"]
print(f"{len(hrsc):,} HRSC observations")

# Timeline of observations by year
import matplotlib.pyplot as plt
df["year"] = ((df["time_min"] - 2451545.0) / 365.25 + 2000).astype(int)
df.groupby(["year", "instrument_name"]).size().unstack().plot(kind="bar", stacked=True)
plt.title("Mars Express observations per year")
plt.ylabel("Count")
plt.tight_layout()
plt.show()
```"""

    # Numeric columns for coercion
    numeric_cols = [
        "time_min", "time_max", "time_sampling_step_min",
        "time_sampling_step_max", "time_exp_min", "time_exp_max",
        "spectral_range_min", "spectral_range_max",
        "spectral_sampling_step_min", "spectral_sampling_step_max",
        "spectral_resolution_min", "spectral_resolution_max",
        "c1min", "c1max", "c2min", "c2max", "c3min", "c3max",
        "c1_resol_min", "c1_resol_max", "c2_resol_min", "c2_resol_max",
        "c3_resol_min", "c3_resol_max",
        "s_region_lon_min", "s_region_lon_max",
        "s_region_lat_min", "s_region_lat_max",
        "incidence_min", "incidence_max",
        "emergence_min", "emergence_max",
        "phase_min", "phase_max",
        "ra_min", "ra_max", "dec_min", "dec_max",
        "solar_longitude_min", "solar_longitude_max",
        "sun_distance_min", "sun_distance_max",
        "target_distance_min", "target_distance_max",
        "subsolar_longitude_min", "subsolar_longitude_max",
        "subsolar_latitude_min", "subsolar_latitude_max",
        "subobserver_longitude_min", "subobserver_longitude_max",
        "subobserver_latitude_min", "subobserver_latitude_max",
        "local_time_min", "local_time_max",
    ]
    numeric_cols = [c for c in numeric_cols if c in df.columns]

    string_cols = [
        "granule_uid", "granule_gid", "obs_id",
        "dataproduct_type", "target_name", "target_class",
        "instrument_host_name", "instrument_name",
        "measurement_type", "processing_level",
        "creation_date", "modification_date", "release_date",
        "service_title", "access_url", "access_format",
        "thumbnail_url", "bib_reference",
    ]
    string_cols = [c for c in string_cols if c in df.columns]

    with Pipeline(
        repo=HF_REPO,
        pretty_name="ESA Mars Express Observations",
        description=DESCRIPTION,
        tags=["space", "mars", "mars-express", "esa", "planetary-science",
              "open-data", "tabular-data", "parquet"],
        source_url="https://psa.esa.int/",
        update_schedule="Weekly (Monday at 07:00 UTC) via [GitHub Actions](https://github.com/juliensimon/space-datasets).",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/space-probe-and-mission-datasets-69c3fe82d410a42b1e313167",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA24309/PIA24309~small.jpg",
            "alt": "Exploring Jezero Crater on Mars (illustration)",
            "credit": "NASA/JPL-Caltech",
        },
        related_datasets=[
            "juliensimon/esa-exomars-tgo-observations",
            "juliensimon/nasa-maven-kp-insitu",
            "juliensimon/nasa-mars-rover-images",
            "juliensimon/mars-craters-robbins",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=numeric_cols,
            strings=string_cols,
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="mars_express_observations.parquet",
            min_rows=1_000_000,
            expected_columns=["granule_uid", "instrument_name", "target_name",
                              "time_min", "time_max", "dataproduct_type"],
            critical_columns=["granule_uid", "instrument_name", "time_min"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Mars Express observations: {n_total:,} observations",
        )
    print("Done.")


if __name__ == "__main__":
    main()
