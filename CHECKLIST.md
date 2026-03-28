# Dataset Addition Checklist

Reusable checklist for adding any new dataset to `juliensimon/space-datasets`. Learned from building 85 datasets.

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
- [ ] HEASARC: if using multi-format fallback (CSV→JSON→text), always add XML guard: `if not resp.text.strip().startswith("<?xml")` before CSV parse
- [ ] HEASARC: add column sanity check after parse (e.g., `and "ra" in df.columns`), not just row count
- [ ] SIMBAD: avoid JOINs with `allfluxes`/`mesDistance`. Use `basic` table only
- [ ] SIMBAD: use `OR` chains, not `IN (...)`. No `regexp()` function
- [ ] VizieR/Gaia: use `FORMAT=csv` (usually works correctly)

---

## 2. HF README — YAML Frontmatter

Required fields for discoverability (HF indexes these for search):

- [ ] `license: cc-by-4.0` (or `cc-by-sa-4.0` if upstream requires)
- [ ] `pretty_name:` — appears in HF search results as title. Use a descriptive, human-readable name (not the repo slug)
- [ ] `language: [en]` — enables language filter
- [ ] `description:` — 1-2 sentences optimized for search snippets. Include: source name, row count/scope, date range, key content. Template: `"{What} from {Source} ({scope}). {Key detail}."` Example: `"All asteroid and comet close approaches to Earth within 0.05 AU (1900-2100) from NASA JPL CNEOS. Updated daily."`
- [ ] `size_categories:` — e.g. `n<1K`, `1K<n<10K`, `10K<n<100K`, `100K<n<1M`
- [ ] `task_categories:` — e.g. `tabular-classification`, `time-series-forecasting`
- [ ] `tags:` — MUST include these 4 mandatory umbrella tags + domain terms + source names:
  - `space` — brand umbrella (every dataset, including physics-only)
  - `open-data` — discoverability in HF "open data" searches
  - `tabular-data` — format category
  - `parquet` — format filter (HF users search by this)
  - Plus domain terms: `astronomy`, `space-weather`, `orbital-mechanics`, `physics`, `planetary-science`, etc.
  - Plus source names: `nasa`, `noaa`, `esa`, `jpl`, etc.
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

## 3. HF README — Body Content (SEO-optimized structure)

Each section serves a dual purpose: human readability AND search engine discoverability.

- [ ] **H1 title** — must match `pretty_name`. This is the strongest on-page SEO signal
- [ ] **Collection backlink** — `*Part of the [Domain Datasets](...) collection on Hugging Face.*` (improves HF nav graph)
- [ ] **CI badge** + **dynamic "updated" badge** — freshness signals for search engines
- [ ] **Keyword-rich intro paragraph** — 2-3 sentences with **bold** key stats (row count, date range, source). Front-load important terms. This paragraph often becomes the Google snippet
- [ ] **Schema table** — Column | Type | Description. Schema tables rank for "[dataset] columns" queries
- [ ] **Quick stats** — computed from data (e.g., "closest approach: X at Y km"). Unique content helps differentiation
- [ ] **Usage section** with `load_dataset()` Python example — ranks for "[dataset] python example" queries. Include 3-5 realistic use cases (filtering, aggregation)
- [ ] **Data source section** with attribution URL — backlink to authoritative source (trust signal)
- [ ] **Update frequency** note (daily/weekly/monthly/quarterly at HH:MM UTC)
- [ ] **Related datasets** section — cross-link 3-4 siblings in same domain/collection (internal linking improves SEO for all linked pages)
- [ ] **Pipeline source link**: `Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)` (backlink to GitHub)
- [ ] **Support section**: `If you find this dataset useful, please give it a ❤️ on the dataset page and share feedback in the Community tab!`
- [ ] **Citation bibtex block** — with correct HF URL. Critical for academic discoverability (Google Scholar indexes BibTeX)
- [ ] **License** — `[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)` (always link, never just "MIT" or plain text)

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
- [ ] Update GitHub repo description if dataset count milestone crossed: `gh repo edit juliensimon/space-datasets --description "..."`
- [ ] Add dataset to GitHub `README.md`:
  - [ ] Update dataset count in opening paragraph (`100+` → new count)
  - [ ] Badge in badge row at top (refreshing datasets only, grouped by domain comment)
  - [ ] Row in correct domain table (Orbital / Space Probes / Planetary / Space Weather / Astronomy / Physics)
  - [ ] Description column with plain-English summary + specific numbers
  - [ ] Manual run command in the `## Manual run` section (in correct domain group)
  - [ ] Add to data sources table if new source
