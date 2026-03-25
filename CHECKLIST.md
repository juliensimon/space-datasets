# Dataset Addition Checklist

Reusable checklist for adding any new dataset to `juliensimon/space-datasets`. Learned from building 23 datasets.

---

## 1. Pipeline Script (`scripts/update-<name>.py`)

- [ ] Fetch data from source with `timeout=` + error handling
- [ ] Add retry logic with exponential backoff for flaky APIs (CelesTrak, HEASARC, SIMBAD)
- [ ] Type coercion: dates → `pd.to_datetime`, IDs → `int32`, numerics → `pd.to_numeric(errors="coerce")`
- [ ] Column rename to snake_case
- [ ] Guard optional columns: `if "col" in df.columns` before accessing
- [ ] Derive computed fields (classifications, categories, flags)
- [ ] Call `check_dataset(df, name, min_rows=N, expected_columns=[...], critical_columns=[...])`
- [ ] Write parquet with zstd: `df.to_parquet(path, index=False, engine="pyarrow", compression="zstd")`
- [ ] Upload via `hf upload` CLI: `["hf", "upload", HF_REPO, str(tmp_dir), ".", "--repo-type", "dataset", "--commit-message", msg]`
- [ ] Emit row count to `$GITHUB_OUTPUT` for status tracking

### If incremental:

- [ ] Download existing parquet from HF via `hf download` in a temp dir
- [ ] Fetch only new/recent data (date window, not full rebuild)
- [ ] Merge: `pd.concat` + `drop_duplicates` by primary key, `keep="last"`
- [ ] Fall back to full rebuild when existing data can't be loaded
- [ ] Verify idempotency: same-day re-run must not create duplicate rows

### If using TAP/ADQL (HEASARC, SIMBAD, VizieR, Gaia):

- [ ] Test ADQL query in isolation first (curl or browser)
- [ ] HEASARC: use `FORMAT=text` (pipe-delimited) — CSV returns VOTable XML
- [ ] SIMBAD: avoid JOINs with `allfluxes`/`mesDistance`. Use `basic` table only
- [ ] SIMBAD: use `OR` chains, not `IN (...)`. No `regexp()` function
- [ ] VizieR/Gaia: use `FORMAT=csv` (usually works correctly)

---

## 2. HF README — YAML Frontmatter

Required fields for discoverability (HF indexes these for search):

- [ ] `license: cc-by-4.0` (or `cc-by-sa-4.0` if upstream requires)
- [ ] `pretty_name:` — appears in search results as title
- [ ] `language: [en]` — enables language filter
- [ ] `description:` — 1-2 sentences, Google-indexed subtitle
- [ ] `size_categories:` — e.g. `n<1K`, `1K<n<10K`, `10K<n<100K`, `100K<n<1M`
- [ ] `task_categories:` — e.g. `tabular-classification`, `time-series-forecasting`
- [ ] `tags:` — include `open-data` + domain terms + source names (nasa, noaa, esa, etc.)
- [ ] `configs:` — list each parquet config with explicit split/path format:
  ```yaml
  configs:
    - config_name: default
      data_files:
        - split: train
          path: data/file.parquet
      default: true
  ```

---

## 3. HF README — Body Content

- [ ] Title as H1 with dataset name
- [ ] CI badge: `![Update](https://github.com/juliensimon/space-datasets/actions/workflows/update-<name>.yml/badge.svg)`
- [ ] Dynamic "updated" badge from status.json (use `$['key-name']` for hyphenated keys)
- [ ] 1-paragraph description with **bold** key stats
- [ ] Schema table: Column | Type | Description (for each config)
- [ ] Usage section with `load_dataset()` Python example
- [ ] Data source section with attribution and URL
- [ ] Update frequency note (daily/weekly/monthly/quarterly at HH:MM UTC)
- [ ] Related datasets section (cross-link siblings in same domain)
- [ ] Pipeline source link: `Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)`
- [ ] Citation bibtex block with correct HF URL matching `HF_REPO` constant

---

## 4. GitHub Actions Workflow (`.github/workflows/update-<name>.yml`)

- [ ] Cron schedule staggered from existing workflows (check range: 06:00–19:30 UTC)
- [ ] `workflow_dispatch:` for manual runs
- [ ] `permissions: contents: write`
- [ ] `environment: HF` (where `HF_TOKEN` secret lives)
- [ ] Python 3.12 + `pip install pandas pyarrow requests huggingface_hub[hf_xet]` (+ extra deps if needed)
- [ ] Capture `steps.update.outputs.rows` from script via `id: update`
- [ ] Status.json update block with 3-attempt retry loop:
  ```yaml
  for i in 1 2 3; do
    git pull --rebase || true
    git checkout status.json 2>/dev/null || true
    python scripts/update-status.py <name> --rows ${{ steps.update.outputs.rows }}
    git add status.json
    git diff --cached --quiet && break
    git commit -m "status: <name> updated $(date -u +%Y-%m-%d)"
    git push && break
    echo "Push failed (attempt $i), retrying..."
    git reset HEAD~1
    sleep 2
  done
  ```
