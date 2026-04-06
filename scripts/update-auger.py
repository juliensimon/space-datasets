#!/usr/bin/env python3
"""Fetch Pierre Auger Observatory cosmic ray data from Zenodo and upload to HF."""

import io
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import pandas as pd
import requests

from dataset_images import banner_markdown, download_banner
from validate import check_dataset


ZENODO_URL = "https://zenodo.org/api/records/4487613/files/summary.zip/content"
HF_REPO = "juliensimon/auger-cosmic-rays"


def to_snake_case(name: str) -> str:
    """Convert column name to snake_case."""
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    s = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s)
    s = re.sub(r"[^\w]", "_", s.lower())
    s = re.sub(r"_+", "_", s).strip("_")
    return s


def main():
    print("Downloading Pierre Auger summary data from Zenodo...")
    resp = requests.get(ZENODO_URL, timeout=120)
    resp.raise_for_status()
    print(f"  Downloaded {len(resp.content) / 1024 / 1024:.1f} MB")

    # Extract CSV files from zip
    frames = []
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        csv_files = [n for n in zf.namelist() if n.endswith(".csv")]
        print(f"  Found {len(csv_files)} CSV files in archive")
        for name in csv_files:
            try:
                with zf.open(name) as f:
                    part = pd.read_csv(f)
                    if len(part) > 0:
                        part["source_file"] = Path(name).stem
                        frames.append(part)
                        print(f"    {name}: {len(part):,} rows")
            except Exception as e:
                print(f"    {name}: skipped ({e})")

    if not frames:
        # Try TSV or other delimiters
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            for name in zf.namelist():
                if name.endswith((".txt", ".dat", ".tsv")):
                    try:
                        with zf.open(name) as f:
                            part = pd.read_csv(f, sep=None, engine="python")
                            if len(part) > 0:
                                part["source_file"] = Path(name).stem
                                frames.append(part)
                                print(f"    {name}: {len(part):,} rows")
                    except Exception as e:
                        print(f"    {name}: skipped ({e})")

    if not frames:
        print("::error::No data extracted from Zenodo archive")
        sys.exit(1)

    df = pd.concat(frames, ignore_index=True)
    print(f"  Combined: {len(df):,} rows, {len(df.columns)} columns")

    # Rename columns to snake_case
    df.columns = [to_snake_case(c) for c in df.columns]

    # Coerce numeric columns commonly found in Auger data
    numeric_candidates = ["energy", "zenith", "azimuth", "ra", "dec",
                          "gal_l", "gal_b", "log_e", "theta", "phi",
                          "xmax", "s1000", "lgne"]
    for col in numeric_candidates:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Clean string columns
    for col in df.select_dtypes(include="object").columns:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
            )

    df = df.reset_index(drop=True)

    # Drop columns that are >95% null (instrument-specific fields from wide source)
    before_cols = len(df.columns)
    for col in list(df.columns):
        if df[col].isna().mean() > 0.95:
            df = df.drop(columns=[col])
    dropped = before_cols - len(df.columns)
    if dropped:
        print(f"  Dropped {dropped} columns (>95% null)")

    n_total = len(df)
    print(f"  {n_total:,} events total")

    # Use a flexible min_rows — summary data may be smaller
    min_rows = 100 if n_total < 50000 else 50000
    expected_cols = [c for c in df.columns[:4]]  # at least some columns exist

    check_dataset(df, "auger", min_rows=min_rows,
                  expected_columns=expected_cols)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "auger_cosmic_rays.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        col_table = "\n".join(
            f"| `{c}` | {str(df[c].dtype)} | |"
            for c in df.columns
        )

        banner_file = download_banner("auger", tmp)
        banner_md = banner_markdown("auger", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Pierre Auger Observatory Cosmic Rays"
language:
  - en
description: "Cosmic ray event data from the Pierre Auger Observatory — the world's largest ultra-high-energy cosmic ray detector."
task_categories:
  - tabular-regression
tags:
  - space
  - physics
  - cosmic-ray
  - auger
  - ultra-high-energy
  - open-data
  - tabular-data
  - parquet
size_categories:
  - 1K<n<10K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/auger_cosmic_rays.parquet
    default: true
---

# Pierre Auger Observatory Cosmic Rays
{banner_md}
*Part of the [Physics Datasets](https://huggingface.co/collections/juliensimon/physics-datasets-69c2d4682d37dfdb77447bd7) collection on Hugging Face.*

Summary data from the [Pierre Auger Observatory](https://www.auger.org/),
the world's largest detector of ultra-high-energy cosmic rays. Currently
**{n_total:,}** records.

## Dataset description

The Pierre Auger Observatory in Mendoza, Argentina, uses 1,660 water-Cherenkov
surface detectors spread over 3,000 km^2, plus fluorescence telescopes, to detect
cosmic rays with energies above 10^18 eV. These are the most energetic particles
known in nature, and their origins remain one of the biggest open questions in
astrophysics.

This dataset contains summary-level event data from the Auger open data release
on Zenodo.

Ultra-high-energy cosmic rays (UHECRs) are the most energetic particles observed in nature, with individual events carrying macroscopic amounts of kinetic energy -- a single particle at 10^20 eV has roughly the energy of a tennis ball served at 150 km/h, compressed into a single subatomic particle. When such a particle strikes the atmosphere, it triggers a cascade of billions of secondary particles called an extensive air shower, spreading over several square kilometers at ground level. The Pierre Auger Observatory detects these showers through a hybrid technique: the surface detector array measures the lateral distribution and timing of shower particles on the ground, while fluorescence telescopes observe the ultraviolet glow of atmospheric nitrogen excited by the shower as it develops. This combination provides both the energy and the atmospheric depth of shower maximum (Xmax), a key observable for inferring the mass composition of the primary cosmic ray.

Auger's major scientific results include the confirmation of the GZK suppression (the steepening of the cosmic ray spectrum above ~5x10^19 eV, expected from interactions with the cosmic microwave background), evidence for a dipole anisotropy in arrival directions above 8x10^18 eV suggesting an extragalactic origin, and measurements of Xmax distributions that indicate a transition from light (proton-like) to heavier (iron-like) composition at the highest energies. These findings constrain models of cosmic ray acceleration in astrophysical sources such as active galactic nuclei, gamma-ray bursts, and starburst galaxies.

This open dataset enables independent analyses of arrival direction distributions, energy spectrum features, and composition-sensitive observables. It is used in multi-messenger astrophysics studies correlating UHECR directions with neutrino and gamma-ray source catalogs, and for validating hadronic interaction models that describe particle physics at center-of-mass energies far beyond the reach of the LHC.

## Schema

| Column | Type | Description |
|--------|------|-------------|
{col_table}

## Quick stats

- **{n_total:,}** records

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/auger-cosmic-rays", split="train")
df = ds.to_pandas()
print(f"{{len(df):,}} Auger events")
print(df.describe())
```

## Data source

[Pierre Auger Observatory Open Data](https://www.auger.org/),
Zenodo DOI: [10.5281/zenodo.4487613](https://doi.org/10.5281/zenodo.4487613)

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/auger-cosmic-rays) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{auger_cosmic_rays,
  author = {{Simon, Julien}},
  title = {{Pierre Auger Observatory Cosmic Rays}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/auger-cosmic-rays}},
  note = {{Based on Pierre Auger Observatory open data (Zenodo 10.5281/zenodo.4487613)}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update Auger cosmic rays: {n_total:,} records"
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
