#!/usr/bin/env python3
"""Fetch ESA JUICE observation catalog from PSA EPN-TAP and upload to HF.

Source: ESA Planetary Science Archive (PSA) -- EPN-TAP service
https://psa.esa.int/

JUICE (Jupiter Icy Moons Explorer) is in its cruise phase; data volume is
moderate. Tries epn_core first, falls back to psa.product_ui_juice.
"""

import io
import shutil
import sys
import tempfile
import time
from pathlib import Path

import pandas as pd
import requests

from hf_dataset_utils import Pipeline
from hf_dataset_utils.banner import banner_markdown as render_banner
from hf_dataset_utils.banner import download_banner
from hf_dataset_utils.github import emit_output
from hf_dataset_utils.upload import upload_to_hf
from hf_dataset_utils.validation import check_dataset

TAP_URL = "https://psa.esa.int/psa-tap/tap/sync"
HF_REPO = "juliensimon/esa-juice-observations"

# JUICE instruments in order of expected catalog size
INSTRUMENTS = ["JMC", "RADEM", "HAA", "NAVCAM"]

PAGE_SIZE = 50_000

# ── Column descriptions ──────────────────────────────────────────────
COLUMN_DESCRIPTIONS = {
    "granule_uid": "Unique observation/granule identifier in the PSA archive; primary key for each data product",
    "granule_gid": "Group identifier linking related granules from the same instrument or sequence",
    "obs_id": "Observation ID assigned by the instrument team; groups related data products",
    "dataproduct_type": "EPN-TAP data product type (e.g. 'im' for image, 'sp' for spectrum, 'sc' for spectral cube)",
    "target_name": "Target body name during cruise phase (e.g. 'Solar Wind', 'Sun', 'Earth', 'Venus', 'Moon'); will include 'Jupiter', 'Ganymede', 'Europa', 'Callisto' after Jupiter arrival in 2031",
    "target_class": "EPN-TAP target class (e.g. 'interplanetary_medium', 'star', 'planet', 'satellite')",
    "instrument_host_name": "Spacecraft name; JUICE or Jupiter Icy Moons Explorer",
    "instrument_name": "Instrument name: JMC (JUICE monitoring camera, context images), RADEM (radiation/particle detector), HAA (heliospheric particle analyzer), NAVCAM (navigation camera)",
    "measurement_type": "Type of physical measurement performed",
    "processing_level": "Data processing level per PDS4 standard (e.g. '2' = calibrated, '3' = derived)",
    "time_min": "Observation start time (Julian Date); JUICE launched JD 2460048 (Apr 14 2023); Jupiter arrival JD ~2462957 (Jul 2031)",
    "time_max": "Observation end time (Julian Date)",
    "time_sampling_step_min": "Minimum time sampling step within the observation",
    "time_sampling_step_max": "Maximum time sampling step within the observation",
    "time_exp_min": "Minimum exposure time of the observation",
    "time_exp_max": "Maximum exposure time of the observation",
    "spectral_range_min": "Minimum wavelength of spectral coverage; units vary by instrument; null for non-spectral instruments",
    "spectral_range_max": "Maximum wavelength of spectral coverage",
    "spectral_sampling_step_min": "Minimum spectral sampling step",
    "spectral_sampling_step_max": "Maximum spectral sampling step",
    "spectral_resolution_min": "Minimum spectral resolution",
    "spectral_resolution_max": "Maximum spectral resolution",
    "c1min": "Spatial coordinate 1 minimum (longitude or RA in degrees)",
    "c1max": "Spatial coordinate 1 maximum",
    "c2min": "Spatial coordinate 2 minimum (latitude or declination in degrees)",
    "c2max": "Spatial coordinate 2 maximum",
    "c3min": "Spatial coordinate 3 minimum (distance or altitude)",
    "c3max": "Spatial coordinate 3 maximum",
    "c1_resol_min": "Spatial coordinate 1 resolution minimum",
    "c1_resol_max": "Spatial coordinate 1 resolution maximum",
    "c2_resol_min": "Spatial coordinate 2 resolution minimum",
    "c2_resol_max": "Spatial coordinate 2 resolution maximum",
    "c3_resol_min": "Spatial coordinate 3 resolution minimum",
    "c3_resol_max": "Spatial coordinate 3 resolution maximum",
    "s_region_lon_min": "Bounding box longitude minimum (degrees)",
    "s_region_lon_max": "Bounding box longitude maximum (degrees)",
    "s_region_lat_min": "Bounding box latitude minimum (degrees)",
    "s_region_lat_max": "Bounding box latitude maximum (degrees)",
    "incidence_min": "Minimum solar incidence angle (degrees)",
    "incidence_max": "Maximum solar incidence angle (degrees)",
    "emergence_min": "Minimum emission/emergence angle (degrees)",
    "emergence_max": "Maximum emission/emergence angle (degrees)",
    "phase_min": "Minimum phase angle (degrees)",
    "phase_max": "Maximum phase angle (degrees)",
    "ra_min": "Right ascension minimum (degrees)",
    "ra_max": "Right ascension maximum (degrees)",
    "dec_min": "Declination minimum (degrees)",
    "dec_max": "Declination maximum (degrees)",
    "solar_longitude_min": "Solar longitude minimum (degrees)",
    "solar_longitude_max": "Solar longitude maximum (degrees)",
    "sun_distance_min": "Minimum heliocentric distance (AU)",
    "sun_distance_max": "Maximum heliocentric distance (AU)",
    "target_distance_min": "Minimum spacecraft-to-target distance (km)",
    "target_distance_max": "Maximum spacecraft-to-target distance (km)",
    "subsolar_longitude_min": "Sub-solar longitude minimum (degrees)",
    "subsolar_longitude_max": "Sub-solar longitude maximum (degrees)",
    "subsolar_latitude_min": "Sub-solar latitude minimum (degrees)",
    "subsolar_latitude_max": "Sub-solar latitude maximum (degrees)",
    "subobserver_longitude_min": "Sub-observer longitude minimum (degrees)",
    "subobserver_longitude_max": "Sub-observer longitude maximum (degrees)",
    "subobserver_latitude_min": "Sub-observer latitude minimum (degrees)",
    "subobserver_latitude_max": "Sub-observer latitude maximum (degrees)",
    "local_time_min": "Local solar time minimum (hours)",
    "local_time_max": "Local solar time maximum (hours)",
    "creation_date": "ISO 8601 date when this data product was created or archived in PSA",
    "modification_date": "ISO 8601 date when this data product was last modified",
    "release_date": "ISO 8601 date when this data product was publicly released",
    "service_title": "Title of the TAP service providing this record",
    "access_url": "Direct URL to retrieve the data product from the ESA PSA",
    "access_format": "MIME type of the data product (e.g. 'application/x-pds4' for PDS4 format)",
    "thumbnail_url": "URL of a thumbnail preview image, if available",
    "bib_reference": "Bibliographic reference for the data product or instrument",
}

