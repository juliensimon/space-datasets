#!/usr/bin/env python3
"""Fetch OMNI hourly merged solar wind & geomagnetic index data from NASA GSFC and upload to HF.

Source: NASA/GSFC Space Physics Data Facility (SPDF) -- OMNI 2 hourly dataset.
Merged near-Earth solar wind magnetic field, plasma, energetic particles,
and geomagnetic activity indices from multiple spacecraft.
"""

import time
from io import StringIO

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

HF_REPO = "juliensimon/omni-solar-wind-parameters"
DATA_URL = "https://spdf.gsfc.nasa.gov/pub/data/omni/low_res_omni/omni2_all_years.dat"

# ── Column definitions (55 columns, fixed-width whitespace-delimited) ──
COLUMNS = [
    "year", "day_of_year", "hour",
    "bartels_rotation_number", "imf_spacecraft_id", "sw_plasma_spacecraft_id",
    "n_imf_points", "n_plasma_points",
    "b_magnitude_avg_nt", "b_magnitude_vector_nt",
    "b_lat_angle_gse_deg", "b_lon_angle_gse_deg",
    "bx_gse_nt", "by_gse_nt", "bz_gse_nt", "by_gsm_nt", "bz_gsm_nt",
    "sigma_b_magnitude_nt", "sigma_b_vector_nt",
    "sigma_bx_nt", "sigma_by_nt", "sigma_bz_nt",
    "proton_temperature_k", "proton_density_cm3",
    "flow_speed_kms", "flow_lon_angle_deg", "flow_lat_angle_deg",
    "alpha_proton_ratio", "flow_pressure_npa",
    "sigma_t_k", "sigma_n_cm3", "sigma_v_kms",
    "sigma_phi_v_deg", "sigma_theta_v_deg", "sigma_alpha_proton_ratio",
    "electric_field_mvpm", "plasma_beta", "alfven_mach_number",
    "kp_index", "sunspot_number", "dst_index_nt", "ae_index_nt",
    "proton_flux_gt1mev", "proton_flux_gt2mev", "proton_flux_gt4mev",
    "proton_flux_gt10mev", "proton_flux_gt30mev", "proton_flux_gt60mev",
    "flux_flag",
    "ap_index_nt", "f107_index_sfu", "pc_n_index",
    "al_index_nt", "au_index_nt", "magnetosonic_mach_number",
]

# Fill values per column -- values at or above these thresholds are NaN
FILL_VALUES = {
    "bartels_rotation_number": 9999,
    "imf_spacecraft_id": 99,
    "sw_plasma_spacecraft_id": 99,
    "n_imf_points": 999,
    "n_plasma_points": 999,
    "b_magnitude_avg_nt": 999.9,
    "b_magnitude_vector_nt": 999.9,
    "b_lat_angle_gse_deg": 999.9,
    "b_lon_angle_gse_deg": 999.9,
    "bx_gse_nt": 999.9,
    "by_gse_nt": 999.9,
    "bz_gse_nt": 999.9,
    "by_gsm_nt": 999.9,
    "bz_gsm_nt": 999.9,
    "sigma_b_magnitude_nt": 999.9,
    "sigma_b_vector_nt": 999.9,
    "sigma_bx_nt": 999.9,
    "sigma_by_nt": 999.9,
    "sigma_bz_nt": 999.9,
    "proton_temperature_k": 9999999.0,
    "proton_density_cm3": 999.9,
    "flow_speed_kms": 9999.0,
    "flow_lon_angle_deg": 999.9,
    "flow_lat_angle_deg": 999.9,
    "alpha_proton_ratio": 9.999,
    "flow_pressure_npa": 99.99,
    "sigma_t_k": 9999999.0,
    "sigma_n_cm3": 999.9,
    "sigma_v_kms": 9999.0,
    "sigma_phi_v_deg": 999.9,
    "sigma_theta_v_deg": 999.9,
    "sigma_alpha_proton_ratio": 9.999,
    "electric_field_mvpm": 999.99,
    "plasma_beta": 999.99,
    "alfven_mach_number": 999.9,
    "kp_index": 99,
    "sunspot_number": 999,
    "dst_index_nt": 99999,
    "ae_index_nt": 9999,
    "proton_flux_gt1mev": 999999.99,
    "proton_flux_gt2mev": 99999.99,
    "proton_flux_gt4mev": 99999.99,
    "proton_flux_gt10mev": 99999.99,
    "proton_flux_gt30mev": 99999.99,
    "proton_flux_gt60mev": 99999.99,
    "ap_index_nt": 999,
    "f107_index_sfu": 999.9,
    "pc_n_index": 999.9,
    "al_index_nt": 99999,
    "au_index_nt": 99999,
    "magnetosonic_mach_number": 99.9,
}

