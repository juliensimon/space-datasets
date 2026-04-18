#!/usr/bin/env python3
"""Fetch GALEX mission observation metadata from MAST CAOM TAP and upload to HF.

Each row = one GALEX observation (imaging tile or spectrum), with target
pointing and the GALEX survey under which it was taken (AIS, MIS, DIS,
NGS, etc.). GALEX (2003–2013) was NASA's dedicated UV all-sky surveyor,
imaging the sky in the FUV (1350–1750 Å) and NUV (1750–2750 Å) bands.
"""

import os
import re
import time

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

HF_REPO = "juliensimon/galex-observations"
TAP_URL = "https://mast.stsci.edu/vo-tap/api/v0.1/caom/sync"
PAGE_SIZE = 100_000
PAGE_SLEEP = 0.5
HTTP_TIMEOUT = 600
CHECKPOINT_PATH = os.environ.get("GALEX_CHECKPOINT", "/tmp/galex_raw.parquet")

SURVEY_NAMES = {
    "AIS": "All-sky Imaging Survey",
    "MIS": "Medium Imaging Survey",
    "DIS": "Deep Imaging Survey",
    "NGS": "Nearby Galaxy Survey",
    "GII": "Guest Investigator Imaging",
    "GIS": "Guest Investigator Spectroscopy",
    "CAI": "Calibration Imaging",
    "CAS": "Calibration Spectroscopy",
    "MSS": "Medium Spectroscopic Survey",
    "DSS": "Deep Spectroscopic Survey",
    "WSS": "Wide Spectroscopic Survey",
    "ETS": "Engineering Test Survey",
}

COLUMN_DESCRIPTIONS = {
    "obs_id": "MAST observation identifier for this GALEX observation (opaque numeric string). Primary key.",
    "survey_code": "GALEX survey code: AIS, MIS, DIS, NGS, GII, GIS, CAI, CAS, MSS, DSS, WSS, ETS. See `survey_name` for expansion.",
    "survey_name": "Human-readable survey name (e.g. 'All-sky Imaging Survey' for AIS)",
    "target_name": "Target field identifier, often encoding the pointing or an associated catalog source",
    "target_ra": "Field centre right ascension in decimal degrees (ICRS)",
    "target_dec": "Field centre declination in decimal degrees (ICRS)",
    "intent": "Observation intent: 'science' (survey pointing) or 'calibration'",
    "obstype": "CAOM observation type code: 'S' (simple single exposure) or 'C' (composite, e.g. a co-added tile)",
}

DESCRIPTION = """\
The GALEX Observation Catalog indexes every pointing observed by NASA's Galaxy Evolution Explorer (GALEX) mission between its launch on April 28, 2003 and the end of operations in June 2013. GALEX was a dedicated ultraviolet space telescope with a 50-cm primary mirror, imaging the sky simultaneously in two bands: Far-UV (FUV, 1350–1750 Å) and Near-UV (NUV, 1750–2750 Å). Its 1.2-degree circular field of view and low-noise microchannel-plate detectors enabled the first comprehensive UV all-sky survey, mapping over 60,000 square degrees and cataloguing hundreds of millions of UV sources.

Each row in this catalog is one GALEX observation, tagged with its survey origin. The surveys include AIS (All-sky Imaging Survey — shallow, wide), MIS (Medium Imaging Survey — overlapping SDSS), DIS (Deep Imaging Survey — deepest UV field survey to date), NGS (Nearby Galaxy Survey), and specialised Guest Investigator, calibration, and spectroscopic programs. Field centres are in ICRS RA/Dec degrees, and the `target_name` captures the proposer-assigned identifier for each tile.

This dataset is designed for cross-matching UV sources with catalogs at other wavelengths (optical Gaia/SDSS/Pan-STARRS, infrared WISE, X-ray Chandra/eROSITA), for stellar population studies (UV is a tracer of young star formation), for AGN selection (UV-bright galaxies and quasars), and for planning deep archival follow-up. It complements the Hubble, JWST, Chandra, and eROSITA observation catalogs in this collection, extending the multi-wavelength view into the UV.

The catalog is derived from MAST's CAOM table `dbo.caomobservation` (collection = 'GALEX'). The GALEX archive is static since 2013, so this dataset is refreshed quarterly for any late reprocessing."""

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
        print(f"    {table}: {total:,} rows (last {order_col}={str(last_key)[:40]}...)")
        if len(df) < current_size:
            break
        time.sleep(PAGE_SLEEP)
    if not chunks:
        return pd.DataFrame()
    return pd.concat(chunks, ignore_index=True)


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


