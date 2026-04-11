#!/usr/bin/env python3
"""Fetch NASA Mars Rover image metadata (Perseverance + Curiosity) and upload to HF.

Incremental pipeline: downloads existing parquet, fetches only newer records
by comparing max ID per mission, then merges and deduplicates.
"""

import re
import time

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

API_URL = "https://mars.nasa.gov/api/v1/raw_image_items/"
HF_REPO = "juliensimon/nasa-mars-rover-images"
MISSIONS = ["mars2020", "msl"]
PER_PAGE = 100
MAX_INITIAL_PER_MISSION = 200_000
SLEEP_BETWEEN_PAGES = 0.2

# ── Column descriptions ────────────────────────────────────────────────
COLUMN_DESCRIPTIONS = {
    "id": "NASA-assigned unique integer image ID; monotonically increasing per mission",
    "mission": 'Mission identifier: "mars2020" (Perseverance, Jezero Crater, landed Feb 18 2021) or "msl" (Curiosity, Gale Crater, landed Aug 6 2012)',
    "sol": "Martian solar day since rover landing (sol 0 = landing date, ~1.0275 Earth days per sol)",
    "instrument": 'Camera instrument name (e.g. "FRONT_HAZCAM_LEFT_A", "NAVCAM_LEFT", "MCZ_RIGHT", "MASTCAM_LEFT"; null rare)',
    "date_taken": "UTC datetime when image was captured on Mars",
    "date_received": "UTC datetime when image was received on Earth via Deep Space Network",
    "site": "Terrain site index along the rover traverse; increments when the rover drives to a new location",
    "drive": "Drive sequence number within a site; tracks individual driving sessions",
    "rover_x": "Rover X position in local site frame (meters); coordinate origin at site establishment point",
    "rover_y": "Rover Y position in local site frame (meters)",
    "rover_z": "Rover Z position in local site frame (meters); typically near zero on flat terrain",
    "mast_azimuth": "Remote sensing mast azimuth angle in degrees (0-360, clockwise from north)",
    "mast_elevation": "Remote sensing mast elevation angle in degrees; positive = above horizon, negative = below",
    "sample_type": 'Image sampling mode: "full" (full-resolution), "subframe" (cropped region), "thumbnail" (reduced-resolution preview)',
    "local_mean_solar_time": 'Local Mean Solar Time at image capture (format "sol HH:MM:SS"); approximates the position of the sun in the sky',
    "image_url": "Direct HTTPS URL to download the raw image from the NASA Mars Raw Images server",
    "is_thumbnail": "True if this row represents a thumbnail image (lower resolution preview), False for full/subframe images",
    "title": "Human-readable image title composed from instrument, sol, and sequence identifiers; may be null",
}

DESCRIPTION = """\
The NASA Mars Rover Image Catalog contains metadata for every raw image captured \
by the Perseverance (Mars 2020) and Curiosity (MSL) rovers on the surface of Mars. \
Perseverance has been exploring Jezero Crater since February 2021, investigating an \
ancient river delta for signs of past microbial life and caching samples for future \
Earth return. Curiosity has been climbing Mount Sharp in Gale Crater since August 2012, \
discovering evidence that Mars once had long-lived lakes and rivers with conditions \
suitable for life. Together, these rovers have captured over 2 million raw images using \
a variety of cameras: engineering cameras for navigation and hazard avoidance, science \
cameras for geological investigation, and specialized instruments like SuperCam and \
Mastcam-Z. This metadata catalog includes image timestamp, sol number, camera instrument, \
rover position (XYZ site frame), pointing angles, and download URLs -- enabling large-scale \
analysis of imaging patterns, traverse mapping, and targeted image retrieval without \
downloading terabytes of raw image data."""


# ── Fetch helpers ───────────────────────────────────────────────────────

def parse_xyz(xyz_str):
    """Parse '(x, y, z)' string into three floats."""
    if not xyz_str or not isinstance(xyz_str, str):
        return None, None, None
    m = re.match(r"\(?\s*([-\d.eE+]+)\s*,\s*([-\d.eE+]+)\s*,\s*([-\d.eE+]+)\s*\)?", xyz_str)
    if m:
        try:
            return float(m.group(1)), float(m.group(2)), float(m.group(3))
        except (ValueError, TypeError):
            pass
    return None, None, None


