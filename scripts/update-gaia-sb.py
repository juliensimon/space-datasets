#!/usr/bin/env python3
"""Fetch Gaia DR3 Spectroscopic Binary orbital solutions from VizieR and upload to HF."""

import io
import re
import sys
import time

import pandas as pd
import requests

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/gaia-dr3-spectroscopic-binaries"

# VizieR table names for Gaia DR3 non-single stars spectroscopic binaries
VIZIER_SB1 = 'SELECT * FROM "I/357/tbosb1"'
VIZIER_SB2 = 'SELECT * FROM "I/357/tbosb2"'

# Alternative VizieR table (nss_two_body_orbit equivalent)
VIZIER_ALT = 'SELECT * FROM "I/357/nsstwobody"'

# Fallback: Gaia Archive TAP
GAIA_TAP = "https://gea.esac.esa.int/tap-server/tap/sync"
GAIA_PAGE_SIZE = 500_000

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "source_id": "Gaia DR3 unique source identifier (64-bit integer as string); stable within the Gaia DR3 data release",
    "solution_type": "NSS solution type: SB1 (single-lined, only primary spectrum visible) or SB2 (double-lined, both spectra visible providing mass ratio)",
    "ra_deg": "Right ascension ICRS at Gaia reference epoch, in decimal degrees (0-360)",
    "dec_deg": "Declination ICRS at Gaia reference epoch, in decimal degrees (-90 to +90)",
    "period_days": "Orbital period in days; ranges from <1 day (contact binaries) to >1000 days (wide systems); the period distribution encodes binary formation physics",
    "period_days_err": "Uncertainty on orbital period (days)",
    "eccentricity": "Orbital eccentricity (0 = circular, 1 = parabolic); short-period systems (P < 10 d) are expected to be circularized by tidal friction",
    "eccentricity_err": "Uncertainty on orbital eccentricity",
    "t_periastron": "Time of periastron passage in Barycentric Julian Date (BJD); reference point for the orbital phase",
    "t_periastron_err": "Uncertainty on periastron time (BJD)",
    "center_of_mass_velocity": "Center-of-mass (systemic) radial velocity in km/s; the velocity of the binary system relative to the Sun",
    "center_of_mass_velocity_err": "Uncertainty on center-of-mass velocity (km/s)",
    "semi_amplitude_k1": "Semi-amplitude of the primary star's radial velocity curve in km/s; combined with period and eccentricity yields the mass function",
    "semi_amplitude_k1_err": "Uncertainty on K1 (km/s)",
    "semi_amplitude_k2": "Semi-amplitude of the secondary star's radial velocity curve in km/s (SB2 only); provides mass ratio q = K1/K2 directly",
    "semi_amplitude_k2_err": "Uncertainty on K2 (km/s)",
    "omega": "Argument of periastron in degrees; describes the orientation of the orbit in the plane of the sky",
    "omega_err": "Uncertainty on argument of periastron (degrees)",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Orbital solutions for spectroscopic binary stars from the ESA Gaia Data Release 3 \
non-single stars (NSS) pipeline -- single-lined (SB1) and double-lined (SB2) systems \
with full Keplerian orbital parameters.

Spectroscopic binaries are star systems where the binary nature is revealed by periodic \
Doppler shifts in the stellar spectral lines as the stars orbit their common center of mass. \
In a single-lined spectroscopic binary (SB1), only one star's spectrum is visible and the \
radial velocity curve yields the orbital period, eccentricity, and the mass function f(m). \
In a double-lined spectroscopic binary (SB2), both stars contribute detectable spectral \
lines, and the two radial velocity curves provide the mass ratio directly.

The orbital elements -- period, eccentricity, argument of periastron, velocity \
semi-amplitudes (K1, K2), and systemic velocity -- enable measurements of stellar masses, \
tests of tidal circularization theory, and identification of compact companions such as \
white dwarfs, neutron stars, and stellar-mass black holes.

