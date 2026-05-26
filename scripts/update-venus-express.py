#!/usr/bin/env python3
"""Fetch ESA Venus Express observation catalog from PSA EPN-TAP and upload to HF.

Source: ESA Planetary Science Archive (PSA) -- EPN-TAP service
https://psa.esa.int/

Multi-instrument dataset. Data is written per-instrument as partitioned parquet
files to keep memory bounded.
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
HF_REPO = "juliensimon/esa-venus-express-observations"

# Venus Express instruments in order of expected catalog size
INSTRUMENTS = [
    "ASPERA-4", "MAG", "SPICAV", "VIRTIS", "VeRa", "VMC",
]

PAGE_SIZE = 500_000

# ── Column descriptions ──────────────────────────────────────────────
COLUMN_DESCRIPTIONS = {
    "granule_uid": "Unique observation/granule identifier in the PSA archive; primary key for each data product",
    "granule_gid": "Group identifier linking related granules from the same instrument or sequence",
    "obs_id": "Observation identifier as defined by the instrument team",
    "dataproduct_type": "EPN-TAP data product type (e.g. 'sp' for spectrum, 'im' for image, 'pr' for profile, 'vo' for occultation)",
    "target_name": "Target body name (primarily 'Venus'; also 'EARTH', 'MOON' for cruise/calibration observations)",
    "target_class": "EPN-TAP target class (e.g. 'planet', 'satellite')",
    "instrument_host_name": "Spacecraft name; always 'Venus Express' for this dataset",
    "instrument_name": "Instrument name: ASPERA-4 (plasma/ion analyzer, ion escape rates), MAG (fluxgate magnetometer, induced magnetosphere), SPICAV (UV/IR spectrometer, atmospheric composition/ozone), VIRTIS (visible/IR thermal imaging spectrometer, cloud-top temperatures), VeRa (radio occultation, atmospheric T/P profiles), VMC (visual monitoring camera, cloud motions at UV)",
    "measurement_type": "Type of physical measurement performed",
    "processing_level": "Data processing level per PDS4 standard (e.g. '2' = calibrated, '3' = derived)",
    "time_min": "Observation start time (Julian Date); Venus Express arrived JD 2453480 (Apr 2006) and operated until JD 2456973 (Nov 2014)",
    "time_max": "Observation end time (Julian Date)",
    "time_sampling_step_min": "Minimum time sampling step within the observation",
    "time_sampling_step_max": "Maximum time sampling step within the observation",
    "time_exp_min": "Minimum exposure time of the observation",
    "time_exp_max": "Maximum exposure time of the observation",
    "spectral_range_min": "Spectral range lower bound in nm (UV: SPICAV/VMC 115-320 nm) or um (infrared: VIRTIS 0.25-5 um); null for non-spectral instruments",
    "spectral_range_max": "Spectral range upper bound",
    "spectral_sampling_step_min": "Minimum spectral sampling step",
    "spectral_sampling_step_max": "Maximum spectral sampling step",
    "spectral_resolution_min": "Minimum spectral resolution",
    "spectral_resolution_max": "Maximum spectral resolution",
    "c1min": "Spatial coordinate 1 minimum (longitude in degrees, 0-360 E for Venus surface/atmosphere observations)",
    "c1max": "Spatial coordinate 1 maximum",
    "c2min": "Spatial coordinate 2 minimum (latitude in degrees, -90 to +90; polar orbit with ~250 km periapsis over north pole)",
    "c2max": "Spatial coordinate 2 maximum",
    "c3min": "Spatial coordinate 3 minimum (altitude or distance)",
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
Complete observation metadata catalog from the ESA Venus Express mission, which studied \
Venus from 2006 to 2014.

Venus Express was a European Space Agency mission that studied the Venusian atmosphere, \
ionosphere, and surface environment from April 2006 until loss of contact in November 2014. \
It carried a suite of instruments including a plasma analyzer (ASPERA-4), magnetometer (MAG), \
UV/IR atmospheric spectrometer (SPICAV), visible and infrared thermal imaging spectrometer \
(VIRTIS), radio science experiment (VeRa), and visual monitoring camera (VMC).

Venus Express made groundbreaking discoveries about Earth's closest planetary neighbor. \
VIRTIS revealed the super-rotating atmosphere in unprecedented detail, mapping the cloud-top \
temperature structure and discovering the south polar atmospheric vortex -- a vast, complex, \
and highly variable double-eye cyclone. SPICAV detected evidence of past water loss through \
deuterium-to-hydrogen ratio measurements and monitored ozone and sulfur dioxide variability \
in the upper atmosphere. MAG characterized the induced magnetosphere and its interaction with \
the solar wind, showing how the unmagnetized planet loses atmospheric ions to space. ASPERA-4 \
measured the escape rates of hydrogen, oxygen, and helium ions, providing constraints on \
long-term atmospheric evolution. VeRa probed the atmospheric temperature and density structure \
through radio occultation, and VMC provided context imaging and tracked cloud motions at \
ultraviolet wavelengths.

The eight-year mission duration spans nearly thirteen Venus days (one Venus day = 243 Earth \
days), enabling studies of both short-term atmospheric dynamics and longer-term variability. \
Each row represents one observation or data granule from the ESA Planetary Science Archive \
(PSA), conforming to the EPN-TAP standard, with timing, spatial coverage, instrument \
parameters, and access URLs."""


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


