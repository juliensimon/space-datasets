#!/usr/bin/env python3
"""Fetch Gaia DR3 Eclipsing Binaries catalog from ESA Gaia Archive and upload to HF."""

import io
import os
import subprocess
import tempfile
import time
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset

GAIA_TAP = "https://gea.esac.esa.int/tap-server/tap/sync"
HF_REPO = "juliensimon/gaia-dr3-eclipsing-binaries"
PAGE_SIZE = 500_000

RENAME = {
    "Source": "source_id",
    "RAJ2000": "ra_deg",
    "DEJ2000": "dec_deg",
    "Freq": "frequency",
    "Freq2": "frequency2",
    "GRank": "global_ranking",
    "Gmag": "g_mag",
    "o_Gmag": "g_mag_num_obs",
    "BPmag": "bp_mag",
    "RPmag": "rp_mag",
    "GmagFund": "g_mag_fund",
    "SigGmagFund": "g_mag_fund_sigma",
    "NumHarmonicsFund": "num_harmonics_fund",
    "GmagRef2": "g_mag_ref2",
    "SigGmagRef2": "g_mag_ref2_sigma",
    "NumHarmonicsRef2": "num_harmonics_ref2",
    "ModelType": "model_type",
    "NumParam": "num_parameters",
    "ReducedChi2": "reduced_chi2",
    "GmagGeom": "g_mag_geom",
    "SigGmagGeom": "g_mag_geom_sigma",
    "GmagPhaseAtMax": "g_mag_phase_at_max",
    "GmagPhaseAtMin": "g_mag_phase_at_min",
    "Epoch": "epoch",
}

NUMERIC_COLS = [
    "ra_deg", "dec_deg", "frequency", "frequency2",
    "global_ranking", "g_mag", "bp_mag", "rp_mag",
    "g_mag_fund", "g_mag_fund_sigma",
    "g_mag_ref2", "g_mag_ref2_sigma",
    "reduced_chi2", "g_mag_geom", "g_mag_geom_sigma",
    "g_mag_phase_at_max", "g_mag_phase_at_min", "epoch",
]

INT_COLS = [
    "g_mag_num_obs", "num_harmonics_fund", "num_harmonics_ref2", "num_parameters",
]


def fetch_gaia_eb():
    """Fetch eclipsing binaries from Gaia archive with OFFSET pagination."""
    all_dfs = []
    offset = 0
    while True:
        query = (
            f"SELECT * FROM gaiadr3.vari_eclipsing_binary "
            f"ORDER BY source_id "
            f"OFFSET {offset}"
        )
        print(f"  Fetching rows {offset:,}–{offset + PAGE_SIZE:,}...")
        resp = requests.post(GAIA_TAP, data={
            "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv",
            "QUERY": query, "MAXREC": PAGE_SIZE,
        }, timeout=600)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text))
        if len(df) == 0:
            break
        all_dfs.append(df)
        print(f"    got {len(df):,} rows")
        offset += len(df)
        if len(df) < PAGE_SIZE:
            break
        time.sleep(2)
    return pd.concat(all_dfs, ignore_index=True)


