#!/usr/bin/env python3
"""Fetch VLASS Epoch 1 Quick Look component catalog from VizieR and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from validate import check_dataset
from vizier_tap import vizier_query

HF_REPO = "juliensimon/vlass-radio-sources"

ADQL = """SELECT * FROM "J/ApJS/255/30/comp" """

RENAME = {
    "CompName": "component_name",
    "CompId": "component_id",
    "IslId": "island_id",
    "RAJ2000": "ra_deg",
    "DEJ2000": "dec_deg",
    "e_RAJ2000": "ra_error_deg",
    "e_DEJ2000": "dec_error_deg",
    "Ftot": "total_flux_mjy",
    "e_Ftot": "total_flux_error_mjy",
    "Fpeak": "peak_flux_mjy_beam",
    "e_Fpeak": "peak_flux_error_mjy_beam",
    "Maj": "major_axis_arcsec",
    "e_Maj": "major_axis_error_arcsec",
    "Min": "minor_axis_arcsec",
    "e_Min": "minor_axis_error_arcsec",
    "PA": "position_angle_deg",
    "e_PA": "position_angle_error_deg",
    "FtotIsl": "island_total_flux_mjy",
    "e_FtotIsl": "island_total_flux_error_mjy",
    "Islrms": "island_rms_mjy_beam",
    "Islmean": "island_mean_mjy_beam",
    "ResIdIslrms": "residual_island_rms_mjy_beam",
    "ResidIslmean": "residual_island_mean_mjy_beam",
    "RAMdeg": "peak_ra_deg",
    "DEMdeg": "peak_dec_deg",
    "e_RAMdeg": "peak_ra_error_deg",
    "e_DEMdeg": "peak_dec_error_deg",
    "SCode": "source_code",
    "Xposn": "x_pixel",
    "e_Xposn": "x_pixel_error",
    "Yposn": "y_pixel",
    "e_Yposn": "y_pixel_error",
    "XposnMax": "peak_x_pixel",
    "e_XposnMax": "peak_x_pixel_error",
    "YposnMax": "peak_y_pixel",
    "e_YposnMax": "peak_y_pixel_error",
    "MajImgPlane": "major_axis_imgplane_arcsec",
    "e_MajImgPlane": "major_axis_imgplane_error_arcsec",
    "MinImgPlane": "minor_axis_imgplane_arcsec",
    "e_MinImgPlane": "minor_axis_imgplane_error_arcsec",
    "PAImgPlane": "pa_imgplane_deg",
    "e_PAImgPlane": "pa_imgplane_error_deg",
    "DCMaj": "deconv_major_arcsec",
    "e_DCMaj": "deconv_major_error_arcsec",
    "DCMin": "deconv_minor_arcsec",
    "e_DCMin": "deconv_minor_error_arcsec",
    "DCPA": "deconv_pa_deg",
    "e_DCPA": "deconv_pa_error_deg",
    "DCMajImgPlane": "deconv_major_imgplane_arcsec",
    "e_DCMajImgPlane": "deconv_major_imgplane_error_arcsec",
    "DCMinImgPlane": "deconv_minor_imgplane_arcsec",
    "e_DCMinImgPlane": "deconv_minor_imgplane_error_arcsec",
    "DCPAImgPlane": "deconv_pa_imgplane_deg",
    "e_DCPAImgPlane": "deconv_pa_imgplane_error_deg",
    "Tile": "tile",
    "Subtile": "subtile",
    "RASdeg": "subtile_ra_deg",
    "DESdeg": "subtile_dec_deg",
    "NVSSdist": "nvss_distance_arcsec",
    "FIRSTdist": "first_distance_arcsec",
    "PeakToRing": "peak_to_ring_ratio",
    "DupFlag": "duplicate_flag",
    "QualFlag": "quality_flag",
    "NNdist": "nearest_neighbor_arcsec",
    "BMaj": "beam_major_arcsec",
    "BMin": "beam_minor_arcsec",
    "BPA": "beam_pa_deg",
    "MainSample": "main_sample",
    "QLcutout": "ql_cutout_url",
}

NUMERIC_COLS = [
    "ra_deg", "dec_deg", "ra_error_deg", "dec_error_deg",
    "total_flux_mjy", "total_flux_error_mjy",
    "peak_flux_mjy_beam", "peak_flux_error_mjy_beam",
    "major_axis_arcsec", "major_axis_error_arcsec",
    "minor_axis_arcsec", "minor_axis_error_arcsec",
    "position_angle_deg", "position_angle_error_deg",
    "island_total_flux_mjy", "island_total_flux_error_mjy",
    "island_rms_mjy_beam", "island_mean_mjy_beam",
    "residual_island_rms_mjy_beam", "residual_island_mean_mjy_beam",
    "peak_ra_deg", "peak_dec_deg", "peak_ra_error_deg", "peak_dec_error_deg",
    "subtile_ra_deg", "subtile_dec_deg",
    "nvss_distance_arcsec", "first_distance_arcsec",
    "peak_to_ring_ratio", "nearest_neighbor_arcsec",
    "beam_major_arcsec", "beam_minor_arcsec", "beam_pa_deg",
    "deconv_major_arcsec", "deconv_major_error_arcsec",
    "deconv_minor_arcsec", "deconv_minor_error_arcsec",
    "deconv_pa_deg", "deconv_pa_error_deg",
]

INT_COLS = [
    "component_id", "island_id", "duplicate_flag", "quality_flag", "main_sample",
]


def main():
    print("Fetching VLASS Epoch 1 Quick Look component catalog from VizieR...")
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

    # Derived column: resolved flag (deconvolved major axis > 0)
    if "deconv_major_arcsec" in df.columns:
        df["is_resolved"] = df["deconv_major_arcsec"] > 0

    # Sort by RA
    df = df.sort_values("ra_deg").reset_index(drop=True)

    # Drop recno (VizieR internal)
    if "recno" in df.columns:
        df = df.drop(columns=["recno"])

    # Stats
    n_total = len(df)
    n_main = int(df["main_sample"].sum()) if "main_sample" in df.columns else 0
    n_resolved = int(df["is_resolved"].sum()) if "is_resolved" in df.columns else 0
    flux_median = df["peak_flux_mjy_beam"].median()
    dec_min, dec_max = df["dec_deg"].min(), df["dec_deg"].max()

    # Validate
    check_dataset(
        df,
        "vlass-radio",
        min_rows=500_000,
        expected_columns=["component_name", "ra_deg", "dec_deg", "total_flux_mjy", "peak_flux_mjy_beam"],
        critical_columns=["component_name", "ra_deg", "dec_deg", "peak_flux_mjy_beam"],
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "vlass_radio_sources.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "VLASS Radio Sources (Epoch 1)"
language:
  - en
description: "Very Large Array Sky Survey (VLASS) Epoch 1 Quick Look component catalog with {n_total:,} radio source detections at 2-4 GHz (S-band)."
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - radio
  - vlass
  - vla
  - nrao
  - astronomy
  - open-data
  - tabular-data
size_categories:
  - 1M<n<10M
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/vlass_radio_sources.parquet
    default: true
---

# VLASS Radio Sources (Epoch 1)

*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

The Very Large Array Sky Survey (VLASS) Epoch 1 Quick Look component catalog from CIRADA,
containing **{n_total:,}** radio source detections at S-band (2-4 GHz) with ~2.5 arcsecond
resolution, covering the sky north of declination -40 degrees. VLASS is the modern successor
to NVSS and FIRST, offering higher resolution and multi-epoch coverage.

## Dataset description

VLASS is a synoptic all-sky radio survey using the Karl G. Jansky Very Large Array (VLA) in
its B-configuration at S-band (2-4 GHz). The survey covers the entire sky visible to the VLA
(declination > -40 deg, ~33,885 sq. deg.) in three epochs. This catalog contains Quick Look
component detections from Epoch 1, processed by the Canadian Initiative for Radio Astronomy
Data Analysis (CIRADA). Each row is a Gaussian component fitted to a radio detection using PyBDSF.

Of the {n_total:,} total detections, **{n_main:,}** are in the curated main sample
(duplicate-free, quality-filtered) and **{n_resolved:,}** are resolved sources.

## Key columns

| Column | Type | Description |
|--------|------|-------------|
| `component_name` | string | IAU component name (VLASS1QLCIR JHHMMSS.ss+DDMMSS.s) |
| `ra_deg` | float64 | Right ascension J2000 (degrees) |
| `dec_deg` | float64 | Declination J2000 (degrees) |
| `total_flux_mjy` | float64 | Integrated flux density at S-band (mJy) |
| `peak_flux_mjy_beam` | float64 | Peak brightness at S-band (mJy/beam) |
| `major_axis_arcsec` | float64 | Fitted major axis FWHM (arcsec) |
| `minor_axis_arcsec` | float64 | Fitted minor axis FWHM (arcsec) |
| `position_angle_deg` | float64 | Fitted position angle (degrees) |
| `deconv_major_arcsec` | float64 | Deconvolved major axis (arcsec) |
| `deconv_minor_arcsec` | float64 | Deconvolved minor axis (arcsec) |
| `island_rms_mjy_beam` | float64 | Local rms noise (mJy/beam) |
| `source_code` | string | Component type: S(ingle), C(omplex), M(ultiple), E(xtended) |
| `nvss_distance_arcsec` | float64 | Angular separation from nearest NVSS source (arcsec) |
| `first_distance_arcsec` | float64 | Angular separation from nearest FIRST source (arcsec) |
| `duplicate_flag` | Int32 | Duplicate detection flag (0=unique) |
| `quality_flag` | Int32 | Quality flag (0=good) |
| `main_sample` | Int32 | Main sample membership (1=curated subset) |
| `is_resolved` | bool | True if deconvolved major axis > 0 |

Full schema includes {len(df.columns)} columns with uncertainties, beam properties, and image-plane measurements.

## Quick stats

- **{n_total:,}** total component detections
- **{n_main:,}** main sample sources (quality-filtered, duplicate-free)
- **{n_resolved:,}** resolved sources ({n_resolved / n_total * 100:.1f}%)
- Median peak flux: {flux_median:.2f} mJy/beam
- Declination range: {dec_min:.1f} to {dec_max:.1f} degrees
- Frequency: S-band (2-4 GHz), ~2.5 arcsec resolution

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/vlass-radio-sources", split="train")
df = ds.to_pandas()

# Main sample only (quality-filtered)
main = df[df["main_sample"] == 1]
print(f"Main sample: {{len(main):,}} sources")

# Flux distribution
import matplotlib.pyplot as plt
df["peak_flux_mjy_beam"].clip(upper=100).hist(bins=200, log=True)
plt.xlabel("Peak flux (mJy/beam)")
plt.ylabel("Count")
plt.title("VLASS Source Flux Distribution")
plt.show()

# Sky density map
plt.hexbin(df["ra_deg"], df["dec_deg"], gridsize=100, mincnt=1)
plt.colorbar(label="Source count")
plt.xlabel("RA (deg)")
plt.ylabel("Dec (deg)")
plt.title("VLASS Epoch 1 Sky Density")
plt.show()

# Cross-match proximity to NVSS/FIRST
has_nvss = df["nvss_distance_arcsec"] < 10
print(f"Within 10 arcsec of NVSS source: {{has_nvss.sum():,}}")
```

## Data source

Gordon, Y.A., et al. (2021), *A Catalog of Very Large Array Sky Survey (VLASS) Epoch 1
Quick Look Components, Version 2.* Astrophysical Journal Supplement Series, 255, 30.
Processed by CIRADA. Via VizieR CDS (J/ApJS/255/30).

## Related datasets

- [NVSS Radio Source Catalog](https://huggingface.co/datasets/juliensimon/nvss-radio-catalog) — predecessor 1.4 GHz survey, 1.8M sources
- [FIRST Radio Survey Catalog](https://huggingface.co/datasets/juliensimon/first-radio-catalog) — predecessor high-resolution 1.4 GHz survey

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/vlass-radio-sources) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{vlass_radio_sources,
  author = {{Simon, Julien}},
  title = {{VLASS Radio Sources (Epoch 1)}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/vlass-radio-sources}},
  note = {{Based on Gordon et al. (2021) via VizieR CDS}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update VLASS radio sources: {n_total:,} components"
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
