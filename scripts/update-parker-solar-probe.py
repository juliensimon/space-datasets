#!/usr/bin/env python3
"""Build the Parker Solar Probe mission encounter timeline.

Static mission table compiled from NASA/JHU APL Parker Solar Probe mission documents
and Fox et al. 2016 (Space Sci. Rev., DOI 10.1007/s11214-015-0211-6). Includes all
24 nominal-mission solar encounters and the 7 Venus gravity assists that sequenced
the spacecraft into seven progressively closer orbital phases ending at the historic
December 24 2024 closest approach of 9.86 R_sun (~6.86 million km).

Data sources verified against JPL Horizons (object id -96) for perihelion dates.
"""

from datetime import datetime

import pandas as pd

from hf_dataset_utils import Pipeline

HF_REPO = "juliensimon/parker-solar-probe-encounters"

# ── Mission events (24 perihelion encounters + 7 Venus flybys) ───────
# Distances in solar radii (R_sun = 695,700 km).
# Perihelion speed in km/s (heliocentric, at periapsis).
# Venus flyby altitude in km above Venus mean surface.
# Phase IDs map to the orbital era between gravity assists.
ENCOUNTERS = [
    # encounter_no, perihelion_date_utc, r_sun, million_km, speed_kms, phase, preceding_va
    (1,  "2018-11-06 03:27", 35.66, 24.81,  95.3, "Phase 1", None),
    (2,  "2019-04-04 22:40", 35.66, 24.81,  95.3, "Phase 1", None),
    (3,  "2019-09-01 17:50", 35.66, 24.81,  95.3, "Phase 1", None),
    (4,  "2020-01-29 09:37", 27.85, 19.38, 109.3, "Phase 2", "VGA-2"),
    (5,  "2020-06-07 08:23", 27.85, 19.38, 109.3, "Phase 2", None),
    (6,  "2020-09-27 09:16", 20.34, 14.15, 129.0, "Phase 3", "VGA-3"),
    (7,  "2021-01-17 17:36", 20.34, 14.15, 129.0, "Phase 3", None),
    (8,  "2021-04-29 08:48", 15.97, 11.11, 147.0, "Phase 4", "VGA-4"),
    (9,  "2021-08-09 19:11", 15.97, 11.11, 147.0, "Phase 4", None),
    (10, "2021-11-21 08:23", 13.28,  9.24, 163.0, "Phase 5", "VGA-5"),
    (11, "2022-02-25 15:38", 13.28,  9.24, 163.0, "Phase 5", None),
    (12, "2022-06-01 19:50", 13.28,  9.24, 163.0, "Phase 5", None),
    (13, "2022-09-06 06:04", 13.28,  9.24, 163.0, "Phase 5", None),
    (14, "2022-12-11 13:16", 13.28,  9.24, 163.0, "Phase 5", None),
    (15, "2023-03-17 20:30", 13.28,  9.24, 163.0, "Phase 5", None),
    (16, "2023-06-22 03:46", 13.28,  9.24, 163.0, "Phase 5", None),
    (17, "2023-09-27 23:28", 11.43,  7.95, 176.0, "Phase 6", "VGA-6"),
    (18, "2023-12-29 00:54", 11.43,  7.95, 176.0, "Phase 6", None),
    (19, "2024-03-30 02:21", 11.43,  7.95, 176.0, "Phase 6", None),
    (20, "2024-06-30 03:47", 11.43,  7.95, 176.0, "Phase 6", None),
    (21, "2024-09-30 05:15", 11.43,  7.95, 176.0, "Phase 6", None),
    (22, "2024-12-24 11:53",  9.86,  6.86, 191.8, "Phase 7", "VGA-7"),
    (23, "2025-03-22 22:42",  9.86,  6.86, 191.8, "Phase 7", None),
    (24, "2025-06-19 09:31",  9.86,  6.86, 191.8, "Phase 7", None),
]