- [ ] No untrusted user inputs in `run:` blocks (only `steps.update.outputs.rows` + `date -u`)

---

## 5. Data Quality Validation

- [ ] `min_rows` threshold set based on expected dataset size
- [ ] `expected_columns` lists all required columns
- [ ] `critical_columns` lists columns that must be <5% null
- [ ] Row trend check enabled via `validate.py` `_check_row_trend` (warns on >20% drop)
- [ ] Spot-check known values (e.g. GW150914 in GW dataset, Kepler-452b in exoplanets, ISS in SATCAT)

---

## 6. Repository Updates

- [ ] Add dataset entry to `status.json` with initial date value
- [ ] Verify `status.json` is valid JSON after editing: `python3 -c "import json; json.loads(open('status.json').read())"`
- [ ] Add dataset to GitHub `README.md`:
  - [ ] Badge in badge row at top
  - [ ] Row in correct domain table (Orbital / Space Weather / Astronomy)
  - [ ] Description column with plain-English summary + specific numbers
  - [ ] Manual run command in the `## Manual run` section
- [ ] Add to data sources table if new source
- [ ] Add to correct HF domain collection (or run `python scripts/add-to-collections.py`):
  - Orbital: `juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994`
  - Planetary: `juliensimon/planetary-science-datasets-69c2d4683bd6a66c34fb4af2`
  - Weather: `juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70`
  - Astronomy: `juliensimon/astronomy-datasets-69c24caf2f17e36128946743`
  - Physics: `juliensimon/physics-datasets-69c2d4682d37dfdb77447bd7`
- [ ] Cross-reference in related datasets' HF READMEs (nice-to-have)

---

## 7. Post-Launch Checks

- [ ] Script compiles: `python3 -c "import py_compile; py_compile.compile('scripts/update-<name>.py', doraise=True)"`
- [ ] Workflow YAML is valid: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/update-<name>.yml'))"`
- [ ] Run script locally — check row counts match expectations
- [ ] Verify parquet loads locally: `load_dataset("juliensimon/<name>", split="train")`
- [ ] Trigger `workflow_dispatch` — badge shows "no status" until first run
- [ ] Confirm workflow succeeds: `gh run list --repo juliensimon/space-datasets --limit 1`
- [ ] Check HF dataset viewer: `curl -s "https://datasets-server.huggingface.co/is-valid?dataset=juliensimon/<name>"` → `viewer: true`
- [ ] Check HF first-rows: `curl -s "https://datasets-server.huggingface.co/first-rows?dataset=juliensimon/<name>&config=default&split=train"` → rows returned
- [ ] README renders correctly on HF dataset page
- [ ] Badges show green (CI badge + status.json dynamic badge)
- [ ] Second run is idempotent (same-day re-run doesn't duplicate rows)
- [ ] Collection page shows new dataset

---

## Common Pitfalls (quick reference)

| Pitfall | Fix |
|---------|-----|
| PyArrow 19.0.0 read bug | `pip install 'pyarrow>=19.0.1'` |
| CelesTrak 500 errors | 1s delay + 3 retries with 2/4/6s backoff |
| HEASARC returns VOTable for CSV | Use `FORMAT=text` (pipe-delimited) |
| SIMBAD JOINs fail with 400 | Use `basic` table only, no joins |
| GFZ Kp API returns 500 | Use NOAA SWPC endpoint instead |
| Badge "no status" | Trigger `workflow_dispatch` after first push |
| status.json push race | 3-attempt `git pull --rebase` retry loop |
| Optional column missing | Guard with `if "col" in df.columns` |
| VizieR column names differ from docs | Always use `SELECT *`, check actual CSV headers with `curl`, add all name variants to rename dict |
| README stats always 0 | The stat references a column that doesn't exist after rename — verify column actually gets created by running locally first |
| Boolean column destroyed by string cleaning | Create derived boolean columns AFTER `df.select_dtypes(include=["object"])` cleaning loop, not before |
| VizieR `[Fe/H]` brackets | VizieR sanitizes special chars in column names — check actual CSV output, don't assume bracket notation works |
| VizieR age/distance columns | Hunt & Reffert uses `logAge50`/`dist50` (with percentile suffixes), not `Age`/`Dist` |
| Multi-config viewer issues | Use explicit `split: train` + `path:` format + `default: true` |
| HF viewer "no status" | Wait 1-2 min after upload, then check `is-valid` API |
