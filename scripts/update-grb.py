#!/usr/bin/env python3
"""Fetch Fermi GBM Gamma-Ray Burst Catalog from HEASARC and upload to HF.

Source: Fermi GBM Burst Catalog (fermigbrst)
HEASARC table: fermigbrst
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import heasarc_query

HF_REPO = "juliensimon/gamma-ray-bursts"

ADQL = """\
SELECT name, trigger_time, ra, dec, t90, t90_error, t50, t50_error,
  fluence, fluence_error, flux_256, pflx_best_fitting_model,
  flnc_band_ampl, flnc_band_epeak, flnc_band_alpha, flnc_band_beta
FROM fermigbrst ORDER BY trigger_time DESC\
"""

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "name": "GRB designation encoding the discovery date and sequence letter (e.g. 'GRB 170817A' = Aug 17 2017, first event that day); 'GRB 170817A' is the electromagnetic counterpart to GW170817, the first confirmed neutron-star merger",
    "trigger_time": "UTC time of the GBM on-board trigger; converted from Modified Julian Date; precision ~milliseconds",
    "ra": "Right ascension of best-fit GRB position (ICRS J2000.0, degrees, 0-360); initial GBM localization uncertainty is several degrees; null if localization failed",
    "dec": "Declination of best-fit GRB position (ICRS J2000.0, degrees, -90 to +90); null if localization failed",
    "t90": "Duration containing 90% of the burst's total photon counts (seconds); short GRBs have T90 < 2 s (neutron star mergers), long GRBs have T90 > 2 s (massive star collapse); bimodal distribution separates two physically distinct progenitor populations; null for bursts with insufficient counts",
    "t90_error": "1-sigma statistical uncertainty on T90 (seconds); null when T90 is not measured",
    "t50": "Duration containing the central 50% of burst counts (seconds); narrower than T90, less sensitive to faint extended emission; useful for comparing burst timescales across detectors",
    "t50_error": "1-sigma statistical uncertainty on T50 (seconds); null when T50 is not measured",
    "fluence": "Total gamma-ray fluence integrated over the burst duration (erg/cm^2); proxy for apparent isotropic energy release; null when spectral fit did not converge",
    "fluence_error": "1-sigma uncertainty on fluence (erg/cm^2); null when fluence is not measured",
    "flux_256": "Peak photon flux measured on a 256 ms timescale (photons/cm^2/s); determines detectability and is used in the logN-logP distribution; null when peak flux measurement failed",
    "pflx_best_fitting_model": "Name of the spectral model providing the best fit to the peak-flux time interval (e.g. 'band', 'comp', 'plaw', 'sbpl'); drives which set of spectral parameters is most reliable",
    "flnc_band_ampl": "Amplitude (normalization) of the Band function fit to the time-integrated (fluence) spectrum (photons/cm^2/s/keV at pivot energy); null when the Band model is not the best fit or fit failed",
    "flnc_band_epeak": "Peak energy of the nuFnu spectrum from the Band function fit (keV); most GRBs fall between 100-2000 keV; correlates with isotropic luminosity (Amati relation); null when Band fit failed",
    "flnc_band_alpha": "Low-energy photon spectral index of the Band function (dimensionless); typically -1.5 to 0; values harder than -2/3 violate synchrotron line-of-death, constraining emission models; null when Band fit failed",
    "flnc_band_beta": "High-energy photon spectral index of the Band function (dimensionless); typically -3 to -2; describes the steep spectral cutoff above E_peak; null when Band fit failed or high-energy data insufficient",
    "duration_class": "Physical classification by T90: 'short' (T90 < 2 s, compact binary merger progenitor) or 'long' (T90 >= 2 s, massive star core collapse progenitor); null when T90 is unavailable",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
GRB detections from Fermi Gamma-ray Burst Monitor with duration, flux, and spectral \
parameters.

Gamma-ray bursts (GRBs) are the most energetic explosions in the universe. They come in \
two classes based on duration: short GRBs (T90 < 2 s, from neutron star mergers) and \
long GRBs (T90 >= 2 s, from massive star collapse). The Fermi GBM has been detecting \
GRBs across the full unocculted sky since 2008.

This dataset includes duration measurements (T90, T50), fluence, peak flux, and Band \
function spectral parameters for each burst.

The physical dichotomy between short and long GRBs reflects fundamentally different \
progenitor systems. Short GRBs (T90 < 2 s) arise from the coalescence of compact binary \
systems -- neutron star-neutron star or neutron star-black hole mergers -- as spectacularly \
confirmed by the joint gravitational-wave and electromagnetic detection of GRB 170817A / \
GW170817. Long GRBs (T90 > 2 s) are produced by the core collapse of massive Wolf-Rayet \
stars, where a newly formed black hole launches ultra-relativistic jets that punch through \
the stellar envelope.

The Fermi GBM is one of the workhorses of modern GRB astronomy, detecting roughly 240 \
bursts per year across its 12 sodium iodide (NaI, 8 keV - 1 MeV) and 2 bismuth germanate \
(BGO, 200 keV - 40 MeV) detectors. This catalog is a cornerstone for multi-messenger \
astrophysics: GBM triggers initiate rapid follow-up campaigns across the electromagnetic \
spectrum and provide temporal coincidence windows for searches in gravitational-wave and \
neutrino data.
"""


