#!/usr/bin/env python3
"""Fetch 3HWC HAWC TeV gamma-ray source catalog from VizieR and upload to HF.

Source: Albert A. et al. (2020, ApJ, 905, 76) — Third HAWC Catalog
VizieR catalog: J/ApJ/905/76
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/hawc-tev-gamma-ray"

# ── Source query ─────────────────────────────────────────────────────
ADQL = 'SELECT * FROM "J/ApJ/905/76/sources"'

# ── Column mapping ───────────────────────────────────────────────────
RENAME = {
    "3HWC": "source_name",
    "f_3HWC": "source_name_flag",
    "RAJ2000": "ra_deg",
    "DEJ2000": "dec_deg",
    "GLON": "glon_deg",
    "GLAT": "glat_deg",
    "ePos": "pos_error_deg",
    "rs": "search_radius_deg",
    "TS": "test_statistic",
    "Sep": "separation_deg",
    "f_TeVCat": "tevcat_flag",
    "TeVCat": "tevcat_name",
    "n_TeVCat": "tevcat_note",
    "F7": "flux_7tev",
    "E_F7": "flux_7tev_err_upper",
    "e_F7": "flux_7tev_err_lower",
    "Ind": "spectral_index",
    "E_Ind": "spectral_index_err_upper",
    "e_Ind": "spectral_index_err_lower",
    "F7sys-u": "flux_7tev_sys_upper",
    "F7sys-l": "flux_7tev_sys_lower",
    "Indsys-u": "spectral_index_sys_upper",
    "Indsys-l": "spectral_index_sys_lower",
    "ER-min": "energy_range_min_tev",
    "ER-max": "energy_range_max_tev",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "source_name": "3HWC catalog designation in format '3HWC JHHMM+DDd' (e.g., 3HWC J0534+220 = Crab Nebula)",
    "source_name_flag": "Flag indicating naming notes (e.g., 'e' = extended source fit, 'c' = confused region)",
    "ra_deg": "Right ascension, ICRS J2000.0 (degrees, 0-360); HAWC angular resolution ~0.1-0.5 deg depending on energy",
    "dec_deg": "Declination, ICRS J2000.0 (degrees); HAWC sky coverage approximately -26 to +64 deg",
    "glon_deg": "Galactic longitude (degrees, 0-360)",
    "glat_deg": "Galactic latitude (degrees, -90 to +90)",
    "pos_error_deg": "1-sigma statistical positional uncertainty (degrees); typically 0.05-0.3 deg",
    "search_radius_deg": "Radius of the spatial template used in the likelihood fit (degrees); larger for extended sources",
    "test_statistic": "Detection test statistic TS = -2 ln(L_null/L_src); catalog threshold TS > 25 (equivalent to ~5 sigma)",
    "separation_deg": "Angular separation to the nearest TeVCat source (degrees); used for cross-match assessment",
    "tevcat_flag": "TeVCat association status: 'Y' if within the search radius of a known TeVCat source, 'N' otherwise",
    "tevcat_name": "Name of the associated TeVCat source; null if no TeVCat counterpart within search radius",
    "tevcat_note": "Notes on the TeVCat association (e.g., 'extended', 'confused', 'new'); null if no association",
    "flux_7tev": "Differential photon flux at 7 TeV in units of 10^-15 cm^-2 s^-1 TeV^-1; 7 TeV is the decorrelation energy for the 3HWC fit",
    "flux_7tev_err_upper": "Upper 1-sigma statistical uncertainty on flux_7tev (same units: 10^-15 cm^-2 s^-1 TeV^-1)",
    "flux_7tev_err_lower": "Lower 1-sigma statistical uncertainty on flux_7tev (same units: 10^-15 cm^-2 s^-1 TeV^-1)",
    "spectral_index": "Power-law photon spectral index Gamma (dN/dE proportional to E^-Gamma); typical range 2.0-3.5 for TeV sources",
    "spectral_index_err_upper": "Upper 1-sigma statistical uncertainty on spectral_index",
    "spectral_index_err_lower": "Lower 1-sigma statistical uncertainty on spectral_index",
    "flux_7tev_sys_upper": "Upper systematic uncertainty on flux_7tev from detector calibration and background model (10^-15 cm^-2 s^-1 TeV^-1)",
    "flux_7tev_sys_lower": "Lower systematic uncertainty on flux_7tev (10^-15 cm^-2 s^-1 TeV^-1)",
    "spectral_index_sys_upper": "Upper systematic uncertainty on spectral_index from detector and analysis systematics",
    "spectral_index_sys_lower": "Lower systematic uncertainty on spectral_index",
    "energy_range_min_tev": "Lower bound of the energy range used in the spectral fit (TeV)",
    "energy_range_max_tev": "Upper bound of the energy range used in the spectral fit (TeV)",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
The Third HAWC Catalog (3HWC) of Very-High-Energy Gamma-Ray Sources, detected by the \
High Altitude Water Cherenkov (HAWC) Observatory over 1,523 days of observation. HAWC \
surveys two-thirds of the sky daily at TeV energies.

The 3HWC catalog represents the most sensitive survey of the TeV gamma-ray sky by HAWC. \
Sources are identified as statistically significant excesses above the cosmic-ray background. \
The catalog includes source positions, test statistics, differential fluxes at 7 TeV, and \
spectral indices assuming a simple power-law model.

HAWC operates at 4,100 m altitude on the Sierra Negra volcano in Mexico, using 300 water \
Cherenkov detectors to sample the particle cascades initiated by gamma rays and cosmic rays \
in the atmosphere. Unlike pointed Cherenkov telescopes, HAWC observes continuously with a \
~2 steradian instantaneous field of view, making it uniquely sensitive to extended emission \
regions and transient phenomena at TeV energies, complementing the deeper but narrower \
observations of IACTs like H.E.S.S., MAGIC, and VERITAS.

The Galactic plane dominates the catalog, with detections tracing pulsar wind nebulae, \
supernova remnants, and unidentified sources that may represent new classes of TeV emitters. \
TeVCat cross-matches included in the catalog facilitate multi-instrument spectral energy \
distribution construction, critical for distinguishing leptonic (inverse-Compton) from \
hadronic (pion-decay) emission mechanisms.
"""


