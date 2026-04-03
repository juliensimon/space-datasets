#!/usr/bin/env python3
"""Fetch ICECAT-1 (IceCube Event Catalog of Alert Tracks) from Harvard Dataverse
and upload to HF.

Static dataset — no GitHub Actions workflow.

Source: https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/SCRUCD
Paper: IceCube Collaboration, ICECAT-1 catalog of neutrino alert tracks.
"""

import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd
import requests

from dataset_images import banner_markdown, download_banner
from validate import check_dataset

# Harvard Dataverse file ID for IceCube_Gold_Bronze_Tracks.tab (TSV summary)
DATAVERSE_FILE_ID = 7502710
DATAVERSE_URL = f"https://dataverse.harvard.edu/api/access/datafile/{DATAVERSE_FILE_ID}"
HF_REPO = "juliensimon/icecat-neutrino-alerts"


def fetch_catalog() -> pd.DataFrame:
    """Download TSV summary table from Harvard Dataverse."""
    print("Fetching ICECAT-1 catalog from Harvard Dataverse...")
    resp = requests.get(DATAVERSE_URL, timeout=120)
    resp.raise_for_status()

    df = pd.read_csv(io.StringIO(resp.text), sep="\t")
    print(f"  Downloaded {len(df):,} rows, {len(df.columns)} columns")
    return df


