#!/usr/bin/env python3
"""Fetch Gaia DR3 RR Lyrae variable star catalog from VizieR and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from validate import check_dataset
from vizier_tap import vizier_query

HF_REPO = "juliensimon/gaia-dr3-rrlyrae"

ADQL = """SELECT * FROM "I/358/vrrlyr" """

RENAME = {
    "RA_ICRS": "ra_deg",
    "RAJ2000": "ra_deg",
    "_RA": "ra_deg",
    "DE_ICRS": "dec_deg",
    "DEJ2000": "dec_deg",
    "_DE": "dec_deg",
    "Source": "source_id",
    "Pf": "period_days",
    "EpochG": "epoch_g_bjd",
    "AmpG": "amplitude_g_mag",
    "RmagG": "mean_g_mag",
    "RmagBP": "mean_bp_mag",
    "RmagRP": "mean_rp_mag",
    "[Fe/H]": "metallicity_feh",
    "Dist": "distance_pc",
    "SType": "subclassification",
    "Best": "best_classification",
    "NbTr": "n_transits",
}

NUMERIC_COLS = [
    "ra_deg", "dec_deg", "period_days", "epoch_g_bjd",
    "amplitude_g_mag", "mean_g_mag", "mean_bp_mag", "mean_rp_mag",
    "metallicity_feh", "distance_pc", "n_transits",
]


def main():
    print("Fetching Gaia DR3 RR Lyrae catalog from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} raw rows")

    # Rename columns
    df = df.rename(columns=RENAME)

    # Type conversions
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Clean string columns
    for col in ["source_id", "subclassification", "best_classification"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
            )

    # Stats
    n_total = len(df)
    n_with_period = int(df["period_days"].notna().sum()) if "period_days" in df.columns else 0
    n_with_metal = int(df["metallicity_feh"].notna().sum()) if "metallicity_feh" in df.columns else 0
    n_with_dist = int(df["distance_pc"].notna().sum()) if "distance_pc" in df.columns else 0
    period_median = df["period_days"].median() if "period_days" in df.columns else 0
    if "best_classification" in df.columns:
        top_classes = df["best_classification"].value_counts().head(5)
        top_classes_str = ", ".join(f"{t} ({c:,})" for t, c in top_classes.items())
        n_classes = int(df["best_classification"].nunique())
    else:
        top_classes_str = "N/A"
        n_classes = 0

    # Validate
    check_dataset(
        df,
        "gaia-rrlyrae",
        min_rows=250_000,
        expected_columns=["ra_deg", "dec_deg"],
        critical_columns=["ra_deg", "dec_deg"],
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "gaia_dr3_rrlyrae.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Gaia DR3 RR Lyrae Variables"
language:
  - en
description: "Gaia DR3 catalog of {n_total:,} RR Lyrae variable stars with periods, amplitudes, metallicities, and distances."
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - gaia
  - rr-lyrae
  - variable-star
  - distance-ladder
  - astronomy
  - open-data
size_categories:
  - 100K<n<1M
---

# Gaia DR3 RR Lyrae Variables

The Gaia Data Release 3 catalog of **{n_total:,}** RR Lyrae variable stars -- the largest
homogeneous catalog of pulsating horizontal-branch stars ever compiled. RR Lyrae stars are
essential standard candles for the cosmic distance ladder.

## Dataset description

RR Lyrae stars are old, low-metallicity pulsating variables found in the Milky Way halo,
bulge, globular clusters, and nearby galaxies. Their well-defined period-luminosity-metallicity
relation makes them fundamental distance indicators. Gaia DR3 provides the most comprehensive
all-sky census of RR Lyrae variables, with precise astrometry, multi-band photometry, light
curve parameters, metallicity estimates from the light curve shape, and photometric distances.

This dataset is a cornerstone for Galactic archaeology, enabling studies of the Milky Way's
stellar halo substructure, tidal streams, and satellite galaxies.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `source_id` | string | Gaia DR3 source identifier |
| `ra_deg` | float64 | Right ascension J2016.0 (degrees) |
| `dec_deg` | float64 | Declination J2016.0 (degrees) |
| `period_days` | float64 | Pulsation period (days) |
| `epoch_g_bjd` | float64 | Epoch of maximum in G band (Barycentric JD) |
| `amplitude_g_mag` | float64 | Peak-to-peak amplitude in G band (mag) |
| `mean_g_mag` | float64 | Mean G-band magnitude |
| `mean_bp_mag` | float64 | Mean BP-band magnitude |
| `mean_rp_mag` | float64 | Mean RP-band magnitude |
| `metallicity_feh` | float64 | Photometric metallicity [Fe/H] (dex) |
| `distance_pc` | float64 | Photometric distance (parsec) |
| `subclassification` | string | RR Lyrae subtype (RRab, RRc, RRd) |
| `best_classification` | string | Best classification label |
| `n_transits` | float64 | Number of Gaia transits used |

## Quick stats

- **{n_total:,}** RR Lyrae variables
- **{n_classes}** classification subtypes: {top_classes_str}
- **{n_with_period:,}** with pulsation period (median {period_median:.4f} days)
- **{n_with_metal:,}** with metallicity estimate
- **{n_with_dist:,}** with photometric distance

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/gaia-dr3-rrlyrae", split="train")
df = ds.to_pandas()

# Period distribution (Bailey diagram)
import matplotlib.pyplot as plt
valid = df.dropna(subset=["period_days", "amplitude_g_mag"])
plt.scatter(valid["period_days"], valid["amplitude_g_mag"], s=0.5, alpha=0.2)
plt.xlabel("Period (days)")
plt.ylabel("Amplitude G (mag)")
plt.title("Gaia DR3 RR Lyrae Bailey Diagram")
plt.show()

# Metallicity distribution
df["metallicity_feh"].dropna().hist(bins=100)
plt.xlabel("[Fe/H] (dex)")
plt.ylabel("Count")
plt.title("RR Lyrae Metallicity Distribution")
plt.show()

# Sky distribution (Galactic coordinates would be ideal)
plt.scatter(df["ra_deg"], df["dec_deg"], s=0.01, alpha=0.1,
            c=df["distance_pc"].clip(upper=50000), cmap="viridis")
plt.colorbar(label="Distance (pc)")
plt.xlabel("RA (deg)")
plt.ylabel("Dec (deg)")
plt.title("Gaia DR3 RR Lyrae Sky Distribution")
plt.show()
```

## Data source

Clementini, G. et al. (2023), *Gaia Data Release 3: Specific processing and validation
of all-sky RR Lyrae and Cepheid stars.* Astronomy & Astrophysics, 674, A18.
Via [VizieR](https://vizier.cds.unistra.fr/) CDS Strasbourg (I/358).

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Citation

```bibtex
@dataset{{gaia_dr3_rrlyrae,
  author = {{Simon, Julien}},
  title = {{Gaia DR3 RR Lyrae Variables}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/gaia-dr3-rrlyrae}},
  note = {{Based on Clementini et al. (2023), Gaia DR3, via VizieR CDS Strasbourg}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update Gaia DR3 RR Lyrae: {n_total:,} variables"
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
