#!/usr/bin/env python3
"""Fetch NASA Mars Rover image metadata (Perseverance + Curiosity) and upload to HF.

Incremental pipeline: downloads existing parquet, fetches only newer records
by comparing max ID per mission, then merges and deduplicates.
"""

import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pandas as pd
import requests

from dataset_images import banner_markdown, download_banner
from validate import check_dataset

API_URL = "https://mars.nasa.gov/api/v1/raw_image_items/"
HF_REPO = "juliensimon/nasa-mars-rover-images"
MISSIONS = ["mars2020", "msl"]
PER_PAGE = 100
MAX_INITIAL_PER_MISSION = 200_000
SLEEP_BETWEEN_PAGES = 0.2


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
        "filter_name": ext.get("filter_name"),
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


def load_existing(tmp_dir):
    """Download existing parquet from HF. Returns DataFrame or None."""
    parquet_path = tmp_dir / "data" / "mars_rover_images.parquet"
    try:
        subprocess.run(
            ["hf", "download", HF_REPO, "data/mars_rover_images.parquet",
             "--repo-type", "dataset", "--local-dir", str(tmp_dir)],
            check=True, capture_output=True, timeout=300,
        )
        if parquet_path.exists():
            df = pd.read_parquet(parquet_path)
            print(f"  Loaded existing: {len(df):,} images")
            return df
    except Exception as e:
        print(f"  Could not load existing ({e}), doing full fetch")
    return None


def size_category(n):
    """Return HF size_categories string."""
    if n >= 1_000_000:
        return "1M<n<10M"
    if n >= 100_000:
        return "100K<n<1M"
    if n >= 10_000:
        return "10K<n<100K"
    return "1K<n<10K"


