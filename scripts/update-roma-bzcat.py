#!/usr/bin/env python3
"""Fetch Roma-BZCAT Multi-frequency Blazar Catalog from VizieR and upload to HF.

Static dataset — no GitHub Actions workflow.

Source: VizieR VII/274/bzcat5 (Massaro et al. 2015, 5th edition)
"""

import re

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/roma-bzcat-blazars"

# ── Source query ────────────────────────────────────────────────────
ADQL = 'SELECT * FROM "VII/274/bzcat5"'

# ── Column mapping ──────────────────────────────────────────────────
RENAME = {
    "Name": "name",
    "1FGL": "fermi_1fgl_name",
    "RAJ2000": "ra_deg",
    "DEJ2000": "dec_deg",
    "z": "redshift",
    "Vmag": "v_mag",
    "Rmag": "r_mag",
    "RadioFlux": "radio_flux_mjy",
    "XFlux": "xray_flux_erg_cm2_s",
    "Class": "blazar_class",
    "SpType": "spectral_type",
    "Atel": "atel_reference",
    "Ref": "reference",
}

# ── Column descriptions for README schema table ────────────────────
COLUMN_DESCRIPTIONS = {
    "name": "Source name / BZCAT designation (e.g. '5BZB J0001+3456'); canonical identifier for blazars in the Roma-BZCAT catalog, encoding the blazar class and J2000 position",
    "fermi_1fgl_name": "Associated Fermi 1FGL gamma-ray source name; links this blazar to its Fermi-LAT counterpart from the first Fermi source catalog; null if no Fermi association",
    "ra_deg": "Right ascension J2000 (degrees, 0-360); position of the blazar's optical/radio counterpart",
    "dec_deg": "Declination J2000 (degrees, -90 to +90)",
    "redshift": "Spectroscopic redshift; BL Lacs often lack measurable lines so redshift may be null; FSRQs have well-determined redshifts from broad emission lines",
    "v_mag": "V-band optical magnitude; highly variable in blazars due to jet emission; values represent the catalog epoch, not a time-averaged brightness",
    "r_mag": "R-band optical magnitude; less affected by host galaxy contamination than V-band for nearby BL Lacs",
    "radio_flux_mjy": "Radio flux density at 1.4 GHz (mJy); blazars are by definition radio-loud AGN with flat radio spectra; values >1000 mJy indicate exceptionally bright radio sources",
    "xray_flux_erg_cm2_s": "X-ray flux (erg/cm2/s); traces inverse-Compton emission from the relativistic jet; strong X-ray flux combined with radio loudness is a hallmark of blazar activity",
    "blazar_class": "Blazar classification: BZB = BL Lac (featureless continuum), BZQ = flat-spectrum radio quasar (broad emission lines), BZG = galaxy-dominated (host outshines jet), BZU = uncertain type",
    "spectral_type": "Spectral type or SED class providing additional classification detail; may encode synchrotron peak frequency (LSP/ISP/HSP) for BL Lacs",
    "atel_reference": "Astronomer's Telegram reference number reporting the blazar identification or activity; null for sources not reported via ATel",
    "reference": "Literature reference code for the original classification or spectroscopic confirmation of this blazar",
}

# ── Dataset description ─────────────────────────────────────────────
DESCRIPTION = """\
The Roma-BZCAT 5th edition -- the definitive multi-frequency catalog of confirmed blazars, \
active galactic nuclei with relativistic jets pointed nearly at Earth.

Blazars are the most extreme class of active galactic nuclei (AGN). They are powered by \
supermassive black holes at the centers of galaxies, but what makes them extraordinary is \
that one of their relativistic jets -- twin beams of plasma moving at nearly the speed of \
light -- points almost directly at Earth. This geometric alignment produces dramatic \
observational effects: apparent superluminal motion, extreme variability across the \
electromagnetic spectrum (from radio to TeV gamma-rays on timescales from minutes to years), \
strong and variable polarization, and Doppler-boosted luminosities that can outshine the \
entire host galaxy by orders of magnitude.

Blazars are divided into two main subclasses based on their optical spectra. BL Lac objects \
(BZB) show featureless or nearly featureless optical continua with weak or absent emission \
lines, dominated by non-thermal synchrotron and inverse-Compton emission from the jet. \
Flat-spectrum radio quasars (BZQ/FSRQ) display strong, broad optical emission lines \
characteristic of quasars, indicating a luminous accretion disk and broad-line region in \
addition to the jet.

The Roma-BZCAT (Massaro et al. 2009, 2015) is the most comprehensive and widely cited \
catalog of confirmed blazars, compiled from multi-wavelength observations spanning radio, \
optical, and X-ray bands. It serves as the reference catalog for blazar identification in \
gamma-ray surveys (Fermi-LAT), neutrino follow-up programs (IceCube), and multi-messenger \
astrophysics.
"""


