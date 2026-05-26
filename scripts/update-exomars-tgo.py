#!/usr/bin/env python3
"""Fetch ESA ExoMars TGO observation catalog from PSA EPN-TAP and upload to HF.

Source: ESA Planetary Science Archive (PSA) — EPN-TAP service
https://psa.esa.int/

This is a large multi-instrument dataset (~27M rows). Data is written per-instrument
as partitioned parquet files to keep memory bounded.
"""

import io
import shutil
import sys
import tempfile
import time
from pathlib import Path

import pandas as pd
import requests

from hf_dataset_utils import Pipeline, check_dataset, upload_to_hf, write_parquet
from hf_dataset_utils.banner import download_banner, banner_markdown as render_banner
from hf_dataset_utils.github import emit_output

TAP_URL = "https://psa.esa.int/psa-tap/tap/sync"
HF_REPO = "juliensimon/esa-exomars-tgo-observations"

# ExoMars TGO instruments
INSTRUMENTS = ["CaSSIS", "ACS", "NOMAD", "FREND", "DREAMS"]

PAGE_SIZE = 50_000

# ── Column descriptions ─────────────────────────────────────────────
COLUMN_DESCRIPTIONS = {
    "granule_uid": "Unique observation/granule identifier in the PSA archive; primary key for each data product",
    "granule_gid": "Group identifier linking related granules within the same observation sequence",
    "obs_id": "Observation ID assigned by the instrument team; groups related data products from a single observation",
    "dataproduct_type": "EPN-TAP data product type (e.g. 'sp' for spectrum, 'im' for image, 'pr' for profile, 'cu' for cube)",
    "target_name": "Target body name (e.g. 'Mars', 'Phobos', 'Deimos', 'Solar Wind')",
    "target_class": "EPN-TAP target class (e.g. 'planet', 'satellite', 'interplanetary_medium')",
    "instrument_host_name": "Spacecraft name hosting the instrument; always 'ExoMars 2016' for TGO",
    "instrument_name": "Instrument name -- one of: ACS (atmospheric chemistry suite, infrared), CaSSIS (stereo camera, ~4.5 m/pixel), NOMAD (nadir/occultation spectrometer suite), FREND (epithermal neutron detector for subsurface hydrogen)",
    "measurement_type": "Type of physical quantity measured (e.g. 'phot.flux' for photon flux, 'phys.flux' for physical flux)",
    "processing_level": "Data processing level per PDS4 standard (e.g. '2' = calibrated, '3' = derived, '5' = partially processed)",
    "time_min": "Observation start time (Julian Date, days since Jan 1 4713 BC noon); TGO science phase began JD 2458220 (Apr 2018)",
    "time_max": "Observation end time (Julian Date)",
    "time_sampling_step_min": "Minimum time sampling step in days; indicates temporal resolution of the observation",
    "time_sampling_step_max": "Maximum time sampling step in days",
    "time_exp_min": "Minimum exposure time in seconds for this data product",
    "time_exp_max": "Maximum exposure time in seconds",
    "spectral_range_min": "Minimum wavelength of spectral coverage in nm (UV/visible) or um (infrared)",
    "spectral_range_max": "Maximum wavelength of spectral coverage",
    "spectral_sampling_step_min": "Minimum spectral sampling step (spectral resolution element size)",
    "spectral_sampling_step_max": "Maximum spectral sampling step",
    "spectral_resolution_min": "Minimum spectral resolving power (wavelength / resolution element)",
    "spectral_resolution_max": "Maximum spectral resolving power",
    "c1min": "Spatial coordinate 1 minimum (longitude in degrees, 0-360 E for surface observations)",
    "c1max": "Spatial coordinate 1 maximum (longitude)",
    "c2min": "Spatial coordinate 2 minimum (latitude in degrees, -90 to +90)",
    "c2max": "Spatial coordinate 2 maximum (latitude)",
    "c3min": "Spatial coordinate 3 minimum (altitude or distance, instrument-dependent)",
    "c3max": "Spatial coordinate 3 maximum",
    "c1_resol_min": "Minimum spatial resolution in coordinate 1 (degrees)",
    "c1_resol_max": "Maximum spatial resolution in coordinate 1",
    "c2_resol_min": "Minimum spatial resolution in coordinate 2 (degrees)",
    "c2_resol_max": "Maximum spatial resolution in coordinate 2",
    "c3_resol_min": "Minimum spatial resolution in coordinate 3",
    "c3_resol_max": "Maximum spatial resolution in coordinate 3",
    "s_region_lon_min": "Bounding box minimum longitude (degrees)",
    "s_region_lon_max": "Bounding box maximum longitude (degrees)",
    "s_region_lat_min": "Bounding box minimum latitude (degrees)",
    "s_region_lat_max": "Bounding box maximum latitude (degrees)",
    "incidence_min": "Minimum solar incidence angle (degrees from surface normal)",
    "incidence_max": "Maximum solar incidence angle",
    "emergence_min": "Minimum emergence (emission) angle (degrees from surface normal)",
    "emergence_max": "Maximum emergence angle",
    "phase_min": "Minimum phase angle (Sun-target-observer, degrees)",
    "phase_max": "Maximum phase angle",
    "ra_min": "Minimum right ascension of pointing (degrees, J2000)",
    "ra_max": "Maximum right ascension of pointing",
    "dec_min": "Minimum declination of pointing (degrees, J2000)",
    "dec_max": "Maximum declination of pointing",
    "solar_longitude_min": "Minimum areocentric solar longitude Ls (degrees, 0-360); Ls 0 = northern spring equinox",
    "solar_longitude_max": "Maximum areocentric solar longitude Ls",
    "sun_distance_min": "Minimum Sun-target distance (AU)",
    "sun_distance_max": "Maximum Sun-target distance (AU)",
    "target_distance_min": "Minimum spacecraft-target distance (km)",
    "target_distance_max": "Maximum spacecraft-target distance (km)",
    "subsolar_longitude_min": "Minimum sub-solar point longitude (degrees)",
    "subsolar_longitude_max": "Maximum sub-solar point longitude",
    "subsolar_latitude_min": "Minimum sub-solar point latitude (degrees)",
    "subsolar_latitude_max": "Maximum sub-solar point latitude",
    "subobserver_longitude_min": "Minimum sub-observer point longitude (degrees)",
    "subobserver_longitude_max": "Maximum sub-observer point longitude",
    "subobserver_latitude_min": "Minimum sub-observer point latitude (degrees)",
    "subobserver_latitude_max": "Maximum sub-observer point latitude",
    "local_time_min": "Minimum local solar time at observation footprint (hours, 0-24)",
    "local_time_max": "Maximum local solar time at observation footprint",
    "creation_date": "ISO 8601 date when this data product was created or archived in PSA",
    "modification_date": "ISO 8601 date when this data product was last modified in the archive",
    "release_date": "ISO 8601 date when this data product was publicly released",
    "service_title": "Title of the TAP service providing the data",
    "access_url": "Direct URL to retrieve the data product from the ESA PSA",
    "access_format": "MIME type of the data product (e.g. 'application/x-pds4' for PDS4 format)",
    "thumbnail_url": "URL of a thumbnail preview image, if available",
    "bib_reference": "Bibliographic reference for the data product (DOI or ADS bibcode)",
}

