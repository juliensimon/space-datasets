#!/usr/bin/env python3
"""Fetch Gaia DR3 Cepheid variable star catalog from VizieR and upload to HF."""

import os
import re
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from validate import check_dataset
from vizier_tap import vizier_query

HF_REPO = "juliensimon/gaia-dr3-cepheids"

ADQL = 'SELECT * FROM "I/358/vcep"'

RENAME = {
    "Source": "source_id",
    "RA_ICRS": "ra_deg",
    "DE_ICRS": "dec_deg",
    "PF": "period_fundamental_days",
    "e_PF": "period_fundamental_error",
    "P1O": "period_1st_overtone_days",
    "e_P1O": "period_1st_overtone_error",
    "P2O": "period_2nd_overtone_days",
    "e_P2O": "period_2nd_overtone_error",
    "EpochG": "epoch_g",
    "e_EpochG": "epoch_g_error",
    "EpochBP": "epoch_bp",
    "EpochRP": "epoch_rp",
    "EpochRV": "epoch_rv",
    "Gmagavg": "gaia_g_mag",
    "e_Gmagavg": "gaia_g_mag_error",
    "BPmagavg": "gaia_bp_mag",
    "e_BPmagavg": "gaia_bp_mag_error",
    "RPmagavg": "gaia_rp_mag",
    "e_RPmagavg": "gaia_rp_mag_error",
    "RVavg": "radial_velocity_kms",
    "e_RVavg": "radial_velocity_error_kms",
    "ptpG": "amplitude_g",
    "e_ptpG": "amplitude_g_error",
    "ptpBP": "amplitude_bp",
    "ptpRP": "amplitude_rp",
    "ptpRV": "amplitude_rv",
    "[M/H]": "metallicity",
    "e_[M/H]": "metallicity_error",
    "R21G": "fourier_r21_g",
    "R31G": "fourier_r31_g",
    "phi21G": "fourier_phi21_g",
    "phi31G": "fourier_phi31_g",
    "NclEpG": "n_epochs_g",
    "NclEpBP": "n_epochs_bp",
    "NclEpRP": "n_epochs_rp",
    "NclEpRV": "n_epochs_rv",
    "Class": "cepheid_type",
    "SubClass": "cepheid_subclass",
    "ModeClass": "mode_class",
    "MulModeClass": "multi_mode_class",
    "FundFreq1": "fundamental_freq_1",
    "FundFreq2": "fundamental_freq_2",
    "SolID": "solution_id",
}

DROP_COLS = ["recno", "SimbadName", "More", "_RA_icrs", "_DE_icrs"]

NUMERIC_COLS = [
    "ra_deg", "dec_deg", "period_fundamental_days", "period_fundamental_error",
    "period_1st_overtone_days", "period_1st_overtone_error",
    "period_2nd_overtone_days", "period_2nd_overtone_error",
    "gaia_g_mag", "gaia_g_mag_error", "gaia_bp_mag", "gaia_bp_mag_error",
    "gaia_rp_mag", "gaia_rp_mag_error", "radial_velocity_kms",
    "radial_velocity_error_kms", "amplitude_g", "amplitude_g_error",
    "amplitude_bp", "amplitude_rp", "amplitude_rv",
    "metallicity", "metallicity_error",
    "fourier_r21_g", "fourier_r31_g", "fourier_phi21_g", "fourier_phi31_g",
    "fundamental_freq_1", "fundamental_freq_2",
]


def snake_case(name: str) -> str:
    """Convert a column name to snake_case."""
    s = re.sub(r"[()]", "", name)
    s = re.sub(r"[\s\-/]+", "_", s)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    return s.lower().strip("_")


