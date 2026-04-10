#!/usr/bin/env python3
"""Fetch all SpaceX launch data from spacex.com and upload to HF.

Incremental mode: downloads existing data from HF, fetches fresh tiles,
identifies new or changed launches, and only fetches details + images for those.
Falls back to full rebuild if no existing data.

Collects launch summaries, mission descriptions, pre/post-launch timelines,
and carousel images from the official SpaceX content API.
"""

import json
import os
import re
import subprocess
import tempfile
import time
from html import unescape
from pathlib import Path

import pandas as pd
import requests

from dataset_images import banner_markdown, download_banner
from validate import check_dataset

HF_REPO = "juliensimon/spacex-launches"

TILES_API = "https://content.spacex.com/api/spacex-website/launches-page-tiles"
STATS_API = "https://content.spacex.com/api/spacex-website/launches-page-stats"
MISSIONS_API = "https://content.spacex.com/api/spacex-website/missions"

HEADERS = {
    "User-Agent": "space-datasets/1.0 (https://github.com/juliensimon/space-datasets)"
}
TIMEOUT = 60
DETAIL_DELAY = 0.3  # seconds between detail API calls
IMAGE_DELAY = 0.1   # seconds between image downloads
MAX_RETRIES = 3

MIN_ROWS = 500

# camelCase API → snake_case columns
TILE_FIELDS = {
    "id": "id",
    "documentId": "document_id",
    "title": "title",
    "link": "slug",
    "missionStatus": "mission_status",
    "missionType": "mission_type",
    "vehicle": "vehicle",
    "launchSite": "launch_site",
    "launchDate": "launch_date",
    "launchTime": "launch_time",
    "returnSite": "return_site",
    "returnDateTime": "return_date_time",
    "endDate": "end_date",
    "endTime": "end_time",
    "directToCell": "direct_to_cell",
    "isLive": "is_live",
}


def _strip_html(html: str) -> str:
    """Remove HTML tags and decode entities to plain text."""
    text = re.sub(r"<[^>]+>", "", html)
    return unescape(text).strip()


def _get_json(url: str, timeout: int = TIMEOUT) -> dict | list:
    """GET JSON with retries and exponential backoff. Raises on 404."""
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout)
            if resp.status_code == 404:
                raise requests.HTTPError("404", response=resp)
            resp.raise_for_status()
            return resp.json()
        except requests.HTTPError as e:
            if resp.status_code == 404:
                raise  # don't retry 404s — permanent
            if attempt < MAX_RETRIES - 1:
                wait = 2 ** attempt
                print(f"  Retry {attempt + 1}/{MAX_RETRIES} for {url}: {e}")
                time.sleep(wait)
            else:
                raise
        except (requests.RequestException, ValueError) as e:
            if attempt < MAX_RETRIES - 1:
                wait = 2 ** attempt
                print(f"  Retry {attempt + 1}/{MAX_RETRIES} for {url}: {e}")
                time.sleep(wait)
            else:
                raise


def _download_image(url: str, dest: Path) -> bool:
    """Download an image file. Returns True on success."""
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30, stream=True)
            resp.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(8192):
                    f.write(chunk)
            return True
        except requests.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
            else:
                print(f"  Warning: failed to download {url}: {e}")
                return False


def fetch_tiles() -> list[dict]:
    """Fetch all launch tiles (summary data)."""
    print("Fetching SpaceX launch tiles...")
    tiles = _get_json(TILES_API)
    print(f"  {len(tiles):,} launches from tiles API")
    return tiles


def fetch_stats() -> dict:
    """Fetch aggregate launch statistics."""
    print("Fetching SpaceX launch stats...")
    return _get_json(STATS_API)


def fetch_mission_details(slugs: list[str]) -> dict[str, dict]:
    """Fetch detail data for each launch by slug."""
    if not slugs:
        return {}
    print(f"Fetching mission details for {len(slugs):,} launches...")
    details = {}
    for i, slug in enumerate(slugs):
        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{len(slugs)}")
        try:
            data = _get_json(f"{MISSIONS_API}/{slug}")
            details[slug] = data
        except Exception as e:
            print(f"  Warning: no detail for {slug}: {e}")
        time.sleep(DETAIL_DELAY)
    print(f"  Got details for {len(details):,} launches")
    return details