- [ ] Add dataset to `scripts/add-to-collections.py` in the correct collection list(s), then run it:
  - **Parent collections** (umbrella — add every dataset to the relevant parent):
    - Orbital: `juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994`
    - Planetary: `juliensimon/planetary-science-datasets-69c2d4683bd6a66c34fb4af2`
    - Weather: `juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70`
    - Astronomy: `juliensimon/astronomy-datasets-69c24caf2f17e36128946743`
    - Physics: `juliensimon/physics-datasets-69c2d4682d37dfdb77447bd7`
    - Solar System: `juliensimon/solar-system-datasets-69c6fa681978de62dff2f347`
  - **Sub-collections** (focused — also add to the best-fit sub-collection):
    - Stellar Catalogs: `juliensimon/stellar-catalogs-69c792b1a52ab2757b0eaa57`
    - Variable Stars & Transients: `juliensimon/variable-stars-and-transients-69c792b1dd7a45812c5a9b36`
    - Galaxies & Cosmology: `juliensimon/galaxies-and-cosmology-69c792b117242a3b236df55d`
    - Sky Surveys: `juliensimon/sky-surveys-69c792b17d77aba7996e2442`
    - Satellites & Launches: `juliensimon/satellites-and-launches-69c792b1fca01f437233082d`
    - Asteroids & Small Bodies: `juliensimon/asteroids-and-small-bodies-69c792b1e0240f3bf1235c66`
- [ ] Update `CANDIDATES.md`: move from remaining to built, update counts, renumber
- [ ] Update `CHECKLIST.md` dataset count if a round number was crossed
- [ ] Cross-reference in related datasets' HF READMEs (nice-to-have)
- [ ] Commit and push all changes (README, CANDIDATES, CHECKLIST, add-to-collections.py, scripts, workflows)

---

## 7. Post-Launch Checks

**Every script must be run locally before considering it done.** Do not skip this — compile-only verification is insufficient.

