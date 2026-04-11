#!/usr/bin/env python3
"""Fetch NASA PDS planetary mission catalog and upload to HF.

Creates three configs in one dataset:
  - missions: investigations (missions, field campaigns, etc.)
  - spacecraft: instrument hosts (spacecraft, landers, rovers, etc.)
  - instruments: scientific instruments with host and type info

Source: NASA Planetary Data System (PDS) Search API -- no authentication needed.
"""

import time

import pandas as pd
import requests

from hf_dataset_utils import Pipeline
from hf_dataset_utils.banner import banner_markdown as render_banner
from hf_dataset_utils.banner import download_banner
from hf_dataset_utils.github import emit_output
from hf_dataset_utils.readme import _size_category, _citation_bibtex
from hf_dataset_utils.upload import upload_to_hf, write_parquet
from hf_dataset_utils.validation import check_dataset

PDS_API = "https://pds.nasa.gov/api/search/1/products"
HF_REPO = "juliensimon/pds-planetary-missions"
HEADERS = {"Accept": "application/json"}
TIMEOUT = 60

# ── Column descriptions ─────────────────────────────────────────────
MISSION_DESCRIPTIONS = {
    "lid": "PDS Logical Identifier (unique key); stable URN-format reference used across the entire PDS archive to link data products to their originating investigation",
    "short_name": "Short machine-friendly name extracted from the LID (e.g. 'galileo', 'cassini-huygens'); useful for joining and filtering",
    "name": "Full human-readable mission/investigation name (e.g. 'GALILEO', 'MARS EXPLORATION ROVER') as registered in the PDS context catalog",
    "type": "Investigation type: 'Mission' (spacecraft-based), 'Field Campaign' (ground-based), 'Observing System' (telescope program), 'Individual Investigation', or other PDS classification",
    "start_date": "Mission start date (UTC); marks the beginning of the investigation period as defined by the PDS registrar; null for missions without a defined start",
    "stop_date": "Mission stop date (UTC); null for ongoing missions or those without a defined end date in the PDS catalog",
    "description": "Free-text description of the investigation from the PDS context product; varies in length and detail; null for entries without descriptions",
    "target_refs": "Semicolon-separated target body identifiers (e.g. 'planet.mars; satellite.phobos'); extracted from PDS target references; can be split and cross-referenced with spacecraft and instrument configs",
    "instrument_refs": "Semicolon-separated instrument identifiers linked to this mission; can be matched against the instruments config for full instrument details",
    "spacecraft_refs": "Semicolon-separated spacecraft/instrument-host identifiers; can be matched against the spacecraft config for host details",
    "num_targets": "Count of distinct target bodies associated with this mission; ranges from 1 (single-body missions) to dozens (survey missions)",
    "num_instruments": "Count of distinct instruments associated with this mission across all spacecraft",
    "num_spacecraft": "Count of distinct spacecraft or instrument hosts involved in this mission (e.g. Cassini-Huygens has 2: orbiter + probe)",
}

SPACECRAFT_DESCRIPTIONS = {
    "lid": "PDS Logical Identifier (unique key) for the instrument host; stable URN used to link spacecraft to missions and instruments across the PDS archive",
    "short_name": "Short machine-friendly name extracted from the LID (e.g. 'co' for Cassini orbiter, 'msl' for Mars Science Laboratory); used as prefix in instrument LIDs",
    "name": "Full human-readable spacecraft/host name (e.g. 'CASSINI ORBITER', 'MARS SCIENCE LABORATORY') as registered in PDS",
    "type": "Host type: 'Spacecraft' (orbiter/flyby), 'Rover' (surface mobile), 'Lander' (surface stationary), 'Earth Based' (ground station/telescope), or other PDS classification",
    "description": "Free-text description of the spacecraft or instrument host from the PDS context product; null for entries without descriptions",
    "investigation_refs": "Semicolon-separated mission identifiers that this spacecraft participated in; can be cross-referenced with the missions config",
    "instrument_refs": "Semicolon-separated instrument identifiers carried by this host; can be matched against the instruments config",
    "target_refs": "Semicolon-separated target body identifiers observed by this spacecraft",
    "num_investigations": "Count of distinct missions or investigations this spacecraft participated in",
    "num_instruments": "Count of distinct scientific instruments carried by or associated with this host",
    "num_targets": "Count of distinct target bodies observed by this spacecraft",
}