# Columns to drop (metadata, not useful for analysis)
DROP_COLUMNS = [
    "imf_spacecraft_id", "sw_plasma_spacecraft_id",
    "n_imf_points", "n_plasma_points", "flux_flag",
]

# ── Column descriptions ────────────────────────────────────────────────
COLUMN_DESCRIPTIONS = {
    "datetime": "Observation timestamp (UTC, hourly cadence). OMNI data begins 1963 and is updated daily.",
    "bartels_rotation_number": "Bartels solar rotation number: sequential count of 27-day rotation periods; used to align data with the solar rotation cycle.",
    "b_magnitude_avg_nt": "Average IMF magnitude 1/N SUM |B| (nT); scalar average of field magnitude over the hour.",
    "b_magnitude_vector_nt": "Magnitude of the hourly-averaged field vector (nT); differs from b_magnitude_avg_nt when the field direction varies within the hour.",
    "b_lat_angle_gse_deg": "Latitude angle of the average IMF vector in GSE coordinates (degrees); +90 = northward, -90 = southward.",
    "b_lon_angle_gse_deg": "Longitude angle of the average IMF vector in GSE coordinates (degrees); 0 = sunward, 180 = anti-sunward.",
    "bx_gse_nt": "IMF Bx component in GSE/GSM coordinates (nT); positive sunward along the Sun-Earth line. Bx is identical in GSE and GSM.",
    "by_gse_nt": "IMF By component in GSE coordinates (nT); positive dawnward (opposite to Earth's orbital motion).",
    "bz_gse_nt": "IMF Bz component in GSE coordinates (nT); positive northward (perpendicular to ecliptic).",
    "by_gsm_nt": "IMF By component in GSM coordinates (nT); GSM rotates with Earth's dipole tilt, important for magnetospheric coupling.",
    "bz_gsm_nt": "IMF Bz component in GSM coordinates (nT); negative (southward) Bz drives magnetic reconnection and geomagnetic storms.",
    "sigma_b_magnitude_nt": "RMS standard deviation of |B| within the averaging hour (nT); measures IMF variability.",
    "sigma_b_vector_nt": "RMS standard deviation of the field vector magnitude within the hour (nT).",
    "sigma_bx_nt": "RMS standard deviation of Bx component, GSE (nT).",
    "sigma_by_nt": "RMS standard deviation of By component, GSE (nT).",
    "sigma_bz_nt": "RMS standard deviation of Bz component, GSE (nT).",
    "proton_temperature_k": "Solar wind proton temperature (K); typical range 10^4-5x10^5 K; elevated in fast streams, depressed in ICMEs.",
    "proton_density_cm3": "Solar wind proton number density (cm^-3); typical 5-10 cm^-3 at 1 AU; spikes during CME sheaths.",
    "flow_speed_kms": "Solar wind bulk plasma speed (km/s); slow wind: 350-450 km/s, fast streams: 600-800 km/s.",
    "flow_lon_angle_deg": "Flow longitude angle in quasi-GSE coordinates (degrees); small departures from 180 deg indicate non-radial flow.",
    "flow_lat_angle_deg": "Flow latitude angle in GSE coordinates (degrees); small departures from 0 deg indicate north/south deflections.",
    "alpha_proton_ratio": "He2+/H+ number density ratio (Na/Np); typical 0.02-0.08; elevated in fast streams and CMEs.",
    "flow_pressure_npa": "Solar wind dynamic (ram) pressure 0.5*rho*v^2 (nPa); typical 1-10 nPa; high values compress the dayside magnetopause.",
    "sigma_t_k": "Intra-hour standard deviation of proton temperature (K); reflects solar wind variability within the averaging window.",
    "sigma_n_cm3": "Intra-hour standard deviation of proton density (cm^-3).",
    "sigma_v_kms": "Intra-hour standard deviation of flow speed (km/s).",
    "sigma_phi_v_deg": "Intra-hour standard deviation of flow longitude angle (degrees).",
    "sigma_theta_v_deg": "Intra-hour standard deviation of flow latitude angle (degrees).",
    "sigma_alpha_proton_ratio": "Intra-hour standard deviation of the He2+/H+ density ratio.",
    "electric_field_mvpm": "Interplanetary electric field component -V x Bz (mV/m); negative (southward Bz) drives magnetospheric energy input; typical range -10 to +10 mV/m.",
    "plasma_beta": "Ratio of thermal pressure to magnetic pressure (nkT / B^2/8pi); beta < 1 = magnetically dominated, beta > 1 = thermally dominated.",
    "alfven_mach_number": "Solar wind speed divided by Alfven speed; typical ~8-10 at 1 AU; determines bow shock and magnetopause standoff.",
    "kp_index": "Planetary geomagnetic 3-hourly Kp index stored as integer x 10 (e.g. 27 = Kp 2.7); scale 0-90; Kp >= 50 = geomagnetic storm.",
    "sunspot_number": "International sunspot number (SILSO v2); tracks the 11-year solar cycle; range ~0-300.",
    "dst_index_nt": "Disturbance Storm Time ring-current index (nT); 0 = quiet; -30 to -50 nT = minor storm; < -100 nT = intense storm.",
    "ae_index_nt": "Auroral Electrojet AE index (nT) = AU - AL; measures substorm and auroral zone current intensity; 0-2000+ nT.",
    "proton_flux_gt1mev": "Energetic proton flux for particles > 1 MeV (1/cm^2 s sr); elevated during solar proton events (SPEs).",
    "proton_flux_gt2mev": "Energetic proton flux for particles > 2 MeV (1/cm^2 s sr).",
    "proton_flux_gt4mev": "Energetic proton flux for particles > 4 MeV (1/cm^2 s sr).",
    "proton_flux_gt10mev": "Energetic proton flux for particles > 10 MeV (1/cm^2 s sr); NOAA SPE threshold: 10 pfu at this energy.",
    "proton_flux_gt30mev": "Energetic proton flux for particles > 30 MeV (1/cm^2 s sr).",
    "proton_flux_gt60mev": "Energetic proton flux for particles > 60 MeV (1/cm^2 s sr).",
    "ap_index_nt": "Linear equivalent of Kp index (nT); 3-hourly; range 0-400 nT; ap >= 100 = major geomagnetic storm.",
    "f107_index_sfu": "Solar 10.7 cm radio flux index (SFU, 1 SFU = 10^-22 W/m^2/Hz); solar cycle range ~65-300 SFU; proxy for EUV output.",
    "pc_n_index": "Polar Cap (North) magnetic activity index from Thule/Qaanaaq magnetometer; tracks cross-polar-cap potential and substorm precursors.",
    "al_index_nt": "Auroral Electrojet lower (AL) index (nT); measures westward electrojet intensity; negative excursions indicate substorm onset.",
    "au_index_nt": "Auroral Electrojet upper (AU) index (nT); measures eastward electrojet intensity; AE = AU - AL.",
    "magnetosonic_mach_number": "Solar wind speed divided by the fast magnetosonic wave speed; determines bow shock geometry; typical ~6-8 at 1 AU.",
}

