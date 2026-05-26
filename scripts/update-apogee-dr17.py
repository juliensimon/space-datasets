#!/usr/bin/env python3
"""Fetch APOGEE DR17 AllStar catalog from VizieR and upload to HF.

Source: Abdurro'uf et al. (2022, ApJS 259, 35) — final SDSS-IV APOGEE release.
VizieR catalog: III/286
"""

import re

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/apogee-dr17"

ADQL = 'SELECT * FROM "III/286/catalog"'

# Abundance elements tracked in APOGEE DR17
ABUNDANCE_ELEMENTS = [
    "C", "CI", "N", "O", "Na", "Mg", "Al", "Si", "S",
    "K", "Ca", "Ti", "TiII", "V", "Mn", "Fe", "Co", "Ni", "Ce", "Nd",
]

# ── Column mapping ───────────────────────────────────────────────────
RENAME = {
    # Coordinates
    "RA_ICRS": "ra_deg", "RAJ2000": "ra_deg", "_RA": "ra_deg", "RAdeg": "ra_deg",
    "DE_ICRS": "dec_deg", "DEJ2000": "dec_deg", "_DE": "dec_deg", "DEdeg": "dec_deg",
    # Identifiers
    "APOGEE_ID": "apogee_id", "APOGEE-ID": "apogee_id", "APOGEE": "apogee_id",
    "ApoID": "apogee_id", "Target": "target_id",
    "2MASS": "twomass_id",
    "Gaia": "gaia_source_id", "GaiaDR3": "gaia_source_id", "GaiaEDR3": "gaia_source_id",
    # Stellar parameters
    "Teff": "teff_k", "e_Teff": "teff_error_k",
    "logg": "logg", "e_logg": "logg_error",
    "TeffSp": "teff_sp", "loggSp": "logg_sp",
    "Vmicro": "vmicro_kms", "Vmacro": "vmacro_kms", "Vsini": "vsini_kms",
    # Overall metallicity [M/H]
    "[M/H]": "m_h", "__M_H_": "m_h", "_M_H_": "m_h",
    "e_[M/H]": "m_h_error", "e__M_H_": "m_h_error",
    # Alpha enhancement [alpha/M]
    "__a_M_": "alpha_m", "_a_M_": "alpha_m", "ALPHA_M": "alpha_m",
    "[a/M]": "alpha_m", "a_M": "alpha_m",
    "e__a_M_": "alpha_m_error", "e_a_M": "alpha_m_error", "e_ALPHA_M": "alpha_m_error",
    # Individual abundances [X/Fe]
    "[C/Fe]": "c_fe", "[C/Fe]Sp": "c_fe_sp", "e_[C/Fe]": "c_fe_err", "f_[C/Fe]": "c_fe_flag",
    "[CI/Fe]": "ci_fe", "[CI/Fe]Sp": "ci_fe_sp", "e_[CI/Fe]": "ci_fe_err", "f_[CI/Fe]": "ci_fe_flag",
    "[N/Fe]": "n_fe", "[N/Fe]Sp": "n_fe_sp", "e_[N/Fe]": "n_fe_err", "f_[N/Fe]": "n_fe_flag",
    "[O/Fe]": "o_fe", "[O/Fe]Sp": "o_fe_sp", "e_[O/Fe]": "o_fe_err", "f_[O/Fe]": "o_fe_flag",
    "[Na/Fe]": "na_fe", "[Na/Fe]Sp": "na_fe_sp", "e_[Na/Fe]": "na_fe_err", "f_[Na/Fe]": "na_fe_flag",
    "[Mg/Fe]": "mg_fe", "[Mg/Fe]Sp": "mg_fe_sp", "e_[Mg/Fe]": "mg_fe_err", "f_[Mg/Fe]": "mg_fe_flag",
    "[Al/Fe]": "al_fe", "[Al/Fe]Sp": "al_fe_sp", "e_[Al/Fe]": "al_fe_err", "f_[Al/Fe]": "al_fe_flag",
    "[Si/Fe]": "si_fe", "[Si/Fe]Sp": "si_fe_sp", "e_[Si/Fe]": "si_fe_err", "f_[Si/Fe]": "si_fe_flag",
    "[S/Fe]": "s_fe", "[S/Fe]Sp": "s_fe_sp", "e_[S/Fe]": "s_fe_err", "f_[S/Fe]": "s_fe_flag",
    "[K/Fe]": "k_fe", "[K/Fe]Sp": "k_fe_sp", "e_[K/Fe]": "k_fe_err", "f_[K/Fe]": "k_fe_flag",
    "[Ca/Fe]": "ca_fe", "[Ca/Fe]Sp": "ca_fe_sp", "e_[Ca/Fe]": "ca_fe_err", "f_[Ca/Fe]": "ca_fe_flag",
    "[Ti/Fe]": "ti_fe", "[Ti/Fe]Sp": "ti_fe_sp", "e_[Ti/Fe]": "ti_fe_err", "f_[Ti/Fe]": "ti_fe_flag",
    "[TiII/Fe]": "tiii_fe", "[TiII/Fe]Sp": "tiii_fe_sp", "e_[TiII/Fe]": "tiii_fe_err", "f_[TiII/Fe]": "tiii_fe_flag",
    "[V/Fe]": "v_fe", "[V/Fe]Sp": "v_fe_sp", "e_[V/Fe]": "v_fe_err", "f_[V/Fe]": "v_fe_flag",
    "[Cr/Fe]": "cr_fe", "[Cr/Fe]Sp": "cr_fe_sp", "e_[Cr/Fe]": "cr_fe_err", "f_[Cr/Fe]": "cr_fe_flag",
    "[Mn/Fe]": "mn_fe", "[Mn/Fe]Sp": "mn_fe_sp", "e_[Mn/Fe]": "mn_fe_err", "f_[Mn/Fe]": "mn_fe_flag",
    "[Co/Fe]": "co_fe", "[Co/Fe]Sp": "co_fe_sp", "e_[Co/Fe]": "co_fe_err", "f_[Co/Fe]": "co_fe_flag",
    "[Ni/Fe]": "ni_fe", "[Ni/Fe]Sp": "ni_fe_sp", "e_[Ni/Fe]": "ni_fe_err", "f_[Ni/Fe]": "ni_fe_flag",
    "[Ce/Fe]": "ce_fe", "[Ce/Fe]Sp": "ce_fe_sp", "e_[Ce/Fe]": "ce_fe_err", "f_[Ce/Fe]": "ce_fe_flag",
    "[Fe/H]": "fe_h", "[Fe/H]Sp": "fe_h_sp", "e_[Fe/H]": "fe_h_err", "f_[Fe/H]": "fe_h_flag",
    "[Fe/H]RV": "fe_h_rv",
    # [X/H] variants
    "__C_H_": "c_h", "_C_H_": "c_h", "C_H": "c_h", "[C/H]": "c_h",
    "__N_H_": "n_h", "_N_H_": "n_h", "N_H": "n_h", "[N/H]": "n_h",
    "__O_H_": "o_h", "_O_H_": "o_h", "O_H": "o_h", "[O/H]": "o_h",
    "__Na_H_": "na_h", "_Na_H_": "na_h", "Na_H": "na_h",
    "__Mg_H_": "mg_h", "_Mg_H_": "mg_h", "Mg_H": "mg_h",
    "__Al_H_": "al_h", "_Al_H_": "al_h", "Al_H": "al_h",
    "__Si_H_": "si_h", "_Si_H_": "si_h", "Si_H": "si_h",
    "__S_H_": "s_h", "_S_H_": "s_h", "S_H": "s_h",
    "__K_H_": "k_h", "_K_H_": "k_h", "K_H": "k_h",
    "__Ca_H_": "ca_h", "_Ca_H_": "ca_h", "Ca_H": "ca_h",
    "__Ti_H_": "ti_h", "_Ti_H_": "ti_h", "Ti_H": "ti_h",
    "__V_H_": "v_h", "_V_H_": "v_h", "V_H": "v_h",
    "__Mn_H_": "mn_h", "_Mn_H_": "mn_h", "Mn_H": "mn_h",
    "__Co_H_": "co_h", "_Co_H_": "co_h", "Co_H": "co_h",
    "__Ni_H_": "ni_h", "_Ni_H_": "ni_h", "Ni_H": "ni_h",
    "__Ce_H_": "ce_h", "_Ce_H_": "ce_h", "Ce_H": "ce_h",
    "__Nd_H_": "nd_h", "_Nd_H_": "nd_h", "Nd_H": "nd_h",
    # Radial velocity
    "VHELIO": "radial_velocity_kms", "VHELIO_AVG": "radial_velocity_kms",
    "HRV": "radial_velocity_kms",
    "RV": "gaia_radial_velocity_kms",
    "e_VHELIO": "radial_velocity_error_kms", "e_VHELIO_AVG": "radial_velocity_error_kms",
    "e_HRV": "radial_velocity_error_kms",
    "e_RV": "gaia_radial_velocity_error_kms",
    "s_HRV": "rv_scatter_kms", "VRSCATTER": "rv_scatter_kms", "VSCATTER": "rv_scatter_kms",
    # Photometry
    "Jmag": "j_mag", "Hmag": "h_mag", "Kmag": "k_mag", "Ksmag": "k_mag",
    "J": "j_mag", "H": "h_mag", "K": "k_mag",
    "e_Jmag": "j_mag_error", "e_Hmag": "h_mag_error", "e_Kmag": "k_mag_error",
    # SNR
    "SNR": "snr", "SNR_AVG": "snr",
    # Visit count
    "NVISITS": "n_visits", "Nvisits": "n_visits", "Nvis": "n_visits",
    # Targeting / flags
    "STARFLAG": "star_flag", "ASPCAPFLAG": "aspcap_flag", "EXTRATARG": "extra_targ",
    # Proper motion
    "pmRA": "pmra_mas_yr", "pmDE": "pmdec_mas_yr",
    "pmGLON": "pm_glon", "pmGLAT": "pm_glat",
    # Galactic coords
    "GLON": "glon_deg", "GLAT": "glat_deg",
    # Distance / parallax
    "Plx": "parallax_mas", "plx": "parallax_mas",
    "e_Plx": "parallax_error_mas", "e_plx": "parallax_error_mas",
    "Gmag": "gaia_g_mag", "BPmag": "gaia_bp_mag", "RPmag": "gaia_rp_mag",
    "rgeo": "distance_geo_pc", "rpgeo": "distance_photogeo_pc",
}

