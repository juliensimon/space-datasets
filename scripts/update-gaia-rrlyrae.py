#!/usr/bin/env python3
"""Fetch Gaia DR3 RR Lyrae variable star catalog from VizieR and upload to HF."""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/gaia-dr3-rrlyrae"

ADQL = """SELECT * FROM "I/358/vrrlyr" """

# ── Column mapping ───────────────────────────────────────────────────
RENAME = {
    "RA_ICRS": "ra_deg",
    "RAJ2000": "ra_deg",
    "_RA": "ra_deg",
    "DE_ICRS": "dec_deg",
    "DEJ2000": "dec_deg",
    "_DE": "dec_deg",
    "Source": "source_id",
    "Pf": "period_days",
    "EpochG": "epoch_g_bjd",
    "AmpG": "amplitude_g_mag",
    "RmagG": "mean_g_mag",
    "RmagBP": "mean_bp_mag",
    "RmagRP": "mean_rp_mag",
    "[Fe/H]": "metallicity_feh",
    "Dist": "distance_pc",
    "SType": "subclassification",
    "Best": "best_classification",
    "NbTr": "n_transits",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "source_id": "Gaia DR3 source identifier (64-bit integer as string); unique and stable within the Gaia DR3 data release",
    "ra_deg": "Right ascension, ICRS J2016.0 (Gaia reference epoch), in decimal degrees (0-360)",
    "dec_deg": "Declination, ICRS J2016.0, in decimal degrees (-90 to +90)",
    "period_days": "Dominant pulsation period in days; RRab (fundamental mode): 0.4-1.0 d; RRc (first overtone): 0.2-0.5 d; null for a small fraction with unreliable period solutions",
    "epoch_g_bjd": "Barycentric Julian Date of maximum light in the G band; reference point for the light curve model",
    "amplitude_g_mag": "Peak-to-peak light curve amplitude in Gaia G band (mag); RRab typically 0.3-1.2 mag; RRc typically 0.1-0.5 mag; encodes metallicity information via the Bailey diagram",
    "mean_g_mag": "Intensity-averaged mean G-band magnitude; RR Lyrae have M_G ~ +0.6 mag (useful standard candles); range ~10-20 mag depending on distance",
    "mean_bp_mag": "Intensity-averaged mean Gaia BP-band (330-680 nm) magnitude; null for faint stars with poor BP photometry",
    "mean_rp_mag": "Intensity-averaged mean Gaia RP-band (640-1050 nm) magnitude; null for faint stars with poor RP photometry",
    "metallicity_feh": "Photometric [Fe/H] in dex, estimated from the period-phi31 Fourier decomposition relation; RR Lyrae are old metal-poor stars, typical range -3.0 to -0.5 dex; null where light curve quality is insufficient",
    "distance_pc": "Photometric distance in parsecs, derived from mean magnitude and period-luminosity-metallicity relation; typical range 100-100,000 pc; null where metallicity or magnitude is unavailable",
    "subclassification": "RR Lyrae pulsation subtype: RRab (fundamental mode, asymmetric light curve), RRc (first overtone, sinusoidal), RRd (double-mode); null for uncertain classifications",
    "best_classification": "Best overall classification label assigned by the Gaia variability pipeline, may include confidence flags",
    "n_transits": "Number of individual Gaia field-of-view transits contributing to the light curve; higher values indicate more reliable period and amplitude estimates",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
The Gaia Data Release 3 catalog of RR Lyrae variable stars -- the largest homogeneous \
catalog of pulsating horizontal-branch stars ever compiled. RR Lyrae stars are essential \
standard candles for the cosmic distance ladder.

RR Lyrae stars are old, low-metallicity pulsating variables found in the Milky Way halo, \
bulge, globular clusters, and nearby galaxies. Their well-defined period-luminosity-metallicity \
relation makes them fundamental distance indicators. Gaia DR3 provides the most comprehensive \
all-sky census of RR Lyrae variables, with precise astrometry, multi-band photometry, light \
curve parameters, metallicity estimates from the light curve shape, and photometric distances.

RR Lyrae stars occupy the horizontal branch of the Hertzsprung-Russell diagram, burning \
helium in their cores after ascending the red giant branch. They are exclusively old \
(> 10 Gyr) and metal-poor to moderately metal-rich, with masses near 0.6-0.8 solar masses \
and luminosities around 40-50 times that of the Sun. Their pulsation is driven by the \
kappa mechanism operating in the partial ionization zone of helium, producing the \
characteristic rapid brightness variations with periods typically between 0.2 and 1.0 days.

The Bailey diagram -- plotting light-curve amplitude against period -- cleanly separates \
the subclasses and encodes information about metallicity: at a given period, more \
metal-poor RRab stars tend to have larger amplitudes. Gaia DR3 exploits this by deriving \
photometric metallicities from the light-curve shape, providing [Fe/H] estimates for \
hundreds of thousands of stars across the Galaxy without the need for spectroscopy.

RR Lyrae stars are particularly powerful tracers of Galactic substructure because they are \
luminous enough to be detected at distances of over 100 kpc, well into the outer halo where \
the debris of accreted dwarf galaxies is found.
"""


def main():
    print("Fetching Gaia DR3 RR Lyrae catalog from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} raw rows")

    # Rename columns
    df = df.rename(columns=RENAME)

    # Clean string columns
    for col in ["source_id", "subclassification", "best_classification"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
            )

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_with_period = int(df["period_days"].notna().sum()) if "period_days" in df.columns else 0
    period_median = df["period_days"].median() if "period_days" in df.columns else 0
    n_with_feh = int(df["metallicity_feh"].notna().sum()) if "metallicity_feh" in df.columns else 0
    feh_median = df["metallicity_feh"].median() if "metallicity_feh" in df.columns else float("nan")
    n_rrab = int((df["subclassification"] == "RRab").sum()) if "subclassification" in df.columns else 0
    n_rrc = int((df["subclassification"] == "RRc").sum()) if "subclassification" in df.columns else 0
    n_rrd = int((df["subclassification"] == "RRd").sum()) if "subclassification" in df.columns else 0

    quick_stats = f"""\
- **{n_total:,}** RR Lyrae variables
- **{n_with_period:,}** with pulsation period (median {period_median:.4f} days)
- **{n_rrab:,}** RRab, **{n_rrc:,}** RRc, **{n_rrd:,}** RRd
- **{n_with_feh:,}** with photometric metallicity (median [Fe/H] = {feh_median:.2f} dex)"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/gaia-dr3-rrlyrae", split="train")
df = ds.to_pandas()