def load_existing(tmp_dir: Path) -> tuple[pd.DataFrame | None, pd.DataFrame | None, pd.DataFrame | None]:
    """Download existing parquet files from HF. Returns (launches, timelines, carousel) or Nones."""
    try:
        subprocess.run(
            ["hf", "download", HF_REPO, "data/launches.parquet",
             "data/timelines.parquet", "data/carousel.parquet",
             "--repo-type", "dataset", "--local-dir", str(tmp_dir)],
            check=True, capture_output=True, timeout=60,
        )
        launches_path = tmp_dir / "data" / "launches.parquet"
        timelines_path = tmp_dir / "data" / "timelines.parquet"
        carousel_path = tmp_dir / "data" / "carousel.parquet"

        if not launches_path.exists():
            return None, None, None

        df_launches = pd.read_parquet(launches_path)
        df_timelines = pd.read_parquet(timelines_path) if timelines_path.exists() else pd.DataFrame()
        df_carousel = pd.read_parquet(carousel_path) if carousel_path.exists() else pd.DataFrame()

        print(f"  Loaded existing: {len(df_launches):,} launches, "
              f"{len(df_timelines):,} timelines, {len(df_carousel):,} carousel")
        return df_launches, df_timelines, df_carousel
    except Exception as e:
        print(f"  Could not load existing ({e}), doing full rebuild")
        return None, None, None


def find_changed_slugs(tiles: list[dict], existing_df: pd.DataFrame) -> list[str]:
    """Compare fresh tiles against existing data. Return slugs that need detail refresh.

    A slug needs refresh if:
    - It's completely new (not in existing data)
    - Its mission_status changed (e.g. upcoming → final)
    - It has no description in existing data (detail fetch failed last time)
    """
    existing_status = dict(zip(existing_df["slug"], existing_df["mission_status"]))
    existing_desc = set(
        existing_df.loc[existing_df["description"].notna(), "slug"]
    ) if "description" in existing_df.columns else set()

    changed = []
    for tile in tiles:
        slug = tile.get("link")
        if not slug:
            continue
        new_status = tile.get("missionStatus")
        old_status = existing_status.get(slug)

        if old_status is None:
            changed.append(slug)  # new launch
        elif old_status != new_status:
            changed.append(slug)  # status changed
        elif slug not in existing_desc:
            changed.append(slug)  # missing description from prior failed fetch

    return changed


def _extract_detail_fields(detail: dict) -> dict:
    """Extract detail-enrichment fields from a mission detail response."""
    paragraphs = detail.get("paragraphs") or []
    desc_parts = [_strip_html(p.get("content", "")) for p in paragraphs if p.get("content")]

    astronauts = detail.get("astronauts") or []
    webcasts = detail.get("webcasts") or []

    return {
        "description": "\n\n".join(desc_parts) if desc_parts else None,
        "astronauts": json.dumps(astronauts) if astronauts else None,
        "webcast_id": webcasts[0].get("videoId") if webcasts else None,
        "webcast_platform": webcasts[0].get("streamingVideoType") if webcasts else None,
        "follow_dragon_enabled": detail.get("followDragonEnabled"),
    }


def _extract_timelines(slug: str, detail: dict) -> list[dict]:
    """Extract timeline rows from a mission detail response."""
    rows = []
    for phase, key in [("pre_launch", "preLaunchTimeline"), ("post_launch", "postLaunchTimeline")]:
        timeline = detail.get(key) or {}
        entries = timeline.get("timelineEntries") or []
        for entry in entries:
            rows.append({
                "slug": slug,
                "phase": phase,
                "event_time": entry.get("time"),
                "description": entry.get("description"),
            })
    return rows


