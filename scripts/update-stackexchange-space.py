#!/usr/bin/env python3
"""Build a space-science Q&A dataset from the Astronomy and Space
Stack Exchange data dumps.

Downloads the two site archives from archive.org, extracts Posts.xml,
joins each question with its top-scored answer, cleans HTML to plain
text, and publishes one row per question with question + answer + tags
+ score.

CC-BY-SA 4.0 — the standard Stack Exchange content license.
"""

import os
import tempfile
from html import unescape
from pathlib import Path
from xml.etree.ElementTree import iterparse

import pandas as pd
import py7zr
import requests
from bs4 import BeautifulSoup

from hf_dataset_utils import Pipeline

HF_REPO = "juliensimon/stackexchange-space-qa"
ARCHIVE_BASE = "https://archive.org/download/stackexchange"
CHECKPOINT_PATH = os.environ.get("SE_CHECKPOINT", "/tmp/se_raw.parquet")

# site_key → (archive_filename, canonical_site_url)
SITES = {
    "astronomy": ("astronomy.stackexchange.com.7z", "https://astronomy.stackexchange.com"),
    "space": ("space.stackexchange.com.7z", "https://space.stackexchange.com"),
}

COLUMN_DESCRIPTIONS = {
    "qid": "Stack Exchange question ID (unique within its site)",
    "site": "Which Stack Exchange site the question is from: 'astronomy' (astronomy.stackexchange.com) or 'space' (space.stackexchange.com — Space Exploration)",
    "url": "Permalink to the question on Stack Exchange",
    "question_title": "Question title as posted",
    "question_body": "Question body in plain text (stripped of HTML, with code blocks and inline formatting preserved)",
    "question_tags": "Semicolon-joined list of tags attached to the question (e.g., 'black-holes;general-relativity')",
    "question_score": "Net vote score of the question (upvotes minus downvotes) at dump time",
    "question_view_count": "Number of times the question has been viewed",
    "question_answer_count": "Total number of answers posted to the question",
    "question_creation_date": "ISO-8601 UTC date when the question was posted",
    "answer_body": "Top-scored answer body in plain text, or null if the question is unanswered. Prefers the accepted answer when one exists; otherwise the highest-scored answer.",
    "answer_score": "Net vote score of the selected answer; null if unanswered",
    "answer_creation_date": "ISO-8601 UTC date when the selected answer was posted; null if unanswered",
    "answer_accepted": "True if the selected answer is the question's accepted answer; False if it is just the top-scored answer; null if unanswered",
}

DESCRIPTION = """\
This dataset is a clean, tabular Q&A corpus of space and astronomy knowledge, derived from two Stack Exchange community Q&A sites: Astronomy Stack Exchange (astronomy.stackexchange.com) and Space Exploration Stack Exchange (space.stackexchange.com). Each row is one question paired with its best answer — either the question's accepted answer, or if none is accepted, the highest-scored answer. Unanswered questions are included with null answer fields so that downstream consumers can choose to filter them out.

Stack Exchange is vote-ranked, which makes it a particularly strong source of instruction-tuning data: community scores already encode a quality signal, and accepted-answer flags add an explicit gold-standard marker. The two sites together cover the full breadth of space science — from cosmology and stellar astrophysics to orbital mechanics, rocket propulsion, satellite operations, and crewed spaceflight. Topics tend toward the graduate-level-to-working-professional end of the spectrum; questions cite papers, use technical vocabulary, and receive carefully-written answers from practitioners.

The dataset is suitable for instruction fine-tuning (question → answer pairs), preference learning (score-ranked accepted vs. unaccepted pairs can be derived by joining this table with itself on qid), retrieval-augmented generation (as a grounded Q&A corpus for a space-science RAG system), benchmarking (filter by tag to build evaluation sets on a specific topic), and linguistic analysis of how practitioners explain space concepts to each other. HTML has been converted to plain text; inline formatting (code blocks, lists, equations) is preserved where possible.

Content is licensed CC-BY-SA 4.0 (Stack Exchange's standard license). Each row retains the question URL so that attribution can be traced to individual authors on the source site. The dataset is refreshed annually — Stack Exchange publishes quarterly data dumps to archive.org, but the quality-ranked subset changes slowly enough that yearly is sufficient."""


