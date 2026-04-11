#!/usr/bin/env python3
"""Fetch TeVCat (TeV gamma-ray source catalog) from HEASARC and upload to HF.

Source: Wakely & Horan, TeVCat online catalog
HEASARC table: tevcat
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import heasarc_query

HF_REPO = "juliensimon/tevcat-tev-gamma-ray"

ADQL = "SELECT * FROM tevcat"

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "source_name": "Canonical TeVCat source name (e.g. 'Crab Nebula', 'Mkn 421', 'HESS J1745-290'); primary identifier used in the VHE community",
    "ra": "ICRS J2000.0 right ascension in degrees (0-360)",
    "dec": "ICRS J2000.0 declination in degrees (-90 to +90)",
    "lii": "Galactic longitude in degrees (0-360)",
    "bii": "Galactic latitude in degrees (-90 to +90); Galactic sources cluster near |b| < 5 deg",
    "source_type": "Astrophysical classification of the TeV source (e.g. 'PWN' = pulsar wind nebula, 'HBL' = high-frequency-peaked BL Lac, 'SNR' = supernova remnant, 'UNID' = unidentified)",
    "flux": "Integral flux above energy threshold in Crab units or photons/cm^2/s; null for sources with only detection significance reported",
    "flux_error": "1-sigma uncertainty on flux; null if flux is null",
    "distance": "Distance to the source in kpc (Galactic) or Mpc (extragalactic); null for unidentified sources or where distance is unknown",
    "redshift": "Redshift of the source; primarily relevant for extragalactic sources (blazars, radio galaxies); null for Galactic objects",
    "discovery_date": "Year or date when the source was first detected at TeV energies; null for some legacy sources",
    "telescope": "Telescope or observatory that discovered or confirmed the TeV detection (e.g. 'H.E.S.S.', 'MAGIC', 'VERITAS', 'HAWC', 'LHAASO')",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Catalog of astronomical sources detected at very high energies (>50 GeV) by \
ground-based gamma-ray telescopes such as H.E.S.S., MAGIC, and VERITAS. TeVCat \
is the reference catalog for the ground-based VHE gamma-ray community, sourced \
from NASA HEASARC.

Very-high-energy (VHE) gamma-ray astronomy probes the most extreme environments \
in the universe: supernova remnants, pulsar wind nebulae, active galactic nuclei, \
and gamma-ray binaries. Ground-based VHE gamma-ray astronomy relies on detecting \
the Cherenkov light produced when gamma rays interact with the atmosphere, creating \
cascades of relativistic particles. Imaging Atmospheric Cherenkov Telescopes (IACTs) \
achieve angular resolutions of a few arcminutes and energy thresholds as low as ~30 GeV, \
while water Cherenkov detectors like HAWC and LHAASO provide continuous wide-field \
monitoring at higher energies.

TeV gamma rays are produced by the highest-energy particles in the universe, either \
through inverse-Compton scattering of ambient photon fields by ultra-relativistic \
electrons or through the decay of neutral pions created in hadronic interactions. \
Distinguishing between these leptonic and hadronic scenarios is a central goal of \
VHE astrophysics, as hadronic emission would identify the long-sought sites of \
cosmic ray acceleration. The redshifts of extragalactic TeV sources are particularly \
valuable because TeV photons are absorbed by pair production on the extragalactic \
background light (EBL), enabling independent constraints on the EBL density.
"""


def main():
    print("Fetching TeVCat catalog from HEASARC...")
    df = heasarc_query("tevcat", ADQL)
    print(f"  {len(df):,} TeV sources fetched")

    # Rename columns to snake_case (normalize any oddities)
    rename = {}
    for col in df.columns:
        clean = col.strip().lower().replace(" ", "_").replace("-", "_")
        if clean != col:
            rename[col] = clean
    if rename:
        df = df.rename(columns=rename)

    # Clean empty strings to NaN for string columns
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip().replace(
            {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
        )

    # Sort by source name
    if "source_name" in df.columns:
        df = df.sort_values("source_name").reset_index(drop=True)
    elif "name" in df.columns:
        df = df.sort_values("name").reset_index(drop=True)

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_with_redshift = int(df["redshift"].notna().sum()) if "redshift" in df.columns else 0
    n_with_flux = int(df["flux"].notna().sum()) if "flux" in df.columns else 0

    type_summary = ""
    if "source_type" in df.columns:
        top_types = df["source_type"].value_counts().head(6)
        type_lines = [f"- **{count:,}** {name}" for name, count in top_types.items()]
        type_summary = "\n".join(type_lines)

    quick_stats = f"""\
- **{n_total:,}** TeV gamma-ray sources
- **{n_with_redshift:,}** with measured redshift
- **{n_with_flux:,}** with flux measurements
- Top source types:
{type_summary}"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/tevcat-tev-gamma-ray", split="train")
df = ds.to_pandas()

print(f"{len(df):,} TeV gamma-ray sources")
print(df["source_type"].value_counts())

# Sky map in Aitoff projection
import matplotlib.pyplot as plt
import numpy as np
fig, ax = plt.subplots(subplot_kw={"projection": "aitoff"})
ra_rad = np.deg2rad(df["ra"].dropna() - 180)
dec_rad = np.deg2rad(df["dec"].dropna())
ax.scatter(ra_rad, dec_rad, s=10, alpha=0.7, c="crimson")
ax.set_title("TeV Gamma-Ray Sky")
ax.grid(True)
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="TeVCat -- TeV Gamma-Ray Source Catalog",
        description=DESCRIPTION,
        tags=["space", "gamma-ray", "tev", "astronomy", "physics",
              "open-data", "tabular-data", "parquet"],
        source_url="https://heasarc.gsfc.nasa.gov/W3Browse/all/tevcat.html",
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
            numeric=["ra", "dec", "lii", "bii", "flux", "flux_error",
                     "distance", "redshift"],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="tevcat.parquet",
            min_rows=200,
            expected_columns=["ra", "dec"],
            critical_columns=["ra", "dec"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update TeVCat: {n_total:,} TeV gamma-ray sources",
        )
    print("Done.")


if __name__ == "__main__":
    main()
