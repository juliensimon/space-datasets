#!/usr/bin/env python3
"""Fetch space agency database from Wikidata and upload to HF.

Source: Wikidata SPARQL endpoint — Q31855 (space agency) class hierarchy
plus a supplementary label-based filter for programs not yet formally classified.
"""

import time

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

HF_REPO = "juliensimon/space-agency-database"

WIKIDATA_URL = "https://query.wikidata.org/sparql"
HEADERS = {"User-Agent": "space-datasets/1.0 (https://github.com/juliensimon/space-datasets)"}

SPARQL_QUERY = """
SELECT ?agency ?agencyLabel ?countryLabel
       ?founded ?headquarters ?headLabel
       ?budget ?employees ?websiteUrl
WHERE {
  ?agency wdt:P31/wdt:P279* wd:Q31855.
  { ?agency wdt:P101 wd:Q5916 }
  UNION { ?agency rdfs:label ?l. FILTER(LANG(?l)="en") FILTER(CONTAINS(LCASE(?l), "space")) }
  OPTIONAL { ?agency wdt:P17 ?country. }
  OPTIONAL { ?agency wdt:P571 ?founded. }
  OPTIONAL { ?agency wdt:P159 ?hq.
             ?hq rdfs:label ?headquarters. FILTER(LANG(?headquarters)="en") }
  OPTIONAL { ?agency wdt:P35 ?head. }
  OPTIONAL { ?agency wdt:P2769 ?budget. }
  OPTIONAL { ?agency wdt:P1128 ?employees. }
  OPTIONAL { ?agency wdt:P856 ?websiteUrl. }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,mul". }
}
"""

# Known false positives: agencies matched by the "space" label filter
# that are clearly not space agencies (government bodies, libraries, etc.)
FALSE_POSITIVE_KEYWORDS = [
    "library", "museum", "hospital", "school", "university", "college",
    "ministry of", "department of", "committee", "council of", "court",
    "bureau of statistics", "office of", "revenue", "tax", "customs",
    "immigration", "police", "military", "army", "navy", "air force",
    "intelligence", "corrections", "prison", "fire department",
    "transport authority", "highway", "road", "water authority",
    "electricity", "power authority", "gas authority",
]

# ── Column descriptions for README schema table ───────────────────────────────────
COLUMN_DESCRIPTIONS = {
    "wikidata_id": "Wikidata entity ID (e.g. 'Q23548' for NASA); resolves to https://www.wikidata.org/wiki/Q23548 — links to the agency's full knowledge graph entry including founding date, budget history, and program list",
    "name": "Official agency name in English (e.g. 'NASA', 'ESA', 'ISRO', 'Roscosmos'); canonical form as recorded in Wikidata",
    "country": "Country or intergovernmental organization that operates the agency (e.g. 'United States', 'European Union'); uses full English name",
    "founded": "Date the agency was formally established, ISO 8601 (YYYY-MM-DD); null if only a founding year is known (see founded_year)",
    "headquarters": "City or region where the agency's primary administrative office is located (e.g. 'Washington, D.C.', 'Paris'); null if not recorded in Wikidata",
    "head": "Name of the current or most-recently recorded director or administrator; null if leadership data is absent from Wikidata",
    "budget_usd": "Most recently recorded annual operating budget converted to US dollars; null for agencies that do not publicly disclose budget figures; values are point-in-time and may lag by several years",
    "employees": "Most recently recorded staff headcount (full-time equivalents); null if workforce data is absent from Wikidata",
    "website": "Official agency website URL (e.g. 'https://www.nasa.gov'); null if not recorded in Wikidata",
    "founded_year": "Integer year extracted from founded; enables numeric filtering when full date is unavailable; null only if founding date is entirely unknown",
}

# ── Dataset description ──────────────────────────────────────────────────────────────────
DESCRIPTION = """\
Database of space agencies and related governmental space organizations worldwide, \
sourced from Wikidata.

From NASA and Roscosmos to emerging national programs in Asia, Africa, and Latin America, \
this dataset catalogs every governmental space agency and related intergovernmental \
organization known to Wikidata. It covers founding dates, headquarters locations, \
leadership, annual budgets (where available), workforce sizes, and official websites.

The dataset enables comparative analysis of national space programs, tracking the \
globalization of space activity, and identifying investment patterns across the space \
sector. It complements the spacecraft-database (what each agency has flown) and the \
astronaut-database (who has flown for them).

Sourced from Wikidata's structured knowledge base using the Q31855 (space agency) class \
hierarchy plus a supplementary label-based filter for programs not yet formally classified. \
Data is community-curated and updated continuously.
"""


