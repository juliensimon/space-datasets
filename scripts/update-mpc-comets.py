#!/usr/bin/env python3
"""Fetch MPC comet orbital elements and upload to HF.

Source: Minor Planet Center — CometEls.txt fixed-width format.
Reference: https://www.minorplanetcenter.net/iau/info/CometOrbitFormat.html
"""

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

SOURCE_URL = "https://www.minorplanetcenter.net/iau/MPCORB/CometEls.txt"
HF_REPO = "juliensimon/mpc-comet-elements"

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "periodic_comet_number": "IAU sequential number for periodic comets (e.g., 1 = Halley, 2 = Encke); null for non-periodic, defunct, uncertain, and interstellar comets",
    "orbit_type": "MPC single-letter orbit type: C = long-period (Oort Cloud origin), P = short-period (<200 yr), D = defunct (no longer observable), X = lost/uncertain, I = interstellar, A = asteroid-like orbit",
    "orbit_type_name": "Human-readable expansion of orbit_type (long-period, periodic, defunct, uncertain, interstellar, minor-planet-like)",
    "packed_designation": "MPC packed provisional designation encoding discovery survey, year, and sequence; null for well-known periodic comets identified only by number",
    "perihelion_year": "Calendar year (CE) of the most recent perihelion passage used in the orbital solution",
    "perihelion_month": "Month (1-12) of the most recent perihelion passage",
    "perihelion_day": "Fractional day of perihelion passage in Terrestrial Time (TT); includes sub-day precision (e.g., 14.567)",
    "perihelion_date": "Perihelion passage date truncated to the nearest whole day (UTC); null for a small number of unparseable entries",
    "perihelion_distance_au": "Distance from the Sun at perihelion in AU; sungrazers have q < 0.01 AU; values near or above 5 AU indicate distant long-period comets",
    "eccentricity": "Orbital eccentricity; e < 1 = bound elliptical, e ~ 1 = parabolic, e > 1 = hyperbolic (interstellar or strongly perturbed)",
    "arg_perihelion_deg": "Argument of perihelion in degrees (0-360), J2000.0 ecliptic; angle from ascending node to perihelion direction",
    "lon_asc_node_deg": "Longitude of the ascending node in degrees (0-360), J2000.0 ecliptic; angle from vernal equinox to orbit-ecliptic intersection",
    "inclination_deg": "Inclination to the J2000.0 ecliptic in degrees (0-180); i > 90 = retrograde orbit, typical of dynamically new Oort Cloud comets",
    "epoch_date": "Reference epoch for perturbed (non-gravitational) osculating element solutions; null for unperturbed or two-body solutions",
    "absolute_magnitude_h": "Total absolute magnitude parameter H used in the standard cometary brightness law m = H + 5 log delta + 10 log r; null for comets lacking photometric data",
    "slope_parameter_g": "Photometric slope parameter G (default 4.0 for comets when not fitted); governs how brightness scales with heliocentric distance",
    "orbital_period_years": "Orbital period in years computed from Kepler's 3rd law (P = a^1.5); null for hyperbolic or parabolic orbits (e >= 1)",
    "is_hyperbolic": "True when eccentricity >= 1.0, indicating an unbound or interstellar trajectory",
    "name": "Official comet name or designation (e.g., '1P/Halley', 'C/2020 F3 (NEOWISE)'); null for a small number of provisional entries",
    "reference": "MPC short reference code for the published orbital solution (e.g., 'MPC 12345'); null if not recorded",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Orbital elements for all known comets published by the Minor Planet Center (MPC). \
Covers periodic, long-period, defunct, and interstellar objects.

The MPC maintains the authoritative catalogue of comet orbits, updated as new \
observations refine existing solutions and new comets are discovered. Each record \
contains the six Keplerian orbital elements (perihelion distance, eccentricity, \
argument of perihelion, longitude of the ascending node, inclination, and \
perihelion date), plus absolute magnitude and slope parameter.