def main():
    print("GALEX Observation Catalog pipeline")

    df = _load_checkpoint()
    if df is None:
        print("  Fetching caomobservation (collection=GALEX)...")
        df = fetch_paginated(
            "observationid, obstype, intent, prpproject, trgname, trgposra, trgposdec",
            "dbo.caomobservation",
            "collection = 'GALEX'",
            "observationid",
        )
        _save_checkpoint(df)

    print(f"  observations: {len(df):,}")

    df = df.rename(columns={
        "observationid": "obs_id",
        "prpproject": "survey_code",
        "trgname": "target_name",
        "trgposra": "target_ra",
        "trgposdec": "target_dec",
    })

    df["survey_name"] = df["survey_code"].map(SURVEY_NAMES)

    df = df.sort_values("obs_id").reset_index(drop=True)

    n_total = len(df)
    n_science = int((df["intent"] == "science").sum())
    n_cal = int((df["intent"] == "calibration").sum())
    survey_counts = df["survey_code"].value_counts().head(5)
    survey_line = ", ".join(f"**{c}** ({n:,})" for c, n in survey_counts.items())

    quick_stats = f"""\
- **{n_total:,}** GALEX observations (2003–2013)
- **{n_science:,}** science, **{n_cal:,}** calibration
- Top surveys: {survey_line}"""

    usage = f"""\
```python
from datasets import load_dataset

ds = load_dataset("{HF_REPO}", split="train")
df = ds.to_pandas()

# Deep survey fields only
deep = df[df["survey_code"] == "DIS"]
print(f"Deep Imaging Survey pointings: {{len(deep):,}}")

# UV sky coverage map (All-sky Imaging Survey)
import matplotlib.pyplot as plt
ais = df[df["survey_code"] == "AIS"]
plt.figure(figsize=(12, 6))
plt.scatter(ais["target_ra"], ais["target_dec"], s=0.3, alpha=0.3)
plt.xlabel("RA (deg)"); plt.ylabel("Dec (deg)")
plt.gca().invert_xaxis()
plt.title("GALEX All-sky Imaging Survey (AIS) pointings")
plt.show()

# Observations per survey
df["survey_code"].value_counts().plot.bar()
plt.ylabel("Observation count")
plt.title("GALEX observations by survey program")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="GALEX Observation Catalog",
        description=DESCRIPTION,
        tags=["space", "galex", "nasa", "ultraviolet", "uv", "all-sky",
              "astronomy", "telescope", "open-data", "tabular-data", "parquet"],
        source_url="https://archive.stsci.edu/missions-and-data/galex",
        task_categories=["tabular-classification"],
        update_schedule="Quarterly (1st of Jan/Apr/Jul/Oct at 14:30 UTC) via [GitHub Actions](https://github.com/juliensimon/space-datasets).",
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA03094/PIA03094~small.jpg",
            "alt": "The GALEX space telescope in orbit with a UV view of the Andromeda Galaxy",
            "credit": "NASA/JPL-Caltech",
        },
        related_datasets=[
            "juliensimon/gswlc-galaxy-properties",
            "juliensimon/hst-observations",
            "juliensimon/jwst-observations",
            "juliensimon/chandra-x-ray-sources",
            "juliensimon/nasa-exoplanets",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=["target_ra", "target_dec"],
            strings=["obs_id", "survey_code", "survey_name", "target_name",
                     "intent", "obstype"],
        )

        df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

        all_null = [c for c in df.columns if df[c].isna().all()]
        if all_null:
            print(f"  Warning: dropping fully-null columns: {all_null}")
            df = df.drop(columns=all_null)

        p.publish(
            df,
            filename="galex_observations.parquet",
            min_rows=200_000,
            expected_columns=["obs_id", "survey_code", "target_ra", "target_dec"],
            critical_columns=["obs_id", "survey_code"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update GALEX observations: {n_total:,} observations",
        )
    print("Done.")


if __name__ == "__main__":
    main()
