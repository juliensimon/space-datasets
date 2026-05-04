#!/usr/bin/env python3
"""Fetch NASA MAVEN Key Parameter (KP) in-situ data from LASP SDC and upload to HF.

MAVEN (Mars Atmosphere and Volatile EvolutioN) has been studying the Martian
upper atmosphere and its interaction with the solar wind since September 2014.
The KP dataset provides time-series measurements from multiple instruments at
4-8 second cadence.

Data source: https://lasp.colorado.edu/maven/sdc/public/data/sci/kp/insitu/
Incremental: downloads existing per-instrument parquets from HF, fetches new
months, merges. Multi-instrument split: one parquet per instrument under data/.
"""

import io
import re
import subprocess
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

from hf_dataset_utils import Pipeline
from hf_dataset_utils.banner import banner_markdown as render_banner
from hf_dataset_utils.banner import download_banner
from hf_dataset_utils.github import emit_output
from hf_dataset_utils.readme import _size_category
from hf_dataset_utils.upload import upload_to_hf
from hf_dataset_utils.validation import check_dataset


BASE_URL = "https://lasp.colorado.edu/maven/sdc/public/data/sci/kp/insitu/"
HF_REPO = "juliensimon/nasa-maven-kp-insitu"

# For initial build, start from 2025 to keep GH Actions runtime under 1 hour.
START_YEAR = 2025
START_MONTH = 1

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "space-datasets/1.0 (https://github.com/juliensimon/space-datasets)"})

# ── Column name mapping (positional index 1-235) ────────────────────────────
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

