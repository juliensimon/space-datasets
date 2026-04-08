#!/usr/bin/env python3
"""
Fetch NASA MAVEN Key Parameter (KP) in-situ data from LASP SDC and upload to HF.

MAVEN (Mars Atmosphere and Volatile EvolutioN) has been studying the Martian
upper atmosphere and its interaction with the solar wind since September 2014.
The KP dataset provides time-series measurements from multiple instruments at
4-8 second cadence.

Data source: https://lasp.colorado.edu/maven/sdc/public/data/sci/kp/insitu/
Incremental: downloads existing per-instrument parquets from HF, fetches new
months, merges. Multi-instrument split: one parquet per instrument under data/.
"""

import io
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

from dataset_images import banner_markdown, download_banner
from validate import check_dataset


BASE_URL = "https://lasp.colorado.edu/maven/sdc/public/data/sci/kp/insitu/"
HF_REPO = "juliensimon/nasa-maven-kp-insitu"

# For initial build, start from 2025 to keep GH Actions runtime under 1 hour.
# Each file is ~43 MB text, ~30s download+parse. Future incremental runs extend.
START_YEAR = 2025
START_MONTH = 1

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "space-datasets/1.0 (https://github.com/juliensimon/space-datasets)"})

# ── Column name mapping (positional index 1-235) ────────────────────────────
# Index 1 = time column, 2-235 = instrument parameters.
# Derived from the MAVEN KP .tab file header specification.

