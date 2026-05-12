# space-datasets — Open Space, Astronomy & Physics Datasets on Hugging Face

Open-source data pipelines that publish **204 space, astronomy, and physics datasets** to [Hugging Face](https://huggingface.co/juliensimon) in Parquet format. Covers satellites, orbital mechanics, asteroids, space weather, solar activity, exoplanets, gravitational waves, pulsars, radio surveys, X-ray catalogs, space probes, particle physics, and more — sourced from NASA, NOAA, ESA, SpaceX, Wikidata, and other public APIs. Updated daily via GitHub Actions.

All datasets are loadable in one line (`load_dataset("juliensimon/...")`), require no API keys, and work with `pandas`, `polars`, or any Parquet-compatible tool.

### Top downloads

<!-- TOP_DOWNLOADS_START -->
**117,360** downloads (all-time)  ·  **10** likes  ·  **213** datasets  ·  updated 2026-05-12

| # | Dataset | Downloads |
|--:|---------|----------:|
| 1 | [esa-exomars-tgo-observations](https://huggingface.co/datasets/juliensimon/esa-exomars-tgo-observations) | 14,091 |
| 2 | [esa-rosetta-observations](https://huggingface.co/datasets/juliensimon/esa-rosetta-observations) | 13,584 |
| 3 | [gaia-dr3-eclipsing-binaries](https://huggingface.co/datasets/juliensimon/gaia-dr3-eclipsing-binaries) | 5,890 |
| 4 | [gaia-dr3-white-dwarfs](https://huggingface.co/datasets/juliensimon/gaia-dr3-white-dwarfs) | 5,800 |
| 5 | [gaia-dr3-cepheids](https://huggingface.co/datasets/juliensimon/gaia-dr3-cepheids) | 5,465 |
| 6 | [gaia-dr3-rrlyrae](https://huggingface.co/datasets/juliensimon/gaia-dr3-rrlyrae) | 5,377 |
| 7 | [gaia-dr3-young-stellar-objects](https://huggingface.co/datasets/juliensimon/gaia-dr3-young-stellar-objects) | 5,262 |
| 8 | [gaia-dr3-spectroscopic-binaries](https://huggingface.co/datasets/juliensimon/gaia-dr3-spectroscopic-binaries) | 4,906 |
| 9 | [space-track-tle-history](https://huggingface.co/datasets/juliensimon/space-track-tle-history) | 4,707 |
| 10 | [wmo-oscar-satellites](https://huggingface.co/datasets/juliensimon/wmo-oscar-satellites) | 2,519 |
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
![Reentry Events](https://github.com/juliensimon/space-datasets/actions/workflows/update-reentry-events.yml/badge.svg)
![Space Missions](https://github.com/juliensimon/space-datasets/actions/workflows/update-space-missions.yml/badge.svg)
![Spacecraft](https://github.com/juliensimon/space-datasets/actions/workflows/update-spacecraft.yml/badge.svg)
![Launch Vehicles](https://github.com/juliensimon/space-datasets/actions/workflows/update-launch-vehicles.yml/badge.svg)
![Space Agencies](https://github.com/juliensimon/space-datasets/actions/workflows/update-space-agencies.yml/badge.svg)
![Comets](https://github.com/juliensimon/space-datasets/actions/workflows/update-comets.yml/badge.svg)
![SpaceX Launches](https://github.com/juliensimon/space-datasets/actions/workflows/update-spacex-launches.yml/badge.svg)
![Constellation TLEs](https://github.com/juliensimon/space-datasets/actions/workflows/update-constellation-tles.yml/badge.svg)
![GMN Meteors](https://github.com/juliensimon/space-datasets/actions/workflows/update-gmn-meteors.yml/badge.svg)
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
![Neutron Monitor](https://github.com/juliensimon/space-datasets/actions/workflows/update-neutron-monitor.yml/badge.svg)
![OMNI](https://github.com/juliensimon/space-datasets/actions/workflows/update-omni.yml/badge.svg)
![Substorm Onsets](https://github.com/juliensimon/space-datasets/actions/workflows/update-substorm-onsets.yml/badge.svg)
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
![Supernovae](https://github.com/juliensimon/space-datasets/actions/workflows/update-supernovae.yml/badge.svg)
![Astronomers](https://github.com/juliensimon/space-datasets/actions/workflows/update-astronomers.yml/badge.svg)
![Observatories](https://github.com/juliensimon/space-datasets/actions/workflows/update-observatories.yml/badge.svg)
![Constellations](https://github.com/juliensimon/space-datasets/actions/workflows/update-constellations.yml/badge.svg)
![Nebulae](https://github.com/juliensimon/space-datasets/actions/workflows/update-nebulae.yml/badge.svg)
![Planck SZ2](https://github.com/juliensimon/space-datasets/actions/workflows/update-planck-sz2.yml/badge.svg)
![X-ray Binaries](https://github.com/juliensimon/space-datasets/actions/workflows/update-xray-binaries.yml/badge.svg)
![CVs](https://github.com/juliensimon/space-datasets/actions/workflows/update-cataclysmic-variables.yml/badge.svg)
![JWST](https://github.com/juliensimon/space-datasets/actions/workflows/update-jwst.yml/badge.svg)
![HST](https://github.com/juliensimon/space-datasets/actions/workflows/update-hst.yml/badge.svg)
![Kepler](https://github.com/juliensimon/space-datasets/actions/workflows/update-kepler-obs.yml/badge.svg)
![K2](https://github.com/juliensimon/space-datasets/actions/workflows/update-k2-obs.yml/badge.svg)
![GALEX](https://github.com/juliensimon/space-datasets/actions/workflows/update-galex.yml/badge.svg)
![IUE](https://github.com/juliensimon/space-datasets/actions/workflows/update-iue.yml/badge.svg)
![FUSE](https://github.com/juliensimon/space-datasets/actions/workflows/update-fuse.yml/badge.svg)
![EUVE](https://github.com/juliensimon/space-datasets/actions/workflows/update-euve.yml/badge.svg)
![SE Space Q&A](https://github.com/juliensimon/space-datasets/actions/workflows/update-stackexchange-space.yml/badge.svg)
![HII Regions](https://github.com/juliensimon/space-datasets/actions/workflows/update-hii-regions.yml/badge.svg)
![Pulsar Glitches](https://github.com/juliensimon/space-datasets/actions/workflows/update-pulsar-glitches.yml/badge.svg)
![Cosmic Voids](https://github.com/juliensimon/space-datasets/actions/workflows/update-cosmic-voids.yml/badge.svg)
![APOD](https://github.com/juliensimon/space-datasets/actions/workflows/update-apod.yml/badge.svg)
<!-- Space Probes -->
![Astronauts](https://github.com/juliensimon/space-datasets/actions/workflows/update-astronauts.yml/badge.svg)
![BepiColombo](https://github.com/juliensimon/space-datasets/actions/workflows/update-bepicolombo.yml/badge.svg)
![ExoMars TGO](https://github.com/juliensimon/space-datasets/actions/workflows/update-exomars-tgo.yml/badge.svg)
![JUICE](https://github.com/juliensimon/space-datasets/actions/workflows/update-juice.yml/badge.svg)
![Mars Express](https://github.com/juliensimon/space-datasets/actions/workflows/update-mars-express.yml/badge.svg)
![Mars Rovers](https://github.com/juliensimon/space-datasets/actions/workflows/update-mars-rovers.yml/badge.svg)
![MAVEN](https://github.com/juliensimon/space-datasets/actions/workflows/update-maven.yml/badge.svg)
![Venus Express](https://github.com/juliensimon/space-datasets/actions/workflows/update-venus-express.yml/badge.svg)
![Artemis II](https://github.com/juliensimon/space-datasets/actions/workflows/update-artemis-ii.yml/badge.svg)
![Deep Space Probes](https://github.com/juliensimon/space-datasets/actions/workflows/update-deep-space-probes.yml/badge.svg)
![MEDA Weather](https://github.com/juliensimon/space-datasets/actions/workflows/update-meda-weather.yml/badge.svg)
![Space Tourism](https://github.com/juliensimon/space-datasets/actions/workflows/update-space-tourism.yml/badge.svg)
<!-- Planetary Science -->
![Impact Craters](https://github.com/juliensimon/space-datasets/actions/workflows/update-impact-craters.yml/badge.svg)
![Meteorites](https://github.com/juliensimon/space-datasets/actions/workflows/update-meteorites.yml/badge.svg)
<!-- Physics -->
![CRDB](https://github.com/juliensimon/space-datasets/actions/workflows/update-crdb.yml/badge.svg)
![PDG](https://github.com/juliensimon/space-datasets/actions/workflows/update-pdg.yml/badge.svg)
![Fermi GBM](https://github.com/juliensimon/space-datasets/actions/workflows/update-fermi-gbm-triggers.yml/badge.svg)
![Physics Nobel](https://github.com/juliensimon/space-datasets/actions/workflows/update-physics-nobel.yml/badge.svg)

## Datasets

### Orbital Mechanics

Track every object orbiting Earth and beyond. This collection covers the complete NORAD satellite catalog, daily Starlink constellation health, two-line element sets dating back to 1959, launch records, and near-Earth asteroid monitoring from NASA JPL. Whether you're propagating orbits with SGP4, analyzing space debris trends, or studying asteroid close approaches, these datasets provide the foundation for orbital mechanics research and space situational awareness.

| Dataset | Description | Last Updated | Schedule | Size |
|---------|-------------|-------------|----------|------|
| [ast-spacemobile-fleet-data](https://huggingface.co/datasets/juliensimon/ast-spacemobile-fleet-data) | Daily AST SpaceMobile BlueBird + BlueWalker direct-to-cell constellation health | ![AST SpaceMobile](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['ast-spacemobile']&label=updated&color=brightgreen) | Daily | <1 MB |
| [asterank-asteroid-mining](https://huggingface.co/datasets/juliensimon/asterank-asteroid-mining) | Mining economics for 400K+ asteroids: estimated value, profit, delta-v, and spectral types from Asterank | — | Static | ~20 MB |
| [asteroid-lightcurves-lcdb](https://huggingface.co/datasets/juliensimon/asteroid-lightcurves-lcdb) | Rotation periods, lightcurve amplitudes, diameters, and taxonomies for 20K+ asteroids from LCDB | — | Static | ~1 MB |
| [blue-origin-launches](https://huggingface.co/datasets/juliensimon/blue-origin-launches) | Complete Blue Origin launch manifest — New Shepard + New Glenn flights (past and upcoming) | ![Blue Origin](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['blue-origin-launches']&label=updated&color=brightgreen) | Daily | <1 MB |
| [bus-demeo-asteroid-taxonomy](https://huggingface.co/datasets/juliensimon/bus-demeo-asteroid-taxonomy) | Reference Bus-DeMeo spectroscopic taxonomy for 371 asteroids (24 classes, 0.45-2.45 um) | — | Static | <1 MB |
| [comet-catalog](https://huggingface.co/datasets/juliensimon/comet-catalog) | 1,278 comets with orbital elements, discoverers, and discovery dates from Wikidata | ![Comets](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['comets']&label=updated&color=brightgreen) | Quarterly | <1 MB |
| [constellation-census](https://huggingface.co/datasets/juliensimon/constellation-census) | 19 satellite constellations (Starlink, OneWeb, Kuiper, GPS, etc.) — 11K+ satellites | ![Census](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['constellation-census']&label=updated&color=brightgreen) | Daily | 0.4 MB |
| [constellation-tle-latest](https://huggingface.co/datasets/juliensimon/constellation-tle-latest) | Daily TLE snapshots for 18 constellations: GNSS, OneWeb, Iridium, Planet, SES, Intelsat, and more | ![Constellation TLEs](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['constellation-tles']&label=updated&color=brightgreen) | Daily | <5 MB |
| [fcc-ngso-filings](https://huggingface.co/datasets/juliensimon/fcc-ngso-filings) | FCC IBFS filings for major NGSO constellations — requested satellite counts, shells, status | ![FCC NGSO](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['fcc-ngso-filings']&label=updated&color=brightgreen) | Weekly | <1 MB |
| [fireball-bolide-events](https://huggingface.co/datasets/juliensimon/fireball-bolide-events) | Fireball and bolide atmospheric impact events detected by US government sensors | ![Fireballs](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.fireballs&label=updated&color=brightgreen) | Weekly | <1 MB |
| [gcat-launch-vehicles](https://huggingface.co/datasets/juliensimon/gcat-launch-vehicles) | 4,875 launch vehicles, engines, and stages from GCAT | — | Static | <1 MB |
| [gcat-satellite-catalog](https://huggingface.co/datasets/juliensimon/gcat-satellite-catalog) | 68K+ satellites, rocket bodies, and debris from GCAT (Jonathan McDowell) | ![GCAT SATCAT](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['gcat-satcat']&label=updated&color=brightgreen) | Weekly | 2.6 MB |
| [global-meteor-network](https://huggingface.co/datasets/juliensimon/global-meteor-network) | 3M+ individual meteor trajectories with orbits, velocities, and shower IDs from 500+ all-sky cameras worldwide (GMN) | ![GMN Meteors](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['gmn-meteors']&label=updated&color=brightgreen) | Daily | 245 MB |
| [globalstar-fleet-data](https://huggingface.co/datasets/juliensimon/globalstar-fleet-data) | Daily Globalstar constellation health — per-generation satellite counts and status (Amazon-owned as of 2026) | ![Globalstar](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.globalstar&label=updated&color=brightgreen) | Daily | <1 MB |
| [iau-meteor-showers](https://huggingface.co/datasets/juliensimon/iau-meteor-showers) | 2,163 meteor shower records from the IAU Meteor Data Center | — | Static | <1 MB |
| [jpl-small-body-database](https://huggingface.co/datasets/juliensimon/jpl-small-body-database) | 1.4M+ asteroids and comets with orbital elements and physical parameters | ![SBDB](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.sbdb&label=updated&color=brightgreen) | Daily | 200 MB |
| [kuiper-fleet-data](https://huggingface.co/datasets/juliensimon/kuiper-fleet-data) | Daily Amazon Project Kuiper constellation health — per-shell satellite counts and status | ![Kuiper](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.kuiper&label=updated&color=brightgreen) | Daily | <1 MB |
| [launch-cost-to-leo](https://huggingface.co/datasets/juliensimon/launch-cost-to-leo) | Historical and current launch vehicle costs per kilogram to low Earth orbit (LEO) | — | Static | <1 MB |
| [launch-vehicles](https://huggingface.co/datasets/juliensimon/launch-vehicles) | 230+ orbital launch vehicles with specs and payload capacity from Wikidata | ![Launch Vehicles](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['launch-vehicles']&label=updated&color=brightgreen) | Quarterly | <1 MB |
| [mpc-comet-elements](https://huggingface.co/datasets/juliensimon/mpc-comet-elements) | Orbital elements for all known comets from the Minor Planet Center | — | Static | <1 MB |
| [neo-close-approaches](https://huggingface.co/datasets/juliensimon/neo-close-approaches) | 35K+ near-Earth asteroid and comet close approaches from NASA JPL | ![NEO](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.neo&label=updated&color=brightgreen) | Daily | 3.2 MB |
| [neowise-asteroid-properties](https://huggingface.co/datasets/juliensimon/neowise-asteroid-properties) | Diameters, albedos, and beaming parameters for 100K+ asteroids from WISE/NEOWISE | — | Static | ~10 MB |
| [nesvorny-asteroid-families](https://huggingface.co/datasets/juliensimon/nesvorny-asteroid-families) | 150K+ asteroids grouped into dynamical families by hierarchical clustering (Nesvorny et al.) | — | Static | ~10 MB |
| [nhats-accessible-asteroids](https://huggingface.co/datasets/juliensimon/nhats-accessible-asteroids) | 4,800+ asteroids accessible for human space missions with delta-v requirements | ![NHATS](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.nhats&label=updated&color=brightgreen) | Daily | <1 MB |
| [oneweb-fleet-data](https://huggingface.co/datasets/juliensimon/oneweb-fleet-data) | Daily OneWeb (Eutelsat) constellation health — per-plane satellite counts at ~1,200 km | ![OneWeb](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.oneweb&label=updated&color=brightgreen) | Daily | <1 MB |
| [orbital-fragmentation-events](https://huggingface.co/datasets/juliensimon/orbital-fragmentation-events) | Catalog of orbital fragmentation events (breakups, explosions, collisions) from NORAD SATCAT | — | Static | <1 MB |
| [reentry-events](https://huggingface.co/datasets/juliensimon/reentry-events) | 35K satellite and debris reentry events with decay dates and locations | ![Reentry](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['reentry-events']&label=updated&color=brightgreen) | Daily | <1 MB |
| [satnogs-transmitters](https://huggingface.co/datasets/juliensimon/satnogs-transmitters) | 10K+ satellite radio transmitters and frequencies from SatNOGS | ![SatNOGS](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.satnogs&label=updated&color=brightgreen) | Weekly | 5 MB |
| [sdss-asteroid-taxonomy](https://huggingface.co/datasets/juliensimon/sdss-asteroid-taxonomy) | Compositional taxonomy for 50K+ SDSS observations of asteroids with ugriz reflectances | — | Static | ~5 MB |
| [sentry-impact-risk](https://huggingface.co/datasets/juliensimon/sentry-impact-risk) | Near-Earth objects with non-zero Earth impact probability | ![Sentry](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.sentry&label=updated&color=brightgreen) | Daily | <1 MB |
| [space-agency-database](https://huggingface.co/datasets/juliensimon/space-agency-database) | Space agencies and governmental space organizations worldwide | ![Space Agencies](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['space-agencies']&label=updated&color=brightgreen) | Quarterly | <1 MB |
| [space-launch-log](https://huggingface.co/datasets/juliensimon/space-launch-log) | Every orbital and suborbital launch since 1957 with sites and outcomes | ![Launches](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['launch-log']&label=updated&color=brightgreen) | Weekly | 2.4 MB |
| [space-missions](https://huggingface.co/datasets/juliensimon/space-missions) | 24K+ crewed and uncrewed space missions from Wikidata | ![Space Missions](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['space-missions']&label=updated&color=brightgreen) | Quarterly | <1 MB |
| [space-track-satcat](https://huggingface.co/datasets/juliensimon/space-track-satcat) | Complete NORAD satellite catalog — 68K satellites, rocket bodies, and debris | ![SATCAT](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.satcat&label=updated&color=brightgreen) | Daily | 1.6 MB |
| [space-track-tle-history](https://huggingface.co/datasets/juliensimon/space-track-tle-history) | 238 million orbital element sets for every cataloged object since 1959 | ![TLE](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.tle-history&label=updated&color=brightgreen) | Daily | 10.9 GB |
| [spacecraft-database](https://huggingface.co/datasets/juliensimon/spacecraft-database) | 8K+ spacecraft with operators, manufacturers, and orbits from Wikidata | ![Spacecraft](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['spacecraft']&label=updated&color=brightgreen) | Quarterly | <1 MB |
| [spacex-launches](https://huggingface.co/datasets/juliensimon/spacex-launches) | 659 SpaceX missions with timelines, descriptions, and carousel photos from spacex.com | ![SpaceX](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['spacex-launches']&label=updated&color=brightgreen) | Daily | ~80 MB |
| [ssodnet-asteroid-properties](https://huggingface.co/datasets/juliensimon/ssodnet-asteroid-properties) | Physical properties for 500K+ asteroids (diameters, albedos, taxonomy, masses) from IMCCE SsODNet | — | Static | ~50 MB |
| [starlink-fleet-data](https://huggingface.co/datasets/juliensimon/starlink-fleet-data) | Daily Starlink constellation health — per-shell satellite counts and status | ![Starlink](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.starlink&label=updated&color=brightgreen) | Daily | 618 MB |
| [starlink-ground-stations](https://huggingface.co/datasets/juliensimon/starlink-ground-stations) | Starlink gateway and point-of-presence locations worldwide | ![Ground Stations](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['ground-stations']&label=updated&color=brightgreen) | Daily | 7 KB |
| [starlink-tle-latest](https://huggingface.co/datasets/juliensimon/starlink-tle-latest) | Latest Starlink + GPS TLEs in raw and Parquet format | ![TLE Latest](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['tle-latest']&label=updated&color=brightgreen) | Daily | 1.5 MB |
| [tno-centaur-properties](https://huggingface.co/datasets/juliensimon/tno-centaur-properties) | 652 TNO/Centaur physical properties (diameter, albedo, density) from PDS | — | Static | <1 MB |
| [ucs-satellite-database](https://huggingface.co/datasets/juliensimon/ucs-satellite-database) | 7,500+ active satellites with purpose, operator, and orbit metadata | ![UCS](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.ucs&label=updated&color=brightgreen) | Quarterly | 5 MB |
| [ula-launches](https://huggingface.co/datasets/juliensimon/ula-launches) | Complete United Launch Alliance manifest — Atlas V, Delta, Vulcan Centaur flights | ![ULA](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['ula-launches']&label=updated&color=brightgreen) | Daily | <1 MB |
| [wmo-oscar-satellites](https://huggingface.co/datasets/juliensimon/wmo-oscar-satellites) | 1,025 Earth-observing satellites and 1,230 instruments from WMO OSCAR | ![WMO OSCAR](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['wmo-oscar']&label=updated&color=brightgreen) | Quarterly | <1 MB |

### Space Probes & Missions

Data returned by humanity's most distant spacecraft and surface explorers. Includes 50+ years of interplanetary measurements from Voyager and Pioneer, Cassini's Saturn observations, Mars surface weather and 2M+ images from Perseverance and Curiosity, MAVEN atmospheric key parameters, rock compositions from Curiosity's laser spectrometer, marsquake detections from InSight, and million-record observation logs from ESA's Mars Express, ExoMars TGO, Rosetta, BepiColombo, JUICE, and Huygens missions. Ideal for planetary science, mission planning studies, and multi-instrument data fusion.

| Dataset | Description | Last Updated | Schedule | Size |
|---------|-------------|-------------|----------|------|
| [artemis-ii](https://huggingface.co/datasets/juliensimon/artemis-ii) | Artemis II crewed lunar flyby: 1,285 trajectory vectors, crew manifest, mission timeline, payloads | ![Artemis II](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['artemis-ii']&label=updated&color=brightgreen) | Daily | <1 MB |
| [cassini-saturn-observations](https://huggingface.co/datasets/juliensimon/cassini-saturn-observations) | 63K Saturn observation records from the Cassini mission (2004-2017) | — | Static | 1.6 MB |
| [deep-space-probes](https://huggingface.co/datasets/juliensimon/deep-space-probes) | 1.2M hourly readings from Voyager 1+2 and Pioneer 10+11 (1972-2025) | ![Probes](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['deep-space-probes']&label=updated&color=blue) | Monthly | 32 MB |
| [esa-bepicolombo-observations](https://huggingface.co/datasets/juliensimon/esa-bepicolombo-observations) | 176K+ observation records from ESA/JAXA BepiColombo Mercury mission (11 instruments, cruise + flybys) | ![BepiColombo](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['bepicolombo']&label=updated&color=brightgreen) | Weekly | ~20 MB |
| [esa-exomars-tgo-observations](https://huggingface.co/datasets/juliensimon/esa-exomars-tgo-observations) | 27M+ observation records from ESA ExoMars TGO (4 instruments, since 2018) | ![ExoMars TGO](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['exomars-tgo']&label=updated&color=brightgreen) | Weekly | ~2 GB |
| [esa-huygens-titan-descent](https://huggingface.co/datasets/juliensimon/esa-huygens-titan-descent) | 14K+ observation metadata from ESA Huygens Titan descent (8 instruments, 2005) | — | Static | <1 MB |
| [esa-juice-observations](https://huggingface.co/datasets/juliensimon/esa-juice-observations) | 6K+ observation records from ESA JUICE Jupiter mission (cruise phase, growing) | ![JUICE](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['juice']&label=updated&color=brightgreen) | Weekly | <1 MB |
| [esa-mars-express-observations](https://huggingface.co/datasets/juliensimon/esa-mars-express-observations) | 1.66M observation metadata from ESA Mars Express (8 instruments, since 2003) | ![Mars Express](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['mars-express']&label=updated&color=brightgreen) | Weekly | 200 MB |
| [esa-rosetta-observations](https://huggingface.co/datasets/juliensimon/esa-rosetta-observations) | 14M+ observation records from ESA Rosetta at comet 67P (15 instruments incl. Philae) | — | Static | ~2 GB |
| [esa-venus-express-observations](https://huggingface.co/datasets/juliensimon/esa-venus-express-observations) | 525K observation metadata from ESA Venus Express (5 instruments, 2006-2014) | ![Venus Express](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['venus-express']&label=updated&color=brightgreen) | Weekly | 21 MB |
| [galileo-jupiter-atmosphere](https://huggingface.co/datasets/juliensimon/galileo-jupiter-atmosphere) | Jupiter atmospheric profile from Galileo Probe descent (1995) — temperature, pressure, density to 24 bar | — | Static | <1 MB |
| [gcat-deep-space](https://huggingface.co/datasets/juliensimon/gcat-deep-space) | 1,206 deep space objects and 469 planetary landings from GCAT | ![GCAT Deep Space](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['gcat-deep-space']&label=updated&color=brightgreen) | Weekly | <1 MB |
| [huygens-titan-atmosphere](https://huggingface.co/datasets/juliensimon/huygens-titan-atmosphere) | Titan atmospheric profile from Huygens Probe descent (2005) — 1,400 km to surface | — | Static | <1 MB |
| [insight-marsquake-catalog](https://huggingface.co/datasets/juliensimon/insight-marsquake-catalog) | 2,715 marsquakes detected by InSight SEIS seismometer (2019-2022, final catalog) | — | Static | <1 MB |
| [isro-missions](https://huggingface.co/datasets/juliensimon/isro-missions) | ISRO spacecraft, launchers, customer satellites, and research centres | ![ISRO](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['isro']&label=updated&color=brightgreen) | Quarterly | <1 MB |
| [mars-chemcam-compositions](https://huggingface.co/datasets/juliensimon/mars-chemcam-compositions) | 30K+ Mars rock/soil oxide compositions from Curiosity ChemCam LIBS | — | Static | 1 MB |
| [mars-perseverance-weather](https://huggingface.co/datasets/juliensimon/mars-perseverance-weather) | Mars surface weather from Perseverance MEDA (temperature, pressure, wind, UV) | ![MEDA](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['meda-weather']&label=updated&color=brightgreen) | Monthly | ~100 MB |
| [nasa-eva-chronology](https://huggingface.co/datasets/juliensimon/nasa-eva-chronology) | 375 spacewalks (EVAs) — complete history from Gemini to ISS | — | Static | <1 MB |
| [nasa-mars-rover-images](https://huggingface.co/datasets/juliensimon/nasa-mars-rover-images) | 400K+ image metadata from Perseverance and Curiosity rovers (sol, camera, position, URLs) | ![Mars Rovers](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['mars-rovers']&label=updated&color=brightgreen) | Weekly | ~50 MB |
| [nasa-maven-kp-insitu](https://huggingface.co/datasets/juliensimon/nasa-maven-kp-insitu) | MAVEN Mars atmosphere key parameters: solar wind, magnetic field, ion composition at 4-8s cadence | ![MAVEN](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['maven']&label=updated&color=brightgreen) | Quarterly | ~500 MB |
| [pds-planetary-missions](https://huggingface.co/datasets/juliensimon/pds-planetary-missions) | NASA PDS mission catalog — 98 missions, 115 spacecraft, 748 instruments with targets and cross-references | — | Static | <5 MB |
| [pluto-atmosphere](https://huggingface.co/datasets/juliensimon/pluto-atmosphere) | Pluto atmospheric profiles (temperature, pressure, composition, haze) from New Horizons | — | Static | <1 MB |
| [space-tourism-flights](https://huggingface.co/datasets/juliensimon/space-tourism-flights) | Commercial spaceflight passengers — 85 seats across Virgin Galactic, Blue Origin, SpaceX, Axiom, and Space Adventures (2001–) | ![Space Tourism](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['space-tourism']&label=updated&color=brightgreen) | Quarterly | <1 MB |

### Planetary Science

Explore the surfaces of other worlds through impact crater databases and geochemistry. Features the most comprehensive crater catalogs available — 1.3 million lunar craters, 384K Mars craters, and 44K Ceres craters mapped by the Dawn mission — alongside IAU-approved planetary nomenclature and the Meteoritical Society's record of every known meteorite fall on Earth.

| Dataset | Description | Last Updated | Schedule | Size |
|---------|-------------|-------------|----------|------|
| [ceres-craters-dawn](https://huggingface.co/datasets/juliensimon/ceres-craters-dawn) | 44,594 impact craters on Ceres (>=1 km) from the Dawn Framing Camera | — | Static | 9 MB |
| [impact-craters](https://huggingface.co/datasets/juliensimon/impact-craters) | 4K+ impact craters across the solar system (Earth, Moon, Mars, etc.) from Wikidata | ![Impact Craters](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['impact-craters']&label=updated&color=brightgreen) | Quarterly | <1 MB |
| [lunar-craters-robbins](https://huggingface.co/datasets/juliensimon/lunar-craters-robbins) | 1.3M+ lunar impact craters from the Robbins 2019 database | — | Static | 200 MB |
| [lunar-sample-geochemistry](https://huggingface.co/datasets/juliensimon/lunar-sample-geochemistry) | 58K geochemical analyses of Apollo/Luna/Chang'e 5 lunar samples (Astromat) | — | Static | 1.4 MB |
| [mars-craters-robbins](https://huggingface.co/datasets/juliensimon/mars-craters-robbins) | 384K+ Mars impact craters from the Robbins & Hynek 2012 database | — | Static | 50 MB |
| [mercury-crater-degradation](https://huggingface.co/datasets/juliensimon/mercury-crater-degradation) | 3,253 Mercury craters with degradation classification (Kinczyk et al. 2020) | — | Static | <1 MB |
| [mercury-craters-herrick](https://huggingface.co/datasets/juliensimon/mercury-craters-herrick) | 16,876 Mercury impact craters from MESSENGER imagery (Herrick et al. 2011) | — | Static | <1 MB |
| [meteorite-database](https://huggingface.co/datasets/juliensimon/meteorite-database) | 1,200+ named meteorites with classification, mass, and fall location from Wikidata | ![Meteorites](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['meteorites']&label=updated&color=brightgreen) | Quarterly | <1 MB |
| [meteorite-landings](https://huggingface.co/datasets/juliensimon/meteorite-landings) | 45K+ known meteorite landings with classification and mass | — | Static | 5 MB |
| [planetary-nomenclature](https://huggingface.co/datasets/juliensimon/planetary-nomenclature) | 15K+ IAU-approved named features on Moon, Mars, Venus, and Mercury | — | Static | 5 MB |
| [solar-system-moons](https://huggingface.co/datasets/juliensimon/solar-system-moons) | All 200+ known natural satellites of planets and dwarf planets with orbital and physical parameters | — | Static | <1 MB |

### Space Weather

Monitor the Sun-Earth connection in near real-time. These datasets track solar flares, coronal mass ejections, geomagnetic storms, and the solar wind — the key drivers of space weather that affect satellite operations, GPS accuracy, power grids, and astronaut safety. Includes essential indices for orbit propagation (Kp, Ap, F10.7), 70+ years of sunspot records, and official NOAA alerts. Updated daily from NOAA SWPC, NASA DONKI, WDC Kyoto, and other authoritative sources.

| Dataset | Description | Last Updated | Schedule | Size |
|---------|-------------|-------------|----------|------|
| [auroral-electrojet-index](https://huggingface.co/datasets/juliensimon/auroral-electrojet-index) | Hourly AE/AU/AL/AO auroral electrojet indices from Kyoto WDC | ![AE](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['ae-index']&label=updated&color=brightgreen) | Daily | 2 MB |
| [celestrak-space-weather](https://huggingface.co/datasets/juliensimon/celestrak-space-weather) | Consolidated space weather data for orbit propagation (Kp, Ap, F10.7) | ![CelesTrak SW](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['celestrak-sw']&label=updated&color=brightgreen) | Daily | 5 MB |
| [donki-space-weather-events](https://huggingface.co/datasets/juliensimon/donki-space-weather-events) | 12K+ coronal mass ejections, geomagnetic storms, and solar particle events (2010+) | ![DONKI](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.donki&label=updated&color=brightgreen) | Daily | 1.0 MB |
| [dst-index](https://huggingface.co/datasets/juliensimon/dst-index) | 600K+ hourly geomagnetic storm intensity readings since 1957 (Dst index) | ![Dst](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['dst-index']&label=updated&color=brightgreen) | Daily | 1.7 MB |
| [f107-solar-flux](https://huggingface.co/datasets/juliensimon/f107-solar-flux) | Daily F10.7 cm solar radio flux since 1947 — primary proxy for atmospheric drag | ![F10.7](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.f107&label=updated&color=brightgreen) | Daily | 2 MB |
| [forbush-decreases](https://huggingface.co/datasets/juliensimon/forbush-decreases) | 7,097 Forbush decrease events (1957-2016) with solar wind, IMF, and CME parameters from IZMIRAN | — | Static | <1 MB |
| [geomagnetic-kp-index](https://huggingface.co/datasets/juliensimon/geomagnetic-kp-index) | 3-hourly geomagnetic disturbance index (Kp 0-9) with NOAA storm scale | ![Kp](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['kp-index']&label=updated&color=brightgreen) | Daily | 4 KB |
| [iers-earth-orientation](https://huggingface.co/datasets/juliensimon/iers-earth-orientation) | Daily Earth orientation parameters (polar motion, UT1-UTC, LOD) since 1973 | ![IERS](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['iers-eop']&label=updated&color=brightgreen) | Daily | 5 MB |
| [neutron-monitor-cosmic-rays](https://huggingface.co/datasets/juliensimon/neutron-monitor-cosmic-rays) | Hourly cosmic ray intensity from the global neutron monitor network | ![Neutron](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['neutron-monitor']&label=updated&color=brightgreen) | Daily | <1 MB |
| [omni-solar-wind-parameters](https://huggingface.co/datasets/juliensimon/omni-solar-wind-parameters) | 561K+ hourly solar wind parameters (velocity, density, IMF) from NASA OMNI | ![OMNI](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.omni&label=updated&color=brightgreen) | Daily | 20 MB |
| [silso-sunspot-number](https://huggingface.co/datasets/juliensimon/silso-sunspot-number) | 120K+ daily sunspot numbers since 1818 from SILSO/Royal Observatory of Belgium | ![Sunspot](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.sunspot&label=updated&color=brightgreen) | Monthly | 3 MB |
| [solar-flare-events](https://huggingface.co/datasets/juliensimon/solar-flare-events) | 16K+ individual solar flare detections from GOES X-ray sensors (2017+) | ![Solar Flares](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['solar-flares']&label=updated&color=brightgreen) | Daily | 0.5 MB |
| [solar-proton-events](https://huggingface.co/datasets/juliensimon/solar-proton-events) | Solar proton events (SPEs) affecting the Earth environment from 1976 to present | — | Static | <1 MB |
| [solar-radio-bursts](https://huggingface.co/datasets/juliensimon/solar-radio-bursts) | Solar radio burst events (Type II/III/IV/V) from HEASARC | ![Solar Radio](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['solar-radio']&label=updated&color=brightgreen) | Weekly | 5 MB |
| [solar-wind](https://huggingface.co/datasets/juliensimon/solar-wind) | Real-time solar wind speed, density, temperature, and magnetic field from L1 | ![Solar Wind](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['solar-wind']&label=updated&color=brightgreen) | Daily | 0.2 MB |
| [space-weather-indices](https://huggingface.co/datasets/juliensimon/space-weather-indices) | Daily Kp, Ap, F10.7 solar and geomagnetic indices since 1957 | ![Space Weather](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['space-weather']&label=updated&color=brightgreen) | Daily | 0.8 MB |
| [substorm-onsets](https://huggingface.co/datasets/juliensimon/substorm-onsets) | 253K+ magnetospheric substorm onsets from 5 detection algorithms (SuperMAG) | ![Substorms](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['substorm-onsets']&label=updated&color=brightgreen) | Quarterly | 3 MB |
| [swpc-alerts](https://huggingface.co/datasets/juliensimon/swpc-alerts) | Official NOAA space weather alerts, watches, and warnings | ![SWPC](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['swpc-alerts']&label=updated&color=brightgreen) | Daily | 2 MB |

### Astronomy & Reference

A broad survey of the observable universe — from exoplanets in our galactic neighborhood to quasars at the edge of the cosmos. Covers confirmed exoplanets from NASA, gravitational wave detections from LIGO/Virgo/KAGRA, gamma-ray bursts, fast radio bursts from CHIME, pulsars, variable stars, galaxy clusters, and million-source radio and X-ray sky surveys. These datasets support multi-messenger astronomy, cross-matching across wavelengths, and large-scale statistical studies of astrophysical populations.

| Dataset | Description | Last Updated | Schedule | Size |
|---------|-------------|-------------|----------|------|
| [4xmm-dr14-xray-sources](https://huggingface.co/datasets/juliensimon/4xmm-dr14-xray-sources) | 630K+ unique X-ray sources from ESA XMM-Newton serendipitous survey (4XMM) | — | Static | ~80 MB |
| [aavso-vsx-variable-stars](https://huggingface.co/datasets/juliensimon/aavso-vsx-variable-stars) | 1.5M+ variable stars from the AAVSO Variable Star Index (VSX) with types, periods, and magnitudes | — | Static | ~100 MB |
| [apogee-dr17](https://huggingface.co/datasets/juliensimon/apogee-dr17) | APOGEE DR17 stellar parameters and abundances from high-resolution infrared spectroscopy | — | Static | ~50 MB |
| [astronaut-database](https://huggingface.co/datasets/juliensimon/astronaut-database) | Every person who has been to space — 560+ astronauts/cosmonauts | ![Astronauts](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['astronauts']&label=updated&color=brightgreen) | Monthly | <1 MB |
| [astronomer-database](https://huggingface.co/datasets/juliensimon/astronomer-database) | 11K+ astronomers with affiliations, awards, and fields of work from Wikidata | ![Astronomers](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['astronomers']&label=updated&color=brightgreen) | Quarterly | <1 MB |
| [black-hole-catalog](https://huggingface.co/datasets/juliensimon/black-hole-catalog) | Known black hole systems and X-ray binaries from SIMBAD | ![BH](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['black-holes']&label=updated&color=brightgreen) | Weekly | 90 KB |
| [bright-star-catalog](https://huggingface.co/datasets/juliensimon/bright-star-catalog) | 9,110 naked-eye stars from the Bright Star Catalogue (BSC5, 5th Revised Edition) | — | Static | ~1 MB |
| [brown-dwarf-catalog](https://huggingface.co/datasets/juliensimon/brown-dwarf-catalog) | 14K ultracool and brown dwarfs within 40 pc | — | Static | 10 MB |
| [carbon-stars](https://huggingface.co/datasets/juliensimon/carbon-stars) | 6,000+ Galactic carbon stars from the General Catalogue of Cool Carbon Stars (GCCS) | — | Static | <1 MB |
| [cataclysmic-variable-catalog](https://huggingface.co/datasets/juliensimon/cataclysmic-variable-catalog) | 2,000+ cataclysmic variables — dwarf novae, polars, and classical novae | ![CVs](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['cataclysmic-variables']&label=updated&color=brightgreen) | Quarterly | <1 MB |
| [chandra-x-ray-sources](https://huggingface.co/datasets/juliensimon/chandra-x-ray-sources) | 28K X-ray sources from the Chandra Source Catalog (CSC 2.1) | — | Static | 1.8 MB |
| [chime-frb-catalog](https://huggingface.co/datasets/juliensimon/chime-frb-catalog) | 4,500+ fast radio bursts from the CHIME/FRB telescope | ![CHIME](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['chime-frb']&label=updated&color=brightgreen) | Semi-annual | 5 MB |
| [cns5-nearby-stars](https://huggingface.co/datasets/juliensimon/cns5-nearby-stars) | Catalogue of Nearby Stars within 25 parsecs (CNS5) with astrometry and photometry | — | Static | <1 MB |
| [constellation-catalog](https://huggingface.co/datasets/juliensimon/constellation-catalog) | 94 IAU constellations with abbreviations, areas, and brightest stars from Wikidata | ![Constellations](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['constellations']&label=updated&color=brightgreen) | Quarterly | <1 MB |
| [cosmic-void-catalog](https://huggingface.co/datasets/juliensimon/cosmic-void-catalog) | 1,000+ cosmic voids from SDSS DR7 (Pan et al. 2012) | ![Voids](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['cosmic-voids']&label=updated&color=brightgreen) | Semi-annual | <1 MB |
| [cosmicflows-galaxy-distances](https://huggingface.co/datasets/juliensimon/cosmicflows-galaxy-distances) | 56K galaxy distances from Cosmicflows-4 (8 distance methods) | — | Static | 3.7 MB |
| [desi-dr1-redshifts](https://huggingface.co/datasets/juliensimon/desi-dr1-redshifts) | 1M+ spectroscopic redshifts from the DESI Data Release 1 Bright Galaxy Survey | — | Static | ~100 MB |
| [erosita-erass1-xray](https://huggingface.co/datasets/juliensimon/erosita-erass1-xray) | 900K X-ray sources from the first eROSITA All-Sky Survey (eRASS1) | ![eROSITA](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.erosita&label=updated&color=brightgreen) | Per release | 500 MB |
| [euve-observations](https://huggingface.co/datasets/juliensimon/euve-observations) | 1,367 EUVE extreme-UV observations (1992–2001) — the only EUV space mission ever flown (70–760 Å) | ![EUVE](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.euve&label=updated&color=brightgreen) | Quarterly | <1 MB |
| [fermi-4fgl-dr4](https://huggingface.co/datasets/juliensimon/fermi-4fgl-dr4) | 7K gamma-ray sources from Fermi LAT 14-year all-sky survey | ![Fermi](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['fermi-4fgl']&label=updated&color=brightgreen) | Annual | 50 MB |
| [first-radio-catalog](https://huggingface.co/datasets/juliensimon/first-radio-catalog) | 946K radio sources from the VLA FIRST Survey at 1.4 GHz (5" resolution) | — | Static | 113 MB |
| [fuse-observations](https://huggingface.co/datasets/juliensimon/fuse-observations) | 5,729 FUSE far-UV spectra (1999–2007) — highest-resolution 905–1187 Å spectrograph ever flown | ![FUSE](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.fuse&label=updated&color=brightgreen) | Quarterly | <1 MB |
| [gaia-dr3-binary-masses](https://huggingface.co/datasets/juliensimon/gaia-dr3-binary-masses) | 195K binary star component masses (m1, m2) from Gaia DR3 astrometric+spectroscopic solutions | — | Static | ~5 MB |
| [gaia-dr3-cepheids](https://huggingface.co/datasets/juliensimon/gaia-dr3-cepheids) | Gaia DR3 Cepheid variable stars with pulsation periods, multi-band photometry, and parallaxes | — | Static | ~10 MB |
| [gaia-dr3-chemical-cartography](https://huggingface.co/datasets/juliensimon/gaia-dr3-chemical-cartography) | 5.6M stars with Galactic orbital actions, kinematics, and energy from Gaia DR3 | — | Static | ~3 GB |
| [gaia-dr3-compact-companions](https://huggingface.co/datasets/juliensimon/gaia-dr3-compact-companions) | 6K candidates for stars orbiting compact objects (black holes/neutron stars) identified via Gaia DR3 ellipsoidal variability | — | Static | ~1 MB |
| [gaia-dr3-eclipsing-binaries](https://huggingface.co/datasets/juliensimon/gaia-dr3-eclipsing-binaries) | Gaia DR3 eclipsing binary candidates with orbital periods and light-curve parameters | — | Static | ~20 MB |
| [gaia-dr3-long-period-variables](https://huggingface.co/datasets/juliensimon/gaia-dr3-long-period-variables) | 1.7M Mira and semi-regular variable stars (LPVs) from Gaia DR3 including carbon star classification | — | Static | ~50 MB |
| [gaia-dr3-qso-candidates](https://huggingface.co/datasets/juliensimon/gaia-dr3-qso-candidates) | 6.6M quasar/AGN candidates with DSC classifier probabilities and photometric redshifts from Gaia DR3 | — | Static | ~2 GB |
| [gaia-dr3-rotation-modulation](https://huggingface.co/datasets/juliensimon/gaia-dr3-rotation-modulation) | 84K stellar rotation periods from Gaia DR3 photometric modulation with starspot activity indices | — | Static | ~9 MB |
| [gaia-dr3-rrlyrae](https://huggingface.co/datasets/juliensimon/gaia-dr3-rrlyrae) | 272K RR Lyrae pulsating stars from Gaia DR3 — distance ladder | — | Static | 50 MB |
| [gaia-dr3-solar-system-objects](https://huggingface.co/datasets/juliensimon/gaia-dr3-solar-system-objects) | 158K solar system objects (asteroids, comets) observed by Gaia DR3 with minor planet numbers and spectra counts | — | Static | ~5 MB |
| [gaia-dr3-spectroscopic-binaries](https://huggingface.co/datasets/juliensimon/gaia-dr3-spectroscopic-binaries) | 180K+ spectroscopic binary star orbital solutions (SB1+SB2) from Gaia DR3 | — | Static | ~20 MB |
| [gaia-dr3-white-dwarfs](https://huggingface.co/datasets/juliensimon/gaia-dr3-white-dwarfs) | 359K white dwarf candidates with atmospheric parameters and masses from Gaia DR3 | — | Static | ~50 MB |
| [gaia-dr3-young-stellar-objects](https://huggingface.co/datasets/juliensimon/gaia-dr3-young-stellar-objects) | 79K+ young stellar object (YSO) candidates with classification scores and variability from Gaia DR3 | — | Static | ~10 MB |
| [galah-dr4-stellar-abundances](https://huggingface.co/datasets/juliensimon/galah-dr4-stellar-abundances) | GALAH DR4 radial velocities, stellar parameters, and elemental abundances for 917K stars | — | Static | ~80 MB |
| [galex-observations](https://huggingface.co/datasets/juliensimon/galex-observations) | 275K GALEX UV survey observations (2003–2013) tagged with survey type (AIS, MIS, DIS, NGS, etc.) | ![GALEX](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.galex&label=updated&color=brightgreen) | Quarterly | ~6 MB |
| [galaxy-clusters](https://huggingface.co/datasets/juliensimon/galaxy-clusters) | 1,650+ galaxy clusters detected by Planck via the Sunyaev-Zeldovich effect | ![Clusters](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['galaxy-clusters']&label=updated&color=brightgreen) | Quarterly | 50 KB |
| [galaxy-zoo-2-morphology](https://huggingface.co/datasets/juliensimon/galaxy-zoo-2-morphology) | 243K citizen-science galaxy morphology classifications with vote fractions and debiased probabilities | — | Static | ~20 MB |
| [gamma-ray-bursts](https://huggingface.co/datasets/juliensimon/gamma-ray-bursts) | 4,200+ gamma-ray bursts from Fermi GBM with duration, flux, and spectral data | ![GRB](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.grb&label=updated&color=brightgreen) | Weekly | 0.3 MB |
| [gcvs-variable-stars](https://huggingface.co/datasets/juliensimon/gcvs-variable-stars) | 58K variable stars from the General Catalogue of Variable Stars | ![GCVS](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.gcvs&label=updated&color=brightgreen) | Quarterly | 15 MB |
| [geneva-copenhagen-stellar-survey](https://huggingface.co/datasets/juliensimon/geneva-copenhagen-stellar-survey) | 16,682 F and G dwarf stars in the solar neighbourhood with ages, metallicities, and kinematics | — | Static | ~5 MB |
| [globular-star-clusters](https://huggingface.co/datasets/juliensimon/globular-star-clusters) | 167 Milky Way globular clusters with masses, structural parameters, and metallicities | — | Static | <1 MB |
| [gravitational-lenses](https://huggingface.co/datasets/juliensimon/gravitational-lenses) | 33K strong gravitational lenses from the lenscat community catalog | — | Static | 0.9 MB |
| [gravitational-wave-events](https://huggingface.co/datasets/juliensimon/gravitational-wave-events) | 260+ black hole and neutron star mergers detected by LIGO/Virgo/KAGRA | ![GW](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['gravitational-waves']&label=updated&color=brightgreen) | Weekly | 30 KB |
| [grbweb-unified-grb-catalog](https://huggingface.co/datasets/juliensimon/grbweb-unified-grb-catalog) | Unified GRB catalog from GRBweb combining Fermi, Swift, BATSE, BeppoSAX, and IPN detectors | — | Static | <1 MB |
| [gswlc-galaxy-properties](https://huggingface.co/datasets/juliensimon/gswlc-galaxy-properties) | 659K galaxies with stellar masses, star formation rates, and dust attenuation from GALEX-SDSS-WISE | — | Static | ~50 MB |
| [hecate-nearby-galaxies](https://huggingface.co/datasets/juliensimon/hecate-nearby-galaxies) | HECATE catalog of nearby galaxies within 200 Mpc with stellar masses, SFR, and morphology | — | Static | ~10 MB |
| [hipparcos-catalog](https://huggingface.co/datasets/juliensimon/hipparcos-catalog) | 118K brightest stars with precise positions and parallaxes from ESA Hipparcos | — | Static | 30 MB |
| [hst-observations](https://huggingface.co/datasets/juliensimon/hst-observations) | 2.6M+ Hubble Space Telescope observations (1990–present) — target, proposal, instrument, detector metadata from MAST | ![HST](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.hst&label=updated&color=brightgreen) | Weekly | ~80 MB |
| [icecube-neutrino-catalog](https://huggingface.co/datasets/juliensimon/icecube-neutrino-catalog) | IceCube neutrino point sources from HEASARC | — | Static | <1 MB |
| [icrf3-reference-frame](https://huggingface.co/datasets/juliensimon/icrf3-reference-frame) | 3,417 ICRF3 extragalactic radio sources — THE celestial reference frame | — | Static | 2 MB |
| [iue-observations](https://huggingface.co/datasets/juliensimon/iue-observations) | 102K IUE UV spectra (1978–1996) — the longest-running UV space observatory, from SWP, LWP, LWR cameras | ![IUE](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.iue&label=updated&color=brightgreen) | Quarterly | ~2 MB |
| [jwst-observations](https://huggingface.co/datasets/juliensimon/jwst-observations) | 960K+ JWST observations from MAST — proposal, target, instrument, timing, and wavelength metadata | ![JWST](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.jwst&label=updated&color=brightgreen) | Weekly | ~150 MB |
| [k2-observations](https://huggingface.co/datasets/juliensimon/k2-observations) | 765K K2 extended-mission observations (2014–2018, campaigns C0–C19) with parsed EPIC ID, campaign, and cadence | ![K2](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['k2-obs']&label=updated&color=brightgreen) | Quarterly | ~20 MB |
| [kepler-eclipsing-binaries](https://huggingface.co/datasets/juliensimon/kepler-eclipsing-binaries) | 2,177 Kepler eclipsing binary stars | — | Static | 1 MB |
| [kepler-observations](https://huggingface.co/datasets/juliensimon/kepler-observations) | 213K Kepler prime-mission observations (2009–2013) with KIC ID, cadence, and per-quarter observation mask | ![Kepler](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['kepler-obs']&label=updated&color=brightgreen) | Quarterly | ~5 MB |
| [kepler-transit-timing](https://huggingface.co/datasets/juliensimon/kepler-transit-timing) | 295K transit times for 2,599 KOIs with O-C residuals, durations, and depths (Holczer+ 2016) | — | Static | ~5 MB |
| [lunar-eclipse-catalog](https://huggingface.co/datasets/juliensimon/lunar-eclipse-catalog) | 12,064 lunar eclipses spanning 5 millennia (-1999 to +3000) from NASA — companion to solar-eclipse-catalog | — | Static | <1 MB |
| [mcgill-magnetar-catalog](https://huggingface.co/datasets/juliensimon/mcgill-magnetar-catalog) | All known magnetars with spin parameters, magnetic field strengths, and X-ray properties | — | Static | <1 MB |
| [messier-catalog](https://huggingface.co/datasets/juliensimon/messier-catalog) | The classic Messier catalog — 110 galaxies, nebulae, and star clusters | ![Messier](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.messier&label=updated&color=brightgreen) | Quarterly | 10 KB |
| [milliquas](https://huggingface.co/datasets/juliensimon/milliquas) | Milliquas v8 — the Million Quasars Catalog with positions, redshifts, and radio/X-ray associations | — | Static | ~100 MB |
| [nasa-apod](https://huggingface.co/datasets/juliensimon/nasa-apod) | 11K+ NASA Astronomy Picture of the Day entries since 1995 — images, videos, and ~2M words of expert astronomy prose | ![APOD](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.apod&label=updated&color=brightgreen) | Daily | ~5 MB |
| [nasa-exoplanets](https://huggingface.co/datasets/juliensimon/nasa-exoplanets) | 6,150 confirmed exoplanets with orbital, stellar, and discovery parameters | ![Exoplanets](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.exoplanets&label=updated&color=brightgreen) | Weekly | 0.5 MB |
| [nebula-catalog](https://huggingface.co/datasets/juliensimon/nebula-catalog) | 60K+ nebulae (emission, reflection, dark, planetary) with coordinates and distances from Wikidata | ![Nebulae](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['nebulae']&label=updated&color=brightgreen) | Quarterly | 1.7 MB |
| [ngc-ic-catalog](https://huggingface.co/datasets/juliensimon/ngc-ic-catalog) | 14K deep-sky objects — galaxies, nebulae, and star clusters (NGC + IC) | ![NGC](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['ngc-ic']&label=updated&color=brightgreen) | Monthly | 0.5 MB |
| [nvss-radio-catalog](https://huggingface.co/datasets/juliensimon/nvss-radio-catalog) | 1.77M radio sources from the NRAO VLA Sky Survey at 1.4 GHz | — | Static | 150 MB |
| [observatory-database](https://huggingface.co/datasets/juliensimon/observatory-database) | 640+ ground and space observatories with locations, apertures, and wavelengths from Wikidata | ![Observatories](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['observatories']&label=updated&color=brightgreen) | Quarterly | <1 MB |
| [open-star-clusters](https://huggingface.co/datasets/juliensimon/open-star-clusters) | 7,167 Gaia-era open star clusters with distances and ages | — | Static | 5 MB |
| [open-supernova-catalog](https://huggingface.co/datasets/juliensimon/open-supernova-catalog) | 72K supernovae with light curves, spectra references, and host galaxies | ![Supernovae](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.supernovae&label=updated&color=brightgreen) | Weekly | 10 MB |
| [otter-tde-catalog](https://huggingface.co/datasets/juliensimon/otter-tde-catalog) | Tidal disruption events (TDEs) from the Open TDE Catalog — stars torn apart by black holes | — | Static | <1 MB |
| [pantheon-plus-sne-ia](https://huggingface.co/datasets/juliensimon/pantheon-plus-sne-ia) | 1,550 Type Ia supernovae — gold standard cosmological distance dataset | — | Static | 10 MB |
| [planck-cold-clumps](https://huggingface.co/datasets/juliensimon/planck-cold-clumps) | 13K+ Galactic cold clumps — pre-stellar cores and star-forming regions from Planck | — | Static | <1 MB |
| [planck-sz2-clusters](https://huggingface.co/datasets/juliensimon/planck-sz2-clusters) | 1,650+ galaxy clusters from Planck SZ2 catalog with mass and redshift | ![Planck SZ2](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['planck-sz2']&label=updated&color=brightgreen) | Semi-annual | <1 MB |
| [planetary-nebulae](https://huggingface.co/datasets/juliensimon/planetary-nebulae) | 1,715 planetary nebulae from MUSE survey | — | Static | <1 MB |
| [pulsar-catalog](https://huggingface.co/datasets/juliensimon/pulsar-catalog) | 4,300+ pulsars with spin period, dispersion measure, and magnetic field | ![Pulsars](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.pulsars&label=updated&color=brightgreen) | Monthly | 0.2 MB |
| [pulsar-glitch-catalog](https://huggingface.co/datasets/juliensimon/pulsar-glitch-catalog) | 700+ pulsar glitch events from the Jodrell Bank Glitch Catalogue | ![Glitches](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['pulsar-glitches']&label=updated&color=brightgreen) | Quarterly | <1 MB |
| [quasar-catalog](https://huggingface.co/datasets/juliensimon/quasar-catalog) | 50K quasars, Seyfert galaxies, blazars, and active galactic nuclei | ![QSO](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.quasars&label=updated&color=brightgreen) | Weekly | 1.3 MB |
| [rave-dr6](https://huggingface.co/datasets/juliensimon/rave-dr6) | RAVE DR6 stellar radial velocities, parameters, and elemental abundances for 518K spectra | — | Static | ~30 MB |
| [rc3-galaxy-morphology](https://huggingface.co/datasets/juliensimon/rc3-galaxy-morphology) | 23K bright galaxies with Hubble morphological types from RC3 | — | Static | 10 MB |
| [roma-bzcat-blazars](https://huggingface.co/datasets/juliensimon/roma-bzcat-blazars) | 3,561 confirmed blazars (BL Lac + FSRQ) from Roma-BZCAT 5th edition | — | Static | <1 MB |
| [solar-eclipse-catalog](https://huggingface.co/datasets/juliensimon/solar-eclipse-catalog) | 12,000+ solar eclipses spanning 5 millennia (-1999 to +3000) from NASA | — | Static | <1 MB |
| [stackexchange-space-qa](https://huggingface.co/datasets/juliensimon/stackexchange-space-qa) | 33K Q&A pairs from Astronomy + Space Exploration Stack Exchange sites — top-scored/accepted answers, CC-BY-SA 4.0 | ![SE Space Q&A](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['stackexchange-space']&label=updated&color=brightgreen) | Annually | ~50 MB |
| [sumss-radio-catalog](https://huggingface.co/datasets/juliensimon/sumss-radio-catalog) | 211K southern radio sources at 843 MHz from SUMSS | — | Static | 30 MB |
| [supernova-remnants](https://huggingface.co/datasets/juliensimon/supernova-remnants) | 310 Galactic supernova remnants with radio flux and spectral index | ![SNR](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.snr&label=updated&color=brightgreen) | Quarterly | 10 KB |
| [tess-toi-candidates](https://huggingface.co/datasets/juliensimon/tess-toi-candidates) | 7K+ TESS Objects of Interest — active exoplanet candidates | ![TESS](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['tess-toi']&label=updated&color=brightgreen) | Weekly | 5 MB |
| [tgss-radio-catalog](https://huggingface.co/datasets/juliensimon/tgss-radio-catalog) | 624K radio sources at 150 MHz from GMRT TGSS ADR1 | — | Static | 80 MB |
| [unified-radio-catalog](https://huggingface.co/datasets/juliensimon/unified-radio-catalog) | SPECFIND v3 unified radio source catalog cross-matching 50+ radio surveys | — | Static | ~100 MB |
| [vlass-radio-sources](https://huggingface.co/datasets/juliensimon/vlass-radio-sources) | 3.4M radio sources from VLA Sky Survey Epoch 1 (VLASS) at 3 GHz | — | Static | 681 MB |
| [wds-double-stars](https://huggingface.co/datasets/juliensimon/wds-double-stars) | 157K visual double star systems from the Washington Double Star Catalog | ![WDS](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.wds&label=updated&color=brightgreen) | Weekly | 50 MB |
| [wise-hii-regions](https://huggingface.co/datasets/juliensimon/wise-hii-regions) | 8,000+ Galactic HII regions from WISE mid-infrared survey (Anderson+ 2014) | ![HII](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['hii-regions']&label=updated&color=brightgreen) | Quarterly | <1 MB |
| [wolf-rayet-stars](https://huggingface.co/datasets/juliensimon/wolf-rayet-stars) | 383 Galactic Wolf-Rayet stars with Gaia DR2 distances and spectral types | — | Static | <1 MB |
| [xray-binary-catalog](https://huggingface.co/datasets/juliensimon/xray-binary-catalog) | 500+ high-mass and low-mass X-ray binaries (Liu et al. 2006/2007) | ![XRBs](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['xray-binaries']&label=updated&color=brightgreen) | Quarterly | <1 MB |

### Physics

Fundamental particle properties and high-energy astrophysics catalogs. Includes the Particle Data Group's authoritative summary of every known particle, cosmic ray energy spectra from 131 experiments, ultra-high-energy events from the Pierre Auger Observatory, and gamma-ray source catalogs spanning MeV to PeV energies from Fermi, Swift, INTEGRAL, HAWC, and LHAASO. Essential for particle physics, astroparticle research, and multi-wavelength source identification.

| Dataset | Description | Last Updated | Schedule | Size |
|---------|-------------|-------------|----------|------|
| [auger-cosmic-rays](https://huggingface.co/datasets/juliensimon/auger-cosmic-rays) | Ultra-high-energy cosmic ray events from Pierre Auger Observatory | — | Static | 100 MB |
| [crdb-cosmic-ray-spectra](https://huggingface.co/datasets/juliensimon/crdb-cosmic-ray-spectra) | 316K cosmic ray measurements from 131 experiments | ![CRDB](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.crdb&label=updated&color=brightgreen) | Quarterly | 50 MB |
| [fermi-3fhl-hard-gamma-ray](https://huggingface.co/datasets/juliensimon/fermi-3fhl-hard-gamma-ray) | 1,558 hard gamma-ray sources (>10 GeV) from Fermi LAT 3FHL | — | Static | 0.6 MB |
| [fermi-3pc-gamma-ray-pulsars](https://huggingface.co/datasets/juliensimon/fermi-3pc-gamma-ray-pulsars) | 7K+ gamma-ray pulsars from Fermi LAT Third Pulsar Catalog (3PC) | — | Static | 2.2 MB |
| [fermi-4lac-agn-catalog](https://huggingface.co/datasets/juliensimon/fermi-4lac-agn-catalog) | 3,409 gamma-ray AGN from Fermi LAT Fourth AGN Catalog (4LAC) | — | Static | 0.7 MB |
| [fermi-gbm-triggers](https://huggingface.co/datasets/juliensimon/fermi-gbm-triggers) | 12.5K+ Fermi GBM triggers — all triggers, not just confirmed GRBs | ![GBM](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['fermi-gbm-triggers']&label=updated&color=brightgreen) | Daily | 1.8 MB |
| [hawc-tev-gamma-ray](https://huggingface.co/datasets/juliensimon/hawc-tev-gamma-ray) | 65 TeV gamma-ray sources from the 3HWC HAWC catalog | — | Static | <1 MB |
| [icecat-neutrino-alerts](https://huggingface.co/datasets/juliensimon/icecat-neutrino-alerts) | High-energy neutrino alert events from the IceCube Neutrino Observatory (ICECAT-1) | — | Static | <1 MB |
| [integral-ibis-hard-xray](https://huggingface.co/datasets/juliensimon/integral-ibis-hard-xray) | 929 hard X-ray sources from INTEGRAL IBIS 17-year survey (17-290 keV) | — | Static | 0.3 MB |
| [lhaaso-gamma-ray-sources](https://huggingface.co/datasets/juliensimon/lhaaso-gamma-ray-sources) | 180 ultra-high-energy gamma-ray sources from 1LHAASO (2024) | — | Static | <1 MB |
| [pdg-particle-properties](https://huggingface.co/datasets/juliensimon/pdg-particle-properties) | Every known particle from the Particle Data Group | ![PDG](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$.pdg&label=updated&color=brightgreen) | Annual | 50 MB |
| [physics-nobel-laureates](https://huggingface.co/datasets/juliensimon/physics-nobel-laureates) | 229 Physics Nobel Prize laureates with institutions and cited work from Wikidata | ![Nobel](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['physics-nobel']&label=updated&color=brightgreen) | Quarterly | <1 MB |
| [swift-bat-hard-xray-survey](https://huggingface.co/datasets/juliensimon/swift-bat-hard-xray-survey) | 1,893 hard X-ray sources (14-195 keV) from Swift-BAT 157-month survey | — | Static | 0.3 MB |
| [tevcat-tev-gamma-ray](https://huggingface.co/datasets/juliensimon/tevcat-tev-gamma-ray) | 322 TeV gamma-ray sources — THE ground-based VHE reference catalog | — | Static | <1 MB |

## Collections on Hugging Face

- [Orbital Mechanics](https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994) — satellites, TLEs, launches, NEOs, asteroids, impact risk
- [Space Probes & Missions](https://huggingface.co/collections/juliensimon/space-probe-and-mission-datasets-69c3fe82d410a42b1e313167) — Voyager, Pioneer, Cassini, Mars Express, Rosetta, Curiosity, Perseverance, EVAs
- [Planetary Science](https://huggingface.co/collections/juliensimon/planetary-science-datasets-69c2d4683bd6a66c34fb4af2) — lunar craters, Mars craters, Mars geochemistry, meteorites
- [Space Weather](https://huggingface.co/collections/juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70) — solar flares, CMEs, geomagnetic storms, solar wind, Kp/Ap/F10.7 indices
- [Astronomy](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) — exoplanets, pulsars, radio surveys, X-ray catalogs, variable stars, gravitational waves, galaxy morphology
- [Physics](https://huggingface.co/collections/juliensimon/physics-datasets-69c2d4682d37dfdb77447bd7) — particle properties, cosmic ray spectra, hard X-ray surveys, gamma-ray catalogs (TeV/UHE)
- [Solar System](https://huggingface.co/collections/juliensimon/solar-system-datasets-69c6fa681978de62dff2f347) — planetary missions, craters (Moon/Mars/Ceres/Mercury), atmospheric profiles (Jupiter/Titan), named features
- [Space Essentials](https://huggingface.co/collections/juliensimon/space-essentials-69cbafd7ea046a10eff11405) — astronauts, space missions, meteorites, constellations, Nobel laureates. No jargon, just names, dates, and places

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
python scripts/update-asterank.py
python scripts/update-bus-demeo.py
python scripts/update-comets.py
python scripts/update-constellation-census.py
python scripts/update-constellation-tles.py
python scripts/update-fireballs.py
python scripts/update-fragmentation-events.py
python scripts/update-gcat.py
python scripts/update-gcat-satcat.py
python scripts/update-gmn-meteors.py
python scripts/update-ground-stations.py
python scripts/update-launch-cost.py
python scripts/update-launch-log.py
python scripts/update-launch-vehicles.py
python scripts/update-lcdb.py
python scripts/update-meteor-showers.py
python scripts/update-meteorite-landings.py
python scripts/update-mpc-comets.py
python scripts/update-neo.py
python scripts/update-neowise.py
python scripts/update-nesvorny-families.py
python scripts/update-nhats.py
python scripts/update-reentry-events.py
python scripts/update-satcat.py
python scripts/update-satnogs.py
python scripts/update-sbdb.py
python scripts/update-sdss-taxonomy.py
python scripts/update-sentry.py
python scripts/update-space-agencies.py
python scripts/update-space-missions.py
python scripts/update-spacecraft.py
python scripts/update-spacex-launches.py
python scripts/update-ssodnet.py
python scripts/update-starlink.py
SPACETRACK_USER=xxx SPACETRACK_PASS=xxx python scripts/update-tle-history.py
python scripts/update-tle-latest.py
python scripts/update-tno-centaur.py
python scripts/update-ucs.py  # requires: pip install openpyxl
python scripts/update-wmo-oscar.py

# Planetary Science
python scripts/update-ceres-craters.py
python scripts/update-impact-craters.py
python scripts/update-lunar-craters.py
python scripts/update-lunar-eclipses.py
python scripts/update-lunar-geochemistry.py
python scripts/update-mars-craters.py
python scripts/update-mercury-craters.py
python scripts/update-mercury-degradation.py
python scripts/update-meteorites.py
python scripts/update-planetary-nomenclature.py
python scripts/update-pluto-atmosphere.py
pip install beautifulsoup4 lxml && python scripts/update-solar-system-moons.py

# Space Weather
python scripts/update-ae-index.py
python scripts/update-celestrak-sw.py
python scripts/update-donki.py
python scripts/update-dst-index.py
python scripts/update-f107.py
python scripts/update-forbush-decreases.py
python scripts/update-iers-eop.py
python scripts/update-kp-index.py
python scripts/update-neutron-monitor.py
python scripts/update-omni.py
python scripts/update-solar-eclipses.py
pip install netCDF4 && python scripts/update-solar-flares.py
pip install beautifulsoup4 lxml && python scripts/update-solar-proton-events.py
python scripts/update-solar-radio.py
python scripts/update-solar-wind.py
python scripts/update-space-weather.py
python scripts/update-substorm-onsets.py
python scripts/update-sunspot.py
python scripts/update-swpc-alerts.py

# Space Probes & Missions
python scripts/update-artemis-ii.py
python scripts/update-astronauts.py
python scripts/update-bepicolombo.py
python scripts/update-cassini.py
python scripts/update-chemcam.py
python scripts/update-deep-space-probes.py
python scripts/update-eva.py
python scripts/update-exomars-tgo.py
python scripts/update-galileo-atmosphere.py
python scripts/update-gcat-deep-space.py
python scripts/update-huygens.py
python scripts/update-huygens-atmosphere.py
python scripts/update-insight-marsquakes.py
python scripts/update-isro.py
python scripts/update-juice.py
python scripts/update-mars-express.py
python scripts/update-mars-rovers.py
python scripts/update-maven.py
python scripts/update-meda-weather.py
python scripts/update-pds-missions.py
python scripts/update-rosetta.py
python scripts/update-space-tourism.py
python scripts/update-venus-express.py

# Astronomy
python scripts/update-4xmm-dr14.py
python scripts/update-aavso-vsx.py
python scripts/update-apod.py
python scripts/update-apogee-dr17.py
python scripts/update-astronomers.py
python scripts/update-black-holes.py
python scripts/update-bright-stars.py
python scripts/update-brown-dwarfs.py
python scripts/update-carbon-stars.py
python scripts/update-cataclysmic-variables.py
python scripts/update-chandra.py
python scripts/update-chime-frb.py
python scripts/update-cns5.py
python scripts/update-constellations.py
python scripts/update-cosmic-voids.py
python scripts/update-cosmicflows.py
python scripts/update-desi.py
python scripts/update-erosita.py
python scripts/update-euve.py
python scripts/update-exoplanets.py
pip install astropy && python scripts/update-fermi-4fgl.py
python scripts/update-first.py
python scripts/update-fuse.py
python scripts/update-gaia-binary-masses.py
python scripts/update-gaia-cepheids.py
python scripts/update-gaia-chemical-cartography.py
python scripts/update-gaia-compact-companions.py
python scripts/update-gaia-eb.py
python scripts/update-gaia-lrv.py
python scripts/update-gaia-qso.py
python scripts/update-gaia-rotation.py
python scripts/update-gaia-rrlyrae.py
python scripts/update-gaia-sb.py
python scripts/update-gaia-sso.py
python scripts/update-gaia-wd.py
python scripts/update-gaia-yso.py
pip install astropy && python scripts/update-galah.py
python scripts/update-galex.py
python scripts/update-galaxy-clusters.py
python scripts/update-galaxy-zoo.py
python scripts/update-gcvs.py
python scripts/update-geneva-copenhagen.py
python scripts/update-globular-clusters.py
python scripts/update-gravitational-lenses.py
python scripts/update-gravitational-waves.py
python scripts/update-grb.py
python scripts/update-grbweb.py
python scripts/update-gswlc.py
python scripts/update-hecate.py
python scripts/update-hst.py
python scripts/update-hii-regions.py
python scripts/update-hipparcos.py
python scripts/update-icecube.py
python scripts/update-icrf3.py
python scripts/update-iue.py
python scripts/update-jwst.py
python scripts/update-k2-obs.py
python scripts/update-kepler-eb.py
python scripts/update-kepler-obs.py
python scripts/update-kepler-ttv.py
python scripts/update-magnetars.py
python scripts/update-messier.py
python scripts/update-milliquas.py
python scripts/update-nebulae.py
python scripts/update-ngc-ic.py
python scripts/update-nvss.py
python scripts/update-observatories.py
python scripts/update-open-clusters.py
python scripts/update-otter-tde.py
python scripts/update-pantheon.py
python scripts/update-planck-pgcc.py
python scripts/update-planck-sz2.py
python scripts/update-planetary-nebulae.py
pip install beautifulsoup4 lxml && python scripts/update-pulsar-glitches.py
python scripts/update-pulsars.py
python scripts/update-quasars.py
python scripts/update-rave-dr6.py
python scripts/update-rc3.py
python scripts/update-roma-bzcat.py
python scripts/update-snr.py
python scripts/update-stackexchange-space.py
python scripts/update-sumss.py
python scripts/update-supernovae.py
python scripts/update-tess-toi.py
python scripts/update-tgss.py
python scripts/update-unified-radio.py
python scripts/update-vlass.py
python scripts/update-wds.py
python scripts/update-wolf-rayet.py
python scripts/update-xray-binaries.py

# Physics
python scripts/update-auger.py
pip install crdb && python scripts/update-crdb.py
python scripts/update-fermi-3fhl.py
python scripts/update-fermi-3pc.py
python scripts/update-fermi-4lac.py
python scripts/update-fermi-gbm-triggers.py
python scripts/update-hawc.py
python scripts/update-icecat.py
python scripts/update-integral-ibis.py
python scripts/update-lhaaso.py
pip install particle && python scripts/update-pdg.py
python scripts/update-physics-nobel.py
python scripts/update-swift-bat.py
python scripts/update-tevcat.py

```

## Bulk ingestion

`build-tle-archive.py` builds historical TLE data from Space-Track yearly bulk zip exports (1959–2025). Daily updates for the current year are automated via `update-tle-history.py` (fetches yesterday's GP history, appends to `tle_{year}.parquet`). Requires `SPACETRACK_USER` and `SPACETRACK_PASS` secrets.

`backfill-tle-history.py` and `backfill-starlink-snapshots.py` are one-time scripts for filling gaps from Space-Track GP history. Not needed for ongoing operation.

## Frequently Asked Questions

### How do I load these datasets in Python?

All datasets are on Hugging Face. Load any dataset in one line:

```python
from datasets import load_dataset
ds = load_dataset("juliensimon/<name>")
```

No API keys needed. Works with pandas, polars, DuckDB, and any Parquet-compatible tool.

### What format are the datasets?

Apache Parquet with zstd compression. Files range from a few KB to several GB.

### How often are datasets updated?

~50 datasets update daily, ~20 weekly, the rest are static snapshots. Each dataset page shows its schedule.

### Can I use these datasets commercially?

Yes. Code is MIT-licensed. Datasets are CC-BY-4.0 (with rare exceptions noted per dataset).

### How do I cite these datasets?

Each dataset page has a BibTeX citation block. See the [Citation](#citation) section below for citing the collection.

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
| Orbital Mechanics | [CelesTrak](https://celestrak.org/) (Dr. T.S. Kelso), [Space-Track.org](https://www.space-track.org/), [GCAT](https://planet4589.org/space/gcat/) (Jonathan McDowell), [Starlink Insider](https://starlinkinsider.com/), [NASA/JPL CNEOS](https://cneos.jpl.nasa.gov/), [NASA/JPL SSD](https://ssd.jpl.nasa.gov/), [NASA NHATS](https://cneos.jpl.nasa.gov/nhats/), [SatNOGS](https://db.satnogs.org/) (Libre Space Foundation), [UCS](https://www.ucsusa.org/resources/satellite-database), [IAU MDC](https://www.ta3.sk/IAUC22DB/MDC2022/), [WMO OSCAR](https://space.oscar.wmo.int/) |
| Space Probes | [NASA SPDF COHOWeb](https://spdf.gsfc.nasa.gov/) (Voyager, Pioneer), [PDS Atmospheres](https://pds-atmospheres.nmsu.edu/) (Cassini, MEDA), [PDS Geosciences](https://pds-geosciences.wustl.edu/) (ChemCam), [ESA PSA](https://psa.esa.int/) (Mars Express, Rosetta, Venus Express), [ISRO](https://www.isro.gov.in/) |
| Planetary Science | [USGS Astrogeology](https://astrogeology.usgs.gov/) (Robbins crater databases), [Meteoritical Society](https://www.lpi.usra.edu/meteor/) (via NASA data.gov) |
| Space Weather | [NOAA SWPC](https://www.swpc.noaa.gov/), [WDC Kyoto](https://wdc.kugi.kyoto-u.ac.jp/dstdir/), [NASA CCMC DONKI](https://ccmc.gsfc.nasa.gov/tools/DONKI/), [NOAA NCEI](https://www.ncei.noaa.gov/) GOES-16 XRS, [SILSO](https://www.sidc.be/SILSO/) (Royal Observatory of Belgium), [LASP LISIRD](https://lasp.colorado.edu/lisird/) (F10.7), [IERS](https://www.iers.org/) |
| Astronomy | [NASA Exoplanet Archive](https://exoplanetarchive.ipac.caltech.edu/), [NASA HEASARC](https://heasarc.gsfc.nasa.gov/) (Fermi, Chandra, Swift), [GWOSC](https://gwosc.org/) (LIGO/Virgo/KAGRA), [ATNF](https://www.atnf.csiro.au/research/pulsar/psrcat/) Pulsar Catalogue, [OpenNGC](https://github.com/mattiaverga/OpenNGC), [Green's SNR Catalog](https://www.mrao.cam.ac.uk/surveys/snrs/), [SIMBAD](https://simbad.u-strasbg.fr/) (CDS Strasbourg), [VizieR](https://vizier.cds.unistra.fr/) (CDS Strasbourg — VLASS, Cosmicflows-4, INTEGRAL, LHAASO, HAWC), [Fermi LAT](https://fermi.gsfc.nasa.gov/ssc/), [CHIME/FRB](https://www.chime-frb.ca/), [eROSITA](https://erosita.mpe.mpg.de/), [Pantheon+](https://github.com/PantheonPlusSH0ES/DataRelease), [lenscat](https://github.com/lenscat/lenscat) |
| Physics | [Particle Data Group](https://pdg.lbl.gov/) (PDG), [CRDB](https://lpsc.in2p3.fr/crdb/) (Cosmic Ray DataBase), [Pierre Auger Observatory](https://www.auger.org/) (via Zenodo), [IceCube](https://icecube.wisc.edu/) (via HEASARC), [Swift/BAT](https://swift.gsfc.nasa.gov/results/bs157mon/) (NASA), [INTEGRAL IBIS](https://www.isdc.unige.ch/) (ESA), [TeVCat](http://tevcat.uchicago.edu/) (via HEASARC), [LHAASO](http://english.ihep.cas.cn/) (via VizieR), [HAWC](https://www.hawc-observatory.org/) (via VizieR) |

## License

Pipeline code: [MIT](LICENSE). Datasets: [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/).