# Human-readable descriptions per column for README schema tables
COL_DESCRIPTIONS = {
    "time": "Timestamp of measurement (UTC)",
    # ── LPW ──
    "lpw_electron_density":           "Electron number density (cm^-3), derived from probe current",
    "lpw_electron_density_quality":   "Quality flag for electron density (0=good)",
    "lpw_electron_density_quality_2": "Secondary quality flag for electron density",
    "lpw_electron_temperature":           "Electron temperature (eV), derived from probe sweep",
    "lpw_electron_temperature_quality":   "Quality flag for electron temperature (0=good)",
    "lpw_electron_temperature_quality_2": "Secondary quality flag for electron temperature",
    "lpw_spacecraft_potential":           "Spacecraft electrostatic potential relative to plasma (V)",
    "lpw_spacecraft_potential_quality":   "Quality flag for spacecraft potential (0=good)",
    "lpw_spacecraft_potential_quality_2": "Secondary quality flag for spacecraft potential",
    "lpw_e_field_power_2_100hz":    "Electric field power spectral density in 2-100 Hz band (V^2/m^2/Hz)",
    "lpw_e_field_2_100hz_quality":  "Quality flag for 2-100 Hz electric field power",
    "lpw_e_field_power_100_800hz":  "Electric field power spectral density in 100-800 Hz band (V^2/m^2/Hz)",
    "lpw_e_field_100_800hz_quality": "Quality flag for 100-800 Hz electric field power",
    "lpw_e_field_power_0p8_1p0mhz":  "Electric field power spectral density in 0.8-1.0 MHz band (V^2/m^2/Hz)",
    "lpw_e_field_0p8_1p0mhz_quality": "Quality flag for 0.8-1.0 MHz electric field power",
    "lpw_euv_irradiance_0p1_7nm":        "Solar EUV irradiance in 0.1-7 nm band (W/m^2), X-ray/soft X-ray",
    "lpw_euv_irradiance_0p1_7nm_quality": "Quality flag for 0.1-7 nm EUV irradiance",
    "lpw_euv_irradiance_17_22nm":        "Solar EUV irradiance in 17-22 nm band (W/m^2), He II continuum",
    "lpw_euv_irradiance_17_22nm_quality": "Quality flag for 17-22 nm EUV irradiance",
    "lpw_euv_irradiance_lyman_alpha":        "Solar Lyman-alpha irradiance at 121.6 nm (W/m^2), dominant UV line",
    "lpw_euv_irradiance_lyman_alpha_quality": "Quality flag for Lyman-alpha irradiance",
    # ── SWEA ──
    "swea_electron_density":          "Total electron number density (cm^-3) from SWEA energy spectra",
    "swea_electron_density_quality":  "Quality flag for SWEA electron density (0=good)",
    "swea_electron_temperature":          "Electron temperature (eV) from SWEA energy spectra",
    "swea_electron_temperature_quality":  "Quality flag for SWEA electron temperature (0=good)",
    "swea_eflux_par_5_100ev":          "Parallel electron energy flux in 5-100 eV band (eV/cm^2/s/sr/eV)",
    "swea_eflux_par_5_100ev_quality":  "Quality flag for 5-100 eV parallel electron flux",
    "swea_eflux_par_100_500ev":        "Parallel electron energy flux in 100-500 eV band",
    "swea_eflux_par_100_500ev_quality": "Quality flag for 100-500 eV parallel electron flux",
    "swea_eflux_par_500_1000ev":        "Parallel electron energy flux in 500-1000 eV band",
    "swea_eflux_par_500_1000ev_quality": "Quality flag for 500-1000 eV parallel electron flux",
    "swea_eflux_anti_5_100ev":          "Anti-parallel electron energy flux in 5-100 eV band",
    "swea_eflux_anti_5_100ev_quality":  "Quality flag for 5-100 eV anti-parallel electron flux",
    "swea_eflux_anti_100_500ev":        "Anti-parallel electron energy flux in 100-500 eV band",
    "swea_eflux_anti_100_500ev_quality": "Quality flag for 100-500 eV anti-parallel electron flux",
    "swea_eflux_anti_500_1000ev":        "Anti-parallel electron energy flux in 500-1000 eV band",
    "swea_eflux_anti_500_1000ev_quality": "Quality flag for 500-1000 eV anti-parallel electron flux",
    "swea_spectrum_shape":         "Shape parameter of the electron energy spectrum (power-law index)",
    "swea_spectrum_shape_quality": "Quality flag for electron spectrum shape",
    # ── SWIA ──
    "swia_h_density":          "Solar wind proton (H+) number density (cm^-3)",
    "swia_h_density_quality":  "Quality flag for proton density (0=good)",
    "swia_h_velocity_mso_x":          "Proton bulk velocity, MSO X component (km/s; X points Sun->Mars)",
    "swia_h_velocity_mso_x_quality":  "Quality flag for proton velocity MSO-X",
    "swia_h_velocity_mso_y":          "Proton bulk velocity, MSO Y component (km/s)",
    "swia_h_velocity_mso_y_quality":  "Quality flag for proton velocity MSO-Y",
    "swia_h_velocity_mso_z":          "Proton bulk velocity, MSO Z component (km/s; Z toward north ecliptic pole)",
    "swia_h_velocity_mso_z_quality":  "Quality flag for proton velocity MSO-Z",
    "swia_h_temperature":          "Proton temperature (eV), from isotropic Maxwellian fit",
    "swia_h_temperature_quality":  "Quality flag for proton temperature",
    "swia_dynamic_pressure":          "Solar wind dynamic pressure (nPa), 0.5 * n * m_p * v^2",
    "swia_dynamic_pressure_quality":  "Quality flag for solar wind dynamic pressure",
    # ── STATIC ──
    "static_quality_flag": "Overall STATIC instrument quality flag (0=good)",
    "static_h_density":          "Hydrogen ion (H+) density in the ionosphere (cm^-3)",
    "static_h_density_quality":  "Quality flag for H+ density",
    "static_o_density":          "Oxygen ion (O+) density (cm^-3), primary ionospheric ion",
    "static_o_density_quality":  "Quality flag for O+ density",
    "static_o2_density":          "Molecular oxygen ion (O2+) density (cm^-3), dominant below ~200 km",
    "static_o2_density_quality":  "Quality flag for O2+ density",
    "static_h_temperature":          "H+ ion temperature (eV)",
    "static_h_temperature_quality":  "Quality flag for H+ temperature",
    "static_o_temperature":          "O+ ion temperature (eV)",
    "static_o_temperature_quality":  "Quality flag for O+ temperature",
    "static_o2_temperature":          "O2+ ion temperature (eV)",
    "static_o2_temperature_quality":  "Quality flag for O2+ temperature",
    "static_o2_velocity_app_x":          "O2+ bulk velocity, spacecraft APP frame X component (km/s)",
    "static_o2_velocity_app_x_quality":  "Quality flag for O2+ velocity APP-X",
    "static_o2_velocity_app_y":          "O2+ bulk velocity, spacecraft APP frame Y component (km/s)",
    "static_o2_velocity_app_y_quality":  "Quality flag for O2+ velocity APP-Y",
    "static_o2_velocity_app_z":          "O2+ bulk velocity, spacecraft APP frame Z component (km/s)",
    "static_o2_velocity_app_z_quality":  "Quality flag for O2+ velocity APP-Z",
    "static_o2_velocity_mso_x":          "O2+ bulk velocity, MSO frame X component (km/s)",
    "static_o2_velocity_mso_x_quality":  "Quality flag for O2+ velocity MSO-X",
    "static_o2_velocity_mso_y":          "O2+ bulk velocity, MSO frame Y component (km/s)",
    "static_o2_velocity_mso_y_quality":  "Quality flag for O2+ velocity MSO-Y",
    "static_o2_velocity_mso_z":          "O2+ bulk velocity, MSO frame Z component (km/s)",
    "static_o2_velocity_mso_z_quality":  "Quality flag for O2+ velocity MSO-Z",
    "static_h_omni_flux":    "H+ omnidirectional differential particle flux (cm^-2 s^-1 sr^-1 eV^-1)",
    "static_h_energy":       "H+ characteristic energy (eV)",
    "static_h_energy_quality": "Quality flag for H+ characteristic energy",
    "static_he_omni_flux":    "He2+ omnidirectional differential particle flux (cm^-2 s^-1 sr^-1 eV^-1)",
    "static_he_energy":       "He2+ characteristic energy (eV)",
    "static_he_energy_quality": "Quality flag for He2+ characteristic energy",
    "static_o_omni_flux":    "O+ omnidirectional differential particle flux (cm^-2 s^-1 sr^-1 eV^-1)",
    "static_o_energy":       "O+ characteristic energy (eV)",
    "static_o_energy_quality": "Quality flag for O+ characteristic energy",
    "static_o2_omni_flux":    "O2+ omnidirectional differential particle flux (cm^-2 s^-1 sr^-1 eV^-1)",
    "static_o2_energy":       "O2+ characteristic energy (eV)",
    "static_o2_energy_quality": "Quality flag for O2+ characteristic energy",
    "static_h_dir_mso_x":   "H+ dominant flow direction, MSO X component (unit vector)",
    "static_h_dir_mso_y":   "H+ dominant flow direction, MSO Y component (unit vector)",
    "static_h_dir_mso_z":   "H+ dominant flow direction, MSO Z component (unit vector)",
    "static_h_angular_width":         "H+ beam angular half-width (degrees)",
    "static_h_angular_width_quality": "Quality flag for H+ angular width",
    "static_pickup_dir_mso_x":   "Pickup ion dominant flow direction, MSO X (unit vector)",
    "static_pickup_dir_mso_y":   "Pickup ion dominant flow direction, MSO Y (unit vector)",
    "static_pickup_dir_mso_z":   "Pickup ion dominant flow direction, MSO Z (unit vector)",
    "static_pickup_angular_width":         "Pickup ion beam angular half-width (degrees)",
    "static_pickup_angular_width_quality": "Quality flag for pickup ion angular width",
    # ── SEP ──
    "sep_ion_fov1f":          "Ion integral flux, SEP sensor 1 forward FOV (cm^-2 s^-1 sr^-1)",
    "sep_ion_fov1f_quality":  "Quality flag for SEP sensor 1 forward ion flux",
    "sep_ion_fov1r":          "Ion integral flux, SEP sensor 1 reverse FOV (cm^-2 s^-1 sr^-1)",
    "sep_ion_fov1r_quality":  "Quality flag for SEP sensor 1 reverse ion flux",
    "sep_ion_fov2f":          "Ion integral flux, SEP sensor 2 forward FOV (cm^-2 s^-1 sr^-1)",
    "sep_ion_fov2f_quality":  "Quality flag for SEP sensor 2 forward ion flux",
    "sep_ion_fov2r":          "Ion integral flux, SEP sensor 2 reverse FOV (cm^-2 s^-1 sr^-1)",
    "sep_ion_fov2r_quality":  "Quality flag for SEP sensor 2 reverse ion flux",
    "sep_electron_fov1f":          "Electron integral flux, SEP sensor 1 forward FOV (cm^-2 s^-1 sr^-1)",
    "sep_electron_fov1f_quality":  "Quality flag for SEP sensor 1 forward electron flux",
    "sep_electron_fov1r":          "Electron integral flux, SEP sensor 1 reverse FOV (cm^-2 s^-1 sr^-1)",
    "sep_electron_fov1r_quality":  "Quality flag for SEP sensor 1 reverse electron flux",
    "sep_electron_fov2f":          "Electron integral flux, SEP sensor 2 forward FOV (cm^-2 s^-1 sr^-1)",
    "sep_electron_fov2f_quality":  "Quality flag for SEP sensor 2 forward electron flux",
    "sep_electron_fov2r":          "Electron integral flux, SEP sensor 2 reverse FOV (cm^-2 s^-1 sr^-1)",
    "sep_electron_fov2r_quality":  "Quality flag for SEP sensor 2 reverse electron flux",
    "sep_look_1f_mso_x": "SEP sensor 1 forward look direction, MSO X (unit vector)",
    "sep_look_1f_mso_y": "SEP sensor 1 forward look direction, MSO Y (unit vector)",
    "sep_look_1f_mso_z": "SEP sensor 1 forward look direction, MSO Z (unit vector)",
    "sep_look_1r_mso_x": "SEP sensor 1 reverse look direction, MSO X (unit vector)",
    "sep_look_1r_mso_y": "SEP sensor 1 reverse look direction, MSO Y (unit vector)",
    "sep_look_1r_mso_z": "SEP sensor 1 reverse look direction, MSO Z (unit vector)",
    "sep_look_2f_mso_x": "SEP sensor 2 forward look direction, MSO X (unit vector)",
    "sep_look_2f_mso_y": "SEP sensor 2 forward look direction, MSO Y (unit vector)",
    "sep_look_2f_mso_z": "SEP sensor 2 forward look direction, MSO Z (unit vector)",
    "sep_look_2r_mso_x": "SEP sensor 2 reverse look direction, MSO X (unit vector)",
    "sep_look_2r_mso_y": "SEP sensor 2 reverse look direction, MSO Y (unit vector)",
    "sep_look_2r_mso_z": "SEP sensor 2 reverse look direction, MSO Z (unit vector)",
    # ── MAG ──
    "mag_mso_x":         "Magnetic field vector, MSO X component (nT; X points Sun->Mars)",
    "mag_mso_x_quality": "Quality flag for magnetic field MSO-X",
    "mag_mso_y":         "Magnetic field vector, MSO Y component (nT)",
    "mag_mso_y_quality": "Quality flag for magnetic field MSO-Y",
    "mag_mso_z":         "Magnetic field vector, MSO Z component (nT; Z toward north ecliptic pole)",
    "mag_mso_z_quality": "Quality flag for magnetic field MSO-Z",
    "mag_geo_x":         "Magnetic field vector, areocentric GEO X component (nT)",
    "mag_geo_x_quality": "Quality flag for magnetic field GEO-X",
    "mag_geo_y":         "Magnetic field vector, areocentric GEO Y component (nT)",
    "mag_geo_y_quality": "Quality flag for magnetic field GEO-Y",
    "mag_geo_z":         "Magnetic field vector, areocentric GEO Z component (nT; Z toward Mars north pole)",
    "mag_geo_z_quality": "Quality flag for magnetic field GEO-Z",
    "mag_rms_deviation": "RMS deviation of the magnetic field magnitude over the accumulation window (nT)",
    "mag_rms_quality":   "Quality flag for magnetic field RMS deviation",
    # ── NGIMS ──
    "ngims_he":           "Helium (He) neutral number density in the upper atmosphere (cm^-3)",
    "ngims_he_precision": "1-sigma precision of the He density measurement",
    "ngims_he_quality":   "Quality flag for He density (0=good)",
    "ngims_o":            "Atomic oxygen (O) neutral number density (cm^-3)",
    "ngims_o_precision":  "1-sigma precision of the O density measurement",
    "ngims_o_quality":    "Quality flag for O density",
    "ngims_co":           "Carbon monoxide (CO) neutral number density (cm^-3)",
    "ngims_co_precision": "1-sigma precision of the CO density measurement",
    "ngims_co_quality":   "Quality flag for CO density",
    "ngims_n2":           "Molecular nitrogen (N2) neutral number density (cm^-3), dominant above ~200 km",
    "ngims_n2_precision": "1-sigma precision of the N2 density measurement",
    "ngims_n2_quality":   "Quality flag for N2 density",
    "ngims_no":           "Nitric oxide (NO) neutral number density (cm^-3)",
    "ngims_no_precision": "1-sigma precision of the NO density measurement",
    "ngims_no_quality":   "Quality flag for NO density",
    "ngims_ar":           "Argon (Ar) neutral number density (cm^-3), used as inert tracer",
    "ngims_ar_precision": "1-sigma precision of the Ar density measurement",
    "ngims_ar_quality":   "Quality flag for Ar density",
    "ngims_co2":           "Carbon dioxide (CO2) neutral number density (cm^-3), dominant below ~200 km",
    "ngims_co2_precision": "1-sigma precision of the CO2 density measurement",
    "ngims_co2_quality":   "Quality flag for CO2 density",
    "ngims_ion32":           "Ion density at m/z=32, primarily O2+ (cm^-3)",
    "ngims_ion32_precision": "1-sigma precision of the m/z=32 ion density",
    "ngims_ion32_quality":   "Quality flag for m/z=32 ion density",
    "ngims_ion44":           "Ion density at m/z=44, primarily CO2+ (cm^-3)",
    "ngims_ion44_precision": "1-sigma precision of the m/z=44 ion density",
    "ngims_ion44_quality":   "Quality flag for m/z=44 ion density",
    "ngims_ion30":           "Ion density at m/z=30, primarily NO+ (cm^-3)",
    "ngims_ion30_precision": "1-sigma precision of the m/z=30 ion density",
    "ngims_ion30_quality":   "Quality flag for m/z=30 ion density",
    "ngims_ion16":           "Ion density at m/z=16, primarily O+ (cm^-3)",
    "ngims_ion16_precision": "1-sigma precision of the m/z=16 ion density",
    "ngims_ion16_quality":   "Quality flag for m/z=16 ion density",
    "ngims_ion28":           "Ion density at m/z=28, CO+ or N2+ (cm^-3)",
    "ngims_ion28_precision": "1-sigma precision of the m/z=28 ion density",
    "ngims_ion28_quality":   "Quality flag for m/z=28 ion density",
    "ngims_ion12":           "Ion density at m/z=12, primarily C+ (cm^-3)",
    "ngims_ion12_precision": "1-sigma precision of the m/z=12 ion density",
    "ngims_ion12_quality":   "Quality flag for m/z=12 ion density",
    "ngims_ion17":           "Ion density at m/z=17, primarily OH+ (cm^-3)",
    "ngims_ion17_precision": "1-sigma precision of the m/z=17 ion density",
    "ngims_ion17_quality":   "Quality flag for m/z=17 ion density",
    "ngims_ion14":           "Ion density at m/z=14, primarily N+ (cm^-3)",
    "ngims_ion14_precision": "1-sigma precision of the m/z=14 ion density",
    "ngims_ion14_quality":   "Quality flag for m/z=14 ion density",
    # ── SPICE ──
    "spice_geo_x": "Spacecraft position, areocentric GEO X component (km)",
    "spice_geo_y": "Spacecraft position, areocentric GEO Y component (km)",
    "spice_geo_z": "Spacecraft position, areocentric GEO Z component (km; toward Mars north pole)",
    "spice_mso_x": "Spacecraft position, MSO frame X component (km; X points Sun->Mars)",
    "spice_mso_y": "Spacecraft position, MSO frame Y component (km)",
    "spice_mso_z": "Spacecraft position, MSO frame Z component (km; Z toward north ecliptic pole)",
    "spice_longitude":          "Sub-spacecraft point east longitude on Mars (degrees, 0-360)",
    "spice_latitude":           "Sub-spacecraft point latitude on Mars (degrees, -90 to +90)",
    "spice_solar_zenith_angle": "Solar zenith angle at the sub-spacecraft point (degrees, 0=subsolar)",
    "spice_local_time":         "Local solar time at the sub-spacecraft point (hours, 0-24)",
    "spice_altitude":           "Spacecraft altitude above Mars areoid (km)",
    "spice_sc_att_geo_x": "Spacecraft +Z axis direction, GEO frame X component (unit vector)",
    "spice_sc_att_geo_y": "Spacecraft +Z axis direction, GEO frame Y component (unit vector)",
    "spice_sc_att_geo_z": "Spacecraft +Z axis direction, GEO frame Z component (unit vector)",
    "spice_sc_att_mso_x": "Spacecraft +Z axis direction, MSO frame X component (unit vector)",
    "spice_sc_att_mso_y": "Spacecraft +Z axis direction, MSO frame Y component (unit vector)",
    "spice_sc_att_mso_z": "Spacecraft +Z axis direction, MSO frame Z component (unit vector)",
    "spice_app_geo_x": "Articulated Payload Platform (APP) boresight, GEO frame X (unit vector)",
    "spice_app_geo_y": "Articulated Payload Platform (APP) boresight, GEO frame Y (unit vector)",
    "spice_app_geo_z": "Articulated Payload Platform (APP) boresight, GEO frame Z (unit vector)",
    "spice_app_mso_x": "Articulated Payload Platform (APP) boresight, MSO frame X (unit vector)",
    "spice_app_mso_y": "Articulated Payload Platform (APP) boresight, MSO frame Y (unit vector)",
    "spice_app_mso_z": "Articulated Payload Platform (APP) boresight, MSO frame Z (unit vector)",
    "spice_orbit_number":       "MAVEN orbit number since Mars orbit insertion (September 2014)",
    "spice_inbound_outbound":   "Orbit phase flag: +1=inbound (before periapsis), -1=outbound (after periapsis)",
    "spice_mars_season_ls":     "Mars solar longitude Ls (degrees; 0=northern spring equinox)",
    "spice_mars_sun_distance_au": "Mars-Sun distance (AU)",
    "spice_subsolar_longitude": "Sub-solar point east longitude on Mars (degrees)",
    "spice_subsolar_latitude":  "Sub-solar point latitude on Mars (degrees)",
    "spice_submars_sun_longitude": "Sub-Mars point longitude as seen from the Sun (degrees)",
    "spice_submars_sun_latitude":  "Sub-Mars point latitude as seen from the Sun (degrees)",
    "spice_rot_mars_r1c1": "Mars body-fixed to inertial rotation matrix, element [1,1]",
    "spice_rot_mars_r1c2": "Mars body-fixed to inertial rotation matrix, element [1,2]",
    "spice_rot_mars_r1c3": "Mars body-fixed to inertial rotation matrix, element [1,3]",
    "spice_rot_mars_r2c1": "Mars body-fixed to inertial rotation matrix, element [2,1]",
    "spice_rot_mars_r2c2": "Mars body-fixed to inertial rotation matrix, element [2,2]",
    "spice_rot_mars_r2c3": "Mars body-fixed to inertial rotation matrix, element [2,3]",
    "spice_rot_mars_r3c1": "Mars body-fixed to inertial rotation matrix, element [3,1]",
    "spice_rot_mars_r3c2": "Mars body-fixed to inertial rotation matrix, element [3,2]",
    "spice_rot_mars_r3c3": "Mars body-fixed to inertial rotation matrix, element [3,3]",
    "spice_rot_sc_r1c1": "Spacecraft body to inertial rotation matrix, element [1,1]",
    "spice_rot_sc_r1c2": "Spacecraft body to inertial rotation matrix, element [1,2]",
    "spice_rot_sc_r1c3": "Spacecraft body to inertial rotation matrix, element [1,3]",
    "spice_rot_sc_r2c1": "Spacecraft body to inertial rotation matrix, element [2,1]",
    "spice_rot_sc_r2c2": "Spacecraft body to inertial rotation matrix, element [2,2]",
    "spice_rot_sc_r2c3": "Spacecraft body to inertial rotation matrix, element [2,3]",
    "spice_rot_sc_r3c1": "Spacecraft body to inertial rotation matrix, element [3,1]",
    "spice_rot_sc_r3c2": "Spacecraft body to inertial rotation matrix, element [3,2]",
    "spice_rot_sc_r3c3": "Spacecraft body to inertial rotation matrix, element [3,3]",
}

