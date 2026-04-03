#!/usr/bin/env python3
"""Fetch Green's SNR Catalog from HEASARC and upload to HF."""

import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd
import requests

from dataset_images import banner_markdown, download_banner
from validate import check_dataset


TAP_URL = "https://heasarc.gsfc.nasa.gov/xamin/vo/tap/sync"
HF_REPO = "juliensimon/supernova-remnants"

ADQL = """\
SELECT name, alt_names, ra, dec, lii, bii, major_diameter, minor_diameter,
  type, flux_1_ghz, spectral_index
FROM snrgreen ORDER BY name\
"""

SNR_TYPE_MAP = {
    "S": "shell",
    "F": "filled-centre",
    "C": "composite",
    "?": "uncertain",
}


def fetch_catalog() -> pd.DataFrame:
    """Try CSV first, fall back to JSON, then pipe-delimited text."""
    # Attempt 1: CSV
    print("Fetching Green's SNR catalog (CSV)...")
    resp = requests.get(TAP_URL, params={
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": ADQL,
    }, timeout=120)
    resp.raise_for_status()

    try:
        df = pd.read_csv(io.StringIO(resp.text))
        if len(df) > 100 and "name" in df.columns:
            print(f"  CSV parse OK: {len(df):,} rows")
            return df
    except Exception as e:
        print(f"  CSV parse failed: {e}")

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

    # Ensure numeric columns
    for col in ["ra", "dec", "lii", "bii", "major_diameter", "minor_diameter",
                "flux_1_ghz", "spectral_index"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Derived column: full SNR type name
    if "type" in df.columns:
        # Extract the leading letter(s) before any qualifiers like '?' suffix
        df["snr_type_name"] = df["type"].apply(
            lambda x: SNR_TYPE_MAP.get(str(x).strip().rstrip("?"), "uncertain")
            if pd.notna(x) and str(x).strip() else None
        )

    print(f"  {len(df):,} SNRs total")

    check_dataset(df, "snr", min_rows=200,
        expected_columns=["name", "ra", "dec", "type", "flux_1_ghz"],
        critical_columns=["name", "ra", "dec"])

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "snr.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        # Compute stats for README
        n_total = len(df)
        type_counts = df["snr_type_name"].value_counts().to_dict() if "snr_type_name" in df.columns else {}
        n_shell = type_counts.get("shell", 0)
        n_filled = type_counts.get("filled-centre", 0)
        n_composite = type_counts.get("composite", 0)

        banner_file = download_banner("snr", tmp)
        banner_md = banner_markdown("snr", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Green's Supernova Remnant Catalog"
language:
  - en
description: "Galactic supernova remnants from Green's catalog with positions, angular sizes, radio flux, and spectral indices"
task_categories:
  - tabular-classification
tags:
  - space
  - supernova-remnant
  - snr
  - astronomy
  - radio
  - galactic
  - open-data
  - tabular-data
  - parquet
size_categories:
  - n<1K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/snr.parquet
    default: true
---

# Green's Supernova Remnant Catalog
{banner_md}
*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

![Update SNR](https://github.com/juliensimon/space-datasets/actions/workflows/update-snr.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.snr&label=updated&color=brightgreen)

Complete catalog of Galactic supernova remnants from
[Green's SNR Catalog](https://www.mrao.cam.ac.uk/surveys/snrs/),
sourced via NASA HEASARC. Currently **{n_total:,}** SNRs.

## Dataset description

Supernova remnants (SNRs) are the expanding shells of gas and dust left behind after a
supernova explosion. They are key sources of cosmic rays and play a major role in the
chemical enrichment of the interstellar medium. Green's catalog is the standard reference
for Galactic SNRs, maintained since 1984.

This dataset includes positions (equatorial and Galactic), angular sizes, morphological
type, 1 GHz radio flux density, and radio spectral index for each remnant.

Supernova remnants are among the most important objects in astrophysics. Their expanding blast waves are widely believed to be the primary accelerators of Galactic cosmic rays up to the "knee" of the cosmic ray spectrum (~3 PeV), a hypothesis supported by detections of TeV gamma-ray and non-thermal X-ray emission from young SNR shells. The three morphological types in Green's catalog -- shell, filled-centre (plerion), and composite -- reflect distinct physical configurations: shell-type remnants are dominated by the forward shock sweeping up the interstellar medium, filled-centre remnants are powered by a central pulsar wind nebula, and composites exhibit both features.

The radio spectral index is a key diagnostic: shell-type SNRs typically show spectral indices around -0.5 (consistent with diffusive shock acceleration of electrons in the Sedov-Taylor phase), while filled-centre remnants powered by pulsar winds tend to have flatter spectra (-0.0 to -0.3). The 1 GHz flux density, combined with distance estimates from HI absorption or association with molecular clouds, constrains the total radio luminosity and energy budget of each remnant. Green's catalog, continuously maintained since 1984 and updated through careful literature review, remains the definitive census of the ~300 known Galactic SNRs -- a number thought to represent only a fraction of the true population, with many remnants hidden behind dense Galactic dust or too old and faint to detect at radio wavelengths.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `name` | string | SNR designation (Galactic coordinates, e.g. "G001.0-00.1") |
| `alt_names` | string | Alternative/common names (e.g. "Cas A", "Crab Nebula") |
| `ra` | float | Right ascension (degrees) |
| `dec` | float | Declination (degrees) |
| `lii` | float | Galactic longitude (degrees) |
| `bii` | float | Galactic latitude (degrees) |
| `major_diameter` | float | Angular size major axis (arcmin) |
| `minor_diameter` | float | Angular size minor axis (arcmin) |
| `type` | string | Morphological type code (S, F, C, ?) |
| `flux_1_ghz` | float | Radio flux density at 1 GHz (Jy) |
| `spectral_index` | float | Radio spectral index |
| `snr_type_name` | string | Full type name: shell, filled-centre, composite, uncertain |

## Quick stats

- **{n_total:,}** supernova remnants
- **{n_shell}** shell, **{n_filled}** filled-centre, **{n_composite}** composite

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/supernova-remnants", split="train")
df = ds.to_pandas()

# SNRs by type
print(df["snr_type_name"].value_counts())

# Brightest SNRs at 1 GHz
top = df.nlargest(10, "flux_1_ghz")[["name", "alt_names", "flux_1_ghz"]]

# Sky distribution in Galactic coordinates
import matplotlib.pyplot as plt
plt.scatter(df["lii"], df["bii"], s=5)
plt.xlabel("Galactic longitude (deg)")
plt.ylabel("Galactic latitude (deg)")
plt.title("Galactic SNR Distribution")
```

## Data source

All data comes from [Green's SNR Catalog](https://www.mrao.cam.ac.uk/surveys/snrs/)
hosted by NASA's High Energy Astrophysics Science Archive Research Center (HEASARC),
accessed via the TAP protocol.

## Update schedule

Quarterly (1st Monday of January, April, July, October at 19:00 UTC) via
[GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [gamma-ray-bursts](https://huggingface.co/datasets/juliensimon/gamma-ray-bursts) — Fermi GBM GRB Catalog
- [gravitational-waves](https://huggingface.co/datasets/juliensimon/gravitational-wave-events) — LIGO/Virgo detections
- [exoplanets](https://huggingface.co/datasets/juliensimon/nasa-exoplanets) — NASA Exoplanet Archive

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/supernova-remnants) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{supernova_remnants,
  author = {{Simon, Julien}},
  title = {{Green's Supernova Remnant Catalog}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/supernova-remnants}},
  note = {{Based on Green's SNR Catalog via NASA HEASARC}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update SNR catalog: {n_total:,} remnants"
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
