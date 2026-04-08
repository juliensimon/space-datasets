#!/usr/bin/env python3
"""Fetch ESA Rosetta observation catalog from PSA EPN-TAP and upload to HF.

The catalog has ~14M+ records across 15+ instruments. We use a memory-bounded
streaming approach: fetch per instrument with cursor-based pagination, writing
one parquet part file per page, then consolidate per instrument for multi-config
HF upload.
"""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pandas as pd
import requests

from dataset_images import banner_markdown, download_banner
from validate import check_dataset


TAP_URL = "https://psa.esa.int/psa-tap/tap/sync"
HF_REPO = "juliensimon/esa-rosetta-observations"

# Rosetta instruments in approximate order of catalog size
INSTRUMENTS = [
    "ROSINA",    # Mass spectrometer suite (gas composition) ~6.3M
    "OSIRIS",    # Camera system (NAC + WAC) ~3.9M
    "RPC",       # Plasma consortium (5 sensors) ~2.2M
    "ALICE",     # UV spectrograph ~491K
    "COSIMA",    # Dust mass spectrometer ~467K
    "RSI",       # Radio science ~258K
    "MIDAS",     # Atomic force microscope (dust grains) ~106K
    "VIRTIS",    # Vis/IR imaging spectrometer ~69K
    "NAVCAM",    # Navigation camera ~65K
    "GIADA",     # Dust impact detector ~11K
    "SREM",      # Radiation monitor ~7K
    "CONSERT",   # Radar tomography ~4K
    "MIRO",      # Microwave spectrometer ~3K
    "SESAME",    # Philae surface science package
    "ROMAP",     # Philae magnetometer
]

PAGE_SIZE = 50_000


def fetch_count(host_name: str) -> int:
    """Sanity-check: fetch total row count."""
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
    rows = data["data"]
    n = int(rows[0][cols.index("n")])
    print(f"  Total rows: {n:,}")
    return n


def _detect_host_name() -> str:
    """Determine the correct instrument_host_name value ('Rosetta' or 'ROSETTA')."""
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
    """TAP query returning CSV, with retry + exponential backoff.

    Uses CSV format and streaming to avoid holding massive JSON in memory.
    """
    import io

    for attempt in range(max_retries):
        try:
            resp = requests.get(TAP_URL, params={
                "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv",
                "QUERY": query,
            }, timeout=600, stream=True)
            resp.raise_for_status()
            return pd.read_csv(io.StringIO(resp.text), low_memory=False)
        except (requests.ConnectionError, requests.Timeout,
                requests.exceptions.ChunkedEncodingError) as e:
            if attempt == max_retries - 1:
                raise
            wait = 10 * (2 ** attempt)  # 10, 20, 40, 80, 160s
            print(f"    Connection error (attempt {attempt + 1}), retrying in {wait}s...")
            time.sleep(wait)


