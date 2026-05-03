#!/usr/bin/env python3
"""Fetch Gaia DR3 Chemical Cartography catalog from ESA Gaia Archive and upload to HF."""

import io
import time

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

GAIA_TAP = "https://gea.esac.esa.int/tap-server/tap/sync"
HF_REPO = "juliensimon/gaia-dr3-chemical-cartography"
PAGE_SIZE = 500_000

# -- Column mapping --------------------------------------------------------
RENAME = {
    # The Gaia archive returns snake_case column names for this table
    # No renaming needed — columns already match our target schema
}

# -- Column descriptions for README schema table ---------------------------
COLUMN_DESCRIPTIONS = {
    "source_id": "Gaia DR3 unique source identifier; use for cross-matching with other Gaia tables",
    # Radial action Jr
    "jr_med": "Radial galactic orbital action Jr, median estimate (kpc·km/s); measures radial oscillation amplitude in the Milky Way potential",
    "jr_hi": "Radial action Jr, upper 1-sigma confidence bound (kpc·km/s)",
    "jr_lo": "Radial action Jr, lower 1-sigma confidence bound (kpc·km/s)",
    # Vertical action Jz
    "jz_med": "Vertical galactic orbital action Jz, median estimate (kpc·km/s); measures oscillation amplitude perpendicular to the Galactic plane",
    "jz_hi": "Vertical action Jz, upper 1-sigma confidence bound (kpc·km/s)",
    "jz_lo": "Vertical action Jz, lower 1-sigma confidence bound (kpc·km/s)",
    # Azimuthal action Jphi
    "jphi_med": "Azimuthal action Jφ (angular momentum), median estimate (kpc·km/s); conserved for axisymmetric potentials; large negative values indicate prograde disk orbits",
    "jphi_hi": "Azimuthal action Jφ, upper 1-sigma confidence bound (kpc·km/s)",
    "jphi_lo": "Azimuthal action Jφ, lower 1-sigma confidence bound (kpc·km/s)",
    # Cylindrical radius R
    "rplane_med": "Current Galactocentric cylindrical radius R, median (kpc); distance from the Galactic rotation axis",
    "rplane_hi": "Galactocentric radius R, upper 1-sigma confidence bound (kpc)",
    "rplane_lo": "Galactocentric radius R, lower 1-sigma confidence bound (kpc)",
    # Radial velocity vR
    "vrplane_med": "Galactocentric radial velocity vR in the plane, median (km/s); positive = moving away from Galactic center",
    "vrplane_hi": "Radial velocity vR, upper 1-sigma confidence bound (km/s)",
    "vrplane_lo": "Radial velocity vR, lower 1-sigma confidence bound (km/s)",
    # Vertical velocity vz
    "vz_med": "Galactocentric vertical velocity vz, median (km/s); positive = moving toward north Galactic pole",
    "vz_hi": "Vertical velocity vz, upper 1-sigma confidence bound (km/s)",
    "vz_lo": "Vertical velocity vz, lower 1-sigma confidence bound (km/s)",
    # Azimuthal velocity vphi
    "vphi_med": "Galactocentric azimuthal velocity vφ, median (km/s); negative values indicate prograde (disk-like) orbits under the Milky Way convention",
    "vphi_hi": "Azimuthal velocity vφ, upper 1-sigma confidence bound (km/s)",
    "vphi_lo": "Azimuthal velocity vφ, lower 1-sigma confidence bound (km/s)",
    # Maximum height zmax
    "zmax_med": "Maximum height above the Galactic plane reached during the orbit, median (kpc); thin disk stars have zmax < 0.3 kpc, thick disk 0.3–3 kpc, halo > 3 kpc",
    "zmax_hi": "Maximum Galactic height zmax, upper 1-sigma confidence bound (kpc)",
    "zmax_lo": "Maximum Galactic height zmax, lower 1-sigma confidence bound (kpc)",
    # Apocentric radius rapo
    "rapo_med": "Orbital apocentric radius (farthest point from Galactic center), median (kpc)",
    "rapo_hi": "Apocentric radius rapo, upper 1-sigma confidence bound (kpc)",
    "rapo_lo": "Apocentric radius rapo, lower 1-sigma confidence bound (kpc)",
    # Pericentric radius rperi
    "rperi_med": "Orbital pericentric radius (closest approach to Galactic center), median (kpc)",
    "rperi_hi": "Pericentric radius rperi, upper 1-sigma confidence bound (kpc)",
    "rperi_lo": "Pericentric radius rperi, lower 1-sigma confidence bound (kpc)",
    # Eccentricity
    "ecc_med": "Orbital eccentricity, median (0=circular, 1=radial); thin disk: ecc < 0.2, thick disk: 0.2–0.5, halo: > 0.5",
    "ecc_hi": "Orbital eccentricity, upper 1-sigma confidence bound",
    "ecc_lo": "Orbital eccentricity, lower 1-sigma confidence bound",
    # Cartesian x
    "x_med": "Galactocentric Cartesian x coordinate, median (kpc); Sun is at x ≈ -8.3 kpc",
    "x_hi": "Cartesian x coordinate, upper 1-sigma confidence bound (kpc)",
    "x_lo": "Cartesian x coordinate, lower 1-sigma confidence bound (kpc)",
    # Cartesian y
    "y_med": "Galactocentric Cartesian y coordinate, median (kpc)",
    "y_hi": "Cartesian y coordinate, upper 1-sigma confidence bound (kpc)",
    "y_lo": "Cartesian y coordinate, lower 1-sigma confidence bound (kpc)",
    # Cartesian z
    "z_med": "Galactocentric Cartesian z coordinate, median (kpc); z = 0 is the Galactic plane",
    "z_hi": "Cartesian z coordinate, upper 1-sigma confidence bound (kpc)",
    "z_lo": "Cartesian z coordinate, lower 1-sigma confidence bound (kpc)",
    # Total energy
    "energy_med": "Total orbital energy (gravitational + kinetic), median (km²/s²); negative values indicate gravitationally bound orbits",
    "energy_hi": "Total orbital energy, upper 1-sigma confidence bound (km²/s²)",
    "energy_lo": "Total orbital energy, lower 1-sigma confidence bound (km²/s²)",
    # Derived columns
    "ecc_uncertainty": "Average 1-sigma eccentricity uncertainty: (ecc_hi - ecc_lo) / 2; reflects propagated errors from astrometry and radial velocity",
    "is_halo_candidate": "Boolean flag: True when ecc_med > 0.7 AND |zmax_med| > 3.0 kpc, indicating likely halo or accreted stellar population",
}

