#!/usr/bin/env python3
"""Fetch ATNF Pulsar Catalogue from HEASARC and upload to HF.

Source: Manchester et al. (2005, AJ 129, 1993) — ATNF Pulsar Catalogue
HEASARC table: atnfpulsar
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import heasarc_query

HF_REPO = "juliensimon/pulsar-catalog"

ADQL = """\
SELECT name, alt_name, ra, dec, period, period_dot, dm, flux_1400_mhz,
  companion_type, dm_distance, age, b_surf, e_dot, pulsar_type, pm_tot,
  discovery_date, assoc_object, binary_model
FROM atnfpulsar ORDER BY name\
"""

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "name": "Primary pulsar designation in the J2000 naming convention (e.g. 'J0437-4715'); encodes approximate right ascension (HHMM) and declination (+-DDMM)",
    "alt_name": "Alternative B1950 designation (e.g. 'B0833-45' for Vela); many historically important pulsars are better known by their B-names; null for recently discovered pulsars",
    "ra": "Right ascension in decimal degrees (ICRS J2000.0)",
    "dec": "Declination in decimal degrees (ICRS J2000.0)",
    "period": "Barycentric spin period in seconds, corrected for Earth's orbital motion; normal pulsars: 0.1-5 s, millisecond pulsars: <0.03 s (fastest known: ~1.4 ms); the most precisely measured quantity for each pulsar",
    "period_dot": "First time derivative of the spin period (dimensionless, s/s); positive values indicate spin-down (energy loss); normal pulsars: ~10^-15, millisecond pulsars: ~10^-20, magnetars: ~10^-11; null if timing baseline is too short",
    "dm": "Dispersion measure in pc/cm^3 -- the integrated column density of free electrons along the line of sight; used with Galactic electron density models (NE2001, YMW16) to estimate distance; higher DM implies greater distance or denser intervening medium",
    "flux_1400_mhz": "Mean radio flux density at 1400 MHz in milliJansky (mJy); most pulsars: 0.1-10 mJy; null for pulsars not detected at this frequency or measured only at other frequencies",
    "companion_type": "Classification of the binary companion star when present: 'NS' (neutron star), 'WD' (white dwarf), 'MS' (main sequence), 'He' (helium white dwarf), 'UL' (ultra-light/planet-mass); null for isolated pulsars",
    "dm_distance": "Distance estimate in kiloparsecs derived from the dispersion measure using a Galactic free-electron density model; typical uncertainty ~20-30%; null if DM is unmeasured",
    "age": "Characteristic spin-down age in years, defined as tau = P / (2Pdot); an upper limit on true age since it assumes the pulsar was born spinning infinitely fast; normal pulsars: 10^4-10^8 yr, millisecond pulsars: often exceed the Hubble time",
    "b_surf": "Estimated surface dipole magnetic field strength in Gauss, derived as B = 3.2e19 sqrt(P*Pdot); magnetars: 10^14-10^15 G, normal pulsars: 10^12-10^13 G, millisecond pulsars (recycled): 10^8-10^9 G; null if period_dot is unavailable",
    "e_dot": "Spin-down luminosity (rotational energy loss rate) in erg/s, defined as Edot = -4pi^2*I*Pdot/P^3 where I ~ 10^45 g cm^2 is the moment of inertia; ranges from ~10^30 to ~10^38 erg/s; the Crab pulsar has Edot ~ 5e38 erg/s",
    "pulsar_type": "Physical classification: 'PSR' (radio pulsar), 'SGR' (soft gamma repeater / magnetar), 'AXP' (anomalous X-ray pulsar / magnetar), 'XINS' (X-ray isolated neutron star), 'RRAT' (rotating radio transient emitting sporadic bursts); null for unclassified sources",
    "pm_tot": "Total proper motion in mas/yr (milliarcseconds per year), combining RA and Dec components; pulsars have high space velocities (median ~200 km/s) due to natal supernova kicks; null if astrometric solution is unavailable",
    "discovery_date": "Year of discovery publication; ranges from 1967 (first pulsar, CP 1919) to present",
    "assoc_object": "Astrophysical associations such as supernova remnant (SNR), globular cluster name, or X-ray source; important for age and formation history; null for isolated field pulsars with no known association",
    "binary_model": "Orbital dynamics model used to fit the binary system (e.g. 'BT' for Blandford-Teukolsky, 'DD' for Damour-Deruelle, 'ELL1' for near-circular orbits); null for isolated (non-binary) pulsars",
    "is_millisecond": "Derived flag: True if period < 30 ms, indicating a recycled pulsar spun up by accretion from a companion; millisecond pulsars are among the most stable clocks in the universe and anchor pulsar timing arrays",
    "is_binary": "Derived flag: True if binary_model is non-null, indicating the pulsar has a detected orbital companion",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Complete catalog of known radio pulsars from the ATNF Pulsar Catalogue, including \
spin parameters, dispersion measures, flux densities, and derived quantities.

Pulsars are rapidly rotating neutron stars that emit beams of electromagnetic radiation. \
The ATNF Pulsar Catalogue (Manchester et al. 2005) is the definitive reference catalog, \
maintained by CSIRO. It includes spin period, period derivative, dispersion measure, \
flux density, distance estimates, and derived quantities such as characteristic age, \
surface magnetic field, and spin-down luminosity.

Millisecond pulsars (period < 30 ms) are ancient pulsars spun up by accretion \
from a companion star. They are among the most precise clocks in the universe and are \
used for pulsar timing arrays to detect gravitational waves.

The physics encoded in this catalog is remarkably rich. The spin period P and its time \
derivative P-dot together constrain the pulsar's magnetic field strength \
(B ~ 3.2e19 sqrt(P * P-dot) Gauss), characteristic age (tau ~ P / 2P-dot), and \
spin-down luminosity. Plotting P vs. P-dot produces the famous pulsar "island diagram," \
revealing distinct populations: normal pulsars clustered around P ~ 0.5 s with \
B ~ 10^12 G, millisecond pulsars in the lower-left corner with B ~ 10^8-9 G and ages \
exceeding the Hubble time, and magnetars in the upper-right with B > 10^14 G.
"""