def main():
    print("Fetching 3HWC HAWC TeV gamma-ray catalog from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} raw rows")

    # Drop VizieR internal columns
    for col in ["recno", "Seq", "H", "N", "_Simbad_"]:
        if col in df.columns:
            df = df.drop(columns=[col])

    df = df.rename(columns={k: v for k, v in RENAME.items() if k in df.columns})

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Sort by source name
    df = df.sort_values("source_name").reset_index(drop=True)

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    ts_median = df["test_statistic"].median()
    ra_min, ra_max = df["ra_deg"].min(), df["ra_deg"].max()
    dec_min, dec_max = df["dec_deg"].min(), df["dec_deg"].max()
    n_with_tevcat = int(df["tevcat_name"].notna().sum())

    quick_stats = f"""\
- **{n_total}** TeV gamma-ray sources
- **{n_with_tevcat}** sources with TeVCat associations
- Median test statistic: **{ts_median:.1f}**
- Sky coverage: RA {ra_min:.1f}--{ra_max:.1f} deg, Dec {dec_min:.1f}--{dec_max:.1f} deg"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/hawc-tev-gamma-ray", split="train")
df = ds.to_pandas()

# Most significant detections
top = df.nlargest(10, "test_statistic")[["source_name", "test_statistic", "flux_7tev"]]
print(top.to_string(index=False))

# Sky map in galactic coordinates
import matplotlib.pyplot as plt
plt.figure(figsize=(12, 5))
plt.scatter(df["glon_deg"], df["glat_deg"], s=df["test_statistic"] / 5, alpha=0.6)
plt.xlabel("Galactic Longitude (deg)")
plt.ylabel("Galactic Latitude (deg)")
plt.title("3HWC Sources in Galactic Coordinates")
plt.gca().invert_xaxis()
plt.show()

# Spectral index distribution
df["spectral_index"].hist(bins=20)
plt.xlabel("Spectral Index")
plt.ylabel("Count")
plt.title("3HWC Spectral Index Distribution")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="3HWC HAWC TeV Gamma-Ray Source Catalog",
        description=DESCRIPTION,
        tags=["space", "gamma-ray", "hawc", "tev", "astronomy", "physics",
              "open-data", "tabular-data", "parquet"],
        source_url="https://vizier.cds.unistra.fr/viz-bin/VizieR?-source=J/ApJ/905/76",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/physics-datasets-69c2d4682d37dfdb77447bd7",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA03519/PIA03519~small.jpg",
            "alt": "Cassiopeia A supernova remnant in X-ray, optical, and infrared light",
            "credit": "NASA/JPL-Caltech/STScI/CXC/SAO",
        },
        related_datasets=[
            "juliensimon/fermi-4fgl-dr4",
            "juliensimon/tevcat-tev-gamma-ray",
            "juliensimon/lhaaso-gamma-ray-sources",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "ra_deg", "dec_deg", "glon_deg", "glat_deg", "pos_error_deg",
                "search_radius_deg", "test_statistic", "separation_deg",
                "flux_7tev", "flux_7tev_err_upper", "flux_7tev_err_lower",
                "spectral_index", "spectral_index_err_upper", "spectral_index_err_lower",
                "flux_7tev_sys_upper", "flux_7tev_sys_lower",
                "spectral_index_sys_upper", "spectral_index_sys_lower",
                "energy_range_min_tev", "energy_range_max_tev",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="hawc_tev_gamma_ray.parquet",
            min_rows=40,
            expected_columns=["source_name", "ra_deg", "dec_deg", "flux_7tev", "spectral_index"],
            critical_columns=["source_name", "ra_deg", "dec_deg", "flux_7tev"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update 3HWC HAWC catalog: {n_total} sources",
        )
    print("Done.")


if __name__ == "__main__":
    main()