Gaia's Radial Velocity Spectrometer (RVS) has obtained multi-epoch radial velocities for \
millions of stars, and the NSS pipeline has fitted Keplerian orbits to those showing \
statistically significant radial velocity variability. The resulting catalog is an order \
of magnitude larger than any previous compilation.
"""


def snake_case(name: str) -> str:
    """Convert a column name to snake_case."""
    s = re.sub(r"[()]", "", name)
    s = re.sub(r"[\s\-/]+", "_", s)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    return s.lower().strip("_")


def try_vizier_sb1_sb2() -> pd.DataFrame | None:
    """Try fetching SB1 and SB2 tables separately from VizieR."""
    dfs = []
    for label, adql in [("SB1", VIZIER_SB1), ("SB2", VIZIER_SB2)]:
        try:
            print(f"  Trying VizieR {label}...")
            df = vizier_query(adql)
            if len(df) > 10:
                df["solution_type"] = label
                dfs.append(df)
                print(f"    {len(df):,} {label} solutions")
            else:
                print(f"    Only {len(df)} rows, skipping")
        except SystemExit:
            raise
        except Exception as e:
            print(f"    {label} failed: {e}")

    if dfs:
        combined = pd.concat(dfs, ignore_index=True)
        if len(combined) > 50_000:
            return combined
        print(f"  Combined only {len(combined):,} rows, trying alternatives...")
    return None


def try_vizier_nsstwobody() -> pd.DataFrame | None:
    """Try the nss_two_body_orbit table on VizieR, filtering for SB solutions."""
    try:
        print("  Trying VizieR nsstwobody table...")
        df = vizier_query(VIZIER_ALT)
        if len(df) > 50_000:
            print(f"    {len(df):,} rows from nsstwobody")
            for col in df.columns:
                if "type" in col.lower() or "sol" in col.lower():
                    mask = df[col].astype(str).str.upper().str.contains("SB", na=False)
                    if mask.sum() > 10_000:
                        df = df[mask].reset_index(drop=True)
                        print(f"    Filtered to {len(df):,} SB solutions")
                        df["solution_type"] = df[col].astype(str).str.strip()
                        break
            return df
    except SystemExit:
        raise
    except Exception as e:
        print(f"    nsstwobody failed: {e}")
    return None


def fetch_gaia_archive() -> pd.DataFrame:
    """Fallback: fetch from Gaia Archive TAP with pagination."""
    print("  Falling back to ESA Gaia Archive TAP...")
    all_dfs = []
    offset = 0
    while True:
        query = (
            "SELECT * FROM gaiadr3.nss_two_body_orbit "
            "WHERE nss_solution_type LIKE 'SB%' "
            f"ORDER BY source_id OFFSET {offset}"
        )
        print(f"    Fetching rows {offset:,}-{offset + GAIA_PAGE_SIZE:,}...")
        resp = requests.post(GAIA_TAP, data={
            "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv",
            "QUERY": query, "MAXREC": GAIA_PAGE_SIZE,
        }, timeout=600)
        resp.raise_for_status()

        if resp.text.strip().startswith("<?xml") or resp.text.strip().startswith("<VOTABLE"):
            print("::error::Gaia Archive returned VOTable instead of CSV")
            sys.exit(1)

        df = pd.read_csv(io.StringIO(resp.text))
        if len(df) == 0:
            break
        all_dfs.append(df)
        print(f"      got {len(df):,} rows")
        offset += len(df)
        if len(df) < GAIA_PAGE_SIZE:
            break
        time.sleep(2)

    if not all_dfs:
        print("::error::Gaia Archive returned no data")
        sys.exit(1)

    result = pd.concat(all_dfs, ignore_index=True)

    # Add solution_type column from nss_solution_type if present
    for col in result.columns:
        if col.lower() in ("nss_solution_type", "nsssolutiontype"):
            result = result.rename(columns={col: "solution_type"})
            break

    return result


def main():
    print("Fetching Gaia DR3 Spectroscopic Binaries...")

    # Strategy 1: VizieR SB1 + SB2 tables
    df = try_vizier_sb1_sb2()

    # Strategy 2: VizieR nsstwobody table
    if df is None:
        df = try_vizier_nsstwobody()

    # Strategy 3: Gaia Archive TAP
    if df is None:
        df = fetch_gaia_archive()

    print(f"  {len(df):,} spectroscopic binary solutions fetched")

    # Drop recno (VizieR internal)
    if "recno" in df.columns:
        df = df.drop(columns=["recno"])

    # Snake-case all columns
    df.columns = [snake_case(c) for c in df.columns]

    # Rename VizieR columns to more descriptive names
    df = df.rename(columns={
        "source": "source_id",
        "sol_id": "solution_id",
        "ra_icrs": "ra_deg",
        "de_icrs": "dec_deg",
        "per": "period_days",
        "e_per": "period_days_err",
        "tperi": "t_periastron",
        "e_tperi": "t_periastron_err",
        "vcm": "center_of_mass_velocity",
        "e_vcm": "center_of_mass_velocity_err",
        "k1": "semi_amplitude_k1",
        "e_k1": "semi_amplitude_k1_err",
        "k2": "semi_amplitude_k2",
        "e_k2": "semi_amplitude_k2_err",
        "e_ecc": "eccentricity_err",
        "e_omega": "omega_err",
    })

    # Ensure solution_type survived renaming
    if "solution_type" not in df.columns:
        for col in df.columns:
            if "sol" in col and "type" in col:
                df = df.rename(columns={col: "solution_type"})
                break

    # Normalize solution_type values
    if "solution_type" in df.columns:
        df["solution_type"] = df["solution_type"].astype(str).str.strip().str.upper()
        sb_mask = df["solution_type"].str.startswith("SB")
        if sb_mask.sum() > 0 and sb_mask.sum() < len(df):
            print(f"  Filtering to SB solutions: {sb_mask.sum():,} of {len(df):,}")
            df = df[sb_mask].reset_index(drop=True)

    # Convert all numeric columns (except string identifiers)
    for col in df.columns:
        if col in ("solution_type", "source_id"):
            continue
        if df[col].dtype == object:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Clean string columns
    for col in ["solution_type", "source_id"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
            )

    # source_id as string (Gaia source IDs are large integers)
    if "source_id" in df.columns:
        df["source_id"] = df["source_id"].astype(str).str.replace(r"\.0$", "", regex=True)

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Sort by source_id
    sort_col = "source_id" if "source_id" in df.columns else df.columns[0]
    df = df.sort_values(sort_col).reset_index(drop=True)

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_sb1 = 0
    n_sb2 = 0
    if "solution_type" in df.columns:
        type_counts = df["solution_type"].value_counts()
        n_sb1 = int(type_counts.get("SB1", 0))
        n_sb2 = int(type_counts.get("SB2", 0))

    # Period stats
    period_median = df["period_days"].median() if "period_days" in df.columns else float("nan")
    period_min = df["period_days"].min() if "period_days" in df.columns else float("nan")
    period_max = df["period_days"].max() if "period_days" in df.columns else float("nan")

    # Eccentricity stats
    ecc_median = df["eccentricity"].median() if "eccentricity" in df.columns else float("nan")
    n_circular = int((df["eccentricity"] < 0.05).sum()) if "eccentricity" in df.columns else 0

    quick_stats = f"""\
