#!/usr/bin/env python3
"""Fetch Fermi LAT Fourth AGN Catalog (4LAC) from HEASARC and upload to HF.

Source: Ajello, M. et al. (2020), ApJ, 892, 105
HEASARC table: fermilac
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import heasarc_query

HF_REPO = "juliensimon/fermi-4lac-agn-catalog"

ADQL = "SELECT * FROM fermilac"

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "name": "IAU source name (4FGL designation)",
    "ra": "Right ascension (J2000, degrees, 0-360)",
    "dec": "Declination (J2000, degrees, -90 to +90)",
    "lii": "Galactic longitude (degrees, 0-360)",
    "bii": "Galactic latitude (degrees, -90 to +90)",
    "glon": "Galactic longitude (degrees, 0-360)",
    "glat": "Galactic latitude (degrees, -90 to +90)",
    "significance": "Detection significance in Gaussian sigma over the 4-year LAT baseline",
    "pivot_energy": "Decorrelation (pivot) energy in MeV at which the flux uncertainty is minimized; minimizes spectral index / normalization degeneracy",
    "flux": "Photon flux in ph/cm2/s integrated over 1-100 GeV",
    "unc_flux": "1-sigma statistical uncertainty on the photon flux (ph/cm2/s)",
    "energy_flux": "Energy flux in erg/cm2/s integrated over 100 MeV-100 GeV",
    "unc_energy_flux": "1-sigma statistical uncertainty on the energy flux (erg/cm2/s)",
    "spectral_index": "Power-law photon spectral index; harder sources (blazars) typically 1.5-2.5",
    "unc_spectral_index": "1-sigma statistical uncertainty on the power-law spectral index",
    "pl_flux": "Photon flux from power-law spectral fit (ph/cm2/s, 1-100 GeV)",
    "lp_flux": "Photon flux from log-parabola spectral fit (ph/cm2/s, 1-100 GeV); preferred for curved spectra",
    "lp_index": "Log-parabola spectral index at the pivot energy",
    "lp_beta": "Log-parabola curvature parameter; >0 indicates spectral softening at higher energies",
    "npred": "Number of source photons predicted by the best-fit spectral model in the ROI",
    "redshift": "Spectroscopic redshift; null for ~40% of BL Lac objects that lack optical emission lines",
    "variability_index": "Flux variability chi-squared statistic over the 4-year baseline; >18.48 indicates significant variability at 99% confidence",
    "frac_variability": "Fractional variability amplitude F_var; null if source is not significantly variable",
    "flux_band1": "Photon flux in energy band 1 (50-100 MeV, ph/cm2/s)",
    "flux_band2": "Photon flux in energy band 2 (100-300 MeV, ph/cm2/s)",
    "flux_band3": "Photon flux in energy band 3 (300 MeV-1 GeV, ph/cm2/s)",
    "flux_band4": "Photon flux in energy band 4 (1-3 GeV, ph/cm2/s)",
    "flux_band5": "Photon flux in energy band 5 (3-300 GeV, ph/cm2/s)",
    "class": "AGN subclass: bll (BL Lac), fsrq (flat-spectrum radio quasar), bcu (blazar of uncertain type), rdg (radio galaxy), nlsy1 (narrow-line Seyfert 1), ssrq (steep-spectrum radio quasar), sey (Seyfert)",
    "source_class": "AGN subclass (same encoding as class): bll, fsrq, bcu, rdg, nlsy1, ssrq, sey",
    "optical_class": "Optical spectroscopic classification of the AGN counterpart",
    "agn_class": "AGN classification type from the 4LAC analysis",
    "clean_class": "Y if source passes all quality cuts for the 4LAC clean sample; stricter subset for population studies",
    "sed_class": "Synchrotron peak classification: LSP (low-synchrotron-peaked), ISP (intermediate), HSP (high)",
    "sed_class_index": "Numeric encoding of sed_class: 1 = LSP, 2 = ISP, 3 = HSP",
    "assoc_name": "Counterpart name at other wavelengths (radio, optical, or X-ray); null if no confident association",
    "counterpart": "Multiwavelength counterpart designation from the 4LAC cross-matching procedure",
    "flags": "Bit-field of analysis flags (e.g., confused source, uncertain association, poor localization)",
    "status": "Source analysis status in the 4LAC pipeline (e.g., clean, flagged)",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Active galactic nuclei (AGN) detected by the Fermi Large Area Telescope, the largest \
gamma-ray AGN catalog with source classifications, spectral parameters, and redshifts.

Active galactic nuclei are supermassive black holes at the centers of galaxies that \
produce powerful jets of relativistic particles. When one of these jets points toward \
Earth, the AGN appears as a blazar -- the most common type of gamma-ray source in the sky.

The Fourth LAT AGN Catalog (4LAC) is based on Fermi LAT observations and represents the \
most comprehensive census of gamma-ray AGN. It includes BL Lac objects, flat-spectrum radio \
quasars (FSRQs), and other AGN types, with spectral parameters, variability indices, and \
multiwavelength counterpart associations.

The two dominant blazar subclasses -- BL Lac objects and FSRQs -- represent fundamentally \
different accretion regimes onto supermassive black holes. FSRQs are high-luminosity sources \
with strong broad emission lines, radiatively efficient accretion disks, and gamma-ray spectra \
that tend to be soft due to dominant external Compton scattering. BL Lac objects have weak or \
absent emission lines, radiatively inefficient accretion flows, and harder gamma-ray spectra \
produced primarily by synchrotron self-Compton emission within the jet.

The gamma-ray properties in 4LAC, combined with radio, optical, and X-ray data, enable \
construction of broadband spectral energy distributions (SEDs) spanning over 15 decades in \
frequency, constraining physical jet models and distinguishing between leptonic and hadronic \
emission scenarios.\
"""


