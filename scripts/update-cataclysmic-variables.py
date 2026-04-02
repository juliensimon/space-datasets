#!/usr/bin/env python3
"""Fetch Ritter & Kolb Cataclysmic Variable catalog from HEASARC and upload to HF."""

import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset


TAP_URL = "https://heasarc.gsfc.nasa.gov/xamin/vo/tap/sync"
HF_REPO = "juliensimon/cataclysmic-variable-catalog"

ADQL = "SELECT * FROM rittercv"


def fetch_catalog() -> pd.DataFrame:
    """Try CSV first, fall back to JSON, then pipe-delimited text."""
    # Attempt 1: CSV
    print("Fetching Ritter & Kolb CV catalog (CSV)...")
    resp = requests.get(TAP_URL, params={
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": ADQL,
    }, timeout=120)
    resp.raise_for_status()

    if not resp.text.strip().startswith("<?xml"):
        try:
            df = pd.read_csv(io.StringIO(resp.text))
            if len(df) > 100:
                print(f"  CSV parse OK: {len(df):,} rows")
                return df
        except Exception as e:
            print(f"  CSV parse failed: {e}")
    else:
        print("  CSV returned XML, skipping")

    # Attempt 2: JSON
    print("Retrying with FORMAT=json...")
    resp = requests.get(TAP_URL, params={
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "json", "QUERY": ADQL,
    }, timeout=120)
    resp.raise_for_status()

    try:
        data = resp.json()
        if "data" in data and "metadata" in data:
            cols = [m["name"] for m in data["metadata"]]
            df = pd.DataFrame(data["data"], columns=cols)
        else:
            df = pd.DataFrame(data)
        if len(df) > 100:
            print(f"  JSON parse OK: {len(df):,} rows")
            return df
    except Exception as e:
        print(f"  JSON parse failed: {e}")

    # Attempt 3: pipe-delimited text
    print("Retrying with FORMAT=text...")
    resp = requests.get(TAP_URL, params={
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "text", "QUERY": ADQL,
    }, timeout=120)
    resp.raise_for_status()

    lines = [l for l in resp.text.strip().splitlines()
             if l.strip() and not l.startswith("-")]
    if len(lines) >= 2:
        header = [c.strip() for c in lines[0].split("|")]
        rows = []
        for line in lines[1:]:
            rows.append([c.strip() for c in line.split("|")])
        df = pd.DataFrame(rows, columns=header)
        df = df.loc[:, df.columns != ""]
        print(f"  Text parse OK: {len(df):,} rows")
        return df

    print("::error::All fetch formats failed")
    sys.exit(1)


