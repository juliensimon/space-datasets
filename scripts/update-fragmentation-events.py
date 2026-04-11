#!/usr/bin/env python3
"""Derive orbital fragmentation events from CelesTrak SATCAT and upload to HF.

Identifies all launches that produced significant cataloged debris (>=4 pieces),
indicating a breakup event (explosion, collision, anomalous event, or deliberate
destruction). For each event, the parent object is identified, and debris
statistics and orbital parameters are computed.

Based on the methodology used by NASA's Orbital Debris Program Office in the
"History of On-Orbit Satellite Fragmentations" report series.
"""

import pandas as pd

from hf_dataset_utils import Pipeline

SATCAT_URL = "https://celestrak.org/pub/satcat.csv"
HF_REPO = "juliensimon/orbital-fragmentation-events"
MIN_DEBRIS = 4  # minimum cataloged debris to qualify as a fragmentation event

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "parent_object_id": "International designator (COSPAR ID) of the parent object (e.g. '1999-025A'); format is YYYY-NNNP where YYYY=launch year, NNN=launch number, P=piece letter",
    "parent_norad_id": "NORAD catalog number of the parent spacecraft or rocket body; sequential integer assigned by the 18th Space Defense Squadron; primary key for cross-referencing with TLE databases",
    "parent_name": "Name of the parent spacecraft or rocket body as listed in the NORAD catalog (e.g. 'FENGYUN 1C', 'COSMOS 2251')",
    "parent_object_type": "Type of the parent object: 'PAY' (payload/spacecraft), 'R/B' (rocket body or upper stage), 'DEB' (debris); most fragmentation events originate from PAY or R/B",
    "country_code": "Two- or three-letter country or organization code of the owner/operator (e.g. 'US', 'CIS', 'PRC', 'ESA') as assigned in the SATCAT",
    "launch_date": "Date of the original launch of the parent object (UTC); used to compute debris residence time; null if launch date not cataloged",
    "launch_year": "Year of launch extracted from launch_date; useful for grouping fragmentation events by decade or era",
    "launch_site": "COSPAR launch site code (e.g. 'TYMSC' = Baikonur Cosmodrome, 'AFETR' = Cape Canaveral); null if unknown",
    "debris_cataloged": "Total number of trackable debris pieces (>~10 cm) cataloged from this fragmentation event; Fengyun-1C ASAT test: 3,500+; Cosmos/Iridium collision: 2,300+",
    "debris_on_orbit": "Number of cataloged debris pieces still in orbit at the time of the last SATCAT update; decreases over time as fragments decay",
    "debris_decayed": "Number of cataloged debris pieces that have reentered the atmosphere; equals debris_cataloged minus debris_on_orbit",
    "decay_pct": "Percentage of total cataloged debris that has decayed (0-100); higher values indicate better long-term cleanup by atmospheric drag; low-altitude events decay faster",
    "apogee_km": "Apogee (highest point) altitude of the parent object's orbit above Earth's surface in km; null if orbital elements unavailable; high apogee means long debris lifetime",
    "perigee_km": "Perigee (lowest point) altitude of the parent object's orbit above Earth's surface in km; low perigee increases atmospheric drag and debris decay rate",
    "altitude_km": "Mean orbital altitude in km, approximately (apogee + perigee) / 2; used to classify the orbital regime and estimate debris lifetime",
    "inclination_deg": "Orbital inclination of the parent object in degrees (0-180); determines which latitudes the debris cloud can reach; sun-synchronous orbits are ~97-98 deg",
    "period_min": "Orbital period of the parent object in minutes; ~88 min at 200 km LEO, ~1436 min at GEO; null if not recorded",
    "orbit_type": "Orbital regime classification: 'LEO' (<2,000 km), 'MEO' (2,000-35,286 km), 'GEO' (~35,786 km), 'HEO' (highly elliptical), 'unknown' if altitude unavailable",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Catalog of orbital fragmentation events derived from the NORAD Satellite Catalog \
(SATCAT) via CelesTrak. Each event represents a launch that produced significant \
cataloged debris from breakups, explosions, collisions, or anomalous events.

Orbital fragmentation is the single largest source of space debris. The most \
consequential events include China's 2007 Fengyun-1C anti-satellite missile test \
(over 3,500 trackable fragments), the 2009 Iridium 33/Cosmos 2251 collision \
(~2,300 cataloged pieces), and the 2021 Russian ASAT test against Cosmos 1408. \
Together, a handful of major breakups account for a disproportionate share of the \
total tracked debris population.

