#!/usr/bin/env python3
"""Fetch GCAT Satellite Catalog, upload to HF.

Source: Jonathan McDowell's General Catalog of Artificial Space Objects (GCAT)
https://planet4589.org/space/gcat/
"""

import pandas as pd

from hf_dataset_utils import Pipeline

HF_REPO = "juliensimon/gcat-satellite-catalog"
URL = "https://planet4589.org/space/gcat/tsv/cat/satcat.tsv"

COL_NAMES = [
    "jcat_id", "satcat_number", "launch_tag", "piece", "type", "name",
    "pl_name", "launch_date", "parent", "separation_date", "primary",
    "decay_date", "status", "dest", "owner", "state_code", "manufacturer",
    "bus", "motor", "mass_kg", "mass_flag", "dry_mass_kg", "dry_flag",
    "total_mass_kg", "total_flag", "length_m", "length_flag", "diameter_m",
    "diameter_flag", "span_m", "span_flag", "shape", "orbit_date",
    "perigee_km", "perigee_flag", "apogee_km", "apogee_flag",
    "inclination_deg", "inclination_flag", "op_orbit", "orbit_qual",
    "alt_names",
]

NUMERIC_COLS = [
    "satcat_number", "mass_kg", "dry_mass_kg", "total_mass_kg",
    "length_m", "diameter_m", "span_m",
    "perigee_km", "apogee_km", "inclination_deg",
]

# ── Column descriptions ───────────────────────────────────────────────

COLUMN_DESCRIPTIONS = {
    "jcat_id": "McDowell's GCAT unique identifier (e.g. 'S00001'); assigned sequentially across all artificial space objects regardless of country or tracking status",
    "satcat_number": "NORAD/Space Force catalog number -- 5-digit integer assigned by US Space Command as objects are tracked; null for objects not independently tracked by Space Force",
    "launch_tag": "GCAT launch event identifier linking this object to its originating launch in the GCAT launch log",
    "piece": "COSPAR international designator in YYYY-NNNX format: launch year + sequential launch number + piece letter (e.g. '1957-001A' for Sputnik 1)",
    "type": "Object type: P = Payload (operational spacecraft), R = Rocket Body (upper stage/booster), D = Debris (fragmentation or mission-related), U = Unknown",
    "name": "Primary tracking designation used by GCAT/Space Force; for debris and rocket bodies this is typically a generic label rather than a proper name",
    "pl_name": "Operational payload name assigned by the owner/operator (e.g. 'STARLINK-1234'); null for rocket bodies and debris without a named payload identity",
    "launch_date": "Date the object was launched (ISO format); for objects deployed from a parent craft this is the original launch date of the parent mission",
    "parent": "JCAT identifier of the parent object this piece separated from; null for primary payloads launched directly",
    "separation_date": "Date and time this object separated from its parent (ISO format); null if the object was the primary payload or separation event is unknown",
    "primary": "Central body the object orbits: Earth, Moon, Sun, Mars, etc.; most cataloged objects orbit Earth",
    "decay_date": "Date the object reentered the atmosphere or was otherwise removed from orbit (ISO format); null if the object is still in orbit",
    "status": "Orbital status: O = currently in orbit, R = reentered/decayed, AR = reentered after achieving orbit, D = intentionally deorbited, L = landed",
    "dest": "Destination or final disposition code for objects that left Earth orbit (e.g. lunar, planetary, escape trajectory)",
    "owner": "GCAT code for the owning organization or operator (e.g. 'NASA', 'SPACEX', 'ROSCOSMOS')",
    "state_code": "ISO 3166-1 alpha-2 country code of the responsible state (e.g. 'US', 'RU', 'CN'); reflects political responsibility, not necessarily launch location",
    "manufacturer": "GCAT code for the organization that built the object; null when manufacturer is unknown",
    "bus": "Spacecraft bus or platform model (e.g. 'SSL-1300', 'Boeing-702'); identifies the structural/avionics heritage; null when not publicly known",
    "motor": "Propulsion system or motor designation for rocket bodies; null for payloads or when propulsion details are unknown",
    "mass_kg": "Launch mass of the object in kg including propellant; null when mass is not publicly known",
    "mass_flag": "Qualifier on mass_kg: '~' approximate, '<' upper bound, '>' lower bound; null for reported values",
    "dry_mass_kg": "Dry mass (no propellant) in kg; null for most objects where dry mass is not separately reported",
    "dry_flag": "Qualifier on dry_mass_kg: '~' approximate, '<' upper bound, '>' lower bound",
    "total_mass_kg": "Total mass including all stages or attached hardware in kg; null when not reported",
    "total_flag": "Qualifier on total_mass_kg: '~' approximate, '<' upper bound, '>' lower bound",
    "length_m": "Longest dimension of the object in meters; null for most objects where dimensions are not publicly cataloged",
    "length_flag": "Qualifier on length_m: '~' approximate, '<' upper bound, '>' lower bound",
    "diameter_m": "Maximum cross-sectional diameter in meters; null when not publicly known",
    "diameter_flag": "Qualifier on diameter_m: '~' approximate, '<' upper bound, '>' lower bound",
    "span_m": "Maximum span including deployable structures (solar arrays, antennas) in meters; null when not cataloged",
    "span_flag": "Qualifier on span_m: '~' approximate, '<' upper bound, '>' lower bound",
    "shape": "Geometric shape description (e.g. 'box', 'cyl', 'sphere', 'cone+cyl'); used for radar cross-section modeling",
    "orbit_date": "Epoch date for the orbital elements in perigee_km, apogee_km, inclination_deg; null if no orbital solution exists",
    "perigee_km": "Altitude of the closest orbital point above Earth's surface in km at epoch; null for objects without tracked orbits",
    "perigee_flag": "Qualifier on perigee_km: '~' approximate, '<' upper bound, '>' lower bound",
    "apogee_km": "Altitude of the farthest orbital point above Earth's surface in km at epoch; perigee = apogee indicates a circular orbit",
    "apogee_flag": "Qualifier on apogee_km: '~' approximate, '<' upper bound, '>' lower bound",
    "inclination_deg": "Orbital inclination in degrees: 0 = equatorial prograde, 90 = polar, 97-98 = Sun-synchronous, 63.4 = Molniya critical inclination",
    "inclination_flag": "Qualifier on inclination_deg: '~' approximate, '<' upper bound, '>' lower bound",
    "op_orbit": "Operational orbit regime: LEO (<2000 km), MEO (2000-35786 km), GEO (~35786 km), HEO (highly elliptical), SSO (Sun-synchronous), Lunar, Heliocentric, etc.",
    "orbit_qual": "Orbit determination quality indicator reflecting confidence in the orbital elements",
    "alt_names": "Pipe-separated list of alternative names, previous designations, or synonyms; null when no alternates are known",
}

