#!/usr/bin/env python3
"""Fetch NVSS radio source catalog from VizieR and upload to HF.

Source: Condon et al. (1998), "The NRAO VLA Sky Survey",
Astronomical Journal, 115, 1693.
VizieR catalog: VIII/65
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/nvss-radio-catalog"

ADQL = """SELECT * FROM "VIII/65/nvss" """

# ── Column mapping ───────────────────────────────────────────────────
RENAME = {
    "NVSS": "source_name",
    "RAJ2000": "ra_deg",
    "DEJ2000": "dec_deg",
    "S1_4": "flux_1400mhz_mjy",
    "e_S1_4": "flux_error_mjy",
    "MajAxis": "major_axis_arcsec",
    "MinAxis": "minor_axis_arcsec",
    "PA": "position_angle_deg",
    "e_RAJ2000": "ra_error_arcsec",
    "e_DEJ2000": "dec_error_arcsec",
    "resFlux": "residual_flux",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "source_name": "NVSS source identifier in the format 'JHHMMSS+DDMMSS' derived from J2000 position",
    "ra_deg": "ICRS J2000.0 right ascension in degrees (0-360); positional accuracy typically < 1 arcsec for sources > 15 mJy",
    "dec_deg": "ICRS J2000.0 declination in degrees (-40 to +90); survey covers declination > -40 deg",
    "flux_1400mhz_mjy": "Integrated flux density at 1.4 GHz in mJy; catalog completeness limit ~2.5 mJy (5-sigma); range from ~2.5 mJy to >100 Jy for the brightest sources",
    "flux_error_mjy": "1-sigma uncertainty on the integrated flux density in mJy; includes thermal noise and systematic calibration error",
    "major_axis_arcsec": "Deconvolved major-axis FWHM of the source in arcsec; null or zero for unresolved point sources (beam = 45 arcsec)",
    "minor_axis_arcsec": "Deconvolved minor-axis FWHM in arcsec; null or zero for unresolved sources; always <= major_axis_arcsec",
    "position_angle_deg": "Position angle of the major axis in degrees east from north (0-180); null for unresolved or circular sources",
    "ra_error_arcsec": "1-sigma uncertainty on the RA position in arcsec; ~1 arcsec near the flux limit, < 0.3 arcsec for bright sources",
    "dec_error_arcsec": "1-sigma uncertainty on the Dec position in arcsec; similar magnitude to ra_error_arcsec",
    "residual_flux": "Residual flux density remaining after Gaussian component subtraction in mJy; large values indicate complex or multi-component sources not well-described by a single Gaussian",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
The NRAO VLA Sky Survey (NVSS) -- the foundational 1.4 GHz radio survey covering 82% of the \
celestial sky (declination > -40 deg) with over 1.8 million discrete radio sources. This is \
the most widely used radio continuum survey in astronomy.

The NVSS used the VLA in its compact D and DnC configurations to survey the sky north of \
declination -40 degrees at 1.4 GHz with ~45" resolution and a completeness limit of about \
2.5 mJy. The resulting catalog is the primary reference for radio source populations and \
is widely used for cross-matching with optical, infrared, and X-ray catalogs.

NVSS remains the single most cited radio survey in astronomy, serving as the backbone for \
virtually all statistical studies of the radio source population at centimeter wavelengths. \
Its uniform sensitivity across more than three-quarters of the celestial sphere makes it the \
standard reference for radio source counts, luminosity functions, and large-scale structure \
analyses. The catalog spans the full range of radio source types, from nearby star-forming \
galaxies and supernova remnants to powerful radio galaxies and quasars at cosmological distances.

The survey's 45-arcsecond resolution means that most extragalactic sources appear unresolved, \
making NVSS particularly well suited for measuring total flux densities of compact and \
moderately extended sources. For extended sources like giant radio galaxies or cluster halos, \
the VLA's D-configuration sensitivity to large angular scales ensures that diffuse emission \
is not resolved out, a critical advantage over higher-resolution surveys like FIRST or VLASS. \
NVSS flux densities are the standard reference point for computing radio spectral indices \
when combined with catalogs at other frequencies.

NVSS is widely used as a finding chart for radio follow-up observations, as a positional \
cross-matching reference for multi-wavelength catalogs (SDSS, 2MASS, WISE, eROSITA), and \
as a training set for machine learning classification of radio sources. Its declination limit \
of -40 degrees makes it complementary to the Sydney University Molonglo Sky Survey (SUMSS), \
which covers the southern sky at 843 MHz with comparable sensitivity and resolution.
"""


def main():
    print("Fetching NVSS radio source catalog from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} raw rows")

    # Rename columns
    df = df.rename(columns={k: v for k, v in RENAME.items() if k in df.columns})

    # Drop VizieR internal columns
    for col in ["recno", "More", "SimbadName"]:
        if col in df.columns:
            df = df.drop(columns=[col])

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    flux_median = df["flux_1400mhz_mjy"].median()
    dec_min, dec_max = df["dec_deg"].min(), df["dec_deg"].max()
    n_bright = int((df["flux_1400mhz_mjy"] > 1000).sum())

    quick_stats = f"""\
- **{n_total:,}** radio sources
- Median flux density: {flux_median:.2f} mJy
- Declination range: {dec_min:.1f} to {dec_max:.1f} degrees
- Sky coverage: ~82% of the celestial sphere (dec > -40 deg)
- **{n_bright:,}** bright sources (> 1 Jy)"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/nvss-radio-catalog", split="train")
df = ds.to_pandas()

# Flux distribution
import matplotlib.pyplot as plt
df["flux_1400mhz_mjy"].clip(upper=1000).hist(bins=200, log=True)
plt.xlabel("Flux density at 1.4 GHz (mJy)")
plt.ylabel("Count")
plt.title("NVSS Source Flux Distribution")
plt.show()

# Sky density map
plt.hexbin(df["ra_deg"], df["dec_deg"], gridsize=100, mincnt=1)
plt.colorbar(label="Source count")
plt.xlabel("RA (deg)")
plt.ylabel("Dec (deg)")
plt.title("NVSS Sky Density")
plt.show()

# Bright sources (> 1 Jy)
bright = df[df["flux_1400mhz_mjy"] > 1000]
print(f"Sources > 1 Jy: {len(bright):,}")
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="NVSS Radio Source Catalog",
        description=DESCRIPTION,
        tags=["space", "radio", "nvss", "vla", "nrao", "astronomy",
              "1400mhz", "open-data", "tabular-data", "parquet"],
        source_url="https://vizier.cds.unistra.fr/viz-bin/VizieR-3?-source=VIII/65",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA13277/PIA13277~small.jpg",
            "alt": "Deep Space Network antenna at Goldstone",
            "credit": "NASA/JPL-Caltech",
        },
        related_datasets=[
            "juliensimon/first-radio-catalog",
            "juliensimon/sumss-radio-catalog",
            "juliensimon/unified-radio-catalog",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "ra_deg", "dec_deg", "flux_1400mhz_mjy", "flux_error_mjy",
                "major_axis_arcsec", "minor_axis_arcsec", "position_angle_deg",
                "ra_error_arcsec", "dec_error_arcsec", "residual_flux",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="nvss_radio_sources.parquet",
            min_rows=1_500_000,
            expected_columns=["source_name", "ra_deg", "dec_deg", "flux_1400mhz_mjy"],
            critical_columns=["source_name", "ra_deg", "dec_deg", "flux_1400mhz_mjy"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update NVSS radio catalog: {n_total:,} sources",
        )
    print("Done.")


if __name__ == "__main__":
    main()