def main():
    print("Fetching ATNF Pulsar Catalogue from HEASARC...")
    df = heasarc_query("atnfpulsar", ADQL)
    print(f"  {len(df):,} pulsars fetched")

    # Derived columns
    df["is_millisecond"] = df["period"].apply(
        lambda x: True if pd.notna(x) and x < 0.03 else (False if pd.notna(x) else None)
    )

    # Clean empty strings to NaN for string columns from text format
    for col in ["companion_type", "binary_model", "pulsar_type", "alt_name", "assoc_object"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
            )

    df["is_binary"] = df["binary_model"].notna()

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Sort by name
    df = df.sort_values("name").reset_index(drop=True)

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_msp = int(df["is_millisecond"].sum())
    n_binary = int(df["is_binary"].sum())
    n_typed = int(df["pulsar_type"].notna().sum())
    median_period = df["period"].median()
    median_dm = df["dm"].median()

    quick_stats = f"""\
- **{n_total:,}** pulsars
- **{n_msp:,}** millisecond pulsars (period < 30 ms)
- **{n_binary:,}** binary pulsars
- Median period: **{median_period:.4f}** s
- Median DM: **{median_dm:.1f}** pc/cm^3"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/pulsar-catalog", split="train")
df = ds.to_pandas()

# Millisecond pulsars
msp = df[df["is_millisecond"] == True]
print(f"{len(msp):,} millisecond pulsars")

# Binary pulsars
binaries = df[df["is_binary"] == True]
print(f"{len(binaries):,} in binary systems")

# Period-period derivative diagram (P-Pdot)
import matplotlib.pyplot as plt
valid = df.dropna(subset=["period", "period_dot"])
valid = valid[valid["period_dot"] > 0]
plt.scatter(valid["period"], valid["period_dot"], s=1, alpha=0.5)
plt.xscale("log"); plt.yscale("log")
plt.xlabel("Period (s)")
plt.ylabel("Period derivative (s/s)")
plt.title("P-Pdot Diagram")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="ATNF Pulsar Catalogue",
        description=DESCRIPTION,
        tags=["space", "pulsar", "neutron-star", "astronomy", "radio",
              "magnetar", "atnf", "open-data", "tabular-data", "parquet"],
        source_url="https://heasarc.gsfc.nasa.gov/W3Browse/all/atnfpulsar.html",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA21085/PIA21085~small.jpg",
            "alt": "Pulsar artist concept showing a rapidly spinning neutron star",
            "credit": "NASA/JPL-Caltech",
        },
        related_datasets=[
            "juliensimon/gamma-ray-bursts",
            "juliensimon/mcgill-magnetar-catalog",
            "juliensimon/xray-binary-catalog",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "ra", "dec", "period", "period_dot", "dm", "flux_1400_mhz",
                "dm_distance", "age", "b_surf", "e_dot", "pm_tot",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="pulsars.parquet",
            min_rows=2000,
            expected_columns=["name", "ra", "dec", "period", "dm", "is_millisecond", "is_binary"],
            critical_columns=["name", "period"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update pulsar catalog: {n_total:,} pulsars",
        )
    print("Done.")


if __name__ == "__main__":
    main()
