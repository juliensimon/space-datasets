#!/usr/bin/env python3
"""Fetch Gaia DR3 Long Period Variables catalog from ESA Gaia Archive and upload to HF."""

import io
import time

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

GAIA_TAP = "https://gea.esac.esa.int/tap-server/tap/sync"
HF_REPO = "juliensimon/gaia-dr3-long-period-variables"
PAGE_SIZE = 500_000

# -- Column mapping --------------------------------------------------------
RENAME = {
    "solution_id": "solution_id",  # will be dropped below
    "source_id": "source_id",
    "frequency": "frequency",
    "frequency_error": "frequency_error",
    "amplitude": "amplitude",
    "median_delta_wl_rp": "median_delta_wl_rp",
    "is_cstar": "is_cstar",
}

# -- Column descriptions for README schema table ---------------------------
COLUMN_DESCRIPTIONS = {
    "source_id": "Gaia DR3 unique source identifier; use for cross-matching with gaia_source to obtain sky coordinates and photometry",
    "frequency": "Dominant pulsation frequency in cycles per day; the primary periodicity of the LPV light curve",
    "frequency_error": "Formal uncertainty on the pulsation frequency in cycles per day",
    "amplitude": "Peak-to-peak variability amplitude in the Gaia G-band in magnitudes; large amplitudes (>1 mag) indicate Mira-type pulsators",
    "median_delta_wl_rp": "Median wavelength shift of the RP (red photometer) spectrum relative to the template spectrum in nm; a proxy for spectral variability driven by TiO/CN molecular band changes over the pulsation cycle",
    "is_cstar": "Boolean classification flag: True if the source is classified as a carbon star (C/O > 1, C-type AGB), False for oxygen-rich LPV (M- or S-type AGB); based on RP spectral shape",
    "period_days": "Dominant pulsation period in days, derived as 1/frequency; ranges from ~10 days (OSARG-type) to >1000 days (long-period Miras)",
}

# -- Dataset description ----------------------------------------------------
DESCRIPTION = """\
The Gaia DR3 Long Period Variables (LPV) catalog contains ~1.7 million variable giant star \
candidates identified by the ESA Gaia mission's variability processing pipeline. Each source \
includes a dominant pulsation frequency, G-band amplitude, RP spectral variability proxy, and \
a carbon-star classification flag.

Long Period Variables are evolved giant stars on the Asymptotic Giant Branch (AGB) that pulsate \
with periods ranging from ~10 to more than 1000 days. They encompass Mira variables \
(large-amplitude, near-sinusoidal light curves driven by fundamental-mode pulsation), \
semi-regular variables (SRb/SRa, multi-periodic or irregular), and OSARG (OGLE Small Amplitude \
Red Giants, overtone pulsators). LPVs are important for multiple reasons: they follow \
tight period-luminosity relations in near-infrared bands (analogous to Cepheids) and serve as \
distance indicators to nearby galaxies; they are among the most prolific producers of dust and \
chemically enriched material in the interstellar medium; and their pulsation properties constrain \
AGB stellar evolution models.

Carbon stars (is_cstar=True) have carbon-to-oxygen ratios greater than one in their atmospheres \
due to dredge-up episodes bringing carbon from the helium-burning shell to the surface. Their \
RP spectra show distinctive CN and C2 molecular band signatures that differ markedly from the \
TiO-dominated spectra of oxygen-rich M-type AGB stars. With 1.7 million candidates, this Gaia \
DR3 catalog is the largest LPV compilation ever assembled, exceeding previous large-scale \
surveys such as OGLE, 2MASS, and WISE by an order of magnitude in sky coverage and sample size.
"""


