#!/usr/bin/env python3
"""Fetch solar radio burst events from NOAA SWPC and upload to HF.

NOAA SWPC edited_events.json covers ~30 days of events. This pipeline uses
incremental mode: download existing parquet from HF, fetch recent events,
merge and deduplicate.
"""

import time

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

SWPC_URL = "https://services.swpc.noaa.gov/json/edited_events.json"
HF_REPO = "juliensimon/solar-radio-bursts"
RADIO_TYPES = {"RSP", "RBR", "RNS"}

# ── Column descriptions ───────────────────────────────────────────────
COLUMN_DESCRIPTIONS = {
    "start_date": "UTC time when the radio burst began",
    "end_date": "UTC time when the radio burst ended; null if event was still in progress at report time",
    "max_date": "UTC time of maximum radio flux intensity; null for noise storms where peak is ill-defined",
    "type": "SWPC event type mapped to descriptive label: 'spectral_sweep' (RSP — frequency-drifting burst including Type II/III/IV/V), 'fixed_freq_burst' (RBR — discrete burst at a single frequency), 'noise_storm' (RNS — sustained broadband emission from active regions)",
    "frequency": "Observing frequency or frequency range in MHz (e.g., '245' or '025-180'); Type III bursts can drift from >100 MHz to <10 MHz in seconds as electron beams propagate outward",
    "observatory": "SWPC station code reporting the event (e.g., 'SGD', 'LEA', 'BOU'); multiple observatories may report the same event independently",
    "quality": "SWPC data quality flag indicating analyst confidence in the event classification (e.g., 'Good', 'Poor'); null if not assigned",
    "burst_class": "Roman numeral subtype for spectral sweep events (e.g., 'III/2', 'II', 'IV'); Roman numeral indicates burst type (I=noise storm enhancement, II=slow-drift shock, III=fast electron beam, IV=continuum, V=post-III continuum); null for fixed-frequency bursts and noise storms",
    "region": "NOAA active region number causally associated with the burst; null if no active region link was established",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Catalog of solar radio burst events (spectral sweeps, fixed-frequency bursts, noise storms) \
from NOAA SWPC. Updated daily with incremental merge.

Solar radio bursts are produced by energetic electrons accelerated during solar flares and \
coronal mass ejections. They are important indicators of space weather activity:

- **Spectral sweeps (RSP)** — frequency-drifting bursts including Type II (CME shocks), \
III (electron beams), IV (post-flare continuum), V (short continuum)
- **Fixed-frequency bursts (RBR)** — discrete bursts at a single frequency
- **Noise storms (RNS)** — sustained broadband emission from active regions

The physics behind these emissions is coherent plasma radiation. When energetic electrons \
stream through the solar corona, they excite Langmuir waves at the local plasma frequency, \
which then convert into electromagnetic radiation at the fundamental and second harmonic. \
Because the plasma frequency depends on electron density — which decreases with altitude in \
the corona — Type III bursts exhibit a characteristic fast frequency drift as the electron \
beam propagates outward along open magnetic field lines.

Solar radio bursts are among the earliest detectable signatures of eruptive solar activity, \
often preceding the arrival of energetic particles and geomagnetic disturbances at Earth by \
minutes to days. Monitoring them is therefore critical for operational space weather forecasting."""


def fetch_swpc_radio_events() -> pd.DataFrame:
    """Fetch solar radio burst events from NOAA SWPC (3 retries, exponential backoff)."""
    print("  Fetching NOAA SWPC edited events...")
    for attempt in range(3):
        try:
            resp = requests.get(SWPC_URL, timeout=60)
            resp.raise_for_status()
            break
        except requests.RequestException as exc:
            if attempt == 2:
                print(f"  SWPC fetch failed after 3 attempts: {exc}")
                return pd.DataFrame()
            wait = 2 ** attempt
            print(f"  Retry {attempt + 1}/2 after {wait}s: {exc}")
            time.sleep(wait)
    data = resp.json()
    print(f"  Total SWPC events: {len(data)}")

    # Filter to radio event types only
    radio = [e for e in data if e.get("type", "") in RADIO_TYPES]
    if not radio:
        print("  No radio events in response")
        return pd.DataFrame()

    df = pd.DataFrame(radio)
    print(f"  Radio events: {len(df)}")
    return df


def normalize_radio_df(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize SWPC radio events to a clean schema."""
    col_map = {
        "begin_datetime": "start_date",
        "end_datetime": "end_date",
        "max_datetime": "max_date",
    }
    df = df.rename(columns=col_map)

    # Parse datetimes
    for col in ["start_date", "end_date", "max_date"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    # Map SWPC type codes to descriptive names
    type_map = {"RSP": "spectral_sweep", "RBR": "fixed_freq_burst", "RNS": "noise_storm"}
    df["type"] = df["type"].map(type_map).fillna(df["type"])

    # For RSP events, particulars1 has the Roman numeral burst classification (e.g., "III/2")
    if "particulars1" in df.columns:
        df["burst_class"] = df["particulars1"].where(
            df["type"] == "spectral_sweep", other=pd.NA
        )

    # Keep only described columns
    keep = [c for c in COLUMN_DESCRIPTIONS if c in df.columns]
    df = df[keep]

    # Clean strings
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].astype(str).str.strip().replace(
            {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA, "none": pd.NA}
        )

    return df


def main():
    print("Fetching solar radio burst events...")

    df_new = fetch_swpc_radio_events()
    if not df_new.empty:
        df_new = normalize_radio_df(df_new)

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Solar Radio Burst Events",
        description=DESCRIPTION,
        tags=["space", "solar", "radio-burst", "type-ii", "type-iii",
              "space-weather", "noaa", "swpc", "open-data", "tabular-data", "parquet"],
        source_url="https://www.swpc.noaa.gov/",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70",
        banner={"url": "https://images-assets.nasa.gov/image/iss072e159172/iss072e159172~medium.jpg",
                "alt": "Aurora borealis blankets the Earth, seen from the ISS",
                "credit": "NASA"},
        update_schedule="Daily at 19:00 UTC",
        related_datasets=[
            "juliensimon/solar-flare-events",
            "juliensimon/donki-space-weather-events",
            "juliensimon/space-weather-indices",
        ],
    ) as p:
        df_existing = p.download_existing("solar_radio_bursts.parquet")

        if df_new.empty and (df_existing is None or len(df_existing) == 0):
            print("::error::No radio events from SWPC and no existing data")
            raise SystemExit(1)

        if df_new.empty:
            print(f"  No new events from SWPC (quiet period or transient); using {len(df_existing):,} existing rows")
            df = df_existing
        elif df_existing is not None and len(df_existing) > 0:
            df_existing["start_date"] = pd.to_datetime(df_existing["start_date"])

            # Align columns
            for col in df_new.columns:
                if col not in df_existing.columns:
                    df_existing[col] = pd.NA
            for col in df_existing.columns:
                if col not in df_new.columns:
                    df_new[col] = pd.NA

            dedup_cols = ["start_date", "frequency", "observatory"]
            dedup_cols = [c for c in dedup_cols if c in df_new.columns and c in df_existing.columns]
            df = p.merge(df_existing, df_new, dedup_on=dedup_cols, sort_by="start_date")
            print(f"  Merged: {len(df):,} events")
        else:
            df = df_new

        df = df.sort_values("start_date").reset_index(drop=True)

        # Keep only described columns
        df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

        df = p.clean(df, strings=["type", "frequency", "observatory", "quality",
                                   "burst_class", "region"])

        # Stats
        n_total = len(df)
        date_min = df["start_date"].min().strftime("%Y-%m-%d")
        date_max = df["start_date"].max().strftime("%Y-%m-%d")
        n_types = int(df["type"].nunique()) if "type" in df.columns else 0
        top_types = df["type"].value_counts().head(5) if "type" in df.columns else pd.Series()
        top_types_str = ", ".join(f"{t} ({c:,})" for t, c in top_types.items())

        quick_stats = f"""\
- **{n_total:,}** radio burst events ({date_min} to {date_max})
- **{n_types}** event type classifications
- Top types: {top_types_str}"""

        usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/solar-radio-bursts", split="train")
df = ds.to_pandas()

# Spectral sweep events (includes Type II, III, IV, V)
sweeps = df[df["type"] == "spectral_sweep"]
print(f"{len(sweeps):,} spectral sweep events")

# Type III bursts specifically
type_iii = sweeps[sweeps["burst_class"].str.contains("III", na=False)]

# Event type distribution over time
import matplotlib.pyplot as plt

df["month"] = df["start_date"].dt.to_period("M")
monthly = df.groupby(["month", "type"]).size().unstack(fill_value=0)
monthly.plot.bar(stacked=True, figsize=(12, 4))
plt.title("Solar Radio Burst Events by Type")
plt.ylabel("Count")
plt.tight_layout()
plt.show()
```"""

        p.publish(
            df,
            filename="solar_radio_bursts.parquet",
            min_rows=10,
            expected_columns=["start_date", "type", "frequency"],
            critical_columns=["start_date"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update solar radio bursts: {n_total:,} events",
        )
    print("Done.")


if __name__ == "__main__":
    main()