def _extract_carousel(slug: str, detail: dict) -> list[dict]:
    """Extract carousel rows from a mission detail response."""
    rows = []
    carousel = detail.get("carousel") or {}
    items = carousel.get("carouselItems") or []
    for idx, item in enumerate(items):
        image = item.get("imageDesktop") or {}
        image_url = image.get("url")
        if image_url and not image_url.startswith("http"):
            image_url = f"https://sxcontent9668.azureedge.us{image_url}"
        ext = Path(image_url).suffix[:4] if image_url else ".jpg"
        rows.append({
            "slug": slug,
            "caption": item.get("caption"),
            "image_url": image_url,
            "image_path": f"images/{slug}_{idx}{ext}" if image_url else None,
        })
    return rows


def build_launches_df(tiles: list[dict], details: dict[str, dict]) -> pd.DataFrame:
    """Build the main launches DataFrame from tiles + detail data."""
    rows = []
    for tile in tiles:
        row = {col: tile.get(api_key) for api_key, col in TILE_FIELDS.items()}
        slug = row["slug"]
        detail = details.get(slug, {})
        row.update(_extract_detail_fields(detail))
        rows.append(row)

    df = pd.DataFrame(rows)

    # Type coercion
    df["launch_date"] = pd.to_datetime(df["launch_date"], errors="coerce")
    df["end_date"] = pd.to_datetime(df["end_date"], errors="coerce")

    # Derived columns
    df["launch_datetime"] = pd.to_datetime(
        df["launch_date"].dt.strftime("%Y-%m-%d").fillna("") + "T" + df["launch_time"].fillna(""),
        errors="coerce",
    )
    df["launch_year"] = df["launch_datetime"].dt.year.astype("Int64")
    df["success"] = df["mission_status"] == "final"
    df["has_landing"] = df["return_site"].notna() & (df["return_site"] != "")

    # Sort by launch date descending (most recent first)
    df = df.sort_values("launch_datetime", ascending=False, na_position="last").reset_index(drop=True)

    return df


def build_timelines_df(details: dict[str, dict]) -> pd.DataFrame:
    """Build the timelines DataFrame from detail data."""
    rows = []
    for slug, detail in details.items():
        rows.extend(_extract_timelines(slug, detail))
    df = pd.DataFrame(rows)
    print(f"  {len(df):,} timeline events")
    return df


def build_carousel_df(details: dict[str, dict]) -> pd.DataFrame:
    """Build the carousel DataFrame from detail data."""
    rows = []
    for slug, detail in details.items():
        rows.extend(_extract_carousel(slug, detail))
    df = pd.DataFrame(rows)
    print(f"  {len(df):,} carousel photos")
    return df


def download_carousel_images(carousel_df: pd.DataFrame, dest_dir: Path,
                             skip_slugs: set[str] | None = None) -> int:
    """Download carousel images. Skip slugs already present. Returns success count."""
    images_dir = dest_dir / "images"
    images_dir.mkdir(exist_ok=True)

    to_download = carousel_df.dropna(subset=["image_url", "image_path"])
    if skip_slugs:
        to_download = to_download[~to_download["slug"].isin(skip_slugs)]

    if to_download.empty:
        print("No new carousel images to download.")
        return 0

    print(f"Downloading {len(to_download):,} carousel images...")
    success = 0
    for i, (_, row) in enumerate(to_download.iterrows()):
        if (i + 1) % 100 == 0:
            print(f"  {i + 1}/{len(to_download)}")
        dest = dest_dir / row["image_path"]
        if _download_image(row["image_url"], dest):
            success += 1
        time.sleep(IMAGE_DELAY)

    print(f"  {success:,}/{len(to_download):,} images downloaded")
    return success


def download_existing_images(carousel_df: pd.DataFrame, dest_dir: Path,
                             slugs_to_keep: set[str]) -> int:
    """Download already-uploaded images from HF for unchanged launches."""
    images_dir = dest_dir / "images"
    images_dir.mkdir(exist_ok=True)

    to_fetch = carousel_df[
        carousel_df["slug"].isin(slugs_to_keep)
        & carousel_df["image_path"].notna()
    ]
    if to_fetch.empty:
        return 0

    # Download all images from HF in one go
    image_paths = to_fetch["image_path"].tolist()
    print(f"Downloading {len(image_paths):,} existing images from HF...")
    try:
        subprocess.run(
            ["hf", "download", HF_REPO, *image_paths,
             "--repo-type", "dataset", "--local-dir", str(dest_dir)],
            check=True, capture_output=True, timeout=120,
        )
        count = sum(1 for p in image_paths if (dest_dir / p).exists())
        print(f"  {count:,} existing images restored from HF")
        return count
    except Exception as e:
        print(f"  Warning: could not restore existing images ({e})")
        return 0


