#!/usr/bin/env python3
"""Fetch Physics Nobel Laureates from Wikidata and upload to HF.

Source: Wikidata SPARQL endpoint — property P166 = Q38104 (Nobel Prize in Physics).
"""

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

HF_REPO = "juliensimon/physics-nobel-laureates"

WIKIDATA_URL = "https://query.wikidata.org/sparql"
HEADERS = {"User-Agent": "space-datasets/1.0 (https://github.com/juliensimon/space-datasets)"}

SPARQL_QUERY = """
SELECT ?person ?personLabel ?birth ?death ?sexLabel
       ?nationalityLabel ?year
       (GROUP_CONCAT(DISTINCT ?employerLabel; separator="; ") AS ?employers)
       (GROUP_CONCAT(DISTINCT ?fieldLabel; separator="; ") AS ?fields)
       ?workLabel
WHERE {
  ?person wdt:P166 wd:Q38104.
  ?person wdt:P31 wd:Q5.
  OPTIONAL { ?person wdt:P569 ?birth. }
  OPTIONAL { ?person wdt:P570 ?death. }
  OPTIONAL { ?person wdt:P21 ?sex. }
  OPTIONAL { ?person wdt:P27 ?nationality. }
  OPTIONAL { ?person p:P166 ?awardStmt.
             ?awardStmt ps:P166 wd:Q38104.
             ?awardStmt pq:P585 ?year. }
  OPTIONAL { ?person wdt:P108 ?employer.
             ?employer rdfs:label ?employerLabel. FILTER(LANG(?employerLabel) = "en") }
  OPTIONAL { ?person wdt:P101 ?field.
             ?field rdfs:label ?fieldLabel. FILTER(LANG(?fieldLabel) = "en") }
  OPTIONAL { ?person p:P166 ?awardStmt2.
             ?awardStmt2 ps:P166 wd:Q38104.
             ?awardStmt2 pq:P6208 ?work. }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,mul". }
}
GROUP BY ?person ?personLabel ?birth ?death ?sexLabel ?nationalityLabel ?year ?workLabel
"""

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "wikidata_id": "Wikidata entity ID for the laureate (e.g. 'Q7240' for Max Planck); stable cross-reference key for linking to Wikipedia and other knowledge bases",
    "name": "Full legal name of the laureate as recorded in Wikidata",
    "birth_date": "Date of birth in ISO 8601 format (YYYY-MM-DD); null for historical figures with only a birth year known",
    "death_date": "Date of death in ISO 8601 format (YYYY-MM-DD); null if laureate is still living",
    "sex": "Sex as recorded in Wikidata: 'male' or 'female'",
    "nationality": "Nationality at time of award or primary nationality; may reflect citizenship changes",
    "award_year": "Year the Nobel Prize in Physics was awarded (1901-present); up to 3 laureates may share a prize year",
    "employers": "Semicolon-separated list of known employers (universities, labs, research institutes) at time of award or career",
    "fields_of_work": "Semicolon-separated physics subfields (e.g. 'quantum mechanics; atomic physics; condensed matter')",
    "cited_work": "Official Nobel Committee citation describing the discovery or contribution that earned the prize",
    "birth_year": "Year of birth derived from birth_date; used for age-at-award calculations",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Complete database of every Physics Nobel Prize laureate, sourced from Wikidata. \
The Nobel Prize in Physics has been awarded since 1901, recognizing landmark \
contributions to our understanding of the universe -- from the discovery of X-rays \
and quantum mechanics through nuclear physics, particle physics, semiconductors, \
lasers, and gravitational waves.

Each row represents one laureate and includes birth/death dates, sex, nationality, \
employer history (universities and research institutions), fields of work, and the \
cited work or discovery for which the prize was awarded. This enables historical \
analysis of Nobel Prize trends, gender and nationality diversity in physics, and \
institutional affiliation patterns.