DESCRIPTION = """\
Complete observation metadata catalog from the ESA ExoMars Trace Gas Orbiter (TGO) mission -- \
studying Mars atmosphere, surface, and subsurface since the spacecraft entered orbit in October 2016.

TGO's primary scientific goal is to study the Martian atmosphere with unprecedented sensitivity, \
searching for trace gases such as methane that could indicate active geological or biological \
processes. The mission also maps subsurface hydrogen (a proxy for water ice) and captures \
high-resolution color and stereo surface images.

TGO carries four science instruments: ACS (Atmospheric Chemistry Suite, three infrared \
spectrometers achieving parts-per-trillion sensitivity), CaSSIS (Colour and Stereo Surface \
Imaging System, ~4.5 m/pixel), FREND (Fine Resolution Epithermal Neutron Detector, maps \
subsurface hydrogen), and NOMAD (Nadir and Occultation for Mars Discovery, UV/visible/IR \
spectrometer suite).

TGO's atmospheric measurements have placed the most stringent upper limits on methane in the \
Martian atmosphere. ACS and NOMAD observations have revealed new details about atmospheric dust, \
water vapor vertical profiles, and the mechanisms driving water escape from Mars. FREND has \
produced refined maps of near-surface water-equivalent hydrogen. CaSSIS images active surface \
processes including recurring slope lineae, dust devil tracks, and fresh impact craters.

Each row represents one observation or data granule from the ESA Planetary Science Archive (PSA), \
conforming to the EPN-TAP standard, with timing, spatial coverage, instrument parameters, and \
access URLs."""