def main():
    df = fetch_catalog()

    # ── Clean up quoted string columns ────────────────────────────────────
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip().str.strip('"')
        df[col] = df[col].replace({"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA})

    # ── Rename columns to snake_case ──────────────────────────────────────
    rename = {
        "NAME": "event_name",
        "RUNID": "run_id",
        "EVENTID": "event_id",
        "START": "event_utc",
        "EVENTMJD": "event_mjd",
        "I3TYPE": "alert_type",
        "RA": "ra_deg",
        "DEC": "dec_deg",
        "RA_ERR_PLUS": "ra_err_plus",
        "RA_ERR_MINUS": "ra_err_minus",
        "DEC_ERR_PLUS": "dec_err_plus",
        "DEC_ERR_MINUS": "dec_err_minus",
        "ENERGY": "energy_tev",
        "FAR": "false_alarm_rate_per_yr",
        "SIGNAL": "signalness",
        "CASCADE_SCR": "score_cascade",
        "SKIMMING_SCR": "score_skimming",
        "START_SCR": "score_starting",
        "STOP_SCR": "score_stopping",
        "THRGOING_SCR": "score_throughgoing",
        "CR_VETO": "cosmic_ray_veto",
        "OTHER_I3TYPES": "other_alert_types",
    }
    df = df.rename(columns=rename)

    # ── Coerce numeric columns ────────────────────────────────────────────
    numeric_cols = [
        "event_mjd", "ra_deg", "dec_deg",
        "ra_err_plus", "ra_err_minus", "dec_err_plus", "dec_err_minus",
        "energy_tev", "false_alarm_rate_per_yr", "signalness",
        "score_cascade", "score_skimming", "score_starting",
        "score_stopping", "score_throughgoing",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # ── Parse event_utc as datetime ───────────────────────────────────────
    if "event_utc" in df.columns:
        df["event_utc"] = pd.to_datetime(df["event_utc"], errors="coerce")

    # ── Coerce boolean cosmic_ray_veto ────────────────────────────────────
    if "cosmic_ray_veto" in df.columns:
        df["cosmic_ray_veto"] = df["cosmic_ray_veto"].astype(str).str.upper().map(
            {"TRUE": True, "FALSE": False}
        )

    # ── Integer IDs ───────────────────────────────────────────────────────
    for col in ["run_id", "event_id"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    # ── Sort by MJD (chronological) ──────────────────────────────────────
    df = df.sort_values("event_mjd").reset_index(drop=True)

    print(f"  {len(df):,} neutrino alert events")
    print(f"  Columns: {list(df.columns)}")
    print(f"  MJD range: {df['event_mjd'].min():.2f} — {df['event_mjd'].max():.2f}")
    print(f"  Energy range: {df['energy_tev'].min():.0f} — {df['energy_tev'].max():.0f} TeV")

    # ── Alert type breakdown ──────────────────────────────────────────────
    type_counts = df["alert_type"].value_counts()
    for atype, count in type_counts.items():
        print(f"    {atype}: {count:,}")

    # ── Validate ──────────────────────────────────────────────────────────
    check_dataset(df, "icecat", min_rows=200,
                  expected_columns=["event_name", "ra_deg", "dec_deg", "energy_tev", "signalness"],
                  critical_columns=["ra_deg", "dec_deg", "energy_tev"])

    # ── Write parquet + README ────────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "icecat.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.2f} MB parquet")

        # Stats for README
        n_total = len(df)
        n_gold = int((df["alert_type"].str.contains("gold", case=False, na=False)).sum())
        n_bronze = int((df["alert_type"].str.contains("bronze", case=False, na=False)).sum())
        median_energy = df["energy_tev"].median()
        median_signalness = df["signalness"].median()
        year_min = df["event_utc"].dt.year.min()
        year_max = df["event_utc"].dt.year.max()

        # Type breakdown for README
        type_lines = [f"- **{count:,}** {atype}" for atype, count in type_counts.items()]
        type_summary = "\n".join(type_lines)

        banner_file = download_banner("icecat", tmp)
        banner_md = banner_markdown("icecat", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "ICECAT-1 — IceCube Event Catalog of Alert Tracks"
language:
  - en
description: "Catalog of {n_total} high-energy neutrino events from the IceCube Neutrino Observatory selected as astrophysical candidates, covering {year_min}–{year_max}."
task_categories:
  - tabular-classification
tags:
  - space
  - neutrinos
  - icecube
  - multi-messenger
  - astronomy
  - physics
  - open-data
  - tabular-data
  - parquet
size_categories:
  - n<1K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/icecat.parquet
    default: true
---

# ICECAT-1 — IceCube Event Catalog of Alert Tracks
{banner_md}
*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

Catalog of **{n_total:,}** high-energy neutrino events from the IceCube Neutrino
Observatory at the South Pole, selected as astrophysical candidates by the Gold
and Bronze track alert program ({year_min}–{year_max}).

## Dataset description

The IceCube Neutrino Observatory is a cubic-kilometer particle detector buried
in the Antarctic ice. ICECAT-1 is the first catalog of neutrino alert tracks,
including events issued in realtime via GCN notices and events that would have
triggered an alert had the program been active since 2011. Each event is a
high-energy (>~100 TeV) muon track with significant probability of astrophysical
origin.

The catalog includes best-fit sky coordinates (RA/Dec with asymmetric errors),
energy estimates, signalness (probability of astrophysical origin), false-alarm
rates, and CNN-based topology classification scores.

High-energy neutrinos are uniquely powerful messengers for probing the non-thermal universe. Unlike photons, they are electrically neutral and weakly interacting, so they travel undeflected by magnetic fields and unabsorbed by intervening matter, pointing directly back to their production sites. The neutrino energies in ICECAT-1 (typically hundreds of TeV to several PeV) imply hadronic acceleration processes -- proton-proton or proton-photon interactions -- occurring in environments such as relativistic jets of blazars, tidal disruption events, or the cores of starburst galaxies. The 2017 coincidence of IceCube-170922A with the flaring blazar TXS 0506+056 provided the first compelling evidence for an extragalactic neutrino point source and inaugurated the era of multi-messenger astronomy with neutrinos.

The "signalness" parameter is central to astrophysical interpretation: it quantifies the probability that a given track event originates from an astrophysical neutrino rather than an atmospheric background muon or atmospheric neutrino. Gold alerts (signalness > 50%) are the highest-confidence candidates for follow-up by electromagnetic and gravitational-wave observatories worldwide. The CNN topology scores classify events by their interaction morphology in the ice -- throughgoing muon tracks provide the best angular resolution (~0.5 degrees) while cascade and starting events offer better energy reconstruction, enabling complementary searches for transient and steady-state sources.

## Quick stats

- **{n_total:,}** neutrino alert events ({year_min}–{year_max})
- **{n_gold:,}** gold alerts, **{n_bronze:,}** bronze alerts
- Median energy: **{median_energy:.0f} TeV**
- Median signalness: **{median_signalness:.3f}**

## Alert types

{type_summary}

## Column reference

| Column | Description |
|--------|-------------|
| `event_name` | IceCube event identifier (e.g., IC110514A) |
| `run_id`, `event_id` | IceCube DAQ identifiers |
| `event_utc`, `event_mjd` | Event time (UTC datetime and Modified Julian Date) |
| `alert_type` | Event selection type: gfu-gold, gfu-bronze, ehe-gold, hese-gold, hese-bronze |
| `ra_deg`, `dec_deg` | Best-fit J2000 equatorial coordinates (degrees) |
| `ra_err_plus/minus`, `dec_err_plus/minus` | Asymmetric 90% CL error (degrees) |
| `energy_tev` | Most probable neutrino energy (TeV), assuming E^(-2.19) flux |
| `false_alarm_rate_per_yr` | Background event rate (events/year) |
| `signalness` | Probability of astrophysical origin |
| `score_*` | CNN topology classifier scores (throughgoing, starting, cascade, skimming, stopping) |
| `cosmic_ray_veto` | Surface IceTop cosmic-ray veto flag |
| `other_alert_types` | Additional alert categories this event passed |

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/icecat-neutrino-alerts", split="train")
df = ds.to_pandas()

print(f"{{len(df):,}} neutrino events")

# Gold alerts only
gold = df[df["alert_type"].str.contains("gold")]
print(f"{{len(gold):,}} gold alerts, median signalness={{gold['signalness'].median():.3f}}")

# Sky map
import matplotlib.pyplot as plt
import numpy as np
fig, ax = plt.subplots(subplot_kw={{"projection": "aitoff"}})
ra_rad = np.deg2rad(df["ra_deg"] - 180)
dec_rad = np.deg2rad(df["dec_deg"])
ax.scatter(ra_rad, dec_rad, s=8, alpha=0.6, c=df["energy_tev"],
           cmap="plasma", norm=plt.matplotlib.colors.LogNorm())
ax.set_title("ICECAT-1 Neutrino Sky Map")
ax.grid(True)
```

## Data source

IceCube Collaboration, *ICECAT-1: IceCube Event Catalog of Alert Tracks*.
Harvard Dataverse, [doi:10.7910/DVN/SCRUCD](https://doi.org/10.7910/DVN/SCRUCD).

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Related datasets

- [gamma-ray-bursts](https://huggingface.co/datasets/juliensimon/gamma-ray-bursts) — Fermi GBM Gamma-Ray Burst Catalog
- [tevcat-tev-gamma-ray](https://huggingface.co/datasets/juliensimon/tevcat-tev-gamma-ray) — TeVCat TeV Gamma-Ray Source Catalog
- [cosmic-rays](https://huggingface.co/datasets/juliensimon/auger-cosmic-rays) — Cosmic Ray Database

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/icecat-neutrino-alerts) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{icecat_neutrino_alerts,
  author = {{IceCube Collaboration}},
  title = {{ICECAT-1: IceCube Event Catalog of Alert Tracks}},
  year = {{2024}},
  publisher = {{Harvard Dataverse}},
  doi = {{10.7910/DVN/SCRUCD}},
  url = {{https://doi.org/10.7910/DVN/SCRUCD}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update ICECAT-1: {n_total:,} neutrino alert events"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={len(df)}\n")
    print("Done.")


if __name__ == "__main__":
    main()
