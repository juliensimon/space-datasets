#!/usr/bin/env python3
"""Fetch space agency database from Wikidata and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset


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


def fetch_agencies() -> pd.DataFrame:
    """Query Wikidata SPARQL for all space agencies."""
    print("Querying Wikidata for space agencies...")
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
    # Keep the row with the most non-null fields.
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

    # Clean string columns
    for col in ["name", "country", "headquarters", "head", "website"]:
        df[col] = df[col].astype(str).str.strip().replace(
            {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
        )

    # Cast numerics with nullable types
    df["budget_usd"] = pd.to_numeric(df["budget_usd"], errors="coerce").astype("Float64")
    df["employees"] = pd.to_numeric(df["employees"], errors="coerce").astype("Int64")

    # Parse founded year
    df["founded_year"] = pd.to_datetime(df["founded"], errors="coerce").dt.year

    df = df.sort_values("name").reset_index(drop=True)
    print(f"  {len(df):,} unique space agencies")

    check_dataset(df, "space-agencies", min_rows=50,
                  expected_columns=["name", "country"],
                  critical_columns=["name"])

    # Stats for README
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

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "space-agencies.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_kb = out.stat().st_size / 1024
        print(f"  {size_kb:.0f} KB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc0-1.0
pretty_name: "Space Agency Database"
language:
  - en
description: >-
  Database of space agencies and related governmental space organizations
  worldwide, sourced from Wikidata. {n:,} agencies from {n_countries} countries
  with founding dates, headquarters, leadership, budgets, and websites.
size_categories:
  - n<1K
task_categories:
  - tabular-classification
tags:
  - space
  - space-agencies
  - wikidata
  - open-data
  - tabular-data
  - parquet
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/space-agencies.parquet
---

# Space Agency Database

*Part of the [Orbital Mechanics Datasets](https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994) collection on Hugging Face.*

Complete database of space agencies and governmental space organizations worldwide — **{n:,}** agencies from **{n_countries}** countries, sourced from [Wikidata](https://www.wikidata.org/).

## Dataset description

From NASA and Roscosmos to emerging national programs in Asia, Africa, and Latin America, this dataset catalogs every governmental space agency and related intergovernmental organization known to Wikidata. It covers founding dates, headquarters locations, leadership, annual budgets (where available), workforce sizes, and official websites.

The dataset enables comparative analysis of national space programs, tracking the globalization of space activity, and identifying investment patterns across the space sector. It complements the spacecraft-database (what each agency has flown) and the astronaut-database (who has flown for them).

Sourced from Wikidata's structured knowledge base using the Q31855 (space agency) class hierarchy plus a supplementary label-based filter for programs not yet formally classified. Data is community-curated and updated continuously.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `wikidata_id` | string | Wikidata entity ID (e.g. Q23548) |
| `name` | string | Agency name |
| `country` | string | Country of operation |
| `founded` | string | Founding date (YYYY-MM-DD) |
| `headquarters` | string | Headquarters city/location |
| `head` | string | Head of agency |
| `budget_usd` | float | Annual budget in USD |
| `employees` | int | Number of employees |
| `website` | string | Official website URL |
| `founded_year` | int | Founding year (derived) |

## Quick stats

- **{n:,}** space agencies from **{n_countries}** countries
- Oldest agency: {oldest_str}
- Largest budget: {max_budget_str}
- **{n_with_budget:,}** agencies with budget data, **{n_with_employees:,}** with employee counts
- Top countries: {top_countries_str}

## Usage

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

# Agencies by country with budgets
by_country = df.groupby("country")["budget_usd"].sum().sort_values(ascending=False)
print(by_country.head(10))
```

## Data source

[Wikidata](https://www.wikidata.org/) SPARQL endpoint. Agencies identified via the Q31855 (space agency) class hierarchy plus a supplementary label-based filter. Data is community-curated by the [WikiProject Spaceflight](https://www.wikidata.org/wiki/Wikidata:WikiProject_Spaceflight) community.

## Update schedule

Quarterly (January, April, July, October). Re-run manually at any time via `workflow_dispatch`.

## Related datasets

- [spacecraft-database](https://huggingface.co/datasets/juliensimon/spacecraft-database) — spacecraft operated by these agencies
- [gcat-launch-vehicles](https://huggingface.co/datasets/juliensimon/gcat-launch-vehicles) — launch vehicles used by space agencies
- [astronaut-database](https://huggingface.co/datasets/juliensimon/astronaut-database) — astronauts who flew for these agencies

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/space-agency-database) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{space_agency_database,
  author = {{Simon, Julien}},
  title = {{Space Agency Database}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/space-agency-database}},
  note = {{Sourced from Wikidata (CC0)}}
}}
```

## License

[CC0-1.0](https://creativecommons.org/publicdomain/zero/1.0/) (Wikidata content is public domain)
""")

        print("Uploading to HF...")
        commit_msg = f"Update space agency database: {n:,} agencies"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={n}\n")
    print("Done.")


if __name__ == "__main__":
    main()