# ── Column descriptions ─────────────────────────────────────────────
COLUMN_DESCRIPTIONS = {
    "apogee_id": "APOGEE target identifier in 2MASS format '2MHHMMSS.ss+DDMMSS.s'; uniquely identifies each star",
    "twomass_id": "2MASS Point Source Catalog identifier; cross-reference to near-infrared JHK photometry",
    "gaia_source_id": "Gaia DR3 source identifier; enables cross-matching to parallaxes and optical photometry from Gaia",
    "ra_deg": "Right ascension in decimal degrees (ICRS J2000.0); range 0-360",
    "dec_deg": "Declination in decimal degrees (ICRS J2000.0); range -90 to +90",
    "glon_deg": "Galactic longitude in degrees (0-360); used for mapping Milky Way disk structure",
    "glat_deg": "Galactic latitude in degrees (-90 to +90); low |b| indicates disk/bulge targets",
    "teff_k": "Effective temperature in Kelvin from ASPCAP; APOGEE primarily targets red giants 3500-5500 K; null if fit failed",
    "teff_error_k": "1-sigma uncertainty on effective temperature in Kelvin",
    "logg": "Log surface gravity in cm/s2 (cgs dex); main-sequence: 4-5, giant: 1-3, red clump: ~2.5; null if fit failed",
    "logg_error": "1-sigma uncertainty on log g in dex",
    "fe_h": "Iron abundance [Fe/H] in dex relative to solar; thin disk: -0.2 to +0.4, thick disk: -0.5 to -1.0, halo: < -1.0; null if SNR too low",
    "fe_h_err": "1-sigma uncertainty on [Fe/H] in dex",
    "m_h": "Overall metallicity [M/H] in dex relative to solar from ASPCAP global fit",
    "m_h_error": "1-sigma uncertainty on [M/H] in dex",
    "alpha_m": "Alpha-element enhancement [alpha/M] in dex; high-alpha (> +0.1) = old thick disk or halo; null if fit failed",
    "alpha_m_error": "1-sigma uncertainty on [alpha/M] in dex",
    "radial_velocity_kms": "Heliocentric radial velocity in km/s averaged over visits; precision ~100 m/s; null if cross-correlation failed",
    "radial_velocity_error_kms": "1-sigma uncertainty on the mean heliocentric radial velocity in km/s",
    "rv_scatter_kms": "RMS scatter in radial velocity across visits in km/s; large scatter (> 1 km/s) indicates binary or pulsations",
    "j_mag": "2MASS J-band (1.24 um) apparent magnitude",
    "h_mag": "2MASS H-band (1.66 um) apparent magnitude; APOGEE observes in H-band",
    "k_mag": "2MASS Ks-band (2.16 um) apparent magnitude; extinction at K is ~10% of optical",
    "snr": "Combined signal-to-noise ratio per pixel; SNR > 100 needed for reliable abundances",
    "n_visits": "Number of individual APOGEE visits co-added; minimum 3 for most targets",
    "pmra_mas_yr": "Proper motion in RA direction in mas/yr (includes cos delta factor) from Gaia",
    "pmdec_mas_yr": "Proper motion in declination in mas/yr from Gaia",
    "parallax_mas": "Trigonometric parallax in milliarcseconds from Gaia; null if cross-match failed",
    "parallax_error_mas": "1-sigma uncertainty on the parallax in milliarcseconds from Gaia",
}

