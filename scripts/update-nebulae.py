#!/usr/bin/env python3
"""Fetch nebula catalog from Wikidata and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

from dataset_images import banner_markdown, download_banner
from validate import check_dataset


HF_REPO = "juliensimon/nebula-catalog"

WIKIDATA_URL = "https://query.wikidata.org/sparql"
HEADERS = {"User-Agent": "space-datasets/1.0 (https://github.com/juliensimon/space-datasets)"}

# Wikidata QIDs for nebula types we want to keep as "most specific"
NEBULA_TYPE_QIDS = {"Q207326", "Q167278", "Q46587", "Q204194"}

SPARQL_TEMPLATE = """
SELECT ?neb ?nebLabel ?typeLabel ?constellationLabel
       ?ra ?dec ?distance
WHERE {{
  ?neb wdt:P31 wd:{qid}.
  OPTIONAL {{ ?neb wdt:P31 ?type. }}
  OPTIONAL {{ ?neb wdt:P59 ?constellation. }}
  OPTIONAL {{ ?neb wdt:P6257 ?ra. }}
  OPTIONAL {{ ?neb wdt:P6258 ?dec. }}
  OPTIONAL {{ ?neb wdt:P2583 ?distance. }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,mul". }}
}}
"""

# Fetch each nebula type separately to keep response sizes under Wikidata limits
NEBULA_TYPE_QUERIES = [
    ("Q207326", "emission nebula"),
    ("Q167278", "reflection nebula"),
    ("Q46587", "dark nebula"),
    ("Q204194", "planetary nebula"),
]

# Per-type catalog query — raw rows, aggregated in Python (GROUP_CONCAT times out)
CATALOG_TEMPLATE = """
SELECT ?neb ?catalogId
WHERE {{
  ?neb wdt:P31 wd:{qid}.
  ?neb wdt:P528 ?catalogId.
}}
"""

# Labels corresponding to the four nebula-type QIDs (lowercase for matching)
SPECIFIC_TYPE_LABELS = {
    "emission nebula",
    "reflection nebula",
    "dark nebula",
    "planetary nebula",
}

# All type labels we consider valid nebulae (includes subtypes)
VALID_NEBULA_TYPES = SPECIFIC_TYPE_LABELS | {
    "nebula",
    "protoplanetary nebula",
    "supernova remnant",
    "h ii region",
    "herbig–haro object",
    "herbig-haro object",
    "bipolar nebula",
    "ring nebula",
    "diffuse nebula",
    "bright nebula",
    "star-forming region",
    "molecular cloud",
    "bok globule",
    "cometary globule",
    "wolf–rayet nebula",
    "wolf-rayet nebula",
    "nova remnant",
}


def _pick_best_type(types_str):
    """Pick the most specific nebula type from a semicolon-separated list."""
    if not types_str:
        return None
    types = [t.strip() for t in types_str.split(";")]
    # Prefer specific nebula type labels
    for t in types:
        if t.lower() in SPECIFIC_TYPE_LABELS:
            return t
    return types[0] if types else None


def _query_wikidata_json(sparql, label="query", retries=3):
    """Run a SPARQL query against Wikidata (JSON), with truncation-tolerant parsing."""
    import json as _json
    import time
    for attempt in range(retries):
        try:
            resp = requests.get(
                WIKIDATA_URL,
                params={"query": sparql, "format": "json"},
                headers=HEADERS,
                timeout=300,
            )
            resp.raise_for_status()
            try:
                results = _json.loads(resp.text, strict=False)["results"]["bindings"]
            except _json.JSONDecodeError:
                # Truncated response — salvage what we can by finding the last complete record
                text = resp.text
                last_close = text.rfind("}")
                if last_close > 0:
                    # Find the end of the last complete binding array entry
                    truncated = text[:last_close + 1] + "]}}"
                    results = _json.loads(truncated, strict=False)["results"]["bindings"]
                    print(f"  {label}: salvaged {len(results):,} rows from truncated response")
                else:
                    raise
            else:
                print(f"  {label}: {len(results):,} rows ({len(resp.text) / 1e6:.1f} MB)")
            return results
        except Exception as e:
            if attempt < retries - 1:
                wait = 30 * (attempt + 1)
                print(f"  {label} attempt {attempt + 1} failed ({e}), retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise


def fetch_nebulae() -> pd.DataFrame:
    """Query Wikidata SPARQL for all nebulae (per-type to stay under size limits)."""
    import time
    print("Querying Wikidata for nebulae...")

    # Fetch each nebula type separately to stay under Wikidata response limits
    all_results = []
    for qid, type_name in NEBULA_TYPE_QUERIES:
        sparql = SPARQL_TEMPLATE.format(qid=qid)
        results = _query_wikidata_json(sparql, type_name)
        all_results.extend(results)
        time.sleep(2)  # be nice to Wikidata

    rows = []
    for r in all_results:
        wikidata_id = r.get("neb", {}).get("value", "").rsplit("/", 1)[-1]
        type_label = r.get("typeLabel", {}).get("value") or None
        rows.append({
            "wikidata_id": wikidata_id,
            "name": r.get("nebLabel", {}).get("value"),
            "nebula_type": type_label,
            "constellation": r.get("constellationLabel", {}).get("value") or None,
            "ra_deg": r.get("ra", {}).get("value") or None,
            "dec_deg": r.get("dec", {}).get("value") or None,
            "distance_ly": r.get("distance", {}).get("value") or None,
        })

    df = pd.DataFrame(rows)

    # Drop entries with no real name (bare Q-IDs = junk Wikidata entities)
    df = df[~df["name"].str.match(r"^Q\d+$", na=False)]

    # For nebula_type: prefer specific type labels over generic ones.
    df["_type_score"] = df["nebula_type"].apply(
        lambda t: 1 if (t or "").lower() in SPECIFIC_TYPE_LABELS else 0
    )
    df["_completeness"] = df[["ra_deg", "dec_deg"]].notna().sum(axis=1)
    df = df.sort_values(
        ["wikidata_id", "_type_score", "_completeness"],
        ascending=[True, False, False],
    ).drop_duplicates(subset=["wikidata_id"], keep="first").drop(
        columns=["_type_score", "_completeness"]
    )

    # Filter: only keep entities whose best type is a recognized nebula type.
    # Wikidata entities often have multiple P31 values (e.g. "dark nebula" AND "summit"),
    # and the UNION query pulls in non-nebula entities that share a type QID.
    before = len(df)
    df = df[df["nebula_type"].str.lower().isin(VALID_NEBULA_TYPES)]
    print(f"  Filtered to valid nebula types: {len(df):,} / {before:,}")

    # Drop columns that are >95% null (distance_ly, angular_size)
    for col in list(df.columns):
        null_pct = df[col].isna().mean()
        if null_pct > 0.95:
            df = df.drop(columns=[col])
            print(f"  Dropped column '{col}' ({null_pct:.0%} null)")

    # Pass 2: catalog IDs (raw rows per-type, aggregated in Python)
    cat_raw = {}  # qid -> list of catalog IDs
    for qid, type_name in NEBULA_TYPE_QUERIES:
        time.sleep(2)
        try:
            cat_results = _query_wikidata_json(
                CATALOG_TEMPLATE.format(qid=qid), f"catalogs/{type_name}"
            )
            for r in cat_results:
                neb_qid = r.get("neb", {}).get("value", "").rsplit("/", 1)[-1]
                cat_id = r.get("catalogId", {}).get("value")
                if cat_id:
                    cat_raw.setdefault(neb_qid, set()).add(cat_id)
        except Exception as e:
            print(f"  Catalog query for {type_name} failed ({e}), skipping")
    # Aggregate: join unique catalog IDs with semicolons
    cat_map = {qid: "; ".join(sorted(ids)) for qid, ids in cat_raw.items()}
    df["catalog_id"] = df["wikidata_id"].map(cat_map)
    n_with_cat = df["catalog_id"].notna().sum()
    print(f"  Catalog IDs: {n_with_cat:,} / {len(df):,} nebulae")

    return df


def main():
    df = fetch_nebulae()

    # Numeric coercions
    for col in ["ra_deg", "dec_deg", "distance_ly", "angular_size"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Clean string columns
    for col in ["name", "nebula_type", "constellation", "catalog_id"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
            )

    df = df.sort_values("name").reset_index(drop=True)
    print(f"  {len(df):,} unique nebulae")

    check_dataset(df, "nebulae", min_rows=10000,
                  expected_columns=["name"],
                  critical_columns=["name"])

    # Stats for README
    n = len(df)
    type_counts = df["nebula_type"].value_counts()
    top_types = type_counts.head(8)
    top_types_str = "\n".join(
        f"- **{t}**: {c:,}" for t, c in top_types.items()
    )

    top_constellations = df["constellation"].value_counts().head(5)
    top_const_str = ", ".join(
        f"{c} ({cnt:,})" for c, cnt in top_constellations.items()
    )

    n_with_coords = int(df[["ra_deg", "dec_deg"]].notna().all(axis=1).sum())
    n_with_catalog = int(df["catalog_id"].notna().sum()) if "catalog_id" in df.columns else 0

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "nebulae.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_kb = out.stat().st_size / 1024
        print(f"  {size_kb:.0f} KB parquet")

        banner_file = download_banner("nebulae", tmp)
        banner_md = banner_markdown("nebulae", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc0-1.0
pretty_name: "Nebula Catalog"
language:
  - en
description: >-
  Catalog of nebulae sourced from Wikidata, covering emission, reflection,
  dark, and planetary nebulae. {n:,} entries with coordinates, distances,
  angular sizes, and constellation assignments.
size_categories:
  - 10K<n<100K
task_categories:
  - tabular-classification
tags:
  - space
  - astronomy
  - nebulae
  - deep-sky
  - wikidata
  - open-data
  - tabular-data
  - parquet
configs:
  - config_name: default
    default: true
    data_files:
      - split: train
        path: data/nebulae.parquet
---

# Nebula Catalog
{banner_md}
*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

A comprehensive catalog of **{n:,}** nebulae sourced from [Wikidata](https://www.wikidata.org/),
covering emission, reflection, dark, and planetary nebulae across the sky.

## Dataset description

Nebulae are clouds of interstellar gas and dust — the birthplaces of stars,
the remnants of dying ones, and some of the most visually spectacular objects
in the universe. This dataset aggregates structured data from Wikidata's
knowledge base, drawing on decades of cataloguing from Messier, NGC, IC, and
other surveys.

Each entry includes the nebula's name, type, host constellation, equatorial
coordinates (right ascension and declination), distance from Earth, angular
size on the sky, and a representative catalog identifier. This enables
sky-survey cross-matching, population studies by type or constellation, and
distance/size distribution analysis.

Sourced from Wikidata SPARQL using P31 (instance of) for emission (Q207326),
reflection (Q167278), dark (Q46587), and planetary (Q204194) nebulae.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `wikidata_id` | string | Wikidata entity ID (e.g. Q12345) |
| `name` | string | Common or catalog name |
| `nebula_type` | string | Nebula type (emission, reflection, dark, planetary) |
| `constellation` | string | Host constellation |
| `ra_deg` | float | Right ascension (degrees) |
| `dec_deg` | float | Declination (degrees) |
| `catalog_id` | string | Catalog identifiers (NGC, IC, Messier, etc.; semicolon-separated) |

## Quick stats

- **{n:,}** nebulae total
- **{n_with_coords:,}** with equatorial coordinates
- **{n_with_catalog:,}** with catalog identifiers
- Top constellations: {top_const_str}

### Breakdown by type

{top_types_str}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/nebula-catalog", split="train")
df = ds.to_pandas()

# Count by nebula type
print(df["nebula_type"].value_counts())

# Planetary nebulae with coordinates
pn = df[(df["nebula_type"] == "planetary nebula") & df["ra_deg"].notna()]
print(pn[["name", "constellation", "ra_deg", "dec_deg"]].head(10))

# Nebulae in Orion
orion = df[df["constellation"] == "Orion"]
print(f"{{len(orion):,}} nebulae in Orion")

# Dark nebulae
dark = df[df["nebula_type"] == "dark nebula"]
print(f"{{len(dark):,}} dark nebulae")
```

## Data source

[Wikidata](https://www.wikidata.org/) SPARQL endpoint. Nebulae identified via
property P31 (instance of) for four nebula-type entities. Data is
community-curated and reflects contributions from astronomical cataloguing
projects worldwide.

## Update schedule

Quarterly (January, April, July, October). Re-run manually at any time to
pick up newly catalogued objects.

## Related datasets

- [planetary-nebulae](https://huggingface.co/datasets/juliensimon/planetary-nebulae) -- dedicated planetary nebula catalog
- [ngc-ic-catalog](https://huggingface.co/datasets/juliensimon/ngc-ic-catalog) -- NGC/IC catalog of deep-sky objects
- [messier-catalog](https://huggingface.co/datasets/juliensimon/messier-catalog) -- Messier catalog

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/nebula-catalog) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{nebula_catalog,
  author = {{Simon, Julien}},
  title = {{Nebula Catalog}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/nebula-catalog}},
  note = {{Sourced from Wikidata (CC0)}}
}}
```

## License

[CC0-1.0](https://creativecommons.org/publicdomain/zero/1.0/) (Wikidata content is public domain)
""")

        print("Uploading to HF...")
        commit_msg = f"Update nebula catalog: {n:,} nebulae"
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
