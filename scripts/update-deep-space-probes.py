#!/usr/bin/env python3
"""Fetch merged hourly data for Voyager 1/2 and Pioneer 10/11 from NASA SPDF and upload to HF.

Source: NASA Space Physics Data Facility (SPDF) — COHO merged hourly data files.
"""

import datetime
import time
from io import StringIO

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

CURRENT_YEAR = datetime.date.today().year

HF_REPO = "juliensimon/deep-space-probes"

BASE = "https://spdf.gsfc.nasa.gov/pub/data"
SOURCES = {
    "voyager_1": {
        "url": f"{BASE}/voyager/voyager1/merged/",
        "pattern": "vy1_{year}.asc",
        "years": range(1977, CURRENT_YEAR + 1),
        "columns": [
            "year", "day_of_year", "hour",
            "heliocentric_distance_au", "hgi_latitude_deg", "hgi_longitude_deg",
            "b_magnitude_avg_nt", "b_magnitude_nt",
            "br_rtn_nt", "bt_rtn_nt", "bn_rtn_nt",
            "flow_speed_kms", "flow_elevation_deg", "flow_azimuth_deg",
            "proton_density_cm3", "proton_temperature_k",
            "flux_h_lecp_0p57_1p78_mev", "flux_h_lecp_3p40_17p6_mev",
            "flux_h_lecp_22p0_31p0_mev",
            "flux_h_crs_3p0_4p6_mev", "flux_h_crs_4p6_6p2_mev",
            "flux_h_crs_6p2_7p7_mev", "flux_h_crs_7p7_12p8_mev",
            "flux_h_crs_12p8_17p9_mev", "flux_h_crs_17p9_30p0_mev",
            "flux_h_crs_30p0_48p0_mev", "flux_h_crs_48p0_56p0_mev",
            "flux_h_crs_74p5_83p7_mev", "flux_h_crs_132p8_154p9_mev",
            "flux_h_crs_154p9_174p9_mev", "flux_h_crs_174p9_187p7_mev",
            "flux_h_crs_187p7_220p5_mev", "flux_h_crs_220p5_270p1_mev",
            "flux_h_crs_270p1_346p0_mev",
        ],
        "fill_values": {
            "heliocentric_distance_au": 999.99,
            "hgi_latitude_deg": 9999.9,
            "hgi_longitude_deg": 9999.9,
            "b_magnitude_avg_nt": 999.999,
            "b_magnitude_nt": 999.999,
            "br_rtn_nt": 999.999,
            "bt_rtn_nt": 999.999,
            "bn_rtn_nt": 999.999,
            "flow_speed_kms": 9999.9,
            "flow_elevation_deg": 9999.9,
            "flow_azimuth_deg": 9999.9,
            "proton_density_cm3": 99.99999,
            "proton_temperature_k": 9999999.0,
        },
        "flux_fill_threshold": 9.9e4,
    },
    "voyager_2": {
        "url": f"{BASE}/voyager/voyager2/merged/",
        "pattern": "vy2_{year}.asc",
        "years": range(1977, CURRENT_YEAR + 1),
        "columns": [
            "year", "day_of_year", "hour",
            "heliocentric_distance_au", "hgi_latitude_deg", "hgi_longitude_deg",
            "b_magnitude_avg_nt", "b_magnitude_nt",
            "br_rtn_nt", "bt_rtn_nt", "bn_rtn_nt",
            "flow_speed_kms", "flow_elevation_deg", "flow_azimuth_deg",
            "proton_density_cm3", "proton_temperature_k",
            "flux_h_lecp_0p52_1p45_mev", "flux_h_lecp_3p04_17p3_mev",
            "flux_h_lecp_22p0_30p0_mev",
            "flux_h_crs_3p0_4p6_mev", "flux_h_crs_4p6_6p2_mev",
            "flux_h_crs_6p2_7p7_mev", "flux_h_crs_7p7_12p8_mev",
            "flux_h_crs_12p8_17p9_mev", "flux_h_crs_17p9_30p0_mev",
            "flux_h_crs_30p0_48p0_mev", "flux_h_crs_48p0_56p0_mev",
            "flux_h_crs_75p9_82p6_mev", "flux_h_crs_130p3_154p2_mev",
            "flux_h_crs_154p2_171p3_mev", "flux_h_crs_171p3_193p6_mev",
            "flux_h_crs_193p6_208p2_mev", "flux_h_crs_208p2_245p7_mev",
            "flux_h_crs_245p7_272p3_mev", "flux_h_crs_272p3_344p0_mev",
            "flux_h_crs_344p0_478p6_mev", "flux_h_crs_478p6_598p7_mev",
        ],
        "fill_values": {
            "heliocentric_distance_au": 999.99,
            "hgi_latitude_deg": 9999.9,
            "hgi_longitude_deg": 9999.9,
            "b_magnitude_avg_nt": 999.999,
            "b_magnitude_nt": 999.999,
            "br_rtn_nt": 999.999,
            "bt_rtn_nt": 999.999,
            "bn_rtn_nt": 999.999,
            "flow_speed_kms": 9999.9,
            "flow_elevation_deg": 9999.9,
            "flow_azimuth_deg": 9999.9,
            "proton_density_cm3": 99.99999,
            "proton_temperature_k": 9999999.0,
        },
        "flux_fill_threshold": 9.9e4,
    },
    "pioneer_10": {
        "url": f"{BASE}/pioneer/pioneer10/merged/coho1hr_magplasma_ascii/",
        "pattern": "p10_{year}.asc",
        "years": range(1972, 1996),
        "columns": [
            "year", "day_of_year", "hour",
            "heliocentric_distance_au", "hgi_latitude_deg", "hgi_longitude_deg",
            "br_rtn_nt", "bt_rtn_nt", "bn_rtn_nt", "b_magnitude_nt",
            "flow_speed_kms", "flow_elevation_deg", "flow_azimuth_deg",
            "proton_density_cm3", "proton_temperature_k",
            "flux_h_crt_3p45_5p15_mev", "flux_h_crt_30p55_56p47_mev",
            "flux_h_crt_120p7_227p3_mev",
        ],
        "fill_values": {
            "heliocentric_distance_au": 999.99,
            "hgi_latitude_deg": 9999.9,
            "hgi_longitude_deg": 9999.9,
            "br_rtn_nt": 999.9999,
            "bt_rtn_nt": 999.9999,
            "bn_rtn_nt": 999.9999,
            "b_magnitude_nt": 999.9999,
            "flow_speed_kms": 9999.9,
            "flow_elevation_deg": 9999.9,
            "flow_azimuth_deg": 9999.9,
            "proton_density_cm3": 999.9999,
            "proton_temperature_k": 9999999.0,
        },
        "flux_fill_threshold": 9.9e6,
    },
    "pioneer_11": {
        "url": f"{BASE}/pioneer/pioneer11/merged/coho1hr_magplasma_ascii/",
        "pattern": "p11_{year}.asc",
        "years": range(1973, 1995),
        "columns": [
            "year", "day_of_year", "hour",
            "heliocentric_distance_au", "hgi_latitude_deg", "hgi_longitude_deg",
            "br_rtn_nt", "bt_rtn_nt", "bn_rtn_nt", "b_magnitude_nt",
            "flow_speed_kms", "flow_elevation_deg", "flow_azimuth_deg",
            "proton_density_cm3", "proton_temperature_k",
            "flux_h_crt_3p45_5p15_mev", "flux_h_crt_30p55_56p47_mev",
            "flux_h_crt_120p7_227p3_mev",
        ],
        "fill_values": {
            "heliocentric_distance_au": 999.99,
            "hgi_latitude_deg": 9999.9,
            "hgi_longitude_deg": 9999.9,
            "br_rtn_nt": 999.9999,
            "bt_rtn_nt": 999.9999,
            "bn_rtn_nt": 999.9999,
            "b_magnitude_nt": 999.9999,
            "flow_speed_kms": 9999.9,
            "flow_elevation_deg": 9999.9,
            "flow_azimuth_deg": 9999.9,
            "proton_density_cm3": 999.9999,
            "proton_temperature_k": 9999999.0,
        },
        "flux_fill_threshold": 9.9e6,
    },
}

