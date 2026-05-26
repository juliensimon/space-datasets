#!/usr/bin/env python3
"""Fetch the Veron-Cetty & Veron 13th edition Quasar/AGN catalog from VizieR.

Source: VizieR VII/258/vv10 — Veron-Cetty, M.-P., Veron, P. (2010),
A&A 518, A10, 'A catalogue of quasars and active nuclei: 13th edition'.
Long-standing reference compilation of every published quasar and active
galactic nucleus through 2010, with positions, redshifts, photometry,
spectral classifications, and radio fluxes. Still the canonical AGN
look-up table for cross-matching and population statistics.
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/veron-agn-quasar-catalog"

ADQL = 'SELECT * FROM "VII/258/vv10"'

RENAME = {
    "raj2000": "ra",
    "dej2000": "dec",
    "cl": "object_class",
    "nr": "radio_flag",
    "n_name": "name_note",
    "n_raj2000": "position_origin",
    "name": "name",
    "f6cm": "flux_6cm_mjy",
    "r_f6cm": "flux_6cm_reference",
    "f20cm": "flux_20cm_mjy",
    "r_f20cm": "flux_20cm_reference",
    "l_z": "redshift_limit",
    "z": "redshift",
    "r_z": "redshift_reference",
    "sp": "spectral_classification",
    "n_vmag": "magnitude_band",
    "vmag": "apparent_magnitude",
    "b-v": "color_bv",
    "u-b": "color_ub",
    "mabs": "absolute_magnitude",
    "fc": "finding_chart_reference",
    "r_vmag": "magnitude_reference",
}

COLUMN_DESCRIPTIONS = {
    "object_class": "Object classification: 'Q' = quasar (M_abs <= -23, brighter than -23), 'A' = AGN (M_abs > -23, fainter), 'B' = BL Lac object",
    "radio_flag": "Radio-detection flag: '*' = detected at radio frequencies, blank = not detected (or no radio coverage)",
    "name": "Primary designation (catalog and survey ID), typically 'SDSS Jhhmm+ddmm', '4C+nn.nn', 'PG hhmm+ddd', etc.",
    "name_note": "Name annotation flag (rare)",
    "position_origin": "Origin code for the J2000 coordinates: 'O' = optical position, 'R' = radio position, 'X' = X-ray, etc.",
    "ra": "Right ascension (degrees, J2000)",
    "dec": "Declination (degrees, J2000)",
    "flux_6cm_mjy": "Radio flux density at 6 cm (4.85 GHz) in mJy where detected; blank otherwise",
    "flux_6cm_reference": "Bibliographic reference code for the 6 cm flux measurement",
    "flux_20cm_mjy": "Radio flux density at 20 cm (1.4 GHz) in mJy where detected",
    "flux_20cm_reference": "Bibliographic reference code for the 20 cm flux measurement",
    "redshift_limit": "Limit flag on redshift: '<' = upper limit, '>' = lower limit, blank = direct measurement",
    "redshift": "Spectroscopic or photometric redshift z (dimensionless); range ~0 to ~7 in this compilation",
    "redshift_reference": "Bibliographic reference code for the redshift",
    "spectral_classification": "Spectral subclass code: 'S1' = Seyfert 1, 'S2' = Seyfert 2, 'S1.5'/'S1.9' = intermediate types, 'NLAGN' = narrow-line AGN, 'HP' = high polarization, 'LINER' = LINER, blank = standard QSO",
    "magnitude_band": "Photometric system letter for the magnitude: 'V' = Johnson V, 'B' = blue, 'R' = red, 'g' = SDSS g, etc.",
    "apparent_magnitude": "Apparent magnitude in the band identified by magnitude_band; brighter sources have smaller values",
    "color_bv": "Johnson B-V color index (mag); positive values indicate redder colors",
    "color_ub": "Johnson U-B color index (mag); the 'UV excess' (negative U-B) is the historical AGN selection signature",
    "absolute_magnitude": "Absolute V magnitude M_V (mag); the Q/A class boundary is M_V = -23. Computed assuming H_0 = 71, Omega_M = 0.27, Omega_lambda = 0.73",
    "finding_chart_reference": "Bibliographic reference code for a published finding chart of the source",
    "magnitude_reference": "Bibliographic reference code for the magnitude measurement",
}

DESCRIPTION = """\
The Veron-Cetty & Veron Quasars and Active Nuclei catalog, 13th edition (VizieR VII/258) — \
the canonical reference compilation of 168,940 quasars and active galactic nuclei published \
through 2010, covering optical/UV-selected quasars, X-ray-selected AGN, radio galaxies, and \
BL Lac objects.

The catalog merges every published QSO and AGN identification with a homogeneous position, \
spectroscopic redshift, optical photometry, B-V and U-B colors, absolute magnitude, and \
(where available) radio fluxes at 6 cm and 20 cm. It remains the standard look-up source for \
cross-matching unidentified sources against the established AGN population, for selecting \
training/test samples by spectral subclass (Seyfert 1, Seyfert 2, LINER, BL Lac), and for \
population statistics in redshift, luminosity, and color spaces.

