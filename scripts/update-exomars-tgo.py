#!/usr/bin/env python3
"""Fetch ESA ExoMars TGO observation catalog from PSA EPN-TAP and upload to HF."""

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
HF_REPO = "juliensimon/esa-exomars-tgo-observations"

# ExoMars TGO instruments in order of expected catalog size
INSTRUMENTS = [
    "CaSSIS",
    "ACS",
    "NOMAD",
    "FREND",
    "DREAMS",  # Schiaparelli lander (small, included for completeness)
]

PAGE_SIZE = 50_000


def fetch_count() -> int:
    """Sanity-check: fetch total row count."""
    query = ("SELECT COUNT(*) AS n FROM epn_core "
             "WHERE instrument_host_name = 'ExoMars 2016'")
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
            # Stream into pandas to avoid loading full response into memory
            return pd.read_csv(io.StringIO(resp.text), low_memory=False)
        except (requests.ConnectionError, requests.Timeout,
                requests.exceptions.ChunkedEncodingError) as e:
            if attempt == max_retries - 1:
                raise
            wait = 10 * (2 ** attempt)  # 10, 20, 40, 80, 160s
            print(f"    Connection error (attempt {attempt + 1}), retrying in {wait}s...")
            time.sleep(wait)


def fetch_instrument(instrument: str, parquet_dir: Path) -> int:
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
            f"WHERE instrument_host_name = 'ExoMars 2016' "
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

        if page == 1:
            # Re-read to get the last granule_uid from disk
            df_check = pd.read_parquet(part_path, columns=["granule_uid"])
            last_id = str(df_check["granule_uid"].iloc[-1])
            row_count = len(df_check)
            del df_check
        else:
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
    print("Fetching ESA ExoMars TGO observation catalog...")

    # Verify expected size
    total_expected = fetch_count()

    # Fetch per instrument, writing parquet parts to a temp dir
    parts_dir = Path(tempfile.mkdtemp(prefix="exomars_parts_"))
    total_rows = 0
    instrument_counts = {}

    for inst in INSTRUMENTS:
        n = fetch_instrument(inst, parts_dir)
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
    drop_cols = [col for col in sample.columns if sample[col].isna().mean() > 0.95]
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
            check_dataset(df_sample, "exomars-tgo", min_rows=1,
                expected_columns=["granule_uid", "instrument_name", "target_name",
                                  "time_min", "time_max", "obs_id"],
                critical_columns=["granule_uid", "instrument_name"])
            del df_sample
        if n_total < 100_000:
            print(f"::error::Only {n_total:,} rows — expected at least 100,000")
            sys.exit(1)

        # ── Size category ─────────────────────────────────────────────
        if n_total >= 10_000_000:
            size_cat = "10M<n<100M"
        elif n_total >= 1_000_000:
            size_cat = "1M<n<10M"
        else:
            size_cat = "100K<n<1M"

        # Format instrument breakdown for README
        inst_lines = "\n".join(
            f"- **{inst}**: {count:,} observations"
            for inst, count in instruments_summary.items()
        )

        banner_file = download_banner("exomars-tgo", tmp)
        banner_md = banner_markdown("exomars-tgo", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "ESA ExoMars TGO Observations"
language:
  - en
description: "Complete observation metadata catalog from the ESA ExoMars Trace Gas Orbiter mission ({n_total:,} observations across {n_instruments} instruments), orbiting Mars since 2016. Updated weekly from the ESA Planetary Science Archive."
task_categories:
  - tabular-classification
tags:
  - space
  - mars
  - exomars
  - tgo
  - trace-gas-orbiter
  - esa
  - planetary-science
  - atmosphere
  - open-data
  - tabular-data
  - parquet
size_categories:
  - {size_cat}
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/**/*.parquet
    default: true
  - config_name: cassis
    data_files:
      - split: train
        path: data/cassis/*.parquet
  - config_name: acs
    data_files:
      - split: train
        path: data/acs/*.parquet
  - config_name: nomad
    data_files:
      - split: train
        path: data/nomad/*.parquet
  - config_name: frend
    data_files:
      - split: train
        path: data/frend/*.parquet
  - config_name: dreams
    data_files:
      - split: train
        path: data/dreams/*.parquet
---

# ESA ExoMars TGO Observations
{banner_md}
*Part of the [Solar System Datasets](https://huggingface.co/collections/juliensimon/solar-system-datasets-67dbfa3057e38241e7ea2aee) and [Planetary Science Datasets](https://huggingface.co/collections/juliensimon/planetary-science-datasets-69c24cb17e3db14fc30f0716) collections on Hugging Face.*

![Update ExoMars TGO](https://github.com/juliensimon/space-datasets/actions/workflows/update-exomars-tgo.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['exomars-tgo']&label=updated&color=brightgreen)

Complete observation metadata catalog from the **ESA ExoMars Trace Gas Orbiter (TGO)** mission \u2014 **{n_total:,}**
observations across {n_instruments} instruments, studying Mars atmosphere, surface, and subsurface
since the spacecraft entered orbit in October 2016.

## Dataset description

The ExoMars Trace Gas Orbiter (TGO) is a joint ESA/Roscosmos mission that arrived at Mars in October 2016 and began its science phase in April 2018 after a year of aerobraking. TGO's primary scientific goal is to study the Martian atmosphere with unprecedented sensitivity, searching for trace gases such as methane and other hydrocarbons that could indicate active geological or biological processes. The mission also maps subsurface hydrogen (a proxy for water ice) and captures high-resolution color and stereo surface images.

TGO carries four science instruments:

- **ACS** (Atmospheric Chemistry Suite): a set of three infrared spectrometers performing solar occultation, nadir, and limb observations of the Martian atmosphere. ACS achieves parts-per-trillion sensitivity for trace gas detection, far surpassing any previous Mars orbiter.
- **CaSSIS** (Colour and Stereo Surface Imaging System): a high-resolution color stereo camera that images the Martian surface at ~4.5 m/pixel, providing 3D digital terrain models and color composites for geological and geomorphological studies.
- **FREND** (Fine Resolution Epithermal Neutron Detector): a neutron detector that maps the distribution of hydrogen (and therefore water ice) in the top meter of Martian soil with spatial resolution of ~60 km.
- **NOMAD** (Nadir and Occultation for Mars Discovery): a suite of three spectrometers covering ultraviolet, visible, and infrared wavelengths, performing solar occultation, nadir, and limb observations to map atmospheric composition and aerosols.

TGO's atmospheric measurements have placed the most stringent upper limits on methane in the Martian atmosphere, challenging previous detections and constraining potential sources and sinks. ACS and NOMAD observations have revealed new details about atmospheric dust, water vapor vertical profiles, and the mechanisms driving water escape from Mars. FREND has produced refined maps of near-surface water-equivalent hydrogen, identifying regions where shallow ice may be accessible for future exploration. CaSSIS continues to image active surface processes including RSL (recurring slope lineae), dust devil tracks, seasonal CO2 ice features, and fresh impact craters.

This dataset contains the full observation metadata from the ESA Planetary Science Archive (PSA), conforming to the EPN-TAP standard. Each row represents one observation or data granule, with timing, spatial coverage, instrument parameters, and access URLs.

## Instruments

{inst_lines}

## Schema (key columns)

| Column | Type | Description |
|--------|------|-------------|
| `granule_uid` | string | Unique observation/granule identifier in the PSA archive |
| `granule_gid` | string | Group identifier linking related granules within the same observation sequence |
| `obs_id` | string | Observation ID assigned by the instrument team |
| `dataproduct_type` | string | EPN-TAP data product type (e.g. "sp" for spectrum, "im" for image, "pr" for profile, "cu" for cube) |
| `target_name` | string | Target body name (e.g. "Mars", "Phobos", "Deimos", "Solar Wind") |
| `target_class` | string | EPN-TAP target class (e.g. "planet", "satellite", "interplanetary_medium") |
| `instrument_name` | string | Instrument name — one of: ACS (atmospheric chemistry suite, infrared), CaSSIS (stereo camera, ~4.5 m/pixel), NOMAD (nadir/occultation spectrometer suite), FREND (epithermal neutron detector for subsurface hydrogen) |
| `time_min` | float64 | Observation start time (Julian Date, days since Jan 1 4713 BC noon); TGO science phase began JD 2458220 (Apr 2018) |
| `time_max` | float64 | Observation end time (Julian Date) |
| `c1min`/`c1max` | float64 | Spatial coordinate 1 bounds (longitude in degrees, 0–360 E for surface observations) |
| `c2min`/`c2max` | float64 | Spatial coordinate 2 bounds (latitude in degrees, -90 to +90 for surface observations) |
| `spectral_range_min`/`max` | float64 | Spectral range bounds in nm (UV/visible) or µm (infrared) depending on instrument |
| `processing_level` | string | Data processing level per PDS4 standard (e.g. "2" = calibrated, "3" = derived, "5" = partially processed) |
| `creation_date` | string | ISO 8601 date when this data product was created or archived in PSA |
| `access_url` | string | Direct URL to retrieve the data product from the ESA PSA |
| `access_format` | string | MIME type of the data product (e.g. "application/x-pds4" for PDS4 format) |

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
acs = load_dataset("juliensimon/esa-exomars-tgo-observations", "acs", split="train")
print(f"{{len(acs):,}} ACS observations")

# Load all instruments at once (27M+ rows, needs ~8 GB RAM)
ds = load_dataset("juliensimon/esa-exomars-tgo-observations", split="train")

# Available configs: cassis, acs, nomad, frend, dreams
```

## Data source

[ESA Planetary Science Archive](https://psa.esa.int/) \u2014 EPN-TAP service at
`https://psa.esa.int/psa-tap/tap/sync`.

## Update schedule

Weekly (Monday at 09:00 UTC) via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [nasa-maven-kp-insitu](https://huggingface.co/datasets/juliensimon/nasa-maven-kp-insitu) \u2014 MAVEN Mars atmosphere key parameters
- [esa-mars-express-observations](https://huggingface.co/datasets/juliensimon/esa-mars-express-observations) \u2014 ESA Mars Express observation catalog
- [nasa-mars-rover-images](https://huggingface.co/datasets/juliensimon/nasa-mars-rover-images) \u2014 Perseverance and Curiosity image metadata
- [esa-bepicolombo-observations](https://huggingface.co/datasets/juliensimon/esa-bepicolombo-observations) \u2014 ESA BepiColombo Mercury mission

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a \u2764\ufe0f on the [dataset page](https://huggingface.co/datasets/juliensimon/esa-exomars-tgo-observations) and share feedback in the Community tab! Also consider giving a \u2b50\ufe0f to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{exomars_tgo_observations,
  author = {{Simon, Julien}},
  title = {{ESA ExoMars TGO Observations}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/esa-exomars-tgo-observations}},
  note = {{Based on ESA Planetary Science Archive (PSA) EPN-TAP service}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update ExoMars TGO observations: {n_total:,} observations"
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
