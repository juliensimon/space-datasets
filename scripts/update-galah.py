#!/usr/bin/env python3
"""Fetch GALAH DR4 stellar abundances catalog (FITS) and upload to HF."""

import tempfile

import pandas as pd
import requests
from astropy.table import Table

from hf_dataset_utils import Pipeline

FITS_URL = "https://cloud.datacentral.org.au/teamdata/GALAH/public/GALAH_DR4/catalogs/galah_dr4_allstar_240705.fits"
HF_REPO = "juliensimon/galah-dr4-stellar-abundances"

# ── Columns to keep ──────────────────────────────────────────────────
# Identifiers & position
ID_COLS = [
    "sobject_id", "star_id", "tmass_id", "gaiadr3_source_id",
    "ra", "dec",
]

# Stellar parameters & radial velocity
PARAM_COLS = [
    "teff", "logg", "fe_h", "vmic", "vsini",
    "rv_comp_1", "rv_comp_2",
]

# Signal-to-noise & quality flags
QUALITY_COLS = [
    "snr_px_ccd1", "snr_px_ccd2", "snr_px_ccd3", "snr_px_ccd4",
    "flag_sp", "flag_red",
]

# Elemental abundances [X/Fe] — 31 elements
ABUNDANCE_COLS = [
    "li_fe", "c_fe", "n_fe", "o_fe",
    "na_fe", "al_fe", "k_fe",
    "mg_fe", "si_fe", "ca_fe", "ti_fe",
    "sc_fe", "v_fe", "cr_fe", "mn_fe", "co_fe", "ni_fe", "cu_fe", "zn_fe",
    "rb_fe", "sr_fe", "y_fe", "zr_fe", "mo_fe", "ba_fe", "la_fe", "ce_fe", "nd_fe",
    "ru_fe", "sm_fe", "eu_fe",
]

KEEP_COLS = ID_COLS + PARAM_COLS + QUALITY_COLS + ABUNDANCE_COLS

