#!/usr/bin/env python3
"""Fetch NASA EVA chronology and upload to HF.

Source: NASA Open Data Portal — Extra-vehicular Activity (EVA) - US and Russia.
"""

import io

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

HF_REPO = "juliensimon/nasa-eva-chronology"

NASA_CSV_URL = (
    "https://data.nasa.gov/docs/legacy/"
    "Extra-vehicular_Activity_EVA_-_US_and_Russia/"
    "Extra-vehicular_Activity_EVA_-_US_and_Russia_rows.csv"
)

# ── Column mapping ───────────────────────────────────────────────────
RENAME = {
    "EVA #": "eva_number",
    "Country": "country",
    "Crew": "crew",
    "Vehicle": "vehicle",
    "Date": "date",
    "Duration": "duration",
    "Purpose": "purpose",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "eva_number": "Sequential EVA number within the NASA/Roscosmos program chronology; not unique across countries",
    "country": "Country responsible for the EVA: 'USA' or 'Russia'",
    "crew": "Astronaut/cosmonaut names performing the EVA, comma-separated (e.g. 'White, McDivitt'); may be a single name for solo EVAs",
    "vehicle": "Spacecraft or station from which the EVA was conducted (e.g. 'Gemini 4', 'Apollo 11', 'ISS', 'Mir', 'Shuttle')",
    "date": "UTC date the EVA began",
    "duration": "EVA duration in H:MM format (e.g. '2:20'); exact logged time from hatch open to hatch close",
    "duration_minutes": "EVA duration in total minutes (e.g. 140.0); range roughly 6 min to ~540 min; null if source duration was unparseable",
    "purpose": "Free-text description of primary EVA objectives (e.g. 'Solar array repair', 'Hardware installation', 'First American spacewalk'); null for early program entries with no recorded objective",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Complete chronology of all extravehicular activities (spacewalks) performed by \
NASA and Roscosmos astronauts and cosmonauts.

Extravehicular activity -- spacewalking -- is among the most demanding and \
dangerous operations in human spaceflight. Every EVA requires hours of \
pre-breathing pure oxygen to avoid decompression sickness, careful choreography \
of tasks in microgravity, and constant monitoring of suit pressure, oxygen \
reserves, and CO2 levels. The first EVA was performed by Alexei Leonov in March \
1965 during Voskhod 2, lasting just 12 minutes; today, ISS maintenance EVAs \
routinely exceed six hours and involve complex hardware installation, thermal \
blanket repairs, and robotic arm operations.

The chronological record of EVAs traces the evolution of spacesuit technology, \
from the rudimentary Berkut suit through NASA's Extravehicular Mobility Unit \
(EMU) to the Orlan series used on the Russian segment of the ISS. The data \
captures every phase of spacewalking history: the Gemini program's early \
experiments with working in vacuum, the Apollo lunar surface EVAs, Skylab \
exterior repairs, Shuttle-era satellite servicing missions (including the \
iconic Hubble Space Telescope repairs), and the ongoing ISS assembly and \
maintenance campaign that has consumed thousands of crew-hours.

This dataset supports research into EVA scheduling efficiency, crew workload \
analysis, the reliability of spacesuit systems, and risk assessment for future \
lunar and Mars surface operations.
"""


def parse_duration_minutes(val: str) -> float | None:
    """Convert 'H:MM' duration string to total minutes."""
    if pd.isna(val) or not isinstance(val, str):
        return None
    val = val.strip()
    if not val or ":" not in val:
        return None
    try:
        parts = val.split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, IndexError):
        return None


def main():
    print("Fetching NASA EVA chronology...")
    resp = requests.get(NASA_CSV_URL, timeout=60)
    resp.raise_for_status()

    df = pd.read_csv(io.StringIO(resp.text))
    print(f"  {len(df):,} EVA records")

    # ── Rename columns ──────────────────────────────────────────────
    df.columns = df.columns.str.strip()
    df = df.rename(columns=RENAME)

    # ── Type coercion ───────────────────────────────────────────────
    df["eva_number"] = pd.to_numeric(df["eva_number"], errors="coerce").astype("Int64")
    df["date"] = pd.to_datetime(df["date"], format="%m/%d/%Y", errors="coerce")

    # Parse duration H:MM -> total minutes, keep original string too
    df["duration_minutes"] = df["duration"].apply(parse_duration_minutes)
    df["duration"] = df["duration"].astype(str).str.strip().replace(
        {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
    )

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Sort
    df = df.sort_values(["date", "eva_number"]).reset_index(drop=True)

    # ── Stats for README ────────────────────────────────────────────
    n = len(df)
    n_usa = int((df["country"] == "USA").sum())
    n_russia = int((df["country"] == "Russia").sum())
    date_min = df["date"].min()
    date_max = df["date"].max()
    year_min = date_min.year if pd.notna(date_min) else "?"
    year_max = date_max.year if pd.notna(date_max) else "?"
    total_hours = df["duration_minutes"].sum() / 60
    n_vehicles = len(df["vehicle"].dropna().unique())
    top_vehicles = df["vehicle"].value_counts().head(5)
    top_vehicles_str = ", ".join(f"{v} ({c:,})" for v, c in top_vehicles.items())

    quick_stats = f"""\
- **{n:,}** EVAs ({n_usa:,} USA, {n_russia:,} Russia)
- **{year_min}** to **{year_max}**
- **{total_hours:,.0f}** total crew-hours
- **{n_vehicles}** vehicles: {top_vehicles_str}"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/nasa-eva-chronology", split="train")
df = ds.to_pandas()

# EVAs per vehicle
print(df["vehicle"].value_counts())

# Total spacewalk hours by country
by_country = df.groupby("country")["duration_minutes"].sum() / 60
print(by_country)

# Longest EVAs
longest = df.nlargest(10, "duration_minutes")[["date", "crew", "vehicle", "duration"]]
print(longest)

# EVA frequency over time
import matplotlib.pyplot as plt
df["year"] = df["date"].dt.year
df.groupby("year").size().plot(kind="bar", figsize=(14, 4))
plt.xlabel("Year")
plt.ylabel("Number of EVAs")
plt.title("Spacewalks Per Year")
plt.tight_layout()
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="NASA EVA Chronology",
        description=DESCRIPTION,
        tags=["space", "eva", "spacewalk", "nasa", "iss", "human-spaceflight",
              "open-data", "tabular-data", "parquet"],
        source_url="https://data.nasa.gov/dataset/extra-vehicular-activity-eva-us-and-russia",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/space-probe-and-mission-datasets-69c3fe82d410a42b1e313167",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA14111/PIA14111~small.jpg",
            "alt": "Voyager spacecraft artist concept",
            "credit": "NASA/JPL-Caltech",
        },
        related_datasets=[
            "juliensimon/astronaut-database",
            "juliensimon/space-launch-log",
        ],
    ) as p:
        df = p.clean(
            df,
            strings=["crew", "vehicle", "purpose", "country"],
        )
        p.publish(
            df,
            filename="eva.parquet",
            min_rows=200,
            expected_columns=["eva_number", "date", "crew", "vehicle", "duration", "country"],
            critical_columns=["crew", "country", "vehicle"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update NASA EVA chronology: {n:,} records",
        )
    print("Done.")


if __name__ == "__main__":
    main()
