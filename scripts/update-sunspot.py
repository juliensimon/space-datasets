#!/usr/bin/env python3
"""Fetch SILSO daily sunspot numbers and upload to HF.

Source: SILSO, World Data Center for the Sunspot Index,
Royal Observatory of Belgium, Brussels.
The longest continuous scientific observation in history, since 1818.
"""

import pandas as pd

from hf_dataset_utils import Pipeline

SILSO_URL = "https://www.sidc.be/SILSO/DATA/SN_d_tot_V2.0.csv"
HF_REPO = "juliensimon/silso-sunspot-number"

# ── Column descriptions ────────────────────────────────────────────────
COLUMN_DESCRIPTIONS = {
    "date": "Observation date (UTC); SILSO daily records begin 1818-01-01.",
    "decimal_date": "Fractional year representation of the date (e.g., 2024.5 ~ July 2 2024); useful for continuous time-series computations.",
    "sunspot_number": "International Sunspot Number (ISN v2.0) -- daily count of sunspots on the solar disk using the Wolf formula (R = k(10g + s)); solar minimum: ~0-10; solar maximum: 150-300+; approximately 11-year cycle; null for days with no observation; v2.0 values are ~1.6x the previous v1.0 series.",
    "std_dev": "Standard deviation of individual station observations around the network mean for that day; larger values indicate disagreement between observers or complex sunspot groups.",
    "n_observations": "Number of SILSO network observing stations that contributed valid measurements that day; typical range 10-50; lower values (early historical records) reflect fewer contributing observers.",
    "is_provisional": "True if the value has not yet been finalized by SILSO (recent ~30 days); provisional values may be revised when additional observer data arrives; False for definitive historical values.",
}

# ── Dataset description ─────────────────────────────────────────────────
DESCRIPTION = """\
Daily total sunspot numbers from the World Data Center SILSO at the Royal Observatory \
of Belgium. This is the longest continuous scientific observation in history, with \
systematic daily records since 1818 and international coordination since 1981.

The International Sunspot Number is the primary index of solar activity, tracking the \
number of sunspots visible on the solar disk each day. Sunspots are temporary phenomena \
on the Sun's photosphere caused by magnetic flux concentrations. Their number follows an \
approximately 11-year cycle (the Schwabe cycle) that profoundly affects space weather, \
satellite operations, radio communications, and Earth's upper atmosphere.

Sunspots are regions where intense magnetic flux tubes (typically 0.1-0.3 T) emerge through \
the photosphere, inhibiting convective energy transport and creating dark spots roughly \
1000-1500 K cooler than the surrounding ~5800 K surface. The daily sunspot number is \
computed using the Wolf formula (R = k(10g + s), where g is the number of sunspot groups, \
s is the total number of individual spots, and k is a station-dependent scaling factor), \
then combined across the observer network into a single international index.

The approximately 11-year Schwabe cycle drives variations in total solar irradiance (order \
0.1%), extreme ultraviolet flux (factor of 10 or more), solar flare and CME rates, and the \
overall heliospheric magnetic field strength. These variations have direct consequences for \
satellite drag, HF radio propagation, radiation exposure, and modulation of galactic cosmic \
ray flux at Earth.

The SILSO Version 2.0 series, released in 2015, recalibrated the entire historical record \
back to 1818 to correct for discontinuities introduced by changes in the reference observer. \
This makes it the most homogeneous long-baseline solar activity record available, spanning \
over 200 years of daily observations and encompassing roughly 19 complete solar cycles.
"""


