#!/usr/bin/env python3
"""Fetch FUSE observation metadata from MAST CAOM TAP and upload to HF.

FUSE (Far Ultraviolet Spectroscopic Explorer) operated 1999–2007 and was
the highest-resolution far-UV spectrograph (905–1187 Å) ever flown. Its
archive covers 5.7K observations across 8 years, dominated by studies of
the interstellar medium, hot white dwarfs, O/B stars, and quasar
absorption-line systems.
"""

import os

import pandas as pd

from hf_dataset_utils import Pipeline
from mast_tap import fetch_observations, load_checkpoint, save_checkpoint

HF_REPO = "juliensimon/fuse-observations"
CHECKPOINT_PATH = os.environ.get("FUSE_CHECKPOINT", "/tmp/fuse_raw.parquet")

COLUMN_DESCRIPTIONS = {
    "obs_id": "FUSE observation identifier (11-char alphanumeric, e.g., 'a0010101000'). Primary key.",
    "proposal_id": "FUSE proposal identifier (e.g., 'A001', 'B234'); cycle-letter + sequence",
    "proposal_pi": "Principal Investigator name (free-form)",
    "target_name": "Target name as provided by the proposer",
    "target_ra": "Target right ascension in decimal degrees (ICRS)",
    "target_dec": "Target declination in decimal degrees (ICRS)",
    "intent": "Observation intent: 'science' or 'calibration'",
    "obstype": "CAOM observation type: 'S' (simple) or 'C' (composite)",
}

DESCRIPTION = """\
The FUSE Observation Catalog indexes every observation obtained by NASA's Far Ultraviolet Spectroscopic Explorer (FUSE), which operated from June 24, 1999 to October 18, 2007. FUSE was uniquely designed to observe the hard-to-reach far-UV band between 905 and 1187 Å, where critical absorption lines from H₂, O VI, and deuterium fall — wavelengths inaccessible to Hubble's instruments. Its four coaligned Rowland-circle spectrographs delivered resolving power R ≈ 20,000, the highest ever achieved in space at these wavelengths.

Each row is one FUSE pointing. The archive totals roughly 5,700 observations — modest in count but extraordinarily high-value because of the unique wavelength coverage. FUSE targets include hot white dwarfs (temperature probes via Lyman series), the diffuse interstellar medium (mapping H₂ and O VI in the Milky Way halo), extragalactic quasars (probing the intergalactic medium via absorption), and early-type stars (stellar winds and mass-loss rates).

This dataset is designed for cross-matching with other UV catalogs (IUE, HST, GALEX), identifying FUSE coverage of any sightline of interest, and as a lookup table for retrieving individual spectra from MAST. It complements the HST, IUE, GALEX, JWST, and Chandra observation catalogs in this collection — FUSE fills the 905–1187 Å band that no other mission in that set covers.

The catalog is derived from MAST's CAOM table `dbo.caomobservation` (collection = 'FUSE'). The archive is static since 2007, so this dataset refreshes quarterly for any late reprocessing or metadata fixes."""


def main():
    print("FUSE Observation Catalog pipeline")

    df = load_checkpoint(CHECKPOINT_PATH)
    if df is None:
        print("  Fetching caomobservation (collection=FUSE)...")
        df = fetch_observations(
            "FUSE",
            columns="observationid, obstype, intent, prpid, prppi, trgname, trgposra, trgposdec",
        )
        save_checkpoint(CHECKPOINT_PATH, df)

    print(f"  observations: {len(df):,}")

    df = df.rename(columns={
        "observationid": "obs_id",
        "prpid": "proposal_id",
        "prppi": "proposal_pi",
        "trgname": "target_name",
        "trgposra": "target_ra",
        "trgposdec": "target_dec",
    })

    df = df.sort_values("obs_id").reset_index(drop=True)

    n_total = len(df)
    unique_targets = df["target_name"].nunique()
    unique_pis = df["proposal_pi"].dropna().nunique()

    quick_stats = f"""\
- **{n_total:,}** FUSE far-UV spectra (1999–2007)
- **{unique_targets:,}** distinct target names
- **{unique_pis:,}** distinct Principal Investigators
- Unique wavelength coverage: **905–1187 Å** (H₂, O VI, deuterium lines)"""

    usage = f"""\
```python
from datasets import load_dataset

ds = load_dataset("{HF_REPO}", split="train")
df = ds.to_pandas()

# Top-observed targets
top = df["target_name"].value_counts().head(20)
print(top)

# Sky distribution
import matplotlib.pyplot as plt
plt.figure(figsize=(12, 6))
plt.scatter(df["target_ra"], df["target_dec"], s=1, alpha=0.5)
plt.xlabel("RA (deg)"); plt.ylabel("Dec (deg)")
plt.gca().invert_xaxis()
plt.title("FUSE target pointings (1999–2007)")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="FUSE Observation Catalog",
        description=DESCRIPTION,
        tags=["space", "fuse", "nasa", "ultraviolet", "far-uv",
              "spectroscopy", "astronomy", "telescope", "open-data",
              "tabular-data", "parquet"],
        source_url="https://archive.stsci.edu/missions-and-data/fuse",
        task_categories=["tabular-classification"],
        update_schedule="Quarterly (1st of Jan/Apr/Jul/Oct at 16:00 UTC) via [GitHub Actions](https://github.com/juliensimon/space-datasets).",
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e002215/GSFC_20171208_Archive_e002215~medium.jpg",
            "alt": "Representative view of the UV sky — FUSE covered the 905–1187 Å band uniquely",
            "credit": "NASA/GSFC",
        },
        related_datasets=[
            "juliensimon/iue-observations",
            "juliensimon/hst-observations",
            "juliensimon/galex-observations",
            "juliensimon/euve-observations",
            "juliensimon/quasar-catalog",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=["target_ra", "target_dec"],
            strings=["obs_id", "proposal_id", "proposal_pi", "target_name",
                     "intent", "obstype"],
        )

        df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

        all_null = [c for c in df.columns if df[c].isna().all()]
        if all_null:
            print(f"  Warning: dropping fully-null columns: {all_null}")
            df = df.drop(columns=all_null)

        p.publish(
            df,
            filename="fuse_observations.parquet",
            min_rows=5_000,
            expected_columns=["obs_id", "target_ra", "target_dec"],
            critical_columns=["obs_id"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update FUSE observations: {n_total:,} observations",
        )
    print("Done.")


if __name__ == "__main__":
    main()
