#!/usr/bin/env python3
"""Fetch INTEGRAL IBIS 17-Year Hard X-Ray Survey catalog from VizieR and upload to HF.

Source: Krivonos et al. (2022, MNRAS 510, 4796) — 17 years of INTEGRAL IBIS
hard X-ray all-sky survey (17-290 keV).
VizieR catalog: J/MNRAS/510/4796
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/integral-ibis-hard-xray"

# ── Source query ─────────────────────────────────────────────────────
ADQL = 'SELECT * FROM "J/MNRAS/510/4796/table1"'

# ── Column mapping ───────────────────────────────────────────────────
RENAME = {
    "SrcID": "source_id",
    "Name": "source_name",
    "RAJ2000": "ra_deg",
    "DEJ2000": "dec_deg",
    "Flux": "flux_17_60kev",
    "e_Flux": "flux_err_17_60kev",
    "S/N": "snr_17_60kev",
    "Type": "source_type",
    "z": "redshift",
    "Trans": "transient_flag",
    "Ext": "extended_flag",
    "Conf": "confused_flag",
    "Noise": "noisy_flag",
    "Refs": "references",
    "Cntp": "counterpart",
    "Notes": "notes",
    "FluxE2": "flux_17_35kev",
    "FluxE3": "flux_35_80kev",
    "FluxE4": "flux_80_150kev",
    "FluxE5": "flux_150_290kev",
    "FluxE6": "flux_17_80kev",
    "FluxE7": "flux_35_150kev",
    "FluxE8": "flux_80_290kev",
    "FluxE9": "flux_17_290kev",
    "e_FluxE2": "flux_err_17_35kev",
    "e_FluxE3": "flux_err_35_80kev",
    "e_FluxE4": "flux_err_80_150kev",
    "e_FluxE5": "flux_err_150_290kev",
    "e_FluxE6": "flux_err_17_80kev",
    "e_FluxE7": "flux_err_35_150kev",
    "e_FluxE8": "flux_err_80_290kev",
    "e_FluxE9": "flux_err_17_290kev",
    "S/NE2": "snr_17_35kev",
    "S/NE3": "snr_35_80kev",
    "S/NE4": "snr_80_150kev",
    "S/NE5": "snr_150_290kev",
    "S/NE6": "snr_17_80kev",
    "S/NE7": "snr_35_150kev",
    "S/NE8": "snr_80_290kev",
    "S/NE9": "snr_17_290kev",
    "Plate": "plate",
    "SimbadName": "simbad_name",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "source_id": "Sequential catalog number from Krivonos et al. 2022 (MNRAS 510, 4796)",
    "source_name": "Primary source name -- IBIS catalog designation (e.g., 'IGR J17480-2446') or standard name (e.g., 'Cyg X-1')",
    "ra_deg": "Right ascension, ICRS J2000.0 (degrees, 0-360); IBIS angular resolution ~12 arcmin",
    "dec_deg": "Declination, ICRS J2000.0 (degrees, -90 to +90)",
    "flux_17_60kev": "Hard X-ray flux in the primary 17-60 keV band (mCrab); 1 Crab ~ 2.4x10^-8 erg/cm^2/s; catalog detection threshold ~5 mCrab",
    "flux_err_17_60kev": "1-sigma statistical uncertainty on flux_17_60kev (mCrab)",
    "snr_17_60kev": "Detection signal-to-noise ratio in the 17-60 keV band; catalog inclusion threshold >4.7 sigma",
    "source_type": "Astrophysical classification (e.g., 'AGN', 'HMXB', 'LMXB', 'CV', 'PSR', 'SNR', 'Galaxy cluster', 'Unidentified')",
    "redshift": "Spectroscopic redshift for extragalactic sources; null for Galactic sources or sources lacking optical identification",
    "transient_flag": "'T' if the source is a known transient (flux variable by >factor 2); null or blank otherwise",
    "extended_flag": "'E' if the source is spatially extended in the IBIS image (e.g., a galaxy cluster); null otherwise",
    "confused_flag": "'C' if the source is in a confused region with nearby bright sources that may affect flux accuracy; null otherwise",
    "noisy_flag": "'N' if the source lies in a noisy sky region due to proximity to very bright sources or the Galactic center; null otherwise",
    "references": "ADS bibcode(s) for the primary identification or classification reference",
    "counterpart": "Name of the multiwavelength counterpart used for source classification",
    "notes": "Additional remarks on the source (e.g., known aliases, special observational circumstances)",
    "flux_17_35kev": "Flux in the 17-35 keV sub-band (mCrab); null if source not detected in this band",
    "flux_35_80kev": "Flux in the 35-80 keV sub-band (mCrab); null if source not detected in this band",
    "flux_80_150kev": "Flux in the 80-150 keV sub-band (mCrab); null if source not detected in this band",
    "flux_150_290kev": "Flux in the 150-290 keV sub-band (mCrab); null if source not detected in this band",
    "flux_17_80kev": "Flux in the combined 17-80 keV sub-band (mCrab)",
    "flux_35_150kev": "Flux in the combined 35-150 keV sub-band (mCrab)",
    "flux_80_290kev": "Flux in the combined 80-290 keV sub-band (mCrab)",
    "flux_17_290kev": "Total broadband flux over 17-290 keV (mCrab)",
    "flux_err_17_35kev": "1-sigma statistical uncertainty on flux_17_35kev (mCrab)",
    "flux_err_35_80kev": "1-sigma statistical uncertainty on flux_35_80kev (mCrab)",
    "flux_err_80_150kev": "1-sigma statistical uncertainty on flux_80_150kev (mCrab)",
    "flux_err_150_290kev": "1-sigma statistical uncertainty on flux_150_290kev (mCrab)",
    "flux_err_17_80kev": "1-sigma statistical uncertainty on flux_17_80kev (mCrab)",
    "flux_err_35_150kev": "1-sigma statistical uncertainty on flux_35_150kev (mCrab)",
    "flux_err_80_290kev": "1-sigma statistical uncertainty on flux_80_290kev (mCrab)",
    "flux_err_17_290kev": "1-sigma statistical uncertainty on flux_err_17_290kev (mCrab)",
    "snr_17_35kev": "Detection signal-to-noise ratio for the 17-35 keV sub-band",
    "snr_35_80kev": "Detection signal-to-noise ratio for the 35-80 keV sub-band",
    "snr_80_150kev": "Detection signal-to-noise ratio for the 80-150 keV sub-band",
    "snr_150_290kev": "Detection signal-to-noise ratio for the 150-290 keV sub-band",
    "snr_17_80kev": "Detection signal-to-noise ratio for the 17-80 keV sub-band",
    "snr_35_150kev": "Detection signal-to-noise ratio for the 35-150 keV sub-band",
    "snr_80_290kev": "Detection signal-to-noise ratio for the 80-290 keV sub-band",
    "snr_17_290kev": "Detection signal-to-noise ratio for the 17-290 keV sub-band",
    "plate": "INTEGRAL sky plate identifier indicating the mosaic tile used for this detection",
    "simbad_name": "Resolved SIMBAD source name for cross-referencing with the CDS database",
    "has_redshift": "True if redshift is non-null; derived convenience column for filtering extragalactic sources",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Catalog of hard X-ray sources (17-290 keV) from 17 years of observations with the \
IBIS coded-mask telescope aboard ESA's INTEGRAL satellite (Krivonos et al. 2022). \
The deepest all-sky survey in the hard X-ray band from any coded-mask instrument.

The hard X-ray band (above ~15 keV) penetrates the dense columns of gas and dust that \
obscure many astrophysical sources at softer energies. INTEGRAL's coded-mask imaging \
technique allows the IBIS/ISGRI detector to achieve arcminute-level localization across \
the entire sky, revealing populations of heavily absorbed active galactic nuclei (AGN), \
high-mass X-ray binaries, cataclysmic variables, and isolated pulsars that are invisible \
to soft X-ray telescopes.

The multi-band flux decomposition across 8 sub-bands from 17 to 290 keV enables broadband \
spectral characterization without requiring pointed follow-up observations. For extragalactic \
sources, the combination of hard X-ray flux and redshift constrains intrinsic luminosities \
and absorption column densities, key parameters for understanding the obscured AGN population \
that dominates the cosmic X-ray background. Transient flags identify sources such as X-ray \
novae and supergiant fast X-ray transients whose variable emission traces accretion \
instabilities in binary systems.
"""


