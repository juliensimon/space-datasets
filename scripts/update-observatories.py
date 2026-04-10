#!/usr/bin/env python3
"""Fetch observatory database from Wikidata and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

from dataset_images import banner_markdown, download_banner
from validate import check_dataset


HF_REPO = "juliensimon/observatory-database"

WIKIDATA_URL = "https://query.wikidata.org/sparql"
HEADERS = {"User-Agent": "space-datasets/1.0 (https://github.com/juliensimon/space-datasets)"}

SPARQL_QUERY = """
SELECT ?obs ?obsLabel ?countryLabel ?lat ?lon
       ?elevation ?aperture
       ?operatorLabel ?openingDate
       (GROUP_CONCAT(DISTINCT ?wavelengthLabel; separator="; ") AS ?wavelengths)
WHERE {
  { ?obs wdt:P31 wd:Q62832 }
  UNION { ?obs wdt:P31 wd:Q1377879 }
  UNION { ?obs wdt:P31 wd:Q148578 }
  OPTIONAL { ?obs wdt:P17 ?country. }
  OPTIONAL { ?obs p:P625 ?coordStmt.
             ?coordStmt psv:P625 ?coordNode.
             ?coordNode wikibase:geoLatitude ?lat.
             ?coordNode wikibase:geoLongitude ?lon. }
  OPTIONAL { ?obs wdt:P2044 ?elevation. }
  OPTIONAL { ?obs wdt:P1090 ?aperture. }
  OPTIONAL { ?obs wdt:P137 ?operator. }
  OPTIONAL { ?obs wdt:P1619 ?openingDate. }
  OPTIONAL { ?obs wdt:P1148 ?wavelength.
             ?wavelength rdfs:label ?wavelengthLabel. FILTER(LANG(?wavelengthLabel) = "en") }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,mul". }
}
GROUP BY ?obs ?obsLabel ?countryLabel ?lat ?lon ?elevation ?aperture ?operatorLabel ?openingDate
"""


def fetch_observatories() -> pd.DataFrame:
    """Query Wikidata SPARQL for all observatories."""
    print("Querying Wikidata for observatories...")
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
        wikidata_id = r.get("obs", {}).get("value", "").rsplit("/", 1)[-1]

        lat = r.get("lat", {}).get("value")
        lon = r.get("lon", {}).get("value")
        elevation = r.get("elevation", {}).get("value")
        aperture = r.get("aperture", {}).get("value")
        opening_date = r.get("openingDate", {}).get("value", "")

        rows.append({
            "wikidata_id": wikidata_id,
            "name": r.get("obsLabel", {}).get("value"),
            "country": r.get("countryLabel", {}).get("value"),
            "latitude": float(lat) if lat is not None else None,
            "longitude": float(lon) if lon is not None else None,
            "elevation_m": float(elevation) if elevation is not None else None,
            "aperture_m": float(aperture) if aperture is not None else None,
            "operator": r.get("operatorLabel", {}).get("value"),
            "opening_date": opening_date[:10] if opening_date else None,
            "wavelengths": r.get("wavelengths", {}).get("value") or None,
        })

    df = pd.DataFrame(rows)

    # Deduplicate on wikidata_id — keep row with most info (longest wavelengths string)
    df["_sort"] = df["wavelengths"].fillna("").str.len()
    df = df.sort_values("_sort", ascending=False).drop_duplicates(
        subset=["wikidata_id"], keep="first"
    ).drop(columns=["_sort"])

    # Drop entries with no real name (bare Q-IDs = junk Wikidata entities)
    df = df[~df["name"].str.match(r"^Q\d+$", na=False)]

    return df


def main():
    df = fetch_observatories()

    # Clean string columns
    for col in ["name", "country", "operator", "wavelengths", "opening_date"]:
        df[col] = df[col].astype(str).str.strip().replace(
            {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
        )

    df = df.sort_values("name").reset_index(drop=True)
    print(f"  {len(df):,} unique observatories")

    check_dataset(df, "observatories", min_rows=200,
                  expected_columns=["name"],
                  critical_columns=["name"])

    # Stats for README
    n = len(df)
    n_countries = int(df["country"].nunique())
    top_countries = df["country"].value_counts().head(5)
    top_countries_str = ", ".join(f"{c} ({cnt:,})" for c, cnt in top_countries.items())

    n_with_coords = int(df["latitude"].notna().sum())
    n_with_aperture = int(df["aperture_m"].notna().sum())
    n_with_elevation = int(df["elevation_m"].notna().sum())

    # Highest elevation
    if n_with_elevation > 0:
        idx_highest = df["elevation_m"].idxmax()
        highest_elev = df.loc[idx_highest, "elevation_m"]
        highest_name = df.loc[idx_highest, "name"]
        highest_str = f"{highest_name} ({highest_elev:,.0f} m)"
    else:
        highest_str = "N/A"

    # Space vs ground
    space_keywords = ["space", "orbital", "satellite", "hubble", "chandra", "spitzer", "kepler",
                      "fermi", "swift", "xmm", "integral", "herschel", "planck", "gaia", "tess",
                      "wise", "galex", "compton", "rosat", "bepposax", "astro", "telescope space"]
    df["_is_space"] = df["name"].str.lower().str.contains(
        "|".join(space_keywords), na=False
    )
    n_space = int(df["_is_space"].sum())
    n_ground = n - n_space
    df = df.drop(columns=["_is_space"])

    # Wavelength coverage
    wl_flat = df["wavelengths"].dropna().str.split("; ").explode()
    top_wavelengths = wl_flat.value_counts().head(5)
    top_wl_str = ", ".join(f"{w} ({cnt:,})" for w, cnt in top_wavelengths.items())

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "observatories.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_kb = out.stat().st_size / 1024
        print(f"  {size_kb:.0f} KB parquet")

        banner_file = download_banner("observatories", tmp)
        banner_md = banner_markdown("observatories", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc0-1.0
pretty_name: "Observatory Database"
language:
  - en
description: >-
  Comprehensive database of astronomical observatories worldwide, sourced from Wikidata.
  {n:,} observatories from {n_countries} countries with coordinates, elevation,
  aperture size, operator, and wavelength coverage.
size_categories:
  - n<1K
task_categories:
  - tabular-classification
tags:
  - space
  - astronomy
  - observatories
  - telescopes
  - wikidata
  - open-data
  - tabular-data
  - parquet
configs:
  - config_name: default
    default: true
    data_files:
      - split: train
        path: data/observatories.parquet
---

# Observatory Database
{banner_md}
*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

Comprehensive database of astronomical observatories — **{n:,}** facilities from
**{n_countries}** countries, sourced from [Wikidata](https://www.wikidata.org/).

## Dataset description

From ancient naked-eye platforms to modern space-based flagship missions, observatories
have been humanity's primary windows into the universe. This dataset covers optical
telescopes, radio dishes, neutrino detectors, gamma-ray satellites, and space observatories —
any facility classified in Wikidata as an astronomical observatory (Q62832), space
observatory (Q1377879), or radio observatory (Q148578).

Each entry includes geographic coordinates (latitude/longitude), elevation above sea level,
primary aperture size, operating organization, opening date, and the electromagnetic
wavelength bands observed. This enables spatial analysis of observatory distribution,
historical studies of observational astronomy, and comparison of ground-based vs.
space-based capabilities.

Sourced from Wikidata's structured knowledge base, curated by the WikiProject Astronomy
community with contributions from professional astronomers and enthusiasts worldwide.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `wikidata_id` | string | Wikidata entity ID (e.g. "Q179224"); stable URI for enrichment and cross-referencing |
| `name` | string | Full official observatory name (e.g. "Palomar Observatory", "European Southern Observatory") |
| `country` | string | Country in which the observatory is physically located (e.g. "United States", "Chile", "Hawaii" mapped to "United States") |
| `latitude` | float | Geographic latitude in decimal degrees; range −90 to +90; positive = North; null if not recorded |
| `longitude` | float | Geographic longitude in decimal degrees; range −180 to +180; positive = East; null if not recorded |
| `elevation_m` | float | Altitude above sea level in metres; relevant for atmospheric transparency and seeing quality; range sea level to ~5,640 m (Atacama sites); null if not recorded |
| `aperture_m` | float | Primary mirror or dish diameter in metres; range ~0.1 m (amateur facilities) to 39 m (ELT); null for multi-telescope complexes or space observatories without a single aperture |
| `operator` | string | Institution or agency operating the observatory (e.g. "NASA", "ESO", "Caltech"); null if not recorded in Wikidata |
| `opening_date` | string | Date the observatory was inaugurated or began operations (YYYY-MM-DD or YYYY); null if unknown |
| `wavelengths` | string | Observed electromagnetic bands, semicolon-separated (e.g. "optical; infrared"; "radio"; "X-ray; gamma-ray"); null if not specified |

## Quick stats

- **{n:,}** observatories from **{n_countries}** countries
- **{n_with_coords:,}** with geographic coordinates
- **{n_with_aperture:,}** with aperture data
- **{n_with_elevation:,}** with elevation data
- Highest elevation: {highest_str}
- Estimated ground-based: **{n_ground:,}**, space-based: **{n_space:,}**
- Top countries: {top_countries_str}
- Top wavelength bands: {top_wl_str}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/observatory-database", split="train")
df = ds.to_pandas()

# Observatories by country
print(df["country"].value_counts().head(10))

# High-altitude observatories (above 3000 m)
high_alt = df[df["elevation_m"] > 3000].sort_values("elevation_m", ascending=False)
print(high_alt[["name", "country", "elevation_m"]].head(10))

# Large aperture telescopes (> 8 m)
large = df[df["aperture_m"] > 8].sort_values("aperture_m", ascending=False)
print(large[["name", "country", "aperture_m"]])

# Radio observatories
radio = df[df["wavelengths"].str.contains("radio", case=False, na=False)]
print(f"{{len(radio):,}} radio observatories")

# Space observatories
space_obs = df[df["wavelengths"].str.contains("X-ray|gamma|ultraviolet", case=False, na=False)]
print(space_obs[["name", "wavelengths"]].head(10))
```

## Data source

[Wikidata](https://www.wikidata.org/) SPARQL endpoint. Observatories identified via
property P31 (instance of) = Q62832 (astronomical observatory), Q1377879 (space
observatory), or Q148578 (radio observatory). Data is community-curated by
[WikiProject Astronomy](https://www.wikidata.org/wiki/Wikidata:WikiProject_Astronomy).

## Update schedule

Quarterly (January, April, July, October). Re-run manually to pick up newly catalogued facilities.

## Related datasets

- [astronomer-database](https://huggingface.co/datasets/juliensimon/astronomer-database) — Astronomers from Wikidata
- [chandra-sources](https://huggingface.co/datasets/juliensimon/chandra-x-ray-sources) — Chandra X-ray source catalog

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/observatory-database) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{observatory_database,
  author = {{Simon, Julien}},
  title = {{Observatory Database}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/observatory-database}},
  note = {{Sourced from Wikidata (CC0)}}
}}
```

## License

[CC0-1.0](https://creativecommons.org/publicdomain/zero/1.0/) (Wikidata content is public domain)
""")

        print("Uploading to HF...")
        commit_msg = f"Update observatory database: {n:,} observatories"
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
