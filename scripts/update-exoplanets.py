#!/usr/bin/env python3
"""Fetch confirmed exoplanets from NASA Exoplanet Archive and upload to HF."""

import io

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

TAP_URL = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
HF_REPO = "juliensimon/nasa-exoplanets"

ADQL_QUERY = """\
SELECT pl_name,hostname,discoverymethod,disc_year,disc_facility,
  pl_orbper,pl_rade,pl_bmasse,pl_eqt,pl_orbsmax,pl_orbeccen,
  st_teff,st_rad,st_mass,sy_dist,sy_vmag,ra,dec,rowupdate
FROM ps WHERE default_flag=1 ORDER BY disc_year DESC"""

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "pl_name": "Planet designation in the form 'Host b/c/d...' (e.g. 'Kepler-452 b'); alphabetical suffixes distinguish planets within the same system",
    "hostname": "Host star identifier; multiple rows share the same hostname in multi-planet systems",
    "discoverymethod": "Detection technique: 'Transit' (brightness dip), 'Radial Velocity' (Doppler shift), 'Direct Imaging', 'Microlensing', 'Astrometry', or 'Timing'; determines which physical parameters are measurable",
    "disc_year": "Calendar year of confirmed discovery; ranges from 1992 (pulsar planets) to present",
    "disc_facility": "Observatory or mission that made the discovery (e.g. 'Kepler', 'TESS', 'La Silla Observatory')",
    "pl_orbper": "Orbital period in days; hot Jupiters: 1-5 days, Earth analogs: ~365 days, outer giants: years; null for directly imaged planets without an orbit solution",
    "pl_rade": "Planet radius in Earth radii; sub-Earths: <1, super-Earths: 1-1.5, mini-Neptunes: 1.5-4, Neptunes: 4-7, Jupiters: >7; null if no transit or imaging measurement available",
    "pl_bmasse": "Best-available planet mass in Earth masses; actual mass if inclination is known, otherwise M sin(i) from radial velocity; rocky: <10, Neptune-class: 10-50, Jupiter: ~318; null for transit-only detections without RV follow-up",
    "pl_eqt": "Planet equilibrium temperature in Kelvin assuming zero albedo; Earth's T_eq ~ 255 K; habitable zone range ~ 200-300 K; null if stellar temperature or semi-major axis is unavailable",
    "pl_orbsmax": "Orbital semi-major axis in AU; sets stellar irradiation flux and equilibrium temperature; null for planets with only transit period and no stellar mass estimate",
    "pl_orbeccen": "Orbital eccentricity (0 = circular, <1 = elliptical); most short-period planets are tidally circularized (e ~ 0); null for planets discovered by transit alone without RV characterization",
    "st_teff": "Host star effective temperature in Kelvin; M dwarfs: 2500-4000 K, K dwarfs: 4000-5200 K, G dwarfs (Sun-like): 5200-6000 K, F dwarfs: 6000-7500 K",
    "st_rad": "Host star radius in solar radii; required to convert observed transit depth into absolute planet radius",
    "st_mass": "Host star mass in solar masses; used with orbital period to compute semi-major axis via Kepler's third law",
    "sy_dist": "System distance in parsecs from Earth; derived from Gaia parallax when available; needed to assess planet detectability and calculate absolute stellar luminosity",
    "sy_vmag": "Host star apparent V-band (optical) magnitude; brighter stars (lower values) are better targets for atmospheric characterization and RV follow-up",
    "ra": "Right ascension in decimal degrees (ICRS J2000.0); range 0-360",
    "dec": "Declination in decimal degrees (ICRS J2000.0); range -90 to +90",
    "rowupdate": "ISO date of the most recent parameter update in the NASA Exoplanet Archive for this row",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Confirmed exoplanets with orbital, stellar, and discovery parameters from the \
NASA Exoplanet Archive.

The NASA Exoplanet Archive is the authoritative database of confirmed exoplanets, \
maintained by Caltech/IPAC under contract with NASA. Each entry represents a \
confirmed planet with its best-available physical and orbital parameters, host star \
properties, and discovery information. This dataset uses the Planetary Systems (ps) \
table with default_flag=1 to select one row per planet with the default parameter set.

The discovery of exoplanets has transformed our understanding of planetary systems \
and the prevalence of worlds beyond our own. The first confirmed detection around a \
Sun-like star came in 1995 with 51 Pegasi b, a "hot Jupiter" whose unexpectedly \
close orbit challenged existing theories of planet formation. Since then, the \
transit method -- measuring the tiny dip in stellar brightness as a planet crosses \
its host star -- has become the dominant discovery technique, largely thanks to the \
Kepler and TESS space telescopes.

