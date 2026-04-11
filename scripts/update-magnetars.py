#!/usr/bin/env python3
"""Fetch the McGill Online Magnetar Catalog and upload to HF.

Static dataset — no GitHub Actions workflow.

Source: http://www.physics.mcgill.ca/~pulsar/magnetar/main.html
CSV:    https://www.physics.mcgill.ca/~pulsar/magnetar/TabO1.csv
Cite:   Olausen & Kaspi (2014), ApJS 212, 6
"""

from io import StringIO

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

CSV_URL = "https://www.physics.mcgill.ca/~pulsar/magnetar/TabO1.csv"
HF_REPO = "juliensimon/mcgill-magnetar-catalog"

# ── Column mapping ───────────────────────────────────────────────────
RENAME = {
    "Name": "name",
    "Period": "period_s",
    "Period_Err": "period_err_s",
    "Pdot": "period_derivative",
    "Pdot_Err": "period_derivative_err",
    "B": "magnetic_field_g",
    "Edot": "spin_down_luminosity_erg_s",
    "Age": "characteristic_age_yr",
    "NH": "column_density_cm2",
    "NH_EUp": "column_density_err_up",
    "NH_EDn": "column_density_err_down",
    "Gamma": "photon_index",
    "Gamma_EUp": "photon_index_err_up",
    "Gamma_EDn": "photon_index_err_down",
    "kT": "blackbody_kt_kev",
    "kT_EUp": "blackbody_kt_err_up",
    "kT_EDn": "blackbody_kt_err_down",
    "kT2": "blackbody_kt2_kev",
    "kT2_EUp": "blackbody_kt2_err_up",
    "kT2_EDn": "blackbody_kt2_err_down",
    "Flux": "xray_flux_erg_cm2_s",
    "Flux_EUp": "xray_flux_err_up",
    "Flux_EDn": "xray_flux_err_down",
    "Dist": "distance_kpc",
    "Dist_EUp": "distance_err_up_kpc",
    "Dist_EDn": "distance_err_down_kpc",
    "Lumin": "xray_luminosity_erg_s",
    "Assoc": "association",
    "RA": "ra_hms",
    "Decl": "dec_dms",
    "RA_Err": "ra_err_arcsec",
    "Decl_Err": "dec_err_arcsec",
    "OptIR": "optical_ir_counterpart",
    "Bands": "observed_bands",
    "Activity": "activity_flags",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "name": "Magnetar designation (e.g. 'SGR 1806-20', '1E 2259+586'); SGR = Soft Gamma Repeater, AXP = Anomalous X-ray Pulsar; both classes are now understood to be magnetars",
    "type": "Historical source class: 'SGR' (detected via gamma-ray bursts) or 'AXP' (detected as anomalous X-ray pulsar); distinction is observational, not physical",
    "is_candidate": "True for unconfirmed magnetar candidates (marked with # in the McGill catalog); candidate status may change as new observations are published",
    "ra_hms": "Right ascension in sexagesimal format (HH MM SS.s), ICRS J2000",
    "dec_dms": "Declination in sexagesimal format (+/-DD MM SS.s), ICRS J2000",
    "ra_deg": "Right ascension in decimal degrees (ICRS J2000.0); derived from ra_hms",
    "dec_deg": "Declination in decimal degrees (ICRS J2000.0); derived from dec_dms",
    "ra_err_arcsec": "1-sigma positional uncertainty in RA in arcseconds; null for sources without a precise X-ray or radio position",
    "dec_err_arcsec": "1-sigma positional uncertainty in Dec in arcseconds; null for sources without a precise X-ray or radio position",
    "period_s": "Spin period in seconds; magnetars: 2-12 s (far slower than recycled millisecond pulsars); null for sources where timing has not been achieved",
    "period_err_s": "1-sigma uncertainty on spin period (s)",
    "period_derivative": "Spin-down rate dP/dt in s/s; magnetars: ~10^-11 s/s, among the fastest-spinning-down neutron stars; drives inferred magnetic field and characteristic age",
    "period_derivative_err": "1-sigma uncertainty on period derivative (s/s)",
    "magnetic_field_g": "Dipole surface magnetic field strength in Gauss, inferred as B ~ 3.2e19 * sqrt(P * Pdot); magnetars: 10^14-10^15 G, roughly 1000x stronger than normal pulsars; null if period or period derivative is unmeasured",
    "magnetic_field_g_is_limit": "True when the magnetic field value is an upper or lower limit rather than a detection",
    "spin_down_luminosity_erg_s": "Rotational energy loss rate Edot = -4*pi^2*I*Pdot/P^3 in erg/s; for magnetars typically 10^32-10^34 erg/s, lower than their observed X-ray luminosity (evidence for magnetic field powering)",
    "spin_down_luminosity_erg_s_is_limit": "True when the spin-down luminosity value is an upper or lower limit",
    "characteristic_age_yr": "Characteristic spin-down age tau = P/(2*Pdot) in years; magnetars: ~10^3-10^4 yr (very young neutron stars); this is an upper limit on true age for initially fast rotators",
    "characteristic_age_yr_is_limit": "True when the characteristic age value is an upper or lower limit",
    "column_density_cm2": "Interstellar hydrogen column density N_H in cm^-2, fit from soft X-ray absorption; used to estimate visual extinction and constrain distance; null if no X-ray spectrum available",
    "column_density_err_up": "Upper 1-sigma uncertainty on column density (cm^-2)",
    "column_density_err_down": "Lower 1-sigma uncertainty on column density (cm^-2)",
    "photon_index": "Photon index Gamma of the hard X-ray power-law spectral component (flux proportional to E^-Gamma); magnetars: Gamma ~ 2-4 in quiescence; null if power-law component not required by the spectrum",
    "photon_index_err_up": "Upper 1-sigma uncertainty on photon index",
    "photon_index_err_down": "Lower 1-sigma uncertainty on photon index",
    "blackbody_kt_kev": "Temperature kT in keV of the soft X-ray blackbody spectral component; magnetars: kT ~ 0.3-0.7 keV; null if spectrum not well-fitted by a blackbody",
    "blackbody_kt_err_up": "Upper 1-sigma uncertainty on blackbody kT (keV)",
    "blackbody_kt_err_down": "Lower 1-sigma uncertainty on blackbody kT (keV)",
    "blackbody_kt2_kev": "Temperature kT in keV of a second blackbody component, if required by the spectral fit; null for most sources",
    "blackbody_kt2_err_up": "Upper 1-sigma uncertainty on second blackbody kT (keV)",
    "blackbody_kt2_err_down": "Lower 1-sigma uncertainty on second blackbody kT (keV)",
    "xray_flux_erg_cm2_s": "Unabsorbed 2-10 keV X-ray flux in erg/cm^2/s from quiescent-state observations; magnetars: ~10^-12-10^-11 erg/cm^2/s; null for transient magnetars in quiescence below detection limits",
    "xray_flux_err_up": "Upper 1-sigma uncertainty on X-ray flux (erg/cm^2/s)",
    "xray_flux_err_down": "Lower 1-sigma uncertainty on X-ray flux (erg/cm^2/s)",
    "xray_flux_erg_cm2_s_is_limit": "True when the X-ray flux value is an upper or lower limit",
    "distance_kpc": "Distance in kpc; null for the majority of magnetars (reliable distances are rare — methods include HI absorption, SNR associations, and maser parallaxes)",
    "distance_err_up_kpc": "Upper 1-sigma uncertainty on distance (kpc)",
    "distance_err_down_kpc": "Lower 1-sigma uncertainty on distance (kpc)",
    "distance_kpc_is_limit": "True when the distance value is an upper or lower limit",
    "xray_luminosity_erg_s": "Quiescent X-ray luminosity in erg/s computed from flux and distance; magnetars: 10^33-10^36 erg/s; null where distance is unknown",
    "xray_luminosity_erg_s_is_limit": "True when the X-ray luminosity value is an upper or lower limit",
    "association": "Name of associated supernova remnant or star cluster (e.g. 'CTB 109', 'Westerlund 1'); null for isolated magnetars without identified associations",
    "optical_ir_counterpart": "Whether an optical or infrared counterpart has been detected; null if no counterpart search has been published",
    "observed_bands": "Observational coverage codes: H=hard X-ray (>10 keV), X=soft X-ray, O=optical, I=infrared, R=radio, G=gamma-ray; null if not tabulated",
    "activity_flags": "Burst/flare activity type codes: B=bursts, G=giant flare, F=flare, T=transient outburst, A=anti-glitch; null for sources with no recorded activity",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
All known magnetars — neutron stars with extreme magnetic fields (10^13-10^15 G) — from \
the McGill Online Magnetar Catalog. Includes spin parameters, magnetic field strengths, \
X-ray properties, and associations.

Magnetars are isolated neutron stars powered by the decay of their ultra-strong magnetic \
fields, rather than by rotation (like normal pulsars) or accretion. They manifest as Soft \
Gamma Repeaters (SGRs) and Anomalous X-ray Pulsars (AXPs), producing dramatic bursts and \
flares in X-rays and gamma-rays.

Magnetar magnetic fields — reaching 10^14 to 10^15 Gauss, a thousand times stronger than \
ordinary pulsars — are the strongest known in the universe. These fields exceed the quantum \
electrodynamic critical field at which the vacuum itself becomes birefringent. The decay of \
these colossal fields powers persistent X-ray emission at luminosities of 10^33-36 erg/s, \
far exceeding what rotational energy alone can supply. During outbursts, magnetars can \
release up to 10^46 erg in giant flares, rivaling the luminosity of the entire Galaxy.

The magnetar population bridges several areas of astrophysics. Their connection to fast \
radio bursts (FRBs) was dramatically confirmed in 2020 when SGR 1935+2154 emitted a \
millisecond radio burst bright enough to be detected at extragalactic distances. Magnetars \
are also candidate central engines for some gamma-ray bursts and super-luminous supernovae.
"""


def parse_ra_to_deg(ra_str):
    """Convert RA string 'HH MM SS.ss' to decimal degrees."""
    if pd.isna(ra_str) or not str(ra_str).strip():
        return None
    parts = str(ra_str).strip().split()
    if len(parts) < 3:
        return None
    try:
        h, m, s = float(parts[0]), float(parts[1]), float(parts[2])
        return (h + m / 60 + s / 3600) * 15.0
    except (ValueError, IndexError):
        return None


def parse_dec_to_deg(dec_str):
    """Convert Dec string '+DD MM SS.s' to decimal degrees."""
    if pd.isna(dec_str) or not str(dec_str).strip():
        return None
    s = str(dec_str).strip()
    sign = -1 if s.startswith("-") else 1
    s = s.lstrip("+-")
    parts = s.split()
    if len(parts) < 3:
        return None
    try:
        d, m, sec = float(parts[0]), float(parts[1]), float(parts[2])
        return sign * (d + m / 60 + sec / 3600)
    except (ValueError, IndexError):
        return None


def main():
    print("Fetching McGill Online Magnetar Catalog...")
    resp = requests.get(CSV_URL, timeout=30)
    resp.raise_for_status()

    df = pd.read_csv(StringIO(resp.text), quotechar='"')
    print(f"  {len(df)} magnetars in raw CSV")

    # Strip trailing ' #' from candidate names
    df["Name"] = df["Name"].str.strip()
    df["is_candidate"] = df["Name"].str.endswith("#")
    df["Name"] = df["Name"].str.rstrip(" #").str.strip()

    # Determine type from name prefix
    def classify(name):
        if name.startswith("SGR"):
            return "SGR"
        return "AXP"

    df["type"] = df["Name"].apply(classify)

    # Convert RA/Dec to decimal degrees
    df["ra_deg"] = df["RA"].apply(parse_ra_to_deg)
    df["dec_deg"] = df["Decl"].apply(parse_dec_to_deg)

    # Numeric columns — handle limit flags (<, >)
    for col in ["Period", "Period_Err", "Pdot", "Pdot_Err", "B", "Edot",
                "Age", "NH", "NH_EUp", "NH_EDn", "Gamma", "Gamma_EUp",
                "Gamma_EDn", "kT", "kT_EUp", "kT_EDn", "kT2", "kT2_EUp",
                "kT2_EDn", "Flux", "Flux_EUp", "Flux_EDn", "Dist",
                "Dist_EUp", "Dist_EDn", "Lumin", "RA_Err", "Decl_Err"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Build limit flag columns for key quantities
    for base, lim_col in [("B", "B_lim"), ("Edot", "Edot_lim"),
                           ("Age", "Age_lim"), ("Flux", "Flux_lim"),
                           ("Lumin", "Lumin_lim"), ("Dist", "Dist_lim")]:
        df[f"{base.lower()}_is_limit"] = df[lim_col].str.strip().isin(["<", ">"]) \
            if lim_col in df.columns else False

    # Rename to snake_case
    df = df.rename(columns=RENAME)

    # Map limit flag columns to final names
    limit_renames = {
        "b_is_limit": "magnetic_field_g_is_limit",
        "edot_is_limit": "spin_down_luminosity_erg_s_is_limit",
        "age_is_limit": "characteristic_age_yr_is_limit",
        "flux_is_limit": "xray_flux_erg_cm2_s_is_limit",
        "lumin_is_limit": "xray_luminosity_erg_s_is_limit",
        "dist_is_limit": "distance_kpc_is_limit",
    }
    df = df.rename(columns={k: v for k, v in limit_renames.items() if k in df.columns})

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Stats for README
    n_confirmed = int((~df["is_candidate"]).sum())
    n_candidate = int(df["is_candidate"].sum())
    n_sgr = int((df["type"] == "SGR").sum())
    n_axp = int((df["type"] == "AXP").sum())
    n_with_period = int(df["period_s"].notna().sum())
    n_with_bfield = int(df["magnetic_field_g"].notna().sum())
    n_with_assoc = int(df["association"].notna().sum() - (df["association"] == "").sum())
    period_min = df["period_s"].min()
    period_max = df["period_s"].max()
    bfield_min = df["magnetic_field_g"].min()
    bfield_max = df["magnetic_field_g"].max()

    quick_stats = f"""\
- **{len(df)}** magnetars ({n_confirmed} confirmed, {n_candidate} candidates)
- **{n_sgr}** Soft Gamma Repeaters, **{n_axp}** Anomalous X-ray Pulsars
- **{n_with_period}** with measured spin periods ({period_min:.2f}--{period_max:.1f} s)
- **{n_with_bfield}** with inferred magnetic fields ({bfield_min:.2e}--{bfield_max:.2e} G)
- **{n_with_assoc}** associated with supernova remnants or star clusters"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/mcgill-magnetar-catalog", split="train")
df = ds.to_pandas()

