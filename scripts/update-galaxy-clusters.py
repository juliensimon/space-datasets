#!/usr/bin/env python3
"""Fetch Planck PSZ2 Galaxy Cluster Catalog from HEASARC and upload to HF."""

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
HF_REPO = "juliensimon/galaxy-clusters"

ADQL = """\
SELECT name, ra, dec, lii, bii, redshift, redshift_source_name, mass_sz,
  mass_sz_pos_err, mass_sz_neg_err, y5r500, y5r500_error, snr,
  det_pipeline_codes
FROM plancksz2 ORDER BY name\
"""


def fetch_catalog() -> pd.DataFrame:
    """Try CSV first, fall back to JSON, then pipe-delimited text."""
    # Attempt 1: CSV
    print("Fetching Planck PSZ2 catalog (CSV)...")
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

    lines = [l for l in resp.text.strip().splitlines()
             if l.strip() and not l.startswith("-")]
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
    for col in ["ra", "dec", "lii", "bii", "redshift", "mass_sz",
                "mass_sz_pos_err", "mass_sz_neg_err", "y5r500", "y5r500_error", "snr"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    print(f"  {len(df):,} clusters total")

    n_with_z = int(df["redshift"].notna().sum()) if "redshift" in df.columns else 0
    print(f"  {n_with_z:,} with redshift")

    check_dataset(df, "galaxy-clusters", min_rows=1000,
        expected_columns=["name", "ra", "dec", "snr"],
        critical_columns=["name", "ra", "dec"])

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "galaxy-clusters.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        # Compute stats for README
        n_total = len(df)
        z_median = df["redshift"].median() if "redshift" in df.columns else 0
        z_max = df["redshift"].max() if "redshift" in df.columns else 0
        snr_median = df["snr"].median() if "snr" in df.columns else 0

        banner_file = download_banner("galaxy-clusters", tmp)
        banner_md = banner_markdown("galaxy-clusters", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Planck PSZ2 Galaxy Cluster Catalog"
language:
  - en
description: "Galaxy clusters detected by the Planck satellite via the Sunyaev-Zel'dovich effect with mass, redshift, and signal-to-noise"
task_categories:
  - tabular-regression
tags:
  - space
  - galaxy-cluster
  - planck
  - sz-effect
  - cosmology
  - astronomy
  - open-data
  - tabular-data
  - parquet
size_categories:
  - 1K<n<10K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/galaxy_clusters.parquet
    default: true
---

# Planck PSZ2 Galaxy Cluster Catalog
{banner_md}
*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

![Update Galaxy Clusters](https://github.com/juliensimon/space-datasets/actions/workflows/update-galaxy-clusters.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$["galaxy-clusters"]&label=updated&color=brightgreen)

Complete catalog of galaxy clusters detected by the
[Planck satellite](https://www.cosmos.esa.int/web/planck) via the Sunyaev-Zel'dovich (SZ)
effect, sourced via NASA HEASARC. Currently **{n_total:,}** clusters.

## Dataset description

Galaxy clusters are the largest gravitationally bound structures in the universe. The
Planck satellite detected them through the thermal Sunyaev-Zel'dovich effect: hot
intracluster gas distorts the cosmic microwave background spectrum. The PSZ2 catalog is
the second and final Planck SZ source catalog, based on the full mission data.

This dataset includes positions, redshifts, SZ-derived mass proxies, integrated SZ
signal, signal-to-noise ratio, and detection pipeline information.

Galaxy clusters occupy a unique position in cosmology: they sit at the intersection of structure formation theory and observational cosmology. As the most massive virialized objects in the universe, their abundance as a function of mass and redshift is exquisitely sensitive to the matter density parameter, the amplitude of density fluctuations (sigma_8), and the dark energy equation of state. Counting clusters at different epochs therefore provides independent constraints on cosmological parameters complementary to those from the CMB power spectrum, baryon acoustic oscillations, and Type Ia supernovae.

The thermal Sunyaev-Zel'dovich effect exploited by Planck arises when CMB photons inverse-Compton scatter off the hot electrons in the intracluster medium, which can reach temperatures of 10^7 to 10^8 K. This produces a characteristic spectral distortion -- a decrement below ~217 GHz and an increment above -- that is independent of redshift, making SZ surveys uniquely capable of detecting massive clusters at any distance. The integrated SZ signal (Y_5R500) is tightly correlated with total cluster mass, providing a nearly mass-limited sample that is essential for cluster cosmology.

The PSZ2 catalog has served as the definitive SZ-selected cluster sample for nearly a decade, anchoring studies of cluster scaling relations, gas physics, and the calibration of weak-lensing mass estimates. It also provides the reference sample for follow-up observations with X-ray telescopes (Chandra, XMM-Newton) and optical/infrared surveys that measure galaxy populations, velocity dispersions, and strong-lensing features within these massive structures.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `name` | string | Planck cluster designation in the format "PSZ2 GXXX.X±XX.X" (Galactic longitude and latitude encoded in the name) |
| `ra` | float | ICRS J2000.0 right ascension of the cluster center in degrees (0–360) |
| `dec` | float | ICRS J2000.0 declination of the cluster center in degrees (-90–+90) |
| `lii` | float | Galactic longitude of the cluster center in degrees (0–360) |
| `bii` | float | Galactic latitude of the cluster center in degrees (-90–+90) |
| `redshift` | float | Cluster spectroscopic or photometric redshift; null for ~30% of Planck clusters lacking optical confirmation |
| `redshift_source_name` | string | Survey or reference providing the redshift (e.g., "SDSS", "ACT", "SPT"); null if redshift is null |
| `mass_sz` | float | SZ-derived cluster mass M_SZ in units of 10^14 solar masses (i.e., multiply by 1e14 for M_sun); Planck clusters range ~1–15; null if Y_5R500 is unavailable |
| `mass_sz_pos_err` | float | Upper (positive) 1-sigma uncertainty on mass_sz in units of 10^14 solar masses; null if mass_sz is null |
| `mass_sz_neg_err` | float | Lower (negative) 1-sigma uncertainty on mass_sz in units of 10^14 solar masses; null if mass_sz is null |
| `y5r500` | float | Integrated Compton y-parameter measured within 5*R_500 in arcmin^2; dimensionless measure of total ICM thermal energy; low-scatter mass proxy; typical range 1e-4 to 1e-2 arcmin^2 |
| `y5r500_error` | float | 1-sigma uncertainty on Y_5R500 in arcmin^2; null if y5r500 is null |
| `snr` | float | Planck detection signal-to-noise ratio; catalog threshold SNR > 4.5; most massive clusters can reach SNR > 50 |
| `det_pipeline_codes` | string | Bitmask or code string indicating which of the three detection pipelines confirmed this cluster: MMF1 (matched multi-frequency filter 1), MMF3 (matched multi-frequency filter 3), PwS (PowellSnakes Bayesian algorithm) |

## Quick stats

- **{n_total:,}** galaxy clusters
- **{n_with_z:,}** with measured redshift (median z = {z_median:.3f}, max z = {z_max:.3f})
- Median detection SNR: **{snr_median:.1f}**

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/galaxy-clusters", split="train")
df = ds.to_pandas()

# Redshift distribution
z = df["redshift"].dropna()
print(f"{{len(z):,}} clusters with redshift, median z = {{z.median():.3f}}")

# Most massive clusters
top = df.nlargest(10, "mass_sz")[["name", "redshift", "mass_sz", "snr"]]

# Sky map in Galactic coordinates
import matplotlib.pyplot as plt
plt.scatter(df["lii"], df["bii"], c=df["snr"], s=3, cmap="viridis")
plt.colorbar(label="SNR")
plt.xlabel("Galactic longitude (deg)")
plt.ylabel("Galactic latitude (deg)")
plt.title("Planck PSZ2 Galaxy Clusters")
```

## Data source

All data comes from the [Planck PSZ2 Catalog](https://heasarc.gsfc.nasa.gov/W3Browse/all/plancksz2.html)
hosted by NASA's High Energy Astrophysics Science Archive Research Center (HEASARC),
accessed via the TAP protocol.

Original reference: Planck Collaboration, 2016, A&A, 594, A27.

## Update schedule

Quarterly (1st Monday of January, April, July, October at 19:30 UTC) via
[GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [supernova-remnants](https://huggingface.co/datasets/juliensimon/supernova-remnants) — Green's SNR Catalog
- [gamma-ray-bursts](https://huggingface.co/datasets/juliensimon/gamma-ray-bursts) — Fermi GBM GRB Catalog
- [exoplanets](https://huggingface.co/datasets/juliensimon/nasa-exoplanets) — NASA Exoplanet Archive

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/galaxy-clusters) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{galaxy_clusters,
  author = {{Simon, Julien}},
  title = {{Planck PSZ2 Galaxy Cluster Catalog}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/galaxy-clusters}},
  note = {{Based on Planck PSZ2 Catalog via NASA HEASARC}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update galaxy cluster catalog: {n_total:,} clusters"
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
