#!/usr/bin/env python3
"""Fetch low-latency gravitational-wave candidate alerts from GraceDB and upload to HF.

Source: GraceDB (Gravitational-Wave Candidate Event Database), LIGO/Virgo/KAGRA
https://gracedb.ligo.org/

Every public "superevent" the online search pipelines promoted during O3 and O4,
including the overwhelming majority that were never confirmed as detections.
"""

import datetime as dt
import time

import pandas as pd

from hf_dataset_utils import Pipeline, fetch_with_retry

HF_REPO = "juliensimon/gw-candidate-alerts"

API_URL = "https://gracedb.ligo.org/api/superevents/"
# Production excludes Test and MDC (mock data challenge) superevents, which are
# injected simulations rather than detector candidates.
QUERY = "category%3A+Production"
PAGE_SIZE = 500
MAX_PAGES = 100

# GPS epoch and the GPS-UTC offset. The offset has been 18 s since 2017-01-01 and
# GraceDB's public record starts in 2019, so a constant is correct for this data.
GPS_EPOCH = dt.datetime(1980, 1, 6, tzinfo=dt.timezone.utc)
GPS_UTC_OFFSET_S = 18

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "superevent_id": "GraceDB superevent identifier, e.g. 'S251118cm'; 'S' prefix plus the UTC date and an alphabetic suffix ordering candidates within that day",
    "created": "UTC timestamp when the superevent record was created in GraceDB; differs from the candidate time by the alert latency",
    "event_time_utc": "UTC time of the candidate signal, converted from gps_time assuming the constant 18 s GPS-UTC offset in force since 2017",
    "gps_time": "GPS time of the candidate signal in seconds (API field 't_0'); join key against the 'gps' column of juliensimon/gravitational-wave-events",
    "gps_start": "GPS time of the start of the superevent time window (API field 't_start')",
    "gps_end": "GPS time of the end of the superevent time window (API field 't_end')",
    "far_hz": "False alarm rate of the superevent in Hz (inverse seconds); 1e-7 Hz is roughly one false alarm per four months; lower means more significant",
    "pipeline": "Online search pipeline that produced the preferred event: gstlal, pycbc, MBTA and spiir are matched-filter CBC searches, CWB and oLIB are unmodelled burst searches, MLy and aframe are machine-learning searches; 'MBTAOnline' is an older label for MBTA and appears only in O3",
    "search": "Search configuration within the pipeline, e.g. 'AllSky', 'EarlyWarning', 'SSM'",
    "analysis_group": "Analysis group of the preferred event: 'CBC' (compact binary coalescence) or 'Burst'",
    "instruments": "Comma-separated detectors contributing to the preferred event: H1 (LIGO Hanford), L1 (LIGO Livingston), V1 (Virgo), K1 (KAGRA)",
    "n_detectors": "Number of detectors in 'instruments'; derived",
    "labels": "Comma-separated GraceDB processing labels, e.g. SKYMAP_READY, EMBRIGHT_READY, PASTRO_READY, DQOK, EM_COINC, PE_READY",
    "is_low_significance": "True when the superevent carries a LOW_SIGNIF_* label, marking it as below the public significant-alert threshold; derived from labels",
    "has_skymap": "True when a sky localization was produced (SKYMAP_READY label); derived from labels",
    "is_em_ready": "True when the alert was released for electromagnetic follow-up (EM_READY label); derived from labels",
    "preferred_event_id": "GraceDB identifier of the single-pipeline event chosen to represent the superevent (API field 'graceid')",
    "preferred_event_far_hz": "False alarm rate of the preferred event alone in Hz; may differ from the superevent FAR after trials factors are applied",
    "reporting_latency_s": "Seconds between the candidate signal and the pipeline uploading it to GraceDB; a measure of low-latency alert performance",
    "n_events": "Number of individual pipeline events grouped into this superevent",
    "is_offline": "True when the preferred event came from an offline (archival) analysis rather than the low-latency online search",
    "likelihood": "Pipeline likelihood or ranking statistic of the preferred event; scale is pipeline-dependent and not comparable across pipelines",
    "submitter": "GraceDB account that created the superevent record; typically an automated follow-up robot",
    "em_type": "Identifier of an associated electromagnetic or neutrino counterpart candidate, when one was recorded",
    "time_coinc_far_hz": "False alarm rate in Hz for a time coincidence with an external trigger (e.g. a gamma-ray burst); null when no external coincidence was evaluated",
    "space_coinc_far_hz": "False alarm rate in Hz for a joint time-and-sky-position coincidence with an external trigger; null when no external coincidence was evaluated",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Low-latency gravitational-wave candidate alerts from GraceDB, the LIGO/Virgo/KAGRA \
