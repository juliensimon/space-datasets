#!/usr/bin/env python3
"""Fetch FIRST radio survey catalog from VizieR and upload to HF."""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/first-radio-catalog"
ADQL = """SELECT * FROM "VIII/92/first14" """

RENAME = {
    "FIRST": "source_name",
    "RAJ2000": "ra_deg",
    "DEJ2000": "dec_deg",
    "Fpeak": "peak_flux_mjy",
    "Fint": "integrated_flux_mjy",
    "Rms": "rms_mjy",
    "Maj": "major_axis_arcsec",
    "Min": "minor_axis_arcsec",
    "PA": "position_angle_deg",
    "fMaj": "deconv_major_arcsec",
    "fMin": "deconv_minor_arcsec",
    "fPA": "deconv_pa_deg",
}

COLUMN_DESCRIPTIONS = {
    "source_name": 'FIRST source identifier in the format "JHHMMSS.s+DDMMSS" derived from J2000 position',
    "ra_deg": "ICRS J2000.0 right ascension in degrees (0-360); positional accuracy ~0.5 arcsec",
    "dec_deg": "ICRS J2000.0 declination in degrees; survey covers ~-10 to +62 deg",
    "peak_flux_mjy": "Peak surface brightness at 1.4 GHz in mJy/beam; detection threshold ~0.75 mJy/beam",
    "integrated_flux_mjy": "Total integrated flux density from Gaussian fit in mJy; use for luminosity calculations",
    "rms_mjy": "Local rms noise at source position in mJy/beam; typically ~0.15 mJy/beam",
    "major_axis_arcsec": "Fitted (convolved) major-axis FWHM in arcsec; includes 5-arcsec beam",
    "minor_axis_arcsec": "Fitted (convolved) minor-axis FWHM in arcsec",
    "position_angle_deg": "Fitted position angle of major axis in degrees east from north (0-180)",
    "deconv_major_arcsec": "Deconvolved major axis in arcsec; 0 for unresolved point sources",
    "deconv_minor_arcsec": "Deconvolved minor axis in arcsec; 0 for unresolved sources",
    "deconv_pa_deg": "Deconvolved position angle in degrees; meaningful only when deconv_major_arcsec > 0",
    "is_resolved": "Derived: True if deconv_major_arcsec > 0 (source resolved above 5-arcsec beam)",
}

DESCRIPTION = """\
The Faint Images of the Radio Sky at Twenty-cm (FIRST) survey catalog, covering 10,575 square degrees
at 1.4 GHz with 5 arcsecond resolution using the NRAO VLA.

The FIRST survey used the VLA in its B-configuration to produce a map of the radio sky at
1.4 GHz with ~5" resolution and a typical rms of 0.15 mJy/beam. The catalog includes
source positions, peak and integrated flux densities, and fitted source sizes.

The FIRST survey was designed as a radio counterpart to the Palomar Observatory Sky Survey, \
targeting the north and south Galactic caps where optical and infrared surveys provide the richest \
multi-wavelength context. Its combination of sub-arcsecond positional accuracy and milliJansky \
sensitivity makes it ideally suited for identifying the radio counterparts of optically selected \
quasars, galaxies, and other extragalactic objects.

Unlike the broader but lower-resolution NVSS, FIRST resolves the internal structure of extended \
radio sources, revealing jets, lobes, and hotspots in radio galaxies. The survey's 5-arcsecond beam \
allows morphological classification of sources and reliable separation of core-dominated and \
lobe-dominated radio AGN.\
"""


def main():
    print("Fetching FIRST radio survey catalog from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} raw rows")

    df = df.rename(columns=RENAME)
    df["is_resolved"] = df["deconv_major_arcsec"] > 0

    # Keep only described columns (drop raw VizieR columns without descriptions)
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Compute domain-specific stats for the README
    n_total = len(df)
    n_resolved = int(df["is_resolved"].sum())
    flux_median = df["peak_flux_mjy"].median()

    quick_stats = f"""\
- **{n_total:,}** radio sources at 1.4 GHz
- **{n_resolved:,}** resolved sources ({n_resolved / n_total * 100:.1f}% of catalog)
- Median peak flux: **{flux_median:.2f}** mJy/beam
- Sky coverage: 10,575 square degrees (north + south Galactic caps)
- Angular resolution: 5 arcsec (VLA B-configuration)"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/first-radio-catalog", split="train")
df = ds.to_pandas()

# Flux distribution (log scale — most sources are faint)
import matplotlib.pyplot as plt

fig, axes = plt.subplots(1, 2, figsize=(14, 5))

df["peak_flux_mjy"].clip(upper=100).hist(bins=200, log=True, ax=axes[0])
axes[0].set_xlabel("Peak flux (mJy/beam)")
axes[0].set_ylabel("Count")
axes[0].set_title("FIRST Source Flux Distribution")

# Sky coverage map
axes[1].scatter(df["ra_deg"], df["dec_deg"], s=0.01, alpha=0.1)
axes[1].set_xlabel("RA (deg)")
axes[1].set_ylabel("Dec (deg)")
axes[1].set_title("FIRST Survey Sky Coverage")
plt.tight_layout()
plt.show()

# Resolved vs unresolved statistics
print(f"Resolved:   {df['is_resolved'].sum():,}")
print(f"Unresolved: {(~df['is_resolved']).sum():,}")
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="FIRST Radio Survey Catalog",
        description=DESCRIPTION,
        tags=["space", "radio", "first", "vla", "astronomy", "1400mhz",
              "open-data", "tabular-data", "parquet"],
        source_url="https://vizier.cds.unistra.fr/viz-bin/VizieR-3?-source=VIII/92",
        license="other",
        license_name="vizier-scientific-use",
        license_link="https://cds.unistra.fr/vizier-org/licences_vizier.html",
        task_categories=["tabular-classification", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={"url": "https://images-assets.nasa.gov/image/PIA13277/PIA13277~small.jpg",
                "alt": "Deep Space Network antenna at Goldstone", "credit": "NASA/JPL-Caltech"},
    ) as p:
        df = p.clean(df, numeric=[
            "ra_deg", "dec_deg", "peak_flux_mjy", "integrated_flux_mjy", "rms_mjy",
            "major_axis_arcsec", "minor_axis_arcsec", "position_angle_deg",
            "deconv_major_arcsec", "deconv_minor_arcsec", "deconv_pa_deg",
        ])
        p.publish(
            df,
            filename="first_radio_sources.parquet",
            min_rows=800_000,
            expected_columns=["source_name", "ra_deg", "dec_deg", "peak_flux_mjy"],
            critical_columns=["source_name", "ra_deg", "dec_deg", "peak_flux_mjy"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update FIRST radio catalog: {len(df):,} sources",
        )
    print("Done.")


if __name__ == "__main__":
    main()
