#!/usr/bin/env python3
"""Fetch CelesTrak SOCRATES satellite conjunction predictions and upload to HF.

SOCRATES (Satellite Orbital Conjunction Reports Assessing Threatening Encounters
in Space) screens the public catalog for close approaches over the next ~7 days.
This pipeline accumulates the genuinely close events into a growing "near-miss"
history. To stay bounded and meaningful it keeps only conjunctions with a miss
distance <= 1 km OR a maximum collision probability >= 1e-4, deduped on the
object pair and time of closest approach.
"""

import io
import time

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

HF_REPO = "juliensimon/satellite-conjunctions"

SOCRATES_URL = "https://celestrak.org/SOCRATES/sort-minRange.csv"

# Curation thresholds for what counts as a recorded near-miss.
RANGE_KM_MAX = 1.0
PROB_MIN = 1e-4

RENAME = {
    "NORAD_CAT_ID_1": "norad_id_1",
    "OBJECT_NAME_1": "object_name_1",
    "DSE_1": "days_since_epoch_1",
    "NORAD_CAT_ID_2": "norad_id_2",
    "OBJECT_NAME_2": "object_name_2",
    "DSE_2": "days_since_epoch_2",
    "TCA": "tca",
    "TCA_RANGE": "min_range_km",
    "TCA_RELATIVE_SPEED": "relative_speed_kms",
    "MAX_PROB": "max_probability",
    "DILUTION": "dilution_km",
}

