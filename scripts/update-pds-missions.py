#!/usr/bin/env python3
"""Fetch NASA PDS planetary mission catalog and upload to HF.

Creates three configs in one dataset:
  - missions: investigations (missions, field campaigns, etc.)
  - spacecraft: instrument hosts (spacecraft, landers, rovers, etc.)
  - instruments: scientific instruments with host and type info

Source: NASA Planetary Data System (PDS) Search API — no authentication needed.
"""

import os
import subprocess
import tempfile
import time
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset

PDS_API = "https://pds.nasa.gov/api/search/1/products"
HF_REPO = "juliensimon/pds-planetary-missions"
HEADERS = {"Accept": "application/json"}
TIMEOUT = 60


def _strip_urn(urn: str, prefix: str) -> str:
    """Strip PDS URN prefix, e.g. urn:nasa:pds:context:target:planet.mars -> planet.mars."""
    full = f"urn:nasa:pds:context:{prefix}:"
    if urn.startswith(full):
        return urn[len(full):]
    return urn


def _join_list(items: list) -> str | None:
    """Join a list of strings with semicolons, or return None if empty."""
    cleaned = [s for s in items if s and s != "null"]
    return "; ".join(cleaned) if cleaned else None


def fetch_pds(query: str, fields: str) -> list[dict]:
    """Fetch all products matching a PDS search query."""
    params = {"q": query, "limit": 2000, "fields": fields}
    resp = requests.get(PDS_API, params=params, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    print(f"  {data['summary']['hits']} hits")
    return data["data"]


def build_missions() -> pd.DataFrame:
    """Fetch investigations (missions) from PDS."""
    print("Fetching investigations (missions)...")
    items = fetch_pds(
        'lid like "urn:nasa:pds:context:investigation:*"',
        "lid,title,pds:Investigation/pds:type,pds:Investigation/pds:start_date,"
        "pds:Investigation/pds:stop_date,pds:Investigation/pds:description,"
        "pds:Internal_Reference/pds:lid_reference",
    )

    rows = []
    for item in items:
        props = item["properties"]
        lid = props.get("lid", [""])[0]

        # Extract target refs from the targets array
        target_ids = [_strip_urn(t["id"], "target") for t in item.get("targets", [])]

        # Extract instrument and spacecraft refs from observing_system_components
        osc = item.get("observing_system_components", [])
        instrument_refs = []
        spacecraft_refs = []
        for comp in osc:
            cid = comp["id"]
            if ":instrument_host:" in cid:
                spacecraft_refs.append(_strip_urn(cid, "instrument_host"))
            elif ":instrument:" in cid:
                instrument_refs.append(_strip_urn(cid, "instrument"))

        # Extract short name from LID: investigation:mission.galileo -> galileo
        short_name = lid.split(":")[-1] if lid else ""
        if "." in short_name:
            short_name = short_name.split(".", 1)[1]

        desc_raw = props.get("pds:Investigation.pds:description", [""])[0]
        description = desc_raw if desc_raw and desc_raw != "null" else None

        rows.append({
            "lid": lid,
            "short_name": short_name,
            "name": item.get("title", ""),
            "type": props.get("pds:Investigation.pds:type", [""])[0] or None,
            "start_date": props.get("pds:Investigation.pds:start_date", [""])[0] or None,
            "stop_date": props.get("pds:Investigation.pds:stop_date", [""])[0] or None,
            "description": description,
            "target_refs": _join_list(target_ids),
            "instrument_refs": _join_list(instrument_refs),
            "spacecraft_refs": _join_list(spacecraft_refs),
            "num_targets": len(target_ids),
            "num_instruments": len(instrument_refs),
            "num_spacecraft": len(spacecraft_refs),
        })

    df = pd.DataFrame(rows)

    # Parse dates
    for col in ["start_date", "stop_date"]:
        df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)

    # Type coercion
    for col in ["num_targets", "num_instruments", "num_spacecraft"]:
        df[col] = df[col].astype("int32")

    # Sort by name
    df = df.sort_values("name", key=lambda s: s.str.lower()).reset_index(drop=True)

    return df


