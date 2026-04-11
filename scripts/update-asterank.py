#!/usr/bin/env python3
"""Fetch Asterank asteroid mining economics data and upload to HF.

Static dataset — ~600K asteroids with estimated mining value, profit,
delta-v, spectral type, and orbital parameters from the Asterank project.
"""

import time as _time

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

API_URL = "http://www.asterank.com/api/asterank"
HF_REPO = "juliensimon/asterank-asteroid-mining"

# Columns to keep and their clean names
RENAME = {
    "full_name": "full_name",
    "name": "name",
    "pdes": "designation_number",
    "prov_des": "provisional_designation",
    "class": "orbit_class",
    "spec": "spectral_type_smassii",
    "spec_B": "spectral_type_bus",
    "spec_T": "spectral_type_tholen",
    "neo": "is_neo",
    "pha": "is_pha",
    "H": "absolute_magnitude",
    "G": "magnitude_slope",
    "diameter": "diameter_km",
    "diameter_sigma": "diameter_sigma_km",
    "albedo": "albedo",
    "extent": "extent_km",
    "rot_per": "rotation_period_h",
    "GM": "gm_km3_s2",
    "a": "semi_major_axis_au",
    "e": "eccentricity",
    "i": "inclination_deg",
    "om": "ascending_node_deg",
    "w": "argument_perihelion_deg",
    "ma": "mean_anomaly_deg",
    "q": "perihelion_au",
    "ad": "aphelion_au",
    "per_y": "orbital_period_yr",
    "n": "mean_motion_deg_day",
    "t_jup": "tisserand_jupiter",
    "moid": "earth_moid_au",
    "moid_ld": "earth_moid_ld",
    "moid_jup": "jupiter_moid_au",
    "epoch": "epoch_jd",
    "epoch_mjd": "epoch_mjd",
    "epoch_cal": "epoch_cal",
    "equinox": "equinox",
    "orbit_id": "orbit_solution_id",
    "condition_code": "orbit_condition_code",
    "data_arc": "data_arc_days",
    "n_obs_used": "n_obs_used",
    "first_obs": "first_obs_date",
    "last_obs": "last_obs_date",
    "rms": "orbit_rms",
    "price": "estimated_value_usd",
    "profit": "estimated_profit_usd",
    "closeness": "closeness_score",
    "score": "asterank_score",
    "BV": "color_index_bv",
    "UB": "color_index_ub",
}

NUMERIC_COLS = [
    "absolute_magnitude", "magnitude_slope", "diameter_km", "diameter_sigma_km",
    "albedo", "rotation_period_h", "gm_km3_s2",
    "semi_major_axis_au", "eccentricity", "inclination_deg",
    "ascending_node_deg", "argument_perihelion_deg", "mean_anomaly_deg",
    "perihelion_au", "aphelion_au", "orbital_period_yr", "mean_motion_deg_day",
    "tisserand_jupiter", "earth_moid_au", "earth_moid_ld", "jupiter_moid_au",
    "epoch_jd", "epoch_mjd", "epoch_cal",
    "orbit_solution_id", "orbit_condition_code",
    "data_arc_days", "n_obs_used", "orbit_rms",
    "estimated_value_usd", "estimated_profit_usd",
    "closeness_score", "asterank_score",
    "color_index_bv", "color_index_ub",
    "designation_number",
]

