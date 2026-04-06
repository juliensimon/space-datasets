#!/usr/bin/env python3
"""Fetch TGSS ADR1 150 MHz radio catalog from VizieR and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from dataset_images import banner_markdown, download_banner
from validate import check_dataset
from vizier_tap import vizier_query

HF_REPO = "juliensimon/tgss-radio-catalog"

ADQL = """SELECT * FROM "J/A+A/598/A78/table3" """

RENAME = {
    "RA_ICRS": "ra_deg",
    "RAJ2000": "ra_deg",
    "_RA": "ra_deg",
    "DE_ICRS": "dec_deg",
    "DEJ2000": "dec_deg",
    "_DE": "dec_deg",
    "Speak": "peak_flux_mjy",
    "Stotal": "integrated_flux_mjy",
    "e_Speak": "e_peak_flux_mjy",
    "e_Stotal": "e_integrated_flux_mjy",
    "Rms": "rms_mjy",
    "Maj": "major_axis_arcsec",
    "Min": "minor_axis_arcsec",
    "PA": "position_angle_deg",
    "TGSS": "source_name",
}

NUMERIC_COLS = [
    "ra_deg", "dec_deg", "peak_flux_mjy", "integrated_flux_mjy",
    "e_peak_flux_mjy", "e_integrated_flux_mjy", "rms_mjy",
    "major_axis_arcsec", "minor_axis_arcsec", "position_angle_deg",
]


def main():
    print("Fetching TGSS ADR1 catalog from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} raw rows")

    # Rename columns
    df = df.rename(columns=RENAME)

    # Type conversions
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Clean string columns
    for col in ["source_name"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
            )

    # Stats
    n_total = len(df)
    flux_median = df["peak_flux_mjy"].median() if "peak_flux_mjy" in df.columns else 0
    ra_min, ra_max = df["ra_deg"].min(), df["ra_deg"].max()
    dec_min, dec_max = df["dec_deg"].min(), df["dec_deg"].max()
    rms_median = df["rms_mjy"].median() if "rms_mjy" in df.columns else 0

    # Validate
    check_dataset(
        df,
        "tgss",
        min_rows=500_000,
        expected_columns=["ra_deg", "dec_deg"],
        critical_columns=["ra_deg", "dec_deg"],
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "tgss_radio_sources.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        banner_file = download_banner("tgss", tmp)
        banner_md = banner_markdown("tgss", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "TGSS Alternative Data Release 1 (150 MHz)"
language:
  - en
description: "TGSS ADR1 catalog of {n_total:,} radio sources at 150 MHz from the Giant Metrewave Radio Telescope."
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - radio
  - tgss
  - gmrt
  - 150mhz
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
        path: data/tgss_radio_sources.parquet
    default: true
---

# TGSS Alternative Data Release 1 (150 MHz)
{banner_md}
*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

The TIFR GMRT Sky Survey Alternative Data Release 1 (TGSS ADR1), a 150 MHz radio continuum
survey covering 90% of the sky (declination > -53 deg) using the Giant Metrewave Radio Telescope.
Contains **{n_total:,}** discrete radio sources, filling the critical low-frequency gap in
all-sky radio catalogs.

## Dataset description

TGSS ADR1 is the largest 150 MHz radio survey, observed between 2010 and 2012 with the GMRT.
It provides 25 arcsecond resolution and a median rms noise of ~3.5 mJy/beam. The catalog is
essential for low-frequency radio spectral studies, identifying steep-spectrum sources such as
pulsars, high-redshift radio galaxies, and galaxy cluster relics.

The Giant Metrewave Radio Telescope (GMRT) near Pune, India, is one of the world's premier low-frequency radio interferometers, consisting of 30 fully steerable 45-meter dishes spread over a 25-kilometer baseline. TGSS ADR1 exploits the GMRT's unique sensitivity at 150 MHz to produce the deepest wide-field survey at this frequency, surpassing earlier efforts like the 7C survey and the Westerbork Northern Sky Survey (WENSS) at 325 MHz. The 150 MHz band is scientifically rich because synchrotron emission from relativistic electrons is strongest at low frequencies, making TGSS especially sensitive to aged electron populations that fade at higher frequencies.

TGSS has proven invaluable for discovering and characterizing diffuse radio emission in galaxy clusters, including radio halos, relics, and mini-halos that trace merger shocks and turbulence in the intracluster medium. The catalog is also a primary resource for identifying ultra-steep-spectrum (USS) radio sources, which are among the best tracers of high-redshift radio galaxies at z > 2. By computing spectral indices between TGSS (150 MHz) and NVSS or FIRST (1.4 GHz), researchers can efficiently select USS candidates for targeted follow-up with optical and infrared telescopes.

At 150 MHz, the ionosphere introduces direction-dependent phase errors that must be carefully calibrated. The ADR1 processing pipeline applied facet-based self-calibration to correct these effects, achieving a median positional accuracy of approximately 2 arcseconds and reliable flux densities above 7 sigma. TGSS ADR1 serves as the primary comparison catalog for next-generation low-frequency surveys from LOFAR and the future SKA-Low.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `source_name` | string | TGSS source designation |
| `ra_deg` | float64 | Right ascension J2000 (degrees) |
| `dec_deg` | float64 | Declination J2000 (degrees) |
| `peak_flux_mjy` | float64 | Peak flux density (mJy/beam) |
| `integrated_flux_mjy` | float64 | Integrated flux density (mJy) |
| `e_peak_flux_mjy` | float64 | Error on peak flux (mJy/beam) |
| `e_integrated_flux_mjy` | float64 | Error on integrated flux (mJy) |
| `rms_mjy` | float64 | Local rms noise (mJy/beam) |
| `major_axis_arcsec` | float64 | Fitted major axis FWHM (arcsec) |
| `minor_axis_arcsec` | float64 | Fitted minor axis FWHM (arcsec) |
| `position_angle_deg` | float64 | Position angle (degrees) |

## Quick stats

- **{n_total:,}** radio sources at 150 MHz
- Median peak flux: {flux_median:.2f} mJy/beam
- Median rms noise: {rms_median:.2f} mJy/beam
- Sky coverage: RA {ra_min:.1f}--{ra_max:.1f} deg, Dec {dec_min:.1f}--{dec_max:.1f} deg

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/tgss-radio-catalog", split="train")
df = ds.to_pandas()

# Flux distribution
import matplotlib.pyplot as plt
df["peak_flux_mjy"].clip(upper=500).hist(bins=200, log=True)
plt.xlabel("Peak flux at 150 MHz (mJy/beam)")
plt.ylabel("Count")
plt.title("TGSS Source Flux Distribution")
plt.show()

# Sky coverage
plt.scatter(df["ra_deg"], df["dec_deg"], s=0.01, alpha=0.1)
plt.xlabel("RA (deg)")
plt.ylabel("Dec (deg)")
plt.title("TGSS ADR1 Sky Coverage (150 MHz)")
plt.show()

# Bright sources (> 1 Jy)
bright = df[df["integrated_flux_mjy"] > 1000]
print(f"{{len(bright):,}} sources brighter than 1 Jy at 150 MHz")
```

## Data source

Intema, H.T., Jagannathan, P., Mooley, K.P., and Frail, D.A. (2017),
*The GMRT 150 MHz all-sky radio survey -- First alternative data release TGSS ADR1.*
Astronomy & Astrophysics, 598, A78. Via [VizieR](https://vizier.cds.unistra.fr/) CDS Strasbourg.

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/tgss-radio-catalog) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{tgss_radio_catalog,
  author = {{Simon, Julien}},
  title = {{TGSS Alternative Data Release 1 (150 MHz)}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/tgss-radio-catalog}},
  note = {{Based on Intema et al. (2017) via VizieR CDS Strasbourg}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update TGSS radio catalog: {n_total:,} sources"
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
