# Engagement Boost Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Increase HuggingFace dataset downloads and likes by modifying the shared `hf_dataset_utils` library so that engagement improvements apply automatically to all 177 datasets on their next scheduled run.

**Architecture:** Three library changes (readme.py, pipeline.py, new crosslinks.py) inject engagement content into every README without touching individual scripts. One audit script validates coverage. All changes propagate via existing daily/weekly GitHub Actions workflows.

**Tech Stack:** Python, pandas, hf_dataset_utils library

---

### Task 1: Add engagement sections to `generate_readme()`

Modify the shared README generator to automatically include a `load_dataset()` one-liner at the top of every Usage section (even when custom usage is provided), a "like" CTA before Citation, and ML task framing.

**Files:**
- Modify: `scripts/hf_dataset_utils/readme.py:105-216`

- [ ] **Step 1: Add `_ml_task_hint()` helper after `_citation_bibtex()`**

Add this helper at line 103 (after `_citation_bibtex`):

```python
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
```

- [ ] **Step 2: Modify the Usage section in `generate_readme()`**

Replace lines 196-200 (the usage section logic) with:

```python
    sections.append("## Usage")
    # Always lead with load_dataset() one-liner
    load_snippet = f'```python\nfrom datasets import load_dataset\n\nds = load_dataset("{repo}", split="train")\ndf = ds.to_pandas()\n```'
    if usage:
        sections.append(load_snippet)
        sections.append(usage)
    else:
        sections.append(load_snippet)
```

- [ ] **Step 3: Add ML task hint after description**

In `generate_readme()`, after the description section (after line 187 `sections.append(description)`), add:

```python
    ml_hint = _ml_task_hint(task_categories)
    if ml_hint:
        sections.append(ml_hint)
```

- [ ] **Step 4: Add "like" CTA before Citation section**

Before the Citation section (before `sections.append("## Citation")`), add:

```python
    sections.append(
        "> If you find this dataset useful, please consider "
        "[giving it a like](https://huggingface.co/datasets/"
        f"{repo}) on Hugging Face. It helps others discover it."
    )
```

- [ ] **Step 5: Verify syntax**

Run: `python3 -c "import py_compile; py_compile.compile('scripts/hf_dataset_utils/readme.py', doraise=True)"`
Expected: No output (success)

- [ ] **Step 6: Commit**

```bash
git add scripts/hf_dataset_utils/readme.py
git commit -m "feat(readme): add load_dataset one-liner, ML task hint, like CTA to all READMEs"
```

---

### Task 2: Build domain-based cross-link registry

Create a new module that maps each domain to its datasets, enabling automatic cross-link suggestions. Modify `Pipeline` to auto-merge domain-based related datasets with explicitly provided ones.

**Files:**
- Create: `scripts/hf_dataset_utils/crosslinks.py`
- Modify: `scripts/hf_dataset_utils/pipeline.py:85-139`
- Modify: `scripts/hf_dataset_utils/__init__.py`

- [ ] **Step 1: Create `crosslinks.py`**

```python
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
    # Exclude self, take up to max_links
    related = [s for s in siblings if s != dataset_key][:max_links]
    return [f"{_PREFIX}{slug}" for slug in related]
```

- [ ] **Step 2: Modify `Pipeline.publish()` to auto-merge cross-links**

In `pipeline.py`, add import at top:

```python
from hf_dataset_utils.crosslinks import get_domain_crosslinks
```

Then in `publish()`, before the `generate_readme()` call (before line 125), add cross-link merging:

```python
        # Auto-merge domain-based cross-links
        related = list(self.related_datasets) if self.related_datasets else []
        domain_links = get_domain_crosslinks(dataset_name)
        for link in domain_links:
            if link not in related and link != f"juliensimon/{dataset_name}":
                related.append(link)
        merged_related = related or None
```

Then update the `generate_readme()` call to use `merged_related` instead of `self.related_datasets`:

```python
            related_datasets=merged_related,
```

- [ ] **Step 3: Add to `__init__.py`**

Add `get_domain_crosslinks` to imports and `__all__`:

```python
from hf_dataset_utils.crosslinks import get_domain_crosslinks
```

- [ ] **Step 4: Verify syntax**

Run: `python3 -c "import py_compile; py_compile.compile('scripts/hf_dataset_utils/crosslinks.py', doraise=True)" && python3 -c "import py_compile; py_compile.compile('scripts/hf_dataset_utils/pipeline.py', doraise=True)"`
Expected: No output (success)

- [ ] **Step 5: Commit**

```bash
git add scripts/hf_dataset_utils/crosslinks.py scripts/hf_dataset_utils/pipeline.py scripts/hf_dataset_utils/__init__.py
git commit -m "feat(crosslinks): auto-merge domain-based related datasets into READMEs"
```

---

### Task 3: Create engagement audit script

Build a script that analyzes all 177 dataset scripts and reports engagement gaps (missing banners, thin descriptions, missing cross-links, missing tags).

**Files:**
- Create: `scripts/audit_engagement.py`

- [ ] **Step 1: Create `audit_engagement.py`**

