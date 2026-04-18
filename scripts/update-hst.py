#!/usr/bin/env python3
"""Fetch Hubble Space Telescope observation metadata from MAST CAOM TAP and upload to HF.

Observation-level only (no per-plane timing/exposure aggregation) — HST has
4.6M planes across 2.6M observations, and joining server-side times out
reliably. v2 can add plane-derived timing once we build an async/batched
plane fetch.
"""

import os

import pandas as pd

from hf_dataset_utils import Pipeline
from mast_tap import fetch_observations, load_checkpoint, save_checkpoint

HF_REPO = "juliensimon/hst-observations"
CHECKPOINT_PATH = os.environ.get("HST_CHECKPOINT", "/tmp/hst_raw.parquet")

# ── Column descriptions ─────────────────────────────────────────────────
COLUMN_DESCRIPTIONS = {
    "obs_id": "MAST observation identifier (e.g., 'hst_05773_54_wfpc2_wf_pc_f547m'); encodes proposal, visit, instrument, aperture, and filter. Primary key.",
    "proposal_id": "HST proposal identifier (string, e.g., '5773'); groups related observations by Principal Investigator's program",
    "proposal_pi": "Last name, first initial of the proposal Principal Investigator",
    "proposal_title": "Full title of the HST observing proposal",
    "proposal_project": "Proposal project code (e.g., 'GO', 'GTO', 'SNAP', 'DDT', 'CAL'); GO = General Observer, SNAP = snapshot survey, DDT = Director's Discretionary, CAL = calibration",
    "proposal_keywords": "Science keywords tagged on the proposal (semicolon-separated)",
    "target_name": "Target name as provided by the proposer (may include survey designations, coordinates, or informal names)",
    "target_ra": "Target right ascension in decimal degrees (ICRS). May be 0 for moving or calibration targets.",
    "target_dec": "Target declination in decimal degrees (ICRS). May be 0 for moving or calibration targets.",
    "target_moving": "True if the target is a moving solar system body (asteroid, comet, planet, moon); False for fixed celestial targets",
    "instrument": "Instrument name: ACS, WFC3, WFPC2, STIS, COS, NICMOS, FOC, FOS, HRS, FGS (from 'INSTRUMENT/DETECTOR' split)",
    "detector": "Detector or observing mode within the instrument (e.g., 'WFC', 'UVIS', 'IR', 'HRC', 'SBC', 'PC', 'WF'); from 'INSTRUMENT/DETECTOR' split",
    "intent": "Observation intent: 'science' or 'calibration'",
    "obstype": "CAOM observation type code: 'S' (simple), 'C' (composite)",
}

DESCRIPTION = """\
The Hubble Space Telescope Observation Catalog is a complete index of every observation obtained by NASA/ESA's Hubble Space Telescope since its launch on April 24, 1990, drawn from the Mikulski Archive for Space Telescopes (MAST). Hubble's 2.4-meter primary mirror and suite of instruments have produced one of the most scientifically productive archives in astronomy, with over 35 years of continuous operation in low Earth orbit.

Each row in this catalog is one HST observation — a unit of telescope time executing an exposure with a specific instrument, detector, filter, and target pointing. Rows include the proposal under which the observation was taken (proposal ID, PI, title, category: GO, SNAP, GTO, DDT, CAL), the target (name, coordinates, moving/fixed flag), the instrument and detector (ACS WFC/HRC/SBC, WFC3 UVIS/IR, WFPC2 WF/PC, STIS, COS, NICMOS, plus legacy FOC/FOS/HRS/FGS), and the observation intent.

This dataset is the canonical reference for answering questions like: what has Hubble observed near a given RA/Dec? Which proposals used STIS for UV spectroscopy? Which targets have the deepest imaging coverage? It is designed for cross-matching with target catalogs (galaxies, quasars, stars, solar system bodies), for program-level summaries, for planning parallel JWST follow-up, and as training data for observation-recommendation systems.

This v1 provides observation-level metadata only. Per-observation timing and exposure data — which require joining with MAST's `dbo.caomplane` table (4.6M rows) — will arrive in a v2 as we build an async batched pipeline. For now, detailed timing/filter information can be retrieved per observation via the MAST Portal or the `astroquery.mast` Python package.

The catalog is derived from MAST's CAOM (Common Archive Observation Model) table `dbo.caomobservation` and is refreshed weekly as HST observations enter the archive. Calibration and engineering observations are included but are distinguishable via the `intent` column."""

# ── Main ─────────────────────────────────────────────────────────────────