NAMES = {
    1: "time",
    2: "lpw_electron_density", 3: "lpw_electron_density_quality", 4: "lpw_electron_density_quality_2",
    5: "lpw_electron_temperature", 6: "lpw_electron_temperature_quality", 7: "lpw_electron_temperature_quality_2",
    8: "lpw_spacecraft_potential", 9: "lpw_spacecraft_potential_quality", 10: "lpw_spacecraft_potential_quality_2",
    11: "lpw_e_field_power_2_100hz", 12: "lpw_e_field_2_100hz_quality",
    13: "lpw_e_field_power_100_800hz", 14: "lpw_e_field_100_800hz_quality",
    15: "lpw_e_field_power_0p8_1p0mhz", 16: "lpw_e_field_0p8_1p0mhz_quality",
    17: "lpw_euv_irradiance_0p1_7nm", 18: "lpw_euv_irradiance_0p1_7nm_quality",
    19: "lpw_euv_irradiance_17_22nm", 20: "lpw_euv_irradiance_17_22nm_quality",
    21: "lpw_euv_irradiance_lyman_alpha", 22: "lpw_euv_irradiance_lyman_alpha_quality",
    23: "swea_electron_density", 24: "swea_electron_density_quality",
    25: "swea_electron_temperature", 26: "swea_electron_temperature_quality",
    27: "swea_eflux_par_5_100ev", 28: "swea_eflux_par_5_100ev_quality",
    29: "swea_eflux_par_100_500ev", 30: "swea_eflux_par_100_500ev_quality",
    31: "swea_eflux_par_500_1000ev", 32: "swea_eflux_par_500_1000ev_quality",
    33: "swea_eflux_anti_5_100ev", 34: "swea_eflux_anti_5_100ev_quality",
    35: "swea_eflux_anti_100_500ev", 36: "swea_eflux_anti_100_500ev_quality",
    37: "swea_eflux_anti_500_1000ev", 38: "swea_eflux_anti_500_1000ev_quality",
    39: "swea_spectrum_shape", 40: "swea_spectrum_shape_quality",
    41: "swia_h_density", 42: "swia_h_density_quality",
    43: "swia_h_velocity_mso_x", 44: "swia_h_velocity_mso_x_quality",
    45: "swia_h_velocity_mso_y", 46: "swia_h_velocity_mso_y_quality",
    47: "swia_h_velocity_mso_z", 48: "swia_h_velocity_mso_z_quality",
    49: "swia_h_temperature", 50: "swia_h_temperature_quality",
    51: "swia_dynamic_pressure", 52: "swia_dynamic_pressure_quality",
    53: "static_quality_flag",
    54: "static_h_density", 55: "static_h_density_quality",
    56: "static_o_density", 57: "static_o_density_quality",
    58: "static_o2_density", 59: "static_o2_density_quality",
    60: "static_h_temperature", 61: "static_h_temperature_quality",
    62: "static_o_temperature", 63: "static_o_temperature_quality",
    64: "static_o2_temperature", 65: "static_o2_temperature_quality",
    66: "static_o2_velocity_app_x", 67: "static_o2_velocity_app_x_quality",
    68: "static_o2_velocity_app_y", 69: "static_o2_velocity_app_y_quality",
    70: "static_o2_velocity_app_z", 71: "static_o2_velocity_app_z_quality",
    72: "static_o2_velocity_mso_x", 73: "static_o2_velocity_mso_x_quality",
    74: "static_o2_velocity_mso_y", 75: "static_o2_velocity_mso_y_quality",
    76: "static_o2_velocity_mso_z", 77: "static_o2_velocity_mso_z_quality",
    78: "static_h_omni_flux", 79: "static_h_energy", 80: "static_h_energy_quality",
    81: "static_he_omni_flux", 82: "static_he_energy", 83: "static_he_energy_quality",
    84: "static_o_omni_flux", 85: "static_o_energy", 86: "static_o_energy_quality",
    87: "static_o2_omni_flux", 88: "static_o2_energy", 89: "static_o2_energy_quality",
    90: "static_h_dir_mso_x", 91: "static_h_dir_mso_y", 92: "static_h_dir_mso_z",
    93: "static_h_angular_width", 94: "static_h_angular_width_quality",
    95: "static_pickup_dir_mso_x", 96: "static_pickup_dir_mso_y", 97: "static_pickup_dir_mso_z",
    98: "static_pickup_angular_width", 99: "static_pickup_angular_width_quality",
    100: "sep_ion_fov1f", 101: "sep_ion_fov1f_quality",
    102: "sep_ion_fov1r", 103: "sep_ion_fov1r_quality",
    104: "sep_ion_fov2f", 105: "sep_ion_fov2f_quality",
    106: "sep_ion_fov2r", 107: "sep_ion_fov2r_quality",
    108: "sep_electron_fov1f", 109: "sep_electron_fov1f_quality",
    110: "sep_electron_fov1r", 111: "sep_electron_fov1r_quality",
    112: "sep_electron_fov2f", 113: "sep_electron_fov2f_quality",
    114: "sep_electron_fov2r", 115: "sep_electron_fov2r_quality",
    116: "sep_look_1f_mso_x", 117: "sep_look_1f_mso_y", 118: "sep_look_1f_mso_z",
    119: "sep_look_1r_mso_x", 120: "sep_look_1r_mso_y", 121: "sep_look_1r_mso_z",
    122: "sep_look_2f_mso_x", 123: "sep_look_2f_mso_y", 124: "sep_look_2f_mso_z",
    125: "sep_look_2r_mso_x", 126: "sep_look_2r_mso_y", 127: "sep_look_2r_mso_z",
    128: "mag_mso_x", 129: "mag_mso_x_quality",
    130: "mag_mso_y", 131: "mag_mso_y_quality",
    132: "mag_mso_z", 133: "mag_mso_z_quality",
    134: "mag_geo_x", 135: "mag_geo_x_quality",
    136: "mag_geo_y", 137: "mag_geo_y_quality",
    138: "mag_geo_z", 139: "mag_geo_z_quality",
    140: "mag_rms_deviation", 141: "mag_rms_quality",
    142: "ngims_he", 143: "ngims_he_precision", 144: "ngims_he_quality",
    145: "ngims_o", 146: "ngims_o_precision", 147: "ngims_o_quality",
    148: "ngims_co", 149: "ngims_co_precision", 150: "ngims_co_quality",
    151: "ngims_n2", 152: "ngims_n2_precision", 153: "ngims_n2_quality",
    154: "ngims_no", 155: "ngims_no_precision", 156: "ngims_no_quality",
    157: "ngims_ar", 158: "ngims_ar_precision", 159: "ngims_ar_quality",
    160: "ngims_co2", 161: "ngims_co2_precision", 162: "ngims_co2_quality",
    163: "ngims_ion32", 164: "ngims_ion32_precision", 165: "ngims_ion32_quality",
    166: "ngims_ion44", 167: "ngims_ion44_precision", 168: "ngims_ion44_quality",
    169: "ngims_ion30", 170: "ngims_ion30_precision", 171: "ngims_ion30_quality",
    172: "ngims_ion16", 173: "ngims_ion16_precision", 174: "ngims_ion16_quality",
    175: "ngims_ion28", 176: "ngims_ion28_precision", 177: "ngims_ion28_quality",
    178: "ngims_ion12", 179: "ngims_ion12_precision", 180: "ngims_ion12_quality",
    181: "ngims_ion17", 182: "ngims_ion17_precision", 183: "ngims_ion17_quality",
    184: "ngims_ion14", 185: "ngims_ion14_precision", 186: "ngims_ion14_quality",
    187: "spice_geo_x", 188: "spice_geo_y", 189: "spice_geo_z",
    190: "spice_mso_x", 191: "spice_mso_y", 192: "spice_mso_z",
    193: "spice_longitude", 194: "spice_latitude",
    195: "spice_solar_zenith_angle", 196: "spice_local_time",
    197: "spice_altitude",
    198: "spice_sc_att_geo_x", 199: "spice_sc_att_geo_y", 200: "spice_sc_att_geo_z",
    201: "spice_sc_att_mso_x", 202: "spice_sc_att_mso_y", 203: "spice_sc_att_mso_z",
    204: "spice_app_geo_x", 205: "spice_app_geo_y", 206: "spice_app_geo_z",
    207: "spice_app_mso_x", 208: "spice_app_mso_y", 209: "spice_app_mso_z",
    210: "spice_orbit_number", 211: "spice_inbound_outbound",
    212: "spice_mars_season_ls", 213: "spice_mars_sun_distance_au",
    214: "spice_subsolar_longitude", 215: "spice_subsolar_latitude",
    216: "spice_submars_sun_longitude", 217: "spice_submars_sun_latitude",
    218: "spice_rot_mars_r1c1", 219: "spice_rot_mars_r1c2", 220: "spice_rot_mars_r1c3",
    221: "spice_rot_mars_r2c1", 222: "spice_rot_mars_r2c2", 223: "spice_rot_mars_r2c3",
    224: "spice_rot_mars_r3c1", 225: "spice_rot_mars_r3c2", 226: "spice_rot_mars_r3c3",
    227: "spice_rot_sc_r1c1", 228: "spice_rot_sc_r1c2", 229: "spice_rot_sc_r1c3",
    230: "spice_rot_sc_r2c1", 231: "spice_rot_sc_r2c2", 232: "spice_rot_sc_r2c3",
    233: "spice_rot_sc_r3c1", 234: "spice_rot_sc_r3c2", 235: "spice_rot_sc_r3c3",
}