def build_spacecraft() -> pd.DataFrame:
    """Fetch instrument hosts (spacecraft) from PDS."""
    print("Fetching instrument hosts (spacecraft)...")
    items = fetch_pds(
        'lid like "urn:nasa:pds:context:instrument_host:*"',
        "lid,title,pds:Instrument_Host/pds:type,pds:Instrument_Host/pds:description,"
        "pds:Internal_Reference/pds:lid_reference",
    )

    rows = []
    for item in items:
        props = item["properties"]
        lid = props.get("lid", [""])[0]

        # Extract investigation refs
        inv_refs = [_strip_urn(inv["id"], "investigation")
                    for inv in item.get("investigations", [])]

        # Extract instrument refs from observing_system_components
        osc = item.get("observing_system_components", [])
        instrument_refs = [_strip_urn(c["id"], "instrument")
                          for c in osc if ":instrument:" in c["id"]]

        # Extract target refs
        target_ids = [_strip_urn(t["id"], "target") for t in item.get("targets", [])]

        # Short name from LID
        short_name = lid.split(":")[-1] if lid else ""
        if "." in short_name:
            short_name = short_name.split(".", 1)[1]

        desc_raw = props.get("pds:Instrument_Host.pds:description", [""])[0]
        description = desc_raw if desc_raw and desc_raw != "null" else None

        rows.append({
            "lid": lid,
            "short_name": short_name,
            "name": item.get("title", ""),
            "type": props.get("pds:Instrument_Host.pds:type", [""])[0] or None,
            "description": description,
            "investigation_refs": _join_list(inv_refs),
            "instrument_refs": _join_list(instrument_refs),
            "target_refs": _join_list(target_ids),
            "num_investigations": len(inv_refs),
            "num_instruments": len(instrument_refs),
            "num_targets": len(target_ids),
        })

    df = pd.DataFrame(rows)

    for col in ["num_investigations", "num_instruments", "num_targets"]:
        df[col] = df[col].astype("int32")

    df = df.sort_values("name", key=lambda s: s.str.lower()).reset_index(drop=True)

    return df


def build_instruments() -> pd.DataFrame:
    """Fetch instruments from PDS."""
    print("Fetching instruments...")
    items = fetch_pds(
        'lid like "urn:nasa:pds:context:instrument:*"',
        "lid,title,pds:Instrument/pds:type,pds:Instrument/pds:description,"
        "pds:Internal_Reference/pds:lid_reference",
    )

    rows = []
    for item in items:
        props = item["properties"]
        lid = props.get("lid", [""])[0]

        # Extract host from LID: instrument:go.epd -> go is the host
        lid_suffix = lid.split(":")[-1] if lid else ""
        host_short = lid_suffix.split(".")[0] if "." in lid_suffix else None

        # Extract investigation refs
        inv_refs = [_strip_urn(inv["id"], "investigation")
                    for inv in item.get("investigations", [])]

        desc_raw = props.get("pds:Instrument.pds:description", [""])[0]
        description = desc_raw if desc_raw and desc_raw != "null" else None

        rows.append({
            "lid": lid,
            "name": item.get("title", ""),
            "type": props.get("pds:Instrument.pds:type", [""])[0] or None,
            "host_short_name": host_short,
            "description": description,
            "investigation_refs": _join_list(inv_refs),
            "num_investigations": len(inv_refs),
        })

    df = pd.DataFrame(rows)
    df["num_investigations"] = df["num_investigations"].astype("int32")
    df = df.sort_values("name", key=lambda s: s.str.lower()).reset_index(drop=True)

    return df


def main():
    # ── Fetch all three entity types ──────────────────────────────────────
    missions = build_missions()
    time.sleep(1)
    spacecraft = build_spacecraft()
    time.sleep(1)
    instruments = build_instruments()

    n_missions = len(missions)
    n_spacecraft = len(spacecraft)
    n_instruments = len(instruments)
    print(f"\n  {n_missions} missions, {n_spacecraft} spacecraft, {n_instruments} instruments")

    # ── Validate ──────────────────────────────────────────────────────────
    check_dataset(
        missions, "pds-missions", min_rows=50,
        expected_columns=["lid", "name", "type", "start_date", "stop_date",
                          "target_refs", "instrument_refs", "spacecraft_refs"],
        critical_columns=["lid", "name"],
    )
    check_dataset(
        spacecraft, "pds-spacecraft", min_rows=50,
        expected_columns=["lid", "name", "type", "investigation_refs",
                          "instrument_refs", "target_refs"],
        critical_columns=["lid", "name"],
    )
    check_dataset(
        instruments, "pds-instruments", min_rows=200,
        expected_columns=["lid", "name", "type", "host_short_name",
                          "investigation_refs"],
        critical_columns=["lid", "name"],
    )

    # ── Compute stats for README ──────────────────────────────────────────
    mission_types = missions["type"].value_counts()
    mission_types_str = ", ".join(f"{t} ({c})" for t, c in mission_types.head(5).items())

    sc_types = spacecraft["type"].value_counts()
    sc_types_str = ", ".join(f"{t} ({c})" for t, c in sc_types.head(5).items())

    inst_types = instruments["type"].value_counts()
    inst_types_str = ", ".join(f"{t} ({c})" for t, c in inst_types.head(5).items())

    # Size category based on largest config
    max_rows = max(n_missions, n_spacecraft, n_instruments)
    if max_rows < 1000:
        size_cat = "n<1K"
    elif max_rows < 10000:
        size_cat = "1K<n<10K"
    else:
        size_cat = "10K<n<100K"

    # ── Write parquet and README ──────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        for name, df in [("missions", missions), ("spacecraft", spacecraft),
                         ("instruments", instruments)]:
            out = data_dir / f"{name}.parquet"
            df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
            size_mb = out.stat().st_size / 1024 / 1024
            print(f"  {name}: {len(df):,} rows, {size_mb:.2f} MB")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "NASA PDS Planetary Missions Catalog"