# -- Dataset description ----------------------------------------------------
DESCRIPTION = """\
The Gaia DR3 Chemical Cartography catalog provides galactic orbital parameters for \
approximately 5.6 million stars derived from Gaia astrometry, radial velocities, and \
chemical abundances from the Radial Velocity Spectrometer (RVS). Each star's orbit in \
the Milky Way's gravitational potential is fully characterized by action integrals \
(Jr, Jz, Jphi), orbital extremes (rapo, rperi, zmax), eccentricity, and current \
phase-space position in both cylindrical and Cartesian Galactocentric coordinates. \
All parameters are provided with three confidence bounds (median, upper, lower 1-sigma) \
that propagate uncertainties from proper motion, parallax, and radial velocity \
measurements through the orbital integration.

Actions are the most powerful coordinates for galactic archaeology because they are \
conserved (or nearly so) over many orbital periods in a smooth potential. Different \
stellar populations occupy distinct, non-overlapping regions of action space: the thin \
disk concentrates near (Jr ≈ 0, Jz ≈ 0, |Jphi| ≈ 1500–2000 kpc·km/s), the thick \
disk spreads to higher Jr and Jz at similar Jphi, accreted halo stars from disrupted \
dwarf galaxies form kinematic streams at characteristic (Jr, Jz, Jphi) loci, and \
the in-situ halo occupies high-eccentricity (ecc > 0.7) retrograde orbits. Combining \
orbital actions with chemical abundances ([Fe/H], [α/Fe]) from the same spectra enables \
chemo-dynamical dissection of the Galaxy's assembly history — the primary science goal \
of chemical cartography.

This is the largest kinematic catalog ever assembled for Milky Way stars, representing \
an order-of-magnitude improvement over previous surveys such as RAVE DR6 (~450,000 \
stars), GALAH DR4 (~600,000 stars), or APOGEE DR17 (~700,000 stars). The Toomre \
diagram (sqrt(vz² + vR²) vs vφ) cleanly separates thin disk, thick disk, and halo \
populations. Scatter plots of zmax vs rapo or ecc distributions reveal the relative \
contributions of in-situ and accreted material across the Galaxy.
"""