DESCRIPTION = """\
Observation metadata catalog from ESA's JUICE (Jupiter Icy Moons Explorer) mission.

JUICE is ESA's flagship mission to the Jovian system, launched April 14, 2023. After \
gravity assists at Earth-Moon (August 2024), Venus (August 2025), and Earth (September \
2026, January 2029), JUICE will arrive at Jupiter in July 2031 for a 3.5-year tour of \
the Galilean moons. The primary science target is Ganymede -- the only moon with its own \
magnetic field -- where JUICE will enter orbit in December 2034, becoming the first \
spacecraft to orbit a moon other than Earth's. The mission will characterize the \
subsurface oceans of Ganymede, Europa, and Callisto, assess their habitability, and study \
Jupiter's atmosphere and magnetosphere.

During the cruise phase, instruments are collecting calibration data and science \
observations during planetary flybys. Currently available data includes radiation \
measurements (RADEM), monitoring camera images (JMC), and heliospheric particle data \
(HAA). The dataset will grow dramatically as JUICE approaches Jupiter and begins its \
science phase.

Each row represents one observation or data granule from the ESA Planetary Science \
Archive (PSA), conforming to the EPN-TAP standard, with timing, spatial coverage, \
instrument parameters, and access URLs."""


# ── TAP query helpers ────────────────────────────────────────────────