def generate_readme(df, banner_md=""):
    """Generate HF dataset card README."""
    n_total = len(df)
    n_m2020 = int((df["mission"] == "mars2020").sum())
    n_msl = int((df["mission"] == "msl").sum())
    n_instruments = df["instrument"].nunique()
    sol_max_m2020 = int(df.loc[df["mission"] == "mars2020", "sol"].max()) if n_m2020 > 0 else 0
    sol_max_msl = int(df.loc[df["mission"] == "msl", "sol"].max()) if n_msl > 0 else 0
    size_cat = size_category(n_total)

    return f"""---
license: cc-by-4.0
pretty_name: "NASA Mars Rover Image Catalog"
language:
  - en
description: "Metadata for every raw image captured by Perseverance (Mars 2020) and Curiosity (MSL) rovers on Mars, including camera, sol, position, and download URLs."
size_categories:
  - {size_cat}
task_categories:
  - tabular-classification
tags:
  - space
  - mars
  - perseverance
  - curiosity
  - mars2020
  - msl
  - rover
  - nasa
  - images
  - open-data
  - tabular-data
  - parquet
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/mars_rover_images.parquet
    default: true
  - config_name: mars2020
    data_files:
      - split: train
        path: data/mars_rover_images.parquet
  - config_name: msl
    data_files:
      - split: train
        path: data/mars_rover_images.parquet
---

# NASA Mars Rover Image Catalog
{banner_md}
*Part of the [Solar System Datasets](https://huggingface.co/collections/juliensimon/solar-system-datasets-69c24ca3c76c541ab1f1abe7) and [Planetary Science Datasets](https://huggingface.co/collections/juliensimon/planetary-science-datasets-69c24cb75fbb91ebe51f2e24) collections on Hugging Face.*

![Update Mars Rovers](https://github.com/juliensimon/space-datasets/actions/workflows/update-mars-rovers.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.mars-rovers&label=updated&color=brightgreen)

Image metadata from NASA's Mars rovers: **{n_m2020:,}** Perseverance images (sol {sol_max_m2020:,}) and **{n_msl:,}** Curiosity images (sol {sol_max_msl:,}), totaling **{n_total:,}** records across **{n_instruments}** camera instruments.

## Dataset description

{_DESCRIPTION}

## Schema

| Column | Type | Description |
|--------|------|-------------|
| `id` | int | Unique image ID from NASA |
| `mission` | string | Mission identifier: "mars2020" (Perseverance) or "msl" (Curiosity) |
| `sol` | int | Martian sol number (days since landing) |
| `instrument` | string | Camera instrument name |
| `date_taken` | string | UTC datetime when image was captured |
| `date_received` | string | UTC datetime when image was received on Earth |
| `site` | int | Site number along the rover traverse |
| `drive` | int | Drive number within the site |
| `rover_x` | float | Rover X position in site frame (meters) |
| `rover_y` | float | Rover Y position in site frame (meters) |
| `rover_z` | float | Rover Z position in site frame (meters) |
| `mast_azimuth` | float | Mast azimuth angle (degrees) |
| `mast_elevation` | float | Mast elevation angle (degrees) |
| `sample_type` | string | Image sample type (full, subframe, thumbnail) |
| `filter_name` | string | Camera filter name |
| `local_mean_solar_time` | string | Local Mean Solar Time on Mars |
| `image_url` | string | Direct HTTPS URL to download the raw image |
| `is_thumbnail` | bool | Whether this is a thumbnail image |
| `title` | string | Image title/caption |

## Usage

```python
from datasets import load_dataset

# Load all images
ds = load_dataset("juliensimon/nasa-mars-rover-images", split="train")
df = ds.to_pandas()

# Perseverance images only
m2020 = df[df["mission"] == "mars2020"]

# Curiosity Mastcam images
mastcam = df[(df["mission"] == "msl") & (df["instrument"].str.contains("MAST", na=False))]

# Images per sol for Perseverance
sol_counts = m2020.groupby("sol").size()
sol_counts.plot(title="Perseverance images per sol")

# Rover traverse (XYZ positions)
positions = m2020.dropna(subset=["rover_x", "rover_y"])
positions.plot.scatter(x="rover_x", y="rover_y", s=0.1, title="Perseverance traverse")
```

## Data source

[NASA Mars Raw Image API](https://mars.nasa.gov/raw_images/). Images are captured by cameras aboard
the Perseverance (Mars 2020) and Curiosity (MSL) rovers and transmitted to Earth via Mars orbiters
and the Deep Space Network.

## Update schedule

Weekly (Monday at 11:00 UTC) via [GitHub Actions](https://github.com/juliensimon/space-datasets).
Incremental updates fetch only images added since the last run.

## Related datasets

- [esa-exomars-tgo-observations](https://huggingface.co/datasets/juliensimon/esa-exomars-tgo-observations) -- ExoMars Trace Gas Orbiter observations
- [esa-mars-express-observations](https://huggingface.co/datasets/juliensimon/esa-mars-express-observations) -- ESA Mars Express observations
- [mars-craters-robbins](https://huggingface.co/datasets/juliensimon/mars-craters-robbins) -- 384K+ Martian impact craters
- [meda-weather](https://huggingface.co/datasets/juliensimon/meda-weather) -- Perseverance MEDA weather station
- [chemcam](https://huggingface.co/datasets/juliensimon/chemcam) -- Curiosity ChemCam LIBS spectra

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/nasa-mars-rover-images) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{nasa_mars_rover_images,
  author = {{Simon, Julien}},
  title = {{NASA Mars Rover Image Catalog}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/nasa-mars-rover-images}},
  note = {{Based on NASA Mars Raw Image API data}}
}}
```
"""


_DESCRIPTION = (
    "The NASA Mars Rover Image Catalog contains metadata for every raw image captured "
    "by the Perseverance (Mars 2020) and Curiosity (MSL) rovers on the surface of Mars. "
    "Perseverance has been exploring Jezero Crater since February 2021, investigating an "
    "ancient river delta for signs of past microbial life and caching samples for future "
    "Earth return. Curiosity has been climbing Mount Sharp in Gale Crater since August 2012, "
    "discovering evidence that Mars once had long-lived lakes and rivers with conditions "
    "suitable for life. Together, these rovers have captured over 2 million raw images using "
    "a variety of cameras: engineering cameras for navigation and hazard avoidance, science "
    "cameras for geological investigation, and specialized instruments like SuperCam and "
    "Mastcam-Z. This metadata catalog includes image timestamp, sol number, camera instrument, "
    "rover position (XYZ site frame), pointing angles, and download URLs — enabling large-scale "
    "analysis of imaging patterns, traverse mapping, and targeted image retrieval without "
    "downloading terabytes of raw image data."
)