def main():
    print("Fetching SILSO daily sunspot numbers...")
    df = pd.read_csv(
        SILSO_URL,
        sep=";",
        header=None,
        names=[
            "year", "month", "day", "decimal_date",
            "sunspot_number", "std_dev", "n_observations", "provisional_flag",
        ],
    )
    print(f"  {len(df):,} raw rows")

    # Filter out rows with day=0 (monthly aggregates mixed in)
    df = df[df["day"] > 0].copy()
    print(f"  {len(df):,} daily rows after filtering day>0")

    # Create proper date column
    df["date"] = pd.to_datetime(
        df[["year", "month", "day"]].rename(
            columns={"year": "year", "month": "month", "day": "day"}
        ),
        errors="coerce",
    )

    # sunspot_number: -1 means missing -> NaN, then convert to Int64
    df["sunspot_number"] = df["sunspot_number"].replace(-1, pd.NA)
    df["sunspot_number"] = pd.to_numeric(df["sunspot_number"], errors="coerce").astype("Int64")

    # Numeric coercion
    for col in ["decimal_date", "std_dev"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["n_observations"] = pd.to_numeric(df["n_observations"], errors="coerce").astype("Int64")

    # provisional_flag: 1 = provisional, 0 = definitive -> is_provisional boolean
    df["is_provisional"] = df["provisional_flag"].map({1: True, 0: False})

    # Drop intermediate columns
    df = df.drop(columns=["year", "month", "day", "provisional_flag"])

    # Reorder to match COLUMN_DESCRIPTIONS
    df = df[["date", "decimal_date", "sunspot_number", "std_dev", "n_observations", "is_provisional"]]

    # Sort by date
    df = df.sort_values("date").reset_index(drop=True)

    # ── Domain-specific stats ────────────────────────────────────────
    n_total = len(df)
    date_min = df["date"].min().strftime("%Y-%m-%d")
    date_max = df["date"].max().strftime("%Y-%m-%d")
    max_sn = int(df["sunspot_number"].max())
    max_sn_date = df.loc[df["sunspot_number"].idxmax(), "date"].strftime("%Y-%m-%d")
    n_provisional = int(df["is_provisional"].sum())

    # Current solar cycle 25 stats (started ~2019-12)
    sc25 = df[df["date"] >= "2019-12-01"]
    sc25_max = int(sc25["sunspot_number"].max()) if len(sc25) > 0 else 0
    sc25_mean = sc25["sunspot_number"].mean()

    quick_stats = f"""\
- **{n_total:,}** daily records ({date_min} to {date_max})
- All-time maximum: **{max_sn}** on {max_sn_date}
- **{n_provisional:,}** provisional values
- Solar Cycle 25 (current): peak so far **{sc25_max}**, mean **{sc25_mean:.1f}**"""

    usage = """\
```python
from datasets import load_dataset
import pandas as pd

ds = load_dataset("juliensimon/silso-sunspot-number", split="train")
df = ds.to_pandas()

# Plot solar cycles
import matplotlib.pyplot as plt
df["date"] = pd.to_datetime(df["date"])
monthly = df.set_index("date").resample("MS")["sunspot_number"].mean()
monthly.plot(figsize=(14, 4), title="Solar Cycles - Monthly Mean Sunspot Number")
plt.ylabel("Sunspot Number")
plt.show()

# Current solar cycle 25
sc25 = df[df["date"] >= "2019-12-01"]
print(f"Cycle 25 max so far: {sc25['sunspot_number'].max()}")
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="SILSO Daily Sunspot Number",
        description=DESCRIPTION,
        tags=["space", "sun", "sunspot", "solar-cycle", "space-weather",
              "silso", "open-data", "tabular-data", "parquet"],
        source_url="https://www.sidc.be/SILSO/",
        license="cc-by-nc-4.0",
        task_categories=["tabular-regression", "time-series-forecasting"],
        collection_url="https://huggingface.co/collections/juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70",
        banner={
            "url": "https://images-assets.nasa.gov/image/brief-outburst_16760026566_o/brief-outburst_16760026566_o~medium.jpg",
            "alt": "The Sun showing solar activity captured by NASA's Solar Dynamics Observatory",
            "credit": "NASA/SDO",
        },
        related_datasets=[
            "juliensimon/solar-flare-events",
            "juliensimon/geomagnetic-kp-index",
            "juliensimon/dst-index",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=["decimal_date", "std_dev"],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="silso_sunspot_number.parquet",
            min_rows=50_000,
            expected_columns=["date", "sunspot_number", "n_observations", "std_dev", "is_provisional"],
            critical_columns=["date", "sunspot_number"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update SILSO sunspot numbers: {n_total:,} records",
        )
    print("Done.")


if __name__ == "__main__":
    main()
