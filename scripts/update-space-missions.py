#!/usr/bin/env python3
"""Fetch space missions database from Wikidata and upload to HF.

Source: Wikidata SPARQL endpoint — community-curated catalog of crewed
and uncrewed space missions maintained by WikiProject Spaceflight.
"""

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

HF_REPO = "juliensimon/space-missions"

WIKIDATA_URL = "https://query.wikidata.org/sparql"
HEADERS = {"User-Agent": "space-datasets/1.0 (https://github.com/juliensimon/space-datasets)"}

SPARQL_QUERY = """
SELECT ?mission ?missionLabel ?launch_date ?end_date
       ?operatorLabel ?destinationLabel ?launch_siteLabel
       ?vehicleLabel ?crewCount ?duration ?outcomeLabel
WHERE {
  { ?mission wdt:P31/wdt:P279* wd:Q2133344 }
  UNION { ?mission wdt:P31 wd:Q1248784 }
  UNION { ?mission wdt:P31 wd:Q12795915 }
  OPTIONAL { ?mission wdt:P619 ?launch_date. }
  OPTIONAL { ?mission wdt:P582 ?end_date. }
  OPTIONAL { ?mission wdt:P137 ?operator. }
  OPTIONAL { ?mission wdt:P1444 ?destination. }
  OPTIONAL { ?mission wdt:P1427 ?launch_site. }
  OPTIONAL { ?mission wdt:P4394 ?vehicle. }
  OPTIONAL { ?mission wdt:P1132 ?crewCount. }
  OPTIONAL { ?mission wdt:P2047 ?duration. }
  OPTIONAL { ?mission wdt:P793 ?outcome. }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,mul". }
}
"""

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "wikidata_id": "Wikidata entity ID (e.g. 'Q183294' for Apollo 11); stable persistent identifier that can be used to link back to the full Wikidata entry for enrichment",
    "name": "Official mission name as recorded in Wikidata (e.g. 'Apollo 11', 'Voyager 1', 'Mars Odyssey'); the English-language label from the Wikidata entity",
    "launch_date": "Date of launch in ISO 8601 format (YYYY-MM-DD); derived from Wikidata property P619; null for missions where launch date is unknown or not yet recorded",
    "end_date": "Date the mission ended in ISO 8601 format (YYYY-MM-DD); derived from Wikidata property P582; null for ongoing missions or those without a recorded end date",
    "operator": "Launching or operating space agency/organization (e.g. 'NASA', 'ESA', 'ISRO', 'Roscosmos', 'CNSA'); null for missions where Wikidata has no operator recorded",
    "destination": "Primary mission destination or target body (e.g. 'Moon', 'Mars', 'Jupiter'); derived from Wikidata property P1444; null for LEO missions or where not recorded",
    "launch_site": "Name of the launch facility (e.g. 'Kennedy Space Center', 'Baikonur Cosmodrome'); derived from Wikidata property P1427; null where not recorded",
    "vehicle": "Launch vehicle used (e.g. 'Saturn V', 'Falcon 9', 'Soyuz-FG'); derived from Wikidata property P4394; null where not recorded",
    "crew_count": "Number of crew members aboard; 0 or null for uncrewed missions; derived from Wikidata property P1132",
    "duration_days": "Mission duration in days, converted from Wikidata's minutes (P2047); null for missions where duration is not recorded or still ongoing",
    "outcome": "Mission outcome or significant event (e.g. 'successful orbital insertion', 'launch failure'); derived from Wikidata property P793; null where not recorded",
    "launch_year": "Year extracted from launch_date for convenience in temporal analysis; null when launch_date is missing",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Comprehensive database of space missions -- both crewed and uncrewed -- sourced \
from Wikidata's structured knowledge base. Covers the full history of spaceflight \
from the dawn of the Space Age to the present.

This dataset draws on Wikidata using three entity types: space missions (Q2133344), \
crewed spaceflights (Q1248784), and uncrewed spaceflights (Q12795915). It is \
maintained by the WikiProject Spaceflight community and updated as new missions \
are flown and documented.

