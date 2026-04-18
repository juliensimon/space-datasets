#!/usr/bin/env python3
"""Fetch EUVE observation metadata from MAST CAOM TAP and upload to HF.

EUVE (Extreme Ultraviolet Explorer) operated 1992–2001 and was the only
dedicated space mission to survey the extreme UV (70–760 Å / ~10–170 eV).
Its 1,367 archive observations include the first all-sky EUV survey, hot
white dwarf atmospheres, coronal emission from nearby stars, and flaring
M dwarfs — many of which remain the only EUV data ever obtained for
those targets.
"""

import os

import pandas as pd

from hf_dataset_utils import Pipeline
from mast_tap import fetch_observations, load_checkpoint, save_checkpoint

HF_REPO = "juliensimon/euve-observations"
CHECKPOINT_PATH = os.environ.get("EUVE_CHECKPOINT", "/tmp/euve_raw.parquet")

COLUMN_DESCRIPTIONS = {
    "obs_id": "EUVE observation identifier (e.g., '1136_1551__9812251330N'); encodes target designation and observation start timestamp. Primary key.",
    "target_name": "Target name as provided by the proposer — often a catalog designation (EUVE, 1ES, PG, HD, etc.)",
    "target_ra": "Target right ascension in decimal degrees (ICRS)",
    "target_dec": "Target declination in decimal degrees (ICRS)",
    "intent": "Observation intent: 'science' or 'calibration'",
    "obstype": "CAOM observation type: 'S' (simple) or 'C' (composite)",
}

DESCRIPTION = """\
The EUVE Observation Catalog indexes every observation obtained by NASA's Extreme Ultraviolet Explorer (EUVE), which operated from June 7, 1992 to January 31, 2001. EUVE was the only dedicated space mission ever flown to survey the extreme UV band (70–760 Å, roughly 10–170 eV) — a region of the electromagnetic spectrum dominated by absorption from the interstellar medium and only reachable after the Voyager UV spectrometers hinted at the possibilities. EUVE combined an all-sky scanner (four telescopes with 100–740 Å coverage) with a deep-survey instrument and a long-wavelength spectrometer (DS/S).

Each row is one EUVE pointing. The 1,367 observations in the archive are small in count but scientifically unique: EUVE produced the first and still only EUV all-sky catalog (>700 sources), it characterised the atmospheres of hot DA white dwarfs that are opaque at other UV wavelengths, it mapped the coronal emission of nearby cool stars (detecting X-ray/EUV flares on M dwarfs in real time), and it observed the flickering interstellar medium absorption toward more than a hundred bright UV sources.

This dataset is designed for cross-matching any bright target with its (possibly only-ever) EUV coverage, for teaching the history of space-UV astronomy, and for identifying EUV sources to revisit with future missions (no current mission covers this band). It complements the IUE, FUSE, GALEX, HST, and JWST observation catalogs in this collection — EUVE extends the UV archive downward in wavelength to the edge of the X-ray band.

The catalog is derived from MAST's CAOM table `dbo.caomobservation` (collection = 'EUVE'). The archive is static since 2001, so this dataset refreshes quarterly for any late reprocessing or metadata fixes."""


def main():
    print("EUVE Observation Catalog pipeline")

    df = load_checkpoint(CHECKPOINT_PATH)
    if df is None:
        print("  Fetching caomobservation (collection=EUVE)...")
        df = fetch_observations(
            "EUVE",
            columns="observationid, obstype, intent, trgname, trgposra, trgposdec",
        )
        save_checkpoint(CHECKPOINT_PATH, df)

    print(f"  observations: {len(df):,}")

    df = df.rename(columns={
        "observationid": "obs_id",
        "trgname": "target_name",
        "trgposra": "target_ra",
        "trgposdec": "target_dec",
    })

    df = df.sort_values("obs_id").reset_index(drop=True)

    n_total = len(df)
    unique_targets = df["target_name"].nunique()

    quick_stats = f"""\
- **{n_total:,}** EUVE observations (1992–2001)
- **{unique_targets:,}** distinct target names
- Unique wavelength coverage: **70–760 Å** (extreme UV — no current mission covers this band)"""

    usage = f"""\
```python
from datasets import load_dataset

ds = load_dataset("{HF_REPO}", split="train")
df = ds.to_pandas()

# Most-observed EUVE targets
print(df["target_name"].value_counts().head(15))

# All-sky EUV pointings
import matplotlib.pyplot as plt
plt.figure(figsize=(12, 6))
plt.scatter(df["target_ra"], df["target_dec"], s=4, alpha=0.6)
plt.xlabel("RA (deg)"); plt.ylabel("Dec (deg)")
plt.gca().invert_xaxis()
plt.title("EUVE pointings (1992–2001)")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="EUVE Observation Catalog",
        description=DESCRIPTION,
        tags=["space", "euve", "nasa", "extreme-uv", "euv",
              "all-sky", "astronomy", "telescope", "open-data",
              "tabular-data", "parquet"],
        source_url="https://archive.stsci.edu/missions-and-data/euve",
        task_categories=["tabular-classification"],
        update_schedule="Quarterly (1st of Jan/Apr/Jul/Oct at 16:30 UTC) via [GitHub Actions](https://github.com/juliensimon/space-datasets).",
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e002215/GSFC_20171208_Archive_e002215~medium.jpg",
            "alt": "The UV-bright sky — EUVE surveyed this with the only extreme-UV observatory ever flown",
            "credit": "NASA/GSFC",
        },
        related_datasets=[
            "juliensimon/fuse-observations",
            "juliensimon/iue-observations",
            "juliensimon/galex-observations",
            "juliensimon/hst-observations",
            "juliensimon/chandra-x-ray-sources",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=["target_ra", "target_dec"],
            strings=["obs_id", "target_name", "intent", "obstype"],
        )

        df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

        all_null = [c for c in df.columns if df[c].isna().all()]
        if all_null:
            print(f"  Warning: dropping fully-null columns: {all_null}")
            df = df.drop(columns=all_null)

        p.publish(
            df,
            filename="euve_observations.parquet",
            min_rows=1_200,
            expected_columns=["obs_id", "target_ra", "target_dec"],
            critical_columns=["obs_id"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update EUVE observations: {n_total:,} observations",
        )
    print("Done.")


if __name__ == "__main__":
    main()
