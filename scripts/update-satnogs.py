#!/usr/bin/env python3
"""Fetch SatNOGS satellite transmitter database and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

from dataset_images import banner_markdown, download_banner
from validate import check_dataset


HF_REPO = "juliensimon/satnogs-transmitters"
API_URL = "https://db.satnogs.org/api/transmitters/"


def main():
    print("Fetching SatNOGS transmitter database...")
    resp = requests.get(API_URL, timeout=60)
    resp.raise_for_status()

    df = pd.DataFrame(resp.json())
    print(f"  {len(df):,} transmitters")

    # Rename columns
    df = df.rename(columns={
        "norad_cat_id": "norad_id",
        "uplink_low": "uplink_low_hz",
        "uplink_high": "uplink_high_hz",
        "downlink_low": "downlink_low_hz",
        "downlink_high": "downlink_high_hz",
    })

    # Convert alive to boolean
    if "alive" in df.columns:
        df["alive"] = df["alive"].astype(bool)

    # Convert frequency columns to numeric
    for col in ["uplink_low_hz", "uplink_high_hz", "downlink_low_hz",
                "downlink_high_hz", "uplink_drift", "downlink_drift", "baud"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Derived: downlink in MHz for easier querying
    if "downlink_low_hz" in df.columns:
        df["downlink_mhz"] = (df["downlink_low_hz"] / 1e6).round(4)

    # Clean string columns
    for col in ["uuid", "description", "type", "mode", "status", "citation"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
            )

    check_dataset(df, "satnogs", min_rows=3000,
        expected_columns=["norad_id", "downlink_low_hz", "mode", "alive"],
        critical_columns=["norad_id", "downlink_low_hz"])

    # Stats for README
    n_total = len(df)
    n_alive = int(df["alive"].sum()) if "alive" in df.columns else 0
    n_modes = int(df["mode"].nunique()) if "mode" in df.columns else 0
    top_modes = df["mode"].value_counts().head(5) if "mode" in df.columns else pd.Series()
    top_modes_str = ", ".join(f"{m} ({c:,})" for m, c in top_modes.items())

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "satnogs_transmitters.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        banner_file = download_banner("satnogs", tmp)
        banner_md = banner_markdown("satnogs", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "SatNOGS Satellite Transmitter Database"
language:
  - en
description: "Crowdsourced database of satellite radio transmitters from the SatNOGS network (Libre Space Foundation). Updated weekly."
task_categories:
  - tabular-classification
tags:
  - space
  - satellite
  - radio
  - transmitter
  - satnogs
  - frequency
  - amateur-radio
  - open-data
  - tabular-data
  - parquet
size_categories:
  - 1K<n<10K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/satnogs_transmitters.parquet
    default: true
---

# SatNOGS Satellite Transmitter Database
{banner_md}
*Part of the [Orbital Mechanics Datasets](https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994) collection on Hugging Face.*

![Update SatNOGS](https://github.com/juliensimon/space-datasets/actions/workflows/update-satnogs.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.satnogs&label=updated&color=brightgreen)

Crowdsourced database of satellite radio transmitters from the SatNOGS network,
maintained by the Libre Space Foundation. Currently **{n_total:,}** transmitter entries
({n_alive:,} active) across {n_modes} transmission modes.

## Dataset description

SatNOGS (Satellite Networked Open Ground Station) is an open-source project that
maintains a comprehensive database of satellite transmitters, including uplink and
downlink frequencies, modulation modes, baud rates, and operational status. The data
is crowdsourced from a global network of ground station operators and is freely available.

The SatNOGS network represents one of the most ambitious citizen science projects in space operations. Hundreds of volunteer-operated ground stations around the world automatically schedule satellite passes, record RF signals, and upload observations to a central database. This distributed approach provides something no single ground station can: near-continuous coverage of satellites in low Earth orbit, capturing telemetry and beacon transmissions that would otherwise go unrecorded. The transmitter database is the curated knowledge base that makes this possible, documenting the exact frequencies, modulation schemes, and data rates needed to decode each satellite's signals.

The database spans the full radio spectrum used by satellites, from VHF (around 145 MHz, used by many amateur and CubeSat missions) through UHF (435 MHz, the most common amateur satellite band) to S-band (2.4 GHz) and beyond. Modulation modes range from simple FM voice and CW (Morse code) beacons to digital modes like BPSK, AFSK, GMSK, and LoRa used by modern small satellites. The baud rate field indicates data throughput capability, from slow 1200-baud packet radio to high-speed downlinks at 9600 baud and above. Each transmitter entry is linked to its parent satellite via NORAD ID, enabling cross-referencing with orbital elements for pass prediction.

This dataset is essential for amateur radio satellite operators planning contacts, university teams commissioning new CubeSat missions, RF spectrum managers identifying potential interference sources, and researchers studying the growing congestion of satellite frequency bands. The alive/status fields provide a real-time view of which satellites are still transmitting, often more current than official status databases.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `uuid` | string | SatNOGS DB unique transmitter identifier (UUID v4); stable primary key for this record |
| `description` | string | Human-readable label for the transmitter (e.g. "NOAA 15 APT", "ISS FM Voice"); null for unlabeled entries |
| `alive` | bool | True if the transmitter is known to be currently active; False if confirmed dead; based on community-verified observations |
| `type` | string | Transmitter functional type (e.g. "Transmitter" for downlink-only, "Transceiver" for uplink+downlink, "Transponder" for linear/inverting) |
| `uplink_low_hz` | float64 | Lower bound of the uplink (ground-to-satellite) frequency range in Hz; null for downlink-only transmitters |
| `uplink_high_hz` | float64 | Upper bound of the uplink frequency range in Hz; equals uplink_low_hz for single-frequency uplinks; null for downlink-only |
| `downlink_low_hz` | float64 | Lower bound of the downlink (satellite-to-ground) frequency range in Hz; primary frequency for fixed-frequency beacons |
| `downlink_high_hz` | float64 | Upper bound of the downlink frequency range in Hz; equals downlink_low_hz for fixed-frequency transmitters; null for beacon-only |
| `downlink_mhz` | float64 | Downlink low frequency in MHz (derived: downlink_low_hz / 1e6); useful for band filtering (VHF: 30–300 MHz, UHF: 300–3000 MHz, S-band: 2000–4000 MHz) |
| `mode` | string | RF modulation and encoding scheme (e.g. "FM" = frequency modulation voice/AFSK, "BPSK" = binary phase-shift keying telemetry, "CW" = Morse code beacon, "AFSK" = audio FSK, "GFSK" = Gaussian FSK); null if unspecified |
| `baud` | float64 | Symbol/bit rate in baud (symbols per second); range ~50 baud (CW) to 9600+ baud (high-rate telemetry); null if not applicable or unspecified |
| `norad_id` | int | NORAD Space Surveillance Network catalog number of the parent satellite; join key with TLE and SATCAT datasets |
| `status` | string | SatNOGS DB curation status: "active" (confirmed working), "inactive" (confirmed not transmitting), "unknown" (unverified) |

## Quick stats

- **{n_total:,}** transmitter entries
- **{n_alive:,}** currently active
- **{n_modes}** transmission modes
- Top modes: {top_modes_str}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/satnogs-transmitters", split="train")
df = ds.to_pandas()

# Active transmitters
active = df[df["alive"] == True]
print(f"{{len(active):,}} active transmitters")

# UHF band (300-3000 MHz)
uhf = df[(df["downlink_mhz"] >= 300) & (df["downlink_mhz"] <= 3000)]
print(f"{{len(uhf):,}} UHF transmitters")

# Transmitters per NORAD ID
sats = df.groupby("norad_id").size().sort_values(ascending=False)
print(f"{{len(sats):,}} unique satellites")
```

## Data source

[SatNOGS DB](https://db.satnogs.org/) by the [Libre Space Foundation](https://libre.space/).
Data is crowdsourced from the global SatNOGS ground station network.

## Update schedule

Weekly (Monday at 18:00 UTC) via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [space-track-satcat](https://huggingface.co/datasets/juliensimon/space-track-satcat) -- NORAD Satellite Catalog
- [ucs-satellite-database](https://huggingface.co/datasets/juliensimon/ucs-satellite-database) -- UCS Satellite Database

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/satnogs-transmitters) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{satnogs_transmitters,
  author = {{Simon, Julien}},
  title = {{SatNOGS Satellite Transmitter Database}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/satnogs-transmitters}},
  note = {{Based on SatNOGS DB by Libre Space Foundation}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update SatNOGS transmitters: {n_total:,} entries"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={len(df)}\n")
    print("Done.")


if __name__ == "__main__":
    main()
