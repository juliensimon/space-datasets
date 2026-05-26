#!/usr/bin/env python3
"""Build the Solar Orbiter mission encounter timeline.

ESA/NASA Solar Orbiter mission events: perihelion encounters and gravity assists
(Venus + Earth) through the high-inclination extended mission. Mission events
compiled from ESA Solar Orbiter operations documents and the Mueller et al. 2020
mission paper (A&A 642, A1, DOI 10.1051/0004-6361/202038467).

Solar Orbiter's distinctive feature among heliospheric missions is its planned
inclination ramp: a sequence of Venus gravity assists tilts the orbit out of the
ecliptic, eventually reaching ~33 degrees heliographic latitude — the first
sustained close-up views of the solar poles.
"""

from datetime import datetime

import pandas as pd

from hf_dataset_utils import Pipeline

HF_REPO = "juliensimon/solar-orbiter-encounters"

# ── Mission events ──────────────────────────────────────────────────
# Perihelion entries: (number, datetime_utc, perihelion_au, aphelion_au, helio_lat_deg, phase)
# Mission phases:
#   Cruise   = pre-2022, before nominal science orbit
#   Nominal  = nominal mission, operational ~0.28 AU perihelion
#   High-Lat = high-inclination phase after VGA-4 raises latitude to >=17 deg
PERIHELIA = [
    (1,  "2020-06-15 17:32", 0.516, 0.916,  5.6, "Cruise"),
    (2,  "2021-02-10 01:00", 0.490, 0.939,  5.4, "Cruise"),
    (3,  "2021-09-12 14:48", 0.589, 0.815,  6.0, "Cruise"),
    (4,  "2022-03-26 03:50", 0.323, 0.943,  6.8, "Nominal"),
    (5,  "2022-10-12 19:16", 0.293, 0.929,  3.4, "Nominal"),
    (6,  "2023-04-10 04:10", 0.293, 0.924,  3.4, "Nominal"),
    (7,  "2023-10-07 22:04", 0.293, 0.924,  3.4, "Nominal"),
    (8,  "2024-04-04 16:47", 0.293, 0.924,  3.4, "Nominal"),
    (9,  "2024-09-30 13:44", 0.293, 0.924,  3.4, "Nominal"),
    (10, "2025-03-31 04:50", 0.293, 0.924, 17.0, "High-Lat"),
    (11, "2025-09-16 21:40", 0.293, 0.924, 17.0, "High-Lat"),
    (12, "2026-03-03 11:50", 0.293, 0.924, 17.0, "High-Lat"),
    (13, "2026-08-18 22:30", 0.293, 0.924, 17.0, "High-Lat"),
]

# Gravity assists (Venus + Earth). All raise inclination after VGA-3.
FLYBYS = [
    # (label, body, datetime_utc, altitude_km, inclination_after_deg, notes)
    ("VGA-1",  "Venus", "2020-12-27 12:39", 7500.0,  None, "First Venus flyby; ecliptic"),
    ("VGA-2",  "Venus", "2021-08-09 04:42", 7995.0,  None, "Second Venus flyby; ecliptic"),
    ("EGA-1",  "Earth", "2021-11-27 04:30",  460.0,  None, "Earth gravity assist; placed spacecraft into nominal science orbit"),
    ("VGA-3",  "Venus", "2022-09-04 01:26", 6000.0,  None, "Third Venus flyby; nominal orbit established"),
    ("VGA-4",  "Venus", "2025-02-18 20:46",  379.0, 17.0, "Fourth Venus flyby; began high-inclination phase, raised heliographic latitude to ~17 deg"),
    ("VGA-5",  "Venus", "2026-12-24 16:00",  950.0, 24.0, "Fifth Venus flyby; raises heliographic latitude to ~24 deg"),
]

AU_KM = 149_597_870.7