def main():
    print("Fetching Roma-BZCAT 5th edition from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} blazars")

    # Clean empty strings to NaN
    df = df.replace(r"^\s*$", pd.NA, regex=True)

    # Drop recno (VizieR internal row number)
    if "recno" in df.columns:
        df = df.drop(columns=["recno"])

    df = df.rename(columns={k: v for k, v in RENAME.items() if k in df.columns})

    # Snake_case any remaining columns not already renamed
    already_renamed = set(RENAME.values())

    def to_snake(name):
        s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
        s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
        return s.lower().replace("-", "_").replace(" ", "_")

    df.columns = [to_snake(c) if c not in already_renamed else c for c in df.columns]

    # Also coerce anything that looks like magnitude, flux, or frequency
    for col in df.columns:
        if any(kw in col for kw in ["mag", "flux", "freq", "alpha", "index"]):
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Clean string columns
    str_cols = [c for c in df.select_dtypes(include=["object"]).columns]
    for col in str_cols:
        df[col] = df[col].astype(str).str.strip().replace(
            {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
        )

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Sort by name
    if "name" in df.columns:
        df = df.sort_values("name").reset_index(drop=True)

    # ── Domain-specific stats for README ────────────────────────────
    n_total = len(df)
    n_with_z = int(df["redshift"].notna().sum()) if "redshift" in df.columns else 0
    n_with_radio = int(df["radio_flux_mjy"].notna().sum()) if "radio_flux_mjy" in df.columns else 0
    n_with_xray = int(df["xray_flux_erg_cm2_s"].notna().sum()) if "xray_flux_erg_cm2_s" in df.columns else 0

    if "blazar_class" in df.columns:
        class_counts = df["blazar_class"].value_counts()
        n_bzb = int(class_counts.get("BZB", 0)) + sum(
            int(v) for k, v in class_counts.items() if str(k).startswith("BZB") and k != "BZB"
        )
        n_bzq = int(class_counts.get("BZQ", 0)) + sum(
            int(v) for k, v in class_counts.items() if str(k).startswith("BZQ") and k != "BZQ"
        )
        n_bzg = int(class_counts.get("BZG", 0)) + sum(
            int(v) for k, v in class_counts.items() if str(k).startswith("BZG") and k != "BZG"
        )
        n_bzu = int(class_counts.get("BZU", 0)) + sum(
            int(v) for k, v in class_counts.items() if str(k).startswith("BZU") and k != "BZU"
        )
    else:
        n_bzb = n_bzq = n_bzg = n_bzu = 0

    z_median = df["redshift"].median() if "redshift" in df.columns else 0
    z_max = df["redshift"].max() if "redshift" in df.columns else 0

    print(f"  {n_bzb:,} BL Lacs, {n_bzq:,} FSRQs, {n_bzg:,} galaxy-dominated, {n_bzu:,} uncertain")
    print(f"  {n_with_z:,} with redshift (median {z_median:.3f}, max {z_max:.3f})")

    quick_stats = f"""\
- **{n_total:,}** confirmed blazars
- **{n_bzb:,}** BL Lac objects (BZB), **{n_bzq:,}** FSRQs (BZQ), **{n_bzg:,}** galaxy-dominated (BZG), **{n_bzu:,}** uncertain (BZU)
- **{n_with_z:,}** with measured redshift (median z = {z_median:.3f}, max z = {z_max:.3f})
- **{n_with_radio:,}** with radio flux, **{n_with_xray:,}** with X-ray flux"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/roma-bzcat-blazars", split="train")
df = ds.to_pandas()

# BL Lac objects vs FSRQs
bl_lacs = df[df["blazar_class"].str.startswith("BZB", na=False)]
fsrqs = df[df["blazar_class"].str.startswith("BZQ", na=False)]
print(f"{len(bl_lacs):,} BL Lacs, {len(fsrqs):,} FSRQs")

# Redshift distribution by class
import matplotlib.pyplot as plt
for cls, label in [("BZB", "BL Lac"), ("BZQ", "FSRQ")]:
    subset = df[df["blazar_class"].str.startswith(cls, na=False)]
    subset["redshift"].dropna().hist(bins=50, alpha=0.6, label=label)
plt.xlabel("Redshift")
plt.ylabel("Count")
plt.legend()
plt.title("Roma-BZCAT Redshift Distribution by Blazar Class")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Roma-BZCAT Multi-frequency Blazar Catalog",
        description=DESCRIPTION,
        tags=["space", "blazar", "agn", "roma-bzcat", "radio",
              "astronomy", "open-data", "tabular-data", "parquet"],
        source_url="https://vizier.cds.unistra.fr/viz-bin/VizieR-3?-source=VII/274",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA12110/PIA12110~small.jpg",
            "alt": "Hubble Deep Field revealing myriad galaxies across cosmic time",
            "credit": "NASA/ESA/STScI",
        },
        related_datasets=[
            "juliensimon/quasar-catalog",
            "juliensimon/milliquas",
            "juliensimon/fermi-4lac-agn-catalog",
            "juliensimon/fermi-4fgl-dr4",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "ra_deg", "dec_deg", "redshift", "v_mag", "r_mag",
                "radio_flux_mjy", "xray_flux_erg_cm2_s",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="roma_bzcat_blazars.parquet",
            min_rows=3000,
            expected_columns=["name", "ra_deg", "dec_deg", "blazar_class"],
            critical_columns=["name", "ra_deg", "dec_deg"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Upload Roma-BZCAT blazar catalog: {n_total:,} blazars",
        )
    print("Done.")


if __name__ == "__main__":
    main()