def main():
    print("Fetching Gaia DR3 Cepheid catalog from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} Cepheids fetched")

    # Drop unwanted columns
    for col in DROP_COLS:
        if col in df.columns:
            df = df.drop(columns=[col])

    # Rename columns
    df = df.rename(columns=RENAME)

    # Snake-case any remaining columns not already renamed
    df.columns = [
        snake_case(c) if c not in RENAME.values() else c
        for c in df.columns
    ]

    # Numeric conversions
    for col in NUMERIC_COLS:
        if col in df.columns and isinstance(df[col], pd.Series):
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Clean string columns
    str_cols = ["source_id", "cepheid_type"]
    for col in str_cols:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
            )

    # Derived column: is_classical (DCEP = classical/fundamental mode Cepheids)
    if "cepheid_type" in df.columns:
        df["is_classical"] = df["cepheid_type"].str.upper().str.contains(
            r"DCEP", na=False
        )

    # Compute best period (fundamental if available, else 1st overtone)
    if "period_fundamental_days" in df.columns:
        df["period_best_days"] = df["period_fundamental_days"].fillna(
            df.get("period_1st_overtone_days", pd.Series(dtype="float64"))
        )
    elif "period_1st_overtone_days" in df.columns:
        df["period_best_days"] = df["period_1st_overtone_days"]

    # Sort by source_id if available, else by ra
    sort_col = "source_id" if "source_id" in df.columns else "ra_deg"
    df = df.sort_values(sort_col).reset_index(drop=True)

    # Stats
    n_total = len(df)

    type_counts = {}
    if "cepheid_type" in df.columns:
        type_counts = df["cepheid_type"].str.strip().value_counts().to_dict()

    n_classical = int(df["is_classical"].sum()) if "is_classical" in df.columns else 0

    period_col = "period_best_days" if "period_best_days" in df.columns else "period_fundamental_days"
    period_min = df[period_col].min() if period_col in df.columns else 0
    period_max = df[period_col].max() if period_col in df.columns else 0
    period_median = df[period_col].median() if period_col in df.columns else 0

    n_with_rv = int(df["radial_velocity_kms"].notna().sum()) if "radial_velocity_kms" in df.columns else 0
    n_with_metallicity = int(df["metallicity"].notna().sum()) if "metallicity" in df.columns else 0

    print(f"  {n_total:,} Cepheids total")
    print(f"  {n_classical:,} classical Cepheids")
    print(f"  Period range: {period_min:.4f} - {period_max:.2f} days (median {period_median:.4f})")
    print(f"  {n_with_rv:,} with radial velocity")
    if type_counts:
        top_types = sorted(type_counts.items(), key=lambda x: -x[1])[:8]
        print(f"  Type breakdown: {', '.join(f'{t}: {c:,}' for t, c in top_types)}")

    # Type breakdown string for README
    type_lines = ""
    if type_counts:
        for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
            type_lines += f"| `{t}` | {c:,} |\n"

    # Validate
    check_dataset(
        df,
        "gaia-cepheids",
        min_rows=10_000,
        expected_columns=["ra_deg", "dec_deg"],
        critical_columns=["ra_deg", "dec_deg"],
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "gaia_cepheids.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Gaia DR3 Cepheid Variables"
language:
  - en
description: "Gaia DR3 catalog of {n_total:,} Cepheid variable stars with pulsation periods, multi-band photometry, parallaxes, and classifications. Essential standard candles for the cosmic distance ladder."
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - stars
  - cepheids
  - variable-stars
  - distance-ladder
  - gaia
  - esa
  - astronomy
  - open-data
  - tabular-data
  - parquet
size_categories:
  - 10K<n<100K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/gaia_cepheids.parquet
    default: true
---

# Gaia DR3 Cepheid Variables

*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

The Gaia Data Release 3 catalog of **{n_total:,}** Cepheid variable stars of all types --
classical (fundamental mode), Type II, and anomalous Cepheids. Cepheids are among the most
important standard candles for calibrating the cosmic distance ladder, with their well-known
period-luminosity relation enabling precise distance measurements across the Local Group and
beyond.

## Dataset description

This dataset contains ~15,006 Cepheids identified and characterized by the Gaia DR3
variability processing pipeline. Each object includes pulsation periods, multi-band
photometric parameters (G, BP, RP), light curve amplitudes, classifications, parallaxes,
and photometric distances. The catalog spans all Cepheid subtypes: classical Cepheids (DCEP),
anomalous Cepheids (ACEP), Type II Cepheids (T2CEP, including BL Her, W Vir, and RV Tau),
and multi-mode pulsators.

Cepheids follow a tight period-luminosity (Leavitt) relation that makes them indispensable
for measuring distances -- from the Milky Way disk to galaxies tens of megaparsecs away. The
Gaia parallaxes provide a geometric anchor for calibrating this relation with unprecedented
precision.

## Quick stats

- **{n_total:,}** Cepheid variables
- **{n_classical:,}** classical Cepheids (DCEP types)
- Period range: **{period_min:.4f}** to **{period_max:.2f}** days (median {period_median:.4f})
- **{n_with_rv:,}** with radial velocity measurements
- **{n_with_metallicity:,}** with metallicity estimates

{"### Type breakdown" if type_lines else ""}
{"" if not type_lines else "| Type | Count |"}
{"" if not type_lines else "|------|-------|"}
{type_lines}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/gaia-dr3-cepheids", split="train")
df = ds.to_pandas()

# Period-luminosity (Leavitt) relation
import matplotlib.pyplot as plt
valid = df.dropna(subset=["period_best_days", "gaia_g_mag"])
plt.scatter(valid["period_best_days"], valid["gaia_g_mag"], s=0.5, alpha=0.3)
plt.xscale("log")
plt.gca().invert_yaxis()
plt.xlabel("Period (days)")
plt.ylabel("G magnitude")
plt.title("Gaia DR3 Cepheid Period-Luminosity Relation")
plt.show()

# Classical vs Type II Cepheids
if "is_classical" in df.columns:
    classical = df[df["is_classical"] == True]
    other = df[df["is_classical"] == False]
    print(f"{{len(classical):,}} classical, {{len(other):,}} other types")

# Sky distribution
plt.scatter(df["ra_deg"], df["dec_deg"], s=0.1, alpha=0.2)
plt.xlabel("RA (deg)")
plt.ylabel("Dec (deg)")
plt.title("Gaia DR3 Cepheids Sky Distribution")
plt.show()
```

## Data source

Ripepi, V. et al. (2023), *Gaia Data Release 3. Specific processing of all-sky RR Lyrae
and Cepheid stars.* Astronomy & Astrophysics, 674, A17.
Via [VizieR](https://vizier.cds.unistra.fr/) CDS Strasbourg (I/358/vcep).

## Related datasets

- [gaia-dr3-rr-lyrae](https://huggingface.co/datasets/juliensimon/gaia-dr3-rrlyrae) -- Gaia DR3 RR Lyrae Variables
- [gcvs-variable-stars](https://huggingface.co/datasets/juliensimon/gcvs-variable-stars) -- General Catalogue of Variable Stars
- [gaia-dr3-eclipsing-binaries](https://huggingface.co/datasets/juliensimon/gaia-dr3-eclipsing-binaries) -- Gaia DR3 Eclipsing Binaries

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a heart on the [dataset page](https://huggingface.co/datasets/juliensimon/gaia-dr3-cepheids) and share feedback in the Community tab! Also consider giving a star to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{gaia_dr3_cepheids,
  author = {{Simon, Julien}},
  title = {{Gaia DR3 Cepheid Variables}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/gaia-dr3-cepheids}},
  note = {{Based on Ripepi et al. (2023), Gaia DR3, via VizieR CDS Strasbourg}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update Gaia DR3 Cepheids: {n_total:,} variables"
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