- [ ] Script compiles: `python3 -c "import py_compile; py_compile.compile('scripts/update-<name>.py', doraise=True)"`
- [ ] Workflow YAML is valid (if applicable): `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/update-<name>.yml'))"`
- [ ] **Run script locally with HF_TOKEN** — verify row count, parquet written, and HF upload succeeds
- [ ] Check HF dataset viewer: `curl -s "https://datasets-server.huggingface.co/is-valid?dataset=juliensimon/<name>"` → `viewer: true`
- [ ] Check HF first-rows: `curl -s "https://datasets-server.huggingface.co/first-rows?dataset=juliensimon/<name>&config=default&split=train"` → rows returned
- [ ] **Add to HF collection** — update `scripts/add-to-collections.py` and run it, or use `add_collection_item()` directly
- [ ] Verify dataset appears on the correct HF collection page
- [ ] README renders correctly on HF dataset page
- [ ] Commit and push all changes to GitHub
- [ ] Verify GitHub README shows the new dataset (badge, table row, manual run command)
- [ ] For refreshing datasets: trigger `workflow_dispatch` and confirm workflow succeeds
- [ ] Badges show green (CI badge + status.json dynamic badge)
- [ ] Second run is idempotent (same-day re-run doesn't duplicate rows)

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
| Multi-config viewer issues | Use explicit `split: train` + `path:` format + `default: true` on one config |
| Multi-config missing `default: true` | `load_dataset()` fails without it — always set `default: true` on the primary config |
| HF viewer "no status" | Wait 1-2 min after upload, then check `is-valid` API |
| HEASARC CSV returns XML silently | `pd.read_csv()` may parse XML as garbage without error — always check `startswith("<?xml")` before parse |
| PDS/GCAT column names with trailing spaces | Strip column names with `df.columns = df.columns.str.strip()` after read |
| Day-of-year datetime format (YYYY-DDDTHH:MM:SS) | Use `pd.to_datetime(col, format="%Y-%jT%H:%M:%S")` — dateutil fallback silently returns NaT |
| README f-string crash on NaN stats | Guard computed stats (e.g., `heaviest = df.loc[df["mass"].idxmax()]`) with `is not None` before using in f-strings |
| Over-broad numeric column matching | Use `startswith()` prefix matching, not `in` substring matching — `"ra" in "separation"` matches incorrectly |
| NASA data.nasa.gov SODA API | Endpoints may go 404 without notice (e.g., `y77d-th95` as of 2026-03). Test before committing |
| HEASARC TAP sync truncates large tables | Sync endpoint has a server-side row limit (~28K for some tables). Add `MAXREC=500000` but it may not help — verify row count matches expected. For 100K+ tables, consider async TAP or VizieR mirror |
| VizieR catalog sizes differ from docs | VLASS component catalog is 3.4M rows (not 700K as listed in papers). Always check actual row count from `vizier_query()` and adjust `size_categories` accordingly |
| `import` inside function body | Keep all imports at file top level for consistency with project convention |
| License body says "MIT" | Always use `[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)` in README body — must match YAML frontmatter |
| HF collection description too long | Hard limit is 150 characters. Use `update_collection_metadata(slug, description=...)` — pack in domain keywords and source names |

---

## SEO Reference

Learnings from the 2026-03-27 SEO audit across 122 dataset scripts.

### GitHub Repo SEO

- **Topics** (17 set): space, astronomy, dataset, nasa, noaa, esa, parquet, physics, python, etc. Limit is 20. Update via `gh repo edit --add-topic`
- **Description**: keyword-rich, shows in Google search results. Update when dataset count milestones crossed
- **Homepage URL**: set to `https://huggingface.co/juliensimon` — links GitHub to HF profile
- **README H1**: includes tagline with key terms ("Open Space, Astronomy & Physics Datasets on Hugging Face"). Google uses H1 as page title in search results
- **README FAQ section**: targets Google "People also ask" long-tail queries. Each H3 question is a potential featured snippet
- **JSON-LD**: do NOT add to GitHub README — GitHub strips `<script>` tags from rendered markdown, making it invisible to crawlers. HF adds structured data server-side on dataset pages

### HF Dataset Card SEO

**Mandatory umbrella tags** (every script must have all 4):
- `space` — brand umbrella, even for physics-only datasets
- `open-data` — HF search discoverability
- `tabular-data` — format category filter
- `parquet` — format filter (users search HF by this)

**Description field** is the most important frontmatter field for SEO:
- HF uses it as the search snippet subtitle
- Keep 100-200 characters, mention source + scope + key metric
- Use f-string templates with dynamic values: `f"{n_total:,} rows"`, `f"{date_min} to {date_max}"`

**What does NOT help on HF:**
- `dataset_summary` field — not part of current HF spec, `description` serves the same role
- Adding more than ~15 tags — diminishing returns, focus on the right tags
- `task_categories` beyond 2 — stick to the relevant 1-2 (tabular-classification, tabular-regression, time-series-forecasting)

### Cross-Linking Strategy

Each dataset page should link to:
1. Parent HF collection (via "Part of the..." line)
2. GitHub repo (via "Source code" line)
3. Original data source (via "Data source" section)
4. 3-4 sibling datasets (via "Related datasets" section)

This creates a dense link graph: GitHub ↔ HF profile ↔ HF collections ↔ individual datasets ↔ each other. Every link strengthens the SEO of all connected pages.

### HF Collection Descriptions

HF collection descriptions have a **150 character hard limit**. Pack in domain keywords and source names — these appear in search results. Current descriptions:

| Collection | Description |
|---|---|
| Orbital Mechanics | Satellites, TLEs, launches, NEOs, and asteroids. Track every orbiting object from NORAD SATCAT to Starlink fleet health and JPL impact risk. |
| Space Probes | Voyager, Pioneer, Cassini, Mars Express, Rosetta, Curiosity, Perseverance, InSight. 50+ years of interplanetary spacecraft data in Parquet. |
| Planetary Science | Impact craters (Moon, Mars, Ceres), IAU planetary nomenclature, and meteorite landings. The most comprehensive surface geology datasets. |
| Space Weather | Solar flares, CMEs, geomagnetic storms, Kp/Ap/Dst/AE indices, F10.7, sunspot numbers, solar wind, and NOAA alerts. Updated daily. |
| Astronomy | Exoplanets, gravitational waves, pulsars, GRBs, FRBs, quasars, variable stars, and million-source radio/X-ray sky surveys in Parquet. |
| Physics | PDG particle properties, cosmic ray spectra, ultra-high-energy events, and gamma-ray catalogs from Fermi, Swift, INTEGRAL, HAWC, and LHAASO. |
| Solar System | Planetary missions, crater databases (Moon/Mars/Ceres), atmospheric profiles (Jupiter/Titan), marsquakes, and Mars surface exploration. |

Update these when adding datasets that significantly expand a collection's scope. Use `update_collection_metadata(slug, description=...)` from `huggingface_hub`.
