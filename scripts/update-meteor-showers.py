#!/usr/bin/env python3
"""Fetch IAU Meteor Data Center shower database and upload to HF."""

from datetime import datetime

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

# IAU MDC data files (year-suffixed)
YEAR = datetime.now().year
BASE_URL = "https://www.ta3.sk/IAUC22DB/MDC2022/Etc"
FULL_URL = f"{BASE_URL}/streamfulldata{YEAR}.txt"
HF_REPO = "juliensimon/iau-meteor-showers"

# Column names matching the header:
# LP  IAUNo  AdNo  Code  s  sub.date  shower_name  activity
# LoSb  LoSe  LoS  Ra  De  dRa  dDe  Vg
# LoR  S_LoR  LaR  theta  phi  Flags
# a  q  e  peri  node  inc  N  Group  CG
# Origin  Remarks  Ote  L-T  References
COLUMNS = [
    "lp", "iau_no", "ad_no", "code", "status_code", "submission_date",
    "shower_name", "activity_type",
    "sol_lon_begin_deg", "sol_lon_end_deg", "sol_lon_peak_deg",
    "ra_deg", "dec_deg", "ra_daily_motion", "dec_daily_motion",
    "geocentric_velocity_kms",
    "sun_centered_ecliptic_lon_deg", "sun_centered_ecliptic_lat_deg",
    "ecliptic_lat_deg", "theta_deg", "phi_deg",
    "flags",
    "semi_major_axis_au", "perihelion_distance_au", "eccentricity",
    "arg_perihelion_deg", "ascending_node_deg", "inclination_deg",
    "n_meteors", "group_no", "cg",
    "parent_body", "remarks", "ote", "lookup_table", "references",
]

STATUS_MAP = {
    1: "established",
    2: "to_be_established",
    0: "working_list",
    -1: "to_be_removed",
    -2: "lack_of_references",
    -3: "too_few_members",
    -4: "duplicate_or_reclassified",
    -5: "misclassification",
    -6: "pro_tempore",
    -7: "removed",
}

COLUMN_DESCRIPTIONS = {
    "lp": "Sequential record number",
    "iau_no": "IAU shower number (unique per shower)",
    "ad_no": "Additional solution number (0 = primary, 1+ = alternate analyses)",
    "code": "Three-letter IAU code (e.g. PER, GEM, LEO)",
    "status_code": "Numeric status flag (1=established, 0=working list, negative=issues)",
    "status": "Human-readable status label",
    "is_established": "True if shower has IAU established status",
    "submission_date": "Date submitted to MDC",
    "shower_name": "Full shower name-designation",
    "activity_type": "Activity pattern (annual, variable, etc.)",
    "sol_lon_begin_deg": "Solar longitude at start of detectable activity (degrees, 0°=vernal equinox, increases ~1°/day); more stable than calendar date for inter-annual comparison",
    "sol_lon_end_deg": "Solar longitude at end of detectable activity (degrees); activity window = sol_lon_end − sol_lon_begin",
    "sol_lon_peak_deg": "Solar longitude at peak activity (degrees); the most reproducible parameter for scheduling observations year to year",
    "ra_deg": "Right ascension of the radiant — the sky point from which meteors appear to diverge — ICRS J2000.0 (degrees, 0–360); drifts during the shower due to Earth's orbital motion",
    "dec_deg": "Declination of the radiant, ICRS J2000.0 (degrees, -90 to +90); showers with dec < −30° are poorly observable from northern mid-latitudes",
    "ra_daily_motion": "Rate of change of radiant right ascension during the shower (degrees/day); caused by Earth's changing viewing geometry",
    "dec_daily_motion": "Rate of change of radiant declination during the shower (degrees/day)",
    "geocentric_velocity_kms": "Meteor entry speed relative to Earth (km/s); range ~11–72 km/s; slow meteors leave short, faint trains; fast meteors produce persistent trains and fireballs",
    "sun_centered_ecliptic_lon_deg": "Ecliptic longitude of the radiant in a Sun-centered frame (degrees); invariant of Earth's position, useful for orbital analysis",
    "sun_centered_ecliptic_lat_deg": "Ecliptic latitude of the radiant in a Sun-centered frame (degrees)",
    "ecliptic_lat_deg": "Ecliptic latitude of the radiant in standard (Earth-centered) ecliptic coordinates (degrees)",
    "theta_deg": "Angular distance from the apex of Earth's way (degrees); used in the Southworth-Hawkins D-criterion for stream association",
    "phi_deg": "Angular distance from the ecliptic plane (degrees); used in stream orbital similarity calculations",
    "flags": "MDC data quality or provenance flags (e.g. \"R\" for refined solution); null if no flag",
    "semi_major_axis_au": "Semi-major axis of the meteoroid stream's mean orbit (AU); null for hyperbolic or unresolved orbits",
    "perihelion_distance_au": "Perihelion distance of the stream orbit (AU); must be ≤1 AU for Earth-crossing showers",
    "eccentricity": "Orbital eccentricity of the stream (0=circular, 1=parabolic); most showers: 0.7–1.0",
    "arg_perihelion_deg": "Argument of perihelion of the stream orbit (degrees, 0–360)",
    "ascending_node_deg": "Longitude of ascending node of the stream orbit (degrees, 0–360); approximately equals the solar longitude at peak when node ≈ Earth's orbit",
    "inclination_deg": "Inclination of the stream orbit to the ecliptic (degrees, 0–180); >90° indicates retrograde stream",
    "n_meteors": "Number of individual meteor observations used to derive this radiant/orbit solution; null if not reported",
    "group_no": "IAU stream group number linking related showers in the same complex",
    "cg": "Shower complex or group code (e.g. \"JFC\" for Jupiter-family comet streams)",
    "parent_body": "Identified parent comet or asteroid (e.g. \"109P/Swift-Tuttle\" for Perseids, \"3200 Phaethon\" for Geminids); null if parent unknown",
    "remarks": "Free-text notes from the MDC submitter (null if none)",
    "ote": "OTE (Orbital Type) classification flag from the MDC",
    "references": "Literature reference(s) for this solution",
}

