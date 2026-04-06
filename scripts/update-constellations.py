#!/usr/bin/env python3
"""Fetch constellation catalog from Wikidata and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

from dataset_images import banner_markdown, download_banner
from validate import check_dataset


HF_REPO = "juliensimon/constellation-catalog"

WIKIDATA_URL = "https://query.wikidata.org/sparql"
HEADERS = {"User-Agent": "space-datasets/1.0 (https://github.com/juliensimon/space-datasets)"}

SPARQL_QUERY = """
SELECT ?cons ?consLabel ?iauAbbrev ?symbolLabel
       ?brightestStarLabel ?areaSquareDeg
       ?raCenter ?decCenter
       ?namedAfterLabel
WHERE {
  ?cons wdt:P31 wd:Q8928.
  OPTIONAL { ?cons wdt:P1813 ?iauAbbrev. }
  OPTIONAL { ?cons wdt:P367 ?symbol. }
  OPTIONAL { ?cons wdt:P7015 ?brightestStar. }
  OPTIONAL { ?cons wdt:P2046 ?areaSquareDeg. }
  OPTIONAL { ?cons wdt:P138 ?namedAfter. }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,mul". }
}
"""


def fetch_constellations() -> pd.DataFrame:
    """Query Wikidata SPARQL for all constellations."""
    print("Querying Wikidata for constellations...")
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
        wikidata_id = r.get("cons", {}).get("value", "").rsplit("/", 1)[-1]
        area_raw = r.get("areaSquareDeg", {}).get("value")
        rows.append({
            "wikidata_id": wikidata_id,
            "name": r.get("consLabel", {}).get("value"),
            "iau_abbreviation": r.get("iauAbbrev", {}).get("value") or None,
            "symbol": r.get("symbolLabel", {}).get("value") or None,
            "brightest_star": r.get("brightestStarLabel", {}).get("value") or None,
            "area_sq_deg": float(area_raw) if area_raw else None,
            "named_after": r.get("namedAfterLabel", {}).get("value") or None,
        })

    df = pd.DataFrame(rows)

    # Deduplicate on wikidata_id — keep first occurrence
    df = df.drop_duplicates(subset=["wikidata_id"], keep="first")

    # Drop entries with no real name (bare Q-IDs = junk Wikidata entities)
    df = df[~df["name"].str.match(r"^Q\d+$", na=False)]

    return df


def main():
    df = fetch_constellations()

    # Clean string columns
    for col in ["name", "iau_abbreviation", "symbol", "brightest_star", "named_after"]:
        df[col] = df[col].astype(str).str.strip().replace(
            {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
        )

    df = df.sort_values("name").reset_index(drop=True)
    print(f"  {len(df):,} unique constellations")

    check_dataset(df, "constellations", min_rows=50,
                  expected_columns=["name"],
                  critical_columns=["name"])

    # Stats for README
    n = len(df)
    n_with_area = int(df["area_sq_deg"].notna().sum())
    n_with_brightest = int(df["brightest_star"].notna().sum())
    n_with_named_after = int(df["named_after"].notna().sum())
    total_area = df["area_sq_deg"].sum()

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "constellations.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_kb = out.stat().st_size / 1024
        print(f"  {size_kb:.0f} KB parquet")

        banner_file = download_banner("constellations", tmp)
        banner_md = banner_markdown("constellations", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc0-1.0
pretty_name: "Constellation Catalog"
language:
  - en
description: >-
  All {n} IAU-recognized constellations sourced from Wikidata, with IAU
  abbreviations, area in square degrees, sky coordinates, brightest star,
  and mythological origin.
size_categories:
  - n<1K
task_categories:
  - tabular-classification
tags:
  - space
  - astronomy
  - constellations
  - wikidata
  - open-data
  - tabular-data
  - parquet
configs:
  - config_name: default
    default: true
    data_files:
      - split: train
        path: data/constellations.parquet
---

# Constellation Catalog
{banner_md}
*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

Complete catalog of all **{n}** IAU-recognized constellations, sourced from [Wikidata](https://www.wikidata.org/).

## Dataset description

The International Astronomical Union (IAU) officially recognizes 88 constellations that together tile the entire celestial sphere. These range from ancient Greek figures catalogued by Ptolemy in the Almagest to southern-hemisphere constellations added by European explorers in the 16th–18th centuries and formalized by Eugène Delporte in 1930.

This dataset records each constellation with its IAU three-letter abbreviation, the area it covers in square degrees, the coordinates of its center (right ascension and declination), its brightest star, and the mythological figure or object it was named after. This enables sky-coverage analysis, educational tools, and cross-referencing with star and deep-sky-object catalogs.

Sourced from Wikidata's structured knowledge base (property P31=Q8928 for instance-of:constellation), maintained by the astronomy community.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `wikidata_id` | string | Wikidata entity ID (e.g. Q8928) |
| `name` | string | Full English name of the constellation |
| `iau_abbreviation` | string | IAU three-letter abbreviation (e.g. Ori, UMa) |
| `symbol` | string | Traditional symbol or figure |
| `brightest_star` | string | Common name of the brightest star |
| `area_sq_deg` | float | Area of the constellation in square degrees |
| `named_after` | string | Mythological figure, animal, or object it represents |

## Quick stats

- **{n}** IAU-recognized constellations
- **{n_with_area:,}** with area in square degrees (total sky: ~{total_area:,.0f} sq deg)
- **{n_with_brightest:,}** with brightest star identified
- **{n_with_named_after:,}** with named-after mythology or origin

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/constellation-catalog", split="train")
df = ds.to_pandas()

# Largest constellations by area
print(df.nlargest(10, "area_sq_deg")[["name", "iau_abbreviation", "area_sq_deg"]])

# Constellations named after mythological figures
myth = df[df["named_after"].notna()]
print(myth[["name", "named_after"]].head(10))

# Find by IAU abbreviation
orion = df[df["iau_abbreviation"] == "Ori"].iloc[0]
print(f"Orion: {{orion['area_sq_deg']:.0f}} sq deg, brightest star: {{orion['brightest_star']}}")
```

## Data source

[Wikidata](https://www.wikidata.org/) SPARQL endpoint. Constellations identified via
property P31 (instance of) = Q8928 (constellation). IAU formalization by Eugène Delporte (1930).

## Update schedule

Quarterly (January, April, July, October). Re-run manually to pick up Wikidata improvements.

## Related datasets

- [astronomer-database](https://huggingface.co/datasets/juliensimon/astronomer-database) -- Astronomer biographies
- [observatory-database](https://huggingface.co/datasets/juliensimon/observatory-database) -- Astronomical observatories
- [bright-star-catalog](https://huggingface.co/datasets/juliensimon/bright-star-catalog) -- Yale Bright Star Catalog

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/constellation-catalog) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{constellation_catalog,
  author = {{Simon, Julien}},
  title = {{Constellation Catalog}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/constellation-catalog}},
  note = {{Sourced from Wikidata (CC0)}}
}}
```

## License

[CC0-1.0](https://creativecommons.org/publicdomain/zero/1.0/) (Wikidata content is public domain)
""")

        print("Uploading to HF...")
        commit_msg = f"Update constellation catalog: {n:,} constellations"
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