def fetch_count() -> int:
    """Sanity-check: fetch total row count."""
    query = ("SELECT COUNT(*) AS n FROM epn_core "
             "WHERE instrument_host_name = 'Venus Express'")
    print("Checking total row count...")
    resp = requests.get(TAP_URL, params={
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "json",
        "QUERY": query,
    }, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    cols = [m["name"] for m in data["metadata"]]
    n = int(data["data"][0][cols.index("n")])
    print(f"  Total rows in catalog: {n:,}")
    return n


def _tap_csv(query: str, max_retries: int = 5) -> pd.DataFrame:
    """TAP query returning CSV, with retry + exponential backoff."""
    for attempt in range(max_retries):
        try:
            resp = requests.get(TAP_URL, params={
                "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv",
                "QUERY": query,
            }, timeout=600, stream=True)
            resp.raise_for_status()
            return pd.read_csv(io.StringIO(resp.text), low_memory=False)
        except (requests.ConnectionError, requests.Timeout,
                requests.exceptions.ChunkedEncodingError):
            if attempt == max_retries - 1:
                raise
            wait = 10 * (2 ** attempt)
            print(f"    Connection error (attempt {attempt + 1}), retrying in {wait}s...")
            time.sleep(wait)


def fetch_instrument(instrument: str, parquet_dir: Path) -> int:
    """Fetch all rows for one instrument via cursor-based pagination.

    Returns row count. Writes one parquet file per page to keep memory bounded.
    """
    print(f"  Fetching {instrument}...")
    last_id = ""
    page = 0
    total_rows = 0

    while True:
        query = (
            f"SELECT TOP {PAGE_SIZE} * FROM epn_core "
            f"WHERE instrument_host_name = 'Venus Express' "
            f"AND instrument_name = '{instrument}' "
            f"AND granule_uid > '{last_id}' "
            f"ORDER BY granule_uid"
        )
        df_page = _tap_csv(query)
        if len(df_page) == 0:
            break

        page += 1
        total_rows += len(df_page)
        print(f"    Page {page}: {len(df_page):,} rows (total: {total_rows:,})")

        part_path = parquet_dir / f"{instrument.lower()}_part{page:04d}.parquet"
        df_page.to_parquet(part_path, index=False, engine="pyarrow", compression="zstd")

        df_check = pd.read_parquet(part_path, columns=["granule_uid"])
        row_count = len(df_check)
        last_id = str(df_check["granule_uid"].iloc[-1])
        del df_check, df_page

        if row_count < PAGE_SIZE:
            break
        time.sleep(1)

    if total_rows == 0:
        print(f"    WARNING: No rows for {instrument}")
    else:
        print(f"    {instrument} total: {total_rows:,} rows")
    return total_rows


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
    print("Fetching ESA Venus Express observation catalog...")

    total_expected = fetch_count()

    # Fetch per instrument, writing parquet parts to a temp dir
    parts_dir = Path(tempfile.mkdtemp(prefix="venus_express_parts_"))
    total_rows = 0
    instrument_counts = {}

    for inst in INSTRUMENTS:
        n = fetch_instrument(inst, parts_dir)
        if n > 0:
            instrument_counts[inst] = n
            total_rows += n
        time.sleep(2)

    if total_rows == 0:
        print("::error::No data fetched")
        sys.exit(1)

    print(f"  Total fetched: {total_rows:,} rows")

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
        pretty_name="ESA Venus Express Observations",
        description=DESCRIPTION,
        tags=["space", "venus", "venus-express", "esa", "planetary-science",
              "atmosphere", "open-data", "tabular-data", "parquet"],
        source_url="https://psa.esa.int/",
        license="other",
        license_name="cc-by-nc-3.0-igo",
        license_link="https://creativecommons.org/licenses/by-nc/3.0/igo/",
        task_categories=["tabular-classification"],
        update_schedule="Weekly (Monday at 08:00 UTC)",
        collection_url="https://huggingface.co/collections/juliensimon/space-probe-and-mission-datasets-69c3fe82d410a42b1e313167",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA23791/PIA23791~small.jpg",
            "alt": "Venus as seen by Mariner 10",
            "credit": "NASA/JPL-Caltech",
        },
        related_datasets=[
            "juliensimon/esa-mars-express-observations",
            "juliensimon/esa-bepicolombo-observations",
            "juliensimon/esa-rosetta-observations",
            "juliensimon/esa-exomars-tgo-observations",
        ],
    ) as p:
        instruments_summary = {}
        time_mins, time_maxs = [], []
        all_targets = set()
        total_size = 0

        for inst, inst_rows in instrument_counts.items():
            inst_lower = inst.lower().replace("-", "_")
            part_files = sorted(parts_dir.glob(f"{inst.lower()}_part*.parquet"))
            if not part_files:
                continue

            inst_dir = p.data_dir / inst_lower
            inst_dir.mkdir()

            print(f"  Processing {inst} ({len(part_files)} parts)...")
            inst_row_count = 0
            inst_size = 0
            for i, pf in enumerate(part_files):
                chunk = pd.read_parquet(pf)
                chunk = _clean_chunk(chunk)
                chunk = chunk.drop(
                    columns=[c for c in drop_cols if c in chunk.columns],
                    errors="ignore")

                if i == 0:
                    if "time_min" in chunk.columns:
                        time_mins.append(chunk["time_min"].min())
                    if "target_name" in chunk.columns:
                        all_targets.update(chunk["target_name"].dropna().unique()[:20])

                out = inst_dir / f"part{i:04d}.parquet"
                chunk.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
                inst_row_count += len(chunk)
                inst_size += out.stat().st_size
                del chunk

            # Get time_max from last chunk
            last_chunk = pd.read_parquet(
                inst_dir / f"part{len(part_files)-1:04d}.parquet",
                columns=["time_max"] if "time_max" in pd.read_parquet(
                    inst_dir / f"part{len(part_files)-1:04d}.parquet", columns=[]).columns
                else [])
            if "time_max" in last_chunk.columns:
                time_maxs.append(last_chunk["time_max"].max())
            del last_chunk

            instruments_summary[inst] = inst_row_count
            inst_mb = inst_size / 1024 / 1024
            total_size += inst_mb
            print(f"    {inst}: {inst_row_count:,} rows, {inst_mb:.1f} MB")

        n_total = total_rows
        n_instruments = len(instruments_summary)
        n_targets = len(all_targets)
        time_range_min = min(time_mins) if time_mins else 0
        time_range_max = max(time_maxs) if time_maxs else 0
        print(f"  {n_total:,} observations across {n_instruments} instruments, {total_size:.1f} MB total")

        # Validate using a sample part
        sample_parts = sorted(p.data_dir.rglob("*.parquet"))
        if sample_parts:
            df_sample = pd.read_parquet(sample_parts[0])
            check_dataset(df_sample, "venus-express", min_rows=1,
                          expected_columns=["granule_uid", "instrument_name",
                                            "target_name", "time_min", "time_max",
                                            "dataproduct_type"],
                          critical_columns=["granule_uid", "instrument_name", "time_min"])
            del df_sample
        if n_total < 200_000:
            print(f"::error::Only {n_total:,} rows -- expected at least 200,000")
            sys.exit(1)

        # Instrument breakdown for README
        inst_lines = "\n".join(
            f"- **{inst}**: {count:,} observations"
            for inst, count in instruments_summary.items()
        )

        quick_stats = f"""\
- **{n_total:,}** total observations
- **{n_instruments}** instruments
- **{n_targets}** distinct targets
- Time span: JD {time_range_min:.1f} -- {time_range_max:.1f}"""

        usage = f"""\
```python
from datasets import load_dataset

ds = load_dataset("{HF_REPO}", split="train")
df = ds.to_pandas()

# Observations per instrument
print(df["instrument_name"].value_counts())

# VIRTIS thermal imaging observations
virtis = df[df["instrument_name"] == "VIRTIS"]
print(f"{{len(virtis):,}} VIRTIS observations")

# Timeline of observations
import matplotlib.pyplot as plt
df["year"] = ((df["time_min"] - 2451545.0) / 365.25 + 2000).astype(int)
df.groupby(["year", "instrument_name"]).size().unstack().plot(kind="bar", stacked=True)
plt.title("Venus Express observations per year")
plt.ylabel("Count")
plt.show()
```"""

        # Build custom README (multi-config dataset)
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
        path: data/**/*.parquet
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
                      f"Update Venus Express observations: {n_total:,} observations")
        emit_output(rows=n_total)

    # Clean up parts
    shutil.rmtree(parts_dir, ignore_errors=True)
    print("Done.")


if __name__ == "__main__":
    main()
