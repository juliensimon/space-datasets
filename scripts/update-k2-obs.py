#!/usr/bin/env python3
"""Fetch K2 mission observation metadata from MAST CAOM TAP and upload to HF.

K2 is the repurposed Kepler mission (2014–2018) after the second of Kepler's
four reaction wheels failed in 2013. The telescope could no longer hold its
original field of view pointing, so it was rolled every ~80 days to observe
a new patch of sky along the ecliptic — a "campaign". 20 campaigns (C0–C19)
were completed before the spacecraft ran out of fuel.

Each row here is one K2 target observation, parsed from obs_ids of the form:
  - ktwo<EPIC>-c<campaign>_<cadence>  (standard targets)
  - polar<EPIC>-c<campaign>_<cadence> (alternate-roll "polar" pointings)
  - k2gap<EPIC>-c<campaign>_<cadence> (Kepler/K2 Galactic Archaeology)
  - k2-c<NN>                          (campaign composite metadata)
"""

import os
import re

import pandas as pd

from hf_dataset_utils import Pipeline
from mast_tap import fetch_observations, load_checkpoint, save_checkpoint

HF_REPO = "juliensimon/k2-observations"
CHECKPOINT_PATH = os.environ.get("K2_CHECKPOINT", "/tmp/k2_raw.parquet")

COLUMN_DESCRIPTIONS = {
    "obs_id": "MAST observation identifier (e.g., 'ktwo201121245-c01_lc'); encodes target type, EPIC ID, campaign, and cadence. Primary key.",
    "epic_id": "Ecliptic Plane Input Catalog (EPIC) identifier (9-digit integer) for the target; null for campaign-composite rows",
    "target_type": "Category inferred from obs_id prefix: 'standard' (ktwo, main K2 target list), 'polar' (alternate-roll pointings with different sky coverage), 'k2gap' (Kepler/K2 Galactic Archaeology Program — asteroseismology / stellar populations), or 'campaign' (20 campaign-metadata rows)",
    "campaign": "K2 campaign number (0–19); each campaign observed a different patch of the ecliptic for ~80 days. Null for some campaign-composite rows.",
    "cadence": "Cadence type: 'lc' (long cadence, 29.4-minute integration) or 'sc' (short cadence, 58.9-second integration). Null for campaign composites.",
    "target_ra": "Target right ascension in decimal degrees (ICRS). Each K2 campaign covers roughly 100 sq. deg. along the ecliptic.",
    "target_dec": "Target declination in decimal degrees (ICRS). All K2 campaigns fall within ±30° of the ecliptic plane.",
    "intent": "Observation intent: 'science' or 'calibration'",
    "obstype": "CAOM observation type code: 'S' (simple) or 'C' (composite)",
}

DESCRIPTION = """\
The K2 Observation Catalog indexes every target observed by NASA's K2 mission — the repurposed Kepler spacecraft that flew between 2014 and 2018 after two of Kepler's four reaction wheels failed. Unable to hold its original Cygnus–Lyra field, K2 used solar radiation pressure as a "virtual third reaction wheel," rolling every ~80 days to observe a new ecliptic-plane field ("campaign"). 20 campaigns (C0–C19) were executed before the spacecraft exhausted its hydrazine fuel.

Each row is one K2 target observation. The dataset is drawn from MAST's `dbo.caomobservation` (collection = 'K2') and merges four observationid flavors that K2 uses to distinguish target-selection programs: `ktwo` (624K rows — the main per-target list from Guest Observer proposals), `polar` (121K rows — alternate-roll pointings that give slightly different sky coverage in the same campaign), `k2gap` (Kepler/K2 Galactic Archaeology Program — asteroseismology and stellar-population targets), and `k2-c<NN>` (20 rows of campaign-composite metadata). Each obs_id is parsed into its EPIC ID (the K2 equivalent of KIC), campaign number, and cadence (long or short).

K2 is the second-most prolific transit-discovery mission after Kepler prime, finding over 500 confirmed exoplanets across unusual hosts — M dwarfs, young stars in clusters, bright and easily-followed nearby systems — that the original Kepler field could not reach. It also produced rich stellar variability, asteroseismology, and solar-system (moving-target) archives.

This dataset is designed for cross-matching with exoplanet catalogs (K2 confirmed planets, K2 candidates, TESS TOI), for campaign-by-campaign target lists, for identifying long-baseline targets observed across multiple campaigns, and for selecting stellar-population samples via the k2gap prefix. It complements the Kepler prime-mission observations dataset in this collection. Raw and de-trended light curves for each target can be retrieved from MAST using the `obs_id`.

The catalog is derived from MAST's CAOM table `dbo.caomobservation` and is refreshed quarterly — K2 operations ended in 2018 but reprocessing (e.g., EVEREST, K2SFF detrended products) continues to land in the archive."""

# ktwo / polar / k2gap all share the format <prefix><EPIC>-c<campaign>_<cadence>
_K2_RE = re.compile(r"^(ktwo|polar|k2gap)(\d+)-c(\d+)_(lc|sc)$")
_CAMPAIGN_RE = re.compile(r"^k2-c(\d+)$")


