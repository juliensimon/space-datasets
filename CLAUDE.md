# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Automated data pipelines that fetch public space data (orbital mechanics, space weather, astronomy, physics), convert to Parquet with zstd compression, and upload to Hugging Face under `juliensimon/`. Currently 207 datasets with 90 GitHub Actions workflows for daily/weekly updates. Static datasets (uploaded once) have no workflow.

## Running a Dataset Pipeline

```bash
pip install -r requirements.txt
# Some scripts need extras: netCDF4 (solar-flares), beautifulsoup4/lxml (already in requirements.txt)

# Run any single pipeline:
HF_TOKEN=hf_xxx python scripts/update-<dataset>.py

# Local testing without HF upload: script fails at `hf upload` but parquet is written to temp dir first
# Syntax check: python3 -c "import py_compile; py_compile.compile('scripts/update-<name>.py', doraise=True)"
```

There is no test suite, linter, or build system. Validation happens inside each script via `validate.py`.

## Architecture

**One script per dataset.** Every pipeline follows the same 6-step pattern:

1. **Fetch** — HTTP request(s) to public API or file download
2. **Transform** — pandas DataFrame: type coercion, column rename, derived columns
3. **Validate** — `check_dataset()` via `hf_dataset_utils` (min rows, expected columns, null thresholds, row trend)
4. **Write** — `df.to_parquet(..., compression="zstd")` + generate README.md with HF metadata frontmatter
5. **Upload** — via `Pipeline.publish()` or `upload_to_hf()` from `hf_dataset_utils`
6. **Status** — workflow calls `python scripts/update-status.py <key> [--rows N]` → updates `status.json`

**Two update strategies:**
- **Full rebuild**: re-fetches entire source. Used when source is a single file or dataset is small.
- **Incremental**: downloads existing parquet from HF, fetches recent window (7–14 days), merges/deduplicates via `pd.concat` + `drop_duplicates(keep="last")`. Falls back to full rebuild if no existing data. Used by: starlink, constellation-census, donki, dst-index, solar-flares, solar-wind, kp-index.

## Key Files

- `scripts/hf_dataset_utils/` — shared Pipeline library used by all 184 dataset scripts. Provides `Pipeline` context manager that handles temp dirs, parquet writing (zstd), README generation, validation (`check_dataset()`), banner images, and HF upload. Key modules: `pipeline.py`, `validation.py`, `banner.py`, `readme.py`, `upload.py`, `tap.py` (VizieR/HEASARC TAP).
- `scripts/validate.py` — legacy `check_dataset()` function (now re-exported from `hf_dataset_utils.validation`).
- `scripts/vizier_tap.py` — legacy VizieR TAP client (now re-exported from `hf_dataset_utils.tap`).
- `scripts/jpl_api.py` — shared helpers for NASA JPL SSD API (NEO, SBDB, Sentry, NHATS). Converts `{"fields": [...], "data": [[...]]}` format to DataFrame.
- `scripts/update-status.py` — updates `status.json` with date and optional row count.
- `scripts/dataset_images.py` — centralized banner image config for HF READMEs. Maps datasets to domains, provides `download_banner()` and `banner_markdown()` helpers. Images are NASA public domain / ESA CC-BY 4.0. New datasets must be added to `DATASET_DOMAIN` dict.
- `scripts/add-to-collections.py` — adds datasets to HF domain collections.
- `status.json` — tracks last-updated date per dataset + `_rows` dict with row counts.
- `CHECKLIST.md` — detailed checklist for adding new datasets (frontmatter fields, workflow template, pitfalls).

## Adding a New Dataset

Create the script (and workflow if not static) following existing patterns. Reference `CHECKLIST.md` for the full procedure. Key files to use as models:
- Full rebuild: `update-neo.py`, `update-exoplanets.py`
- Incremental: `update-donki.py`, `update-starlink.py`
- VizieR TAP source: `update-pulsars.py`, `update-quasars.py`
- HEASARC TAP source: `update-grb.py`, `update-fermi-4fgl.py`

### Conventions

- HF repo name: `juliensimon/<descriptive-name>` (kebab-case)
- Parquet file goes in `data/` subdir within the temp upload directory
- README.md uses HF dataset card frontmatter (license: cc-by-4.0, tags, size_categories, configs with explicit split/path)
- Column names: snake_case, descriptive (e.g., `distance_au` not `dist`)
- Always call `check_dataset()` before upload
- Output row count for status tracking
- Add badge + table row to repo `README.md`
- Add to correct HF collection (Orbital/Planetary/Weather/Astronomy/Physics)
- Static datasets get a script only, no GitHub Actions workflow

## Workflow Template

```yaml
name: Update DATASET
on:
  schedule:
    - cron: '0 6 * * *'  # stagger across 06:00-19:30 UTC range
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

## Data Source Gotchas

APIs are unauthenticated except HF uploads and Space-Track (TLE history). Use `time.sleep()` between sequential API calls and set `timeout=` on requests.

**Space-Track** (`update-tle-history.py`): requires `SPACETRACK_USER` and `SPACETRACK_PASS` secrets in the HF environment. Makes exactly 2 requests/day (login + GP history for yesterday). Be extremely conservative with rate limits — the account has been banned before.

| Source | Gotcha |
|--------|--------|
| VizieR TAP | Always `SELECT *`, check actual CSV headers with curl. Column names may differ from docs (e.g. `logAge50` not `Age`, brackets get sanitized). No OFFSET — use `recno` pagination via `vizier_tap.py`. |
| HEASARC TAP | Use `FORMAT=text` (pipe-delimited). `FORMAT=csv` returns VOTable XML. |
| SIMBAD TAP | Use `basic` table only — JOINs with `allfluxes`/`mesDistance` fail. Use `OR` chains, not `IN (...)`. No `regexp()`. |
| CelesTrak | 500 errors are common — add 1s delay + 3 retries with exponential backoff. |
| GFZ Kp API | Unreliable — use NOAA SWPC endpoint instead. |
| Space-Track | Authenticated (cookie session). Max 2 requests/day for the daily pipeline. GP history returns only TLEs *generated* that day, not a complete snapshot — use forward-fill for backfills. Account has been banned before for aggressive usage. |