COLUMN_DESCRIPTIONS = {
    "full_name": "Full IAU-formatted name including number and name where available (e.g. '1 Ceres', '3552 Don Quixote'); for unnumbered objects contains the provisional designation",
    "name": "Short IAU proper name if assigned (e.g. 'Ceres', 'Eros'); null for the majority of asteroids that have only a provisional designation and no proper name",
    "designation_number": "Permanent MPC asteroid number assigned after a sufficiently well-determined orbit (e.g. 1 for Ceres); null for unnumbered asteroids whose orbits are not yet secure enough for permanent numbering",
    "provisional_designation": "MPC provisional designation in YYYY-XNX format assigned at discovery (e.g. '2024 YR4'); null for numbered asteroids where the provisional form has been retired",
    "orbit_class": "JPL/MPC orbital class: MBA (Main Belt Asteroid, 2.0-3.3 AU), APO (Apollo, a>=1 AU, q<1.017 AU), ATE (Aten, a<1 AU, Q>0.983 AU), AMO (Amor, 1.017<q<1.3 AU), TJN (Jupiter Trojan), CEN (Centaur), TNO (Trans-Neptunian), COM (Comet-like), IEO (Interior-Earth)",
    "spectral_type_smassii": "SMASS II (Bus 2002) spectral class based on visible/near-IR reflectance: C (carbonaceous, ~75% of asteroids, dark/primitive), S (silicaceous, ~17%, rocky/stony), X (metallic or featureless), B/D/K/L/Q/R/T/V (minor classes); null when no spectral observation exists",
    "spectral_type_bus": "Bus spectral classification (precursor to SMASS II); similar taxonomy to SMASS II; null for most asteroids; may agree or disagree with spectral_type_smassii due to different wavelength coverage",
    "spectral_type_tholen": "Tholen (1984) spectral classification from ECAS broadband photometry: C (carbonaceous), S (silicaceous), M (metallic), E (enstatite achondrite), R, V (vestoid), T, D, F, G, B, P; null for objects not in the ECAS survey",
    "is_neo": "Near-Earth Object flag: true if the asteroid's orbit brings it within 1.3 AU of the Sun (perihelion q < 1.3 AU); false otherwise; null if classification is unavailable",
    "is_pha": "Potentially Hazardous Asteroid flag: true if absolute magnitude H<=22 (diameter roughly >140 m) AND Earth MOID <=0.05 AU; false otherwise; PHA status is reviewed as orbits are refined",
    "absolute_magnitude": "H magnitude -- intrinsic brightness at zero solar phase angle and 1 AU distance; lower H = brighter = larger: H~18 is ~1 km, H~22 is ~140 m, H~26 is ~20 m; primary proxy for size when no direct diameter exists",
    "magnitude_slope": "G slope parameter in the H-G magnitude system describing how brightness varies with solar phase angle; typical value ~0.15; affects apparent brightness estimates at different elongations",
    "diameter_km": "Physically measured or radiometrically derived diameter in kilometers; null for the vast majority of asteroids (~99%) where no direct size measurement exists",
    "diameter_sigma_km": "1-sigma uncertainty on diameter_km in kilometers; null when diameter_km is null",
    "albedo": "Geometric albedo -- fraction of incident sunlight reflected at zero phase angle; C-type ~0.03-0.09 (very dark), S-type ~0.10-0.30, M-type ~0.10-0.30, E-type ~0.40-0.60; used with H magnitude to compute diameter",
    "extent_km": "Tri-axial body dimensions as 'AxBxC' in kilometers for elongated or irregular objects with detailed shape models; null for the vast majority of asteroids",
    "rotation_period_h": "Sidereal rotation period in hours from lightcurve observations; null for most asteroids; typical range 2-1000 hours; fast rotators (<2.2 h) constrain internal strength",
    "gm_km3_s2": "Gravitational parameter GM in km^3/s^2; derived from spacecraft flyby or binary companion mass estimates; null for nearly all asteroids except the largest or visited ones",
    "semi_major_axis_au": "Keplerian semi-major axis of the heliocentric orbit in AU: inner main belt ~2.0-2.5 AU, outer main belt ~2.5-3.3 AU, near-Earth asteroids <1.3 AU perihelion, Trojans ~5.2 AU",
    "eccentricity": "Orbital eccentricity (dimensionless, 0-1): 0=circular, >0=elliptical; main belt typically 0.0-0.3; near-Earth asteroids often 0.1-0.7",
    "inclination_deg": "Orbital inclination relative to the ecliptic plane in degrees; main belt typically 0-30 deg; high inclination (>30 deg) reduces mission accessibility",
    "ascending_node_deg": "Longitude of the ascending node in degrees (0-360); defines where the orbit crosses the ecliptic from south to north",
    "argument_perihelion_deg": "Argument of perihelion in degrees (0-360); angular distance from ascending node to perihelion point along the orbit",
    "mean_anomaly_deg": "Mean anomaly at epoch in degrees (0-360); angular position along the orbit at the reference epoch assuming uniform angular motion",
    "perihelion_au": "Closest approach distance to the Sun in AU; perihelion < 1.017 AU means the asteroid crosses Earth's orbit",
    "aphelion_au": "Farthest distance from the Sun in AU; along with perihelion, defines the orbit extent",
    "orbital_period_yr": "Time to complete one heliocentric orbit in years; main belt ~3-6 years; near-Earth asteroids ~1-3 years",
    "mean_motion_deg_day": "Average angular velocity in degrees per day; reciprocal of orbital period; faster motion = shorter period = smaller orbit",
    "tisserand_jupiter": "Tisserand parameter with respect to Jupiter (dimensionless); T_J > 3: main-belt asteroid; 2 < T_J < 3: Jupiter-family comet; T_J < 2: Halley-type comet",
    "earth_moid_au": "Minimum Orbit Intersection Distance to Earth in AU; <0.05 AU is the PHA threshold; does not predict an actual collision",
    "earth_moid_ld": "Earth MOID expressed in Lunar Distances (1 LD ~ 0.00257 AU ~ 384,400 km); <7.3 LD is the PHA threshold",
    "jupiter_moid_au": "Minimum Orbit Intersection Distance to Jupiter in AU; low values indicate potential for Jupiter gravitational perturbations",
    "epoch_jd": "Julian Date of the orbital element epoch",
    "epoch_mjd": "Modified Julian Date of the orbital element epoch",
    "epoch_cal": "Calendar date of the orbital element epoch as a numeric YYYYMMDD value",
    "equinox": "Reference equinox for the orbital elements (typically J2000)",
    "orbit_solution_id": "JPL orbit solution identifier; increments as the orbit is refined with new observations",
    "orbit_condition_code": "JPL orbit condition code (0-9): 0 = best-determined orbit, 9 = very uncertain",
    "data_arc_days": "Total observation arc length in days from first to last observation; longer arcs produce more reliable orbital solutions",
    "n_obs_used": "Number of individual astrometric observations used in the orbital solution",
    "first_obs_date": "Date of the earliest observation used in the orbit fit",
    "last_obs_date": "Date of the most recent observation used in the orbit fit",
    "orbit_rms": "Root mean square residual of the orbit fit in arcseconds; lower values indicate a tighter fit",
    "estimated_value_usd": "Asterank's estimated total extractable resource value in USD, derived by mapping spectral type to bulk composition and scaling by estimated mass; highly speculative order-of-magnitude estimate",
    "estimated_profit_usd": "Asterank's estimated mining profit in USD: estimated_value_usd minus modeled mission cost (a function of delta-v); negative values indicate missions that cost more than the resources are worth",
    "closeness_score": "Asterank accessibility metric encoding delta-v cost to reach the asteroid; higher score = lower delta-v = easier to reach",
    "asterank_score": "Composite Asterank ranking score combining estimated_profit_usd and closeness_score to identify the most economically interesting targets; higher = more attractive for mining",
    "color_index_bv": "B-V photometric color index (Johnson B minus V magnitudes); C-type asteroids ~0.7, S-type ~0.9; null for most asteroids",
    "color_index_ub": "U-B photometric color index (Johnson U minus B magnitudes); provides additional compositional discrimination alongside B-V; null for most asteroids",
}

