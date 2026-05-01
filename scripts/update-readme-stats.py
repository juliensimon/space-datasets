#!/usr/bin/env python3
"""Update README.md with top 10 space datasets by all-time downloads from HF API.

Filters to space-datasets only (excludes unrelated HF repos).
Shows daily delta by comparing to previous snapshot.
All-time counts fetched via REST API expand parameter (not available via SDK).
"""

import json
import re
import requests
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from huggingface_hub import HfApi

README = Path(__file__).parent.parent / "README.md"
SNAPSHOT_FILE = Path(__file__).parent.parent / "data" / "download-stats.json"
MARKER_START = "<!-- TOP_DOWNLOADS_START -->"
MARKER_END = "<!-- TOP_DOWNLOADS_END -->"

EXCLUDE = {
    "amazon-shoe-reviews", "autonlp-data-song-lyrics", "autonlp-data-imdb-demo-hf",
    "food102",
}


def fetch_alltime(dataset_id: str) -> int:
    try:
        r = requests.get(
            f"https://huggingface.co/api/datasets/{dataset_id}?expand[]=downloadsAllTime",
            timeout=10,
        )
        return r.json().get("downloadsAllTime", 0) or 0
    except Exception:
        return 0


def load_previous() -> dict[str, int]:
    if SNAPSHOT_FILE.exists():
        return json.loads(SNAPSHOT_FILE.read_text())
    return {}


def save_snapshot(current: dict[str, int]) -> None:
    SNAPSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_FILE.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n")


def main():
    api = HfApi()
    datasets = [d for d in api.list_datasets(author="juliensimon")]
    datasets = [d for d in datasets if d.id.replace("juliensimon/", "") not in EXCLUDE]

    with ThreadPoolExecutor(max_workers=20) as ex:
        alltime_counts = list(ex.map(lambda d: fetch_alltime(d.id), datasets))

    now = datetime.now(timezone.utc)
    previous = load_previous()

    current = {}
    results = []
    for d, alltime in zip(datasets, alltime_counts):
        name = d.id.replace("juliensimon/", "")
        current[name] = alltime
        results.append((name, d.id, d.likes, alltime))

    results.sort(key=lambda x: x[3], reverse=True)
    top10 = results[:10]
    total_downloads = sum(dl for _, _, _, dl in results)
    total_likes = sum(l for _, _, l, _ in results)
    prev_total = sum(previous.values()) if previous else None
    today = now.strftime("%Y-%m-%d")

    header = f"**{total_downloads:,}** downloads (all-time)"
    if prev_total is not None:
        delta_total = total_downloads - prev_total
        if delta_total != 0:
            sign = "+" if delta_total > 0 else "−"
            header += f" ({sign}{abs(delta_total):,})"
    header += f"  ·  **{total_likes}** likes  ·  **{len(results)}** datasets  ·  updated {today}"

    lines = [
        header,
        "",
        "| # | Dataset | Downloads |",
        "|--:|---------|----------:|",
    ]
    for i, (name, full_id, _, downloads) in enumerate(top10, 1):
        prev = previous.get(name)
        if prev is not None:
            delta = downloads - prev
            if delta != 0:
                sign = "+" if delta > 0 else "−"
                delta_str = f" ({sign}{abs(delta):,})"
            else:
                delta_str = ""
        else:
            delta_str = " (new)"
        lines.append(f"| {i} | [{name}](https://huggingface.co/datasets/{full_id}) | {downloads:,}{delta_str} |")

    new_section = "\n".join(lines)

    readme = README.read_text()
    pattern = re.compile(
        re.escape(MARKER_START) + r".*?" + re.escape(MARKER_END),
        re.DOTALL,
    )

    if pattern.search(readme):
        readme = pattern.sub(
            f"{MARKER_START}\n{new_section}\n{MARKER_END}",
            readme,
        )
    else:
        print("::warning::Markers not found in README.md — add them manually")
        return

    README.write_text(readme)
    save_snapshot(current)
    print(f"Updated README: {total_downloads:,} all-time downloads, top 10 refreshed")


if __name__ == "__main__":
    main()
