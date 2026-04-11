#!/usr/bin/env python3
"""Fetch Fermi LAT Third Catalog of Hard Sources (3FHL, >10 GeV) from HEASARC and upload to HF."""

import io
import sys

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

TAP_URL = "https://heasarc.gsfc.nasa.gov/xamin/vo/tap/sync"
HF_REPO = "juliensimon/fermi-3fhl-hard-gamma-ray"

ADQL = """\
SELECT * FROM fermi3fhl\
"""

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "name": "Official 3FHL source designation, e.g. '3FHL J0001.2-0748'; encodes the catalog prefix and J2000 coordinates of the source centroid; uniquely identifies each entry in the catalog",
    "ra": "Right ascension of the source in degrees (J2000, ICRS); range 0-360; derived from a maximum-likelihood fit to the >10 GeV photon distribution",
    "dec": "Declination of the source in degrees (J2000, ICRS); range -90 to +90; derived from a maximum-likelihood fit to the >10 GeV photon distribution",
    "lii": "Galactic longitude in degrees; range 0-360; derived from ra and dec via the standard IAU coordinate transformation; useful for studying Galactic plane sources",
    "bii": "Galactic latitude in degrees; range -90 to +90; sources near bii=0 lie in the Galactic plane where diffuse emission complicates detection",
    "error_radius": "95% confidence radius on the source position in degrees; smaller values indicate better localization; typically 0.01-0.1 deg for bright sources",
    "roi": "Region of interest number used in the analysis; the sky was divided into overlapping ROIs for the maximum-likelihood source detection",
    "significance": "Detection significance in the 10 GeV - 2 TeV band expressed as the square root of the test statistic (sqrt(TS)); higher values indicate more confident detections; catalog threshold is sqrt(TS) >= 4",
    "pivot_energy": "Pivot (decorrelation) energy in MeV at which the flux uncertainty is minimized; chosen to reduce correlation between spectral index and flux normalization",
    "flux_density": "Differential photon flux at the pivot energy in units of ph/cm2/s/MeV; the spectral normalization parameter used in the likelihood fit",
    "flux_density_error": "1-sigma statistical uncertainty on flux_density in ph/cm2/s/MeV",
    "flux": "Integrated photon flux in the 10 GeV - 2 TeV band in ph/cm2/s; obtained by integrating the best-fit spectral model over the full energy range",
    "flux_error": "1-sigma statistical uncertainty on the integrated photon flux in ph/cm2/s",
    "energy_flux": "Integrated energy flux in the 10 GeV - 2 TeV band in erg/cm2/s; accounts for the energy weighting of the spectrum; more physically meaningful than photon flux for comparing source luminosities",
    "energy_flux_error": "1-sigma statistical uncertainty on the energy flux in erg/cm2/s",
    "curve_significance": "Significance of spectral curvature with respect to a simple power-law model; high values (>3) indicate that a curved spectrum (log-parabola or exponential cutoff) is preferred over a power law",
    "spectrum_type": "Best-fit spectral model type: 'PowerLaw', 'LogParabola', or 'PLExpCutoff'; selected based on the curve_significance test",
    "spectral_index": "Photon spectral index of the best-fit model; for a power law dN/dE ~ E^(-index), typical values are 1.5-4; harder (lower index) sources emit relatively more high-energy photons",
    "spectral_index_error": "1-sigma statistical uncertainty on the spectral index",
    "beta": "Curvature parameter for LogParabola spectra: dN/dE ~ (E/E0)^(-(alpha + beta*ln(E/E0))); zero for pure power-law sources; larger beta indicates stronger curvature",
    "beta_error": "1-sigma statistical uncertainty on the beta curvature parameter; null for sources fit with a simple power law",
    "powerlaw_index": "Photon index when the source is fit with a simple power law regardless of whether curvature is significant; useful for uniform comparisons across all sources",
    "powerlaw_index_error": "1-sigma uncertainty on the power-law photon index",
    "flux_10_20_gev": "Photon flux in the 10-20 GeV sub-band in ph/cm2/s; first of five logarithmically spaced energy bins used to construct the broadband spectral energy distribution",
    "flux_10_20_gev_neg_err": "Lower (negative) 1-sigma error on the 10-20 GeV photon flux in ph/cm2/s; asymmetric errors reflect the Poisson nature of photon counting",
    "flux_10_20_gev_pos_err": "Upper (positive) 1-sigma error on the 10-20 GeV photon flux in ph/cm2/s",
    "nufnu_10_20_gev": "Energy flux (nu*F_nu) in the 10-20 GeV band in erg/cm2/s; represents the spectral energy distribution value at the geometric mean energy of the bin",
    "sqrt_ts_10_20_gev": "Detection significance (sqrt of test statistic) in the 10-20 GeV band; values below ~2 indicate the source is not significantly detected in this sub-band",
    "flux_20_50_gev": "Photon flux in the 20-50 GeV sub-band in ph/cm2/s",
    "flux_20_50_gev_neg_err": "Lower 1-sigma error on the 20-50 GeV photon flux in ph/cm2/s",
    "flux_20_50_gev_pos_err": "Upper 1-sigma error on the 20-50 GeV photon flux in ph/cm2/s",
    "nufnu_20_50_gev": "Energy flux (nu*F_nu) in the 20-50 GeV band in erg/cm2/s",
    "sqrt_ts_20_50_gev": "Detection significance (sqrt(TS)) in the 20-50 GeV band",
    "flux_50_150_gev": "Photon flux in the 50-150 GeV sub-band in ph/cm2/s",
    "flux_50_150_gev_neg_err": "Lower 1-sigma error on the 50-150 GeV photon flux in ph/cm2/s",
    "flux_50_150_gev_pos_err": "Upper 1-sigma error on the 50-150 GeV photon flux in ph/cm2/s",
    "nufnu_50_150_gev": "Energy flux (nu*F_nu) in the 50-150 GeV band in erg/cm2/s",
    "sqrt_ts_50_150_gev": "Detection significance (sqrt(TS)) in the 50-150 GeV band",
    "flux_150_500_gev": "Photon flux in the 150-500 GeV sub-band in ph/cm2/s",
    "flux_150_500_gev_neg_err": "Lower 1-sigma error on the 150-500 GeV photon flux in ph/cm2/s",
    "flux_150_500_gev_pos_err": "Upper 1-sigma error on the 150-500 GeV photon flux in ph/cm2/s",
    "nufnu_150_500_gev": "Energy flux (nu*F_nu) in the 150-500 GeV band in erg/cm2/s",
    "sqrt_ts_150_500_gev": "Detection significance (sqrt(TS)) in the 150-500 GeV band",
    "flux_0p5_2_tev": "Photon flux in the 0.5-2 TeV sub-band in ph/cm2/s; the highest energy bin, probing the TeV regime where ground-based Cherenkov telescopes provide complementary coverage",
    "flux_0p5_2_tev_neg_err": "Lower 1-sigma error on the 0.5-2 TeV photon flux in ph/cm2/s",
    "flux_0p5_2_tev_pos_err": "Upper 1-sigma error on the 0.5-2 TeV photon flux in ph/cm2/s",
    "nufnu_0p5_2_tev": "Energy flux (nu*F_nu) in the 0.5-2 TeV band in erg/cm2/s",
    "sqrt_ts_0p5_2_tev": "Detection significance (sqrt(TS)) in the 0.5-2 TeV band",
    "npred": "Total number of predicted photons from this source in the model; a measure of signal strength that accounts for exposure and PSF; higher npred means more photons attributed to this source",
    "hep_energy": "Energy of the highest-energy photon associated with the source in GeV; constrained by the LAT effective area and source spectrum; can exceed 1 TeV for the hardest sources",
    "hep_prob": "Probability that the highest-energy photon truly belongs to this source rather than a neighboring source or diffuse background; values near 1.0 give high confidence in the association",
    "num_bayesian_blocks": "Number of Bayesian blocks in the source light curve; a value of 1 indicates no significant variability detected; higher values suggest flux changes over the 7-year observation period",
    "extended_source_name": "Name of the spatial template if the source is modeled as spatially extended (e.g. supernova remnants, pulsar wind nebulae); null for point sources which are the majority of the catalog",
    "alt_gammaray_name": "Alternative gamma-ray catalog designation from earlier Fermi catalogs (e.g. 3FGL, 2FHL) or other experiments; useful for cross-matching with the broader gamma-ray literature",
    "tev_assoc_flag": "Flag indicating association with a known TeV source from ground-based observations; non-null values indicate overlap with sources detected by H.E.S.S., MAGIC, or VERITAS",
    "assoc_tevcat": "Name of the associated TeV source in TeVCat; provides the link between Fermi LAT and ground-based Cherenkov telescope detections of the same astrophysical object",
    "source_class": "Astrophysical classification of the source (e.g. 'bll' = BL Lac blazar, 'fsrq' = flat-spectrum radio quasar, 'psr' = pulsar, 'snr' = supernova remnant, 'pwn' = pulsar wind nebula, '' = unassociated)",
    "assoc_name_1": "Primary counterpart name at other wavelengths from automated association methods; typically a radio or X-ray catalog designation used to identify the gamma-ray source",
    "assoc_name_2": "Secondary counterpart name at other wavelengths; provides an alternative identification when multiple association methods yield different but plausible counterparts",
    "assoc_prob_bay": "Bayesian association probability for the primary counterpart; range 0-1; values above 0.8 indicate a highly confident multi-wavelength association",
    "assoc_prob_lr": "Likelihood-ratio association probability for the primary counterpart; range 0-1; an independent association metric complementing the Bayesian probability",
    "redshift": "Spectroscopic redshift of the associated extragalactic counterpart; null for Galactic sources and unassociated sources; used to compute intrinsic luminosity and EBL absorption corrections",
    "nupeak_obs": "Observed synchrotron peak frequency in Hz (log10 scale) for blazar-type sources; classifies blazars as low-synchrotron-peaked (LSP, <10^14 Hz), intermediate (ISP), or high-synchrotron-peaked (HSP, >10^15 Hz); null for non-blazar sources",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