# ── Instrument column ranges (1-indexed keys in NAMES) ──────────────────────
INSTRUMENTS = {
    "lpw":    (2, 22),
    "swea":   (23, 40),
    "swia":   (41, 52),
    "static": (53, 99),
    "sep":    (100, 127),
    "mag":    (128, 141),
    "ngims":  (142, 186),
    "spice":  (187, 235),
}

# Human-readable descriptions for README
INSTRUMENT_DESCRIPTIONS = {
    "lpw":    "Langmuir Probe and Waves — electron density, temperature, EUV irradiance",
    "swea":   "Solar Wind Electron Analyzer — electron energy spectra and pitch angle distributions",
    "swia":   "Solar Wind Ion Analyzer — solar wind proton density, velocity, temperature",
    "static": "Suprathermal and Thermal Ion Composition — ion mass/charge composition and energy spectra",
    "sep":    "Solar Energetic Particle — high-energy particle fluxes from solar events",
    "mag":    "Magnetometer — magnetic field vector components (MSO and GEO frames)",
    "ngims":  "Neutral Gas and Ion Mass Spectrometer — neutral and ion densities in upper atmosphere",
    "spice":  "Spacecraft ephemeris — position, attitude, altitude, solar zenith angle, orbit metadata",
}


def _instrument_columns(instrument: str) -> list[str]:
    """Return the list of proper column names for an instrument (excluding time)."""
    lo, hi = INSTRUMENTS[instrument]
    return [NAMES[i] for i in range(lo, hi + 1)]


def list_tab_files(year: int, month: int) -> list[str]:
    """Fetch directory listing for a year/month and return .tab filenames."""
    url = f"{BASE_URL}{year:04d}/{month:02d}/"
    try:
        resp = SESSION.get(url, timeout=60)
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"    WARNING: could not list {url}: {e}")
        return []

    # Parse href links from HTML directory listing
    filenames = re.findall(r'href="(mvn_kp_insitu_[^"]+\.tab)"', resp.text)
    return sorted(set(filenames))