def fetch_gaia_chemical_cartography():
    """Fetch chemical cartography catalog from Gaia archive with OFFSET pagination."""
    all_dfs = []
    offset = 0
    while True:
        query = (
            f"SELECT * FROM gaiadr3.chemical_cartography "
            f"ORDER BY source_id "
            f"OFFSET {offset}"
        )
        print(f"  Fetching rows {offset:,}-{offset + PAGE_SIZE:,}...")
        resp = requests.post(GAIA_TAP, data={
            "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv",
            "QUERY": query, "MAXREC": PAGE_SIZE,
        }, timeout=600)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text))
        if len(df) == 0:
            break
        all_dfs.append(df)
        print(f"    got {len(df):,} rows")
        offset += len(df)
        if len(df) < PAGE_SIZE:
            break
        time.sleep(2)
    return pd.concat(all_dfs, ignore_index=True)


def main():
    print("Fetching Gaia DR3 Chemical Cartography from ESA Gaia Archive...")
    df = fetch_gaia_chemical_cartography()
    print(f"  {len(df):,} raw rows")

    # Drop internal columns
    for col in ["solution_id", "recno"]:
        if col in df.columns:
            df = df.drop(columns=[col])

    # Apply rename dict (identity for this table, but kept for consistency)
    df = df.rename(columns=RENAME)

    # Type conversions -- object columns to numeric
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Derived: eccentricity uncertainty
    if "ecc_hi" in df.columns and "ecc_lo" in df.columns:
        df["ecc_uncertainty"] = (df["ecc_hi"] - df["ecc_lo"]) / 2.0

    # Derived: halo candidate flag
    if "ecc_med" in df.columns and "zmax_med" in df.columns:
        df["is_halo_candidate"] = (df["ecc_med"] > 0.7) & (df["zmax_med"].abs() > 3.0)

    # Sort by source_id
    if "source_id" in df.columns:
        df = df.sort_values("source_id").reset_index(drop=True)

    # Keep only described columns (in COLUMN_DESCRIPTIONS order)
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Stats
    n_total = len(df)
    ecc_median = df["ecc_med"].median() if "ecc_med" in df.columns else float("nan")
    frac_eccentric = (df["ecc_med"] > 0.5).mean() if "ecc_med" in df.columns else float("nan")
    zmax_median = df["zmax_med"].median() if "zmax_med" in df.columns else float("nan")
    rapo_median = df["rapo_med"].median() if "rapo_med" in df.columns else float("nan")
    n_halo = int(df["is_halo_candidate"].sum()) if "is_halo_candidate" in df.columns else 0

    quick_stats = f"""\
- **{n_total:,}** stars with galactic orbital parameters
- Median orbital eccentricity (ecc_med): {ecc_median:.3f}
- Fraction with ecc > 0.5 (eccentric/halo orbits): {frac_eccentric:.1%}
- Median maximum Galactic height (zmax_med): {zmax_median:.3f} kpc
- Median apocentric radius (rapo_med): {rapo_median:.3f} kpc
- Halo candidates (ecc > 0.7 & |zmax| > 3 kpc): {n_halo:,}"""

    usage = """\
```python
from datasets import load_dataset
import numpy as np

ds = load_dataset("juliensimon/gaia-dr3-chemical-cartography", split="train")
df = ds.to_pandas()

# Toomre diagram: separates thin disk, thick disk, and halo
import matplotlib.pyplot as plt
vtot = np.sqrt(df["vz_med"]**2 + df["vrplane_med"]**2)
plt.hexbin(df["vphi_med"], vtot, gridsize=300, mincnt=1, cmap="hot")
plt.colorbar(label="Count")
plt.xlabel("vφ (km/s)")
plt.ylabel("√(vz² + vR²) (km/s)")
plt.title("Toomre Diagram — Gaia DR3 Chemical Cartography")
plt.show()

# Eccentricity distribution
df["ecc_med"].hist(bins=100, log=True)
plt.xlabel("Orbital eccentricity")
plt.ylabel("Count (log)")
plt.title("Orbital Eccentricity Distribution")
plt.show()

# zmax vs rapo to show thin/thick disk/halo separation
thin_disk = df[df["ecc_med"] < 0.2]
thick_disk = df[(df["ecc_med"] >= 0.2) & (df["ecc_med"] < 0.5)]
halo = df[df["ecc_med"] >= 0.7]
plt.scatter(thin_disk["rapo_med"].sample(5000), thin_disk["zmax_med"].sample(5000),
            s=1, alpha=0.3, label="Thin disk (ecc<0.2)")
plt.scatter(thick_disk["rapo_med"].sample(5000), thick_disk["zmax_med"].sample(5000),
            s=1, alpha=0.3, label="Thick disk (0.2≤ecc<0.5)")
plt.scatter(halo["rapo_med"].sample(min(5000, len(halo))),
            halo["zmax_med"].sample(min(5000, len(halo))),
            s=1, alpha=0.5, label="Halo (ecc≥0.7)")
plt.xlabel("Apocentric radius rapo (kpc)")
plt.ylabel("Maximum height zmax (kpc)")
plt.legend()
plt.title("Galactic Structure: zmax vs rapo")
plt.show()

# Action space: Jr vs Jphi colored by Jz
halo_candidates = df[df["is_halo_candidate"]]
print(f"Halo candidates: {len(halo_candidates):,}")
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Gaia DR3 Chemical Cartography",
        description=DESCRIPTION,
        tags=["space", "gaia", "milky-way", "galactic-dynamics", "stellar-kinematics",
              "esa", "astronomy", "open-data", "tabular-data", "parquet"],
        source_url="https://gea.esac.esa.int/archive/",
        task_categories=["tabular-classification", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA17005/PIA17005~small.jpg",
            "alt": "The Milky Way galaxy seen from above — NASA composite",
            "credit": "NASA/JPL-Caltech",
        },
        related_datasets=[
            "juliensimon/gaia-dr3-young-stellar-objects",
            "juliensimon/galah-dr4-stellar-abundances",
            "juliensimon/apogee-dr17",
            "juliensimon/rave-dr6",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "jr_med", "jr_hi", "jr_lo",
                "jz_med", "jz_hi", "jz_lo",
                "jphi_med", "jphi_hi", "jphi_lo",
                "rplane_med", "rplane_hi", "rplane_lo",
                "vrplane_med", "vrplane_hi", "vrplane_lo",
                "vz_med", "vz_hi", "vz_lo",
                "vphi_med", "vphi_hi", "vphi_lo",
                "zmax_med", "zmax_hi", "zmax_lo",
                "rapo_med", "rapo_hi", "rapo_lo",
                "rperi_med", "rperi_hi", "rperi_lo",
                "ecc_med", "ecc_hi", "ecc_lo",
                "x_med", "x_hi", "x_lo",
                "y_med", "y_hi", "y_lo",
                "z_med", "z_hi", "z_lo",
                "energy_med", "energy_hi", "energy_lo",
                "ecc_uncertainty",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="gaia_dr3_chemical_cartography.parquet",
            min_rows=5_000_000,
            expected_columns=["source_id", "ecc_med", "jr_med", "jphi_med", "jz_med"],
            critical_columns=["source_id", "ecc_med"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Gaia DR3 chemical cartography: {n_total:,} sources",
        )
    print("Done.")


if __name__ == "__main__":
    main()