# ── Dataset description ─────────────────────────────────────────────────
DESCRIPTION = """\
Merged hourly near-Earth solar wind magnetic field, plasma, energetic particle parameters \
combined with geomagnetic and solar activity indices from NASA's OMNI dataset. The master \
bridge dataset for space weather analysis -- it time-aligns IMF, solar wind, and geomagnetic \
response in a single file.

The OMNI dataset from NASA's Goddard Space Flight Center merges solar wind observations from \
multiple spacecraft (IMP 8, ACE, Wind, DSCOVR, and others) into a single consistent hourly \
time series at Earth's bow shock nose. It combines interplanetary magnetic field (IMF) \
components, solar wind plasma parameters, energetic particle fluxes, and geomagnetic activity \
indices. Key parameter groups include IMF (field magnitude, Bx/By/Bz in GSE and GSM), solar \
wind plasma (proton density, temperature, bulk flow speed), derived quantities (flow pressure, \
plasma beta, electric field, Alfven and magnetosonic Mach numbers), geomagnetic indices (Kp, \
Dst, AE, AL, AU, ap, PC(N)), solar indices (F10.7, sunspot number), and energetic particles \
(proton fluxes at >1 to >60 MeV).

A key feature of the OMNI processing is the time-shifting of upstream spacecraft data to \
the Earth's bow shock nose. Observations from monitors at the L1 Lagrange point (ACE, Wind, \
DSCOVR -- roughly 1.5 million km upstream) are propagated to the bow shock using the measured \
solar wind speed, ensuring temporal alignment with the geomagnetic indices they drive.

The derived quantities encode important plasma physics. Plasma beta distinguishes magnetically \
dominated structures such as magnetic clouds (beta << 1) from the ambient solar wind (beta ~ 1). \
The Alfven Mach number characterizes how supersonic the flow is relative to the Alfven wave \
speed. The convective electric field (-V x B) quantifies magnetic flux transport toward the \
magnetopause and is a key input to empirical geomagnetic activity models.
"""


