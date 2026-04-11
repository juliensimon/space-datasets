#!/usr/bin/env python3
"""Fetch Cassini Saturn observation master schedule and upload to HF.

Source: NASA PDS Atmospheres Node — Cassini Master Schedule
https://pds-atmospheres.nmsu.edu/data_and_services/atmospheres_data/Cassini_PDS3/logs/
"""

import io

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

CSV_URL = "https://pds-atmospheres.nmsu.edu/data_and_services/atmospheres_data/Cassini_PDS3/logs/master%20as%20planned%209-15-18.csv"
HF_REPO = "juliensimon/cassini-saturn-observations"

COLUMN_RENAME = {
    "Start time (UTC)": "start_time_utc",
    "Duration": "duration",
    "Date": "date",
    "Team": "team",
    "SPASS Type": "spass_type",
    "Target": "target",
    "Request Name": "request_name",
    "Library Definition": "library_definition",
    "Title": "title",
    "Description": "description",
}

COLUMN_DESCRIPTIONS = {
    "start_time_utc": "Observation start time (UTC); covers 2004-2017, the full 13-year orbital mission at Saturn",
    "duration": "Planned duration of observation in HH:MM:SS format",
    "date": "Calendar date in YYYY-DOY format (day-of-year) from the master schedule",
    "team": "Science team responsible (e.g. CIRS=thermal IR, ISS=imaging, UVIS=UV, VIMS=visual/IR mapping, MAG=magnetometer, RPWS=radio/plasma, RADAR, CAPS=plasma spectrometer)",
    "spass_type": "SPASS (Science Planning and Sequencing System) observation type code classifying the kind of science activity",
    "target": "Observation target body (e.g. SATURN, TITAN, ENCELADUS, RINGS, RHEA, DIONE, IAPETUS)",
    "request_name": "Unique internal request name assigned by the sequencing system",
    "library_definition": "Reference to the observation library template defining instrument parameters",
    "title": "Short human-readable observation title",
    "description": "Detailed description of the science goals and instrument configuration for this observation",
}

DESCRIPTION = """\
Complete Cassini mission observation master schedule -- planned science observations \
spanning 2004 to 2017. Cassini orbited Saturn for 13 years, studying the planet, its \
rings, and its moons before its planned destruction in Saturn's atmosphere on \
September 15, 2017.

The Cassini-Huygens mission was one of the most ambitious planetary exploration \
endeavors ever undertaken. A joint NASA/ESA/ASI project, Cassini spent 13 years in \
orbit around Saturn, completing 294 orbits and 127 close flybys of Titan, along with \
numerous encounters with Enceladus, Rhea, Dione, and other Saturnian moons. The \
spacecraft carried 12 science instruments spanning imaging, spectroscopy, radar, \
magnetometry, and particle detection, operated by dedicated science teams (identified \
as CIRS, ISS, UVIS, VIMS, CAPS, MAG, RADAR, RPWS, and others in this observation \
schedule).

Among Cassini's landmark discoveries were the active water-ice geysers erupting from \
Enceladus's south polar tiger stripe fractures -- revealing a subsurface ocean with \
hydrothermal activity and the potential for habitability -- and the detailed \
characterization of Titan's methane hydrological cycle through RADAR mapping of surface \
lakes and seas. Cassini also observed the hexagonal jet stream at Saturn's north pole, \
tracked the evolution of a massive northern hemisphere storm in 2010-2011, measured \
Saturn's internal rotation period through ring seismology, and discovered seven new \
moons. The mission's Grand Finale in 2017 sent the spacecraft between Saturn's \
innermost ring and the planet's atmosphere, providing the closest-ever measurements of \
Saturn's gravity field and magnetic field.

This observation master schedule documents every planned science activity across the \
entire mission, making it possible to reconstruct which targets were observed, by which \
instrument teams, and when."""


def main():
    print("Fetching Cassini observation master schedule...")
    resp = requests.get(CSV_URL, timeout=120)
    resp.raise_for_status()

    # Skip first 2 rows (title + blank), use row 3 as headers
    df = pd.read_csv(io.StringIO(resp.text), skiprows=2, low_memory=False)
    print(f"  {len(df):,} raw rows")

    # Clean up trailing commas -- drop fully unnamed columns
    df = df.loc[:, ~df.columns.str.startswith("Unnamed")]

    # Strip whitespace from column names (e.g., "Date " -> "Date")
    df.columns = df.columns.str.strip()

    # Drop rows that are all-NaN
    df = df.dropna(how="all").reset_index(drop=True)

    # Rename columns to snake_case
    df = df.rename(columns=COLUMN_RENAME)

    # Parse start_time_utc -- format is YYYY-DDDTHH:MM:SS (day-of-year)
    df["start_time_utc"] = pd.to_datetime(
        df["start_time_utc"], format="%Y-%jT%H:%M:%S", errors="coerce"
    )

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Sort by start_time_utc
    df = df.sort_values("start_time_utc").reset_index(drop=True)

    print(f"  {len(df):,} rows after cleanup")

    # ── Domain-specific stats ────────────────────────────────────────
    n = len(df)
    n_targets = df["target"].nunique()
    n_teams = df["team"].nunique()
    valid_times = df["start_time_utc"].dropna()
    year_min = int(valid_times.dt.year.min()) if len(valid_times) > 0 else 2004
    year_max = int(valid_times.dt.year.max()) if len(valid_times) > 0 else 2017
    top_target = df["target"].value_counts().index[0]

    quick_stats = f"""\
- **{n:,}** planned observations ({year_min}--{year_max})
- **{n_targets}** distinct targets (most observed: {top_target})
- **{n_teams}** science teams"""

    usage = f"""\
```python
from datasets import load_dataset

ds = load_dataset("{HF_REPO}", split="train")
df = ds.to_pandas()

# Observations by target
df["target"].value_counts().head(10)

# Titan flybys
titan = df[df["target"] == "TITAN"].sort_values("start_time_utc")

# Timeline of observations per year
import matplotlib.pyplot as plt
df["year"] = df["start_time_utc"].dt.year
df.groupby("year").size().plot(kind="bar")
plt.xlabel("Year")
plt.ylabel("Observations")
plt.title("Cassini observations per year")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Cassini Saturn Observations",
        description=DESCRIPTION,
        tags=["space", "saturn", "cassini", "nasa", "planetary-science",
              "pds", "open-data", "tabular-data", "parquet"],
        source_url="https://pds-atmospheres.nmsu.edu/data_and_services/atmospheres_data/Cassini_PDS3/logs/",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/space-probe-and-mission-datasets-69c3fe82d410a42b1e313167",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA06193/PIA06193~small.jpg",
            "alt": "Saturn and its rings, captured by the Cassini spacecraft",
            "credit": "NASA/JPL-Caltech/SSI",
        },
        related_datasets=[
            "juliensimon/mars-craters-robbins",
            "juliensimon/lunar-craters-robbins",
            "juliensimon/nasa-exoplanets",
        ],
    ) as p:
        df = p.clean(df, drop_mostly_null_threshold=0.95)
        p.publish(
            df,
            filename="cassini_observations.parquet",
            min_rows=50_000,
            expected_columns=list(COLUMN_DESCRIPTIONS.keys()),
            critical_columns=["start_time_utc", "target", "team"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Upload Cassini observations: {n:,} records",
        )
    print("Done.")


if __name__ == "__main__":
    main()
