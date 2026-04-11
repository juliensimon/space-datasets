"""GitHub Actions helpers: output emission and workflow generation."""

from __future__ import annotations

import os


def emit_output(rows: int) -> None:
    """Write row count to GITHUB_OUTPUT if running in GitHub Actions.

    No-op when GITHUB_OUTPUT env var is not set.

    Args:
        rows: Number of rows in the published dataset.
    """
    gh_output = os.environ.get("GITHUB_OUTPUT")
    if gh_output:
        with open(gh_output, "a") as f:
            f.write(f"rows={rows}\n")


def generate_workflow(
    name: str,
    script: str,
    cron: str,
    status_key: str,
    extra_pip: list[str] | None = None,
) -> str:
    """Generate a GitHub Actions workflow YAML for a dataset pipeline.

    Args:
        name: Workflow display name.
        script: Path to the Python script.
        cron: Cron expression.
        status_key: Key for update-status.py.
        extra_pip: Additional pip packages beyond defaults.

    Returns:
        Complete workflow YAML as a string.
    """
    pip_packages = ["pandas", "pyarrow", "requests", "huggingface_hub[hf_xet]"]
    if extra_pip:
        pip_packages.extend(extra_pip)
    pip_line = " ".join(pip_packages)

    return f"""name: {name}
on:
  schedule:
    - cron: '{cron}'
  workflow_dispatch:
permissions:
  contents: write
jobs:
  update:
    runs-on: ubuntu-latest
    environment: HF
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install {pip_line}
      - name: Run pipeline
        id: update
        run: python {script}
        env:
          HF_TOKEN: ${{{{ secrets.HF_TOKEN }}}}
      - name: Update and push status
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          for i in 1 2 3; do
            git pull --rebase || true
            git checkout status.json 2>/dev/null || true
            python scripts/update-status.py {status_key} --rows ${{{{ steps.update.outputs.rows }}}}
            git add status.json
            git diff --cached --quiet && break
            git commit -m "status: {status_key} updated $(date -u +%Y-%m-%d)"
            git push && break
            echo "Push failed (attempt $i), retrying..."
            git reset HEAD~1
            sleep 2
          done
"""
