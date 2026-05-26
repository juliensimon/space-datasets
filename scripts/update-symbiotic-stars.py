#!/usr/bin/env python3
"""Fetch the Belczynski symbiotic stars catalog from VizieR.

Source: VizieR J/A+AS/146/407/catalog — Belczynski, K., Mikolajewska, J.,
Munari, U., Ivison, R.J., Friedjung, M. (2000), A&AS 146, 407,
'A catalogue of symbiotic stars'. Reference compilation of 218 confirmed
and suspected symbiotic stars — interacting binaries combining a cool
giant donor and a hot compact accretor (typically a white dwarf).
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/symbiotic-stars-catalog"

ADQL = 'SELECT * FROM "J/A+AS/146/407/catalog"'

RENAME = {
    "raj2000": "ra",
    "dej2000": "dec",
    "glon": "galactic_longitude",
    "glat": "galactic_latitude",
    "[bmm2000]": "bmm2000_id",
    "n_[bmm2000]": "bmm2000_note",
    "vmag": "v_magnitude",
    "l_vmag": "v_magnitude_limit",
    "u_vmag": "v_magnitude_uncertainty_flag",
    "kmag": "k_magnitude",
    "l_kmag": "k_magnitude_limit",
    "ir": "infrared_type",
    "iue": "iue_observed",
    "x": "x_ray_detection",
    "u_x": "x_ray_uncertainty_flag",
    "imax": "outburst_amplitude_mag",
    "u_imax": "outburst_amplitude_uncertainty_flag",
}

COLUMN_DESCRIPTIONS = {
    "bmm2000_id": "Sequential identifier in the Belczynski-Mikolajewska-Munari-Friedjung 2000 compilation (e.g. '001', '002')",
    "bmm2000_note": "Annotation flag on the BMM2000 identifier (rare)",
    "name": "Primary star designation (e.g. 'SMC1', 'AG Peg', 'Z And'); resolves to SIMBAD",
    "ra": "Right ascension (degrees, J2000, 0-360)",
    "dec": "Declination (degrees, J2000, -90 to +90)",
    "galactic_longitude": "Galactic longitude (degrees, 0-360)",
    "galactic_latitude": "Galactic latitude (degrees, -90 to +90)",
    "v_magnitude_limit": "Limit flag on V magnitude: '<' = upper limit, '>' = lower limit, blank = direct measurement",
    "v_magnitude": "Apparent V-band magnitude in quiescence (mag); brighter sources have smaller values",
    "v_magnitude_uncertainty_flag": "Uncertainty/quality flag for the V magnitude",
    "k_magnitude_limit": "Limit flag for K-band magnitude (same convention as v_magnitude_limit)",
    "k_magnitude": "Apparent K-band (2.2 um) magnitude in quiescence (mag); samples the cool-giant donor",
    "infrared_type": "Infrared spectral type classification of the cool donor: 'S' = S-type (stellar, no dust), 'D' = D-type (dusty, Mira variable), 'D'' = intermediate; appended ':' marks uncertain class",
    "iue_observed": "IUE ultraviolet spectrum availability flag: '+' = observed by IUE, blank = not observed",
    "x_ray_detection": "X-ray detection flag: '+' = detected, '-' = upper limit, blank = unobserved; symbiotic X-ray emission comes from accretion onto the white dwarf",
    "x_ray_uncertainty_flag": "Uncertainty flag for the X-ray detection",
    "outburst_amplitude_mag": "Maximum observed outburst amplitude (magnitudes); symbiotic novae outbursts can exceed 5 magnitudes",
    "outburst_amplitude_uncertainty_flag": "Uncertainty flag for the outburst amplitude",
}

DESCRIPTION = """\
The Belczynski-Mikolajewska-Munari-Ivison-Friedjung catalog of symbiotic stars (VizieR \
J/A+AS/146/407, A&AS 146, 407, 2000) — the reference compilation of 218 confirmed and \
suspected symbiotic stars.

Symbiotic stars are interacting binary systems where a cool giant (typically an M-type Mira \
or red giant) loses mass to a hot compact accretor (almost always a white dwarf, occasionally \
a neutron star). The strong color contrast between the cool donor and the hot \
accretion/nebular component produces a distinctive composite spectrum with both molecular \
absorption bands and high-excitation emission lines. Symbiotics are central to several open \
questions in stellar astrophysics: as candidate Type Ia supernova progenitors (white dwarf \
mass growth via stable hydrogen burning), as testbeds for binary mass transfer in wide orbits, \
and as the dominant population of recurrent novae.