# ── Column descriptions ──────────────────────────────────────────────
COLUMN_DESCRIPTIONS = {
    "event_type": "Event category: 'perihelion' for the spacecraft's closest-Sun point on each orbit, 'venus_flyby' for a Venus gravity assist, 'earth_flyby' for the single Earth gravity assist on 2021-11-27",
    "sequence_number": "Perihelion number for perihelion events (1-13+) or flyby number within its body for gravity assists (Venus 1-5+, Earth 1)",
    "event_label": "Human-readable label such as 'P5' for perihelion 5, 'VGA-4' for Venus gravity assist 4, or 'EGA-1' for the Earth gravity assist",
    "event_datetime_utc": "Event date and time in UTC (perihelion epoch for perihelion events, closest-approach time for flybys); minute-precision values are taken from ESA mission planning publications",
    "event_year": "Calendar year of the event (integer, derived from event_datetime_utc)",
    "perihelion_distance_au": "Heliocentric distance at perihelion in astronomical units (1 AU = 149,597,870.7 km); null for flybys; the operational orbit perihelion is ~0.293 AU",
    "perihelion_distance_million_km": "Heliocentric distance at perihelion in millions of kilometers; null for flybys; operational perihelion ~43.8 million km",
    "perihelion_distance_rsun": "Heliocentric distance at perihelion in solar radii (R_sun = 695,700 km); null for flybys; operational perihelion ~63 R_sun (compare to Parker Solar Probe at 9.86 R_sun for the closest approach)",
    "aphelion_distance_au": "Heliocentric distance at the corresponding aphelion in astronomical units; null for flybys; operational aphelion ~0.92 AU",
    "heliographic_latitude_deg": "Maximum heliographic latitude of the spacecraft on the orbit hosting this perihelion, in degrees; positive = north of the solar equator; rises from ~5-6 deg in the Cruise phase to 17+ deg after VGA-4 and 24+ deg after VGA-5",
    "flyby_body": "For gravity assists, the body providing the assist: 'Venus' or 'Earth'; null for perihelion events",
    "flyby_altitude_km": "Closest-approach altitude above the body's mean surface in kilometers for gravity assists; null for perihelion events; ranges from 379 km (VGA-4, lowest Venus altitude) up to ~7,995 km (VGA-2)",
    "inclination_after_deg": "Heliographic-equator orbital inclination achieved after this gravity assist, in degrees; null for events that did not change orbit inclination",
    "mission_phase": "Mission phase identifier: Cruise (pre-2022, before nominal orbit), Nominal (nominal science orbit ~0.29 AU perihelion in the ecliptic), High-Lat (high-inclination phase after VGA-4, sustained polar views of the Sun); null for flyby rows",
    "notes": "Brief free-text annotation describing significance of the event (e.g. 'began high-inclination phase'); short for perihelion rows, longer for flyby rows",
}

DESCRIPTION = """\
Complete mission event timeline for the ESA/NASA Solar Orbiter — the first spacecraft designed to \
deliver sustained close-up views of the Sun's polar regions. Compiled from ESA Solar Orbiter \
operations documents and the Mueller et al. 2020 mission overview paper (A&A 642, A1).

The dataset covers all perihelion encounters from P1 (2020-06-15, 0.516 AU) through the planned \
encounters of the early high-inclination phase, interleaved with the gravity assists (5 Venus + 1 \
Earth) that progressively raised orbital inclination above the ecliptic. Each row records the event \
date and time in UTC, perihelion distance in AU, R_sun, and million km, aphelion distance, the \
heliographic latitude reached on each orbit, flyby altitudes, and the mission phase identifier.

Solar Orbiter's distinctive trajectory complements NASA's Parker Solar Probe: PSP achieves the \
closest physical approach (9.86 R_sun) but stays near the ecliptic, while Solar Orbiter's nominal \
perihelion of ~0.293 AU (~63 R_sun) is paired with a planned ramp to ~33 degrees heliographic \
latitude, enabling the first systematic remote-sensing observations of the solar poles. Use this \
dataset alongside juliensimon/parker-solar-probe-encounters for direct mission comparison, with \
juliensimon/sunspot and juliensimon/solar-flares for solar-activity context, and with \
juliensimon/donki for cross-correlation against catalogued space weather events.\
"""


