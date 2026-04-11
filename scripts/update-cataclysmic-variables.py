#!/usr/bin/env python3
"""Fetch Ritter & Kolb Cataclysmic Variable catalog from HEASARC and upload to HF.

Source: Ritter H., Kolb U., 2003, A&A 404, 301 (Edition 7.24)
HEASARC table: rittercv
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import heasarc_query

HF_REPO = "juliensimon/cataclysmic-variable-catalog"

ADQL = "SELECT * FROM rittercv"

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "name": "Standard CV designation (e.g. 'SS Cyg', 'AM Her'); CVs are close binaries where a white dwarf accretes matter from a donor star",
    "ra": "Right ascension ICRS J2000.0 in degrees (0-360)",
    "dec": "Declination ICRS J2000.0 in degrees (-90 to +90)",
    "lii": "Galactic longitude in degrees (0-360, increasing toward Galactic center direction)",
    "bii": "Galactic latitude in degrees (-90 to +90; most CVs within |b| < 30 deg)",
    "class": "CV classification code from Ritter & Kolb catalog (e.g. DN, NL, N, RN, AM, IP)",
    "type2": "Secondary classification flag from Ritter & Kolb (qualifier or additional subtype)",
    "porb": "Orbital period in hours; typical range 1.3-12 h; the 2-3 h 'period gap' reflects disrupted mass transfer",
    "porb2": "Secondary or alternative orbital period solution in hours (null if not applicable)",
    "mag1": "V-band magnitude at outburst maximum (brightest state); lower value = brighter",
    "mag2": "V-band magnitude at quiescence (faint state); difference mag2-mag1 = outburst amplitude",
    "spect1": "MK spectral type of the primary component (accreting white dwarf or disk)",
    "spect2": "MK spectral type of the secondary (donor) star",
    "cv_subtype": "Derived CV subtype: 'dwarf_nova' (DN, recurring outbursts), 'polar' (AM Her, strongly magnetic), 'intermediate_polar' (DQ Her/IP), 'nova_like' (NL, steady high accretion), 'classical_nova' (N/RN, thermonuclear runaway), or 'other'",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Catalog of cataclysmic variables (CVs) from the Ritter & Kolb catalog, sourced from \
NASA HEASARC. CVs are binary star systems where a white dwarf accretes matter from a \
companion star.

Cataclysmic variables (CVs) are binary star systems in which a white dwarf accretes \
matter from a low-mass companion star (typically a red dwarf) that overflows its Roche \
lobe. The infalling material forms an accretion disk around the white dwarf, producing \
dramatic brightness variations across timescales from seconds to decades. CVs are \
classified into several subtypes based on their outburst behavior and magnetic field \
strength:

Dwarf novae (DN) exhibit quasi-periodic outbursts of 2-8 magnitudes caused by thermal \
instabilities in the accretion disk. Classical novae (N) undergo thermonuclear explosions \
on the white dwarf surface when accreted hydrogen reaches a critical mass, brightening by \
6-19 magnitudes. Polars (AM Her) are strongly magnetic white dwarfs (B ~ 10-230 MG) where \
the magnetic field channels accretion directly onto the poles. Intermediate polars (DQ Her) \
are moderately magnetic white dwarfs with a truncated accretion disk. Nova-like variables \
(NL) are high mass-transfer rate systems in a persistent bright state.

The Ritter & Kolb catalog is the standard reference catalog for CV research, containing \
orbital periods, spectral types, magnitudes, and classifications for the known CV \
population. This dataset is essential for population studies, period distribution \
analysis, and understanding the evolution of compact binary systems.
"""


