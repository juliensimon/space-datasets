#!/usr/bin/env python3
"""Fetch INTEGRAL IBIS 17-Year Hard X-Ray Survey catalog from VizieR and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from dataset_images import banner_markdown, download_banner
from validate import check_dataset
from vizier_tap import vizier_query

HF_REPO = "juliensimon/integral-ibis-hard-xray"

ADQL = """SELECT * FROM "J/MNRAS/510/4796/table1" """

RENAME = {
    "SrcID": "source_id",
    "Name": "source_name",
    "RAJ2000": "ra_deg",
    "DEJ2000": "dec_deg",
    "Flux": "flux_17_60kev",
    "e_Flux": "flux_err_17_60kev",
    "S/N": "snr_17_60kev",
    "Type": "source_type",
    "z": "redshift",
    "Trans": "transient_flag",
    "Ext": "extended_flag",
    "Conf": "confused_flag",
    "Noise": "noisy_flag",
    "Refs": "references",
    "Cntp": "counterpart",
    "Notes": "notes",
    "FluxE2": "flux_17_35kev",
    "FluxE3": "flux_35_80kev",
    "FluxE4": "flux_80_150kev",
    "FluxE5": "flux_150_290kev",
    "FluxE6": "flux_17_80kev",
    "FluxE7": "flux_35_150kev",
    "FluxE8": "flux_80_290kev",
    "FluxE9": "flux_17_290kev",
    "e_FluxE2": "flux_err_17_35kev",
    "e_FluxE3": "flux_err_35_80kev",
    "e_FluxE4": "flux_err_80_150kev",
    "e_FluxE5": "flux_err_150_290kev",
    "e_FluxE6": "flux_err_17_80kev",
    "e_FluxE7": "flux_err_35_150kev",
    "e_FluxE8": "flux_err_80_290kev",
    "e_FluxE9": "flux_err_17_290kev",
    "S/NE2": "snr_17_35kev",
    "S/NE3": "snr_35_80kev",
    "S/NE4": "snr_80_150kev",
    "S/NE5": "snr_150_290kev",
    "S/NE6": "snr_17_80kev",
    "S/NE7": "snr_35_150kev",
    "S/NE8": "snr_80_290kev",
    "S/NE9": "snr_17_290kev",
    "Plate": "plate",
    "SimbadName": "simbad_name",
}

NUMERIC_COLS = [
    "ra_deg", "dec_deg", "source_id", "redshift",
    "flux_17_60kev", "flux_err_17_60kev", "snr_17_60kev",
    "flux_17_35kev", "flux_35_80kev", "flux_80_150kev", "flux_150_290kev",
    "flux_17_80kev", "flux_35_150kev", "flux_80_290kev", "flux_17_290kev",
    "flux_err_17_35kev", "flux_err_35_80kev", "flux_err_80_150kev", "flux_err_150_290kev",
    "flux_err_17_80kev", "flux_err_35_150kev", "flux_err_80_290kev", "flux_err_17_290kev",
    "snr_17_35kev", "snr_35_80kev", "snr_80_150kev", "snr_150_290kev",
    "snr_17_80kev", "snr_35_150kev", "snr_80_290kev", "snr_17_290kev",
]


def main():
    print("Fetching INTEGRAL IBIS hard X-ray survey catalog from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} raw rows")

    # Drop VizieR internal row number
    if "recno" in df.columns:
        df = df.drop(columns=["recno"])

    # Rename columns
    df = df.rename(columns=RENAME)

    # Type conversions
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Coerce integer ID
    if "source_id" in df.columns:
        df["source_id"] = df["source_id"].astype("Int32")

    # Strip whitespace from string columns
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].str.strip()

    # Derived columns
    df["has_redshift"] = df["redshift"].notna()

    # Sort by S/N descending (most significant detections first)
    df = df.sort_values("snr_17_60kev", ascending=False).reset_index(drop=True)

    # Stats
    n_total = len(df)
    n_with_z = int(df["has_redshift"].sum())
    flux_median = df["flux_17_60kev"].median()
    snr_max = df["snr_17_60kev"].max()
    n_types = df["source_type"].nunique()

    # Validate
    check_dataset(
        df,
        "integral-ibis",
        min_rows=800,
        expected_columns=[
            "source_id", "source_name", "ra_deg", "dec_deg",
            "flux_17_60kev", "snr_17_60kev", "source_type",
        ],
        critical_columns=["source_name", "ra_deg", "dec_deg", "flux_17_60kev", "snr_17_60kev"],
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "integral_ibis_hard_xray.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        banner_file = download_banner("integral-ibis", tmp)
        banner_md = banner_markdown("integral-ibis", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "INTEGRAL IBIS 17-Year Hard X-Ray Survey"
language:
  - en
description: "Catalog of {n_total:,} hard X-ray sources (17-290 keV) from 17 years of INTEGRAL IBIS observations (Krivonos+ 2022)."
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - x-ray
  - integral
  - esa
  - hard-x-ray
  - astronomy
  - physics
  - open-data
  - tabular-data
  - parquet
size_categories:
  - n<1K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/integral_ibis_hard_xray.parquet
    default: true
---

# INTEGRAL IBIS 17-Year Hard X-Ray Survey
{banner_md}
*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

The INTEGRAL IBIS hard X-ray survey catalog from 17 years of observations with the IBIS coded-mask
telescope aboard ESA's INTEGRAL satellite. Contains **{n_total:,}** hard X-ray sources detected in
the 17--290 keV energy range across **{n_types}** source types, with multi-band flux measurements
in 8 energy sub-bands.

## Dataset description

This catalog (Krivonos et al. 2022, MNRAS 510, 4796) presents the deepest all-sky survey in the
hard X-ray band to date. Sources were detected using the IBIS/ISGRI detector over 17 years of
INTEGRAL observations (2003--2020). The catalog provides flux measurements in 8 energy sub-bands
spanning 17--290 keV, plus source classifications, redshifts, and transient/extended flags.

The hard X-ray band (above ~15 keV) is uniquely valuable because it penetrates the dense columns of gas and dust that obscure many astrophysical sources at softer energies. INTEGRAL's coded-mask imaging technique allows the IBIS/ISGRI detector to achieve arcminute-level localization across the entire sky, revealing populations of heavily absorbed active galactic nuclei (AGN), high-mass X-ray binaries, cataclysmic variables, and isolated pulsars that are invisible to soft X-ray telescopes. The 17-year integration time makes this the most sensitive hard X-ray all-sky survey from any coded-mask instrument.

The multi-band flux decomposition across 8 sub-bands from 17 to 290 keV enables broadband spectral characterization without requiring pointed follow-up observations. For extragalactic sources, the combination of hard X-ray flux and redshift constrains intrinsic luminosities and absorption column densities, key parameters for understanding the obscured AGN population that dominates the cosmic X-ray background. Transient flags identify sources such as X-ray novae and supergiant fast X-ray transients whose variable emission traces accretion instabilities in binary systems.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `source_id` | Int32 | Sequential catalog number from Krivonos et al. 2022 (MNRAS 510, 4796) |
| `source_name` | string | Primary source name — IBIS catalog designation (e.g., "IGR J17480-2446") or standard name (e.g., "Cyg X-1") |
| `ra_deg` | float64 | Right ascension, ICRS J2000.0 (degrees, 0–360); IBIS angular resolution ~12 arcmin |
| `dec_deg` | float64 | Declination, ICRS J2000.0 (degrees, −90 to +90) |
| `flux_17_60kev` | float64 | Hard X-ray flux in the primary 17–60 keV band (mCrab); 1 Crab ≈ 2.4×10⁻⁸ erg/cm²/s; catalog detection threshold ~5 mCrab |
| `flux_err_17_60kev` | float64 | 1-sigma statistical uncertainty on flux_17_60kev (mCrab) |
| `snr_17_60kev` | float64 | Detection signal-to-noise ratio in the 17–60 keV band; catalog inclusion threshold >4.7σ |
| `source_type` | string | Astrophysical classification (e.g., "AGN", "HMXB", "LMXB", "CV", "PSR", "SNR", "Galaxy cluster", "Unidentified") |
| `redshift` | float64 | Spectroscopic redshift for extragalactic sources; null for Galactic sources or sources lacking optical identification |
| `transient_flag` | string | "T" if the source is a known transient (flux variable by >factor 2); null or blank otherwise |
| `extended_flag` | string | "E" if the source is spatially extended in the IBIS image (e.g., a galaxy cluster); null otherwise |
| `confused_flag` | string | "C" if the source is in a confused region with nearby bright sources that may affect flux accuracy; null otherwise |
| `noisy_flag` | string | "N" if the source lies in a noisy sky region due to proximity to very bright sources or the Galactic center; null otherwise |
| `references` | string | ADS bibcode(s) for the primary identification or classification reference |
| `counterpart` | string | Name of the multiwavelength counterpart used for source classification |
| `notes` | string | Additional remarks on the source (e.g., known aliases, special observational circumstances) |
| `flux_17_35kev` | float64 | Flux in the 17–35 keV sub-band (mCrab); null if source not detected in this band |
| `flux_35_80kev` | float64 | Flux in the 35–80 keV sub-band (mCrab); null if source not detected in this band |
| `flux_80_150kev` | float64 | Flux in the 80–150 keV sub-band (mCrab); null if source not detected in this band |
| `flux_150_290kev` | float64 | Flux in the 150–290 keV sub-band (mCrab); null if source not detected in this band |
| `flux_17_80kev` | float64 | Flux in the combined 17–80 keV sub-band (mCrab) |
| `flux_35_150kev` | float64 | Flux in the combined 35–150 keV sub-band (mCrab) |
| `flux_80_290kev` | float64 | Flux in the combined 80–290 keV sub-band (mCrab) |
| `flux_17_290kev` | float64 | Total broadband flux over 17–290 keV (mCrab) |
| `flux_err_*` | float64 | 1-sigma statistical uncertainty on the corresponding flux column (mCrab) |
| `snr_*` | float64 | Detection signal-to-noise ratio for the corresponding energy sub-band |
| `plate` | string | INTEGRAL sky plate identifier indicating the mosaic tile used for this detection |
| `simbad_name` | string | Resolved SIMBAD source name for cross-referencing with the CDS database |
| `has_redshift` | bool | True if redshift is non-null; derived convenience column |

## Quick stats

- **{n_total:,}** hard X-ray sources
- **{n_with_z:,}** sources with measured redshift ({n_with_z / n_total * 100:.1f}%)
- Median flux (17--60 keV): {flux_median:.2f} mCrab
- Peak S/N: {snr_max:.1f}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/integral-ibis-hard-xray", split="train")
df = ds.to_pandas()

# Flux distribution
import matplotlib.pyplot as plt
df["flux_17_60kev"].clip(upper=100).hist(bins=100, log=True)
plt.xlabel("Flux 17-60 keV (mCrab)")
plt.ylabel("Count")
plt.title("INTEGRAL IBIS Hard X-Ray Flux Distribution")
plt.show()

# Source type breakdown
df["source_type"].value_counts().head(10).plot.barh()
plt.xlabel("Count")
plt.title("Top 10 Source Types")
plt.tight_layout()
plt.show()

# Sky map
plt.scatter(df["ra_deg"], df["dec_deg"], s=2, c=df["snr_17_60kev"].clip(upper=50), cmap="hot")
plt.colorbar(label="S/N")
plt.xlabel("RA (deg)")
plt.ylabel("Dec (deg)")
plt.title("INTEGRAL IBIS All-Sky Hard X-Ray Sources")
plt.show()
```

## Data source

Krivonos, R. et al. (2022), *INTEGRAL/IBIS 17-yr hard X-ray all-sky survey.*
Monthly Notices of the Royal Astronomical Society, 510, 4796--4828.
Via VizieR CDS (J/MNRAS/510/4796/table1).

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/integral-ibis-hard-xray) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{integral_ibis_hard_xray,
  author = {{Simon, Julien}},
  title = {{INTEGRAL IBIS 17-Year Hard X-Ray Survey}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/integral-ibis-hard-xray}},
  note = {{Based on Krivonos et al. (2022) via VizieR CDS}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update INTEGRAL IBIS hard X-ray survey: {n_total:,} sources"
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
