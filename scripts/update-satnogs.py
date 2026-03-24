#!/usr/bin/env python3
"""Fetch SatNOGS satellite transmitter database and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

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
size_categories:
  - 1K<n<10K
---

# SatNOGS Satellite Transmitter Database

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

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `uuid` | string | Unique transmitter identifier |
| `description` | string | Transmitter description |
| `alive` | bool | Whether the transmitter is currently active |
| `type` | string | Transmitter type |
| `uplink_low_hz` | float64 | Uplink low frequency (Hz) |
| `uplink_high_hz` | float64 | Uplink high frequency (Hz) |
| `downlink_low_hz` | float64 | Downlink low frequency (Hz) |
| `downlink_high_hz` | float64 | Downlink high frequency (Hz) |
| `downlink_mhz` | float64 | Downlink low frequency (MHz, derived) |
| `mode` | string | Transmission mode (e.g. FM, AFSK, BPSK) |
| `baud` | float64 | Baud rate |
| `norad_id` | int | NORAD catalog ID |
| `status` | string | Operational status |

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
