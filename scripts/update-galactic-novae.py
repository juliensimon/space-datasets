#!/usr/bin/env python3
"""Fetch Schaefer's compilation of Galactic novae from VizieR and upload to HF.

Source: VizieR J/MNRAS/517/6150/table3 — Schaefer, B.E. (2022), MNRAS 517, 6150.
'The distances to Galactic classical novae' compiles V_peak (peak apparent
visual magnitude at outburst) and reddening E(B-V) for ~400 Galactic classical
novae from the literature, then derives peak absolute magnitude (M_peak) using
multiple independent distance estimators.
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/galactic-novae-schaefer"

ADQL = 'SELECT * FROM "J/MNRAS/517/6150/table3"'

RENAME = {
    "_ra": "ra",
    "_de": "dec",
    "nova": "name",
    "l_vpeak": "vpeak_limit",
    "vpeak": "v_peak_magnitude",
    "e_vpeak": "v_peak_magnitude_uncertainty",
    "e(b-v)": "ebv",
    "e_e(b-v)": "ebv_uncertainty",
    "l_dmpeak": "dmpeak_limit",
    "dmpeak": "distance_modulus_peak",
    "e_dmpeak": "distance_modulus_peak_uncertainty",
    "simbadname": "simbad_name",
}

COLUMN_DESCRIPTIONS = {
    "name": "Variable-star designation of the nova (Bayer-Argelander convention, e.g. 'OS And', 'CI Aql', 'V603 Aql'); resolves to SIMBAD",
    "ra": "Right ascension (degrees, J2000); transcribed from SIMBAD via VizieR",
    "dec": "Declination (degrees, J2000); transcribed from SIMBAD via VizieR",
    "vpeak_limit": "Limit flag for the peak V magnitude: '<' = fainter than this value (upper limit), '>' = brighter than this value (lower limit), blank = direct measurement",
    "v_peak_magnitude": "Peak apparent visual magnitude at outburst (mag); smaller values are brighter; classical novae typically peak between V = 2 and V = 12 depending on distance and reddening",
    "v_peak_magnitude_uncertainty": "Uncertainty on V_peak (mag); reflects spread across published photometry compilations",
    "ebv": "Interstellar reddening E(B-V) (mag); larger values indicate heavier dust absorption; the V-band extinction is roughly A_V = 3.1 x E(B-V)",
    "ebv_uncertainty": "Uncertainty on E(B-V) (mag)",
    "dmpeak_limit": "Limit flag on the peak distance modulus, same convention as vpeak_limit",
    "distance_modulus_peak": "Apparent distance modulus at peak (mag); equal to V_peak - M_peak - A_V; used to derive heliocentric distance via d = 10^((mu+5)/5) parsecs after reddening correction",
    "distance_modulus_peak_uncertainty": "Uncertainty on the peak distance modulus (mag)",
    "simbad_name": "Canonical SIMBAD identifier for cross-matching (usually identical to `name` but occasionally a longer alias)",
}

DESCRIPTION = """\
Schaefer's compendium of Galactic classical novae — VizieR J/MNRAS/517/6150 from Schaefer, \
B.E. (2022), MNRAS 517, 6150, 'The distances to Galactic classical novae'.

Classical novae are thermonuclear runaways on the surface of a white dwarf accreting hydrogen \
from a close binary companion, producing brightening of 8-15 magnitudes in days and a slow \
photometric decline lasting weeks to months. They are central to several open questions in \
astrophysics: as candidate progenitors of Type Ia supernovae, as contributors to the \
chemical enrichment of the interstellar medium with CNO-cycle isotopes, and as testbeds for \
binary-star evolution and degenerate-matter physics. Schaefer's paper standardized the \
literature compilation of two key observables for every recorded Galactic nova: V_peak (peak \
apparent visual magnitude at outburst) and the interstellar reddening E(B-V) along the line \
of sight, then combined them with multiple independent distance indicators to derive a \
homogeneous peak-distance-modulus catalog.

Each row in this dataset records one Galactic nova with its variable-star designation, J2000 \
sky position from SIMBAD, peak V magnitude and reddening from Schaefer's literature collation, \
and the corresponding peak distance modulus. Use this dataset alongside \
juliensimon/cataclysmic-variable-catalog for the broader CV parent population, \
juliensimon/aavso-vsx-variable-stars for ongoing time-domain photometry, \
juliensimon/open-supernova-catalog for the closely related thermonuclear-explosion population, \
and juliensimon/hot-subdwarf-stars for an alternative end state of binary-stripped stellar \
evolution.\
"""


