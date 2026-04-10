#!/usr/bin/env python3
"""Fetch Physics Nobel Laureates from Wikidata and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

from dataset_images import banner_markdown, download_banner
from validate import check_dataset


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
    # Score by number of non-null fields to pick the richest row
    df["_completeness"] = df.notna().sum(axis=1)
    df = df.sort_values("_completeness", ascending=False).drop_duplicates(
        subset=["wikidata_id"], keep="first"
    ).drop(columns=["_completeness"])

    # Drop entries with no real name (bare Q-IDs = junk Wikidata entities)
    df = df[~df["name"].str.match(r"^Q\d+$", na=False)]

    return df


def main():
    df = fetch_laureates()

    # Clean string columns
    for col in ["name", "sex", "nationality", "employers", "fields_of_work", "cited_work"]:
        df[col] = df[col].astype(str).str.strip().replace(
            {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
        )

    # award_year as nullable integer
    df["award_year"] = pd.to_numeric(df["award_year"], errors="coerce").astype("Int64")

    # Derive birth_year for stats
    df["birth_year"] = pd.to_datetime(df["birth_date"], errors="coerce").dt.year.astype("Int64")

    df = df.sort_values(["award_year", "name"]).reset_index(drop=True)
    print(f"  {len(df):,} unique Physics Nobel Laureates")

    check_dataset(df, "physics-nobel", min_rows=100,
                  expected_columns=["name", "award_year"],
                  critical_columns=["name"])

    # Stats for README
    n = len(df)
    n_nationalities = int(df["nationality"].nunique())

    # By decade
    df["_decade"] = (df["award_year"] // 10 * 10).astype("Int64")
    by_decade = df.groupby("_decade").size()
    by_decade_str = ", ".join(
        f"{int(decade)}s ({cnt})" for decade, cnt in by_decade.items()
        if pd.notna(decade)
    )

    # By nationality (top 5)
    top_nations = df["nationality"].value_counts().head(5)
    top_nations_str = ", ".join(f"{nat} ({cnt})" for nat, cnt in top_nations.items())

    # Female laureates
    n_female = int((df["sex"] == "female").sum())

    df = df.drop(columns=["_decade"])

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "physics-nobel.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_kb = out.stat().st_size / 1024
        print(f"  {size_kb:.0f} KB parquet")

        banner_file = download_banner("physics-nobel", tmp)
        banner_md = banner_markdown("physics-nobel", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc0-1.0
pretty_name: "Physics Nobel Laureates"
language:
  - en
description: >-
  All Physics Nobel Prize laureates sourced from Wikidata.
  {n:,} laureates with biographical data, fields of work,
  affiliated institutions, and cited works.
size_categories:
  - n<1K
task_categories:
  - tabular-classification
tags:
  - space
  - physics
  - nobel-prize
  - wikidata
  - open-data
  - tabular-data
  - parquet
configs:
  - config_name: default
    default: true
    data_files:
      - split: train
        path: data/physics-nobel.parquet
---

# Physics Nobel Laureates
{banner_md}
*Part of the [Physics Datasets](https://huggingface.co/collections/juliensimon/physics-datasets-69c2d4682d37dfdb77447bd7) collection on Hugging Face.*

Complete database of every Physics Nobel Prize laureate — **{n:,}** scientists,
sourced from [Wikidata](https://www.wikidata.org/).

## Dataset description

The Nobel Prize in Physics has been awarded since 1901, recognizing landmark contributions
to our understanding of the universe — from the discovery of X-rays and quantum mechanics
through nuclear physics, particle physics, semiconductors, lasers, and gravitational waves.
This dataset records every laureate from Wilhelm Röntgen (1901) to the present.

Each row represents one laureate and includes birth/death dates, sex, nationality,
employer history (universities and research institutions), fields of work, and the
cited work or discovery for which the prize was awarded. This enables historical analysis
of Nobel Prize trends, gender and nationality diversity in physics, and institutional
affiliation patterns.

Sourced from Wikidata's structured knowledge base (property P166=Q38104 for
Nobel Prize in Physics), maintained by the Wikipedia/Wikidata community and
updated as new laureates are announced each October.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `wikidata_id` | string | Wikidata entity ID for the laureate (e.g. "Q7240" for Max Planck); use as stable cross-reference key |
| `name` | string | Full legal name of the laureate as recorded in Wikidata |
| `birth_date` | string | Date of birth in ISO 8601 format (YYYY-MM-DD); null for historical figures with only a birth year |
| `death_date` | string | Date of death in ISO 8601 format (YYYY-MM-DD); null if laureate is still living |
| `sex` | string | Sex as recorded in Wikidata: "male" or "female" |
| `nationality` | string | Nationality at time of award or primary nationality (may be comma-separated for dual nationals) |
| `award_year` | int | Year the Nobel Prize in Physics was awarded (1901–present); up to 3 laureates may share a prize year |
| `employers` | string | Semicolon-separated list of known employers (universities, labs, research institutes) at time of award or career |
| `fields_of_work` | string | Semicolon-separated physics subfields (e.g. "quantum mechanics; atomic physics; condensed matter") |
| `cited_work` | string | Official Nobel Committee citation describing the discovery or contribution that earned the prize |
| `birth_year` | int | Year of birth derived from birth_date; used for age-at-award calculations |

## Quick stats

- **{n:,}** Physics Nobel Laureates from **{n_nationalities}** nationalities
- **{n_female:,}** female laureates
- Awards by decade: {by_decade_str}
- Top nationalities: {top_nations_str}

## Usage

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
df["decade"] = (df["award_year"] // 10 * 10).astype("Int64")
print(df.groupby("decade").size())

# Quantum physicists
quantum = df[df["fields_of_work"].str.contains("quantum", case=False, na=False)]
print(f"{{len(quantum):,}} laureates with quantum physics in their fields")
```

## Data source

[Wikidata](https://www.wikidata.org/) SPARQL endpoint. Laureates identified via
property P166 (award received) = Q38104 (Nobel Prize in Physics). Data is
community-curated and updated annually when new laureates are announced.

## Update schedule

Quarterly (January, April, July, October). The October run captures each year's
new laureates shortly after announcement.

## Related datasets

- [astronomer-database](https://huggingface.co/datasets/juliensimon/astronomer-database) -- Astronomers from Wikidata
- [pdg-particle-properties](https://huggingface.co/datasets/juliensimon/pdg-particle-properties) -- Particle Data Group properties

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/physics-nobel-laureates) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{physics_nobel_laureates,
  author = {{Simon, Julien}},
  title = {{Physics Nobel Laureates}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/physics-nobel-laureates}},
  note = {{Sourced from Wikidata (CC0)}}
}}
```

## License

[CC0-1.0](https://creativecommons.org/publicdomain/zero/1.0/) (Wikidata content is public domain)
""")

        print("Uploading to HF...")
        commit_msg = f"Update Physics Nobel Laureates: {n:,} laureates"
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
