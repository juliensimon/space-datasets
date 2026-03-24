#!/usr/bin/env python3
"""Fetch NVSS radio source catalog from VizieR and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from validate import check_dataset
from vizier_tap import vizier_query

HF_REPO = "juliensimon/nvss-radio-catalog"

ADQL = """SELECT * FROM "VIII/65/nvss" """

RENAME = {
    "NVSS": "source_name",
    "RAJ2000": "ra_deg",
    "DEJ2000": "dec_deg",
    "S1_4": "flux_1400mhz_mjy",
    "e_S1_4": "flux_error_mjy",
    "MajAxis": "major_axis_arcsec",
    "MinAxis": "minor_axis_arcsec",
    "PA": "position_angle_deg",
    "e_RAJ2000": "ra_error_arcsec",
    "e_DEJ2000": "dec_error_arcsec",
    "resFlux": "residual_flux",
}

NUMERIC_COLS = [
    "ra_deg", "dec_deg", "flux_1400mhz_mjy", "flux_error_mjy",
    "major_axis_arcsec", "minor_axis_arcsec", "position_angle_deg",
    "ra_error_arcsec", "dec_error_arcsec",
]


def main():
    print("Fetching NVSS radio source catalog from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} raw rows")

    # Rename columns
    df = df.rename(columns=RENAME)

    # Type conversions
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Stats
    n_total = len(df)
    flux_median = df["flux_1400mhz_mjy"].median()
    dec_min, dec_max = df["dec_deg"].min(), df["dec_deg"].max()

    # Validate
    check_dataset(
        df,
        "nvss-radio",
        min_rows=1_500_000,
        expected_columns=["source_name", "ra_deg", "dec_deg", "flux_1400mhz_mjy"],
        critical_columns=["source_name", "ra_deg", "dec_deg", "flux_1400mhz_mjy"],
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "nvss_radio_sources.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "NVSS Radio Source Catalog"
language:
  - en
description: "NRAO VLA Sky Survey (NVSS) catalog with {n_total:,} discrete radio sources at 1.4 GHz covering 82% of the sky."
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - radio
  - nvss
  - vla
  - nrao
  - astronomy
  - 1400mhz
  - open-data
size_categories:
  - 1M<n<10M
---

# NVSS Radio Source Catalog

The NRAO VLA Sky Survey (NVSS) -- THE foundational 1.4 GHz radio survey covering 82% of the celestial
sky (declination > -40 deg) with **{n_total:,}** discrete radio sources. This is the most widely
used radio continuum survey in astronomy.

## Dataset description

The NVSS used the VLA in its compact D and DnC configurations to survey the sky north of
declination -40 degrees at 1.4 GHz with ~45" resolution and a completeness limit of about
2.5 mJy. The resulting catalog is the primary reference for radio source populations and
is widely used for cross-matching with optical, infrared, and X-ray catalogs.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `source_name` | string | NVSS source name (HHMMSS+DDMMSS format) |
| `ra_deg` | float64 | Right ascension J2000 (degrees) |
| `dec_deg` | float64 | Declination J2000 (degrees) |
| `flux_1400mhz_mjy` | float64 | Integrated flux density at 1.4 GHz (mJy) |
| `flux_error_mjy` | float64 | Flux density uncertainty (mJy) |
| `major_axis_arcsec` | float64 | Fitted major axis FWHM (arcsec) |
| `minor_axis_arcsec` | float64 | Fitted minor axis FWHM (arcsec) |
| `position_angle_deg` | float64 | Fitted position angle (degrees) |
| `ra_error_arcsec` | float64 | RA position uncertainty (arcsec) |
| `dec_error_arcsec` | float64 | Dec position uncertainty (arcsec) |
| `residual_code` | string | Residual code from Gaussian fitting |

## Quick stats

- **{n_total:,}** radio sources
- Median flux density: {flux_median:.2f} mJy
- Declination range: {dec_min:.1f} to {dec_max:.1f} degrees
- Sky coverage: ~82% of the celestial sphere (dec > -40 deg)

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/nvss-radio-catalog", split="train")
df = ds.to_pandas()

# Flux distribution
import matplotlib.pyplot as plt
df["flux_1400mhz_mjy"].clip(upper=1000).hist(bins=200, log=True)
plt.xlabel("Flux density at 1.4 GHz (mJy)")
plt.ylabel("Count")
plt.title("NVSS Source Flux Distribution")
plt.show()

# Sky density map
plt.hexbin(df["ra_deg"], df["dec_deg"], gridsize=100, mincnt=1)
plt.colorbar(label="Source count")
plt.xlabel("RA (deg)")
plt.ylabel("Dec (deg)")
plt.title("NVSS Sky Density")
plt.show()

# Bright sources (> 1 Jy)
bright = df[df["flux_1400mhz_mjy"] > 1000]
print(f"Sources > 1 Jy: {{len(bright):,}}")
```

## Data source

Condon, J.J., Cotton, W.D., Greisen, E.W., Yin, Q.F., Perley, R.A., Taylor, G.B.,
and Broderick, J.J. (1998), *The NRAO VLA Sky Survey.* Astronomical Journal, 115, 1693.
Via VizieR CDS (VIII/65).

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Citation

```bibtex
@dataset{{nvss_radio_catalog,
  author = {{Simon, Julien}},
  title = {{NVSS Radio Source Catalog}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/nvss-radio-catalog}},
  note = {{Based on Condon et al. (1998) via VizieR CDS}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update NVSS radio catalog: {n_total:,} sources"
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