def main():
    tiles = fetch_tiles()
    stats = fetch_stats()

    # Try incremental: load existing data from HF
    with tempfile.TemporaryDirectory() as probe:
        probe = Path(probe)
        existing_launches, existing_timelines, existing_carousel = load_existing(probe)

    incremental = existing_launches is not None and len(existing_launches) > 0

    if incremental:
        changed_slugs = find_changed_slugs(tiles, existing_launches)
        all_slugs = [t.get("link") for t in tiles if t.get("link")]
        unchanged_slugs = set(all_slugs) - set(changed_slugs)

        if changed_slugs:
            print(f"Incremental: {len(changed_slugs)} new/changed, "
                  f"{len(unchanged_slugs)} unchanged")
            new_details = fetch_mission_details(changed_slugs)
        else:
            print("Incremental: no changes detected")
            new_details = {}

        # Build detail dict: reuse existing detail-enriched fields for unchanged,
        # use fresh API data for changed
        # For unchanged slugs, reconstruct a pseudo-detail dict from existing parquet
        details = {}
        for slug in all_slugs:
            if slug in new_details:
                details[slug] = new_details[slug]
            elif slug in unchanged_slugs:
                # Reconstruct from existing parquet row
                row = existing_launches[existing_launches["slug"] == slug]
                if not row.empty:
                    r = row.iloc[0]
                    details[slug] = {"_from_existing": True, "_row": r}

        # Build launches df from tiles + merged details
        print("Building DataFrames...")
        rows = []
        for tile in tiles:
            row = {col: tile.get(api_key) for api_key, col in TILE_FIELDS.items()}
            slug = row["slug"]
            detail = details.get(slug, {})

            if detail.get("_from_existing"):
                # Reuse existing detail fields
                r = detail["_row"]
                row["description"] = r.get("description") if pd.notna(r.get("description")) else None
                row["astronauts"] = r.get("astronauts") if pd.notna(r.get("astronauts")) else None
                row["webcast_id"] = r.get("webcast_id") if pd.notna(r.get("webcast_id")) else None
                row["webcast_platform"] = r.get("webcast_platform") if pd.notna(r.get("webcast_platform")) else None
                row["follow_dragon_enabled"] = r.get("follow_dragon_enabled")
            else:
                row.update(_extract_detail_fields(detail))
            rows.append(row)

        df = pd.DataFrame(rows)
        df["launch_date"] = pd.to_datetime(df["launch_date"], errors="coerce")
        df["end_date"] = pd.to_datetime(df["end_date"], errors="coerce")
        df["launch_datetime"] = pd.to_datetime(
            df["launch_date"].dt.strftime("%Y-%m-%d").fillna("") + "T" + df["launch_time"].fillna(""),
            errors="coerce",
        )
        df["launch_year"] = df["launch_datetime"].dt.year.astype("Int64")
        df["success"] = df["mission_status"] == "final"
        df["has_landing"] = df["return_site"].notna() & (df["return_site"] != "")
        df = df.sort_values("launch_datetime", ascending=False, na_position="last").reset_index(drop=True)

        # Timelines: keep existing for unchanged slugs, add new
        new_timeline_rows = []
        for slug in changed_slugs:
            if slug in new_details:
                new_timeline_rows.extend(_extract_timelines(slug, new_details[slug]))
        new_timelines = pd.DataFrame(new_timeline_rows) if new_timeline_rows else pd.DataFrame(
            columns=["slug", "phase", "event_time", "description"])

        if existing_timelines is not None and not existing_timelines.empty:
            kept_timelines = existing_timelines[existing_timelines["slug"].isin(unchanged_slugs)]
            timelines_df = pd.concat([kept_timelines, new_timelines], ignore_index=True)
        else:
            timelines_df = new_timelines
        print(f"  {len(timelines_df):,} timeline events")

        # Carousel: keep existing for unchanged slugs, add new
        new_carousel_rows = []
        for slug in changed_slugs:
            if slug in new_details:
                new_carousel_rows.extend(_extract_carousel(slug, new_details[slug]))
        new_carousel = pd.DataFrame(new_carousel_rows) if new_carousel_rows else pd.DataFrame(
            columns=["slug", "caption", "image_url", "image_path"])

        if existing_carousel is not None and not existing_carousel.empty:
            kept_carousel = existing_carousel[existing_carousel["slug"].isin(unchanged_slugs)]
            carousel_df = pd.concat([kept_carousel, new_carousel], ignore_index=True)
        else:
            carousel_df = new_carousel
        print(f"  {len(carousel_df):,} carousel photos")

    else:
        # Full rebuild
        print("Full rebuild mode")
        all_slugs = [t.get("link") for t in tiles if t.get("link")]
        details = fetch_mission_details(all_slugs)
        changed_slugs = all_slugs
        unchanged_slugs = set()

        print("Building DataFrames...")
        df = build_launches_df(tiles, details)
        timelines_df = build_timelines_df(details)
        carousel_df = build_carousel_df(details)

    check_dataset(
        df, "spacex-launches",
        min_rows=MIN_ROWS,
        expected_columns=["title", "vehicle", "launch_date", "mission_status",
                          "launch_site", "slug", "mission_type"],
        critical_columns=["title", "vehicle", "launch_date"],
        incremental=incremental,
    )

    # ── Stats for README ────────────────────────────────────────────────
    n = len(df)
    n_completed = int((df["mission_status"] == "final").sum())
    n_upcoming = int((df["mission_status"] == "upcoming").sum())
    vehicles = df["vehicle"].value_counts()
    vehicles_str = ", ".join(f"{v} ({c:,})" for v, c in vehicles.items())
    mission_types = df["mission_type"].value_counts().head(5)
    types_str = ", ".join(f"{t} ({c:,})" for t, c in mission_types.items())
    n_landings = int(df["has_landing"].sum())
    n_with_desc = int(df["description"].notna().sum())
    n_timeline_events = len(timelines_df)
    n_photos = len(carousel_df)
    year_min = int(df["launch_year"].min()) if df["launch_year"].notna().any() else "?"
    year_max = int(df["launch_year"].max()) if df["launch_year"].notna().any() else "?"

    total_launches = stats.get("totalLaunches", n_completed)
    total_landings = stats.get("totalLandings", "N/A")
    total_reflights = stats.get("totalReflights", "N/A")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        # Write parquet files
        launches_out = data_dir / "launches.parquet"
        df.to_parquet(launches_out, index=False, engine="pyarrow", compression="zstd")
        print(f"  launches.parquet: {launches_out.stat().st_size / 1024:.0f} KB")

        timelines_out = data_dir / "timelines.parquet"
        timelines_df.to_parquet(timelines_out, index=False, engine="pyarrow", compression="zstd")
        print(f"  timelines.parquet: {timelines_out.stat().st_size / 1024:.0f} KB")

        carousel_out = data_dir / "carousel.parquet"
        carousel_df.to_parquet(carousel_out, index=False, engine="pyarrow", compression="zstd")
        print(f"  carousel.parquet: {carousel_out.stat().st_size / 1024:.0f} KB")

        # Images: restore unchanged from HF, download new from CDN
        if incremental and unchanged_slugs:
            download_existing_images(carousel_df, tmp, unchanged_slugs)
        download_carousel_images(carousel_df, tmp, skip_slugs=unchanged_slugs if incremental else None)

        # Banner
        banner_file = download_banner("spacex-launches", tmp)
        banner_md = banner_markdown("spacex-launches", banner_file)

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "SpaceX Launch History"
language:
  - en