INSTRUMENT_DESCRIPTIONS = {
    "lid": "PDS Logical Identifier (unique key) for the instrument; format includes the host short name (e.g. 'urn:nasa:pds:context:instrument:go.epd' for Galileo EPD)",
    "name": "Full human-readable instrument name (e.g. 'ALPHA PARTICLE X-RAY SPECTROMETER', 'PANORAMIC CAMERA') as registered in PDS",
    "type": "Instrument type classification: 'Imager' (camera), 'Spectrometer' (spectral analyzer), 'Radiometer', 'Magnetometer', 'Altimeter', 'Dust Detector', 'Accelerometer', or other PDS-defined type",
    "host_short_name": "Short name of the host spacecraft extracted from the instrument LID (e.g. 'go' for Galileo, 'msl' for MSL Curiosity); foreign key to spacecraft config",
    "description": "Free-text description of the instrument from the PDS context product; includes measurement capabilities, wavelength ranges, and scientific objectives; null for entries without descriptions",
    "investigation_refs": "Semicolon-separated mission identifiers that this instrument contributed data to; can be cross-referenced with the missions config",
    "num_investigations": "Count of distinct missions or investigations this instrument was used in; some instruments serve multiple missions (e.g. ground-based telescope instruments)",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Comprehensive catalog of planetary science investigations (missions), instrument hosts \
(spacecraft), and scientific instruments from the NASA Planetary Data System (PDS). The PDS \
is the official archive for all NASA planetary science data, established in 1989 to ensure \
long-term preservation and accessibility.

This dataset spans the entire history of NASA's planetary exploration program, from early \
flyby missions like Mariner and Pioneer through flagship orbiters (Cassini, Juno), landers \
and rovers (Viking, Curiosity, Perseverance), sample return missions (OSIRIS-REx, Stardust), \
and ground-based observing campaigns. The linked structure of missions, spacecraft, and \
instruments provides a natural knowledge graph for exploring planetary exploration history.

Each entity includes its PDS Logical Identifier (LID), which serves as a stable cross-reference \
key. Target bodies, instruments, and spacecraft are linked via semicolon-separated reference \
columns that can be split and joined across the three configs.
"""


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

        target_ids = [_strip_urn(t["id"], "target") for t in item.get("targets", [])]

        osc = item.get("observing_system_components", [])
        instrument_refs = []
        spacecraft_refs = []
        for comp in osc:
            cid = comp["id"]
            if ":instrument_host:" in cid:
                spacecraft_refs.append(_strip_urn(cid, "instrument_host"))
            elif ":instrument:" in cid:
                instrument_refs.append(_strip_urn(cid, "instrument"))

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

    for col in ["start_date", "stop_date"]:
        df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)

    for col in ["num_targets", "num_instruments", "num_spacecraft"]:
        df[col] = df[col].astype("int32")

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

        inv_refs = [_strip_urn(inv["id"], "investigation")
                    for inv in item.get("investigations", [])]

        osc = item.get("observing_system_components", [])
        instrument_refs = [_strip_urn(c["id"], "instrument")
                          for c in osc if ":instrument:" in c["id"]]

        target_ids = [_strip_urn(t["id"], "target") for t in item.get("targets", [])]

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

        lid_suffix = lid.split(":")[-1] if lid else ""
        host_short = lid_suffix.split(".")[0] if "." in lid_suffix else None

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
    # ── Fetch all three entity types ─────────────────────────────────
    missions = build_missions()
    time.sleep(1)
    spacecraft = build_spacecraft()
    time.sleep(1)
    instruments = build_instruments()

    n_missions = len(missions)
    n_spacecraft = len(spacecraft)
    n_instruments = len(instruments)
    total_rows = n_missions + n_spacecraft + n_instruments
    print(f"\n  {n_missions} missions, {n_spacecraft} spacecraft, {n_instruments} instruments")

    # ── Validate ─────────────────────────────────────────────────────
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

    # ── Compute stats ────────────────────────────────────────────────
    mission_types = missions["type"].value_counts()
    mission_types_str = ", ".join(f"{t} ({c})" for t, c in mission_types.head(5).items())

    sc_types = spacecraft["type"].value_counts()
    sc_types_str = ", ".join(f"{t} ({c})" for t, c in sc_types.head(5).items())

    inst_types = instruments["type"].value_counts()
    inst_types_str = ", ".join(f"{t} ({c})" for t, c in inst_types.head(5).items())

    # ── Schema helper ────────────────────────────────────────────────
    def _schema(descs):
        lines = ["| Column | Type | Description |", "|--------|------|-------------|"]
        for col, desc in descs.items():
            lines.append(f"| `{col}` | -- | {desc} |")
        return "\n".join(lines)

    # ── Build multi-config dataset using Pipeline context ────────────
    with Pipeline(
        repo=HF_REPO,
        pretty_name="NASA PDS Planetary Missions Catalog",
        description="",  # custom README below
        tags=[],
        source_url="https://pds.nasa.gov/api/search/1/",
        collection_url="https://huggingface.co/collections/juliensimon/space-probe-and-mission-datasets-69c3fe82d410a42b1e313167",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA14111/PIA14111~small.jpg",
            "alt": "Voyager spacecraft artist concept",
            "credit": "NASA/JPL-Caltech",
        },
    ) as p:
        # Write all 3 parquet configs
        write_parquet(missions, p.data_dir / "missions.parquet")
        write_parquet(spacecraft, p.data_dir / "spacecraft.parquet")
        write_parquet(instruments, p.data_dir / "instruments.parquet")

        # Banner
        banner_file = download_banner(p.banner["url"], p.tmp_dir)
        banner_md = render_banner(
            p.banner["alt"], p.banner["credit"],
            filename=banner_file,
        ) if banner_file else ""

        readme = f"""---
license: cc-by-4.0
pretty_name: "NASA PDS Planetary Missions Catalog"
language:
  - en
description: "NASA PDS planetary mission catalog -- {n_missions} missions, {n_spacecraft} spacecraft, and {n_instruments} instruments with target bodies, dates, and cross-references."
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
  - {_size_category(max(n_missions, n_spacecraft, n_instruments))}
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
{banner_md}
*Part of a [dataset collection](https://huggingface.co/collections/juliensimon/space-probe-and-mission-datasets-69c3fe82d410a42b1e313167) on Hugging Face.*

## Dataset description

{DESCRIPTION}

## Configs

This dataset has three configs (tables):

### `missions` ({n_missions} rows)

Planetary science investigations including orbital missions, flybys, landers, rovers, field campaigns, and observing programs.

{_schema(MISSION_DESCRIPTIONS)}

### `spacecraft` ({n_spacecraft} rows)

Instrument hosts: spacecraft, landers, rovers, ground stations, telescopes, and other platforms.

{_schema(SPACECRAFT_DESCRIPTIONS)}

### `instruments` ({n_instruments} rows)

Scientific instruments across all missions and platforms.

{_schema(INSTRUMENT_DESCRIPTIONS)}

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

# Spacecraft with the most instruments
import matplotlib.pyplot as plt
top = spacecraft.nlargest(15, "num_instruments")
plt.barh(top["name"], top["num_instruments"])
plt.xlabel("Number of Instruments")
plt.title("PDS Spacecraft with Most Instruments")
plt.tight_layout()
plt.show()

# Instruments on the Cassini spacecraft
cassini_inst = instruments[instruments["host_short_name"] == "co"]
print(cassini_inst[["name", "type"]].to_string())
```

## Data source

[NASA Planetary Data System (PDS) Search API](https://pds.nasa.gov/api/search/1/) -- the official NASA archive for planetary science data. The context catalog is maintained by PDS discipline nodes and updated as new missions and instruments are registered.

## Related datasets

- [juliensimon/deep-space-probes](https://huggingface.co/datasets/juliensimon/deep-space-probes)
- [juliensimon/cassini-saturn-observations](https://huggingface.co/datasets/juliensimon/cassini-saturn-observations)
- [juliensimon/esa-mars-express-observations](https://huggingface.co/datasets/juliensimon/esa-mars-express-observations)
- [juliensimon/nasa-eva-chronology](https://huggingface.co/datasets/juliensimon/nasa-eva-chronology)

## Citation

{_citation_bibtex(HF_REPO, "NASA PDS Planetary Missions Catalog")}

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
"""
        (p.tmp_dir / "README.md").write_text(readme)

        # Upload
        upload_to_hf(
            HF_REPO, p.tmp_dir,
            f"Update PDS missions catalog: {n_missions} missions, "
            f"{n_spacecraft} spacecraft, {n_instruments} instruments",
        )

    emit_output(rows=total_rows)
    print("Done.")


if __name__ == "__main__":
    main()
