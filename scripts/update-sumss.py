#!/usr/bin/env python3
"""Fetch SUMSS 843 MHz radio catalog from VizieR and upload to HF.

Source: Mauch et al. (2003, MNRAS 342, 1117) — Sydney University Molonglo
Sky Survey at 843 MHz, covering the southern sky (Dec < -30 deg).
VizieR catalog: VIII/81B
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/sumss-radio-catalog"

# ── Source query ────────────────────────────────────────────────────
ADQL = """SELECT * FROM "VIII/81B/sumss212" """

# ── Column mapping ──────────────────────────────────────────────────
RENAME = {
    "RA_ICRS": "ra_deg",
    "RAJ2000": "ra_deg",
    "_RA": "ra_deg",
    "DE_ICRS": "dec_deg",
    "DEJ2000": "dec_deg",
    "_DE": "dec_deg",
    "Sp": "peak_flux_mjy",
    "St": "integrated_flux_mjy",
    "e_St": "e_integrated_flux_mjy",
    "Maj": "major_axis_arcsec",
    "Min": "minor_axis_arcsec",
    "PA": "position_angle_deg",
    "MajDec": "deconv_major_arcsec",
    "MinDec": "deconv_minor_arcsec",
    "PADec": "deconv_pa_deg",
    "Mosaic": "mosaic_name",
}

# ── Column descriptions for README schema table ────────────────────
COLUMN_DESCRIPTIONS = {
    "ra_deg": "ICRS J2000.0 right ascension in degrees (0-360); survey covers the southern sky (declination < -30 deg); astrometric accuracy ~1-2 arcsec for bright sources",
    "dec_deg": "ICRS J2000.0 declination in degrees; survey lower limit is -90 deg, upper limit -30 deg; the elliptical beam is elongated at lower elevations",
    "peak_flux_mjy": "Peak surface brightness at 843 MHz in mJy/beam; beam size is 45x45 arcsec^2 x sec|dec|, so the effective beam area increases toward the south; equals total flux for compact sources",
    "integrated_flux_mjy": "Total integrated flux density in mJy at 843 MHz; exceeds peak flux for resolved sources such as nearby galaxies or supernova remnants",
    "e_integrated_flux_mjy": "1-sigma uncertainty on integrated flux density in mJy; increases for resolved sources due to deconvolution errors",
    "major_axis_arcsec": "Fitted (beam-convolved) major axis FWHM in arcseconds; includes the synthesized beam contribution; use deconvolved axes for intrinsic source size",
    "minor_axis_arcsec": "Fitted (beam-convolved) minor axis FWHM in arcseconds; always >= the effective beam minor axis",
    "position_angle_deg": "Fitted position angle of the major axis in degrees east from north (0-180); reflects the beam orientation for unresolved sources",
    "deconv_major_arcsec": "Deconvolved major axis FWHM in arcseconds after removing the synthesized beam; null or zero for unresolved point sources where only an upper limit applies",
    "deconv_minor_arcsec": "Deconvolved minor axis FWHM in arcseconds; null or zero for point sources; nonzero confirms the source is spatially resolved at 45 arcsec resolution",
    "deconv_pa_deg": "Deconvolved position angle of the major axis in degrees east from north; null for circular or unresolved sources",
    "mosaic_name": "Identifier of the SUMSS survey mosaic tile containing this source; maps to a specific observed field and can be used to retrieve the parent image",
    "is_resolved": "True if the deconvolved major axis is > 0, indicating the source is spatially resolved; False for point sources; derived flag not present in the original catalog",
}

# ── Dataset description ─────────────────────────────────────────────
DESCRIPTION = """\
The Sydney University Molonglo Sky Survey (SUMSS) at 843 MHz, the southern-sky \
complement to NVSS. Observed with the Molonglo Observatory Synthesis Telescope \
(MOST), covering declinations south of -30 deg.

SUMSS is a deep radio survey at 843 MHz covering 8,100 square degrees of the \
southern sky (declination < -30 deg) with 45 x 45 cosec|dec| arcsecond resolution. \
It fills the gap left by northern-hemisphere surveys like NVSS and FIRST, providing \
a matched-sensitivity southern radio catalog essential for all-sky studies.

