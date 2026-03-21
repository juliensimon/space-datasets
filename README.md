# space-datasets

Automated pipelines that keep space-related datasets on Hugging Face up to date.

![Update SATCAT](https://github.com/juliensimon/space-datasets/actions/workflows/update-satcat.yml/badge.svg)
![Update Launch Log](https://github.com/juliensimon/space-datasets/actions/workflows/update-launch-log.yml/badge.svg)
![Update Starlink Fleet](https://github.com/juliensimon/space-datasets/actions/workflows/update-starlink.yml/badge.svg)

## Datasets

| Dataset | Status | Schedule | Source | Records |
|---------|--------|----------|--------|---------|
| [space-track-tle-history](https://huggingface.co/datasets/juliensimon/space-track-tle-history) | Manual | Yearly | Space-Track.org | 232M TLEs (1959–2025) |
| [space-track-satcat](https://huggingface.co/datasets/juliensimon/space-track-satcat) | ![SATCAT](https://github.com/juliensimon/space-datasets/actions/workflows/update-satcat.yml/badge.svg) | Daily 06:00 UTC | CelesTrak | 68k objects |
| [space-launch-log](https://huggingface.co/datasets/juliensimon/space-launch-log) | ![Launches](https://github.com/juliensimon/space-datasets/actions/workflows/update-launch-log.yml/badge.svg) | Weekly Mon 07:00 UTC | GCAT | 75k launches + 708 sites |
| [starlink-fleet-data](https://huggingface.co/datasets/juliensimon/starlink-fleet-data) | ![Starlink](https://github.com/juliensimon/space-datasets/actions/workflows/update-starlink.yml/badge.svg) | Daily 08:00 UTC | CelesTrak | 21.4M TLEs, 10k satellites |

## How it works

Each dataset has a Python script in `scripts/` and a GitHub Actions workflow in `.github/workflows/`. The scripts fetch data from public sources, convert to Parquet, and upload to Hugging Face.

No database, no state — each run rebuilds from source.

## Setup

The only secret needed is `HF_TOKEN` — a Hugging Face write token, set in the repo's GitHub Actions secrets.

## Manual run

```bash
pip install pandas pyarrow requests huggingface_hub[hf_xet]

# Update SATCAT
python scripts/update-satcat.py

# Update launch log
python scripts/update-launch-log.py

# Update Starlink latest satellites
python scripts/update-starlink.py
```

## Bulk ingestion scripts

These scripts are for one-time or yearly data loads, not automated pipelines:

| Script | Purpose |
|--------|---------|
| `build-tle-archive.py` | Build TLE history from Space-Track yearly bulk zip exports (232M records) |
| `ingest-bulk-zip.ts` | Ingest Starlink TLEs from bulk zips into SQLite fleet database |
| `backfill-spacetrack.ts` | Backfill Starlink TLEs via Space-Track GP_History API |
| `export-dataset.py` | Export SQLite fleet database to Parquet for HF upload |
| `check-data-quality.ts` | Validate fleet database before upload |
