#!/usr/bin/env python3
"""Fetch Asterank asteroid mining economics data and upload to HF.

Static dataset — ~600K asteroids with estimated mining value, profit,
delta-v, spectral type, and orbital parameters from the Asterank project.
"""

import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

from dataset_images import banner_markdown, download_banner
from validate import check_dataset

API_URL = "http://www.asterank.com/api/asterank"
HF_REPO = "juliensimon/asterank-asteroid-mining"
MIN_ROWS = 400_000

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
    "saved": "saved",
    "BV": "color_index_bv",
    "UB": "color_index_ub",
    "spkid": "spkid",
}

# Columns that should be numeric
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
    "closeness_score", "asterank_score", "saved",
    "color_index_bv", "color_index_ub", "spkid",
    "designation_number",
]

EXPECTED_COLS = [
    "full_name", "name", "designation_number", "orbit_class",
    "spectral_type_smassii", "absolute_magnitude",
    "diameter_km", "semi_major_axis_au", "eccentricity", "inclination_deg",
    "earth_moid_au", "estimated_value_usd", "estimated_profit_usd",
    "closeness_score", "asterank_score",
]

CRITICAL_COLS = [
    "full_name", "semi_major_axis_au", "eccentricity",
    "estimated_value_usd", "estimated_profit_usd",
]


def fetch_asterank(max_records=600_000, page_size=1000):
    """Fetch asteroid data from Asterank API with pagination.

    The API caps at 1,000 per request regardless of limit parameter.
    Paginate using offset until we get fewer than page_size results.
    """
    import time as _time
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

    # Drop the 'saved' column — internal Asterank field, not useful
    if "saved" in df.columns:
        df = df.drop(columns=["saved"])

    # Sort by estimated value descending (most valuable first)
    df = df.sort_values("estimated_value_usd", ascending=False, na_position="last")
    df = df.reset_index(drop=True)

    return df


