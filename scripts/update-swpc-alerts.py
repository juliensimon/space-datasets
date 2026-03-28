#!/usr/bin/env python3
"""Fetch NOAA SWPC Space Weather Alerts and upload to HF."""

import os
import re
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset


SWPC_URL = "https://services.swpc.noaa.gov/products/alerts.json"
HF_REPO = "juliensimon/swpc-alerts"


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

    if "issue_datetime" in df.columns:
        df = df.sort_values("issue_datetime").reset_index(drop=True)

    check_dataset(df, "swpc-alerts", min_rows=100,
                  expected_columns=["issue_datetime", "product_id", "message"],
                  critical_columns=["issue_datetime", "product_id"])

    # Stats for README
    n = len(df)
    date_min = df["issue_datetime"].min().strftime("%Y-%m-%d") if "issue_datetime" in df.columns else "N/A"
    date_max = df["issue_datetime"].max().strftime("%Y-%m-%d") if "issue_datetime" in df.columns else "N/A"
    type_counts = df["alert_type"].value_counts().to_dict() if "alert_type" in df.columns else {}

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "swpc_alerts.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_kb = out.stat().st_size / 1024
        print(f"  {size_kb:.0f} KB parquet")

        type_lines = "\n".join(f"  - {k}: **{v:,}**" for k, v in sorted(type_counts.items()))

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "NOAA SWPC Space Weather Alerts"
language:
  - en
description: >-
  Official space weather alerts, watches, and warnings issued by NOAA's Space
  Weather Prediction Center. Updated daily.
size_categories:
  - 1K<n<10K
task_categories:
  - text-classification
tags:
  - space
  - space-weather
  - noaa
  - swpc
  - alert
  - geomagnetic-storm
  - open-data
  - tabular-data
  - parquet
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/swpc_alerts.parquet
---

# NOAA SWPC Space Weather Alerts

*Part of the [Space Weather Datasets](https://huggingface.co/collections/juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70) collection on Hugging Face.*

![Update SWPC Alerts](https://github.com/juliensimon/space-datasets/actions/workflows/update-swpc-alerts.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.swpc-alerts&label=updated&color=brightgreen)

Official space weather alerts from NOAA's Space Weather Prediction Center, spanning
**{date_min}** to **{date_max}**. Currently **{n:,}** alerts.

## Dataset description

This dataset contains official space weather alerts, watches, and warnings issued by
NOAA's Space Weather Prediction Center (SWPC). These notifications cover:

- **Geomagnetic storms**: G1 (minor) through G5 (extreme) storms from CME impacts
- **Solar radiation storms**: S1 through S5 proton events
- **Radio blackouts**: R1 through R5 HF radio absorption events
- **Watches and warnings**: advance notice of expected space weather impacts

These alerts are critical for satellite operators, power grid managers, aviation,
and anyone affected by space weather.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `product_id` | string | SWPC product identifier |
| `issue_datetime` | datetime | Date and time the alert was issued (UTC) |
| `message` | string | Full alert message text |
| `alert_type` | string | Extracted type: ALERT, WARNING, WATCH, SUMMARY, or OTHER |

## Quick stats

- **{n:,}** alerts ({date_min} to {date_max})
- By type:
{type_lines}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/swpc-alerts", split="train")
df = ds.to_pandas()

# Recent warnings
warnings = df[df["alert_type"] == "WARNING"].sort_values("issue_datetime", ascending=False)
print(warnings[["issue_datetime", "product_id"]].head(10))

# Geomagnetic storm alerts
geo = df[df["message"].str.contains("Geomagnetic Storm", case=False, na=False)]
print(f"Geomagnetic storm alerts: {{len(geo)}}")
```

## Data source

[NOAA Space Weather Prediction Center (SWPC)](https://www.swpc.noaa.gov/) alerts API.

## Update schedule

Daily at 15:00 UTC via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/swpc-alerts) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{swpc_alerts,
  author = {{Simon, Julien}},
  title = {{NOAA SWPC Space Weather Alerts}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/swpc-alerts}},
  note = {{Based on NOAA Space Weather Prediction Center alerts data}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update SWPC alerts: {n:,} records"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={n}\n")
    print("Done.")


if __name__ == "__main__":
    main()