# ── Column descriptions for README schema table ──────────────────────
COLUMN_DESCRIPTIONS = {
    "sobject_id": "GALAH spectroscopic observation identifier (unique per exposure); format encodes field and fiber number",
    "star_id": "GALAH unique star identifier; a star observed multiple times shares the same star_id but has distinct sobject_id values",
    "tmass_id": "2MASS photometric catalog cross-identifier (e.g. 'J12345678+1234567'); null if no 2MASS match",
    "gaiadr3_source_id": "Gaia DR3 astrometric source identifier; enables cross-match for precise positions, proper motions, and parallaxes; null if unmatched",
    "ra": "Right ascension, ICRS J2000.0, in decimal degrees (0-360)",
    "dec": "Declination, ICRS J2000.0, in decimal degrees (-90 to +90)",
    "teff_k": "Effective temperature in Kelvin from spectral synthesis; GALAH targets FGK stars, typical range 4000-7500 K; uncertainty ~100 K; null if spectral pipeline failed (flag_sp > 0)",
    "logg": "Log surface gravity in cgs (log cm/s²); main sequence dwarfs: 4.0-5.0, subgiants: 3.5-4.5, red giants: 1.5-3.5; null if flag_sp > 0",
    "fe_h_dex": "[Fe/H] iron abundance in dex relative to solar; GALAH surveys -2.5 to +0.5 dex; typical uncertainty ~0.1 dex; null if flag_sp > 0",
    "vmic": "Microturbulence velocity in km/s; internal parameter of the spectral model capturing small-scale turbulent broadening; typical range 0.5-2.0 km/s",
    "vsini": "Projected rotational velocity v sin i in km/s; slow rotators (FGK dwarfs) typically < 10 km/s; null for stars where rotation is unresolved at R~28,000",
    "radial_velocity_kms": "Barycentric radial velocity in km/s from cross-correlation; precision ~0.1 km/s; null for very low S/N spectra",
    "radial_velocity_comp2_kms": "Barycentric radial velocity of a detected binary companion in km/s; non-null only for double-lined spectroscopic binaries (SB2)",
    "snr_px_ccd1": "Signal-to-noise ratio per pixel for HERMES CCD 1 (blue channel, ~4713-4903 Å); drives which light-element abundances can be measured",
    "snr_px_ccd2": "Signal-to-noise ratio per pixel for HERMES CCD 2 (green channel, ~5648-5873 Å); drives which iron-peak abundances can be measured",
    "snr_px_ccd3": "Signal-to-noise ratio per pixel for HERMES CCD 3 (red channel, ~6478-6737 Å); drives which alpha-element abundances can be measured",
    "snr_px_ccd4": "Signal-to-noise ratio per pixel for HERMES CCD 4 (IR channel, ~7585-7887 Å); drives which neutron-capture abundances can be measured",
    "snr_mean": "Mean S/N per pixel averaged across all four HERMES CCDs; derived column; stars with snr_mean < 30 have fewer reliable abundance measurements",
    "flag_sp": "Spectroscopic analysis quality flag; 0 = good stellar parameters; >0 encodes specific problems (binary contamination, emission, grid edge); use flag_sp == 0 for clean samples",
    "flag_red": "Reduction pipeline quality flag; 0 = successful reduction; >0 indicates issues with sky subtraction, cross-talk, or cosmic rays",
    "n_abundances": "Count of non-null [X/Fe] abundance measurements for this star; ranges 0-31; derived column useful for selecting well-characterised stars",
    "li_fe": "[Li/Fe] lithium abundance ratio in dex; sensitive to stellar age and mixing; often unmeasurable — null in most stars",
    "c_fe": "[C/Fe] carbon abundance ratio in dex; elevated in carbon-enhanced metal-poor (CEMP) stars",
    "n_fe": "[N/Fe] nitrogen abundance ratio in dex; a tracer of CNO cycling and AGB dredge-up",
    "o_fe": "[O/Fe] oxygen abundance ratio in dex; key alpha-element tracing core-collapse supernova enrichment",
    "na_fe": "[Na/Fe] sodium abundance ratio in dex; anti-correlates with O in globular cluster stars",
    "al_fe": "[Al/Fe] aluminium abundance ratio in dex; traces Mg-Al chain proton captures in massive stars",
    "k_fe": "[K/Fe] potassium abundance ratio in dex; sensitive to non-LTE effects; limited by spectral coverage",
    "mg_fe": "[Mg/Fe] magnesium abundance ratio in dex; primary alpha-element; high in old, metal-poor disk stars; decreases with increasing [Fe/H] due to Type Ia SNe iron contribution",
    "si_fe": "[Si/Fe] silicon abundance ratio in dex; alpha-element; co-produced with Mg in core-collapse supernovae",
    "ca_fe": "[Ca/Fe] calcium abundance ratio in dex; alpha-element; traces both core-collapse and Type Ia supernova nucleosynthesis",
    "ti_fe": "[Ti/Fe] titanium abundance ratio in dex; odd alpha-element; useful for separating thin disk, thick disk, and halo populations",
    "sc_fe": "[Sc/Fe] scandium abundance ratio in dex; iron-peak element; produced mainly in core-collapse supernovae",
    "v_fe": "[V/Fe] vanadium abundance ratio in dex; iron-peak element; constrains explosive nucleosynthesis models",
    "cr_fe": "[Cr/Fe] chromium abundance ratio in dex; iron-peak element with known non-LTE corrections required",
    "mn_fe": "[Mn/Fe] manganese abundance ratio in dex; traces Type Ia supernova contribution (Mn is overproduced in Chandrasekhar-mass SNe Ia)",
    "co_fe": "[Co/Fe] cobalt abundance ratio in dex; iron-peak element sensitive to neutron excess in the explosive burning region",
    "ni_fe": "[Ni/Fe] nickel abundance ratio in dex; closely follows Fe; used to distinguish thick-disk from halo stars",
    "cu_fe": "[Cu/Fe] copper abundance ratio in dex; iron-peak element with significant s-process contribution",
    "zn_fe": "[Zn/Fe] zinc abundance ratio in dex; bridges iron-peak and neutron-capture elements; useful metallicity probe",
    "rb_fe": "[Rb/Fe] rubidium abundance ratio in dex; s-process element; traces AGB stellar nucleosynthesis",
    "sr_fe": "[Sr/Fe] strontium abundance ratio in dex; light s-process element; also has r-process and charged-particle process contributions",
    "y_fe": "[Y/Fe] yttrium abundance ratio in dex; s-process element with Ba/Y ratio used to age-date stellar populations",
    "zr_fe": "[Zr/Fe] zirconium abundance ratio in dex; s-process element co-produced with Y and Sr",
    "mo_fe": "[Mo/Fe] molybdenum abundance ratio in dex; neutron-capture element with both s- and r-process origin",
    "ba_fe": "[Ba/Fe] barium abundance ratio in dex; dominant s-process tracer; high in AGB-enriched stars and young thin-disk stars",
    "la_fe": "[La/Fe] lanthanum abundance ratio in dex; s-process element; La/Eu ratio distinguishes s- from r-process enrichment",
    "ce_fe": "[Ce/Fe] cerium abundance ratio in dex; s-process element produced in low-mass AGB stars",
    "nd_fe": "[Nd/Fe] neodymium abundance ratio in dex; mixed s- and r-process origin",
    "ru_fe": "[Ru/Fe] ruthenium abundance ratio in dex; primarily r-process origin; rare to measure in stellar spectra",
    "sm_fe": "[Sm/Fe] samarium abundance ratio in dex; r-process dominated element; traces neutron star merger enrichment",
    "eu_fe": "[Eu/Fe] europium abundance ratio in dex; the cleanest r-process tracer; high in metal-poor halo stars; r-process enrichment from neutron star mergers",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
The fourth data release of the GALactic Archaeology with HERMES (GALAH) survey, \
providing radial velocities, stellar parameters, and up to 31 elemental abundances \
for 917,588 stars observed with the HERMES spectrograph on the Anglo-Australian Telescope.

GALAH DR4 is one of the largest stellar spectroscopic surveys, designed to unravel \
the formation and evolution of the Milky Way through chemical tagging. Each star has \
high-resolution spectra decomposed into fundamental stellar parameters and individual \
elemental abundances spanning light elements, alpha-elements, iron-peak elements, \
and neutron-capture elements.

GALAH was specifically designed for chemical tagging — the idea that stars born in \
the same molecular cloud retain a unique multi-dimensional chemical fingerprint that \
persists long after the birth cluster has dispersed. The HERMES spectrograph delivers \
four non-contiguous optical wavelength channels at R ~ 28,000, capturing lines of light \
elements (Li, C, N, O), alpha-elements (Mg, Si, Ca, Ti), iron-peak elements \
(Sc, V, Cr, Mn, Fe, Co, Ni, Cu, Zn), and neutron-capture elements \
(Rb, Sr, Y, Zr, Mo, Ba, La, Ce, Nd, Ru, Sm, Eu) — up to 31 distinct abundance \
dimensions per star.

DR4 represents a major advance over DR3, incorporating improved spectral analysis \
techniques, better treatment of non-LTE effects for critical elements, and \
cross-matching with Gaia DR3 for precise astrometric information. The inclusion of \
both s-process elements (Ba, La, Ce from AGB nucleosynthesis) and r-process elements \
(Eu from neutron star mergers) makes GALAH uniquely powerful for constraining the \
sites and timescales of heavy element production in the Milky Way.
"""


def main():
    # ── Download FITS ─────────────────────────────────────────────────
    print("Downloading GALAH DR4 allstar FITS catalog (~723 MB)...")
    with tempfile.NamedTemporaryFile(suffix=".fits") as tmp_fits:
        with requests.get(FITS_URL, timeout=600, stream=True) as resp:
            resp.raise_for_status()
            total = 0
            for chunk in resp.iter_content(chunk_size=8 * 1024 * 1024):
                tmp_fits.write(chunk)
                total += len(chunk)
            tmp_fits.flush()
        print(f"  Downloaded {total / 1024 / 1024:.0f} MB")

        # ── Read FITS into DataFrame ──────────────────────────────────
        print("Reading FITS table...")
        table = Table.read(tmp_fits.name, hdu=1)

    # Keep only columns that actually exist in the file
    available = [c for c in KEEP_COLS if c in table.colnames]
    missing = set(KEEP_COLS) - set(available)
    if missing:
        print(f"  Note: {len(missing)} requested columns not in FITS: {sorted(missing)}")

    # Filter out any multidimensional columns (can't convert to pandas)
    scalar = [c for c in available if len(table[c].shape) <= 1]
    df = table[scalar].to_pandas()
    print(f"  {len(df):,} stars, {len(df.columns)} columns")

    # ── Rename columns ────────────────────────────────────────────────
    rename_map = {
        "rv_comp_1": "radial_velocity_kms",
        "rv_comp_2": "radial_velocity_comp2_kms",
        "fe_h": "fe_h_dex",
        "teff": "teff_k",
    }
    rename_map = {k: v for k, v in rename_map.items() if k in df.columns}
    df = df.rename(columns=rename_map)

    # String identifiers
    for col in ("sobject_id", "star_id", "tmass_id", "gaiadr3_source_id"):
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
            df[col] = df[col].replace({"": None, "nan": None})

    # Integer flag columns
    for col in ("flag_sp", "flag_red"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    # ── Derived columns ───────────────────────────────────────────────
    abund_cols_in_df = [c for c in ABUNDANCE_COLS if c in df.columns]
    df["n_abundances"] = df[abund_cols_in_df].notna().sum(axis=1).astype("Int64")

    snr_cols = [c for c in ("snr_px_ccd1", "snr_px_ccd2", "snr_px_ccd3", "snr_px_ccd4")
                if c in df.columns]
    if snr_cols:
        df["snr_mean"] = df[snr_cols].mean(axis=1)

    # ── Stats for README ──────────────────────────────────────────────
    n_total = len(df)
    rv_col = "radial_velocity_kms" if "radial_velocity_kms" in df.columns else "rv_comp_1"
    n_rv = int(df[rv_col].notna().sum()) if rv_col in df.columns else 0
    n_abund = int((df["n_abundances"] > 0).sum())
    median_abund = int(df["n_abundances"].median()) if "n_abundances" in df.columns else 0
    median_snr = f"{df['snr_mean'].median():.1f}" if "snr_mean" in df.columns else "N/A"
    n_elements = len(abund_cols_in_df)
    n_flag_good = int((df["flag_sp"] == 0).sum()) if "flag_sp" in df.columns else 0

    quick_stats = f"""\
- **{n_total:,}** stars observed with HERMES spectrograph
- **{n_rv:,}** stars with radial velocity measurements
- **{n_abund:,}** stars with at least one elemental abundance ({100*n_abund/n_total:.0f}%)
- **{n_elements}** elemental abundance columns ([X/Fe]), median **{median_abund}** per star
- **{n_flag_good:,}** stars with clean spectroscopic flags (flag_sp == 0)
- Median SNR across 4 HERMES CCDs: **{median_snr}** per pixel"""

    usage = f"""\
```python
from datasets import load_dataset
import matplotlib.pyplot as plt

ds = load_dataset("{HF_REPO}", split="train")
df = ds.to_pandas()

# Kiel diagram (Teff vs logg) coloured by [Fe/H] — shows stellar populations
best = df[(df["flag_sp"] == 0) & df["teff_k"].notna() & df["logg"].notna()]
sample = best.sample(min(50_000, len(best)), random_state=42)

sc = plt.scatter(sample["teff_k"], sample["logg"],
                 c=sample["fe_h_dex"], s=0.1, cmap="coolwarm",
                 vmin=-1.5, vmax=0.5, alpha=0.6)
plt.gca().invert_xaxis()
plt.gca().invert_yaxis()
plt.xlabel("Effective Temperature (K)")
plt.ylabel("log g (dex)")
plt.title("GALAH DR4 Kiel Diagram")
plt.colorbar(sc, label="[Fe/H] (dex)")
plt.tight_layout()
plt.show()

# Abundance pattern: alpha-element enhancement vs metallicity
alpha_cols = ["mg_fe", "si_fe", "ca_fe", "ti_fe"]
best["alpha_fe"] = best[alpha_cols].mean(axis=1)
sub = best.dropna(subset=["fe_h_dex", "alpha_fe"]).sample(30_000, random_state=0)
plt.figure()
plt.scatter(sub["fe_h_dex"], sub["alpha_fe"], s=0.1, alpha=0.3, c="steelblue")
plt.axhline(0, color="gray", lw=0.5, ls="--")
plt.xlabel("[Fe/H] (dex)")
plt.ylabel("[alpha/Fe] (dex)")
plt.title("Alpha-element Enhancement vs Metallicity")
plt.tight_layout()
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="GALAH DR4 — Stellar Abundances for 917k Stars",
        description=DESCRIPTION,
        tags=["space", "stars", "spectroscopy", "galah", "abundances", "astronomy",
              "open-data", "tabular-data", "parquet"],
        source_url="https://www.galah-survey.org/dr4/",
        task_categories=["tabular-classification", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e000191/GSFC_20171208_Archive_e000191~medium.jpg",
            "alt": "A youthful globular star cluster observed by the Hubble Space Telescope",
            "credit": "NASA/ESA/Hubble",
        },
        update_schedule="Static dataset — uploaded once from the DR4 release catalog",
        related_datasets=[
            "juliensimon/apogee-dr17-stellar-abundances",
            "juliensimon/hipparcos-catalog",
            "juliensimon/pulsar-catalog",
        ],
    ) as p:
        numeric_cols = [
            c for c in df.columns
            if c not in ("sobject_id", "star_id", "tmass_id", "gaiadr3_source_id",
                         "flag_sp", "flag_red", "n_abundances")
        ]
        df = p.clean(
            df,
            numeric=numeric_cols,
        )
        p.publish(
            df,
            filename="galah_dr4_allstar.parquet",
            min_rows=500_000,
            expected_columns=["sobject_id", "ra", "dec", "teff_k", "logg", "fe_h_dex",
                               "radial_velocity_kms"],
            critical_columns=["sobject_id", "ra", "dec", "teff_k"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update GALAH DR4: {n_total:,} stars, {n_elements} elements",
        )
    print("Done.")


if __name__ == "__main__":
    main()