# Confirmed magnetars only
confirmed = df[~df["is_candidate"]]

# P-Pdot diagram (period vs. period derivative)
import matplotlib.pyplot as plt
import numpy as np

valid = confirmed.dropna(subset=["period_s", "period_derivative"])
plt.figure(figsize=(8, 6))
plt.scatter(valid["period_s"], valid["period_derivative"], s=50, c="crimson", edgecolors="k")
plt.xscale("log")
plt.yscale("log")
plt.xlabel("Spin Period (s)")
plt.ylabel("Period Derivative (s/s)")
plt.title("Magnetar P-Pdot Diagram")
plt.tight_layout()
plt.show()

# Strongest magnetic fields
strongest = confirmed.sort_values("magnetic_field_g", ascending=False).head(5)
print(strongest[["name", "type", "magnetic_field_g", "period_s"]])
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="McGill Online Magnetar Catalog",
        description=DESCRIPTION,
        tags=["space", "magnetars", "neutron-stars", "x-ray", "astronomy",
              "open-data", "tabular-data", "parquet"],
        source_url="http://www.physics.mcgill.ca/~pulsar/magnetar/main.html",
        task_categories=["tabular-classification", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-67ac2ada12aceb39f8feca3b",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA23863/PIA23863~small.jpg",
            "alt": "Illustration of different types of neutron stars",
            "credit": "NASA/JPL-Caltech",
        },
        related_datasets=[
            "juliensimon/pulsar-catalog",
            "juliensimon/gamma-ray-bursts",
            "juliensimon/fermi-4fgl-dr4",
        ],
    ) as p:
        df = p.clean(df, drop_mostly_null_threshold=0.95)
        p.publish(
            df,
            filename="mcgill_magnetar_catalog.parquet",
            min_rows=20,
            expected_columns=["name", "ra_deg", "dec_deg", "period_s",
                              "period_derivative", "magnetic_field_g",
                              "characteristic_age_yr", "xray_luminosity_erg_s",
                              "distance_kpc", "association"],
            critical_columns=["name", "ra_deg", "dec_deg"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update McGill magnetar catalog: {len(df)} magnetars",
        )
    print("Done.")


if __name__ == "__main__":
    main()
