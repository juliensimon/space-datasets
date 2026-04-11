#!/usr/bin/env python3
"""Fetch CHIME/FRB Catalog from VizieR and upload to HF.

Source: CHIME/FRB Collaboration (2021, ApJS, 257, 59)
VizieR catalog: J/ApJS/257/59/table2
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/chime-frb-catalog"

# ── Source query ────────────────────────────────────────────────────
ADQL = """\
SELECT Name, RpName, RAJ2000, DEJ2000, GLON, GLAT, SNR, DM, DMfitb, \
bcwidth, Scat, Flux, Fluence, Nsb \
FROM "J/ApJS/257/59/table2"\
"""

# ── Column mapping ──────────────────────────────────────────────────
RENAME = {
    "Name": "tns_name",
    "RpName": "repeater_name",
    "RAJ2000": "ra_deg",
    "DEJ2000": "dec_deg",
    "GLON": "glon_deg",
    "GLAT": "glat_deg",
    "SNR": "snr",
    "DM": "dm_pc_cm3",
    "DMfitb": "dm_fitb_pc_cm3",
    "bcwidth": "width_ms",
    "Scat": "scattering_time_ms",
    "Flux": "flux_jy",
    "Fluence": "fluence_jy_ms",
    "Nsb": "sub_burst_count",
}

# ── Column descriptions for README schema table ────────────────────
COLUMN_DESCRIPTIONS = {
    "tns_name": "Transient Name Server designation encoding the discovery date (e.g. 'FRB 20181030A' = detected 2018 Oct 30, first event that day); the canonical identifier for cross-referencing with other catalogs",
    "repeater_name": "Common name of the repeating source this burst belongs to (e.g. 'FRB 20121102A'); null for apparent one-off events; non-null values rule out cataclysmic progenitor models for that source",
    "ra_deg": "Right ascension of best-fit burst position (ICRS J2000.0, degrees, 0-360); CHIME localization precision is typically 10-30 arcmin due to the instrument's fixed north-south orientation",
    "dec_deg": "Declination of best-fit burst position (ICRS J2000.0, degrees, -90 to +90); CHIME is sensitive to declinations above roughly -20 deg",
    "glon_deg": "Galactic longitude (degrees, 0-360); used to assess line-of-sight Milky Way DM contribution and scattering screen effects",
    "glat_deg": "Galactic latitude (degrees, -90 to +90); bursts at low |b| have higher Milky Way DM contributions and stronger scattering",
    "dm_pc_cm3": "Dispersion Measure -- integrated free-electron column density along the line of sight (pc/cm3); extragalactic FRBs typically 100-2500 pc/cm3; subtract Milky Way contribution to obtain host+IGM DM, a crude redshift proxy",
    "dm_fitb_pc_cm3": "DM measured by fitting the burst structure (pc/cm3); may differ from dm_pc_cm3 when the burst has complex sub-structure; null if structure-based fitting was not performed",
    "width_ms": "Burst width at 600 MHz after intra-channel dedispersion (ms); FRBs span ~0.1-100 ms; very narrow widths (<1 ms) constrain the emission region size",
    "flux_jy": "Peak flux density at the fiducial reference frequency (Jy; 1 Jy = 10^-26 W/m2/Hz); null when only an upper or lower limit is available",
    "fluence_jy_ms": "Burst fluence -- flux density integrated over the burst duration (Jy*ms); proportional to detected energy; used to construct the FRB energy function",
    "scattering_time_ms": "Temporal broadening of the burst due to multi-path scattering in turbulent plasma (ms at 600 MHz); scales steeply with DM; null when the burst is unresolved",
    "snr": "Signal-to-noise ratio of the detection in the CHIME/FRB real-time pipeline; drives the detection completeness function; bursts near the threshold (SNR ~8-10) have less reliable morphology parameters",
    "sub_burst_count": "Number of distinct sub-bursts identified within the event envelope; values >=2 indicate temporal fine structure common in repeating sources; null when sub-burst decomposition was not attempted",
    "is_repeater": "True if this burst originates from a source with at least one other detected burst in the catalog or literature; False for apparent one-off events; repeaters have distinct morphological and spectral properties",
}

# ── Dataset description ─────────────────────────────────────────────
DESCRIPTION = """\
Fast Radio Bursts (FRBs) detected by the Canadian Hydrogen Intensity Mapping Experiment \
(CHIME) telescope -- one of the most exciting mysteries in modern astrophysics.

First discovered in 2007, FRBs are millisecond-duration radio transients of extragalactic \
origin whose physical origin remains debated, though magnetars are a leading candidate. \
CHIME, a radio telescope at the Dominion Radio Astrophysical Observatory in British Columbia, \
Canada, has revolutionized FRB science by detecting hundreds of bursts thanks to its enormous \
field of view (~200 square degrees) and continuous operation at 400-800 MHz.

