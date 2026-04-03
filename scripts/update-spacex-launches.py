#!/usr/bin/env python3
"""Fetch all SpaceX launch data from spacex.com and upload to HF.

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


def build_launches_df(tiles: list[dict], details: dict[str, dict]) -> pd.DataFrame:
    """Build the main launches DataFrame from tiles + detail data."""
    rows = []
    for tile in tiles:
        row = {col: tile.get(api_key) for api_key, col in TILE_FIELDS.items()}
        slug = row["slug"]

        # Enrich with detail data
        detail = details.get(slug, {})

        # Description: join paragraph HTML → plain text
        paragraphs = detail.get("paragraphs") or []
        desc_parts = [_strip_html(p.get("content", "")) for p in paragraphs if p.get("content")]
        row["description"] = "\n\n".join(desc_parts) if desc_parts else None

        # Astronauts
        astronauts = detail.get("astronauts") or []
        row["astronauts"] = json.dumps(astronauts) if astronauts else None

        # Webcasts
        webcasts = detail.get("webcasts") or []
        if webcasts:
            row["webcast_id"] = webcasts[0].get("videoId")
            row["webcast_platform"] = webcasts[0].get("streamingVideoType")
        else:
            row["webcast_id"] = None
            row["webcast_platform"] = None

        # Dragon tracking flags
        row["follow_dragon_enabled"] = detail.get("followDragonEnabled")

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
    df = pd.DataFrame(rows)
    print(f"  {len(df):,} timeline events")
    return df


def build_carousel_df(details: dict[str, dict]) -> pd.DataFrame:
    """Build the carousel DataFrame from detail data."""
    rows = []
    for slug, detail in details.items():
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
    df = pd.DataFrame(rows)
    print(f"  {len(df):,} carousel photos")
    return df


def download_carousel_images(carousel_df: pd.DataFrame, dest_dir: Path) -> int:
    """Download all carousel images. Returns count of successful downloads."""
    images_dir = dest_dir / "images"
    images_dir.mkdir(exist_ok=True)

    to_download = carousel_df.dropna(subset=["image_url", "image_path"])
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


def main():
    tiles = fetch_tiles()
    stats = fetch_stats()
    slugs = [t.get("link") for t in tiles if t.get("link")]
    details = fetch_mission_details(slugs)

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

        # Download carousel images
        n_images = download_carousel_images(carousel_df, tmp)

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
| `id` | string | SpaceX CMS identifier |
| `document_id` | string | CMS document reference |
| `title` | string | Mission name (e.g. "Starlink Mission") |
| `slug` | string | URL slug — primary key, join field |
| `mission_status` | string | `final`, `upcoming`, or `in-progress` |
| `mission_type` | string | starlink, commercialSatellite, resupply, nssl, hsf, rideshare, science, starship |
| `vehicle` | string | Falcon 9, Falcon Heavy, Starship, Falcon 1 |
| `launch_site` | string | Launch location (e.g. "SLC-40, Florida") |
| `launch_date` | date | Launch date |
| `launch_time` | string | Launch time (HH:MM:SS UTC) |
| `return_site` | string | Landing site (e.g. "Droneship") |
| `return_date_time` | string | Return timestamp (if available) |
| `end_date` | date | Mission end date (if available) |
| `end_time` | string | Mission end time (if available) |
| `direct_to_cell` | bool | Direct-to-cell mission flag |
| `is_live` | bool | Currently live flag |
| `description` | string | Full mission description (plain text from HTML) |
| `astronauts` | string | JSON array of astronaut data (crewed missions) |
| `webcast_id` | string | Webcast video ID |
| `webcast_platform` | string | Streaming platform (e.g. "x.com") |
| `follow_dragon_enabled` | bool | Dragon tracking available |
| `launch_datetime` | datetime | Combined launch date + time |
| `launch_year` | int | Year of launch (derived) |
| `success` | bool | True if mission_status is "final" |
| `has_landing` | bool | True if return_site is present |

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
- **{n_photos:,}** carousel photos ({n_images:,} downloaded)
- SpaceX totals: {total_launches:,} launches, {total_landings} landings, {total_reflights} reflights

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

Monthly rebuild via GitHub Actions.

## Related datasets

- [launch-log](https://huggingface.co/datasets/juliensimon/launch-log) — McDowell launch log (all providers)
- [launch-cost](https://huggingface.co/datasets/juliensimon/launch-cost) — Historical launch costs
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