# Columns common to all spacecraft (used for the merged output)
COMMON_COLUMNS = [
    "spacecraft", "datetime",
    "heliocentric_distance_au", "hgi_latitude_deg", "hgi_longitude_deg",
    "b_magnitude_nt", "br_rtn_nt", "bt_rtn_nt", "bn_rtn_nt",
    "flow_speed_kms", "flow_elevation_deg", "flow_azimuth_deg",
    "proton_density_cm3", "proton_temperature_k",
]

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "spacecraft": "Spacecraft identifier: voyager_1, voyager_2, pioneer_10, or pioneer_11",
    "datetime": "Observation timestamp (UTC, hourly cadence) derived from year, day-of-year, and hour in the source data",
    "heliocentric_distance_au": "Distance from the Sun in astronomical units (AU); ranges from ~1 AU at launch to 160+ AU for Voyager 1 in interstellar space",
    "hgi_latitude_deg": "Heliographic Inertial (HGI) latitude in degrees; measures angular position above/below the solar equatorial plane",
    "hgi_longitude_deg": "Heliographic Inertial (HGI) longitude in degrees; measures angular position in the solar equatorial plane relative to the ascending node of the solar equator on the ecliptic",
    "b_magnitude_avg_nt": "Average magnetic field magnitude in nT, computed as 1/N SUM |B| over the hour; Voyager only, null for Pioneer",
    "b_magnitude_nt": "Magnetic field magnitude in nT, computed as sqrt(Br^2 + Bt^2 + Bn^2); falls off approximately as 1/r^2 (radial) to 1/r (tangential) with distance",
    "br_rtn_nt": "Radial component of the interplanetary magnetic field in RTN coordinates (nT); positive outward from the Sun along the Parker spiral",
    "bt_rtn_nt": "Tangential component of the magnetic field in RTN coordinates (nT); positive in the direction of planetary motion; dominates at large heliocentric distances",
    "bn_rtn_nt": "Normal component of the magnetic field in RTN coordinates (nT); positive northward; typically small compared to Br and Bt",
    "flow_speed_kms": "Proton bulk flow speed in km/s; typically 300-800 km/s in the inner heliosphere, decelerating in the outer heliosheath; null beyond the heliopause where solar wind is absent",
    "flow_elevation_deg": "Flow velocity elevation angle in degrees relative to the RTN radial direction; non-radial flows indicate stream interactions or shock deflections",
    "flow_azimuth_deg": "Flow velocity azimuth angle in degrees in the RTN tangential-normal plane; deviations from purely radial flow",
    "proton_density_cm3": "Proton number density in particles/cm^3; decreases roughly as 1/r^2 with heliocentric distance; typical values: ~5 at 1 AU, ~0.001 at 100 AU",
    "proton_temperature_k": "Proton temperature in Kelvin; decreases with distance but more slowly than adiabatic due to pickup ion heating in the outer heliosphere",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Merged hourly magnetic field, solar wind plasma, and energetic particle \
