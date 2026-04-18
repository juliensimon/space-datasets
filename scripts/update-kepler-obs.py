#!/usr/bin/env python3
"""Fetch Kepler mission observation metadata from MAST CAOM TAP and upload to HF.

Observation-level only. Each row = one Kepler target (identified by KIC ID)
with its pointing, cadence type, and quarters observed (encoded in obs_id).
The Kepler prime mission observed ~200K stars in a single 100 sq. deg field
from 2009 to 2013, discovering the majority of confirmed exoplanets by
photometric transit detection.
"""

import os
import re
import time

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

HF_REPO = "juliensimon/kepler-observations"
TAP_URL = "https://mast.stsci.edu/vo-tap/api/v0.1/caom/sync"
PAGE_SIZE = 100_000
PAGE_SLEEP = 0.5
HTTP_TIMEOUT = 600
CHECKPOINT_PATH = os.environ.get("KEPLER_CHECKPOINT", "/tmp/kepler_raw.parquet")

COLUMN_DESCRIPTIONS = {
    "obs_id": "MAST observation identifier (e.g., 'kplr000757076_lc_Q111111111111111111'); encodes KIC ID, cadence (lc=long, sc=short), and Q-flags for each of the 17 Kepler quarters (1=observed, 0=not). Primary key.",
    "kic_id": "Kepler Input Catalog identifier (9-digit integer) for the target star; shared with the NASA Exoplanet Archive",
    "cadence": "Cadence type: 'lc' (long cadence, 29.4-minute integration) or 'sc' (short cadence, 58.9-second integration)",
    "quarters_observed": "Number of Kepler quarters (out of 17) in which the target was observed; higher = longer light-curve baseline",
    "quarters_mask": "17-character string of '1'/'0' flags marking which Kepler quarters contain data for this target (Q1–Q17, in order)",
    "target_ra": "Target right ascension in decimal degrees (ICRS). Kepler observed a fixed ~100 sq. deg. field near RA 290°, Dec 45° in Cygnus-Lyra.",
    "target_dec": "Target declination in decimal degrees (ICRS)",
    "intent": "Observation intent: 'science' (target star monitoring) or 'calibration'",
}

DESCRIPTION = """\
The Kepler Observation Catalog indexes every target observed by NASA's Kepler space telescope during its prime mission (2009–2013), drawn from the Mikulski Archive for Space Telescopes (MAST). Kepler is the most successful exoplanet-hunting mission in history: by continuously monitoring ~200,000 stars in a single 100-square-degree field of view in Cygnus–Lyra, it discovered the majority of confirmed exoplanets through high-precision photometric transit detection, including the first Earth-sized planets in habitable zones.

Each row in this catalog is one Kepler target — identified by its 9-digit Kepler Input Catalog (KIC) ID — with the cadence at which it was observed (long cadence = 29.4-minute integration, capable of catching transits on weeks-to-months orbital periods; short cadence = 58.9-second integration, used for asteroseismology and short-period transits), the pointing (RA/Dec), and a 17-character bitmask indicating which of Kepler's 17 quarterly observing periods contain data for that target. The `quarters_observed` column summarises the mask as an integer count — a target observed in all 17 quarters has the longest, most exoplanet-favourable light curve in the archive.

This dataset is designed for cross-matching with other exoplanet catalogs (Kepler confirmed planets, TESS TOI, Gaia DR3), for selecting targets with long baselines for long-period planet searches, and for understanding the Kepler field's completeness. It complements the Kepler eclipsing binary and transit timing variation catalogs already in this collection by providing the full target list. Each target's raw and de-trended light curves can be retrieved from MAST using the `obs_id`.

The catalog is derived from MAST's CAOM table `dbo.caomobservation` (collection = 'KEPLER'). The K2 extended mission (2014–2018) uses a different observation-id schema and is published as a separate dataset (planned). The Kepler prime-mission archive is static, so this dataset is refreshed quarterly to pick up any late-stage reprocessing."""

# ── TAP helpers ──────────────────────────────────────────────────────────

_TR_RE = re.compile(r"<TR>(.*?)</TR>", re.S)
_TD_RE = re.compile(r"<TD>(.*?)</TD>", re.S)
_FIELD_RE = re.compile(r'<FIELD\s+name="([^"]+)"', re.S)


