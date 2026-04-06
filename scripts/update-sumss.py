#!/usr/bin/env python3
"""Fetch SUMSS 843 MHz radio catalog from VizieR and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from dataset_images import banner_markdown, download_banner
from validate import check_dataset
from vizier_tap import vizier_query

HF_REPO = "juliensimon/sumss-radio-catalog"

ADQL = """SELECT * FROM "VIII/81B/sumss212" """

RENAME = {
    "RA_ICRS": "ra_deg",
    "RAJ2000": "ra_deg",
    "_RA": "ra_deg",
    "DE_ICRS": "dec_deg",
    "DEJ2000": "dec_deg",
    "_DE": "dec_deg",
    "Sp": "peak_flux_mjy",
    "St": "integrated_flux_mjy",
    "e_St": "e_integrated_flux_mjy",
    "Maj": "major_axis_arcsec",
    "Min": "minor_axis_arcsec",
    "PA": "position_angle_deg",
    "MajDec": "deconv_major_arcsec",
    "MinDec": "deconv_minor_arcsec",
    "PADec": "deconv_pa_deg",
    "Mosaic": "mosaic_name",
}

NUMERIC_COLS = [
    "ra_deg", "dec_deg", "peak_flux_mjy", "integrated_flux_mjy",
    "e_integrated_flux_mjy",
    "major_axis_arcsec", "minor_axis_arcsec", "position_angle_deg",
    "deconv_major_arcsec", "deconv_minor_arcsec", "deconv_pa_deg",
]


def main():
    print("Fetching SUMSS catalog from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} raw rows")

    # Rename columns
    df = df.rename(columns=RENAME)

    # Type conversions
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Derived column
    if "deconv_major_arcsec" in df.columns:
        df["is_resolved"] = df["deconv_major_arcsec"] > 0
    else:
        df["is_resolved"] = False

    # Clean string columns
    for col in ["mosaic_name"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
            )

    # Stats
    n_total = len(df)
    n_resolved = int(df["is_resolved"].sum())
    flux_median = df["peak_flux_mjy"].median() if "peak_flux_mjy" in df.columns else 0
    ra_min, ra_max = df["ra_deg"].min(), df["ra_deg"].max()
    dec_min, dec_max = df["dec_deg"].min(), df["dec_deg"].max()

    # Validate
    check_dataset(
        df,
        "sumss",
        min_rows=200_000,
        expected_columns=["ra_deg", "dec_deg"],
        critical_columns=["ra_deg", "dec_deg"],
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "sumss_radio_sources.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        banner_file = download_banner("sumss", tmp)
        banner_md = banner_markdown("sumss", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Sydney University Molonglo Sky Survey (SUMSS)"
language:
  - en
description: "SUMSS catalog of {n_total:,} radio sources at 843 MHz from the Molonglo Observatory Synthesis Telescope."
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - radio
  - sumss
  - molonglo
  - 843mhz
  - astronomy
  - open-data
  - tabular-data
  - parquet
size_categories:
  - 100K<n<1M
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/sumss_radio_sources.parquet
    default: true
---

# Sydney University Molonglo Sky Survey (SUMSS)
{banner_md}
*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

The Sydney University Molonglo Sky Survey (SUMSS) at 843 MHz, the southern-sky complement to
NVSS. Observed with the Molonglo Observatory Synthesis Telescope (MOST), covering declinations
south of -30 deg. Contains **{n_total:,}** discrete radio sources.

## Dataset description

SUMSS is a deep radio survey at 843 MHz covering 8,100 square degrees of the southern sky
(declination < -30 deg) with 45 x 45 cosec|dec| arcsecond resolution. It fills the gap left
by northern-hemisphere surveys like NVSS and FIRST, providing a matched-sensitivity southern
radio catalog essential for all-sky studies.

The Molonglo Observatory Synthesis Telescope (MOST) is a large east-west Earth-rotation aperture synthesis telescope located near Canberra, Australia. Originally built for pulsar research, it was reconfigured for continuum survey work at 843 MHz, a frequency chosen to complement the 1.4 GHz NVSS in the north. SUMSS achieves a limiting peak brightness of approximately 6 mJy/beam at declination -50 degrees, with sensitivity scaling as the cosecant of declination due to the telescope's cylindrical geometry. The catalog reaches roughly the same source density as NVSS, enabling seamless all-sky radio source studies when the two surveys are combined.

SUMSS is particularly important for studying radio sources in the Magellanic Clouds, the Galactic bulge at southern latitudes, and southern galaxy clusters that are inaccessible to VLA-based surveys. The 843 MHz observing frequency also provides a longer lever arm for spectral index measurements when combined with 1.4 GHz (NVSS/FIRST) or 150 MHz (TGSS) data, improving constraints on the emission mechanisms of individual sources. Steep-spectrum sources identified through SUMSS-NVSS spectral indices have been used to discover high-redshift radio galaxies and dying radio AGN.

The survey has been cross-matched extensively with X-ray catalogs (ROSAT, eROSITA), infrared surveys (2MASS, WISE), and optical redshift surveys to build multi-wavelength samples of AGN, star-forming galaxies, and galaxy clusters across the southern sky.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `ra_deg` | float64 | Right ascension J2000 (degrees) |
| `dec_deg` | float64 | Declination J2000 (degrees) |
| `peak_flux_mjy` | float64 | Peak flux density (mJy/beam) |
| `integrated_flux_mjy` | float64 | Integrated flux density (mJy) |
| `e_integrated_flux_mjy` | float64 | Error on integrated flux (mJy) |
| `major_axis_arcsec` | float64 | Fitted major axis FWHM (arcsec) |
| `minor_axis_arcsec` | float64 | Fitted minor axis FWHM (arcsec) |
| `position_angle_deg` | float64 | Position angle (degrees) |
| `deconv_major_arcsec` | float64 | Deconvolved major axis (arcsec) |
| `deconv_minor_arcsec` | float64 | Deconvolved minor axis (arcsec) |
| `deconv_pa_deg` | float64 | Deconvolved position angle (degrees) |
| `mosaic_name` | string | Mosaic image name |
| `is_resolved` | bool | True if deconvolved major axis > 0 |

## Quick stats

- **{n_total:,}** radio sources at 843 MHz
- **{n_resolved:,}** resolved sources ({n_resolved / n_total * 100:.1f}%)
- Median peak flux: {flux_median:.2f} mJy/beam
- Sky coverage: RA {ra_min:.1f}--{ra_max:.1f} deg, Dec {dec_min:.1f}--{dec_max:.1f} deg

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/sumss-radio-catalog", split="train")
df = ds.to_pandas()

# Flux distribution
import matplotlib.pyplot as plt
df["peak_flux_mjy"].clip(upper=500).hist(bins=200, log=True)
plt.xlabel("Peak flux at 843 MHz (mJy/beam)")
plt.ylabel("Count")
plt.title("SUMSS Source Flux Distribution")
plt.show()

# Sky coverage (southern sky)
plt.scatter(df["ra_deg"], df["dec_deg"], s=0.01, alpha=0.1)
plt.xlabel("RA (deg)")
plt.ylabel("Dec (deg)")
plt.title("SUMSS Sky Coverage (843 MHz, Dec < -30)")
plt.show()

# Resolved vs unresolved
print(f"Resolved: {{df['is_resolved'].sum():,}}")
print(f"Unresolved: {{(~df['is_resolved']).sum():,}}")
```

## Data source

Mauch, T., Murphy, T., Buttery, H.J., Curran, J., Hunstead, R.W., Piestrzynski, B.,
Robertson, J.G., and Sadler, E.M. (2003),
*SUMSS: A wide-field radio imaging survey of the southern sky. II. The source catalogue.*
Monthly Notices of the Royal Astronomical Society, 342, 1117.
Via [VizieR](https://vizier.cds.unistra.fr/) CDS Strasbourg (VIII/81B).

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/sumss-radio-catalog) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{sumss_radio_catalog,
  author = {{Simon, Julien}},
  title = {{Sydney University Molonglo Sky Survey (SUMSS)}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/sumss-radio-catalog}},
  note = {{Based on Mauch et al. (2003) via VizieR CDS Strasbourg}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update SUMSS radio catalog: {n_total:,} sources"
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