DESCRIPTION = """\
The complete IAU Meteor Data Center shower catalogue with radiant coordinates, \
geocentric velocities, orbital elements, and parent body identifications.

The International Astronomical Union (IAU) Meteor Data Center maintains the authoritative \
list of meteor showers. This dataset includes every entry from the MDC shower database: \
established showers, working-list candidates, and records flagged for various issues \
(insufficient data, duplicates, misclassifications). Multiple records per shower reflect \
independent analyses by different research groups.

Meteor showers occur when Earth passes through a stream of debris shed by a comet or, \
less commonly, an asteroid along its orbit. The radiant -- the apparent point on the sky \
from which shower meteors diverge -- is determined by the intersection geometry of Earth's \
orbit with the meteoroid stream. The geocentric velocity depends on the encounter geometry \
and the stream's own orbital velocity: head-on encounters with retrograde streams (like \
the Perseids, from comet 109P/Swift-Tuttle) produce fast meteors at 59 km/s, while \
overtaking encounters with prograde streams (like the Taurids) yield slower meteors near \
27 km/s. The radiant position drifts daily as Earth's motion changes the apparent approach \
direction, captured by the ra_daily_motion and dec_daily_motion columns.

The orbital elements of each shower constrain the identity of its parent body. Established \
parent-shower associations are well-determined for major showers (e.g., 1P/Halley for the \
Eta Aquariids and Orionids, 21P/Giacobini-Zinner for the Draconids), but many working-list \
showers lack confirmed parents. The solar longitude at peak activity provides a more precise \
timing reference than calendar date, as it accounts for the irregularities of Earth's \
elliptical orbit. Multiple records per IAU shower number reflect independent analyses using \
different observational techniques (visual, video, radar), each contributing orbital element \
solutions with varying precision and sample sizes recorded in the n_meteors column.
"""


def parse_mdc_file(text: str) -> pd.DataFrame:
    """Parse IAU MDC pipe-delimited text into a DataFrame."""
    rows = []
    for line in text.splitlines():
        if not line.startswith('"'):
            continue
        # Fields are pipe-delimited and quoted
        parts = line.split("|")
        # Strip quotes and whitespace from each field
        cleaned = [p.strip('"').strip() for p in parts]
        rows.append(cleaned)

    # Trim or pad rows to match expected column count
    n_cols = len(COLUMNS)
    trimmed = []
    for row in rows:
        if len(row) >= n_cols:
            trimmed.append(row[:n_cols])
        else:
            trimmed.append(row + [""] * (n_cols - len(row)))

    df = pd.DataFrame(trimmed, columns=COLUMNS)
    return df


