#!/usr/bin/env python3
"""Fetch Milky Way globular cluster data from Baumgardt & Harris, merge, upload to HF.

Static dataset — no GitHub Actions workflow.

Sources:
  Baumgardt: https://people.smp.uq.edu.au/HolgerBaumgardt/globular/parameter.html
    Combined table with masses, structural/dynamical parameters for 167 clusters.
    Cite: Baumgardt & Hilker (2018), MNRAS 478, 1520; Baumgardt et al. (2023+)

  Harris (2010 edition): https://physics.mcmaster.ca/~harris/mwgc.dat
    Fixed-width catalog with metallicities, photometry, colors for 157 clusters.
    Cite: Harris (1996, AJ 112, 1487) — 2010 edition
"""

import re
import time

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

BAUMGARDT_URL = "https://people.smp.uq.edu.au/HolgerBaumgardt/globular/combined_table.txt"
HARRIS_URL = "https://physics.mcmaster.ca/~harris/mwgc.dat"

HF_REPO = "juliensimon/globular-star-clusters"
MIN_ROWS = 100


# ── Column descriptions for README schema table ─────────────────────────────
COLUMN_DESCRIPTIONS = {
    "name": "Cluster name (e.g. 'NGC 104', 'Pal 5'); Baumgardt name where available, Harris name otherwise",
    "ra_deg": "Right ascension of the cluster center in decimal degrees, J2000.0 epoch",
    "dec_deg": "Declination of the cluster center in decimal degrees, J2000.0 epoch",
    "distance_kpc": "Distance from the Sun (kpc; 1 kpc = 3260 light-years); derived from Baumgardt N-body fits to Gaia proper motions and HST data; typical range 2–100 kpc",
    "distance_err_kpc": "1-sigma uncertainty on the heliocentric distance (kpc) from the Baumgardt N-body model fits; null for Harris-only clusters",
    "distance_gc_kpc": "Distance from the Galactic center (kpc), assuming R☉ = 8.1 kpc; used to study spatial distribution and orbital properties",
    "distance_gc_err_kpc": "1-sigma uncertainty on the Galactocentric distance (kpc); null for Harris-only clusters",
    "metallicity_fe_h": "Iron abundance [Fe/H] in dex (log₁₀ of Fe/H relative to the Sun); dex = decimal exponent, so [Fe/H] = -1 means 1/10 solar iron; typical globular cluster range -2.5 to +0.5; lower values indicate older, more metal-poor clusters",
    "reddening_e_bv": "Foreground dust reddening E(B−V) in magnitudes from the Harris catalog; measures differential extinction between B and V bands due to interstellar dust along the line of sight; must be corrected before comparing intrinsic colors",
    "apparent_mag_v": "Apparent integrated V-band (550 nm) magnitude summing light from all cluster member stars; this is the total cluster flux, not a single star's brightness; typical range 5–16 mag; Baumgardt value where available, Harris otherwise",
    "absolute_mag_v": "Absolute integrated V-band magnitude (apparent magnitude corrected for distance and reddening); proxy for total stellar luminosity; typical range -5 to -10 mag; null for Baumgardt-only clusters",
    "distance_modulus_v": "V-band distance modulus μ = m_V − M_V (mag), where μ = 5 log₁₀(d/10 pc); includes reddening; null for Baumgardt-only clusters",
    "color_u_b": "Integrated U−B color index (mag) from Harris catalog; measures the integrated stellar population color; redder values indicate more dust reddening or more metal-rich/older populations; null for Baumgardt-only clusters",
    "color_b_v": "Integrated B−V color index (mag) from Harris catalog; measures the integrated stellar population color; redder values indicate more dust reddening or more metal-rich/older populations; null for Baumgardt-only clusters",
    "color_v_r": "Integrated V−R color index (mag) from Harris catalog; measures the integrated stellar population color; redder values indicate more dust reddening or more metal-rich/older populations; null for Baumgardt-only clusters",
    "color_v_i": "Integrated V−I color index (mag) from Harris catalog; measures the integrated stellar population color; redder values indicate more dust reddening or more metal-rich/older populations; null for Baumgardt-only clusters",
    "spectral_type": "Integrated spectral type of the cluster from the Harris catalog (e.g. 'F5', 'G0'); reflects the luminosity-weighted mean stellar temperature; null for most clusters",
    "ellipticity": "Projected ellipticity e = 1 − b/a where a and b are the major and minor axis lengths; 0 = perfectly circular, values up to ~0.3 for the most flattened clusters; from Harris catalog",
    "mass_msun": "Total dynamical mass (M☉) from Baumgardt N-body fits to velocity dispersion profiles; typical range 10⁴–10⁶ M☉; null for Harris-only clusters",
    "mass_err_msun": "1-sigma uncertainty on the total dynamical mass (M☉) from the N-body fit; null for Harris-only clusters",
    "mass_to_light_v": "Present-day V-band mass-to-light ratio (M☉/L☉); higher values indicate more mass in faint or dark remnants (neutron stars, black holes, white dwarfs); typical range 1–4 M☉/L☉",
    "mass_to_light_v_err": "1-sigma uncertainty on the V-band mass-to-light ratio (M☉/L☉)",
    "log_initial_mass_msun": "Log₁₀ of the initial (birth) cluster mass (M☉) estimated from the present-day mass and the modeled mass lost to stellar evolution and tidal stripping",
    "dissolution_time_gyr": "Predicted time until the cluster is fully disrupted by the Galactic tidal field (Gyr), based on current mass and orbit; null for Harris-only clusters",
    "core_radius_pc": "Core radius r_c (pc): the projected radius at which the surface brightness falls to half its central value in a King model; small values (~0.1 pc) indicate a dense or core-collapsed cluster",
    "half_light_radius_pc": "Projected (2D) half-light radius r_h (pc): the radius enclosing half the cluster's total V-band luminosity as seen on the sky; the most directly observable structural size parameter",
    "half_mass_radius_pc": "Three-dimensional half-mass radius r_hm (pc) from N-body fits: the radius enclosing half the total cluster mass in 3D; slightly larger than the projected half-light radius",
    "tidal_radius_pc": "Tidal (Jacobi) radius r_t (pc): the distance from the cluster center at which the Galactic tidal force equals the cluster's self-gravity; stars beyond this radius are unbound",
    "log_central_density_msun_pc3": "Log₁₀ of the central mass density (M☉/pc³) from N-body fits; core-collapsed clusters can exceed 10⁶ M☉/pc³",
    "log_half_mass_density_msun_pc3": "Log₁₀ of the mean mass density within the 3D half-mass radius (M☉/pc³); less sensitive to core-collapse than central density",
    "log_central_surface_density_msun_pc2": "Log₁₀ of the projected central surface mass density (M☉/pc²); the column density at the cluster center",
    "log_half_mass_surface_density_msun_pc2": "Log₁₀ of the mean projected surface mass density within the projected half-mass radius (M☉/pc²)",
    "log_half_mass_relaxation_time_yr": "Log₁₀ of the half-mass relaxation time (yr): the timescale on which two-body gravitational encounters redistribute energy and erase memory of initial conditions; clusters with log T_rh < 10 are dynamically evolved",
    "velocity_dispersion_km_s": "Central 1D line-of-sight velocity dispersion σ₀ (km/s) from N-body fits; related to cluster mass via the virial theorem; typical range 2–20 km/s; null for Harris-only clusters",
    "escape_velocity_km_s": "Central escape velocity v_esc (km/s) from the cluster potential; stars moving faster than this are unbound; typical range 10–50 km/s",
    "radial_velocity_km_s": "Heliocentric line-of-sight (systemic) radial velocity of the cluster (km/s) from Harris catalog; positive = receding; used to determine cluster orbits",
    "radial_velocity_err_km_s": "1-sigma uncertainty on the systemic radial velocity (km/s)",
    "anisotropy_central": "Velocity anisotropy parameter η at the center; η > 0 indicates radially biased orbits, η < 0 tangentially biased; isotropic = 0",
    "anisotropy_half_mass": "Velocity anisotropy parameter η at the half-mass radius; η > 0 indicates radially biased orbits, η < 0 tangentially biased; isotropic = 0",
    "rotation_amplitude_km_s": "Peak amplitude of internal cluster rotation (km/s) from Baumgardt fits; higher values indicate significant solid-body-like rotation",
    "rotation_probability_pct": "Statistical probability (%) that the detected rotation signal is real rather than noise; values > 95% are considered significant detections",
    "mass_function_slope": "Present-day stellar mass function slope α (where dN/dm ∝ m^α) over the fitted mass range; a steep negative slope (e.g. α ~ -2) means many low-mass stars; a flat or positive slope indicates preferential loss of low-mass stars through tidal stripping",
    "mass_function_slope_err": "1-sigma uncertainty on the present-day mass function slope α",
    "mass_function_low_msun": "Lower stellar mass limit (M☉) over which the mass function slope was fitted",
    "mass_function_high_msun": "Upper stellar mass limit (M☉) over which the mass function slope was fitted",
    "n_radial_velocity_stars": "Number of individual member stars with radial velocity measurements used in the Baumgardt N-body fit; larger samples yield more reliable dispersion profiles",
    "n_proper_motion_stars": "Number of individual member stars with proper motion measurements (mostly from Gaia DR3) used in the N-body fit",
    "core_collapsed": "True if the cluster has undergone core collapse (gravothermal catastrophe), as flagged in the Harris catalog; core-collapsed clusters show a cusp-like central brightness profile rather than a flat core",
    "concentration_harris": "King-model concentration parameter c = log₁₀(r_t / r_c), the log ratio of tidal to core radius; higher c means a more centrally concentrated cluster; null for Baumgardt-only clusters; core-collapsed clusters are assigned c = 2.5 by convention",
}