language:
  - en
description: "NASA PDS planetary mission catalog — {n_missions} missions, {n_spacecraft} spacecraft, and {n_instruments} instruments with target bodies, dates, and cross-references."
task_categories:
  - tabular-classification
tags:
  - space
  - nasa
  - planetary-science
  - missions
  - spacecraft
  - instruments
  - pds
  - open-data
  - tabular-data
  - parquet
size_categories:
  - {size_cat}
configs:
  - config_name: missions
    data_files:
      - split: train
        path: data/missions.parquet
    default: true
  - config_name: spacecraft
    data_files:
      - split: train
        path: data/spacecraft.parquet
  - config_name: instruments
    data_files:
      - split: train
        path: data/instruments.parquet
---

# NASA PDS Planetary Missions Catalog

*Part of the [Space Probes & Mission Datasets](https://huggingface.co/collections/juliensimon/space-probe-and-mission-datasets-69c3fe82d410a42b1e313167) collection on Hugging Face.*

Comprehensive catalog of **{n_missions}** planetary science investigations (missions), **{n_spacecraft}** instrument hosts (spacecraft), and **{n_instruments}** scientific instruments from the NASA Planetary Data System (PDS). Includes mission dates, target bodies, and full cross-references between missions, spacecraft, and instruments.

## Dataset description

The NASA [Planetary Data System](https://pds.nasa.gov/) is the official archive for all NASA planetary science data. Its context catalog defines every mission, spacecraft, and instrument that has contributed data to the archive. This dataset extracts those three entity types into linked tables, making it easy to explore the full landscape of planetary exploration — from Pioneer and Voyager through Perseverance and Psyche.

Each entity includes its PDS Logical Identifier (LID), which serves as a stable cross-reference key. Target bodies, instruments, and spacecraft are linked via semicolon-separated reference columns that can be split and joined across the three configs.

The Planetary Data System was established in 1989 to ensure the long-term preservation and accessibility of NASA's planetary science data. It is organized into discipline nodes — Atmospheres, Geosciences, Imaging, Plasma Interactions, Ring-Moon Systems, and Small Bodies — each responsible for archiving data from relevant instruments and missions. The context catalog captured in this dataset serves as the master registry that links every archived data product back to its originating mission, spacecraft, and instrument, forming the backbone of the PDS metadata infrastructure.

This catalog spans the entire history of NASA's planetary exploration program, from early flyby missions like Mariner and Pioneer through flagship orbiters (Cassini, Juno, Mars Reconnaissance Orbiter), landers and rovers (Viking, Phoenix, Curiosity, Perseverance), sample return missions (Stardust, OSIRIS-REx, Genesis), and ground-based observing campaigns. The mission dates, target body references, and instrument cross-links enable systematic analysis of how planetary exploration has evolved over six decades — which bodies have been studied, with what instrument types, and over what time periods. For data scientists, the linked structure of missions, spacecraft, and instruments provides a natural knowledge graph for building recommendation systems, planning future investigations, or simply navigating the vast PDS archive.

## Configs

This dataset has three configs (tables):

### `missions` ({n_missions} rows)

Planetary science investigations including orbital missions, flybys, landers, rovers, field campaigns, and observing programs.

| Column | Type | Description |
|--------|------|-------------|
| `lid` | string | PDS Logical Identifier (unique key) |
| `short_name` | string | Short machine-friendly name extracted from LID |
| `name` | string | Full mission/investigation name |
| `type` | string | Investigation type (Mission, Field Campaign, etc.) |
| `start_date` | datetime | Mission start date (UTC) |
| `stop_date` | datetime | Mission stop date (UTC) |
| `description` | string | Free-text description of the investigation |
| `target_refs` | string | Semicolon-separated target body identifiers |
| `instrument_refs` | string | Semicolon-separated instrument identifiers |
| `spacecraft_refs` | string | Semicolon-separated spacecraft identifiers |
| `num_targets` | int32 | Number of target bodies |
| `num_instruments` | int32 | Number of instruments |
| `num_spacecraft` | int32 | Number of spacecraft |

### `spacecraft` ({n_spacecraft} rows)

Instrument hosts: spacecraft, landers, rovers, ground stations, telescopes, and other platforms.

| Column | Type | Description |
|--------|------|-------------|
| `lid` | string | PDS Logical Identifier (unique key) |
| `short_name` | string | Short machine-friendly name extracted from LID |
| `name` | string | Full spacecraft/host name |
| `type` | string | Host type (Spacecraft, Rover, Lander, etc.) |
| `description` | string | Free-text description |
| `investigation_refs` | string | Semicolon-separated mission identifiers |
| `instrument_refs` | string | Semicolon-separated instrument identifiers |
| `target_refs` | string | Semicolon-separated target body identifiers |
| `num_investigations` | int32 | Number of linked missions |
| `num_instruments` | int32 | Number of instruments on this host |
| `num_targets` | int32 | Number of target bodies |

### `instruments` ({n_instruments} rows)

Scientific instruments across all missions and platforms.

| Column | Type | Description |
|--------|------|-------------|
| `lid` | string | PDS Logical Identifier (unique key) |
| `name` | string | Full instrument name |
| `type` | string | Instrument type (Imager, Spectrometer, etc.) |
| `host_short_name` | string | Short name of host spacecraft (from LID) |
| `description` | string | Free-text description |
| `investigation_refs` | string | Semicolon-separated mission identifiers |
| `num_investigations` | int32 | Number of linked missions |

## Quick stats

- **{n_missions}** investigations: {mission_types_str}
- **{n_spacecraft}** instrument hosts: {sc_types_str}
- **{n_instruments}** instruments: {inst_types_str}

## Usage

```python
from datasets import load_dataset

# Load all three configs
missions = load_dataset("juliensimon/pds-planetary-missions", "missions", split="train").to_pandas()
spacecraft = load_dataset("juliensimon/pds-planetary-missions", "spacecraft", split="train").to_pandas()
instruments = load_dataset("juliensimon/pds-planetary-missions", "instruments", split="train").to_pandas()

# All missions targeting Mars
mars = missions[missions["target_refs"].str.contains("mars", case=False, na=False)]
print(mars[["name", "type", "start_date"]].to_string())

# Instruments on the Cassini spacecraft
cassini_inst = instruments[instruments["host_short_name"] == "co"]
print(cassini_inst[["name", "type"]].to_string())

# Spacecraft with the most instruments
spacecraft.nlargest(10, "num_instruments")[["name", "type", "num_instruments"]]

# Cross-reference: find all instruments for a mission
mission_lid = missions.loc[missions["name"].str.contains("Galileo", case=False), "instrument_refs"].iloc[0]
if mission_lid:
    inst_lids = [f"urn:nasa:pds:context:instrument:{{ref}}" for ref in mission_lid.split("; ")]
    galileo_instruments = instruments[instruments["lid"].isin(inst_lids)]
```

## Data source

[NASA Planetary Data System (PDS) Search API](https://pds.nasa.gov/api/search/1/) — the official NASA archive for planetary science data. The context catalog is maintained by PDS discipline nodes and updated as new missions and instruments are registered.

## Related datasets

- [deep-space-probes](https://huggingface.co/datasets/juliensimon/deep-space-probes) — Detailed deep space probe catalog from GCAT
- [cassini-saturn-observations](https://huggingface.co/datasets/juliensimon/cassini-saturn-observations) — Cassini mission observation log
- [esa-mars-express-observations](https://huggingface.co/datasets/juliensimon/esa-mars-express-observations) — ESA Mars Express observation log
- [nasa-eva-chronology](https://huggingface.co/datasets/juliensimon/nasa-eva-chronology) — NASA EVA history

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/pds-planetary-missions) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{pds_planetary_missions,
  author = {{Simon, Julien}},
  title = {{NASA PDS Planetary Missions Catalog}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/pds-planetary-missions}},
  note = {{Based on NASA Planetary Data System (PDS) context catalog via the PDS Search API}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = (f"Update PDS missions catalog: {n_missions} missions, "
                      f"{n_spacecraft} spacecraft, {n_instruments} instruments")
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={n_missions + n_spacecraft + n_instruments}\n")
    print("Done.")


if __name__ == "__main__":
    main()
