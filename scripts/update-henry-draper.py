#!/usr/bin/env python3
"""Fetch the Henry Draper Catalogue of stellar spectral types from VizieR and upload to HF.

Source: Cannon & Pickering (1918–1924), Harvard Annals — VizieR III/135A/catalog
Static dataset — 272,150 stars with spectral classifications.
"""

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/henry-draper-catalog"

ADQL = 'SELECT * FROM "III/135A/catalog"'

RENAME = {
    "HD": "hd_number",
    "DM": "dm_designation",
    "Ptm": "photo_mag",
    "q_Ptm": "photo_mag_quality",
    "Ptg": "photo_visual_mag",
    "q_Ptg": "photo_visual_mag_quality",
    "SpT": "spectral_type",
    "Int": "intensity_code",
    "Rem": "remarks",
    "_RA_icrs": "ra_deg",
    "_DE_icrs": "dec_deg",
}

DROP_COLS = ["recno", "RAB1900", "DEB1900", "n_Ptm", "n_Ptg"]

COLUMN_DESCRIPTIONS = {
    "hd_number": "Henry Draper Catalogue number (HD 1–272150) — the primary stellar identifier in this catalog",
    "dm_designation": "Durchmusterung identifier (BD, CD, or CP prefix) giving the Bonner/Córdoba/Cape catalog cross-match",
    "photo_mag": "Photographic magnitude (blue-sensitive plates, ~B band equivalent); brighter = lower number",
    "photo_mag_quality": "Quality code for photo_mag: 0=normal, other codes indicate uncertain or combined measurements",
    "photo_visual_mag": "Photovisual magnitude (orthochromatic plates, ~V band equivalent)",
    "photo_visual_mag_quality": "Quality code for photo_visual_mag: 0=normal",
    "spectral_type": "MK spectral type and luminosity class (e.g. G2V, K0III, A3m) — the primary classification product",
    "intensity_code": "Relative intensity indicator (1–6) used during classification; relates to plate exposure",
    "remarks": "Remarks field: note on unusual classification, binary, or catalog flags",
    "ra_deg": "Right ascension (J2000, degrees) — computed by VizieR from B1900 coordinates",
    "dec_deg": "Declination (J2000, degrees) — computed by VizieR from B1900 coordinates",
}

DESCRIPTION = """\
The Henry Draper Catalogue (HD) is the foundational reference for stellar spectral \
classification, containing 272,150 stars with spectral types assigned by Annie Jump \
Cannon at the Harvard College Observatory. Published in the Harvard Annals between \
1918 and 1924, it established the OBAFGKM spectral sequence that remains in use today.

Annie Jump Cannon classified each star visually by examining the pattern of absorption \
lines on photographic plates, working at a rate of about 300 stars per hour. Her \
one-dimensional spectral sequence (O, B, A, F, G, K, M, plus R, N, S for carbon \
and zirconium-rich stars) encodes stellar surface temperature: O stars are the \
hottest (>30,000 K, ionised helium) and M stars the coolest (<3,500 K, molecular \
bands). The HD number (HD 1–272150) became the universal stellar identifier \
used in astrophysical literature throughout the 20th century and remains widely \
cited today.

Stars are classified to the nearest half subtype (e.g., G2V for the Sun). The \
luminosity class suffix — Ia (supergiant), II (bright giant), III (giant), IV \
(subgiant), V (main-sequence/dwarf) — was added for stars in the extension \
catalogs. The colour index B–V (photo_mag – photo_visual_mag) provides an \
independent temperature indicator correlated with spectral type, enabling \
photometric classification for very large samples.

This catalogue fills the key gap of stellar spectral types in the collection: \
no other dataset provides canonical MK classifications for a large, all-sky \
stellar sample. It is the natural complement to the Hipparcos parallax catalogue \
(astrometry), the Gaia DR3 datasets (photometry and radial velocities), and the \
GCVS variable star catalogue (variability). It enables HR-diagram studies, \
population synthesis, and training spectral-type classifiers."""

COLLECTION_URL = "https://huggingface.co/collections/juliensimon/stellar-catalogs-69c792b1a52ab2757b0eaa57"