def fetch_gaia_lrv():
    """Fetch long period variables from Gaia archive with OFFSET pagination."""
    all_dfs = []
    offset = 0
    while True:
        query = (
            f"SELECT * FROM gaiadr3.vari_long_period_variable "
            f"ORDER BY source_id "
            f"OFFSET {offset}"
        )
        print(f"  Fetching rows {offset:,}-{offset + PAGE_SIZE:,}...")
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
    print("Fetching Gaia DR3 Long Period Variables from ESA Gaia Archive...")
    df = fetch_gaia_lrv()
    print(f"  {len(df):,} raw rows")

    # Rename columns (Gaia archive already uses snake_case)
    df = df.rename(columns=RENAME)

    # Drop internal Gaia processing column
    for col in ["solution_id"]:
        if col in df.columns:
            df = df.drop(columns=[col])

    # Type conversions -- object columns to numeric
    for col in df.select_dtypes(include=["object"]).columns:
        if col != "is_cstar":
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # is_cstar: coerce to boolean if not already
    if "is_cstar" in df.columns:
        if df["is_cstar"].dtype == object:
            df["is_cstar"] = df["is_cstar"].map(
                {"true": True, "false": False, "True": True, "False": False}
            ).astype("boolean")
        else:
            df["is_cstar"] = df["is_cstar"].astype("boolean")

    # Derived: period from frequency
    if "frequency" in df.columns:
        df["period_days"] = df["frequency"].where(df["frequency"] > 0).rdiv(1.0)

    # Keep only described columns (preserves order)
    df = df[[c for c in COLUMN_DESCRIPTIONS if c in df.columns]]

    # Sort by source_id
    if "source_id" in df.columns:
        df = df.sort_values("source_id").reset_index(drop=True)

    # Stats
    n_total = len(df)
    n_cstar = int(df["is_cstar"].sum()) if "is_cstar" in df.columns else 0
    n_oxygen = n_total - n_cstar
    period_median = df["period_days"].median() if "period_days" in df.columns else float("nan")
    amp_median = df["amplitude"].median() if "amplitude" in df.columns else float("nan")
    cstar_pct = 100.0 * n_cstar / n_total if n_total > 0 else 0.0

    quick_stats = f"""\
- **{n_total:,}** LPV candidates total
- Carbon stars (is_cstar=True): **{n_cstar:,}** ({cstar_pct:.1f}%)
- Oxygen-rich LPVs (is_cstar=False): **{n_oxygen:,}** ({100-cstar_pct:.1f}%)
- Median pulsation period: **{period_median:.1f}** days
- Median G-band amplitude: **{amp_median:.3f}** mag"""

    usage = """\
```python
from datasets import load_dataset
import matplotlib.pyplot as plt

ds = load_dataset("juliensimon/gaia-dr3-long-period-variables", split="train")
df = ds.to_pandas()

# Carbon stars vs oxygen-rich LPVs
n_cstar = df["is_cstar"].sum()
print(f"Carbon stars: {n_cstar:,} ({100*n_cstar/len(df):.1f}%)")
print(f"Oxygen-rich LPVs: {(~df['is_cstar']).sum():,}")

# Period distribution (log scale)
df["period_days"].clip(upper=2000).hist(bins=200, log=True)
plt.xlabel("Period (days)")
plt.ylabel("Count (log scale)")
plt.title("Gaia DR3 LPV Period Distribution")
plt.show()

# Amplitude vs period scatter (random subsample)
sample = df.sample(50_000)
plt.scatter(sample["period_days"], sample["amplitude"],
            c=sample["is_cstar"].astype(int),
            cmap="coolwarm", s=1, alpha=0.3)
plt.xscale("log")
plt.xlabel("Period (days)")
plt.ylabel("G-band amplitude (mag)")
plt.title("Amplitude vs Period — Gaia DR3 LPVs")
plt.colorbar(label="Carbon star (1=True)")
plt.show()

# Cross-match with gaia_source for sky coordinates
# (source_id is the Gaia DR3 64-bit identifier)
print("Use source_id to join with gaia_source for RA/Dec, parallax, etc.")
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Gaia DR3 Long Period Variables",
        description=DESCRIPTION,
        tags=["space", "gaia", "variable-stars", "long-period-variables",
              "agb-stars", "esa", "astronomy", "open-data", "tabular-data", "parquet"],
        source_url="https://gea.esac.esa.int/archive/",
        task_categories=["tabular-classification", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA03606/PIA03606~small.jpg",
            "alt": "Hubble Space Telescope image used as banner for Gaia LPV dataset",
            "credit": "NASA/ESA/Hubble",
        },
        related_datasets=[
            "juliensimon/gaia-dr3-cepheids",
            "juliensimon/gaia-dr3-rrlyrae",
            "juliensimon/gcvs-variable-stars",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "frequency", "frequency_error", "amplitude",
                "median_delta_wl_rp", "period_days",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="gaia_dr3_long_period_variables.parquet",
            min_rows=1_500_000,
            expected_columns=["source_id", "frequency", "amplitude", "is_cstar"],
            critical_columns=["source_id", "frequency"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Gaia DR3 long period variables: {n_total:,} sources",
        )
    print("Done.")


if __name__ == "__main__":
    main()