# ── Column descriptions ───────────────────────────────────────────────
COLUMN_DESCRIPTIONS = {
    "event_key": "Stable identifier for a conjunction event: the two NORAD IDs (sorted) joined with the time of closest approach rounded to the hour. Used to deduplicate the same physical encounter as its prediction is refined across daily runs.",
    "norad_id_1": "NORAD catalog number of the first object in the conjunction pair.",
    "object_name_1": "Name of the first object (payload, rocket body, or debris) as listed in the satellite catalog.",
    "days_since_epoch_1": "Age in days of the orbital element set (TLE) used for the first object at the time of screening. Larger values mean a staler TLE and a less reliable prediction.",
    "norad_id_2": "NORAD catalog number of the second object in the conjunction pair.",
    "object_name_2": "Name of the second object in the conjunction pair.",
    "days_since_epoch_2": "Age in days of the orbital element set (TLE) used for the second object. Larger values mean a less reliable prediction.",
    "tca": "Time of Closest Approach (UTC): the predicted moment the two objects are nearest.",
    "min_range_km": "Predicted miss distance at closest approach, in kilometers. The headline figure of a conjunction screen.",
    "relative_speed_kms": "Relative velocity of the two objects at closest approach, in km/s. High closing speeds (10-15 km/s are typical for crossing orbits) mean a tiny timing error translates to a large position error.",
    "max_probability": "Maximum collision probability for the encounter (dimensionless, 0-1), computed by scaling the assumed position uncertainty to its worst case. A screening upper bound, not an operational probability.",
    "dilution_km": "Dilution distance (km): the combined position-uncertainty scale at which the maximum collision probability occurs. Reflects how uncertain the TLE-based positions are.",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
A growing log of close approaches ("conjunctions") between catalogued objects in \
Earth orbit, from CelesTrak's SOCRATES screening service. Updated daily, \
accumulating distinct near-miss events over time.

SOCRATES (Satellite Orbital Conjunction Reports Assessing Threatening Encounters \
in Space) propagates the public two-line element (TLE) catalog forward roughly a \
week and reports every pair of objects predicted to pass within a few kilometers of \
each other. Each report gives the time of closest approach, the predicted miss \
distance, the relative speed, and an upper-bound collision probability. This is the \
public situational-awareness tool for tracking the increasingly crowded LEO \
environment, where active payloads, spent rocket bodies, and debris fragments \
routinely thread past one another.

To keep this dataset focused and bounded, it does not store the full daily screen \
(roughly 150,000 sub-5-km pairings). Instead it records only the genuinely close or \
risky events -- those with a predicted miss distance of 1 km or less, or a maximum \
collision probability of 1e-4 or greater -- and deduplicates the same physical \
encounter as its prediction is refined from day to day. The result is a historical \
record of serious near-misses suitable for studying conjunction rates, the objects \
and orbital regimes most often involved, and the growth of collision risk over time. \
Because predictions are derived from TLEs rather than high-precision owner/operator \
ephemerides, the figures are a screening aid, not operational collision-avoidance \
guidance."""


def fetch_socrates():
    """Fetch and curate the SOCRATES close-approach screen (CelesTrak 500-retry)."""
    print("  Fetching SOCRATES conjunctions from CelesTrak...")
    for attempt in range(3):
        try:
            resp = requests.get(SOCRATES_URL, timeout=60,
                                headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            break
        except requests.RequestException as exc:
            if attempt == 2:
                raise
            wait = 2 ** attempt
            print(f"  Retry {attempt + 1}/2 after {wait}s: {exc}")
            time.sleep(wait)

    df = pd.read_csv(io.StringIO(resp.text)).rename(columns=RENAME)
    n_all = len(df)

    for col in ["min_range_km", "relative_speed_kms", "max_probability", "dilution_km",
                "days_since_epoch_1", "days_since_epoch_2"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["tca"] = pd.to_datetime(df["tca"], errors="coerce")

    # Clean the trailing CelesTrak status markers ("[+]" / "[-]") off the names.
    for col in ["object_name_1", "object_name_2"]:
        df[col] = df[col].astype(str).str.replace(r"\s*\[[+-]\]\s*$", "", regex=True).str.strip()

    # Curate to genuinely close / risky encounters.
    keep = (df["min_range_km"] <= RANGE_KM_MAX) | (df["max_probability"] >= PROB_MIN)
    df = df[keep & df["tca"].notna()].copy()
    print(f"  {n_all:,} screened pairs -> {len(df):,} near-misses "
          f"(<= {RANGE_KM_MAX} km or Pc >= {PROB_MIN}); dropped {n_all - len(df):,}")

    lo = df[["norad_id_1", "norad_id_2"]].min(axis=1).astype(int)
    hi = df[["norad_id_1", "norad_id_2"]].max(axis=1).astype(int)
    df["event_key"] = (lo.astype(str) + "-" + hi.astype(str) + "-"
                       + df["tca"].dt.strftime("%Y%m%d%H"))

    cols = ["event_key"] + list(RENAME.values())
    return df[cols].sort_values("tca").reset_index(drop=True)


def main():
    print("Fetching satellite conjunctions from CelesTrak SOCRATES...")

    df_new = fetch_socrates()

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Satellite Conjunctions (SOCRATES Near-Misses)",
        description=DESCRIPTION,
        tags=["space", "satellites", "conjunctions", "space-debris", "celestrak",
              "orbital-mechanics", "open-data", "tabular-data", "parquet"],
        source_url="https://celestrak.org/SOCRATES/",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994",
        banner={"url": "https://images-assets.nasa.gov/image/iss071e439624/iss071e439624~medium.jpg",
                "alt": "An orbital sunrise illuminates the Earth's atmosphere, seen from the ISS",
                "credit": "NASA"},
        license="other",
        license_name="celestrak-usage-policy",
        license_link="https://celestrak.org/usage-policy.php",
        update_schedule="Daily at 16:40 UTC",
        related_datasets=[
            "juliensimon/orbital-fragmentation-events",
            "juliensimon/reentry-events",
            "juliensimon/gcat-satellite-catalog",
            "juliensimon/starlink-fleet-data",
            "juliensimon/starlink-tle-latest",
        ],
    ) as p:
        df_existing = p.download_existing("conjunctions.parquet")

        if df_existing is not None and len(df_existing) > 0:
            df_existing["tca"] = pd.to_datetime(df_existing["tca"])
            df = p.merge(df_existing, df_new, dedup_on="event_key", sort_by="tca")
            print(f"  Merged: {len(df):,} events ({len(df) - len(df_existing):+,} net new)")
        else:
            df = df_new

        df = p.clean(
            df,
            numeric=["min_range_km", "relative_speed_kms", "max_probability", "dilution_km",
                     "days_since_epoch_1", "days_since_epoch_2"],
            integer=["norad_id_1", "norad_id_2"],
            strings=["event_key", "object_name_1", "object_name_2"],
        )

        # ── Stats ────────────────────────────────────────────────────
        n = len(df)
        n_sub_km = int((df["min_range_km"] < 1).sum())
        closest = df["min_range_km"].min()
        date_max = df["tca"].max().strftime("%Y-%m-%d")

        quick_stats = f"""\
- **{n:,}** recorded close-approach events (through {date_max})
- **{n_sub_km:,}** with a predicted miss distance under 1 km
- Closest approach on record: **{closest:.3f} km**"""

        usage = """\
```python
from datasets import load_dataset
import matplotlib.pyplot as plt

ds = load_dataset("juliensimon/satellite-conjunctions", split="train")
df = ds.to_pandas()

# Distribution of miss distances for recorded near-misses
fig, ax = plt.subplots(figsize=(9, 4))
ax.hist(df["min_range_km"], bins=40)
ax.set_xlabel("Miss distance at closest approach (km)")
ax.set_ylabel("Number of conjunctions")
ax.set_title("Satellite Conjunction Miss Distances")
plt.tight_layout()
plt.show()

# The tightest predicted passes
print(df.nsmallest(10, "min_range_km")[
    ["object_name_1", "object_name_2", "tca", "min_range_km", "max_probability"]])
```"""

        p.publish(
            df,
            filename="conjunctions.parquet",
            min_rows=100,
            expected_columns=["event_key", "tca", "min_range_km", "max_probability"],
            critical_columns=["event_key", "tca", "min_range_km"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update satellite conjunctions: {n:,} events",
        )
    print("Done.")


if __name__ == "__main__":
    main()
