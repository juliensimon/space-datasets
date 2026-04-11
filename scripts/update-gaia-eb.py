#!/usr/bin/env python3
"""Fetch Gaia DR3 Eclipsing Binaries catalog from ESA Gaia Archive and upload to HF."""

import io
import time

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

GAIA_TAP = "https://gea.esac.esa.int/tap-server/tap/sync"
HF_REPO = "juliensimon/gaia-dr3-eclipsing-binaries"
PAGE_SIZE = 500_000

# -- Column mapping --------------------------------------------------------
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

# -- Column descriptions for README schema table ---------------------------
COLUMN_DESCRIPTIONS = {
    "source_id": "Gaia DR3 unique source identifier; use for cross-matching with other Gaia tables",
    "ra_deg": "Right ascension ICRS at epoch J2016.0, decimal degrees (0-360)",
    "dec_deg": "Declination ICRS at epoch J2016.0, decimal degrees (-90 to +90)",
    "frequency": "Primary orbital frequency in cycles per day; the fundamental periodicity detected in the light curve",
    "frequency2": "Secondary frequency in cycles per day; non-null for systems showing a second periodicity (e.g. eccentric orbits with apsidal motion)",
    "global_ranking": "Classification confidence score (0-1) indicating the probability that this source is a genuine eclipsing binary; higher values indicate greater confidence",
    "g_mag": "Mean Gaia G-band (330-1050 nm) apparent magnitude",
    "g_mag_num_obs": "Number of G-band field-of-view transits used in the variability analysis",
    "bp_mag": "Mean Gaia BP-band (330-680 nm) apparent magnitude",
    "rp_mag": "Mean Gaia RP-band (630-1050 nm) apparent magnitude",
    "g_mag_fund": "G-band fundamental Fourier amplitude in magnitudes; measures the depth of the primary eclipse",
    "g_mag_fund_sigma": "Uncertainty on the G-band fundamental amplitude (mag)",
    "num_harmonics_fund": "Number of Fourier harmonics used for the fundamental frequency model; more harmonics indicate a more complex eclipse shape",
    "g_mag_ref2": "G-band second-reference Fourier amplitude in magnitudes; measures the secondary eclipse depth relative to the fundamental",
    "g_mag_ref2_sigma": "Uncertainty on the G-band second-reference amplitude (mag)",
    "num_harmonics_ref2": "Number of Fourier harmonics used for the second reference frequency",
    "model_type": "Light-curve model type used in the Fourier decomposition",
    "num_parameters": "Total number of free parameters in the light-curve model",
    "reduced_chi2": "Reduced chi-squared of the best-fit model; values near 1 indicate a good fit; large values suggest the model does not fully capture the variability",
    "g_mag_geom": "G-band geometric mean magnitude computed from the model; represents the out-of-eclipse baseline brightness",
    "g_mag_geom_sigma": "Uncertainty on the geometric mean magnitude (mag)",
    "g_mag_phase_at_max": "Orbital phase at maximum brightness (0-1); typically near 0.25 or 0.75 between eclipses",
    "g_mag_phase_at_min": "Orbital phase at minimum brightness (0-1); the phase of the primary eclipse",
    "epoch": "Reference epoch for phase zero in Barycentric Julian Date (BJD - 2455197.5 days)",
    "period_days": "Orbital period in days, derived as 1/frequency; ranges from hours (contact binaries) to hundreds of days (detached systems)",
    "bp_rp": "BP-RP color index (bp_mag - rp_mag); traces stellar temperature and reddening; bluer (smaller) values indicate hotter systems",
}

