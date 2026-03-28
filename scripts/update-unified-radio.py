#!/usr/bin/env python3
"""Fetch SPECFIND v3 unified radio catalog from VizieR and upload to HF.

SPECFIND v3 (Stein, Vollmer et al. 2024) cross-matches radio sources across
50+ surveys including NVSS, FIRST, SUMSS, TGSS, GLEAM, and others. Each row
is a source measurement at a specific frequency with fitted spectral parameters.
"""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from validate import check_dataset
from vizier_tap import vizier_query

HF_REPO = "juliensimon/unified-radio-catalog"

ADQL = """SELECT * FROM "VIII/104/spectra" """

RENAME = {
    "Seq": "source_id",
    "Name": "source_name",
    "N": "n_frequencies",
    "a": "spectral_index",
    "b": "spectral_intercept",
    "nu": "frequency_mhz",
    "S(nu)": "flux_density_mjy",
    "e_S(nu)": "flux_density_error_mjy",
    "RAJ2000": "ra_deg",
    "DEJ2000": "dec_deg",
    "dFlux": "flux_residual_pct",
    "dRA": "ra_offset_arcsec",
    "dDE": "dec_offset_arcsec",
    "beam": "beam_arcsec",
}

NUMERIC_COLS = [
    "spectral_index",
    "spectral_intercept",
    "frequency_mhz",
    "flux_density_mjy",
    "flux_density_error_mjy",
    "ra_deg",
    "dec_deg",
    "flux_residual_pct",
    "ra_offset_arcsec",
    "dec_offset_arcsec",
    "beam_arcsec",
]

INT_COLS = [
    "source_id",
    "n_frequencies",
]