```python
"""Audit dataset scripts for engagement gaps.

Usage:
    python scripts/audit_engagement.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
REQUIRED_TAGS = {"space", "open-data", "tabular-data", "parquet"}


def _extract_string_constant(node: ast.AST) -> str | None:
    """Extract string value from an AST Constant node."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "<f-string>"
    return None


def audit_script(path: Path) -> dict:
    """Audit a single update script for engagement signals."""
    source = path.read_text()
    issues = []
    dataset_name = path.stem.replace("update-", "")

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {"dataset": dataset_name, "issues": ["SYNTAX ERROR"]}

    # Walk AST looking for Pipeline() constructor call
    pipeline_kwargs: dict[str, ast.AST] = {}
    publish_kwargs: dict[str, ast.AST] = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = ""
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name == "Pipeline":
                for kw in node.keywords:
                    pipeline_kwargs[kw.arg] = kw.value
            if name == "publish":
                for kw in node.keywords:
                    publish_kwargs[kw.arg] = kw.value

    # Check description length
    desc_node = pipeline_kwargs.get("description")
    if desc_node:
        desc = _extract_string_constant(desc_node)
        if desc and len(desc) < 100:
            issues.append(f"Short description ({len(desc)} chars, aim for 200+)")
    else:
        # Check if DESCRIPTION is a module-level constant
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "DESCRIPTION":
                        desc = _extract_string_constant(node.value)
                        if desc and len(desc) < 100:
                            issues.append(f"Short DESCRIPTION ({len(desc)} chars)")

    # Check tags
    tags_node = pipeline_kwargs.get("tags")
    if isinstance(tags_node, ast.List):
        tag_values = set()
        for elt in tags_node.elts:
            v = _extract_string_constant(elt)
            if v:
                tag_values.add(v)
        missing = REQUIRED_TAGS - tag_values
        if missing:
            issues.append(f"Missing tags: {', '.join(sorted(missing))}")

    # Check related_datasets
    related_node = pipeline_kwargs.get("related_datasets")
    if isinstance(related_node, ast.List):
        if len(related_node.elts) == 0:
            issues.append("Empty related_datasets list")
    elif related_node is None:
        issues.append("No related_datasets parameter")

    # Check banner
    banner_node = pipeline_kwargs.get("banner")
    if isinstance(banner_node, ast.Dict):
        if len(banner_node.keys) == 0:
            issues.append("Empty banner dict")

    # Check column_descriptions
    col_desc_node = publish_kwargs.get("column_descriptions")
    if col_desc_node is None:
        issues.append("No column_descriptions in publish()")

    # Check collection_url
    collection_node = pipeline_kwargs.get("collection_url")
    if collection_node is None:
        issues.append("No collection_url")

    return {"dataset": dataset_name, "issues": issues}


def main():
    scripts = sorted(SCRIPTS_DIR.glob("update-*.py"))
    print(f"Auditing {len(scripts)} dataset scripts for engagement gaps...\n")

    total_issues = 0
    results = []

    for script in scripts:
        result = audit_script(script)
        results.append(result)
        total_issues += len(result["issues"])

    # Summary by issue type
    issue_counts: dict[str, int] = {}
    for r in results:
        for issue in r["issues"]:
            key = issue.split("(")[0].split(":")[0].strip()
            issue_counts[key] = issue_counts.get(key, 0) + 1

    print("=== Issue Summary ===")
    for issue, count in sorted(issue_counts.items(), key=lambda x: -x[1]):
        print(f"  {count:3d}  {issue}")
    print(f"\nTotal: {total_issues} issues across {len(scripts)} scripts")

    # Detail for scripts with issues
    scripts_with_issues = [r for r in results if r["issues"]]
    if scripts_with_issues:
        print(f"\n=== Scripts with Issues ({len(scripts_with_issues)}) ===")
        for r in scripts_with_issues:
            print(f"\n  {r['dataset']}:")
            for issue in r["issues"]:
                print(f"    - {issue}")

    # Clean scripts
    clean = [r for r in results if not r["issues"]]
    print(f"\n=== Clean Scripts ({len(clean)}) ===")
    for r in clean:
        print(f"  {r['dataset']}")

    return 1 if total_issues > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run the audit**

Run: `cd /Users/julien/Development/repos/space-datasets && python scripts/audit_engagement.py`
Expected: Summary of engagement gaps across all scripts

- [ ] **Step 3: Commit**

```bash
git add scripts/audit_engagement.py
git commit -m "feat: add engagement audit script for dataset quality reporting"
```

---

### Task 4: Smoke-test the full pipeline

Run one dataset script in dry-run to verify the README changes render correctly.

**Files:**
- No files modified

- [ ] **Step 1: Pick a small, fast dataset and inspect its generated README**

Run a quick import test to ensure all modules load:

```bash
cd /Users/julien/Development/repos/space-datasets
python3 -c "
import sys; sys.path.insert(0, 'scripts')
from hf_dataset_utils.readme import generate_readme, _ml_task_hint
from hf_dataset_utils.crosslinks import get_domain_crosslinks
from hf_dataset_utils.pipeline import Pipeline

# Test ML hint
hint = _ml_task_hint(['time-series-forecasting', 'tabular-regression'])
assert 'time-series forecasting' in hint
assert 'tabular regression' in hint

# Test crosslinks
links = get_domain_crosslinks('neo')
assert any('sentry' in l for l in links)
assert not any('neo' in l for l in links)  # should exclude self

# Test generate_readme produces new sections
import pandas as pd
df = pd.DataFrame({'a': [1,2,3], 'b': ['x','y','z']})
readme = generate_readme(
    repo='juliensimon/test', pretty_name='Test', description='A test dataset.',
    tags=['space', 'open-data'], df=df, filename='test.parquet',
    source_url='https://example.com',
    task_categories=['tabular-regression'],
    usage='Custom usage here',
)
assert 'load_dataset' in readme  # one-liner always present
assert 'Custom usage here' in readme  # custom usage preserved
assert 'tabular regression' in readme  # ML hint present
assert 'giving it a like' in readme  # CTA present
print('All checks passed.')
"
```

Expected: `All checks passed.`

- [ ] **Step 2: Commit (no changes needed, just verification)**

No commit needed — this is a verification step.