The 3FHL catalog (Ajello et al. 2017) contains sources detected by Fermi LAT in the \
10 GeV - 2 TeV energy range using 7 years of Pass 8 data. This catalog bridges the gap \
between the GeV regime covered by the standard Fermi catalogs and the TeV regime \
covered by ground-based Cherenkov telescopes (H.E.S.S., MAGIC, VERITAS).

Sources include blazars, pulsar wind nebulae, supernova remnants, and unidentified \
gamma-ray emitters. The catalog is essential for planning observations with current \
and future TeV observatories like CTA.

The 10 GeV - 2 TeV energy range probed by 3FHL occupies a critical frontier in \
high-energy astrophysics. Below ~10 GeV, the Fermi LAT standard catalogs (3FGL, 4FGL) \
provide comprehensive coverage with large photon statistics. Above ~100 GeV, imaging \
atmospheric Cherenkov telescopes (IACTs) like H.E.S.S., MAGIC, and VERITAS achieve \
superior sensitivity but with limited fields of view and duty cycles. The 3FHL catalog \
bridges this gap using Fermi LAT's Pass 8 event reconstruction, which dramatically \
improved the instrument's effective area and point-spread function at high energies, \
enabling detection of hard-spectrum sources that were previously buried in background.

The source population in 3FHL is dominated by blazars — active galactic nuclei whose \
relativistic jets point close to our line of sight, producing Doppler-boosted emission \
that peaks in the GeV-TeV band. The catalog also contains Galactic sources such as \
pulsar wind nebulae (where ultra-relativistic electron-positron winds from young pulsars \
produce inverse-Compton emission), supernova remnants (candidate sites of cosmic-ray \
acceleration up to PeV energies), and a significant fraction of unidentified sources \
that may represent entirely new source classes. For extragalactic sources, the interaction \
of TeV photons with the extragalactic background light (EBL) via pair production imprints \
a redshift-dependent spectral cutoff, making this catalog a powerful probe of the EBL \
intensity and its evolution.

