#!/usr/bin/env python3
"""Derive orbital fragmentation events from CelesTrak SATCAT and upload to HF.

Identifies all launches that produced significant cataloged debris (>=4 pieces),
indicating a breakup event (explosion, collision, anomalous event, or deliberate
destruction). For each event, the parent object is identified, and debris
statistics and orbital parameters are computed.

Based on the methodology used by NASA's Orbital Debris Program Office in the
"History of On-Orbit Satellite Fragmentations" report series.
"""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from dataset_images import banner_markdown, download_banner
from validate import check_dataset

SATCAT_URL = "https://celestrak.org/pub/satcat.csv"
HF_REPO = "juliensimon/orbital-fragmentation-events"
MIN_DEBRIS = 4  # minimum cataloged debris to qualify as a fragmentation event


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

    # ── Validate ─────────────────────────────────────────────────────────
    check_dataset(
        events, "fragmentation-events", min_rows=200,
        expected_columns=[
            "parent_object_id", "parent_norad_id", "parent_name",
            "country_code", "debris_cataloged", "debris_on_orbit",
            "altitude_km", "orbit_type",
        ],
        critical_columns=["parent_norad_id", "parent_name", "debris_cataloged"],
    )

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

    top5 = events.nlargest(5, "debris_cataloged")
    top5_lines = "\n".join(
        f"| {r['parent_name']} | {r['country_code']} | {r['debris_cataloged']:,} | "
        f"{r['debris_on_orbit']:,} | {int(r['altitude_km']) if pd.notna(r['altitude_km']) else 'N/A'} |"
        for _, r in top5.iterrows()
    )

    # ── Write parquet and README ─────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "fragmentation-events.parquet"
        events.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.2f} MB parquet")

        banner_file = download_banner("fragmentation-events", tmp)
        banner_md = banner_markdown("fragmentation-events", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Orbital Fragmentation Events"
language:
  - en
description: "Catalog of {n_events:,} orbital fragmentation events derived from the NORAD SATCAT via CelesTrak. Each event represents a launch that produced significant cataloged debris from breakups, explosions, collisions, or anomalous events. Includes parent object identification, debris counts, and orbital parameters."
task_categories:
  - tabular-classification
tags:
  - space
  - debris
  - fragmentation
  - orbital-mechanics
  - collisions
  - open-data
  - tabular-data
  - parquet
size_categories:
  - n<1K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/fragmentation-events.parquet
    default: true
---

# Orbital Fragmentation Events
{banner_md}
*Part of the [Orbital Mechanics Datasets](https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994) collection on Hugging Face.*

Catalog of **{n_events:,}** orbital fragmentation events derived from the NORAD Satellite Catalog
(SATCAT) via [CelesTrak](https://celestrak.org/). A fragmentation event is identified as any launch
that produced {MIN_DEBRIS} or more cataloged debris objects, indicating an in-orbit breakup caused
by explosions, collisions, anomalous events, or deliberate destruction.

## Dataset description

Every significant breakup event in Earth orbit since {year_min} is captured in this dataset. When a
satellite or rocket body fragments -- whether from a propulsion failure, accidental collision, deliberate
destruction (e.g., anti-satellite tests), or unexplained anomaly -- it produces tracked debris objects
cataloged by the 18th Space Defense Squadron. This dataset aggregates those debris back to their
parent launch, identifying the primary spacecraft or rocket body involved and computing debris
statistics. It is inspired by the methodology used in NASA's "History of On-Orbit Satellite
Fragmentations" technical report series published by the Orbital Debris Program Office.

Orbital fragmentation is the single largest source of space debris. The most consequential events in history include China's 2007 Fengyun-1C anti-satellite missile test (which created over 3,500 trackable fragments, many in long-lived orbits above 800 km), the 2009 accidental collision between Iridium 33 and the defunct Cosmos 2251 (producing roughly 2,300 cataloged pieces), and the 2021 Russian ASAT test against Cosmos 1408. Together, a handful of major breakups account for a disproportionate share of the total tracked debris population. The debris_on_orbit field reveals which events continue to pollute the space environment: high-altitude fragmentations produce debris that can persist for decades or centuries, while low-altitude events clear relatively quickly through atmospheric drag.

The root causes of fragmentation events have shifted over time. In the early decades of spaceflight, the dominant cause was accidental explosions of rocket upper stages that retained residual propellant or pressurized tanks after completing their mission. This led to the adoption of passivation requirements -- venting residual fuel and depressurizing batteries -- in modern launch vehicle designs. More recently, deliberate destruction (ASAT tests) and accidental collisions have become prominent causes. The Kessler syndrome hypothesis warns that above a critical density threshold, collisional cascading could make certain orbital bands unusable -- a concern that fragmentation event data directly informs.

This dataset enables researchers to study fragmentation event rates over time, assess the long-term debris environment contribution by orbit altitude and event type, evaluate the effectiveness of debris mitigation policies, and identify which nations and operators have generated the most orbital debris. The decay percentage field provides a measure of how effectively atmospheric drag is cleaning up after each event.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `parent_object_id` | string | International designator of parent object (COSPAR ID) |
| `parent_norad_id` | int32 | NORAD catalog number of the parent object |
| `parent_name` | string | Name of the parent spacecraft or rocket body |
| `parent_object_type` | string | `PAY` (payload), `R/B` (rocket body), `DEB` (debris) |
| `country_code` | string | Owner/operator country or organization code |
| `launch_date` | datetime | Date of the original launch (UTC) |
| `launch_year` | int32 | Year of launch (for grouping/filtering) |
| `launch_site` | string | Launch site code |
| `debris_cataloged` | int32 | Total number of cataloged debris pieces from this event |
| `debris_on_orbit` | int32 | Number of debris pieces still in orbit |
| `debris_decayed` | int32 | Number of debris pieces that have reentered |
| `decay_pct` | float | Percentage of debris that has decayed |
| `apogee_km` | float | Apogee altitude of parent object orbit (km) |
| `perigee_km` | float | Perigee altitude of parent object orbit (km) |
| `altitude_km` | float | Mean orbital altitude (km) |
| `inclination_deg` | float | Orbital inclination (degrees) |
| `period_min` | float | Orbital period (minutes) |
| `orbit_type` | string | LEO, MEO, GEO, or HEO |

## Quick stats

- **{n_events:,}** fragmentation events spanning **{year_min}** to **{year_max}**
- **{total_debris:,}** total cataloged debris, **{total_on_orbit:,}** still on orbit
- Orbit distribution: {orbit_str}
- Top countries: {top_countries_str}

### Most prolific breakup events

| Parent Object | Country | Debris Cataloged | On Orbit | Altitude (km) |
|---------------|---------|----------------:|----------:|---------------:|
{top5_lines}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/orbital-fragmentation-events", split="train")
df = ds.to_pandas()

# Most prolific breakups
df.nlargest(10, "debris_cataloged")[["parent_name", "debris_cataloged", "debris_on_orbit"]]

# Events still polluting orbit (>90% debris remaining)
active_pollution = df[df["decay_pct"] < 10].sort_values("debris_on_orbit", ascending=False)

# Breakups by orbit type
df.groupby("orbit_type")["debris_cataloged"].sum()

# Events by decade
df["decade"] = (df["launch_year"] // 10) * 10
df.groupby("decade")["parent_norad_id"].count()

# Country breakdown
df.groupby("country_code")["debris_cataloged"].agg(["count", "sum"]).sort_values("sum", ascending=False).head(10)
```

## Data source

Derived from the [CelesTrak SATCAT](https://celestrak.org/pub/satcat.csv), which mirrors the
official US Space Command catalog maintained by the 18th Space Defense Squadron. Fragmentation
events are identified by grouping cataloged debris objects by their international designator prefix
(launch ID) and filtering for launches with {MIN_DEBRIS}+ debris pieces.

For authoritative event-by-event analysis including assessed causes, see NASA's
[History of On-Orbit Satellite Fragmentations](https://orbitaldebris.jsc.nasa.gov/) report series.

## Related datasets

- [reentry-events](https://huggingface.co/datasets/juliensimon/reentry-events) -- Atmospheric reentry catalog
- [space-track-satcat](https://huggingface.co/datasets/juliensimon/space-track-satcat) -- Full NORAD satellite catalog
- [active-satellites](https://huggingface.co/datasets/juliensimon/space-track-satcat) -- Currently operational spacecraft

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Citation

```bibtex
@dataset{{fragmentation_events,
  author = {{Simon, Julien}},
  title = {{Orbital Fragmentation Events}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/orbital-fragmentation-events}},
  note = {{Derived from NORAD SATCAT via CelesTrak (Dr. T.S. Kelso)}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update fragmentation events: {n_events:,} events, {total_debris:,} debris"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={n_events}\n")
    print("Done.")


if __name__ == "__main__":
    main()