def main():
    print("Fetching Schaefer Galactic novae catalog from VizieR J/MNRAS/517/6150...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} novae fetched")

    df.columns = [c.strip().lower() for c in df.columns]
    df = df.rename(columns=RENAME)

    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip().replace(
            {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
        )

    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    n_total = len(df)

    vp = pd.to_numeric(df["v_peak_magnitude"], errors="coerce").dropna() if "v_peak_magnitude" in df.columns else pd.Series(dtype=float)
    ebv = pd.to_numeric(df["ebv"], errors="coerce").dropna() if "ebv" in df.columns else pd.Series(dtype=float)
    dm = pd.to_numeric(df["distance_modulus_peak"], errors="coerce").dropna() if "distance_modulus_peak" in df.columns else pd.Series(dtype=float)

    bright_line = f"\n- Peak apparent magnitudes (V_peak) span **{vp.min():.1f}** to **{vp.max():.1f}** mag" if len(vp) else ""
    reddening_line = f"\n- Interstellar reddening E(B-V) ranges from **{ebv.min():.2f}** to **{ebv.max():.2f}** mag — many novae lie behind heavy Galactic dust" if len(ebv) else ""
    distance_line = f"\n- Distance moduli at peak: **{dm.min():.1f}** to **{dm.max():.1f}** mag (heliocentric distances ~0.3 to ~30 kpc)" if len(dm) else ""

    quick_stats = f"""\
- **{n_total}** Galactic classical novae with literature-compiled photometry and reddening
- Homogeneous peak-magnitude catalog spanning over a century of recorded outbursts{bright_line}{reddening_line}{distance_line}"""

    usage = """\
```python
from datasets import load_dataset
import matplotlib.pyplot as plt
import numpy as np

df = load_dataset("juliensimon/galactic-novae-schaefer", split="train").to_pandas()

# Reddening vs distance modulus — heavy dust traces Galactic plane novae
mask = df["ebv"].notna() & df["distance_modulus_peak"].notna()
fig, ax = plt.subplots(figsize=(8, 6))
ax.scatter(df.loc[mask, "distance_modulus_peak"], df.loc[mask, "ebv"],
           s=30, alpha=0.7)
ax.set_xlabel("Distance modulus at peak (mag)")
ax.set_ylabel("E(B-V) reddening (mag)")
ax.set_title("Galactic novae: reddening grows with distance through the disk")
plt.tight_layout()
plt.show()

# Derive heliocentric distance from distance modulus, correcting for extinction
dist_pc = 10 ** ((df["distance_modulus_peak"] - 3.1 * df["ebv"] + 5) / 5)
print(f"Median heliocentric distance: {np.nanmedian(dist_pc) / 1000:.1f} kpc")
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Galactic Classical Novae (Schaefer 2022)",
        description=DESCRIPTION,
        tags=["space", "astronomy", "novae", "classical-novae", "variable-stars",
              "binary-stars", "white-dwarfs", "stellar-evolution", "vizier",
              "open-data", "tabular-data", "parquet"],
        source_url="https://cdsarc.cds.unistra.fr/viz-bin/cat/J/MNRAS/517/6150",
        license="other",
        license_name="vizier-scientific-use",
        license_link="https://cds.unistra.fr/vizier-org/licences_vizier.html",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/variable-stars-and-transients-69c792b1dd7a45812c5a9b36",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA03606/PIA03606~small.jpg",
            "alt": "Crab Nebula — Type II supernova remnant, related transient class",
            "credit": "NASA/ESA/Hubble",
        },
        related_datasets=[
            "juliensimon/cataclysmic-variable-catalog",
            "juliensimon/aavso-vsx-variable-stars",
            "juliensimon/open-supernova-catalog",
            "juliensimon/hot-subdwarf-stars",
            "juliensimon/gaia-dr3-white-dwarfs",
            "juliensimon/pantheon-plus-sne-ia",
        ],
    ) as p:
        df_clean = p.clean(
            df,
            numeric=[
                "ra", "dec",
                "v_peak_magnitude", "v_peak_magnitude_uncertainty",
                "ebv", "ebv_uncertainty",
                "distance_modulus_peak", "distance_modulus_peak_uncertainty",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df_clean,
            filename="galactic_novae.parquet",
            min_rows=300,
            expected_columns=["name", "v_peak_magnitude", "ebv"],
            critical_columns=["name"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Galactic novae (Schaefer 2022): {n_total} entries",
        )
    print("Done.")


if __name__ == "__main__":
    main()