- **{n_total:,}** spectroscopic binary orbital solutions
- **{n_sb1:,}** single-lined (SB1) systems
- **{n_sb2:,}** double-lined (SB2) systems
- Period range: **{period_min:.4f}** to **{period_max:.2f}** days (median {period_median:.4f})
- Median eccentricity: **{ecc_median:.3f}** ({n_circular:,} near-circular with e < 0.05)"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/gaia-dr3-spectroscopic-binaries", split="train")
df = ds.to_pandas()

# SB1 vs SB2 breakdown
print(df["solution_type"].value_counts())

# Period-eccentricity diagram (tidal circularization)
import matplotlib.pyplot as plt
valid = df.dropna(subset=["period_days", "eccentricity"])
plt.scatter(valid["period_days"], valid["eccentricity"], s=0.3, alpha=0.3)
plt.xscale("log")
plt.xlabel("Period (days)")
plt.ylabel("Eccentricity")
plt.title("Gaia DR3 Spectroscopic Binaries: Period vs Eccentricity")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Gaia DR3 Spectroscopic Binary Stars",
        description=DESCRIPTION,
        tags=["space", "gaia", "esa", "binary-stars", "spectroscopic", "stellar",
              "astronomy", "open-data", "tabular-data", "parquet"],
        source_url="https://vizier.cds.unistra.fr/viz-bin/VizieR-3?-source=I/357",
        license="other",
        license_name="cc-by-nc-3.0-igo",
        license_link="https://creativecommons.org/licenses/by-nc/3.0/igo/",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e000191/GSFC_20171208_Archive_e000191~medium.jpg",
            "alt": "A youthful globular star cluster observed by the Hubble Space Telescope",
            "credit": "NASA/ESA/Hubble",
        },
        related_datasets=[
            "juliensimon/wds-double-stars",
            "juliensimon/gaia-dr3-eclipsing-binaries",
            "juliensimon/kepler-eclipsing-binaries",
            "juliensimon/xray-binary-catalog",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "ra_deg", "dec_deg", "period_days", "period_days_err",
                "eccentricity", "eccentricity_err",
                "t_periastron", "t_periastron_err",
                "center_of_mass_velocity", "center_of_mass_velocity_err",
                "semi_amplitude_k1", "semi_amplitude_k1_err",
                "semi_amplitude_k2", "semi_amplitude_k2_err",
                "omega", "omega_err",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="gaia_dr3_spectroscopic_binaries.parquet",
            min_rows=100_000,
            expected_columns=["source_id", "solution_type", "period_days"],
            critical_columns=["source_id", "solution_type"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Gaia DR3 spectroscopic binaries: {n_total:,} orbital solutions",
        )
    print("Done.")


if __name__ == "__main__":
    main()
