#!/usr/bin/env python3
"""Fetch all SpaceX launch data from spacex.com and upload to HF.

Incremental mode: downloads existing data from HF, fetches fresh tiles,
identifies new or changed launches, and only fetches details + images for those.
Falls back to full rebuild if no existing data.

Collects launch summaries, mission descriptions, pre/post-launch timelines,
and carousel images from the official SpaceX content API.

Source: spacex.com/launches (SpaceX Strapi CMS)
"""

import json
import re
import subprocess
import time
from html import unescape
from pathlib import Path

import pandas as pd
import requests

from hf_dataset_utils import Pipeline
from hf_dataset_utils.upload import write_parquet

HF_REPO = "juliensimon/spacex-launches"

TILES_API = "https://content.spacex.com/api/spacex-website/launches-page-tiles"
STATS_API = "https://content.spacex.com/api/spacex-website/launches-page-stats"
MISSIONS_API = "https://content.spacex.com/api/spacex-website/missions"

HEADERS = {
    "User-Agent": "space-datasets/1.0 (https://github.com/juliensimon/space-datasets)"
}
TIMEOUT = 60
DETAIL_DELAY = 0.3
IMAGE_DELAY = 0.1
MAX_RETRIES = 3
MIN_ROWS = 500

# camelCase API -> snake_case columns
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