Object class column conventions: 'Q' marks quasars (M_V <= -23, brighter than the historical \
QSO/AGN boundary), 'A' marks lower-luminosity AGN (M_V > -23), and 'B' marks BL Lac objects. \
The spectral classification column captures Seyfert sub-type and special spectral phenomena. \
Use this dataset alongside juliensimon/milliquas (the more recent Million Quasars Catalog \
that supersedes Veron for survey-era discoveries), juliensimon/gaia-dr3-qso-candidates \
(Gaia-selected QSOs), juliensimon/black-hole-catalog, juliensimon/4xmm-dr14-xray-sources, \
and juliensimon/icrf3-reference-frame for AGN cross-mission analysis.\
"""


def main():
    print("Fetching Veron 13th-edition AGN catalog from VizieR VII/258...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} sources fetched")

    df.columns = [c.strip().lower() for c in df.columns]
    df = df.rename(columns=RENAME)

    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip().replace(
            {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
        )

    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    n_total = len(df)
    n_q = int((df["object_class"] == "Q").sum()) if "object_class" in df.columns else 0
    n_a = int((df["object_class"] == "A").sum()) if "object_class" in df.columns else 0
    n_b = int((df["object_class"] == "B").sum()) if "object_class" in df.columns else 0
    n_radio = int((df["radio_flag"] == "*").sum()) if "radio_flag" in df.columns else 0

    z_line = ""
    if "redshift" in df.columns:
        z = pd.to_numeric(df["redshift"], errors="coerce").dropna()
        if len(z):
            z_line = f"\n- Redshift range: **{z.min():.2f}** to **{z.max():.2f}** (median {z.median():.2f})"

    mabs_line = ""
    if "absolute_magnitude" in df.columns:
        m = pd.to_numeric(df["absolute_magnitude"], errors="coerce").dropna()
        if len(m):
            mabs_line = f"\n- Absolute magnitude (M_V): **{m.min():.1f}** (most luminous) to **{m.max():.1f}** (faintest)"

    quick_stats = f"""\
- **{n_total:,}** quasars + AGN + BL Lac objects in the canonical compilation
- **{n_q:,}** quasars (M_V <= -23) + **{n_a:,}** lower-luminosity AGN + **{n_b:,}** BL Lac objects
- **{n_radio:,}** sources with detected radio counterparts (6cm or 20cm){z_line}{mabs_line}"""

    usage = """\
```python
from datasets import load_dataset
import matplotlib.pyplot as plt
import numpy as np

df = load_dataset("juliensimon/veron-agn-quasar-catalog", split="train").to_pandas()

# Hubble diagram: absolute magnitude vs redshift, colored by class
mask = df["redshift"].notna() & df["absolute_magnitude"].notna()
fig, ax = plt.subplots(figsize=(10, 6))
for cls, color in zip(["Q", "A", "B"], ["blue", "orange", "red"]):
    sub = df[mask & (df["object_class"] == cls)]
    ax.scatter(sub["redshift"], sub["absolute_magnitude"], s=2, alpha=0.3, color=color, label=cls)
ax.axhline(-23, color="grey", linestyle="--", label="QSO/AGN boundary")
ax.invert_yaxis()  # brighter = up
ax.set_xscale("log")
ax.set_xlabel("Redshift z")
ax.set_ylabel("Absolute V magnitude")
ax.legend()
plt.tight_layout()
plt.show()

# Seyfert sub-type breakdown
print(df["spectral_classification"].value_counts().head(15))
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Veron-Cetty AGN/Quasar Catalog (13th edition)",
        description=DESCRIPTION,
        tags=["space", "astronomy", "agn", "quasars", "active-galactic-nuclei",
              "seyfert", "blazars", "bl-lac", "vizier", "open-data",
              "tabular-data", "parquet"],
        source_url="https://cdsarc.cds.unistra.fr/viz-bin/cat/VII/258",
        license="other",
        license_name="vizier-scientific-use",
        license_link="https://cds.unistra.fr/vizier-org/licences_vizier.html",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/galaxies-and-cosmology-69c792b117242a3b236df55d",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA22085/PIA22085~small.jpg",
            "alt": "Artist concept of a supermassive black hole with a relativistic jet — AGN engine",
            "credit": "NASA/JPL-Caltech",
        },
        related_datasets=[
            "juliensimon/milliquas",
            "juliensimon/gaia-dr3-qso-candidates",
            "juliensimon/black-hole-catalog",
            "juliensimon/4xmm-dr14-xray-sources",
            "juliensimon/icrf3-reference-frame",
            "juliensimon/roma-bzcat-blazars",
        ],
    ) as p:
        df_clean = p.clean(
            df,
            numeric=[
                "ra", "dec",
                "flux_6cm_mjy", "flux_20cm_mjy",
                "redshift", "apparent_magnitude",
                "color_bv", "color_ub", "absolute_magnitude",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df_clean,
            filename="veron_agn_catalog.parquet",
            min_rows=150_000,
            expected_columns=["name", "ra", "dec", "redshift", "object_class"],
            critical_columns=["name", "ra", "dec"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Veron AGN/quasar catalog: {n_total:,} sources",
        )
    print("Done.")


if __name__ == "__main__":
    main()
