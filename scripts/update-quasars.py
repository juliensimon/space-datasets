#!/usr/bin/env python3
"""Fetch quasar/AGN catalog from SIMBAD and upload to HF."""

import io
import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import requests

from dataset_images import banner_markdown, download_banner
from validate import check_dataset


HF_REPO = "juliensimon/quasar-catalog"

SIMBAD_TAP = "https://simbad.u-strasbg.fr/simbad/sim-tap/sync"

# SIMBAD otypes for AGN: QSO (quasar), AGN (active galactic nucleus),

# Sy1/Sy2 (Seyfert), BLL (BL Lac), Bla (Blazar), LIN (LINER)
ADQL = """SELECT TOP 100000 main_id AS name, ra, dec, otype_txt AS object_type
FROM basic
WHERE otype_txt = 'QSO' OR otype_txt = 'AGN' OR otype_txt = 'Sy1' OR otype_txt = 'Sy2' OR otype_txt = 'BLL' OR otype_txt = 'Bla' OR otype_txt = 'LIN'
ORDER BY main_id"""


def main():
    print("Fetching quasar/AGN catalog from SIMBAD...")

    resp = requests.get(SIMBAD_TAP, params={
        "REQUEST": "doQuery",
        "LANG": "ADQL",
        "FORMAT": "csv",
        "QUERY": ADQL,
    }, timeout=300)
    resp.raise_for_status()

    df = pd.read_csv(io.StringIO(resp.text))
    print(f"  {len(df)} objects from SIMBAD")

    df = df.rename(columns={
        "name": "name",
        "ra": "ra_deg",
        "dec": "dec_deg",
        "object_type": "object_type",
    })

    for col in ["ra_deg", "dec_deg"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Deduplicate (multiple redshift measurements)
    df = df.drop_duplicates("name", keep="first")

    # Readable AGN category
    type_map = {
        "QSO": "Quasar",
        "AGN": "Active Galactic Nucleus",
        "Sy1": "Seyfert 1",
        "Sy2": "Seyfert 2",
        "BLL": "BL Lac Object",
        "Bla": "Blazar",
        "LIN": "LINER",
    }
    df["agn_category"] = df["object_type"].map(type_map).fillna(df["object_type"])

    df = df.sort_values("name").reset_index(drop=True)

    check_dataset(df, "quasars", min_rows=1000,
                  expected_columns=["name", "ra_deg", "dec_deg", "object_type"],
                  critical_columns=["name", "ra_deg"])

    n = len(df)
    n_qso = int((df["object_type"] == "QSO").sum())
    n_agn = int((df["object_type"] == "AGN").sum())
    n_seyfert = int(df["object_type"].isin(["Sy1", "Sy2"]).sum())
    n_blazar = int(df["object_type"].isin(["BLL", "Bla"]).sum())
    pass  # stats computed from available columns only

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        data_dir = tmp_dir / "data"
        data_dir.mkdir()

        out = data_dir / "quasars.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        banner_file = download_banner("quasars", tmp_dir)
        banner_md = banner_markdown("quasars", banner_file)

        (tmp_dir / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Quasar & AGN Catalog"
language:
  - en
description: >-
  Catalog of {n:,} quasars and active galactic nuclei from SIMBAD — quasars,
  Seyfert galaxies, blazars, and LINERs with redshifts and photometry.
size_categories:
  - {"10K<n<100K" if n >= 10000 else "1K<n<10K"}
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - open-data
  - astronomy
  - quasar
  - agn
  - blazar
  - seyfert
  - redshift
  - simbad
  - cosmology
  - tabular-data
  - parquet
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/quasars.parquet
---

# Quasar & AGN Catalog
{banner_md}
*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

![Update Quasars](https://github.com/juliensimon/space-datasets/actions/workflows/update-quasars.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.quasars&label=updated&color=brightgreen)

Catalog of **{n:,}** quasars and active galactic nuclei from
[SIMBAD](https://simbad.u-strasbg.fr/): **{n_qso:,}** quasars, **{n_seyfert:,}**
Seyfert galaxies, **{n_blazar:,}** blazars/BL Lacs, **{n_agn:,}** general AGN.

## Dataset description

Active galactic nuclei are galaxies whose central supermassive black holes are actively accreting matter, releasing enormous amounts of energy across the electromagnetic spectrum. Quasars, the most luminous subclass, can outshine their entire host galaxy by factors of a hundred or more and are visible at cosmological distances, making them powerful probes of the early universe. The different AGN categories in this catalog -- Seyfert 1 and 2 galaxies, blazars, BL Lac objects, and LINERs -- are thought to represent different viewing angles and accretion rates of the same underlying phenomenon, unified under orientation-dependent models.

These objects are critical for multiple areas of astrophysics. Quasars serve as background beacons for studying the intergalactic medium through absorption-line spectroscopy, they anchor the International Celestial Reference Frame (ICRF) used for precision astrometry, and their redshift distribution traces the growth history of supermassive black holes across cosmic time. Blazars, whose relativistic jets point nearly along our line of sight, are among the brightest persistent sources in the gamma-ray sky and are candidate sources of high-energy cosmic neutrinos.

The SIMBAD database aggregates classifications from thousands of publications, providing a heterogeneous but broadly representative census of known AGN. This catalog is useful for cross-matching with multi-wavelength surveys, selecting targets for spectroscopic follow-up, and building training sets for machine-learning classification of AGN from photometric data.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `name` | string | Primary SIMBAD identifier (e.g. "QSO J1230+1223" or "3C 273"); unique within SIMBAD but may differ from other catalog designations |
| `ra_deg` | float | Right ascension of the AGN nucleus in the ICRS J2000.0 frame, decimal degrees (0–360) |
| `dec_deg` | float | Declination of the AGN nucleus in the ICRS J2000.0 frame, decimal degrees (−90 to +90) |
| `object_type` | string | SIMBAD machine-readable type code: "QSO" = radio-quiet quasar, "AGN" = broad-line active galactic nucleus, "Sy1" = Seyfert 1 (broad + narrow lines, type-1 viewing angle), "Sy2" = Seyfert 2 (narrow lines only, obscured nucleus), "BLL" = BL Lac object (featureless continuum, jet pointing toward observer), "Bla" = blazar (BL Lac or FSRQ with relativistic jet), "LIN" = LINER (Low Ionization Nuclear Emission Region, weak AGN activity) |
| `agn_category` | string | Human-readable category derived from `object_type`: one of "Quasar", "AGN", "Seyfert 1", "Seyfert 2", "BL Lac", "Blazar", "LINER"; useful for grouped analysis without parsing SIMBAD codes |



## Quick stats

- **{n:,}** objects
- **{n_qso:,}** quasars, **{n_seyfert:,}** Seyferts, **{n_blazar:,}** blazars

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/quasar-catalog", split="train")
df = ds.to_pandas()

# AGN type breakdown
df["agn_category"].value_counts()
```

## Update frequency

Updated **weekly on Monday at 19:00 UTC** via GitHub Actions.

## Data source

[SIMBAD Astronomical Database](https://simbad.u-strasbg.fr/) (CDS, Strasbourg).

## Related datasets

- [black-hole-catalog](https://huggingface.co/datasets/juliensimon/black-hole-catalog) — Known black hole systems and X-ray binaries
- [messier-catalog](https://huggingface.co/datasets/juliensimon/messier-catalog) — 110 iconic deep-sky objects
- [ngc-ic-catalog](https://huggingface.co/datasets/juliensimon/ngc-ic-catalog) — 14K deep-sky objects (NGC + IC)
- [galaxy-clusters](https://huggingface.co/datasets/juliensimon/galaxy-clusters) — 1,650+ Planck SZ-detected clusters

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/quasar-catalog) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{quasar_catalog,
  author = {{Simon, Julien}},
  title = {{Quasar & AGN Catalog}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/quasar-catalog}},
  note = {{Based on SIMBAD astronomical database (CDS Strasbourg)}}
}}
```
""")

        print("Uploading to HF...")
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp_dir), ".",
             "--repo-type", "dataset",
             "--commit-message", f"Update quasar catalog: {n:,} objects"],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={n}\n")
    print("Done.")


if __name__ == "__main__":
    main()
