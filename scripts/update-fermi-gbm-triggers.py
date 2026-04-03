#!/usr/bin/env python3
"""Fetch Fermi GBM All-Trigger Catalog from HEASARC and upload to HF.

Incremental: downloads existing parquet, fetches recent triggers, merges.
Falls back to full rebuild if no existing data.
"""

import io
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

from dataset_images import banner_markdown, download_banner
from validate import check_dataset


TAP_URL = "https://heasarc.gsfc.nasa.gov/xamin/vo/tap/sync"
HF_REPO = "juliensimon/fermi-gbm-triggers"

ADQL_FULL = """\
SELECT * FROM fermigtrig ORDER BY trigger_time DESC\
"""

# Incremental: fetch triggers from the last N days (with overlap for corrections)
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


def fetch_tap(adql: str) -> pd.DataFrame:
    """Fetch from HEASARC TAP. Try CSV first (with XML guard), fall back to
    JSON, then pipe-delimited text."""

    # Attempt 1: CSV
    print("Fetching Fermi GBM triggers (CSV)...")
    resp = requests.get(TAP_URL, params={
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": adql,
    }, timeout=300)
    resp.raise_for_status()

    # XML guard: HEASARC sometimes returns VOTable XML instead of CSV
    if not resp.text.strip().startswith("<?xml"):
        try:
            df = pd.read_csv(io.StringIO(resp.text))
            # Column sanity check: make sure we got real columns, not an error
            if len(df) > 100 and len(df.columns) >= 5:
                print(f"  CSV parse OK: {len(df):,} rows, {len(df.columns)} cols")
                return df
        except Exception as e:
            print(f"  CSV parse failed: {e}")
    else:
        print("  CSV not supported (got XML/VOTable response)")

    # Attempt 2: JSON
    print("Retrying with FORMAT=json...")
    resp = requests.get(TAP_URL, params={
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "json", "QUERY": adql,
    }, timeout=300)
    resp.raise_for_status()

    try:
        data = resp.json()
        if "data" in data and "metadata" in data:
            cols = [m["name"] for m in data["metadata"]]
            df = pd.DataFrame(data["data"], columns=cols)
        else:
            df = pd.DataFrame(data)
        if len(df) > 100:
            print(f"  JSON parse OK: {len(df):,} rows")
            return df
    except Exception as e:
        print(f"  JSON parse failed: {e}")

    # Attempt 3: pipe-delimited text
    print("Retrying with FORMAT=text...")
    resp = requests.get(TAP_URL, params={
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "text", "QUERY": adql,
    }, timeout=300)
    resp.raise_for_status()

    lines = [l for l in resp.text.strip().splitlines()
             if l.strip() and not l.startswith("-")]
    if len(lines) >= 2:
        header = [c.strip() for c in lines[0].split("|")]
        rows = []
        for line in lines[1:]:
            rows.append([c.strip() for c in line.split("|")])
        df = pd.DataFrame(rows, columns=header)
        df = df.loc[:, df.columns != ""]
        print(f"  Text parse OK: {len(df):,} rows")
        return df

    print("::error::All fetch formats failed")
    sys.exit(1)


def transform(df: pd.DataFrame) -> pd.DataFrame:
    """Clean, rename, and type-coerce the raw DataFrame."""
    # Lowercase all column names for consistent matching
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

    # Derived: is_grb flag based on trigger_type or classification
    if "trigger_type" in df.columns:
        df["is_grb"] = df["trigger_type"].str.lower().str.contains("grb", na=False)
    elif "classification" in df.columns:
        df["is_grb"] = df["classification"].str.lower().str.contains("grb", na=False)
    else:
        df["is_grb"] = pd.NA

    # Sort by trigger_time descending
    if "trigger_time" in df.columns:
        df = df.sort_values("trigger_time", ascending=False).reset_index(drop=True)

    return df


def load_existing(tmp_dir: Path) -> pd.DataFrame | None:
    """Download existing parquet from HF. Returns DataFrame or None."""
    parquet_path = tmp_dir / "data" / "fermi_gbm_triggers.parquet"
    try:
        subprocess.run(
            ["hf", "download", HF_REPO, "data/fermi_gbm_triggers.parquet",
             "--repo-type", "dataset", "--local-dir", str(tmp_dir)],
            check=True, capture_output=True, timeout=60,
        )
        if parquet_path.exists():
            df = pd.read_parquet(parquet_path)
            if "trigger_time" in df.columns:
                df["trigger_time"] = pd.to_datetime(df["trigger_time"])
            print(f"  Loaded existing: {len(df):,} triggers")
            return df
    except Exception as e:
        print(f"  Could not load existing ({e}), will do full rebuild")
    return None


