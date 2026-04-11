#!/usr/bin/env python3
"""Fetch Fermi GBM All-Trigger Catalog from HEASARC and upload to HF.

Incremental: downloads existing parquet, fetches recent triggers, merges.
Falls back to full rebuild if no existing data.

HEASARC table: fermigtrig
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import heasarc_query

HF_REPO = "juliensimon/fermi-gbm-triggers"

ADQL_FULL = "SELECT * FROM fermigtrig ORDER BY trigger_time DESC"

OVERLAP_DAYS = 14

RENAME = {
    "name": "name",
    "trigger_time": "trigger_time",
    "ra": "ra",
    "dec": "dec",
    "error_radius": "error_radius",
    "trigger_type": "trigger_type",
    "reliability": "reliability",
    "trigger_signif": "trigger_significance",
    "trigger_timescale": "trigger_timescale",
    "localization_source": "localization_source",
    "class": "classification",
    "bii": "galactic_lat",
    "lii": "galactic_lon",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "name": "Trigger identifier in the format 'bnYYMMDDFFF' (bn + UTC date + fraction of day, e.g. bn170817529)",
    "trigger_time": "Trigger UTC timestamp, converted from MJD; spans 2008-July to present",
    "ra": "Right ascension of best-fit localization, ICRS J2000.0 (degrees, 0-360); null if localization failed",
    "dec": "Declination of best-fit localization, ICRS J2000.0 (degrees, -90 to +90); null if localization failed",
    "error_radius": "1-sigma statistical localization error radius (degrees); GBM typical ~1-10 degrees",
    "trigger_type": "On-board trigger algorithm type (e.g. 'long', 'short', 'soft'); reflects the detector timescale and energy range that fired",
    "reliability": "Ground-based reliability score (0-1) from automated classification; higher = more likely astrophysical",
    "trigger_significance": "Trigger detection significance in sigma above background; threshold for catalog inclusion typically >4.5 sigma",
    "trigger_timescale": "Trigger accumulation timescale in milliseconds (e.g. 16, 64, 256, 1024, 4096 ms); shorter scales identify short GRBs and TGFs",
    "localization_source": "Origin of the reported sky position: 'flight' (on-board), 'ground' (refined post-downlink), or 'IPN' (triangulation)",
    "classification": "Event classification: GRB, SGR (soft gamma repeater), TGF (terrestrial gamma-ray flash), Solar flare, Particle event, Other",
    "galactic_lat": "Galactic latitude of trigger localization (degrees, -90 to +90)",
    "galactic_lon": "Galactic longitude of trigger localization (degrees, 0-360)",
    "is_grb": "True if classification or trigger_type contains 'GRB'; derived column for filtering",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
All triggers from the Fermi Gamma-ray Burst Monitor -- GRBs, solar flares, SGRs, \
terrestrial particles, and more. Updated daily from NASA HEASARC.

The Fermi GBM detects transient events across the full unocculted sky in the 8 keV to \
40 MeV energy range. While the confirmed GRB catalog contains only verified gamma-ray \
bursts, this all-trigger catalog includes every trigger the instrument recorded: GRBs, \
solar flares, soft gamma repeaters (SGRs), terrestrial gamma-ray flashes, particle \
events, and unclassified triggers.

The GBM trigger system operates continuously on multiple timescales (16 ms to 4.096 s), \
flagging statistically significant count-rate increases above background in any of its \
12 NaI detectors (8 keV - 1 MeV) or 2 BGO detectors (200 keV - 40 MeV). The resulting \
trigger population is a rich zoo of astrophysical and non-astrophysical transients.

For multi-messenger astrophysics, the complete trigger catalog is essential because \
sub-threshold events can become significant when combined with external coincidences. \
The landmark GW170817 / GRB 170817A detection demonstrated that even a weak, off-axis \
GRB can produce a marginal GBM trigger that becomes unambiguous only in the context of \
a gravitational-wave detection.\
"""


