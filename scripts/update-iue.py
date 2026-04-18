#!/usr/bin/env python3
"""Fetch IUE (International Ultraviolet Explorer) observation metadata and upload to HF.

IUE was a joint NASA/ESA/UK mission operating from 1978 to 1996 — the first
truly operational space UV observatory. Its three cameras (LWP, LWR, SWP)
produced ~100K spectra across 18.7 years, a record for continuous UV
coverage that remains a primary reference archive for UV astronomy.
"""

import os
import re

import pandas as pd

from hf_dataset_utils import Pipeline
from mast_tap import fetch_observations, load_checkpoint, save_checkpoint

HF_REPO = "juliensimon/iue-observations"
CHECKPOINT_PATH = os.environ.get("IUE_CHECKPOINT", "/tmp/iue_raw.parquet")

CAMERA_NAMES = {
    "LWP": "Long Wave Prime (2000–3200 Å, primary)",
    "LWR": "Long Wave Redundant (2000–3200 Å, backup — failed 1983)",
    "SWP": "Short Wave Prime (1150–2000 Å, primary)",
}

COLUMN_DESCRIPTIONS = {
    "obs_id": "IUE image identifier (e.g., 'lwp00501'); camera prefix followed by a 5-digit exposure number. Primary key.",
    "camera": "IUE camera code: LWP, LWR, or SWP (see `camera_name` for expansion)",
    "camera_name": "Human-readable camera name with wavelength range",
    "exposure_number": "Sequential exposure number within the camera's archive (1–many thousands)",
    "proposal_id": "IUE observing proposal identifier (mixed-case alphanumeric, e.g., 'KQ120')",
    "proposal_pi": "Principal Investigator name (free-form; no canonical format)",
    "target_name": "Target name as provided by the proposer — catalog designations, common names, or coordinates",
    "target_ra": "Target right ascension in decimal degrees (ICRS)",
    "target_dec": "Target declination in decimal degrees (ICRS)",
    "intent": "Observation intent: 'science' or 'calibration'",
    "obstype": "CAOM observation type: 'S' (simple single spectrum) or 'C' (composite)",
}

DESCRIPTION = """\
The IUE Observation Catalog indexes every spectrum obtained by the International Ultraviolet Explorer (IUE), a joint NASA/ESA/UK mission that operated from January 26, 1978 to September 30, 1996 — 18.7 years, a record for a UV space observatory. IUE orbited in a geosynchronous orbit at ~36,000 km altitude, allowing 24-hour observation from a ground station in Maryland (NASA) and another in Villafranca (ESA). Its 45-cm Ritchey–Chrétien telescope fed echelle spectrographs in three cameras: SWP (Short Wave Prime, 1150–2000 Å), LWP (Long Wave Prime, 2000–3200 Å), and LWR (Long Wave Redundant, same range as LWP; operated until a 1983 failure).

Each row is one IUE spectrum — over 100,000 pointings across nearly two decades. Targets span every UV-interesting astronomical object class: bright OB stars, symbiotic binaries, supernovae (IUE watched SN 1987A live), Seyfert galaxies and quasars (including the famous 3C 273 and NGC 4151 monitoring programs visible in this table), protoplanetary nebulae, comets, planets, and solar-system moons. Because IUE's archive is so long, it remains the go-to source for UV variability studies on timescales from days to decades.

This dataset is the canonical catalog of what IUE observed, useful for historical cross-matching (finding the IUE coverage of any source that became interesting later), for UV variability archaeology (many active galactic nuclei and cataclysmic variables have IUE baselines nowhere else in the archive), and for teaching (IUE calibration data and well-studied objects like η Carinae are included in many astronomy curricula). It complements the HST, GALEX, JWST, and Chandra observation catalogs in this collection.

The catalog is derived from MAST's CAOM table `dbo.caomobservation` (collection = 'IUE'). The IUE archive is static since 1996; this dataset refreshes quarterly to pick up any late reprocessing or metadata fixes."""


_IUE_RE = re.compile(r"^(LWP|LWR|SWP)(\d+)$", re.I)


