#!/usr/bin/env python3
"""Fetch gravitational wave events from GWOSC and upload to HF."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset


GWOSC_URL = "https://gwosc.org/eventapi/json/allevents/"
HF_REPO = "juliensimon/gravitational-wave-events"

# Map catalog prefixes to observing runs

CATALOG_TO_RUN = {
    "O1_O2": "O1/O2",
    "Initial_LIGO": "Initial",
    "GWTC-1": "O1/O2",
    "GWTC-2": "O3a",
    "GWTC-3": "O3b",
    "GWTC-4": "O4a",
    "IAS-O3a": "O3a",
    "O3_": "O3",
    "O4_": "O4",
}


def _infer_run(catalog: str | None) -> str | None:
    """Infer the observing run from the catalog name."""
    if not catalog:
        return None
    for prefix, run in CATALOG_TO_RUN.items():
        if catalog.startswith(prefix):
            return run
    return None


def main():
    print("Fetching gravitational wave events from GWOSC...")
    resp = requests.get(GWOSC_URL, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    events_dict = data.get("events", data)
    print(f"  {len(events_dict):,} event versions in API response")

    # Deduplicate: keep latest version of each commonName
    seen: dict[str, tuple[dict, int]] = {}
    for event_key, e in events_dict.items():
        common = e.get("commonName", event_key)
        version = e.get("version", 0) or 0
        if common not in seen or version > seen[common][1]:
            seen[common] = (e, version)

    rows = []
    for common_name, (e, _version) in seen.items():
        # Fields are directly on the event object (flat structure from allevents API)
        row = {
            "name": common_name,
            "gps": e.get("GPS"),
            "catalog": e.get("catalog.shortName"),
            "run": _infer_run(e.get("catalog.shortName")),
            "mass_1": e.get("mass_1_source"),
            "mass_1_lower": e.get("mass_1_source_lower"),
            "mass_1_upper": e.get("mass_1_source_upper"),
            "mass_2": e.get("mass_2_source"),
            "mass_2_lower": e.get("mass_2_source_lower"),
            "mass_2_upper": e.get("mass_2_source_upper"),
            "chirp_mass": e.get("chirp_mass_source"),
            "chirp_mass_lower": e.get("chirp_mass_source_lower"),
            "chirp_mass_upper": e.get("chirp_mass_source_upper"),
            "luminosity_distance": e.get("luminosity_distance"),
            "luminosity_distance_lower": e.get("luminosity_distance_lower"),
            "luminosity_distance_upper": e.get("luminosity_distance_upper"),
            "redshift": e.get("redshift"),
            "redshift_lower": e.get("redshift_lower"),
            "redshift_upper": e.get("redshift_upper"),
            "chi_eff": e.get("chi_eff"),
            "chi_eff_lower": e.get("chi_eff_lower"),
            "chi_eff_upper": e.get("chi_eff_upper"),
            "network_snr": e.get("network_matched_filter_snr"),
            "network_snr_lower": e.get("network_matched_filter_snr_lower"),
            "network_snr_upper": e.get("network_matched_filter_snr_upper"),
            "p_astro": e.get("p_astro"),
            "far": e.get("far"),
            "far_lower": e.get("far_lower"),
            "far_upper": e.get("far_upper"),
            "final_mass": e.get("final_mass_source"),
            "final_mass_lower": e.get("final_mass_source_lower"),
            "final_mass_upper": e.get("final_mass_source_upper"),
            "final_spin": e.get("final_spin"),
            "final_spin_lower": e.get("final_spin_lower"),
            "final_spin_upper": e.get("final_spin_upper"),
        }
        rows.append(row)

    df = pd.DataFrame(rows)

    # Sort by GPS time
    df = df.sort_values("gps", na_position="last").reset_index(drop=True)
    print(f"  {len(df):,} unique events after deduplication")

    check_dataset(df, "gravitational-waves", min_rows=100,
        expected_columns=["name", "gps", "catalog", "mass_1", "luminosity_distance"],
        critical_columns=["name", "gps"])

    # Compute stats for README
    n_events = len(df)
    catalogs = df["catalog"].dropna().unique()
    catalog_list = ", ".join(sorted(catalogs))
    n_catalogs = len(catalogs)
    runs = df["run"].dropna().unique()
    run_list = ", ".join(sorted(runs))
    median_mass1 = df["mass_1"].median()
    median_dist = df["luminosity_distance"].median()
    size_cat = "n<1K" if n_events < 1000 else "1K<n<10K"

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "gravitational-wave-events.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.2f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Gravitational Wave Events (GWOSC)"
language:
  - en
description: "All confirmed gravitational wave events from LIGO/Virgo/KAGRA observing runs, sourced from the Gravitational-Wave Open Science Center (GWOSC). Updated weekly."
task_categories:
  - tabular-classification
tags:
  - space
  - gravitational-waves
  - ligo
  - virgo
  - kagra
  - gwosc
  - black-hole
  - neutron-star
  - astronomy
  - open-data
  - tabular-data
  - parquet
size_categories:
  - {size_cat}
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/gravitational_waves.parquet
    default: true
---

# Gravitational Wave Events (GWOSC)

*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

![Update Gravitational Waves](https://github.com/juliensimon/space-datasets/actions/workflows/update-gravitational-waves.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['gravitational-waves']&label=updated&color=brightgreen)

All confirmed gravitational wave events from the [Gravitational-Wave Open Science Center](https://gwosc.org/)
(GWOSC), covering LIGO, Virgo, and KAGRA observing runs. Currently **{n_events:,}** events
across {n_catalogs} catalogs ({catalog_list}).

## Dataset description

Each row represents one gravitational wave event (merger of compact objects such as black holes
and/or neutron stars). Parameters include component masses, distance, spins, signal-to-noise
ratio, and astrophysical probability. For each measured parameter, lower and upper uncertainty
bounds are provided where available.

Gravitational waves are ripples in spacetime generated by the acceleration of massive objects, predicted by Einstein's general theory of relativity in 1916 and first directly detected on September 14, 2015, by the LIGO detectors in Hanford, Washington, and Livingston, Louisiana. That event, GW150914, was produced by the merger of two black holes approximately 36 and 29 solar masses at a distance of 1.3 billion light-years -- a detection that earned the 2017 Nobel Prize in Physics and opened an entirely new observational window on the universe.

The catalog spans multiple observing runs of increasing sensitivity, from the initial O1/O2 runs through O3 and into O4. The vast majority of events are binary black hole (BBH) mergers, but the catalog also includes binary neutron star (BNS) mergers -- most notably GW170817, the first event with an electromagnetic counterpart across the entire spectrum from gamma rays to radio -- and neutron star-black hole (NSBH) systems. Each event is characterized by source-frame component masses, chirp mass (the mass combination that gravitational wave signals are most sensitive to), luminosity distance, effective spin parameter, and network signal-to-noise ratio. The false alarm rate and astrophysical probability columns quantify detection confidence.

This dataset enables research into the mass distribution of stellar-mass black holes, the equation of state of neutron star matter, the expansion rate of the universe (via "standard siren" cosmology), and the formation channels of compact binary systems. It is also widely used for testing general relativity in the strong-field regime, constraining populations synthesis models, and developing machine learning methods for gravitational wave signal detection and parameter estimation.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `name` | string | Event name (e.g. GW150914, GW230529) |
| `gps` | float | GPS time of the event |
| `catalog` | string | Source catalog short name |
| `run` | string | Observing run (O1/O2, O3a, O3b, O4a, ...) |
| `mass_1` | float | Primary source mass (solar masses) |
| `mass_1_lower/upper` | float | 90% credible interval bounds |
| `mass_2` | float | Secondary source mass (solar masses) |
| `mass_2_lower/upper` | float | 90% credible interval bounds |
| `chirp_mass` | float | Chirp mass (solar masses) |
| `luminosity_distance` | float | Luminosity distance (Mpc) |
| `redshift` | float | Cosmological redshift |
| `chi_eff` | float | Effective inspiral spin parameter |
| `network_snr` | float | Network matched-filter SNR |
| `p_astro` | float | Probability of astrophysical origin |
| `far` | float | False alarm rate (Hz) |
| `final_mass` | float | Remnant mass (solar masses) |
| `final_spin` | float | Remnant dimensionless spin |

All parameters with uncertainties also have `_lower` and `_upper` columns.

## Quick stats

- **{n_events:,}** gravitational wave events
- **{n_catalogs}** catalogs: {catalog_list}
- Observing runs: {run_list}
- Median primary mass: **{median_mass1:.1f}** solar masses
- Median luminosity distance: **{median_dist:.0f}** Mpc

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/gravitational-wave-events", split="train")
df = ds.to_pandas()

# Binary black hole mergers (both masses > 3 solar masses)
bbh = df[(df["mass_1"] > 3) & (df["mass_2"] > 3)]
print(f"{{len(bbh)}} binary black hole events")

# Closest events
closest = df.nsmallest(5, "luminosity_distance")[["name", "luminosity_distance", "mass_1", "mass_2"]]

# Events by observing run
df["run"].value_counts()
```

## Data source

All data comes from the [GWOSC Event API](https://gwosc.org/eventapi/), the official
open data portal for LIGO, Virgo, and KAGRA gravitational wave detections.

## Update schedule

Weekly on Monday at 17:30 UTC via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [space-track-satcat](https://huggingface.co/datasets/juliensimon/space-track-satcat) -- NORAD Satellite Catalog
- [space-launch-log](https://huggingface.co/datasets/juliensimon/space-launch-log) -- Global launch history

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/gravitational-wave-events) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{gravitational_wave_events,
  author = {{Simon, Julien}},
  title = {{Gravitational Wave Events (GWOSC)}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/gravitational-wave-events}},
  note = {{Based on LIGO/Virgo/KAGRA data from the Gravitational-Wave Open Science Center (GWOSC)}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update gravitational wave events: {n_events:,} events"
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
