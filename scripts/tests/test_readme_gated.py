#!/usr/bin/env python3
"""Regression test: gated-access front matter survives README regeneration.

Context: on 2026-11-03 five datasets were gated on the Hub with a custom
access form (`extra_gated_prompt` and `extra_gated_fields` in the dataset
card). The daily pipelines rebuild README.md from scratch in
`generate_readme`, so the next run would have dropped those keys and reset
the form to the Hub default. The gate itself is a repo setting and survives;
only the questions would vanish.

These tests pin the carry-over: the keys are read back from the existing card
and written again inside the new front matter, and a card without them yields
nothing to carry.

Run:
    python3 scripts/tests/test_readme_gated.py
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import pandas as pd

from hf_dataset_utils.readme import gated_frontmatter, generate_readme

GATED = (
    'extra_gated_prompt: "Access is granted automatically. A line about who '
    'you are helps."\n'
    "extra_gated_fields:\n"
    "  Organization: text\n"
    "  Intended use: text\n"
    "  I will cite the dataset in publications: checkbox\n"
)

CARD_WITH_GATE = (
    "---\n"
    "license: cc-by-4.0\n"
    'pretty_name: "Demo"\n'
    "configs:\n"
    "  - config_name: default\n"
    "    data_files:\n"
    "      - split: train\n"
    "        path: data/demo.parquet\n"
    "    default: true\n"
    f"{GATED}"
    "---\n\n# Demo\n\nextra_gated_fields: mentioned in the body, not front matter\n"
)

CARD_WITHOUT_GATE = (
    "---\nlicense: cc-by-4.0\npretty_name: \"Demo\"\n---\n\n# Demo\n"
)


def _frontmatter(readme: str) -> str:
    assert readme.startswith("---\n")
    return readme.split("\n---", 1)[0]


def test_extracts_only_gated_keys():
    assert gated_frontmatter(CARD_WITH_GATE) == GATED


def test_nothing_to_carry_without_gate():
    assert gated_frontmatter(CARD_WITHOUT_GATE) == ""
    assert gated_frontmatter("") == ""
    assert gated_frontmatter("# no front matter\n") == ""


def _generate(extra):
    df = pd.DataFrame({"a": [1, 2, 3]})
    return generate_readme(
        repo="juliensimon/demo",
        pretty_name="Demo",
        description="A demo.",
        tags=["demo"],
        df=df,
        filename="demo.parquet",
        source_url="https://example.org",
        extra_frontmatter=extra,
    )


def test_gated_keys_written_inside_frontmatter():
    readme = _generate(GATED)
    fm = _frontmatter(readme)
    assert "extra_gated_prompt:" in fm
    assert "  I will cite the dataset in publications: checkbox" in fm
    # once in the front matter, nowhere in the body
    assert readme.count("extra_gated_fields:") == 1


def test_round_trip_is_stable():
    first = _generate(GATED)
    second = _generate(gated_frontmatter(first))
    assert _frontmatter(second) == _frontmatter(first)


def test_no_extra_keeps_card_unchanged():
    assert _generate(None) == _generate("")
    assert "extra_gated" not in _generate(None)


if __name__ == "__main__":
    test_extracts_only_gated_keys()
    test_nothing_to_carry_without_gate()
    test_gated_keys_written_inside_frontmatter()
    test_round_trip_is_stable()
    test_no_extra_keeps_card_unchanged()
    print("All tests passed.")
