"""HF dataset card (README.md) generation."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

_YAML_TAG_SPECIAL = ('": ', ': ', '{', '[', '#', '"')


def _yaml_escape(s: str) -> str:
    """Escape a string for embedding inside a double-quoted YAML scalar.

    - Replaces newlines with spaces (keeps the value on one line)
    - Escapes backslashes before escaping quotes (order matters)
    - Escapes double quotes
    """
    s = s.replace("\n", " ")
    s = s.replace("\\", "\\\\")
    s = s.replace('"', '\\"')
    return s


def _yaml_tag(s: str) -> str:
    """Wrap a YAML list item in double quotes if it contains special characters."""
    needs_quoting = (
        s.startswith(("#", "{", "[", '"', "&", "*", "!", "|", ">", "'", "%", "@", "`"))
        or ": " in s
        or '"' in s
    )
    if needs_quoting:
        return f'"{_yaml_escape(s)}"'
    return s


def _size_category(n_rows: int) -> str:
    """Map row count to HF size_categories bucket string."""
    thresholds = [
        (10_000_000_000, "10B<n<100B"),
        (1_000_000_000, "1B<n<10B"),
        (100_000_000, "100M<n<1B"),
        (10_000_000, "10M<n<100M"),
        (1_000_000, "1M<n<10M"),
        (100_000, "100K<n<1M"),
        (10_000, "10K<n<100K"),
        (1_000, "1K<n<10K"),
    ]
    for threshold, label in thresholds:
        if n_rows >= threshold:
            return label
    return "n<1K"


def _schema_table(df: pd.DataFrame, column_descriptions: dict[str, str] | None = None) -> str:
    """Generate a markdown table describing the DataFrame schema."""
    descs = column_descriptions or {}
    lines = [
        "| Column | Type | Description | Sample | Null % |",
        "|--------|------|-------------|--------|--------|",
    ]
    for col in df.columns:
        dtype = str(df[col].dtype)
        desc = descs.get(col, "")
        non_null = df[col].dropna()
        sample = str(non_null.iloc[0]) if len(non_null) > 0 else ""
        if len(sample) > 40:
            sample = sample[:37] + "..."
        null_pct = f"{df[col].isna().mean():.1%}"
        lines.append(f"| `{col}` | {dtype} | {desc} | {sample} | {null_pct} |")
    return "\n".join(lines)


def _quick_stats(df: pd.DataFrame) -> str:
    """Generate quick stats bullet list."""
    lines = [
        f"- **Rows:** {len(df):,}",
        f"- **Columns:** {len(df.columns)}",
    ]
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            min_date = df[col].min()
            max_date = df[col].max()
            if pd.notna(min_date) and pd.notna(max_date):
                lines.append(f"- **Date range:** {min_date:%Y-%m-%d} to {max_date:%Y-%m-%d}")
                break
    return "\n".join(lines)


def _ml_task_hint(task_categories: list[str]) -> str:
    """Generate ML task framing from HF task categories."""
    hints = {
        "time-series-forecasting": "time-series forecasting",
        "tabular-regression": "tabular regression",
        "tabular-classification": "tabular classification",
        "text-classification": "text classification",
    }
    tasks = [hints[t] for t in task_categories if t in hints]
    if not tasks:
        return ""
    joined = ", ".join(tasks)
    return f"This dataset is suitable for **{joined}** tasks."


def _citation_bibtex(repo: str, pretty_name: str) -> str:
    """Generate a BibTeX citation block."""
    year = datetime.now(timezone.utc).year
    key = repo.split("/")[-1].replace("-", "_")
    return f"""```bibtex
@dataset{{{key},
  title = {{{pretty_name}}},
  author = {{{repo.split("/")[0]}}},
  year = {{{year}}},
  url = {{https://huggingface.co/datasets/{repo}}},
  publisher = {{Hugging Face}}
}}
```"""


def generate_readme(
    repo: str,
    pretty_name: str,
    description: str,
    tags: list[str],
    df: pd.DataFrame,
    filename: str,
    source_url: str,
    license: str = "cc-by-4.0",
    language: list[str] | None = None,
    task_categories: list[str] | None = None,
    update_schedule: str | None = None,
    related_datasets: list[str] | None = None,
    collection_url: str | None = None,
    banner_markdown: str | None = None,
    column_descriptions: dict[str, str] | None = None,
    extra_sections: dict[str, str] | None = None,
    quick_stats: str | None = None,
    usage: str | None = None,
) -> str:
    """Generate a complete HF dataset card (README.md with YAML frontmatter).

    Args:
        repo: HF repo ID.
        pretty_name: Human-readable dataset title.
        description: Dataset description.
        tags: HF dataset tags.
        df: The DataFrame (drives schema, stats).
        filename: Parquet filename.
        source_url: URL of the original data source.
        license: License identifier.
        language: Language codes.
        task_categories: HF task categories.
        update_schedule: e.g., "Daily". Omit for static datasets.
        related_datasets: HF repo IDs of related datasets.
        collection_url: HF collection URL for backlink.
        banner_markdown: Pre-rendered banner HTML.
        column_descriptions: Column name -> description for schema.
        extra_sections: Additional sections as {heading: content}.
        quick_stats: Custom quick stats markdown. Replaces auto-generated stats if provided.
        usage: Custom usage snippet markdown. Replaces default load_dataset snippet if provided.

    Returns:
        Complete README string.
    """
    language = language or ["en"]
    task_categories = task_categories or ["other"]
    size_cat = _size_category(len(df))
    safe_name = _yaml_escape(pretty_name)
    short_desc = _yaml_escape(description[:200])

    tags_yaml = "\n".join(f"  - {_yaml_tag(t)}" for t in tags)
    lang_yaml = "\n".join(f"  - {_yaml_tag(l)}" for l in language)
    task_yaml = "\n".join(f"  - {_yaml_tag(t)}" for t in task_categories)

    frontmatter = f"""---
