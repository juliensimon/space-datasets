#!/usr/bin/env python3
"""Fetch Fermi LAT 4FGL-DR4 gamma-ray source catalog and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests
from astropy.io import fits
from astropy.table import Table

from dataset_images import banner_markdown, download_banner
from validate import check_dataset

FITS_URL = "https://fermi.gsfc.nasa.gov/ssc/data/access/lat/14yr_catalog/gll_psc_v35.fit"
HF_REPO = "juliensimon/fermi-4fgl-dr4"


def main():
    print("Downloading Fermi 4FGL-DR4 FITS catalog...")
    resp = requests.get(FITS_URL, timeout=300)
    resp.raise_for_status()

    with tempfile.NamedTemporaryFile(suffix=".fit") as tmp_fits:
        tmp_fits.write(resp.content)
        tmp_fits.flush()
        print(f"  Downloaded {len(resp.content) / 1024 / 1024:.1f} MB")

        table = Table.read(tmp_fits.name, hdu=1)
        # Filter out multidimensional columns (can't convert to pandas)
        names = [name for name in table.colnames if len(table[name].shape) <= 1]
        df = table[names].to_pandas()

    print(f"  {len(df):,} sources in catalog")

    # Select and rename columns
    col_map = {
        "Source_Name": "source_name",
        "RAJ2000": "ra_deg",
        "DEJ2000": "dec_deg",
        "GLON": "glon_deg",
        "GLAT": "glat_deg",
        "Signif_Avg": "significance",
        "Flux1000": "flux_1000_mev",
        "Energy_Flux100": "energy_flux_100_mev",
        "SpectrumType": "spectrum_type",
        "Variability_Index": "variability_index",
        "CLASS1": "source_class",
        "ASSOC1": "association",
        "Redshift": "redshift",
        "Flags": "flags",
        "Pivot_Energy": "pivot_energy_mev",
        "PL_Index": "power_law_index",
        "LP_Index": "log_parabola_index",
        "LP_beta": "log_parabola_beta",
    }

    available = {k: v for k, v in col_map.items() if k in df.columns}
    df = df[list(available.keys())].rename(columns=available)

    # Convert numerics
    numeric_cols = [
        "ra_deg", "dec_deg", "glon_deg", "glat_deg", "significance",
        "flux_1000_mev", "energy_flux_100_mev", "variability_index",
        "redshift", "pivot_energy_mev", "power_law_index",
        "log_parabola_index", "log_parabola_beta",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Convert flags to int
    if "flags" in df.columns:
        df["flags"] = pd.to_numeric(df["flags"], errors="coerce").astype("Int64")

    # Clean string columns
    for col in ["source_name", "spectrum_type", "source_class", "association"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
            df[col] = df[col].replace({"": None, "nan": None})

    # Derived column
    df["is_variable"] = df["variability_index"] > 18.48

    # Validation
    check_dataset(
        df, "fermi-4fgl",
        min_rows=5000,
        expected_columns=["source_name", "ra_deg", "dec_deg", "significance", "flux_1000_mev"],
        critical_columns=["source_name", "ra_deg", "dec_deg", "significance"],
    )

    # Stats for README
    n_total = len(df)
    n_variable = int(df["is_variable"].sum())
    n_redshift = int(df["redshift"].notna().sum()) if "redshift" in df.columns else 0
    top_classes = (
        df[df["source_class"].notna() & (df["source_class"] != "")]
        .groupby("source_class").size()
        .sort_values(ascending=False)
        .head(10)
    )
    top_classes_str = "\n".join(
        f"  - **{cls}**: {count:,}" for cls, count in top_classes.items()
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "fermi_4fgl_dr4.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        banner_file = download_banner("fermi-4fgl", tmp)
        banner_md = banner_markdown("fermi-4fgl", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Fermi LAT 4FGL-DR4 Gamma-Ray Source Catalog"
language:
  - en
description: "The 14-year all-sky gamma-ray source catalog from the Fermi Large Area Telescope — the deepest survey of the gamma-ray sky."
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - gamma-ray
  - fermi
  - lat
  - nasa
  - astronomy
  - high-energy
  - open-data
  - tabular-data
  - parquet
size_categories:
  - 1K<n<10K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/fermi_4fgl_dr4.parquet
    default: true
---

# Fermi LAT 4FGL-DR4 Gamma-Ray Source Catalog
{banner_md}
*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

![Update Fermi 4FGL](https://github.com/juliensimon/space-datasets/actions/workflows/update-fermi-4fgl.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.fermi-4fgl&label=updated&color=brightgreen)

The Fourth Fermi Large Area Telescope Source Catalog, Data Release 4 (4FGL-DR4),
based on 14 years of all-sky gamma-ray survey data. Currently **{n_total:,}** sources.

## Dataset description

This dataset contains every gamma-ray source detected by the Fermi LAT instrument
in its 14-year all-sky survey. The 4FGL-DR4 is the deepest catalog of the
gamma-ray sky ever produced, with sources spanning blazars, pulsars, supernova
remnants, globular clusters, starburst galaxies, and many unidentified sources.

Each record includes sky position, spectral properties, flux measurements,
variability information, and source associations with counterparts at other
wavelengths.

The 4FGL-DR4 represents the culmination of 14 years of continuous all-sky monitoring by the Fermi LAT, a pair-conversion telescope sensitive to gamma rays from roughly 20 MeV to more than 1 TeV. The LAT detects gamma rays by tracking the electron-positron pairs produced when incoming photons interact with tungsten converter foils, yielding both the direction and energy of the incident photon. With Pass 8 event reconstruction and 14 years of exposure, the catalog reaches a point-source sensitivity of approximately 2 x 10^-12 erg/cm^2/s in energy flux — deep enough to detect faint pulsars, distant blazars, and diffuse emission from star-forming regions.

The source population is remarkably diverse. Blazars (BL Lac objects and flat-spectrum radio quasars) dominate the extragalactic sky, their relativistic jets producing variable gamma-ray emission through inverse-Compton scattering of synchrotron photons or external radiation fields. Pulsars — rapidly rotating neutron stars — are the most numerous Galactic source class, emitting pulsed gamma rays from magnetospheric particle acceleration and curvature radiation in their extreme magnetic fields (10^8-10^13 Gauss). Supernova remnants and pulsar wind nebulae trace cosmic-ray acceleration sites, while the Galactic diffuse emission encodes information about cosmic-ray propagation and interstellar gas distribution. Over a thousand sources remain unassociated with known counterparts, representing active classification targets for machine learning and multi-wavelength follow-up.

The variability index and monthly light curves in 4FGL are particularly powerful for time-domain astrophysics. Blazar flares can brighten by factors of 10-100 on timescales of hours to weeks, driven by shock propagation or magnetic reconnection in their jets. These flares trigger multi-wavelength and multi-messenger campaigns, and the 4FGL variability data serve as the baseline for identifying and characterizing such events across the entire Fermi mission.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `source_name` | string | 4FGL catalog designation encoding position (e.g. "4FGL J0001.2+3738" = J2000 RA 00h01m, Dec +37°38'); the "4FGL" prefix identifies this as the Fourth Fermi LAT catalog |
| `ra_deg` | float64 | Right ascension of source centroid (ICRS J2000.0, degrees, 0–360); LAT angular resolution is ~0.1° at 10 GeV, ~1° at 1 GeV |
| `dec_deg` | float64 | Declination of source centroid (ICRS J2000.0, degrees, −90 to +90) |
| `glon_deg` | float64 | Galactic longitude (degrees, 0–360); sources at low |b| sit in the Galactic plane where diffuse emission and source confusion are highest |
| `glat_deg` | float64 | Galactic latitude (degrees, −90 to +90); |b| < 10° indicates Galactic plane sources; extragalactic sources (blazars, radio galaxies) populate high latitudes |
| `significance` | float64 | Detection significance averaged over the full energy range (sigma); threshold for catalog inclusion is ~4σ; bright sources exceed 100σ |
| `flux_1000_mev` | float64 | Integral photon flux above 1 GeV (photons/cm²/s); chosen to minimize dependence on the poorly constrained low-energy spectral shape; null for very soft sources that fall below threshold above 1 GeV |
| `energy_flux_100_mev` | float64 | Integral energy flux from 100 MeV to 100 GeV (erg/cm²/s); the most physically meaningful flux measure because it captures the bolometric gamma-ray output over the LAT band |
| `spectrum_type` | string | Best-fit spectral model: "PowerLaw" (single power law, typical for young pulsars and flat-spectrum radio quasars), "LogParabola" (curved spectrum, typical for BL Lacs and GeV-peaking blazars), "PLSuperExpCutoff" (power law with exponential cutoff, characteristic of millisecond and young pulsars) |
| `variability_index` | float64 | Sum of log-likelihood ratio test statistics from monthly light curve fits; values above 18.48 indicate flux variability at >99% confidence (chi-squared threshold for 11 degrees of freedom); blazars typically show values of 20–1000 |
| `source_class` | string | Astrophysical classification of the associated counterpart: "bll" (BL Lac object), "fsrq" (Flat Spectrum Radio Quasar), "psr" (pulsar), "snr" (supernova remnant), "pwn" (pulsar wind nebula), "glc" (globular cluster), "rdg" (radio galaxy), "sbg" (starburst galaxy), "spp" (potential association with SNR or PWN), "" / null (unassociated — no confirmed counterpart); uppercase indicates high-confidence association |
| `association` | string | Name of the counterpart source at other wavelengths (e.g. radio, X-ray, optical); null for unassociated sources (~26% of catalog); the basis for `source_class` |
| `redshift` | float64 | Spectroscopic redshift of the associated extragalactic counterpart; null for Galactic sources and unassociated sources; confirmed range spans 0.002 to ~3.1 for blazars |
| `flags` | Int64 | Bitmask of analysis quality and caution flags (see 4FGL paper Table 3); bit 0 = source is in a region of bright diffuse emission; bit 1 = localization quality is poor; non-zero flags indicate results should be used with caution |
| `pivot_energy_mev` | float64 | Reference energy at which the spectral normalization and index are decorrelated (MeV); chosen to minimize the covariance between flux normalization and spectral index; varies per source (typically 500–5000 MeV) |
| `power_law_index` | float64 | Photon spectral index Γ for sources fit with a power law (flux ∝ E^−Γ); typical values: Γ ~ 1.5–2.0 for hard blazars, 2.0–3.0 for soft sources and pulsars; null for sources using a different spectral model |
| `log_parabola_index` | float64 | Spectral index α at the pivot energy for sources fit with a log-parabola (flux ∝ (E/E₀)^−(α+β log(E/E₀))); null for sources using a different spectral model |
| `log_parabola_beta` | float64 | Spectral curvature parameter β for log-parabola sources; β > 0 means the spectrum curves downward (softer at higher energies); β ~ 0.1–0.8 for BL Lacs; null for sources using a different spectral model |
| `is_variable` | bool | True when `variability_index` exceeds 18.48 (99% confidence variability threshold); predominantly blazars; False includes both truly steady sources and sources with insufficient statistics to detect variability |

## Quick stats

- **{n_total:,}** gamma-ray sources
- **{n_variable:,}** variable sources (99% confidence)
- **{n_redshift:,}** sources with measured redshift
- Top source classes:
{top_classes_str}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/fermi-4fgl-dr4", split="train")
df = ds.to_pandas()

# Brightest sources by significance
brightest = df.sort_values("significance", ascending=False).head(20)

# Variable blazars
variable_blazars = df[
    (df["is_variable"] == True) &
    (df["source_class"].isin(["bll", "fsrq", "BLL", "FSRQ"]))
]

# Sources with known redshift
with_z = df[df["redshift"].notna()].sort_values("redshift", ascending=False)

# Sky distribution
import matplotlib.pyplot as plt
fig, ax = plt.subplots(subplot_kw={{"projection": "aitoff"}})
import numpy as np
l = np.radians(df["glon_deg"].values)
l[l > np.pi] -= 2 * np.pi
b = np.radians(df["glat_deg"].values)
ax.scatter(l, b, s=0.1, alpha=0.3)
```

## Data source

[Fermi LAT collaboration](https://fermi.gsfc.nasa.gov/ssc/data/access/lat/14yr_catalog/),
4FGL-DR4 (Abdollahi et al. 2022, updated). Based on 14 years of Fermi LAT
Pass 8 data.

## Update schedule

Annual (January 1) via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [grb-catalog](https://huggingface.co/datasets/juliensimon/gamma-ray-bursts) -- Gamma-ray burst catalog
- [snr-catalog](https://huggingface.co/datasets/juliensimon/supernova-remnants) -- Supernova remnant catalog
- [pulsar-catalog](https://huggingface.co/datasets/juliensimon/pulsar-catalog) -- Pulsar catalog

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/fermi-4fgl-dr4) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{fermi_4fgl_dr4,
  author = {{Simon, Julien}},
  title = {{Fermi LAT 4FGL-DR4 Gamma-Ray Source Catalog}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/fermi-4fgl-dr4}},
  note = {{Based on Fermi LAT 4FGL-DR4 catalog (Abdollahi et al. 2022, updated)}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update Fermi 4FGL-DR4: {n_total:,} sources"
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
