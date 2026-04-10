#!/usr/bin/env python3
"""Fetch Fermi LAT Fourth AGN Catalog (4LAC) from HEASARC and upload to HF."""

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
HF_REPO = "juliensimon/fermi-4lac-agn-catalog"

ADQL = """\
SELECT * FROM fermilac\
"""


def fetch_catalog() -> pd.DataFrame:
    """Try CSV first, fall back to JSON, then pipe-delimited text."""
    # Attempt 1: CSV
    print("Fetching Fermi 4LAC catalog (CSV)...")
    resp = requests.get(TAP_URL, params={
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": ADQL,
    }, timeout=120)
    resp.raise_for_status()

    if not resp.text.strip().startswith("<?xml"):
        try:
            df = pd.read_csv(io.StringIO(resp.text))
            if len(df) > 100 and "ra" in df.columns:
                print(f"  CSV parse OK: {len(df):,} rows")
                return df
        except Exception as e:
            print(f"  CSV parse failed: {e}")
    else:
        print("  CSV not supported (got XML/VOTable response)")

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

    lines = [l for l in resp.text.strip().splitlines() if l.strip() and not l.startswith("-")]
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

    # Rename columns to snake_case (HEASARC columns are already lowercase)
    # Clean up any remaining uppercase or awkward names
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    # Ensure numeric columns
    numeric_cols = [
        "ra", "dec", "lii", "bii", "glon", "glat",
        "significance", "pivot_energy", "flux",
        "energy_flux", "spectral_index", "redshift",
        "variability_index", "frac_variability",
        "flux_band1", "flux_band2", "flux_band3", "flux_band4", "flux_band5",
        "unc_flux", "unc_energy_flux", "unc_spectral_index",
        "pl_flux", "lp_flux", "lp_index", "lp_beta",
        "npred", "sed_class_index",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Clean empty strings to NaN for string columns
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip().replace(
            {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
        )

    # Sort by significance or flux descending (prefer significance)
    if "significance" in df.columns:
        df = df.sort_values("significance", ascending=False).reset_index(drop=True)
        print(f"  Sorted by significance descending")
    elif "flux" in df.columns:
        df = df.sort_values("flux", ascending=False).reset_index(drop=True)
        print(f"  Sorted by flux descending")

    n_total = len(df)
    print(f"  {n_total:,} AGN total")

    # Count by class if available
    class_col = None
    for candidate in ["class", "source_class", "optical_class", "agn_class", "clean_class"]:
        if candidate in df.columns:
            class_col = candidate
            break

    if class_col:
        class_counts = df[class_col].value_counts()
        print(f"  AGN classes ({class_col}):")
        for cls, count in class_counts.head(10).items():
            print(f"    {cls}: {count:,}")

    n_with_redshift = int(df["redshift"].notna().sum()) if "redshift" in df.columns else 0
    print(f"  {n_with_redshift:,} sources with redshift")

    check_dataset(df, "fermi-4lac", min_rows=2_500,
        expected_columns=["ra", "dec"],
        critical_columns=["ra", "dec"])

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "fermi-4lac.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        # Stats for README
        median_redshift = df["redshift"].median() if "redshift" in df.columns else 0

        # Build class summary string
        class_summary = ""
        if class_col:
            top_classes = df[class_col].value_counts().head(5)
            parts = [f"{count:,} {cls}" for cls, count in top_classes.items()]
            class_summary = ", ".join(parts)

        # Build schema table from actual columns with descriptions
        col_descriptions = {
            "name": "IAU source name (4FGL designation)",
            "ra": "Right ascension (J2000, degrees)",
            "dec": "Declination (J2000, degrees)",
            "lii": "Galactic longitude (degrees)",
            "bii": "Galactic latitude (degrees)",
            "glon": "Galactic longitude (degrees)",
            "glat": "Galactic latitude (degrees)",
            "significance": "Detection significance in Gaussian sigma over the 4-year LAT baseline",
            "pivot_energy": "Decorrelation (pivot) energy in MeV at which the flux uncertainty is minimized; minimizes spectral index / normalization degeneracy",
            "flux": "Photon flux in ph/cm²/s integrated over 1–100 GeV",
            "unc_flux": "1-sigma statistical uncertainty on the photon flux (ph/cm²/s)",
            "energy_flux": "Energy flux in erg/cm²/s integrated over 100 MeV–100 GeV",
            "unc_energy_flux": "1-sigma statistical uncertainty on the energy flux (erg/cm²/s)",
            "spectral_index": "Power-law photon spectral index Γ; harder sources (blazars) typically Γ ~ 1.5–2.5",
            "unc_spectral_index": "1-sigma statistical uncertainty on the power-law spectral index",
            "pl_flux": "Photon flux from power-law spectral fit (ph/cm²/s, 1–100 GeV)",
            "lp_flux": "Photon flux from log-parabola spectral fit (ph/cm²/s, 1–100 GeV); preferred for curved spectra",
            "lp_index": "Log-parabola spectral index α at the pivot energy",
            "lp_beta": "Log-parabola curvature parameter β; β > 0 indicates spectral softening at higher energies",
            "npred": "Number of source photons predicted by the best-fit spectral model in the ROI",
            "redshift": "Spectroscopic redshift; null for ~40% of BL Lac objects that lack optical emission lines",
            "variability_index": "Flux variability chi-squared statistic over the 4-year baseline; >18.48 indicates significant variability at 99% confidence",
            "frac_variability": "Fractional variability amplitude F_var = sqrt((S² − σ²) / mean²); null if source is not significantly variable",
            "flux_band1": "Photon flux in energy band 1 (50–100 MeV, ph/cm²/s)",
            "flux_band2": "Photon flux in energy band 2 (100–300 MeV, ph/cm²/s)",
            "flux_band3": "Photon flux in energy band 3 (300 MeV–1 GeV, ph/cm²/s)",
            "flux_band4": "Photon flux in energy band 4 (1–3 GeV, ph/cm²/s)",
            "flux_band5": "Photon flux in energy band 5 (3–300 GeV, ph/cm²/s)",
            "class": "AGN subclass: bll (BL Lac), fsrq (flat-spectrum radio quasar), bcu (blazar of uncertain type), rdg (radio galaxy), nlsy1 (narrow-line Seyfert 1), ssrq (steep-spectrum radio quasar), sey (Seyfert)",
            "source_class": "AGN subclass (same encoding as class): bll, fsrq, bcu, rdg, nlsy1, ssrq, sey",
            "optical_class": "Optical spectroscopic classification of the AGN counterpart",
            "agn_class": "AGN classification type from the 4LAC analysis",
            "clean_class": "Y if source passes all quality cuts for the 4LAC clean sample; stricter subset for population studies",
            "sed_class": "Synchrotron peak classification: LSP (low-synchrotron-peaked, ν_peak < 10¹⁴ Hz), ISP (intermediate), HSP (high, ν_peak > 10¹⁵ Hz)",
            "sed_class_index": "Numeric encoding of sed_class: 1 = LSP, 2 = ISP, 3 = HSP",
            "assoc_name": "Counterpart name at other wavelengths (radio, optical, or X-ray); null if no confident association",
            "counterpart": "Multiwavelength counterpart designation from the 4LAC cross-matching procedure",
            "flags": "Bit-field of analysis flags (e.g., confused source, uncertain association, poor localization)",
            "status": "Source analysis status in the 4LAC pipeline (e.g., clean, flagged)",
        }
        schema_rows = []
        for col in df.columns:
            dtype = str(df[col].dtype)
            if "float" in dtype:
                col_type = "float"
            elif "int" in dtype:
                col_type = "int"
            elif "datetime" in dtype:
                col_type = "datetime"
            elif "bool" in dtype:
                col_type = "bool"
            else:
                col_type = "string"
            desc = col_descriptions.get(col, "")
            schema_rows.append(f"| `{col}` | {col_type} | {desc} |")
        schema_table = "\n".join(schema_rows)

        banner_file = download_banner("fermi-4lac", tmp)
        banner_md = banner_markdown("fermi-4lac", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Fermi LAT Fourth AGN Catalog (4LAC)"
language:
  - en
description: "Active galactic nuclei detected by the Fermi Large Area Telescope, the largest gamma-ray AGN catalog with source classifications, spectral parameters, and redshifts."
task_categories:
  - tabular-classification
tags:
  - space
  - gamma-ray
  - fermi
  - nasa
  - agn
  - blazars
  - astronomy
  - open-data
  - tabular-data
  - parquet
size_categories:
  - 1K<n<10K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/fermi-4lac.parquet
    default: true
---

# Fermi LAT Fourth AGN Catalog (4LAC)
{banner_md}
*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

The largest catalog of gamma-ray active galactic nuclei (AGN), detected by the
[Fermi Large Area Telescope (LAT)](https://fermi.gsfc.nasa.gov/). Currently **{n_total:,}**
sources with classifications, spectral parameters, and multiwavelength associations.

## Dataset description

Active galactic nuclei (AGN) are supermassive black holes at the centers of galaxies that
produce powerful jets of relativistic particles. When one of these jets points toward Earth,
the AGN appears as a blazar -- the most common type of gamma-ray source in the sky.

The Fourth LAT AGN Catalog (4LAC) is based on Fermi LAT observations and represents the
most comprehensive census of gamma-ray AGN. It includes BL Lac objects, flat-spectrum radio
quasars (FSRQs), and other AGN types, with spectral parameters, variability indices, and
multiwavelength counterpart associations.

The two dominant blazar subclasses — BL Lac objects and FSRQs — represent fundamentally different accretion regimes onto supermassive black holes. FSRQs are high-luminosity sources with strong broad emission lines, radiatively efficient accretion disks, and gamma-ray spectra that tend to be soft (steep spectral indices) due to dominant external Compton scattering off photons from the broad-line region or dusty torus. BL Lac objects have weak or absent emission lines, radiatively inefficient accretion flows, and harder gamma-ray spectra produced primarily by synchrotron self-Compton emission within the jet. This spectral dichotomy underpins the "blazar sequence" — the observed anti-correlation between bolometric luminosity and the peak frequency of the synchrotron spectral component — though its physical origin remains debated.

The 4LAC is a cornerstone for AGN unification studies and jet physics. The redshift distribution encodes the cosmological evolution of the blazar population: FSRQs show strong positive evolution (more numerous and luminous at higher redshifts, peaking around z ~ 1-2), tracing the epoch of peak supermassive black hole growth, while BL Lac objects show weaker or negative evolution. The spectral parameters — power-law indices, log-parabola curvatures, and pivot energies — constrain particle acceleration mechanisms and the jet magnetic field structure. Variability indices identify flaring sources that are prime targets for very-long-baseline interferometry (VLBI) imaging of superluminal jet components and for multi-messenger searches in neutrino data.

The gamma-ray properties in 4LAC, combined with radio, optical, and X-ray data, enable construction of broadband spectral energy distributions (SEDs) spanning over 15 decades in frequency. These SEDs are the primary observational tool for constraining physical jet models — distinguishing between leptonic scenarios (where electrons and positrons radiate via synchrotron and inverse-Compton processes) and hadronic models (where protons accelerated in the jet produce gamma rays through pion cascades, with accompanying neutrino emission).

## Schema

| Column | Type | Description |
|--------|------|-------------|
{schema_table}

## Quick stats

- **{n_total:,}** active galactic nuclei
- **{n_with_redshift:,}** sources with measured redshift
- Median redshift: **{median_redshift:.3f}**
{f"- Top classes: {class_summary}" if class_summary else ""}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/fermi-4lac-agn-catalog", split="train")
df = ds.to_pandas()

# Brightest AGN by flux
top = df.nlargest(10, "flux")[["name", "flux", "spectral_index", "redshift"]] if "name" in df.columns else df.nlargest(10, "flux")

# Redshift distribution
import matplotlib.pyplot as plt
df["redshift"].dropna().hist(bins=50)
plt.xlabel("Redshift")
plt.title("4LAC AGN Redshift Distribution")
```

## Data source

All data comes from the [Fermi LAT 4LAC Catalog](https://heasarc.gsfc.nasa.gov/W3Browse/fermi/fermilac.html)
hosted by NASA's High Energy Astrophysics Science Archive Research Center (HEASARC),
accessed via the TAP protocol.

**Reference:** Ajello, M. et al. (2020), "The Fourth Catalog of Active Galactic Nuclei
Detected by the Fermi Large Area Telescope", ApJ, 892, 105.

## Related datasets

- [gamma-ray-bursts](https://huggingface.co/datasets/juliensimon/gamma-ray-bursts) -- Fermi GBM Gamma-Ray Burst Catalog
- [pulsar-catalog](https://huggingface.co/datasets/juliensimon/pulsar-catalog) -- ATNF Pulsar Catalogue
- [near-earth-objects](https://huggingface.co/datasets/juliensimon/neo-close-approaches) -- NEO close approaches

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/fermi-4lac-agn-catalog) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{fermi_4lac,
  author = {{Simon, Julien}},
  title = {{Fermi LAT Fourth AGN Catalog (4LAC)}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/fermi-4lac-agn-catalog}},
  note = {{Based on Fermi LAT 4LAC (Ajello et al. 2020) via NASA HEASARC}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update Fermi 4LAC AGN catalog: {n_total:,} sources"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={n_total}\n")
    print("Done.")


if __name__ == "__main__":
    main()