# Nucleosynthetic channel context for individual elements
ELEM_CONTEXT = {
    "C": "light element altered by CN-cycle mixing on the red giant branch",
    "CI": "neutral atomic carbon line; complementary to the molecular C measurement",
    "N": "light element enhanced by CN-cycle mixing; [C/N] ratio is a stellar age proxy for red giants",
    "O": "alpha element; dominant producer is core-collapse SNe; traces thick vs. thin disk",
    "NA": "odd-Z element; enhanced in AGB stars and some globular cluster stars",
    "MG": "alpha element; [Mg/Fe] is the cleanest alpha/iron ratio",
    "AL": "odd-Z element; anti-correlated with Mg in globular cluster stars",
    "SI": "alpha element; produced in hydrostatic oxygen burning and explosive nucleosynthesis",
    "S": "alpha element measured via weak H-band lines; traces similar evolution to Mg and O",
    "K": "odd-Z element; produced via neutron capture on Ar during explosive nucleosynthesis",
    "CA": "alpha element; used to validate APOGEE pipeline via comparison with optical surveys",
    "TI": "alpha element; two ionization states measured (Ti I and Ti II)",
    "TIII": "Ti II (singly ionized titanium); ionization equilibrium constrains surface gravity",
    "V": "iron-peak element produced in incomplete Si-burning",
    "CR": "iron-peak element; tracks Fe in most environments",
    "MN": "iron-peak element; predominantly from Type Ia supernovae; [Mn/Fe] increases with [Fe/H]",
    "CO": "iron-peak element; traces neutron excess during Si-burning",
    "NI": "iron-peak element; tightly correlated with Fe; [Ni/Fe] ~ 0 for most disk stars",
    "CE": "neutron-capture element (s-process) from low-mass AGB stars",
    "ND": "neutron-capture element (mixed r+s-process); tracks heavy element enrichment from AGB and NSM",
}