# ── Column descriptions ─────────────────────────────────────────────
COLUMN_DESCRIPTIONS = {
    "id": "Internal SpaceX CMS (Strapi) identifier; opaque string, stable within the CMS",
    "document_id": "CMS document reference used for CMS versioning; opaque, not meaningful for analysis",
    "title": "Human-readable mission name from spacex.com (e.g. 'Starlink Mission', 'CRS-25', 'Intuitive Machines-1')",
    "slug": "URL slug used as the primary key and join field across all three tables (e.g. 'sl-10-22'); unique per mission",
    "mission_status": "Mission lifecycle state: 'final' = completed, 'upcoming' = not yet launched, 'in-progress' = currently executing",
    "mission_type": "Mission category: 'starlink', 'commercialSatellite', 'resupply', 'nssl', 'hsf', 'rideshare', 'science', 'starship'",
    "vehicle": "Launch vehicle variant: 'Falcon 9', 'Falcon Heavy', 'Starship', or 'Falcon 1' (retired)",
    "launch_site": "Launch complex and geographic location (e.g. 'SLC-40, Florida', 'LC-39A, Florida', 'SLC-4E, California')",
    "launch_date": "UTC calendar date of launch (YYYY-MM-DD); null for upcoming missions without a confirmed date",
    "launch_time": "UTC launch time in HH:MM:SS format; null for unconfirmed upcoming launches",
    "return_site": "First-stage landing site (e.g. 'LZ-1', 'JRTI' droneship, 'OCISLY' droneship); null if no landing attempted",
    "return_date_time": "Timestamp of first-stage return/landing (if available); null for expendable flights",
    "end_date": "Mission completion date (e.g. Dragon splashdown, satellite handoff); null if ongoing or not recorded",
    "end_time": "Mission completion time (UTC HH:MM:SS); null if not recorded",
    "direct_to_cell": "True for Starlink Direct-to-Cell missions (satellites with cellular connectivity capability)",
    "is_live": "True if the mission is currently streaming live; typically False in archived data",
    "description": "Full plaintext mission description sourced from spacex.com (HTML stripped); null for missions without a published description",
    "astronauts": "JSON array of crew member data (name, title, image) for crewed missions; null for uncrewed flights",
    "webcast_id": "Video identifier for the official launch webcast; null if no webcast was published",
    "webcast_platform": "Streaming platform hosting the webcast (e.g. 'x.com', 'youtube'); null if no webcast",
    "follow_dragon_enabled": "True if real-time Dragon capsule tracking was available for this mission; null for non-Dragon missions",
    "launch_datetime": "Combined UTC launch datetime (date + time); null if launch_time is not available",
    "launch_year": "Calendar year of launch derived from launch_date; useful for time-series grouping; null if launch_date is null",
    "success": "True if mission_status == 'final' (mission completed); False for upcoming or in-progress",
    "has_landing": "True if return_site is non-null, indicating a first-stage landing was recorded",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Complete record of every SpaceX launch from spacex.com, including mission descriptions, \
pre/post-launch timelines, and photo galleries. Covers Falcon 1, Falcon 9, Falcon Heavy, \
and Starship missions.

The data is sourced from the official SpaceX content API and organized into three tables \
that can be joined on the slug field: launches (one row per mission with all metadata), \
timelines (countdown/deployment events), and carousel (mission photos with captions).

SpaceX has transformed the economics of spaceflight through first-stage reuse, achieving \
rapid launch cadence with Falcon 9 and developing Starship as the next-generation fully \
reusable vehicle.\
"""


# ── Fetch helpers (kept from original) ───────────────────────────────

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
        except requests.HTTPError:
            if resp.status_code == 404:
                raise
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
            else:
                raise
        except (requests.RequestException, ValueError) as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
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
        except requests.RequestException:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
            else:
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


def find_changed_slugs(tiles: list[dict], existing_df: pd.DataFrame) -> list[str]:
    """Compare fresh tiles against existing data. Return slugs that need detail refresh."""
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
            changed.append(slug)
        elif old_status != new_status:
            changed.append(slug)
        elif slug not in existing_desc:
            changed.append(slug)

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


def load_existing_parquets(p: Pipeline) -> tuple:
    """Download all three existing parquet files. Returns (launches, timelines, carousel) or Nones."""
    launches = p.download_existing("launches.parquet")
    timelines = p.download_existing("timelines.parquet")
    carousel = p.download_existing("carousel.parquet")
    return launches, timelines, carousel


# ── Main pipeline ────────────────────────────────────────────────────

def main():
    tiles = fetch_tiles()
    stats = fetch_stats()

    with Pipeline(
        repo=HF_REPO,
        pretty_name="SpaceX Launch History",
        description=DESCRIPTION,
        tags=["space", "spacex", "falcon-9", "falcon-heavy", "starship",
              "rocket-launch", "orbital-mechanics", "launch-history",
              "open-data", "tabular-data", "parquet"],
        source_url="https://www.spacex.com/launches",
        task_categories=["tabular-classification"],
        update_schedule="Daily incremental updates via GitHub Actions",
        collection_url="https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994",
        banner={
            "url": "https://images-assets.nasa.gov/image/iss071e439624/iss071e439624~medium.jpg",
            "alt": "An orbital sunrise illuminates the Earth's atmosphere, seen from the ISS",
            "credit": "NASA",
        },
        related_datasets=[
            "juliensimon/space-launch-log",
            "juliensimon/launch-cost-to-leo",
            "juliensimon/launch-vehicles",
            "juliensimon/starlink-fleet-data",
        ],
    ) as p:
        # Try incremental
        existing_launches, existing_timelines, existing_carousel = load_existing_parquets(p)
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

            # Build detail dict: reuse existing for unchanged, fresh for changed
            details = {}
            for slug in all_slugs:
                if slug in new_details:
                    details[slug] = new_details[slug]
                elif slug in unchanged_slugs:
                    row = existing_launches[existing_launches["slug"] == slug]
                    if not row.empty:
                        details[slug] = {"_from_existing": True, "_row": row.iloc[0]}

            # Build launches df
            print("Building DataFrames...")
            rows = []
            for tile in tiles:
                row = {col: tile.get(api_key) for api_key, col in TILE_FIELDS.items()}
                slug = row["slug"]
                detail = details.get(slug, {})

                if detail.get("_from_existing"):
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

        # Keep only described columns in launches
        df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

        # Write timelines and carousel parquet files
        write_parquet(timelines_df, p.data_dir / "timelines.parquet")
        write_parquet(carousel_df, p.data_dir / "carousel.parquet")

        # Images: restore unchanged from HF, download new from CDN
        if incremental and unchanged_slugs:
            download_existing_images(carousel_df, p.tmp_dir, unchanged_slugs)
        download_carousel_images(carousel_df, p.tmp_dir, skip_slugs=unchanged_slugs if incremental else None)

        # ── Stats for README ────────────────────────────────────────
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

        quick_stats = f"""\
- **{n:,}** total missions ({n_completed:,} completed, {n_upcoming:,} upcoming)
- **Vehicles**: {vehicles_str}
- **Top mission types**: {types_str}
- **{n_landings:,}** missions with landing data
- **{n_with_desc:,}** missions with descriptions
- **{n_timeline_events:,}** timeline events, **{n_photos:,}** carousel photos
- SpaceX totals: **{total_launches:,}** launches, **{total_landings}** landings, **{total_reflights}** reflights"""

        usage = f"""\
```python
from datasets import load_dataset

# Load main launches table
launches = load_dataset("juliensimon/spacex-launches", "launches", split="train")
df = launches.to_pandas()

# Falcon 9 missions
f9 = df[df["vehicle"] == "Falcon 9"]
print(f"{{len(f9):,}} Falcon 9 launches")

# Launches per year
import matplotlib.pyplot as plt
df.groupby("launch_year").size().plot(kind="bar", title="SpaceX Launches per Year")
plt.xlabel("Year")
plt.ylabel("Launch Count")
plt.show()

# Load timelines and join
timelines = load_dataset("juliensimon/spacex-launches", "timelines", split="train")
tl = timelines.to_pandas()

# Post-launch events for a specific mission
events = tl[(tl["slug"] == "sl-10-22") & (tl["phase"] == "post_launch")]
print(events[["event_time", "description"]])
```"""

        p.publish(
            df,
            filename="launches.parquet",
            min_rows=MIN_ROWS,
            expected_columns=["title", "vehicle", "launch_date", "mission_status",
                              "launch_site", "slug", "mission_type"],
            critical_columns=["title", "vehicle", "launch_date"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update SpaceX launches: {n:,} missions, {n_timeline_events:,} events, {n_photos:,} photos",
        )
    print("Done.")


if __name__ == "__main__":
    main()