def main():
    df = fetch_catalog()

    # Clean empty strings to NaN
    df = df.replace(r"^\s*$", pd.NA, regex=True)

    # Auto-drop columns that are >95% null
    null_frac = df.isna().mean()
    drop_cols = null_frac[null_frac > 0.95].index.tolist()
    if drop_cols:
        print(f"  Dropping {len(drop_cols)} columns >95% null: {drop_cols[:10]}...")
        df = df.drop(columns=drop_cols)

    # Lowercase column names to snake_case
    df.columns = [c.strip().lower() for c in df.columns]

    # Numeric coercion on coordinate and physical columns
    numeric_candidates = ["ra", "dec", "period", "mag1", "mag2",
                          "porb", "porb2", "ra_deg", "dec_deg",
                          "lii", "bii"]
    for col in numeric_candidates:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Also coerce anything that looks like magnitude or period
    for col in df.columns:
        if any(kw in col for kw in ["mag", "period", "porb", "flux", "dist"]):
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Derive CV subtype classification if a type column exists
    type_col = None
    for candidate in ["type", "cv_type", "class", "obj_type", "source_type", "type2"]:
        if candidate in df.columns:
            type_col = candidate
            break

    if type_col:
        def classify_cv(t):
            if pd.isna(t):
                return None
            t_upper = str(t).upper().strip()
            if "DN" in t_upper or "DWARF" in t_upper or "SU" in t_upper or "UG" in t_upper:
                return "dwarf_nova"
            if "AM" in t_upper and "HER" in t_upper:
                return "polar"
            if "DQ" in t_upper and "HER" in t_upper:
                return "intermediate_polar"
            if "IP" in t_upper:
                return "intermediate_polar"
            if t_upper in ("AM", "P", "POLAR"):
                return "polar"
            if "NL" in t_upper or "NOVA-LIKE" in t_upper or "NOVALIKE" in t_upper:
                return "nova_like"
            if "NA" in t_upper or "NB" in t_upper or "NC" in t_upper or "NR" in t_upper:
                return "classical_nova"
            if "N " in t_upper or t_upper == "N":
                return "classical_nova"
            return "other"

        df["cv_subtype"] = df[type_col].apply(classify_cv)
        print(f"  Derived cv_subtype from '{type_col}'")
        subtype_counts = df["cv_subtype"].value_counts()
        for st, cnt in subtype_counts.items():
            print(f"    {st}: {cnt:,}")

    # Identify name column
    name_col = None
    for candidate in ["name", "source_name", "object_name", "designation"]:
        if candidate in df.columns:
            name_col = candidate
            break

    if name_col:
        df = df.sort_values(name_col).reset_index(drop=True)
        print(f"  Sorted by '{name_col}'")

    n_total = len(df)
    print(f"  {n_total:,} cataclysmic variables total")

    check_dataset(df, "cataclysmic-variables", min_rows=1000,
                  expected_columns=[c for c in ["name", "ra", "dec", "type"]
                                    if c in df.columns],
                  critical_columns=[c for c in ["name", "ra", "dec"]
                                    if c in df.columns])

    # Stats for README
    n_cols = len(df.columns)
    has_subtype = "cv_subtype" in df.columns
    if has_subtype:
        subtype_counts = df["cv_subtype"].value_counts()
        subtype_str = "\n".join(
            f"  - **{st}**: {cnt:,}" for st, cnt in subtype_counts.items()
        )
    else:
        subtype_str = "  - Type classification not available"

    has_period = "period" in df.columns or "porb" in df.columns
    period_col = "period" if "period" in df.columns else ("porb" if "porb" in df.columns else None)
    if period_col:
        n_with_period = int(df[period_col].notna().sum())
    else:
        n_with_period = 0

    # Build schema table from actual columns
    schema_rows = []
    for col in df.columns:
        dtype = str(df[col].dtype)
        schema_rows.append(f"| `{col}` | {dtype} |")
    schema_table = "\n".join(schema_rows)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "cataclysmic_variables.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Ritter & Kolb Cataclysmic Variable Catalog"
language:
  - en
description: "Catalog of cataclysmic variables (CVs) from the Ritter & Kolb catalog — white dwarfs accreting from companion stars"
task_categories:
  - tabular-classification
tags:
  - space
  - cataclysmic-variable
  - white-dwarf
  - nova
  - dwarf-nova
  - binary-star
  - astronomy
  - accretion
  - open-data
  - tabular-data
  - parquet
size_categories:
  - 1K<n<10K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/cataclysmic_variables.parquet
    default: true
---

# Ritter & Kolb Cataclysmic Variable Catalog

