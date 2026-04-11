#!/usr/bin/env python3
"""Fetch Washington Double Star Catalog from VizieR and upload to HF.

Source: Mason et al., US Naval Observatory WDS catalog.
VizieR catalog: B/wds/wds
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/wds-double-stars"

# ── Source query ────────────────────────────────────────────────────
ADQL = 'SELECT * FROM "B/wds/wds"'

# ── Column mapping ──────────────────────────────────────────────────
RENAME = {
    "WDS": "wds_id",
    "RAJ2000": "ra_deg",
    "RA_ICRS": "ra_deg",
    "DEJ2000": "dec_deg",
    "DE_ICRS": "dec_deg",
    "Comp": "components",
    "Obs1": "first_observation_year",
    "Obs2": "last_observation_year",
    "Nobs": "n_observations",
    "pa1": "position_angle_first",
    "pa2": "position_angle_last",
    "sep1": "separation_first_arcsec",
    "sep2": "separation_last_arcsec",
    "mag1": "magnitude_primary",
    "mag2": "magnitude_secondary",
    "SpType": "spectral_type",
    "Disc": "discoverer_code",
}

# ── Column descriptions for README schema table ────────────────────
COLUMN_DESCRIPTIONS = {
    "wds_id": "WDS designation in format 'HHMMM+DDMMM' encoding the J2000 position (e.g. '00055+5258'); the standard identifier for double stars in this catalog",
    "ra_deg": "Right ascension of the primary star, ICRS J2000.0 (degrees, 0-360)",
    "dec_deg": "Declination of the primary star, ICRS J2000.0 (degrees, -90 to +90)",
    "components": "Component pair designation (e.g. 'AB' = primary+secondary, 'AC' = primary+tertiary); systems may have multiple entries for different pairs",
    "first_observation_year": "Year of the earliest published observation of this pair (fractional year, e.g. 1889.0)",
    "last_observation_year": "Year of the most recent published observation (fractional year); span indicates how long the pair has been monitored",
    "n_observations": "Total number of published position-angle/separation measurements for this pair",
    "position_angle_first": "Position angle of secondary relative to primary at epoch of first observation (degrees, 0-359, measured East from North); change over time may reveal orbital motion",
    "position_angle_last": "Position angle at epoch of last observation (degrees, 0-359); compare with position_angle_first to detect orbital motion",
    "separation_first_arcsec": "Angular separation between primary and secondary at first observation (arcseconds); decreasing separation may indicate an inclined orbit",
    "separation_last_arcsec": "Angular separation at last observation (arcseconds); null if only one observation exists",
    "magnitude_primary": "Visual (V-band) magnitude of the primary star; null if not measured",
    "magnitude_secondary": "Visual (V-band) magnitude of the secondary star; null if not measured; difference = magnitude contrast",
    "spectral_type": "MK spectral type of the primary component (e.g. 'G2V', 'K0III'); null if not cataloged",
    "discoverer_code": "Standard WDS discoverer code + sequence number (e.g. 'STF2272' = Struve discovery #2272); identifies the original survey or observer",
}

# ── Dataset description ─────────────────────────────────────────────
DESCRIPTION = """\
The Washington Double Star Catalog (WDS) is the world reference catalog for visual double \
and multiple star systems, maintained by the US Naval Observatory.

Double stars are essential for determining stellar masses -- the most fundamental property \
of a star -- and for testing stellar evolution models. The WDS traces its lineage back to \
Sherburne Wesley Burnham's catalog of 1906 and has been continuously maintained at the US \
Naval Observatory for over a century, incorporating astrometric measurements from visual \
micrometry, speckle interferometry, adaptive optics, long-baseline optical interferometry, \
and space-based observations (Hipparcos, Gaia).

The catalog includes both gravitationally bound physical pairs (true binaries) and optical \
doubles -- chance alignments of unrelated stars along the same line of sight. Distinguishing \
between the two requires common proper motion analysis or, ideally, measurement of orbital \
curvature over a sufficient arc of the orbit.