The Molonglo Observatory Synthesis Telescope (MOST) is a large east-west Earth-rotation \
aperture synthesis telescope located near Canberra, Australia. Originally built for \
pulsar research, it was reconfigured for continuum survey work at 843 MHz, a frequency \
chosen to complement the 1.4 GHz NVSS in the north. SUMSS achieves a limiting peak \
brightness of approximately 6 mJy/beam at declination -50 degrees, with sensitivity \
scaling as the cosecant of declination due to the telescope's cylindrical geometry. \
The catalog reaches roughly the same source density as NVSS, enabling seamless all-sky \
radio source studies when the two surveys are combined.

SUMSS is particularly important for studying radio sources in the Magellanic Clouds, \
the Galactic bulge at southern latitudes, and southern galaxy clusters that are \
inaccessible to VLA-based surveys. The 843 MHz observing frequency also provides a \
longer lever arm for spectral index measurements when combined with 1.4 GHz (NVSS/FIRST) \
or 150 MHz (TGSS) data, improving constraints on the emission mechanisms of individual \
sources.
"""


def main():
    print("Fetching SUMSS catalog from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} raw rows")

    # Rename columns
    df = df.rename(columns={k: v for k, v in RENAME.items() if k in df.columns})

    # Clean string columns
    for col in ["mosaic_name"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
            )

    # Derived column
    if "deconv_major_arcsec" in df.columns:
        df["is_resolved"] = df["deconv_major_arcsec"] > 0
    else:
        df["is_resolved"] = False

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_resolved = int(df["is_resolved"].sum())
    flux_median = df["peak_flux_mjy"].median() if "peak_flux_mjy" in df.columns else 0
    ra_min, ra_max = df["ra_deg"].min(), df["ra_deg"].max()
    dec_min, dec_max = df["dec_deg"].min(), df["dec_deg"].max()

    quick_stats = f"""\
- **{n_total:,}** radio sources at 843 MHz
- **{n_resolved:,}** resolved sources ({n_resolved / n_total * 100:.1f}%)
- Median peak flux: {flux_median:.2f} mJy/beam
- Sky coverage: RA {ra_min:.1f}--{ra_max:.1f} deg, Dec {dec_min:.1f}--{dec_max:.1f} deg"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/sumss-radio-catalog", split="train")
df = ds.to_pandas()

# Flux distribution
import matplotlib.pyplot as plt
df["peak_flux_mjy"].clip(upper=500).hist(bins=200, log=True)
plt.xlabel("Peak flux at 843 MHz (mJy/beam)")
plt.ylabel("Count")
plt.title("SUMSS Source Flux Distribution")
plt.show()

# Sky coverage (southern sky)
plt.scatter(df["ra_deg"], df["dec_deg"], s=0.01, alpha=0.1)
plt.xlabel("RA (deg)")
plt.ylabel("Dec (deg)")
plt.title("SUMSS Sky Coverage (843 MHz, Dec < -30)")
plt.show()

# Resolved vs unresolved
print(f"Resolved: {df['is_resolved'].sum():,}")
print(f"Unresolved: {(~df['is_resolved']).sum():,}")
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Sydney University Molonglo Sky Survey (SUMSS)",
        description=DESCRIPTION,
        tags=["space", "radio", "sumss", "molonglo", "843mhz", "astronomy",
              "open-data", "tabular-data", "parquet"],
        source_url="https://vizier.cds.unistra.fr/viz-bin/VizieR-3?-source=VIII/81B",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA13277/PIA13277~small.jpg",
            "alt": "Deep Space Network antenna at Goldstone",
            "credit": "NASA/JPL-Caltech",
        },
        related_datasets=[
            "juliensimon/nvss-radio-catalog",
            "juliensimon/first-radio-catalog",
            "juliensimon/tgss-radio-catalog",
            "juliensimon/unified-radio-catalog",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "ra_deg", "dec_deg", "peak_flux_mjy", "integrated_flux_mjy",
                "e_integrated_flux_mjy",
                "major_axis_arcsec", "minor_axis_arcsec", "position_angle_deg",
                "deconv_major_arcsec", "deconv_minor_arcsec", "deconv_pa_deg",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="sumss_radio_sources.parquet",
            min_rows=200_000,
            expected_columns=["ra_deg", "dec_deg"],
            critical_columns=["ra_deg", "dec_deg"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update SUMSS radio catalog: {n_total:,} sources",
        )
    print("Done.")


if __name__ == "__main__":
    main()
