#!/usr/bin/env python3
"""Fetch fireball/bolide data from NASA JPL CNEOS and upload to HF."""

import pandas as pd

from hf_dataset_utils import Pipeline
from jpl_api import jpl_query, jpl_fields_data_to_df

HF_REPO = "juliensimon/fireball-bolide-events"

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "datetime": "Date and time of peak brightness (UTC); derived from satellite and infrasound sensor data",
    "radiated_energy_j": "Total optical energy radiated in joules (x10^10); proportional to kinetic energy; Chelyabinsk 2013: ~5x10^14 J; null for events without optical energy estimate",
    "impact_energy_kt": "Estimated total impact energy in kilotons of TNT equivalent; Chelyabinsk ~500 kt; null for ~half of events where conversion is not available",
    "latitude": "Geographic latitude of peak brightness in decimal degrees (positive = N, negative = S); null for events where coordinates are withheld or unavailable",
    "lat_direction": "Original source latitude hemisphere indicator: 'N' or 'S'; retained for provenance; use signed latitude for analysis",
    "longitude": "Geographic longitude of peak brightness in decimal degrees (positive = E, negative = W); null for events where coordinates are withheld or unavailable",
    "lon_direction": "Original source longitude hemisphere indicator: 'E' or 'W'; retained for provenance; use signed longitude for analysis",
    "altitude_km": "Altitude at peak brightness in km; typical fireball burn-up range 20-80 km; null for events without altitude measurement",
    "velocity_kms": "Pre-entry velocity at peak brightness in km/s; range ~11 km/s (escape velocity minimum) to ~72 km/s (maximum relative to Earth's orbit); null for events without velocity measurement",
    "vx_kms": "East-West velocity component in km/s, Earth-Centered Earth-Fixed (ECEF) frame; null when full velocity solution unavailable",
    "vy_kms": "North-South velocity component in km/s, ECEF frame; null when full velocity solution unavailable",
    "vz_kms": "Vertical (radial) velocity component in km/s, ECEF frame; null when full velocity solution unavailable",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Atmospheric impact events (fireballs and bolides) detected by US government sensors, \
from NASA JPL CNEOS.

Fireballs are exceptionally bright meteors caused by small asteroids or large \
meteoroids entering the atmosphere at high speed. The largest events can release \
energy equivalent to tens or hundreds of kilotons of TNT.

The detection threshold for these sensors corresponds roughly to bolides with impact \
energies above 0.1 kilotons of TNT, equivalent to a meteoroid roughly 1 meter in \
diameter striking the atmosphere at typical velocities of 15-25 km/s. The largest \
event in the modern record is the Chelyabinsk airburst of February 2013, which \
released approximately 440 kilotons and produced a shockwave that injured over 1,500 \
people. Events of this magnitude (10-20 meter impactors) are estimated to occur \
roughly once per century, while meter-scale impacts happen several times per year.

The velocity components (Vx, Vy, Vz) in the Earth-Centered Earth-Fixed (ECEF) frame \
allow reconstruction of the pre-atmospheric orbit, connecting individual bolides to \
their parent populations in the asteroid or cometary reservoirs.

The geographic distribution of detected fireballs reflects both the true impact flux \
and sensor coverage biases. Most events are detected over open ocean or unpopulated \
regions, and coordinate data may be withheld for events near politically sensitive \
areas. The radiated energy represents only a fraction of the total kinetic energy, \
with the remainder partitioned into the shockwave, fragmentation, heating, and \
deceleration.
"""


def main():
    print("Fetching fireball/bolide events from NASA JPL CNEOS...")
    payload = jpl_query("fireball.api", params={"limit": "9999"})

    df = jpl_fields_data_to_df(payload)
    print(f"  {len(df):,} events")

    # Rename columns to snake_case
    df = df.rename(columns={
        "date": "datetime",
        "energy": "radiated_energy_j",
        "impact-e": "impact_energy_kt",
        "lat": "latitude",
        "lat-dir": "lat_direction",
        "lon": "longitude",
        "lon-dir": "lon_direction",
        "alt": "altitude_km",
        "vel": "velocity_kms",
        "vx": "vx_kms",
        "vy": "vy_kms",
        "vz": "vz_kms",
    })

    # Type conversions
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    for col in ["radiated_energy_j", "impact_energy_kt", "latitude", "longitude",
                "altitude_km", "velocity_kms", "vx_kms", "vy_kms", "vz_kms"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Create signed latitude/longitude
    if "lat_direction" in df.columns:
        df["latitude"] = df.apply(
            lambda r: -r["latitude"] if r["lat_direction"] == "S" else r["latitude"],
            axis=1,
        )
    if "lon_direction" in df.columns:
        df["longitude"] = df.apply(
            lambda r: -r["longitude"] if r["lon_direction"] == "W" else r["longitude"],
            axis=1,
        )

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    df = df.sort_values("datetime").reset_index(drop=True)

    # ── Domain-specific stats for README ─────────────────────────────
    n = len(df)
    date_min = df["datetime"].min().strftime("%Y-%m-%d")
    date_max = df["datetime"].max().strftime("%Y-%m-%d")
    max_energy = df["impact_energy_kt"].max()
    n_with_energy = int(df["impact_energy_kt"].notna().sum())
    n_with_coords = int(df["latitude"].notna().sum())

    quick_stats = f"""\
- **{n:,}** fireball events ({date_min} to {date_max})
- **{n_with_energy}** events with measured impact energy
- **{n_with_coords}** events with geographic coordinates
- Largest impact energy: **{max_energy:.1f} kt**"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/fireball-bolide-events", split="train")
df = ds.to_pandas()

# High-energy events (> 1 kiloton)
big = df[df["impact_energy_kt"] > 1].sort_values("impact_energy_kt", ascending=False)
print(big[["datetime", "impact_energy_kt", "latitude", "longitude"]])

# Plot events on a map
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(12, 6))
coords = df.dropna(subset=["latitude", "longitude"])
ax.scatter(coords["longitude"], coords["latitude"],
           s=coords["impact_energy_kt"].fillna(0.1) * 5, alpha=0.5)
ax.set_xlabel("Longitude")
ax.set_ylabel("Latitude")
ax.set_title("Fireball Events by Location and Energy")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Fireball and Bolide Events",
        description=DESCRIPTION,
        tags=["space", "fireball", "bolide", "meteor", "impact", "nasa",
              "planetary-defense", "open-data", "tabular-data", "parquet"],
        source_url="https://cneos.jpl.nasa.gov/fireballs/",
        task_categories=["tabular-classification", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA17666/PIA17666~small.jpg",
            "alt": "Rosetta spacecraft approaching Comet 67P/Churyumov-Gerasimenko",
            "credit": "NASA/ESA",
        },
        related_datasets=[
            "juliensimon/neo-close-approaches",
            "juliensimon/sentry-impact-risk",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "radiated_energy_j", "impact_energy_kt", "latitude", "longitude",
                "altitude_km", "velocity_kms", "vx_kms", "vy_kms", "vz_kms",
            ],
        )
        p.publish(
            df,
            filename="fireball_bolide_events.parquet",
            min_rows=500,
            expected_columns=["datetime", "latitude", "longitude", "impact_energy_kt"],
            critical_columns=["datetime", "latitude", "longitude"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update fireball/bolide events: {n:,} records",
        )
    print("Done.")


if __name__ == "__main__":
    main()
