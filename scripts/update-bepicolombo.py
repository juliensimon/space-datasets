#!/usr/bin/env python3
"""Fetch ESA BepiColombo observation catalog from PSA EPN-TAP and upload to HF.

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
HF_REPO = "juliensimon/esa-bepicolombo-observations"

# BepiColombo instruments in order of expected catalog size
INSTRUMENTS = [
    "MORE", "MPO-MAG", "SIXS", "BERM", "MIXS", "SERENA",
    "PHEBUS", "MCAM", "MGNS", "MERTIS", "BELA",
]

PAGE_SIZE = 500_000

# ── Column descriptions ──────────────────────────────────────────────
COLUMN_DESCRIPTIONS = {
    "granule_uid": "Globally unique identifier for this data granule within the EPN-TAP registry; format is instrument-dependent (e.g. 'BELA_2023-01-15T12:00:00'); used as the pagination key",
    "granule_gid": "Group identifier linking related granules (e.g. all observations from a single instrument session or sequence); less unique than granule_uid",
    "obs_id": "Observation identifier as defined by the instrument team; may correspond to a commanding sequence or science block ID in the PSA archive",
    "dataproduct_type": "EPN-TAP data product type vocabulary: sp = spectrum, im = image, sc = scan/profile, ds = dynamic spectrum, vo = spectral cube, pr = profile, ma = map; determines the spatial/spectral structure of the data",
    "target_name": "Name of the primary observation target (e.g. 'Mercury', 'Venus', 'Sun', 'CALIBRATION'); BepiColombo cruise data includes Venus flyby and Mercury flyby targets",
    "target_class": "EPN-TAP target class vocabulary: planet, satellite, star, interplanetary_medium, calibration; broad category of the observation target",
    "instrument_host_name": "Spacecraft name hosting the instrument; always 'BepiColombo' for this dataset",
    "instrument_name": "Instrument that acquired this granule: MORE (radio science/gravity), MPO-MAG (magnetometer), SIXS (solar X-ray/particle), BERM (radiation monitor), MIXS (X-ray spectrometer), SERENA (neutral/ion analyzer), PHEBUS (UV spectrometer), MCAM (monitoring cameras), MGNS (gamma/neutron spectrometer), MERTIS (thermal IR, 7-40 um), BELA (laser altimeter)",
    "measurement_type": "UCD (Unified Content Descriptor) code for the physical quantity measured (e.g. phot.flux = photon flux density, phys.magField = magnetic field strength, phys.particle.density); follows IVOA UCD1+ vocabulary",
    "processing_level": "PDS/PSA data processing level as a string: '1' = raw telemetry, '2' = calibrated data in physical units, '3' = derived/higher-order products, '4' = mission-level ancillary; stored as string because some archives use e.g. '2a'/'2b' variants",
    "time_min": "Observation start time in Julian Date (TDB timescale); JD 2458775.5 = 2019-Oct-20 (launch + ~1 yr); convert to datetime via pd.to_datetime(time_min - 2440587.5, unit='d', origin='unix')",
    "time_max": "Observation end time in Julian Date (TDB timescale); difference time_max - time_min gives duration in days",
    "time_sampling_step_min": "Minimum interval (seconds) between successive data samples within the observation; characterizes temporal cadence",
    "time_sampling_step_max": "Maximum interval (seconds) between successive data samples within the observation",
    "time_exp_min": "Minimum integration/exposure time per sample (seconds)",
    "time_exp_max": "Maximum integration/exposure time per sample (seconds)",
    "spectral_range_min": "Minimum wavelength or frequency of the spectral coverage (Hz); EPN-TAP standard stores all spectral bounds in Hz regardless of instrument band; null for non-spectral instruments",
    "spectral_range_max": "Maximum wavelength or frequency of the spectral coverage (Hz)",
    "spectral_sampling_step_min": "Minimum spectral sampling step (Hz); distance between adjacent spectral channels",
    "spectral_sampling_step_max": "Maximum spectral sampling step (Hz)",
    "spectral_resolution_min": "Minimum spectral resolving power R = nu/dnu (dimensionless); higher values mean finer spectral discrimination",
    "spectral_resolution_max": "Maximum spectral resolving power R = nu/dnu (dimensionless)",
    "c1min": "Spatial coordinate 1 minimum in degrees; meaning is frame-dependent: longitude for body-fixed frames, right ascension for celestial frames",
    "c1max": "Spatial coordinate 1 maximum in degrees",
    "c2min": "Spatial coordinate 2 minimum in degrees; typically latitude (body-fixed) or declination (celestial)",
    "c2max": "Spatial coordinate 2 maximum in degrees",
    "c3min": "Spatial coordinate 3 minimum in km (radial distance from frame origin or altitude above body surface; meaning frame-dependent)",
    "c3max": "Spatial coordinate 3 maximum in km",
    "c1_resol_min": "Minimum angular resolution along spatial coordinate 1 (degrees); effective pixel/sample size",
    "c1_resol_max": "Maximum angular resolution along spatial coordinate 1 (degrees)",
    "c2_resol_min": "Minimum angular resolution along spatial coordinate 2 (degrees)",
    "c2_resol_max": "Maximum angular resolution along spatial coordinate 2 (degrees)",
    "c3_resol_min": "Minimum radial resolution along spatial coordinate 3 (km)",
    "c3_resol_max": "Maximum radial resolution along spatial coordinate 3 (km)",
    "s_region_lon_min": "Bounding box longitude minimum (degrees, 0-360 or -180 to 180)",
    "s_region_lon_max": "Bounding box longitude maximum (degrees)",
    "s_region_lat_min": "Bounding box latitude minimum (degrees, -90 to 90)",
    "s_region_lat_max": "Bounding box latitude maximum (degrees, -90 to 90)",
    "incidence_min": "Minimum solar incidence angle (degrees, 0-180; angle between surface normal and Sun direction, 0=subsolar, 90=terminator)",
    "incidence_max": "Maximum solar incidence angle (degrees, 0-180)",
    "emergence_min": "Minimum emission/emergence angle (degrees, 0-90; angle between surface normal and line-of-sight to observer)",
    "emergence_max": "Maximum emission/emergence angle (degrees, 0-90)",
    "phase_min": "Minimum phase angle (degrees, 0-180; Sun-target-observer angle, 0=opposition, 180=backlit)",
    "phase_max": "Maximum phase angle (degrees, 0-180)",
    "ra_min": "Right ascension minimum (degrees)",
    "ra_max": "Right ascension maximum (degrees)",
    "dec_min": "Declination minimum (degrees)",
    "dec_max": "Declination maximum (degrees)",
    "solar_longitude_min": "Planetocentric solar longitude minimum (degrees, 0-360); heliocentric longitude of the Sun in the body-fixed frame — proxy for season on Mercury/Venus",
    "solar_longitude_max": "Planetocentric solar longitude maximum (degrees, 0-360)",
    "sun_distance_min": "Minimum heliocentric distance of the spacecraft (AU); BepiColombo cruise ranges ~0.3 (Mercury) to ~1.0 (Earth flyby)",
    "sun_distance_max": "Maximum heliocentric distance (AU)",
    "target_distance_min": "Minimum spacecraft-to-target distance (km); for Mercury flybys can drop below 1000 km",
    "target_distance_max": "Maximum spacecraft-to-target distance (km)",
    "subsolar_longitude_min": "Minimum longitude of the sub-solar point on the target body (degrees, 0-360)",
    "subsolar_longitude_max": "Maximum longitude of the sub-solar point (degrees, 0-360)",
    "subsolar_latitude_min": "Minimum latitude of the sub-solar point (degrees, -90 to 90); near 0 for Mercury due to small axial tilt",
    "subsolar_latitude_max": "Maximum latitude of the sub-solar point (degrees, -90 to 90)",
    "subobserver_longitude_min": "Minimum longitude of the sub-spacecraft point on the target body (degrees, 0-360)",
    "subobserver_longitude_max": "Maximum longitude of the sub-spacecraft point (degrees, 0-360)",
    "subobserver_latitude_min": "Minimum latitude of the sub-spacecraft point (degrees, -90 to 90)",
    "subobserver_latitude_max": "Maximum latitude of the sub-spacecraft point (degrees, -90 to 90)",
    "local_time_min": "Minimum local solar time at the sub-observer point (hours, 0-24; 12 = local noon, 0/24 = local midnight)",
    "local_time_max": "Maximum local solar time at the sub-observer point (hours, 0-24)",
    "creation_date": "ISO 8601 date when the data product was generated or ingested into the PSA archive; reflects pipeline processing date, not observation date",
    "modification_date": "ISO 8601 date when the data product was last modified",
    "release_date": "ISO 8601 date when the data product was publicly released",
    "service_title": "Title of the TAP service providing this record (e.g. 'PSA EPN-TAP' for the ESA Planetary Science Archive)",
    "access_url": "Direct URL to download the data product from the ESA Planetary Science Archive",
    "access_format": "MIME type of the data product: application/x-pds = PDS4 format, application/fits = FITS, text/plain = ASCII table",
    "thumbnail_url": "URL of a thumbnail preview image (JPEG/PNG), if available",
    "bib_reference": "Bibliographic reference (DOI, ADS bibcode, or citation string) for the data product or parent instrument paper",
}

DESCRIPTION = """\
Complete observation metadata catalog from the ESA/JAXA BepiColombo mission to Mercury.

