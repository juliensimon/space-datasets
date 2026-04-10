#!/usr/bin/env python3
"""Fetch GCAT Satellite Catalog, upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from dataset_images import banner_markdown, download_banner
from validate import check_dataset


URL = "https://planet4589.org/space/gcat/tsv/cat/satcat.tsv"
HF_REPO = "juliensimon/gcat-satellite-catalog"

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


def main():
    # ── Fetch ────────────────────────────────────────────────────────────
    print("Fetching GCAT satellite catalog...")
    df = pd.read_csv(
        URL, sep="\t", comment="#", names=COL_NAMES,
        low_memory=False, skipinitialspace=True,
    )
    print(f"  {len(df):,} objects")

    # ── Transform ────────────────────────────────────────────────────────
    # Strip whitespace from string columns
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].str.strip()

    # Replace GCAT dash placeholder with NaN
    df.replace("-", pd.NA, inplace=True)

    # Coerce numeric columns
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # ── Validate ─────────────────────────────────────────────────────────
    check_dataset(
        df, "gcat-satcat", min_rows=50000,
        expected_columns=["jcat_id", "name", "status", "owner", "state_code",
                          "launch_date", "perigee_km", "apogee_km"],
        critical_columns=["jcat_id", "name"],
    )

    # ── Write parquet + README ───────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        data_dir = tmp_dir / "data"
        data_dir.mkdir()
        df.to_parquet(
            data_dir / "satcat.parquet", index=False,
            engine="pyarrow", compression="zstd",
        )

        # Stats for README
        n_countries = df["state_code"].nunique()
        n_owners = df["owner"].nunique()
        n_orbits = df["op_orbit"].nunique()
        n_active = int((df["status"] == "O").sum()) if "status" in df.columns else 0
        n_decayed = int((df["status"] == "R").sum()) if "status" in df.columns else 0
        n_types = df["type"].nunique() if "type" in df.columns else 0

        banner_file = download_banner("gcat-satcat", tmp_dir)
        banner_md = banner_markdown("gcat-satcat", banner_file)

        (tmp_dir / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "GCAT Satellite Catalog"
language:
  - en
description: "Comprehensive satellite catalog from GCAT with {len(df):,} space objects — spacecraft, rocket bodies, debris — including orbital parameters, mass, and ownership. Based on Jonathan McDowell's General Catalog of Artificial Space Objects."
task_categories:
  - tabular-classification
tags:
  - space
  - satellites
  - satellite-catalog
  - gcat
  - orbital-mechanics
  - spacecraft
  - open-data
  - tabular-data
  - parquet
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/satcat.parquet
    default: true
size_categories:
  - 10K<n<100K
---

# GCAT Satellite Catalog
{banner_md}
*Part of the [Orbital Mechanics Datasets](https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994) collection on Hugging Face.*

Comprehensive catalog of **{len(df):,}** space objects from
[GCAT](https://planet4589.org/space/gcat/) (General Catalog of Artificial Space Objects),
maintained by Jonathan McDowell at the Harvard-Smithsonian Center for Astrophysics.
Covers every cataloged spacecraft, rocket body, and debris piece from 1957 to present,
with orbital parameters, physical dimensions, mass, ownership, and operational status.

## Dataset description

The GCAT Satellite Catalog (satcat) is the most comprehensive open reference for objects that have been cataloged in Earth orbit and beyond. Unlike the US Space Force catalog (which tracks radar-observable objects) or the UCS Satellite Database (which covers only active satellites), GCAT aims to catalog every artificial space object ever assigned an identifier — including rocket bodies, mission-related debris, and objects that reentered decades ago.

Each entry includes the JCAT identifier (McDowell's own comprehensive numbering), the NORAD/Space Force catalog number, COSPAR international designator, object type classification, ownership and manufacturer information, physical properties (mass, dimensions, shape), and orbital elements at a reference epoch. The status field distinguishes between objects still in orbit ("O"), those that have reentered ("R"), and other dispositions. The operational orbit field classifies the orbit type (LEO, MEO, GEO, HEO, etc.) with inclination qualifiers.

This dataset is valuable for studying the growth of the space object population over time, analyzing debris generation events, comparing national space programs by object count and mass on orbit, and building training data for orbital classification models. It complements the GCAT launch log (which records the launches that placed these objects) and the Space-Track SATCAT (which provides the official US military catalog perspective on the same objects).

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `jcat_id` | string | McDowell's GCAT unique identifier (e.g. "S00001"); assigned sequentially across all artificial space objects regardless of country or tracking status |
| `satcat_number` | float | NORAD/Space Force catalog number — 5-digit integer assigned sequentially by US Space Command as objects are tracked; null for objects not yet independently tracked by Space Force |
| `launch_tag` | string | GCAT launch event identifier linking this object to its originating launch in the GCAT launch log |
| `piece` | string | COSPAR international designator in YYYY-NNNX format: launch year + sequential launch number + piece letter (e.g. "1957-001A" for Sputnik 1, "1957-001B" for its rocket body) |
| `type` | string | Object type: P=Payload (operational spacecraft), R=Rocket Body (upper stage or booster), D=Debris (fragmentation or mission-related), U=Unknown |
| `name` | string | Primary tracking designation used by GCAT/Space Force; for debris and rocket bodies this is typically a generic label (e.g. "ATLAS CENTAUR R/B") rather than a proper name |
| `pl_name` | string | Operational payload name assigned by the owner/operator (e.g. "STARLINK-1234"); null for rocket bodies and debris pieces that have no named payload identity |
| `launch_date` | string | Date the object was launched (ISO format); for objects deployed from a parent craft this is the original launch date of the parent mission |
| `parent` | string | JCAT identifier of the parent object this piece separated from (e.g. a rocket stage from its payload); null for primary payloads launched directly |
| `separation_date` | string | Date and time this object separated from its parent (ISO format); null if the object was the primary payload or separation event is unknown |
| `primary` | string | Central body the object orbits: Earth, Moon, Sun, Mars, etc.; most cataloged objects are "Earth" |
| `decay_date` | string | Date the object reentered the atmosphere or was otherwise removed from orbit (ISO format); null if the object is still in orbit — a non-null value confirms deorbit |
| `status` | string | Orbital status: O=currently in orbit, R=reentered/decayed, AR=reentered after achieving orbit, D=intentionally deorbited, L=landed, other codes for deep space dispositions |
| `dest` | string | Destination or final disposition code for objects that left Earth orbit (e.g. lunar, planetary, escape trajectory) |
| `owner` | string | GCAT code for the owning organization or operator (e.g. "NASA", "SPACEX", "ROSCOSMOS"); may differ from the launching state |
| `state_code` | string | ISO 3166-1 alpha-2 country code of the responsible state (e.g. "US", "RU", "CN"); "ISS" for International Space Station components; reflects political responsibility, not necessarily physical launch location |
| `manufacturer` | string | GCAT code for the organization that built the object; null when manufacturer is unknown or not cataloged |
| `bus` | string | Spacecraft bus or platform model (e.g. "SSL-1300", "Boeing-702"); identifies the structural/avionics heritage; null when not publicly known |
| `motor` | string | Propulsion system or motor designation for rocket bodies; null for payloads or when propulsion details are unknown |
| `mass_kg` | float | Launch mass of the object in kilograms; for payloads this typically includes propellant; null when mass is not publicly known |
| `mass_flag` | string | Qualifier on mass_kg: "~" approximate, "<" upper bound, ">" lower bound; null when mass value is a reported figure |
| `dry_mass_kg` | float | Dry mass (no propellant) in kilograms; null for most objects where dry mass is not separately reported |
| `dry_flag` | string | Qualifier on dry_mass_kg: "~" approximate, "<" upper bound, ">" lower bound |
| `total_mass_kg` | float | Total mass including all stages or attached hardware in kilograms; null when not reported |
| `total_flag` | string | Qualifier on total_mass_kg: "~" approximate, "<" upper bound, ">" lower bound |
| `length_m` | float | Longest dimension of the object in meters; null for most objects where dimensions are not publicly cataloged |
| `length_flag` | string | Qualifier on length_m: "~" approximate, "<" upper bound, ">" lower bound |
| `diameter_m` | float | Maximum cross-sectional diameter in meters; null when not publicly known |
| `diameter_flag` | string | Qualifier on diameter_m: "~" approximate, "<" upper bound, ">" lower bound |
| `span_m` | float | Maximum span including deployable structures such as solar arrays or antennas in meters; null when not cataloged |
| `span_flag` | string | Qualifier on span_m: "~" approximate, "<" upper bound, ">" lower bound |
| `shape` | string | Geometric shape description (e.g. "box", "cyl", "sphere", "cone+cyl"); used for radar cross-section modeling |
| `orbit_date` | string | Epoch date for the orbital elements in perigee_km, apogee_km, inclination_deg; null if no orbital solution exists |
| `perigee_km` | float | Altitude of the closest orbital point above Earth's surface in kilometers (at epoch); null for objects without tracked orbits or with sub-orbital trajectories |
| `perigee_flag` | string | Qualifier on perigee_km: "~" approximate, "<" upper bound, ">" lower bound |
| `apogee_km` | float | Altitude of the farthest orbital point above Earth's surface in kilometers (at epoch); null for objects without tracked orbits; perigee=apogee indicates a circular orbit |
| `apogee_flag` | string | Qualifier on apogee_km: "~" approximate, "<" upper bound, ">" lower bound |
| `inclination_deg` | float | Orbital inclination from Earth's equatorial plane in degrees: 0°=equatorial prograde, 90°=polar, 97-98°=Sun-synchronous, 63.4°=Molniya critical inclination; null for objects without tracked orbits |
| `inclination_flag` | string | Qualifier on inclination_deg: "~" approximate, "<" upper bound, ">" lower bound |
| `op_orbit` | string | Operational orbit regime classification: LEO (Low Earth Orbit, <2000 km), MEO (Medium Earth Orbit, 2000–35786 km), GEO (Geostationary, ~35786 km), HEO (Highly Elliptical), Lunar, Heliocentric, etc.; may include inclination qualifiers (e.g. "SSO" for Sun-synchronous LEO) |
| `orbit_qual` | string | Orbit determination quality indicator; reflects confidence in the orbital elements |
| `alt_names` | string | Pipe-separated list of alternative names, previous designations, or synonyms for the object; null when no alternates are known |

## Quick stats

- **{len(df):,}** cataloged space objects
- **{n_active:,}** currently in orbit (status "O")
- **{n_decayed:,}** reentered (status "R")
- **{n_countries}** countries/state codes
- **{n_owners}** distinct owners/operators
- **{n_orbits}** orbit type classifications
- **{n_types}** object type codes

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/gcat-satellite-catalog", split="train")
df = ds.to_pandas()

# Currently active satellites
active = df[df["status"] == "O"]
print(f"{{len(active):,}} objects currently in orbit")

# Objects by country
print(df["state_code"].value_counts().head(10))

# Heaviest objects in orbit
in_orbit = df[df["status"] == "O"].dropna(subset=["mass_kg"])
print(in_orbit.nlargest(10, "mass_kg")[["name", "owner", "mass_kg", "op_orbit"]])

# LEO vs GEO population
leo = df[df["op_orbit"].str.contains("LEO", na=False)]
geo = df[df["op_orbit"].str.contains("GEO", na=False)]
print(f"LEO: {{len(leo):,}}, GEO: {{len(geo):,}}")

# Growth of cataloged objects over time
df["launch_year"] = df["launch_date"].str[:4]
print(df["launch_year"].value_counts().sort_index().tail(10))
```

## Data source

[GCAT](https://planet4589.org/space/gcat/) (General Catalog of Artificial Space Objects)
by Jonathan McDowell, Harvard-Smithsonian Center for Astrophysics. GCAT is the most
comprehensive public catalog of artificial space objects and is widely used in the
spaceflight research community.

## Update schedule

Static dataset — rebuilt manually when GCAT is updated (approximately monthly).

## Related datasets

- [space-launch-log](https://huggingface.co/datasets/juliensimon/space-launch-log) — Complete global launch history from GCAT
- [space-track-satcat](https://huggingface.co/datasets/juliensimon/space-track-satcat) — NORAD satellite catalog from Space-Track
- [ucs-satellite-database](https://huggingface.co/datasets/juliensimon/ucs-satellite-database) — Union of Concerned Scientists active satellite database

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/gcat-satellite-catalog) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{gcat_satellite_catalog,
  author = {{Simon, Julien}},
  title = {{GCAT Satellite Catalog}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/gcat-satellite-catalog}},
  note = {{Based on GCAT by Jonathan McDowell, Harvard-Smithsonian Center for Astrophysics}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update GCAT satellite catalog: {len(df):,} objects"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp_dir), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={len(df)}\n")
    print(f"Done. {len(df):,} objects.")


if __name__ == "__main__":
    main()