def main():
    print("Fetching SPECFIND v3 unified radio catalog from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} raw rows")

    # Rename columns
    df = df.rename(columns=RENAME)

    # Type conversions — numeric
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Type conversions — integer
    for col in INT_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int32")

    # Derive survey name from source_name prefix
    if "source_name" in df.columns:
        df["survey"] = df["source_name"].str.extract(r"^([A-Za-z0-9\[\]]+)", expand=False)

    # Derive frequency band label
    if "frequency_mhz" in df.columns:
        df["frequency_band"] = pd.cut(
            df["frequency_mhz"],
            bins=[0, 100, 500, 2000, 8000, 1e9],
            labels=["VLF", "low", "mid", "high", "SHF"],
            right=False,
        )

    # Sort by source_id, then frequency
    sort_cols = []
    if "source_id" in df.columns:
        sort_cols.append("source_id")
    if "frequency_mhz" in df.columns:
        sort_cols.append("frequency_mhz")
    if sort_cols:
        df = df.sort_values(sort_cols).reset_index(drop=True)

    # Drop recno (VizieR internal)
    if "recno" in df.columns:
        df = df.drop(columns=["recno"])

    # Stats
    n_total = len(df)
    n_sources = df["source_id"].nunique() if "source_id" in df.columns else 0
    n_surveys = df["survey"].nunique() if "survey" in df.columns else 0
    freq_min = df["frequency_mhz"].min() if "frequency_mhz" in df.columns else 0
    freq_max = df["frequency_mhz"].max() if "frequency_mhz" in df.columns else 0
    median_flux = df["flux_density_mjy"].median() if "flux_density_mjy" in df.columns else 0
    median_si = df["spectral_index"].median() if "spectral_index" in df.columns else 0

    # Validate
    check_dataset(
        df,
        "unified-radio",
        min_rows=1_500_000,
        expected_columns=["source_name", "ra_deg", "dec_deg", "frequency_mhz", "flux_density_mjy"],
        critical_columns=["source_name", "ra_deg", "dec_deg", "flux_density_mjy"],
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "unified_radio_catalog.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Unified Radio Catalog (SPECFIND v3)"
language:
  - en
description: "SPECFIND v3 unified radio source catalog with {n_total:,} cross-matched measurements across {n_surveys} radio surveys including NVSS, FIRST, SUMSS, TGSS, and GLEAM."
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - radio
  - nvss
  - first
  - sumss
  - astronomy
  - open-data
  - tabular-data
  - parquet
size_categories:
  - 1M<n<10M
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/unified_radio_catalog.parquet
    default: true
---

# Unified Radio Catalog (SPECFIND v3)

*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

The SPECFIND v3 unified radio source catalog, containing **{n_total:,}** cross-matched radio
source measurements from **{n_surveys}** surveys spanning {freq_min:.0f} to {freq_max:.0f} MHz.
SPECFIND positionally cross-identifies radio sources across major surveys including NVSS, FIRST,
SUMSS, TGSS, GLEAM, and dozens of others, then fits power-law radio spectra.

## Dataset description

SPECFIND (Vollmer et al. 2005, updated Stein et al. 2024) is the largest positional cross-identification
of radio continuum catalogs. Version 3 matches sources across 50+ radio surveys at frequencies from
{freq_min:.0f} to {freq_max:.0f} MHz, covering the entire sky. Each row represents a source detection at a
specific frequency, grouped by a unique source identifier (`source_id`). For sources detected in
multiple surveys, SPECFIND fits a power-law spectrum S(nu) = 10^b * nu^a, where `a` is the spectral
index and `b` is the intercept.

The catalog contains **{n_sources:,}** unique radio sources with measurements from surveys
including NVSS (1.4 GHz), FIRST (1.4 GHz), SUMSS (843 MHz), TGSS (150 MHz), GLEAM (200 MHz),
and many others.

## Key columns

| Column | Type | Description |
|--------|------|-------------|
| `source_id` | Int32 | Unique source identifier (groups cross-matched detections) |
| `source_name` | string | Survey-specific source designation |
| `ra_deg` | float64 | Right ascension J2000 (degrees) |
| `dec_deg` | float64 | Declination J2000 (degrees) |
| `frequency_mhz` | float64 | Observation frequency (MHz) |
| `flux_density_mjy` | float64 | Flux density at this frequency (mJy) |
| `flux_density_error_mjy` | float64 | Flux density uncertainty (mJy) |
| `spectral_index` | float64 | Fitted spectral index (a in S ~ nu^a) |
| `spectral_intercept` | float64 | Fitted spectral intercept (b in log S = a*log(nu) + b) |
| `n_frequencies` | Int32 | Number of frequency measurements for this source |
| `flux_residual_pct` | float64 | Flux residual from spectral fit (%) |
| `beam_arcsec` | float64 | Survey beam size (arcsec) |
| `survey` | string | Survey name extracted from source designation |
| `frequency_band` | category | Frequency band: VLF (<100), low (100-500), mid (500-2000), high (2-8 GHz), SHF (>8 GHz) |

Full schema includes {len(df.columns)} columns with positional offsets and uncertainties.

## Quick stats

- **{n_total:,}** total source measurements
- **{n_sources:,}** unique radio sources
- **{n_surveys}** contributing surveys
- Frequency range: {freq_min:.0f} to {freq_max:.0f} MHz
- Median flux density: {median_flux:.1f} mJy
- Median spectral index: {median_si:.2f}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/unified-radio-catalog", split="train")
df = ds.to_pandas()

# Group by source to see multi-frequency data
source = df[df["source_id"] == df["source_id"].iloc[0]]
print(f"Source {{source['source_name'].iloc[0]}}: {{len(source)}} frequencies")

# Spectral index distribution
import matplotlib.pyplot as plt
si = df.drop_duplicates("source_id")["spectral_index"].dropna()
si.clip(-3, 3).hist(bins=200)
plt.xlabel("Spectral index")
plt.ylabel("Count")
plt.title("Radio Source Spectral Index Distribution")
plt.axvline(-0.7, color="red", linestyle="--", label="Typical synchrotron")
plt.legend()
plt.show()

# Sky coverage map
plt.hexbin(df["ra_deg"], df["dec_deg"], gridsize=100, mincnt=1)
plt.colorbar(label="Measurement count")
plt.xlabel("RA (deg)")
plt.ylabel("Dec (deg)")
plt.title("SPECFIND v3 Sky Coverage")
plt.show()

# Survey contribution
print(df["survey"].value_counts().head(10))
```

## Data source

Stein, Y., Vollmer, B., Boch, T., et al. (2024), *SPECFIND v3.0 — A catalog of radio
continuum cross-identifications and spectra.* VizieR catalog VIII/104.
Based on Vollmer, B. et al. (2005, 2010). Via VizieR CDS.

## Related datasets

- [NVSS Radio Source Catalog](https://huggingface.co/datasets/juliensimon/nvss-radio-catalog) — NVSS 1.4 GHz survey, 1.8M sources
- [FIRST Radio Survey Catalog](https://huggingface.co/datasets/juliensimon/first-radio-catalog) — FIRST 1.4 GHz survey
- [VLASS Radio Sources](https://huggingface.co/datasets/juliensimon/vlass-radio-sources) — VLA Sky Survey 2-4 GHz

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/unified-radio-catalog) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{unified_radio_catalog,
  author = {{Simon, Julien}},
  title = {{Unified Radio Catalog (SPECFIND v3)}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/unified-radio-catalog}},
  note = {{Based on Stein, Vollmer et al. (2024) SPECFIND v3 via VizieR CDS}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update unified radio catalog: {n_total:,} measurements, {n_sources:,} sources"
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