def main():
    print("Fetching INTEGRAL IBIS hard X-ray survey catalog from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} raw rows")

    # Drop VizieR internal columns
    for col in ["recno"]:
        if col in df.columns:
            df = df.drop(columns=[col])

    # Rename columns
    df = df.rename(columns={k: v for k, v in RENAME.items() if k in df.columns})

    # Strip whitespace from string columns
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].str.strip()

    # Coerce integer ID
    if "source_id" in df.columns:
        df["source_id"] = pd.to_numeric(df["source_id"], errors="coerce").astype("Int32")

    # Derived columns
    df["has_redshift"] = df["redshift"].notna() if "redshift" in df.columns else False

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Sort by S/N descending (most significant detections first)
    df = df.sort_values("snr_17_60kev", ascending=False).reset_index(drop=True)

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_with_z = int(df["has_redshift"].sum())
    flux_median = df["flux_17_60kev"].median()
    snr_max = df["snr_17_60kev"].max()
    n_types = df["source_type"].nunique()

    quick_stats = f"""\
- **{n_total:,}** hard X-ray sources across **{n_types}** source types
- **{n_with_z:,}** sources with measured redshift ({n_with_z / n_total * 100:.1f}%)
- Median flux (17-60 keV): **{flux_median:.2f}** mCrab
- Peak S/N: **{snr_max:.1f}**
- 8 energy sub-bands spanning 17-290 keV"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/integral-ibis-hard-xray", split="train")
df = ds.to_pandas()

# Flux distribution
import matplotlib.pyplot as plt
df["flux_17_60kev"].clip(upper=100).hist(bins=100, log=True)
plt.xlabel("Flux 17-60 keV (mCrab)")
plt.ylabel("Count")
plt.title("INTEGRAL IBIS Hard X-Ray Flux Distribution")
plt.show()

# Source type breakdown
df["source_type"].value_counts().head(10).plot.barh()
plt.xlabel("Count")
plt.title("Top 10 Source Types")
plt.tight_layout()
plt.show()

# Sky map
plt.scatter(df["ra_deg"], df["dec_deg"], s=2, c=df["snr_17_60kev"].clip(upper=50), cmap="hot")
plt.colorbar(label="S/N")
plt.xlabel("RA (deg)")
plt.ylabel("Dec (deg)")
plt.title("INTEGRAL IBIS All-Sky Hard X-Ray Sources")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="INTEGRAL IBIS 17-Year Hard X-Ray Survey",
        description=DESCRIPTION,
        tags=["space", "x-ray", "integral", "esa", "hard-x-ray", "astronomy",
              "physics", "open-data", "tabular-data", "parquet"],
        source_url="https://vizier.cds.unistra.fr/viz-bin/VizieR-3?-source=J/MNRAS/510/4796",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/physics-datasets-69c2d4682d37dfdb77447bd7",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA03519/PIA03519~small.jpg",
            "alt": "Cassiopeia A supernova remnant in X-ray, optical, and infrared light",
            "credit": "NASA/JPL-Caltech/STScI/CXC/SAO",
        },
        related_datasets=[
            "juliensimon/swift-bat-hard-xray-survey",
            "juliensimon/chandra-x-ray-sources",
            "juliensimon/erosita-erass1-xray",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "ra_deg", "dec_deg", "redshift",
                "flux_17_60kev", "flux_err_17_60kev", "snr_17_60kev",
                "flux_17_35kev", "flux_35_80kev", "flux_80_150kev", "flux_150_290kev",
                "flux_17_80kev", "flux_35_150kev", "flux_80_290kev", "flux_17_290kev",
                "flux_err_17_35kev", "flux_err_35_80kev", "flux_err_80_150kev",
                "flux_err_150_290kev", "flux_err_17_80kev", "flux_err_35_150kev",
                "flux_err_80_290kev", "flux_err_17_290kev",
                "snr_17_35kev", "snr_35_80kev", "snr_80_150kev", "snr_150_290kev",
                "snr_17_80kev", "snr_35_150kev", "snr_80_290kev", "snr_17_290kev",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="integral_ibis_hard_xray.parquet",
            min_rows=800,
            expected_columns=[
                "source_id", "source_name", "ra_deg", "dec_deg",
                "flux_17_60kev", "snr_17_60kev", "source_type",
            ],
            critical_columns=["source_name", "ra_deg", "dec_deg", "flux_17_60kev", "snr_17_60kev"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update INTEGRAL IBIS hard X-ray survey: {n_total:,} sources",
        )
    print("Done.")


if __name__ == "__main__":
    main()