def main():
    print("Fetching Henry Draper Catalogue from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} rows fetched")

    df = df.drop(columns=[c for c in DROP_COLS if c in df.columns])
    df = df.rename(columns=RENAME)

    # Derive broad spectral class from first character of SpT
    df["spectral_class"] = df["spectral_type"].str.strip().str[0].where(
        df["spectral_type"].str.strip().str[0].isin(list("OBAFGKM")), other=None
    )

    COLUMN_DESCRIPTIONS["spectral_class"] = (
        "Broad spectral class (O/B/A/F/G/K/M) extracted from spectral_type; "
        "null for unusual types (W, R, N, S, C)"
    )

    n = len(df)
    class_counts = df["spectral_class"].value_counts()
    top_class = class_counts.index[0]
    top_n = int(class_counts.iloc[0])
    n_classified = int(df["spectral_class"].notna().sum())
    n_with_coords = int(df["ra_deg"].notna().sum())

    quick_stats = f"""\
- **{n:,}** stars with spectral type classifications (HD 1–{df['hd_number'].max():,})
- **{n_classified:,}** with OBAFGKM broad class; most common: {top_class} stars ({top_n:,}, {top_n/n*100:.1f}%)
- Magnitudes span {df['photo_mag'].min():.1f}–{df['photo_mag'].max():.1f} (photographic)
- **{n_with_coords:,}** stars with J2000 coordinates"""

    usage = f"""\
```python
from datasets import load_dataset

ds = load_dataset("{HF_REPO}", split="train")
df = ds.to_pandas()

# Spectral type distribution
import matplotlib.pyplot as plt
order = list("OBAFGKM")
counts = df["spectral_class"].value_counts().reindex(order, fill_value=0)
counts.plot(kind="bar", color="steelblue")
plt.xlabel("Spectral class")
plt.ylabel("Count")
plt.title("Henry Draper Catalogue — spectral class distribution")
plt.show()

# Colour-magnitude diagram (photo_mag vs B-V proxy)
import numpy as np
bv = df["photo_mag"] - df["photo_visual_mag"]
good = df[(df["photo_mag"] < 9) & bv.notna()]
plt.figure(figsize=(7, 8))
plt.scatter(bv[good.index], good["photo_mag"], s=0.3, alpha=0.2)
plt.gca().invert_yaxis()
plt.xlabel("B−V (photo_mag − photo_visual_mag)")
plt.ylabel("Photographic magnitude")
plt.title("HD Catalogue — colour-magnitude diagram")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Henry Draper Catalogue",
        description=DESCRIPTION,
        tags=["space", "stellar", "spectral-classification", "astronomy",
              "henry-draper", "stellar-catalog", "open-data", "tabular-data", "parquet"],
        source_url="https://vizier.cds.unistra.fr/viz-bin/VizieR-3?-source=III/135A/catalog",
        task_categories=["tabular-classification"],
        collection_url=COLLECTION_URL,
        banner={
            "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e000191/GSFC_20171208_Archive_e000191~medium.jpg",
            "alt": "Dense stellar field — the stars classified in the Henry Draper Catalogue",
            "credit": "NASA/ESA/Hubble Heritage",
        },
        related_datasets=[
            "juliensimon/hipparcos-catalog",
            "juliensimon/gaia-dr3-spectroscopic-binaries",
            "juliensimon/bright-stars",
        ],
    ) as p:
        NUMERIC_COLS = [
            "hd_number", "photo_mag", "photo_mag_quality",
            "photo_visual_mag", "photo_visual_mag_quality",
            "intensity_code", "ra_deg", "dec_deg",
        ]
        STRING_COLS = ["dm_designation", "spectral_type", "remarks", "spectral_class"]
        df = p.clean(
            df,
            numeric=NUMERIC_COLS,
            strings=STRING_COLS,
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="henry_draper.parquet",
            min_rows=270_000,
            expected_columns=["hd_number", "spectral_type", "ra_deg", "dec_deg"],
            critical_columns=["hd_number", "spectral_type"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Upload Henry Draper Catalogue: {n:,} stellar spectral types",
        )
    print("Done.")


if __name__ == "__main__":
    main()