def fetch_page(mission, page, order="id desc", max_retries=3):
    """Fetch a single page from the NASA Mars API."""
    params = {
        "mission": mission,
        "per_page": PER_PAGE,
        "page": page,
        "order": order,
    }
    for attempt in range(max_retries):
        try:
            resp = requests.get(API_URL, params=params, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            return data.get("items", []), data.get("total", 0)
        except requests.HTTPError as e:
            if resp.status_code == 403 and attempt < max_retries - 1:
                wait = 5 * (attempt + 1)
                print(f"    403 Forbidden (attempt {attempt + 1}), retrying in {wait}s...")
                time.sleep(wait)
                continue
            raise


def parse_image(img, mission):
    """Parse a single image JSON object into a flat dict."""
    ext = img.get("extended") or {}
    x, y, z = parse_xyz(img.get("xyz"))

    return {
        "id": img.get("id"),
        "mission": mission,
        "sol": img.get("sol"),
        "instrument": img.get("instrument"),
        "date_taken": img.get("date_taken"),
        "date_received": img.get("date_received"),
        "site": img.get("site"),
        "drive": img.get("drive"),
        "rover_x": x,
        "rover_y": y,
        "rover_z": z,
        "mast_azimuth": ext.get("mast_az"),
        "mast_elevation": ext.get("mast_el"),
        "sample_type": ext.get("sample_type"),
        "local_mean_solar_time": ext.get("lmst"),
        "image_url": img.get("https_url"),
        "is_thumbnail": bool(img.get("is_thumbnail")),
        "title": img.get("title"),
    }


def fetch_mission_images(mission, max_known_id=None, limit=MAX_INITIAL_PER_MISSION):
    """Fetch images for a mission, stopping at max_known_id or limit."""
    rows = []
    page = 0
    total = None
    stop_reason = None

    while True:
        images, api_total = fetch_page(mission, page)
        if total is None:
            total = api_total
            print(f"  {mission}: {total:,} total images on server")

        if not images:
            stop_reason = "no more pages"
            break

        for img in images:
            img_id = img.get("id")
            if max_known_id is not None and img_id is not None and img_id <= max_known_id:
                stop_reason = f"reached known id {max_known_id}"
                break
            rows.append(parse_image(img, mission))

        if stop_reason:
            break

        if len(rows) >= limit:
            stop_reason = f"reached limit {limit:,}"
            break

        page += 1
        if page % 100 == 0:
            print(f"    page {page}, {len(rows):,} images so far...")
        time.sleep(SLEEP_BETWEEN_PAGES)

    print(f"  {mission}: fetched {len(rows):,} new images ({stop_reason})")
    return rows


# ── Main ────────────────────────────────────────────────────────────────

def main():
    print("NASA Mars Rover Image Catalog pipeline")

    with Pipeline(
        repo=HF_REPO,
        pretty_name="NASA Mars Rover Image Catalog",
        description=DESCRIPTION,
        tags=["space", "mars", "perseverance", "curiosity", "mars2020", "msl",
              "rover", "nasa", "images", "open-data", "tabular-data", "parquet"],
        source_url="https://mars.nasa.gov/raw_images/",
        task_categories=["tabular-classification"],
        update_schedule="Weekly (Monday at 11:00 UTC) via [GitHub Actions](https://github.com/juliensimon/space-datasets). Incremental updates fetch only images added since the last run.",
        collection_url="https://huggingface.co/collections/juliensimon/space-probe-and-mission-datasets-69c3fe82d410a42b1e313167",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA19808/PIA19808~small.jpg",
            "alt": "NASA's Curiosity rover on the surface of Mars",
            "credit": "NASA/JPL-Caltech/MSSS",
        },
        related_datasets=[
            "juliensimon/esa-exomars-tgo-observations",
            "juliensimon/esa-mars-express-observations",
            "juliensimon/mars-craters-robbins",
            "juliensimon/mars-perseverance-weather",
            "juliensimon/mars-chemcam-compositions",
        ],
    ) as p:
        # ── Incremental: load existing data ─────────────────────────
        df_existing = p.download_existing("mars_rover_images.parquet")

        # Determine max known ID per mission
        max_ids = {}
        if df_existing is not None and len(df_existing) > 0:
            for mission in MISSIONS:
                subset = df_existing[df_existing["mission"] == mission]
                if len(subset) > 0:
                    max_ids[mission] = int(subset["id"].max())
                    print(f"  {mission}: max existing id = {max_ids[mission]}")

        # ── Fetch new images per mission ────────────────────────────
        all_new_rows = []
        for mission in MISSIONS:
            print(f"Fetching {mission}...")
            max_known = max_ids.get(mission)
            rows = fetch_mission_images(mission, max_known_id=max_known)
            all_new_rows.extend(rows)

        df_new = pd.DataFrame(all_new_rows)
        print(f"Total new images fetched: {len(df_new):,}")

        # ── Merge with existing ─────────────────────────────────────
        if df_existing is not None and len(df_existing) > 0:
            if not df_new.empty:
                df = p.merge(df_existing, df_new, dedup_on=["id", "mission"], sort_by="id")
                print(f"Merged: {len(df):,} total ({len(df) - len(df_existing):+,} net new)")
            else:
                df = df_existing
                print("No new images found")
        else:
            if df_new.empty:
                print("::error::No images fetched and no existing data")
                import sys
                sys.exit(1)
            df = df_new

        # ── Type coercion ───────────────────────────────────────────
        df["is_thumbnail"] = df["is_thumbnail"].astype(bool)

        df = p.clean(
            df,
            integer=["id", "sol", "site", "drive"],
            numeric=["rover_x", "rover_y", "rover_z", "mast_azimuth", "mast_elevation"],
        )

        # Keep only described columns
        df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]
        df = df.sort_values("id").reset_index(drop=True)

        n_total = len(df)
        n_m2020 = int((df["mission"] == "mars2020").sum())
        n_msl = int((df["mission"] == "msl").sum())
        n_instruments = df["instrument"].nunique()
        sol_max_m2020 = int(df.loc[df["mission"] == "mars2020", "sol"].max()) if n_m2020 > 0 else 0
        sol_max_msl = int(df.loc[df["mission"] == "msl", "sol"].max()) if n_msl > 0 else 0

        quick_stats = f"""\
- **{n_total:,}** total images
- **{n_m2020:,}** Perseverance images (through sol {sol_max_m2020:,})
- **{n_msl:,}** Curiosity images (through sol {sol_max_msl:,})
- **{n_instruments}** camera instruments"""

        usage = f"""\
```python
from datasets import load_dataset

# Load all images
ds = load_dataset("{HF_REPO}", split="train")
df = ds.to_pandas()

# Perseverance images only
m2020 = df[df["mission"] == "mars2020"]

# Curiosity Mastcam images
mastcam = df[(df["mission"] == "msl") & (df["instrument"].str.contains("MAST", na=False))]

# Images per sol for Perseverance
import matplotlib.pyplot as plt
sol_counts = m2020.groupby("sol").size()
sol_counts.plot(title="Perseverance images per sol")
plt.xlabel("Sol")
plt.ylabel("Image count")
plt.show()

# Rover traverse (XYZ positions)
positions = m2020.dropna(subset=["rover_x", "rover_y"])
positions.plot.scatter(x="rover_x", y="rover_y", s=0.1, title="Perseverance traverse")
plt.show()
```"""

        print(f"Final dataset: {n_total:,} images ({n_m2020:,} Perseverance, {n_msl:,} Curiosity)")

        p.publish(
            df,
            filename="mars_rover_images.parquet",
            min_rows=100_000,
            expected_columns=["id", "mission", "sol", "instrument", "date_taken",
                              "image_url", "rover_x", "rover_y", "rover_z"],
            critical_columns=["id", "mission", "sol", "instrument"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Mars rover images: {n_total:,} total ({n_m2020:,} Perseverance, {n_msl:,} Curiosity)",
        )
    print("Done.")


if __name__ == "__main__":
    main()