def main():
    print("Fermi GBM All-Trigger Catalog")
    print("=" * 40)

    now = datetime.now(timezone.utc)

    # Try incremental first
    with tempfile.TemporaryDirectory() as probe:
        df_existing = load_existing(Path(probe))

    if df_existing is not None and len(df_existing) > 0:
        # Incremental: fetch recent triggers only
        max_date = df_existing["trigger_time"].max()
        fetch_from_mjd = (pd.Timestamp(max_date) - pd.Timedelta(days=OVERLAP_DAYS)
                          - pd.Timestamp("1858-11-17")).total_seconds() / 86400.0
        adql_inc = (
            f"SELECT * FROM fermigtrig "
            f"WHERE trigger_time >= {fetch_from_mjd:.6f} "
            f"ORDER BY trigger_time DESC"
        )
        print(f"  Incremental fetch: last {OVERLAP_DAYS} days overlap from {max_date}")
        df_new = fetch_tap(adql_inc)
        df_new = transform(df_new)

        if not df_new.empty:
            # Merge: new records override existing (for corrections)
            df = pd.concat([df_existing, df_new], ignore_index=True)
            df = df.drop_duplicates(subset="name", keep="last")
            df = df.sort_values("trigger_time", ascending=False).reset_index(drop=True)
            print(f"  Merged: {len(df):,} triggers ({len(df) - len(df_existing):+,} net)")
        else:
            df = df_existing
            print("  No new triggers")
    else:
        # Full rebuild
        print("  Full rebuild...")
        df = fetch_tap(ADQL_FULL)
        df = transform(df)

    n_total = len(df)
    print(f"  {n_total:,} triggers total")

    # Validation
    check_dataset(df, "fermi-gbm-triggers", min_rows=10_000,
                  expected_columns=["name", "trigger_time", "ra", "dec"],
                  critical_columns=["name", "trigger_time"],
            incremental=True)

    # Stats for README
    n_grb = int(df["is_grb"].sum()) if "is_grb" in df.columns else 0
    n_non_grb = n_total - n_grb

    trigger_types = {}
    if "trigger_type" in df.columns:
        trigger_types = df["trigger_type"].value_counts().head(8).to_dict()

    date_min = df["trigger_time"].min()
    date_max = df["trigger_time"].max()
    date_range = f"{date_min:%Y-%m-%d} to {date_max:%Y-%m-%d}"

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "fermi_gbm_triggers.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        # Build trigger type breakdown for README
        type_lines = ""
        for ttype, count in trigger_types.items():
            type_lines += f"- **{count:,}** {ttype}\n"

        # Build schema from actual columns
        col_descriptions = {
            "name": ("string", "Trigger name / identifier"),
            "trigger_time": ("datetime", "Trigger time (UTC, converted from MJD)"),
            "ra": ("float", "Right ascension (degrees)"),
            "dec": ("float", "Declination (degrees)"),
            "error_radius": ("float", "Localization error radius (degrees)"),
            "trigger_type": ("string", "Trigger classification type"),
            "reliability": ("float", "Trigger reliability flag"),
            "trigger_significance": ("float", "Trigger significance (sigma)"),
            "trigger_timescale": ("float", "Trigger timescale (ms)"),
            "localization_source": ("string", "Source of localization (e.g. ground, flight)"),
            "classification": ("string", "Event classification"),
            "galactic_lat": ("float", "Galactic latitude (degrees)"),
            "galactic_lon": ("float", "Galactic longitude (degrees)"),
            "is_grb": ("bool", "True if trigger is classified as a GRB"),
        }
        schema_rows = ""
        for col in df.columns:
            if col in col_descriptions:
                dtype, desc = col_descriptions[col]
                schema_rows += f"| `{col}` | {dtype} | {desc} |\n"
            else:
                schema_rows += f"| `{col}` | mixed | HEASARC column |\n"

        banner_file = download_banner("fermi-gbm-triggers", tmp)
        banner_md = banner_markdown("fermi-gbm-triggers", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Fermi GBM All-Trigger Catalog"
language:
  - en
description: "All triggers from the Fermi Gamma-ray Burst Monitor — GRBs, solar flares, SGRs, terrestrial particles, and more. Updated daily from NASA HEASARC."
task_categories:
  - tabular-classification
tags:
  - space
  - gamma-ray
  - fermi
  - nasa
  - grb
  - triggers
  - astronomy
  - physics
  - open-data
  - tabular-data
  - parquet
size_categories:
  - 10K<n<100K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/fermi_gbm_triggers.parquet
    default: true
---

# Fermi GBM All-Trigger Catalog
{banner_md}
*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

![Update Fermi GBM Triggers](https://github.com/juliensimon/space-datasets/actions/workflows/update-fermi-gbm-triggers.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['fermi-gbm-triggers']&label=updated&color=brightgreen)

Complete catalog of **all** triggers from the
[Fermi Gamma-ray Burst Monitor (GBM)](https://fermi.gsfc.nasa.gov/ssc/data/access/gbm/),
sourced from NASA HEASARC. Currently **{n_total:,}** triggers ({n_grb:,} GRBs,
{n_non_grb:,} non-GRB triggers).

## Dataset description

The Fermi GBM detects transient events across the full unocculted sky in the 8 keV to
40 MeV energy range. While the confirmed GRB catalog (`fermigbrst`) contains only
verified gamma-ray bursts, this **all-trigger catalog** (`fermigtrig`) includes every
trigger the instrument recorded: GRBs, solar flares, soft gamma repeaters (SGRs),
terrestrial gamma-ray flashes, particle events, and unclassified triggers.

This broader view is valuable for studying the full population of high-energy transients,
training trigger classifiers, and analyzing detection statistics.

The GBM trigger system operates continuously on multiple timescales (16 ms to 4.096 s), flagging statistically significant count-rate increases above background in any of its 12 NaI detectors (8 keV - 1 MeV) or 2 BGO detectors (200 keV - 40 MeV). The resulting trigger population is a rich zoo of astrophysical and non-astrophysical transients. Beyond confirmed GRBs, the catalog contains solar flares (ranging from C-class microflares to X-class events that saturate the detectors), soft gamma repeaters (SGRs) and anomalous X-ray pulsars (magnetars emitting repeated bursts from magnetic field reconfiguration in neutron star crusts), terrestrial gamma-ray flashes (TGFs — millisecond bursts of bremsstrahlung radiation from thunderstorm electrical discharges), Cygnus X-1 flares, and charged particle events from passages through the South Atlantic Anomaly or solar energetic particle events.

The classification of GBM triggers is itself an active area of research. Ground-based analysis refines the initial on-board classification using spectral and temporal properties, localization quality, and coincidence with known sources. Machine learning classifiers trained on this catalog can automate real-time triage of triggers, enabling faster alerts for genuine astrophysical events. The trigger significance, timescale, and localization metadata provide the feature space for such classification tasks, while the human-assigned classifications serve as training labels.

For multi-messenger astrophysics, the complete trigger catalog is essential because sub-threshold events — triggers that fall below the formal GRB detection criteria — can become significant when combined with external coincidences. The landmark GW170817 / GRB 170817A detection demonstrated that even a weak, off-axis GRB can produce a marginal GBM trigger that becomes unambiguous only in the context of a gravitational-wave detection. Systematic searches through this catalog for temporal and spatial coincidences with gravitational-wave candidates, neutrino events, and fast radio bursts are a key component of multi-messenger pipelines.

## Schema

| Column | Type | Description |
|--------|------|-------------|
{schema_rows}

## Quick stats

- **{n_total:,}** triggers ({date_range})
- **{n_grb:,}** classified as GRBs
- **{n_non_grb:,}** non-GRB triggers (solar flares, SGRs, particles, etc.)

### Trigger type breakdown
{type_lines}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/fermi-gbm-triggers", split="train")
df = ds.to_pandas()

# Filter to confirmed GRBs
grbs = df[df["is_grb"] == True]
print(f"{{len(grbs):,}} GRBs out of {{len(df):,}} total triggers")

# Non-GRB triggers
non_grb = df[df["is_grb"] == False]
print(non_grb["trigger_type"].value_counts())

# Triggers per year
df["year"] = df["trigger_time"].dt.year
df.groupby("year").size().plot(kind="bar", title="Fermi GBM Triggers per Year")

# Sky map of triggers
import matplotlib.pyplot as plt
plt.scatter(df["ra"], df["dec"], s=1, alpha=0.3)
plt.xlabel("RA (deg)")
plt.ylabel("Dec (deg)")
plt.title("Fermi GBM Trigger Sky Distribution")
```

## Data source

All data comes from the [Fermi GBM Trigger Catalog](https://heasarc.gsfc.nasa.gov/W3Browse/fermi/fermigtrig.html)
hosted by NASA's High Energy Astrophysics Science Archive Research Center (HEASARC),
accessed via the TAP protocol.

## Update schedule

Daily at 20:00 UTC via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [gamma-ray-bursts](https://huggingface.co/datasets/juliensimon/gamma-ray-bursts) — Fermi GBM confirmed GRB Catalog
- [fermi-4fgl](https://huggingface.co/datasets/juliensimon/fermi-4fgl-dr4) — Fermi LAT 4FGL Source Catalog
- [solar-flare-events](https://huggingface.co/datasets/juliensimon/solar-flare-events) — GOES X-ray flare detections

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/fermi-gbm-triggers) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{fermi_gbm_triggers,
  author = {{Simon, Julien}},
  title = {{Fermi GBM All-Trigger Catalog}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/fermi-gbm-triggers}},
  note = {{Based on NASA HEASARC Fermi GBM Trigger Catalog data}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update Fermi GBM triggers: {n_total:,} triggers"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={n_total}\n")
    print("Done.")


if __name__ == "__main__":
    main()
