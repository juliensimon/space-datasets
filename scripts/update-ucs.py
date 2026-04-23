#!/usr/bin/env python3
"""Fetch UCS Satellite Database and upload to HF.

Source: Union of Concerned Scientists — the most comprehensive publicly available
database of operational satellites, tracking active satellites with purpose,
operator, orbit, and physical characteristics.
"""

import io
import sys

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

HF_REPO = "juliensimon/ucs-satellite-database"

UCS_URLS = [
    # Stable media redirect — points to whatever version UCS currently hosts
    "https://www.ucs.org/media/11492",
    # Direct file link (May 2023 version, latest available as of Apr 2026)
    "https://www.ucs.org/sites/default/files/2024-01/UCS-Satellite-Database%205-1-2023.xlsx",
    # Legacy paths in case UCS publishes a newer version
    "https://www.ucsusa.org/sites/default/files/2025-02/UCS-Satellite-Database-5-1-2024.xlsx",
    "https://s3.amazonaws.com/ucs-documents/nuclear-weapons/sat-database/5-2024-update/UCS-Satellite-Database-5-1-2024.xlsx",
]

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; space-datasets/1.0; +https://github.com/juliensimon/space-datasets)",
}

# ── Column mapping ───────────────────────────────────────────────────
COL_RENAME = {
    "Name of Satellite": "satellite_name",
    "Name of Satellite, Alternate Names": "satellite_name",
    "Current Official Name of Satellite": "official_name",
    "Country/Org of UN Registry": "country_registry",
    "Country of Operator/Owner": "operator_country",
    "Operator/Owner": "operator",
    "Users": "users",
    "Purpose": "purpose",
    "Detailed Purpose": "detailed_purpose",
    "Class of Orbit": "orbit_class",
    "Type of Orbit": "orbit_type",
    "Longitude of GEO (degrees)": "geo_longitude",
    "Perigee (Kilometers)": "perigee_km",
    "Perigee (km)": "perigee_km",
    "Apogee (Kilometers)": "apogee_km",
    "Apogee (km)": "apogee_km",
    "Eccentricity": "eccentricity",
    "Inclination (Degrees)": "inclination_deg",
    "Inclination (degrees)": "inclination_deg",
    "Period (Minutes)": "period_minutes",
    "Period (minutes)": "period_minutes",
    "Launch Mass (Kilograms)": "launch_mass_kg",
    "Launch Mass (kg.)": "launch_mass_kg",
    "Dry Mass (Kilograms)": "dry_mass_kg",
    "Dry Mass (kg.)": "dry_mass_kg",
    "Power (Watts)": "power_watts",
    "Power (watts)": "power_watts",
    "Date of Launch": "launch_date",
    "Expected Lifetime (Years)": "expected_lifetime_years",
    "Expected Lifetime (yrs.)": "expected_lifetime_years",
    "Contractor": "contractor",
    "Country of Contractor": "contractor_country",
    "Launch Site": "launch_site",
    "Launch Vehicle": "launch_vehicle",
    "COSPAR Number": "cospar_id",
    "NORAD Number": "norad_id",
    "Comments": "comments",
    "Source Used for Orbital Data": "source_refs",
    "Source": "source_refs",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "satellite_name": "Official satellite name as registered with UNOOSA (e.g. 'STARLINK-1234', 'GPS IIF-10', 'Sentinel-2A')",
    "official_name": "Current official name of the satellite if different from registered name; null for most entries",
    "country_registry": "Country or organization that registered the satellite with the UN; may differ from operator's nationality",
    "operator_country": "Country where the satellite operator/owner is headquartered",
    "operator": "Organization operating or owning the satellite (e.g. 'SpaceX', 'NASA', 'ESA', 'Intelsat')",
    "users": "Primary user category: 'Civil', 'Commercial', 'Government', or 'Military'; occasionally multi-value slash-separated",
    "purpose": "Primary mission purpose (e.g. 'Communications', 'Earth Observation', 'Navigation', 'Technology Development', 'Space Science')",
    "detailed_purpose": "Expanded purpose description from the UCS spreadsheet (e.g. 'Communications/Maritime tracking', 'Earth Observation/SAR'); null for entries without a sub-classification",
    "orbit_class": "Orbital regime: 'LEO' (altitude <2,000 km), 'MEO' (2,000-35,786 km), 'GEO' (~35,786 km geostationary), 'Elliptical' (highly elliptical/Molniya orbits)",
    "orbit_type": "More specific orbit description (e.g. 'Sun-synchronous', 'Polar', 'Inclined geosynchronous'); null if not classified",
    "geo_longitude": "Assigned geostationary longitude in degrees for GEO satellites; null for non-GEO orbits",
    "perigee_km": "Closest orbital altitude above Earth's surface in km; null for GEO satellites (listed as circular) or missing TLE data",
    "apogee_km": "Farthest orbital altitude above Earth's surface in km; null for GEO satellites or missing TLE data; equals perigee for circular orbits",
    "eccentricity": "Orbital eccentricity (0 = circular, approaching 1 = highly elliptical); typically <0.01 for LEO/GEO, higher for Molniya orbits",
    "inclination_deg": "Orbital inclination in degrees relative to the equatorial plane; range 0 deg (equatorial) to 98 deg (sun-synchronous); null if not available",
    "period_minutes": "Orbital period in minutes; ~90 min for LEO (400 km), ~1,436 min for GEO; null if not available",
    "launch_mass_kg": "Satellite mass at launch in kilograms; null for most entries (UCS coverage is incomplete)",
    "dry_mass_kg": "Satellite mass without fuel in kilograms; null for most entries",
    "power_watts": "Electrical power generation capacity in watts; null for most entries",
    "launch_date": "Date of launch as provided by UCS; format varies between releases",
    "expected_lifetime_years": "Designed operational lifetime in years; null for most entries",
    "contractor": "Primary spacecraft manufacturer or contractor; null for many entries",
    "contractor_country": "Country where the contractor is headquartered",
    "launch_site": "Name of the launch site (e.g. 'Cape Canaveral', 'Baikonur Cosmodrome', 'Jiuquan')",
    "launch_vehicle": "Launch vehicle used (e.g. 'Falcon 9', 'Atlas V', 'Soyuz-2.1b')",
    "cospar_id": "COSPAR/NSSDC international designator (e.g. '2019-074A'); format YYYY-NNNL; null if not assigned",
    "norad_id": "NORAD Space Surveillance Network catalog number; unique per object; float due to pandas NA handling; join key with TLE/SATCAT datasets",
    "comments": "Free-text notes from UCS analysts about the satellite's mission, status, or special characteristics",
    "source_refs": "Bibliographic references used by UCS to compile the entry; useful for provenance tracking",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
The Union of Concerned Scientists (UCS) Satellite Database is the most comprehensive \
publicly available database of operational satellites. Updated roughly quarterly, it \
includes detailed information about each operational satellite: its name, country of \
registry, operator, purpose, orbital parameters, launch details, and physical characteristics.

What makes the UCS database uniquely valuable is its focus on the "why" behind each \
satellite, not just the "where." While NORAD's SATCAT tracks orbital parameters and the \
TLE catalog provides ephemeris data, the UCS database adds the human layer: who operates \
each satellite, what it does, who pays for it, and what sector it serves. This makes it \
the go-to source for policy researchers studying the militarization of space, economists \
analyzing the satellite communications market, and journalists reporting on the growing \
commercial space industry.

The database captures the full diversity of the operational satellite population across all \
orbit regimes. LEO satellites include Earth observation platforms, broadband mega-constellations, \
and scientific missions. MEO hosts navigation constellations like GPS and Galileo. GEO \
satellites serve as communications relays, weather sentinels, and early warning platforms. \
Physical parameters such as launch mass, dry mass, and power output help characterize satellite \
capability classes, from 1-kg CubeSats to 6,000-kg GEO communications platforms.\
"""


def main():
    print("Fetching UCS Satellite Database...")
    df = None
    for url in UCS_URLS:
        print(f"  Trying {url}...")
        try:
            resp = requests.get(url, timeout=120, allow_redirects=True, headers=_HEADERS)
            resp.raise_for_status()
            df = pd.read_excel(io.BytesIO(resp.content), engine="openpyxl")
            print(f"  Success: {len(df):,} rows")
            break
        except Exception as e:
            print(f"  Failed: {e}")

    if df is None or len(df) == 0:
        print("::error::Failed to fetch UCS Satellite Database from any URL")
        sys.exit(1)

    # Drop unnamed/empty columns (Excel artifacts)
    df = df.loc[:, ~df.columns.str.startswith("Unnamed")]
    df = df.loc[:, ~df.columns.str.startswith("Source.")]
    # Drop the standalone "Source" column if "Source Used for Orbital Data" exists
    if "Source Used for Orbital Data" in df.columns and "Source" in df.columns:
        df = df.drop(columns=["Source"])

    df = df.rename(columns=COL_RENAME)

    # Snake-case any remaining columns not in the rename map
    rename_map = {}
    for col in df.columns:
        if col not in COL_RENAME.values():
            snake = col.replace(" ", "_").replace("-", "_").replace("(", "").replace(")", "").replace(".", "").lower()
            if snake != col:
                rename_map[col] = snake
    if rename_map:
        df = df.rename(columns=rename_map)

    # Drop duplicate columns (can happen when both 2023 and 2024 names map to same target)
    df = df.loc[:, ~df.columns.duplicated()]

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Convert numerics
    numeric_cols = ["geo_longitude", "perigee_km", "apogee_km", "eccentricity",
                    "inclination_deg", "period_minutes", "launch_mass_kg", "dry_mass_kg",
                    "power_watts", "expected_lifetime_years", "norad_id"]

    # Coerce remaining object columns to clean strings
    str_cols = [c for c in df.columns if c not in numeric_cols and df[c].dtype == "object"]

    # ── Stats for README ────────────────────────────────────────────
    n_total = len(df)
    n_countries = int(df["country_registry"].nunique()) if "country_registry" in df.columns else 0
    n_purposes = int(df["purpose"].nunique()) if "purpose" in df.columns else 0
    top_orbits = df["orbit_class"].value_counts().head(5) if "orbit_class" in df.columns else pd.Series()
    top_orbits_str = ", ".join(f"{o} ({c:,})" for o, c in top_orbits.items())
    n_operators = int(df["operator"].nunique()) if "operator" in df.columns else 0

    quick_stats = f"""\
- **{n_total:,}** active satellites
- **{n_countries}** countries/organizations
- **{n_purposes}** purpose categories
- **{n_operators}** distinct operators
- Orbit classes: {top_orbits_str}"""

    usage = f"""\
```python
from datasets import load_dataset

ds = load_dataset("{HF_REPO}", split="train")
df = ds.to_pandas()

# Satellites by orbit class
print(df["orbit_class"].value_counts())

# Communications satellites
comms = df[df["purpose"].str.contains("Communications", na=False)]
print(f"{{len(comms):,}} communications satellites")

# Satellites by country
by_country = df["country_registry"].value_counts().head(10)
print(by_country)

# Orbit class distribution with matplotlib
import matplotlib.pyplot as plt
df["orbit_class"].value_counts().plot.bar()
plt.ylabel("Count")
plt.title("Satellites by Orbit Class")
plt.tight_layout()
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="UCS Satellite Database",
        description=DESCRIPTION,
        tags=["space", "satellite", "orbit", "ucs", "launch",
              "earth-observation", "open-data", "tabular-data", "parquet"],
        source_url="https://www.ucsusa.org/resources/satellite-database",
        task_categories=["tabular-classification"],
        update_schedule="Quarterly (1st of the month at 06:00 UTC) via [GitHub Actions](https://github.com/juliensimon/space-datasets).",
        collection_url="https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994",
        banner={
            "url": "https://images-assets.nasa.gov/image/iss071e439624/iss071e439624~medium.jpg",
            "alt": "An orbital sunrise illuminates the Earth's atmosphere, seen from the ISS",
            "credit": "NASA",
        },
        related_datasets=[
            "juliensimon/space-track-satcat",
            "juliensimon/satnogs-transmitters",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=numeric_cols,
            strings=str_cols,
        )
        p.publish(
            df,
            filename="ucs_satellite_database.parquet",
            min_rows=5000,
            expected_columns=["satellite_name", "norad_id", "purpose", "orbit_class"],
            critical_columns=["satellite_name"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update UCS satellite database: {n_total:,} satellites",
        )
    print("Done.")


if __name__ == "__main__":
    main()