measurements from humanity's four most distant spacecraft: Voyager 1, \
Voyager 2, Pioneer 10, and Pioneer 11.

Each record includes spacecraft position (heliocentric distance, HGI \
latitude/longitude), interplanetary magnetic field components (RTN \
coordinates), solar wind plasma parameters (flow speed, proton density, \
temperature), and energetic particle fluxes at multiple energy channels \
from the LECP, CRS, and CRT instruments.

Voyager 1 crossed the heliopause (~121 AU) in August 2012 and Voyager 2 \
(~119 AU) in November 2018, making this dataset unique in spanning the \
transition from the heliosphere to interstellar space. Pioneer 10 and 11, \
launched in 1972-1973, were the first spacecraft to traverse the asteroid \
belt and encounter Jupiter and Saturn.

The interplanetary magnetic field measurements trace the structure of the \
Parker spiral carried outward by the solar wind. Solar wind speed, density, \
and temperature document how the wind decelerates and heats through \
interactions with pickup ions in the outer heliosphere. The energetic \
particle fluxes record galactic cosmic rays modulated by the solar cycle, \
anomalous cosmic rays accelerated at the termination shock, and transient \
particle events from solar energetic particle events and interplanetary shocks.
"""


def fetch_spacecraft(name, cfg):
    """Download and parse yearly files for one spacecraft."""
    frames = []
    session = requests.Session()
    for year in cfg["years"]:
        url = cfg["url"] + cfg["pattern"].format(year=year)
        try:
            resp = session.get(url, timeout=60)
            resp.raise_for_status()
        except requests.HTTPError:
            if resp.status_code == 404:
                print(f"    {name} {year}: not found, skipping")
                continue
            raise
        except requests.RequestException as e:
            print(f"    {name} {year}: error {e}, skipping")
            continue

        df = pd.read_csv(
            StringIO(resp.text),
            sep=r"\s+",
            header=None,
            names=cfg["columns"][:],
        )
        frames.append(df)
        time.sleep(0.3)

    if not frames:
        print(f"  WARNING: no data for {name}")
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    print(f"  {name}: {len(df):,} raw rows ({int(df['year'].min())}-{int(df['year'].max())})")

    # Create datetime from year + day_of_year + hour
    df["datetime"] = pd.to_datetime(
        df["year"].astype(int).astype(str) + "-" +
        df["day_of_year"].astype(int).astype(str) + "-" +
        df["hour"].astype(int).astype(str),
        format="%Y-%j-%H",
        errors="coerce",
    )

    # Replace fill values with NaN for non-flux columns
    for col, fill in cfg["fill_values"].items():
        if col in df.columns:
            df.loc[df[col] >= fill, col] = pd.NA

    # Replace fill values for flux columns
    flux_cols = [c for c in df.columns if c.startswith("flux_")]
    threshold = cfg["flux_fill_threshold"]
    for col in flux_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        df.loc[df[col] >= threshold, col] = pd.NA

    # Voyager has b_magnitude_avg_nt; Pioneer does not
    if "b_magnitude_avg_nt" not in df.columns:
        df["b_magnitude_avg_nt"] = pd.NA

    df["spacecraft"] = name
    df = df.drop(columns=["year", "day_of_year", "hour"], errors="ignore")

    return df


def main():
    print("Fetching deep space probe data from NASA SPDF...")

    all_frames = []
    for name, cfg in SOURCES.items():
        print(f"\nDownloading {name}...")
        df = fetch_spacecraft(name, cfg)
        if len(df) > 0:
            all_frames.append(df)

    print("\nMerging all spacecraft data...")
    df = pd.concat(all_frames, ignore_index=True)
    print(f"  {len(df):,} total rows before cleanup")

    # Drop rows with no datetime
    df = df.dropna(subset=["datetime"])

    # Keep only common columns + b_magnitude_avg_nt + all flux columns
    flux_cols = sorted([c for c in df.columns if c.startswith("flux_")])
    keep_cols = COMMON_COLUMNS + ["b_magnitude_avg_nt"] + flux_cols
    keep_cols = [c for c in keep_cols if c in df.columns]
    df = df[keep_cols]

    df = df.sort_values(["spacecraft", "datetime"]).reset_index(drop=True)
    print(f"  {len(df):,} rows after cleanup")

    # Stats per spacecraft
    for sc in sorted(df["spacecraft"].unique()):
        sub = df[df["spacecraft"] == sc]
        date_min = sub["datetime"].min().strftime("%Y-%m-%d")
        date_max = sub["datetime"].max().strftime("%Y-%m-%d")
        dist_max = sub["heliocentric_distance_au"].max()
        print(f"  {sc}: {len(sub):,} rows, {date_min} to {date_max}, max {dist_max:.1f} AU")

    # ── Stats for README ────────────────────────────────────────────
    n_total = len(df)
    sc_counts = df["spacecraft"].value_counts().to_dict()
    date_min = df["datetime"].min().strftime("%Y-%m-%d")
    date_max = df["datetime"].max().strftime("%Y-%m-%d")
    max_dist_row = df.loc[df["heliocentric_distance_au"].idxmax()]
    max_dist = max_dist_row["heliocentric_distance_au"]
    max_dist_sc = max_dist_row["spacecraft"]

    sc_bullets = "\n".join(
        f"- **{sc.replace('_', ' ').title()}**: {sc_counts.get(sc, 0):,} hourly records"
        for sc in ["voyager_1", "voyager_2", "pioneer_10", "pioneer_11"]
    )

    quick_stats = f"""\
