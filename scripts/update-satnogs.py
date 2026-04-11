#!/usr/bin/env python3
"""Fetch SatNOGS satellite transmitter database and upload to HF.

Source: SatNOGS DB API (Libre Space Foundation)
https://db.satnogs.org/api/transmitters/
"""

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

HF_REPO = "juliensimon/satnogs-transmitters"
API_URL = "https://db.satnogs.org/api/transmitters/"

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "uuid": "SatNOGS DB unique transmitter identifier (UUID v4); stable primary key for this record",
    "description": "Human-readable label for the transmitter (e.g. 'NOAA 15 APT', 'ISS FM Voice'); null for unlabeled entries",
    "alive": "True if the transmitter is known to be currently active; False if confirmed dead; based on community-verified observations",
    "type": "Transmitter functional type (e.g. 'Transmitter' for downlink-only, 'Transceiver' for uplink+downlink, 'Transponder' for linear/inverting)",
    "uplink_low_hz": "Lower bound of the uplink (ground-to-satellite) frequency range in Hz; null for downlink-only transmitters",
    "uplink_high_hz": "Upper bound of the uplink frequency range in Hz; equals uplink_low_hz for single-frequency uplinks; null for downlink-only",
    "uplink_drift": "Uplink frequency drift in Hz/s due to Doppler or oscillator instability; null for most entries",
    "downlink_low_hz": "Lower bound of the downlink (satellite-to-ground) frequency range in Hz; primary frequency for fixed-frequency beacons",
    "downlink_high_hz": "Upper bound of the downlink frequency range in Hz; equals downlink_low_hz for fixed-frequency transmitters; null for beacon-only",
    "downlink_drift": "Downlink frequency drift in Hz/s due to Doppler or oscillator instability; null for most entries",
    "downlink_mhz": "Downlink low frequency in MHz (derived: downlink_low_hz / 1e6); useful for band filtering (VHF: 30-300, UHF: 300-3000, S-band: 2000-4000 MHz)",
    "mode": "RF modulation and encoding scheme (e.g. 'FM', 'BPSK', 'CW', 'AFSK', 'GFSK', 'LoRa'); null if unspecified",
    "baud": "Symbol/bit rate in baud (symbols per second); range ~50 baud (CW) to 9600+ baud (high-rate telemetry); null if not applicable",
    "norad_id": "NORAD Space Surveillance Network catalog number of the parent satellite; join key with TLE and SATCAT datasets",
    "status": "SatNOGS DB curation status: 'active' (confirmed working), 'inactive' (confirmed not transmitting), 'unknown' (unverified)",
    "citation": "Free-text attribution or reference for the transmitter entry; null for most community-contributed entries",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Crowdsourced database of satellite radio transmitters from the SatNOGS network, \
maintained by the Libre Space Foundation.

SatNOGS (Satellite Networked Open Ground Station) is an open-source project that \
maintains a comprehensive database of satellite transmitters, including uplink and \
downlink frequencies, modulation modes, baud rates, and operational status. The data \
is crowdsourced from a global network of ground station operators.

The SatNOGS network represents one of the most ambitious citizen science projects in \
space operations. Hundreds of volunteer-operated ground stations around the world \
automatically schedule satellite passes, record RF signals, and upload observations to \
a central database. The transmitter database documents the exact frequencies, modulation \
schemes, and data rates needed to decode each satellite's signals.

The database spans the full radio spectrum used by satellites, from VHF (around 145 MHz) \
through UHF (435 MHz, the most common amateur satellite band) to S-band (2.4 GHz) and \
beyond. Each transmitter entry is linked to its parent satellite via NORAD ID, enabling \
cross-referencing with orbital elements for pass prediction.
"""


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

    # Derived: downlink in MHz for easier querying
    if "downlink_low_hz" in df.columns:
        df["downlink_mhz"] = (pd.to_numeric(df["downlink_low_hz"], errors="coerce") / 1e6).round(4)

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_alive = int(df["alive"].sum()) if "alive" in df.columns else 0
    n_modes = int(df["mode"].nunique()) if "mode" in df.columns else 0
    n_sats = int(df["norad_id"].nunique()) if "norad_id" in df.columns else 0

    top_modes = df["mode"].value_counts().head(5) if "mode" in df.columns else pd.Series()
    top_modes_str = ", ".join(f"{m} ({c:,})" for m, c in top_modes.items())

    quick_stats = f"""\
- **{n_total:,}** transmitter entries
- **{n_alive:,}** currently active
- **{n_sats:,}** unique satellites
- **{n_modes}** transmission modes
- Top modes: {top_modes_str}"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/satnogs-transmitters", split="train")
df = ds.to_pandas()

# Active transmitters
active = df[df["alive"] == True]
print(f"{len(active):,} active transmitters")

# UHF band (300-3000 MHz)
uhf = df[(df["downlink_mhz"] >= 300) & (df["downlink_mhz"] <= 3000)]

# Frequency band distribution
import matplotlib.pyplot as plt
import numpy as np
freqs = df["downlink_mhz"].dropna()
plt.hist(freqs[freqs < 3000], bins=100)
plt.xlabel("Downlink Frequency (MHz)")
plt.ylabel("Count")
plt.title("Satellite Transmitter Frequency Distribution")
plt.show()

# Transmitters per satellite
sats = df.groupby("norad_id").size().sort_values(ascending=False)
print(f"{len(sats):,} unique satellites")
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="SatNOGS Satellite Transmitter Database",
        description=DESCRIPTION,
        tags=["space", "satellite", "radio", "transmitter", "satnogs",
              "frequency", "amateur-radio", "open-data", "tabular-data", "parquet"],
        source_url="https://db.satnogs.org/",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994",
        banner={
            "url": "https://images-assets.nasa.gov/image/iss071e439624/iss071e439624~medium.jpg",
            "alt": "An orbital sunrise illuminates the Earth's atmosphere, seen from the ISS",
            "credit": "NASA",
        },
        related_datasets=[
            "juliensimon/space-track-satcat",
            "juliensimon/ucs-satellite-database",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "uplink_low_hz", "uplink_high_hz", "uplink_drift",
                "downlink_low_hz", "downlink_high_hz", "downlink_drift",
                "downlink_mhz", "baud",
            ],
            strings=["uuid", "description", "type", "mode", "status", "citation"],
        )
        p.publish(
            df,
            filename="satnogs_transmitters.parquet",
            min_rows=3000,
            expected_columns=["norad_id", "downlink_low_hz", "mode", "alive"],
            critical_columns=["norad_id", "downlink_low_hz"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update SatNOGS transmitters: {n_total:,} entries",
        )
    print("Done.")


if __name__ == "__main__":
    main()
