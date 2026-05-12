#!/usr/bin/env python3
"""Fetch NOAA SWPC Space Weather Alerts and upload to HF.

Source: NOAA Space Weather Prediction Center — official space weather
alerts, watches, and warnings.
"""

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

SWPC_URL = "https://services.swpc.noaa.gov/products/alerts.json"
HF_REPO = "juliensimon/swpc-alerts"

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "product_id": "SWPC product code identifying the alert category and threshold (e.g., 'ALTEF3' = electron flux alert level 3, 'WATA20' = geomagnetic activity watch, 'ALTK06' = Kp=6 alert, 'SUMSUD' = summary); encodes both product type and severity level",
    "issue_datetime": "UTC timestamp when the alert was officially issued by NOAA SWPC",
    "message": "Full text of the alert as issued, including threshold values, affected systems, and analyst commentary; unstructured plain text suitable for NLP analysis",
    "alert_type": "Derived alert category extracted from product_id and message text: 'ALERT' (real-time threshold exceeded), 'WARNING' (threshold expected to be exceeded within hours), 'WATCH' (significant event possible within 1-3 days), 'SUMMARY' (post-event synopsis), 'OTHER' (miscellaneous products)",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Official space weather alerts from NOAA's Space Weather Prediction Center, \
including alerts, watches, warnings, and summaries covering geomagnetic storms, \
solar radiation storms, and radio blackouts.

SWPC operates as the United States' official source for space weather forecasts \
and warnings, analogous to the National Weather Service for terrestrial weather. \
The alert system follows a structured hierarchy: **watches** are issued 1-3 days \
in advance when conditions favor a significant event (e.g., an Earth-directed CME \
has been observed), **warnings** indicate that an event is imminent or already in \
progress, and **alerts** notify when specific thresholds are exceeded in real-time. \
Summaries provide post-event documentation.

Each alert references the NOAA scales: G1-G5 for geomagnetic storms (based on Kp), \
S1-S5 for solar radiation storms (based on >10 MeV proton flux), and R1-R5 for \
radio blackouts (based on X-ray flare class). The alert messages contain rich \
unstructured information: analyst assessments of CME morphology, expected arrival \
windows, confidence levels, affected sectors (HF radio, GPS, power systems, satellite \
operations, aviation radiation), and references to specific active regions.

From an operational standpoint, these alerts drive real-world responses: satellite \
operators may postpone maneuvers during geomagnetic storm warnings, airlines reroute \
polar flights during solar radiation storms to reduce crew radiation exposure, and \
power grid operators increase reactive power reserves when G3+ storms are forecast.
"""


def extract_alert_type(product_id, message):
    """Extract alert type from product_id or message content."""
    if pd.isna(product_id):
        product_id = ""
    if pd.isna(message):
        message = ""
    pid = str(product_id).upper()
    msg_upper = str(message).upper()

    if "WARNING" in pid or "WARNING" in msg_upper[:200]:
        return "WARNING"
    elif "WATCH" in pid or "WATCH" in msg_upper[:200]:
        return "WATCH"
    elif "ALERT" in pid or "ALERT" in msg_upper[:200]:
        return "ALERT"
    elif "SUMMARY" in pid or "SUMMARY" in msg_upper[:200]:
        return "SUMMARY"
    else:
        return "OTHER"


def main():
    print("Fetching NOAA SWPC Space Weather Alerts...")
    resp = requests.get(SWPC_URL, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    print(f"  {len(data):,} alerts")

    df = pd.DataFrame(data)

    # Parse issue_datetime
    if "issue_datetime" in df.columns:
        df["issue_datetime"] = pd.to_datetime(df["issue_datetime"], errors="coerce")

    # Extract alert type
    if "product_id" in df.columns and "message" in df.columns:
        df["alert_type"] = df.apply(
            lambda r: extract_alert_type(r.get("product_id"), r.get("message")),
            axis=1,
        )
    elif "product_id" in df.columns:
        df["alert_type"] = df["product_id"].apply(
            lambda x: extract_alert_type(x, "")
        )

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    if "issue_datetime" in df.columns:
        df = df.sort_values("issue_datetime").reset_index(drop=True)

    # ── Domain-specific stats for README ─────────────────────────────
    n = len(df)
    _ts_min = df["issue_datetime"].min() if "issue_datetime" in df.columns else None
    _ts_max = df["issue_datetime"].max() if "issue_datetime" in df.columns else None
    date_min = _ts_min.strftime("%Y-%m-%d") if _ts_min is not None and pd.notna(_ts_min) else "N/A"
    date_max = _ts_max.strftime("%Y-%m-%d") if _ts_max is not None and pd.notna(_ts_max) else "N/A"
    type_counts = df["alert_type"].value_counts().to_dict() if "alert_type" in df.columns else {}
    type_lines = "\n".join(f"  - {k}: **{v:,}**" for k, v in sorted(type_counts.items()))

    quick_stats = f"""\
- **{n:,}** alerts ({date_min} to {date_max})
- By type:
{type_lines}"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/swpc-alerts", split="train")
df = ds.to_pandas()

# Recent warnings
warnings = df[df["alert_type"] == "WARNING"].sort_values("issue_datetime", ascending=False)
print(warnings[["issue_datetime", "product_id"]].head(10))

# Geomagnetic storm alerts
geo = df[df["message"].str.contains("Geomagnetic Storm", case=False, na=False)]
print(f"Geomagnetic storm alerts: {len(geo)}")

# Alert type distribution
import matplotlib.pyplot as plt
df["alert_type"].value_counts().plot(kind="bar")
plt.ylabel("Count")
plt.title("SWPC Alert Types")
plt.tight_layout()
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="NOAA SWPC Space Weather Alerts",
        description=DESCRIPTION,
        tags=["space", "space-weather", "noaa", "swpc", "alert",
              "geomagnetic-storm", "open-data", "tabular-data", "parquet"],
        source_url="https://www.swpc.noaa.gov/",
        task_categories=["text-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70",
        banner={
            "url": "https://images-assets.nasa.gov/image/iss072e159172/iss072e159172~medium.jpg",
            "alt": "Aurora borealis blankets the Earth, seen from the ISS",
            "credit": "NASA",
        },
    ) as p:
        df = p.clean(
            df,
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="swpc_alerts.parquet",
            min_rows=50,
            expected_columns=["issue_datetime", "product_id", "message"],
            critical_columns=["issue_datetime", "product_id"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update SWPC alerts: {n:,} records",
        )
    print("Done.")


if __name__ == "__main__":
    main()
