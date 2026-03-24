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

| Dataset | Description | Last Updated | Schedule | Size |
|---------|-------------|-------------|----------|------|
| [space-track-tle-history](https://huggingface.co/datasets/juliensimon/space-track-tle-history) | 232 million orbital element sets for every cataloged object since 1959 | ![TLE](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.tle-history&label=updated&color=blue) | Yearly (manual) | 10.9 GB |
| [space-track-satcat](https://huggingface.co/datasets/juliensimon/space-track-satcat) | Complete NORAD satellite catalog — 68K satellites, rocket bodies, and debris | ![SATCAT](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.satcat&label=updated&color=brightgreen) | Daily | 1.6 MB |
| [space-launch-log](https://huggingface.co/datasets/juliensimon/space-launch-log) | Every orbital and suborbital launch since 1957 with sites and outcomes | ![Launches](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['launch-log']&label=updated&color=brightgreen) | Weekly | 2.4 MB |
| [starlink-fleet-data](https://huggingface.co/datasets/juliensimon/starlink-fleet-data) | Daily Starlink constellation health — per-shell satellite counts and status | ![Starlink](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.starlink&label=updated&color=brightgreen) | Daily | 618 MB |
| [constellation-census](https://huggingface.co/datasets/juliensimon/constellation-census) | 19 satellite constellations (Starlink, OneWeb, Kuiper, GPS, etc.) — 11K+ satellites | ![Census](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['constellation-census']&label=updated&color=brightgreen) | Daily | 0.4 MB |
| [starlink-ground-stations](https://huggingface.co/datasets/juliensimon/starlink-ground-stations) | Starlink gateway and point-of-presence locations worldwide | ![Ground Stations](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['ground-stations']&label=updated&color=brightgreen) | Daily | 7 KB |
| [neo-close-approaches](https://huggingface.co/datasets/juliensimon/neo-close-approaches) | 35K+ near-Earth asteroid and comet close approaches from NASA JPL | ![NEO](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.neo&label=updated&color=brightgreen) | Daily | 3.2 MB |

### Space Weather

| Dataset | Description | Last Updated | Schedule | Size |
|---------|-------------|-------------|----------|------|
| [space-weather-indices](https://huggingface.co/datasets/juliensimon/space-weather-indices) | Daily Kp, Ap, F10.7 solar and geomagnetic indices since 1957 | ![Space Weather](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['space-weather']&label=updated&color=brightgreen) | Daily | 0.8 MB |
| [solar-flare-events](https://huggingface.co/datasets/juliensimon/solar-flare-events) | 16K+ individual solar flare detections from GOES X-ray sensors (2017+) | ![Solar Flares](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['solar-flares']&label=updated&color=brightgreen) | Daily | 0.5 MB |
| [dst-index](https://huggingface.co/datasets/juliensimon/dst-index) | 600K+ hourly geomagnetic storm intensity readings since 1957 (Dst index) | ![Dst](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['dst-index']&label=updated&color=brightgreen) | Daily | 1.7 MB |
| [donki-space-weather-events](https://huggingface.co/datasets/juliensimon/donki-space-weather-events) | 12K+ coronal mass ejections, geomagnetic storms, and solar particle events (2010+) | ![DONKI](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.donki&label=updated&color=brightgreen) | Daily | 1.0 MB |
| [solar-wind](https://huggingface.co/datasets/juliensimon/solar-wind) | Real-time solar wind speed, density, temperature, and magnetic field from L1 | ![Solar Wind](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['solar-wind']&label=updated&color=brightgreen) | Daily | 0.2 MB |
| [geomagnetic-kp-index](https://huggingface.co/datasets/juliensimon/geomagnetic-kp-index) | 3-hourly geomagnetic disturbance index (Kp 0-9) with NOAA storm scale | ![Kp](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['kp-index']&label=updated&color=brightgreen) | Daily | 4 KB |

### Astronomy

| Dataset | Description | Last Updated | Schedule | Size |
|---------|-------------|-------------|----------|------|
| [nasa-exoplanets](https://huggingface.co/datasets/juliensimon/nasa-exoplanets) | 6,150 confirmed exoplanets with orbital, stellar, and discovery parameters | ![Exoplanets](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.exoplanets&label=updated&color=brightgreen) | Weekly | 0.5 MB |
| [gamma-ray-bursts](https://huggingface.co/datasets/juliensimon/gamma-ray-bursts) | 4,200+ gamma-ray bursts from Fermi GBM with duration, flux, and spectral data | ![GRB](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.grb&label=updated&color=brightgreen) | Weekly | 0.3 MB |
| [gravitational-wave-events](https://huggingface.co/datasets/juliensimon/gravitational-wave-events) | 260+ black hole and neutron star mergers detected by LIGO/Virgo/KAGRA | ![GW](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['gravitational-waves']&label=updated&color=brightgreen) | Weekly | 30 KB |
| [pulsar-catalog](https://huggingface.co/datasets/juliensimon/pulsar-catalog) | 4,300+ pulsars with spin period, dispersion measure, and magnetic field | ![Pulsars](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.pulsars&label=updated&color=brightgreen) | Monthly | 0.2 MB |
| [ngc-ic-catalog](https://huggingface.co/datasets/juliensimon/ngc-ic-catalog) | 14K deep-sky objects — galaxies, nebulae, and star clusters (NGC + IC) | ![NGC](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['ngc-ic']&label=updated&color=brightgreen) | Monthly | 0.5 MB |
| [supernova-remnants](https://huggingface.co/datasets/juliensimon/supernova-remnants) | 310 Galactic supernova remnants with radio flux and spectral index | ![SNR](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.snr&label=updated&color=brightgreen) | Quarterly | 10 KB |
| [galaxy-clusters](https://huggingface.co/datasets/juliensimon/galaxy-clusters) | 1,650+ galaxy clusters detected by Planck via the Sunyaev-Zeldovich effect | ![Clusters](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['galaxy-clusters']&label=updated&color=brightgreen) | Quarterly | 50 KB |
| [messier-catalog](https://huggingface.co/datasets/juliensimon/messier-catalog) | The classic Messier catalog — 110 galaxies, nebulae, and star clusters | ![Messier](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.messier&label=updated&color=brightgreen) | Quarterly | 10 KB |
| [black-hole-catalog](https://huggingface.co/datasets/juliensimon/black-hole-catalog) | Known black hole systems and X-ray binaries from SIMBAD | ![BH](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['black-holes']&label=updated&color=brightgreen) | Weekly | 90 KB |
| [quasar-catalog](https://huggingface.co/datasets/juliensimon/quasar-catalog) | 50K quasars, Seyfert galaxies, blazars, and active galactic nuclei | ![QSO](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.quasars&label=updated&color=brightgreen) | Weekly | 1.3 MB |

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