INSTRUMENT_DESCRIPTIONS = {
    "lpw":    "Langmuir Probe and Waves -- electron density, temperature, EUV irradiance",
    "swea":   "Solar Wind Electron Analyzer -- electron energy spectra and pitch angle distributions",
    "swia":   "Solar Wind Ion Analyzer -- solar wind proton density, velocity, temperature",
    "static": "Suprathermal and Thermal Ion Composition -- ion mass/charge composition and energy spectra",
    "sep":    "Solar Energetic Particle -- high-energy particle fluxes from solar events",
    "mag":    "Magnetometer -- magnetic field vector components (MSO and GEO frames)",
    "ngims":  "Neutral Gas and Ion Mass Spectrometer -- neutral and ion densities in upper atmosphere",
    "spice":  "Spacecraft ephemeris -- position, attitude, altitude, solar zenith angle, orbit metadata",
}

DESCRIPTION = """\
MAVEN (Mars Atmosphere and Volatile EvolutioN) is a NASA Mars orbiter that has been \
studying the Martian upper atmosphere and its interaction with the solar wind since \
September 2014. The mission investigates how Mars lost its early atmosphere and water \
to space -- a process driven by solar wind stripping in the absence of a global magnetic \
field. MAVEN's key parameter (KP) dataset provides time-series measurements from multiple \
instruments at 4-8 second cadence: solar wind density, velocity, and temperature (SWIA/SWEA), \
magnetic field components (MAG), ion composition and energy spectra (STATIC), solar energetic \
particles (SEP), neutral gas composition (NGIMS), and electron density/temperature (LPW). \
Combined with spacecraft ephemeris (altitude, latitude, longitude, solar zenith angle), this \
dataset enables studies of atmospheric escape rates, ionospheric variability, and solar \
wind-magnetosphere coupling at Mars across a full solar cycle."""