candidate event database.

When the detector network is observing, a set of online search pipelines analyses the \
strain data continuously and uploads anything that looks like a signal within seconds \
to minutes. Related uploads are grouped into a "superevent" and given a public alert. \
This dataset is the complete public record of those superevents across the O3 and O4 \
observing runs.

Most of these candidates are not real. That is the point of the dataset: the confirmed \
detection catalogs describe only the events that survived offline analysis, while this \
record describes everything the detection system actually flagged in real time, \
including the noise. It makes the selection function visible.

Nine pipeline labels appear in the record. gstlal, pycbc, MBTA and spiir are \
matched-filter searches that correlate the data against modelled compact-binary \
waveforms; MBTAOnline is an older label for MBTA seen only in O3. CWB and oLIB are \
unmodelled burst searches that look for coherent excess power across detectors without \
assuming a waveform, oLIB having been retired after O3. MLy and aframe are \
machine-learning searches, and their arrival in O4 makes this dataset a record of when \
neural-network pipelines entered production gravitational-wave astronomy.

The false alarm rate, in hertz, is the central quantity. A candidate at 1e-7 Hz \
corresponds to roughly one false alarm every four months of observing; candidates near \
1e-5 Hz are expected several times a day from noise alone. The reporting latency column \
records how long each pipeline took to upload its candidate, which is what determines \
whether a telescope can be pointed at a merger while its electromagnetic counterpart is \
still bright.

Coverage note: the O4 run ended on 2025-11-18 and no new superevents are expected until \
O5 begins. The pipeline continues to run weekly and will resume collecting \
automatically when the network returns to observing.
"""


def _fetch_superevents():
    """Page through the GraceDB superevent API, newest first."""
    rows = []
    start = 0
    total = None
    for _ in range(MAX_PAGES):
        url = f"{API_URL}?query={QUERY}&count={PAGE_SIZE}&start={start}&format=json"
        resp = fetch_with_retry(url, label=f"GraceDB superevents start={start}")
        payload = resp.json()
        batch = payload.get("superevents") or []
        if total is None:
            total = payload.get("numRows")
            print(f"  {total:,} superevents reported by the API")
        if not batch:
            break
        rows.extend(batch)
        start += len(batch)
        print(f"  fetched {len(rows):,}/{total:,}")
        if total is not None and start >= total:
            break
        time.sleep(1)
    else:
        raise RuntimeError(f"Pagination exceeded {MAX_PAGES} pages; aborting")
    return rows


def _gps_to_utc(gps):
    if pd.isna(gps):
        return pd.NaT
    return GPS_EPOCH + dt.timedelta(seconds=float(gps) - GPS_UTC_OFFSET_S)


def _flatten(records):
    """Flatten superevents into one row each, lifting preferred_event_data scalars.

    'extra_attributes' is dropped: it carries only SingleInspiral/MultiBurst
    containers whose sole populated fields duplicate 'instruments'.
    """
    out = []
    for rec in records:
        pref = rec.get("preferred_event_data") or {}
        labels = rec.get("labels") or []
        instruments = pref.get("instruments") or ""
        out.append({
            "superevent_id": rec.get("superevent_id"),
            "created": rec.get("created"),
            "gps_time": rec.get("t_0"),
            "gps_start": rec.get("t_start"),
            "gps_end": rec.get("t_end"),
            "far_hz": rec.get("far"),
            "pipeline": pref.get("pipeline"),
            "search": pref.get("search"),
            "analysis_group": pref.get("group"),
            "instruments": instruments,
            "n_detectors": len([i for i in instruments.split(",") if i]),
            "labels": ",".join(labels),
            "is_low_significance": any(l.startswith("LOW_SIGNIF") for l in labels),
            "has_skymap": "SKYMAP_READY" in labels,
            "is_em_ready": "EM_READY" in labels,
            "preferred_event_id": pref.get("graceid"),
            "preferred_event_far_hz": pref.get("far"),
            "reporting_latency_s": pref.get("reporting_latency"),
            "n_events": pref.get("nevents"),
            "is_offline": pref.get("offline"),
            "likelihood": pref.get("likelihood"),
            "submitter": rec.get("submitter"),
            "em_type": rec.get("em_type"),
            "time_coinc_far_hz": rec.get("time_coinc_far"),
            "space_coinc_far_hz": rec.get("space_coinc_far"),
        })
    return pd.DataFrame(out)


def main():
    print("Fetching gravitational-wave candidate alerts from GraceDB...")
    records = _fetch_superevents()

    df = _flatten(records)
    print(f"  {len(df):,} superevents")

    df["created"] = pd.to_datetime(df["created"], format="mixed", utc=True, errors="coerce")
    for col in ["gps_time", "gps_start", "gps_end", "far_hz", "preferred_event_far_hz",
                "reporting_latency_s", "likelihood", "time_coinc_far_hz",
                "space_coinc_far_hz"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["n_events"] = pd.to_numeric(df["n_events"], errors="coerce").astype("Int64")
    df["event_time_utc"] = df["gps_time"].map(_gps_to_utc)

    # Keep only described columns, in declared order
    df = df[[c for c in COLUMN_DESCRIPTIONS if c in df.columns]]

    df = df.sort_values("gps_time").reset_index(drop=True)

    # ── Domain-specific stats for README ─────────────────────────────
    n = len(df)
    date_min = df["event_time_utc"].min().strftime("%Y-%m-%d")
    date_max = df["event_time_utc"].max().strftime("%Y-%m-%d")
    n_pipelines = df["pipeline"].nunique()
    n_significant = int((~df["is_low_significance"]).sum())
    median_latency = df["reporting_latency_s"].median()
    top_pipeline = df["pipeline"].value_counts().idxmax()

    quick_stats = f"""\
