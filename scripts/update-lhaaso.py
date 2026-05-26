#!/usr/bin/env python3
"""Fetch 1LHAASO gamma-ray source catalog from VizieR and upload to HF.

Source: Cao et al. (2024, ApJS 271, 25) — First LHAASO catalog of
gamma-ray sources from KM2A and WCDA detectors.
VizieR catalog: J/ApJS/271/25
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/lhaaso-gamma-ray-sources"

# ── Source query ─────────────────────────────────────────────────────
ADQL = 'SELECT * FROM "J/ApJS/271/25/catalog"'

# ── Column mapping ───────────────────────────────────────────────────
RENAME = {
    "1LHAASO": "source_name",
    "f_1LHAASO": "source_name_flag",
    "Comp": "component",
    "f_Comp": "component_flag",
    "RAJ2000": "ra_deg",
    "DEJ2000": "dec_deg",
    "RA_ICRS": "ra_deg",
    "DE_ICRS": "dec_deg",
    "RAICRS": "ra_deg",
    "DEICRS": "dec_deg",
    "ePos": "pos_error_deg",
    "r39": "extension_deg",
    "e_r39": "extension_error_deg",
    "TS": "significance",
    "N0": "diff_flux_norm",
    "e_N0": "diff_flux_norm_error",
    "Index": "spectral_index",
    "e_Index": "spectral_index_error",
    "TS100": "ts_above_100tev",
    "Assoc": "association",
    "f_Assoc": "association_flag",
    "Sep": "association_separation_deg",
    "SimbadName": "simbad_name",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "source_name": "1LHAASO catalog designation in format '1LHAASO JHHMMSS.s+DDMMSS'; primary identifier for referencing sources in the first LHAASO catalog",
    "source_name_flag": "Flag qualifying the source name (e.g., notes on naming conventions or duplicates); null for most entries",
    "component": "Detector component used for this catalog entry: 'KM2A' (sensitive above ~25 TeV, up to PeV) or 'WCDA' (sensitive 1-25 TeV); a source may have separate entries for each detector",
    "component_flag": "Flag on the component entry indicating special circumstances for the detection; null for standard entries",
    "ra_deg": "Right ascension, ICRS J2000.0 (degrees, 0-360); LHAASO sources are primarily Galactic, concentrated along the Galactic plane",
    "dec_deg": "Declination, ICRS J2000.0 (degrees, -90 to +90); LHAASO sky coverage extends up to ~80 deg N declination",
    "pos_error_deg": "1-sigma statistical positional uncertainty (degrees); typically 0.05-0.3 deg depending on significance and source extension",
    "extension_deg": "Gaussian extension radius of the source (degrees); null or 0 for point-like sources; LHAASO detects extensions of 0.1-2 deg for resolved sources",
    "extension_error_deg": "1-sigma uncertainty on the extension measurement (degrees); null for point-like sources",
    "significance": "Detection test statistic (TS); related to significance by TS ~ sigma^2 for a 1 d.o.f. fit; catalog inclusion threshold >7 sigma equivalent",
    "diff_flux_norm": "Differential flux normalization N0 at the reference energy (photons cm^-2 s^-1 TeV^-1); the spectral model is dN/dE = N0 * (E/E_ref)^(-Index)",
    "diff_flux_norm_error": "1-sigma statistical uncertainty on the flux normalization N0 (same units)",
    "spectral_index": "Power-law photon spectral index Gamma (dN/dE proportional to E^-Gamma); LHAASO UHE sources typically Gamma ~ 2.0-3.5; harder spectra suggest hadronic PeVatron origin",
    "spectral_index_error": "1-sigma statistical uncertainty on spectral_index",
    "ts_above_100tev": "Test statistic for emission above 100 TeV; non-null positive values indicate UHE detection, directly relevant for identifying PeVatron candidates",
    "association": "Name of the best multi-wavelength counterpart (SNR, PWN, molecular cloud, stellar cluster, etc.); null if no confident association exists",
    "association_flag": "Flag on the association indicating confidence level or ambiguity in the identification; null for clean associations",
    "association_separation_deg": "Angular separation between the LHAASO source centroid and the associated counterpart (degrees); smaller separations indicate more confident associations",
    "simbad_name": "Resolved SIMBAD name for the associated counterpart, for cross-referencing with the CDS database",
    "is_extended": "True if extension_deg is non-null and >0, indicating a spatially resolved source; derived column",
    "has_association": "True if association is non-null, indicating a known multi-wavelength counterpart; derived column",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
First catalog of gamma-ray sources from LHAASO (Large High Altitude Air Shower Observatory), \
the most sensitive ultra-high-energy (UHE) gamma-ray observatory in the Northern Hemisphere. \
Located at 4,410 m altitude in Sichuan, China, LHAASO detects gamma-ray sources at very-high-energy \
(VHE, >0.1 TeV) and ultra-high-energy (>100 TeV) using two complementary detector sub-systems.

LHAASO has fundamentally reshaped ultra-high-energy gamma-ray astronomy by demonstrating that the \
Milky Way contains numerous sources capable of accelerating particles beyond 1 PeV (10^15 eV), \
the so-called "PeVatron" threshold. Before LHAASO, only a handful of sources had been detected \
above 100 TeV; the 1LHAASO catalog reveals a rich population of UHE emitters concentrated along \
the Galactic plane, many associated with pulsar wind nebulae, supernova remnants, and massive \
stellar clusters. These detections directly constrain the origin of Galactic cosmic rays, one of \
the oldest unsolved problems in astrophysics.

The two detector sub-systems provide complementary energy coverage: WCDA (Water Cherenkov Detector \
Array) is sensitive from ~1 to 25 TeV with a large effective area for survey work, while KM2A (the \
square-kilometer particle detector array) achieves unprecedented sensitivity above 25 TeV and \
extends to the PeV regime. The spectral index measured for each source encodes the energy \
distribution of the parent particle population, and the presence or absence of spectral cutoffs \
above 100 TeV distinguishes hadronic PeVatrons from leptonic emitters limited by synchrotron and \
inverse-Compton cooling.
"""