def parse_dt(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d %H:%M")


def build_dataframe() -> pd.DataFrame:
    rows = []
    for n, dt_str, peri_au, ap_au, lat, phase in PERIHELIA:
        dt = parse_dt(dt_str)
        rows.append({
            "event_type": "perihelion",
            "sequence_number": n,
            "event_label": f"P{n}",
            "event_datetime_utc": dt,
            "event_year": dt.year,
            "perihelion_distance_au": peri_au,
            "perihelion_distance_million_km": peri_au * AU_KM / 1_000_000,
            "perihelion_distance_rsun": peri_au * AU_KM / 695_700.0,
            "aphelion_distance_au": ap_au,
            "heliographic_latitude_deg": lat,
            "flyby_body": None,
            "flyby_altitude_km": None,
            "inclination_after_deg": None,
            "mission_phase": phase,
            "notes": None,
        })

    venus_n = 0
    earth_n = 0
    for label, body, dt_str, alt, incl_after, notes in FLYBYS:
        if body == "Venus":
            venus_n += 1
            seq = venus_n
            etype = "venus_flyby"
        else:
            earth_n += 1
            seq = earth_n
            etype = "earth_flyby"
        dt = parse_dt(dt_str)
        rows.append({
            "event_type": etype,
            "sequence_number": seq,
            "event_label": label,
            "event_datetime_utc": dt,
            "event_year": dt.year,
            "perihelion_distance_au": None,
            "perihelion_distance_million_km": None,
            "perihelion_distance_rsun": None,
            "aphelion_distance_au": None,
            "heliographic_latitude_deg": None,
            "flyby_body": body,
            "flyby_altitude_km": alt,
            "inclination_after_deg": incl_after,
            "mission_phase": None,
            "notes": notes,
        })

    df = pd.DataFrame(rows).sort_values("event_datetime_utc").reset_index(drop=True)
    return df


def main():
    print("Building Solar Orbiter encounter timeline...")
    df = build_dataframe()

    n_peri = int((df["event_type"] == "perihelion").sum())
    n_venus = int((df["event_type"] == "venus_flyby").sum())
    n_earth = int((df["event_type"] == "earth_flyby").sum())

    perihelia = df[df["event_type"] == "perihelion"]
    closest_au = float(perihelia["perihelion_distance_au"].min())
    closest_rsun = float(perihelia["perihelion_distance_rsun"].min())
    max_lat = float(perihelia["heliographic_latitude_deg"].max())
    span_years = perihelia["event_year"].max() - perihelia["event_year"].min()
    lowest_va_alt = float(df.loc[df["event_type"] == "venus_flyby", "flyby_altitude_km"].min())

    print(f"  {n_peri} perihelia + {n_venus} Venus flybys + {n_earth} Earth flyby")
    print(f"  Closest perihelion: {closest_au:.3f} AU ({closest_rsun:.1f} R_sun)")
    print(f"  Max heliographic latitude (planned): {max_lat:.1f} deg")
    print(f"  Lowest Venus flyby altitude: {lowest_va_alt:.0f} km")

    quick_stats = f"""\
- **{n_peri}** perihelion encounters (P1 through P{n_peri}) plus **{n_venus}** Venus gravity assists and **{n_earth}** Earth gravity assist across **{span_years} years** of operations
- **Closest perihelion: {closest_au:.3f} AU** ({closest_rsun:.1f} R_sun, ~43.8 million km) — operational orbit since 2022
- **Maximum heliographic latitude: {max_lat:.0f} deg** after VGA-4 (Feb 2025), ramping toward ~33 deg over subsequent Venus flybys for sustained polar views of the Sun
- **Lowest Venus flyby altitude: {lowest_va_alt:.0f} km** (VGA-4, Feb 2025) — placed spacecraft into the high-inclination phase
- Mission phases: **Cruise** (pre-2022), **Nominal** (2022-2024 ecliptic science orbit), **High-Lat** (post-VGA-4 polar campaign)"""

    usage = """\
```python
from datasets import load_dataset
import matplotlib.pyplot as plt

so = load_dataset("juliensimon/solar-orbiter-encounters", split="train").to_pandas()
psp = load_dataset("juliensimon/parker-solar-probe-encounters", split="train").to_pandas()

# Compare Sun-approach distance (R_sun) for the two heliospheric flagships
peri_so = so[so["event_type"] == "perihelion"]
peri_psp = psp[psp["event_type"] == "perihelion"]

fig, ax = plt.subplots(figsize=(12, 5))
ax.scatter(peri_so["event_datetime_utc"], peri_so["perihelion_distance_rsun"],
           label="Solar Orbiter", s=60)
ax.scatter(peri_psp["event_datetime_utc"], peri_psp["perihelion_distance_rsun"],
           label="Parker Solar Probe", s=60)
ax.set_yscale("log")
ax.invert_yaxis()
ax.set_ylabel("Perihelion distance (R_sun, log scale)")
ax.set_title("Heliospheric flagships: PSP gets closest, Solar Orbiter goes polar")
ax.legend()
plt.tight_layout()
plt.show()

# Show how heliographic latitude ramps after each Venus flyby
print(peri_so[["event_label", "event_datetime_utc",
               "perihelion_distance_au", "heliographic_latitude_deg",
               "mission_phase"]].to_string(index=False))
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Solar Orbiter Encounter Timeline",
        description=DESCRIPTION,
        tags=["space", "heliophysics", "solar-orbiter", "esa", "nasa",
              "sun", "corona", "solar-wind", "spacecraft", "mission-timeline",
              "encounters", "open-data", "tabular-data", "parquet"],
        source_url="https://www.esa.int/Science_Exploration/Space_Science/Solar_Orbiter",
        license="other",
        license_name="cc-by-nc-3.0-igo",
        license_link="https://creativecommons.org/licenses/by-nc/3.0/igo/",
        task_categories=["tabular-classification", "time-series-forecasting"],
        collection_url="https://huggingface.co/collections/juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70",
        banner={
            "url": "https://images-assets.nasa.gov/image/brief-outburst_16760026566_o/brief-outburst_16760026566_o~medium.jpg",
            "alt": "The Sun captured by NASA's Solar Dynamics Observatory — Solar Orbiter's target",
            "credit": "NASA/SDO",
        },
        related_datasets=[
            "juliensimon/parker-solar-probe-encounters",
            "juliensimon/sunspot",
            "juliensimon/solar-flares",
            "juliensimon/donki",
            "juliensimon/solar-wind",
            "juliensimon/space-weather",
        ],
    ) as p:
        df_clean = p.clean(
            df,
            numeric=[
                "perihelion_distance_au",
                "perihelion_distance_million_km",
                "perihelion_distance_rsun",
                "aphelion_distance_au",
                "heliographic_latitude_deg",
                "flyby_altitude_km",
                "inclination_after_deg",
            ],
        )
        p.publish(
            df_clean,
            filename="solar_orbiter_encounters.parquet",
            min_rows=18,
            expected_columns=[
                "event_type", "sequence_number", "event_label",
                "event_datetime_utc", "perihelion_distance_au",
            ],
            critical_columns=["event_type", "sequence_number", "event_datetime_utc"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=(
                f"Update Solar Orbiter encounters: {n_peri} perihelia + "
                f"{n_venus} Venus + {n_earth} Earth flybys, max latitude {max_lat:.0f} deg"
            ),
        )
    print("Done.")


if __name__ == "__main__":
    main()
