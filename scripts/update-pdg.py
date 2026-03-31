#!/usr/bin/env python3
"""Fetch PDG particle properties via the particle package and upload to HF."""

import os
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
from particle import Particle

from validate import check_dataset

HF_REPO = "juliensimon/pdg-particle-properties"


def main():
    print("Building PDG particle properties from particle package...")
    particles = Particle.findall()

    records = []
    for p in particles:
        try:
            mass = float(p.mass) if p.mass is not None else None
        except (TypeError, ValueError):
            mass = None
        try:
            mass_unc = float(p.mass_upper) if p.mass_upper is not None else None
        except (TypeError, ValueError):
            mass_unc = None
        try:
            width = float(p.width) if p.width is not None else None
        except (TypeError, ValueError):
            width = None
        try:
            width_unc = float(p.width_upper) if p.width_upper is not None else None
        except (TypeError, ValueError):
            width_unc = None
        try:
            lifetime = float(p.lifetime) if p.lifetime is not None else None
        except (TypeError, ValueError):
            lifetime = None
        try:
            ctau = float(p.ctau) if p.ctau is not None else None
        except (TypeError, ValueError):
            ctau = None
        try:
            charge = float(p.charge) if p.charge is not None else None
        except (TypeError, ValueError):
            charge = None
        try:
            J = float(p.J) if p.J is not None else None
        except (TypeError, ValueError):
            J = None
        try:
            P = int(p.P) if p.P is not None else None
        except (TypeError, ValueError):
            P = None
        try:
            I = str(p.I) if p.I is not None else None
        except (TypeError, ValueError):
            I = None
        try:
            G = int(p.G) if p.G is not None else None
        except (TypeError, ValueError):
            G = None
        try:
            C = int(p.C) if p.C is not None else None
        except (TypeError, ValueError):
            C = None

        records.append({
            "pdg_id": int(p.pdgid),
            "name": p.name,
            "latex_name": p.latex_name,
            "mass_mev": mass,
            "mass_uncertainty_mev": mass_unc,
            "width_mev": width,
            "width_uncertainty_mev": width_unc,
            "charge": charge,
            "spin": J,
            "parity": P,
            "isospin": I,
            "g_parity": G,
            "c_parity": C,
            "anti_flag": int(p.anti_flag.value) if hasattr(p.anti_flag, "value") else int(p.anti_flag),
            "is_self_conjugate": p.is_self_conjugate,
            "lifetime_ns": lifetime,
            "ctau_mm": ctau,
        })

    df = pd.DataFrame(records)
    print(f"  {len(df):,} particles")

    # Convert numerics
    numeric_cols = [
        "mass_mev", "mass_uncertainty_mev", "width_mev", "width_uncertainty_mev",
        "charge", "spin", "lifetime_ns", "ctau_mm",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["parity"] = pd.to_numeric(df["parity"], errors="coerce").astype("Int64")
    df["g_parity"] = pd.to_numeric(df["g_parity"], errors="coerce").astype("Int64")
    df["c_parity"] = pd.to_numeric(df["c_parity"], errors="coerce").astype("Int64")

    # Validation
    check_dataset(
        df, "pdg",
        min_rows=200,
        expected_columns=["pdg_id", "name", "mass_mev", "charge"],
        critical_columns=["pdg_id", "name"],
    )

    # Stats for README
    n_total = len(df)
    n_with_mass = int(df["mass_mev"].notna().sum())
    n_with_width = int(df["width_mev"].notna().sum())
    n_stable = int((df["width_mev"].isna() & df["mass_mev"].notna()).sum())
    n_self_conj = int(df["is_self_conjugate"].sum())
    heaviest = df.loc[df["mass_mev"].idxmax()] if df["mass_mev"].notna().any() else None

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "pdg_particle_properties.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        heaviest_str = ""
        if heaviest is not None:
            heaviest_str = f"- Heaviest particle: **{heaviest['name']}** ({heaviest['mass_mev']:,.0f} MeV)"

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "PDG Particle Properties"
language:
  - en
description: "Every known particle from the Particle Data Group (PDG) — THE reference used by every particle physicist."
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - physics
  - particle
  - pdg
  - standard-model
  - high-energy-physics
  - open-data
  - tabular-data
  - parquet
size_categories:
  - n<1K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/pdg_particle_properties.parquet
    default: true
---

# PDG Particle Properties

*Part of the [Physics Datasets](https://huggingface.co/collections/juliensimon/physics-datasets-69c2d4682d37dfdb77447bd7) collection on Hugging Face.*

![Update PDG](https://github.com/juliensimon/space-datasets/actions/workflows/update-pdg.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.pdg&label=updated&color=brightgreen)

Properties of every known particle from the Particle Data Group (PDG).
Currently **{n_total:,}** particles.

## Dataset description

The Particle Data Group (PDG) is THE definitive reference for particle physics
properties, used by every particle physicist worldwide. This dataset provides
a machine-readable version of the PDG particle listings, including masses,
widths, lifetimes, quantum numbers, and decay properties for all known
elementary particles, hadrons, and nuclei.

Data is sourced via the `particle` Python package which provides clean,
programmatic access to the full PDG dataset.

The Particle Data Group, based at Lawrence Berkeley National Laboratory, has published its Review of Particle Physics since 1957 -- the single most cited publication in high-energy physics. The PDG compiles and critically evaluates measurements from thousands of experiments at facilities like CERN's Large Hadron Collider, Fermilab, KEK, and SLAC to produce world-average values for particle masses, widths, lifetimes, and quantum numbers. Every experimentalist and theorist in particle physics relies on PDG values as the authoritative reference when designing experiments, comparing predictions, or setting limits on new physics.

The dataset covers the full spectrum of known particles: the six quarks, six leptons, and gauge bosons of the Standard Model; the Higgs boson discovered at CERN in 2012; hundreds of mesons (quark-antiquark bound states) and baryons (three-quark bound states) organized by flavor quantum numbers; and light nuclei. Each entry carries quantum numbers (spin, parity, isospin, G-parity, C-parity) that encode the particle's transformation properties under fundamental symmetries. The mass uncertainty and decay width together constrain how precisely a particle can be identified in detector data and how quickly it decays -- from stable particles like the proton (lifetime exceeding 10^34 years) to resonances that exist for barely 10^-24 seconds.

This machine-readable version of the PDG listings supports automated analysis pipelines in high-energy physics, Monte Carlo event generators that simulate particle collisions, detector simulation frameworks, and educational tools. It is also valuable for machine learning applications in particle identification, anomaly detection in collider data, and studies of mass spectrum patterns that may reveal deeper organizational principles beyond the Standard Model.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `pdg_id` | int64 | PDG Monte Carlo particle ID |
| `name` | string | Particle name (e.g. "pi+", "K*(892)0") |
| `latex_name` | string | LaTeX-formatted name |
| `mass_mev` | float64 | Mass (MeV/c^2) |
| `mass_uncertainty_mev` | float64 | Mass upper uncertainty (MeV/c^2) |
| `width_mev` | float64 | Decay width (MeV) |
| `width_uncertainty_mev` | float64 | Width upper uncertainty (MeV) |
| `charge` | float64 | Electric charge (units of e) |
| `spin` | float64 | Spin J |
| `parity` | Int64 | Parity P (+1 or -1) |
| `isospin` | string | Isospin I |
| `g_parity` | Int64 | G-parity (+1 or -1) |
| `c_parity` | Int64 | C-parity (+1 or -1) |
| `anti_flag` | int64 | Anti-particle flag |
| `is_self_conjugate` | bool | Whether particle is its own antiparticle |
| `lifetime_ns` | float64 | Lifetime (nanoseconds) |
| `ctau_mm` | float64 | Proper decay length c*tau (mm) |

## Quick stats

- **{n_total:,}** particles in the database
- **{n_with_mass:,}** with measured mass
- **{n_with_width:,}** with measured width
- **{n_self_conj:,}** self-conjugate particles
{heaviest_str}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/pdg-particle-properties", split="train")
df = ds.to_pandas()

# All mesons (PDG ID 100-999)
mesons = df[(df["pdg_id"].abs() >= 100) & (df["pdg_id"].abs() < 1000)]

# Mass spectrum plot
import matplotlib.pyplot as plt
masses = df[df["mass_mev"].notna()]["mass_mev"]
plt.hist(masses[masses < 5000], bins=100, log=True)
plt.xlabel("Mass (MeV/c^2)")
plt.ylabel("Count")
plt.title("Particle Mass Spectrum")

# Stable particles (no measured width)
stable = df[df["width_mev"].isna() & df["mass_mev"].notna()]

# Heaviest particles
heaviest = df.sort_values("mass_mev", ascending=False).head(20)
```

## Data source

[Particle Data Group](https://pdg.lbl.gov/) (PDG), via the
[`particle`](https://pypi.org/project/particle/) Python package.

## Update schedule

Annual (August 1) via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/pdg-particle-properties) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{pdg_particle_properties,
  author = {{Simon, Julien}},
  title = {{PDG Particle Properties}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/pdg-particle-properties}},
  note = {{Based on Particle Data Group (PDG) data via the particle Python package}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update PDG particle properties: {n_total:,} particles"
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