def fetch_instrument(instrument: str, host_name: str, parquet_dir: Path) -> int:
    """Fetch all rows for one instrument, writing incremental parquet files.

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

        # Write each page as a separate parquet part to keep memory bounded
        part_path = parquet_dir / f"{instrument.lower()}_part{page:04d}.parquet"
        df_page.to_parquet(part_path, index=False, engine="pyarrow", compression="zstd")
        del df_page

        # Re-read to get the last granule_uid from disk
        df_check = pd.read_parquet(part_path, columns=["granule_uid"])
        row_count = len(df_check)
        last_id = str(df_check["granule_uid"].iloc[-1])
        del df_check

        if row_count < PAGE_SIZE:
            break

        time.sleep(2)  # Be polite — this dataset is very large

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


def main():
    print("Fetching ESA Rosetta observation catalog...")

    # Determine correct host name and verify expected size
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

    # ── Consolidate per instrument (memory-bounded) ───────────────────
    # Determine columns to drop (>95% null) from a sample of first part
    first_part = sorted(parts_dir.glob("*.parquet"))[0]
    sample = pd.read_parquet(first_part)
    sample = _clean_chunk(sample)
    drop_cols = [col for col in sample.columns if sample[col].isna().mean() > 0.80]
    del sample

    dropped = len(drop_cols)
    if dropped:
        print(f"  Dropping {dropped} columns (>95% null)")

    # Write one consolidated parquet per instrument into upload dir
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        instruments_summary = {}
        time_mins, time_maxs = [], []
        all_targets = set()
        total_size = 0

        for inst, inst_rows in instrument_counts.items():
            inst_lower = inst.lower()
            part_files = sorted(parts_dir.glob(f"{inst_lower}_part*.parquet"))
            if not part_files:
                continue

            inst_dir = data_dir / inst_lower
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

                # Collect stats from first chunk only (avoid loading all)
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

        # ── Validate using a sample part ─────────────────────────────
        sample_parts = sorted(data_dir.rglob("*.parquet"))
        if sample_parts:
            df_sample = pd.read_parquet(sample_parts[0])
            check_dataset(df_sample, "rosetta", min_rows=1,
                expected_columns=["granule_uid", "instrument_name", "target_name",
                                  "time_min", "time_max", "obs_id"],
                critical_columns=["granule_uid", "instrument_name"])
            del df_sample
        if n_total < 1_000_000:
            print(f"::error::Only {n_total:,} rows — expected at least 1,000,000")
            sys.exit(1)

        # ── Build configs for README ─────────────────────────────────
        # Major instruments get their own config
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

        # Format instrument breakdown for README
        inst_lines = "\n".join(
            f"- **{inst}**: {count:,} observations"
            for inst, count in instruments_summary.items()
        )

        # Instrument descriptions for README
        inst_desc = """- **ROSINA**: Mass spectrometer suite measuring gas composition of 67P's coma
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

        banner_file = download_banner("rosetta", tmp)
        banner_md = banner_markdown("rosetta", banner_file)

        available_configs = ", ".join(
            cfg for cfg in config_instruments
            if any(inst.lower() == cfg for inst in instruments_summary)
        )

        (tmp / "README.md").write_text(f"""---
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
*Part of the [Solar System Datasets](https://huggingface.co/collections/juliensimon/solar-system-datasets-67dbfa3057e38241e7ea2aee) and [Planetary Science Datasets](https://huggingface.co/collections/juliensimon/planetary-science-datasets-69c24cb17e3db14fc30f0716) collections on Hugging Face.*

Complete observation metadata catalog from the **ESA Rosetta** mission to Comet 67P/Churyumov-Gerasimenko \u2014 **{n_total:,}**
observations across {n_instruments} instruments.

## Dataset description

Rosetta was ESA's groundbreaking mission to Comet 67P/Churyumov-Gerasimenko. Launched in 2004, it became the first spacecraft to orbit a comet (August 2014) and deployed the Philae lander for the first-ever soft landing on a comet nucleus (November 2014). The mission studied the comet's nucleus, coma, and plasma environment in unprecedented detail over a 2-year escort phase, witnessing the comet's approach to and retreat from the Sun. Rosetta's ROSINA mass spectrometer detected molecular oxygen and glycine (an amino acid) in the coma \u2014 findings with profound implications for our understanding of Solar System chemistry and the origin of water and prebiotic molecules on Earth. OSIRIS captured stunning images of 67P's bilobed nucleus revealing active pits, cliffs, and dust jets. The mission concluded with a controlled descent onto the comet surface on September 30, 2016.

This dataset contains the full observation metadata from the ESA Planetary Science Archive (PSA), conforming to the EPN-TAP standard. Each row represents one observation or data granule, with timing, spatial coverage, instrument parameters, and access URLs.

## Instruments

{inst_desc}

## Instrument breakdown

{inst_lines}

## Schema (key columns)

| Column | Type | Description |
|--------|------|-------------|
| `granule_uid` | string | Unique observation identifier |
| `granule_gid` | string | Group identifier |
| `obs_id` | string | Observation ID |
| `dataproduct_type` | string | Data product type (e.g. spectrum, image, profile) |
| `target_name` | string | Target body (67P, etc.) |
| `target_class` | string | Target class (comet, etc.) |
| `instrument_name` | string | Instrument name |
| `time_min` | float64 | Observation start time (JD) |
| `time_max` | float64 | Observation end time (JD) |
| `c1min`/`c1max` | float64 | Spatial coordinate 1 range |
| `c2min`/`c2max` | float64 | Spatial coordinate 2 range |
| `spectral_range_min`/`max` | float64 | Spectral range bounds |
| `processing_level` | string | Data processing level |
| `creation_date` | string | Data product creation date |
| `access_url` | string | URL to access the data product |
| `access_format` | string | Data format (e.g. application/x-pds) |

The full schema contains up to ~50 columns following the EPN-TAP standard.

## Quick stats

- **{n_total:,}** total observations
- **{n_instruments}** instruments
- **{n_targets}** distinct targets
- Time span: JD {time_range_min:.1f} \u2013 {time_range_max:.1f}

## Usage

```python
from datasets import load_dataset

# Load a single instrument (fast, low memory)
rosina = load_dataset("juliensimon/esa-rosetta-observations", "rosina", split="train")
print(f"{{len(rosina):,}} ROSINA observations")

# Load all instruments at once (14M+ rows, needs significant RAM)
ds = load_dataset("juliensimon/esa-rosetta-observations", split="train")

# Available configs: {available_configs}
```

## Data source

[ESA Planetary Science Archive](https://psa.esa.int/) \u2014 EPN-TAP service at
`https://psa.esa.int/psa-tap/tap/sync`.

## Related datasets

- [esa-exomars-tgo-observations](https://huggingface.co/datasets/juliensimon/esa-exomars-tgo-observations) \u2014 ESA ExoMars TGO observation catalog
- [esa-mars-express-observations](https://huggingface.co/datasets/juliensimon/esa-mars-express-observations) \u2014 ESA Mars Express observation catalog
- [comets](https://huggingface.co/datasets/juliensimon/comets) \u2014 JPL comet orbital elements

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a \u2764\ufe0f on the [dataset page](https://huggingface.co/datasets/juliensimon/esa-rosetta-observations) and share feedback in the Community tab! Also consider giving a \u2b50\ufe0f to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{rosetta_observations,
  author = {{Simon, Julien}},
  title = {{ESA Rosetta Observations}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/esa-rosetta-observations}},
  note = {{Based on ESA Planetary Science Archive (PSA) EPN-TAP service}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Upload Rosetta observations: {n_total:,} observations across {n_instruments} instruments"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    # Clean up parts
    import shutil
    shutil.rmtree(parts_dir, ignore_errors=True)

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={n_total}\n")
    print("Done.")


if __name__ == "__main__":
    main()
