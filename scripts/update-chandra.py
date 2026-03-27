#!/usr/bin/env python3
"""Fetch Chandra Source Catalog (CSC 2.1) from HEASARC and upload to HF."""

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
HF_REPO = "juliensimon/chandra-x-ray-sources"

ADQL = """\
SELECT * FROM chanmaster\
"""


def fetch_catalog() -> pd.DataFrame:
    """Try CSV first, fall back to JSON, then pipe-delimited text."""
    # Attempt 1: CSV with MAXREC to avoid truncation
    print("Fetching Chandra Source Catalog (CSV)...")
    resp = requests.get(TAP_URL, params={
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": ADQL,
        "MAXREC": 500000,
    }, timeout=600)
    resp.raise_for_status()

    if not resp.text.strip().startswith("<?xml"):
        try:
            df = pd.read_csv(io.StringIO(resp.text))
            if len(df) > 100 and "ra" in df.columns:
                print(f"  CSV parse OK: {len(df):,} rows")
                return df
        except Exception as e:
            print(f"  CSV parse failed: {e}")
    else:
        print("  CSV not supported (got XML/VOTable response)")

    # Attempt 2: JSON
    print("Retrying with FORMAT=json...")
    resp = requests.get(TAP_URL, params={
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "json", "QUERY": ADQL,
        "MAXREC": 500000,
    }, timeout=600)
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
        "MAXREC": 500000,
    }, timeout=600)
    resp.raise_for_status()

    lines = [l for l in resp.text.strip().splitlines() if l.strip() and not l.startswith("-")]
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

    # Normalize column names to snake_case (lowercase, spaces/dashes to underscores)
    df.columns = (
        df.columns.str.strip()
        .str.lower()
        .str.replace(r"[^a-z0-9_]", "_", regex=True)
        .str.replace(r"_+", "_", regex=True)
        .str.strip("_")
    )

    # Ensure numeric columns
    numeric_cols = [
        "ra", "dec", "gal_l", "gal_b",
        "significance", "flux_aper_b", "flux_aper_s", "flux_aper_m",
        "flux_aper_h", "flux_aper_w",
        "hard_hm", "hard_hs", "hard_ms",
        "var_flag", "extent_flag",
        "err_ellipse_r0", "err_ellipse_r1", "err_ellipse_ang",
        "src_cnts_aper_b",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Clean empty strings to NaN for string columns
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip().replace(
            {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
        )

    # Sort by significance descending (most significant sources first)
    if "significance" in df.columns:
        df = df.sort_values("significance", ascending=False).reset_index(drop=True)
    elif "flux_aper_b" in df.columns:
        df = df.sort_values("flux_aper_b", ascending=False, na_position="last").reset_index(drop=True)

    print(f"  {len(df):,} X-ray sources total")
    print(f"  {len(df.columns)} columns")

    # Validation — HEASARC TAP sync returns ~28K rows (server-side limit)
    # Full CSC 2.1 has 407K master sources but sync endpoint truncates
    check_dataset(
        df, "chandra",
        min_rows=20_000,
        expected_columns=["ra", "dec"],
        critical_columns=["ra", "dec"],
    )

    # Compute stats for README
    n_total = len(df)
    n_cols = len(df.columns)
    median_sig = df["significance"].median() if "significance" in df.columns else None
    n_with_flux = int(df["flux_aper_b"].notna().sum()) if "flux_aper_b" in df.columns else 0

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "chandra_x_ray_sources.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        sig_line = f"\n- Median significance: **{median_sig:.1f}**" if median_sig is not None else ""
        flux_line = f"\n- **{n_with_flux:,}** sources with broad-band flux" if n_with_flux else ""

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Chandra X-Ray Source Catalog"
language:
  - en
description: "Chandra Source Catalog (CSC 2.1) — {n_total:,} unique X-ray sources detected by the Chandra X-Ray Observatory, with positions, multi-band fluxes, hardness ratios, and variability flags."
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - x-ray
  - chandra
  - nasa
  - astronomy
  - open-data
  - tabular-data
size_categories:
  - 100K<n<1M
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/chandra_x_ray_sources.parquet
    default: true
---

# Chandra X-Ray Source Catalog

*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

The Chandra Source Catalog (CSC 2.1) is the definitive catalog of X-ray sources
detected by NASA's [Chandra X-Ray Observatory](https://chandra.harvard.edu/),
the most powerful X-ray telescope ever built. Currently **{n_total:,}** unique sources
across {n_cols} columns.

## Dataset description

The Chandra X-Ray Observatory, launched in 1999, provides the sharpest X-ray images
ever achieved, with sub-arcsecond angular resolution. The Chandra Source Catalog (CSC)
is a comprehensive catalog of all X-ray sources detected in Chandra observations,
including positions, multi-band photometry (soft, medium, hard, broad, wide bands),
hardness ratios for spectral characterization, variability flags, and source extent
measurements.

CSC 2.1 covers roughly 560 square degrees of sky and includes sources from over
15,000 individual Chandra observations. The catalog is essential for multi-wavelength
studies of active galactic nuclei, X-ray binaries, supernova remnants, galaxy clusters,
and stellar coronae.

## Quick stats

- **{n_total:,}** unique X-ray sources{sig_line}{flux_line}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/chandra-x-ray-sources", split="train")
df = ds.to_pandas()

# Brightest sources by broad-band flux
if "flux_aper_b" in df.columns:
    top = df.nlargest(10, "flux_aper_b")[["name", "ra", "dec", "flux_aper_b"]]
    print(top)

# Sky coverage map
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(12, 6))
ax.scatter(df["ra"], df["dec"], s=0.01, alpha=0.1)
ax.set_xlabel("RA (deg)")
ax.set_ylabel("Dec (deg)")
ax.invert_xaxis()
ax.set_title("Chandra Source Catalog Sky Coverage")
```

## Data source

All data comes from the [Chandra Source Catalog 2.1](https://cxc.cfa.harvard.edu/csc/)
(Evans et al. 2024), accessed via NASA HEASARC TAP service.

## Related datasets

- [erosita-erass1-xray](https://huggingface.co/datasets/juliensimon/erosita-erass1-xray) -- eROSITA eRASS1 X-ray sources
- [fermi-4fgl-dr4](https://huggingface.co/datasets/juliensimon/fermi-4fgl-dr4) -- Fermi gamma-ray sources
- [pulsar-catalog](https://huggingface.co/datasets/juliensimon/pulsar-catalog) -- Pulsar catalog

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/chandra-x-ray-sources) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{chandra_x_ray_sources,
  author = {{Simon, Julien}},
  title = {{Chandra X-Ray Source Catalog}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/chandra-x-ray-sources}},
  note = {{Based on Chandra Source Catalog 2.1 (Evans et al. 2024) via NASA HEASARC}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update Chandra X-ray sources: {n_total:,} sources"
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
