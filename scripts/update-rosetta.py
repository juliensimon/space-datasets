#!/usr/bin/env python3
"""Fetch ESA Rosetta observation catalog from PSA EPN-TAP and upload to HF.

The catalog has ~14M+ records across 15+ instruments. We use a memory-bounded
streaming approach: fetch per instrument with cursor-based pagination, writing
one parquet part file per page, then consolidate per instrument for multi-config
HF upload.
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
HF_REPO = "juliensimon/esa-rosetta-observations"

# Rosetta instruments in approximate order of catalog size
INSTRUMENTS = [
    "ROSINA", "OSIRIS", "RPC", "ALICE", "COSIMA", "RSI", "MIDAS",
    "VIRTIS", "NAVCAM", "GIADA", "SREM", "CONSERT", "MIRO",
    "SESAME", "ROMAP",
]

PAGE_SIZE = 50_000

# ── Column descriptions ────────────────────────────────────────────────
COLUMN_DESCRIPTIONS = {
    "granule_uid": "Unique observation/granule identifier in the PSA archive",
    "granule_gid": "Group identifier linking related granules from the same instrument or sequence",
    "obs_id": "Observation ID assigned by the instrument team",
    "dataproduct_type": 'EPN-TAP data product type (e.g. "sp" for spectrum, "im" for image, "pr" for profile, "cu" for cube)',
    "target_name": 'Target body name (primarily "67P/CHURYUMOV-GERASIMENKO 1 (1969 R1)"; also flyby targets CERES, LUTETIA, STEINS, and gravity-assist bodies EARTH, MARS)',
    "target_class": 'EPN-TAP target class (e.g. "comet", "asteroid", "planet")',
    "instrument_host_name": "Spacecraft name (Rosetta)",
    "instrument_name": "Instrument name -- ROSINA, OSIRIS, RPC, ALICE, COSIMA, VIRTIS, NAVCAM, MIDAS, GIADA, CONSERT, MIRO, SREM, RSI, SESAME, ROMAP",
    "measurement_type": "Type of physical measurement performed",
    "processing_level": 'Data processing level per PDS4 standard (e.g. "2" = calibrated, "3" = derived)',
    "time_min": "Observation start time (Julian Date); Rosetta escorted 67P from JD 2456875 (Aug 2014) to JD 2457661 (Sep 2016)",
    "time_max": "Observation end time (Julian Date)",
    "time_sampling_step_min": "Minimum time sampling step within the observation",
    "time_sampling_step_max": "Maximum time sampling step within the observation",
    "time_exp_min": "Minimum exposure time of the observation",
    "time_exp_max": "Maximum exposure time of the observation",
    "spectral_range_min": "Spectral range lower bound in nm (UV/visible) or um (infrared); null for non-spectral instruments",
    "spectral_range_max": "Spectral range upper bound in nm or um",
    "spectral_sampling_step_min": "Minimum spectral sampling step",
    "spectral_sampling_step_max": "Maximum spectral sampling step",
    "spectral_resolution_min": "Minimum spectral resolution",
    "spectral_resolution_max": "Maximum spectral resolution",
    "c1min": "Spatial coordinate 1 lower bound (longitude in degrees for nucleus surface observations)",
    "c1max": "Spatial coordinate 1 upper bound",
    "c2min": "Spatial coordinate 2 lower bound (latitude in degrees for nucleus surface observations)",
    "c2max": "Spatial coordinate 2 upper bound",
    "c3min": "Spatial coordinate 3 lower bound (distance or altitude)",
    "c3max": "Spatial coordinate 3 upper bound",
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
    "release_date": "ISO 8601 date when this data product was released",
    "service_title": "Title of the TAP service providing this record",
    "access_url": "Direct URL to retrieve the data product from the ESA PSA",
    "access_format": 'MIME type of the data product (e.g. "application/x-pds4" for PDS4 format)',
    "thumbnail_url": "URL of a thumbnail preview image, if available",
    "bib_reference": "Bibliographic reference for the data product or instrument",
}

DESCRIPTION = """\
Complete observation metadata catalog from the ESA Rosetta mission to Comet \
67P/Churyumov-Gerasimenko. Rosetta was ESA's groundbreaking mission that became \
the first spacecraft to orbit a comet (August 2014) and deployed the Philae lander \
for the first-ever soft landing on a comet nucleus (November 2014). The mission \
studied the comet's nucleus, coma, and plasma environment in unprecedented detail \
over a 2-year escort phase, witnessing the comet's approach to and retreat from the \
Sun. Rosetta's ROSINA mass spectrometer detected molecular oxygen and glycine (an \
amino acid) in the coma -- findings with profound implications for our understanding \
of Solar System chemistry and the origin of water and prebiotic molecules on Earth. \
OSIRIS captured stunning images of 67P's bilobed nucleus revealing active pits, \
cliffs, and dust jets. The mission concluded with a controlled descent onto the \
comet surface on September 30, 2016. This dataset contains the full observation \
metadata from the ESA Planetary Science Archive (PSA), conforming to the EPN-TAP \
standard. Each row represents one observation or data granule, with timing, spatial \
coverage, instrument parameters, and access URLs."""

