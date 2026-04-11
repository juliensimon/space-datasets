#!/usr/bin/env python3
"""Fetch General Catalogue of Variable Stars from VizieR and upload to HF.

Source: Samus' N.N. et al. (2017, Astronomy Reports 61, 80) — the canonical
catalog of variable stars maintained since 1948 by the Sternberg Astronomical
Institute, Moscow.
VizieR catalog: B/gcvs/gcvs_cat
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/gcvs-variable-stars"

ADQL = """\
SELECT GCVS, RAJ2000, DEJ2000, VarType, magMax, l_Min1, Min1, \
Period, Epoch, SpType \
FROM "B/gcvs/gcvs_cat"\
"""

# ── Column mapping ───────────────────────────────────────────────────
RENAME = {
    "GCVS": "gcvs_name",
    "RAJ2000": "ra_deg",
    "DEJ2000": "dec_deg",
    "VarType": "variable_type",
    "magMax": "magnitude_max",
    "Min1": "magnitude_min",
    "l_Min1": "magnitude_min_flag",
    "Period": "period_days",
    "Epoch": "epoch_jd",
    "SpType": "spectral_type",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "gcvs_name": "GCVS official designation — Greek letter + constellation for bright variables (e.g. 'R And', 'delta Cep'), or V+number for fainter ones (e.g. 'V1500 Cyg'); IAU-recognized identifier",
    "ra_deg": "Right ascension, ICRS J2000.0, in decimal degrees (0-360)",
    "dec_deg": "Declination, ICRS J2000.0, in decimal degrees (-90 to +90)",
    "variable_type": "GCVS variability type code; common values: DCEP (classical Cepheid, period-luminosity standard candle), RR (RR Lyrae, old metal-poor horizontal-branch pulsator), M (Mira, AGB long-period pulsator), SR (semi-regular), EA/EB/EW (eclipsing binaries), UV (UV Ceti/flare star), N (nova), SN (supernova); ~100 distinct types",
    "magnitude_max": "Brightness at maximum light in V-band (mag); lower value = brighter star; null for a small number of entries",
    "magnitude_min_flag": "Qualifier on magnitude_min: '(' means value is amplitude (mag range) rather than absolute minimum magnitude; blank otherwise",
    "magnitude_min": "Brightness at minimum light in V-band (mag); for eclipsing binaries this is the primary minimum; amplitude = magnitude_min - magnitude_max; null for irregular variables with poorly defined minima",
    "period_days": "Pulsation or orbital period in days; null for irregular variables (type L, I), single-event novae, and eruptive stars with no recurring period",
    "epoch_jd": "Julian Date of the light curve reference point — epoch of maximum light for pulsators, epoch of primary minimum for eclipsing binaries; null when no reliable epoch has been established",
    "spectral_type": "MK spectral type at the phase of maximum light; null for ~40% of entries where spectral classification is unavailable",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
The General Catalogue of Variable Stars (GCVS) is the canonical reference catalog of variable \
stars, maintained since 1948 by the Sternberg Astronomical Institute at Moscow State University.

Variable stars are stars whose brightness changes over time, either due to intrinsic physical \
processes (pulsation, eruption, rotation) or extrinsic geometry (eclipsing binaries). The GCVS \
is the internationally recognized authority for variable star designations and classifications. \
It has been compiled and updated for over 75 years, serving as the foundation for stellar \
variability research.

The catalog spans an extraordinary range of stellar physics. Mira variables (type M) are \
asymptotic giant branch stars with periods of hundreds of days and visual amplitudes exceeding \
2.5 magnitudes, driven by radial pulsations in their extended hydrogen envelopes. Semi-regular \
variables (SR) occupy a similar evolutionary stage but pulsate with smaller amplitudes and \
less predictable cycles. Eclipsing binaries (EA, EB, EW) are not intrinsically variable at \
all -- their brightness changes arise purely from orbital geometry as one star transits the \
disk of its companion. At the other extreme, eruptive variables like UV Ceti flare stars and \
FU Orionis objects undergo sudden, dramatic outbursts linked to magnetic reconnection events \
or disk accretion instabilities.

Among the most scientifically important classes are the pulsating variables used as standard \
candles: classical Cepheids (DCEP), whose period-luminosity relation underpins the \
extragalactic distance ladder, and RR Lyrae stars (RR), horizontal-branch pulsators that \
trace the old stellar populations of the Galactic halo and globular clusters.

Because the GCVS draws on over a century of photometric monitoring, it captures variability \
on timescales inaccessible to modern surveys that have operated for only a few years. Many \
entries include epochs of maximum light stretching back to the early twentieth century, \
enabling studies of period changes, evolutionary effects, and long-term amplitude modulation \
that would be impossible from any single contemporary survey alone.
"""


def main():
    print("Fetching GCVS from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} variable stars")

    df = df.rename(columns={k: v for k, v in RENAME.items() if k in df.columns})

    # Clean string columns
    for col in ["gcvs_name", "variable_type", "magnitude_min_flag", "spectral_type"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
            )

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    df = df.sort_values("gcvs_name").reset_index(drop=True)

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_with_period = int(df["period_days"].notna().sum())
    n_with_spectral = int(df["spectral_type"].notna().sum())
    n_types = int(df["variable_type"].nunique())
    top_types = df["variable_type"].value_counts().head(5)
    top_types_str = ", ".join(f"{t} ({c:,})" for t, c in top_types.items())

    quick_stats = f"""\
- **{n_total:,}** variable stars
- **{n_types}** variability types
- **{n_with_period:,}** with known period
- **{n_with_spectral:,}** with spectral type
- Top types: {top_types_str}"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/gcvs-variable-stars", split="train")
df = ds.to_pandas()

# Cepheid variables (standard candles for distance measurement)
cepheids = df[df["variable_type"].str.startswith("DCEP", na=False)]
print(f"{len(cepheids):,} classical Cepheids")

# Eclipsing binaries
eclipsing = df[df["variable_type"].str.startswith("E", na=False)]
print(f"{len(eclipsing):,} eclipsing binaries")

# Period-luminosity distribution
import matplotlib.pyplot as plt
valid = df.dropna(subset=["period_days", "magnitude_max"])
valid = valid[valid["period_days"] > 0]
plt.scatter(valid["period_days"], valid["magnitude_max"], s=0.5, alpha=0.3)
plt.xscale("log")
plt.gca().invert_yaxis()
plt.xlabel("Period (days)")
plt.ylabel("Magnitude (max brightness)")
plt.title("GCVS Period vs Magnitude")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="General Catalogue of Variable Stars (GCVS)",
        description=DESCRIPTION,
        tags=["space", "variable-star", "astronomy", "gcvs", "stellar",
              "open-data", "tabular-data", "parquet"],
        source_url="https://www.sai.msu.su/gcvs/gcvs/",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA03606/PIA03606~small.jpg",
            "alt": "The Crab Nebula, a supernova remnant",
            "credit": "NASA/ESA/Hubble",
        },
        related_datasets=[
            "juliensimon/pulsar-catalog",
            "juliensimon/messier-catalog",
            "juliensimon/ngc-ic-catalog",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "ra_deg", "dec_deg", "magnitude_max", "magnitude_min",
                "period_days", "epoch_jd",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="gcvs_variable_stars.parquet",
            min_rows=40_000,
            expected_columns=["gcvs_name", "ra_deg", "dec_deg", "variable_type"],
            critical_columns=["gcvs_name", "ra_deg", "dec_deg"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update GCVS variable stars: {n_total:,} stars",
        )
    print("Done.")


if __name__ == "__main__":
    main()
