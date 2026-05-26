#!/usr/bin/env python3
"""Fetch TGSS ADR1 150 MHz radio catalog from VizieR and upload to HF.

Source: Intema et al. (2017, A&A 598, A78) — TIFR GMRT Sky Survey
Alternative Data Release 1 at 150 MHz, covering 90% of the sky.
VizieR catalog: J/A+A/598/A78
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/tgss-radio-catalog"

# ── Source query ────────────────────────────────────────────────────
ADQL = """SELECT * FROM "J/A+A/598/A78/table3" """

# ── Column mapping ──────────────────────────────────────────────────
RENAME = {
    "RA_ICRS": "ra_deg",
    "RAJ2000": "ra_deg",
    "_RA": "ra_deg",
    "DE_ICRS": "dec_deg",
    "DEJ2000": "dec_deg",
    "_DE": "dec_deg",
    "Speak": "peak_flux_mjy",
    "Stotal": "integrated_flux_mjy",
    "e_Speak": "e_peak_flux_mjy",
    "e_Stotal": "e_integrated_flux_mjy",
    "Rms": "rms_mjy",
    "Maj": "major_axis_arcsec",
    "Min": "minor_axis_arcsec",
    "PA": "position_angle_deg",
    "TGSS": "source_name",
}

# ── Column descriptions for README schema table ────────────────────
COLUMN_DESCRIPTIONS = {
    "source_name": "TGSS catalog designation in the format 'TGSSADR JHHMMSS.s+DDMMSS'; the J2000 sexagesimal position is encoded directly in the name, making the sky coordinates recoverable from the ID alone",
    "ra_deg": "ICRS J2000.0 right ascension in degrees (0-360); derived from the Gaussian fit to the 150 MHz radio emission; typical astrometric accuracy ~2 arcsec",
    "dec_deg": "ICRS J2000.0 declination in degrees (-90 to +90); survey covers declination > -53 deg; derived from the Gaussian fit to the 150 MHz radio emission",
    "peak_flux_mjy": "Peak surface brightness at 150 MHz in mJy/beam, measured at the beam center using a 25 arcsec FWHM synthesized beam; best flux estimator for unresolved point sources",
    "integrated_flux_mjy": "Total integrated flux density in mJy at 150 MHz; for extended sources this exceeds the peak flux; for point sources it equals the peak flux within noise",
    "e_peak_flux_mjy": "1-sigma uncertainty on peak flux density in mJy/beam; includes thermal noise and calibration errors",
    "e_integrated_flux_mjy": "1-sigma uncertainty on integrated flux density in mJy; typically larger than the peak flux error for resolved sources",
    "rms_mjy": "Local background rms noise in mJy/beam measured in an annulus around the source; indicates detection sensitivity at that sky position; sources detected at >= 7 sigma",
    "major_axis_arcsec": "Deconvolved major axis FWHM in arcseconds after removing the 25 arcsec beam; null or ~0 for unresolved point sources where only an upper limit on size is available",
    "minor_axis_arcsec": "Deconvolved minor axis FWHM in arcseconds; null or ~0 for unresolved point sources; a nonzero value indicates the source is spatially resolved",
    "position_angle_deg": "Position angle of the major axis in degrees east from north (0-180); null for circular or unresolved sources where the angle is unconstrained",
}

# ── Dataset description ─────────────────────────────────────────────
DESCRIPTION = """\
The TIFR GMRT Sky Survey Alternative Data Release 1 (TGSS ADR1), a 150 MHz radio \
continuum survey covering 90% of the sky (declination > -53 deg) using the Giant \
Metrewave Radio Telescope. Fills the critical low-frequency gap in all-sky radio catalogs.

TGSS ADR1 is the largest 150 MHz radio survey, observed between 2010 and 2012 with \
the GMRT. It provides 25 arcsecond resolution and a median rms noise of ~3.5 mJy/beam. \
The catalog is essential for low-frequency radio spectral studies, identifying \
steep-spectrum sources such as pulsars, high-redshift radio galaxies, and galaxy \
cluster relics.

