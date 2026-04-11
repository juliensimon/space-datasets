#!/usr/bin/env python3
"""Fetch Fermi LAT 4FGL-DR4 gamma-ray source catalog and upload to HF.

Source: Fermi LAT collaboration — 14-year all-sky gamma-ray survey.
FITS catalog from https://fermi.gsfc.nasa.gov/ssc/data/access/lat/14yr_catalog/
"""

import tempfile

import pandas as pd
import requests
from astropy.io import fits
from astropy.table import Table

from hf_dataset_utils import Pipeline

FITS_URL = "https://fermi.gsfc.nasa.gov/ssc/data/access/lat/14yr_catalog/gll_psc_v35.fit"
HF_REPO = "juliensimon/fermi-4fgl-dr4"

# ── Column mapping ───────────────────────────────────────────────────
RENAME = {
    "Source_Name": "source_name",
    "RAJ2000": "ra_deg",
    "DEJ2000": "dec_deg",
    "GLON": "glon_deg",
    "GLAT": "glat_deg",
    "Signif_Avg": "significance",
    "Flux1000": "flux_1000_mev",
    "Energy_Flux100": "energy_flux_100_mev",
    "SpectrumType": "spectrum_type",
    "Variability_Index": "variability_index",
    "CLASS1": "source_class",
    "ASSOC1": "association",
    "Redshift": "redshift",
    "Flags": "flags",
    "Pivot_Energy": "pivot_energy_mev",
    "PL_Index": "power_law_index",
    "LP_Index": "log_parabola_index",
    "LP_beta": "log_parabola_beta",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "source_name": "4FGL catalog designation encoding position (e.g. '4FGL J0001.2+3738' = J2000 RA 00h01m, Dec +37d38'); the '4FGL' prefix identifies this as the Fourth Fermi LAT catalog",
    "ra_deg": "Right ascension of source centroid (ICRS J2000.0, degrees, 0-360); LAT angular resolution is ~0.1 deg at 10 GeV, ~1 deg at 1 GeV",
    "dec_deg": "Declination of source centroid (ICRS J2000.0, degrees, -90 to +90)",
    "glon_deg": "Galactic longitude (degrees, 0-360); sources at low |b| sit in the Galactic plane where diffuse emission and source confusion are highest",
    "glat_deg": "Galactic latitude (degrees, -90 to +90); |b| < 10 deg indicates Galactic plane sources; extragalactic sources (blazars, radio galaxies) populate high latitudes",
    "significance": "Detection significance averaged over the full energy range (sigma); threshold for catalog inclusion is ~4 sigma; bright sources exceed 100 sigma",
    "flux_1000_mev": "Integral photon flux above 1 GeV (photons/cm2/s); chosen to minimize dependence on the poorly constrained low-energy spectral shape; null for very soft sources",
    "energy_flux_100_mev": "Integral energy flux from 100 MeV to 100 GeV (erg/cm2/s); the most physically meaningful flux measure capturing the bolometric gamma-ray output over the LAT band",
    "spectrum_type": "Best-fit spectral model: 'PowerLaw' (single power law, typical for young pulsars), 'LogParabola' (curved spectrum, typical for BL Lacs), 'PLSuperExpCutoff' (power law with exponential cutoff, characteristic of pulsars)",
    "variability_index": "Sum of log-likelihood ratio test statistics from monthly light curve fits; values above 18.48 indicate flux variability at >99% confidence; blazars typically show values of 20-1000",
    "source_class": "Astrophysical classification: 'bll' (BL Lac object), 'fsrq' (Flat Spectrum Radio Quasar), 'psr' (pulsar), 'snr' (supernova remnant), 'pwn' (pulsar wind nebula), '' / null (unassociated); uppercase indicates high-confidence association",
    "association": "Name of the counterpart source at other wavelengths (e.g. radio, X-ray, optical); null for unassociated sources (~26% of catalog)",
    "redshift": "Spectroscopic redshift of the associated extragalactic counterpart; null for Galactic sources and unassociated sources; confirmed range spans 0.002 to ~3.1 for blazars",
    "flags": "Bitmask of analysis quality and caution flags (see 4FGL paper Table 3); bit 0 = source is in a region of bright diffuse emission; non-zero flags indicate results should be used with caution",
    "pivot_energy_mev": "Reference energy at which the spectral normalization and index are decorrelated (MeV); chosen to minimize the covariance between flux normalization and spectral index; typically 500-5000 MeV",
    "power_law_index": "Photon spectral index Gamma for sources fit with a power law (flux proportional to E^-Gamma); typical values: 1.5-2.0 for hard blazars, 2.0-3.0 for soft sources and pulsars; null for other spectral models",
    "log_parabola_index": "Spectral index alpha at the pivot energy for sources fit with a log-parabola; null for sources using a different spectral model",
    "log_parabola_beta": "Spectral curvature parameter beta for log-parabola sources; beta > 0 means the spectrum curves downward (softer at higher energies); null for other spectral models",
    "is_variable": "True when variability_index exceeds 18.48 (99% confidence variability threshold); predominantly blazars; False includes both truly steady sources and sources with insufficient statistics",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
The Fourth Fermi Large Area Telescope Source Catalog, Data Release 4 (4FGL-DR4), \
based on 14 years of all-sky gamma-ray survey data. The deepest catalog of the \
gamma-ray sky ever produced, with sources spanning blazars, pulsars, supernova \
remnants, globular clusters, starburst galaxies, and many unidentified sources.

The Fermi LAT is a pair-conversion telescope sensitive to gamma rays from roughly \
20 MeV to more than 1 TeV. With Pass 8 event reconstruction and 14 years of exposure, \
the catalog reaches a point-source sensitivity of approximately 2 x 10^-12 erg/cm2/s \
in energy flux -- deep enough to detect faint pulsars, distant blazars, and diffuse \
emission from star-forming regions.

The source population is remarkably diverse. Blazars dominate the extragalactic sky, \
their relativistic jets producing variable gamma-ray emission through inverse-Compton \
scattering. Pulsars are the most numerous Galactic source class, emitting pulsed gamma \
rays from magnetospheric particle acceleration. Over a thousand sources remain \
unassociated with known counterparts, representing active classification targets for \
machine learning and multi-wavelength follow-up.
"""


def main():
    print("Downloading Fermi 4FGL-DR4 FITS catalog...")
    resp = requests.get(FITS_URL, timeout=300)
    resp.raise_for_status()

    with tempfile.NamedTemporaryFile(suffix=".fit") as tmp_fits:
        tmp_fits.write(resp.content)
        tmp_fits.flush()
        print(f"  Downloaded {len(resp.content) / 1024 / 1024:.1f} MB")

        table = Table.read(tmp_fits.name, hdu=1)
        # Filter out multidimensional columns (can't convert to pandas)
        names = [name for name in table.colnames if len(table[name].shape) <= 1]
        df = table[names].to_pandas()

    print(f"  {len(df):,} sources in catalog")

    # Select and rename columns
    available = {k: v for k, v in RENAME.items() if k in df.columns}
    df = df[list(available.keys())].rename(columns=available)

    # Convert flags to int
    if "flags" in df.columns:
        df["flags"] = pd.to_numeric(df["flags"], errors="coerce").astype("Int64")

    # Clean string columns
    for col in ["source_name", "spectrum_type", "source_class", "association"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
            df[col] = df[col].replace({"": None, "nan": None})

    # Derived column
    df["is_variable"] = df["variability_index"] > 18.48

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_variable = int(df["is_variable"].sum())
    n_redshift = int(df["redshift"].notna().sum()) if "redshift" in df.columns else 0
    top_classes = (
        df[df["source_class"].notna() & (df["source_class"] != "")]
        .groupby("source_class").size()
        .sort_values(ascending=False)
        .head(10)
    )
    top_classes_str = "\n".join(
        f"  - **{cls}**: {count:,}" for cls, count in top_classes.items()
    )

    quick_stats = f"""\
- **{n_total:,}** gamma-ray sources
- **{n_variable:,}** variable sources (99% confidence)
- **{n_redshift:,}** sources with measured redshift
- Top source classes:
{top_classes_str}"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/fermi-4fgl-dr4", split="train")
df = ds.to_pandas()