The root causes of fragmentation have shifted over time. Early decades were \
dominated by accidental explosions of rocket upper stages retaining residual \
propellant. More recently, deliberate destruction (ASAT tests) and accidental \
collisions have become prominent. The Kessler syndrome hypothesis warns that \
above a critical density threshold, collisional cascading could make certain \
orbital bands unusable -- a concern that fragmentation event data directly informs.
"""


def identify_parent(group: pd.DataFrame) -> pd.Series:
    """Identify the most likely parent object for a fragmentation event.

    Priority: piece "A" payload > any payload > piece "A" rocket body >
    any rocket body > first non-DEB object > first object.
    """
    non_deb = group[group["OBJECT_TYPE"] != "DEB"]
    pay = non_deb[non_deb["OBJECT_TYPE"] == "PAY"]
    rb = non_deb[non_deb["OBJECT_TYPE"] == "R/B"]

    # Check for "A" piece (primary object of the launch)
    a_piece = non_deb[non_deb["OBJECT_ID"].str.strip().str.endswith("A")]

    if len(pay) > 0:
        a_pay = pay[pay["OBJECT_ID"].str.strip().str.endswith("A")]
        if len(a_pay) > 0:
            return a_pay.iloc[0]
        return pay.iloc[0]
    if len(a_piece) > 0:
        return a_piece.iloc[0]
    if len(rb) > 0:
        return rb.iloc[0]
    if len(non_deb) > 0:
        return non_deb.iloc[0]
    return group.iloc[0]


def main():
    print("Fetching SATCAT from CelesTrak...")
    df = pd.read_csv(SATCAT_URL)
    print(f"  {len(df):,} total objects")

    # Parse dates
    df["LAUNCH_DATE"] = pd.to_datetime(df["LAUNCH_DATE"], errors="coerce")
    df["DECAY_DATE"] = pd.to_datetime(df["DECAY_DATE"], errors="coerce")

    # Extract launch ID prefix (YYYY-NNN) from international designator
    df["launch_id"] = df["OBJECT_ID"].str.strip().str[:8]

    # ── Compute debris statistics per launch ─────────────────────────────
    deb = df[df["OBJECT_TYPE"] == "DEB"]

    deb_stats = deb.groupby("launch_id").agg(
        debris_cataloged=("NORAD_CAT_ID", "count"),
        debris_on_orbit=("DECAY_DATE", lambda x: int(x.isna().sum())),
    ).reset_index()

    # Filter to launches with significant debris (fragmentation events)
    deb_stats = deb_stats[deb_stats["debris_cataloged"] >= MIN_DEBRIS].copy()
    print(f"  {len(deb_stats):,} launches with >= {MIN_DEBRIS} cataloged debris")

    # ── Identify parent objects ──────────────────────────────────────────
    print("Identifying parent objects...")
    parents = []
    for lid in deb_stats["launch_id"]:
        group = df[df["launch_id"] == lid]
        parent = identify_parent(group)

        parents.append({
            "launch_id": lid,
            "parent_norad_id": int(parent["NORAD_CAT_ID"]),
            "parent_name": str(parent["OBJECT_NAME"]).strip(),
            "parent_object_type": str(parent["OBJECT_TYPE"]).strip(),
            "parent_object_id": str(parent["OBJECT_ID"]).strip(),
            "country_code": str(parent["OWNER"]).strip() if pd.notna(parent["OWNER"]) else "",
            "launch_date": parent["LAUNCH_DATE"],
            "launch_site": str(parent["LAUNCH_SITE"]).strip() if pd.notna(parent["LAUNCH_SITE"]) else "",
            "apogee_km": parent["APOGEE"],
            "perigee_km": parent["PERIGEE"],
            "inclination_deg": parent["INCLINATION"],
            "period_min": parent["PERIOD"],
        })

    parent_df = pd.DataFrame(parents)

    # ── Merge and derive columns ─────────────────────────────────────────
    events = deb_stats.merge(parent_df, on="launch_id")

    # Compute debris decay percentage
    events["debris_decayed"] = events["debris_cataloged"] - events["debris_on_orbit"]
    events["decay_pct"] = (
        events["debris_decayed"] / events["debris_cataloged"] * 100
    ).round(1)

    # Compute approximate altitude (mean of apogee and perigee)
    events["altitude_km"] = ((events["apogee_km"] + events["perigee_km"]) / 2).round(0)

    # Classify orbit type
    def classify_orbit(row):
        alt = row["altitude_km"]
        if pd.isna(alt):
            return "unknown"
        if alt < 2000:
            return "LEO"
        elif alt < 35786 - 500:
            return "MEO"
        elif alt < 35786 + 500:
            return "GEO"
        else:
            return "HEO"

    events["orbit_type"] = events.apply(classify_orbit, axis=1)

    # Derive event year from launch date
    events["launch_year"] = events["launch_date"].dt.year.astype("Int32")

    # ── Type coercion ────────────────────────────────────────────────────
    events["parent_norad_id"] = events["parent_norad_id"].astype("int32")
    events["debris_cataloged"] = events["debris_cataloged"].astype("int32")
    events["debris_on_orbit"] = events["debris_on_orbit"].astype("int32")
    events["debris_decayed"] = events["debris_decayed"].astype("int32")
    for col in ["apogee_km", "perigee_km", "inclination_deg", "period_min", "altitude_km"]:
        events[col] = pd.to_numeric(events[col], errors="coerce")

    # ── Select and order columns ─────────────────────────────────────────
    events = events[[
        "parent_object_id", "parent_norad_id", "parent_name",
        "parent_object_type", "country_code", "launch_date", "launch_year",
        "launch_site", "debris_cataloged", "debris_on_orbit", "debris_decayed",
        "decay_pct", "apogee_km", "perigee_km", "altitude_km",
        "inclination_deg", "period_min", "orbit_type",
    ]].copy()

    # Sort by debris count descending (most significant events first)
    events = events.sort_values("debris_cataloged", ascending=False).reset_index(drop=True)

    # Keep only described columns
    events = events[[c for c in events.columns if c in COLUMN_DESCRIPTIONS]]

    # Drop the intermediate launch_id if it survived
    if "launch_id" in events.columns:
        events = events.drop(columns=["launch_id"])

    # ── Compute stats for README ─────────────────────────────────────────
    n_events = len(events)
    total_debris = int(events["debris_cataloged"].sum())
    total_on_orbit = int(events["debris_on_orbit"].sum())
    top_event = events.iloc[0]
    year_min = int(events["launch_year"].min()) if events["launch_year"].notna().any() else 0
    year_max = int(events["launch_year"].max()) if events["launch_year"].notna().any() else 0

    orbit_dist = events["orbit_type"].value_counts()
    orbit_str = ", ".join(f"{otype} ({cnt})" for otype, cnt in orbit_dist.items())

    top_countries = events["country_code"].value_counts().head(5)
    top_countries_str = ", ".join(
        f"{code} ({count})" for code, count in top_countries.items()
    )

    quick_stats = f"""\