Comets occupy a special place in solar system dynamics. Short-period comets (P < 200 \
years) predominantly originate in the Kuiper Belt and scattered disk beyond Neptune, \
while long-period comets fall inward from the Oort Cloud at distances of 10,000--100,000 \
AU. As a comet approaches perihelion, solar heating sublimates volatile ices, producing \
the characteristic coma and tail. The eccentricity distribution reveals the dynamical \
boundary between bound elliptical orbits (e < 1) and hyperbolic trajectories (e >= 1) \
that indicate interstellar origin or strong planetary perturbation.
"""


def parse_comet_line(line: str) -> dict | None:
    """Parse one fixed-width line from CometEls.txt.

    Format: MPC Ephemerides and Orbital Elements format.
    Reference: https://www.minorplanetcenter.net/iau/info/CometOrbitFormat.html
    """
    if len(line.strip()) < 100:
        return None

    try:
        # Columns are 1-indexed in the MPC spec; Python slicing is 0-indexed.
        num_str = line[0:4].strip()
        orbit_type = line[4:5].strip()
        packed_desig = line[5:12].strip()

        # Perihelion date components
        peri_year = line[14:18].strip()
        peri_month = line[19:21].strip()
        peri_day = line[22:29].strip()

        perihelion_distance_au = line[30:39].strip()
        eccentricity = line[41:49].strip()

        arg_perihelion_deg = line[51:59].strip()
        lon_asc_node_deg = line[61:69].strip()
        inclination_deg = line[71:79].strip()

        # Epoch (perturbed solutions)
        epoch_year = line[81:85].strip()
        epoch_month = line[85:87].strip()
        epoch_day = line[87:89].strip()

        abs_magnitude_h = line[91:95].strip()
        slope_param_g = line[96:100].strip()

        name = line[102:158].strip()
        reference = line[159:168].strip()

        # Build perihelion date string
        perihelion_date = None
        if peri_year and peri_month and peri_day:
            try:
                perihelion_date = pd.Timestamp(
                    year=int(peri_year),
                    month=int(peri_month),
                    day=int(float(peri_day)),
                )
            except (ValueError, OverflowError):
                pass

        # Build epoch date
        epoch_date = None
        if epoch_year and epoch_month and epoch_day:
            try:
                epoch_date = pd.Timestamp(
                    year=int(epoch_year),
                    month=int(epoch_month),
                    day=int(epoch_day),
                )
            except (ValueError, OverflowError):
                pass

        return {
            "periodic_comet_number": int(num_str) if num_str else None,
            "orbit_type": orbit_type or None,
            "packed_designation": packed_desig or None,
            "perihelion_year": int(peri_year) if peri_year else None,
            "perihelion_month": int(peri_month) if peri_month else None,
            "perihelion_day": float(peri_day) if peri_day else None,
            "perihelion_date": perihelion_date,
            "perihelion_distance_au": float(perihelion_distance_au) if perihelion_distance_au else None,
            "eccentricity": float(eccentricity) if eccentricity else None,
            "arg_perihelion_deg": float(arg_perihelion_deg) if arg_perihelion_deg else None,
            "lon_asc_node_deg": float(lon_asc_node_deg) if lon_asc_node_deg else None,
            "inclination_deg": float(inclination_deg) if inclination_deg else None,
            "epoch_date": epoch_date,
            "absolute_magnitude_h": float(abs_magnitude_h) if abs_magnitude_h else None,
            "slope_parameter_g": float(slope_param_g) if slope_param_g else None,
            "name": name or None,
            "reference": reference or None,
        }
    except (ValueError, IndexError):
        return None


def main():
    print("Fetching MPC comet orbital elements...")
    resp = requests.get(SOURCE_URL, timeout=120)
    resp.raise_for_status()
    text = resp.text

    lines = text.splitlines()
    print(f"  Downloaded {len(lines):,} lines")

    records = []
    for line in lines:
        rec = parse_comet_line(line)
        if rec is not None:
            records.append(rec)

    df = pd.DataFrame(records)
    print(f"  Parsed {len(df):,} comets")

    # Classify orbit type
    orbit_type_map = {
        "C": "long-period", "P": "periodic", "D": "defunct",
        "X": "uncertain", "I": "interstellar", "A": "minor-planet",
    }
    df["orbit_type_name"] = df["orbit_type"].map(orbit_type_map)

    # Derived: is_hyperbolic (eccentricity >= 1)
    df["is_hyperbolic"] = df["eccentricity"] >= 1.0

    # Compute orbital period for elliptical orbits (Kepler's 3rd law)
    # P = a^(3/2) years, where a = q / (1 - e) for e < 1
    def compute_period(row):
        e = row["eccentricity"]
        q = row["perihelion_distance_au"]
        if pd.isna(e) or pd.isna(q) or e >= 1.0:
            return None
        a = q / (1.0 - e)
        return round(a ** 1.5, 2)

    df["orbital_period_years"] = df.apply(compute_period, axis=1)

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_periodic = int((df["orbit_type"] == "P").sum())
    n_long_period = int((df["orbit_type"] == "C").sum())
    n_hyperbolic = int(df["is_hyperbolic"].sum())
    n_defunct = int((df["orbit_type"] == "D").sum())
    q_min = df["perihelion_distance_au"].min()
    q_max = df["perihelion_distance_au"].max()
    closest = df.loc[df["perihelion_distance_au"].idxmin()]

    quick_stats = f"""\
