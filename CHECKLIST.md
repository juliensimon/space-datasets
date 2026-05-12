# Dataset Addition Checklist

Reusable checklist for adding any new dataset to `juliensimon/space-datasets`. Learned from building 207 datasets. For architecture, workflow template, and source gotchas, see `CLAUDE.md`.

---

## 1. Pipeline Script (`scripts/update-<name>.py`)

- [ ] Fetch with `timeout=` + error handling; retry with backoff for flaky APIs
- [ ] Type coercion: dates → `pd.to_datetime`, IDs → `int32`, numerics → `pd.to_numeric(errors="coerce")`
- [ ] Column rename to snake_case
- [ ] Guard optional columns: `if "col" in df.columns`
- [ ] Derive computed fields (classifications, categories, flags)
- [ ] `check_dataset(df, name, min_rows=N, expected_columns=[...], critical_columns=[...], warn_all_nulls=0.90)`
- [ ] Write parquet: `df.to_parquet(path, index=False, engine="pyarrow", compression="zstd")`
- [ ] Upload: `["hf", "upload", HF_REPO, str(tmp_dir), ".", "--repo-type", "dataset", "--commit-message", msg]`
- [ ] Emit row count to `$GITHUB_OUTPUT`

**If incremental** — also:
- [ ] Download existing parquet via `hf download`, merge with `pd.concat` + `drop_duplicates(keep="last")`
- [ ] Fall back to full rebuild when existing data can't be loaded
- [ ] Verify idempotency: same-day re-run must not create duplicates

**If TAP/ADQL** (HEASARC, SIMBAD, VizieR, Gaia, EPN-TAP) — also:
- [ ] Auto-drop >95% null columns after fetch (wide schemas carry empty optional fields)
- [ ] Drop columns that became all-null after numeric coercion (flag/limit columns with `>`, `<`)
- [ ] HEASARC: `FORMAT=text` (pipe-delimited) — CSV returns VOTable XML; add `startswith("<?xml")` guard
- [ ] HEASARC: column sanity check after parse (e.g., `"ra" in df.columns`), not just row count
- [ ] SIMBAD: `basic` table only, `OR` chains not `IN (...)`, no `regexp()`
- [ ] VizieR/Gaia: `FORMAT=csv`; always `SELECT *` then check actual headers

---

## 2. HF README — YAML Frontmatter

- [ ] `license: cc-by-4.0` (or `cc-by-sa-4.0` if upstream requires)
- [ ] `pretty_name:` — human-readable title (not repo slug)
- [ ] `language: [en]`
- [ ] `description:` — 100-200 chars, Google-indexed. Template: `"{What} from {Source} ({scope}). {Key detail}."`
- [ ] `size_categories:` — `n<1K` / `1K<n<10K` / `10K<n<100K` / `100K<n<1M`
- [ ] `task_categories:` — 1-2 of: `tabular-classification`, `tabular-regression`, `time-series-forecasting`
- [ ] `tags:` — 4 mandatory (`space`, `open-data`, `tabular-data`, `parquet`) + domain + source names
- [ ] `configs:` with explicit `split: train`, `path:`, and `default: true`

---

## 3. HF README — Body Content

- [ ] **H1** matching `pretty_name` (strongest SEO signal)
- [ ] **Collection backlink**: `*Part of the [Domain Datasets](...) collection on Hugging Face.*`
- [ ] **Banner image** via `download_banner()` / `banner_markdown()` — add key to `DATASET_DOMAIN` in `dataset_images.py`
- [ ] **Badges**: CI + dynamic "updated" badge
- [ ] **Intro paragraph**: 2-3 sentences, **bold** key stats, front-load important terms (becomes Google snippet)
- [ ] **Schema table**: Column | Type | Description (3 columns always)
- [ ] **Quick stats** computed from data
- [ ] **Usage section**: `load_dataset()` + 3-5 realistic examples
- [ ] **Data source** with attribution URL
- [ ] **Update frequency** (daily/weekly/monthly at HH:MM UTC)
- [ ] **Related datasets**: cross-link 3-4 siblings (verify slugs match `HF_REPO` values)
- [ ] **Pipeline source link**: `Source code: [juliensimon/space-datasets](...)`
- [ ] **Support section** with ❤️ prompt
- [ ] **Citation BibTeX** with correct HF URL
- [ ] **License**: `[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)` (link, not plain text)

---

## 4. GitHub Actions Workflow

See `CLAUDE.md` for full template. Key points:
- [ ] Cron staggered within 06:00–19:30 UTC (check existing workflows)
- [ ] `workflow_dispatch:` enabled
- [ ] `permissions: contents: write` + `environment: HF`
- [ ] Python 3.12, deps: `pandas pyarrow requests huggingface_hub[hf_xet]`
- [ ] Capture `steps.update.outputs.rows` via `id: update`
- [ ] Status.json update with 3-attempt retry loop

---

## 5. Validation

- [ ] `min_rows` threshold based on expected dataset size
- [ ] `expected_columns` lists all required columns
- [ ] `critical_columns` lists columns that must be <5% null
- [ ] For TAP `SELECT *`: auto-drop >95% null columns before validation
- [ ] Spot-check known values (e.g., GW150914, Kepler-452b, ISS)
- [ ] Run `python scripts/audit-nulls.py --dataset <name>` — no columns >80% null without justification

---

## 6. Repository Updates

- [ ] `status.json`: add entry, verify valid JSON
- [ ] `README.md`: badge row + domain table row + manual run command + update dataset count
- [ ] `scripts/add-to-collections.py`: add to parent + sub-collection (see table below), then run it
- [ ] `CANDIDATES.md`: move from remaining → built, update counts
- [ ] Update repo description if milestone crossed: `gh repo edit --description "..."`

