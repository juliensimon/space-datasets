# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Automated data pipelines that fetch public space data (orbital mechanics, space weather, astronomy), convert to Parquet with zstd compression, and upload to Hugging Face. Currently 23 datasets, all under `juliensimon/` on HF.

## Running a Dataset Pipeline

```bash
pip install -r requirements.txt
# Some scripts need extras: netCDF4 (solar-flares)

# Run any single pipeline:
HF_TOKEN=hf_xxx python scripts/update-<dataset>.py

# Skip HF upload for local testing: the script will fail at the `hf upload` step
# but the parquet file will be written to a temp dir before that
```

There is no test suite, linter, or build system. Validation happens inside each script via `validate.py`.

## Architecture

**One script + one workflow per dataset.** Every dataset follows the same pattern:

1. **Fetch** — HTTP request(s) to public API or file download
2. **Transform** — pandas DataFrame: type coercion, column rename, derived columns
3. **Validate** — `check_dataset()` from `scripts/validate.py` (min rows, expected columns, null thresholds, row trend)
4. **Write** — `df.to_parquet(..., compression="zstd")` + generate README.md with HF metadata frontmatter
5. **Upload** — `hf upload <repo> <tmpdir> . --repo-type dataset`
6. **Status** — workflow calls `python scripts/update-status.py <key> [--rows N]` → updates `status.json`

**Two update strategies:**
- **Full rebuild**: re-fetches entire source. Used when source is a single file or dataset is small.
- **Incremental**: downloads existing parquet from HF, fetches recent window (7–14 days), merges/deduplicates. Falls back to full rebuild if no existing data. Used by: starlink, constellation-census, donki, dst-index, solar-flares, solar-wind, kp-index.

## Key Files

- `scripts/validate.py` — shared `check_dataset()` function. Hard-fails on row count or missing columns; warns on null thresholds and row-count drops >20%.
- `scripts/update-status.py` — updates `status.json` with date and optional row count. Called by every workflow.
- `status.json` — tracks last-updated date per dataset + `_rows` dict with row counts.
- `.github/workflows/update-<dataset>.yml` — GitHub Actions workflows. All use Python 3.12, `environment: HF` (for `HF_TOKEN` secret), and a 3-attempt retry loop for git push conflicts on status.json.

## Adding a New Dataset

Create two files following existing patterns (e.g., `update-neo.py` for full-rebuild, `update-donki.py` for incremental):

1. **`scripts/update-<name>.py`** — fetch, transform, validate, write parquet + README, upload via `hf upload`
2. **`.github/workflows/update-<name>.yml`** — schedule, pip install, run script, update-status.py + git push

Conventions:
- HF repo name: `juliensimon/<descriptive-name>` (kebab-case)
- Parquet file goes in `data/` subdir within the temp upload directory
- README.md uses HF dataset card frontmatter (license: cc-by-4.0, tags, size_categories)
- Column names: snake_case, descriptive (e.g., `distance_au` not `dist`)
- Always call `check_dataset()` before upload
- Output row count for status tracking
- Add badge to repo README.md

## Workflow Template

```yaml
name: Update DATASET
on:
  schedule:
    - cron: '0 6 * * *'
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
      - run: pip install pandas pyarrow requests huggingface_hub[hf_xet]
      - run: python scripts/update-<name>.py
        env:
          HF_TOKEN: ${{ secrets.HF_TOKEN }}
      - name: Update and push status
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          for i in 1 2 3; do
            git pull --rebase || true
            git checkout status.json 2>/dev/null || true
            python scripts/update-status.py <key> --rows ${{ steps.update.outputs.rows }}
            git add status.json
            git diff --cached --quiet && break
            git commit -m "status: <key> updated $(date -u +%Y-%m-%d)"
            git push && break
            echo "Push failed (attempt $i), retrying..."
            git reset HEAD~1
            sleep 2
          done
```

## Data Sources

APIs are unauthenticated (except HF uploads). Be polite: use `time.sleep()` between sequential API calls, set reasonable `timeout=` on requests. Many sources (VizieR, HEASARC, NASA APIs) have rate limits but no auth.