def main():
    records = fetch_asterank()
    df = transform(records)

    check_dataset(
        df,
        dataset_name="asterank",
        min_rows=MIN_ROWS,
        expected_columns=EXPECTED_COLS,
        critical_columns=CRITICAL_COLS,
    )

    # Stats for README
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

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "asterank_asteroid_mining.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet, {n_total:,} rows")

        banner_file = download_banner("asterank", tmp)
        banner_md = banner_markdown("asterank", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Asterank Asteroid Mining Economics"
language:
  - en
description: "Mining economics for ~600K asteroids: estimated value, profit, delta-v accessibility, spectral types, and orbital elements from the Asterank project."
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - asteroids
  - mining
  - economics
  - orbital-mechanics
  - open-data
  - tabular-data
  - parquet
size_categories:
  - 100K<n<1M
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/asterank_asteroid_mining.parquet
    default: true
---

# Asterank Asteroid Mining Economics
{banner_md}
*Part of the [Orbital Mechanics Datasets](https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994) collection on Hugging Face.*

Economic analysis of **{n_total:,}** asteroids for space mining potential, combining NASA/JPL orbital data
with estimated accessibility and resource value from the [Asterank](https://asterank.com/) project.

## Dataset description

Asterank ranks nearly 600,000 cataloged asteroids by estimated mining profitability. It
combines multiple data sources -- NASA/JPL Small-Body Database orbital elements, spectral
classifications, and published scientific papers on asteroid composition -- to estimate each
asteroid's resource value and the cost of reaching it.

Key economic fields:
- **estimated_value_usd** -- total estimated resource value based on spectral type and size
- **estimated_profit_usd** -- value minus estimated mission cost (delta-v dependent)
- **closeness_score** -- accessibility metric (lower delta-v = higher closeness)
- **asterank_score** -- composite ranking combining value, profit, and accessibility

Asteroid mining economics rest on three pillars: what an object is made of, how large it is, and how much energy is needed to reach it. Spectral classification provides the primary compositional constraint -- C-type (carbonaceous) asteroids are rich in water and organic compounds, S-type (silicaceous) asteroids contain iron-nickel metal and silicate minerals, and M-type (metallic) asteroids may be fragments of differentiated planetesimal cores with high concentrations of iron, nickel, cobalt, and platinum-group elements. A single kilometer-scale M-type asteroid could contain more platinum-group metals than have ever been mined on Earth. The estimated values in this dataset are derived by mapping spectral types to expected bulk compositions and scaling by volume, producing order-of-magnitude resource valuations.

The economic viability of asteroid mining depends critically on the delta-v cost of reaching a target, which determines propellant mass and thus mission cost. The closeness score in Asterank encodes this accessibility: objects in Earth-like orbits (low eccentricity, low inclination, semimajor axis near 1 AU) require minimal orbital energy to rendezvous with and return material from. The most economically interesting asteroids are therefore not necessarily the largest or most resource-rich, but those that combine moderate resource value with exceptionally low access cost -- typically small near-Earth asteroids in low-inclination, low-eccentricity orbits.

The profit estimates should be understood as theoretical upper bounds under optimistic assumptions about extraction technology, launch costs, and market dynamics. In practice, returning even kilograms of asteroid material to Earth requires solving formidable engineering challenges in autonomous mining, ore processing in microgravity, and deep-space transportation. Nevertheless, the dataset captures a meaningful ranking of relative economic potential and serves as a starting point for trade studies comparing mission architectures, target selection, and resource utilization strategies for the emerging space resource economy.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `full_name` | string | Full IAU-formatted name including number and name where available (e.g. "1 Ceres", "3552 Don Quixote"); for unnumbered objects contains the provisional designation |
| `name` | string | Short IAU proper name if assigned (e.g. "Ceres", "Eros"); null for the majority of asteroids that have only a provisional designation and no proper name |
| `designation_number` | int | Permanent MPC asteroid number assigned after a sufficiently well-determined orbit (e.g. 1 for Ceres); null for unnumbered asteroids whose orbits are not yet secure enough for permanent numbering |
| `provisional_designation` | string | MPC provisional designation in YYYY-XNX format assigned at discovery (e.g. "2024 YR4"); null for numbered asteroids where the provisional form has been retired |
| `orbit_class` | string | JPL/MPC orbital class: MBA (Main Belt Asteroid, 2.0–3.3 AU), APO (Apollo, a>=1 AU, q<1.017 AU), ATE (Aten, a<1 AU, Q>0.983 AU), AMO (Amor, 1.017<q<1.3 AU), TJN (Jupiter Trojan), CEN (Centaur), TNO (Trans-Neptunian), COM (Comet-like), IEO (Interior-Earth) |
| `spectral_type_smassii` | string | SMASS II (Bus 2002) spectral class based on visible/near-IR reflectance: C (carbonaceous, ~75% of asteroids, dark/primitive), S (silicaceous, ~17%, rocky/stony), X (metallic or featureless, includes M/E/P sub-types), B/D/K/L/Q/R/T/V (minor classes); null when no spectral observation exists |
| `spectral_type_bus` | string | Bus spectral classification (precursor to SMASS II); similar taxonomy to SMASS II; null for most asteroids; may agree or disagree with spectral_type_smassii due to different wavelength coverage |
| `spectral_type_tholen` | string | Tholen (1984) spectral classification from ECAS broadband photometry: C (carbonaceous), S (silicaceous), M (metallic, high radar albedo), E (enstatite achondrite, very high albedo), R, V (vestoid), T, D, F, G, B, P; null for objects not in the ECAS survey; the oldest major taxonomy, now largely superseded by SMASS II |
| `is_neo` | bool | Near-Earth Object flag: true if the asteroid's orbit brings it within 1.3 AU of the Sun (perihelion q < 1.3 AU); false otherwise; null if classification is unavailable |
| `is_pha` | bool | Potentially Hazardous Asteroid flag: true if absolute magnitude H<=22 (diameter roughly >140 m) AND Earth MOID <=0.05 AU; false otherwise; PHA status is reviewed as orbits are refined |
| `absolute_magnitude` | float64 | H magnitude — intrinsic brightness at zero solar phase angle and 1 AU distance; lower H = brighter = larger: H~18 is ~1 km, H~22 is ~140 m, H~26 is ~20 m; primary proxy for size when no direct diameter exists |
| `magnitude_slope` | float64 | G slope parameter in the H-G magnitude system describing how brightness varies with solar phase angle; typical value ~0.15; affects apparent brightness estimates at different elongations |
| `diameter_km` | float64 | Physically measured or radiometrically derived diameter in kilometers; null for the vast majority of asteroids (~99%) where no direct size measurement exists; when present, far more reliable than H-magnitude estimates |
| `diameter_sigma_km` | float64 | 1-sigma uncertainty on diameter_km in kilometers; null when diameter_km is null |
| `albedo` | float64 | Geometric albedo — fraction of incident sunlight reflected back at zero phase angle; C-type ~0.03–0.09 (very dark), S-type ~0.10–0.30, M-type ~0.10–0.30, E-type ~0.40–0.60; used with H magnitude to compute diameter |
| `extent_km` | string | Tri-axial body dimensions as "AxBxC" in kilometers for elongated or irregular objects with detailed shape models; null for the vast majority of asteroids |
| `rotation_period_h` | float64 | Sidereal rotation period in hours from lightcurve observations; null for most asteroids; typical range 2–1000 hours; fast rotators (<2.2 h) constrain internal strength |
| `gm_km3_s2` | float64 | Gravitational parameter GM in km³/s²; derived from spacecraft flyby or binary companion mass estimates; null for nearly all asteroids except the largest or visited ones |
| `semi_major_axis_au` | float64 | Keplerian semi-major axis of the heliocentric orbit in AU: inner main belt ~2.0–2.5 AU, outer main belt ~2.5–3.3 AU, near-Earth asteroids <1.3 AU perihelion, Trojans ~5.2 AU |
| `eccentricity` | float64 | Orbital eccentricity (dimensionless, 0–1): 0=circular, >0=elliptical; main belt typically 0.0–0.3; near-Earth asteroids often 0.1–0.7; value near 1 indicates a highly elongated or comet-like orbit |
| `inclination_deg` | float64 | Orbital inclination relative to the ecliptic plane in degrees; main belt typically 0–30°; high inclination (>30°) reduces mission accessibility; Aten/Apollo/Amor groups cover wide range |
| `ascending_node_deg` | float64 | Longitude of the ascending node in degrees (0–360); defines where the orbit crosses the ecliptic from south to north; one of the six Keplerian elements |
| `argument_perihelion_deg` | float64 | Argument of perihelion in degrees (0–360); angular distance from ascending node to perihelion point along the orbit; one of the six Keplerian elements |
| `mean_anomaly_deg` | float64 | Mean anomaly at epoch in degrees (0–360); angular position along the orbit at the reference epoch assuming uniform angular motion; one of the six Keplerian elements |
| `perihelion_au` | float64 | Closest approach distance to the Sun in AU; perihelion < 1.017 AU means the asteroid crosses Earth's orbit; perihelion < 0.307 AU classifies it as Vulcanoid-like |
| `aphelion_au` | float64 | Farthest distance from the Sun in AU; along with perihelion, defines the orbit extent; aphelion > 3.3 AU for Jupiter-crossing or outer solar system objects |
| `orbital_period_yr` | float64 | Time to complete one heliocentric orbit in years; main belt ~3–6 years; near-Earth asteroids ~1–3 years; derived from semi-major axis via Kepler's third law |
| `mean_motion_deg_day` | float64 | Average angular velocity in degrees per day; reciprocal of orbital period; faster motion = shorter period = smaller orbit |
| `tisserand_jupiter` | float64 | Tisserand parameter with respect to Jupiter (dimensionless); T_J > 3: main-belt asteroid; 2 < T_J < 3: Jupiter-family comet or Centaur; T_J < 2: Halley-type or long-period comet; key classifier for distinguishing asteroids from comets |
| `earth_moid_au` | float64 | Minimum Orbit Intersection Distance to Earth in AU — the minimum possible distance between Earth's orbit and the asteroid's orbit; <0.05 AU is the PHA threshold; <0.002 AU warrants close-approach monitoring; does not predict an actual collision |
| `earth_moid_ld` | float64 | Earth MOID expressed in Lunar Distances (1 LD ≈ 0.00257 AU ≈ 384,400 km); <7.3 LD is the PHA threshold in these units; null when earth_moid_au is null |
| `jupiter_moid_au` | float64 | Minimum Orbit Intersection Distance to Jupiter in AU; low values indicate potential for Jupiter gravitational perturbations that can reshape the orbit over time |
| `estimated_value_usd` | float64 | Asterank's estimated total extractable resource value in USD, derived by mapping spectral type to bulk composition and scaling by estimated mass; highly speculative order-of-magnitude estimate; null if spectral type or size data is insufficient for estimation |
| `estimated_profit_usd` | float64 | Asterank's estimated mining profit in USD: estimated_value_usd minus modeled mission cost (a function of delta-v); negative values indicate missions that cost more than the resources are worth; null if value or accessibility cannot be estimated |
| `closeness_score` | float64 | Asterank accessibility metric encoding delta-v cost to reach the asteroid; higher score = lower delta-v = easier to reach; combines orbital elements into a single dimensionless figure of merit; targets with closeness > threshold are reachable by current propulsion (~7 km/s) |
| `asterank_score` | float64 | Composite Asterank ranking score combining estimated_profit_usd and closeness_score to identify the most economically interesting and accessible targets; higher = more attractive for mining; primary sort key in Asterank's public interface |
| `orbit_condition_code` | float64 | JPL orbit condition code (0–9): 0 = best-determined orbit, 9 = very uncertain; high codes indicate sparse or short-arc observations; objects with code >= 7 have orbits that may change significantly with new data |
| `data_arc_days` | float64 | Total observation arc length in days from first to last observation; longer arcs produce more reliable orbital solutions; < 30 days indicates a newly discovered or poorly-tracked object |
| `n_obs_used` | float64 | Number of individual astrometric observations used in the orbital solution; more observations generally means a tighter orbit determination |
| `first_obs_date` | datetime | Date of the earliest observation used in the orbit fit; indicates how long the object has been tracked |
| `last_obs_date` | datetime | Date of the most recent observation used in the orbit fit; gap between last_obs_date and today indicates how stale the orbital solution is |
| `orbit_rms` | float64 | Root mean square residual of the orbit fit in arcseconds; lower values indicate a tighter fit to observations; typical good fit < 0.5 arcseconds |
| `color_index_bv` | float64 | B-V photometric color index (Johnson B minus V magnitudes); C-type asteroids ~0.7, S-type ~0.9, reflects surface composition and space weathering; null for most asteroids |
| `color_index_ub` | float64 | U-B photometric color index (Johnson U minus B magnitudes); provides additional compositional discrimination alongside B-V; null for most asteroids |

## Quick stats

- **{n_total:,}** asteroids ranked by mining economics
- **{n_neo:,}** Near-Earth Objects, **{n_pha:,}** Potentially Hazardous
- **{n_with_diameter:,}** with measured diameters, **{n_with_spectral:,}** with spectral types
- **{orbit_classes}** distinct orbital classes
- Most valuable: **{top_name}** at **${top_value:,.0f}** (profit: ${top_profit:,.0f})
- Median estimated value: **${median_value:,.0f}**
- Total estimated value of all asteroids: **${total_value:,.0f}**

## Usage

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
by_class = df.groupby("orbit_class")["estimated_value_usd"].agg(["count", "median", "sum"])
by_class = by_class.sort_values("sum", ascending=False)

# Accessible targets: low MOID + high profit
accessible = df[
    (df["earth_moid_au"] < 0.1) &
    (df["estimated_profit_usd"] > 1e9)
].sort_values("estimated_profit_usd", ascending=False)
```

## Data source

[Asterank](https://asterank.com/) by Ian Webster, combining data from NASA/JPL Small-Body
Database, spectral survey data, and published asteroid composition models.

## Related datasets

- [neo-close-approaches](https://huggingface.co/datasets/juliensimon/neo-close-approaches) -- NEO close approaches from NASA JPL
- [space-track-satcat](https://huggingface.co/datasets/juliensimon/space-track-satcat) -- Full NORAD satellite catalog
- [space-launch-log](https://huggingface.co/datasets/juliensimon/space-launch-log) -- Global launch history

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/asterank-asteroid-mining) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{asterank_mining,
  author = {{Simon, Julien}},
  title = {{Asterank Asteroid Mining Economics}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/asterank-asteroid-mining}},
  note = {{Based on Asterank (asterank.com) asteroid mining economics data}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Upload Asterank asteroid mining economics: {n_total:,} asteroids"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    print(f"rows={n_total}")
    print("Done.")


if __name__ == "__main__":
    main()