INSTRUMENT_DESCRIPTIONS = """\
- **ROSINA**: Mass spectrometer suite measuring gas composition of 67P's coma
- **OSIRIS**: Camera system (NAC + WAC) imaging the comet nucleus and coma
- **RPC**: Plasma consortium with 5 sensors studying the plasma environment
- **ALICE**: Ultraviolet spectrograph characterizing coma and surface composition
- **COSIMA**: Dust mass spectrometer analyzing collected dust grains
- **RSI**: Radio science instrument probing the comet interior and coma
- **MIDAS**: Atomic force microscope imaging dust grain morphology at nm scale
- **VIRTIS**: Visible/infrared imaging spectrometer mapping surface and coma
- **NAVCAM**: Navigation camera providing wide-field context images
- **GIADA**: Dust impact detector measuring grain flux and momentum
- **SREM**: Standard radiation environment monitor
- **CONSERT**: Radar tomography of the comet nucleus (with Philae)
- **MIRO**: Microwave spectrometer measuring subsurface temperature and volatile outgassing
- **SESAME**: Philae surface science package (acoustic, permittivity, dust)
- **ROMAP**: Philae magnetometer and plasma monitor"""


# ── TAP fetch helpers (domain-specific) ─────────────────────────────────

def fetch_count(host_name: str) -> int:
    """Fetch total row count."""
    query = (f"SELECT COUNT(*) AS n FROM epn_core "
             f"WHERE instrument_host_name = '{host_name}'")
    print(f"Checking total row count (instrument_host_name = '{host_name}')...")
    resp = requests.get(TAP_URL, params={
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "json",
        "QUERY": query,
    }, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    cols = [m["name"] for m in data["metadata"]]
    n = int(data["data"][0][cols.index("n")])
    print(f"  Total rows: {n:,}")
    return n


def _detect_host_name() -> str:
    """Determine the correct instrument_host_name value."""
    for name in ("Rosetta", "ROSETTA"):
        query = (f"SELECT COUNT(*) AS n FROM epn_core "
                 f"WHERE instrument_host_name = '{name}'")
        resp = requests.get(TAP_URL, params={
            "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "json",
            "QUERY": query,
        }, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        cols = [m["name"] for m in data["metadata"]]
        n = int(data["data"][0][cols.index("n")])
        if n > 0:
            print(f"  Using instrument_host_name = '{name}' ({n:,} rows)")
            return name
    print("::error::No rows found for Rosetta in epn_core")
    sys.exit(1)


def _tap_csv(query: str, max_retries=5) -> pd.DataFrame:
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


def fetch_instrument(instrument: str, host_name: str, parquet_dir: Path) -> int:
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
            f"WHERE instrument_host_name = '{host_name}' "
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
        del df_page

        df_check = pd.read_parquet(part_path, columns=["granule_uid"])
        row_count = len(df_check)
        last_id = str(df_check["granule_uid"].iloc[-1])
        del df_check

        if row_count < PAGE_SIZE:
            break
        time.sleep(2)

    if total_rows == 0:
        print(f"    WARNING: No rows for {instrument}")
    else:
        print(f"    {instrument} total: {total_rows:,} rows")
    return total_rows


def _clean_chunk(df: pd.DataFrame) -> pd.DataFrame:
    """Apply column cleanup to a DataFrame chunk."""
    df.columns = [c.strip().lower() for c in df.columns]
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
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    string_cols = [
        "granule_uid", "granule_gid", "obs_id",
        "dataproduct_type", "target_name", "target_class",
        "instrument_host_name", "instrument_name",
        "measurement_type", "processing_level",
        "creation_date", "modification_date", "release_date",
        "service_title", "access_url", "access_format",
        "thumbnail_url", "bib_reference",
    ]
    for col in string_cols:
        if col in df.columns:
            df[col] = (df[col].astype(str).str.strip()
                       .replace({"": pd.NA, "None": pd.NA,
                                 "nan": pd.NA, "null": pd.NA}))
    return df


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    print("Fetching ESA Rosetta observation catalog...")

    host_name = _detect_host_name()
    total_expected = fetch_count(host_name)

    # Fetch per instrument, writing parquet parts to a temp dir
    parts_dir = Path(tempfile.mkdtemp(prefix="rosetta_parts_"))
    total_rows = 0
    instrument_counts = {}

    for inst in INSTRUMENTS:
        n = fetch_instrument(inst, host_name, parts_dir)
        if n > 0:
            instrument_counts[inst] = n
            total_rows += n
        time.sleep(10)

    if total_rows == 0:
        print("::error::No data fetched")
        sys.exit(1)

    print(f"  Total fetched: {total_rows:,} rows")

    # Determine columns to drop (>80% null) from a sample
    first_part = sorted(parts_dir.glob("*.parquet"))[0]
    sample = pd.read_parquet(first_part)
    sample = _clean_chunk(sample)
    drop_cols = [col for col in sample.columns if sample[col].isna().mean() > 0.80]
    del sample
    if drop_cols:
        print(f"  Dropping {len(drop_cols)} columns (>80% null)")

    # ── Consolidate and upload using Pipeline context ──────────────────
    with Pipeline(
        repo=HF_REPO,
        pretty_name="ESA Rosetta Observations",
        description=DESCRIPTION,
        tags=["space", "comet", "67p", "rosetta", "philae", "esa",
              "planetary-science", "open-data", "tabular-data", "parquet"],
        source_url="https://psa.esa.int/",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/space-probe-and-mission-datasets-69c3fe82d410a42b1e313167",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA17666/PIA17666~small.jpg",
            "alt": "Rosetta spacecraft approaching Comet 67P/Churyumov-Gerasimenko",
            "credit": "NASA/ESA",
        },
        related_datasets=[
            "juliensimon/esa-exomars-tgo-observations",
            "juliensimon/esa-mars-express-observations",
            "juliensimon/mpc-comet-elements",
        ],
    ) as p:
        instruments_summary = {}
        time_mins, time_maxs = [], []
        all_targets = set()
        total_size = 0

        for inst, inst_rows in instrument_counts.items():
            inst_lower = inst.lower()
            part_files = sorted(parts_dir.glob(f"{inst_lower}_part*.parquet"))
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
                columns=["time_max"])
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

        # ── Validate using a sample part ────────────────────────────────
        sample_parts = sorted(p.data_dir.rglob("*.parquet"))
        if sample_parts:
            df_sample = pd.read_parquet(sample_parts[0])
            check_dataset(df_sample, "rosetta", min_rows=1,
                          expected_columns=["granule_uid", "instrument_name",
                                            "target_name", "time_min", "time_max", "obs_id"],
                          critical_columns=["granule_uid", "instrument_name"])
            del df_sample
        if n_total < 1_000_000:
            print(f"::error::Only {n_total:,} rows -- expected at least 1,000,000")
            sys.exit(1)

        # ── Build configs YAML ──────────────────────────────────────────
        config_instruments = ["rosina", "osiris", "rpc", "alice", "cosima",
                              "virtis", "navcam", "midas"]
        config_yaml_lines = []
        for cfg in config_instruments:
            if any(inst.lower() == cfg for inst in instruments_summary):
                config_yaml_lines.append(f"""  - config_name: {cfg}
    data_files:
      - split: train
        path: data/{cfg}/*.parquet""")
        config_yaml = "\n".join(config_yaml_lines)

        inst_lines = "\n".join(
            f"- **{inst}**: {count:,} observations"
            for inst, count in instruments_summary.items()
        )

        available_configs = ", ".join(
            cfg for cfg in config_instruments
            if any(inst.lower() == cfg for inst in instruments_summary)
        )

        # ── Banner ──────────────────────────────────────────────────────
        banner_file = download_banner(
            "https://images-assets.nasa.gov/image/PIA17666/PIA17666~small.jpg",
            p.tmp_dir)
        banner_md = ""
        if banner_file:
            banner_md = render_banner(
                "Rosetta spacecraft approaching Comet 67P/Churyumov-Gerasimenko",
                "NASA/ESA",
                filename=banner_file,
            )

        # ── README (custom multi-config format) ─────────────────────────
        (p.tmp_dir / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "ESA Rosetta Observations"
language:
  - en
description: "Complete observation metadata catalog from the ESA Rosetta mission to Comet 67P/Churyumov-Gerasimenko ({n_total:,} observations across {n_instruments} instruments). Static dataset from the ESA Planetary Science Archive."
task_categories:
  - tabular-classification
tags:
  - space
  - comet
  - 67p
  - rosetta
  - philae
  - esa
  - planetary-science
  - open-data
  - tabular-data
  - parquet
size_categories:
  - 10M<n<100M
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/**/*.parquet
    default: true
{config_yaml}
---

# ESA Rosetta Observations
{banner_md}
*Part of a [dataset collection](https://huggingface.co/collections/juliensimon/space-probe-and-mission-datasets-69c3fe82d410a42b1e313167) on Hugging Face.*

## Dataset description

{DESCRIPTION}

## Instruments

{INSTRUMENT_DESCRIPTIONS}

## Instrument breakdown

{inst_lines}

## Schema (key columns)

| Column | Type | Description |
|--------|------|-------------|
| `granule_uid` | string | {COLUMN_DESCRIPTIONS["granule_uid"]} |
| `granule_gid` | string | {COLUMN_DESCRIPTIONS["granule_gid"]} |
| `obs_id` | string | {COLUMN_DESCRIPTIONS["obs_id"]} |
| `dataproduct_type` | string | {COLUMN_DESCRIPTIONS["dataproduct_type"]} |
| `target_name` | string | {COLUMN_DESCRIPTIONS["target_name"]} |
| `target_class` | string | {COLUMN_DESCRIPTIONS["target_class"]} |
| `instrument_name` | string | {COLUMN_DESCRIPTIONS["instrument_name"]} |
| `time_min` | float64 | {COLUMN_DESCRIPTIONS["time_min"]} |
| `time_max` | float64 | {COLUMN_DESCRIPTIONS["time_max"]} |
| `c1min`/`c1max` | float64 | {COLUMN_DESCRIPTIONS["c1min"]} |
| `c2min`/`c2max` | float64 | {COLUMN_DESCRIPTIONS["c2min"]} |
| `spectral_range_min`/`max` | float64 | {COLUMN_DESCRIPTIONS["spectral_range_min"]} |
| `processing_level` | string | {COLUMN_DESCRIPTIONS["processing_level"]} |
| `creation_date` | string | {COLUMN_DESCRIPTIONS["creation_date"]} |
| `access_url` | string | {COLUMN_DESCRIPTIONS["access_url"]} |
| `access_format` | string | {COLUMN_DESCRIPTIONS["access_format"]} |

The full schema contains up to ~50 columns following the EPN-TAP standard.

## Quick stats

- **{n_total:,}** total observations
- **{n_instruments}** instruments
- **{n_targets}** distinct targets
- Time span: JD {time_range_min:.1f} -- {time_range_max:.1f}

## Usage

```python
from datasets import load_dataset

# Load a single instrument (fast, low memory)
rosina = load_dataset("{HF_REPO}", "rosina", split="train")
print(f"{{len(rosina):,}} ROSINA observations")

# Load all instruments at once (14M+ rows, needs significant RAM)
ds = load_dataset("{HF_REPO}", split="train")

# Available configs: {available_configs}

# Plot observation density over time
import matplotlib.pyplot as plt
df = rosina.to_pandas()
plt.hist(df["time_min"].dropna(), bins=100)
plt.xlabel("Julian Date")
plt.ylabel("Observation count")
plt.title("ROSINA observation density over time")
plt.show()
```

## Data source

[ESA Planetary Science Archive](https://psa.esa.int/) -- EPN-TAP service at `https://psa.esa.int/psa-tap/tap/sync`.

## Related datasets

- [juliensimon/esa-exomars-tgo-observations](https://huggingface.co/datasets/juliensimon/esa-exomars-tgo-observations)
- [juliensimon/esa-mars-express-observations](https://huggingface.co/datasets/juliensimon/esa-mars-express-observations)
- [juliensimon/comets](https://huggingface.co/datasets/juliensimon/comets)

## Citation

```bibtex
@dataset{{esa_rosetta_observations,
  title = {{ESA Rosetta Observations}},
  author = {{juliensimon}},
  year = {{2026}},
  url = {{https://huggingface.co/datasets/{HF_REPO}}},
  publisher = {{Hugging Face}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        # Upload
        print("Uploading to HF...")
        commit_msg = f"Upload Rosetta observations: {n_total:,} observations across {n_instruments} instruments"
        upload_to_hf(HF_REPO, p.tmp_dir, commit_msg)

    # Clean up parts
    shutil.rmtree(parts_dir, ignore_errors=True)

    emit_output(rows=n_total)
    print("Done.")


if __name__ == "__main__":
    main()