def main():
    print("NASA Mars Rover Image Catalog pipeline")

    # ── Try incremental: load existing data ─────────────────────────────
    with tempfile.TemporaryDirectory() as probe:
        df_existing = load_existing(Path(probe))

    # Determine max known ID per mission
    max_ids = {}
    if df_existing is not None and len(df_existing) > 0:
        for mission in MISSIONS:
            subset = df_existing[df_existing["mission"] == mission]
            if len(subset) > 0:
                max_ids[mission] = int(subset["id"].max())
                print(f"  {mission}: max existing id = {max_ids[mission]}")

    # ── Fetch new images per mission ────────────────────────────────────
    all_new_rows = []
    for mission in MISSIONS:
        print(f"Fetching {mission}...")
        max_known = max_ids.get(mission)
        rows = fetch_mission_images(mission, max_known_id=max_known)
        all_new_rows.extend(rows)

    df_new = pd.DataFrame(all_new_rows)
    print(f"Total new images fetched: {len(df_new):,}")

    # ── Merge with existing ─────────────────────────────────────────────
    if df_existing is not None and len(df_existing) > 0:
        if not df_new.empty:
            df = pd.concat([df_existing, df_new], ignore_index=True)
            df = df.drop_duplicates("id", keep="last")
            print(f"Merged: {len(df):,} total ({len(df) - len(df_existing):+,} net new)")
        else:
            df = df_existing
            print("No new images found")
    else:
        if df_new.empty:
            print("::error::No images fetched and no existing data")
            sys.exit(1)
        df = df_new

    # ── Type coercion ───────────────────────────────────────────────────
    df["id"] = pd.to_numeric(df["id"], errors="coerce").astype("Int64")
    df["sol"] = pd.to_numeric(df["sol"], errors="coerce").astype("Int64")
    df["site"] = pd.to_numeric(df["site"], errors="coerce").astype("Int64")
    df["drive"] = pd.to_numeric(df["drive"], errors="coerce").astype("Int64")
    for col in ["rover_x", "rover_y", "rover_z", "mast_azimuth", "mast_elevation"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["is_thumbnail"] = df["is_thumbnail"].astype(bool)
    df = df.sort_values("id").reset_index(drop=True)

    n_total = len(df)
    n_m2020 = int((df["mission"] == "mars2020").sum())
    n_msl = int((df["mission"] == "msl").sum())
    print(f"Final dataset: {n_total:,} images ({n_m2020:,} Perseverance, {n_msl:,} Curiosity)")

    # ── Validate ────────────────────────────────────────────────────────
    check_dataset(
        df, "mars-rovers", min_rows=100_000,
        expected_columns=["id", "mission", "sol", "instrument", "date_taken",
                          "image_url", "rover_x", "rover_y", "rover_z"],
        critical_columns=["id", "mission", "sol", "instrument"],
        incremental=True,
    )

    # ── Write and upload ────────────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "mars_rover_images.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"Parquet: {size_mb:.1f} MB")

        banner_file = download_banner("mars-rovers", tmp)
        banner_md = banner_markdown("mars-rovers", banner_file)
        (tmp / "README.md").write_text(generate_readme(df, banner_md))

        print("Uploading to HF...")
        commit_msg = (
            f"Update Mars rover images: {n_total:,} total "
            f"({n_m2020:,} Perseverance, {n_msl:,} Curiosity)"
        )
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={n_total}\n")
    print(f"Done. {n_total:,} images.")


if __name__ == "__main__":
    main()