def main():
    print("Fetching Fermi 4LAC catalog from HEASARC...")
    df = heasarc_query("fermilac", ADQL)
    print(f"  {len(df):,} AGN fetched")

    # Normalize column names
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    # Numeric coercion
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

    # Clean string columns
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip().replace(
            {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
        )

    # Sort by significance descending
    if "significance" in df.columns:
        df = df.sort_values("significance", ascending=False).reset_index(drop=True)

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    n_total = len(df)

    # Count by class
    class_col = None
    for candidate in ["class", "source_class", "optical_class", "agn_class", "clean_class"]:
        if candidate in df.columns:
            class_col = candidate
            break

    n_with_redshift = int(df["redshift"].notna().sum()) if "redshift" in df.columns else 0
    median_redshift = df["redshift"].median() if "redshift" in df.columns else 0

    class_summary = ""
    if class_col:
        top_classes = df[class_col].value_counts().head(5)
        parts = [f"{count:,} {cls}" for cls, count in top_classes.items()]
        class_summary = ", ".join(parts)

    quick_stats = f"""\
- **{n_total:,}** active galactic nuclei
- **{n_with_redshift:,}** sources with measured redshift
- Median redshift: **{median_redshift:.3f}**"""
    if class_summary:
        quick_stats += f"\n- Top classes: {class_summary}"

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/fermi-4lac-agn-catalog", split="train")
df = ds.to_pandas()

# Brightest AGN by flux
top = df.nlargest(10, "flux")[["name", "flux", "spectral_index", "redshift"]]
print(top)

# Redshift distribution
import matplotlib.pyplot as plt
df["redshift"].dropna().hist(bins=50)
plt.xlabel("Redshift")
plt.title("4LAC AGN Redshift Distribution")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Fermi LAT Fourth AGN Catalog (4LAC)",
        description=DESCRIPTION,
        tags=["space", "gamma-ray", "fermi", "nasa", "agn", "blazars",
              "astronomy", "open-data", "tabular-data", "parquet"],
        source_url="https://heasarc.gsfc.nasa.gov/W3Browse/fermi/fermilac.html",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/physics-datasets-69c2d4682d37dfdb77447bd7",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA03519/PIA03519~small.jpg",
            "alt": "Cassiopeia A supernova remnant in X-ray, optical, and infrared light",
            "credit": "NASA/JPL-Caltech/STScI/CXC/SAO",
        },
        related_datasets=[
            "juliensimon/gamma-ray-bursts",
            "juliensimon/pulsar-catalog",
            "juliensimon/fermi-4fgl-dr4",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[c for c in numeric_cols if c in df.columns],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="fermi-4lac.parquet",
            min_rows=2_500,
            expected_columns=["name", "ra", "dec"],
            critical_columns=["ra", "dec"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Fermi 4LAC AGN catalog: {n_total:,} sources",
        )
    print("Done.")


if __name__ == "__main__":
    main()