The Giant Metrewave Radio Telescope (GMRT) near Pune, India, is one of the world's \
premier low-frequency radio interferometers, consisting of 30 fully steerable 45-meter \
dishes spread over a 25-kilometer baseline. TGSS ADR1 exploits the GMRT's unique \
sensitivity at 150 MHz to produce the deepest wide-field survey at this frequency, \
surpassing earlier efforts like the 7C survey and the Westerbork Northern Sky Survey \
(WENSS) at 325 MHz. The 150 MHz band is scientifically rich because synchrotron \
emission from relativistic electrons is strongest at low frequencies, making TGSS \
especially sensitive to aged electron populations that fade at higher frequencies.

TGSS has proven invaluable for discovering and characterizing diffuse radio emission \
in galaxy clusters, including radio halos, relics, and mini-halos that trace merger \
shocks and turbulence in the intracluster medium. The catalog is also a primary \
resource for identifying ultra-steep-spectrum (USS) radio sources, which are among \
the best tracers of high-redshift radio galaxies at z > 2.
"""


def main():
    print("Fetching TGSS ADR1 catalog from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} raw rows")

    # Rename columns
    df = df.rename(columns={k: v for k, v in RENAME.items() if k in df.columns})

    # Clean string columns
    for col in ["source_name"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
            )

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    flux_median = df["peak_flux_mjy"].median() if "peak_flux_mjy" in df.columns else 0
    rms_median = df["rms_mjy"].median() if "rms_mjy" in df.columns else 0
    ra_min, ra_max = df["ra_deg"].min(), df["ra_deg"].max()
    dec_min, dec_max = df["dec_deg"].min(), df["dec_deg"].max()

    quick_stats = f"""\
- **{n_total:,}** radio sources at 150 MHz
- Median peak flux: {flux_median:.2f} mJy/beam
- Median rms noise: {rms_median:.2f} mJy/beam
- Sky coverage: RA {ra_min:.1f}--{ra_max:.1f} deg, Dec {dec_min:.1f}--{dec_max:.1f} deg"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/tgss-radio-catalog", split="train")
df = ds.to_pandas()

# Flux distribution
import matplotlib.pyplot as plt
df["peak_flux_mjy"].clip(upper=500).hist(bins=200, log=True)
plt.xlabel("Peak flux at 150 MHz (mJy/beam)")
plt.ylabel("Count")
plt.title("TGSS Source Flux Distribution")
plt.show()

# Sky coverage
plt.scatter(df["ra_deg"], df["dec_deg"], s=0.01, alpha=0.1)
plt.xlabel("RA (deg)")
plt.ylabel("Dec (deg)")
plt.title("TGSS ADR1 Sky Coverage (150 MHz)")
plt.show()

# Bright sources (> 1 Jy)
bright = df[df["integrated_flux_mjy"] > 1000]
print(f"{len(bright):,} sources brighter than 1 Jy at 150 MHz")
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="TGSS Alternative Data Release 1 (150 MHz)",
        description=DESCRIPTION,
        tags=["space", "radio", "tgss", "gmrt", "150mhz", "astronomy",
              "open-data", "tabular-data", "parquet"],
        source_url="https://vizier.cds.unistra.fr/viz-bin/VizieR-3?-source=J/A+A/598/A78",
        license="other",
        license_name="vizier-scientific-use",
        license_link="https://cds.unistra.fr/vizier-org/licences_vizier.html",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA13277/PIA13277~small.jpg",
            "alt": "Deep Space Network antenna at Goldstone",
            "credit": "NASA/JPL-Caltech",
        },
        related_datasets=[
            "juliensimon/nvss-radio-catalog",
            "juliensimon/sumss-radio-catalog",
            "juliensimon/unified-radio-catalog",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "ra_deg", "dec_deg", "peak_flux_mjy", "integrated_flux_mjy",
                "e_peak_flux_mjy", "e_integrated_flux_mjy", "rms_mjy",
                "major_axis_arcsec", "minor_axis_arcsec", "position_angle_deg",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="tgss_radio_sources.parquet",
            min_rows=500_000,
            expected_columns=["ra_deg", "dec_deg"],
            critical_columns=["ra_deg", "dec_deg"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update TGSS radio catalog: {n_total:,} sources",
        )
    print("Done.")


if __name__ == "__main__":
    main()
