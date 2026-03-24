# space-datasets

Automated pipelines that keep space-related datasets on Hugging Face up to date.

![Update SATCAT](https://github.com/juliensimon/space-datasets/actions/workflows/update-satcat.yml/badge.svg)
![Update Launch Log](https://github.com/juliensimon/space-datasets/actions/workflows/update-launch-log.yml/badge.svg)
![Update Starlink Fleet](https://github.com/juliensimon/space-datasets/actions/workflows/update-starlink.yml/badge.svg)
![Update Ground Stations](https://github.com/juliensimon/space-datasets/actions/workflows/update-ground-stations.yml/badge.svg)
![Update NEO Close Approaches](https://github.com/juliensimon/space-datasets/actions/workflows/update-neo.yml/badge.svg)
![Update Space Weather](https://github.com/juliensimon/space-datasets/actions/workflows/update-space-weather.yml/badge.svg)
![Update Solar Flares](https://github.com/juliensimon/space-datasets/actions/workflows/update-solar-flares.yml/badge.svg)
![Update Dst Index](https://github.com/juliensimon/space-datasets/actions/workflows/update-dst-index.yml/badge.svg)
![Update DONKI Events](https://github.com/juliensimon/space-datasets/actions/workflows/update-donki.yml/badge.svg)
![Update Constellation Census](https://github.com/juliensimon/space-datasets/actions/workflows/update-constellation-census.yml/badge.svg)

## Datasets

| Dataset | Last Updated | Schedule | Update | Source | Records |
|---------|-------------|----------|--------|--------|---------|
| [space-track-tle-history](https://huggingface.co/datasets/juliensimon/space-track-tle-history) | ![TLE](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.tle-history&label=updated&color=blue) | Yearly (manual) | Full | Space-Track.org | ~232M TLEs (1959-present) |
| [space-track-satcat](https://huggingface.co/datasets/juliensimon/space-track-satcat) | ![SATCAT](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.satcat&label=updated&color=brightgreen) | Daily 06:00 UTC | Full | CelesTrak | Full NORAD catalog |
| [space-launch-log](https://huggingface.co/datasets/juliensimon/space-launch-log) | ![Launches](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['launch-log']&label=updated&color=brightgreen) | Weekly Mon 07:00 UTC | Full | GCAT | All launches + sites |
| [starlink-fleet-data](https://huggingface.co/datasets/juliensimon/starlink-fleet-data) | ![Starlink](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.starlink&label=updated&color=brightgreen) | Daily 08:00 UTC | Incremental | CelesTrak | Daily constellation snapshots |
| [constellation-census](https://huggingface.co/datasets/juliensimon/constellation-census) | ![Census](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['constellation-census']&label=updated&color=brightgreen) | Daily 09:00 UTC | Incremental | CelesTrak | ~20 constellations, ~11K sats |
| [starlink-ground-stations](https://huggingface.co/datasets/juliensimon/starlink-ground-stations) | ![Ground Stations](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['ground-stations']&label=updated&color=brightgreen) | Daily 09:00 UTC | Full | Starlink Insider + FCC IBFS | Gateways + PoPs |
| [neo-close-approaches](https://huggingface.co/datasets/juliensimon/neo-close-approaches) | ![NEO](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.neo&label=updated&color=brightgreen) | Daily 10:00 UTC | Full | NASA JPL CNEOS | ~35K close approaches |
| [space-weather-indices](https://huggingface.co/datasets/juliensimon/space-weather-indices) | ![Space Weather](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['space-weather']&label=updated&color=brightgreen) | Daily 11:00 UTC | Full | CelesTrak / NOAA SWPC | Daily indices since 1957 |
| [solar-flare-events](https://huggingface.co/datasets/juliensimon/solar-flare-events) | ![Solar Flares](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['solar-flares']&label=updated&color=brightgreen) | Daily 12:00 UTC | Incremental | NCEI GOES-16 + SWPC | ~16K flare events (2017+) |
| [dst-index](https://huggingface.co/datasets/juliensimon/dst-index) | ![Dst](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['dst-index']&label=updated&color=brightgreen) | Daily 13:00 UTC | Incremental | WDC Kyoto | ~600K hourly readings (1957+) |
| [donki-space-weather-events](https://huggingface.co/datasets/juliensimon/donki-space-weather-events) | ![DONKI](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.donki&label=updated&color=brightgreen) | Daily 14:00 UTC | Incremental | NASA CCMC DONKI | CMEs, storms, shocks (2010+) |

## How it works

Each dataset has a Python script in `scripts/` and a GitHub Actions workflow in `.github/workflows/`. The scripts fetch data from public sources, convert to Parquet, and upload to Hugging Face.

Pipelines use two update strategies:

- **Full rebuild** — re-fetches the entire dataset from source. Used when the source is a single file with no delta endpoint (SATCAT, Space Weather) or the dataset is small enough that incremental updates aren't worth the complexity.
- **Incremental** — downloads the existing Parquet from HF, fetches only new/recent data, merges and deduplicates, then uploads. Falls back to full rebuild automatically when no existing data is found. Used by Starlink, Constellation Census, DONKI (14-day window), Dst Index (current month only), and Solar Flares (SWPC daily append).

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

# Update constellation census
python scripts/update-constellation-census.py

# Update ground stations & PoPs
python scripts/update-ground-stations.py

# Update NEO close approaches
python scripts/update-neo.py

# Update space weather indices
python scripts/update-space-weather.py

# Update solar flare events (requires netCDF4)
pip install netCDF4
python scripts/update-solar-flares.py

# Update Dst geomagnetic index
python scripts/update-dst-index.py

# Update DONKI space weather events
python scripts/update-donki.py
```

## Bulk ingestion

`build-tle-archive.py` builds the TLE history dataset from Space-Track yearly bulk zip exports (232M records). Run manually when new yearly exports are available.

Starlink fleet ingestion scripts (`ingest-bulk-zip.ts`, `backfill-spacetrack.ts`, `export-dataset.py`) live in the [starlink-viz](https://github.com/juliensimon/starlink-viz) repo as they depend on its classification library.

## Citation

If you use these datasets, please cite:

```bibtex
@dataset{space_datasets,
  author = {Simon, Julien},
  title = {Space Datasets: Automated Space Data Pipelines for Hugging Face},
  year = {2026},
  publisher = {Hugging Face},
  url = {https://github.com/juliensimon/space-datasets}
}
```

### Data sources

These datasets are built from the following public sources — please cite them as appropriate:

| Dataset | Original source |
|---------|----------------|
| SATCAT, Starlink Fleet, Constellation Census, Space Weather | [CelesTrak](https://celestrak.org/) (Dr. T.S. Kelso), NORAD/18th Space Defense Squadron |
| TLE History | [Space-Track.org](https://www.space-track.org/), 18th Space Defense Squadron |
| Launch Log | [GCAT](https://planet4589.org/space/gcat/) (Jonathan McDowell, Harvard-Smithsonian CfA) |
| Ground Stations | [Starlink Insider](https://starlinkinsider.com/), [FCC IBFS](https://www.fcc.gov/international-bureau-filing-system) |
| NEO Close Approaches | [NASA/JPL CNEOS](https://cneos.jpl.nasa.gov/), SBDB Close-Approach API |
| Solar Flares | [NOAA NCEI](https://www.ncei.noaa.gov/) GOES-16 XRS, [SWPC](https://www.swpc.noaa.gov/) |
| Dst Index | [WDC for Geomagnetism, Kyoto](https://wdc.kugi.kyoto-u.ac.jp/dstdir/) |
| DONKI Events | [NASA CCMC DONKI](https://ccmc.gsfc.nasa.gov/tools/DONKI/) |

## License

Pipeline code: [MIT](LICENSE). Datasets: [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/).
