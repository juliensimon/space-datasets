#!/usr/bin/env python3
"""Fetch TESS Objects of Interest from NASA Exoplanet Archive and upload to HF."""

import io

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

HF_REPO = "juliensimon/tess-toi-candidates"
TAP_URL = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"

ADQL = "SELECT * FROM toi"

# ── Column mapping ───────────────────────────────────────────────────
RENAME = {
    "tid": "toi_id",
    "toipfx": "toi_prefix",
    "pl_name": "planet_name",
    "rastr": "ra_str",
    "ra": "ra_deg",
    "decstr": "dec_str",
    "dec": "dec_deg",
    "pl_orbper": "period_days",
    "pl_orbpererr1": "period_err_upper",
    "pl_orbpererr2": "period_err_lower",
    "pl_rade": "radius_earth",
    "pl_radeerr1": "radius_err_upper",
    "pl_radeerr2": "radius_err_lower",
    "pl_eqt": "equilibrium_temp_k",
    "pl_trandep": "transit_depth_ppm",
    "st_tmag": "tmag",
    "toi_created": "created_date",
    "tfopwg_disp": "disposition",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "toi_id": "TESS Input Catalog (TIC) integer identifier of the host star; the primary stellar ID in TIC v8; multiple planet candidates from the same star share the same toi_id",
    "toi_prefix": "TOI designation number (e.g. 175.01); format is TIC_ID.candidate_number; additional candidates from the same star increment the decimal (.01, .02, ...)",
    "planet_name": "Confirmed planet designation (e.g. 'TOI-175 b'); null for unconfirmed candidates that have not yet received an official planet name",
    "ra_str": "Right ascension of the host star in sexagesimal notation (HH:MM:SS.ss); provided for human-readable reference alongside the numeric ra_deg",
    "ra_deg": "ICRS J2000.0 right ascension of the host star in degrees (0-360)",
    "dec_str": "Declination of the host star in sexagesimal notation (+/-DD:MM:SS.s); provided for human-readable reference alongside the numeric dec_deg",
    "dec_deg": "ICRS J2000.0 declination of the host star in degrees (-90 to +90)",
    "period_days": "Orbital period in days from the transit fit; null for single-transit events where period cannot be determined; typical range 0.5-100 days for TESS detections",
    "period_err_upper": "Upper 1-sigma uncertainty on orbital period in days; null when period itself is null",
    "period_err_lower": "Lower 1-sigma uncertainty on orbital period in days (negative value); null when period itself is null",
    "radius_earth": "Planet radius in Earth radii derived from the transit depth and stellar radius; null until stellar parameters are available; sub-Neptunes: 1.5-4, Neptunes: 4-7, giant planets: >7",
    "radius_err_upper": "Upper 1-sigma uncertainty on planet radius in Earth radii; null when radius itself is null",
    "radius_err_lower": "Lower 1-sigma uncertainty on planet radius in Earth radii (negative value); null when radius itself is null",
    "equilibrium_temp_k": "Estimated equilibrium temperature of the planet in Kelvin assuming zero albedo; derived from stellar luminosity and orbital distance; null if stellar parameters unavailable",
    "transit_depth_ppm": "Transit depth in parts per million (fractional flux dip x 10^6); typical range 100-50000 ppm; an Earth-sized planet transiting a Sun-like star produces ~84 ppm; giant planets can exceed 10000 ppm",
    "tmag": "Host star brightness in the TESS T-band (~600-1000 nm); similar to but not identical to Cousins I-band; typical range 6-15 for TOI hosts; brighter stars yield better photometric precision",
    "created_date": "ISO date when the TOI entry was first created in the TESS TOI catalog; tracks when the candidate was initially flagged by the TESS pipeline",
    "disposition": "TESS Follow-Up Observing Program Working Group (TFOPWG) disposition after ground-based vetting: 'CP' = Confirmed Planet, 'PC' = Planet Candidate (active), 'APC' = Ambiguous Planet Candidate, 'FP' = False Positive (ruled out), 'KP' = Known Planet",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Planet candidates identified by NASA's Transiting Exoplanet Survey Satellite (TESS), \
from the NASA Exoplanet Archive TOI catalog. Updated weekly.

TESS is a NASA space telescope launched in 2018 that surveys the entire sky for \
transiting exoplanets. When a star shows periodic brightness dips consistent with \
a planet crossing in front of it, it is flagged as a TESS Object of Interest (TOI). \
Each TOI undergoes follow-up observations to determine whether it is a genuine planet, \
a false positive (e.g., eclipsing binary), or remains an active candidate.

TESS represents a fundamentally different survey strategy from its predecessor Kepler. While \
Kepler stared at a single patch of sky for four years to find small planets around faint stars, \
TESS surveys nearly the entire sky in 27-day sectors, optimized for finding planets around the \
nearest and brightest stars. This design choice means TESS planets are far more amenable to \
ground-based follow-up: radial velocity mass measurements, atmospheric characterization with \
JWST, and even direct imaging with next-generation telescopes. The TOI catalog is the primary \
pipeline output that feeds this follow-up ecosystem.

Each TOI entry carries a disposition assigned by the TESS Follow-up Observing Program Working \
Group (TFOPWG): CP for confirmed planets that have passed rigorous vetting, FP for false \
positives ruled out by follow-up observations (commonly background eclipsing binaries or \
stellar variability), KP for known planets independently discovered, and PC for active planet \
candidates still awaiting confirmation.
"""


def main():
    print("Fetching TESS TOI catalog from NASA Exoplanet Archive...")
    resp = requests.post(TAP_URL, data={
        "REQUEST": "doQuery",
        "LANG": "ADQL",
        "FORMAT": "csv",
        "QUERY": ADQL,
    }, timeout=120)
    resp.raise_for_status()

    df = pd.read_csv(io.StringIO(resp.text))
    print(f"  {len(df):,} TOI entries")

    # Rename key columns
    df = df.rename(columns={k: v for k, v in RENAME.items() if k in df.columns})

    # Clean string columns
    for col in ["planet_name", "ra_str", "dec_str", "disposition", "created_date"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
            )

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    df = df.sort_values("toi_id").reset_index(drop=True)

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_confirmed = int(df["disposition"].eq("CP").sum()) if "disposition" in df.columns else 0
    n_fp = int(df["disposition"].eq("FP").sum()) if "disposition" in df.columns else 0
    n_with_radius = int(df["radius_earth"].notna().sum()) if "radius_earth" in df.columns else 0

    quick_stats = f"""\
- **{n_total:,}** TOI entries
- **{n_confirmed:,}** confirmed planets (CP)
- **{n_fp:,}** false positives (FP)
- **{n_with_radius:,}** with radius estimates"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/tess-toi-candidates", split="train")
df = ds.to_pandas()

