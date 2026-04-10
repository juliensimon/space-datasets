#!/usr/bin/env python3
"""Fetch astronomer database from Wikidata and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

from dataset_images import banner_markdown, download_banner
from validate import check_dataset


HF_REPO = "juliensimon/astronomer-database"

WIKIDATA_URL = "https://query.wikidata.org/sparql"
HEADERS = {"User-Agent": "space-datasets/1.0 (https://github.com/juliensimon/space-datasets)"}

MAX_RETRIES = 3

# Pass 1: core person data (lightweight, no multi-valued JOINs)
SPARQL_CORE = """
SELECT ?person ?personLabel ?birth ?death ?sexLabel ?nationalityLabel
WHERE {
  ?person wdt:P106 wd:Q11063.
  ?person wdt:P31 wd:Q5.
  OPTIONAL { ?person wdt:P569 ?birth. }
  OPTIONAL { ?person wdt:P570 ?death. }
  OPTIONAL { ?person wdt:P21 ?sex. }
  OPTIONAL { ?person wdt:P27 ?nationality. }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,mul". }
}
"""

# Pass 2: multi-valued properties aggregated per person
SPARQL_ENRICHMENT = """
SELECT ?person
       (GROUP_CONCAT(DISTINCT ?employerLabel; separator="; ") AS ?employers)
       (GROUP_CONCAT(DISTINCT ?awardLabel; separator="; ") AS ?awards)
       (GROUP_CONCAT(DISTINCT ?fieldLabel; separator="; ") AS ?fields)