def main():
    # ── Fetch with year fallback ────────────────────────────────────
    print(f"Fetching IAU MDC meteor shower data ({YEAR})...")
    resp = requests.get(FULL_URL, timeout=60)
    if resp.status_code == 404:
        fallback_url = f"{BASE_URL}/streamfulldata{YEAR - 1}.txt"
        print(f"  {YEAR} file not found, trying {YEAR - 1}...")
        resp = requests.get(fallback_url, timeout=60)
    resp.raise_for_status()

    df = parse_mdc_file(resp.text)
    print(f"  {len(df):,} records parsed")

    # ── Numeric coercion ─────────────────────────────────────────────
    int_cols = ["lp", "iau_no"]
    for col in int_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int32")

    df["ad_no"] = pd.to_numeric(df["ad_no"], errors="coerce").astype("Int32")
    df["status_code"] = pd.to_numeric(df["status_code"], errors="coerce").astype("Int16")

    float_cols = [
        "sol_lon_begin_deg", "sol_lon_end_deg", "sol_lon_peak_deg",
        "ra_deg", "dec_deg", "ra_daily_motion", "dec_daily_motion",
        "geocentric_velocity_kms",
        "sun_centered_ecliptic_lon_deg", "sun_centered_ecliptic_lat_deg",
        "ecliptic_lat_deg", "theta_deg", "phi_deg",
        "semi_major_axis_au", "perihelion_distance_au", "eccentricity",
        "arg_perihelion_deg", "ascending_node_deg", "inclination_deg",
    ]
    for col in float_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["n_meteors"] = pd.to_numeric(df["n_meteors"], errors="coerce").astype("Int32")
    df["group_no"] = pd.to_numeric(df["group_no"], errors="coerce").astype("Int32")

    # ── Derived columns ──────────────────────────────────────────────
    df["status"] = df["status_code"].map(STATUS_MAP).fillna("unknown")
    df["is_established"] = df["status_code"] == 1

    # Clean string columns
    str_cols = ["code", "shower_name", "activity_type", "flags",
                "parent_body", "remarks", "ote", "references"]
    for col in str_cols:
        df[col] = df[col].str.strip()
        df[col] = df[col].replace("", pd.NA)

    # Clean up references: strip HTML tags and leading numbering
    df["references"] = (
        df["references"]
        .str.replace(r"<[^>]+>", "", regex=True)
        .str.replace(r"^\d+\]\s*", "", regex=True)
        .str.strip()
        .replace("", pd.NA)
    )

    # Drop lookup_table column (always the same value)
    df = df.drop(columns=["lookup_table"])

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # ── Sort ─────────────────────────────────────────────────────────
    df = df.sort_values(["iau_no", "ad_no"]).reset_index(drop=True)

    # ── Stats ────────────────────────────────────────────────────────
    n_unique = df["iau_no"].nunique()
    n_established = int(df[df["ad_no"] == 0]["is_established"].sum())
    n_with_parent = int(df["parent_body"].notna().sum())

    print(f"  {n_unique:,} unique showers ({n_established} established)")
    print(f"  {n_with_parent:,} records with identified parent body")

    quick_stats = f"""\
- **{len(df):,}** records across **{n_unique:,}** unique showers
- **{n_established}** IAU-established showers
- **{n_with_parent:,}** records with identified parent body"""

    usage = """\
```python
from datasets import load_dataset
import matplotlib.pyplot as plt

ds = load_dataset("juliensimon/iau-meteor-showers", split="train")
df = ds.to_pandas()

# All established showers (primary record only)
established = df[(df["is_established"] == True) & (df["ad_no"] == 0)]

# Major annual showers sorted by geocentric velocity
majors = established[established["activity_type"] == "annual"].sort_values(
    "geocentric_velocity_kms", ascending=False
)

# Plot geocentric velocity distribution of established showers
plt.figure(figsize=(10, 5))
plt.hist(established["geocentric_velocity_kms"].dropna(), bins=30, edgecolor="black")
plt.xlabel("Geocentric Velocity (km/s)")
plt.ylabel("Number of Showers")
plt.title("Geocentric Velocity Distribution of IAU Established Meteor Showers")
plt.tight_layout()
plt.show()

# Showers with known parent bodies
with_parent = df[df["parent_body"].notna()][
    ["shower_name", "parent_body", "iau_no"]
].drop_duplicates("iau_no")
print(with_parent.head(20))
```"""

    # ── Publish ──────────────────────────────────────────────────────
    with Pipeline(
        repo=HF_REPO,
        pretty_name="IAU Meteor Shower Database",
        description=DESCRIPTION,
        tags=["space", "meteors", "meteor-showers", "iau", "orbital-mechanics",
              "open-data", "tabular-data", "parquet"],
        source_url="https://www.ta3.sk/IAUC22DB/MDC2022/",
        task_categories=["tabular-classification", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA17666/PIA17666~small.jpg",
            "alt": "Rosetta spacecraft approaching Comet 67P/Churyumov-Gerasimenko",
            "credit": "NASA/ESA",
        },
        related_datasets=[
            "juliensimon/neo-close-approaches",
            "juliensimon/fireball-bolide-events",
        ],
    ) as p:
        p.publish(
            df,
            filename="iau_meteor_showers.parquet",
            min_rows=800,
            expected_columns=[
                "lp", "iau_no", "ad_no", "code", "status_code", "status",
                "shower_name", "ra_deg", "dec_deg", "geocentric_velocity_kms",
                "semi_major_axis_au", "eccentricity", "inclination_deg",
            ],
            critical_columns=["iau_no", "code", "shower_name", "status"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update IAU meteor showers: {len(df):,} records, {n_unique:,} showers",
        )
    print("Done.")


if __name__ == "__main__":
    main()