def _download(url: str, dest: Path) -> None:
    print(f"    downloading {url} → {dest.name}")
    with requests.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        with dest.open("wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)


def _extract_posts_xml(archive_path: Path, out_dir: Path) -> Path:
    """Extract only Posts.xml from a site's 7z archive."""
    with py7zr.SevenZipFile(archive_path, mode="r") as z:
        names = z.getnames()
        posts = [n for n in names if n.endswith("Posts.xml")]
        if not posts:
            raise RuntimeError(f"No Posts.xml in {archive_path}")
        z.extract(path=out_dir, targets=posts)
    return out_dir / posts[0]


def _html_to_text(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    # Collapse whitespace but keep newlines between block elements
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for block in soup.find_all(["p", "li", "pre", "blockquote", "div"]):
        block.insert_before("\n")
        block.insert_after("\n")
    text = soup.get_text()
    # Normalise multiple blank lines
    lines = [line.rstrip() for line in text.splitlines()]
    cleaned = "\n".join(lines)
    while "\n\n\n" in cleaned:
        cleaned = cleaned.replace("\n\n\n", "\n\n")
    return cleaned.strip()


def _parse_tags(tags_field: str) -> list[str]:
    # SE stores tags as "<tag1><tag2>..." (HTML-escaped as "&lt;tag1&gt;...")
    if not tags_field:
        return []
    s = unescape(tags_field)
    return [t for t in s.replace(">", " ").replace("<", "").split() if t]


def _parse_site(site_key: str, posts_xml: Path) -> pd.DataFrame:
    """Stream Posts.xml, joining questions with their best answer."""
    questions: dict[int, dict] = {}
    # answers_by_parent[q_id] = list of (score, answer_id, dict)
    answers_by_parent: dict[int, list] = {}

    for _, elem in iterparse(str(posts_xml), events=("end",)):
        if elem.tag != "row":
            continue
        attrib = elem.attrib
        post_type = attrib.get("PostTypeId")
        if post_type == "1":  # question
            qid = int(attrib["Id"])
            questions[qid] = {
                "qid": qid,
                "question_title": attrib.get("Title", ""),
                "question_body_html": attrib.get("Body", ""),
                "question_tags": ";".join(_parse_tags(attrib.get("Tags", ""))),
                "question_score": int(attrib.get("Score", 0)),
                "question_view_count": int(attrib.get("ViewCount", 0)),
                "question_answer_count": int(attrib.get("AnswerCount", 0)),
                "question_creation_date": attrib.get("CreationDate", ""),
                "accepted_answer_id": int(attrib["AcceptedAnswerId"]) if "AcceptedAnswerId" in attrib else None,
            }
        elif post_type == "2":  # answer
            parent = int(attrib.get("ParentId", 0))
            if parent:
                answers_by_parent.setdefault(parent, []).append({
                    "answer_id": int(attrib["Id"]),
                    "answer_body_html": attrib.get("Body", ""),
                    "answer_score": int(attrib.get("Score", 0)),
                    "answer_creation_date": attrib.get("CreationDate", ""),
                })
        elem.clear()

    print(f"    {site_key}: {len(questions):,} questions, {sum(len(v) for v in answers_by_parent.values()):,} answers")

    rows = []
    for qid, q in questions.items():
        answers = answers_by_parent.get(qid, [])
        chosen = None
        accepted_id = q.pop("accepted_answer_id")
        if answers:
            if accepted_id is not None:
                # Prefer the accepted answer
                chosen = next((a for a in answers if a["answer_id"] == accepted_id), None)
            if chosen is None:
                # Fall back to the top-scored answer
                chosen = max(answers, key=lambda a: a["answer_score"])

        row = {
            "qid": q["qid"],
            "site": site_key,
            "url": f"{SITES[site_key][1]}/questions/{q['qid']}",
            "question_title": q["question_title"],
            "question_body": _html_to_text(q["question_body_html"]),
            "question_tags": q["question_tags"],
            "question_score": q["question_score"],
            "question_view_count": q["question_view_count"],
            "question_answer_count": q["question_answer_count"],
            "question_creation_date": q["question_creation_date"],
            "answer_body": _html_to_text(chosen["answer_body_html"]) if chosen else None,
            "answer_score": chosen["answer_score"] if chosen else None,
            "answer_creation_date": chosen["answer_creation_date"] if chosen else None,
            "answer_accepted": (chosen["answer_id"] == accepted_id) if (chosen and accepted_id) else (False if chosen else None),
        }
        rows.append(row)

    return pd.DataFrame(rows)


def _fetch_all_sites() -> pd.DataFrame:
    chunks = []
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        for site_key, (filename, _) in SITES.items():
            archive_path = work / filename
            extract_dir = work / site_key
            extract_dir.mkdir()
            _download(f"{ARCHIVE_BASE}/{filename}", archive_path)
            print(f"    extracting Posts.xml from {filename}...")
            posts_xml = _extract_posts_xml(archive_path, extract_dir)
            df = _parse_site(site_key, posts_xml)
            chunks.append(df)
            archive_path.unlink()  # free disk early
    return pd.concat(chunks, ignore_index=True)


def _normalize_dates(s: pd.Series) -> pd.Series:
    """SE stores dates like '2015-04-30T12:34:56.123'. Normalize to '...Z'."""
    return (
        pd.to_datetime(s, errors="coerce", utc=True)
        .dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    )


def main():
    print("Stack Exchange space Q&A pipeline")

    df = None
    if CHECKPOINT_PATH and Path(CHECKPOINT_PATH).exists():
        try:
            df = pd.read_parquet(CHECKPOINT_PATH)
            print(f"  Loaded checkpoint: {len(df):,} rows")
        except Exception as e:
            print(f"  Checkpoint unreadable: {e}")

    if df is None:
        df = _fetch_all_sites()
        try:
            df.to_parquet(CHECKPOINT_PATH, compression="zstd")
            print(f"  Saved checkpoint to {CHECKPOINT_PATH}")
        except Exception as e:
            print(f"  Checkpoint save failed: {e}")

    print(f"  total Q&A rows: {len(df):,}")

    df["question_creation_date"] = _normalize_dates(df["question_creation_date"])
    df["answer_creation_date"] = _normalize_dates(df["answer_creation_date"])

    # Sort by score descending, so highest-quality questions come first
    df = df.sort_values(["site", "question_score"], ascending=[True, False]).reset_index(drop=True)

    # ── Stats ──────────────────────────────────────────────────────────
    n_total = len(df)
    per_site = df["site"].value_counts()
    site_line = ", ".join(f"**{s}** ({n:,})" for s, n in per_site.items())
    n_answered = int(df["answer_body"].notna().sum())
    n_accepted = int(df["answer_accepted"].fillna(False).astype(bool).sum())
    median_score = float(df["question_score"].median())
    total_views = int(df["question_view_count"].sum())

    quick_stats = f"""\
- **{n_total:,}** questions across {site_line}
- **{n_answered:,}** have a top answer (**{n_accepted:,}** of those are the question's accepted answer)
- Median question score: **{median_score:.0f}**
- **{total_views:,}** total question views across the corpus"""

    usage = f"""\
```python
from datasets import load_dataset

ds = load_dataset("{HF_REPO}", split="train")
df = ds.to_pandas()

# High-quality accepted answers only — solid instruction-tuning pairs
high_quality = df[(df["answer_accepted"] == True) & (df["question_score"] >= 5)]
print(f"Accepted answers on highly-voted questions: {{len(high_quality):,}}")

# Filter by tag (e.g. exoplanets on Astronomy SE)
exo = df[df["question_tags"].str.contains("exoplanet", na=False)]
print(f"Exoplanet questions: {{len(exo):,}}")

# SFT-ready Q→A pairs
sft = (
    df[df["answer_body"].notna()]
    [["qid", "site", "question_title", "question_body", "answer_body"]]
    .rename(columns={{"question_body": "prompt_body", "answer_body": "response"}})
)

# Plot top 20 tags (astronomy)
import matplotlib.pyplot as plt
astro = df[df["site"] == "astronomy"]
tag_counts = astro["question_tags"].str.split(";").explode().value_counts().head(20)
tag_counts.plot.barh(figsize=(10, 6))
plt.xlabel("Questions"); plt.title("Most-used tags on Astronomy Stack Exchange")
plt.gca().invert_yaxis()
plt.tight_layout(); plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Stack Exchange Space Q&A",
        description=DESCRIPTION,
        tags=["space", "astronomy", "question-answering", "stack-exchange",
              "instruction-tuning", "sft", "qa-pairs", "open-data",
              "tabular-data", "parquet"],
        source_url="https://archive.org/details/stackexchange",
        license="cc-by-sa-4.0",
        task_categories=["question-answering", "text-generation"],
        update_schedule="Annually — SE publishes quarterly data dumps, but the accepted-answer quality-filtered subset changes slowly.",
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e002215/GSFC_20171208_Archive_e002215~medium.jpg",
            "alt": "The gamma-ray sky — representative of the community-written answers covering all of space science",
            "credit": "NASA/DOE/Fermi LAT Collaboration",
        },
        related_datasets=[
            "juliensimon/nasa-exoplanets",
            "juliensimon/astronaut-database",
            "juliensimon/space-agency-database",
            "juliensimon/hst-observations",
            "juliensimon/jwst-observations",
        ],
    ) as p:
        df = p.clean(
            df,
            integer=["qid", "question_score", "question_view_count",
                     "question_answer_count", "answer_score"],
            strings=["site", "url", "question_title", "question_body",
                     "question_tags", "question_creation_date",
                     "answer_body", "answer_creation_date"],
        )

        # answer_accepted is nullable bool — keep as-is
        df["answer_accepted"] = df["answer_accepted"].astype("boolean")

        df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

        all_null = [c for c in df.columns if df[c].isna().all()]
        if all_null:
            print(f"  Warning: dropping fully-null columns: {all_null}")
            df = df.drop(columns=all_null)

        p.publish(
            df,
            filename="stackexchange_space_qa.parquet",
            min_rows=10_000,
            expected_columns=["qid", "site", "question_title", "question_body"],
            critical_columns=["qid", "site", "question_title", "question_body"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Stack Exchange space Q&A: {n_total:,} questions",
        )
    print("Done.")


if __name__ == "__main__":
    main()