# Venus gravity assists (7 total). VGA-1 occurred Oct 3 2018 before E1.
VENUS_FLYBYS = [
    # flyby_no, date_utc, altitude_km, direction
    (1, "2018-10-03 08:44", 2548, "Inbound"),
    (2, "2019-12-26 18:14", 3023, "Inbound"),
    (3, "2020-07-11 03:22",  834, "Outbound"),
    (4, "2021-02-20 20:25", 2392, "Outbound"),
    (5, "2021-10-16 09:00", 3786, "Inbound"),
    (6, "2023-08-21 14:00", 3939, "Inbound"),
    (7, "2024-11-06 17:39",  317, "Outbound"),
]

R_SUN_KM = 695_700.0
SUN_RADIUS_REF = "R_sun = 695,700 km (IAU nominal solar radius)"

# ── Column descriptions ──────────────────────────────────────────────
COLUMN_DESCRIPTIONS = {
    "event_type": "Event category: 'perihelion' for one of the 24 nominal-mission solar encounters, 'venus_flyby' for one of the 7 Venus gravity assists that lowered perihelion altitude",
    "sequence_number": "Encounter number (E1-E24) for perihelions or Venus flyby number (VGA-1 through VGA-7) within its event_type",
    "event_label": "Human-readable label such as 'E1' for encounter 1 or 'VGA-3' for the third Venus gravity assist",
    "event_datetime_utc": "Event date and time in UTC (perihelion epoch for encounters, closest-approach time for flybys); minute-precision values are taken from JHU APL mission planning publications",
    "event_year": "Calendar year of the event (integer, derived from event_datetime_utc)",
    "perihelion_distance_rsun": "Heliocentric distance at perihelion in solar radii (R_sun = 695,700 km); null for Venus flybys; ranges from 35.66 R_sun in Phase 1 down to 9.86 R_sun for the post-VGA-7 final phase",
    "perihelion_distance_million_km": "Heliocentric distance at perihelion in millions of kilometers; null for Venus flybys; the December 24 2024 closest approach was 6.86 million km from the photosphere",
    "perihelion_distance_au": "Heliocentric distance at perihelion in astronomical units (1 AU = 149,597,870.7 km); null for Venus flybys",
    "perihelion_speed_kms": "Heliocentric speed at perihelion in km/s; null for Venus flybys; the spacecraft is the fastest human-made object ever, reaching ~191.8 km/s (~691,000 km/h) during Phase 7 perihelions",
    "venus_flyby_altitude_km": "Closest-approach altitude above Venus's mean surface in kilometers; null for perihelion encounters; ranges from 317 km (VGA-7, the final and lowest-altitude assist) to 3,939 km (VGA-6)",
    "venus_flyby_direction": "Trajectory direction relative to Venus orbit at flyby: 'Inbound' (decelerating into a smaller orbit) or 'Outbound' (departing for a new perihelion); null for perihelion encounters",
    "mission_phase": "Orbital phase identifier: Phase 1 (post-launch through VGA-2), Phase 2 (after VGA-2, perihelion ~27.85 R_sun), Phase 3 (after VGA-3, ~20.34 R_sun), Phase 4 (after VGA-4, ~15.97 R_sun), Phase 5 (after VGA-5, ~13.28 R_sun, eight encounters), Phase 6 (after VGA-6, ~11.43 R_sun), Phase 7 (after VGA-7, ~9.86 R_sun, final phase)",
    "preceding_venus_flyby": "For perihelion encounters that immediately followed a Venus gravity assist, the label of that flyby (e.g. 'VGA-2'); null for encounters within an established phase and for the flyby rows themselves",
}