def main():
    print("Fetching OMNI hourly data from NASA GSFC...")
    for attempt in range(3):
        try:
            resp = requests.get(DATA_URL, timeout=300)
            resp.raise_for_status()
            break
        except Exception as exc:
            if attempt < 2:
                wait = 30 * (2 ** attempt)
                print(f"  NASA GSFC attempt {attempt + 1}/3 failed: {exc}; retrying in {wait}s...")
                time.sleep(wait)
            else:
                print(f"  NASA GSFC failed after 3 attempts: {exc}")
                raise
    print(f"  Downloaded {len(resp.content) / 1024 / 1024:.1f} MB")

    # Parse fixed-width whitespace-delimited ASCII
    df = pd.read_csv(
        StringIO(resp.text),
        sep=r"\s+",
        header=None,
        names=COLUMNS,
        dtype=float,
    )
    print(f"  {len(df):,} raw rows ({int(df['year'].min())}-{int(df['year'].max())})")

    # Create datetime from year + day_of_year + hour
    df["datetime"] = pd.to_datetime(
        df["year"].astype(int).astype(str) + "-" +
        df["day_of_year"].astype(int).astype(str) + "-" +
        df["hour"].astype(int).astype(str),
        format="%Y-%j-%H",
        errors="coerce",
    )

    # Replace fill values with NaN
    for col, fill in FILL_VALUES.items():
        if col in df.columns:
            df.loc[df[col] >= fill, col] = pd.NA

    # Drop raw time columns and metadata columns
    df = df.drop(columns=["year", "day_of_year", "hour"] + DROP_COLUMNS, errors="ignore")

    # Move datetime to first column
    cols = ["datetime"] + [c for c in df.columns if c != "datetime"]
    df = df[cols]

    # Drop rows with no datetime
    df = df.dropna(subset=["datetime"])

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Sort by datetime
    df = df.sort_values("datetime").reset_index(drop=True)

    # ── Domain-specific stats ────────────────────────────────────────
    n_total = len(df)
    date_min = df["datetime"].min().strftime("%Y-%m-%d")
    date_max = df["datetime"].max().strftime("%Y-%m-%d")

    # Coverage stats
    bz_coverage = (1 - df["bz_gsm_nt"].isna().mean()) * 100
    v_coverage = (1 - df["flow_speed_kms"].isna().mean()) * 100
    dst_coverage = (1 - df["dst_index_nt"].isna().mean()) * 100

    quick_stats = f"""\
- **{n_total:,}** hourly records ({date_min} to {date_max})
- **{len(COLUMN_DESCRIPTIONS)}** parameters spanning IMF, solar wind, geomagnetic indices, and energetic particles
- Bz coverage: **{bz_coverage:.1f}%**, flow speed: **{v_coverage:.1f}%**, Dst: **{dst_coverage:.1f}%**
- Standard reference dataset for solar wind-magnetosphere coupling studies"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/omni-solar-wind-parameters", split="train")
df = ds.to_pandas()

# Southward IMF (Bz < 0) and geomagnetic storms (Dst < -50)
storms = df[(df["bz_gsm_nt"] < -5) & (df["dst_index_nt"] < -50)]
print(f"Storm hours with strong southward IMF: {len(storms):,}")

# Solar wind speed distribution
print(df["flow_speed_kms"].describe())

# Plasma beta vs Alfven Mach number
import matplotlib.pyplot as plt
sub = df[["plasma_beta", "alfven_mach_number"]].dropna()
plt.scatter(sub["plasma_beta"], sub["alfven_mach_number"], s=0.1, alpha=0.1)
plt.xlabel("Plasma Beta")
plt.ylabel("Alfven Mach Number")
plt.xscale("log")
plt.yscale("log")
plt.title("OMNI: Plasma Beta vs Alfven Mach Number")
plt.show()
```"""

    # Identify numeric columns for clean()
    numeric_cols = [c for c in df.columns if c != "datetime" and c in COLUMN_DESCRIPTIONS]

    with Pipeline(
        repo=HF_REPO,
        pretty_name="OMNI Hourly Solar Wind Parameters",
        description=DESCRIPTION,
        tags=["space", "solar-wind", "imf", "magnetic-field", "space-weather",
              "nasa", "open-data", "tabular-data", "parquet"],
        source_url="https://omniweb.gsfc.nasa.gov/",
        task_categories=["tabular-regression", "time-series-forecasting"],
        collection_url="https://huggingface.co/collections/juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70",
        banner={
            "url": "https://images-assets.nasa.gov/image/iss072e159172/iss072e159172~medium.jpg",
            "alt": "Aurora borealis blankets the Earth, seen from the ISS",
            "credit": "NASA",
        },
        related_datasets=[
            "juliensimon/solar-wind",
            "juliensimon/dst-index",
            "juliensimon/geomagnetic-kp-index",
            "juliensimon/auroral-electrojet-index",
            "juliensimon/f107-solar-flux",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=numeric_cols,
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="omni_solar_wind_parameters.parquet",
            min_rows=400_000,
            expected_columns=[
                "datetime", "b_magnitude_avg_nt", "bx_gse_nt", "by_gse_nt",
                "bz_gse_nt", "by_gsm_nt", "bz_gsm_nt", "flow_speed_kms",
                "proton_density_cm3", "proton_temperature_k", "flow_pressure_npa",
                "plasma_beta", "alfven_mach_number", "magnetosonic_mach_number",
                "kp_index", "dst_index_nt", "ae_index_nt", "ap_index_nt",
                "f107_index_sfu", "sunspot_number",
            ],
            critical_columns=["datetime"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update OMNI solar wind parameters: {n_total:,} records",
        )
    print("Done.")


if __name__ == "__main__":
    main()
