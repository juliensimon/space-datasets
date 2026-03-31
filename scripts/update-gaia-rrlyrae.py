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
    period_median = df["period_days"].median() if "period_days" in df.columns else 0

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
  - tabular-data
  - parquet
size_categories:
  - 100K<n<1M
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/gaia_dr3_rrlyrae.parquet
    default: true
---

# Gaia DR3 RR Lyrae Variables

*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

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

RR Lyrae stars occupy the horizontal branch of the Hertzsprung-Russell diagram, burning
helium in their cores after ascending the red giant branch. They are exclusively old
(> 10 Gyr) and metal-poor to moderately metal-rich, with masses near 0.6--0.8 solar masses
and luminosities around 40--50 times that of the Sun. Their pulsation is driven by the
kappa mechanism operating in the partial ionization zone of helium, producing the
characteristic rapid brightness variations with periods typically between 0.2 and 1.0 days.
Three pulsation modes are recognized: RRab stars pulsate in the radial fundamental mode with
large, asymmetric light curves and periods around 0.5--0.7 days; RRc stars pulsate in the
first overtone with smaller amplitudes and more sinusoidal variations near 0.25--0.40 days;
and RRd stars pulsate simultaneously in both modes, providing strong constraints on stellar
structure models.

The Bailey diagram -- plotting light-curve amplitude against period -- cleanly separates
these subclasses and encodes information about metallicity: at a given period, more
metal-poor RRab stars tend to have larger amplitudes. Gaia DR3 exploits this by deriving
photometric metallicities from the light-curve shape, providing [Fe/H] estimates for
hundreds of thousands of stars across the Galaxy without the need for spectroscopy. Combined
with the photometric distances in this catalog, these metallicities enable three-dimensional
chemical mapping of the Milky Way's oldest stellar populations.

RR Lyrae stars are particularly powerful tracers of Galactic substructure because they are
luminous enough to be detected at distances of over 100 kpc, well into the outer halo where
the debris of accreted dwarf galaxies is found. They have been instrumental in the discovery
of the Sagittarius stream, the Virgo overdensity, and numerous other halo substructures.
The Gaia DR3 catalog, with its combination of all-sky coverage, uniform photometry, and
precise astrometry, provides the definitive census of RR Lyrae populations throughout the
Milky Way system.

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
- **{n_with_period:,}** with pulsation period (median {period_median:.4f} days)

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

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/gaia-dr3-rrlyrae) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

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