# ── TAP query helpers ────────────────────────────────────────────────

def fetch_count():
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


def _tap_csv(query, max_retries=5):
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
                requests.exceptions.ChunkedEncodingError) as e:
            if attempt == max_retries - 1:
                raise
            wait = 10 * (2 ** attempt)
            print(f"    Connection error (attempt {attempt + 1}), retrying in {wait}s...")
            time.sleep(wait)


def fetch_instrument(instrument, parquet_dir):
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

        part_path = parquet_dir / f"{instrument.lower()}_part{page:04d}.parquet"
        df_page.to_parquet(part_path, index=False, engine="pyarrow", compression="zstd")

        df_check = pd.read_parquet(part_path, columns=["granule_uid"])
        row_count = len(df_check)
        last_id = str(df_check["granule_uid"].iloc[-1])
        del df_check, df_page

        if row_count < PAGE_SIZE:
            break

        time.sleep(2)

    if total_rows == 0:
        print(f"    WARNING: No rows for {instrument}")
    else:
        print(f"    {instrument} total: {total_rows:,} rows")

    return total_rows


# ── Chunk cleaning ───────────────────────────────────────────────────

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


def _clean_chunk(df):
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
    print("Fetching ESA ExoMars TGO observation catalog...")

    # Verify expected size
    total_expected = fetch_count()

    # Fetch per instrument
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
        pretty_name="ESA ExoMars TGO Observations",
        description=DESCRIPTION,
        tags=["space", "mars", "exomars", "tgo", "trace-gas-orbiter", "esa",
              "planetary-science", "atmosphere", "open-data", "tabular-data", "parquet"],
        source_url="https://psa.esa.int/",
        license="other",
        license_name="cc-by-nc-3.0-igo",
        license_link="https://creativecommons.org/licenses/by-nc/3.0/igo/",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/space-probe-and-mission-datasets-69c3fe82d410a42b1e313167",
        banner={"url": "https://images-assets.nasa.gov/image/PIA24309/PIA24309~small.jpg",
                "alt": "Exploring Jezero Crater on Mars (illustration)",
                "credit": "NASA/JPL-Caltech"},
        update_schedule="Weekly (Monday at 09:00 UTC)",
        related_datasets=[
            "juliensimon/nasa-maven-kp-insitu",
            "juliensimon/esa-mars-express-observations",
            "juliensimon/nasa-mars-rover-images",
            "juliensimon/esa-bepicolombo-observations",
        ],
    ) as p:
        # Write consolidated parquet per instrument into upload dir
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
            check_dataset(df_sample, "exomars-tgo", min_rows=1,
                          expected_columns=["granule_uid", "instrument_name", "target_name",
                                            "time_min", "time_max", "obs_id"],
                          critical_columns=["granule_uid", "instrument_name"])
            del df_sample
        if n_total < 100_000:
            print(f"::error::Only {n_total:,} rows -- expected at least 100,000")
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

        usage = """\
```python
from datasets import load_dataset

# Load a single instrument (fast, low memory)
acs = load_dataset("juliensimon/esa-exomars-tgo-observations", "acs", split="train")
print(f"{len(acs):,} ACS observations")

# Load all instruments at once (27M+ rows, needs ~8 GB RAM)
ds = load_dataset("juliensimon/esa-exomars-tgo-observations", split="train")

# Available configs: cassis, acs, nomad, frend, dreams

# Plot observation timeline
import matplotlib.pyplot as plt

df = acs.to_pandas()
df["time_min"].hist(bins=100, figsize=(12, 4))
plt.title("ACS Observation Timeline")
plt.xlabel("Julian Date")
plt.ylabel("Observations")
plt.tight_layout()
plt.show()
```"""

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

        # Write custom README (multi-config dataset)
        from hf_dataset_utils.readme import _size_category, _citation_bibtex, _yaml_escape, _yaml_tag
        size_cat = _size_category(n_total)
        safe_name = _yaml_escape(p.pretty_name)
        short_desc = _yaml_escape(p.description[:200])
        tags_yaml = "\n".join(f"  - {_yaml_tag(t)}" for t in p.tags)
        task_yaml = "\n".join(f"  - {_yaml_tag(t)}" for t in (p.task_categories or ["other"]))

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
                      f"Update ExoMars TGO observations: {n_total:,} observations")
        emit_output(rows=n_total)

    # Clean up parts
    shutil.rmtree(parts_dir, ignore_errors=True)
    print("Done.")


if __name__ == "__main__":
    main()