def parse_tab_file(content: str) -> pd.DataFrame | None:
    """Parse a MAVEN KP .tab file (fixed-width text with # header lines).

    The header contains metadata including the line number where data begins.
    Data is whitespace-delimited with 235 columns. After parsing, columns are
    renamed from positional to proper names using the NAMES mapping.
    """
    lines = content.splitlines()

    # Extract data start line from header (line ~8: "#     348   Line on which data begins")
    data_start_line = None
    for line in lines[:20]:
        if "Line on which data begins" in line:
            match = re.search(r"#\s+(\d+)\s+Line on which", line)
            if match:
                data_start_line = int(match.group(1)) - 1  # 0-indexed
                break

    if data_start_line is None:
        # Fallback: find first non-# non-empty line
        for i, line in enumerate(lines):
            if not line.startswith("#") and line.strip():
                data_start_line = i
                break

    if data_start_line is None or data_start_line >= len(lines):
        return None

    data_lines = [l for l in lines[data_start_line:] if l.strip()]
    if not data_lines:
        return None

    data_text = "\n".join(data_lines)
    try:
        df = pd.read_csv(
            io.StringIO(data_text),
            sep=r"\s+",
            header=None,
            na_values=["-9.99999990E+30", "-1.00000000E+31", "NO_DATA", "NaN"],
        )
    except Exception:
        return None

    if df.empty:
        return None

    # Rename columns from positional (0..n-1) to proper names (NAMES index 1..n)
    n_cols = len(df.columns)
    col_names = [NAMES.get(i + 1, f"unknown_{i + 1}") for i in range(n_cols)]
    df.columns = col_names

    # Convert time to datetime
    df["time"] = pd.to_datetime(df["time"], errors="coerce")

    # Numeric coercion for all non-time columns
    for col in df.columns:
        if col == "time":
            continue
        if df[col].dtype == object:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def download_and_parse(year: int, month: int, filename: str) -> pd.DataFrame | None:
    """Download a single .tab file and parse it."""
    url = f"{BASE_URL}{year:04d}/{month:02d}/{filename}"
    try:
        resp = SESSION.get(url, timeout=120)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"    WARNING: failed to download {filename}: {e}")
        return None

    return parse_tab_file(resp.text)


def load_existing_instrument(instrument: str, local_dir: Path) -> pd.DataFrame | None:
    """Download and load an existing instrument parquet from HF."""
    parquet_path = local_dir / "data" / instrument / f"{instrument}.parquet"
    if parquet_path.exists():
        df = pd.read_parquet(parquet_path)
        if "time" in df.columns:
            df["time"] = pd.to_datetime(df["time"])
        return df
    return None


def load_all_existing(tmp_dir: Path) -> dict[str, pd.DataFrame]:
    """Download existing per-instrument parquets from HF. Returns dict of DataFrames."""
    try:
        subprocess.run(
            ["hf", "download", HF_REPO, "data/",
             "--repo-type", "dataset", "--local-dir", str(tmp_dir)],
            check=True, capture_output=True, timeout=300,
        )
    except Exception as e:
        print(f"  Could not download existing data ({e}), doing full rebuild")
        return {}

    existing = {}
    for instrument in INSTRUMENTS:
        df = load_existing_instrument(instrument, tmp_dir)
        if df is not None and not df.empty:
            existing[instrument] = df
            print(f"  Loaded existing {instrument}: {len(df):,} rows")

    return existing


def generate_months(start_year: int, start_month: int, end_year: int, end_month: int):
    """Generate (year, month) tuples in range."""
    y, m = start_year, start_month
    while (y, m) <= (end_year, end_month):
        yield y, m
        m += 1
        if m > 12:
            m = 1
            y += 1


def extract_instrument_df(df: pd.DataFrame, instrument: str) -> pd.DataFrame:
    """Extract time + instrument columns from a full DataFrame."""
    cols = ["time"] + _instrument_columns(instrument)
    # Only keep columns that exist in df
    cols = [c for c in cols if c in df.columns]
    return df[cols].copy()