def _parse_votable(text: str) -> pd.DataFrame:
    fields = _FIELD_RE.findall(text)
    if not fields:
        return pd.DataFrame()
    rows = []
    for tr in _TR_RE.findall(text):
        cells = _TD_RE.findall(tr)
        if len(cells) == len(fields):
            rows.append(cells)
    df = pd.DataFrame(rows, columns=fields)
    df.replace({"": pd.NA}, inplace=True)
    return df


def _tap_query(adql: str, tries: int = 3) -> pd.DataFrame:
    last_err = None
    for attempt in range(tries):
        try:
            r = requests.post(
                TAP_URL,
                data={"QUERY": adql, "REQUEST": "doQuery", "LANG": "ADQL"},
                timeout=HTTP_TIMEOUT,
            )
            if r.status_code == 200:
                return _parse_votable(r.text)
            last_err = f"HTTP {r.status_code}: {r.text[:200]}"
        except requests.RequestException as e:
            last_err = str(e)
        wait = 5 * (attempt + 1)
        print(f"    TAP error ({last_err}); retry in {wait}s")
        time.sleep(wait)
    raise RuntimeError(f"TAP query failed after {tries} attempts: {last_err}")


def fetch_paginated(base_select: str, table: str, where: str, order_col: str,
                     page_size: int = PAGE_SIZE) -> pd.DataFrame:
    chunks = []
    last_key = None
    total = 0
    current_size = page_size
    while True:
        clause = where if last_key is None else f"{where} AND {order_col} > '{last_key}'"
        q = f"SELECT TOP {current_size} {base_select} FROM {table} WHERE {clause} ORDER BY {order_col}"
        try:
            df = _tap_query(q)
        except RuntimeError as e:
            if "504" in str(e) and current_size > 5_000:
                current_size = max(current_size // 2, 5_000)
                print(f"    504 on {table}: halving page size to {current_size:,}")
                time.sleep(10)
                continue
            raise
        if df.empty:
            break
        chunks.append(df)
        total += len(df)
        last_key = df[order_col].iloc[-1]
        print(f"    {table}: {total:,} rows (last {order_col}={str(last_key)[:50]}...)")
        if len(df) < current_size:
            break
        time.sleep(PAGE_SLEEP)
    if not chunks:
        return pd.DataFrame()
    return pd.concat(chunks, ignore_index=True)


# ── Main ─────────────────────────────────────────────────────────────────

def _load_checkpoint():
    if CHECKPOINT_PATH and os.path.exists(CHECKPOINT_PATH):
        try:
            df = pd.read_parquet(CHECKPOINT_PATH)
            print(f"  Loaded checkpoint: {len(df):,} rows")
            return df
        except Exception as e:
            print(f"  Checkpoint load failed: {e}")
    return None


def _save_checkpoint(df):
    if CHECKPOINT_PATH:
        try:
            df.to_parquet(CHECKPOINT_PATH, compression="zstd")
            print(f"  Saved checkpoint to {CHECKPOINT_PATH}")
        except Exception as e:
            print(f"  Checkpoint save failed: {e}")


# Regex to parse obs_id = "kplr<KIC>_<cadence>_Q<mask>" for Kepler
# and "ktwo<EPIC>_..." for K2 (different format)
_KEPLER_RE = re.compile(r"^kplr(\d+)_(lc|sc)_Q([01]+)$")


def main():
    print("Kepler Observation Catalog pipeline")

    df = _load_checkpoint()
    if df is None:
        print("  Fetching caomobservation (collection=KEPLER)...")
        df = fetch_paginated(
            "observationid, obstype, intent, trgposra, trgposdec",
            "dbo.caomobservation",
            "collection = 'KEPLER'",
            "observationid",
        )
        _save_checkpoint(df)

    print(f"  observations: {len(df):,}")

    # ── Parse obs_id + derive columns ──────────────────────────────────
    parsed = df["observationid"].astype(str).str.extract(_KEPLER_RE)
    df["kic_id"] = pd.to_numeric(parsed[0], errors="coerce").astype("Int64")
    df["cadence"] = parsed[1]
    df["quarters_mask"] = parsed[2]
    df["quarters_observed"] = parsed[2].fillna("").str.count("1").astype("Int64")

    df = df.rename(columns={
        "observationid": "obs_id",
        "trgposra": "target_ra",
        "trgposdec": "target_dec",
    })

    df = df.sort_values("obs_id").reset_index(drop=True)

    # ── Stats ──────────────────────────────────────────────────────────
    n_total = len(df)
    n_lc = int((df["cadence"] == "lc").sum())
    n_sc = int((df["cadence"] == "sc").sum())
    all_17_q = int((df["quarters_observed"] == 17).sum())
    unique_kic = df["kic_id"].nunique()

    quick_stats = f"""\
- **{n_total:,}** Kepler prime-mission observations (2009–2013)
- **{n_lc:,}** long cadence (29.4 min), **{n_sc:,}** short cadence (58.9 s)
- **{all_17_q:,}** targets observed in all 17 Kepler quarters (maximum baseline)
- **{unique_kic:,}** distinct Kepler Input Catalog (KIC) targets"""

    usage = f"""\
```python
from datasets import load_dataset

ds = load_dataset("{HF_REPO}", split="train")
df = ds.to_pandas()

# Targets with longest baseline (all 17 quarters)
full_baseline = df[(df["quarters_observed"] == 17) & (df["cadence"] == "lc")]
print(f"Targets observed across the full Kepler prime mission: {{len(full_baseline):,}}")

# Map of Kepler field
import matplotlib.pyplot as plt
sample = df.sample(min(50000, len(df)))
plt.figure(figsize=(10, 8))
plt.scatter(sample["target_ra"], sample["target_dec"], s=0.2, alpha=0.3)
plt.xlabel("RA (deg)"); plt.ylabel("Dec (deg)")
plt.title("Kepler prime-mission field of view (50K sample)")
plt.gca().invert_xaxis()
plt.show()

# Cadence distribution per quarter
import numpy as np
mask_chars = np.array([list(m) for m in df["quarters_mask"].fillna("0" * 17)])
per_quarter = (mask_chars == "1").sum(axis=0)
plt.bar(range(1, 18), per_quarter)
plt.xlabel("Kepler quarter"); plt.ylabel("Targets observed")
plt.title("Kepler target count per quarter")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Kepler Observation Catalog",
        description=DESCRIPTION,
        tags=["space", "kepler", "k2", "nasa", "exoplanets", "astronomy",
              "telescope", "photometry", "open-data", "tabular-data", "parquet"],
        source_url="https://archive.stsci.edu/missions-and-data/kepler",
        task_categories=["tabular-classification"],
        update_schedule="Quarterly (1st of Jan/Apr/Jul/Oct at 14:00 UTC) via [GitHub Actions](https://github.com/juliensimon/space-datasets).",
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA13272/PIA13272~small.jpg",
            "alt": "Artist concept of NASA's Kepler space telescope in orbit, surrounded by a starfield",
            "credit": "NASA/Ames/JPL-Caltech",
        },
        related_datasets=[
            "juliensimon/kepler-eclipsing-binaries",
            "juliensimon/kepler-transit-timing",
            "juliensimon/nasa-exoplanets",
            "juliensimon/tess-toi-candidates",
            "juliensimon/hst-observations",
            "juliensimon/jwst-observations",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=["target_ra", "target_dec"],
            integer=["kic_id", "quarters_observed"],
            strings=["obs_id", "cadence", "quarters_mask",
                     "intent", "obstype"],
        )

        # obstype isn't described (all = 'C' composite); drop it
        df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

        all_null = [c for c in df.columns if df[c].isna().all()]
        if all_null:
            print(f"  Warning: dropping fully-null columns: {all_null}")
            df = df.drop(columns=all_null)

        p.publish(
            df,
            filename="kepler_observations.parquet",
            min_rows=150_000,
            expected_columns=["obs_id", "kic_id", "cadence",
                              "target_ra", "target_dec"],
            critical_columns=["obs_id", "cadence"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Kepler observations: {n_total:,} observations",
        )
    print("Done.")


if __name__ == "__main__":
    main()