- **{n_total:,}** hourly records ({date_min} to {date_max})
- **4 spacecraft**: Voyager 1 & 2, Pioneer 10 & 11
- Maximum heliocentric distance: **{max_dist:.1f} AU** ({max_dist_sc.replace('_', ' ').title()})
- Covers heliosphere, heliosheath, and interstellar space
{sc_bullets}"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/deep-space-probes", split="train")
df = ds.to_pandas()

# Voyager 1 in interstellar space (beyond heliopause at ~121 AU)
v1_interstellar = df[
    (df["spacecraft"] == "voyager_1") &
    (df["heliocentric_distance_au"] > 121)
]

# Compare solar wind speed across all probes
for sc in df["spacecraft"].unique():
    sub = df[df["spacecraft"] == sc].dropna(subset=["flow_speed_kms"])
    print(f"{sc}: mean flow speed = {sub['flow_speed_kms'].mean():.0f} km/s")

# Magnetic field decay with distance
import matplotlib.pyplot as plt
v1 = df[df["spacecraft"] == "voyager_1"].dropna(subset=["b_magnitude_nt"])
plt.scatter(v1["heliocentric_distance_au"], v1["b_magnitude_nt"], s=0.1, alpha=0.3)
plt.xlabel("Distance (AU)")
plt.ylabel("|B| (nT)")
plt.yscale("log")
plt.title("Voyager 1: Magnetic Field vs Distance")
plt.show()
```"""

    # Build column descriptions including flux columns dynamically
    col_descs = dict(COLUMN_DESCRIPTIONS)
    for col in flux_cols:
        # flux_h_lecp_0p57_1p78_mev -> "LECP proton flux 0.57-1.78 MeV ..."
        parts = col.replace("flux_h_", "").split("_")
        instrument = parts[0].upper()
        energy_range = "_".join(parts[1:]).replace("p", ".").replace("_mev", "").replace("_", "-")
        col_descs[col] = (
            f"Differential proton flux from {instrument} instrument in the "
            f"{energy_range} MeV energy channel, in units of 1/(cm^2 s sr MeV); "
            f"null when fill values indicate no valid measurement"
        )

    # Drop any columns not in col_descs
    df = df[[c for c in df.columns if c in col_descs]]

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Deep Space Probes -- Merged Hourly Data",
        description=DESCRIPTION,
        tags=["space", "heliophysics", "voyager", "pioneer", "solar-wind",
              "magnetic-field", "deep-space", "nasa", "spdf", "interstellar",
              "open-data", "tabular-data", "parquet"],
        source_url="https://spdf.gsfc.nasa.gov/",
        task_categories=["tabular-regression", "time-series-forecasting"],
        update_schedule="Monthly (1st at 07:00 UTC). Voyager data is still being collected; Pioneer missions ended in the 1990s.",
        collection_url="https://huggingface.co/collections/juliensimon/space-probe-and-mission-datasets-69c3fe82d410a42b1e313167",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA14111/PIA14111~small.jpg",
            "alt": "Voyager spacecraft artist concept",
            "credit": "NASA/JPL-Caltech",
        },
        related_datasets=[
            "juliensimon/solar-wind",
            "juliensimon/dst-index",
            "juliensimon/geomagnetic-kp-index",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "heliocentric_distance_au", "hgi_latitude_deg", "hgi_longitude_deg",
                "b_magnitude_avg_nt", "b_magnitude_nt",
                "br_rtn_nt", "bt_rtn_nt", "bn_rtn_nt",
                "flow_speed_kms", "flow_elevation_deg", "flow_azimuth_deg",
                "proton_density_cm3", "proton_temperature_k",
            ],
        )
        p.publish(
            df,
            filename="deep_space_probes.parquet",
            min_rows=1_000_000,
            expected_columns=[
                "spacecraft", "datetime", "heliocentric_distance_au",
                "b_magnitude_nt", "br_rtn_nt", "bt_rtn_nt", "bn_rtn_nt",
                "flow_speed_kms", "proton_density_cm3", "proton_temperature_k",
            ],
            critical_columns=["spacecraft", "datetime", "heliocentric_distance_au"],
            column_descriptions=col_descs,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update deep space probes: {n_total:,} records",
        )
    print("Done.")


if __name__ == "__main__":
    main()