- **{n:,}** candidate alerts ({date_min} to {date_max})
- **{n_pipelines}** online search pipelines, most prolific: **{top_pipeline}**
- **{n_significant:,}** without a low-significance label
- Median reporting latency: **{median_latency:.1f} s**"""

    usage = """\
```python
import pandas as pd
from datasets import load_dataset

ds = load_dataset("juliensimon/gw-candidate-alerts", split="train")
df = ds.to_pandas()

# Alert latency by pipeline: how fast is each search?
print(df.groupby("pipeline")["reporting_latency_s"].describe()[["count", "50%", "max"]])

# Which candidates became confirmed detections? Join on GPS time (within 1 s).
confirmed = load_dataset("juliensimon/gravitational-wave-events", split="train").to_pandas()
matched = pd.merge_asof(
    df.sort_values("gps_time"),
    confirmed[["name", "gps"]].sort_values("gps"),
    left_on="gps_time", right_on="gps", tolerance=1, direction="nearest",
)
print(matched["name"].notna().sum(), "of", len(df), "candidates match a confirmed event")

# False alarm rate distribution
import matplotlib.pyplot as plt
import numpy as np
fig, ax = plt.subplots(figsize=(10, 5))
ax.hist(np.log10(df["far_hz"].dropna()), bins=60)
ax.set_xlabel("log10(false alarm rate / Hz)")
ax.set_ylabel("Candidates")
ax.set_title("GW candidate significance, O3-O4")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Gravitational-Wave Candidate Alerts",
        description=DESCRIPTION,
        tags=["space", "gravitational-waves", "ligo", "virgo", "kagra", "gracedb",
              "multi-messenger", "alerts", "physics", "astronomy",
              "open-data", "tabular-data", "parquet"],
        source_url="https://gracedb.ligo.org/",
        update_schedule="Weekly",
        task_categories=["tabular-classification", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/physics-datasets-69c2d4682d37dfdb77447bd7",
        banner={
            "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e000415/GSFC_20171208_Archive_e000415~orig.jpg",
            "alt": "Artist illustration of two merging black holes emitting gravitational waves",
            "credit": "NASA/CXC/A. Hobart",
        },
        related_datasets=[
            "juliensimon/gravitational-wave-events",
            "juliensimon/black-hole-catalog",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "gps_time", "gps_start", "gps_end", "far_hz",
                "preferred_event_far_hz", "reporting_latency_s", "likelihood",
                "time_coinc_far_hz", "space_coinc_far_hz",
            ],
        )
        p.publish(
            df,
            filename="gw_candidate_alerts.parquet",
            min_rows=1000,
            expected_columns=["superevent_id", "gps_time", "far_hz", "pipeline"],
            critical_columns=["superevent_id", "gps_time", "far_hz"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update GW candidate alerts: {n:,} superevents",
        )
    print("Done.")


if __name__ == "__main__":
    main()