def main():
    print("Fetching Fermi GBM Gamma-Ray Burst Catalog from HEASARC...")
    df = heasarc_query("fermigbrst", ADQL)
    print(f"  {len(df):,} GRBs fetched")

    # Convert trigger_time from MJD to datetime
    # MJD epoch: 1858-11-17T00:00:00
    mjd_epoch = pd.Timestamp("1858-11-17")
    df["trigger_time"] = pd.to_numeric(df["trigger_time"], errors="coerce")
    df["trigger_time"] = mjd_epoch + pd.to_timedelta(df["trigger_time"], unit="D")

    # Derived column: duration class (fundamental GRB classification)
    df["duration_class"] = df["t90"].apply(
        lambda x: "short" if pd.notna(x) and x < 2.0 else ("long" if pd.notna(x) else None)
    )

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Sort by trigger_time DESC
    df = df.sort_values("trigger_time", ascending=False).reset_index(drop=True)

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_short = int((df["duration_class"] == "short").sum())
    n_long = int((df["duration_class"] == "long").sum())
    date_min = df["trigger_time"].min()
    date_max = df["trigger_time"].max()
    date_range = f"{date_min:%Y-%m-%d} to {date_max:%Y-%m-%d}"

    brightest_idx = df["fluence"].idxmax()
    brightest_name = df.loc[brightest_idx, "name"] if pd.notna(brightest_idx) else "N/A"
    brightest_fluence = df.loc[brightest_idx, "fluence"] if pd.notna(brightest_idx) else 0

    quick_stats = f"""\
- **{n_total:,}** gamma-ray bursts
- **{n_short:,}** short GRBs, **{n_long:,}** long GRBs
- Date range: **{date_range}**
- Brightest burst: **{brightest_name}** (fluence {brightest_fluence:.2e} erg/cm^2)"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/gamma-ray-bursts", split="train")
df = ds.to_pandas()

# Short vs long GRBs
short = df[df["duration_class"] == "short"]
long = df[df["duration_class"] == "long"]
print(f"{len(short):,} short, {len(long):,} long GRBs")

# Brightest bursts
top = df.nlargest(10, "fluence")[["name", "trigger_time", "fluence", "t90"]]

# T90 distribution
import matplotlib.pyplot as plt
df["t90"].dropna().apply(lambda x: max(x, 1e-3)).hist(bins=50, log=True)
plt.xlabel("T90 (s)")
plt.title("GRB Duration Distribution")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Fermi GBM Gamma-Ray Burst Catalog",
        description=DESCRIPTION,
        tags=["space", "gamma-ray-burst", "grb", "fermi", "nasa",
              "astronomy", "high-energy", "open-data", "tabular-data", "parquet"],
        source_url="https://heasarc.gsfc.nasa.gov/W3Browse/fermi/fermigbrst.html",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e002215/GSFC_20171208_Archive_e002215~medium.jpg",
            "alt": "The gamma-ray sky as seen by NASA's Fermi telescope",
            "credit": "NASA/DOE/Fermi LAT Collaboration",
        },
        related_datasets=[
            "juliensimon/pulsar-catalog",
            "juliensimon/supernova-remnants",
            "juliensimon/gravitational-wave-events",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "ra", "dec", "t90", "t90_error", "t50", "t50_error",
                "fluence", "fluence_error", "flux_256",
                "flnc_band_ampl", "flnc_band_epeak", "flnc_band_alpha", "flnc_band_beta",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="grb.parquet",
            min_rows=3000,
            expected_columns=["name", "trigger_time", "t90", "fluence"],
            critical_columns=["name", "trigger_time"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update GRB catalog: {n_total:,} bursts",
        )
    print("Done.")


if __name__ == "__main__":
    main()