**Note:** Wikidata coverage is uneven -- most entries have only a name and Wikidata ID. \
Columns with <5% data coverage are automatically dropped during pipeline processing.
"""


def fetch_missions() -> pd.DataFrame:
    """Query Wikidata SPARQL for all space missions."""
    print("Querying Wikidata for space missions...")
    resp = requests.get(
        WIKIDATA_URL,
        params={"query": SPARQL_QUERY, "format": "json"},
        headers=HEADERS,
        timeout=120,
    )
    resp.raise_for_status()

    results = resp.json()["results"]["bindings"]
    print(f"  {len(results):,} raw rows from Wikidata")

    rows = []
    for r in results:
        wikidata_id = r.get("mission", {}).get("value", "").rsplit("/", 1)[-1]
        # duration from Wikidata is in minutes
        duration_raw = r.get("duration", {}).get("value")
        duration_days = None
        if duration_raw:
            try:
                duration_days = round(float(duration_raw) / 1440, 4)  # minutes -> days
            except (ValueError, TypeError):
                duration_days = None
        rows.append({
            "wikidata_id": wikidata_id,
            "name": r.get("missionLabel", {}).get("value"),
            "launch_date": r.get("launch_date", {}).get("value", "")[:10] or None,
            "end_date": r.get("end_date", {}).get("value", "")[:10] or None,
            "operator": r.get("operatorLabel", {}).get("value"),
            "destination": r.get("destinationLabel", {}).get("value"),
            "launch_site": r.get("launch_siteLabel", {}).get("value"),
            "vehicle": r.get("vehicleLabel", {}).get("value"),
            "crew_count": (
                int(float(r.get("crewCount", {}).get("value")))
                if r.get("crewCount", {}).get("value") else None
            ),
            "duration_days": duration_days,
            "outcome": r.get("outcomeLabel", {}).get("value"),
        })

    df = pd.DataFrame(rows)

    # Deduplicate: keep the row with the most non-null fields per wikidata_id
    df["_non_null"] = df.notna().sum(axis=1)
    df = df.sort_values("_non_null", ascending=False).drop_duplicates(
        subset=["wikidata_id"], keep="first"
    ).drop(columns=["_non_null"])

    # Drop entries with no real name (bare Q-IDs = junk Wikidata entities)
    df = df[~df["name"].str.match(r"^Q\d+$", na=False)]

    return df


def main():
    df = fetch_missions()

    # Clean string columns
    for col in ["name", "operator", "destination", "launch_site", "vehicle", "outcome"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
            )

    # Derive launch_year for stats
    df["launch_year"] = pd.to_datetime(df["launch_date"], errors="coerce").dt.year

    df = df.sort_values("launch_date", na_position="last").reset_index(drop=True)
    print(f"  {len(df):,} unique missions")

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # ── Domain-specific stats for README ─────────────────────────────
    n = len(df)
    n_with_date = int(df["launch_date"].notna().sum()) if "launch_date" in df.columns else 0
    n_crewed = int((df["crew_count"].fillna(0) > 0).sum()) if "crew_count" in df.columns else 0
    n_destinations = int(df["destination"].nunique()) if "destination" in df.columns else 0
    if "operator" in df.columns:
        top_operators = df["operator"].value_counts().head(5)
        top_operators_str = ", ".join(f"{op} ({cnt:,})" for op, cnt in top_operators.items())
    else:
        top_operators_str = "N/A"

    quick_stats = f"""\
- **{n:,}** total missions in the database
- **{n_with_date}** with known launch dates
- **{n_crewed}** crewed missions
- **{n_destinations}** unique destinations
- Top operators: {top_operators_str}"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/space-missions", split="train")
df = ds.to_pandas()

# Missions by operator
if "operator" in df.columns:
    print(df["operator"].value_counts().head(10))

# Launches per decade
import matplotlib.pyplot as plt
df["decade"] = (df["launch_year"] // 10) * 10
df.dropna(subset=["decade"]).groupby("decade").size().plot(kind="bar")
plt.ylabel("Number of Missions")
plt.title("Space Missions by Decade")
plt.tight_layout()
plt.show()

# Crewed vs uncrewed by operator
if "crew_count" in df.columns and "operator" in df.columns:
    df["crewed"] = df["crew_count"].fillna(0) > 0
    top = df["operator"].value_counts().head(8).index
    df[df["operator"].isin(top)].groupby(["operator", "crewed"]).size().unstack().plot(kind="bar")
    plt.title("Crewed vs Uncrewed by Operator")
    plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Space Missions Database",
        description=DESCRIPTION,
        license="cc0-1.0",
        tags=["space", "missions", "spaceflight", "wikidata",
              "open-data", "tabular-data", "parquet"],
        source_url="https://www.wikidata.org/wiki/Wikidata:WikiProject_Spaceflight",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/space-probe-and-mission-datasets-69c3fe82d410a42b1e313167",
        banner={
            "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e001386/GSFC_20171208_Archive_e001386~medium.jpg",
            "alt": "Blue Marble — Earth from space as photographed by Suomi NPP satellite",
            "credit": "NASA/GSFC/Suomi NPP",
        },
        related_datasets=[
            "juliensimon/astronaut-database",
            "juliensimon/space-launch-log",
            "juliensimon/spacecraft-database",
            "juliensimon/deep-space-probes",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=["crew_count", "duration_days", "launch_year"],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="space_missions.parquet",
            min_rows=5000,
            expected_columns=["name"],
            critical_columns=["name"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update space missions database: {n:,} missions",
        )
    print("Done.")


if __name__ == "__main__":
    main()
