#!/usr/bin/env python3
"""Fetch MUSE Planetary Nebulae catalog from VizieR and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from validate import check_dataset
from vizier_tap import vizier_query


HF_REPO = "juliensimon/planetary-nebulae"

ADQL = """\
SELECT * FROM "J/ApJS/271/40/table3"\
"""


def main():
    print("Fetching MUSE planetary nebulae from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} planetary nebulae")

    # Rename key columns
    known_renames = {
        "RA": "ra_deg",
        "RA_ICRS": "ra_deg",
        "RAICRS": "ra_deg",
        "RAJ2000": "ra_deg",
        "_RA": "ra_deg",
        "DEC": "dec_deg",
        "DE": "dec_deg",
        "DE_ICRS": "dec_deg",
        "DEICRS": "dec_deg",
        "DEJ2000": "dec_deg",
        "_DE": "dec_deg",
        "Vel": "velocity_kms",
        "RV": "velocity_kms",
        "HRV": "velocity_kms",
        "Vhel": "velocity_kms",
        "Morph": "morphology",
        "morph": "morphology",
        "Vmag": "v_mag",
        "Gmag": "g_mag",
        "Bmag": "b_mag",
        "Rmag": "r_mag",
        "Imag": "i_mag",
        "Diam": "diameter_arcsec",
        "diam": "diameter_arcsec",
        "Dist": "distance_kpc",
        "dist": "distance_kpc",
        "OIII": "oiii_flux",
        "Halpha": "halpha_flux",
        "Ha": "halpha_flux",
        "Name": "name",
        "PNG": "png_id",
    }
    rename_map = {k: v for k, v in known_renames.items() if k in df.columns}
    if rename_map:
        df = df.rename(columns=rename_map)

    # Snake-case remaining columns
    already_renamed = set(rename_map.values())
    snake_map = {}
    for col in df.columns:
        if col not in already_renamed:
            snake = col.replace(" ", "_").replace("-", "_").lower()
            if snake != col:
                snake_map[col] = snake
    if snake_map:
        df = df.rename(columns=snake_map)

    # Convert numerics
    for col in ["ra_deg", "dec_deg", "velocity_kms", "v_mag", "g_mag", "b_mag",
                "r_mag", "i_mag", "diameter_arcsec", "distance_kpc",
                "oiii_flux", "halpha_flux"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    check_dataset(df, "planetary-nebulae", min_rows=1000,
        expected_columns=["ra_deg", "dec_deg"],
        critical_columns=["ra_deg", "dec_deg"])

    # Stats for README
    n_total = len(df)
    n_with_m5007 = int(df["m5007"].notna().sum()) if "m5007" in df.columns else 0
    n_galaxies = int(df["gal"].nunique()) if "gal" in df.columns else 0

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "planetary_nebulae.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Planetary Nebulae (MUSE Survey)"
language:
  - en
description: "Planetary nebulae identified by MUSE (Multi Unit Spectroscopic Explorer). Sourced via VizieR CDS Strasbourg."
task_categories:
  - tabular-classification
tags:
  - space
  - planetary-nebula
  - muse
  - astronomy
  - open-data
  - tabular-data
size_categories:
  - 1K<n<10K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/planetary_nebulae.parquet
    default: true
---

# Planetary Nebulae (MUSE Survey)

*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

Catalog of **{n_total:,}** planetary nebulae from the MUSE (Multi Unit Spectroscopic
Explorer) survey, with positions and [OIII] 5007 magnitudes.

## Dataset description

Planetary nebulae (PNe) are glowing shells of ionized gas expelled by intermediate-mass
stars at the end of their lives. They are important distance indicators and tracers of
stellar populations and chemical enrichment. This catalog from Jacoby et al. (2024)
presents PNe identified and characterized using the MUSE integral-field spectrograph
on ESO's Very Large Telescope, providing unprecedented spectroscopic detail.

## Quick stats

- **{n_total:,}** planetary nebulae
- **{n_with_m5007:,}** with [OIII] 5007 magnitude measurements
- **{n_galaxies}** host galaxies surveyed

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/planetary-nebulae", split="train")
df = ds.to_pandas()

# PNe with [OIII] magnitudes
if "m5007" in df.columns:
    with_mag = df.dropna(subset=["m5007"])
    print(f"{{len(with_mag):,}} PNe with [OIII] magnitudes")
    print(f"Velocity range: {{with_vel['velocity_kms'].min():.0f}} to {{with_vel['velocity_kms'].max():.0f}} km/s")

# Sky distribution
import matplotlib.pyplot as plt
plt.scatter(df["ra_deg"], df["dec_deg"], s=1, alpha=0.5)
plt.xlabel("RA (deg)")
plt.ylabel("Dec (deg)")
plt.title("MUSE Planetary Nebulae")
```

## Data source

Jacoby, G.H. et al. (2024), "Planetary Nebulae from the MUSE Survey",
ApJS, 271, 40. Accessed via [VizieR](https://vizier.cds.unistra.fr/), CDS Strasbourg.

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update planetary nebulae: {n_total:,} PNe"
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