# Period distribution (Bailey diagram)
import matplotlib.pyplot as plt
valid = df.dropna(subset=["period_days", "amplitude_g_mag"])
plt.scatter(valid["period_days"], valid["amplitude_g_mag"], s=0.5, alpha=0.2)
plt.xlabel("Period (days)")
plt.ylabel("Amplitude G (mag)")
plt.title("Gaia DR3 RR Lyrae Bailey Diagram")
plt.show()

# Metallicity distribution
df["metallicity_feh"].dropna().hist(bins=100)
plt.xlabel("[Fe/H] (dex)")
plt.ylabel("Count")
plt.title("RR Lyrae Metallicity Distribution")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Gaia DR3 RR Lyrae Variables",
        description=DESCRIPTION,
        tags=["space", "gaia", "rr-lyrae", "variable-star", "distance-ladder",
              "astronomy", "open-data", "tabular-data", "parquet"],
        source_url="https://vizier.cds.unistra.fr/viz-bin/VizieR-3?-source=I/358/vrrlyr",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA03606/PIA03606~small.jpg",
            "alt": "The Crab Nebula, a supernova remnant",
            "credit": "NASA/ESA/Hubble",
        },
        related_datasets=[
            "juliensimon/gaia-dr3-cepheids",
            "juliensimon/gcvs-variable-stars",
            "juliensimon/gaia-dr3-eclipsing-binaries",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "ra_deg", "dec_deg", "period_days", "epoch_g_bjd",
                "amplitude_g_mag", "mean_g_mag", "mean_bp_mag", "mean_rp_mag",
                "metallicity_feh", "distance_pc", "n_transits",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="gaia_dr3_rrlyrae.parquet",
            min_rows=250_000,
            expected_columns=["source_id", "ra_deg", "dec_deg", "period_days"],
            critical_columns=["source_id", "ra_deg", "dec_deg"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Gaia DR3 RR Lyrae: {n_total:,} variables",
        )
    print("Done.")


if __name__ == "__main__":
    main()