DESCRIPTION = """\
Economic analysis of ~600,000 asteroids for space mining potential, combining NASA/JPL \
orbital data with estimated accessibility and resource value from the Asterank project.

Asterank ranks nearly 600,000 cataloged asteroids by estimated mining profitability. It \
combines multiple data sources -- NASA/JPL Small-Body Database orbital elements, spectral \
classifications, and published scientific papers on asteroid composition -- to estimate each \
asteroid's resource value and the cost of reaching it.

Key economic fields:
- **estimated_value_usd** -- total estimated resource value based on spectral type and size
- **estimated_profit_usd** -- value minus estimated mission cost (delta-v dependent)
- **closeness_score** -- accessibility metric (lower delta-v = higher closeness)
- **asterank_score** -- composite ranking combining value, profit, and accessibility

Asteroid mining economics rest on three pillars: what an object is made of, how large it is, \
and how much energy is needed to reach it. Spectral classification provides the primary \
compositional constraint -- C-type (carbonaceous) asteroids are rich in water and organic \
compounds, S-type (silicaceous) asteroids contain iron-nickel metal and silicate minerals, \
and M-type (metallic) asteroids may be fragments of differentiated planetesimal cores with \
high concentrations of iron, nickel, cobalt, and platinum-group elements.

The economic viability of asteroid mining depends critically on the delta-v cost of reaching \
a target, which determines propellant mass and thus mission cost. The closeness score in \
Asterank encodes this accessibility: objects in Earth-like orbits require minimal orbital \
energy to rendezvous with and return material from. The most economically interesting \
asteroids are therefore not necessarily the largest or most resource-rich, but those that \
combine moderate resource value with exceptionally low access cost.

The profit estimates should be understood as theoretical upper bounds under optimistic \
assumptions about extraction technology, launch costs, and market dynamics.
"""