# Confirmed planets
confirmed = df[df["disposition"] == "CP"]
print(f"{len(confirmed):,} confirmed planets")

# Small rocky planets (< 2 Earth radii)
rocky = df[df["radius_earth"] < 2.0].dropna(subset=["radius_earth"])
print(f"{len(rocky):,} candidates with radius < 2 Earth radii")

# Period distribution
import matplotlib.pyplot as plt
valid = df.dropna(subset=["period_days"])
plt.hist(valid["period_days"], bins=100, range=(0, 50))
plt.xlabel("Orbital period (days)")
plt.ylabel("Count")
plt.title("TESS TOI Period Distribution")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="TESS Objects of Interest (TOI) Planet Candidates",
        description=DESCRIPTION,
        tags=["space", "exoplanet", "tess", "planet-candidate", "transit",
              "nasa", "open-data", "tabular-data", "parquet"],
        source_url="https://exoplanetarchive.ipac.caltech.edu/",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA21423/PIA21423~small.jpg",
            "alt": "Artist concept of the surface of TRAPPIST-1f exoplanet",
            "credit": "NASA/JPL-Caltech",
        },
        related_datasets=[
            "juliensimon/nasa-exoplanets",
            "juliensimon/neo-close-approaches",
            "juliensimon/pulsar-catalog",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "ra_deg", "dec_deg", "period_days", "period_err_upper",
                "period_err_lower", "radius_earth", "radius_err_upper",
                "radius_err_lower", "equilibrium_temp_k", "transit_depth_ppm", "tmag",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="tess_toi_candidates.parquet",
            min_rows=5000,
            expected_columns=["toi_id", "ra_deg", "dec_deg", "period_days"],
            critical_columns=["toi_id", "ra_deg", "dec_deg"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update TESS TOI candidates: {n_total:,} entries",
        )
    print("Done.")


if __name__ == "__main__":
    main()