# ── Dataset description ──────────────────────────────────────────────

DESCRIPTION = """\
Comprehensive catalog of space objects from Jonathan McDowell's General Catalog of \
Artificial Space Objects (GCAT). Covers every cataloged spacecraft, rocket body, and \
debris piece from 1957 to present, with orbital parameters, physical dimensions, mass, \
ownership, and operational status.

Unlike the US Space Force catalog (which tracks radar-observable objects) or the UCS \
Satellite Database (which covers only active satellites), GCAT aims to catalog every \
artificial space object ever assigned an identifier -- including rocket bodies, \
mission-related debris, and objects that reentered decades ago.

Each entry includes the JCAT identifier (McDowell's comprehensive numbering), the \
NORAD catalog number, COSPAR international designator, object type classification, \
ownership and manufacturer information, physical properties (mass, dimensions, shape), \
and orbital elements at a reference epoch.

This dataset is valuable for studying the growth of the space object population over \
time, analyzing debris generation events, comparing national space programs by object \
count and mass on orbit, and building training data for orbital classification models.
"""


def main():
    # ── Fetch ────────────────────────────────────────────────────────────
    print("Fetching GCAT satellite catalog...")
    df = pd.read_csv(
        URL, sep="\t", comment="#", names=COL_NAMES,
        low_memory=False, skipinitialspace=True,
    )
    print(f"  {len(df):,} objects")

    # ── Transform ────────────────────────────────────────────────────────
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].str.strip()
    df.replace("-", pd.NA, inplace=True)

    # ── Keep only described columns ──────────────────────────────────────
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # ── Stats for README ─────────────────────────────────────────────────
    n_countries = df["state_code"].nunique()
    n_owners = df["owner"].nunique()
    n_active = int((df["status"] == "O").sum()) if "status" in df.columns else 0
    n_decayed = int((df["status"] == "R").sum()) if "status" in df.columns else 0
    n_orbits = df["op_orbit"].nunique() if "op_orbit" in df.columns else 0

    quick_stats = f"""\
- **{len(df):,}** cataloged space objects
- **{n_active:,}** currently in orbit (status "O")
- **{n_decayed:,}** reentered (status "R")
- **{n_countries}** countries/state codes
- **{n_owners}** distinct owners/operators
- **{n_orbits}** orbit type classifications"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/gcat-satellite-catalog", split="train")
df = ds.to_pandas()

# Currently active satellites
active = df[df["status"] == "O"]
print(f"{len(active):,} objects currently in orbit")

# Objects by country
print(df["state_code"].value_counts().head(10))

# Growth of cataloged objects over time
import matplotlib.pyplot as plt
df["launch_year"] = df["launch_date"].str[:4].astype(float)
yearly = df.groupby("launch_year").size()
plt.bar(yearly.index, yearly.values, width=0.8)
plt.xlabel("Year")
plt.ylabel("Objects Launched")
plt.title("Space Object Launches by Year")
plt.show()
```"""

    # ── Publish ──────────────────────────────────────────────────────────
    with Pipeline(
        repo=HF_REPO,
        pretty_name="GCAT Satellite Catalog",
        description=DESCRIPTION,
        tags=["space", "satellites", "satellite-catalog", "gcat",
              "orbital-mechanics", "spacecraft", "open-data",
              "tabular-data", "parquet"],
        source_url="https://planet4589.org/space/gcat/",
        collection_url="https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994",
        task_categories=["tabular-classification"],
        banner={
            "url": "https://images-assets.nasa.gov/image/iss071e439624/iss071e439624~medium.jpg",
            "alt": "An orbital sunrise illuminates the Earth's atmosphere, seen from the ISS",
            "credit": "NASA",
        },
        related_datasets=[
            "juliensimon/space-launch-log",
            "juliensimon/space-track-satcat",
            "juliensimon/ucs-satellite-database",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=NUMERIC_COLS,
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="satcat.parquet",
            min_rows=50000,
            expected_columns=["jcat_id", "name", "status", "owner", "state_code",
                              "launch_date", "perigee_km", "apogee_km"],
            critical_columns=["jcat_id", "name"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update GCAT satellite catalog: {len(df):,} objects",
        )
    print("Done.")


if __name__ == "__main__":
    main()