- **{n_events:,}** fragmentation events spanning **{year_min}** to **{year_max}**
- **{total_debris:,}** total cataloged debris, **{total_on_orbit:,}** still on orbit
- Worst event: **{top_event['parent_name']}** with **{top_event['debris_cataloged']:,}** cataloged debris
- Orbit distribution: {orbit_str}
- Top countries: {top_countries_str}"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/orbital-fragmentation-events", split="train")
df = ds.to_pandas()

# Most prolific breakups
print(df.nlargest(10, "debris_cataloged")[["parent_name", "debris_cataloged", "debris_on_orbit"]])

# Events still polluting orbit (>90% debris remaining)
active_pollution = df[df["decay_pct"] < 10].sort_values("debris_on_orbit", ascending=False)

# Debris by orbit type
import matplotlib.pyplot as plt
by_orbit = df.groupby("orbit_type")["debris_cataloged"].sum().sort_values(ascending=False)
by_orbit.plot(kind="bar", edgecolor="black")
plt.ylabel("Total Cataloged Debris")
plt.title("Fragmentation Debris by Orbit Type")
plt.tight_layout()
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Orbital Fragmentation Events",
        description=DESCRIPTION,
        tags=["space", "debris", "fragmentation", "orbital-mechanics",
              "collisions", "open-data", "tabular-data", "parquet"],
        source_url="https://celestrak.org/pub/satcat.csv",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994",
        banner={
            "url": "https://images-assets.nasa.gov/image/iss071e439624/iss071e439624~medium.jpg",
            "alt": "An orbital sunrise illuminates the Earth's atmosphere, seen from the ISS",
            "credit": "NASA",
        },
        related_datasets=[
            "juliensimon/reentry-events",
            "juliensimon/space-track-satcat",
            "juliensimon/gcat-satellite-catalog",
        ],
    ) as p:
        events = p.clean(
            events,
            numeric=["parent_norad_id", "debris_cataloged", "debris_on_orbit",
                     "debris_decayed", "decay_pct", "apogee_km", "perigee_km",
                     "altitude_km", "inclination_deg", "period_min"],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            events,
            filename="fragmentation_events.parquet",
            min_rows=200,
            expected_columns=[
                "parent_object_id", "parent_norad_id", "parent_name",
                "country_code", "debris_cataloged", "debris_on_orbit",
                "altitude_km", "orbit_type",
            ],
            critical_columns=["parent_norad_id", "parent_name", "debris_cataloged"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update fragmentation events: {n_events:,} events, {total_debris:,} debris",
        )
    print("Done.")


if __name__ == "__main__":
    main()