NUMERIC_COLS = [
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

STRING_COLS = [
    "granule_uid", "granule_gid", "obs_id",
    "dataproduct_type", "target_name", "target_class",
    "instrument_host_name", "instrument_name",
    "measurement_type", "processing_level",
    "creation_date", "modification_date", "release_date",
    "service_title", "access_url", "access_format",
    "thumbnail_url", "bib_reference",
]


def try_epn_core() -> bool:
    """Try a COUNT query on epn_core to see if it responds in time."""
    query = ("SELECT COUNT(*) AS n FROM epn_core "
             "WHERE instrument_host_name LIKE '%JUICE%'")
    print("Testing epn_core availability...")
    try:
        resp = requests.get(TAP_URL, params={
            "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "json",
            "QUERY": query,
        }, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        cols = [m["name"] for m in data["metadata"]]
        n = int(data["data"][0][cols.index("n")])
        print(f"  epn_core returns {n:,} JUICE rows")
        return n > 0
    except (requests.exceptions.Timeout, requests.exceptions.RequestException) as e:
        print(f"  epn_core query failed: {e}")
        return False


def _tap_csv(query: str, max_retries: int = 5) -> pd.DataFrame:
    """TAP query returning CSV, with retry + exponential backoff."""
    for attempt in range(max_retries):
        try:
            resp = requests.get(TAP_URL, params={
                "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv",
                "QUERY": query,
            }, timeout=300, stream=True)
            resp.raise_for_status()
            return pd.read_csv(io.StringIO(resp.text), low_memory=False)
        except (requests.ConnectionError, requests.Timeout,
                requests.exceptions.ChunkedEncodingError):
            if attempt == max_retries - 1:
                raise
            wait = 10 * (2 ** attempt)
            print(f"    Connection error (attempt {attempt + 1}), retrying in {wait}s...")
            time.sleep(wait)


def fetch_epn_core(parquet_dir: Path) -> dict:
    """Fetch all JUICE rows from epn_core, paginated by granule_uid.

    Returns dict of {instrument: row_count}.
    """
    print("Fetching from epn_core...")
    instrument_counts = {}
    last_id = ""
    page = 0

    while True:
        query = (
            f"SELECT TOP {PAGE_SIZE} * FROM epn_core "
            f"WHERE instrument_host_name LIKE '%JUICE%' "
            f"AND granule_uid > '{last_id}' "
            f"ORDER BY granule_uid"
        )
        df_page = _tap_csv(query)
        if len(df_page) == 0:
            break

        page += 1
        print(f"  Page {page}: {len(df_page):,} rows")

        # Write one part file per page
        part_path = parquet_dir / f"all_part{page:04d}.parquet"
        df_page.to_parquet(part_path, index=False, engine="pyarrow", compression="zstd")

        # Track per-instrument counts
        df_page.columns = [c.strip().lower() for c in df_page.columns]
        if "instrument_name" in df_page.columns:
            for inst, cnt in df_page["instrument_name"].value_counts().items():
                instrument_counts[inst] = instrument_counts.get(inst, 0) + cnt

        df_check = pd.read_parquet(part_path, columns=["granule_uid"])
        last_id = str(df_check["granule_uid"].iloc[-1])
        row_count = len(df_check)
        del df_check, df_page

        if row_count < PAGE_SIZE:
            break
        time.sleep(1)

    return instrument_counts


def fetch_product_ui_juice(parquet_dir: Path) -> dict:
    """Fallback: fetch from psa.product_ui_juice table."""
    print("Falling back to psa.product_ui_juice...")
    instrument_counts = {}
    offset = 0
    page = 0

    while True:
        query = (
            f"SELECT TOP {PAGE_SIZE} * FROM psa.product_ui_juice "
            f"WHERE 1=1 "
            f"OFFSET {offset}"
        )
        df_page = _tap_csv(query)
        if len(df_page) == 0:
            break

        page += 1
        print(f"  Page {page}: {len(df_page):,} rows")

        part_path = parquet_dir / f"all_part{page:04d}.parquet"
        df_page.to_parquet(part_path, index=False, engine="pyarrow", compression="zstd")

        df_page.columns = [c.strip().lower() for c in df_page.columns]
        if "instrument_name" in df_page.columns:
            for inst, cnt in df_page["instrument_name"].value_counts().items():
                instrument_counts[inst] = instrument_counts.get(inst, 0) + cnt

        if len(df_page) < PAGE_SIZE:
            del df_page
            break

        offset += PAGE_SIZE
        del df_page
        time.sleep(1)

    return instrument_counts


def _clean_chunk(df: pd.DataFrame) -> pd.DataFrame:
    """Apply column cleanup to a DataFrame chunk."""
    df.columns = [c.strip().lower() for c in df.columns]

    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in STRING_COLS:
        if col in df.columns:
            df[col] = (df[col].astype(str).str.strip()
                       .replace({"": pd.NA, "None": pd.NA,
                                 "nan": pd.NA, "null": pd.NA}))

    # Drop undescribed columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    return df


# ── Main ─────────────────────────────────────────────────────────────

def main():
    print("Fetching ESA JUICE observation catalog...")

    parts_dir = Path(tempfile.mkdtemp(prefix="juice_parts_"))
    instrument_counts = {}

    # Strategy 1: try epn_core
    if try_epn_core():
        instrument_counts = fetch_epn_core(parts_dir)
        time.sleep(2)

    # Strategy 2: fallback to product_ui_juice
    if not instrument_counts:
        print("epn_core returned no data, trying product_ui_juice...")
        instrument_counts = fetch_product_ui_juice(parts_dir)

    total_rows = sum(instrument_counts.values())
    if total_rows == 0:
        print("::error::No data fetched from either source")
        sys.exit(1)

    print(f"  Total fetched: {total_rows:,} rows")
    for inst, count in instrument_counts.items():
        print(f"    {inst}: {count:,}")

    # Determine columns to drop (>95% null) from a sample
    first_part = sorted(parts_dir.glob("*.parquet"))[0]
    sample = pd.read_parquet(first_part)
    sample.columns = [c.strip().lower() for c in sample.columns]
    drop_cols = [col for col in sample.columns if sample[col].isna().mean() > 0.95]
    del sample
    if drop_cols:
        print(f"  Dropping {len(drop_cols)} columns (>95% null)")

    with Pipeline(
        repo=HF_REPO,
        pretty_name="ESA JUICE Observations",
        description=DESCRIPTION,
        tags=["space", "jupiter", "juice", "ganymede", "europa", "callisto",
              "esa", "planetary-science", "open-data", "tabular-data", "parquet"],
        source_url="https://psa.esa.int/",
        license="other",
        license_name="cc-by-nc-3.0-igo",
        license_link="https://creativecommons.org/licenses/by-nc/3.0/igo/",
        task_categories=["tabular-classification"],
        update_schedule="Weekly (Monday at 10:00 UTC)",
        collection_url="https://huggingface.co/collections/juliensimon/space-probe-and-mission-datasets-69c3fe82d410a42b1e313167",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA00600/PIA00600~small.jpg",
            "alt": "Jupiter's Great Red Spot and the Galilean satellites",
            "credit": "NASA/JPL-Caltech",
        },
        related_datasets=[
            "juliensimon/esa-rosetta-observations",
            "juliensimon/esa-bepicolombo-observations",
            "juliensimon/galileo-jupiter-atmosphere",
            "juliensimon/solar-system-moons",
        ],
    ) as p:
        # Process all part files, cleaning and writing to data dir
        time_mins, time_maxs = [], []
        all_targets = set()
        total_clean_rows = 0
        total_size = 0

        part_files = sorted(parts_dir.glob("*.parquet"))
        for i, pf in enumerate(part_files):
            chunk = pd.read_parquet(pf)
            chunk = _clean_chunk(chunk)
            chunk = chunk.drop(
                columns=[c for c in drop_cols if c in chunk.columns],
                errors="ignore")

            if "time_min" in chunk.columns:
                time_mins.append(chunk["time_min"].min())
                time_maxs.append(chunk["time_max"].max() if "time_max" in chunk.columns else float("nan"))
            if "target_name" in chunk.columns:
                all_targets.update(chunk["target_name"].dropna().unique()[:20])

            out = p.data_dir / f"part{i:04d}.parquet"
            chunk.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
            total_clean_rows += len(chunk)
            total_size += out.stat().st_size
            del chunk

        n_total = total_clean_rows
        n_instruments = len(instrument_counts)
        n_targets = len(all_targets)
        time_range_min = min(time_mins) if time_mins else 0
        time_range_max = max(time_maxs) if time_maxs else 0
        total_mb = total_size / 1024 / 1024
        print(f"  {n_total:,} observations across {n_instruments} instruments, {total_mb:.1f} MB total")

        # Validate using a sample part
        sample_parts = sorted(p.data_dir.rglob("*.parquet"))
        if sample_parts:
            df_sample = pd.read_parquet(sample_parts[0])
            expected = [c for c in ["granule_uid", "instrument_name", "target_name",
                                     "time_min", "time_max", "dataproduct_type"]
                        if c in df_sample.columns]
            critical = [c for c in ["granule_uid", "instrument_name", "time_min"]
                        if c in df_sample.columns]
            check_dataset(df_sample, "juice", min_rows=1,
                          expected_columns=expected,
                          critical_columns=critical)
            del df_sample
        if n_total < 1_000:
            print(f"::error::Only {n_total:,} rows -- expected at least 1,000")
            sys.exit(1)

        # Instrument breakdown for README
        inst_lines = "\n".join(
            f"- **{inst}**: {count:,} observations"
            for inst, count in instrument_counts.items()
        )

        time_info = ""
        if time_range_min and time_range_max:
            time_info = f"\n- Time span: JD {time_range_min:.1f} -- {time_range_max:.1f}"

        quick_stats = f"""\
- **{n_total:,}** total observations
- **{n_instruments}** instruments
- **{n_targets}** distinct targets{time_info}"""

        usage = f"""\
```python
from datasets import load_dataset

ds = load_dataset("{HF_REPO}", split="train")
df = ds.to_pandas()

# Observations per instrument
print(df["instrument_name"].value_counts())

# RADEM radiation measurements
radem = df[df["instrument_name"] == "RADEM"]
print(f"{{len(radem):,}} RADEM observations")

# Observations per target
print(df["target_name"].value_counts())

# Timeline of observations
import matplotlib.pyplot as plt
df["time_min"].hist(bins=50, figsize=(10, 4))
plt.xlabel("Julian Date")
plt.ylabel("Count")
plt.title("JUICE observation density over time")
plt.show()
```"""

        # Build custom README
        from hf_dataset_utils.readme import _size_category, _citation_bibtex, _yaml_escape, _yaml_tag
        size_cat = _size_category(n_total)
        safe_name = _yaml_escape(p.pretty_name)
        short_desc = _yaml_escape(p.description[:200])
        tags_yaml = "\n".join(f"  - {_yaml_tag(t)}" for t in p.tags)
        task_yaml = "\n".join(f"  - {_yaml_tag(t)}" for t in (p.task_categories or ["other"]))

        # Banner
        banner_md = None
        if p.banner:
            banner_file = download_banner(p.banner["url"], p.tmp_dir)
            if banner_file:
                banner_md = render_banner(
                    p.banner.get("alt", ""),
                    p.banner.get("credit", ""),
                    filename=banner_file,
                )

        readme_text = f"""---
license: {p.license}
pretty_name: "{safe_name}"
language:
  - en
description: "{short_desc}"
task_categories:
{task_yaml}
tags:
{tags_yaml}
size_categories:
  - {size_cat}
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/*.parquet
    default: true
---

# {p.pretty_name}
{banner_md or ''}
*Part of a [dataset collection]({p.collection_url}) on Hugging Face.*

## Dataset description

{p.description}

## Instruments

{inst_lines}

## Quick stats

{quick_stats}

## Usage

{usage}

## Data source

[ESA Planetary Science Archive]({p.source_url}) -- EPN-TAP service at
`https://psa.esa.int/psa-tap/tap/sync`.

## Update schedule

{p.update_schedule}

## Related datasets

{chr(10).join(f'- [{ds}](https://huggingface.co/datasets/{ds})' for ds in (p.related_datasets or []))}

## Citation

{_citation_bibtex(p.repo, p.pretty_name)}

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
"""
        (p.tmp_dir / "README.md").write_text(readme_text)

        # Upload
        print("Uploading to HF...")
        upload_to_hf(p.repo, p.tmp_dir,
                      f"Update JUICE observations: {n_total:,} observations")
        emit_output(rows=n_total)

    # Clean up parts
    shutil.rmtree(parts_dir, ignore_errors=True)
    print("Done.")


if __name__ == "__main__":
    main()
