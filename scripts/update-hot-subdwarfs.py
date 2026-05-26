#!/usr/bin/env python3
"""Fetch the Catalogue of Hot Subdwarf Stars from VizieR and upload to HF.

Source: VizieR III/137 — Kilkenny, Heber & Drilling (1988), 'A catalogue of
spectroscopically identified hot subdwarfs', SAAO Circular 12, 1. Long-standing
reference compilation of B- and O-type subdwarf stars (sdB, sdO) — evolved
helium-burning cores stripped of their hydrogen envelopes that occupy the
'extreme horizontal branch' of the Hertzsprung-Russell diagram.
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/hot-subdwarf-stars"

ADQL = 'SELECT * FROM "III/137/catalog"'

RENAME = {
    "raj2000": "ra",
    "dej2000": "dec",
    "sname": "name",
    "vmag": "v_magnitude",
    "u_vmag": "v_magnitude_uncertainty",
    "r_vmag": "v_magnitude_reference",
    "ci1": "color_index_1",
    "u_ci1": "color_index_1_uncertainty",
    "ci2": "color_index_2",
    "u_ci2": "color_index_2_uncertainty",
    "ci3": "color_index_3",
    "sp": "spectral_type",
    "r_sp": "spectral_type_reference",
    "teff": "effective_temperature_k",
    "u_teff": "effective_temperature_uncertainty_k",
    "l_teff": "effective_temperature_limit",
    "log(g)": "log_g",
    "u_log(g)": "log_g_uncertainty",
    "l_log(g)": "log_g_limit",
    "r_log(g)": "log_g_reference",
    "comment": "comment",
    "nr": "catalog_number",
}

COLUMN_DESCRIPTIONS = {
    "catalog_number": "Sequence number in the Kilkenny-Heber-Drilling catalog; entries 1-N are listed in spectral-type order",
    "ra": "Right ascension (degrees, J2000, 0-360)",
    "dec": "Declination (degrees, J2000, -90 to +90)",
    "name": "Primary star designation (e.g. 'PB 6958', 'PG 0044+097', 'EC 11481-2303'); compiled from the discovery survey",
    "comment": "Free-text remark on the entry (e.g. 'composite spectrum', 'eclipsing binary', alternate identifications)",
    "v_magnitude": "Apparent V-band magnitude (Johnson V); brighter sources have smaller values",
    "v_magnitude_uncertainty": "Uncertainty on V-band magnitude (mag)",
    "v_magnitude_reference": "Bibliographic reference code for the V-band photometry",
    "color_index_1": "Color index 1 (U-B or B-V depending on photometric system; Johnson UBV by default)",
    "color_index_1_uncertainty": "Uncertainty on color index 1",
    "color_index_2": "Color index 2 (typically B-V or Stromgren b-y)",
    "color_index_2_uncertainty": "Uncertainty on color index 2",
    "color_index_3": "Color index 3 (third photometric color, system-dependent)",
    "spectral_type": "Spectral classification (e.g. 'sdB', 'sdO', 'sdB+F'); 'sd' denotes subdwarf; the secondary letter (B or O) marks the underlying spectral class; '+X' suffix indicates a composite spectrum with cool companion of type X",
    "spectral_type_reference": "Bibliographic reference code for the spectral classification",
    "effective_temperature_k": "Effective temperature (Kelvin); sdB stars cluster around 25,000-35,000 K, sdO stars at 40,000-80,000 K",
    "effective_temperature_uncertainty_k": "Uncertainty on effective temperature (Kelvin)",
    "effective_temperature_limit": "Limit flag: '<' = upper limit, '>' = lower limit, blank = measured value",
    "log_g": "Logarithm (base 10) of surface gravity in cgs units (cm/s^2); hot subdwarfs occupy log_g = 5-6, intermediate between main-sequence (4-5) and white dwarfs (7-9)",
    "log_g_uncertainty": "Uncertainty on log_g",
    "log_g_limit": "Limit flag for log_g: '<' = upper limit, '>' = lower limit",
    "log_g_reference": "Bibliographic reference code for the log_g determination",
}

DESCRIPTION = """\
The Catalogue of Hot Subdwarf Stars (Kilkenny, Heber & Drilling 1988), retrieved from \
VizieR III/137. The compendium remains the historical reference for the population of \
spectroscopically identified subdwarf B (sdB) and subdwarf O (sdO) stars — evolved low-mass \
stars that occupy the extreme horizontal branch of the Hertzsprung-Russell diagram.

Hot subdwarfs are believed to be the bare helium-burning cores of red giants that lost almost \
all of their hydrogen envelopes near the tip of the giant branch. The dominant formation \
channel is binary interaction (Roche-lobe overflow or common-envelope ejection), making sdB \
stars a key laboratory for testing binary stellar evolution theory and the origin of single \
hot subdwarfs via mergers. They are also major contributors to the ultraviolet excess (UV \
upturn) observed in elliptical galaxies. Each entry in this catalog records the J2000 sky \
position, primary designation, V-band photometry, color indices, spectral classification, and \
the atmospheric parameters effective temperature and surface gravity (log g) when available.

