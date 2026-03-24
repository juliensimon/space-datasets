# space-datasets

Automated pipelines that keep space-related datasets on Hugging Face up to date.

![Update SATCAT](https://github.com/juliensimon/space-datasets/actions/workflows/update-satcat.yml/badge.svg)
![Update Launch Log](https://github.com/juliensimon/space-datasets/actions/workflows/update-launch-log.yml/badge.svg)
![Update Starlink Fleet](https://github.com/juliensimon/space-datasets/actions/workflows/update-starlink.yml/badge.svg)
![Update Ground Stations](https://github.com/juliensimon/space-datasets/actions/workflows/update-ground-stations.yml/badge.svg)
![Update Constellation Census](https://github.com/juliensimon/space-datasets/actions/workflows/update-constellation-census.yml/badge.svg)
![Update NEO Close Approaches](https://github.com/juliensimon/space-datasets/actions/workflows/update-neo.yml/badge.svg)
![Update Space Weather](https://github.com/juliensimon/space-datasets/actions/workflows/update-space-weather.yml/badge.svg)
![Update Solar Flares](https://github.com/juliensimon/space-datasets/actions/workflows/update-solar-flares.yml/badge.svg)
![Update Dst Index](https://github.com/juliensimon/space-datasets/actions/workflows/update-dst-index.yml/badge.svg)
![Update DONKI Events](https://github.com/juliensimon/space-datasets/actions/workflows/update-donki.yml/badge.svg)
![Update Solar Wind](https://github.com/juliensimon/space-datasets/actions/workflows/update-solar-wind.yml/badge.svg)
![Update Kp Index](https://github.com/juliensimon/space-datasets/actions/workflows/update-kp-index.yml/badge.svg)
![Update Exoplanets](https://github.com/juliensimon/space-datasets/actions/workflows/update-exoplanets.yml/badge.svg)
![Update Gamma-Ray Bursts](https://github.com/juliensimon/space-datasets/actions/workflows/update-grb.yml/badge.svg)
![Update Gravitational Waves](https://github.com/juliensimon/space-datasets/actions/workflows/update-gravitational-waves.yml/badge.svg)
![Update Pulsars](https://github.com/juliensimon/space-datasets/actions/workflows/update-pulsars.yml/badge.svg)
![Update NGC IC](https://github.com/juliensimon/space-datasets/actions/workflows/update-ngc-ic.yml/badge.svg)
![Update SNR](https://github.com/juliensimon/space-datasets/actions/workflows/update-snr.yml/badge.svg)
![Update Galaxy Clusters](https://github.com/juliensimon/space-datasets/actions/workflows/update-galaxy-clusters.yml/badge.svg)
![Update Messier](https://github.com/juliensimon/space-datasets/actions/workflows/update-messier.yml/badge.svg)
![Update Black Holes](https://github.com/juliensimon/space-datasets/actions/workflows/update-black-holes.yml/badge.svg)
![Update Quasars](https://github.com/juliensimon/space-datasets/actions/workflows/update-quasars.yml/badge.svg)

## Datasets

### Orbital Mechanics

| Dataset | Last Updated | Schedule | Update | Size | Source | Records |
|---------|-------------|----------|--------|------|--------|---------|
| [space-track-tle-history](https://huggingface.co/datasets/juliensimon/space-track-tle-history) | ![TLE](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.tle-history&label=updated&color=blue) | Yearly (manual) | Full | 10.9 GB | Space-Track.org | ~232M TLEs (1959-present) |
| [space-track-satcat](https://huggingface.co/datasets/juliensimon/space-track-satcat) | ![SATCAT](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.satcat&label=updated&color=brightgreen) | Daily 06:00 UTC | Full | 1.6 MB | CelesTrak | Full NORAD catalog |
| [space-launch-log](https://huggingface.co/datasets/juliensimon/space-launch-log) | ![Launches](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['launch-log']&label=updated&color=brightgreen) | Weekly Mon 07:00 UTC | Full | 2.4 MB | GCAT | All launches + sites |
| [starlink-fleet-data](https://huggingface.co/datasets/juliensimon/starlink-fleet-data) | ![Starlink](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.starlink&label=updated&color=brightgreen) | Daily 08:00 UTC | Incremental | 618 MB | CelesTrak | Daily constellation snapshots |
| [constellation-census](https://huggingface.co/datasets/juliensimon/constellation-census) | ![Census](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['constellation-census']&label=updated&color=brightgreen) | Daily 09:00 UTC | Incremental | 0.4 MB | CelesTrak | ~20 constellations, ~11K sats |
| [starlink-ground-stations](https://huggingface.co/datasets/juliensimon/starlink-ground-stations) | ![Ground Stations](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['ground-stations']&label=updated&color=brightgreen) | Daily 09:00 UTC | Full | 7 KB | Starlink Insider + FCC IBFS | Gateways + PoPs |
| [neo-close-approaches](https://huggingface.co/datasets/juliensimon/neo-close-approaches) | ![NEO](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.neo&label=updated&color=brightgreen) | Daily 10:00 UTC | Full | 3.2 MB | NASA JPL CNEOS | ~35K close approaches |

### Space Weather

| Dataset | Last Updated | Schedule | Update | Size | Source | Records |
|---------|-------------|----------|--------|------|--------|---------|
| [space-weather-indices](https://huggingface.co/datasets/juliensimon/space-weather-indices) | ![Space Weather](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['space-weather']&label=updated&color=brightgreen) | Daily 11:00 UTC | Full | 0.8 MB | CelesTrak / NOAA SWPC | Daily indices since 1957 |
| [solar-flare-events](https://huggingface.co/datasets/juliensimon/solar-flare-events) | ![Solar Flares](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['solar-flares']&label=updated&color=brightgreen) | Daily 12:00 UTC | Incremental | 0.5 MB | NCEI GOES-16 + SWPC | ~16K flare events (2017+) |
| [dst-index](https://huggingface.co/datasets/juliensimon/dst-index) | ![Dst](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['dst-index']&label=updated&color=brightgreen) | Daily 13:00 UTC | Incremental | 1.7 MB | WDC Kyoto | ~600K hourly readings (1957+) |
| [donki-space-weather-events](https://huggingface.co/datasets/juliensimon/donki-space-weather-events) | ![DONKI](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.donki&label=updated&color=brightgreen) | Daily 14:00 UTC | Incremental | 1.0 MB | NASA CCMC DONKI | CMEs, storms, shocks (2010+) |
| [solar-wind](https://huggingface.co/datasets/juliensimon/solar-wind) | ![Solar Wind](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['solar-wind']&label=updated&color=brightgreen) | Daily 15:00 UTC | Incremental | 0.2 MB | NOAA SWPC (DSCOVR/ACE) | Real-time L1 plasma + mag |
| [geomagnetic-kp-index](https://huggingface.co/datasets/juliensimon/geomagnetic-kp-index) | ![Kp](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['kp-index']&label=updated&color=brightgreen) | Daily 15:30 UTC | Incremental | 4 KB | NOAA SWPC / GFZ Potsdam | 3-hourly Kp index |

### Astronomy

| Dataset | Last Updated | Schedule | Update | Size | Source | Records |
|---------|-------------|----------|--------|------|--------|---------|
| [nasa-exoplanets](https://huggingface.co/datasets/juliensimon/nasa-exoplanets) | ![Exoplanets](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.exoplanets&label=updated&color=brightgreen) | Weekly Mon 16:00 UTC | Full | 0.5 MB | NASA Exoplanet Archive | ~6K confirmed planets |
| [gamma-ray-bursts](https://huggingface.co/datasets/juliensimon/gamma-ray-bursts) | ![GRB](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.grb&label=updated&color=brightgreen) | Weekly Mon 17:00 UTC | Full | 0.3 MB | NASA HEASARC Fermi GBM | ~4K GRBs (2008+) |
| [gravitational-wave-events](https://huggingface.co/datasets/juliensimon/gravitational-wave-events) | ![GW](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['gravitational-waves']&label=updated&color=brightgreen) | Weekly Mon 17:30 UTC | Full | 30 KB | GWOSC (LIGO/Virgo/KAGRA) | ~260 events (O1-O4) |
| [pulsar-catalog](https://huggingface.co/datasets/juliensimon/pulsar-catalog) | ![Pulsars](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.pulsars&label=updated&color=brightgreen) | Monthly 1st Mon 18:00 UTC | Full | 0.2 MB | ATNF / HEASARC | ~3K pulsars |
| [ngc-ic-catalog](https://huggingface.co/datasets/juliensimon/ngc-ic-catalog) | ![NGC](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['ngc-ic']&label=updated&color=brightgreen) | Monthly 1st Mon 18:30 UTC | Full | 0.5 MB | OpenNGC | ~14K deep-sky objects |
| [supernova-remnants](https://huggingface.co/datasets/juliensimon/supernova-remnants) | ![SNR](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.snr&label=updated&color=brightgreen) | Quarterly | Full | 10 KB | Green's Catalog / HEASARC | ~310 Galactic SNRs |
| [galaxy-clusters](https://huggingface.co/datasets/juliensimon/galaxy-clusters) | ![Clusters](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['galaxy-clusters']&label=updated&color=brightgreen) | Quarterly | Full | 50 KB | Planck PSZ2 / HEASARC | ~1.6K SZ-detected clusters |
| [messier-catalog](https://huggingface.co/datasets/juliensimon/messier-catalog) | ![Messier](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.messier&label=updated&color=brightgreen) | Quarterly | Full | 10 KB | SIMBAD | 110 iconic deep-sky objects |
| [black-hole-catalog](https://huggingface.co/datasets/juliensimon/black-hole-catalog) | ![BH](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['black-holes']&label=updated&color=brightgreen) | Weekly Mon 18:30 UTC | Full | 90 KB | SIMBAD | BH systems + X-ray binaries |
| [quasar-catalog](https://huggingface.co/datasets/juliensimon/quasar-catalog) | ![QSO](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.quasars&label=updated&color=brightgreen) | Weekly Mon 19:00 UTC | Full | 1.3 MB | SIMBAD | ~50K quasars + AGN |

## How it works

Each dataset has a Python script in `scripts/` and a GitHub Actions workflow in `.github/workflows/`. The scripts fetch data from public sources, convert to Parquet, and upload to Hugging Face.

Pipelines use two update strategies:

- **Full rebuild** — re-fetches the entire dataset from source. Used when the source is a single file with no delta endpoint (SATCAT, Space Weather) or the dataset is small enough that incremental updates aren't worth the complexity.
- **Incremental** — downloads the existing Parquet from HF, fetches only new/recent data, merges and deduplicates, then uploads. Falls back to full rebuild automatically when no existing data is found. Used by Starlink, Constellation Census, DONKI (14-day window), Dst Index (current month only), Solar Flares (SWPC daily append), Solar Wind (7-day rolling window), and Kp Index.

## Setup

The only secret needed is `HF_TOKEN` — a Hugging Face write token, set in the repo's GitHub Actions secrets.

## Manual run

```bash
pip install pandas pyarrow requests huggingface_hub[hf_xet]

# Orbital Mechanics
python scripts/update-satcat.py
python scripts/update-launch-log.py
python scripts/update-starlink.py
python scripts/update-constellation-census.py
python scripts/update-ground-stations.py
python scripts/update-neo.py

# Space Weather
python scripts/update-space-weather.py
pip install netCDF4 && python scripts/update-solar-flares.py
python scripts/update-dst-index.py
python scripts/update-donki.py
python scripts/update-solar-wind.py
python scripts/update-kp-index.py

# Astronomy
python scripts/update-exoplanets.py
python scripts/update-grb.py
python scripts/update-gravitational-waves.py
python scripts/update-pulsars.py
python scripts/update-ngc-ic.py
python scripts/update-snr.py
python scripts/update-galaxy-clusters.py
python scripts/update-messier.py
python scripts/update-black-holes.py
python scripts/update-quasars.py
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

| Domain | Original source |
|--------|----------------|
| Orbital Mechanics | [CelesTrak](https://celestrak.org/) (Dr. T.S. Kelso), [Space-Track.org](https://www.space-track.org/), [GCAT](https://planet4589.org/space/gcat/) (Jonathan McDowell), [Starlink Insider](https://starlinkinsider.com/), [NASA/JPL CNEOS](https://cneos.jpl.nasa.gov/) |
| Space Weather | [NOAA SWPC](https://www.swpc.noaa.gov/), [WDC Kyoto](https://wdc.kugi.kyoto-u.ac.jp/dstdir/), [NASA CCMC DONKI](https://ccmc.gsfc.nasa.gov/tools/DONKI/), [NOAA NCEI](https://www.ncei.noaa.gov/) GOES-16 XRS |
| Astronomy | [NASA Exoplanet Archive](https://exoplanetarchive.ipac.caltech.edu/), [NASA HEASARC](https://heasarc.gsfc.nasa.gov/) Fermi GBM, [GWOSC](https://gwosc.org/) (LIGO/Virgo/KAGRA), [ATNF](https://www.atnf.csiro.au/research/pulsar/psrcat/) Pulsar Catalogue, [OpenNGC](https://github.com/mattiaverga/OpenNGC), [Green's SNR Catalog](https://www.mrao.cam.ac.uk/surveys/snrs/), [SIMBAD](https://simbad.u-strasbg.fr/) (CDS Strasbourg) |

## License

Pipeline code: [MIT](LICENSE). Datasets: [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/).