def main():
    print("Fetching Gaia DR3 Eclipsing Binaries from ESA Gaia Archive...")
    df = fetch_gaia_eb()
    print(f"  {len(df):,} raw rows")

    # Gaia archive returns snake_case columns already — rename only if needed
    df = df.rename(columns=RENAME)

    # Type conversions — numeric (all Gaia columns are already typed from CSV)
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Type conversions — integer
    for col in INT_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int32")

    # Derived: period from frequency
    if "frequency" in df.columns:
        df["period_days"] = 1.0 / df["frequency"]

    # Derived: color index
    if "bp_mag" in df.columns and "rp_mag" in df.columns:
        df["bp_rp"] = df["bp_mag"] - df["rp_mag"]

    # Sort by source_id
    if "source_id" in df.columns:
        df = df.sort_values("source_id").reset_index(drop=True)

    # Drop recno (VizieR internal)
    if "recno" in df.columns:
        df = df.drop(columns=["recno"])

    # Stats
    n_total = len(df)
    g_median = df["g_mag"].median() if "g_mag" in df.columns else float("nan")
    period_median = df["period_days"].median() if "period_days" in df.columns else float("nan")
    rank_median = df["global_ranking"].median() if "global_ranking" in df.columns else float("nan")

    # Validate
    check_dataset(
        df,
        "gaia-eb",
        min_rows=1_500_000,
        expected_columns=["source_id", "frequency", "global_ranking"],
        critical_columns=["source_id", "frequency"],
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "gaia_dr3_eclipsing_binaries.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Gaia DR3 Eclipsing Binaries"
language:
  - en
description: "Gaia DR3 eclipsing binary candidates — {n_total:,} variable stars with orbital periods, light-curve model parameters, and photometry from ESA Gaia mission."
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - gaia
  - eclipsing-binaries
  - stars
  - esa
  - astronomy
  - open-data
  - tabular-data
  - parquet
size_categories:
  - 1M<n<10M
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/gaia_dr3_eclipsing_binaries.parquet
    default: true
---

# Gaia DR3 Eclipsing Binaries

*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

The Gaia DR3 eclipsing binary catalog, containing **{n_total:,}** eclipsing binary candidates
identified by the ESA Gaia mission's variability processing pipeline. Each source includes
orbital frequency, light-curve model parameters, global ranking score, and multi-band
photometry (G, BP, RP).

## Dataset description

Eclipsing binaries are pairs of stars whose orbital plane is aligned with our line of sight,
causing periodic brightness dips as one star passes in front of the other. Gaia's all-sky
photometric survey identified these candidates through automated variability classification
and Fourier-based light-curve modeling. The `global_ranking` score (0-1) indicates the
confidence that a source is a genuine eclipsing binary.

Eclipsing binaries are among the most astrophysically valuable variable stars because they
provide model-independent measurements of fundamental stellar properties. When combined with
radial velocity curves, the eclipse geometry yields absolute masses and radii of both
components to precisions of a few percent -- the only direct method for calibrating stellar
evolution models across a wide range of masses, ages, and compositions. Detached eclipsing
binaries in particular serve as primary distance indicators: their physical radii and
effective temperatures give an absolute luminosity that, compared with the observed flux,
directly yields the distance without recourse to the period-luminosity relations used for
pulsating stars.

The sheer scale of this Gaia catalog -- over a million candidates identified from the
spacecraft's all-sky photometric time series -- represents an order-of-magnitude increase
over previous compilations such as the Kepler Eclipsing Binary Catalog (~2,900 systems) or
the OGLE collection (~450,000 systems in the Magellanic Clouds and bulge). The orbital
periods span from ultra-short contact binaries completing a revolution in a few hours to
long-period detached systems with periods of hundreds of days. The Fourier-based light curve
decomposition provided in the catalog (fundamental and second-reference amplitudes, number
of harmonics, reduced chi-squared) enables automated morphological classification into
detached, semi-detached, and contact configurations without requiring manual inspection of
individual light curves.

Because Gaia surveys the entire sky uniformly, this catalog is free from the spatial
selection biases inherent in pointed surveys. It therefore provides the first statistically
complete view of the eclipsing binary population across the full Milky Way disk, halo, and
satellite system, enabling population studies of binary fraction, period distribution, and
mass-ratio statistics as a function of Galactic environment.

## Key columns

| Column | Type | Description |
|--------|------|-------------|
| `source_id` | string | Gaia DR3 unique source identifier |
| `ra_deg` | float64 | Right ascension ICRS (degrees) |
| `dec_deg` | float64 | Declination ICRS (degrees) |
| `frequency` | float64 | Orbital frequency (cycles/day) |
| `period_days` | float64 | Orbital period (days), derived as 1/frequency |
| `epoch` | float64 | Reference epoch (BJD - 2455197.5 days) |
| `global_ranking` | float64 | Classification confidence score (0-1) |
| `g_mag` | float64 | Mean G-band magnitude |
| `bp_mag` | float64 | Mean BP-band magnitude |
| `rp_mag` | float64 | Mean RP-band magnitude |
| `bp_rp` | float64 | BP-RP color index (derived) |
| `model_type` | string | Light-curve model type |
| `num_parameters` | Int32 | Number of model parameters |
| `reduced_chi2` | float64 | Reduced chi-squared of model fit |
| `g_mag_fund` | float64 | G-band fundamental amplitude |
| `num_harmonics_fund` | Int32 | Number of Fourier harmonics (fundamental) |

Full schema includes {len(df.columns)} columns with amplitudes, uncertainties, and geometric magnitudes.

## Quick stats

- **{n_total:,}** eclipsing binary candidates
- Median G magnitude: {g_median:.2f}
- Median orbital period: {period_median:.4f} days
- Median global ranking: {rank_median:.3f}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/gaia-dr3-eclipsing-binaries", split="train")
df = ds.to_pandas()

# High-confidence eclipsing binaries
high_conf = df[df["global_ranking"] > 0.5]
print(f"High-confidence EBs: {{len(high_conf):,}}")

# Period distribution
import matplotlib.pyplot as plt
df["period_days"].clip(upper=10).hist(bins=200, log=True)
plt.xlabel("Period (days)")
plt.ylabel("Count")
plt.title("Gaia DR3 Eclipsing Binary Period Distribution")
plt.show()

# HR diagram (color-magnitude)
plt.hexbin(df["bp_rp"], df["g_mag"], gridsize=200, mincnt=1, cmap="hot")
plt.colorbar(label="Count")
plt.xlabel("BP - RP (mag)")
plt.ylabel("G (mag)")
plt.gca().invert_yaxis()
plt.title("Gaia EB Color-Magnitude Diagram")
plt.show()
```

## Data source

Gaia Collaboration (2023), *Gaia Data Release 3: variability processing and analysis results.*
European Space Agency. Via VizieR CDS (I/355/gaiadr3).

## Related datasets

- [Gaia DR3 Variable Star Summary](https://huggingface.co/datasets/juliensimon/gaia-dr3-variable-summary) — all Gaia variable star classifications

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/gaia-dr3-eclipsing-binaries) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{gaia_dr3_eclipsing_binaries,
  author = {{Simon, Julien}},
  title = {{Gaia DR3 Eclipsing Binaries}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/gaia-dr3-eclipsing-binaries}},
  note = {{Based on Gaia DR3 (ESA) via VizieR CDS}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update Gaia DR3 eclipsing binaries: {n_total:,} sources"
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
