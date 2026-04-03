#!/usr/bin/env python3
"""Fetch RAVE DR6 stellar parameters from VizieR and upload to HF.

Source: Steinmetz et al. (2020), "The Sixth Data Release of the Radial
Velocity Experiment (RAVE)", AJ, 160, 83.
VizieR catalog: III/283
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from dataset_images import banner_markdown, download_banner
from validate import check_dataset
from vizier_tap import vizier_query


HF_REPO = "juliensimon/rave-dr6"
ADQL = 'SELECT * FROM "III/283/ravedr6"'


def main():
    print("Fetching RAVE DR6 stellar parameters from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} RAVE DR6 observations")

    # Drop VizieR internal columns
    for col in ["recno", "SimbadName", "More"]:
        if col in df.columns:
            df = df.drop(columns=[col])

    # Rename columns to snake_case — generous dict with all VizieR variants
    rename = {
        # Identifiers
        "RAVEID": "rave_id",
        "Target": "rave_id",
        "RAVE_OBS_ID": "rave_id",
        # Coordinates
        "RA_ICRS": "ra_deg",
        "RAJ2000": "ra_deg",
        "RAdeg": "ra_deg",
        "DE_ICRS": "dec_deg",
        "DEJ2000": "dec_deg",
        "DEdeg": "dec_deg",
        # Proper motions
        "pmRA": "pm_ra_mas_yr",
        "pmDE": "pm_dec_mas_yr",
        "e_pmRA": "pm_ra_error_mas_yr",
        "e_pmDE": "pm_dec_error_mas_yr",
        # Parallax
        "plx": "parallax_mas",
        "e_plx": "parallax_error_mas",
        # Radial velocity
        "HRV": "radial_velocity_kms",
        "RV": "radial_velocity_kms",
        "eHRV": "radial_velocity_error_kms",
        "e_HRV": "radial_velocity_error_kms",
        "e_RV": "radial_velocity_error_kms",
        # Stellar parameters
        "Teff_K": "teff_k",
        "Teff": "teff_k",
        "TeffK": "teff_k",
        "e_Teff_K": "teff_error_k",
        "e_Teff": "teff_error_k",
        "logg_K": "logg",
        "logg": "logg",
        "e_logg_K": "logg_error",
        "e_logg": "logg_error",
        "Met_K": "metallicity_fe_h",
        "__Fe_H_": "metallicity_fe_h",
        "_Fe_H_": "metallicity_fe_h",
        "[Fe/H]": "metallicity_fe_h",
        "Met_N_K": "metallicity_fe_h",
        "e_Met_K": "metallicity_error",
        "e__Fe_H_": "metallicity_error",
        "e_Met_N_K": "metallicity_error",
        # Photometry
        "Jmag": "j_mag",
        "Hmag": "h_mag",
        "Kmag": "k_mag",
        "e_Jmag": "j_mag_error",
        "e_Hmag": "h_mag_error",
        "e_Kmag": "k_mag_error",
        "Gmag": "gaia_g_mag",
        "BPmag": "gaia_bp_mag",
        "RPmag": "gaia_rp_mag",
        # Alpha enhancement
        "__a_Fe_": "alpha_fe",
        "_a_Fe_": "alpha_fe",
        "[a/Fe]": "alpha_fe",
        "e__a_Fe_": "alpha_fe_error",
        # Individual abundances
        "__Al_H_": "al_h",
        "__Fe_H_N": "fe_h_n",
        "__Mg_H_": "mg_h",
        "__Ni_H_": "ni_h",
        "__Si_H_": "si_h",
        "__Ti_H_": "ti_h",
        "__O_H_": "o_h",
        # Signal-to-noise
        "SNR_K": "snr",
        "STN": "snr",
        "S_N": "snr",
        "SNR": "snr",
        # Gaia cross-match
        "GaiaDR2": "gaia_dr2_source_id",
        "Source": "gaia_dr2_source_id",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

    # Snake_case remaining columns not yet renamed
    def to_snake(name):
        # Handle already snake_case
        if name == name.lower() and "_" in name:
            return name
        s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
        s = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s)
        s = s.replace("-", "_").replace(" ", "_").lower()
        # Clean up double underscores and leading/trailing
        s = re.sub(r"_+", "_", s).strip("_")
        return s

    df.columns = [to_snake(c) for c in df.columns]

    # Numeric conversion for key science columns
    numeric_cols = [
        "ra_deg", "dec_deg",
        "pm_ra_mas_yr", "pm_dec_mas_yr", "pm_ra_error_mas_yr", "pm_dec_error_mas_yr",
        "parallax_mas", "parallax_error_mas",
        "radial_velocity_kms", "radial_velocity_error_kms",
        "teff_k", "teff_error_k",
        "logg", "logg_error",
        "metallicity_fe_h", "metallicity_error",
        "j_mag", "h_mag", "k_mag",
        "j_mag_error", "h_mag_error", "k_mag_error",
        "gaia_g_mag", "gaia_bp_mag", "gaia_rp_mag",
        "alpha_fe", "alpha_fe_error",
        "al_h", "mg_h", "ni_h", "si_h", "ti_h", "o_h",
        "snr",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Validate
    check_dataset(
        df, "rave-dr6",
        min_rows=400_000,
        expected_columns=["ra_deg", "dec_deg", "radial_velocity_kms"],
        critical_columns=["ra_deg", "dec_deg", "radial_velocity_kms"],
    )

    # Stats for README
    n_total = len(df)
    n_with_teff = int(df["teff_k"].notna().sum()) if "teff_k" in df.columns else 0
    n_with_met = int(df["metallicity_fe_h"].notna().sum()) if "metallicity_fe_h" in df.columns else 0
    teff_min = df["teff_k"].min() if "teff_k" in df.columns else 0
    teff_max = df["teff_k"].max() if "teff_k" in df.columns else 0
    met_min = df["metallicity_fe_h"].min() if "metallicity_fe_h" in df.columns else 0
    met_max = df["metallicity_fe_h"].max() if "metallicity_fe_h" in df.columns else 0

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "rave_dr6.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        banner_file = download_banner("rave-dr6", tmp)
        banner_md = banner_markdown("rave-dr6", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "RAVE DR6 Stellar Parameters"
language:
  - en
description: "RAVE DR6 (Radial Velocity Experiment, Data Release 6): {n_total:,} stellar observations with radial velocities, stellar parameters (Teff, log g, [Fe/H]), and elemental abundances for ~452K unique stars from the final data release of this major southern-hemisphere spectroscopic survey. 518K spectra with radial velocities and stellar parameters. Based on Steinmetz et al. (2020), sourced via VizieR CDS Strasbourg."
task_categories:
  - tabular-classification
tags:
  - space
  - stars
  - stellar
  - spectroscopy
  - radial-velocity
  - rave
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
        path: data/rave_dr6.parquet
    default: true
---

# RAVE DR6 Stellar Parameters
{banner_md}
*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

The **Radial Velocity Experiment (RAVE)** Data Release 6 is the final release of this major
southern-hemisphere stellar spectroscopic survey. It contains **{n_total:,}** spectral observations
of ~452,000 unique stars, providing radial velocities, stellar atmospheric parameters
(effective temperature, surface gravity, metallicity), and individual elemental abundances.

## Dataset description

RAVE observed stars in the magnitude range 9 < I < 12 using the 6dF multi-object spectrograph
on the 1.2m UK Schmidt Telescope at the Australian Astronomical Observatory. The survey
operated from 2003 to 2013, covering the calcium triplet region (8410-8795 A) at a spectral
resolution of R ~ 7500.

DR6 provides radial velocities with a typical accuracy of ~1 km/s, effective temperatures,
surface gravities, overall metallicities, and individual abundances for elements including
Mg, Al, Si, Ti, Fe, and Ni. Stellar parameters were derived using an updated pipeline
combining the MADERA algorithm with spectro-photometric information from 2MASS and Gaia DR2.

RAVE was one of the pioneering large-scale stellar spectroscopic surveys, conceived in the early 2000s to measure radial velocities for hundreds of thousands of stars and thereby map the kinematic structure of the Milky Way. Its focus on the calcium triplet region was a deliberate choice: these strong absorption lines are detectable even at modest spectral resolution and in relatively faint stars, making them ideal for efficient radial velocity measurements. The Ca II triplet lines also carry information about stellar surface gravity and metallicity, enabling the derivation of atmospheric parameters beyond the primary velocity measurement.

The survey's target selection in the magnitude range 9 < I < 12 means RAVE primarily sampled giant stars at distances of 1-3 kpc and nearby dwarf stars within a few hundred parsecs. This selection function makes RAVE particularly valuable for studying the Galactic thick disk and halo populations in the solar neighborhood, complementing deeper but more narrowly targeted surveys like APOGEE. When combined with Gaia astrometry (proper motions and parallaxes), RAVE radial velocities complete the six-dimensional phase-space information needed to compute full Galactic orbits, enabling dynamical studies of stellar streams, moving groups, and the local dark matter density.

DR6 includes individual abundances for several alpha-elements (Mg, Si, Ti) and iron-peak elements (Fe, Ni, Al) derived from the spectra, although the moderate spectral resolution limits abundance precision compared to higher-resolution surveys like GALAH or APOGEE. The catalog has been extensively cross-matched with Gaia DR2, providing a ready-made resource for combined spectroscopic-astrometric studies of Galactic structure and stellar populations.

## Quick stats

- **{n_total:,}** spectral observations
- **{n_with_teff:,}** with effective temperature (Teff range: {teff_min:.0f} - {teff_max:.0f} K)
- **{n_with_met:,}** with metallicity ([Fe/H] range: {met_min:.2f} to {met_max:.2f} dex)

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/rave-dr6", split="train")
df = ds.to_pandas()

# Metallicity distribution
import matplotlib.pyplot as plt
met = df["metallicity_fe_h"].dropna()
plt.hist(met, bins=100, edgecolor="none")
plt.xlabel("[Fe/H] (dex)")
plt.ylabel("Count")
plt.title("RAVE DR6 Metallicity Distribution")

# HR diagram (Teff vs log g)
valid = df.dropna(subset=["teff_k", "logg"])
plt.figure()
plt.scatter(valid["teff_k"], valid["logg"], s=0.1, alpha=0.3)
plt.gca().invert_xaxis()
plt.gca().invert_yaxis()
plt.xlabel("Teff (K)")
plt.ylabel("log g (dex)")
plt.title("RAVE DR6 Kiel Diagram")
```

## Data source

Steinmetz M. et al. (2020), "The Sixth Data Release of the Radial Velocity Experiment (RAVE)",
*The Astronomical Journal*, 160, 83.
Accessed via [VizieR](https://vizier.cds.unistra.fr/) (III/283), CDS Strasbourg.

## Related datasets

- [wolf-rayet-stars](https://huggingface.co/datasets/juliensimon/wolf-rayet-stars) -- Galactic Wolf-Rayet Stars
- [brown-dwarf-catalog](https://huggingface.co/datasets/juliensimon/brown-dwarf-catalog) -- Brown Dwarf Catalog
- [galah-dr4](https://huggingface.co/datasets/juliensimon/galah-dr4-stellar-abundances) -- GALAH DR4 Stellar Parameters

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a heart on the [dataset page](https://huggingface.co/datasets/juliensimon/rave-dr6) and share feedback in the Community tab! Also consider giving a star to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{rave_dr6,
  author = {{Simon, Julien}},
  title = {{RAVE DR6 Stellar Parameters}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/rave-dr6}},
  note = {{Based on Steinmetz et al. (2020, AJ 160, 83) via VizieR CDS Strasbourg}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update RAVE DR6 stellar parameters: {n_total:,} observations"
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