def transform(df: pd.DataFrame) -> pd.DataFrame:
    """Clean, rename, and type-coerce the raw DataFrame."""
    df.columns = df.columns.str.lower().str.strip()

    # Rename columns that exist
    actual_rename = {k: v for k, v in RENAME.items() if k in df.columns}
    df = df.rename(columns=actual_rename)

    # Coerce numeric columns
    numeric_cols = [
        "trigger_time", "ra", "dec", "error_radius",
        "trigger_significance", "trigger_timescale",
        "galactic_lat", "galactic_lon", "reliability",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Convert trigger_time from MJD to datetime
    if "trigger_time" in df.columns:
        mjd_epoch = pd.Timestamp("1858-11-17")
        df["trigger_time"] = mjd_epoch + pd.to_timedelta(df["trigger_time"], unit="D")

    # Clean string columns
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = (df[col].astype(str).str.strip()
                   .replace({"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}))

    # Derived: is_grb flag
    if "trigger_type" in df.columns:
        df["is_grb"] = df["trigger_type"].str.lower().str.contains("grb", na=False)
    elif "classification" in df.columns:
        df["is_grb"] = df["classification"].str.lower().str.contains("grb", na=False)
    else:
        df["is_grb"] = pd.NA

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Sort by trigger_time descending
    if "trigger_time" in df.columns:
        df = df.sort_values("trigger_time", ascending=False).reset_index(drop=True)

    return df


def main():
    print("Fermi GBM All-Trigger Catalog")
    print("=" * 40)

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Fermi GBM All-Trigger Catalog",
        description=DESCRIPTION,
        tags=["space", "gamma-ray", "fermi", "nasa", "grb", "triggers",
              "astronomy", "physics", "open-data", "tabular-data", "parquet"],
        source_url="https://heasarc.gsfc.nasa.gov/W3Browse/fermi/fermigtrig.html",
        task_categories=["tabular-classification"],
        update_schedule="Daily at 20:00 UTC via GitHub Actions",
        collection_url="https://huggingface.co/collections/juliensimon/physics-datasets-69c2d4682d37dfdb77447bd7",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA03519/PIA03519~small.jpg",
            "alt": "Cassiopeia A supernova remnant in X-ray, optical, and infrared light",
            "credit": "NASA/JPL-Caltech/STScI/CXC/SAO",
        },
        related_datasets=[
            "juliensimon/gamma-ray-bursts",
            "juliensimon/fermi-4fgl-dr4",
            "juliensimon/solar-flare-events",
        ],
    ) as p:
        # Try incremental first
        df_existing = p.download_existing("fermi_gbm_triggers.parquet")

        if df_existing is not None and len(df_existing) > 0:
            # Ensure trigger_time is datetime in existing data
            if "trigger_time" in df_existing.columns:
                df_existing["trigger_time"] = pd.to_datetime(df_existing["trigger_time"])

            max_date = df_existing["trigger_time"].max()
            fetch_from_mjd = (pd.Timestamp(max_date) - pd.Timedelta(days=OVERLAP_DAYS)
                              - pd.Timestamp("1858-11-17")).total_seconds() / 86400.0
            adql_inc = (
                f"SELECT * FROM fermigtrig "
                f"WHERE trigger_time >= {fetch_from_mjd:.6f} "
                f"ORDER BY trigger_time DESC"
            )
            print(f"  Incremental fetch: last {OVERLAP_DAYS} days overlap from {max_date}")
            df_new = heasarc_query("fermigtrig", adql_inc, timeout=300)
            df_new = transform(df_new)

            if not df_new.empty:
                df = p.merge(df_existing, df_new, dedup_on="name", sort_by="trigger_time")
                # Re-sort descending after merge (merge sorts ascending)
                df = df.sort_values("trigger_time", ascending=False).reset_index(drop=True)
                print(f"  Merged: {len(df):,} triggers ({len(df) - len(df_existing):+,} net)")
            else:
                df = df_existing
                print("  No new triggers")
        else:
            # Full rebuild
            print("  Full rebuild...")
            df = heasarc_query("fermigtrig", ADQL_FULL, timeout=300)
            df = transform(df)

        n_total = len(df)
        print(f"  {n_total:,} triggers total")

        # Stats for README
        n_grb = int(df["is_grb"].sum()) if "is_grb" in df.columns else 0
        n_non_grb = n_total - n_grb

        trigger_types = {}
        if "trigger_type" in df.columns:
            trigger_types = df["trigger_type"].value_counts().head(8).to_dict()

        date_min = df["trigger_time"].min()
        date_max = df["trigger_time"].max()

        type_lines = "\n".join(f"- **{count:,}** {ttype}" for ttype, count in trigger_types.items())

        quick_stats = f"""\
- **{n_total:,}** triggers ({date_min:%Y-%m-%d} to {date_max:%Y-%m-%d})
- **{n_grb:,}** classified as GRBs
- **{n_non_grb:,}** non-GRB triggers (solar flares, SGRs, particles, etc.)"""
        if type_lines:
            quick_stats += f"\n\n### Trigger type breakdown\n{type_lines}"

        usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/fermi-gbm-triggers", split="train")
df = ds.to_pandas()

# Filter to confirmed GRBs
grbs = df[df["is_grb"] == True]
print(f"{len(grbs):,} GRBs out of {len(df):,} total triggers")

# Non-GRB triggers
non_grb = df[df["is_grb"] == False]
print(non_grb["trigger_type"].value_counts())

# Triggers per year
import matplotlib.pyplot as plt
df["year"] = df["trigger_time"].dt.year
df.groupby("year").size().plot(kind="bar", title="Fermi GBM Triggers per Year")
plt.show()
```"""

        p.publish(
            df,
            filename="fermi_gbm_triggers.parquet",
            min_rows=10_000,
            expected_columns=["name", "trigger_time", "ra", "dec"],
            critical_columns=["name", "trigger_time"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Fermi GBM triggers: {n_total:,} triggers",
        )
    print("Done.")


if __name__ == "__main__":
    main()