def clean_instrument_df(df: pd.DataFrame) -> pd.DataFrame:
    """Drop >80% null columns and all-null rows for an instrument DataFrame."""
    # Drop columns that are >80% null (excluding time)
    for col in list(df.columns):
        if col == "time":
            continue
        if df[col].isna().mean() > 0.80:
            df = df.drop(columns=[col])

    # Drop rows where all non-time columns are null
    non_time = [c for c in df.columns if c != "time"]
    if non_time:
        df = df.dropna(subset=non_time, how="all")

    return df


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=None,
                        help="Fetch only this single year (e.g. --year 2020)")
    args = parser.parse_args()

    print("Fetching NASA MAVEN KP in-situ data...")

    yesterday = date.today() - timedelta(days=1)

    # Try incremental: load existing data
    with tempfile.TemporaryDirectory() as probe:
        existing = load_all_existing(Path(probe))

    # Determine time range of existing data from spice (always populated)
    existing_max_time = None
    if existing:
        for inst_df in existing.values():
            if "time" in inst_df.columns and not inst_df.empty:
                t = inst_df["time"].max()
                if existing_max_time is None or t > existing_max_time:
                    existing_max_time = t

    if args.year:
        # Single-year mode: fetch one year, merge with existing
        fetch_start_year = args.year
        fetch_start_month = 1
        fetch_end_year = args.year
        fetch_end_month = 12
        print(f"  Single-year mode: fetching {args.year}")
    elif existing_max_time is not None:
        # Incremental: fetch from the month of the last data point
        fetch_start_year = existing_max_time.year
        fetch_start_month = existing_max_time.month
        fetch_end_year = yesterday.year
        fetch_end_month = yesterday.month
        print(f"  Incremental from {fetch_start_year}-{fetch_start_month:02d}")
    else:
        # Full rebuild from START_YEAR
        existing = {}
        fetch_start_year = START_YEAR
        fetch_start_month = START_MONTH
        fetch_end_year = yesterday.year
        fetch_end_month = yesterday.month
        print(f"  Full rebuild from {fetch_start_year}-{fetch_start_month:02d}")

    # Fetch new data month by month
    all_new = []
    total_files = 0

    for year, month in generate_months(fetch_start_year, fetch_start_month,
                                       fetch_end_year, fetch_end_month):
        print(f"  {year}-{month:02d}...", end="", flush=True)
        filenames = list_tab_files(year, month)
        if not filenames:
            print(" no files")
            time.sleep(1)
            continue

        print(f" {len(filenames)} files", end="", flush=True)
        month_rows = 0
        for fname in filenames:
            df_file = download_and_parse(year, month, fname)
            if df_file is not None and not df_file.empty:
                all_new.append(df_file)
                month_rows += len(df_file)
                total_files += 1
            time.sleep(0.5)

        print(f" -> {month_rows:,} rows")
        time.sleep(1)

    print(f"  Downloaded {total_files} files")

    if all_new:
        df_new = pd.concat(all_new, ignore_index=True)
        print(f"  New data: {len(df_new):,} rows")
    else:
        df_new = pd.DataFrame()
        print("  No new data downloaded")

    if df_new.empty and not existing:
        print("::error::No data available")
        sys.exit(1)

    # ── Per-instrument merge, clean, write ───────────────────────────────────
    instrument_dfs = {}
    instrument_rows = {}

    for instrument in INSTRUMENTS:
        # Extract this instrument's columns from new data
        if not df_new.empty:
            df_inst_new = extract_instrument_df(df_new, instrument)
        else:
            df_inst_new = pd.DataFrame()

        # Merge with existing
        df_inst_existing = existing.get(instrument)

        if df_inst_existing is not None and not df_inst_new.empty:
            df_inst = pd.concat([df_inst_existing, df_inst_new], ignore_index=True)
            df_inst = df_inst.drop_duplicates(subset=["time"], keep="last")
            print(f"  {instrument}: merged {len(df_inst_existing):,} existing + {len(df_inst_new):,} new -> {len(df_inst):,} rows")
        elif df_inst_existing is not None:
            df_inst = df_inst_existing
            print(f"  {instrument}: using existing {len(df_inst):,} rows")
        elif not df_inst_new.empty:
            df_inst = df_inst_new
            print(f"  {instrument}: new {len(df_inst):,} rows")
        else:
            print(f"  {instrument}: no data, skipping")
            continue

        # Sort by time
        df_inst = df_inst.sort_values("time").reset_index(drop=True)

        # Clean: drop >80% null columns and all-null rows
        before_cols = len(df_inst.columns)
        before_rows = len(df_inst)
        df_inst = clean_instrument_df(df_inst)
        dropped_cols = before_cols - len(df_inst.columns)
        dropped_rows = before_rows - len(df_inst)
        if dropped_cols or dropped_rows:
            print(f"    Cleaned: dropped {dropped_cols} cols, {dropped_rows:,} rows")

        if df_inst.empty or len(df_inst.columns) <= 1:
            print(f"    {instrument}: empty after cleaning, skipping")
            continue

        instrument_dfs[instrument] = df_inst
        instrument_rows[instrument] = len(df_inst)

    if not instrument_dfs:
        print("::error::No instrument data after cleaning")
        sys.exit(1)

    # ── Validate on spice (always has data) ──────────────────────────────────
    if "spice" in instrument_dfs:
        check_dataset(
            instrument_dfs["spice"],
            "maven",
            min_rows=100_000,
            expected_columns=["time", "spice_altitude"],
            critical_columns=["time"],
            incremental=True,
        )
    else:
        # Fallback: validate the largest instrument
        largest = max(instrument_dfs, key=lambda k: len(instrument_dfs[k]))
        check_dataset(
            instrument_dfs[largest],
            "maven",
            min_rows=100_000,
            expected_columns=["time"],
            critical_columns=["time"],
            incremental=True,
        )

    # ── Compute stats ────────────────────────────────────────────────────────
    n_total = sum(instrument_rows.values())
    # Time range from spice or fallback to any instrument
    ref_df = instrument_dfs.get("spice", next(iter(instrument_dfs.values())))
    time_min = ref_df["time"].min().strftime("%Y-%m-%d")
    time_max = ref_df["time"].max().strftime("%Y-%m-%d")

    if n_total >= 100_000_000:
        size_cat = "100M<n<1B"
    elif n_total >= 10_000_000:
        size_cat = "10M<n<100M"
    elif n_total >= 1_000_000:
        size_cat = "1M<n<10M"
    else:
        size_cat = "100K<n<1M"

    # ── Write parquets and README ────────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        # Write per-instrument parquets
        total_size_mb = 0
        for instrument, df_inst in instrument_dfs.items():
            inst_dir = tmp / "data" / instrument
            inst_dir.mkdir(parents=True)
            out = inst_dir / f"{instrument}.parquet"
            df_inst.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
            size_mb = out.stat().st_size / 1024 / 1024
            total_size_mb += size_mb
            print(f"  {instrument}: {size_mb:.1f} MB, {len(df_inst):,} rows, {len(df_inst.columns)} cols")

        print(f"  Total: {total_size_mb:.1f} MB across {len(instrument_dfs)} instruments")

        # ── Generate configs YAML block ──────────────────────────────────────
        configs_yaml = ""
        for instrument in INSTRUMENTS:
            if instrument not in instrument_dfs:
                continue
            is_default = (instrument == "spice")
            configs_yaml += f"""  - config_name: {instrument}
    data_files:
      - split: train
        path: data/{instrument}/{instrument}.parquet
"""
            if is_default:
                configs_yaml += "    default: true\n"

        # ── Instrument table for README ──────────────────────────────────────
        inst_table = "| Instrument | Description | Rows | Columns |\n"
        inst_table += "|------------|-------------|-----:|--------:|\n"
        for instrument in INSTRUMENTS:
            if instrument not in instrument_dfs:
                continue
            desc = INSTRUMENT_DESCRIPTIONS.get(instrument, "")
            rows = len(instrument_dfs[instrument])
            cols = len(instrument_dfs[instrument].columns)
            inst_table += f"| **{instrument.upper()}** | {desc} | {rows:,} | {cols} |\n"

        # ── Banner ───────────────────────────────────────────────────────────
        banner_file = download_banner("maven", tmp)
        banner_md = banner_markdown("maven", banner_file)

        # ── Usage examples ───────────────────────────────────────────────────
        first_inst = next(iter(instrument_dfs))

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "NASA MAVEN Key Parameters (In-Situ)"
language:
  - en