def fetch_asterank(max_records=600_000, page_size=1000):
    """Fetch asteroid data from Asterank API with pagination."""
    print(f"Fetching up to {max_records:,} asteroids from Asterank API...")
    all_records = []
    offset = 0
    while offset < max_records:
        resp = requests.get(
            API_URL,
            params={"query": "{}", "limit": str(page_size), "offset": str(offset)},
            timeout=120,
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        all_records.extend(batch)
        offset += len(batch)
        if len(all_records) % 10_000 == 0 or len(batch) < page_size:
            print(f"  {len(all_records):,} records fetched...")
        if len(batch) < page_size:
            break
        _time.sleep(0.3)
    print(f"  Total: {len(all_records):,} records")
    return all_records


def transform(records):
    """Transform raw API records into a clean DataFrame."""
    df = pd.DataFrame(records)
    print(f"  Raw columns: {len(df.columns)}")

    # Drop MongoDB _id field if present
    if "_id" in df.columns:
        df = df.drop(columns=["_id"])

    # Keep only columns we have mappings for, skip missing ones
    available = [c for c in RENAME if c in df.columns]
    df = df[available].rename(columns=RENAME)

    # Convert numeric columns
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Convert boolean-like columns
    if "is_neo" in df.columns:
        df["is_neo"] = df["is_neo"].map({"Y": True, "N": False})
    if "is_pha" in df.columns:
        df["is_pha"] = df["is_pha"].map({"Y": True, "N": False})

    # Convert date columns
    for col in ["first_obs_date", "last_obs_date"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    # Clean string columns — replace empty strings with None
    str_cols = df.select_dtypes(include="object").columns
    for col in str_cols:
        df[col] = df[col].replace("", None)

    # Strip whitespace from name/full_name
    for col in ["full_name", "name", "provisional_designation"]:
        if col in df.columns:
            df[col] = df[col].str.strip()

    # Drop undescribed columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Sort by estimated value descending (most valuable first)
    df = df.sort_values("estimated_value_usd", ascending=False, na_position="last")
    df = df.reset_index(drop=True)

    return df


def main():
    records = fetch_asterank()
    df = transform(records)

    # ── Stats for README ─────────────────────────────────────────────
    n_total = len(df)
    n_neo = int(df["is_neo"].sum()) if "is_neo" in df.columns else 0
    n_pha = int(df["is_pha"].sum()) if "is_pha" in df.columns else 0
    n_with_diameter = int(df["diameter_km"].notna().sum())
    n_with_spectral = int(df["spectral_type_smassii"].notna().sum())

    top = df.head(1).iloc[0]
    top_name = top["full_name"] or top["name"] or str(top.get("designation_number", "?"))
    top_value = top["estimated_value_usd"]
    top_profit = top["estimated_profit_usd"]

    median_value = df["estimated_value_usd"].median()
    total_value = df["estimated_value_usd"].sum()
    orbit_classes = df["orbit_class"].nunique()

    quick_stats = f"""\
- **{n_total:,}** asteroids ranked by mining economics
- **{n_neo:,}** Near-Earth Objects, **{n_pha:,}** Potentially Hazardous
- **{n_with_diameter:,}** with measured diameters, **{n_with_spectral:,}** with spectral types
- **{orbit_classes}** distinct orbital classes
- Most valuable: **{top_name}** at **${top_value:,.0f}** (profit: ${top_profit:,.0f})
- Median estimated value: **${median_value:,.0f}**
- Total estimated value of all asteroids: **${total_value:,.0f}**"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/asterank-asteroid-mining", split="train")
df = ds.to_pandas()

# Top 20 most profitable asteroids
top_profit = df.nlargest(20, "estimated_profit_usd")[
    ["full_name", "orbit_class", "spectral_type_smassii",
     "estimated_value_usd", "estimated_profit_usd", "earth_moid_au"]
]

# Near-Earth asteroids sorted by profit
neo_mining = df[df["is_neo"] == True].nlargest(50, "estimated_profit_usd")

# Value distribution by orbit class
import matplotlib.pyplot as plt
by_class = df.groupby("orbit_class")["estimated_value_usd"].agg(["count", "median", "sum"])
by_class = by_class.sort_values("sum", ascending=False)
by_class["median"].plot.bar()
plt.ylabel("Median estimated value (USD)")
plt.title("Asteroid Mining Value by Orbit Class")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Asterank Asteroid Mining Economics",
        description=DESCRIPTION,
        tags=["space", "asteroids", "mining", "economics", "orbital-mechanics",
              "open-data", "tabular-data", "parquet"],
        source_url="https://asterank.com/",
        task_categories=["tabular-classification", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA17666/PIA17666~small.jpg",
            "alt": "Rosetta spacecraft approaching Comet 67P/Churyumov-Gerasimenko",
            "credit": "NASA/ESA",
        },
        related_datasets=[
            "juliensimon/neo-close-approaches",
            "juliensimon/jpl-small-body-database",
            "juliensimon/bus-demeo-asteroid-taxonomy",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=NUMERIC_COLS,
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="asterank_asteroid_mining.parquet",
            min_rows=400_000,
            expected_columns=[
                "full_name", "name", "designation_number", "orbit_class",
                "spectral_type_smassii", "absolute_magnitude",
                "diameter_km", "semi_major_axis_au", "eccentricity", "inclination_deg",
                "earth_moid_au", "estimated_value_usd", "estimated_profit_usd",
                "closeness_score", "asterank_score",
            ],
            critical_columns=[
                "full_name", "semi_major_axis_au", "eccentricity",
                "estimated_value_usd", "estimated_profit_usd",
            ],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Asterank asteroid mining economics: {n_total:,} asteroids",
        )
    print("Done.")


if __name__ == "__main__":
    main()