def main():
    print("Fetching 1LHAASO gamma-ray source catalog from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} raw rows")
    print(f"  Raw columns: {list(df.columns)}")

    # Drop VizieR internal columns
    for col in ["recno"]:
        if col in df.columns:
            df = df.drop(columns=[col])

    # Rename columns (guard for variants)
    df = df.rename(columns={k: v for k, v in RENAME.items() if k in df.columns})

    # Clean string columns
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip()
        df[col] = df[col].replace({"nan": None, "": None, "None": None})

    # Derived columns
    if "extension_deg" in df.columns:
        df["is_extended"] = df["extension_deg"].notna() & (df["extension_deg"] > 0)
    if "association" in df.columns:
        df["has_association"] = df["association"].notna()

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Sort by source name
    if "source_name" in df.columns:
        df = df.sort_values("source_name").reset_index(drop=True)
    elif "ra_deg" in df.columns:
        df = df.sort_values("ra_deg").reset_index(drop=True)

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_extended = int(df["is_extended"].sum()) if "is_extended" in df.columns else 0
    n_associated = int(df["has_association"].sum()) if "has_association" in df.columns else 0
    unique_sources = df["source_name"].nunique() if "source_name" in df.columns else n_total

    # Component breakdown
    n_km2a = len(df[df["component"] == "KM2A"]) if "component" in df.columns else 0
    n_wcda = len(df[df["component"] == "WCDA"]) if "component" in df.columns else 0

    # UHE stats
    n_uhe = 0
    if "ts_above_100tev" in df.columns:
        n_uhe = int((df["ts_above_100tev"].notna() & (df["ts_above_100tev"] > 0)).sum())

    quick_stats = f"""\
- **{n_total}** catalog entries covering **{unique_sources}** unique sources
- **{n_km2a}** KM2A entries (>25 TeV), **{n_wcda}** WCDA entries (1-25 TeV)
- **{n_uhe}** sources detected above 100 TeV (PeVatron candidates)
- **{n_extended}** spatially extended sources
- **{n_associated}** with known multi-wavelength associations"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/lhaaso-gamma-ray-sources", split="train")
df = ds.to_pandas()

# Sources by detector component
print(df["component"].value_counts())

# Spectral index distribution
import matplotlib.pyplot as plt
df["spectral_index"].dropna().hist(bins=30)
plt.xlabel("Spectral Index")
plt.ylabel("Count")
plt.title("1LHAASO Spectral Index Distribution")
plt.show()

# Sky map colored by significance
plt.scatter(df["ra_deg"], df["dec_deg"], c=df["significance"], cmap="hot", s=20)
plt.colorbar(label="Test Statistic")
plt.xlabel("RA (deg)")
plt.ylabel("Dec (deg)")
plt.title("1LHAASO Sources on the Sky")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="1LHAASO Gamma-Ray Source Catalog",
        description=DESCRIPTION,
        tags=["space", "gamma-ray", "lhaaso", "tev", "uhe", "astronomy",
              "physics", "open-data", "tabular-data", "parquet"],
        source_url="https://vizier.cds.unistra.fr/viz-bin/VizieR-3?-source=J/ApJS/271/25",
        license="other",
        license_name="vizier-scientific-use",
        license_link="https://cds.unistra.fr/vizier-org/licences_vizier.html",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/physics-datasets-69c2d4682d37dfdb77447bd7",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA03519/PIA03519~small.jpg",
            "alt": "Cassiopeia A supernova remnant in X-ray, optical, and infrared light",
            "credit": "NASA/JPL-Caltech/STScI/CXC/SAO",
        },
        related_datasets=[
            "juliensimon/tevcat-tev-gamma-ray",
            "juliensimon/hawc-tev-gamma-ray",
            "juliensimon/fermi-4fgl-dr4",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "ra_deg", "dec_deg",
                "pos_error_deg",
                "extension_deg", "extension_error_deg",
                "significance",
                "diff_flux_norm", "diff_flux_norm_error",
                "spectral_index", "spectral_index_error",
                "ts_above_100tev",
                "association_separation_deg",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="lhaaso_gamma_ray_sources.parquet",
            min_rows=50,
            expected_columns=["source_name", "ra_deg", "dec_deg", "significance"],
            critical_columns=["source_name", "ra_deg", "dec_deg"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update 1LHAASO gamma-ray source catalog: {n_total} entries",
        )
    print("Done.")


if __name__ == "__main__":
    main()
