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
        if desc and desc != "<f-string>" and len(desc) < 100:
            issues.append(f"Short description ({len(desc)} chars, aim for 200+)")
    else:
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "DESCRIPTION":
                        desc = _extract_string_constant(node.value)
                        if desc and desc != "<f-string>" and len(desc) < 100:
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
