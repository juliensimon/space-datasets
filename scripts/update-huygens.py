#!/usr/bin/env python3
"""Fetch ESA Huygens Titan descent observation catalog from PSA EPN-TAP and upload to HF.

Source: ESA Planetary Science Archive — EPN-TAP service
The Huygens probe descended through Titan's atmosphere on January 14, 2005.
"""

import sys
import time

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

TAP_URL = "https://psa.esa.int/psa-tap/tap/sync"
HF_REPO = "juliensimon/esa-huygens-titan-descent"

INSTRUMENTS = [
    "DISR", "GCMS", "HASI", "HUYGENS_HK", "SSP", "DTWG", "ACP", "DWE",
]

PAGE_SIZE = 500_000

# ── Column descriptions ─────────────────────────────────────────────
COLUMN_DESCRIPTIONS = {
    "granule_uid": "Unique observation/granule identifier in the PSA archive",
    "granule_gid": "Group identifier linking related granules from the same instrument or sequence",
    "obs_id": "Observation ID assigned by the instrument team",
    "dataproduct_type": "EPN-TAP data product type (e.g. 'sp' for spectrum, 'im' for image, 'pr' for profile, 'cu' for cube)",
    "target_name": "Target body name (primarily 'Titan'; descent lasted ~2.5 hours on Jan 14 2005)",
    "target_class": "EPN-TAP target class (e.g. 'satellite')",
    "instrument_host_name": "Name of the spacecraft hosting the instrument (Huygens)",
    "instrument_name": "Instrument name: DISR (descent imager), GCMS (gas chromatograph mass spectrometer), HASI (atmospheric structure), SSP (surface science package), ACP (aerosol collector), DWE (Doppler wind experiment), DTWG (descent trajectory), HUYGENS_HK (housekeeping)",
    "measurement_type": "Type of physical measurement (e.g. 'phot.flux' for photometry, 'phys.mass' for mass spectrometry)",
    "processing_level": "Data processing level (e.g. '2' = calibrated, '3' = derived)",
    "time_min": "Observation start time (Julian Date); Huygens descent spanned JD 2453384.88-2453385.00",
    "time_max": "Observation end time (Julian Date)",
    "time_sampling_step_min": "Minimum time sampling step (Julian Date units)",
    "time_sampling_step_max": "Maximum time sampling step (Julian Date units)",
    "time_exp_min": "Minimum exposure time (Julian Date units)",
    "time_exp_max": "Maximum exposure time (Julian Date units)",
    "spectral_range_min": "Spectral range lower bound (nm); for DISR optical measurements",
    "spectral_range_max": "Spectral range upper bound (nm); for DISR optical measurements",
    "c1min": "Spatial coordinate 1 lower bound (longitude in degrees, Titan surface 0-360 E)",
    "c1max": "Spatial coordinate 1 upper bound (longitude in degrees)",
    "c2min": "Spatial coordinate 2 lower bound (latitude in degrees, -90 to +90)",
    "c2max": "Spatial coordinate 2 upper bound (latitude in degrees)",
    "creation_date": "ISO 8601 date when this data product was created or archived in PSA",
    "modification_date": "ISO 8601 date when this data product was last modified in PSA",
    "release_date": "ISO 8601 date when this data product was publicly released",
    "service_title": "Title of the EPN-TAP service providing this data",
    "access_url": "Direct URL to retrieve the data product from the ESA PSA",
    "access_format": "MIME type of the data product (e.g. 'application/x-pds4' for PDS4 format)",
    "thumbnail_url": "URL to a thumbnail preview image of the data product",
    "bib_reference": "Bibliographic reference associated with this data product",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
In-situ observation catalog from the ESA Huygens probe descent through Titan's \
atmosphere and landing on January 14, 2005. This is the complete observation catalog \
from the ESA Planetary Science Archive (PSA), conforming to the EPN-TAP standard.

On January 14, 2005, the ESA Huygens probe made history as the first human-made \
object to land on a body in the outer Solar System. Released from the Cassini orbiter, \
Huygens descended through Titan's thick nitrogen-methane atmosphere for 2 hours 27 \
minutes, transmitting data from 160 km altitude down to the surface.

The Descent Imager/Spectral Radiometer (DISR) captured images revealing drainage \
channels, shorelines, and a landscape shaped by liquid methane. The Gas Chromatograph \
Mass Spectrometer (GCMS) analyzed atmospheric composition during descent, while the \
Huygens Atmospheric Structure Instrument (HASI) measured temperature, pressure, and \
density profiles. The Surface Science Package (SSP) recorded the impact and confirmed \
Huygens landed on a soft, damp surface — likely methane-saturated hydrocarbon sediment.

Each row represents one observation or data granule, with timing, spatial coverage, \
instrument parameters, and access URLs.
"""


def fetch_count() -> int:
    """Sanity-check: fetch total row count."""
    query = ("SELECT COUNT(*) AS n FROM epn_core "
             "WHERE instrument_host_name LIKE '%Huygens%'")
    print("Checking total row count...")
    resp = requests.get(TAP_URL, params={
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "json",
        "QUERY": query,
    }, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    cols = [m["name"] for m in data["metadata"]]
    rows = data["data"]
    n = int(rows[0][cols.index("n")])
    print(f"  Total rows in catalog: {n:,}")
    return n


def fetch_instrument(instrument: str) -> pd.DataFrame:
    """Fetch all rows for one instrument using granule_uid pagination."""
    print(f"  Fetching {instrument}...")
    all_dfs = []
    last_id = ""
    page = 0

    while True:
        query = (
            f"SELECT TOP {PAGE_SIZE} * FROM epn_core "
            f"WHERE instrument_host_name LIKE '%Huygens%' "
            f"AND instrument_name = '{instrument}' "
            f"AND granule_uid > '{last_id}' "
            f"ORDER BY granule_uid"
        )
        resp = requests.get(TAP_URL, params={
            "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "json",
            "QUERY": query,
        }, timeout=600)
        resp.raise_for_status()

        data = resp.json()
        cols = [m["name"] for m in data["metadata"]]
        rows = data["data"]

        if not rows:
            break

        df_page = pd.DataFrame(rows, columns=cols)
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
    print("Fetching ESA Huygens Titan descent observation catalog...")

    fetch_count()

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

    # Column cleanup
    df.columns = [c.strip().lower() for c in df.columns]

    # Numeric columns
    numeric_cols = [
        "time_min", "time_max", "time_sampling_step_min",
        "time_sampling_step_max", "time_exp_min", "time_exp_max",
        "spectral_range_min", "spectral_range_max",
        "c1min", "c1max", "c2min", "c2max",
    ]

    # String columns
    string_cols = [
        "granule_uid", "granule_gid", "obs_id",
        "dataproduct_type", "target_name", "target_class",
        "instrument_host_name", "instrument_name",
        "measurement_type", "processing_level",
        "creation_date", "modification_date", "release_date",
        "service_title", "access_url", "access_format",
        "thumbnail_url", "bib_reference",
    ]

    # Sort by observation start time
    if "time_min" in df.columns:
        df["time_min"] = pd.to_numeric(df["time_min"], errors="coerce")
        df = df.sort_values("time_min", na_position="last").reset_index(drop=True)

    # Keep only described columns (drop undescribed EPN-TAP columns)
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # ── Stats ────────────────────────────────────────────────────────
    n_total = len(df)
    n_instruments = df["instrument_name"].nunique()
    instruments_summary = df["instrument_name"].value_counts().head(8).to_dict()
    n_targets = df["target_name"].nunique() if "target_name" in df.columns else 0

    print(f"  {n_total:,} observations across {n_instruments} instruments")

    inst_lines = "\n".join(
        f"- **{inst}**: {count:,} observations"
        for inst, count in instruments_summary.items()
    )

    quick_stats = f"""\
- **{n_total:,}** total observations
- **{n_instruments}** instruments
- **{n_targets}** distinct targets
{inst_lines}"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/esa-huygens-titan-descent", split="train")
df = ds.to_pandas()

