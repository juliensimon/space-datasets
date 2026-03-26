#!/usr/bin/env python3
"""Fetch the McGill Online Magnetar Catalog and upload to HF.

Static dataset — no GitHub Actions workflow.

Source: http://www.physics.mcgill.ca/~pulsar/magnetar/main.html
CSV:    https://www.physics.mcgill.ca/~pulsar/magnetar/TabO1.csv
Cite:   Olausen & Kaspi (2014), ApJS 212, 6
"""

import subprocess
import tempfile
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset

CSV_URL = "https://www.physics.mcgill.ca/~pulsar/magnetar/TabO1.csv"
HF_REPO = "juliensimon/mcgill-magnetar-catalog"
MIN_ROWS = 20


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

    # Parse CSV — some fields have commas inside quoted strings (Assoc column)
    df = pd.read_csv(StringIO(resp.text), quotechar='"')
    print(f"  {len(df)} magnetars in raw CSV")

    # Strip trailing ' #' from candidate names
    df["Name"] = df["Name"].str.strip()

    # Mark candidates (names ending with #)
    df["is_candidate"] = df["Name"].str.endswith("#")
    df["Name"] = df["Name"].str.rstrip(" #").str.strip()

    # Determine type from name prefix
    def classify(name):
        if name.startswith("SGR"):
            return "SGR"
        elif name.startswith("AXP") or name.startswith("1E") or name.startswith("4U"):
            return "AXP"
        elif name.startswith("CXOU") or name.startswith("XTE"):
            return "AXP"
        elif name.startswith("1RXS") or name.startswith("3XMM"):
            return "AXP"
        elif name.startswith("PSR"):
            return "AXP"
        elif name.startswith("Swift"):
            return "AXP"  # Swift sources are mostly AXP-like
        elif name.startswith("AX"):
            return "AXP"
        else:
            return "unknown"

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

    # Rename to snake_case descriptive names
    df = df.rename(columns={
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
    })

    # Select and order final columns
    cols = [
        "name", "type", "is_candidate",
        "ra_hms", "dec_dms", "ra_deg", "dec_deg",
        "ra_err_arcsec", "dec_err_arcsec",
        "period_s", "period_err_s",
        "period_derivative", "period_derivative_err",
        "magnetic_field_g", "magnetic_field_g_is_limit",
        "spin_down_luminosity_erg_s", "spin_down_luminosity_erg_s_is_limit",
        "characteristic_age_yr", "characteristic_age_yr_is_limit",
        "column_density_cm2", "column_density_err_up", "column_density_err_down",
        "photon_index", "photon_index_err_up", "photon_index_err_down",
        "blackbody_kt_kev", "blackbody_kt_err_up", "blackbody_kt_err_down",
        "blackbody_kt2_kev", "blackbody_kt2_err_up", "blackbody_kt2_err_down",
        "xray_flux_erg_cm2_s", "xray_flux_err_up", "xray_flux_err_down",
        "xray_flux_erg_cm2_s_is_limit",
        "distance_kpc", "distance_err_up_kpc", "distance_err_down_kpc",
        "distance_kpc_is_limit",
        "xray_luminosity_erg_s", "xray_luminosity_erg_s_is_limit",
        "association",
        "optical_ir_counterpart", "observed_bands", "activity_flags",
    ]
    # Only keep columns that exist
    cols = [c for c in cols if c in df.columns]
    df = df[cols]

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

    # Validate
    check_dataset(
        df,
        "mcgill-magnetar-catalog",
        min_rows=MIN_ROWS,
        expected_columns=["name", "ra_deg", "dec_deg", "period_s",
                          "period_derivative", "magnetic_field_g",
                          "characteristic_age_yr", "xray_luminosity_erg_s",
                          "distance_kpc", "association"],
        critical_columns=["name", "ra_deg", "dec_deg"],
        max_null_pct=0.30,  # candidates have many nulls
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "mcgill_magnetar_catalog.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_kb = out.stat().st_size / 1024
        print(f"  {size_kb:.1f} KB parquet ({len(df)} rows, {len(df.columns)} columns)")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "McGill Online Magnetar Catalog"
language:
  - en
description: "All known magnetars (neutron stars with extreme magnetic fields) from the McGill Online Magnetar Catalog. Includes spin parameters, magnetic field strengths, X-ray properties, and associations."
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - magnetars
  - neutron-stars
  - x-ray
  - astronomy
  - open-data
  - tabular-data
size_categories:
  - n<1K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/mcgill_magnetar_catalog.parquet
    default: true
---

# McGill Online Magnetar Catalog

*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-67ac2ada12aceb39f8feca3b) collection on Hugging Face.*

