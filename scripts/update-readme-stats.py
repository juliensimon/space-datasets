#!/usr/bin/env python3
"""Update README.md with top 10 datasets by downloads from HF API."""

import re
from datetime import datetime, timezone
from pathlib import Path

from huggingface_hub import HfApi

README = Path(__file__).parent.parent / "README.md"
MARKER_START = "<!-- TOP_DOWNLOADS_START -->"
MARKER_END = "<!-- TOP_DOWNLOADS_END -->"


def main():
    api = HfApi()
    datasets = [d for d in api.list_datasets(author="juliensimon")]

    results = []
    for d in datasets:
        name = d.id.replace("juliensimon/", "")
        results.append((name, d.id, d.likes, d.downloads))

    results.sort(key=lambda x: x[3], reverse=True)
    top10 = results[:10]
    total_downloads = sum(d for _, _, _, d in results)
    total_likes = sum(l for _, _, l, _ in results)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    lines = [
        f"**{total_downloads:,}** downloads  ·  **{total_likes}** likes  ·  **{len(results)}** datasets  ·  updated {today}",
        "",
        "| # | Dataset | Downloads |",
        "|--:|---------|----------:|",
    ]
    for i, (name, full_id, _, downloads) in enumerate(top10, 1):
        lines.append(f"| {i} | [{name}](https://huggingface.co/datasets/{full_id}) | {downloads:,} |")

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
    print(f"Updated README: {total_downloads:,} downloads, top 10 refreshed")


if __name__ == "__main__":
    main()
