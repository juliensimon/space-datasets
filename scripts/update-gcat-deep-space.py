#!/usr/bin/env python3
"""Fetch GCAT deep space objects and planetary landings, upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from validate import check_dataset


DEEP_URL = "https://planet4589.org/space/gcat/tsv/cat/deepcat.tsv"
LANDER_URL = "https://planet4589.org/space/gcat/tsv/cat/landercat.tsv"
HF_REPO = "juliensimon/gcat-deep-space"

DEEP_COLS = [
    "jcat", "satcat", "launch_tag", "piece", "type", "name", "pl_name",
    "ldate", "parent", "sdate", "primary", "ddate", "status", "dest",
    "owner", "state", "manufacturer", "bus", "motor", "mass", "mass_flag",
    "dry_mass", "dry_flag", "tot_mass", "tot_flag", "length", "l_flag",
    "diameter", "d_flag", "span", "span_flag", "shape", "odate", "perigee",
    "pf", "apogee", "af", "inc", "if_flag", "op_orbit", "oqual", "alt_names",
]

LANDER_COLS = [
    "jcat", "piece", "name", "owner", "state", "world", "lon", "lat",
    "ltype", "status", "launch_date", "land_date", "off_date", "dur",
    "lsite", "comment",
]


def _fetch_tsv(url, col_names, label):
    """Fetch a GCAT TSV, assign column names, clean up."""
    print(f"Fetching {label}...")
    df = pd.read_csv(url, sep="\t", comment="#", names=col_names,
                     low_memory=False, skipinitialspace=True)
    # Strip whitespace from string columns
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].str.strip()
    # Replace GCAT dash placeholder with NaN
    df.replace("-", pd.NA, inplace=True)
    print(f"  {len(df):,} {label}")
    return df


def _coerce_numeric(df, columns):
    """Coerce columns to numeric, ignoring errors."""
    for col in columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")


def main():
    # ── Fetch ────────────────────────────────────────────────────────────
    deep = _fetch_tsv(DEEP_URL, DEEP_COLS, "deep space objects")
    landers = _fetch_tsv(LANDER_URL, LANDER_COLS, "planetary landings")

    # ── Transform: coerce numeric columns ────────────────────────────────
    _coerce_numeric(deep, [
        "mass", "dry_mass", "tot_mass", "length", "diameter", "span",
        "perigee", "apogee", "inc",
    ])
    _coerce_numeric(landers, ["lon", "lat", "dur"])

    # ── Validate ─────────────────────────────────────────────────────────
    total_rows = len(deep) + len(landers)

    check_dataset(deep, "deep_space_objects", min_rows=500,
                  expected_columns=["jcat", "name", "state", "dest", "status"],
                  critical_columns=["jcat", "name"])
    check_dataset(landers, "planetary_landings", min_rows=200,
                  expected_columns=["jcat", "name", "world", "land_date", "status"],
                  critical_columns=["jcat", "name"])

    # ── Stats for README ─────────────────────────────────────────────────
    n_deep_states = deep["state"].nunique()
    n_dests = deep["dest"].nunique()
    n_lander_worlds = landers["world"].nunique()
    n_lander_states = landers["state"].nunique()

    # Landing type breakdown
    ltype_counts = landers["ltype"].value_counts()
    n_landings = int(ltype_counts.get("L", 0))
    n_impacts = int(ltype_counts.get("I", 0))

    # Notable world counts
    world_counts = landers["world"].value_counts()

    # ── Write parquet + README ───────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        data_dir = tmp_dir / "data"
        data_dir.mkdir()
        deep.to_parquet(data_dir / "deep_space_objects.parquet", index=False,
                        engine="pyarrow", compression="zstd")
        landers.to_parquet(data_dir / "planetary_landings.parquet", index=False,
                           engine="pyarrow", compression="zstd")

        (tmp_dir / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "GCAT Deep Space Objects and Planetary Landings"
language:
  - en
description: "Interplanetary spacecraft and planetary/lunar landings from Jonathan McDowell's General Catalog of Artificial Space Objects (GCAT). {total_rows:,} records across two tables."
task_categories:
  - tabular-classification
tags:
  - space
  - deep-space
  - interplanetary
  - planetary-landings
  - lunar-landings
  - gcat
  - solar-system
  - spacecraft
  - open-data
  - tabular-data
  - parquet
configs:
  - config_name: deep_space_objects
    data_files:
      - split: train
        path: data/deep_space_objects.parquet
    default: true
  - config_name: planetary_landings
    data_files:
      - split: train
        path: data/planetary_landings.parquet
size_categories:
  - 1K<n<10K
---

# GCAT Deep Space Objects and Planetary Landings

*Part of the [Solar System Datasets](https://huggingface.co/collections/juliensimon/solar-system-datasets-69c6fa681978de62dff2f347) collection on Hugging Face.*

Deep space spacecraft and planetary/lunar landings from
[GCAT](https://planet4589.org/space/gcat/) (General Catalog of Artificial Space Objects),
maintained by Jonathan McDowell at the Harvard-Smithsonian Center for Astrophysics.

Currently **{len(deep):,}** deep space objects and **{len(landers):,}** planetary landings
({total_rows:,} records total).

## Dataset description

This dataset captures humanity's exploration beyond Earth orbit in two complementary tables. The deep space catalog lists every spacecraft, rocket stage, and component that has traveled beyond cislunar space or entered a heliocentric orbit, from the pioneering Luna and Pioneer missions of 1959 to modern interplanetary probes. It includes mission metadata, physical specifications (mass, dimensions, shape), orbital parameters, and current status for each object.

The planetary landings catalog records every intentional and unintentional contact with another world -- soft landings, hard impacts, controlled crashes, and flyby probe deployments. It covers landings on {n_lander_worlds} different worlds: {', '.join(world_counts.index[:8])}{"," if len(world_counts) > 8 else ""} and more. The data spans the full international history of planetary exploration, including Soviet Luna and Venera missions, NASA's Surveyor and Apollo landings, ESA's Huygens descent to Titan, Japan's Hayabusa asteroid sample returns, China's Chang'e lunar program, and India's Chandrayaan missions.

Together these tables enable analysis of interplanetary mission trends, success rates by nation and decade, the geographic distribution of lunar landing sites, and the evolution of deep space spacecraft design over six decades.

## Configs

### `deep_space_objects` -- {len(deep):,} objects

Every known spacecraft and component that has traveled beyond Earth orbit.

| Column | Type | Description |
|--------|------|-------------|
| `jcat` | string | GCAT deep space catalog ID (e.g. D00001) |
| `satcat` | string | NORAD/Satcat ID (NNA if not assigned) |
| `launch_tag` | string | GCAT launch identifier |
| `piece` | string | Launch piece designation |
| `type` | string | Object type code (P=payload, R=rocket body, C=component) |
| `name` | string | Object name |
| `pl_name` | string | Payload name |
| `ldate` | string | Launch date |
| `parent` | string | Parent object JCAT ID |
| `sdate` | string | Separation date from parent |
| `primary` | string | Primary gravitational body |
| `ddate` | string | Deep space date |
| `status` | string | Current status code |
| `dest` | string | Destination (Luna, HCO=heliocentric, etc.) |
| `owner` | string | Owner organization |
| `state` | string | Country/state code |
| `manufacturer` | string | Manufacturer code |
| `bus` | string | Spacecraft bus type |
| `motor` | string | Propulsion motor |
| `mass` | float | Mass in kg |
| `mass_flag` | string | Mass qualifier flag |
| `dry_mass` | float | Dry mass in kg |
| `dry_flag` | string | Dry mass qualifier flag |
| `tot_mass` | float | Total mass in kg |
| `tot_flag` | string | Total mass qualifier flag |
| `length` | float | Length in meters |
| `l_flag` | string | Length qualifier flag |
| `diameter` | float | Diameter in meters |
| `d_flag` | string | Diameter qualifier flag |
| `span` | float | Span in meters |
| `span_flag` | string | Span qualifier flag |
| `shape` | string | Physical shape description |
| `odate` | string | Orbit date |
| `perigee` | float | Perigee in km |
| `pf` | string | Perigee qualifier flag |
| `apogee` | float | Apogee in km |
| `af` | string | Apogee qualifier flag |
| `inc` | float | Inclination in degrees |
| `if_flag` | string | Inclination qualifier flag |
| `op_orbit` | string | Operational orbit type |
| `oqual` | string | Orbit quality flag |
| `alt_names` | string | Alternative names/designations |

### `planetary_landings` -- {len(landers):,} landings

Every lunar and planetary landing or impact, including controlled and uncontrolled surface contact.

| Column | Type | Description |
|--------|------|-------------|
| `jcat` | string | GCAT deep space catalog ID |
| `piece` | string | Launch piece designation |
| `name` | string | Object name |
| `owner` | string | Owner organization |
| `state` | string | Country/state code |
| `world` | string | Target world (Luna, Mars, Venus, Titan, etc.) |
| `lon` | float | Landing longitude (degrees) |
| `lat` | float | Landing latitude (degrees) |
| `ltype` | string | Landing type (L=landing, I=impact, LA=landing attempt, etc.) |
| `status` | string | Outcome status (L=landed, I=impact, etc.) |
| `launch_date` | string | Launch date |
| `land_date` | string | Landing/impact date |
| `off_date` | string | End-of-mission date |
| `dur` | float | Surface duration in days |
| `lsite` | string | Landing site name |
| `comment` | string | Mission notes |

## Quick stats

- **{len(deep):,}** deep space objects from **{n_deep_states}** countries/entities
- **{n_dests}** distinct destinations
- **{len(landers):,}** planetary landings on **{n_lander_worlds}** worlds
- **{n_landings}** successful landings, **{n_impacts}** impacts
- Landings by world: {', '.join(f'{w} ({c})' for w, c in world_counts.head(6).items())}
- International coverage: US, Soviet Union, China, Japan, ESA, India, and more

## Usage

```python
from datasets import load_dataset

deep = load_dataset("juliensimon/gcat-deep-space", "deep_space_objects", split="train")
landings = load_dataset("juliensimon/gcat-deep-space", "planetary_landings", split="train")

ddf = deep.to_pandas()

# Spacecraft by destination
print(ddf["dest"].value_counts().head(10))

# Payloads only (exclude rocket bodies and components)
payloads = ddf[ddf["type"].str.startswith("P", na=False)]
print(f"{{len(payloads)}} payload objects")

# Planetary landings by world
ldf = landings.to_pandas()
print(ldf["world"].value_counts())

# Successful lunar landings with coordinates
lunar = ldf[(ldf["world"] == "Luna") & (ldf["status"] == "L")]
print(f"{{len(lunar)}} successful lunar landings")
print(lunar[["name", "state", "land_date", "lon", "lat", "dur"]].head(10))

# Mars landings
mars = ldf[ldf["world"] == "Mars"]
print(f"{{len(mars)}} Mars landings/impacts")
```

## Data source

[GCAT](https://planet4589.org/space/gcat/) (General Catalog of Artificial Space Objects)
by Jonathan McDowell, Harvard-Smithsonian Center for Astrophysics. GCAT is the most
comprehensive public catalog of space objects, widely used in the spaceflight research
community.

## Update schedule

Static dataset -- rebuilt manually when GCAT is updated (approximately monthly).

## Related datasets

- [space-missions](https://huggingface.co/datasets/juliensimon/space-missions) -- Space missions from Wikidata
- [spacecraft](https://huggingface.co/datasets/juliensimon/spacecraft) -- Spacecraft catalog from Wikidata
- [gcat-satellite-catalog](https://huggingface.co/datasets/juliensimon/gcat-satellite-catalog) -- GCAT orbital satellite catalog
- [deep-space-probes](https://huggingface.co/datasets/juliensimon/deep-space-probes) -- Deep space probe trajectories

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/gcat-deep-space) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{gcat_deep_space,
  author = {{Simon, Julien}},
  title = {{GCAT Deep Space Objects and Planetary Landings}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/gcat-deep-space}},
  note = {{Based on GCAT by Jonathan McDowell, Harvard-Smithsonian Center for Astrophysics}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = (f"Update GCAT deep space: {len(deep):,} objects, "
                      f"{len(landers):,} landings")
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp_dir), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={total_rows}\n")
    print(f"Done. {total_rows:,} total rows.")


if __name__ == "__main__":
    main()