Sourced from Wikidata's structured knowledge base (property P166=Q38104 for \
Nobel Prize in Physics), maintained by the Wikipedia/Wikidata community and \
updated as new laureates are announced each October.
"""


def fetch_laureates() -> pd.DataFrame:
    """Query Wikidata SPARQL for all Physics Nobel Laureates."""
    print("Querying Wikidata for Physics Nobel Laureates...")
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
        wikidata_id = r.get("person", {}).get("value", "").rsplit("/", 1)[-1]

        # Parse award year from the xsd:dateTime or plain year string
        year_val = r.get("year", {}).get("value", "")
        award_year = None
        if year_val:
            try:
                award_year = int(year_val[:4])
            except (ValueError, IndexError):
                pass

        rows.append({
            "wikidata_id": wikidata_id,
            "name": r.get("personLabel", {}).get("value"),
            "birth_date": r.get("birth", {}).get("value", "")[:10] or None,
            "death_date": r.get("death", {}).get("value", "")[:10] or None,
            "sex": r.get("sexLabel", {}).get("value"),
            "nationality": r.get("nationalityLabel", {}).get("value"),
            "award_year": award_year,
            "employers": r.get("employers", {}).get("value") or None,
            "fields_of_work": r.get("fields", {}).get("value") or None,
            "cited_work": r.get("workLabel", {}).get("value") or None,
        })

    df = pd.DataFrame(rows)

    # Deduplicate on wikidata_id: keep most complete row
    df["_completeness"] = df.notna().sum(axis=1)
    df = df.sort_values("_completeness", ascending=False).drop_duplicates(
        subset=["wikidata_id"], keep="first"
    ).drop(columns=["_completeness"])

    # Drop entries with no real name (bare Q-IDs = junk Wikidata entities)
    df = df[~df["name"].str.match(r"^Q\d+$", na=False)]

    return df


def main():
    df = fetch_laureates()

    # award_year as nullable integer
    df["award_year"] = pd.to_numeric(df["award_year"], errors="coerce").astype("Int64")

    # Derive birth_year for stats
    df["birth_year"] = pd.to_datetime(df["birth_date"], errors="coerce").dt.year.astype("Int64")

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    df = df.sort_values(["award_year", "name"]).reset_index(drop=True)
    print(f"  {len(df):,} unique Physics Nobel Laureates")

    # ── Domain-specific stats for README ─────────────────────────────
    n = len(df)
    n_nationalities = int(df["nationality"].nunique())
    n_female = int((df["sex"] == "female").sum())

    # By decade
    decades = (df["award_year"] // 10 * 10).astype("Int64")
    by_decade = df.groupby(decades).size()
    by_decade_str = ", ".join(
        f"{int(decade)}s ({cnt})" for decade, cnt in by_decade.items()
        if pd.notna(decade)
    )

    # Top nationalities
    top_nations = df["nationality"].value_counts().head(5)
    top_nations_str = ", ".join(f"{nat} ({cnt})" for nat, cnt in top_nations.items())

    quick_stats = f"""\
- **{n:,}** Physics Nobel Laureates from **{n_nationalities}** nationalities
- **{n_female:,}** female laureates
- Awards by decade: {by_decade_str}
- Top nationalities: {top_nations_str}"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/physics-nobel-laureates", split="train")
df = ds.to_pandas()

# Laureates by nationality
print(df["nationality"].value_counts().head(10))

# Female laureates
female = df[df["sex"] == "female"]
print(female[["name", "award_year", "nationality"]])

# Awards by decade
import matplotlib.pyplot as plt
df["decade"] = (df["award_year"] // 10 * 10).astype("Int64")
counts = df.groupby("decade").size()
plt.bar(counts.index.astype(int), counts.values)
plt.xlabel("Decade")
plt.ylabel("Number of Laureates")
plt.title("Physics Nobel Prizes by Decade")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Physics Nobel Laureates",
        description=DESCRIPTION,
        tags=["space", "physics", "nobel-prize", "wikidata",
              "open-data", "tabular-data", "parquet"],
        source_url="https://www.wikidata.org/",
        license="cc0-1.0",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/physics-datasets-69c2d4682d37dfdb77447bd7",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA03519/PIA03519~small.jpg",
            "alt": "Cassiopeia A supernova remnant in X-ray, optical, and infrared light",
            "credit": "NASA/JPL-Caltech/STScI/CXC/SAO",
        },
        related_datasets=[
            "juliensimon/astronomer-database",
            "juliensimon/pdg-particle-properties",
        ],
    ) as p:
        df = p.clean(
            df,
            integer=["award_year", "birth_year"],
            strings=["name", "sex", "nationality", "employers",
                      "fields_of_work", "cited_work"],
        )
        p.publish(
            df,
            filename="physics_nobel_laureates.parquet",
            min_rows=100,
            expected_columns=["name", "award_year"],
            critical_columns=["name"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Physics Nobel Laureates: {n:,} laureates",
        )
    print("Done.")


if __name__ == "__main__":
    main()