license: {license}
pretty_name: "{safe_name}"
language:
{lang_yaml}
description: "{short_desc}"
task_categories:
{task_yaml}
tags:
{tags_yaml}
size_categories:
  - {size_cat}
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/{filename}
    default: true
---"""

    sections = []
    sections.append(f"# {pretty_name}")
    if banner_markdown:
        sections.append(banner_markdown)
    if collection_url:
        sections.append(f"*Part of a [dataset collection]({collection_url}) on Hugging Face.*")
    sections.append("## Dataset description")
    sections.append(description)
    ml_hint = _ml_task_hint(task_categories)
    if ml_hint:
        sections.append(ml_hint)
    if extra_sections:
        for heading, content in extra_sections.items():
            sections.append(heading)
            sections.append(content)
    sections.append("## Schema")
    sections.append(_schema_table(df, column_descriptions))
    sections.append("## Quick stats")
    sections.append(quick_stats if quick_stats else _quick_stats(df))
    sections.append("## Usage")
    load_snippet = (
        f'```python\nfrom datasets import load_dataset\n\n'
        f'ds = load_dataset("{repo}", split="train")\n'
        f'df = ds.to_pandas()\n```'
    )
    sections.append(load_snippet)
    if usage:
        sections.append(usage)
    sections.append("## Data source")
    sections.append(source_url)
    if update_schedule:
        sections.append("## Update schedule")
        sections.append(update_schedule)
    if related_datasets:
        sections.append("## Related datasets")
        for ds_repo in related_datasets:
            sections.append(f"- [{ds_repo}](https://huggingface.co/datasets/{ds_repo})")
    sections.append(
        "> If you find this dataset useful, please consider "
        "[giving it a like](https://huggingface.co/datasets/"
        f"{repo}) on Hugging Face. It helps others discover it."
    )
    sections.append("## About the author")
    sections.append(
        "Created by [Julien Simon](https://julien.org) "
        "— AI Operating Partner at Fortino Capital. "
        "Part of the [Space Datasets](https://julien.org/datasets) collection."
    )
    sections.append("## Citation")
    sections.append(_citation_bibtex(repo, pretty_name))
    sections.append("## License")
    sections.append(f"[{license.upper()}](https://creativecommons.org/licenses/by/4.0/)")

    body = "\n\n".join(sections)
    return f"{frontmatter}\n\n{body}\n"
