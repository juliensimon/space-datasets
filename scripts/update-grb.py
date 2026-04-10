#!/usr/bin/env python3
"""Fetch Fermi GBM Gamma-Ray Burst Catalog from HEASARC and upload to HF."""

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
HF_REPO = "juliensimon/gamma-ray-bursts"

ADQL = """\
SELECT name, trigger_time, ra, dec, t90, t90_error, t50, t50_error,
  fluence, fluence_error, flux_256, pflx_best_fitting_model,
  flnc_band_ampl, flnc_band_epeak, flnc_band_alpha, flnc_band_beta
FROM fermigbrst ORDER BY trigger_time DESC\
"""


def fetch_catalog() -> pd.DataFrame:
    """Try CSV first, fall back to JSON, then pipe-delimited text."""
    # Attempt 1: CSV
    print("Fetching Fermi GBM catalog (CSV)...")
    resp = requests.get(TAP_URL, params={
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": ADQL,
    }, timeout=120)
    resp.raise_for_status()

    try:
        df = pd.read_csv(io.StringIO(resp.text))
        if len(df) > 100 and "name" in df.columns:
            print(f"  CSV parse OK: {len(df):,} rows")
            return df
    except Exception as e:
        print(f"  CSV parse failed: {e}")

    # Attempt 2: JSON
    print("Retrying with FORMAT=json...")
    resp = requests.get(TAP_URL, params={
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "json", "QUERY": ADQL,
    }, timeout=120)
    resp.raise_for_status()

    try:
        data = resp.json()
        # VOTable JSON format: metadata + data arrays
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

    # Ensure numeric columns (trigger_time is MJD, convert below)
    for col in ["trigger_time", "ra", "dec", "t90", "t90_error", "t50", "t50_error",
                "fluence", "fluence_error", "flux_256",
                "flnc_band_ampl", "flnc_band_epeak", "flnc_band_alpha", "flnc_band_beta"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Convert trigger_time from MJD to datetime
    # MJD epoch: 1858-11-17T00:00:00
    mjd_epoch = pd.Timestamp("1858-11-17")
    df["trigger_time"] = mjd_epoch + pd.to_timedelta(df["trigger_time"], unit="D")

    # Derived column: duration class (fundamental GRB classification)
    df["duration_class"] = df["t90"].apply(
        lambda x: "short" if pd.notna(x) and x < 2.0 else ("long" if pd.notna(x) else None)
    )

    # Sort by trigger_time DESC
    df = df.sort_values("trigger_time", ascending=False).reset_index(drop=True)

    print(f"  {len(df):,} GRBs total")

    check_dataset(df, "grb", min_rows=3000,
        expected_columns=["name", "trigger_time", "t90", "fluence"],
        critical_columns=["name", "trigger_time"])

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "grb.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        # Compute stats for README
        n_total = len(df)
        n_short = int((df["duration_class"] == "short").sum())
        n_long = int((df["duration_class"] == "long").sum())
        date_min = df["trigger_time"].min()
        date_max = df["trigger_time"].max()
        date_range = f"{date_min:%Y-%m-%d} to {date_max:%Y-%m-%d}"

        brightest_idx = df["fluence"].idxmax()
        brightest_name = df.loc[brightest_idx, "name"] if pd.notna(brightest_idx) else "N/A"
        brightest_fluence = df.loc[brightest_idx, "fluence"] if pd.notna(brightest_idx) else 0

        banner_file = download_banner("grb", tmp)
        banner_md = banner_markdown("grb", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Fermi GBM Gamma-Ray Burst Catalog"
language:
  - en
description: "GRB detections from Fermi Gamma-ray Burst Monitor with duration, flux, and spectral parameters"
task_categories:
  - tabular-classification
tags:
  - space
  - gamma-ray-burst
  - grb
  - fermi
  - nasa
  - astronomy
  - high-energy
  - open-data
  - tabular-data
  - parquet
size_categories:
  - 1K<n<10K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/grb.parquet
    default: true
---

# Fermi GBM Gamma-Ray Burst Catalog
{banner_md}
*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

![Update GRB](https://github.com/juliensimon/space-datasets/actions/workflows/update-grb.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.grb&label=updated&color=brightgreen)

Complete catalog of gamma-ray bursts detected by the
[Fermi Gamma-ray Burst Monitor (GBM)](https://fermi.gsfc.nasa.gov/ssc/data/access/gbm/),
sourced from NASA HEASARC. Currently **{n_total:,}** GRBs ({n_short:,} short, {n_long:,} long).

## Dataset description

Gamma-ray bursts (GRBs) are the most energetic explosions in the universe. They come in
two classes based on duration: **short** GRBs (T90 < 2 s, from neutron star mergers) and
**long** GRBs (T90 >= 2 s, from massive star collapse). The Fermi GBM has been detecting
GRBs across the full unocculted sky since 2008.

This dataset includes duration measurements (T90, T50), fluence, peak flux, and Band
function spectral parameters for each burst.

The physical dichotomy between short and long GRBs reflects fundamentally different progenitor systems. Short GRBs (T90 < 2 s) arise from the coalescence of compact binary systems — neutron star-neutron star or neutron star-black hole mergers — as spectacularly confirmed by the joint gravitational-wave and electromagnetic detection of GRB 170817A / GW170817. Long GRBs (T90 > 2 s) are produced by the core collapse of massive Wolf-Rayet stars, where a newly formed black hole launches ultra-relativistic jets that punch through the stellar envelope. In both cases, the observed gamma-ray emission originates from internal shocks or magnetic dissipation within jets moving at Lorentz factors of 100-1000.

The Fermi GBM is one of the workhorses of modern GRB astronomy, detecting roughly 240 bursts per year across its 12 sodium iodide (NaI, 8 keV - 1 MeV) and 2 bismuth germanate (BGO, 200 keV - 40 MeV) detectors. Its near all-sky field of view (roughly 8 steradians unocculted) makes it the most prolific GRB detector currently operating. The Band function spectral parameters included here (amplitude, peak energy E_peak, and low/high-energy power-law indices alpha and beta) characterize the canonical non-thermal GRB spectrum and are essential for computing energetics, testing emission models, and calibrating the E_peak-E_iso (Amati) relation used as a cosmological distance indicator.

This catalog is a cornerstone for multi-messenger astrophysics: GBM triggers initiate rapid follow-up campaigns across the electromagnetic spectrum and provide temporal coincidence windows for searches in gravitational-wave and neutrino data from LIGO/Virgo/KAGRA and IceCube.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `name` | string | GRB designation encoding the discovery date and sequence letter (e.g. "GRB 170817A" = Aug 17 2017, first event that day); "GRB 170817A" is the electromagnetic counterpart to GW170817, the first confirmed neutron-star merger |
| `trigger_time` | datetime | UTC time of the GBM on-board trigger; converted from Modified Julian Date; precision ~milliseconds |
| `ra` | float | Right ascension of best-fit GRB position (ICRS J2000.0, degrees, 0–360); initial GBM localization uncertainty is several degrees; null if localization failed |
| `dec` | float | Declination of best-fit GRB position (ICRS J2000.0, degrees, −90 to +90); null if localization failed |
| `t90` | float | Duration containing 90% of the burst's total photon counts (seconds); short GRBs have T90 < 2 s (neutron star mergers), long GRBs have T90 > 2 s (massive star collapse); bimodal distribution separates two physically distinct progenitor populations; null for bursts with insufficient counts |
| `t90_error` | float | 1-sigma statistical uncertainty on T90 (seconds); null when T90 is not measured |
| `t50` | float | Duration containing the central 50% of burst counts (seconds); narrower than T90, less sensitive to faint extended emission; useful for comparing burst timescales across detectors |
| `t50_error` | float | 1-sigma statistical uncertainty on T50 (seconds); null when T50 is not measured |
| `fluence` | float | Total gamma-ray fluence integrated over the burst duration (erg/cm²; 1 erg = 10⁻⁷ J); proxy for apparent isotropic energy release; null when spectral fit did not converge |
| `fluence_error` | float | 1-sigma uncertainty on fluence (erg/cm²); null when fluence is not measured |
| `flux_256` | float | Peak photon flux measured on a 256 ms timescale (photons/cm²/s); determines detectability and is used in the logN-logP distribution; null when peak flux measurement failed |
| `pflx_best_fitting_model` | string | Name of the spectral model providing the best fit to the peak-flux time interval (e.g. "band", "comp", "plaw", "sbpl"); drives which set of spectral parameters is most reliable |
| `flnc_band_ampl` | float | Amplitude (normalization) of the Band function fit to the time-integrated (fluence) spectrum (photons/cm²/s/keV at pivot energy); null when the Band model is not the best fit or fit failed |
| `flnc_band_epeak` | float | Peak energy of the νFν spectrum from the Band function fit (keV); most GRBs fall between 100–2000 keV; correlates with isotropic luminosity (Amati relation); null when Band fit failed |
| `flnc_band_alpha` | float | Low-energy photon spectral index of the Band function (dimensionless); typically −1.5 to 0; values harder than −2/3 violate synchrotron line-of-death, constraining emission models; null when Band fit failed |
| `flnc_band_beta` | float | High-energy photon spectral index of the Band function (dimensionless); typically −3 to −2; describes the steep spectral cutoff above E_peak; null when Band fit failed or high-energy data insufficient |
| `duration_class` | string | Physical classification by T90: "short" (T90 < 2 s, compact binary merger progenitor) or "long" (T90 ≥ 2 s, massive star core collapse progenitor); null when T90 is unavailable |

## Quick stats

- **{n_total:,}** gamma-ray bursts
- **{n_short:,}** short GRBs, **{n_long:,}** long GRBs
- Date range: **{date_range}**
- Brightest burst: **{brightest_name}** (fluence {brightest_fluence:.2e} erg/cm^2)

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/gamma-ray-bursts", split="train")
df = ds.to_pandas()

# Short vs long GRBs
short = df[df["duration_class"] == "short"]
long = df[df["duration_class"] == "long"]
print(f"{{len(short):,}} short, {{len(long):,}} long GRBs")

# Brightest bursts
top = df.nlargest(10, "fluence")[["name", "trigger_time", "fluence", "t90"]]

# T90 distribution
import matplotlib.pyplot as plt
df["t90"].dropna().apply(lambda x: max(x, 1e-3)).hist(bins=50, log=True)
plt.xlabel("T90 (s)")
plt.title("GRB Duration Distribution")
```

## Data source

All data comes from the [Fermi GBM Burst Catalog](https://heasarc.gsfc.nasa.gov/W3Browse/fermi/fermigbrst.html)
hosted by NASA's High Energy Astrophysics Science Archive Research Center (HEASARC),
accessed via the TAP protocol.

## Update schedule

Weekly on Monday at 17:00 UTC via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [space-track-satcat](https://huggingface.co/datasets/juliensimon/space-track-satcat) — NORAD Satellite Catalog
- [solar-flare-index](https://huggingface.co/datasets/juliensimon/solar-flare-events) — Solar flare observations
- [near-earth-objects](https://huggingface.co/datasets/juliensimon/neo-close-approaches) — NEO close approaches

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/gamma-ray-bursts) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{gamma_ray_bursts,
  author = {{Simon, Julien}},
  title = {{Fermi GBM Gamma-Ray Burst Catalog}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/gamma-ray-bursts}},
  note = {{Based on NASA HEASARC Fermi GBM Burst Catalog data}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update GRB catalog: {n_total:,} bursts"
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