def main():
    print("Fetching APOGEE DR17 AllStar catalog from VizieR...")
    df = vizier_query(ADQL, timeout=600)
    print(f"  {len(df):,} rows fetched")

    # Only rename columns that actually exist
    rename_actual = {k: v for k, v in RENAME.items() if k in df.columns}
    df = df.rename(columns=rename_actual)

    # Drop unwanted columns
    drop_cols = [c for c in ["recno", "SimbadName", "More", "Simbad"] if c in df.columns]
    if drop_cols:
        df = df.drop(columns=drop_cols)

    # Snake-case any remaining columns not yet renamed
    def to_snake(name):
        if name == name.lower() and "_" in name:
            return name
        s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
        s = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s)
        s = re.sub(r"[-.\s]+", "_", s)
        return s.lower().strip("_")

    df.columns = [to_snake(c) for c in df.columns]

    # Integer columns
    for col in ["n_visits"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    # Deduplicate columns (keep first occurrence)
    df = df.loc[:, ~df.columns.duplicated()]

    # Identify abundance columns dynamically
    fe_abundance_cols = [c for c in df.columns if c.endswith("_fe") and c != "fe_h"]
    h_abundance_cols = [c for c in df.columns if c.endswith("_h") and c not in ("fe_h", "fe_h_err", "alpha_m")]

    # Add abundance column descriptions dynamically
    for col in sorted(fe_abundance_cols):
        elem = col.replace("_fe", "").upper()
        context = ELEM_CONTEXT.get(elem, "")
        desc = f"[{elem}/Fe] abundance ratio in dex relative to solar; null if SNR too low"
        if context:
            desc += f"; {context}"
        COLUMN_DESCRIPTIONS[col] = desc
    for col in sorted(h_abundance_cols):
        elem = col.replace("_h", "").upper()
        context = ELEM_CONTEXT.get(elem, "")
        desc = f"[{elem}/H] absolute abundance in dex relative to solar; null if SNR too low"
        if context:
            desc += f"; {context}"
        COLUMN_DESCRIPTIONS[col] = desc

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Sort by APOGEE ID if available
    if "apogee_id" in df.columns:
        df = df.sort_values("apogee_id").reset_index(drop=True)

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_with_teff = int(df["teff_k"].notna().sum()) if "teff_k" in df.columns else 0
    n_with_feh = int(df["fe_h"].notna().sum()) if "fe_h" in df.columns else 0
    teff_min = df["teff_k"].min() if "teff_k" in df.columns else 0
    teff_max = df["teff_k"].max() if "teff_k" in df.columns else 0
    feh_min = df["fe_h"].min() if "fe_h" in df.columns else 0
    feh_max = df["fe_h"].max() if "fe_h" in df.columns else 0

    all_abund_cols = fe_abundance_cols + h_abundance_cols
    n_elements = len(set(c.replace("_fe", "").replace("_h", "") for c in all_abund_cols))

    # Build numeric columns list for clean()
    abundance_num_cols = [
        "fe_h", "fe_h_err", "m_h", "m_h_error", "alpha_m", "alpha_m_error",
    ] + fe_abundance_cols + h_abundance_cols

    numeric_cols = [
        "ra_deg", "dec_deg", "teff_k", "teff_error_k", "logg", "logg_error",
        "radial_velocity_kms", "radial_velocity_error_kms", "rv_scatter_kms",
        "j_mag", "h_mag", "k_mag",
        "snr", "parallax_mas", "parallax_error_mas",
        "pmra_mas_yr", "pmdec_mas_yr", "glon_deg", "glat_deg",
    ] + abundance_num_cols

    quick_stats = f"""\
- **{n_total:,}** stars total
- **{n_with_teff:,}** with effective temperature
- **{n_with_feh:,}** with [Fe/H] metallicity
- **{n_elements}** individual abundance elements
- Teff range: **{teff_min:.0f}** -- **{teff_max:.0f}** K
- [Fe/H] range: **{feh_min:.2f}** to **{feh_max:.2f}** dex"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/apogee-dr17", split="train")
df = ds.to_pandas()

# Kiel diagram (Teff vs log g)
import matplotlib.pyplot as plt
valid = df.dropna(subset=["teff_k", "logg"])
plt.scatter(valid["teff_k"], valid["logg"], c=valid["fe_h"],
            s=0.1, alpha=0.3, cmap="coolwarm", vmin=-2, vmax=0.5)
plt.gca().invert_xaxis()
plt.gca().invert_yaxis()
plt.xlabel("Teff (K)")
plt.ylabel("log g (dex)")
plt.colorbar(label="[Fe/H]")
plt.title("APOGEE DR17 Kiel Diagram")

# [Mg/Fe] vs [Fe/H] — chemical evolution
if "mg_fe" in df.columns:
    valid = df.dropna(subset=["fe_h", "mg_fe"])
    plt.figure()
    plt.scatter(valid["fe_h"], valid["mg_fe"], s=0.1, alpha=0.2)
    plt.xlabel("[Fe/H] (dex)")
    plt.ylabel("[Mg/Fe] (dex)")
    plt.title("Chemical Evolution: [Mg/Fe] vs [Fe/H]")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="APOGEE DR17 Stellar Parameters & Abundances",
        description="""\
The APOGEE DR17 AllStar catalog provides high-resolution infrared (H-band) spectroscopic \
stellar parameters and 20+ individual chemical element abundances for stars across the \
Milky Way. This is the final data release from SDSS-IV APOGEE and represents the premier \
stellar chemical abundance catalog available today.

The Apache Point Observatory Galactic Evolution Experiment (APOGEE) is a large-scale, \
high-resolution (R ~ 22,500), near-infrared (H-band, 1.51-1.70 um) spectroscopic survey \
of Milky Way stellar populations. DR17 is the final release of SDSS-IV, containing the \
complete APOGEE-2 dataset with observations from both the Northern (APO 2.5m) and Southern \
(du Pont 2.5m at LCO) hemispheres.

APOGEE's choice of the near-infrared H-band allows it to observe stars deep into the \
Galactic plane, bulge, and heavily obscured star-forming regions that are invisible to \
optical surveys. The 20+ individual elemental abundances span multiple nucleosynthetic \
channels: alpha-elements (O, Mg, Si, S, Ca, Ti), iron-peak elements (Fe, Mn, Ni, Co, V, Cr), \
odd-Z elements (Na, Al, K), light elements (C, N), and neutron-capture elements (Ce, Nd). \
This chemical dimensionality makes APOGEE the premier dataset for chemical tagging and \
Galactic chemical evolution models.
""",
        tags=["space", "stars", "stellar", "spectroscopy", "chemical-abundances",
              "apogee", "sdss", "astronomy", "open-data", "tabular-data", "parquet"],
        source_url="https://vizier.cds.unistra.fr/viz-bin/VizieR?-source=III/286",
        license="other",
        license_name="sdss-data-use-policy",
        license_link="https://www.sdss4.org/dr17/data_access/",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e000191/GSFC_20171208_Archive_e000191~medium.jpg",
            "alt": "A youthful globular star cluster observed by the Hubble Space Telescope",
            "credit": "NASA/ESA/Hubble",
        },
        related_datasets=[
            "juliensimon/rave-dr6",
            "juliensimon/wolf-rayet-stars",
            "juliensimon/brown-dwarf-catalog",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[c for c in numeric_cols if c in df.columns],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="apogee_dr17.parquet",
            min_rows=500_000,
            expected_columns=["ra_deg", "dec_deg", "teff_k", "fe_h"],
            critical_columns=["ra_deg", "dec_deg", "teff_k"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Upload APOGEE DR17: {n_total:,} stars, {n_elements} elements",
        )
    print("Done.")


if __name__ == "__main__":
    main()
