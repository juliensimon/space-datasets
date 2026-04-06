#!/usr/bin/env python3
"""Fetch Jodrell Bank Pulsar Glitch Catalogue and upload to HF."""

import io
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent))
from dataset_images import banner_markdown, download_banner
from validate import check_dataset

HF_REPO = "juliensimon/pulsar-glitch-catalog"
GLITCH_TABLE_URL = "https://www.jb.man.ac.uk/pulsar/glitches/gTable.html"
GLITCH_FALLBACK_URL = "https://www.jb.man.ac.uk/pulsar/glitches.html"


def fetch_html(url: str, retries: int = 3) -> str:
    """Fetch HTML page with retries and exponential backoff."""
    for attempt in range(1, retries + 1):
        try:
            print(f"  Fetching {url} (attempt {attempt})...")
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            print(f"  Attempt {attempt} failed: {e}")
            if attempt < retries:
                time.sleep(2 ** attempt)
    print(f"::error::Failed to fetch {url} after {retries} attempts")
    sys.exit(1)


def parse_glitch_table(html: str) -> pd.DataFrame:
    """Parse the HTML glitch table from Jodrell Bank.

    The table has an unusual structure:
    - Row 0-2: metadata (title, counts, citation note)
    - Row 3: column names (Pulsar name, J-name, No., MJD, +/-, dF/F, +/-, dF1/F1, +/-, References)
    - Row 4: units row (PSR, Glt's, days, days, 1e-9, 1e-9, 1e-3, 1e-3, ...)
    - Row 5+: data rows
    """
    soup = BeautifulSoup(html, "lxml")

    tables = soup.find_all("table")
    if not tables:
        return pd.DataFrame()

    # Pick the largest table
    best_table = max(tables, key=lambda t: len(t.find_all("tr")))
    all_rows = best_table.find_all("tr")

    if len(all_rows) < 10:
        return pd.DataFrame()

    # Find the header row — it's the one containing "MJD" or "Pulsar"
    header_idx = None
    for i, tr in enumerate(all_rows[:10]):
        cells = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
        if any("MJD" in c for c in cells):
            header_idx = i
            break

    if header_idx is None:
        # Fallback: use row 3
        header_idx = 3

    header_cells = [c.get_text(strip=True) for c in all_rows[header_idx].find_all(["td", "th"])]

    # Assign meaningful names based on the known structure:
    # [empty, "Pulsar name", "J-name", "No.", "MJD", "+/-", "dF/F", "+/-", "dF1/F1", "+/-", "References"]
    # Map to clean names
    col_names = []
    for i, h in enumerate(header_cells):
        if "pulsar" in h.lower() and "name" in h.lower():
            col_names.append("bname")
        elif h.lower() in ("j-name", "jname"):
            col_names.append("jname")
        elif h.lower() in ("no.", "no", "glt"):
            col_names.append("n_glitches")
        elif h == "MJD":
            col_names.append("epoch_mjd")
        elif h in ("dF/F", "df/f"):
            col_names.append("delta_nu_nu")
        elif h in ("dF1/F1", "df1/f1"):
            col_names.append("delta_nudot_nudot")
        elif h.lower() in ("ref", "refs", "reference", "references"):
            col_names.append("references")
        elif h == "+/-" or h == "±":
            # Disambiguate error columns by position
            if col_names and col_names[-1] == "epoch_mjd":
                col_names.append("epoch_mjd_err")
            elif col_names and col_names[-1] == "delta_nu_nu":
                col_names.append("delta_nu_nu_err")
            elif col_names and col_names[-1] == "delta_nudot_nudot":
                col_names.append("delta_nudot_nudot_err")
            else:
                col_names.append(f"err_{i}")
        elif h == "":
            col_names.append(f"_empty_{i}")
        else:
            col_names.append(re.sub(r"[^a-zA-Z0-9]+", "_", h).strip("_").lower())

    n_cols = len(col_names)

    # Parse data rows (skip header + units row)
    data_start = header_idx + 2  # skip header and units
    data_rows = []
    for tr in all_rows[data_start:]:
        cells = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
        if len(cells) != n_cols:
            continue
        # Skip rows that are all empty or contain only metadata
        if not any(c.strip() for c in cells[1:6]):
            continue
        data_rows.append(cells)

    if not data_rows:
        return pd.DataFrame()

    df = pd.DataFrame(data_rows, columns=col_names)

    # Drop empty placeholder columns
    df = df.loc[:, ~df.columns.str.startswith("_empty_")]

    print(f"  Parsed {len(df):,} rows, {len(df.columns)} columns from HTML table")
    print(f"  Columns: {list(df.columns)}")
    return df


def normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise column names to snake_case and standardise known fields."""
    # Build a rename map based on common patterns in the Jodrell Bank table
    rename_map = {}
    for col in df.columns:
        lower = col.strip().lower()
        # Pulsar name columns
        if lower in ("jname", "j-name", "psr jname", "psr j-name", "pulsar jname"):
            rename_map[col] = "jname"
        elif lower in ("bname", "b-name", "psr bname", "psr b-name", "pulsar bname", "name"):
            rename_map[col] = "bname"
        # Glitch epoch
        elif "epoch" in lower or lower in ("mjd", "glitch epoch", "glitch epoch (mjd)"):
            rename_map[col] = "epoch_mjd"
        # Delta nu / nu (fractional frequency change = glitch size)
        elif "nu/nu" in lower.replace(" ", "") or "delta_nu/nu" in lower.replace(" ", "") \
                or "dnu/nu" in lower.replace(" ", "") or "deltanu/nu" in lower.replace(" ", ""):
            if "dot" not in lower:
                rename_map[col] = "delta_nu_nu"
            else:
                rename_map[col] = "delta_nudot_nudot"
        elif "nudot" in lower.replace(" ", "") or "nu_dot" in lower:
            rename_map[col] = "delta_nudot_nudot"
        elif lower in ("ref", "refs", "reference", "references"):
            rename_map[col] = "references"

    df = df.rename(columns=rename_map)

    # Convert any remaining column names to snake_case
    clean = {}
    for col in df.columns:
        if col in rename_map.values():
            clean[col] = col
        else:
            s = re.sub(r"[^a-zA-Z0-9]+", "_", col.strip()).strip("_").lower()
            clean[col] = s if s else col
    df = df.rename(columns=clean)

    return df


def fetch_catalog() -> pd.DataFrame:
    """Fetch and parse the Jodrell Bank Pulsar Glitch Catalogue."""
    # Attempt 1: main table page
    print("Fetching Jodrell Bank Glitch Catalogue (gTable.html)...")
    html = fetch_html(GLITCH_TABLE_URL)
    df = parse_glitch_table(html)

    if len(df) >= 100:
        return df

    # Attempt 2: fallback page
    print("Primary table too small or failed, trying fallback page...")
    html = fetch_html(GLITCH_FALLBACK_URL)
    df = parse_glitch_table(html)

    if len(df) >= 100:
        return df

    print(f"::error::Could not parse enough glitch data (got {len(df)} rows)")
    sys.exit(1)


def main():
    df = fetch_catalog()

    # Column names are already assigned by parse_glitch_table
    # Only normalise if we used a fallback path that didn't assign names
    if "epoch_mjd" not in df.columns:
        df = normalise_columns(df)

    # Clean string columns — strip whitespace, replace empty with NaN
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA, "-": pd.NA, "--": pd.NA, "---": pd.NA}
            )

    # Numeric coercion
    numeric_cols = ["epoch_mjd", "epoch_mjd_err", "delta_nu_nu", "delta_nu_nu_err",
                    "delta_nudot_nudot", "delta_nudot_nudot_err", "n_glitches"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Scale: table values are in units of 1e-9 (dF/F) and 1e-3 (dF1/F1)
    # Convert to dimensionless fractional values
    for col in ["delta_nu_nu", "delta_nu_nu_err"]:
        if col in df.columns:
            df[col] = df[col] * 1e-9
    for col in ["delta_nudot_nudot", "delta_nudot_nudot_err"]:
        if col in df.columns:
            df[col] = df[col] * 1e-3

    # Convert MJD epoch to datetime
    if "epoch_mjd" in df.columns:
        mjd_epoch = pd.Timestamp("1858-11-17")
        df["epoch_datetime"] = mjd_epoch + pd.to_timedelta(df["epoch_mjd"], unit="D")

    # Derived column: is_large_glitch (giant glitches typical of Vela-like pulsars)
    # Threshold: delta_nu/nu > 1e-6 (now in proper dimensionless units)
    if "delta_nu_nu" in df.columns:
        df["is_large_glitch"] = df["delta_nu_nu"].apply(
            lambda x: True if pd.notna(x) and x > 1e-6 else (False if pd.notna(x) else None)
        )

    # Sort by epoch descending
    if "epoch_mjd" in df.columns:
        df = df.sort_values("epoch_mjd", ascending=False).reset_index(drop=True)

    print(f"  {len(df):,} glitch events total")
    print(f"  Columns: {list(df.columns)}")

    # Determine the pulsar name column for stats
    name_col = "jname" if "jname" in df.columns else "bname" if "bname" in df.columns else None

    if name_col:
        n_pulsars = df[name_col].nunique()
        print(f"  {n_pulsars:,} unique pulsars")

    if "is_large_glitch" in df.columns:
        n_large = int(df["is_large_glitch"].sum())
        print(f"  {n_large:,} large glitches (delta_nu/nu > 1e-6)")

    # Build expected columns list based on what we have
    expected = []
    if name_col:
        expected.append(name_col)
    for c in ["epoch_mjd", "delta_nu_nu"]:
        if c in df.columns:
            expected.append(c)

    critical = [c for c in [name_col, "epoch_mjd"] if c and c in df.columns]

    check_dataset(df, "pulsar-glitches", min_rows=400,
                  expected_columns=expected or ["epoch_mjd"],
                  critical_columns=critical or None)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "pulsar-glitches.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        # Compute stats for README
        n_total = len(df)
        n_pulsars = df[name_col].nunique() if name_col else 0
        n_large = int(df["is_large_glitch"].sum()) if "is_large_glitch" in df.columns else 0

        # Largest glitch
        if "delta_nu_nu" in df.columns:
            largest_idx = df["delta_nu_nu"].idxmax()
            largest_size = df.loc[largest_idx, "delta_nu_nu"] if pd.notna(largest_idx) else 0
            largest_pulsar = df.loc[largest_idx, name_col] if name_col and pd.notna(largest_idx) else "N/A"
        else:
            largest_size = 0
            largest_pulsar = "N/A"

        # Most frequently glitching pulsar
        if name_col:
            glitch_counts = df[name_col].value_counts()
            most_active = glitch_counts.index[0] if len(glitch_counts) > 0 else "N/A"
            most_active_count = int(glitch_counts.iloc[0]) if len(glitch_counts) > 0 else 0
        else:
            most_active = "N/A"
            most_active_count = 0

        # Build schema table from actual columns
        col_descriptions = {
            "jname": ("string", "Pulsar J-name (e.g. J0534+2200)"),
            "bname": ("string", "Pulsar B-name (e.g. B0531+21)"),
            "epoch_mjd": ("float", "Glitch epoch (Modified Julian Date)"),
            "epoch_datetime": ("datetime", "Glitch epoch (UTC datetime, derived from MJD)"),
            "delta_nu_nu": ("float", "Fractional frequency change (delta_nu/nu), the glitch size"),
            "delta_nudot_nudot": ("float", "Fractional frequency derivative change (delta_nudot/nudot)"),
            "is_large_glitch": ("bool", "True if delta_nu/nu > 1e-6 (giant glitch)"),
            "references": ("string", "Literature references"),
        }

        schema_rows = []
        for col in df.columns:
            if col in col_descriptions:
                dtype, desc = col_descriptions[col]
            else:
                dtype = str(df[col].dtype)
                desc = col.replace("_", " ").title()
            schema_rows.append(f"| `{col}` | {dtype} | {desc} |")
        schema_table = "\n".join(schema_rows)

        banner_file = download_banner("pulsar-glitches", tmp)
        banner_md = banner_markdown("pulsar-glitches", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Jodrell Bank Pulsar Glitch Catalogue"
language:
  - en
description: "Comprehensive catalog of pulsar glitch events from the Jodrell Bank Centre for Astrophysics, including glitch sizes, epochs, and frequency derivative changes."
task_categories:
  - tabular-classification
tags:
  - space
  - pulsar
  - glitch
  - neutron-star
  - astronomy
  - jodrell-bank
  - radio
  - open-data
  - tabular-data
  - parquet
size_categories:
  - n<1K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/pulsar-glitches.parquet
    default: true
---

# Jodrell Bank Pulsar Glitch Catalogue
{banner_md}
*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) and [Stellar Catalogs](https://huggingface.co/collections/juliensimon/stellar-catalogs-69c24caf2f17e36128946744) collections on Hugging Face.*

![Update Pulsar Glitches](https://github.com/juliensimon/space-datasets/actions/workflows/update-pulsar-glitches.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$["pulsar-glitches"]&label=updated&color=brightgreen)

Comprehensive catalog of pulsar glitch events from the
[Jodrell Bank Centre for Astrophysics](https://www.jb.man.ac.uk/pulsar/glitches.html).
Currently **{n_total:,}** glitch events across **{n_pulsars:,}** pulsars
({n_large:,} large/giant glitches).

## Dataset description

Pulsar glitches are sudden spin-up events in neutron stars, thought to arise from
angular momentum transfer between the superfluid interior and the solid crust.
During a glitch, the rotation frequency of the pulsar increases abruptly, typically
by a fractional amount delta_nu/nu ranging from ~10^-11 to ~10^-5. The largest
glitches (delta_nu/nu > 10^-6) are called "giant glitches" and are characteristic
of young pulsars like the Vela pulsar (PSR B0833-45), which glitches roughly every
2-3 years.

The physics of pulsar glitches provides a unique window into the interior structure
of neutron stars. The leading model invokes a reservoir of angular momentum stored in
quantised vortices pinned to the inner crust lattice. As the star spins down
electromagnetically, a rotational lag develops between the superfluid and the crust.
When the Magnus force on pinned vortices exceeds the pinning force, vortices unpin
catastrophically and transfer angular momentum outward, producing the observed
spin-up. The cumulative glitch activity of a pulsar constrains the fractional moment
of inertia of the superfluid component, which in turn constrains the neutron star
equation of state and the extent of the crustal superfluid.

The Jodrell Bank Glitch Catalogue is the most comprehensive compilation of pulsar
glitch parameters, maintained by the Jodrell Bank Centre for Astrophysics at the
University of Manchester. It has been the standard reference for glitch studies
since its inception and is regularly updated as new glitches are detected by
pulsar timing programmes worldwide.

## Schema

| Column | Type | Description |
|--------|------|-------------|
{schema_table}

## Quick stats

- **{n_total:,}** glitch events
- **{n_pulsars:,}** unique pulsars
- **{n_large:,}** large/giant glitches (delta_nu/nu > 10^-6)
- Largest glitch: **{largest_pulsar}** (delta_nu/nu = {largest_size:.2e})
- Most frequently glitching pulsar: **{most_active}** ({most_active_count} glitches)

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/pulsar-glitch-catalog", split="train")
df = ds.to_pandas()

# Glitch size distribution
import matplotlib.pyplot as plt
sizes = df["delta_nu_nu"].dropna()
sizes[sizes > 0].hist(bins=50, log=True)
plt.xlabel("delta_nu/nu")
plt.ylabel("Count")
plt.title("Pulsar Glitch Size Distribution")

# Most glitching pulsars
top = df.groupby("{name_col or 'jname'}").size().sort_values(ascending=False).head(10)
print(top)

# Giant glitches only
giants = df[df["is_large_glitch"] == True]
print(f"{{len(giants):,}} giant glitches")

# Glitch rate analysis: glitches per year for well-studied pulsars
if "epoch_datetime" in df.columns:
    vela = df[df["{name_col or 'jname'}"].str.contains("0833", na=False)]
    print(f"Vela pulsar: {{len(vela)}} glitches")
```

## Data source

All data comes from the [Jodrell Bank Pulsar Glitch Catalogue](https://www.jb.man.ac.uk/pulsar/glitches.html),
maintained by the Jodrell Bank Centre for Astrophysics, University of Manchester
(Espinoza et al. 2011, Basu et al. 2022).

## Update schedule

Quarterly (Feb/May/Aug/Nov 1st at 09:30 UTC) via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [pulsar-catalog](https://huggingface.co/datasets/juliensimon/pulsar-catalog) — ATNF Pulsar Catalogue
- [mcgill-magnetar-catalog](https://huggingface.co/datasets/juliensimon/mcgill-magnetar-catalog) — McGill Magnetar Catalog
- [gravitational-wave-events](https://huggingface.co/datasets/juliensimon/gravitational-wave-events) — LIGO/Virgo/KAGRA Gravitational Wave Events
- [supernova-remnants](https://huggingface.co/datasets/juliensimon/supernova-remnants) — Supernova Remnant Catalog

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a \u2764\ufe0f on the [dataset page](https://huggingface.co/datasets/juliensimon/pulsar-glitch-catalog) and share feedback in the Community tab! Also consider giving a \u2b50\ufe0f to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{pulsar_glitch_catalog,
  author = {{Simon, Julien}},
  title = {{Jodrell Bank Pulsar Glitch Catalogue}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/pulsar-glitch-catalog}},
  note = {{Based on Jodrell Bank Pulsar Glitch Catalogue (Espinoza et al. 2011)}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update pulsar glitch catalog: {n_total:,} glitches across {n_pulsars:,} pulsars"
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