def main():
    print("Fetching Ritter & Kolb CV catalog from HEASARC...")
    df = heasarc_query("rittercv", ADQL)
    print(f"  {len(df):,} cataclysmic variables fetched")

    # Clean empty strings to NaN
    df = df.replace(r"^\s*$", pd.NA, regex=True)

    # Lowercase column names to snake_case
    df.columns = [c.strip().lower() for c in df.columns]

    # Derive CV subtype classification if a type column exists
    type_col = None
    for candidate in ["type", "cv_type", "class", "obj_type", "source_type", "type2"]:
        if candidate in df.columns:
            type_col = candidate
            break

    if type_col:
        def classify_cv(t):
            if pd.isna(t):
                return None
            t_upper = str(t).upper().strip()
            if "DN" in t_upper or "DWARF" in t_upper or "SU" in t_upper or "UG" in t_upper:
                return "dwarf_nova"
            if "AM" in t_upper and "HER" in t_upper:
                return "polar"
            if "DQ" in t_upper and "HER" in t_upper:
                return "intermediate_polar"
            if "IP" in t_upper:
                return "intermediate_polar"
            if t_upper in ("AM", "P", "POLAR"):
                return "polar"
            if "NL" in t_upper or "NOVA-LIKE" in t_upper or "NOVALIKE" in t_upper:
                return "nova_like"
            if "NA" in t_upper or "NB" in t_upper or "NC" in t_upper or "NR" in t_upper:
                return "classical_nova"
            if "N " in t_upper or t_upper == "N":
                return "classical_nova"
            return "other"

        df["cv_subtype"] = df[type_col].apply(classify_cv)
        print(f"  Derived cv_subtype from '{type_col}'")

    # Sort by name
    name_col = None
    for candidate in ["name", "source_name", "object_name", "designation"]:
        if candidate in df.columns:
            name_col = candidate
            break
    if name_col:
        df = df.sort_values(name_col).reset_index(drop=True)

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    has_subtype = "cv_subtype" in df.columns
    if has_subtype:
        subtype_counts = df["cv_subtype"].value_counts()
        subtype_lines = [f"- **{cnt:,}** {st}" for st, cnt in subtype_counts.items()]
        subtype_str = "\n".join(subtype_lines)
    else:
        subtype_str = "- Type classification not available"

    period_col = "porb" if "porb" in df.columns else None
    n_with_period = int(df[period_col].notna().sum()) if period_col else 0
    period_median = df[period_col].median() if period_col and n_with_period > 0 else 0

    quick_stats = f"""\
- **{n_total:,}** cataclysmic variables
- **{n_with_period:,}** systems with measured orbital period (median {period_median:.1f} h)
- CV subtypes:
{subtype_str}"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/cataclysmic-variable-catalog", split="train")
df = ds.to_pandas()

# Filter by CV subtype
dwarf_novae = df[df["cv_subtype"] == "dwarf_nova"]
polars = df[df["cv_subtype"] == "polar"]
print(f"{len(dwarf_novae):,} dwarf novae, {len(polars):,} polars")

# Period distribution showing the famous period gap
import matplotlib.pyplot as plt
periods = df["porb"].dropna()
periods[periods > 0].hist(bins=50)
plt.xlabel("Orbital period (hours)")
plt.ylabel("Count")
plt.title("CV Orbital Period Distribution")
plt.axvspan(2.0, 3.0, alpha=0.2, color="red", label="Period gap")
plt.legend()
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Ritter & Kolb Cataclysmic Variable Catalog",
        description=DESCRIPTION,
        tags=["space", "cataclysmic-variable", "white-dwarf", "nova",
              "dwarf-nova", "binary-star", "astronomy", "accretion",
              "open-data", "tabular-data", "parquet"],
        source_url="https://heasarc.gsfc.nasa.gov/W3Browse/all/rittercv.html",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA03606/PIA03606~small.jpg",
            "alt": "The Crab Nebula, a supernova remnant",
            "credit": "NASA/ESA/Hubble",
        },
        related_datasets=[
            "juliensimon/xray-binary-catalog",
            "juliensimon/gaia-dr3-white-dwarfs",
            "juliensimon/gcvs-variable-stars",
            "juliensimon/kepler-eclipsing-binaries",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=["ra", "dec", "lii", "bii", "porb", "porb2", "mag1", "mag2"],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="cataclysmic_variables.parquet",
            min_rows=1000,
            expected_columns=["name", "ra", "dec"],
            critical_columns=["name", "ra", "dec"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update cataclysmic variable catalog: {n_total:,} CVs",
        )
    print("Done.")


if __name__ == "__main__":
    main()
