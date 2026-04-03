#!/usr/bin/env python3
"""Fetch Gaia DR3 White Dwarf candidates (Gentile Fusillo+ 2021) from VizieR and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from dataset_images import banner_markdown, download_banner
from validate import check_dataset
from vizier_tap import vizier_query

HF_REPO = "juliensimon/gaia-dr3-white-dwarfs"

# Gentile Fusillo+ 2021 (MNRAS 508, 3877): THE definitive Gaia DR3 WD catalog
# 359,073 high-confidence white dwarf candidates
ADQL = 'SELECT * FROM "J/MNRAS/508/3877/maincat"'


def main():
    print("Fetching Gaia DR3 White Dwarfs (Gentile Fusillo+ 2021) from VizieR...")
    df = vizier_query(ADQL, timeout=600)
    print(f"  {len(df):,} raw rows")

    # Drop VizieR internal recno
    if "recno" in df.columns:
        df = df.drop(columns=["recno"])

    # Discover actual column names from VizieR
    print(f"  Columns ({len(df.columns)}): {list(df.columns)[:20]}...")

    # Rename key columns to snake_case (VizieR names vary; build a broad rename dict)
    rename = {
        "WDJname": "wdj_name",
        "WDJ": "wdj_name",
        "Source": "source_id",
        "GaiaEDR3": "source_id",
        "GaiaDR2": "source_id_dr2",
        "EDR3Name": "edr3_name",
        "RA_ICRS": "ra_deg",
        "DE_ICRS": "dec_deg",
        "Plx": "parallax_mas",
        "e_Plx": "parallax_error_mas",
        "pmRA": "pmra_mas_yr",
        "e_pmRA": "pmra_error_mas_yr",
        "pmDE": "pmdec_mas_yr",
        "e_pmDE": "pmdec_error_mas_yr",
        "Gmag": "g_mag",
        "e_Gmag": "g_mag_error",
        "BPmag": "bp_mag",
        "e_BPmag": "bp_mag_error",
        "RPmag": "rp_mag",
        "e_RPmag": "rp_mag_error",
        "BP-RP": "bp_rp",
        "Pwd": "prob_wd",
        "Teff": "teff_k",
        "e_Teff": "teff_error_k",
        "logg": "log_g",
        "e_logg": "log_g_error",
        "Mass": "mass_msun",
        "e_Mass": "mass_error_msun",
        "chi2": "chi2",
        "Grv": "radial_velocity_km_s",
        "e_Grv": "radial_velocity_error_km_s",
        "RUWE": "ruwe",
        "GAbsmag": "g_abs_mag",
        "Dist": "distance_pc",
        "e_Dist": "distance_error_pc",
        "AG": "extinction_g",
        "E_BP-RP_": "ebp_rp",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

    # Convert numeric columns
    numeric_cols = [
        "ra_deg", "dec_deg", "parallax_mas", "parallax_error_mas",
        "pmra_mas_yr", "pmra_error_mas_yr", "pmdec_mas_yr", "pmdec_error_mas_yr",
        "g_mag", "g_mag_error", "bp_mag", "bp_mag_error", "rp_mag", "rp_mag_error",
        "bp_rp", "prob_wd", "teff_k", "teff_error_k", "log_g", "log_g_error",
        "mass_msun", "mass_error_msun", "chi2", "radial_velocity_km_s",
        "radial_velocity_error_km_s", "ruwe", "g_abs_mag",
        "distance_pc", "distance_error_pc", "extinction_g", "ebp_rp",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Convert source_id to string (Gaia source IDs are 64-bit ints)
    if "source_id" in df.columns:
        df["source_id"] = df["source_id"].astype(str).str.strip()

    # Clean string columns
    for col in ["wdj_name"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
            )

    # Sort by source_id
    if "source_id" in df.columns:
        df = df.sort_values("source_id").reset_index(drop=True)

    # Stats
    n_total = len(df)
    g_median = df["g_mag"].median() if "g_mag" in df.columns else float("nan")
    teff_median = df["teff_k"].median() if "teff_k" in df.columns else float("nan")
    mass_median = df["mass_msun"].median() if "mass_msun" in df.columns else float("nan")
    pwd_median = df["prob_wd"].median() if "prob_wd" in df.columns else float("nan")
    n_high_prob = int((df["prob_wd"] > 0.75).sum()) if "prob_wd" in df.columns else 0

    # Validate
    check_dataset(
        df,
        "gaia-wd",
        min_rows=250_000,
        expected_columns=["source_id", "ra_deg", "dec_deg", "prob_wd"],
        critical_columns=["source_id", "ra_deg", "dec_deg"],
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "gaia_dr3_white_dwarfs.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        banner_file = download_banner("gaia-wd", tmp)
        banner_md = banner_markdown("gaia-wd", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Gaia DR3 White Dwarfs"
language:
  - en
description: "Gaia DR3 white dwarf candidates from the Gentile Fusillo+ 2021 catalog — {n_total:,} high-confidence WD candidates with atmospheric parameters, masses, and photometry."
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - gaia
  - white-dwarfs
  - stars
  - esa
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
        path: data/gaia_dr3_white_dwarfs.parquet
    default: true
---

# Gaia DR3 White Dwarfs
{banner_md}
*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

The definitive Gaia DR3 white dwarf catalog from Gentile Fusillo et al. (2021), containing
**{n_total:,}** high-confidence white dwarf candidates identified from ESA Gaia astrometry
and photometry. Each source includes a WD probability score, atmospheric parameters
(effective temperature, surface gravity), mass estimates, and multi-band photometry.

## Dataset description

White dwarfs are the dense stellar remnants left after low- and intermediate-mass stars
exhaust their nuclear fuel. They represent the final evolutionary stage of over 95% of all
stars. This catalog was constructed by selecting Gaia DR3 sources in the white dwarf region
of the Hertzsprung-Russell diagram and assigning each a probability of being a genuine WD
(`prob_wd`) using a random forest classifier trained on spectroscopically confirmed samples.

Atmospheric parameters (Teff, log g) and masses were derived by fitting Gaia photometry
and parallaxes to hydrogen-atmosphere (DA) and helium-atmosphere (DB) white dwarf models.

White dwarfs are remarkably compact objects, packing roughly the mass of the Sun into a
volume comparable to the Earth. Their interiors are supported against gravitational collapse
not by nuclear fusion but by electron degeneracy pressure -- a quantum mechanical effect that
sets a theoretical upper mass limit near 1.4 solar masses (the Chandrasekhar limit). The
mass distribution of white dwarfs peaks sharply near 0.6 solar masses, reflecting the
initial-to-final mass relation that maps a main-sequence progenitor of several solar masses
down to a compact remnant through extensive mass loss on the asymptotic giant branch. The
width and shape of this mass peak, along with the high-mass and low-mass tails, encode
information about binary evolution, merger products, and the star formation history of the
Galactic disk.

Because white dwarfs cool predictably over billions of years -- radiating away their
residual thermal energy with well-understood physics -- they serve as cosmic chronometers.
The white dwarf luminosity function (the number of white dwarfs per luminosity bin) encodes
the age of the Galactic disk: the faint end cutoff corresponds to the oldest, coolest white
dwarfs and provides an independent age estimate of 8--10 Gyr for the thin disk. With Gaia
parallaxes enabling precise absolute magnitudes, this catalog allows construction of the
luminosity function with unprecedented completeness out to several hundred parsecs.

The Hertzsprung-Russell diagram of white dwarfs reveals rich substructure beyond the main
cooling sequence. A bifurcation separates hydrogen-atmosphere (DA) white dwarfs from
helium-atmosphere (DB/DC) objects, which follow a redder cooling track. Crystallization of
the carbon-oxygen core produces a pile-up on the cooling sequence, observable as an
overdensity first conclusively detected in Gaia data. Massive white dwarfs from merged
binary systems populate a distinct sequence at higher surface gravities. This catalog,
with its probability scores, atmospheric parameters, and multi-band photometry, provides
the foundation for studying all of these phenomena across a volume-complete sample.

## Key columns

| Column | Type | Description |
|--------|------|-------------|
| `wdj_name` | string | WD J designation |
| `source_id` | string | Gaia DR3 unique source identifier |
| `ra_deg` | float64 | Right ascension ICRS (degrees) |
| `dec_deg` | float64 | Declination ICRS (degrees) |
| `parallax_mas` | float64 | Parallax (milliarcseconds) |
| `prob_wd` | float64 | Probability of being a white dwarf (0-1) |
| `g_mag` | float64 | Mean G-band magnitude |
| `bp_mag` | float64 | Mean BP-band magnitude |
| `rp_mag` | float64 | Mean RP-band magnitude |
| `bp_rp` | float64 | BP-RP color index |
| `g_abs_mag` | float64 | Absolute G-band magnitude |
| `teff_k` | float64 | Effective temperature (K) |
| `log_g` | float64 | Surface gravity (log cm/s^2) |
| `mass_msun` | float64 | Mass (solar masses) |
| `distance_pc` | float64 | Distance (parsecs) |
| `ruwe` | float64 | Renormalized unit weight error |

Full schema includes {len(df.columns)} columns with proper motions, uncertainties, extinction, and radial velocities.

## Quick stats

- **{n_total:,}** white dwarf candidates
- **{n_high_prob:,}** with Pwd > 0.75
- Median G magnitude: {g_median:.2f}
- Median Teff: {teff_median:,.0f} K
- Median mass: {mass_median:.2f} Msun
- Median Pwd: {pwd_median:.3f}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/gaia-dr3-white-dwarfs", split="train")
df = ds.to_pandas()

# High-confidence white dwarfs
high_conf = df[df["prob_wd"] > 0.75]
print(f"High-confidence WDs: {{len(high_conf):,}}")

# HR diagram
import matplotlib.pyplot as plt
valid = df.dropna(subset=["bp_rp", "g_abs_mag"])
plt.hexbin(valid["bp_rp"], valid["g_abs_mag"], gridsize=200, mincnt=1, cmap="hot")
plt.colorbar(label="Count")
plt.xlabel("BP - RP (mag)")
plt.ylabel("Absolute G (mag)")
plt.gca().invert_yaxis()
plt.title("Gaia DR3 White Dwarf HR Diagram")
plt.show()

# Mass distribution
df["mass_msun"].dropna().hist(bins=100)
plt.xlabel("Mass (solar masses)")
plt.ylabel("Count")
plt.title("White Dwarf Mass Distribution")
plt.show()
```

## Data source

Gentile Fusillo, N.P. et al. (2021), "A catalogue of white dwarfs in Gaia EDR3",
*MNRAS*, 508, 3877. Accessed via [VizieR CDS](https://vizier.cds.unistra.fr/)
(catalog J/MNRAS/508/3877).

## Related datasets

- [Gaia DR3 Eclipsing Binaries](https://huggingface.co/datasets/juliensimon/gaia-dr3-eclipsing-binaries) -- Gaia eclipsing binary candidates
- [Gaia DR3 Variable Star Summary](https://huggingface.co/datasets/juliensimon/gcvs-variable-stars) -- all Gaia variable star classifications

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/gaia-dr3-white-dwarfs) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{gaia_dr3_white_dwarfs,
  author = {{Simon, Julien}},
  title = {{Gaia DR3 White Dwarfs}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/gaia-dr3-white-dwarfs}},
  note = {{Based on Gentile Fusillo+ 2021 (MNRAS 508, 3877) via VizieR CDS}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update Gaia DR3 white dwarfs: {n_total:,} sources"
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
