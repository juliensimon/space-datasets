"""Domain-based cross-link registry for related datasets."""

from __future__ import annotations

import sys
from pathlib import Path

# Import DATASET_DOMAIN from the sibling module (scripts/ directory)
_scripts_dir = str(Path(__file__).resolve().parent.parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from dataset_images import DATASET_DOMAIN

# HF repo prefix
_PREFIX = "juliensimon/"


def _invert_domain_map() -> dict[str, list[str]]:
    """Build {domain: [dataset_key, ...]} from DATASET_DOMAIN."""
    result: dict[str, list[str]] = {}
    for dataset_key, domain in DATASET_DOMAIN.items():
        result.setdefault(domain, []).append(dataset_key)
    return result


_DOMAIN_DATASETS = _invert_domain_map()


def get_domain_crosslinks(
    dataset_key: str,
    max_links: int = 4,
) -> list[str]:
    """Return related dataset repo IDs based on shared domain.

    Args:
        dataset_key: Dataset slug (e.g., "neo", "exoplanets").
        max_links: Maximum number of related datasets to return.

    Returns:
        List of HF repo IDs (e.g., ["juliensimon/sentry-impact-risk"]).
    """
    domain = DATASET_DOMAIN.get(dataset_key)
    if not domain:
        return []
    siblings = _DOMAIN_DATASETS.get(domain, [])
    related = [s for s in siblings if s != dataset_key][:max_links]
    return [f"{_PREFIX}{slug}" for slug in related]