DESCRIPTION = """\
Complete mission timeline for NASA's Parker Solar Probe — the first spacecraft to "touch" the Sun's \
corona and the fastest human-made object ever built. Compiled from JHU APL mission documents and \
the Fox et al. 2016 mission design paper (Space Sci. Rev. 204), with perihelion epochs cross-checked \
against JPL Horizons (object id -96).

The dataset covers all 24 nominal-mission perihelion encounters from E1 (November 6 2018, 35.66 R_sun) \
through E24 (June 19 2025, 9.86 R_sun), interleaved with the 7 Venus gravity assists (VGA-1 through \
VGA-7) that sequenced the spacecraft into seven progressively closer orbital phases. Each row records \
the event date and time in UTC, perihelion distance (in solar radii, million km, and AU), heliocentric \
speed at perihelion, mission phase identifier, and Venus flyby altitude where applicable.

The historic December 24 2024 perihelion (E22) brought the spacecraft to 9.86 R_sun (6.86 million km) \
from the Sun's photosphere at 191.8 km/s — about 691,000 km/h — making it the closest and fastest \
solar approach ever achieved. This encounter and the two subsequent Phase 7 perihelions in 2025 \
completed the seven-year primary mission. Use this dataset alongside juliensimon/spacex-launches and \
juliensimon/blue-origin-launches for mission-cadence comparisons, with juliensimon/sunspot and \
juliensimon/solar-flares for solar-activity context, and with juliensimon/donki for direct correlation \
of Parker observations against catalogued space weather events.\
"""


