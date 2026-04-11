#!/usr/bin/env python3
"""Fetch Pierre Auger Observatory cosmic ray data from Zenodo and upload to HF.

Source: Pierre Auger Observatory open data release on Zenodo.
DOI: 10.5281/zenodo.4487613
"""

import io
import re
import sys
import zipfile
from pathlib import Path

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

ZENODO_URL = "https://zenodo.org/api/records/4487613/files/summary.zip/content"
HF_REPO = "juliensimon/auger-cosmic-rays"

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "energy": "Cosmic ray energy in EeV (10^18 eV); Auger detects events typically 1-300 EeV; the GZK suppression steepens the spectrum above ~40 EeV due to interactions with CMB photons",
    "log_e": "Base-10 logarithm of the cosmic ray energy in eV (e.g. 19.5 = 10^19.5 eV ~ 3 EeV); convenient for plotting the steeply falling energy spectrum",
    "lgne": "Base-10 logarithm of the cosmic ray energy (alternate column name for log_e; same units and range)",
    "ra": "Reconstructed right ascension of the cosmic ray arrival direction (ICRS J2000.0, degrees, 0-360); deflected by Galactic and extragalactic magnetic fields, so this is an approximate source direction; angular uncertainty ~1 deg for the highest-energy events",
    "dec": "Reconstructed declination of the cosmic ray arrival direction (ICRS J2000.0, degrees, -90 to +90); limited to the Auger Observatory sky coverage centered on the Southern Hemisphere",
    "gal_l": "Galactic longitude of the reconstructed arrival direction (degrees, 0-360); used to search for correlations with Galactic structures (magnetic field, sources near the Galactic plane)",
    "gal_b": "Galactic latitude of the reconstructed arrival direction (degrees, -90 to +90); |b| < 10 deg indicates directions close to the Galactic plane where magnetic deflection is largest",
    "zenith": "Zenith angle of the incoming air shower at the Auger array (degrees); <60 deg = vertical shower dominated by electromagnetic component, 60-80 deg = inclined shower with muon-rich content at ground; affects the reconstruction method and energy calibration",
    "theta": "Shower zenith angle (degrees); equivalent to zenith column when both are present; see zenith description",
    "azimuth": "Azimuth angle of the shower arrival direction measured at the array (degrees, 0-360 clockwise from north); combined with zenith angle, defines the reconstructed particle trajectory",
    "phi": "Azimuth angle of the shower (degrees); equivalent to azimuth column when both are present",
    "xmax": "Atmospheric depth of shower maximum X_max (g/cm^2); the depth in the atmosphere at which the air shower reaches peak particle multiplicity; heavier nuclei (iron) have smaller X_max than lighter nuclei (protons) at the same energy; key observable for mass composition measurements",
    "s1000": "Signal at 1000 m from the shower core measured by the surface detector array (in VEM -- Vertical Equivalent Muon units); the primary energy estimator for surface-detector-only events; calibrated against fluorescence detector energies",
    "source_file": "Identifier of the source file within the Zenodo archive from which this event was extracted; useful for tracing events back to the original release tables",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Summary data from the Pierre Auger Observatory, the world's largest detector of \
ultra-high-energy cosmic rays. Located in Mendoza, Argentina, it uses 1,660 \
water-Cherenkov surface detectors spread over 3,000 km^2, plus fluorescence \
telescopes, to detect cosmic rays with energies above 10^18 eV.

Ultra-high-energy cosmic rays (UHECRs) are the most energetic particles observed \
in nature, with individual events carrying macroscopic amounts of kinetic energy -- \
a single particle at 10^20 eV has roughly the energy of a tennis ball served at \
150 km/h, compressed into a single subatomic particle. When such a particle strikes \
the atmosphere, it triggers a cascade of billions of secondary particles called an \
extensive air shower, spreading over several square kilometers at ground level.

The Pierre Auger Observatory detects these showers through a hybrid technique: the \
surface detector array measures the lateral distribution and timing of shower particles \
on the ground, while fluorescence telescopes observe the ultraviolet glow of atmospheric \
nitrogen excited by the shower as it develops. This combination provides both the energy \
and the atmospheric depth of shower maximum (Xmax), a key observable for inferring the \
mass composition of the primary cosmic ray.