# Brightest sources by significance
brightest = df.sort_values("significance", ascending=False).head(20)

# Variable blazars
variable_blazars = df[
    (df["is_variable"] == True) &
    (df["source_class"].isin(["bll", "fsrq", "BLL", "FSRQ"]))
]

# Sky distribution
import matplotlib.pyplot as plt
import numpy as np
fig, ax = plt.subplots(subplot_kw={"projection": "aitoff"})
l = np.radians(df["glon_deg"].values)
l[l > np.pi] -= 2 * np.pi
b = np.radians(df["glat_deg"].values)
ax.scatter(l, b, s=0.1, alpha=0.3)
plt.title("Fermi 4FGL-DR4 Gamma-Ray Sky")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Fermi LAT 4FGL-DR4 Gamma-Ray Source Catalog",
        description=DESCRIPTION,
        tags=["space", "gamma-ray", "fermi", "lat", "nasa", "astronomy",
              "high-energy", "open-data", "tabular-data", "parquet"],
        source_url="https://fermi.gsfc.nasa.gov/ssc/data/access/lat/14yr_catalog/",
        task_categories=["tabular-classification", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/physics-datasets-69c2d4682d37dfdb77447bd7",
        banner={
            "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e002215/GSFC_20171208_Archive_e002215~medium.jpg",
            "alt": "The gamma-ray sky as seen by NASA's Fermi telescope",
            "credit": "NASA/DOE/Fermi LAT Collaboration",
        },
        related_datasets=[
            "juliensimon/gamma-ray-bursts",
            "juliensimon/supernova-remnants",
            "juliensimon/pulsar-catalog",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "ra_deg", "dec_deg", "glon_deg", "glat_deg", "significance",
                "flux_1000_mev", "energy_flux_100_mev", "variability_index",
                "redshift", "pivot_energy_mev", "power_law_index",
                "log_parabola_index", "log_parabola_beta",
            ],
        )
        p.publish(
            df,
            filename="fermi_4fgl_dr4.parquet",
            min_rows=5000,
            expected_columns=["source_name", "ra_deg", "dec_deg", "significance", "flux_1000_mev"],
            critical_columns=["source_name", "ra_deg", "dec_deg", "significance"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Fermi 4FGL-DR4: {n_total:,} sources",
        )
    print("Done.")


if __name__ == "__main__":
    main()
