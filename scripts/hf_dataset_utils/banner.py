"""Banner image download and markdown generation."""

from __future__ import annotations

import re
from pathlib import Path

import requests


def _sanitize_filename(filename: str) -> str:
    """Replace unsafe characters in filename with hyphens."""
    if "." in filename:
        name, ext = filename.rsplit(".", 1)
    else:
        name, ext = filename, "jpg"
    name = re.sub(r"[^\w\-]", "-", name).strip("-")
    return f"{name}.{ext}" if name else f"banner.{ext}"


def download_banner(
    url: str,
    dest_dir: str | Path,
    filename: str = "banner.jpg",
    timeout: int = 30,
) -> str | None:
    """Download a banner image to dest_dir.

    Args:
        url: Image URL to download.
        dest_dir: Directory to save the image in.
        filename: Filename for the saved image.
        timeout: Request timeout in seconds.

    Returns:
        The filename on success, or None on failure.
    """
    filename = _sanitize_filename(filename)
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        path = Path(dest_dir) / filename
        path.write_bytes(resp.content)
        return filename
    except Exception as e:
        print(f"  Warning: could not download banner image: {e}")
        return None


def banner_markdown(
    alt_text: str,
    credit: str,
    filename: str = "banner.jpg",
) -> str:
    """Generate centered HTML for a banner image.

    Args:
        alt_text: Alt text for the image.
        credit: Credit line (e.g., "NASA/JPL"). Empty string to omit.
        filename: Image filename.

    Returns:
        HTML string with centered image and optional credit.
    """
    lines = [
        "",
        '<div align="center">',
        f'  <img src="{filename}" alt="{alt_text}" width="400">',
    ]
    if credit:
        lines.append(f"  <p><em>Credit: {credit}</em></p>")
    lines.extend(["</div>", ""])
    return "\n".join(lines)