def fetch_agencies() -> pd.DataFrame:
    """Query Wikidata SPARQL for all space agencies (3 retries with backoff)."""
    print("Querying Wikidata for space agencies...")
    for attempt in range(3):
        try:
            resp = requests.get(
                WIKIDATA_URL,
                params={"query": SPARQL_QUERY, "format": "json"},
                headers=HEADERS,
                timeout=120,
            )
            resp.raise_for_status()
            break
        except Exception as exc:
            if attempt < 2:
                wait = 30 * (2 ** attempt)
                print(f"  Wikidata attempt {attempt + 1}/3 failed: {exc}; retrying in {wait}s...")
                time.sleep(wait)
            else:
                print(f"  Wikidata failed after 3 attempts: {exc}")
                raise

    results = resp.json()["results"]["bindings"]
    print(f"  {len(results):,} raw rows from Wikidata")

    rows = []
    for r in results:
        wikidata_id = r.get("agency", {}).get("value", "").rsplit("/", 1)[-1]
        budget_raw = r.get("budget", {}).get("value")
        budget_usd = None
        if budget_raw:
            try:
                budget_usd = float(budget_raw)
            except (ValueError, TypeError):
                pass

        employees_raw = r.get("employees", {}).get("value")
        employees = None
        if employees_raw:
            try:
                employees = int(float(employees_raw))
            except (ValueError, TypeError):
                pass

        rows.append({
            "wikidata_id": wikidata_id,
            "name": r.get("agencyLabel", {}).get("value"),
            "country": r.get("countryLabel", {}).get("value"),
            "founded": r.get("founded", {}).get("value", "")[:10] or None,
            "headquarters": r.get("headquarters", {}).get("value"),
            "head": r.get("headLabel", {}).get("value"),
            "budget_usd": budget_usd,
            "employees": employees,
            "website": r.get("websiteUrl", {}).get("value"),
        })

    df = pd.DataFrame(rows)

    # Deduplicate: multiple optional fields can create duplicate rows per agency.
    df["_score"] = df.notna().sum(axis=1)
    df = df.sort_values("_score", ascending=False).drop_duplicates(
        subset=["wikidata_id"], keep="first"
    ).drop(columns=["_score"])

    # Drop bare Q-ID names (junk Wikidata entities with no English label)
    df = df[~df["name"].str.match(r"^Q\d+$", na=False)]

    # Remove obvious false positives from the "space" label UNION branch
    name_lower = df["name"].str.lower().fillna("")
    mask_fp = pd.Series(False, index=df.index)
    for kw in FALSE_POSITIVE_KEYWORDS:
        mask_fp |= name_lower.str.contains(kw, regex=False)
    n_removed = int(mask_fp.sum())
    if n_removed:
        print(f"  Removed {n_removed} false-positive rows (non-space agencies)")
    df = df[~mask_fp]

    return df


def main():
    df = fetch_agencies()

    # Parse founded year
    df["founded_year"] = pd.to_datetime(df["founded"], errors="coerce").dt.year

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    df = df.sort_values("name").reset_index(drop=True)
    print(f"  {len(df):,} unique space agencies")

    # ── Domain-specific stats for README ─────────────────────────────────────────────
    n = len(df)
    n_countries = int(df["country"].nunique())
    top_countries = df["country"].value_counts().head(5)
    top_countries_str = ", ".join(
        f"{c} ({cnt:,})" for c, cnt in top_countries.items()
    )
    n_with_budget = int(df["budget_usd"].notna().sum())
    n_with_employees = int(df["employees"].notna().sum())

    # Oldest agency
    oldest_row = df.dropna(subset=["founded_year"]).nsmallest(1, "founded_year")
    if not oldest_row.empty:
        oldest_name = oldest_row.iloc[0]["name"]
        oldest_year = int(oldest_row.iloc[0]["founded_year"])
        oldest_str = f"{oldest_name} ({oldest_year})"
    else:
        oldest_str = "N/A"

    # Largest budget
    if n_with_budget > 0:
        max_budget_row = df.nlargest(1, "budget_usd").iloc[0]
        max_budget_name = max_budget_row["name"]
        max_budget_val = float(max_budget_row["budget_usd"])
        if max_budget_val >= 1e9:
            max_budget_str = f"{max_budget_name} (${max_budget_val/1e9:.1f}B)"
        else:
            max_budget_str = f"{max_budget_name} (${max_budget_val/1e6:.0f}M)"
    else:
        max_budget_str = "N/A"

    quick_stats = f"""\
- **{n:,}** space agencies from **{n_countries}** countries
- Oldest agency: {oldest_str}
- Largest budget: {max_budget_str}
- **{n_with_budget:,}** agencies with budget data, **{n_with_employees:,}** with employee counts
- Top countries: {top_countries_str}"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/space-agency-database", split="train")
df = ds.to_pandas()

# Agencies by country
print(df["country"].value_counts().head(10))

# Agencies with known budgets, sorted descending
budget_df = df.dropna(subset=["budget_usd"]).sort_values("budget_usd", ascending=False)
print(budget_df[["name", "country", "budget_usd"]].head(10))

# Agencies founded after 2000 (new space era)
new_era = df[df["founded_year"] >= 2000].sort_values("founded_year")
print(new_era[["name", "country", "founded_year"]])

# Founding timeline
import matplotlib.pyplot as plt
df.dropna(subset=["founded_year"]).hist("founded_year", bins=30)
plt.xlabel("Year Founded")
plt.ylabel("Count")
plt.title("Space Agency Founding Timeline")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Space Agency Database",
        description=DESCRIPTION,
        tags=["space", "space-agencies", "wikidata",
              "open-data", "tabular-data", "parquet"],
        source_url="https://www.wikidata.org/",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/space-essentials-69cbafd7ea046a10eff11405",
        banner={
            "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e001386/GSFC_20171208_Archive_e001386~medium.jpg",
            "alt": "Blue Marble — high-definition image of Earth from space",
            "credit": "NASA/GSFC/Suomi NPP",
        },
        license="cc0-1.0",
        related_datasets=[
            "juliensimon/spacecraft-database",
            "juliensimon/gcat-launch-vehicles",
            "juliensimon/astronaut-database",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=["budget_usd"],
            integer=["employees", "founded_year"],
            strings=["name", "country", "headquarters", "head", "website"],
        )
        # Wikidata optional fields may be entirely null; drop to pass validation
        for col in ["head"]:
            if col in df.columns and df[col].isna().all():
                df = df.drop(columns=[col])
        p.publish(
            df,
            filename="space-agencies.parquet",
            min_rows=50,
            expected_columns=["name", "country"],
            critical_columns=["name"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update space agency database: {n:,} agencies",
        )
    print("Done.")


if __name__ == "__main__":
    main()
