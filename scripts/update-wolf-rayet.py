#!/usr/bin/env python3
"""Fetch Galactic Wolf-Rayet Stars catalog from VizieR and upload to HF.

Source: Rate & Crowther (2020, MNRAS 493, 1512) — Gaia DR2 distances
and properties for 383 Galactic Wolf-Rayet stars.
VizieR catalog: J/MNRAS/493/1512
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/wolf-rayet-stars"

# ── Source queries ───────────────────────────────────────────────────
ADQL_MAIN = 'SELECT * FROM "J/MNRAS/493/1512/table1"'
ADQL_KMAG = 'SELECT * FROM "J/MNRAS/493/1512/table6"'

# ── Column mapping ───────────────────────────────────────────────────
RENAME = {
    "WR": "wr_number",
    "f_WR": "wr_flag",
    "SpType": "spectral_type",
    "Name": "name",
    "RA_ICRS": "ra_deg",
    "DE_ICRS": "dec_deg",
    "plx": "parallax_mas",
    "e_plx": "parallax_error_mas",
    "Dist": "distance_kpc",
    "E_Dist": "distance_upper_error_kpc",
    "e_Dist": "distance_lower_error_kpc",
    "z": "galactic_height_pc",
    "E_z": "galactic_height_upper_error_pc",
    "e_z": "galactic_height_lower_error_pc",
    "Gmag": "gaia_g_mag",
    "BP-RP": "gaia_bp_rp",
    "Excess": "astrometric_excess_noise",
    "logL": "log_luminosity",
    "flag": "error_flag",
    "Ksmag": "ks_mag",
    "J-Ks": "j_ks_color",
    "H-Ks": "h_ks_color",
    "AKs": "ks_extinction",
    "KsMAGWR": "ks_abs_mag",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "wr_number": "Standard WR catalog number (e.g. 'WR 1', 'WR 140') from the VIIth Catalog of Galactic Wolf-Rayet Stars; primary identifier used throughout the literature",
    "wr_flag": "Flag qualifying the WR designation (e.g. 'a' for additions/updates after the main catalog); null for most entries",
    "spectral_type": "Full WR spectral classification (e.g. 'WN4b', 'WC7+O5-8', 'WO2'); WN = nitrogen-sequence, WC = carbon-sequence, WO = oxygen-sequence; '+' indicates a spectroscopic binary companion",
    "wr_subtype": "Broad WR sequence derived from spectral_type: WN (exposing CNO-cycle products, WN2-WN11), WC (exposing He-burning products, WC4-WC9), WO (most evolved, WO1-WO4); null if spectral type is ambiguous",
    "is_binary": "True if the spectral type contains '+', indicating a detected companion; WR+O binaries are important progenitors of compact object mergers",
    "name": "Alternative designation (usually HD number or other catalog ID); null for stars without a common alternative name",
    "ra_deg": "Right ascension, ICRS at Gaia DR2 reference epoch Ep=2015.5, in decimal degrees (0-360)",
    "dec_deg": "Declination, ICRS at Ep=2015.5, in decimal degrees (-90 to +90)",
    "parallax_mas": "Zero-point corrected Gaia DR2 parallax in milliarcseconds; many WR stars have negative or zero parallax due to faintness/crowding — distances are derived via a Bayesian method",
    "parallax_error_mas": "1-sigma uncertainty on Gaia DR2 parallax (mas)",
    "distance_kpc": "Distance from the Sun in kpc, derived from Gaia DR2 parallax using a Bayesian prior; null for stars where Gaia astrometry is too poor; most Galactic WR stars lie within 10 kpc",
    "distance_upper_error_kpc": "Asymmetric upper 1-sigma uncertainty on distance (kpc); distances are often asymmetrically uncertain because negative parallaxes give poorly constrained distances",
    "distance_lower_error_kpc": "Asymmetric lower 1-sigma uncertainty on distance (kpc)",
    "galactic_height_pc": "Perpendicular distance from the Galactic mid-plane in pc, calculated from distance and Galactic latitude; WR stars trace the thin disk, typically |z| < 200 pc",
    "galactic_height_upper_error_pc": "Upper 1-sigma uncertainty on Galactic height (pc)",
    "galactic_height_lower_error_pc": "Lower 1-sigma uncertainty on Galactic height (pc)",
    "gaia_g_mag": "Gaia DR2 G-band (330-1050 nm) apparent magnitude; WR stars typically G = 8-18 mag; heavily reddened WR stars may be absent from Gaia",
    "gaia_bp_rp": "Gaia DR2 BP-RP colour index; WR stars are hot (blue) but often appear red due to interstellar extinction and emission lines; null where BP/RP photometry is unavailable",
    "astrometric_excess_noise": "Gaia DR2 astrometric excess noise in mas; elevated values indicate binarity, source confusion, or poor astrometric solution",
    "log_luminosity": "Log bolometric luminosity in solar units log(L/L_sun); WR stars: 10^5-10^6 L_sun (log L ~ 5.0-6.0); null for stars without a reliable distance or spectroscopic analysis",
    "error_flag": "Quality or error flag from Rate & Crowther (2020) indicating issues with the spectral classification, photometry, or distance; null for clean entries",
    "ks_mag": "2MASS Ks-band (2.17 um) apparent magnitude; near-infrared photometry less affected by interstellar extinction than optical",
    "j_ks_color": "2MASS J-Ks colour index; traces near-infrared excess from free-free emission in WR winds; WC stars show strong IR excess",
    "h_ks_color": "2MASS H-Ks colour index; additional near-infrared wind emission diagnostic",
    "ks_extinction": "Ks-band extinction A_Ks in magnitudes, derived from comparison of observed and intrinsic colours; used to compute absolute magnitudes",
    "ks_abs_mag": "Absolute Ks-band magnitude of the WR star, corrected for extinction; useful for luminosity comparisons independent of optical reddening; null where distance or extinction is unknown",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Catalog of Galactic Wolf-Rayet stars — massive evolved stars with powerful stellar \
winds and broad emission lines. Wolf-Rayet stars represent a brief but spectacular \
late stage in the lives of the most massive stars (>25 solar masses), just before \
they explode as supernovae.

Wolf-Rayet (WR) stars are among the hottest and most luminous stars known, with surface \
temperatures of 30,000-200,000 K and luminosities up to a million times the Sun. Their \
spectra are dominated by broad emission lines from helium, nitrogen (WN subtype), carbon \
(WC subtype), or oxygen (WO subtype), produced by their extreme stellar winds losing mass \
at rates of 10^-5 solar masses per year.

This catalog is based on Rate & Crowther (2020), which combined the most complete census of \
Galactic WR stars with Gaia DR2 parallaxes to derive distances, luminosities, and spatial \
distribution. The dataset includes astrometric positions, spectral classifications, Gaia and \
infrared photometry, and distance estimates.

Wolf-Rayet stars represent a fleeting but critical phase in massive star evolution. Stars \
born with initial masses above roughly 25 solar masses shed their hydrogen envelopes through \
powerful radiation-driven winds and episodic mass loss, exposing first the products of \
CNO-cycle hydrogen burning (nitrogen-rich WN phase) and then the products of helium burning \
(carbon- and oxygen-rich WC/WO phases). Their powerful winds inject enormous mechanical \
energy and chemically enriched material into the surrounding interstellar medium, sculpting \
ring nebulae and contributing to Galactic chemical evolution.
"""