# Observations per instrument
print(df["instrument_name"].value_counts())

# DISR imaging observations
disr = df[df["instrument_name"] == "DISR"]
print(f"{len(disr):,} DISR observations")

# Observation counts by instrument
import matplotlib.pyplot as plt
df.groupby("instrument_name").size().sort_values(ascending=False).plot(kind="bar")
plt.title("Huygens observations by instrument")
plt.ylabel("Count")
plt.tight_layout()
plt.show()
```"""

    # Filter numeric/string cols to only those present and described
    numeric_cols = [c for c in numeric_cols if c in df.columns]
    string_cols = [c for c in string_cols if c in df.columns]

    with Pipeline(
        repo=HF_REPO,
        pretty_name="ESA Huygens Titan Descent",
        description=DESCRIPTION,
        tags=["space", "titan", "huygens", "cassini", "saturn", "esa",
              "planetary-science", "atmosphere",
              "open-data", "tabular-data", "parquet"],
        source_url="https://psa.esa.int/",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/solar-system-datasets-69c6fa681978de62dff2f347",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA06193/PIA06193~small.jpg",
            "alt": "Saturn and its rings, captured by the Cassini spacecraft",
            "credit": "NASA/JPL-Caltech/SSI",
        },
        related_datasets=[
            "juliensimon/cassini-saturn-observations",
            "juliensimon/huygens-titan-atmosphere",
            "juliensimon/galileo-jupiter-atmosphere",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=numeric_cols,
            strings=string_cols,
            drop_mostly_null_threshold=0.80,
        )
        p.publish(
            df,
            filename="huygens_observations.parquet",
            min_rows=5_000,
            expected_columns=["granule_uid", "instrument_name", "target_name",
                              "time_min", "time_max", "dataproduct_type"],
            critical_columns=["granule_uid", "instrument_name", "time_min"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Huygens Titan descent observations: {n_total:,} observations",
        )
    print("Done.")


if __name__ == "__main__":
    main()