For physical binaries with well-determined orbits, the combination of angular separation, \
orbital period, and parallax yields dynamical masses through Kepler's third law. These \
direct mass measurements are the gold standard for calibrating the mass-luminosity relation \
and testing stellar structure models across spectral types from O-type supergiants to \
late M-dwarfs. The position angle and separation measurements recorded at the first and \
last epochs encode information about orbital motion: systems showing significant changes \
in these quantities over the observing baseline are strong candidates for orbit determination.

The WDS encompasses an enormous diversity of systems, from pairs separated by fractions \
of an arcsecond -- resolvable only by interferometric techniques -- to wide common proper \
motion companions separated by arcminutes or more. Wide binaries (separations > 1000 AU) \
are particularly interesting as probes of the Galactic gravitational potential.
"""


def main():
    print("Fetching Washington Double Star Catalog from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} double star systems")

    # Drop VizieR internal columns
    for col in ["recno"]:
        if col in df.columns:
            df = df.drop(columns=[col])

    df = df.rename(columns={k: v for k, v in RENAME.items() if k in df.columns})

    # Clean string columns
    for col in ["wds_id", "components", "spectral_type", "discoverer_code"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
            )

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    df = df.sort_values("wds_id").reset_index(drop=True)

    # ── Domain-specific stats for README ────────────────────────────
    n = len(df)
    n_with_sep = int(df["separation_last_arcsec"].notna().sum()) if "separation_last_arcsec" in df.columns else 0
    n_with_spectral = int(df["spectral_type"].notna().sum()) if "spectral_type" in df.columns else 0
    obs_span_min = int(df["first_observation_year"].min()) if "first_observation_year" in df.columns else 0
    obs_span_max = int(df["last_observation_year"].max()) if "last_observation_year" in df.columns else 0

    quick_stats = f"""\
- **{n:,}** double/multiple star systems
- Observations spanning **{obs_span_min}** to **{obs_span_max}**
- **{n_with_sep:,}** with measured separation
- **{n_with_spectral:,}** with spectral type"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/wds-double-stars", split="train")
df = ds.to_pandas()

# Systems with large separation change (orbital motion)
has_both = df.dropna(subset=["separation_first_arcsec", "separation_last_arcsec"])
has_both["sep_change"] = abs(has_both["separation_last_arcsec"] - has_both["separation_first_arcsec"])
movers = has_both.nlargest(20, "sep_change")
print(movers[["wds_id", "separation_first_arcsec", "separation_last_arcsec", "sep_change"]])

# Separation distribution
import matplotlib.pyplot as plt
df["separation_last_arcsec"].dropna().clip(upper=100).hist(bins=100)
plt.xlabel("Separation (arcsec)")
plt.ylabel("Count")
plt.title("WDS Angular Separation Distribution")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Washington Double Star Catalog",
        description=DESCRIPTION,
        tags=["space", "double-star", "binary", "wds", "usno", "astrometry",
              "astronomy", "open-data", "tabular-data", "parquet"],
        source_url="https://vizier.cds.unistra.fr/viz-bin/VizieR-3?-source=B/wds/wds",
        task_categories=["tabular-classification", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e000191/GSFC_20171208_Archive_e000191~medium.jpg",
            "alt": "A youthful globular star cluster observed by the Hubble Space Telescope",
            "credit": "NASA/ESA/Hubble",
        },
        related_datasets=[
            "juliensimon/hipparcos-catalog",
            "juliensimon/gcvs-variable-stars",
            "juliensimon/open-star-clusters",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "ra_deg", "dec_deg", "first_observation_year", "last_observation_year",
                "n_observations", "position_angle_first", "position_angle_last",
                "separation_first_arcsec", "separation_last_arcsec",
                "magnitude_primary", "magnitude_secondary",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="wds_double_stars.parquet",
            min_rows=150000,
            expected_columns=["wds_id", "ra_deg", "dec_deg"],
            critical_columns=["wds_id", "ra_deg", "dec_deg"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update WDS double stars: {n:,} systems",
        )
    print("Done.")


if __name__ == "__main__":
    main()