Auger's major scientific results include the confirmation of the GZK suppression (the \
steepening of the cosmic ray spectrum above ~5x10^19 eV, expected from interactions \
with the cosmic microwave background), evidence for a dipole anisotropy in arrival \
directions above 8x10^18 eV suggesting an extragalactic origin, and measurements of \
Xmax distributions that indicate a transition from light (proton-like) to heavier \
(iron-like) composition at the highest energies.
"""


def to_snake_case(name: str) -> str:
    """Convert column name to snake_case."""
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    s = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s)
    s = re.sub(r"[^\w]", "_", s.lower())
    s = re.sub(r"_+", "_", s).strip("_")
    return s


def main():
    print("Downloading Pierre Auger summary data from Zenodo...")
    resp = requests.get(ZENODO_URL, timeout=120)
    resp.raise_for_status()
    print(f"  Downloaded {len(resp.content) / 1024 / 1024:.1f} MB")

    # Extract CSV files from zip
    frames = []
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        csv_files = [n for n in zf.namelist() if n.endswith(".csv")]
        print(f"  Found {len(csv_files)} CSV files in archive")
        for name in csv_files:
            try:
                with zf.open(name) as f:
                    part = pd.read_csv(f)
                    if len(part) > 0:
                        part["source_file"] = Path(name).stem
                        frames.append(part)
                        print(f"    {name}: {len(part):,} rows")
            except Exception as e:
                print(f"    {name}: skipped ({e})")

    if not frames:
        # Try TSV or other delimiters
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            for name in zf.namelist():
                if name.endswith((".txt", ".dat", ".tsv")):
                    try:
                        with zf.open(name) as f:
                            part = pd.read_csv(f, sep=None, engine="python")
                            if len(part) > 0:
                                part["source_file"] = Path(name).stem
                                frames.append(part)
                                print(f"    {name}: {len(part):,} rows")
                    except Exception as e:
                        print(f"    {name}: skipped ({e})")

    if not frames:
        print("::error::No data extracted from Zenodo archive")
        sys.exit(1)

    df = pd.concat(frames, ignore_index=True)
    print(f"  Combined: {len(df):,} rows, {len(df.columns)} columns")

    # Rename columns to snake_case
    df.columns = [to_snake_case(c) for c in df.columns]

    # Clean string columns
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].astype(str).str.strip().replace(
            {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
        )

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    df = df.reset_index(drop=True)
    n_total = len(df)
    print(f"  {n_total:,} events total")

    # ── Domain-specific stats for README ─────────────────────────────
    has_energy = "energy" in df.columns and df["energy"].notna().any()
    has_xmax = "xmax" in df.columns and df["xmax"].notna().any()

    stats_lines = [f"- **{n_total:,}** cosmic ray events"]
    if has_energy:
        e_min = df["energy"].min()
        e_max = df["energy"].max()
        stats_lines.append(f"- Energy range: **{e_min:.1f}** to **{e_max:.1f}** EeV")
    if has_xmax:
        n_xmax = int(df["xmax"].notna().sum())
        stats_lines.append(f"- **{n_xmax:,}** events with X_max composition measurement")
    n_sources = df["source_file"].nunique() if "source_file" in df.columns else 0
    if n_sources:
        stats_lines.append(f"- Data from **{n_sources}** source tables in the Zenodo archive")
    quick_stats = "\n".join(stats_lines)

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/auger-cosmic-rays", split="train")
df = ds.to_pandas()
print(f"{len(df):,} Auger events")
print(df.describe())

# Energy spectrum
import matplotlib.pyplot as plt
if "energy" in df.columns:
    plt.hist(df["energy"].dropna(), bins=50, log=True)
    plt.xlabel("Energy (EeV)")
    plt.ylabel("Count")
    plt.title("Auger Cosmic Ray Energy Distribution")
    plt.show()
```"""

    # Use a flexible min_rows -- summary data may be smaller
    min_rows = 100 if n_total < 50000 else 50000

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Pierre Auger Observatory Cosmic Rays",
        description=DESCRIPTION,
        tags=["space", "physics", "cosmic-ray", "auger", "ultra-high-energy",
              "open-data", "tabular-data", "parquet"],
        source_url="https://doi.org/10.5281/zenodo.4487613",
        task_categories=["tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/physics-datasets-69c2d4682d37dfdb77447bd7",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA03519/PIA03519~small.jpg",
            "alt": "Cassiopeia A supernova remnant in X-ray, optical, and infrared light",
            "credit": "NASA/JPL-Caltech/STScI/CXC/SAO",
        },
        related_datasets=[
            "juliensimon/crdb-cosmic-ray-spectra",
        ],
    ) as p:
        numeric_cols = [c for c in ["energy", "zenith", "azimuth", "ra", "dec",
                                     "gal_l", "gal_b", "log_e", "theta", "phi",
                                     "xmax", "s1000", "lgne"] if c in df.columns]
        df = p.clean(
            df,
            numeric=numeric_cols,
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="auger_cosmic_rays.parquet",
            min_rows=min_rows,
            expected_columns=[c for c in df.columns[:4]],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Auger cosmic rays: {n_total:,} records",
        )
    print("Done.")


if __name__ == "__main__":
    main()