def _parse_obs_id(obs_id: str) -> dict:
    if not isinstance(obs_id, str):
        return {"camera": None, "exposure_number": None}
    m = _IUE_RE.match(obs_id)
    if not m:
        return {"camera": None, "exposure_number": None}
    return {"camera": m.group(1).upper(), "exposure_number": int(m.group(2))}


def main():
    print("IUE Observation Catalog pipeline")

    df = load_checkpoint(CHECKPOINT_PATH)
    if df is None:
        print("  Fetching caomobservation (collection=IUE)...")
        df = fetch_observations(
            "IUE",
            columns="observationid, obstype, intent, prpid, prppi, trgname, trgposra, trgposdec",
        )
        save_checkpoint(CHECKPOINT_PATH, df)

    print(f"  observations: {len(df):,}")

    parsed = df["observationid"].apply(_parse_obs_id).apply(pd.Series)
    df = pd.concat([df, parsed], axis=1)
    df["camera_name"] = df["camera"].map(CAMERA_NAMES)

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
    cam_counts = df["camera"].value_counts()
    cam_line = ", ".join(f"**{c}** ({n:,})" for c, n in cam_counts.items())
    unique_targets = df["target_name"].nunique()
    unique_proposals = df["proposal_id"].nunique()

    quick_stats = f"""\
- **{n_total:,}** IUE spectra (1978–1996)
- Cameras: {cam_line}
- **{unique_targets:,}** distinct target names
- **{unique_proposals:,}** distinct observing proposals"""

    usage = f"""\
```python
from datasets import load_dataset

ds = load_dataset("{HF_REPO}", split="train")
df = ds.to_pandas()

# All spectra of 3C 273 (famous quasar with long IUE monitoring)
tres_c_273 = df[df["target_name"].str.contains("3C 273", case=False, na=False)]
print(f"3C 273 spectra: {{len(tres_c_273):,}}")

# Spectra by camera
import matplotlib.pyplot as plt
df["camera"].value_counts().plot.bar()
plt.ylabel("Spectrum count"); plt.title("IUE exposures by camera (1978–1996)")
plt.show()

# Sky distribution of IUE pointings (sample)
sample = df.sample(min(50000, len(df)))
plt.figure(figsize=(12, 6))
plt.scatter(sample["target_ra"], sample["target_dec"], s=0.3, alpha=0.3)
plt.xlabel("RA (deg)"); plt.ylabel("Dec (deg)")
plt.gca().invert_xaxis()
plt.title("IUE target sky distribution (50K sample)")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="IUE Observation Catalog",
        description=DESCRIPTION,
        tags=["space", "iue", "nasa", "esa", "ultraviolet", "uv",
              "spectroscopy", "astronomy", "telescope", "open-data",
              "tabular-data", "parquet"],
        source_url="https://archive.stsci.edu/missions-and-data/iue",
        task_categories=["tabular-classification"],
        update_schedule="Quarterly (1st of Jan/Apr/Jul/Oct at 15:30 UTC) via [GitHub Actions](https://github.com/juliensimon/space-datasets).",
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e002215/GSFC_20171208_Archive_e002215~medium.jpg",
            "alt": "UV-bright sky — representative of the ultraviolet sky that IUE surveyed for nearly two decades",
            "credit": "NASA/GSFC",
        },
        related_datasets=[
            "juliensimon/hst-observations",
            "juliensimon/galex-observations",
            "juliensimon/jwst-observations",
            "juliensimon/chandra-x-ray-sources",
            "juliensimon/quasar-catalog",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=["target_ra", "target_dec"],
            integer=["exposure_number"],
            strings=["obs_id", "camera", "camera_name", "proposal_id",
                     "proposal_pi", "target_name", "intent", "obstype"],
        )

        df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

        all_null = [c for c in df.columns if df[c].isna().all()]
        if all_null:
            print(f"  Warning: dropping fully-null columns: {all_null}")
            df = df.drop(columns=all_null)

        p.publish(
            df,
            filename="iue_observations.parquet",
            min_rows=80_000,
            expected_columns=["obs_id", "camera", "target_ra", "target_dec"],
            critical_columns=["obs_id", "camera"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update IUE observations: {n_total:,} spectra",
        )
    print("Done.")


if __name__ == "__main__":
    main()
