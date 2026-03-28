#!/usr/bin/env python3
"""Fetch FIRST radio survey catalog from VizieR and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from validate import check_dataset
from vizier_tap import vizier_query

HF_REPO = "juliensimon/first-radio-catalog"

ADQL = """SELECT * FROM "VIII/92/first14" """

RENAME = {
    "FIRST": "source_name",
    "RAJ2000": "ra_deg",
    "DEJ2000": "dec_deg",
    "Fpeak": "peak_flux_mjy",
    "Fint": "integrated_flux_mjy",
    "Rms": "rms_mjy",
    "Maj": "major_axis_arcsec",
    "Min": "minor_axis_arcsec",
    "PA": "position_angle_deg",
    "fMaj": "deconv_major_arcsec",
    "fMin": "deconv_minor_arcsec",
    "fPA": "deconv_pa_deg",
}

NUMERIC_COLS = [
    "ra_deg", "dec_deg", "peak_flux_mjy", "integrated_flux_mjy", "rms_mjy",
    "major_axis_arcsec", "minor_axis_arcsec", "position_angle_deg",
    "deconv_major_arcsec", "deconv_minor_arcsec", "deconv_pa_deg",
]


def main():
    print("Fetching FIRST radio survey catalog from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} raw rows")

    # Rename columns
    df = df.rename(columns=RENAME)

    # Type conversions
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Derived column
    df["is_resolved"] = df["deconv_major_arcsec"] > 0

    # Stats
    n_total = len(df)
    n_resolved = int(df["is_resolved"].sum())
    flux_median = df["peak_flux_mjy"].median()
    ra_min, ra_max = df["ra_deg"].min(), df["ra_deg"].max()
    dec_min, dec_max = df["dec_deg"].min(), df["dec_deg"].max()

    # Validate
    check_dataset(
        df,
        "first-radio",
        min_rows=800_000,
        expected_columns=["source_name", "ra_deg", "dec_deg", "peak_flux_mjy", "integrated_flux_mjy"],
        critical_columns=["source_name", "ra_deg", "dec_deg", "peak_flux_mjy"],
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "first_radio_sources.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "FIRST Radio Survey Catalog"
language:
  - en
description: "Faint Images of the Radio Sky at Twenty-cm (FIRST) survey catalog with {n_total:,} radio sources at 1.4 GHz."
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - radio
  - first
  - vla
  - astronomy
  - 1400mhz
  - open-data
  - tabular-data
  - parquet
size_categories:
  - 100K<n<1M
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/first_radio_sources.parquet
    default: true
---

# FIRST Radio Survey Catalog

*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

The Faint Images of the Radio Sky at Twenty-cm (FIRST) survey catalog, covering 10,575 square degrees
at 1.4 GHz with 5 arcsecond resolution using the NRAO VLA. Contains **{n_total:,}** discrete radio sources.

A natural companion to NVSS, FIRST provides higher angular resolution over a smaller sky area.

## Dataset description

The FIRST survey used the VLA in its B-configuration to produce a map of the radio sky at
1.4 GHz with ~5" resolution and a typical rms of 0.15 mJy/beam. The catalog includes
source positions, peak and integrated flux densities, and fitted source sizes.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `source_name` | string | FIRST source name (HHMMSS.s+DDMMSS format) |
| `ra_deg` | float64 | Right ascension J2000 (degrees) |
| `dec_deg` | float64 | Declination J2000 (degrees) |
| `peak_flux_mjy` | float64 | Peak flux density (mJy/beam) |
| `integrated_flux_mjy` | float64 | Integrated flux density (mJy) |
| `rms_mjy` | float64 | Local rms noise (mJy/beam) |
| `major_axis_arcsec` | float64 | Fitted major axis FWHM (arcsec) |
| `minor_axis_arcsec` | float64 | Fitted minor axis FWHM (arcsec) |
| `position_angle_deg` | float64 | Fitted position angle (degrees) |
| `deconv_major_arcsec` | float64 | Deconvolved major axis (arcsec, 0 if unresolved) |
| `deconv_minor_arcsec` | float64 | Deconvolved minor axis (arcsec) |
| `deconv_pa_deg` | float64 | Deconvolved position angle (degrees) |
| `is_resolved` | bool | True if deconvolved major axis > 0 |

## Quick stats

- **{n_total:,}** radio sources
- **{n_resolved:,}** resolved sources ({n_resolved / n_total * 100:.1f}%)
- Median peak flux: {flux_median:.2f} mJy/beam
- Sky coverage: RA {ra_min:.1f}--{ra_max:.1f} deg, Dec {dec_min:.1f}--{dec_max:.1f} deg

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/first-radio-catalog", split="train")
df = ds.to_pandas()

# Flux distribution
import matplotlib.pyplot as plt
df["peak_flux_mjy"].clip(upper=100).hist(bins=200, log=True)
plt.xlabel("Peak flux (mJy/beam)")
plt.ylabel("Count")
plt.title("FIRST Source Flux Distribution")
plt.show()

# Sky coverage map
plt.scatter(df["ra_deg"], df["dec_deg"], s=0.01, alpha=0.1)
plt.xlabel("RA (deg)")
plt.ylabel("Dec (deg)")
plt.title("FIRST Survey Sky Coverage")
plt.show()

# Resolved vs unresolved
print(f"Resolved: {{df['is_resolved'].sum():,}}")
print(f"Unresolved: {{(~df['is_resolved']).sum():,}}")
```

## Data source

Becker, R.H., White, R.L., and Helfand, D.J. (1995), *The FIRST Survey: Faint Images of the
Radio Sky at Twenty Centimeters.* Astrophysical Journal, 450, 559.
Catalog version 14Dec17. Via VizieR CDS (VIII/92).

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/first-radio-catalog) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{first_radio_catalog,
  author = {{Simon, Julien}},
  title = {{FIRST Radio Survey Catalog}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/first-radio-catalog}},
  note = {{Based on Becker, White & Helfand (1995) via VizieR CDS}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update FIRST radio catalog: {n_total:,} sources"
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