def parse_dt(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d %H:%M")


def build_dataframe() -> pd.DataFrame:
    rows = []
    for n, dt_str, r_sun, mkm, speed, phase, preceding_va in ENCOUNTERS:
        dt = parse_dt(dt_str)
        rows.append({
            "event_type": "perihelion",
            "sequence_number": n,
            "event_label": f"E{n}",
            "event_datetime_utc": dt,
            "event_year": dt.year,
            "perihelion_distance_rsun": r_sun,
            "perihelion_distance_million_km": mkm,
            "perihelion_distance_au": (r_sun * R_SUN_KM) / 149_597_870.7,
            "perihelion_speed_kms": speed,
            "venus_flyby_altitude_km": None,
            "venus_flyby_direction": None,
            "mission_phase": phase,
            "preceding_venus_flyby": preceding_va,
        })
    for n, dt_str, alt, direction in VENUS_FLYBYS:
        dt = parse_dt(dt_str)
        rows.append({
            "event_type": "venus_flyby",
            "sequence_number": n,
            "event_label": f"VGA-{n}",
            "event_datetime_utc": dt,
            "event_year": dt.year,
            "perihelion_distance_rsun": None,
            "perihelion_distance_million_km": None,
            "perihelion_distance_au": None,
            "perihelion_speed_kms": None,
            "venus_flyby_altitude_km": float(alt),
            "venus_flyby_direction": direction,
            "mission_phase": None,
            "preceding_venus_flyby": None,
        })
    df = pd.DataFrame(rows).sort_values("event_datetime_utc").reset_index(drop=True)
    return df


def main():
    print("Building Parker Solar Probe encounter timeline...")
    df = build_dataframe()

    n_perihelia = int((df["event_type"] == "perihelion").sum())
    n_flybys = int((df["event_type"] == "venus_flyby").sum())
    encounters = df[df["event_type"] == "perihelion"]
    closest_r_sun = float(encounters["perihelion_distance_rsun"].min())
    closest_million_km = float(encounters["perihelion_distance_million_km"].min())
    fastest_kms = float(encounters["perihelion_speed_kms"].max())
    fastest_kmh = fastest_kms * 3600
    span_years = encounters["event_year"].max() - encounters["event_year"].min()
    lowest_va_alt = float(df["venus_flyby_altitude_km"].min())

    print(f"  {n_perihelia} perihelion encounters + {n_flybys} Venus gravity assists")
    print(f"  Closest approach: {closest_r_sun:.2f} R_sun ({closest_million_km:.2f} million km)")
    print(f"  Fastest perihelion speed: {fastest_kms:.1f} km/s ({fastest_kmh:,.0f} km/h)")
    print(f"  Lowest Venus flyby altitude: {lowest_va_alt:,.0f} km")

    quick_stats = f"""\
- **{n_perihelia}** perihelion encounters (E1 through E{n_perihelia}) plus **{n_flybys}** Venus gravity assists across **{span_years} years** of nominal mission
- **Closest approach: {closest_r_sun:.2f} R_sun** ({closest_million_km:.2f} million km) on December 24 2024 — the closest any spacecraft has ever come to the Sun
- **Fastest perihelion speed: {fastest_kms:.1f} km/s** (~{fastest_kmh:,.0f} km/h) — the highest speed ever achieved by a human-made object
- **Lowest Venus flyby altitude: {lowest_va_alt:,.0f} km** (VGA-7, November 6 2024) — final gravity assist that placed the spacecraft into Phase 7
- Mission organized into **7 orbital phases** keyed to the 7 Venus gravity assists, with perihelion altitude stepping down from 35.66 to 9.86 R_sun"""

    usage = """\
```python
from datasets import load_dataset
import matplotlib.pyplot as plt

df = load_dataset("juliensimon/parker-solar-probe-encounters", split="train").to_pandas()

# Plot perihelion altitude over time, color-coded by mission phase
peri = df[df["event_type"] == "perihelion"]
fig, ax = plt.subplots(figsize=(12, 5))
for phase, sub in peri.groupby("mission_phase"):
    ax.scatter(sub["event_datetime_utc"], sub["perihelion_distance_rsun"],
               label=phase, s=80)
# Overlay Venus flybys as vertical lines
for _, row in df[df["event_type"] == "venus_flyby"].iterrows():
    ax.axvline(row["event_datetime_utc"], color="grey", alpha=0.4, linestyle="--")
ax.set_ylabel("Perihelion distance (R_sun)")
ax.set_title("Parker Solar Probe — perihelion altitude across mission phases")
ax.invert_yaxis()  # closer = lower
ax.legend(title="Mission phase", ncol=2)
plt.tight_layout()
plt.show()

# Highlight the historic E22 closest approach
e22 = peri[peri["sequence_number"] == 22].iloc[0]
print(f"E22: {e22['event_datetime_utc']:%Y-%m-%d %H:%M UTC} — "
      f"{e22['perihelion_distance_rsun']:.2f} R_sun at {e22['perihelion_speed_kms']:.1f} km/s")
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Parker Solar Probe Encounter Timeline",
        description=DESCRIPTION,
        tags=["space", "heliophysics", "parker-solar-probe", "psp", "nasa",
              "sun", "corona", "solar-wind", "spacecraft", "mission-timeline",
              "encounters", "open-data", "tabular-data", "parquet"],
        source_url="https://parkersolarprobe.jhuapl.edu/Spacecraft/index.php",
        task_categories=["tabular-classification", "time-series-forecasting"],
        collection_url="https://huggingface.co/collections/juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70",
        banner={
            "url": "https://images-assets.nasa.gov/image/brief-outburst_16760026566_o/brief-outburst_16760026566_o~medium.jpg",
            "alt": "The Sun captured by NASA's Solar Dynamics Observatory — Parker Solar Probe's target",
            "credit": "NASA/SDO",
        },
        related_datasets=[
            "juliensimon/sunspot",
            "juliensimon/solar-flares",
            "juliensimon/donki",
            "juliensimon/solar-wind",
            "juliensimon/space-weather",
            "juliensimon/deep-space-probes",
        ],
    ) as p:
        df_clean = p.clean(
            df,
            numeric=[
                "perihelion_distance_rsun",
                "perihelion_distance_million_km",
                "perihelion_distance_au",
                "perihelion_speed_kms",
                "venus_flyby_altitude_km",
            ],
        )
        p.publish(
            df_clean,
            filename="parker_solar_probe_encounters.parquet",
            min_rows=30,
            expected_columns=[
                "event_type", "sequence_number", "event_label",
                "event_datetime_utc", "perihelion_distance_rsun",
            ],
            critical_columns=["event_type", "sequence_number", "event_datetime_utc"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=(
                f"Update Parker Solar Probe encounters: {n_perihelia} perihelia + "
                f"{n_flybys} Venus flybys, closest approach {closest_r_sun:.2f} R_sun"
            ),
        )
    print("Done.")


if __name__ == "__main__":
    main()
