#!/usr/bin/env python3
"""Fetch F10.7 Solar Radio Flux data from LASP LISIRD and upload to HF.

Source: NRC Herzberg / DRAO Penticton via LASP LISIRD
Daily 10.7 cm (2800 MHz) solar radio flux -- the primary proxy for solar EUV radiation.
"""

import time

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

LISIRD_URL = "https://lasp.colorado.edu/lisird/latis/dap/penticton_radio_flux.csv"
HF_REPO = "juliensimon/f107-solar-flux"

# ── Column descriptions ────────────────────────────────────────────────
COLUMN_DESCRIPTIONS = {
    "date": "Observation date (UTC); Penticton, Canada measurements continuous since 1947.",
    "observed_flux_sfu": "Daily solar radio flux at 10.7 cm (2800 MHz) measured at local noon in Solar Flux Units (1 SFU = 10^-22 W/m^2/Hz); quiet sun: 65-70 SFU; solar maximum: 200-300+ SFU; required input to atmospheric drag models.",
    "adjusted_flux_sfu": "F10.7 flux corrected to 1 AU from the Sun, removing the ~3.3% variation caused by Earth's orbital eccentricity; preferred value for solar cycle analysis and most operational models.",
    "absolute_flux_sfu": "F10.7 tied to the primary calibration scale (slightly differs from observed due to gain corrections); null for early historical records.",
}

# ── Dataset description ─────────────────────────────────────────────────
DESCRIPTION = """\
Daily F10.7 cm (2800 MHz) solar radio flux measurements from the Dominion Radio \
Astrophysical Observatory in Penticton, BC. The primary proxy for solar extreme \
ultraviolet (EUV) radiation, measured continuously since 1947.

The F10.7 solar radio flux is THE primary proxy for solar extreme ultraviolet (EUV) \
radiation. It has been measured continuously since 1947, making it one of the longest \
running solar activity indices. It is used in atmospheric density models (NRLMSISE-00, \
JB2008, DTM), orbit propagation for drag modelling, ionospheric models for GPS/GNSS \
correction and HF radio propagation, and solar cycle monitoring.

The F10.7 index originates from thermal bremsstrahlung and gyroresonance emission in the \
solar corona and chromosphere, primarily above active regions. Unlike direct EUV measurements \
-- which require space-based instruments -- the 10.7 cm wavelength penetrates Earth's \
atmosphere, allowing ground-based observation. The measurement has been made at local noon \
at the DRAO in Penticton, British Columbia since 1947, making it the longest continuous \
solar activity proxy available after sunspot numbers.

Three variants are provided: the observed flux (as measured), the adjusted flux (corrected \
to 1 AU to remove the ~3.3% variation from Earth's orbital eccentricity), and the absolute \
flux (tied to the calibration scale). During solar maximum, F10.7 can exceed 300 SFU for \
extended periods, increasing thermospheric density at 400 km by a factor of 10-20 compared \
to deep solar minimum (~65 SFU).
"""


def _fetch_with_retry(url, retries=3, timeout=120):
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp
        except Exception as e:
            if attempt == retries:
                raise
            wait = 2 ** attempt
            print(f"  Attempt {attempt} failed ({e}), retrying in {wait}s...")
            time.sleep(wait)


def main():
    print("Fetching F10.7 Solar Radio Flux from LASP LISIRD...")
    resp = _fetch_with_retry(LISIRD_URL)

    df = pd.read_csv(pd.io.common.StringIO(resp.text))
    print(f"  {len(df):,} rows, columns: {list(df.columns)}")

    # The LISIRD CSV columns include units in their names, e.g.:
    #   "time (Julian Date)", "observed_flux (solar flux unit (SFU))", etc.
    time_col = None
    for col in df.columns:
        cl = col.strip().lower()
        if cl.startswith("time"):
            time_col = col
            break

    # Convert time column: Julian Date -> datetime
    if time_col is not None:
        if "julian" in time_col.lower():
            df["date"] = pd.to_datetime(
                df[time_col].astype(float), unit="D", origin="julian", errors="coerce"
            )
        else:
            df["date"] = pd.to_datetime(df[time_col], errors="coerce")
        if time_col != "date":
            df = df.drop(columns=[time_col])

    # Rename flux columns -- match actual names with units
    rename_map = {}
    for col in df.columns:
        cl = col.strip().lower()
        if cl.startswith("observed_flux"):
            rename_map[col] = "observed_flux_sfu"
        elif cl.startswith("adjusted_flux"):
            rename_map[col] = "adjusted_flux_sfu"
        elif cl.startswith("absolute_flux"):
            rename_map[col] = "absolute_flux_sfu"
    df = df.rename(columns=rename_map)

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    if "date" in df.columns:
        df = df.sort_values("date").reset_index(drop=True)

    # ── Domain-specific stats ────────────────────────────────────────
    n = len(df)
    date_min = df["date"].min().strftime("%Y-%m-%d") if "date" in df.columns else "N/A"
    date_max = df["date"].max().strftime("%Y-%m-%d") if "date" in df.columns else "N/A"
    mean_flux = df["observed_flux_sfu"].mean() if "observed_flux_sfu" in df.columns else 0
    max_flux = df["observed_flux_sfu"].max() if "observed_flux_sfu" in df.columns else 0

    quick_stats = f"""\
- **{n:,}** daily observations ({date_min} to {date_max})
- Mean observed flux: **{mean_flux:.1f}** SFU
- Peak observed flux: **{max_flux:.1f}** SFU"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/f107-solar-flux", split="train")
df = ds.to_pandas()

# Recent solar activity
recent = df[df["date"] > "2024-01-01"].sort_values("date")
print(recent[["date", "observed_flux_sfu", "adjusted_flux_sfu"]])

# Solar cycle plot
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(14, 5))
ax.plot(df["date"], df["observed_flux_sfu"], linewidth=0.3, alpha=0.5)
ax.set_xlabel("Date")
ax.set_ylabel("F10.7 (SFU)")
ax.set_title("F10.7 Solar Radio Flux")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="F10.7 Solar Radio Flux (Penticton)",
        description=DESCRIPTION,
        tags=["space", "solar", "f10.7", "space-weather", "ionosphere",
              "atmospheric-drag", "open-data", "tabular-data", "parquet"],
        source_url="https://lasp.colorado.edu/lisird/data/penticton_radio_flux/",
        task_categories=["tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70",
        banner={
            "url": "https://images-assets.nasa.gov/image/iss072e159172/iss072e159172~medium.jpg",
            "alt": "Aurora borealis blankets the Earth, seen from the ISS",
            "credit": "NASA",
        },
        related_datasets=[
            "juliensimon/celestrak-space-weather",
            "juliensimon/geomagnetic-kp-index",
            "juliensimon/dst-index",
            "juliensimon/solar-wind",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=["observed_flux_sfu", "adjusted_flux_sfu", "absolute_flux_sfu"],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="f107_solar_flux.parquet",
            min_rows=20_000,
            expected_columns=["date", "observed_flux_sfu"],
            critical_columns=["date", "observed_flux_sfu"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update F10.7 solar flux: {n:,} records",
        )
    print("Done.")


if __name__ == "__main__":
    main()