BepiColombo is a joint ESA/JAXA mission to Mercury, launched October 2018. It consists \
of two orbiters: the Mercury Planetary Orbiter (MPO) and the Mercury Magnetospheric \
Orbiter (Mio/MMO). After a 7-year cruise with gravity assists at Earth, Venus (x2), and \
Mercury (x6), it will enter Mercury orbit in late 2025. During cruise, instruments have \
been collecting calibration and flyby science data.

Key instruments include MORE (radio science for gravity), MPO-MAG (magnetometer), SIXS \
(solar X-ray/particle spectrometer), BERM (radiation monitor), MIXS (X-ray spectrometer), \
SERENA (neutral/ion analyzer), PHEBUS (UV spectrometer), MCAM (monitoring cameras), MGNS \
(gamma/neutron spectrometer), MERTIS (thermal IR), and BELA (laser altimeter).

The cruise phase data is scientifically valuable in its own right. MPO-MAG has mapped the \
interplanetary magnetic field along the spacecraft's trajectory, including measurements \
during Venus and Mercury flybys that provide unique geometry for studying planetary \
magnetospheres. MORE has conducted superior solar conjunction experiments to test general \
relativity. SIXS and BERM have monitored the solar particle environment, building a \
multi-year record of solar energetic particle events and cosmic ray flux variations along \
the inner heliosphere trajectory. The Mercury flyby observations from MERTIS, MIXS, and \
MGNS provide early science returns and instrument calibration data ahead of orbital \
operations.

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
             "WHERE instrument_host_name = 'BepiColombo'")
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
            f"WHERE instrument_host_name = 'BepiColombo' "
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
    print("Fetching ESA BepiColombo observation catalog...")

    total_expected = fetch_count()

    # Fetch per instrument, writing parquet parts to a temp dir
    parts_dir = Path(tempfile.mkdtemp(prefix="bepicolombo_parts_"))
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

    # Determine columns to drop (>80% null) from a sample
    first_part = sorted(parts_dir.glob("*.parquet"))[0]
    sample = pd.read_parquet(first_part)
    sample.columns = [c.strip().lower() for c in sample.columns]
    drop_cols = [col for col in sample.columns if sample[col].isna().mean() > 0.80]
    del sample
    if drop_cols:
        print(f"  Dropping {len(drop_cols)} columns (>80% null)")

    with Pipeline(
        repo=HF_REPO,
        pretty_name="ESA BepiColombo Observations",
        description=DESCRIPTION,
        tags=["space", "mercury", "bepicolombo", "esa",
              "planetary-science", "open-data", "tabular-data", "parquet"],
        source_url="https://psa.esa.int/",
        license="other",
        license_name="cc-by-nc-3.0-igo",
        license_link="https://creativecommons.org/licenses/by-nc/3.0/igo/",
        task_categories=["tabular-classification"],
        update_schedule="Weekly (Monday at 09:30 UTC)",
        collection_url="https://huggingface.co/collections/juliensimon/space-probe-and-mission-datasets-69c3fe82d410a42b1e313167",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA11245/PIA11245~small.jpg",
            "alt": "Mercury as seen by the MESSENGER spacecraft",
            "credit": "NASA/Johns Hopkins APL/Carnegie Institution of Washington",
        },
        related_datasets=[
            "juliensimon/esa-mars-express-observations",
            "juliensimon/esa-exomars-tgo-observations",
            "juliensimon/esa-venus-express-observations",
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
            check_dataset(df_sample, "bepicolombo", min_rows=1,
                          expected_columns=["granule_uid", "instrument_name",
                                            "time_min", "time_max", "dataproduct_type"],
                          critical_columns=["granule_uid", "instrument_name", "time_min"])
            del df_sample
        if n_total < 50_000:
            print(f"::error::Only {n_total:,} rows -- expected at least 50,000")
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

# MORE radio science observations
more = df[df["instrument_name"] == "MORE"]
print(f"{{len(more):,}} MORE observations")

# Timeline of observations
import matplotlib.pyplot as plt
df["year"] = ((df["time_min"] - 2451545.0) / 365.25 + 2000).astype(int)
df.groupby(["year", "instrument_name"]).size().unstack().plot(kind="bar", stacked=True)
plt.title("BepiColombo observations per year")
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
                      f"Update BepiColombo observations: {n_total:,} observations")
        emit_output(rows=n_total)

    # Clean up parts
    shutil.rmtree(parts_dir, ignore_errors=True)
    print("Done.")


if __name__ == "__main__":
    main()