def main():
    print("HST Observation Catalog pipeline")

    df = load_checkpoint(CHECKPOINT_PATH)
    if df is None:
        print("  Fetching caomobservation (collection=HST)...")
        df = fetch_observations(
            "HST",
            columns="observationid, obstype, intent, prpid, prppi, prptitle, prpproject, prpkeywords, trgname, trgposra, trgposdec, trgmoving, insname",
        )
        save_checkpoint(CHECKPOINT_PATH, df)

    print(f"  observations: {len(df):,}")

    # ── Rename + derive ────────────────────────────────────────────────
    rename = {
        "observationid": "obs_id",
        "prpid": "proposal_id",
        "prppi": "proposal_pi",
        "prptitle": "proposal_title",
        "prpproject": "proposal_project",
        "prpkeywords": "proposal_keywords",
        "trgname": "target_name",
        "trgposra": "target_ra",
        "trgposdec": "target_dec",
        "trgmoving": "target_moving",
    }
    df = df.rename(columns=rename)

    # Split insname ("ACS/WFC") into instrument + detector
    ins = df["insname"].fillna("").astype(str).str.split("/", n=1, expand=True)
    df["instrument"] = ins[0].replace("", pd.NA)
    df["detector"] = ins[1].replace("", pd.NA) if ins.shape[1] > 1 else pd.NA

    def _to_bool(v):
        if pd.isna(v):
            return False
        return str(v).strip().lower() in ("true", "1", "t", "yes")
    df["target_moving"] = df["target_moving"].map(_to_bool).astype(bool)

    # Sort by obs_id (deterministic; proposal_id-prefixed ids group programs)
    df = df.sort_values("obs_id").reset_index(drop=True)

    # ── Stats ──────────────────────────────────────────────────────────
    n_total = len(df)
    n_science = int((df["intent"] == "science").sum())
    n_cal = int((df["intent"] == "calibration").sum())
    n_proposals = df["proposal_id"].nunique()
    top_instruments = df["instrument"].value_counts().head(5)
    top_instr_line = ", ".join(f"**{name}** ({cnt:,})" for name, cnt in top_instruments.items())

    quick_stats = f"""\
- **{n_total:,}** HST observations (1990–present)
- **{n_science:,}** science, **{n_cal:,}** calibration
- **{n_proposals:,}** distinct proposals
- Top instruments: {top_instr_line}"""

    usage = f"""\
```python
from datasets import load_dataset

ds = load_dataset("{HF_REPO}", split="train")
df = ds.to_pandas()

# Science observations with WFC3 UVIS detector
import pandas as pd
wfc3_uvis = df[(df["intent"] == "science") & (df["instrument"] == "WFC3") & (df["detector"] == "UVIS")]
print(f"WFC3 UVIS science observations: {{len(wfc3_uvis):,}}")

# Proposals per decade
df["decade"] = df["proposal_id"].astype(str).str[:1].replace({{
    "5": "1990s", "6": "1990s-2000s", "7": "1990s-2000s",
    "8": "2000s", "9": "2000s", "1": "2000s-2020s",
}})
df.groupby("instrument")["proposal_id"].nunique().sort_values(ascending=False).head(15).plot.bar()
import matplotlib.pyplot as plt
plt.ylabel("Distinct proposals")
plt.title("HST proposal count by instrument")
plt.show()

# Cone search around a target (Hubble Deep Field)
import numpy as np
ra, dec = 189.139, 62.217
sep = np.hypot(df["target_ra"] - ra, df["target_dec"] - dec)
nearby = df[sep < 0.1]
print(f"HST observations within 0.1 deg of HDF: {{len(nearby):,}}")

# Instrument usage pie
df["instrument"].value_counts().head(10).plot.pie(autopct="%1.1f%%")
plt.title("HST instrument usage (observation count)")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Hubble Space Telescope Observation Catalog",
        description=DESCRIPTION,
        tags=["space", "hubble", "hst", "nasa", "esa", "astronomy",
              "telescope", "open-data", "tabular-data", "parquet"],
        source_url="https://archive.stsci.edu/",
        task_categories=["tabular-classification"],
        update_schedule="Weekly (Monday at 13:30 UTC) via [GitHub Actions](https://github.com/juliensimon/space-datasets).",
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA01236/PIA01236~small.jpg",
            "alt": "The Hubble Space Telescope being deployed from the Space Shuttle Discovery in 1990",
            "credit": "NASA",
        },
        related_datasets=[
            "juliensimon/jwst-observations",
            "juliensimon/chandra-x-ray-sources",
            "juliensimon/erosita-erass1-xray",
            "juliensimon/4xmm-dr14-xray-sources",
            "juliensimon/nasa-exoplanets",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=["target_ra", "target_dec"],
            strings=[
                "obs_id", "proposal_id", "proposal_pi", "proposal_title",
                "proposal_project", "proposal_keywords", "target_name",
                "instrument", "detector", "intent", "obstype",
            ],
        )

        df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

        all_null = [c for c in df.columns if df[c].isna().all()]
        if all_null:
            print(f"  Warning: dropping fully-null columns: {all_null}")
            df = df.drop(columns=all_null)

        p.publish(
            df,
            filename="hst_observations.parquet",
            min_rows=1_500_000,
            expected_columns=["obs_id", "proposal_id", "target_name",
                              "instrument", "intent"],
            critical_columns=["obs_id", "instrument", "intent"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update HST observations: {n_total:,} observations",
        )
    print("Done.")


if __name__ == "__main__":
    main()