Each row records the BMM2000 identifier, primary designation, J2000 sky position, Galactic \
coordinates, V and K magnitudes in quiescence, infrared spectral type of the donor (S, D, or \
D'), and detection flags for IUE ultraviolet spectroscopy and X-ray observations along with \
the maximum observed outburst amplitude.

Use this dataset alongside juliensimon/cataclysmic-variable-catalog (closely-related \
short-period white dwarf binaries), juliensimon/galactic-novae-schaefer (the recurrent-nova \
overlap class), juliensimon/aavso-vsx-variable-stars (ongoing photometry of symbiotic \
outbursts), juliensimon/gaia-dr3-white-dwarfs (the accretor population), and \
juliensimon/xray-binary-catalog (the X-ray-bright symbiotic subset).\
"""


def main():
    print("Fetching Belczynski symbiotic stars catalog from VizieR J/A+AS/146/407...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} symbiotic stars fetched")

    df.columns = [c.strip().lower() for c in df.columns]
    df = df.rename(columns=RENAME)

    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip().replace(
            {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
        )

    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    n_total = len(df)
    n_iue = int((df["iue_observed"] == "+").sum()) if "iue_observed" in df.columns else 0
    n_xray = int((df["x_ray_detection"] == "+").sum()) if "x_ray_detection" in df.columns else 0

    ir_breakdown = ""
    if "infrared_type" in df.columns:
        ir_clean = df["infrared_type"].fillna("").str.strip().str.rstrip(":")
        top = ir_clean.replace("", pd.NA).dropna().value_counts().head(5)
        ir_breakdown = "\n- Infrared donor classes: " + ", ".join(
            f"**{t}** ({n})" for t, n in top.items()
        )

    v_line = ""
    if "v_magnitude" in df.columns:
        v = pd.to_numeric(df["v_magnitude"], errors="coerce").dropna()
        if len(v):
            v_line = f"\n- Quiescent V magnitudes span **{v.min():.1f}** to **{v.max():.1f}** mag"

    quick_stats = f"""\
- **{n_total}** confirmed + suspected symbiotic stars in the canonical Belczynski 2000 compilation
- **{n_iue}** observed with IUE in the ultraviolet; **{n_xray}** detected in X-rays{ir_breakdown}{v_line}"""

    usage = """\
```python
from datasets import load_dataset
import matplotlib.pyplot as plt
import numpy as np

df = load_dataset("juliensimon/symbiotic-stars-catalog", split="train").to_pandas()

# Galactic distribution — symbiotics trace bulge and disk populations
mask = df["galactic_longitude"].notna() & df["galactic_latitude"].notna()
fig, ax = plt.subplots(figsize=(10, 5), subplot_kw={"projection": "mollweide"})
glon = np.radians(np.where(df.loc[mask, "galactic_longitude"] > 180,
                            df.loc[mask, "galactic_longitude"] - 360,
                            df.loc[mask, "galactic_longitude"]))
glat = np.radians(df.loc[mask, "galactic_latitude"])
ax.scatter(-glon, glat, s=12, alpha=0.7)
ax.grid(True)
ax.set_title("Galactic distribution of symbiotic stars (Belczynski+ 2000)")
plt.tight_layout()
plt.show()

# Infrared-type breakdown — S vs D-type donors
print(df["infrared_type"].value_counts().head(10))
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Symbiotic Stars Catalog (Belczynski 2000)",
        description=DESCRIPTION,
        tags=["space", "astronomy", "symbiotic-stars", "binary-stars",
              "white-dwarfs", "mira-variables", "stellar-evolution", "vizier",
              "open-data", "tabular-data", "parquet"],
        source_url="https://cdsarc.cds.unistra.fr/viz-bin/cat/J/A+AS/146/407",
        license="other",
        license_name="vizier-scientific-use",
        license_link="https://cds.unistra.fr/vizier-org/licences_vizier.html",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/stellar-catalogs-69c792b1a52ab2757b0eaa57",
        banner={
            "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e000191/GSFC_20171208_Archive_e000191~medium.jpg",
            "alt": "A youthful globular star cluster observed by the Hubble Space Telescope",
            "credit": "NASA/ESA/Hubble",
        },
        related_datasets=[
            "juliensimon/cataclysmic-variable-catalog",
            "juliensimon/galactic-novae-schaefer",
            "juliensimon/aavso-vsx-variable-stars",
            "juliensimon/gaia-dr3-white-dwarfs",
            "juliensimon/xray-binary-catalog",
            "juliensimon/hot-subdwarf-stars",
        ],
    ) as p:
        df_clean = p.clean(
            df,
            numeric=[
                "ra", "dec", "galactic_longitude", "galactic_latitude",
                "v_magnitude", "k_magnitude", "outburst_amplitude_mag",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df_clean,
            filename="symbiotic_stars.parquet",
            min_rows=150,
            expected_columns=["name", "ra", "dec"],
            critical_columns=["name", "ra", "dec"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update symbiotic stars catalog: {n_total} entries",
        )
    print("Done.")


if __name__ == "__main__":
    main()