The dataset includes key physical parameters such as orbital period, planet radius \
and mass, equilibrium temperature, orbital eccentricity, and semi-major axis, \
alongside host star properties like effective temperature, radius, mass, and \
distance. These parameters are fundamental to characterizing planetary systems: \
radius and mass together constrain bulk composition (rocky vs. gaseous), equilibrium \
temperature indicates potential habitability, and eccentricity reveals dynamical \
history.

This data underpins a wide range of astrophysical research, from occurrence rate \
calculations (how common are Earth-like planets?) to atmospheric characterization \
target selection for JWST and future missions.
"""


def main():
    print("Fetching confirmed exoplanets from NASA Exoplanet Archive...")
    resp = requests.get(TAP_URL, params={"query": ADQL_QUERY, "format": "csv"}, timeout=120)
    resp.raise_for_status()

    df = pd.read_csv(io.StringIO(resp.text))
    print(f"  {len(df):,} confirmed planets")

    # Type coercion
    df["disc_year"] = df["disc_year"].astype("Int64")
    for col in ["pl_orbper", "pl_rade", "pl_bmasse", "pl_eqt", "pl_orbsmax",
                "pl_orbeccen", "st_teff", "st_rad", "st_mass", "sy_dist", "sy_vmag",
                "ra", "dec"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Sort by discovery year descending
    df = df.sort_values("disc_year", ascending=False, na_position="last").reset_index(drop=True)

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    method_counts = df["discoverymethod"].value_counts()
    method_lines = "\n".join(
        f"| {method} | {count:,} |" for method, count in method_counts.head(8).items()
    )

    year_counts = df["disc_year"].dropna().astype(int).value_counts().sort_index(ascending=False)
    recent_years = "\n".join(
        f"| {year} | {count:,} |" for year, count in year_counts.head(10).items()
    )

    most_recent = df.iloc[0]
    most_recent_name = most_recent["pl_name"]
    most_recent_year = int(most_recent["disc_year"]) if pd.notna(most_recent["disc_year"]) else "N/A"

    quick_stats = f"""\
- **{n_total:,}** confirmed exoplanets
- Most recent discovery: **{most_recent_name}** ({most_recent_year})

### By discovery method

| Method | Count |
|--------|-------|
{method_lines}

### Recent discoveries by year

| Year | Count |
|------|-------|
{recent_years}"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/nasa-exoplanets", split="train")
df = ds.to_pandas()

# Earth-like candidates: rocky, in habitable zone
habitable = df[
    (df["pl_rade"] < 1.6) &
    (df["pl_eqt"] > 200) & (df["pl_eqt"] < 310)
]
print(f"{len(habitable)} potentially habitable planets")

# Transit vs radial velocity discoveries over time
transit = df[df["discoverymethod"] == "Transit"]
rv = df[df["discoverymethod"] == "Radial Velocity"]

# Planets by discovery facility
top_facilities = df["disc_facility"].value_counts().head(10)
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="NASA Exoplanet Archive",
        description=DESCRIPTION,
        tags=["space", "exoplanet", "astronomy", "nasa", "transit",
              "radial-velocity", "kepler", "tess", "open-data", "tabular-data",
              "parquet"],
        source_url="https://exoplanetarchive.ipac.caltech.edu/",
        task_categories=["tabular-classification", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA21423/PIA21423~small.jpg",
            "alt": "Artist concept of the surface of TRAPPIST-1f exoplanet",
            "credit": "NASA/JPL-Caltech",
        },
        related_datasets=[
            "juliensimon/tess-toi-candidates",
            "juliensimon/kepler-eclipsing-binaries",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "pl_orbper", "pl_rade", "pl_bmasse", "pl_eqt", "pl_orbsmax",
                "pl_orbeccen", "st_teff", "st_rad", "st_mass", "sy_dist",
                "sy_vmag", "ra", "dec",
            ],
            integer=["disc_year"],
        )
        p.publish(
            df,
            filename="exoplanets.parquet",
            min_rows=5000,
            expected_columns=["pl_name", "hostname", "discoverymethod", "disc_year", "pl_orbper"],
            critical_columns=["pl_name", "hostname"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update exoplanets: {n_total:,} confirmed planets",
        )
    print("Done.")


if __name__ == "__main__":
    main()
