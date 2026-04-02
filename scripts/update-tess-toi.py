#!/usr/bin/env python3
"""Fetch TESS Objects of Interest from NASA Exoplanet Archive and upload to HF."""

import io
import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset


HF_REPO = "juliensimon/tess-toi-candidates"
TAP_URL = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"

ADQL = "SELECT * FROM toi"


def main():
    print("Fetching TESS TOI catalog from NASA Exoplanet Archive...")
    resp = requests.post(TAP_URL, data={
        "REQUEST": "doQuery",
        "LANG": "ADQL",
        "FORMAT": "csv",
        "QUERY": ADQL,
    }, timeout=120)
    resp.raise_for_status()

    df = pd.read_csv(io.StringIO(resp.text))
    print(f"  {len(df):,} TOI entries")

    # Rename key columns
    df = df.rename(columns={
        "tid": "toi_id",
        "toipfx": "toi_prefix",
        "pl_name": "planet_name",
        "rastr": "ra_str",
        "ra": "ra_deg",
        "decstr": "dec_str",
        "dec": "dec_deg",
        "pl_orbper": "period_days",
        "pl_orbpererr1": "period_err_upper",
        "pl_orbpererr2": "period_err_lower",
        "pl_rade": "radius_earth",
        "pl_radeerr1": "radius_err_upper",
        "pl_radeerr2": "radius_err_lower",
        "pl_eqt": "equilibrium_temp_k",
        "pl_trandep": "transit_depth_ppm",
        "st_tmag": "tmag",
        "toi_created": "created_date",
        "tfopwg_disp": "disposition",
    })

    # Convert numerics
    for col in ["ra_deg", "dec_deg", "period_days", "period_err_upper",
                "period_err_lower", "radius_earth", "radius_err_upper",
                "radius_err_lower", "equilibrium_temp_k", "transit_depth_ppm", "tmag"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Clean string columns
    for col in ["planet_name", "ra_str", "dec_str", "disposition", "created_date"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
            )

    # Drop columns that are >95% null (unused fields from SELECT *)
    before_cols = len(df.columns)
    for col in list(df.columns):
        if df[col].isna().mean() > 0.95:
            df = df.drop(columns=[col])
    dropped = before_cols - len(df.columns)
    if dropped:
        print(f"  Dropped {dropped} columns (>95% null)")

    check_dataset(df, "tess-toi", min_rows=5000,
        expected_columns=["toi_id", "ra_deg", "dec_deg", "period_days"],
        critical_columns=["toi_id", "ra_deg", "dec_deg"])

    # Stats for README
    n_total = len(df)
    n_confirmed = int(df["disposition"].eq("CP").sum()) if "disposition" in df.columns else 0
    n_fp = int(df["disposition"].eq("FP").sum()) if "disposition" in df.columns else 0
    n_with_radius = int(df["radius_earth"].notna().sum()) if "radius_earth" in df.columns else 0

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "tess_toi_candidates.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "TESS Objects of Interest (TOI) Planet Candidates"
language:
  - en
description: "Planet candidates identified by NASA's TESS mission, from the NASA Exoplanet Archive TOI catalog. Updated weekly."
task_categories:
  - tabular-classification
tags:
  - space
  - exoplanet
  - tess
  - planet-candidate
  - transit
  - nasa
  - open-data
  - tabular-data
  - parquet
size_categories:
  - 1K<n<10K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/tess_toi_candidates.parquet
    default: true
---

# TESS Objects of Interest (TOI) Planet Candidates

*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

![Update TESS TOI](https://github.com/juliensimon/space-datasets/actions/workflows/update-tess-toi.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.tess-toi&label=updated&color=brightgreen)

Planet candidates identified by NASA's Transiting Exoplanet Survey Satellite (TESS),
currently **{n_total:,}** TOI entries including confirmed planets, false positives, and
active candidates.

## Dataset description

TESS is a NASA space telescope launched in 2018 that surveys the entire sky for
transiting exoplanets. When a star shows periodic brightness dips consistent with
a planet crossing in front of it, it is flagged as a TESS Object of Interest (TOI).
Each TOI undergoes follow-up observations to determine whether it is a genuine planet,
a false positive (e.g., eclipsing binary), or remains an active candidate.

TESS represents a fundamentally different survey strategy from its predecessor Kepler. While Kepler stared at a single patch of sky for four years to find small planets around faint stars, TESS surveys nearly the entire sky in 27-day sectors, optimized for finding planets around the nearest and brightest stars. This design choice means TESS planets are far more amenable to ground-based follow-up: radial velocity mass measurements, atmospheric characterization with JWST, and even direct imaging with next-generation telescopes. The TOI catalog is the primary pipeline output that feeds this follow-up ecosystem.

Each TOI entry carries a disposition assigned by the TESS Follow-up Observing Program Working Group (TFOPWG): CP for confirmed planets that have passed rigorous vetting, FP for false positives ruled out by follow-up observations (commonly background eclipsing binaries or stellar variability), KP for known planets independently discovered, and PC for active planet candidates still awaiting confirmation. The transit depth, period, and estimated radius allow rapid triage of candidates by scientific interest -- from ultra-short-period rocky worlds to temperate sub-Neptunes in the habitable zone.

The TOI catalog is essential for exoplanet demographics, enabling occurrence rate calculations that complement Kepler's results for different stellar populations and orbital period ranges. It is also a primary resource for selecting atmospheric characterization targets, planning radial velocity campaigns, and training machine learning classifiers for automated transit vetting. The weekly update cadence captures new candidates as TESS completes additional sky sectors in its extended mission.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `toi_id` | float64 | TESS Input Catalog (TIC) ID |
| `toi_prefix` | float64 | TOI number (e.g. 175.01) |
| `planet_name` | string | Confirmed planet name (if any) |
| `ra_deg` | float64 | Right ascension (degrees) |
| `dec_deg` | float64 | Declination (degrees) |
| `period_days` | float64 | Orbital period (days) |
| `radius_earth` | float64 | Planet radius (Earth radii) |
| `equilibrium_temp_k` | float64 | Equilibrium temperature (K) |
| `transit_depth_ppm` | float64 | Transit depth (ppm) |
| `tmag` | float64 | TESS magnitude of host star |
| `disposition` | string | TFOPWG disposition (CP/FP/KP/PC) |

## Quick stats

- **{n_total:,}** TOI entries
- **{n_confirmed:,}** confirmed planets (CP)
- **{n_fp:,}** false positives (FP)
- **{n_with_radius:,}** with radius estimates

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/tess-toi-candidates", split="train")
df = ds.to_pandas()

# Confirmed planets
confirmed = df[df["disposition"] == "CP"]
print(f"{{len(confirmed):,}} confirmed planets")

# Small rocky planets (< 2 Earth radii)
rocky = df[df["radius_earth"] < 2.0].dropna(subset=["radius_earth"])
print(f"{{len(rocky):,}} candidates with radius < 2 Earth radii")

# Period distribution
import matplotlib.pyplot as plt
valid = df.dropna(subset=["period_days"])
plt.hist(valid["period_days"], bins=100, range=(0, 50))
plt.xlabel("Orbital period (days)")
plt.ylabel("Count")
plt.title("TESS TOI Period Distribution")
```

## Data source

[NASA Exoplanet Archive](https://exoplanetarchive.ipac.caltech.edu/), TESS TOI catalog,
accessed via the TAP service.

## Update schedule

Weekly (Monday at 17:00 UTC) via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [neo-close-approaches](https://huggingface.co/datasets/juliensimon/neo-close-approaches) -- NEO Close Approaches
- [pulsar-catalog](https://huggingface.co/datasets/juliensimon/pulsar-catalog) -- ATNF Pulsar Catalogue

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/tess-toi-candidates) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{tess_toi_candidates,
  author = {{Simon, Julien}},
  title = {{TESS Objects of Interest (TOI) Planet Candidates}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/tess-toi-candidates}},
  note = {{Based on NASA Exoplanet Archive TESS TOI catalog}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update TESS TOI candidates: {n_total:,} entries"
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