WHERE {
  ?person wdt:P106 wd:Q11063.
  ?person wdt:P31 wd:Q5.
  OPTIONAL { ?person wdt:P108 ?employer.
             ?employer rdfs:label ?employerLabel. FILTER(LANG(?employerLabel) = "en") }
  OPTIONAL { ?person wdt:P166 ?award.
             ?award rdfs:label ?awardLabel. FILTER(LANG(?awardLabel) = "en") }
  OPTIONAL { ?person wdt:P101 ?field.
             ?field rdfs:label ?fieldLabel. FILTER(LANG(?fieldLabel) = "en") }
}
GROUP BY ?person
"""


def _query_wikidata(sparql, label="query"):
    """Run a SPARQL query with retries."""
    import time
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(
                WIKIDATA_URL,
                params={"query": sparql, "format": "json"},
                headers=HEADERS,
                timeout=180,
            )
            resp.raise_for_status()
            results = resp.json()["results"]["bindings"]
            print(f"  {label}: {len(results):,} rows")
            return results
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                wait = 30 * (attempt + 1)
                print(f"  {label} attempt {attempt + 1} failed ({e}), retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise


def fetch_astronomers() -> pd.DataFrame:
    """Query Wikidata SPARQL for all astronomers (two-pass for reliability)."""
    print("Querying Wikidata for astronomers...")

    # Pass 1: core person data
    results = _query_wikidata(SPARQL_CORE, "core")

    rows = []
    for r in results:
        wikidata_id = r.get("person", {}).get("value", "").rsplit("/", 1)[-1]
        rows.append({
            "wikidata_id": wikidata_id,
            "name": r.get("personLabel", {}).get("value"),
            "birth_date": r.get("birth", {}).get("value", "")[:10] or None,
            "death_date": r.get("death", {}).get("value", "")[:10] or None,
            "sex": r.get("sexLabel", {}).get("value"),
            "nationality": r.get("nationalityLabel", {}).get("value"),
        })

    df = pd.DataFrame(rows)

    # Deduplicate: multiple nationalities create duplicate rows
    df = df.drop_duplicates(subset=["wikidata_id"], keep="first")

    # Pass 2: enrichment (employers, awards, fields)
    import time
    time.sleep(2)
    try:
        enrich = _query_wikidata(SPARQL_ENRICHMENT, "enrichment")
        enrich_map = {}
        for r in enrich:
            qid = r.get("person", {}).get("value", "").rsplit("/", 1)[-1]
            enrich_map[qid] = {
                "employers": r.get("employers", {}).get("value") or None,
                "awards": r.get("awards", {}).get("value") or None,
                "fields_of_work": r.get("fields", {}).get("value") or None,
            }
        df["employers"] = df["wikidata_id"].map(lambda q: (enrich_map.get(q) or {}).get("employers"))
        df["awards"] = df["wikidata_id"].map(lambda q: (enrich_map.get(q) or {}).get("awards"))
        df["fields_of_work"] = df["wikidata_id"].map(lambda q: (enrich_map.get(q) or {}).get("fields_of_work"))
    except Exception as e:
        print(f"  Enrichment query failed ({e}), skipping employers/awards/fields")
        df["employers"] = pd.NA
        df["awards"] = pd.NA
        df["fields_of_work"] = pd.NA

    # Drop entries with no real name (bare Q-IDs = junk Wikidata entities)
    df = df[~df["name"].str.match(r"^Q\d+$", na=False)]

    return df


def main():
    df = fetch_astronomers()

    # Clean string columns
    for col in ["name", "sex", "nationality", "employers", "awards", "fields_of_work"]:
        df[col] = df[col].astype(str).str.strip().replace(
            {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
        )

    # Derive birth_year for stats
    df["birth_year"] = pd.to_datetime(df["birth_date"], errors="coerce").dt.year

    df = df.sort_values("name").reset_index(drop=True)
    print(f"  {len(df):,} unique astronomers")

    check_dataset(df, "astronomers", min_rows=5000,
                  expected_columns=["name", "nationality"],
                  critical_columns=["name"])

    # Stats for README
    n = len(df)
    n_nationalities = int(df["nationality"].nunique())
    top_nations = df["nationality"].value_counts().head(5)
    top_nations_str = ", ".join(f"{nat} ({cnt:,})" for nat, cnt in top_nations.items())
    n_female = int((df["sex"] == "female").sum())
    n_male = int((df["sex"] == "male").sum())
    n_with_fields = int(df["fields_of_work"].notna().sum())
    n_with_awards = int(df["awards"].notna().sum())

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "astronomers.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_kb = out.stat().st_size / 1024
        print(f"  {size_kb:.0f} KB parquet")

        banner_file = download_banner("astronomers", tmp)
        banner_md = banner_markdown("astronomers", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc0-1.0
pretty_name: "Astronomer Database"
language:
  - en
description: >-
  A comprehensive database of astronomers throughout history, sourced from Wikidata.
  {n:,} astronomers from {n_nationalities} countries with fields of work,
  awards, and employer history.
size_categories:
  - 10K<n<100K
task_categories:
  - tabular-classification
tags:
  - space
  - astronomy
  - astronomers
  - wikidata
  - open-data
  - tabular-data
  - parquet
configs:
  - config_name: default
    default: true
    data_files:
      - split: train
        path: data/astronomers.parquet
---

# Astronomer Database
{banner_md}
*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

Complete database of astronomers throughout history — **{n:,}** individuals
from **{n_nationalities}** countries, sourced from [Wikidata](https://www.wikidata.org/).

## Dataset description

From ancient stargazers to modern astrophysicists, this dataset captures the lives and
work of astronomers across the ages. It spans from historical figures like Galileo Galilei
and Johannes Kepler to contemporary researchers studying gravitational waves, exoplanets,
and the large-scale structure of the universe.

The dataset includes birth/death dates, sex, nationality, employer history (universities,
observatories, research institutions), awards received (Nobel Prize, etc.), and fields
of work (cosmology, planetary science, stellar physics, etc.). This enables historical
analysis of the astronomy profession, diversity-in-STEM research, and bibliometric studies
of scientific communities.

Sourced from Wikidata's structured knowledge base (property P106=Q11063 for
occupation: astronomer), which is maintained by the Wikipedia/Wikidata community
and updated continuously.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `wikidata_id` | string | Wikidata entity ID (e.g. "Q935" for Galileo Galilei); resolves to https://www.wikidata.org/wiki/Q935 — links to full biographical and bibliographic data including publications, awards, and institutional affiliations |
| `name` | string | Full name in English as recorded in Wikidata (Latin transliteration for non-Latin scripts) |
| `birth_date` | string | Date of birth in ISO 8601 format (YYYY-MM-DD); null for ancient or medieval astronomers whose birth year is uncertain, and occasionally for modern astronomers with private records |
| `death_date` | string | Date of death in ISO 8601 format (YYYY-MM-DD); null for living astronomers |
| `sex` | string | Recorded biological sex; values: "male", "female"; null if not recorded in Wikidata |
| `nationality` | string | Country of primary professional affiliation or citizenship (e.g. "United States", "Germany"); uses full English country name; may differ from country of birth |
| `employers` | string | Universities, observatories, and research institutes where the astronomer has worked, semicolon-separated (e.g. "Harvard University;Smithsonian Astrophysical Observatory"); null if no employer is recorded in Wikidata |
| `awards` | string | Honours and prizes received, semicolon-separated (e.g. "Nobel Prize in Physics;Kavli Prize"); null if no awards are recorded in Wikidata |
| `fields_of_work` | string | Primary research specializations, semicolon-separated (e.g. "astrophysics;cosmology;stellar astronomy"); drawn from Wikidata property P101; null if not categorized |
| `birth_year` | int | Integer year extracted from `birth_date`; enables era-based filtering (e.g. pre-telescopic vs. modern) when full date is unavailable; null only if birth date is entirely unknown |

## Quick stats

- **{n:,}** astronomers from **{n_nationalities}** countries
- **{n_male:,}** male, **{n_female:,}** female
- **{n_with_fields:,}** with recorded fields of work
- **{n_with_awards:,}** with recorded awards
- Top nationalities: {top_nations_str}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/astronomer-database", split="train")
df = ds.to_pandas()

# Astronomers by nationality
print(df["nationality"].value_counts().head(10))

# Female astronomers
female = df[df["sex"] == "female"]
print(f"{{len(female):,}} female astronomers")

# Astronomers by field
cosmologists = df[df["fields_of_work"].str.contains("cosmology", case=False, na=False)]
print(f"{{len(cosmologists):,}} cosmologists")

# Award winners
nobel = df[df["awards"].str.contains("Nobel", na=False)]
print(f"{{len(nobel):,}} Nobel Prize recipients")

# University affiliation
cambridge = df[df["employers"].str.contains("Cambridge", na=False)]
print(f"{{len(cambridge):,}} Cambridge-affiliated astronomers")
```

## Data source

[Wikidata](https://www.wikidata.org/) SPARQL endpoint. Astronomers identified via
property P106 (occupation) = Q11063 (astronomer). Data is community-curated and
updated continuously by Wikipedia editors worldwide.

## Update schedule

Quarterly (January, April, July, October). Re-run manually at any time to pick up new entries.

## Related datasets

- [astronaut-database](https://huggingface.co/datasets/juliensimon/astronaut-database) — Every person who has traveled to space
- [observatory-database](https://huggingface.co/datasets/juliensimon/observatory-database) — Astronomical observatories worldwide

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/astronomer-database) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{astronomer_database,
  author = {{Simon, Julien}},
  title = {{Astronomer Database}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/astronomer-database}},
  note = {{Sourced from Wikidata (CC0)}}
}}
```

## License

[CC0-1.0](https://creativecommons.org/publicdomain/zero/1.0/) (Wikidata content is public domain)
""")

        print("Uploading to HF...")
        commit_msg = f"Update astronomer database: {n:,} astronomers"
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