description: "Time-series measurements from NASA's MAVEN Mars orbiter — solar wind, magnetic field, ion composition, neutral gas, and spacecraft ephemeris at 4-8 second cadence (2014-present). Split by instrument."
task_categories:
  - time-series-forecasting
tags:
  - space
  - mars
  - maven
  - atmosphere
  - solar-wind
  - magnetosphere
  - planetary-science
  - nasa
  - open-data
  - tabular-data
  - parquet
size_categories:
  - {size_cat}
configs:
{configs_yaml}---

# NASA MAVEN Key Parameters (In-Situ)
{banner_md}
*Part of the [Solar System Datasets](https://huggingface.co/collections/juliensimon/solar-system-datasets-67dbfa3057e38241e7ea2aee) and [Planetary Science Datasets](https://huggingface.co/collections/juliensimon/planetary-science-datasets-69c24cb17e3db14fc30f0716) collections on Hugging Face.*

![Update MAVEN](https://github.com/juliensimon/space-datasets/actions/workflows/update-maven.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.maven&label=updated&color=brightgreen)

MAVEN (Mars Atmosphere and Volatile EvolutioN) is a NASA Mars orbiter that has been studying the Martian upper atmosphere and its interaction with the solar wind since September 2014. The mission investigates how Mars lost its early atmosphere and water to space — a process driven by solar wind stripping in the absence of a global magnetic field. MAVEN's key parameter (KP) dataset provides time-series measurements from multiple instruments at 4-8 second cadence: solar wind density, velocity, and temperature (SWIA/SWEA), magnetic field components (MAG), ion composition and energy spectra (STATIC), solar energetic particles (SEP), neutral gas composition (NGIMS), and electron density/temperature (LPW). Combined with spacecraft ephemeris (altitude, latitude, longitude, solar zenith angle), this dataset enables studies of atmospheric escape rates, ionospheric variability, and solar wind-magnetosphere coupling at Mars across a full solar cycle.

## Dataset description

Data spans **{time_min}** to **{time_max}**, split into {len(instrument_dfs)} instrument configs:

{inst_table}

Each config shares the same `time` column, enabling cross-instrument joins. Per-instrument splitting reduces download size — load only the instruments you need.

## Usage

```python
from datasets import load_dataset

# Load a single instrument
ds = load_dataset("juliensimon/nasa-maven-kp-insitu", "mag", split="train")
df_mag = ds.to_pandas()

# Load and join multiple instruments
ds_spice = load_dataset("juliensimon/nasa-maven-kp-insitu", "spice", split="train")
ds_swia = load_dataset("juliensimon/nasa-maven-kp-insitu", "swia", split="train")
df = ds_spice.to_pandas().merge(ds_swia.to_pandas(), on="time")

# Filter by altitude for ionospheric studies (< 500 km)
df_iono = df[df["spice_altitude"] < 500]
print(df_iono.describe())
```

## Data source

[LASP SDC](https://lasp.colorado.edu/maven/sdc/public/data/sci/kp/insitu/) — NASA MAVEN Science Data Center at the Laboratory for Atmospheric and Space Physics, University of Colorado Boulder.

## Update schedule

Quarterly via [GitHub Actions](https://github.com/juliensimon/space-datasets). LASP publishes KP data with a ~6-8 month lag.

## Related datasets

- [esa-exomars-tgo-observations](https://huggingface.co/datasets/juliensimon/esa-exomars-tgo-observations) — ESA ExoMars TGO observation catalog
- [esa-mars-express-observations](https://huggingface.co/datasets/juliensimon/esa-mars-express-observations) — ESA Mars Express observation catalog
- [meda-weather](https://huggingface.co/datasets/juliensimon/meda-weather) — Mars surface weather from Perseverance rover
- [solar-wind](https://huggingface.co/datasets/juliensimon/solar-wind) — Real-time solar wind data from L1 monitors

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/nasa-maven-kp-insitu) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{maven_kp_insitu,
  author = {{Simon, Julien}},
  title = {{NASA MAVEN Key Parameters (In-Situ)}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/nasa-maven-kp-insitu}},
  note = {{Based on NASA MAVEN KP data from LASP SDC}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update MAVEN KP in-situ: {len(instrument_dfs)} instruments ({time_min} to {time_max})"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg,
             "--delete", "data/maven_kp_insitu.parquet"],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={n_total}\n")
    print("Done.")


if __name__ == "__main__":
    main()
