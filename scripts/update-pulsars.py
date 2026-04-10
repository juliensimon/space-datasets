#!/usr/bin/env python3
"""Fetch ATNF Pulsar Catalogue from HEASARC and upload to HF."""

import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd
import requests

from dataset_images import banner_markdown, download_banner
from validate import check_dataset


TAP_URL = "https://heasarc.gsfc.nasa.gov/xamin/vo/tap/sync"
HF_REPO = "juliensimon/pulsar-catalog"

ADQL = """\
SELECT name, alt_name, ra, dec, period, period_dot, dm, flux_1400_mhz,
  companion_type, dm_distance, age, b_surf, e_dot, pulsar_type, pm_tot,
  discovery_date, assoc_object, binary_model
FROM atnfpulsar ORDER BY name\
"""


def fetch_catalog() -> pd.DataFrame:
    """Try CSV first, fall back to JSON, then pipe-delimited text."""
    # Attempt 1: CSV
    print("Fetching ATNF Pulsar Catalogue (CSV)...")
    resp = requests.get(TAP_URL, params={
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": ADQL,
    }, timeout=120)
    resp.raise_for_status()

    if not resp.text.strip().startswith("<?xml"):
        try:
            df = pd.read_csv(io.StringIO(resp.text))
            if len(df) > 100 and "name" in df.columns:
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
        df = df.loc[:, df.columns != ""]
        print(f"  Text parse OK: {len(df):,} rows")
        return df

    print("::error::All fetch formats failed")
    sys.exit(1)