description: >-
  Complete SpaceX launch history from spacex.com — all {n:,} Falcon 9, Falcon Heavy,
  Starship, and Falcon 1 missions with vehicle, site, status, landing, mission descriptions,
  pre/post-launch timelines, and carousel photos.
size_categories:
  - n<1K
task_categories:
  - tabular-classification
tags:
  - space
  - spacex
  - falcon-9
  - falcon-heavy
  - starship
  - rocket-launch
  - orbital-mechanics
  - launch-history
  - open-data
  - tabular-data
  - parquet
configs:
  - config_name: launches
    data_files:
      - split: train
        path: data/launches.parquet
    default: true
  - config_name: timelines
    data_files:
      - split: train
        path: data/timelines.parquet
  - config_name: carousel
    data_files:
      - split: train
        path: data/carousel.parquet
---

# SpaceX Launch History
{banner_md}
*Part of the [Satellites & Launches Datasets](https://huggingface.co/collections/juliensimon/satellites-launches-datasets-67b4e0f9418e9f467c5e0e67) collection on Hugging Face.*

Complete record of every SpaceX launch from spacex.com — **{n:,}** missions
({year_min}–{year_max}), including mission descriptions, pre/post-launch timelines,
and photo galleries.

## Dataset description

This dataset captures the full content of every launch page on [spacex.com/launches](https://www.spacex.com/launches),
spanning from the first Falcon 1 test flights through the latest Starship missions.
It includes structured timeline data for each launch phase (countdown, ascent,
stage separation, landing, payload deployment), mission descriptions, webcast references,
and carousel imagery.

The data is organized into three tables that can be joined on the `slug` field:
- **launches** — one row per mission with all metadata, descriptions, and derived fields
- **timelines** — one row per countdown/deployment event across all missions
- **carousel** — one row per photo with captions and image paths

SpaceX reports **{total_launches:,}** total launches, **{total_landings}** landings,
and **{total_reflights}** reflights as of the latest update.

## Schema — launches ({n:,} rows)

| Column | Type | Description |
|--------|------|-------------|
| `id` | string | Internal SpaceX CMS (Strapi) identifier; opaque string, stable within the CMS |
| `document_id` | string | CMS document reference used for CMS versioning; opaque, not meaningful for analysis |
| `title` | string | Human-readable mission name from spacex.com (e.g. "Starlink Mission", "CRS-25", "Intuitive Machines-1") |
| `slug` | string | URL slug used as the primary key and join field across all three tables (e.g. "sl-10-22"); unique per mission |
| `mission_status` | string | Mission lifecycle state: "final" = completed and results confirmed, "upcoming" = not yet launched, "in-progress" = currently executing |
| `mission_type` | string | Mission category: "starlink" (Starlink constellation replenishment), "commercialSatellite" (third-party GEO/LEO satellite), "resupply" (ISS cargo), "nssl" (National Security Space Launch), "hsf" (human spaceflight), "rideshare" (SmallSat Rideshare), "science" (NASA/research payload), "starship" (Starship test flight) |
| `vehicle` | string | Launch vehicle variant: "Falcon 9", "Falcon Heavy", "Starship", or "Falcon 1" (retired) |
| `launch_site` | string | Launch complex and geographic location (e.g. "SLC-40, Florida", "LC-39A, Florida", "SLC-4E, California") |
| `launch_date` | date | UTC calendar date of launch (YYYY-MM-DD); null for upcoming missions without a confirmed date |
| `launch_time` | string | UTC launch time in HH:MM:SS format; null for unconfirmed upcoming launches |
| `return_site` | string | First-stage landing site (e.g. "LZ-1", "LZ-2", "JRTI" droneship, "OCISLY" droneship); null if no landing attempted or vehicle expended |
| `return_date_time` | string | Timestamp of first-stage return/landing (if available); null for expendable flights or when not recorded |
| `end_date` | date | Mission completion date (e.g. Dragon splashdown, satellite handoff); null if ongoing or not recorded |
| `end_time` | string | Mission completion time (UTC HH:MM:SS); null if not recorded |
| `direct_to_cell` | bool | True for Starlink Direct-to-Cell missions (satellites with cellular connectivity capability) |
| `is_live` | bool | True if the mission is currently streaming live; intended for real-time use; typically False in archived data |
| `description` | string | Full plaintext mission description sourced from spacex.com (HTML stripped); null for missions without a published description |
| `astronauts` | string | JSON array of crew member data (name, title, image) for crewed missions; null for uncrewed flights |
| `webcast_id` | string | Video identifier for the official launch webcast; null if no webcast was published |
| `webcast_platform` | string | Streaming platform hosting the webcast (e.g. "x.com", "youtube"); null if no webcast |
| `follow_dragon_enabled` | bool | True if real-time Dragon capsule tracking was available for this mission; null for non-Dragon missions |
| `launch_datetime` | datetime | Combined UTC launch datetime (date + time); null if launch_time is not available |
| `launch_year` | int | Calendar year of launch derived from launch_date; useful for time-series grouping; null if launch_date is null |
| `success` | bool | True if mission_status == "final" (mission completed); False for upcoming or in-progress; proxy for mission success |
| `has_landing` | bool | True if return_site is non-null, indicating a first-stage landing was recorded; does not distinguish success from failure |

## Schema — timelines ({n_timeline_events:,} rows)

| Column | Type | Description |
|--------|------|-------------|
| `slug` | string | FK to launches.slug |
| `phase` | string | `pre_launch` or `post_launch` |
| `event_time` | string | Relative time (e.g. "00:01:12") |
| `description` | string | Event description (e.g. "Max Q") |

## Schema — carousel ({n_photos:,} rows)

| Column | Type | Description |
|--------|------|-------------|
| `slug` | string | FK to launches.slug |
| `caption` | string | Photo caption |
| `image_url` | string | Original CDN URL |
| `image_path` | string | Local path in dataset (e.g. `images/sl-10-22_0.jpg`) |

## Quick stats

- **{n:,}** total missions ({n_completed:,} completed, {n_upcoming:,} upcoming)
- **Vehicles**: {vehicles_str}
- **Top mission types**: {types_str}
- **{n_landings:,}** missions with landing data
- **{n_with_desc:,}** missions with descriptions
- **{n_timeline_events:,}** timeline events across all missions
- **{n_photos:,}** carousel photos

## Usage

```python
from datasets import load_dataset

# Load main launches table
launches = load_dataset("juliensimon/spacex-launches", "launches", split="train")
df = launches.to_pandas()

# Falcon 9 missions
f9 = df[df["vehicle"] == "Falcon 9"]
print(f"{{len(f9):,}} Falcon 9 launches")

# Launches by year
print(df.groupby("launch_year").size())

# Starlink missions
starlink = df[df["mission_type"] == "starlink"]
print(f"{{len(starlink):,}} Starlink missions")

# Load timelines and join
timelines = load_dataset("juliensimon/spacex-launches", "timelines", split="train")
tl = timelines.to_pandas()

# Get post-launch events for a specific mission
events = tl[(tl["slug"] == "sl-10-22") & (tl["phase"] == "post_launch")]
print(events[["event_time", "description"]])

# Load carousel
carousel = load_dataset("juliensimon/spacex-launches", "carousel", split="train")
photos = carousel.to_pandas()
print(f"{{len(photos):,}} photos across all missions")
```

## Data source

[spacex.com/launches](https://www.spacex.com/launches) — official SpaceX website.
Data sourced from the SpaceX content API (Strapi CMS).

## Update schedule

Daily incremental updates via GitHub Actions.

## Related datasets

- [launch-log](https://huggingface.co/datasets/juliensimon/space-launch-log) — McDowell launch log (all providers)
- [launch-cost](https://huggingface.co/datasets/juliensimon/launch-cost-to-leo) — Historical launch costs
- [launch-vehicles](https://huggingface.co/datasets/juliensimon/launch-vehicles) — Rocket specifications
- [starlink](https://huggingface.co/datasets/juliensimon/starlink-fleet-data) — Starlink constellation snapshots

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/spacex-launches) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{spacex_launches,
  author = {{Simon, Julien}},
  title = {{SpaceX Launch History}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/spacex-launches}},
  note = {{Sourced from spacex.com}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/) — Data sourced from spacex.com.
""")

        print("Uploading to HF...")
        commit_msg = f"Update SpaceX launches: {n:,} missions, {n_timeline_events:,} events, {n_photos:,} photos"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={n}\n")
    print("Done.")


if __name__ == "__main__":
    main()