This dataset complements juliensimon/gaia-dr3-white-dwarfs (the post-AGB end-state into which \
some hot subdwarfs evolve), juliensimon/cataclysmic-variable-catalog and \
juliensimon/xray-binary-catalog (compact binary systems formed by similar evolutionary \
pathways), and juliensimon/brown-dwarf-catalog and juliensimon/cns5-nearby-stars for broader \
stellar-population context.\
"""


def main():
    print("Fetching Hot Subdwarf catalog from VizieR III/137...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} entries fetched")

    df.columns = [c.strip().lower() for c in df.columns]
    # The raw catalog has both `sname` (primary designation) and `name` (secondary
    # survey identifier). Drop the secondary `name` so the rename produces a single
    # `name` column from `sname`.
    if "name" in df.columns and "sname" in df.columns:
        df = df.drop(columns=["name"])
    df = df.rename(columns=RENAME)

    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip().replace(
            {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
        )

    # Spectral-type cleanup — collapse internal whitespace
    if "spectral_type" in df.columns:
        df["spectral_type"] = df["spectral_type"].str.replace(r"\s+", "", regex=True).str.strip()

    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    n_total = len(df)
    n_sdb = int(df["spectral_type"].fillna("").str.startswith("sdB").sum()) if "spectral_type" in df.columns else 0
    n_sdo = int(df["spectral_type"].fillna("").str.startswith("sdO").sum()) if "spectral_type" in df.columns else 0
    n_composite = int(df["spectral_type"].fillna("").str.contains(r"\+", regex=True).sum()) if "spectral_type" in df.columns else 0

    teff_line = ""
    if "effective_temperature_k" in df.columns:
        t = pd.to_numeric(df["effective_temperature_k"], errors="coerce").dropna()
        if len(t):
            teff_line = f"\n- Effective temperatures span **{int(t.min()):,}** to **{int(t.max()):,}** K"

    logg_line = ""
    if "log_g" in df.columns:
        g = pd.to_numeric(df["log_g"], errors="coerce").dropna()
        if len(g):
            logg_line = f"\n- Surface gravities (log g) cluster between **{g.min():.2f}** and **{g.max():.2f}** cgs"

    quick_stats = f"""\
- **{n_total:,}** spectroscopically identified hot subdwarf stars
- **{n_sdb:,}** sdB-type + **{n_sdo:,}** sdO-type entries
- **{n_composite:,}** composite-spectrum binaries (e.g. sdB+F, sdO+K){teff_line}{logg_line}"""

    usage = """\
```python
from datasets import load_dataset
import matplotlib.pyplot as plt

df = load_dataset("juliensimon/hot-subdwarf-stars", split="train").to_pandas()

# Kiel diagram (Teff vs log g) — the standard plane for hot subdwarf analysis
mask = df["effective_temperature_k"].notna() & df["log_g"].notna()
fig, ax = plt.subplots(figsize=(8, 6))
ax.scatter(df.loc[mask, "effective_temperature_k"], df.loc[mask, "log_g"],
           c=df.loc[mask, "v_magnitude"], s=30, cmap="viridis_r")
ax.invert_xaxis()  # hot on the left
ax.invert_yaxis()  # large gravity on the bottom
ax.set_xscale("log")
ax.set_xlabel("Effective temperature (K)")
ax.set_ylabel("log g (cgs)")
ax.set_title("Kiel diagram of hot subdwarfs — sdB cluster vs sdO tail")
plt.tight_layout()
plt.show()

# Spectral-type breakdown
print(df["spectral_type"].value_counts().head(20))
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Hot Subdwarf Star Catalog",
        description=DESCRIPTION,
        tags=["space", "astronomy", "stars", "subdwarfs", "stellar-evolution",
              "extreme-horizontal-branch", "vizier", "open-data",
              "tabular-data", "parquet"],
        source_url="https://cdsarc.cds.unistra.fr/viz-bin/cat/III/137",
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
            "juliensimon/gaia-dr3-white-dwarfs",
            "juliensimon/cataclysmic-variable-catalog",
            "juliensimon/xray-binary-catalog",
            "juliensimon/brown-dwarf-catalog",
            "juliensimon/cns5-nearby-stars",
            "juliensimon/carbon-stars",
        ],
    ) as p:
        df_clean = p.clean(
            df,
            numeric=[
                "catalog_number", "ra", "dec",
                "v_magnitude", "v_magnitude_uncertainty",
                "color_index_1", "color_index_1_uncertainty",
                "color_index_2", "color_index_2_uncertainty",
                "color_index_3",
                "effective_temperature_k", "effective_temperature_uncertainty_k",
                "log_g", "log_g_uncertainty",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df_clean,
            filename="hot_subdwarfs.parquet",
            min_rows=1000,
            expected_columns=["name", "ra", "dec", "spectral_type"],
            critical_columns=["name", "ra", "dec"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Hot Subdwarf catalog: {n_total:,} stars",
        )
    print("Done.")


if __name__ == "__main__":
    main()