The First CHIME/FRB Catalog (CHIME/FRB Collaboration, 2021, ApJS, 257, 59) contains FRBs \
detected between 2018 July 25 and 2019 July 1, representing the largest uniform FRB sample \
to date.

The dispersion measure (DM) recorded for each burst encodes the integrated column density \
of free electrons along the line of sight, making FRBs powerful probes of the intergalactic \
medium and the so-called 'missing baryons' problem. High-DM events trace sightlines through \
cosmological distances where the intervening plasma imprints information about large-scale \
structure, the epoch of helium reionization, and the baryon content of the cosmic web.

Repeating sources are of particular scientific interest because they rule out cataclysmic \
progenitor models and constrain the local environment of the source. Burst morphology \
parameters such as scattering time and sub-burst structure encode propagation effects \
through turbulent plasma, providing diagnostics of the circum-source and host-galaxy \
interstellar medium at extragalactic distances.
"""


def main():
    print("Fetching CHIME/FRB Catalog from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} FRB events")

    df = df.rename(columns={k: v for k, v in RENAME.items() if k in df.columns})

    # Clean string columns
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip().replace(
            {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
        )

    # Derive is_repeater AFTER string cleaning
    if "repeater_name" in df.columns:
        df["is_repeater"] = df["repeater_name"].notna() & (df["repeater_name"] != "-9999") & (df["repeater_name"] != "<NA>")

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # ── Domain-specific stats for README ────────────────────────────
    n_total = len(df)
    n_repeaters = int(df["is_repeater"].sum()) if "is_repeater" in df.columns and df["is_repeater"].dtype == bool else 0
    median_dm = df["dm_pc_cm3"].median() if "dm_pc_cm3" in df.columns else 0
    max_dm = df["dm_pc_cm3"].max() if "dm_pc_cm3" in df.columns else 0
    median_snr = df["snr"].median() if "snr" in df.columns else 0

    quick_stats = f"""\
- **{n_total:,}** FRB events
- **{n_repeaters}** from repeating sources
- Median DM: **{median_dm:.1f}** pc/cm^3
- Max DM: **{max_dm:.1f}** pc/cm^3
- Median S/N: **{median_snr:.1f}**"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/chime-frb-catalog", split="train")
df = ds.to_pandas()

# DM distribution
import matplotlib.pyplot as plt
df["dm_pc_cm3"].hist(bins=50)
plt.xlabel("Dispersion Measure (pc/cm^3)")
plt.ylabel("Count")
plt.title("CHIME/FRB DM Distribution")
plt.show()

# Repeaters vs one-offs
repeaters = df[df["is_repeater"] == True]
one_offs = df[df["is_repeater"] == False]
print(f"{len(repeaters)} repeaters, {len(one_offs)} one-offs")

# Sky distribution colored by DM
plt.figure(figsize=(12, 6))
plt.scatter(df["ra_deg"], df["dec_deg"], c=df["dm_pc_cm3"], s=5, cmap="viridis")
plt.colorbar(label="DM (pc/cm^3)")
plt.xlabel("RA (deg)")
plt.ylabel("Dec (deg)")
plt.title("CHIME/FRB Sky Distribution")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="CHIME/FRB Catalog",
        description=DESCRIPTION,
        tags=["space", "frb", "fast-radio-burst", "chime", "radio",
              "astronomy", "open-data", "tabular-data", "parquet"],
        source_url="https://vizier.cds.unistra.fr/viz-bin/VizieR-3?-source=J/ApJS/257/59",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA13277/PIA13277~small.jpg",
            "alt": "Deep Space Network antenna at Goldstone",
            "credit": "NASA/JPL-Caltech",
        },
        related_datasets=[
            "juliensimon/pulsar-catalog",
            "juliensimon/gamma-ray-bursts",
            "juliensimon/gravitational-wave-events",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "ra_deg", "dec_deg", "dm_pc_cm3", "dm_fitb_pc_cm3",
                "width_ms", "flux_jy", "fluence_jy_ms",
                "scattering_time_ms", "snr", "sub_burst_count",
                "glon_deg", "glat_deg",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="chime_frb_catalog.parquet",
            min_rows=500,
            expected_columns=["tns_name", "ra_deg", "dec_deg", "dm_pc_cm3"],
            critical_columns=["tns_name", "dm_pc_cm3"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update CHIME/FRB catalog: {n_total:,} events",
        )
    print("Done.")


if __name__ == "__main__":
    main()