All **{len(df)}** known magnetars — neutron stars with extreme magnetic fields (10\u00b9\u00b3-10\u00b9\u2075 G) — from the
[McGill Online Magnetar Catalog](http://www.physics.mcgill.ca/~pulsar/magnetar/main.html).
Currently **{n_confirmed}** confirmed and **{n_candidate}** candidates ({n_sgr} SGRs, {n_axp} AXPs).

## Dataset description

Magnetars are isolated neutron stars powered by the decay of their ultra-strong magnetic fields,
rather than by rotation (like normal pulsars) or accretion. They manifest as Soft Gamma Repeaters
(SGRs) and Anomalous X-ray Pulsars (AXPs), producing dramatic bursts and flares in X-rays and
gamma-rays.

This dataset contains the persistent (quiescent) properties of every known magnetar, including
spin period, period derivative, inferred dipolar magnetic field strength, characteristic age,
X-ray flux and luminosity, spectral parameters, distance, and SNR/cluster associations.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `name` | string | Source name (e.g. "SGR 1806-20", "1E 2259+586") |
| `type` | string | Classification: SGR or AXP |
| `is_candidate` | bool | True if unconfirmed magnetar candidate |
| `ra_hms` / `dec_dms` | string | Position in sexagesimal coordinates |
| `ra_deg` / `dec_deg` | float64 | Position in decimal degrees (J2000) |
| `ra_err_arcsec` / `dec_err_arcsec` | float64 | Position uncertainty (arcsec) |
| `period_s` | float64 | Spin period (seconds) |
| `period_err_s` | float64 | Period uncertainty |
| `period_derivative` | float64 | Spin-down rate (s/s) |
| `period_derivative_err` | float64 | Period derivative uncertainty |
| `magnetic_field_g` | float64 | Dipolar magnetic field strength (Gauss) |
| `spin_down_luminosity_erg_s` | float64 | Spin-down luminosity (erg/s) |
| `characteristic_age_yr` | float64 | Characteristic age P/(2 P-dot) (years) |
| `column_density_cm2` | float64 | Hydrogen column density N_H (cm\u207b\u00b2) |
| `photon_index` | float64 | Power-law photon index |
| `blackbody_kt_kev` | float64 | Blackbody temperature kT (keV) |
| `xray_flux_erg_cm2_s` | float64 | Unabsorbed 2-10 keV X-ray flux (erg/cm\u00b2/s) |
| `distance_kpc` | float64 | Distance (kpc) |
| `xray_luminosity_erg_s` | float64 | X-ray luminosity (erg/s) |
| `association` | string | Associated SNR or star cluster |
| `optical_ir_counterpart` | string | Optical/IR counterpart detected? |
| `observed_bands` | string | Bands with detections (H=hard X, X=soft X, O=optical, I=IR, R=radio, G=gamma) |
| `activity_flags` | string | Activity type codes (B=bursts, G=giant flare, F=flare, T=transient, A=anti-glitch) |
| `*_is_limit` | bool | True when corresponding value is an upper or lower limit |

## Quick stats

- **{len(df)}** magnetars ({n_confirmed} confirmed, {n_candidate} candidates)
- **{n_sgr}** Soft Gamma Repeaters, **{n_axp}** Anomalous X-ray Pulsars
- **{n_with_period}** with measured spin periods ({period_min:.2f}--{period_max:.1f} s)
- **{n_with_bfield}** with inferred magnetic fields ({bfield_min:.2e}--{bfield_max:.2e} G)
- **{n_with_assoc}** associated with supernova remnants or star clusters

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/mcgill-magnetar-catalog", split="train")
df = ds.to_pandas()

# Confirmed magnetars only
confirmed = df[~df["is_candidate"]]

# Strongest magnetic fields
strongest = confirmed.sort_values("magnetic_field_g", ascending=False).head(5)

# SGRs vs AXPs
sgrs = df[df["type"] == "SGR"]
axps = df[df["type"] == "AXP"]

# Magnetars associated with supernova remnants
with_snr = df[df["association"].notna() & (df["association"] != "")]
```

## Data source

[McGill Online Magnetar Catalog](http://www.physics.mcgill.ca/~pulsar/magnetar/main.html),
maintained by the McGill Pulsar Group. Please cite
[Olausen & Kaspi (2014), ApJS 212, 6](http://adsabs.harvard.edu/abs/2014ApJS..212....6O)
and refer to the catalog URL when using this data.

## Related datasets

- [pulsars](https://huggingface.co/datasets/juliensimon/pulsars) — ATNF Pulsar Catalogue (3,400+ pulsars)
- [gamma-ray-bursts](https://huggingface.co/datasets/juliensimon/gamma-ray-bursts) — HEASARC GRB catalog
- [fermi-4fgl](https://huggingface.co/datasets/juliensimon/fermi-4fgl) — Fermi LAT 4FGL source catalog

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Citation

```bibtex
@dataset{{mcgill_magnetar_catalog,
  author = {{Simon, Julien}},
  title = {{McGill Online Magnetar Catalog}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/mcgill-magnetar-catalog}},
  note = {{Based on the McGill Online Magnetar Catalog (Olausen \\& Kaspi 2014, ApJS 212, 6)}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", f"Update McGill magnetar catalog: {len(df)} magnetars"],
            check=True,
        )

    print(f"rows={len(df)}")
    print("Done.")


if __name__ == "__main__":
    main()
