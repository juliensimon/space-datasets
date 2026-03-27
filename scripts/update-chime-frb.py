#!/usr/bin/env python3
"""Fetch CHIME/FRB Catalog from VizieR and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from validate import check_dataset
from vizier_tap import vizier_query


HF_REPO = "juliensimon/chime-frb-catalog"

ADQL = """\
SELECT Name, RpName, RAJ2000, DEJ2000, GLON, GLAT, SNR, DM, DMfitb, \
bcwidth, Scat, Flux, Fluence, Nsb \
FROM "J/ApJS/257/59/table2"\
"""


def main():
    print("Fetching CHIME/FRB Catalog from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} FRB events")

    # Rename columns
    df = df.rename(columns={
        "Name": "tns_name",
        "RpName": "repeater_name",
        "RAJ2000": "ra_deg",
        "DEJ2000": "dec_deg",
        "GLON": "glon_deg",
        "GLAT": "glat_deg",
        "SNR": "snr",
        "DM": "dm_pc_cm3",
        "DMfitb": "dm_fitb_pc_cm3",
        "bcwidth": "width_ms",
        "Scat": "scattering_time_ms",
        "Flux": "flux_jy",
        "Fluence": "fluence_jy_ms",
        "Nsb": "sub_burst_count",
    })

    # Derive is_repeater from repeater_name
    # Convert numerics
    numeric_cols = ["ra_deg", "dec_deg", "dm_pc_cm3", "width_ms", "flux_jy",
                    "fluence_jy_ms", "scattering_time_ms", "snr", "sub_burst_count"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Clean string columns
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip().replace(
            {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
        )

    # Derive is_repeater AFTER string cleaning
    if "repeater_name" in df.columns:
        df["is_repeater"] = df["repeater_name"].notna() & (df["repeater_name"] != "-9999") & (df["repeater_name"] != "<NA>")

    check_dataset(df, "chime-frb", min_rows=500,
        expected_columns=["tns_name", "ra_deg", "dec_deg", "dm_pc_cm3"],
        critical_columns=["tns_name", "dm_pc_cm3"])

    # Stats for README
    n_total = len(df)
    n_repeaters = int(df["is_repeater"].sum()) if "is_repeater" in df.columns and df["is_repeater"].dtype == bool else 0
    median_dm = df["dm_pc_cm3"].median() if "dm_pc_cm3" in df.columns else 0
    max_dm = df["dm_pc_cm3"].max() if "dm_pc_cm3" in df.columns else 0
    median_snr = df["snr"].median() if "snr" in df.columns else 0

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "chime_frb_catalog.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "CHIME/FRB Catalog"
language:
  - en
description: "Fast Radio Bursts detected by the Canadian Hydrogen Intensity Mapping Experiment (CHIME), the world's most prolific FRB detector. Sourced via VizieR CDS Strasbourg."
task_categories:
  - tabular-classification
tags:
  - space
  - frb
  - fast-radio-burst
  - chime
  - radio
  - astronomy
  - open-data
  - tabular-data
size_categories:
  - 1K<n<10K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/chime_frb_catalog.parquet
    default: true
---

# CHIME/FRB Catalog

*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

![Update CHIME/FRB](https://github.com/juliensimon/space-datasets/actions/workflows/update-chime-frb.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.chime-frb&label=updated&color=brightgreen)

Fast Radio Bursts (FRBs) detected by the Canadian Hydrogen Intensity Mapping Experiment (CHIME)
telescope. Currently **{n_total:,}** FRB events from the First CHIME/FRB Catalog.

## Dataset description

Fast Radio Bursts are millisecond-duration radio transients of extragalactic origin -- one of
the most exciting mysteries in modern astrophysics. First discovered in 2007, their physical
origin remains debated, though magnetars are a leading candidate. CHIME, a radio telescope
at the Dominion Radio Astrophysical Observatory in British Columbia, Canada, has revolutionized
FRB science by detecting hundreds of bursts thanks to its enormous field of view
(~200 square degrees) and continuous operation at 400-800 MHz.

The First CHIME/FRB Catalog (CHIME/FRB Collaboration, 2021, ApJS, 257, 59) contains FRBs
detected between 2018 July 25 and 2019 July 1, representing the largest uniform FRB sample
to date.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `tns_name` | string | Transient Name Server designation (e.g. FRB 20181030A) |
| `ra_deg` | float64 | Right ascension (degrees) |
| `dec_deg` | float64 | Declination (degrees) |
| `dm_pc_cm3` | float64 | Dispersion measure (pc/cm^3) |
| `width_ms` | float64 | Burst width (milliseconds) |
| `flux_jy` | float64 | Peak flux density (Jy) |
| `fluence_jy_ms` | float64 | Fluence (Jy ms) |
| `scattering_time_ms` | float64 | Scattering timescale (ms) |
| `snr` | float64 | Signal-to-noise ratio |
| `is_repeater` | bool | True if source is a known repeater |
| `sub_burst_count` | float64 | Number of sub-bursts |

## Quick stats

- **{n_total:,}** FRB events
- **{n_repeaters}** from repeating sources
- Median DM: **{median_dm:.1f}** pc/cm^3
- Max DM: **{max_dm:.1f}** pc/cm^3
- Median S/N: **{median_snr:.1f}**

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/chime-frb-catalog", split="train")
df = ds.to_pandas()

# DM distribution
import matplotlib.pyplot as plt
df["dm_pc_cm3"].hist(bins=50)
plt.xlabel("Dispersion Measure (pc/cm^3)")
plt.ylabel("Count")
plt.title("CHIME/FRB DM Distribution")

# Repeaters vs one-offs
repeaters = df[df["is_repeater"] == True]
one_offs = df[df["is_repeater"] == False]
print(f"Repeaters: {{len(repeaters)}}, One-offs: {{len(one_offs)}}")

# Sky distribution
plt.figure(figsize=(12, 6))
plt.scatter(df["ra_deg"], df["dec_deg"], c=df["dm_pc_cm3"], s=5, cmap="viridis")
plt.colorbar(label="DM (pc/cm^3)")
plt.xlabel("RA (deg)")
plt.ylabel("Dec (deg)")
plt.title("CHIME/FRB Sky Distribution")
```

## Data source

[CHIME/FRB Collaboration](https://www.chime-frb.ca/), 2021, ApJS, 257, 59.
"The First CHIME/FRB Fast Radio Burst Catalog", accessed via
[VizieR](https://vizier.cds.unistra.fr/), CDS Strasbourg.

## Update schedule

Semi-annually (1st of the month at 06:00 UTC) via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [pulsar-catalog](https://huggingface.co/datasets/juliensimon/pulsar-catalog) -- ATNF Pulsar Catalogue
- [gamma-ray-bursts](https://huggingface.co/datasets/juliensimon/gamma-ray-bursts) -- Fermi GBM Gamma-Ray Burst Catalog
- [gravitational-waves](https://huggingface.co/datasets/juliensimon/gravitational-waves) -- LIGO/Virgo Gravitational Wave Events

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/chime-frb-catalog) and share feedback in the Community tab!

## Citation

```bibtex
@dataset{{chime_frb_catalog,
  author = {{Simon, Julien}},
  title = {{CHIME/FRB Catalog}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/chime-frb-catalog}},
  note = {{Based on CHIME/FRB Collaboration (2021, ApJS, 257, 59) via VizieR CDS Strasbourg}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update CHIME/FRB catalog: {n_total:,} events"
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