# ── Name normalisation ──────────────────────────────────────────────────────
# Baumgardt uses abbreviated names; Harris uses full names.
# Exact name mappings: Baumgardt name -> Harris name (lowercased)
_EXACT_ALIASES = {
    "eso 452-sc11": "1636-283",
    "rlgc 1": "glimpse01",
    "rlgc 2": "glimpse02",
}

# Prefix aliases: Baumgardt prefix -> Harris prefix
_PREFIX_ALIASES = {
    "ter ": "terzan ",
    "djor ": "djorg ",
    "2mass-gc": "2ms-gc",
    "eso 280-sc06": "eso-sc06",
}


def _normalise_name(name: str) -> str:
    """Normalise cluster name for matching."""
    s = name.strip().replace("_", " ").replace("  ", " ")
    s = re.sub(r"\s+", " ", s).lower().strip()
    # Exact aliases
    if s in _EXACT_ALIASES:
        return _EXACT_ALIASES[s]
    # Prefix aliases (longest match first)
    for short, full in sorted(_PREFIX_ALIASES.items(), key=lambda x: -len(x[0])):
        if s.startswith(short):
            s = full + s[len(short):]
            break
    return s


# ── Baumgardt parser ─────────────────────────────────────────────────────────
def fetch_baumgardt() -> pd.DataFrame:
    """Fetch and parse Baumgardt combined_table.txt (space-delimited)."""
    print("Fetching Baumgardt globular cluster database...")
    resp = requests.get(BAUMGARDT_URL, timeout=60)
    resp.raise_for_status()

    lines = resp.text.strip().splitlines()
    # Skip comment lines starting with #
    header_line = lines[0]
    data_lines = [l for l in lines if not l.startswith("#")]

    # Column names from the header (first # line)
    cols = header_line.lstrip("# ").split()
    # The columns are space-delimited; parse with fixed whitespace
    rows = []
    for line in data_lines:
        parts = line.split()
        if len(parts) >= len(cols):
            rows.append(parts[: len(cols)])
        elif len(parts) > 0:
            # Pad with None for missing trailing columns
            row = parts + [None] * (len(cols) - len(parts))
            rows.append(row)

    df = pd.DataFrame(rows, columns=cols)
    print(f"  {len(df)} clusters from Baumgardt")

    # Convert numeric columns
    numeric_cols = [c for c in df.columns if c != "Cluster"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


# ── Harris parser ────────────────────────────────────────────────────────────
def _float(s):
    """Parse float from fixed-width field, returning None for blanks."""
    s = s.strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _is_harris_data_line(line: str) -> bool:
    """Harris data lines start with a space followed by a letter or digit."""
    return len(line) > 2 and line[0] == " " and line[1].isalnum()


def fetch_harris() -> pd.DataFrame:
    """Fetch and parse the Harris (2010) catalog — Parts II and III."""
    print("Fetching Harris (2010 edition) catalog...")
    resp = requests.get(HARRIS_URL, timeout=60)
    resp.raise_for_status()

    lines = resp.text.splitlines()

    # Find section boundaries (lines starting with ___)
    separators = [i for i, l in enumerate(lines) if l.startswith("___")]
    # Part I: separators[0] .. separators[1]
    # Part II: separators[1] .. separators[2]
    # Part III: separators[2] .. separators[3]

    # ── Parse Part II for metallicity and photometry ─────────────────────
    # Fixed-width format (columns measured from actual data):
    # Col  0-12: ID (e.g. " NGC 104    ")
    # Col 12-19: [Fe/H]
    # Col 19-22: weight
    # Col 22-29: E(B-V)
    # Col 29-35: V_HB
    # Col 35-41: (m-M)V
    # Col 41-47: V_t
    # Col 47-55: M_V,t
    # Col 55-61: U-B
    # Col 61-67: B-V
    # Col 67-73: V-R
    # Col 73-79: V-I
    # Col 79-85: spt
    # Col 85-:   ellip
    part2_start = separators[1] + 1
    part2_end = separators[2]
    part2_rows = []
    for line in lines[part2_start:part2_end]:
        if not _is_harris_data_line(line):
            continue
        id_field = line[0:12].strip()
        if not id_field:
            continue
        row = {
            "harris_id": id_field,
            "metallicity_fe_h": _float(line[12:19]),
            "reddening_e_bv": _float(line[22:29]),
            "v_hb_mag": _float(line[29:35]),
            "distance_modulus_v": _float(line[35:41]),
            "harris_apparent_mag_v": _float(line[41:47]),
            "absolute_mag_v": _float(line[47:55]),
            "color_u_b": _float(line[55:61]),
            "color_b_v": _float(line[61:67]),
            "color_v_r": _float(line[67:73]),
            "color_v_i": _float(line[73:79]),
            "spectral_type": line[79:85].strip() if len(line) > 79 else None,
            "ellipticity": _float(line[85:]) if len(line) > 85 else None,
        }
        part2_rows.append(row)

    # ── Parse Part III for radial velocity, concentration, core collapse ─
    # Fixed-width format:
    # Col  0-14: ID (e.g. " NGC 104     ")
    # Col 14-22: v_r
    # Col 22-28: +/- (v_r err)
    # Col 28-38: v_LSR
    # Col 38-46: sig_v
    # Col 46-51: +/- (sig_v err)
    # Col 51-59: c (concentration, may include "c" flag for core-collapsed)
    part3_start = separators[2] + 1
    part3_end = separators[3]
    part3_rows = []
    for line in lines[part3_start:part3_end]:
        if not _is_harris_data_line(line):
            continue
        id_field = line[0:14].strip().rstrip("-").strip()
        if not id_field:
            continue

        c_str = line[51:59].strip() if len(line) > 59 else ""
        core_collapsed = False
        c_val = None
        if c_str:
            # "c" or "c:" flag means core-collapsed
            core_collapsed = "c" in c_str
            c_clean = c_str.replace("c:", "").replace("c", "").strip()
            c_val = _float(c_clean) if c_clean else None

        row = {
            "harris_id": id_field,
            "radial_velocity_km_s": _float(line[14:22]),
            "radial_velocity_err": _float(line[22:28]),
            "core_collapsed": core_collapsed,
            "harris_concentration_val": c_val,
        }
        part3_rows.append(row)

    df2 = pd.DataFrame(part2_rows)
    df3 = pd.DataFrame(part3_rows)

    # Merge Part II and III on harris_id
    harris = df2.merge(df3, on="harris_id", how="outer")
    print(f"  {len(harris)} clusters from Harris (2010 edition)")
    return harris


# ── Dataset description ──────────────────────────────────────────────────────
DESCRIPTION = """\
Comprehensive catalog of Milky Way globular clusters merging the Harris (2010) \
and Baumgardt databases. Includes positions, distances, metallicities, masses, \
velocity dispersions, structural parameters, and photometry.

Globular clusters are ancient, gravitationally bound collections of stars orbiting the Milky Way. \
They are among the oldest objects in the Galaxy (10--13 Gyr), with typical masses of \
10⁴--10⁶ M☉ and half-light radii of a few parsecs. Their metallicities, dynamics, \
and spatial distribution encode the formation and assembly history of the Milky Way.

This dataset combines Harris (2010) photometric and chemical data with Baumgardt's dynamical \
parameters derived from N-body fits to modern astrometric and spectroscopic data, providing \
the most complete per-cluster view available.

Globular clusters formed in the early universe, within the first few billion years after the \
Big Bang, and their metallicity distribution preserves a fossil record of the chemical \
enrichment conditions at that epoch. The bimodal metallicity distribution observed in many \
galaxies -- with a metal-poor peak near [Fe/H] ~ -1.5 and a metal-rich peak near \
[Fe/H] ~ -0.5 -- is widely interpreted as evidence for two distinct formation channels: \
an in-situ population formed during the early collapse of the proto-Galaxy, and an accreted \
population brought in by satellite galaxies that were subsequently tidally disrupted. The \
combination of metallicity, age, and orbital parameters in this catalog enables assignment \
of individual clusters to these formation channels, linking them to specific accretion \
events identified in the Gaia era such as the Gaia-Enceladus/Sausage merger and the \
Sequoia and Helmi streams.

The dynamical parameters from the Baumgardt database are derived from sophisticated N-body \
models fit simultaneously to Gaia proper motion profiles and HST/ground-based velocity \
dispersion profiles. These fits yield not only total masses but also the internal mass \
function slope, which encodes the degree to which a cluster has been stripped of its \
low-mass stars by two-body relaxation and tidal interactions. Clusters with flat or \
inverted mass functions have lost a large fraction of their initial low-mass population, \
while those retaining steep mass functions are dynamically younger. The dissolution \
timescale provided in this catalog predicts how long each cluster will survive before \
being fully disrupted by the Galactic tidal field.

Core-collapsed clusters -- flagged in this catalog from the Harris compilation -- represent \
systems that have undergone gravothermal catastrophe, a runaway contraction of the core \
driven by the negative heat capacity of self-gravitating systems. In these clusters, the \
core has contracted to a cusp-like density profile sustained by binary star heating, and \
the central density can exceed 10^6 solar masses per cubic parsec. The structural parameters \
(core radius, half-light radius, tidal radius, concentration) together with the velocity \
dispersion and anisotropy profiles provide a complete dynamical portrait of each cluster, \
suitable for comparison with theoretical models and numerical simulations.
"""


def main():
    baumgardt = fetch_baumgardt()
    time.sleep(1)
    harris = fetch_harris()

    # ── Normalise names for merging ──────────────────────────────────────
    baumgardt["_merge_key"] = baumgardt["Cluster"].apply(
        lambda x: _normalise_name(str(x))
    )
    harris["_merge_key"] = harris["harris_id"].apply(
        lambda x: _normalise_name(str(x))
    )

    # Merge: Baumgardt is primary (more clusters, better data), Harris supplements
    df = baumgardt.merge(harris, on="_merge_key", how="outer", indicator=True)

    n_both = (df["_merge"] == "both").sum()
    n_baumgardt_only = (df["_merge"] == "left_only").sum()
    n_harris_only = (df["_merge"] == "right_only").sum()
    print(f"  Merge: {n_both} matched, {n_baumgardt_only} Baumgardt-only, {n_harris_only} Harris-only")

    # Use Baumgardt name where available, else Harris
    df["name"] = df["Cluster"].fillna(df["harris_id"])
    # Clean underscores from Baumgardt names
    df["name"] = df["name"].str.replace("_", " ")

    # ── Build clean output columns ───────────────────────────────────────
    out = pd.DataFrame()
    out["name"] = df["name"]
    out["ra_deg"] = df["RA"].astype(float, errors="ignore")
    out["dec_deg"] = df["DEC"].astype(float, errors="ignore")

    # Distance (Baumgardt R_Sun in kpc)
    out["distance_kpc"] = df["R_Sun"]
    out["distance_err_kpc"] = df["DRSun"]
    out["distance_gc_kpc"] = df["R_GC"]
    out["distance_gc_err_kpc"] = df["DRGC"]

    # Harris metallicity and photometry
    out["metallicity_fe_h"] = df["metallicity_fe_h"]
    out["reddening_e_bv"] = df["reddening_e_bv"]
    # Baumgardt V mag, fall back to Harris for Harris-only clusters
    out["apparent_mag_v"] = df["V"].combine_first(df.get("harris_apparent_mag_v"))
    out["absolute_mag_v"] = df["absolute_mag_v"]
    out["distance_modulus_v"] = df["distance_modulus_v"]
    out["color_u_b"] = df["color_u_b"]
    out["color_b_v"] = df["color_b_v"]
    out["color_v_r"] = df["color_v_r"]
    out["color_v_i"] = df["color_v_i"]
    out["spectral_type"] = df["spectral_type"]
    out["ellipticity"] = df["ellipticity"]

    # Baumgardt mass and dynamics
    out["mass_msun"] = df["Mass"]
    out["mass_err_msun"] = df["DM"]
    out["mass_to_light_v"] = df["M/L_V"]
    out["mass_to_light_v_err"] = df["DM/L"]
    out["log_initial_mass_msun"] = df["lg(Mini)"]
    out["dissolution_time_gyr"] = df["T_Diss"]

    # Structural parameters (Baumgardt)
    out["core_radius_pc"] = df["rc"]
    out["half_light_radius_pc"] = df["rh,l"]
    out["half_mass_radius_pc"] = df["rh,m"]
    out["tidal_radius_pc"] = df["rt"]

    # Density
    out["log_central_density_msun_pc3"] = df["rho_c"]
    out["log_half_mass_density_msun_pc3"] = df["rho_h,m"]
    out["log_central_surface_density_msun_pc2"] = df["sig_c"]
    out["log_half_mass_surface_density_msun_pc2"] = df["sig_h,m"]

    # Relaxation time
    out["log_half_mass_relaxation_time_yr"] = df["lg(Trh)"]

    # Kinematics
    out["velocity_dispersion_km_s"] = df["sig0"]
    out["escape_velocity_km_s"] = df["vesc"]
    out["radial_velocity_km_s"] = df["radial_velocity_km_s"]
    out["radial_velocity_err_km_s"] = df["radial_velocity_err"]
    out["anisotropy_central"] = df["etac"]
    out["anisotropy_half_mass"] = df["etah"]
    out["rotation_amplitude_km_s"] = df["A_Rot"]
    out["rotation_probability_pct"] = df["P_Rot"]

    # Mass function
    out["mass_function_slope"] = df["MF"]
    out["mass_function_slope_err"] = df["Delta_MF"]
    out["mass_function_low_msun"] = df["M_Low"]
    out["mass_function_high_msun"] = df["M_High"]

    # Observation counts (Baumgardt)
    out["n_radial_velocity_stars"] = df["N_RV"]
    out["n_proper_motion_stars"] = df["N_PM"]

    # Harris structural extras
    out["core_collapsed"] = df.get("core_collapsed")
    out["concentration_harris"] = df.get("harris_concentration_val")

    # Convert numeric columns
    for col in out.columns:
        if col not in ("name", "spectral_type", "core_collapsed"):
            out[col] = pd.to_numeric(out[col], errors="coerce")

    # Convert core_collapsed to proper bool
    if "core_collapsed" in out.columns:
        out["core_collapsed"] = out["core_collapsed"].fillna(False).astype(bool)

    # Keep only columns with descriptions
    out = out[[c for c in out.columns if c in COLUMN_DESCRIPTIONS]]

    # Sort by name
    out = out.sort_values("name").reset_index(drop=True)

    # ── Stats for README ─────────────────────────────────────────────────
    n_total = len(out)
    n_with_mass = int(out["mass_msun"].notna().sum())
    n_with_feh = int(out["metallicity_fe_h"].notna().sum())
    n_with_vdisp = int(out["velocity_dispersion_km_s"].notna().sum())
    n_with_rv = int(out["radial_velocity_km_s"].notna().sum())
    n_cc = int(out["core_collapsed"].sum()) if "core_collapsed" in out.columns else 0
    mass_min = out["mass_msun"].min()
    mass_max = out["mass_msun"].max()
    feh_min = out["metallicity_fe_h"].min()
    feh_max = out["metallicity_fe_h"].max()

    print(f"\n  Final catalog: {n_total} globular clusters")
    print(f"  {n_with_mass} with mass, {n_with_feh} with [Fe/H], {n_with_vdisp} with velocity dispersion")
    print(f"  {n_cc} core-collapsed")

    quick_stats = f"""\
- **{n_total}** Milky Way globular clusters
- **{n_with_mass}** with dynamical mass estimates ({mass_min:.2e}–{mass_max:.2e} M☉)
- **{n_with_feh}** with metallicity measurements ({feh_min:.2f} to {feh_max:.2f} dex)
- **{n_with_vdisp}** with central velocity dispersions
- **{n_cc}** identified as core-collapsed"""

    usage = """\
```python
from datasets import load_dataset
import matplotlib.pyplot as plt

ds = load_dataset("juliensimon/globular-star-clusters", split="train")
df = ds.to_pandas()

# Most massive clusters
massive = df.nlargest(10, "mass_msun")[["name", "mass_msun", "metallicity_fe_h"]]

# Metal-poor vs metal-rich populations
metal_poor = df[df["metallicity_fe_h"] < -1.5]
metal_rich = df[df["metallicity_fe_h"] >= -1.5]

# Core-collapsed clusters
cc = df[df["core_collapsed"]]

# Mass-metallicity relation
plt.scatter(df["metallicity_fe_h"], df["mass_msun"].apply(lambda x: x if x else None))
plt.xlabel("[Fe/H]"); plt.ylabel("Mass (M☉)"); plt.yscale("log")
plt.title("Globular Cluster Mass vs Metallicity")
plt.tight_layout()
plt.show()
```"""

    # ── Publish via Pipeline ─────────────────────────────────────────────
    with Pipeline(
        repo=HF_REPO,
        pretty_name="Milky Way Globular Star Clusters",
        description=DESCRIPTION,
        tags=["space", "globular-clusters", "stars", "milky-way", "astronomy",
              "open-data", "tabular-data", "parquet"],
        source_url="https://people.smp.uq.edu.au/HolgerBaumgardt/globular/",
        task_categories=["tabular-classification", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-67ac2ada12aceb39f8feca3b",
        banner={
            "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e000191/GSFC_20171208_Archive_e000191~medium.jpg",
            "alt": "A youthful globular star cluster observed by Hubble",
            "credit": "NASA/ESA/Hubble",
        },
        related_datasets=[
            "juliensimon/open-star-clusters",
            "juliensimon/stellar-streams",
            "juliensimon/pulsar-catalog",
        ],
    ) as p:
        p.publish(
            out,
            filename="globular_star_clusters.parquet",
            min_rows=MIN_ROWS,
            expected_columns=[
                "name", "ra_deg", "dec_deg", "distance_kpc",
                "metallicity_fe_h", "mass_msun", "velocity_dispersion_km_s",
                "half_light_radius_pc", "core_radius_pc",
            ],
            critical_columns=["name", "ra_deg", "dec_deg"],
            max_null_pct=0.15,
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update globular star clusters: {n_total} clusters",
        )
    print("Done.")


if __name__ == "__main__":
    main()
