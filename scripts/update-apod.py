#!/usr/bin/env python3
"""Fetch NASA Astronomy Picture of the Day (APOD) and upload to HF.

Incremental: downloads existing parquet, fetches last 14 days, merges.
Falls back to full yearly rebuild if no existing data.

Source: NASA APOD API (https://api.nasa.gov/planetary/apod)
"""

import os
import time
from collections import Counter
from datetime import datetime, timedelta

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

APOD_BASE = "https://api.nasa.gov/planetary/apod"
HF_REPO = "juliensimon/nasa-apod"
APOD_START = "1995-06-16"
OVERLAP_DAYS = 14

# DEMO_KEY is rate-limited to 30 req/hour, 50/day per IP — set NASA_API_KEY in env
# (free at https://api.nasa.gov/) to lift to 1000/hour.
NASA_API_KEY = os.environ.get("NASA_API_KEY", "DEMO_KEY")

# ── Column descriptions ──────────────────────────────────────────────
COLUMN_DESCRIPTIONS = {
    "date": "Date of the APOD entry in ISO format (YYYY-MM-DD); one entry per day since 1995-06-16; the primary key",
    "title": "Title of the astronomical image or media as chosen by the APOD editorial team; typically includes the object name or event described",
    "explanation": "Scientific explanation (~150-300 words) written by a professional astronomer; covers the physics, history, and significance of the featured subject; suitable for NLP, summarization, and astronomy education tasks",
    "url": "Primary media URL — direct image link or YouTube video URL; images are typically JPEG/PNG hosted on NASA GSFC servers",
    "hdurl": "Full-resolution (HD) image URL; null for video entries; typically 2000-8000px; may be very large",
    "media_type": "Content type: 'image' (majority) or 'video' (YouTube embeds); determines which URL fields are populated",
    "copyright": "Attribution string for the image author/photographer; null when the image is NASA, ESA, or other government agency public domain; ~30% of entries are copyrighted (amateur astrophotographers)",
    "thumbnail_url": "YouTube thumbnail URL for video entries; null for image entries; useful for visual preview without loading the full video",
    "is_public_domain": "True when copyright is null or empty, indicating NASA/ESA/public agency imagery with no usage restrictions; False for copyrighted astrophotography",
    "year": "Calendar year of the entry (1995–present); derived from date; useful for time-series analysis and filtering by solar cycle or mission era",
    "month": "Month (1–12) of the entry; derived from date; useful for seasonal sky analysis (e.g., summer Milky Way, winter Orion)",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Daily astronomy images and explanations from NASA's Astronomy Picture of the Day (APOD) \
program, the longest-running astronomy outreach initiative on the internet. Each entry \
features a curated astronomical image or video with a written explanation by a \
professional astronomer.

APOD has published one entry every day since June 16, 1995 — an unbroken 30-year record \
spanning more than 10,000 entries. The subjects range from the mundane to the profound: \
sunsets, aurora, meteor showers, deep galaxy fields from the Hubble Space Telescope, \
gravitational wave detections, exoplanet atmosphere spectroscopy, and images from every \
NASA mission. Each explanation is written in accessible but scientifically accurate \
language, making the corpus particularly valuable for training and evaluating astronomy \
language models.

This dataset captures the full structured metadata for every APOD entry: date, title, \
explanation text, media URL, copyright status, and media type. Roughly 70% of entries \
feature NASA or ESA imagery in the public domain; the remaining ~30% are copyrighted \
contributions from amateur astrophotographers around the world. The url and hdurl fields \
provide stable links to the original images, enabling this metadata to be used as an \
index for downloading visual training data. The explanation field alone constitutes \
roughly 2 million words of expert-authored astronomy prose.
"""


# ── Fetch helpers ────────────────────────────────────────────────────

def fetch_apod(start_date, end_date):
    """Fetch APOD entries for a date range. Returns list of dicts."""
    params = {
        "api_key": NASA_API_KEY,
        "start_date": start_date,
        "end_date": end_date,
        "thumbs": "True",
    }
    resp = requests.get(APOD_BASE, params=params, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    # API returns a list for multi-day ranges, a dict for single day
    if isinstance(data, dict):
        data = [data]
    return data


def fetch_full_rebuild():
    """Fetch all APOD entries year by year from 1995 to today."""
    now = datetime.utcnow()
    all_entries = []
    start_year = 1995

    for year in range(start_year, now.year + 1):
        if year == start_year:
            start_date = APOD_START
        else:
            start_date = f"{year}-01-01"

        if year < now.year:
            end_date = f"{year}-12-31"
        else:
            end_date = now.strftime("%Y-%m-%d")

        try:
            entries = fetch_apod(start_date, end_date)
            all_entries.extend(entries)
            print(f"    {year}: {len(entries)} entries")
        except Exception as e:
            print(f"    {year}: error - {e}")

        time.sleep(1)

    return all_entries


def parse_entries(raw_list):
    """Convert raw API dicts to flat DataFrame rows."""
    rows = []
    for entry in raw_list:
        rows.append({
            "date": entry.get("date"),
            "title": entry.get("title"),
            "explanation": entry.get("explanation"),
            "url": entry.get("url"),
            "hdurl": entry.get("hdurl") or None,
            "media_type": entry.get("media_type"),
            "copyright": entry.get("copyright") or None,
            "thumbnail_url": entry.get("thumbnail_url") or None,
        })
    return rows


def build_dataframe(rows):
    """Build and type-coerce the APOD DataFrame."""
    df = pd.DataFrame(rows)

    # Derived columns
    df["is_public_domain"] = df["copyright"].isna() | (df["copyright"].str.strip() == "")
    df["date_parsed"] = pd.to_datetime(df["date"], errors="coerce")
    df["year"] = df["date_parsed"].dt.year.astype("Int32")
    df["month"] = df["date_parsed"].dt.month.astype("Int32")
    df = df.drop(columns=["date_parsed"])

    # Enforce column order
    col_order = list(COLUMN_DESCRIPTIONS.keys())
    df = df[[c for c in col_order if c in df.columns]]

    return df


# ── Main pipeline ────────────────────────────────────────────────────

def main():
    print("Fetching NASA APOD entries...")
    now = datetime.utcnow()

    with Pipeline(
        repo=HF_REPO,
        pretty_name="NASA Astronomy Picture of the Day",
        description=DESCRIPTION,
        tags=["space", "nasa", "astronomy", "apod", "natural-language-processing",
              "image", "open-data", "tabular-data", "parquet"],
        source_url="https://apod.nasa.gov/apod/",
        task_categories=["tabular-classification", "text-classification"],
        update_schedule="Daily at 07:00 UTC",
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e001386/GSFC_20171208_Archive_e001386~medium.jpg",
            "alt": "Blue Marble — high-definition image of Earth from space",
            "credit": "NASA/GSFC/Suomi NPP",
        },
        related_datasets=[
            "juliensimon/hubble-space-telescope-observations",
            "juliensimon/james-webb-space-telescope-observations",
        ],
    ) as p:
        df_existing = p.download_existing("apod.parquet")

        if df_existing is not None and len(df_existing) > 0:
            # Incremental: fetch the overlap window
            df_existing["date"] = df_existing["date"].astype(str)
            max_date = pd.to_datetime(df_existing["date"]).max()
            fetch_from = (max_date - timedelta(days=OVERLAP_DAYS)).strftime("%Y-%m-%d")
            fetch_to = now.strftime("%Y-%m-%d")
            print(f"  Incremental fetch: {fetch_from} to {fetch_to}")

            try:
                raw = fetch_apod(fetch_from, fetch_to)
                rows = parse_entries(raw)
                df_new = build_dataframe(pd.DataFrame(rows) if rows else pd.DataFrame())
                print(f"  Fetched {len(df_new):,} entries in window")
            except Exception as e:
                print(f"  Fetch error: {e} — keeping existing data only")
                df_new = pd.DataFrame()

            if not df_new.empty:
                df = p.merge(df_existing, df_new, dedup_on="date", sort_by="date")
                print(f"  Merged: {len(df):,} entries ({len(df) - len(df_existing):+,} net)")
            else:
                df = df_existing
                print("  No new entries, keeping existing data")
        else:
            # Full rebuild year by year
            print("  Full rebuild from 1995...")
            raw = fetch_full_rebuild()
            rows = parse_entries(raw)
            df = build_dataframe(rows)
            print(f"  Full rebuild: {len(df):,} entries")

        # Ensure derived columns are present after merge (existing parquet may already have them)
        if "is_public_domain" not in df.columns:
            df["is_public_domain"] = df["copyright"].isna() | (df["copyright"].str.strip() == "")
        if "year" not in df.columns:
            df["year"] = pd.to_datetime(df["date"], errors="coerce").dt.year.astype("Int32")
        if "month" not in df.columns:
            df["month"] = pd.to_datetime(df["date"], errors="coerce").dt.month.astype("Int32")

        df = df.sort_values("date").reset_index(drop=True)

        # Enforce final column set
        col_order = list(COLUMN_DESCRIPTIONS.keys())
        df = df[[c for c in col_order if c in df.columns]]

        df = p.clean(
            df,
            strings=["title", "explanation", "url", "hdurl", "media_type", "copyright", "thumbnail_url"],
        )

        # ── Stats for README ─────────────────────────────────────────
        n_total = len(df)
        date_min = df["date"].min()
        date_max = df["date"].max()

        n_image = int((df["media_type"] == "image").sum())
        n_video = int((df["media_type"] == "video").sum())
        n_public = int(df["is_public_domain"].sum())
        n_copyright = n_total - n_public

        # Top astronomy words in titles
        title_words = []
        for title in df["title"].dropna():
            for word in title.split():
                w = word.strip(".,!?;:()[]\"'").lower()
                if len(w) > 3:
                    title_words.append(w)
        common_objects = ["galaxy", "nebula", "star", "moon", "comet", "sun",
                          "aurora", "supernova", "cluster", "jupiter", "saturn",
                          "mars", "eclipse", "milky"]
        word_counts = Counter(w for w in title_words if w in common_objects)
        top_words = ", ".join(
            f"**{w}** ({c:,})" for w, c in word_counts.most_common(5)
        )

        quick_stats = f"""\
- **{n_total:,}** entries ({date_min} to {date_max})
- **{n_image:,}** images, **{n_video:,}** videos
- **{n_public:,}** public domain entries (NASA/ESA), **{n_copyright:,}** copyrighted
- Most common subjects in titles: {top_words}"""

        usage = '''\
```python
from datasets import load_dataset
import pandas as pd

ds = load_dataset("juliensimon/nasa-apod", split="train")
df = ds.to_pandas()

# Public domain images only (safe to download/use)
public = df[df["is_public_domain"] == True]
print(f"{len(public):,} public domain entries with hdurl")

# Most popular topics by year
df["year"] = pd.to_numeric(df["year"])
topics = df[df["title"].str.contains("Galaxy|Nebula|Star|Comet|Moon", case=False, na=False)]
topics.groupby("year").size().plot(title="Cosmic Objects in APOD by Year")

# Recent entries
recent = df.sort_values("date").tail(10)[["date", "title", "media_type", "is_public_domain"]]
print(recent.to_string())
```
'''

        p.publish(
            df,
            filename="apod.parquet",
            min_rows=10000,
            expected_columns=["date", "title", "explanation", "url", "media_type"],
            critical_columns=["date", "title", "explanation"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update NASA APOD: {n_total:,} entries",
        )

    print("Done.")


if __name__ == "__main__":
    main()