# ── Data parsing helpers (domain-specific) ────────────────────────────────

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
    filenames = re.findall(r'href="(mvn_kp_insitu_[^"]+\.tab)"', resp.text)
    return sorted(set(filenames))


def parse_tab_file(content: str) -> pd.DataFrame | None:
    """Parse a MAVEN KP .tab file (fixed-width text with # header lines)."""
    lines = content.splitlines()
    data_start_line = None
    for line in lines[:20]:
        if "Line on which data begins" in line:
            match = re.search(r"#\s+(\d+)\s+Line on which", line)
            if match:
                data_start_line = int(match.group(1)) - 1
                break
    if data_start_line is None:
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
            io.StringIO(data_text), sep=r"\s+", header=None,
            na_values=["-9.99999990E+30", "-1.00000000E+31", "NO_DATA", "NaN"],
        )
    except Exception:
        return None
    if df.empty:
        return None
    n_cols = len(df.columns)
    col_names = [NAMES.get(i + 1, f"unknown_{i + 1}") for i in range(n_cols)]
    df.columns = col_names
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    for col in df.columns:
        if col != "time" and df[col].dtype == object:
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
    cols = [c for c in cols if c in df.columns]
    return df[cols].copy()


def clean_instrument_df(df: pd.DataFrame) -> pd.DataFrame:
    """Drop rows where all non-time columns are null."""
    non_time = [c for c in df.columns if c != "time"]
    if non_time:
        df = df.dropna(subset=non_time, how="all")
    return df