# -- Dataset description ----------------------------------------------------
DESCRIPTION = """\
The Gaia DR3 eclipsing binary catalog contains eclipsing binary candidates identified by the \
ESA Gaia mission's variability processing pipeline. Each source includes orbital frequency, \
light-curve model parameters, global ranking score, and multi-band photometry (G, BP, RP).

Eclipsing binaries are pairs of stars whose orbital plane is aligned with our line of sight, \
causing periodic brightness dips as one star passes in front of the other. Gaia's all-sky \
photometric survey identified these candidates through automated variability classification \
and Fourier-based light-curve modeling. The global_ranking score (0-1) indicates the \
confidence that a source is a genuine eclipsing binary.

Eclipsing binaries are among the most astrophysically valuable variable stars because they \
provide model-independent measurements of fundamental stellar properties. When combined with \
radial velocity curves, the eclipse geometry yields absolute masses and radii of both \
components to precisions of a few percent -- the only direct method for calibrating stellar \
evolution models across a wide range of masses, ages, and compositions. Detached eclipsing \
binaries in particular serve as primary distance indicators: their physical radii and \
effective temperatures give an absolute luminosity that, compared with the observed flux, \
directly yields the distance without recourse to the period-luminosity relations used for \
pulsating stars.

The sheer scale of this Gaia catalog represents an order-of-magnitude increase over previous \
compilations such as the Kepler Eclipsing Binary Catalog (~2,900 systems) or the OGLE \
collection (~450,000 systems in the Magellanic Clouds and bulge). The Fourier-based light \
curve decomposition (fundamental and second-reference amplitudes, number of harmonics, \
reduced chi-squared) enables automated morphological classification into detached, \
semi-detached, and contact configurations without requiring manual inspection of individual \
light curves.
"""


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
    print("Fetching Gaia DR3 Eclipsing Binaries from ESA Gaia Archive...")
    df = fetch_gaia_eb()
    print(f"  {len(df):,} raw rows")

    # Gaia archive returns snake_case columns already -- rename only if needed
    df = df.rename(columns=RENAME)

    # Type conversions -- object columns to numeric
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Type conversions -- integer
    for col in ["g_mag_num_obs", "num_harmonics_fund", "num_harmonics_ref2",
                "num_parameters"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int32")

    # Derived: period from frequency
    if "frequency" in df.columns:
        df["period_days"] = 1.0 / df["frequency"]

    # Derived: color index
    if "bp_mag" in df.columns and "rp_mag" in df.columns:
        df["bp_rp"] = df["bp_mag"] - df["rp_mag"]

    # Drop VizieR/internal columns
    for col in ["recno"]:
        if col in df.columns:
            df = df.drop(columns=[col])

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Sort by source_id
    if "source_id" in df.columns:
        df = df.sort_values("source_id").reset_index(drop=True)

    # Stats
    n_total = len(df)
    g_median = df["g_mag"].median() if "g_mag" in df.columns else float("nan")
    period_median = df["period_days"].median() if "period_days" in df.columns else float("nan")
    rank_median = df["global_ranking"].median() if "global_ranking" in df.columns else float("nan")

    quick_stats = f"""\
- **{n_total:,}** eclipsing binary candidates
- Median G magnitude: {g_median:.2f}
- Median orbital period: {period_median:.4f} days
- Median global ranking: {rank_median:.3f}"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/gaia-dr3-eclipsing-binaries", split="train")
df = ds.to_pandas()

# High-confidence eclipsing binaries
high_conf = df[df["global_ranking"] > 0.5]
print(f"High-confidence EBs: {len(high_conf):,}")

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
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Gaia DR3 Eclipsing Binaries",
        description=DESCRIPTION,
        tags=["space", "gaia", "eclipsing-binaries", "stars", "esa",
              "astronomy", "open-data", "tabular-data", "parquet"],
        source_url="https://gea.esac.esa.int/archive/",
        task_categories=["tabular-classification", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA03606/PIA03606~small.jpg",
            "alt": "The Crab Nebula, a supernova remnant",
            "credit": "NASA/ESA/Hubble",
        },
        related_datasets=[
            "juliensimon/gcvs-variable-stars",
            "juliensimon/aavso-vsx-variable-stars",
            "juliensimon/gaia-dr3-young-stellar-objects",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "ra_deg", "dec_deg", "frequency", "frequency2",
                "global_ranking", "g_mag", "bp_mag", "rp_mag",
                "g_mag_fund", "g_mag_fund_sigma",
                "g_mag_ref2", "g_mag_ref2_sigma",
                "reduced_chi2", "g_mag_geom", "g_mag_geom_sigma",
                "g_mag_phase_at_max", "g_mag_phase_at_min", "epoch",
                "period_days", "bp_rp",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="gaia_dr3_eclipsing_binaries.parquet",
            min_rows=1_500_000,
            expected_columns=["source_id", "frequency", "global_ranking"],
            critical_columns=["source_id", "frequency"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Gaia DR3 eclipsing binaries: {n_total:,} sources",
        )
    print("Done.")


if __name__ == "__main__":
    main()