def _parse_obs_id(obs_id: str) -> dict:
    """Return {target_type, epic_id, campaign, cadence} for an obs_id string.
    Unparseable rows return Nones — keep them but flagged target_type='unknown'.
    """
    if not isinstance(obs_id, str):
        return {"target_type": "unknown", "epic_id": None, "campaign": None, "cadence": None}
    m = _K2_RE.match(obs_id)
    if m:
        return {
            "target_type": {"ktwo": "standard", "polar": "polar", "k2gap": "k2gap"}[m.group(1)],
            "epic_id": int(m.group(2)),
            "campaign": int(m.group(3)),
            "cadence": m.group(4),
        }
    m = _CAMPAIGN_RE.match(obs_id)
    if m:
        return {"target_type": "campaign", "epic_id": None, "campaign": int(m.group(1)), "cadence": None}
    return {"target_type": "unknown", "epic_id": None, "campaign": None, "cadence": None}


def main():
    print("K2 Observation Catalog pipeline")

    df = load_checkpoint(CHECKPOINT_PATH)
    if df is None:
        print("  Fetching caomobservation (collection=K2)...")
        df = fetch_observations(
            "K2",
            columns="observationid, obstype, intent, trgposra, trgposdec",
        )
        save_checkpoint(CHECKPOINT_PATH, df)

    print(f"  observations: {len(df):,}")

    # ── Parse obs_id ────────────────────────────────────────────────────
    parsed = df["observationid"].apply(_parse_obs_id).apply(pd.Series)
    df = pd.concat([df, parsed], axis=1)

    df = df.rename(columns={
        "observationid": "obs_id",
        "trgposra": "target_ra",
        "trgposdec": "target_dec",
    })

    df = df.sort_values("obs_id").reset_index(drop=True)

    # ── Stats ──────────────────────────────────────────────────────────
    n_total = len(df)
    type_counts = df["target_type"].value_counts()
    type_line = ", ".join(f"**{t}** ({c:,})" for t, c in type_counts.items())
    n_campaigns = df["campaign"].nunique()
    n_lc = int((df["cadence"] == "lc").sum())
    n_sc = int((df["cadence"] == "sc").sum())
    unique_epic = df["epic_id"].nunique()

    quick_stats = f"""\
- **{n_total:,}** K2 observations (2014–2018, campaigns C0–C19)
- Target types: {type_line}
- **{n_campaigns}** distinct campaigns
- **{n_lc:,}** long cadence (29.4 min), **{n_sc:,}** short cadence (58.9 s)
- **{unique_epic:,}** distinct EPIC (Ecliptic Plane Input Catalog) targets"""

    usage = f"""\
```python
from datasets import load_dataset

ds = load_dataset("{HF_REPO}", split="train")
df = ds.to_pandas()

# Standard K2 targets observed across ≥5 campaigns (long baseline)
import pandas as pd
std = df[df["target_type"] == "standard"]
multi_campaign = std.groupby("epic_id").size()
long_baseline = multi_campaign[multi_campaign >= 5]
print(f"EPIC targets observed in ≥5 campaigns: {{len(long_baseline):,}}")

# K2 sky coverage (each campaign = different patch of ecliptic)
import matplotlib.pyplot as plt
sci = df[df["target_type"].isin(["standard", "polar", "k2gap"])]
plt.figure(figsize=(12, 6))
for c in sorted(sci["campaign"].dropna().unique()):
    subset = sci[sci["campaign"] == c]
    plt.scatter(subset["target_ra"], subset["target_dec"], s=0.2, alpha=0.3, label=f"C{{int(c)}}")
plt.xlabel("RA (deg)"); plt.ylabel("Dec (deg)")
plt.gca().invert_xaxis()
plt.title("K2 campaigns on the sky")
plt.legend(loc="upper right", fontsize=6, ncol=2)
plt.show()

# Targets per campaign
per_c = sci.groupby("campaign").size()
per_c.plot.bar()
plt.xlabel("Campaign"); plt.ylabel("Target observations")
plt.title("K2 target count per campaign")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="K2 Observation Catalog",
        description=DESCRIPTION,
        tags=["space", "k2", "kepler", "nasa", "exoplanets", "astronomy",
              "telescope", "photometry", "open-data", "tabular-data", "parquet"],
        source_url="https://archive.stsci.edu/missions-and-data/k2",
        task_categories=["tabular-classification"],
        update_schedule="Quarterly (1st of Jan/Apr/Jul/Oct at 15:00 UTC) via [GitHub Actions](https://github.com/juliensimon/space-datasets).",
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA18904/PIA18904~small.jpg",
            "alt": "Artist concept of NASA's Kepler space telescope observing along the ecliptic plane during its K2 mission",
            "credit": "NASA/Ames/JPL-Caltech",
        },
        related_datasets=[
            "juliensimon/kepler-observations",
            "juliensimon/kepler-eclipsing-binaries",
            "juliensimon/kepler-transit-timing",
            "juliensimon/nasa-exoplanets",
            "juliensimon/tess-toi-candidates",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=["target_ra", "target_dec"],
            integer=["epic_id", "campaign"],
            strings=["obs_id", "target_type", "cadence", "intent", "obstype"],
        )

        df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

        all_null = [c for c in df.columns if df[c].isna().all()]
        if all_null:
            print(f"  Warning: dropping fully-null columns: {all_null}")
            df = df.drop(columns=all_null)

        p.publish(
            df,
            filename="k2_observations.parquet",
            min_rows=700_000,
            expected_columns=["obs_id", "target_type", "target_ra", "target_dec"],
            critical_columns=["obs_id", "target_type"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update K2 observations: {n_total:,} observations",
        )
    print("Done.")


if __name__ == "__main__":
    main()