def load_existing_instruments(tmp_dir: Path) -> dict[str, pd.DataFrame]:
    """Download existing per-instrument parquets from HF."""
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
        parquet_path = tmp_dir / "data" / instrument / f"{instrument}.parquet"
        if parquet_path.exists():
            df = pd.read_parquet(parquet_path)
            if "time" in df.columns:
                df["time"] = pd.to_datetime(df["time"])
            existing[instrument] = df
            print(f"  Loaded existing {instrument}: {len(df):,} rows")
    return existing


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=None,
                        help="Fetch only this single year (e.g. --year 2020)")
    parser.add_argument("--months", type=int, default=None,
                        help="Fetch last N months (rolling window, skips large HF download)")
    args = parser.parse_args()

    print("Fetching NASA MAVEN KP in-situ data...")

    yesterday = date.today() - timedelta(days=1)
    existing = {}

    if args.year:
        fetch_start_year, fetch_start_month = args.year, 1
        fetch_end_year, fetch_end_month = args.year, 12
        print(f"  Single-year mode: fetching {args.year}")
    elif args.months:
        # Rolling window: avoids downloading the full ~14 GB existing dataset
        cutoff = date.today().replace(day=1) - timedelta(days=args.months * 30)
        fetch_start_year, fetch_start_month = cutoff.year, cutoff.month
        fetch_end_year, fetch_end_month = yesterday.year, yesterday.month
        print(f"  Rolling {args.months}-month window from {fetch_start_year}-{fetch_start_month:02d}")
    else:
        fetch_start_year, fetch_start_month = START_YEAR, START_MONTH
        fetch_end_year, fetch_end_month = yesterday.year, yesterday.month
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
    df_new = pd.concat(all_new, ignore_index=True) if all_new else pd.DataFrame()
    if not df_new.empty:
        print(f"  New data: {len(df_new):,} rows")
    else:
        print("  No new data downloaded")

    if df_new.empty and not existing:
        print("::error::No data available")
        sys.exit(1)

    # ── Per-instrument merge, clean, write ───────────────────────────────
    instrument_dfs = {}
    instrument_rows = {}

    for instrument in INSTRUMENTS:
        df_inst_new = extract_instrument_df(df_new, instrument) if not df_new.empty else pd.DataFrame()
        df_inst_existing = existing.get(instrument)

        if df_inst_existing is not None and not df_inst_new.empty:
            df_inst = pd.concat([df_inst_existing, df_inst_new], ignore_index=True)
            df_inst = df_inst.drop_duplicates(subset=["time"], keep="last")
            print(f"  {instrument}: merged {len(df_inst_existing):,} + {len(df_inst_new):,} -> {len(df_inst):,}")
        elif df_inst_existing is not None:
            df_inst = df_inst_existing
            print(f"  {instrument}: using existing {len(df_inst):,} rows")
        elif not df_inst_new.empty:
            df_inst = df_inst_new
            print(f"  {instrument}: new {len(df_inst):,} rows")
        else:
            print(f"  {instrument}: no data, skipping")
            continue

        df_inst = df_inst.sort_values("time").reset_index(drop=True)
        df_inst = clean_instrument_df(df_inst)

        if df_inst.empty or len(df_inst.columns) <= 1:
            print(f"    {instrument}: empty after cleaning, skipping")
            continue

        instrument_dfs[instrument] = df_inst
        instrument_rows[instrument] = len(df_inst)

    if not instrument_dfs:
        print("::error::No instrument data after cleaning")
        sys.exit(1)

    # ── Validate ────────────────────────────────────────────────────────
    if "spice" in instrument_dfs:
        check_dataset(instrument_dfs["spice"], "maven", min_rows=100_000,
                      expected_columns=["time", "spice_altitude"],
                      critical_columns=["time"])
    else:
        largest = max(instrument_dfs, key=lambda k: len(instrument_dfs[k]))
        check_dataset(instrument_dfs[largest], "maven", min_rows=100_000,
                      expected_columns=["time"], critical_columns=["time"])

    # ── Stats ───────────────────────────────────────────────────────────
    n_total = sum(instrument_rows.values())
    ref_df = instrument_dfs.get("spice", next(iter(instrument_dfs.values())))
    time_min = ref_df["time"].min().strftime("%Y-%m-%d")
    time_max = ref_df["time"].max().strftime("%Y-%m-%d")
    size_cat = _size_category(n_total)

    # ── Write and upload using Pipeline context ─────────────────────────
    with Pipeline(
        repo=HF_REPO,
        pretty_name="NASA MAVEN Key Parameters (In-Situ)",
        description=DESCRIPTION,
        tags=["space", "mars", "maven", "atmosphere", "solar-wind",
              "magnetosphere", "planetary-science", "nasa",
              "open-data", "tabular-data", "parquet"],
        source_url="https://lasp.colorado.edu/maven/sdc/public/data/sci/kp/insitu/",
        task_categories=["time-series-forecasting"],
        update_schedule="Quarterly via [GitHub Actions](https://github.com/juliensimon/space-datasets). LASP publishes KP data with a ~6-8 month lag.",
        collection_url="https://huggingface.co/collections/juliensimon/space-probe-and-mission-datasets-69c3fe82d410a42b1e313167",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA24309/PIA24309~small.jpg",
            "alt": "Exploring Jezero Crater on Mars (illustration)",
            "credit": "NASA/JPL-Caltech",
        },
        related_datasets=[
            "juliensimon/esa-exomars-tgo-observations",
            "juliensimon/esa-mars-express-observations",
            "juliensimon/mars-perseverance-weather",
            "juliensimon/solar-wind",
        ],
    ) as p:
        # Write per-instrument parquets
        total_size_mb = 0
        for instrument, df_inst in instrument_dfs.items():
            inst_dir = p.data_dir / instrument
            inst_dir.mkdir(parents=True)
            out = inst_dir / f"{instrument}.parquet"
            df_inst.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
            size_mb = out.stat().st_size / 1024 / 1024
            total_size_mb += size_mb
            print(f"  {instrument}: {size_mb:.1f} MB, {len(df_inst):,} rows, {len(df_inst.columns)} cols")
        print(f"  Total: {total_size_mb:.1f} MB across {len(instrument_dfs)} instruments")

        # ── Build configs YAML ──────────────────────────────────────────
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

        # ── Instrument table ────────────────────────────────────────────
        inst_table = "| Instrument | Description | Rows | Columns |\n"
        inst_table += "|------------|-------------|-----:|--------:|\n"
        for instrument in INSTRUMENTS:
            if instrument not in instrument_dfs:
                continue
            desc = INSTRUMENT_DESCRIPTIONS.get(instrument, "")
            rows = len(instrument_dfs[instrument])
            cols = len(instrument_dfs[instrument].columns)
            inst_table += f"| **{instrument.upper()}** | {desc} | {rows:,} | {cols} |\n"

        # ── Per-instrument schema sections ──────────────────────────────
        schema_sections = ""
        for instrument in INSTRUMENTS:
            if instrument not in instrument_dfs:
                continue
            df_inst = instrument_dfs[instrument]
            inst_full = INSTRUMENT_DESCRIPTIONS.get(instrument, instrument.upper())
            schema_sections += f"\n### {instrument.upper()} -- {inst_full}\n\n"
            schema_sections += "| Column | Type | Description |\n"
            schema_sections += "|--------|------|-------------|\n"
            for col in df_inst.columns:
                desc = COL_DESCRIPTIONS.get(col, "")
                dtype = str(df_inst[col].dtype)
                schema_sections += f"| `{col}` | {dtype} | {desc} |\n"

        # ── Banner ──────────────────────────────────────────────────────
        banner_file = download_banner(
            "https://images-assets.nasa.gov/image/PIA24309/PIA24309~small.jpg",
            p.tmp_dir)
        banner_md = ""
        if banner_file:
            banner_md = render_banner(
                "Exploring Jezero Crater on Mars (illustration)",
                "NASA/JPL-Caltech",
                filename=banner_file,
            )

        # ── README (custom multi-config format) ─────────────────────────
        (p.tmp_dir / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "NASA MAVEN Key Parameters (In-Situ)"
language:
  - en
description: "Time-series measurements from NASA's MAVEN Mars orbiter -- solar wind, magnetic field, ion composition, neutral gas, and spacecraft ephemeris at 4-8 second cadence (2014-present). Split by instrument."
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
*Part of a [dataset collection](https://huggingface.co/collections/juliensimon/space-probe-and-mission-datasets-69c3fe82d410a42b1e313167) on Hugging Face.*

## Dataset description

Data spans **{time_min}** to **{time_max}**, split into {len(instrument_dfs)} instrument configs:

{inst_table}

Each config shares the same `time` column, enabling cross-instrument joins. Per-instrument splitting reduces download size -- load only the instruments you need.

**Coordinate frames:** MSO (Mars-Sun-Orbit) has X pointing Sun->Mars, Z toward north ecliptic pole, Y completing the right-hand system. GEO (areocentric geographic) has Z toward the Mars north pole, X through 0 deg longitude. APP is the Articulated Payload Platform body frame used by NGIMS, IUVS, and STATIC.

**Quality flags:** Each physical measurement has one or two integer quality flags. 0 = good; higher values indicate caution levels defined in the MAVEN KP SIS document. Use `flag == 0` for the highest-quality science data.

## Schema
{schema_sections}

## Quick stats

- **{n_total:,}** total measurements across {len(instrument_dfs)} instruments
- **Time span:** {time_min} to {time_max}
- **Cadence:** 4-8 seconds

## Usage

```python
from datasets import load_dataset

# Load a single instrument
ds = load_dataset("{HF_REPO}", "mag", split="train")
df_mag = ds.to_pandas()

# Load and join multiple instruments
ds_spice = load_dataset("{HF_REPO}", "spice", split="train")
ds_swia = load_dataset("{HF_REPO}", "swia", split="train")
df = ds_spice.to_pandas().merge(ds_swia.to_pandas(), on="time")

# Filter by altitude for ionospheric studies (< 500 km)
import matplotlib.pyplot as plt
df_iono = df[df["spice_altitude"] < 500]
plt.scatter(df_iono["spice_solar_zenith_angle"], df_iono["swia_h_density"], s=0.1, alpha=0.3)
plt.xlabel("Solar Zenith Angle (deg)")
plt.ylabel("Proton Density (cm^-3)")
plt.title("Solar Wind Density vs Solar Zenith Angle")
plt.show()
```

## Data source

[LASP SDC](https://lasp.colorado.edu/maven/sdc/public/data/sci/kp/insitu/) -- NASA MAVEN Science Data Center at the Laboratory for Atmospheric and Space Physics, University of Colorado Boulder.

## Related datasets

- [juliensimon/esa-exomars-tgo-observations](https://huggingface.co/datasets/juliensimon/esa-exomars-tgo-observations)
- [juliensimon/esa-mars-express-observations](https://huggingface.co/datasets/juliensimon/esa-mars-express-observations)
- [juliensimon/meda-weather](https://huggingface.co/datasets/juliensimon/meda-weather)
- [juliensimon/solar-wind](https://huggingface.co/datasets/juliensimon/solar-wind)

## Citation

```bibtex
@dataset{{maven_kp_insitu,
  title = {{NASA MAVEN Key Parameters (In-Situ)}},
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
        commit_msg = f"Update MAVEN KP in-situ: {len(instrument_dfs)} instruments ({time_min} to {time_max})"
        upload_to_hf(HF_REPO, p.tmp_dir, commit_msg)

    emit_output(rows=n_total)
    print("Done.")


if __name__ == "__main__":
    main()
