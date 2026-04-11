#!/usr/bin/env python3
"""Fetch cosmic ray spectra from CRDB and upload to HF.

Source: Cosmic Ray Database (CRDB), Maurin et al.
https://lpsc.in2p3.fr/crdb/
"""

import sys

import crdb
import pandas as pd

from hf_dataset_utils import Pipeline

HF_REPO = "juliensimon/crdb-cosmic-ray-spectra"

# ── Column mapping ───────────────────────────────────────────────────
RENAME_MAP = {
    "quantity": "particle",
    "exp": "experiment",
    "exp_type": "experiment_type",
    "sub_exp": "sub_experiment",
    "e": "energy_gev_n",
    "e_bin_lo": "energy_bin_lo_gev_n",
    "e_bin_hi": "energy_bin_hi_gev_n",
    "value": "flux",
    "err_sta_lo": "stat_error_lo",
    "err_sta_hi": "stat_error_hi",
    "err_sys_lo": "sys_error_lo",
    "err_sys_hi": "sys_error_hi",
    "e_relerr": "energy_relative_error",
    "is_upper_limit": "is_upper_limit",
    "phi": "solar_modulation_mv",
    "ads": "ads_bibcode",
    "e_type": "energy_type",
    "datetime": "observation_period",
    "distance": "distance_au",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "particle": "Measured particle or nucleus species: 'H' (proton), 'He', 'C', 'O', 'Fe', 'e-' (electron), 'e+' (positron), 'p-bar' (antiproton), or secondary-to-primary ratios like 'B/C'",
    "experiment": "Name of the cosmic ray experiment that produced the measurement (e.g. 'AMS-02', 'PAMELA', 'CREAM', 'CALET', 'DAMPE')",
    "experiment_type": "Type of detection platform: 'ISS' (International Space Station), 'balloon', 'satellite', 'ground' (air shower array)",
    "sub_experiment": "Sub-experiment, detector configuration, or analysis variant within the experiment; null if not applicable",
    "energy_gev_n": "Kinetic energy per nucleon at the bin center in GeV/n; cosmic ray spectrum spans ~0.01 GeV/n to 10^11 GeV/n",
    "energy_bin_lo_gev_n": "Lower edge of the kinetic energy bin in GeV/n",
    "energy_bin_hi_gev_n": "Upper edge of the kinetic energy bin in GeV/n",
    "flux": "Differential flux in m^-2 s^-1 sr^-1 (GeV/n)^-1, or dimensionless ratio for secondary-to-primary quantities; decreases roughly as E^-3 power law",
    "stat_error_lo": "Downward 1-sigma statistical uncertainty on the flux, in the same units as flux",
    "stat_error_hi": "Upward 1-sigma statistical uncertainty on the flux, in the same units as flux",
    "sys_error_lo": "Downward systematic uncertainty on the flux, in the same units as flux",
    "sys_error_hi": "Upward systematic uncertainty on the flux, in the same units as flux",
    "energy_relative_error": "Relative uncertainty on the energy measurement (fractional); reflects the energy resolution of the detector",
    "is_upper_limit": "True if the flux value represents an upper limit rather than a detection",
    "solar_modulation_mv": "Solar modulation potential in MV (force-field approximation); accounts for the Sun's magnetic field effect on low-energy cosmic rays; higher values mean stronger suppression",
    "ads_bibcode": "NASA ADS bibcode for the publication reporting this measurement",
    "energy_type": "Energy variable used for the measurement: 'EKN' = kinetic energy per nucleon, 'EK' = total kinetic energy, 'R' = rigidity",
    "observation_period": "Time period of the observation as reported by the experiment; format varies by experiment",
    "distance_au": "Heliocentric distance of the measurement in AU; 1.0 for Earth-based, other values for interplanetary missions (Voyager, Pioneer)",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Complete cosmic ray spectral database from CRDB (Cosmic Ray DataBase) -- the \
reference database for cosmic ray physics, maintained by D. Maurin et al. at \
LPSC Grenoble.

Cosmic rays are high-energy charged particles -- mostly protons and atomic nuclei, \
but also electrons and positrons -- that bombard the Earth from all directions. Their \
energies span an astonishing range, from sub-GeV particles modulated by the solar wind \
to ultra-high-energy events exceeding 10^20 eV, far beyond what any terrestrial \
accelerator can produce.

CRDB aggregates measurements from an extraordinary variety of instruments: magnetic \
spectrometers on the International Space Station (AMS-02), balloon-borne calorimeters \
(CREAM, TRACER), satellite experiments (PAMELA, CALET, DAMPE), ground-based air shower \
arrays (KASCADE, Tibet AS-gamma), and Cherenkov telescopes. The database also includes \
secondary-to-primary ratios like boron-to-carbon (B/C), which are critical probes of \
cosmic ray propagation models and the diffusion coefficient of the interstellar medium.

This dataset is essential for constraining cosmic ray propagation models (e.g., GALPROP, \
DRAGON, USINE), testing dark matter annihilation signatures in positron and antiproton \
spectra, calibrating hadronic interaction models used in air shower simulations, and \
studying solar modulation effects.
"""


def main():
    print("Fetching cosmic ray spectra from CRDB...")

    # Query major particle species separately (CRDB doesn't support "*")
    particles = [
        "H", "He", "C", "N", "O", "Ne", "Mg", "Si", "Fe",
        "e-", "e+", "p-bar",
        "B/C", "Be/B", "Be/C",
        "Li", "Be", "B", "F", "Na", "Al", "P", "S", "Cl", "Ar",
        "K", "Ca", "Ti", "V", "Cr", "Mn", "Co", "Ni",
    ]
    all_dfs = []
    for p in particles:
        try:
            tab = crdb.query(p, energy_type="EKN")
            # Flatten multidimensional recarray fields
            rows = []
            for rec in tab:
                row = {}
                for name in tab.dtype.names:
                    val = rec[name]
                    if hasattr(val, '__len__') and not isinstance(val, str) and len(val) == 2:
                        row[f"{name}_lo"] = val[0]
                        row[f"{name}_hi"] = val[1]
                    else:
                        row[name] = val
                rows.append(row)
            df_p = pd.DataFrame(rows)
            print(f"  {p}: {len(df_p):,} rows")
            all_dfs.append(df_p)
        except Exception as e:
            print(f"  {p}: skipped ({e})")

    if not all_dfs:
        print("::error::No data fetched from CRDB")
        sys.exit(1)

    df = pd.concat(all_dfs, ignore_index=True)
    df = df.drop_duplicates()
    print(f"  Total: {len(df):,} unique rows, {len(df.columns)} columns")

    # Rename columns
    rename = {k: v for k, v in RENAME_MAP.items() if k in df.columns}
    df = df.rename(columns=rename)

    # Convert is_upper_limit to bool
    if "is_upper_limit" in df.columns:
        df["is_upper_limit"] = df["is_upper_limit"].astype(bool)

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    df = df.reset_index(drop=True)

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_particles = df["particle"].nunique() if "particle" in df.columns else 0
    n_experiments = df["experiment"].nunique() if "experiment" in df.columns else 0
    print(f"  {n_total:,} measurements, {n_particles} particle types, {n_experiments} experiments")

    quick_stats = f"""\
- **{n_total:,}** cosmic ray flux measurements
- **{n_particles}** particle species
- **{n_experiments}** experiments"""

    if "energy_gev_n" in df.columns and df["energy_gev_n"].notna().any():
        e_min = df["energy_gev_n"].min()
        e_max = df["energy_gev_n"].max()
        quick_stats += f"\n- Energy range: **{e_min:.2e}** to **{e_max:.2e}** GeV/n"

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/crdb-cosmic-ray-spectra", split="train")
df = ds.to_pandas()

# Proton spectrum from AMS-02
ams02_p = df[(df["particle"] == "H") & (df["experiment"] == "AMS-02")]
print(f"{len(ams02_p):,} AMS-02 proton data points")

# All experiments for a given particle
import matplotlib.pyplot as plt
protons = df[df["particle"] == "H"]
for exp, grp in protons.groupby("experiment"):
    plt.scatter(grp["energy_gev_n"], grp["flux"], s=1, label=exp, alpha=0.5)
plt.xscale("log"); plt.yscale("log")
plt.xlabel("Energy (GeV/n)"); plt.ylabel("Flux")
plt.title("Proton Cosmic Ray Spectrum")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Cosmic Ray Database (CRDB)",
        description=DESCRIPTION,
        tags=["space", "physics", "cosmic-ray", "crdb", "high-energy",
              "particle", "open-data", "tabular-data", "parquet"],
        source_url="https://lpsc.in2p3.fr/crdb/",
        task_categories=["tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/physics-datasets-69c2d4682d37dfdb77447bd7",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA03519/PIA03519~small.jpg",
            "alt": "Cassiopeia A supernova remnant in X-ray, optical, and infrared light",
            "credit": "NASA/JPL-Caltech/STScI/CXC/SAO",
        },
        related_datasets=[
            "juliensimon/auger-cosmic-rays",
        ],
    ) as p:
        numeric_cols = [c for c in [
            "energy_gev_n", "energy_bin_lo_gev_n", "energy_bin_hi_gev_n",
            "flux", "stat_error_lo", "stat_error_hi",
            "sys_error_lo", "sys_error_hi", "energy_relative_error",
            "solar_modulation_mv", "distance_au",
        ] if c in df.columns]
        df = p.clean(
            df,
            numeric=numeric_cols,
            strings=[c for c in ["particle", "experiment", "sub_experiment",
                                  "ads_bibcode"] if c in df.columns],
        )
        p.publish(
            df,
            filename="crdb_cosmic_ray_spectra.parquet",
            min_rows=5000,
            expected_columns=["particle", "experiment", "energy_gev_n", "flux"],
            critical_columns=["particle", "experiment"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update CRDB cosmic ray spectra: {n_total:,} measurements",
        )
    print("Done.")


if __name__ == "__main__":
    main()