*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) and [Variable Stars & Transients](https://huggingface.co/collections/juliensimon/variable-stars-transients-69c24caf2f17e36128946744) collections on Hugging Face.*

![Update Cataclysmic Variables](https://github.com/juliensimon/space-datasets/actions/workflows/update-cataclysmic-variables.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.cataclysmic-variables&label=updated&color=brightgreen)

The Ritter & Kolb catalog of cataclysmic variables (CVs), sourced from NASA HEASARC.
Currently **{n_total:,}** CVs with {n_cols} attributes.

## Dataset description

Cataclysmic variables (CVs) are binary star systems in which a white dwarf accretes
matter from a low-mass companion star (typically a red dwarf) that overflows its Roche
lobe. The infalling material forms an accretion disk around the white dwarf, producing
dramatic brightness variations across timescales from seconds to decades. CVs are
classified into several subtypes based on their outburst behavior and magnetic field
strength:

- **Dwarf novae** (DN): exhibit quasi-periodic outbursts of 2-8 magnitudes caused by
  thermal instabilities in the accretion disk. Includes SU UMa, U Gem, and Z Cam subtypes.
- **Classical novae** (N): undergo thermonuclear explosions on the white dwarf surface
  when accreted hydrogen reaches a critical mass, brightening by 6-19 magnitudes.
- **Polars** (AM Her): strongly magnetic white dwarfs (B ~ 10-230 MG) where the magnetic
  field channels accretion directly onto the poles, preventing disk formation.
- **Intermediate polars** (DQ Her): moderately magnetic white dwarfs (B ~ 1-10 MG)
  with a truncated accretion disk and magnetically channeled inner flow.
- **Nova-like variables** (NL): high mass-transfer rate systems in a persistent
  bright state without the outburst cycles of dwarf novae.

The Ritter & Kolb catalog is the standard reference catalog for CV research, containing
orbital periods, spectral types, magnitudes, and classifications for the known CV
population. This dataset is essential for population studies, period distribution
analysis, and understanding the evolution of compact binary systems.

## Schema

| Column | Type |
|--------|------|
{schema_table}

## Quick stats

- **{n_total:,}** cataclysmic variables
- **{n_with_period:,}** systems with measured orbital period
- CV subtypes:
{subtype_str}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/cataclysmic-variable-catalog", split="train")
df = ds.to_pandas()

# Filter by CV subtype
{"dwarf_novae = df[df['cv_subtype'] == 'dwarf_nova']" if has_subtype else "# cv_subtype column not available"}
{"polars = df[df['cv_subtype'] == 'polar']" if has_subtype else ""}

# Period distribution
{f'''import matplotlib.pyplot as plt
periods = df["{period_col}"].dropna()
periods[periods > 0].hist(bins=50)
plt.xlabel("Orbital period")
plt.ylabel("Count")
plt.title("CV Orbital Period Distribution")''' if period_col else "# No period column available"}

# Sky distribution
import matplotlib.pyplot as plt
import numpy as np
fig, ax = plt.subplots(subplot_kw={{"projection": "aitoff"}})
ra = np.radians(df["ra"].values - 180) if "ra" in df.columns else []
dec = np.radians(df["dec"].values) if "dec" in df.columns else []
ax.scatter(ra, dec, s=1, alpha=0.5)
plt.title("Cataclysmic Variables - Sky Distribution")
```

## Data source

All data comes from the [Ritter & Kolb Cataclysmic Binaries catalog](https://heasarc.gsfc.nasa.gov/W3Browse/all/rittercv.html)
hosted by NASA's High Energy Astrophysics Science Archive Research Center (HEASARC),
accessed via the TAP protocol. Originally published in:
Ritter H., Kolb U., 2003, A&A 404, 301 (Edition 7.24).

## Update schedule

Quarterly (Feb/May/Aug/Nov 1st at 08:30 UTC) via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [xray-binary-catalog](https://huggingface.co/datasets/juliensimon/xray-binary-catalog) — X-ray binary systems
- [gaia-dr3-white-dwarfs](https://huggingface.co/datasets/juliensimon/gaia-dr3-white-dwarfs) — Gaia white dwarf catalog
- [gcvs-variable-stars](https://huggingface.co/datasets/juliensimon/gcvs-variable-stars) — General Catalogue of Variable Stars
- [kepler-eclipsing-binaries](https://huggingface.co/datasets/juliensimon/kepler-eclipsing-binaries) — Kepler eclipsing binary catalog

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a heart on the [dataset page](https://huggingface.co/datasets/juliensimon/cataclysmic-variable-catalog) and share feedback in the Community tab! Also consider giving a star to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{cataclysmic_variable_catalog,
  author = {{Simon, Julien}},
  title = {{Ritter & Kolb Cataclysmic Variable Catalog}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/cataclysmic-variable-catalog}},
  note = {{Based on Ritter & Kolb (2003) catalog, sourced from NASA HEASARC}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update cataclysmic variable catalog: {n_total:,} CVs"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={len(df)}\n")
    print("Done.")


if __name__ == "__main__":
    main()