- **{n_total:,}** comets total
- **{n_periodic:,}** periodic (P), **{n_long_period:,}** long-period (C), **{n_defunct:,}** defunct (D)
- **{n_hyperbolic:,}** on hyperbolic orbits (eccentricity >= 1)
- Perihelion distances range from **{q_min:.4f}** to **{q_max:.1f}** AU
- Closest perihelion: **{closest['name']}** at **{closest['perihelion_distance_au']:.6f}** AU"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/mpc-comet-elements", split="train")
df = ds.to_pandas()

# All periodic comets
periodic = df[df["orbit_type"] == "P"].sort_values("perihelion_distance_au")

# Hyperbolic / interstellar visitors
hyperbolic = df[df["is_hyperbolic"]].sort_values("eccentricity", ascending=False)

# Distribution of inclinations
import matplotlib.pyplot as plt
df["inclination_deg"].hist(bins=50)
plt.xlabel("Inclination (degrees)")
plt.ylabel("Count")
plt.title("Comet Orbital Inclination Distribution")
plt.show()

# Eccentricity vs perihelion distance
plt.scatter(df["perihelion_distance_au"], df["eccentricity"], s=5, alpha=0.5)
plt.xlabel("Perihelion Distance (AU)")
plt.ylabel("Eccentricity")
plt.axhline(y=1.0, color="r", linestyle="--", label="Parabolic limit")
plt.title("Comet Eccentricity vs Perihelion Distance")
plt.legend()
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="MPC Comet Orbital Elements",
        description=DESCRIPTION,
        tags=["space", "comets", "orbits", "mpc", "orbital-mechanics",
              "open-data", "tabular-data", "parquet"],
        source_url="https://www.minorplanetcenter.net/iau/MPCORB/CometEls.txt",
        license="other",
        license_name="iau-mpc-policy",
        license_link="https://www.minorplanetcenter.net/iau/WWWPolicy.html",
        task_categories=["tabular-classification", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA17666/PIA17666~small.jpg",
            "alt": "Rosetta spacecraft approaching Comet 67P/Churyumov-Gerasimenko",
            "credit": "NASA/ESA",
        },
        related_datasets=[
            "juliensimon/neo-close-approaches",
            "juliensimon/mpc-comet-elements",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "perihelion_distance_au", "eccentricity",
                "arg_perihelion_deg", "lon_asc_node_deg", "inclination_deg",
                "absolute_magnitude_h", "slope_parameter_g",
                "perihelion_day", "orbital_period_years",
            ],
            integer=["periodic_comet_number", "perihelion_year", "perihelion_month"],
        )
        p.publish(
            df,
            filename="mpc_comet_elements.parquet",
            min_rows=500,
            expected_columns=[
                "periodic_comet_number", "orbit_type", "packed_designation",
                "perihelion_date", "perihelion_distance_au", "eccentricity",
                "arg_perihelion_deg", "lon_asc_node_deg", "inclination_deg",
                "absolute_magnitude_h", "slope_parameter_g", "name",
            ],
            critical_columns=["perihelion_distance_au", "eccentricity", "inclination_deg", "name"],
            max_null_pct=0.05,
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update MPC comet elements: {n_total:,} comets",
        )
    print("Done.")


if __name__ == "__main__":
    main()