def main():
    print("Fetching Galactic Wolf-Rayet stars from VizieR...")
    df = vizier_query(ADQL_MAIN)
    print(f"  {len(df):,} Wolf-Rayet stars (main table)")

    df_kmag = vizier_query(ADQL_KMAG)
    print(f"  {len(df_kmag):,} stars with Ks-band photometry")

    # Merge Ks magnitudes onto main table
    kmag_cols = ["WR", "Ksmag", "J-Ks", "H-Ks", "AKs", "KsMAGWR"]
    kmag_cols = [col for col in kmag_cols if col in df_kmag.columns]
    if "WR" in df_kmag.columns:
        df_kmag_sub = df_kmag[kmag_cols].copy()
        df_kmag_sub["WR"] = df_kmag_sub["WR"].astype(str).str.strip()
        df["WR"] = df["WR"].astype(str).str.strip()
        df = df.merge(df_kmag_sub, on="WR", how="left")

    # Drop VizieR internal columns
    for col in ["recno", "More", "SimbadName"]:
        if col in df.columns:
            df = df.drop(columns=[col])

    df = df.rename(columns={k: v for k, v in RENAME.items() if k in df.columns})

    # Clean string columns
    for col in ["wr_number", "wr_flag", "spectral_type", "name", "error_flag"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
            )

    # Derive WR subtype (WN, WC, WO) from spectral type
    def get_subtype(sp):
        if pd.isna(sp):
            return pd.NA
        sp = str(sp).strip()
        if sp.startswith("WO"):
            return "WO"
        if sp.startswith("WN"):
            return "WN"
        if sp.startswith("WC"):
            return "WC"
        return pd.NA

    df["wr_subtype"] = df["spectral_type"].apply(get_subtype)
    df["is_binary"] = df["spectral_type"].str.contains(r"\+", na=False)

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    df = df.sort_values("wr_number").reset_index(drop=True)

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_wn = int((df["wr_subtype"] == "WN").sum())
    n_wc = int((df["wr_subtype"] == "WC").sum())
    n_wo = int((df["wr_subtype"] == "WO").sum())
    n_binary = int(df["is_binary"].sum())
    n_with_distance = int(df["distance_kpc"].notna().sum())
    n_with_luminosity = int(df["log_luminosity"].notna().sum())
    median_dist = df["distance_kpc"].median()

    quick_stats = f"""\
- **{n_total:,}** Galactic Wolf-Rayet stars
- **{n_wn}** WN (nitrogen sequence), **{n_wc}** WC (carbon sequence), **{n_wo}** WO (oxygen sequence)
- **{n_binary}** spectroscopic binaries
- **{n_with_distance}** with Gaia-based distance estimates (median {median_dist:.1f} kpc)
- **{n_with_luminosity}** with luminosity measurements"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/wolf-rayet-stars", split="train")
df = ds.to_pandas()

# WN vs WC distribution
print(df["wr_subtype"].value_counts())

# Nearest WR stars
nearest = df.nsmallest(10, "distance_kpc")[["wr_number", "spectral_type", "distance_kpc", "name"]]
print(nearest)

# Luminosity distribution by subtype
import matplotlib.pyplot as plt
for st in ["WN", "WC"]:
    sub = df[df["wr_subtype"] == st].dropna(subset=["log_luminosity"])
    plt.hist(sub["log_luminosity"], bins=15, alpha=0.6, label=st)
plt.xlabel("log(L/L_sun)")
plt.ylabel("Count")
plt.legend()
plt.title("Wolf-Rayet Luminosity Distribution")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Galactic Wolf-Rayet Stars",
        description=DESCRIPTION,
        tags=["space", "stars", "wolf-rayet", "massive-stars", "astronomy",
              "open-data", "tabular-data", "parquet"],
        source_url="https://vizier.cds.unistra.fr/viz-bin/VizieR-3?-source=J/MNRAS/493/1512",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e000191/GSFC_20171208_Archive_e000191~medium.jpg",
            "alt": "A youthful globular star cluster observed by the Hubble Space Telescope",
            "credit": "NASA/ESA/Hubble",
        },
        related_datasets=[
            "juliensimon/bright-star-catalog",
            "juliensimon/gcvs-variable-stars",
            "juliensimon/pulsar-catalog",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "ra_deg", "dec_deg", "parallax_mas", "parallax_error_mas",
                "distance_kpc", "distance_upper_error_kpc", "distance_lower_error_kpc",
                "galactic_height_pc", "galactic_height_upper_error_pc",
                "galactic_height_lower_error_pc",
                "gaia_g_mag", "gaia_bp_rp", "astrometric_excess_noise", "log_luminosity",
                "ks_mag", "j_ks_color", "h_ks_color", "ks_extinction", "ks_abs_mag",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="wolf_rayet_stars.parquet",
            min_rows=350,
            expected_columns=["wr_number", "ra_deg", "dec_deg", "spectral_type"],
            critical_columns=["wr_number", "ra_deg", "dec_deg"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Galactic Wolf-Rayet stars: {n_total:,} stars",
        )
    print("Done.")


if __name__ == "__main__":
    main()