The 3FHL is the primary seed catalog for the Cherenkov Telescope Array (CTA), the \
next-generation ground-based gamma-ray observatory. Nearly every 3FHL source above the \
CTA sensitivity threshold is expected to be detected, and the catalog's uniform sky \
coverage helps define CTA's key science programs including surveys of the Galactic plane \
and extragalactic deep fields.
"""


def fetch_catalog() -> pd.DataFrame:
    """Try CSV first, fall back to JSON, then pipe-delimited text."""
    # Attempt 1: CSV
    print("Fetching Fermi 3FHL catalog (CSV)...")
    resp = requests.get(TAP_URL, params={
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": ADQL,
    }, timeout=120)
    resp.raise_for_status()

    if not resp.text.strip().startswith("<?xml"):
        try:
            df = pd.read_csv(io.StringIO(resp.text))
            if len(df) > 100:
                print(f"  CSV parse OK: {len(df):,} rows")
                return df
        except Exception as e:
            print(f"  CSV parse failed: {e}")
    else:
        print("  CSV not supported (got XML/VOTable response)")

    # Attempt 2: JSON
    print("Retrying with FORMAT=json...")
    resp = requests.get(TAP_URL, params={
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "json", "QUERY": ADQL,
    }, timeout=120)
    resp.raise_for_status()

    try:
        data = resp.json()
        if "data" in data and "metadata" in data:
            cols = [m["name"] for m in data["metadata"]]
            df = pd.DataFrame(data["data"], columns=cols)
        else:
            df = pd.DataFrame(data)
        if len(df) > 100:
            print(f"  JSON parse OK: {len(df):,} rows")
            return df
    except Exception as e:
        print(f"  JSON parse failed: {e}")

    # Attempt 3: pipe-delimited text
    print("Retrying with FORMAT=text...")
    resp = requests.get(TAP_URL, params={
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "text", "QUERY": ADQL,
    }, timeout=120)
    resp.raise_for_status()

    lines = [l for l in resp.text.strip().splitlines() if l.strip() and not l.startswith("-")]
    if len(lines) >= 2:
        header = [c.strip() for c in lines[0].split("|")]
        rows = []
        for line in lines[1:]:
            rows.append([c.strip() for c in line.split("|")])
        df = pd.DataFrame(rows, columns=header)
        # Drop empty columns from leading/trailing pipes
        df = df.loc[:, df.columns != ""]
        print(f"  Text parse OK: {len(df):,} rows")
        return df

    print("::error::All fetch formats failed")
    sys.exit(1)


def main():
    df = fetch_catalog()

    # Rename columns to snake_case (HEASARC columns are already lowercase)
    rename = {}
    for col in df.columns:
        clean = col.strip().lower().replace(" ", "_").replace("-", "_")
        if clean != col:
            rename[col] = clean
    if rename:
        df = df.rename(columns=rename)

    # Clean empty strings to NaN for all string columns
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip().replace(
            {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
        )

    # Coerce numeric columns (common 3FHL columns)
    numeric_prefixes = (
        "ra", "dec", "lii", "bii", "flux", "significance", "npred",
        "energy", "pivot", "spectral_index", "error_", "cutoff",
        "semi_major", "semi_minor", "pos_angle", "variability",
    )
    numeric_cols = [c for c in df.columns if c.startswith(numeric_prefixes)]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Coerce remaining numeric columns that don't match prefixes
    extra_numeric = [
        "roi", "pivot_energy", "flux_density", "flux_density_error",
        "curve_significance", "spectral_index_error", "beta", "beta_error",
        "powerlaw_index", "powerlaw_index_error", "npred",
        "hep_energy", "hep_prob", "num_bayesian_blocks",
        "assoc_prob_bay", "assoc_prob_lr", "redshift", "nupeak_obs",
        "nufnu_10_20_gev", "sqrt_ts_10_20_gev",
        "nufnu_20_50_gev", "sqrt_ts_20_50_gev",
        "nufnu_50_150_gev", "sqrt_ts_50_150_gev",
        "nufnu_150_500_gev", "sqrt_ts_150_500_gev",
        "nufnu_0p5_2_tev", "sqrt_ts_0p5_2_tev",
    ]
    for col in extra_numeric:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Sort by significance descending (highest-significance sources first)
    sort_col = None
    for candidate in ["significance", "signif_avg", "sqrt_ts"]:
        if candidate in df.columns:
            sort_col = candidate
            break
    if sort_col is None:
        for candidate in ["flux", "energy_flux", "flux_density"]:
            if candidate in df.columns:
                sort_col = candidate
                break

    if sort_col:
        df[sort_col] = pd.to_numeric(df[sort_col], errors="coerce")
        df = df.sort_values(sort_col, ascending=False).reset_index(drop=True)
        print(f"  Sorted by {sort_col} descending")
    else:
        df = df.reset_index(drop=True)
        print("  No significance/flux column found for sorting")

    # Keep only columns that have descriptions (drop HEASARC internal columns)
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    n_total = len(df)
    n_cols = len(df.columns)
    print(f"  {n_total:,} hard gamma-ray sources, {n_cols} columns")

    # ── Domain-specific stats for README ─────────────────────────────
    n_blazars = int(df["source_class"].isin(["bll", "BLL", "fsrq", "FSRQ", "bcu", "BCU"]).sum()) if "source_class" in df.columns else 0
    n_with_redshift = int(df["redshift"].notna().sum()) if "redshift" in df.columns else 0
    median_sig = df["significance"].median() if "significance" in df.columns else 0

    quick_stats = f"""\