### Collection Slugs

| Parent | Slug |
|--------|------|
| Orbital | `juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994` |
| Planetary | `juliensimon/planetary-science-datasets-69c2d4683bd6a66c34fb4af2` |
| Weather | `juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70` |
| Astronomy | `juliensimon/astronomy-datasets-69c24caf2f17e36128946743` |
| Physics | `juliensimon/physics-datasets-69c2d4682d37dfdb77447bd7` |
| Solar System | `juliensimon/solar-system-datasets-69c6fa681978de62dff2f347` |

| Sub-collection | Slug |
|----------------|------|
| Stellar Catalogs | `juliensimon/stellar-catalogs-69c792b1a52ab2757b0eaa57` |
| Variable Stars & Transients | `juliensimon/variable-stars-and-transients-69c792b1dd7a45812c5a9b36` |
| Galaxies & Cosmology | `juliensimon/galaxies-and-cosmology-69c792b117242a3b236df55d` |
| Sky Surveys | `juliensimon/sky-surveys-69c792b17d77aba7996e2442` |
| Satellites & Launches | `juliensimon/satellites-and-launches-69c792b1fca01f437233082d` |
| Asteroids & Small Bodies | `juliensimon/asteroids-and-small-bodies-69c792b1e0240f3bf1235c66` |

---

## 7. Post-Launch Verification

**Every script must be run locally before considering it done.**

- [ ] Syntax check: `python3 -c "import py_compile; py_compile.compile('scripts/update-<name>.py', doraise=True)"`
- [ ] Workflow YAML valid: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/update-<name>.yml'))"`
- [ ] **Run locally with HF_TOKEN** — verify row count, parquet written, upload succeeds
- [ ] HF viewer works: `curl -s "https://datasets-server.huggingface.co/is-valid?dataset=juliensimon/<name>"` → `viewer: true`
- [ ] Dataset appears in correct HF collection
- [ ] README renders correctly on HF page
- [ ] For refreshing datasets: trigger `workflow_dispatch`, confirm success, verify idempotent re-run
- [ ] Badges show green

---

## Common Pitfalls

### Data Sources

| Source | Pitfall | Fix |
|--------|---------|-----|
| HEASARC | CSV returns VOTable XML silently | `FORMAT=text`; guard with `startswith("<?xml")` |
| HEASARC | TAP sync truncates large tables (~28K) | Add `MAXREC=500000`; for 100K+ consider async TAP or VizieR mirror |
| SIMBAD | JOINs with `allfluxes`/`mesDistance` fail | Use `basic` table only |
| VizieR | Column names differ from docs | `SELECT *`, check actual CSV with `curl`, add name variants to rename dict |
| VizieR | `[Fe/H]` brackets get sanitized | Check actual CSV output, don't assume bracket notation |
| CelesTrak | Frequent 500 errors | 1s delay + 3 retries with 2/4/6s backoff |
| Wikidata | Mostly-empty stub entities | Drop >95% null columns; guard README stats with `if "col" in df.columns` |
| NASA SODA | Endpoints go 404 without notice | Test endpoint before committing |

### Transform & Validation

| Pitfall | Fix |
|---------|-----|
| Boolean column destroyed by string cleaning | Create derived booleans AFTER `df.select_dtypes(include=["object"])` loop |
| Over-broad numeric column matching | Use `startswith()` prefix, not `in` substring — `"ra" in "separation"` matches |
| Day-of-year datetime (YYYY-DDDTHH:MM:SS) | `pd.to_datetime(col, format="%Y-%jT%H:%M:%S")` — dateutil fallback returns NaT |
| PDS/GCAT trailing spaces in column names | `df.columns = df.columns.str.strip()` |
| README f-string crash on NaN stats | Guard `idxmax()` results with `is not None` |
| Schema table lists dropped columns | Generate schema dynamically or list only core columns that always survive |

### HF Configuration

| Pitfall | Fix |
|---------|-----|
| Multi-config missing `default: true` | `load_dataset()` fails without it — always set on primary config |
| Related dataset links use wrong slug | URLs must match actual `HF_REPO` values |
| License body says "MIT" | Always `[CC-BY-4.0](...)` — must match YAML frontmatter |
| Badge shows "no status" | Trigger `workflow_dispatch` after first push |
| `import` inside function body | Keep all imports at file top level (project convention) |
| Collection description too long | Hard limit 150 chars — pack in domain keywords |

---

## HF Collection Descriptions (150 char limit)

| Collection | Description |
|---|---|
| Orbital | Satellites, TLEs, launches, NEOs, and asteroids. Track every orbiting object from NORAD SATCAT to Starlink fleet health and JPL impact risk. |
| Space Probes | Voyager, Pioneer, Cassini, Mars Express, Rosetta, Curiosity, Perseverance, InSight. 50+ years of interplanetary spacecraft data in Parquet. |
| Planetary | Impact craters (Moon, Mars, Ceres), IAU planetary nomenclature, and meteorite landings. The most comprehensive surface geology datasets. |
| Weather | Solar flares, CMEs, geomagnetic storms, Kp/Ap/Dst/AE indices, F10.7, sunspot numbers, solar wind, and NOAA alerts. Updated daily. |
| Astronomy | Exoplanets, gravitational waves, pulsars, GRBs, FRBs, quasars, variable stars, and million-source radio/X-ray sky surveys in Parquet. |
| Physics | PDG particle properties, cosmic ray spectra, ultra-high-energy events, and gamma-ray catalogs from Fermi, Swift, INTEGRAL, HAWC, and LHAASO. |
| Solar System | Planetary missions, crater databases (Moon/Mars/Ceres), atmospheric profiles (Jupiter/Titan), marsquakes, and Mars surface exploration. |
