# space-datasets

Open-source data pipelines that publish **110+ space, astronomy, and physics datasets** to [Hugging Face](https://huggingface.co/juliensimon) in Parquet format. Covers satellites, orbital mechanics, asteroids, space weather, solar activity, exoplanets, gravitational waves, pulsars, radio surveys, X-ray catalogs, space probes, particle physics, and more — sourced from NASA, NOAA, ESA, and other public APIs. Updated daily via GitHub Actions.

All datasets are loadable in one line (`load_dataset("juliensimon/...")`), require no API keys, and work with `pandas`, `polars`, or any Parquet-compatible tool.

### Top downloads

<!-- TOP_DOWNLOADS_START -->
**2,392** downloads  ·  **3** likes  ·  **114** datasets  ·  updated 2026-03-27

| # | Dataset | Downloads |
|--:|---------|----------:|
| 1 | [space-track-tle-history](https://huggingface.co/datasets/juliensimon/space-track-tle-history) | 135 |
| 2 | [starlink-fleet-data](https://huggingface.co/datasets/juliensimon/starlink-fleet-data) | 120 |
| 3 | [amazon-shoe-reviews](https://huggingface.co/datasets/juliensimon/amazon-shoe-reviews) | 109 |
| 4 | [starlink-ground-stations](https://huggingface.co/datasets/juliensimon/starlink-ground-stations) | 56 |
| 5 | [donki-space-weather-events](https://huggingface.co/datasets/juliensimon/donki-space-weather-events) | 51 |
| 6 | [constellation-census](https://huggingface.co/datasets/juliensimon/constellation-census) | 51 |
| 7 | [autonlp-data-song-lyrics](https://huggingface.co/datasets/juliensimon/autonlp-data-song-lyrics) | 44 |
| 8 | [messier-catalog](https://huggingface.co/datasets/juliensimon/messier-catalog) | 43 |
| 9 | [food102](https://huggingface.co/datasets/juliensimon/food102) | 41 |
| 10 | [space-track-satcat](https://huggingface.co/datasets/juliensimon/space-track-satcat) | 40 |
<!-- TOP_DOWNLOADS_END -->

<!-- Orbital Mechanics -->
![TLE History](https://github.com/juliensimon/space-datasets/actions/workflows/update-tle-history.yml/badge.svg)
![SATCAT](https://github.com/juliensimon/space-datasets/actions/workflows/update-satcat.yml/badge.svg)
![Launch Log](https://github.com/juliensimon/space-datasets/actions/workflows/update-launch-log.yml/badge.svg)
![Starlink](https://github.com/juliensimon/space-datasets/actions/workflows/update-starlink.yml/badge.svg)
![Ground Stations](https://github.com/juliensimon/space-datasets/actions/workflows/update-ground-stations.yml/badge.svg)
![TLE Latest](https://github.com/juliensimon/space-datasets/actions/workflows/update-tle-latest.yml/badge.svg)
![Census](https://github.com/juliensimon/space-datasets/actions/workflows/update-constellation-census.yml/badge.svg)
![NEO](https://github.com/juliensimon/space-datasets/actions/workflows/update-neo.yml/badge.svg)
![SBDB](https://github.com/juliensimon/space-datasets/actions/workflows/update-sbdb.yml/badge.svg)
![Sentry](https://github.com/juliensimon/space-datasets/actions/workflows/update-sentry.yml/badge.svg)
![Fireballs](https://github.com/juliensimon/space-datasets/actions/workflows/update-fireballs.yml/badge.svg)
![NHATS](https://github.com/juliensimon/space-datasets/actions/workflows/update-nhats.yml/badge.svg)
![SatNOGS](https://github.com/juliensimon/space-datasets/actions/workflows/update-satnogs.yml/badge.svg)
![UCS](https://github.com/juliensimon/space-datasets/actions/workflows/update-ucs.yml/badge.svg)
<!-- Space Weather -->
![CelesTrak SW](https://github.com/juliensimon/space-datasets/actions/workflows/update-celestrak-sw.yml/badge.svg)
![Space Weather](https://github.com/juliensimon/space-datasets/actions/workflows/update-space-weather.yml/badge.svg)
![Solar Flares](https://github.com/juliensimon/space-datasets/actions/workflows/update-solar-flares.yml/badge.svg)
![Dst](https://github.com/juliensimon/space-datasets/actions/workflows/update-dst-index.yml/badge.svg)
![DONKI](https://github.com/juliensimon/space-datasets/actions/workflows/update-donki.yml/badge.svg)
![Solar Wind](https://github.com/juliensimon/space-datasets/actions/workflows/update-solar-wind.yml/badge.svg)
![Kp](https://github.com/juliensimon/space-datasets/actions/workflows/update-kp-index.yml/badge.svg)
![Sunspot](https://github.com/juliensimon/space-datasets/actions/workflows/update-sunspot.yml/badge.svg)
![F10.7](https://github.com/juliensimon/space-datasets/actions/workflows/update-f107.yml/badge.svg)
![SWPC Alerts](https://github.com/juliensimon/space-datasets/actions/workflows/update-swpc-alerts.yml/badge.svg)
![Solar Radio](https://github.com/juliensimon/space-datasets/actions/workflows/update-solar-radio.yml/badge.svg)
![IERS EOP](https://github.com/juliensimon/space-datasets/actions/workflows/update-iers-eop.yml/badge.svg)
![AE Index](https://github.com/juliensimon/space-datasets/actions/workflows/update-ae-index.yml/badge.svg)
<!-- Astronomy -->
![Exoplanets](https://github.com/juliensimon/space-datasets/actions/workflows/update-exoplanets.yml/badge.svg)
![GRB](https://github.com/juliensimon/space-datasets/actions/workflows/update-grb.yml/badge.svg)
![GW](https://github.com/juliensimon/space-datasets/actions/workflows/update-gravitational-waves.yml/badge.svg)
![Pulsars](https://github.com/juliensimon/space-datasets/actions/workflows/update-pulsars.yml/badge.svg)
![NGC/IC](https://github.com/juliensimon/space-datasets/actions/workflows/update-ngc-ic.yml/badge.svg)
![SNR](https://github.com/juliensimon/space-datasets/actions/workflows/update-snr.yml/badge.svg)
![Clusters](https://github.com/juliensimon/space-datasets/actions/workflows/update-galaxy-clusters.yml/badge.svg)
![Messier](https://github.com/juliensimon/space-datasets/actions/workflows/update-messier.yml/badge.svg)
![Black Holes](https://github.com/juliensimon/space-datasets/actions/workflows/update-black-holes.yml/badge.svg)
![Quasars](https://github.com/juliensimon/space-datasets/actions/workflows/update-quasars.yml/badge.svg)
![eROSITA](https://github.com/juliensimon/space-datasets/actions/workflows/update-erosita.yml/badge.svg)
![GCVS](https://github.com/juliensimon/space-datasets/actions/workflows/update-gcvs.yml/badge.svg)
![Fermi](https://github.com/juliensimon/space-datasets/actions/workflows/update-fermi-4fgl.yml/badge.svg)
![CHIME/FRB](https://github.com/juliensimon/space-datasets/actions/workflows/update-chime-frb.yml/badge.svg)
![TESS TOI](https://github.com/juliensimon/space-datasets/actions/workflows/update-tess-toi.yml/badge.svg)
![WDS](https://github.com/juliensimon/space-datasets/actions/workflows/update-wds.yml/badge.svg)
<!-- Space Probes -->
![Deep Space Probes](https://github.com/juliensimon/space-datasets/actions/workflows/update-deep-space-probes.yml/badge.svg)
![Mars Express](https://github.com/juliensimon/space-datasets/actions/workflows/update-mars-express.yml/badge.svg)
![MEDA Weather](https://github.com/juliensimon/space-datasets/actions/workflows/update-meda-weather.yml/badge.svg)
<!-- Physics -->
![CRDB](https://github.com/juliensimon/space-datasets/actions/workflows/update-crdb.yml/badge.svg)
![PDG](https://github.com/juliensimon/space-datasets/actions/workflows/update-pdg.yml/badge.svg)
![Fermi GBM](https://github.com/juliensimon/space-datasets/actions/workflows/update-fermi-gbm-triggers.yml/badge.svg)

## Datasets

### Orbital Mechanics

| Dataset | Description | Last Updated | Schedule | Size |
|---------|-------------|-------------|----------|------|
| [space-track-tle-history](https://huggingface.co/datasets/juliensimon/space-track-tle-history) | 238 million orbital element sets for every cataloged object since 1959 | ![TLE](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.tle-history&label=updated&color=brightgreen) | Daily | 10.9 GB |
| [space-track-satcat](https://huggingface.co/datasets/juliensimon/space-track-satcat) | Complete NORAD satellite catalog — 68K satellites, rocket bodies, and debris | ![SATCAT](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.satcat&label=updated&color=brightgreen) | Daily | 1.6 MB |
| [space-launch-log](https://huggingface.co/datasets/juliensimon/space-launch-log) | Every orbital and suborbital launch since 1957 with sites and outcomes | ![Launches](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['launch-log']&label=updated&color=brightgreen) | Weekly | 2.4 MB |
| [starlink-fleet-data](https://huggingface.co/datasets/juliensimon/starlink-fleet-data) | Daily Starlink constellation health — per-shell satellite counts and status | ![Starlink](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.starlink&label=updated&color=brightgreen) | Daily | 618 MB |
| [constellation-census](https://huggingface.co/datasets/juliensimon/constellation-census) | 19 satellite constellations (Starlink, OneWeb, Kuiper, GPS, etc.) — 11K+ satellites | ![Census](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['constellation-census']&label=updated&color=brightgreen) | Daily | 0.4 MB |
| [starlink-ground-stations](https://huggingface.co/datasets/juliensimon/starlink-ground-stations) | Starlink gateway and point-of-presence locations worldwide | ![Ground Stations](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['ground-stations']&label=updated&color=brightgreen) | Daily | 7 KB |
| [starlink-tle-latest](https://huggingface.co/datasets/juliensimon/starlink-tle-latest) | Latest Starlink + GPS TLEs in raw and Parquet format | ![TLE Latest](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['tle-latest']&label=updated&color=brightgreen) | Daily | 1.5 MB |
| [neo-close-approaches](https://huggingface.co/datasets/juliensimon/neo-close-approaches) | 35K+ near-Earth asteroid and comet close approaches from NASA JPL | ![NEO](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.neo&label=updated&color=brightgreen) | Daily | 3.2 MB |
| [jpl-small-body-database](https://huggingface.co/datasets/juliensimon/jpl-small-body-database) | 1.4M+ asteroids and comets with orbital elements and physical parameters | ![SBDB](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.sbdb&label=updated&color=brightgreen) | Daily | 200 MB |
| [sentry-impact-risk](https://huggingface.co/datasets/juliensimon/sentry-impact-risk) | Near-Earth objects with non-zero Earth impact probability | ![Sentry](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.sentry&label=updated&color=brightgreen) | Daily | <1 MB |
| [fireball-bolide-events](https://huggingface.co/datasets/juliensimon/fireball-bolide-events) | Fireball and bolide atmospheric impact events detected by US government sensors | ![Fireballs](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.fireballs&label=updated&color=brightgreen) | Weekly | <1 MB |
| [nhats-accessible-asteroids](https://huggingface.co/datasets/juliensimon/nhats-accessible-asteroids) | 4,800+ asteroids accessible for human space missions with delta-v requirements | ![NHATS](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.nhats&label=updated&color=brightgreen) | Daily | <1 MB |
| [satnogs-transmitters](https://huggingface.co/datasets/juliensimon/satnogs-transmitters) | 10K+ satellite radio transmitters and frequencies from SatNOGS | ![SatNOGS](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.satnogs&label=updated&color=brightgreen) | Weekly | 5 MB |
| [ucs-satellite-database](https://huggingface.co/datasets/juliensimon/ucs-satellite-database) | 7,500+ active satellites with purpose, operator, and orbit metadata | ![UCS](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.ucs&label=updated&color=brightgreen) | Quarterly | 5 MB |
| [iau-meteor-showers](https://huggingface.co/datasets/juliensimon/iau-meteor-showers) | 2,163 meteor shower records from the IAU Meteor Data Center | — | Static | <1 MB |
| [gcat-launch-vehicles](https://huggingface.co/datasets/juliensimon/gcat-launch-vehicles) | 4,875 launch vehicles, engines, and stages from GCAT | — | Static | <1 MB |

### Space Probes

| Dataset | Description | Last Updated | Schedule | Size |
|---------|-------------|-------------|----------|------|
| [deep-space-probes](https://huggingface.co/datasets/juliensimon/deep-space-probes) | 1.2M hourly readings from Voyager 1+2 and Pioneer 10+11 (1972–2025) | ![Probes](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['deep-space-probes']&label=updated&color=blue) | Monthly | 32 MB |
| [cassini-saturn-observations](https://huggingface.co/datasets/juliensimon/cassini-saturn-observations) | 63K Saturn observation records from the Cassini mission (2004–2017) | — | Static | 1.6 MB |
| [esa-mars-express-observations](https://huggingface.co/datasets/juliensimon/esa-mars-express-observations) | 1.66M observation metadata from ESA Mars Express (8 instruments, since 2003) | — | Weekly | 200 MB |
| [esa-rosetta-observations](https://huggingface.co/datasets/juliensimon/esa-rosetta-observations) | 8.3M observation records from ESA Rosetta at comet 67P | — | Static | 1 GB |
| [mars-chemcam-compositions](https://huggingface.co/datasets/juliensimon/mars-chemcam-compositions) | 30K+ Mars rock/soil oxide compositions from Curiosity ChemCam LIBS | — | Static | 1 MB |
| [mars-perseverance-weather](https://huggingface.co/datasets/juliensimon/mars-perseverance-weather) | Mars surface weather from Perseverance MEDA (temperature, pressure, wind, UV) | — | Monthly | ~100 MB |
| [nasa-eva-chronology](https://huggingface.co/datasets/juliensimon/nasa-eva-chronology) | 375 spacewalks (EVAs) — complete history from Gemini to ISS | — | Static | <1 MB |

### Planetary Science

| Dataset | Description | Last Updated | Schedule | Size |
|---------|-------------|-------------|----------|------|
| [lunar-craters-robbins](https://huggingface.co/datasets/juliensimon/lunar-craters-robbins) | 1.3M+ lunar impact craters from the Robbins 2019 database | — | Static | 200 MB |
| [mars-craters-robbins](https://huggingface.co/datasets/juliensimon/mars-craters-robbins) | 384K+ Mars impact craters from the Robbins & Hynek 2012 database | — | Static | 50 MB |
| [meteorite-landings](https://huggingface.co/datasets/juliensimon/meteorite-landings) | 45K+ known meteorite landings with classification and mass | — | Static | 5 MB |

### Space Weather

| Dataset | Description | Last Updated | Schedule | Size |
|---------|-------------|-------------|----------|------|
| [space-weather-indices](https://huggingface.co/datasets/juliensimon/space-weather-indices) | Daily Kp, Ap, F10.7 solar and geomagnetic indices since 1957 | ![Space Weather](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['space-weather']&label=updated&color=brightgreen) | Daily | 0.8 MB |
| [solar-flare-events](https://huggingface.co/datasets/juliensimon/solar-flare-events) | 16K+ individual solar flare detections from GOES X-ray sensors (2017+) | ![Solar Flares](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['solar-flares']&label=updated&color=brightgreen) | Daily | 0.5 MB |
| [dst-index](https://huggingface.co/datasets/juliensimon/dst-index) | 600K+ hourly geomagnetic storm intensity readings since 1957 (Dst index) | ![Dst](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['dst-index']&label=updated&color=brightgreen) | Daily | 1.7 MB |
| [donki-space-weather-events](https://huggingface.co/datasets/juliensimon/donki-space-weather-events) | 12K+ coronal mass ejections, geomagnetic storms, and solar particle events (2010+) | ![DONKI](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.donki&label=updated&color=brightgreen) | Daily | 1.0 MB |
| [solar-wind](https://huggingface.co/datasets/juliensimon/solar-wind) | Real-time solar wind speed, density, temperature, and magnetic field from L1 | ![Solar Wind](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['solar-wind']&label=updated&color=brightgreen) | Daily | 0.2 MB |
| [geomagnetic-kp-index](https://huggingface.co/datasets/juliensimon/geomagnetic-kp-index) | 3-hourly geomagnetic disturbance index (Kp 0-9) with NOAA storm scale | ![Kp](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['kp-index']&label=updated&color=brightgreen) | Daily | 4 KB |
| [silso-sunspot-number](https://huggingface.co/datasets/juliensimon/silso-sunspot-number) | 120K+ daily sunspot numbers since 1818 from SILSO/Royal Observatory of Belgium | ![Sunspot](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.sunspot&label=updated&color=brightgreen) | Monthly | 3 MB |
| [f107-solar-flux](https://huggingface.co/datasets/juliensimon/f107-solar-flux) | Daily F10.7 cm solar radio flux since 1947 — primary proxy for atmospheric drag | ![F10.7](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.f107&label=updated&color=brightgreen) | Daily | 2 MB |
| [swpc-alerts](https://huggingface.co/datasets/juliensimon/swpc-alerts) | Official NOAA space weather alerts, watches, and warnings | ![SWPC](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['swpc-alerts']&label=updated&color=brightgreen) | Daily | 2 MB |
| [solar-radio-bursts](https://huggingface.co/datasets/juliensimon/solar-radio-bursts) | Solar radio burst events (Type II/III/IV/V) from HEASARC | ![Solar Radio](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['solar-radio']&label=updated&color=brightgreen) | Weekly | 5 MB |
| [iers-earth-orientation](https://huggingface.co/datasets/juliensimon/iers-earth-orientation) | Daily Earth orientation parameters (polar motion, UT1-UTC, LOD) since 1973 | ![IERS](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['iers-eop']&label=updated&color=brightgreen) | Daily | 5 MB |
| [celestrak-space-weather](https://huggingface.co/datasets/juliensimon/celestrak-space-weather) | Consolidated space weather data for orbit propagation (Kp, Ap, F10.7) | ![CelesTrak SW](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['celestrak-sw']&label=updated&color=brightgreen) | Daily | 5 MB |
| [auroral-electrojet-index](https://huggingface.co/datasets/juliensimon/auroral-electrojet-index) | Hourly AE/AU/AL/AO auroral electrojet indices from Kyoto WDC | ![AE](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['ae-index']&label=updated&color=brightgreen) | Daily | 2 MB |

### Astronomy & Reference

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
| [nvss-radio-catalog](https://huggingface.co/datasets/juliensimon/nvss-radio-catalog) | 1.77M radio sources from the NRAO VLA Sky Survey at 1.4 GHz | — | Static | 150 MB |
| [first-radio-catalog](https://huggingface.co/datasets/juliensimon/first-radio-catalog) | 946K radio sources from the VLA FIRST Survey at 1.4 GHz (5" resolution) | — | Static | 113 MB |
| [erosita-erass1-xray](https://huggingface.co/datasets/juliensimon/erosita-erass1-xray) | 900K X-ray sources from the first eROSITA All-Sky Survey (eRASS1) | ![eROSITA](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.erosita&label=updated&color=brightgreen) | Per release | 500 MB |
| [gcvs-variable-stars](https://huggingface.co/datasets/juliensimon/gcvs-variable-stars) | 58K variable stars from the General Catalogue of Variable Stars | ![GCVS](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.gcvs&label=updated&color=brightgreen) | Quarterly | 15 MB |
| [fermi-4fgl-dr4](https://huggingface.co/datasets/juliensimon/fermi-4fgl-dr4) | 7K gamma-ray sources from Fermi LAT 14-year all-sky survey | ![Fermi](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['fermi-4fgl']&label=updated&color=brightgreen) | Annual | 50 MB |
| [chime-frb-catalog](https://huggingface.co/datasets/juliensimon/chime-frb-catalog) | 4,500+ fast radio bursts from the CHIME/FRB telescope | ![CHIME](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['chime-frb']&label=updated&color=brightgreen) | Semi-annual | 5 MB |
| [pantheon-plus-sne-ia](https://huggingface.co/datasets/juliensimon/pantheon-plus-sne-ia) | 1,550 Type Ia supernovae — gold standard cosmological distance dataset | — | Static | 10 MB |
| [tess-toi-candidates](https://huggingface.co/datasets/juliensimon/tess-toi-candidates) | 7K+ TESS Objects of Interest — active exoplanet candidates | ![TESS](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['tess-toi']&label=updated&color=brightgreen) | Weekly | 5 MB |
| [open-star-clusters](https://huggingface.co/datasets/juliensimon/open-star-clusters) | 7,167 Gaia-era open star clusters with distances and ages | — | Static | 5 MB |
| [icrf3-reference-frame](https://huggingface.co/datasets/juliensimon/icrf3-reference-frame) | 3,417 ICRF3 extragalactic radio sources — THE celestial reference frame | — | Static | 2 MB |
| [tgss-radio-catalog](https://huggingface.co/datasets/juliensimon/tgss-radio-catalog) | 624K radio sources at 150 MHz from GMRT TGSS ADR1 | — | Static | 80 MB |
| [sumss-radio-catalog](https://huggingface.co/datasets/juliensimon/sumss-radio-catalog) | 211K southern radio sources at 843 MHz from SUMSS | — | Static | 30 MB |
| [hipparcos-catalog](https://huggingface.co/datasets/juliensimon/hipparcos-catalog) | 118K brightest stars with precise positions and parallaxes from ESA Hipparcos | — | Static | 30 MB |
| [gaia-dr3-rrlyrae](https://huggingface.co/datasets/juliensimon/gaia-dr3-rrlyrae) | 272K RR Lyrae pulsating stars from Gaia DR3 — distance ladder | — | Static | 50 MB |
| [rc3-galaxy-morphology](https://huggingface.co/datasets/juliensimon/rc3-galaxy-morphology) | 23K bright galaxies with Hubble morphological types from RC3 | — | Static | 10 MB |
| [wds-double-stars](https://huggingface.co/datasets/juliensimon/wds-double-stars) | 157K visual double star systems from the Washington Double Star Catalog | ![WDS](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.wds&label=updated&color=brightgreen) | Weekly | 50 MB |
| [astronaut-database](https://huggingface.co/datasets/juliensimon/astronaut-database) | Every person who has been to space — 560 astronauts/cosmonauts | — | Static | <1 MB |
| [icecube-neutrino-catalog](https://huggingface.co/datasets/juliensimon/icecube-neutrino-catalog) | IceCube neutrino point sources from HEASARC | — | Static | <1 MB |
| [brown-dwarf-catalog](https://huggingface.co/datasets/juliensimon/brown-dwarf-catalog) | 14K ultracool and brown dwarfs within 40 pc | — | Static | 10 MB |
| [kepler-eclipsing-binaries](https://huggingface.co/datasets/juliensimon/kepler-eclipsing-binaries) | 2,177 Kepler eclipsing binary stars | — | Static | 1 MB |
| [planetary-nebulae](https://huggingface.co/datasets/juliensimon/planetary-nebulae) | 1,715 planetary nebulae from MUSE survey | — | Static | <1 MB |
| [vlass-radio-sources](https://huggingface.co/datasets/juliensimon/vlass-radio-sources) | 3.4M radio sources from VLA Sky Survey Epoch 1 (VLASS) at 3 GHz | — | Static | 681 MB |
| [chandra-x-ray-sources](https://huggingface.co/datasets/juliensimon/chandra-x-ray-sources) | 28K X-ray sources from the Chandra Source Catalog (CSC 2.1) | — | Static | 1.8 MB |
| [cosmicflows-galaxy-distances](https://huggingface.co/datasets/juliensimon/cosmicflows-galaxy-distances) | 56K galaxy distances from Cosmicflows-4 (8 distance methods) | — | Static | 3.7 MB |
| [gravitational-lenses](https://huggingface.co/datasets/juliensimon/gravitational-lenses) | 33K strong gravitational lenses from the lenscat community catalog | — | Static | 0.9 MB |

### Physics

| Dataset | Description | Last Updated | Schedule | Size |
|---------|-------------|-------------|----------|------|
| [pdg-particle-properties](https://huggingface.co/datasets/juliensimon/pdg-particle-properties) | Every known particle from the Particle Data Group | ![PDG](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.pdg&label=updated&color=brightgreen) | Annual | 50 MB |
| [crdb-cosmic-ray-spectra](https://huggingface.co/datasets/juliensimon/crdb-cosmic-ray-spectra) | 316K cosmic ray measurements from 131 experiments | ![CRDB](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.crdb&label=updated&color=brightgreen) | Quarterly | 50 MB |
| [auger-cosmic-rays](https://huggingface.co/datasets/juliensimon/auger-cosmic-rays) | Ultra-high-energy cosmic ray events from Pierre Auger Observatory | — | Static | 100 MB |
| [swift-bat-hard-xray-survey](https://huggingface.co/datasets/juliensimon/swift-bat-hard-xray-survey) | 1,893 hard X-ray sources (14–195 keV) from Swift-BAT 157-month survey | — | Static | 0.3 MB |
| [fermi-4lac-agn-catalog](https://huggingface.co/datasets/juliensimon/fermi-4lac-agn-catalog) | 3,409 gamma-ray AGN from Fermi LAT Fourth AGN Catalog (4LAC) | — | Static | 0.7 MB |
| [fermi-3fhl-hard-gamma-ray](https://huggingface.co/datasets/juliensimon/fermi-3fhl-hard-gamma-ray) | 1,558 hard gamma-ray sources (>10 GeV) from Fermi LAT 3FHL | — | Static | 0.6 MB |
| [fermi-gbm-triggers](https://huggingface.co/datasets/juliensimon/fermi-gbm-triggers) | 12.5K+ Fermi GBM triggers — all triggers, not just confirmed GRBs | ![GBM](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['fermi-gbm-triggers']&label=updated&color=brightgreen) | Daily | 1.8 MB |
| [integral-ibis-hard-xray](https://huggingface.co/datasets/juliensimon/integral-ibis-hard-xray) | 929 hard X-ray sources from INTEGRAL IBIS 17-year survey (17–290 keV) | — | Static | 0.3 MB |
| [tevcat-tev-gamma-ray](https://huggingface.co/datasets/juliensimon/tevcat-tev-gamma-ray) | 322 TeV gamma-ray sources — THE ground-based VHE reference catalog | — | Static | <1 MB |
| [lhaaso-gamma-ray-sources](https://huggingface.co/datasets/juliensimon/lhaaso-gamma-ray-sources) | 180 ultra-high-energy gamma-ray sources from 1LHAASO (2024) | — | Static | <1 MB |
| [hawc-tev-gamma-ray](https://huggingface.co/datasets/juliensimon/hawc-tev-gamma-ray) | 65 TeV gamma-ray sources from the 3HWC HAWC catalog | — | Static | <1 MB |

## Collections on Hugging Face

- [Orbital Mechanics](https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994) — satellites, TLEs, launches, NEOs, asteroids, impact risk
- [Space Probes & Missions](https://huggingface.co/collections/juliensimon/space-probe-and-mission-datasets-69c3fe82d410a42b1e313167) — Voyager, Pioneer, Cassini, Mars Express, Rosetta, Curiosity, Perseverance, EVAs
- [Planetary Science](https://huggingface.co/collections/juliensimon/planetary-science-datasets-69c2d4683bd6a66c34fb4af2) — lunar craters, Mars craters, Mars geochemistry, meteorites
- [Space Weather](https://huggingface.co/collections/juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70) — solar flares, CMEs, geomagnetic storms, solar wind, Kp/Ap/F10.7 indices
- [Astronomy](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) — exoplanets, pulsars, radio surveys, X-ray catalogs, variable stars, gravitational waves, galaxy morphology
- [Physics](https://huggingface.co/collections/juliensimon/physics-datasets-69c2d4682d37dfdb77447bd7) — particle properties, cosmic ray spectra, hard X-ray surveys, gamma-ray catalogs (TeV/UHE)

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
python scripts/update-sbdb.py
python scripts/update-sentry.py
python scripts/update-fireballs.py
python scripts/update-nhats.py
python scripts/update-satnogs.py
python scripts/update-ucs.py  # requires: pip install openpyxl
python scripts/update-meteor-showers.py
python scripts/update-gcat.py

# Planetary Science
python scripts/update-lunar-craters.py
python scripts/update-mars-craters.py
python scripts/update-meteorite-landings.py

# Space Weather
python scripts/update-space-weather.py
pip install netCDF4 && python scripts/update-solar-flares.py
python scripts/update-dst-index.py
python scripts/update-donki.py
python scripts/update-solar-wind.py
python scripts/update-kp-index.py
python scripts/update-sunspot.py
python scripts/update-f107.py
python scripts/update-swpc-alerts.py
python scripts/update-solar-radio.py
python scripts/update-iers-eop.py
python scripts/update-celestrak-sw.py
python scripts/update-ae-index.py

# Space Probes
python scripts/update-deep-space-probes.py
python scripts/update-cassini.py
python scripts/update-mars-express.py
python scripts/update-rosetta.py
python scripts/update-chemcam.py
python scripts/update-meda-weather.py
python scripts/update-eva.py

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
python scripts/update-nvss.py
python scripts/update-first.py
python scripts/update-erosita.py
python scripts/update-gcvs.py
pip install astropy && python scripts/update-fermi-4fgl.py
python scripts/update-chime-frb.py
python scripts/update-pantheon.py
python scripts/update-tess-toi.py
python scripts/update-open-clusters.py
python scripts/update-icrf3.py
python scripts/update-tgss.py
python scripts/update-sumss.py
python scripts/update-hipparcos.py
python scripts/update-gaia-rrlyrae.py
python scripts/update-rc3.py
python scripts/update-icecube.py
python scripts/update-brown-dwarfs.py
python scripts/update-kepler-eb.py
python scripts/update-planetary-nebulae.py
python scripts/update-wds.py
python scripts/update-astronauts.py
python scripts/update-vlass.py
python scripts/update-chandra.py
python scripts/update-cosmicflows.py
python scripts/update-gravitational-lenses.py

# Physics
pip install particle && python scripts/update-pdg.py
pip install crdb && python scripts/update-crdb.py
python scripts/update-auger.py
python scripts/update-swift-bat.py
python scripts/update-fermi-4lac.py
python scripts/update-fermi-3fhl.py
python scripts/update-fermi-gbm-triggers.py
python scripts/update-integral-ibis.py
python scripts/update-tevcat.py
python scripts/update-lhaaso.py
python scripts/update-hawc.py
```

## Bulk ingestion

`build-tle-archive.py` builds historical TLE data from Space-Track yearly bulk zip exports (1959–2025). Daily updates for the current year are automated via `update-tle-history.py` (fetches yesterday's GP history, appends to `tle_{year}.parquet`). Requires `SPACETRACK_USER` and `SPACETRACK_PASS` secrets.

`backfill-tle-history.py` and `backfill-starlink-snapshots.py` are one-time scripts for filling gaps from Space-Track GP history. Not needed for ongoing operation.

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
| Orbital Mechanics | [CelesTrak](https://celestrak.org/) (Dr. T.S. Kelso), [Space-Track.org](https://www.space-track.org/), [GCAT](https://planet4589.org/space/gcat/) (Jonathan McDowell), [Starlink Insider](https://starlinkinsider.com/), [NASA/JPL CNEOS](https://cneos.jpl.nasa.gov/), [NASA/JPL SSD](https://ssd.jpl.nasa.gov/), [NASA NHATS](https://cneos.jpl.nasa.gov/nhats/), [SatNOGS](https://db.satnogs.org/) (Libre Space Foundation), [UCS](https://www.ucsusa.org/resources/satellite-database), [IAU MDC](https://www.ta3.sk/IAUC22DB/MDC2022/) |
| Space Probes | [NASA SPDF COHOWeb](https://spdf.gsfc.nasa.gov/) (Voyager, Pioneer), [PDS Atmospheres](https://pds-atmospheres.nmsu.edu/) (Cassini, MEDA), [PDS Geosciences](https://pds-geosciences.wustl.edu/) (ChemCam), [ESA PSA](https://psa.esa.int/) (Mars Express, Rosetta) |
| Planetary Science | [USGS Astrogeology](https://astrogeology.usgs.gov/) (Robbins crater databases), [Meteoritical Society](https://www.lpi.usra.edu/meteor/) (via NASA data.gov) |
| Space Weather | [NOAA SWPC](https://www.swpc.noaa.gov/), [WDC Kyoto](https://wdc.kugi.kyoto-u.ac.jp/dstdir/), [NASA CCMC DONKI](https://ccmc.gsfc.nasa.gov/tools/DONKI/), [NOAA NCEI](https://www.ncei.noaa.gov/) GOES-16 XRS, [SILSO](https://www.sidc.be/SILSO/) (Royal Observatory of Belgium), [LASP LISIRD](https://lasp.colorado.edu/lisird/) (F10.7), [IERS](https://www.iers.org/) |
| Astronomy | [NASA Exoplanet Archive](https://exoplanetarchive.ipac.caltech.edu/), [NASA HEASARC](https://heasarc.gsfc.nasa.gov/) (Fermi, Chandra, Swift), [GWOSC](https://gwosc.org/) (LIGO/Virgo/KAGRA), [ATNF](https://www.atnf.csiro.au/research/pulsar/psrcat/) Pulsar Catalogue, [OpenNGC](https://github.com/mattiaverga/OpenNGC), [Green's SNR Catalog](https://www.mrao.cam.ac.uk/surveys/snrs/), [SIMBAD](https://simbad.u-strasbg.fr/) (CDS Strasbourg), [VizieR](https://vizier.cds.unistra.fr/) (CDS Strasbourg — VLASS, Cosmicflows-4, INTEGRAL, LHAASO, HAWC), [Fermi LAT](https://fermi.gsfc.nasa.gov/ssc/), [CHIME/FRB](https://www.chime-frb.ca/), [eROSITA](https://erosita.mpe.mpg.de/), [Pantheon+](https://github.com/PantheonPlusSH0ES/DataRelease), [lenscat](https://github.com/lenscat/lenscat) |
| Physics | [Particle Data Group](https://pdg.lbl.gov/) (PDG), [CRDB](https://lpsc.in2p3.fr/crdb/) (Cosmic Ray DataBase), [Pierre Auger Observatory](https://www.auger.org/) (via Zenodo), [IceCube](https://icecube.wisc.edu/) (via HEASARC), [Swift/BAT](https://swift.gsfc.nasa.gov/results/bs157mon/) (NASA), [INTEGRAL IBIS](https://www.isdc.unige.ch/) (ESA), [TeVCat](http://tevcat.uchicago.edu/) (via HEASARC), [LHAASO](http://english.ihep.cas.cn/) (via VizieR), [HAWC](https://www.hawc-observatory.org/) (via VizieR) |

## License

Pipeline code: [MIT](LICENSE). Datasets: [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/).