- **{n_total:,}** gamma-ray sources above 10 GeV
- **{n_blazars:,}** blazar-type sources (BL Lac, FSRQ, BCU)
- **{n_with_redshift:,}** with measured redshift
- Median detection significance: **{median_sig:.1f}** sigma"""

    # ── Custom usage example ─────────────────────────────────────────
    usage = """\
```python
from datasets import load_dataset
import matplotlib.pyplot as plt

ds = load_dataset("juliensimon/fermi-3fhl-hard-gamma-ray", split="train")
df = ds.to_pandas()

# Highest significance sources
print(df.sort_values("significance", ascending=False).head(10)[["name", "ra", "dec", "significance"]])

# Sky map in Galactic coordinates
fig, ax = plt.subplots(figsize=(12, 6), subplot_kw={"projection": "aitoff"})
import numpy as np
l = np.radians(df["lii"] - 180)  # center on Galactic center
b = np.radians(df["bii"])
ax.scatter(l, b, s=df["significance"] * 0.5, alpha=0.5, c=df["energy_flux"],
           cmap="inferno", norm=plt.matplotlib.colors.LogNorm())
ax.set_title("Fermi 3FHL Sources (>10 GeV) — Galactic Coordinates")
ax.grid(True)
plt.tight_layout()
plt.show()

# Spectral index distribution
plt.figure(figsize=(8, 5))
plt.hist(df["spectral_index"].dropna(), bins=40, edgecolor="black", alpha=0.7)
plt.xlabel("Photon Spectral Index")
plt.ylabel("Number of Sources")
plt.title("3FHL Spectral Index Distribution")
plt.tight_layout()
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Fermi LAT Third Catalog of Hard Sources (3FHL)",
        description=DESCRIPTION,
        tags=["space", "gamma-ray", "fermi", "nasa", "tev", "high-energy",
              "astronomy", "open-data", "tabular-data", "parquet"],
        source_url="https://heasarc.gsfc.nasa.gov/W3Browse/fermi/fermi3fhl.html",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e002215/GSFC_20171208_Archive_e002215~medium.jpg",
            "alt": "The gamma-ray sky as seen by NASA's Fermi telescope",
            "credit": "NASA/DOE/Fermi LAT Collaboration",
        },
        related_datasets=[
            "juliensimon/gamma-ray-bursts",
            "juliensimon/pulsar-catalog",
        ],
    ) as p:
        p.publish(
            df,
            filename="fermi-3fhl.parquet",
            min_rows=1_200,
            expected_columns=["name", "ra", "dec"],
            critical_columns=["name", "ra", "dec"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Fermi 3FHL catalog: {n_total:,} hard gamma-ray sources",
        )
    print("Done.")


if __name__ == "__main__":
    main()