def main():
    df = fetch_catalog()

    # Ensure numeric columns
    for col in ["ra", "dec", "period", "period_dot", "dm", "flux_1400_mhz",
                "dm_distance", "age", "b_surf", "e_dot", "pm_tot"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Derived columns
    df["is_millisecond"] = df["period"].apply(
        lambda x: True if pd.notna(x) and x < 0.03 else (False if pd.notna(x) else None)
    )
    # Clean empty strings to NaN for string columns from text format
    for col in ["companion_type", "binary_model", "pulsar_type", "alt_name", "assoc_object"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace({"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA})

    df["is_binary"] = df["binary_model"].notna()

    # Sort by name
    df = df.sort_values("name").reset_index(drop=True)

    print(f"  {len(df):,} pulsars total")

    n_msp = int(df["is_millisecond"].sum())
    n_binary = int(df["is_binary"].sum())
    print(f"  {n_msp:,} millisecond pulsars, {n_binary:,} in binaries")

    check_dataset(df, "pulsars", min_rows=2000,
        expected_columns=["name", "ra", "dec", "period", "dm", "is_millisecond", "is_binary"],
        critical_columns=["name", "period"])

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "pulsars.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        # Compute stats for README
        n_total = len(df)
        n_typed = df["pulsar_type"].notna().sum()
        median_period = df["period"].median()
        median_dm = df["dm"].median()

        banner_file = download_banner("pulsars", tmp)
        banner_md = banner_markdown("pulsars", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "ATNF Pulsar Catalogue"
language:
  - en
description: "Complete catalog of known radio pulsars from the ATNF Pulsar Catalogue, including spin parameters, dispersion measures, flux densities, and derived quantities. Updated monthly."
task_categories:
  - tabular-classification
tags:
  - space
  - pulsar
  - neutron-star
  - astronomy
  - radio
  - magnetar
  - atnf
  - open-data
  - tabular-data
  - parquet
size_categories:
  - 1K<n<10K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/pulsars.parquet
    default: true
---

# ATNF Pulsar Catalogue
{banner_md}
*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

![Update Pulsars](https://github.com/juliensimon/space-datasets/actions/workflows/update-pulsars.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.pulsars&label=updated&color=brightgreen)

Complete catalog of known radio pulsars from the
[ATNF Pulsar Catalogue](https://www.atnf.csiro.au/research/pulsar/psrcat/),
sourced via NASA HEASARC. Currently **{n_total:,}** pulsars ({n_msp:,} millisecond pulsars,
{n_binary:,} in binary systems).

## Dataset description

Pulsars are rapidly rotating neutron stars that emit beams of electromagnetic radiation.
The ATNF Pulsar Catalogue (Manchester et al. 2005) is the definitive reference catalog,
maintained by CSIRO. It includes spin period, period derivative, dispersion measure,
flux density, distance estimates, and derived quantities such as characteristic age,
surface magnetic field, and spin-down luminosity.

**Millisecond pulsars** (period < 30 ms) are ancient pulsars spun up by accretion
from a companion star. They are among the most precise clocks in the universe and are
used for pulsar timing arrays to detect gravitational waves.

The physics encoded in this catalog is remarkably rich. The spin period P and its time derivative P-dot together constrain the pulsar's magnetic field strength (B ~ 3.2e19 sqrt(P * P-dot) Gauss), characteristic age (tau ~ P / 2P-dot), and spin-down luminosity. Plotting P vs. P-dot produces the famous pulsar "island diagram," revealing distinct populations: normal pulsars clustered around P ~ 0.5 s with B ~ 10^12 G, millisecond pulsars in the lower-left corner with B ~ 10^8-9 G and ages exceeding the Hubble time, and magnetars in the upper-right with B > 10^14 G. The dispersion measure (DM) — the integrated column density of free electrons along the line of sight — serves as a proxy for distance when combined with Galactic electron density models such as NE2001 or YMW16.

Pulsars are natural laboratories for fundamental physics. Their extraordinary rotational stability enables tests of general relativity in strong-field regimes, particularly in relativistic binary systems where post-Keplerian orbital parameters can be measured with exquisite precision. The double pulsar PSR J0737-3039A/B provided the most stringent test of GR to date. Pulsar timing arrays — networks of millisecond pulsars monitored over decades — have recently achieved the first evidence for a nanohertz gravitational wave background, likely produced by supermassive black hole binaries. The catalog also underpins studies of neutron star equations of state, Galactic magnetic field structure (via rotation measures), and the interstellar medium.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `name` | string | Primary pulsar designation in the J2000 naming convention (e.g. "J0437−4715"); encodes approximate right ascension (HHMM) and declination (±DDMM) |
| `alt_name` | string | Alternative B1950 designation (e.g. "B0833−45" for Vela); many historically important pulsars are better known by their B-names; null for recently discovered pulsars |
| `ra` | float | Right ascension in decimal degrees (ICRS J2000.0) |
| `dec` | float | Declination in decimal degrees (ICRS J2000.0) |
| `period` | float | Barycentric spin period in seconds, corrected for Earth's orbital motion; normal pulsars: 0.1–5 s, millisecond pulsars: <0.03 s (fastest known: ~1.4 ms); the most precisely measured quantity for each pulsar |
| `period_dot` | float | First time derivative of the spin period (dimensionless, s/s); positive values indicate spin-down (energy loss); normal pulsars: ~10⁻¹⁵, millisecond pulsars: ~10⁻²⁰, magnetars: ~10⁻¹¹; null if timing baseline is too short |
| `dm` | float | Dispersion measure in pc/cm³ — the integrated column density of free electrons along the line of sight; used with Galactic electron density models (NE2001, YMW16) to estimate distance; higher DM implies greater distance or denser intervening medium |
| `flux_1400_mhz` | float | Mean radio flux density at 1400 MHz in milliJansky (mJy); most pulsars: 0.1–10 mJy; null for pulsars not detected at this frequency or measured only at other frequencies |
| `companion_type` | string | Classification of the binary companion star when present: "NS" (neutron star), "WD" (white dwarf), "MS" (main sequence), "He" (helium white dwarf), "UL" (ultra-light/planet-mass); null for isolated pulsars |
| `dm_distance` | float | Distance estimate in kiloparsecs derived from the dispersion measure using a Galactic free-electron density model; typical uncertainty ~20–30%; null if DM is unmeasured |
| `age` | float | Characteristic spin-down age in years, defined as τ = P / (2Ṗ); an upper limit on true age since it assumes the pulsar was born spinning infinitely fast; normal pulsars: 10⁴–10⁸ yr, millisecond pulsars: often exceed the Hubble time |
| `b_surf` | float | Estimated surface dipole magnetic field strength in Gauss, derived as B = 3.2×10¹⁹ √(P·Ṗ); magnetars: 10¹⁴–10¹⁵ G, normal pulsars: 10¹²–10¹³ G, millisecond pulsars (recycled): 10⁸–10⁹ G; null if period_dot is unavailable |
| `e_dot` | float | Spin-down luminosity (rotational energy loss rate) in erg/s, defined as Ė = −4π²Iİ/P³ where I ~ 10⁴⁵ g cm² is the moment of inertia; ranges from ~10³⁰ to ~10³⁸ erg/s; the Crab pulsar has Ė ~ 5×10³⁸ erg/s |
| `pulsar_type` | string | Physical classification: "PSR" (radio pulsar), "SGR" (soft gamma repeater / magnetar), "AXP" (anomalous X-ray pulsar / magnetar), "XINS" (X-ray isolated neutron star), "RRAT" (rotating radio transient emitting sporadic bursts); null for unclassified sources |
| `pm_tot` | float | Total proper motion in mas/yr (milliarcseconds per year), combining RA and Dec components; pulsars have high space velocities (median ~200 km/s) due to natal supernova kicks; null if astrometric solution is unavailable |
| `discovery_date` | int | Year of discovery publication; ranges from 1967 (first pulsar, CP 1919) to present |
| `assoc_object` | string | Astrophysical associations such as supernova remnant (SNR), globular cluster name, or X-ray source; important for age and formation history; null for isolated field pulsars with no known association |
| `binary_model` | string | Orbital dynamics model used to fit the binary system (e.g. "BT" for Blandford-Teukolsky, "DD" for Damour-Deruelle, "ELL1" for near-circular orbits); null for isolated (non-binary) pulsars |
| `is_millisecond` | bool | Derived flag: True if period < 30 ms, indicating a recycled pulsar spun up by accretion from a companion; millisecond pulsars are among the most stable clocks in the universe and anchor pulsar timing arrays |
| `is_binary` | bool | Derived flag: True if binary_model is non-null, indicating the pulsar has a detected orbital companion |

## Quick stats

- **{n_total:,}** pulsars
- **{n_msp:,}** millisecond pulsars (period < 30 ms)
- **{n_binary:,}** binary pulsars
- Median period: **{median_period:.4f}** s
- Median DM: **{median_dm:.1f}** pc/cm^3

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/pulsar-catalog", split="train")
df = ds.to_pandas()

# Millisecond pulsars
msp = df[df["is_millisecond"] == True]
print(f"{{len(msp):,}} millisecond pulsars")

# Binary pulsars
binaries = df[df["is_binary"] == True]
print(f"{{len(binaries):,}} in binary systems")

# Period-period derivative diagram (P-Pdot)
import matplotlib.pyplot as plt
valid = df.dropna(subset=["period", "period_dot"])
valid = valid[valid["period_dot"] > 0]
plt.scatter(valid["period"], valid["period_dot"], s=1, alpha=0.5)
plt.xscale("log"); plt.yscale("log")
plt.xlabel("Period (s)")
plt.ylabel("Period derivative (s/s)")
plt.title("P-Pdot Diagram")
```

## Data source

All data comes from the [ATNF Pulsar Catalogue](https://www.atnf.csiro.au/research/pulsar/psrcat/)
(Manchester, R. N., Hobbs, G. B., Teoh, A. & Hobbs, M., 2005, AJ, 129, 1993),
accessed via NASA HEASARC TAP service.

## Update schedule

Monthly (1st Monday at 18:00 UTC) via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [gamma-ray-bursts](https://huggingface.co/datasets/juliensimon/gamma-ray-bursts) — Fermi GBM Gamma-Ray Burst Catalog
- [space-track-satcat](https://huggingface.co/datasets/juliensimon/space-track-satcat) — NORAD Satellite Catalog
- [solar-flare-index](https://huggingface.co/datasets/juliensimon/solar-flare-events) — Solar flare observations

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/pulsar-catalog) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{pulsar_catalog,
  author = {{Simon, Julien}},
  title = {{ATNF Pulsar Catalogue}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/pulsar-catalog}},
  note = {{Based on ATNF Pulsar Catalogue (Manchester et al. 2005) via NASA HEASARC}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update pulsar catalog: {n_total:,} pulsars"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={len(df)}\n")
    print("Done.")


if __name__ == "__main__":
    main()
