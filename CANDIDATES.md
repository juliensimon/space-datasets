# The Definitive Space Data Archive — Candidate Datasets

*Researched 2026-03-24, expanded 2026-03-26, solar system missions added 2026-03-27, Wikidata datasets added 2026-03-31. Goal: the most comprehensive free, tabular space data collection on Hugging Face.*

**Built: 207 dataset scripts** | **Remaining candidates: 20** | All sources free, no auth.

---

## Already Built (207 dataset scripts)

All P0 and P1 candidates are built, plus many P2 and 8 Wikidata datasets. Scripts in `scripts/update-*.py`, workflows in `.github/workflows/`.

**From P0 (all 14):** JPL SBDB, NVSS, Lunar Craters, FIRST, eROSITA, Mars Craters, Sunspot, GCVS, Fermi 4FGL, CHIME/FRB, Sentry, Fireballs, Pantheon+, PDG

**From P1 Original (25 of 30):** IceCube, TGSS, CRDB, Gaia RR Lyrae, SUMSS, Hipparcos, WDS, Auger, CelesTrak SW, RC3, IERS EOP, F10.7, SWPC Alerts, SatNOGS, TESS TOI, Open Clusters, NHATS, ICRF3, Astronauts, VLASS (3.4M), Chandra (28K), Cosmicflows-4, IAU Meteor Showers, GCAT, NASA EVA. *Not built: Transients (needs API key). Source unavailable: Solar Radio (HEASARC table removed 2026-03), UCS (download URLs dead 2026-03)*

**From P1 Space Probes (all 4):** ChemCam MOC (30K), ESA Mars Express (1.66M, weekly), ESA Rosetta (8.3M), Perseverance MEDA Weather (monthly)

**From P1 Particle Physics (all 5):** INTEGRAL IBIS, TeVCat, 1LHAASO, 3HWC HAWC, Fermi GBM Triggers (12.5K, daily)

**From P1 Connected Domains (all 8):** Galaxy Zoo 2 (243K), AAVSO VSX (10.3M), NEOWISE (183K), Geneva-Copenhagen (16K), Open Supernova Catalog (72K, weekly), GALAH DR4 (918K), Gaia DR3 Eclipsing Binaries (2.18M), DESI DR1 (5M BGS subset)

**From P1 Unblocked (2):** Neutron Monitor (470K, daily), Reentry Events (30K, daily)

**From P2 (20):** AE Index, Brown Dwarfs, Kepler EB, Planetary Nebulae, Gaia DR3 White Dwarfs (1.28M), SsODNet (1.49M), OTTER TDE (90), CNS5 (5.9K), Wolf-Rayet (380), Nesvorny Families (171K), Asterank Mining (600K), LCDB Lightcurves (36K), Solar System Moons (440), Magnetars (31), MPC Comets (1K), Unified Radio (1.66M), Bus-DeMeo Taxonomy (371), Solar Proton Events (300), Globular Clusters (168), Launch Cost to LEO (100)

**From new research (7):** Deep Space Probes (1.2M, monthly), Cassini (63K), Swift-BAT, Fermi 4LAC, Fermi 3FHL, Gravitational Lenses (33K), Meteorite Landings

**From Wikidata (8, quarterly):** Space Missions (25K), Astronomer Database (11.5K), Spacecraft Database (8.8K), Impact Craters (4.5K), Meteorite Database (1.2K), Observatory Database (609), Launch Vehicles (209), Space Agency Database (141)

**Pre-existing (23):** NEO, Starlink, SATCAT, Launch Log, Ground Stations, Constellation Census, DONKI, Dst Index, Kp Index, Solar Flares, Solar Wind, Space Weather, Exoplanets, GRB, Gravitational Waves, Pulsars, NGC/IC, SNR, Messier, Black Holes, Quasars, Galaxy Clusters

**Gap-filling bridge datasets (8):** OMNI Solar Wind (500K+, daily), GRBweb Unified GRBs (9K), ICECAT-1 Neutrino Alerts (348), Kepler Transit Timing (295K), SDSS Asteroid Taxonomy, Gaia YSOs, HECATE Galaxies, GSWLC-2

**New research (1):** SpaceX Launches (659, monthly) — all SpaceX missions with timelines, descriptions, and carousel photos from spacex.com

**From P1 Solar System Missions (8 uploaded):** PDS Planetary Missions (137+115+748, multi-config), InSight Marsquakes (2,715), IAU Planetary Nomenclature (13,723 features across Moon/Mars/Venus/Mercury), Ceres Craters (44K), Galileo Jupiter Atmosphere (686, entry+descent), Huygens Titan Atmosphere (2,727, entry+descent+velocity), GCAT Deep Space Missions, Venus Express Observations

**From new research (2026-04-04, 7):** Mercury Craters Herrick (16.9K, static), Substorm Onsets SuperMAG (253K, quarterly), Forbush Decreases IZMIRAN (7.1K, static), TNO/Centaur Properties PDS (652, static), Mercury Crater Degradation Kinczyk (3.3K, static), Pluto Atmosphere New Horizons (1.9K, static), Lunar Sample Geochemistry Astromat (58K, static)

**From gap analysis (2026-04-05, 5):** 4XMM X-ray Sources (630K, static, VizieR IX/68 DR12s), Roma-BZCAT Blazars (3.6K, static, VizieR VII/274), Planck Cold Clumps PGCC (13.2K, static, VizieR J/A+A/594/A28), Gaia DR3 Spectroscopic Binaries (186K, static, VizieR I/357 SB1+SB2), Fermi 3PC Gamma-ray Pulsars (7.2K, static, HEASARC fermilpsc)

**From new additions (2026-04-26, 4):** NASA APOD (11.3K entries since 1995, daily), Global Meteor Network (3M+ trajectories, daily), Lunar Eclipse Catalog (12K, static, NASA Five Millennium), Space Tourism Flights (85 commercial flights, monthly)

**From new additions (2026-05-10, 3):** Henry Draper Catalogue (272K stars, static, VizieR III/135A) — foundational MK spectral types by Annie Jump Cannon; IRAS Faint Source Catalog v2.0 (173K mid-IR sources, static, VizieR II/156A); ROSAT All-Sky Survey Bright Source Catalogue (18.8K soft X-ray sources, static, VizieR IX/10A)

**Note on actual sizes:** VLASS is 3.4M rows (not 700K — full component catalog). Chandra is 28K rows (HEASARC TAP truncates). AAVSO VSX is 10.3M (not 2.1M — catalog grew). DESI BGS subset is ~5M of the full 28.4M.

---

## P1 — Solar System Missions (researched 2026-03-27)

Built and uploaded: #1 PDS Missions, #2 InSight Marsquakes, #3 IAU Nomenclature, #4 Ceres Craters, #5 Galileo Atmosphere, #6 Huygens Atmosphere, #7 GCAT Deep Space, #12 Venus Express.

| # | Dataset | Domain | Rows | Size | Incr? | Schedule | Source | Notes |
|---|---------|--------|-----:|------|:-----:|----------|--------|-------|
| 4 | ~~Ceres Crater Database~~ | Planetary | 44,594 | 9 MB | No | Static | USGS Astropedia | **Built 2026-04** as `ceres-craters`. CSV in zip. Zeilnhofer 2020 |
| 7 | ~~GCAT Deep Space Missions~~ | Missions | 600+ | ~5 MB | No | Monthly | `planet4589.org/space/deepcat/` | **Built 2026-04** as `gcat-deep-space`. TSV. deepcat.tsv + mission phases. All interplanetary objects/encounters |
| 8 | ~~Mercury Craters (Herrick)~~ | Planetary | 16,876 | <1 MB | No | Static | U. Alaska | **Built 2026-04-04** as `mercury-craters-herrick` |
| 9 | Venus Craters (Herrick/USGS) | Planetary | ~900 | <1 MB | No | Static | USGS Astropedia CSV | Site currently down for maintenance. ~900 Magellan-era craters |
| 10 | ~~TNO/Centaur Properties~~ | Outer SS | 652 | <1 MB | No | Static | PDS Small Bodies Node | **Built 2026-04-04** as `tno-centaur-properties` |
| 11 | Mars Odyssey GRS Elements | Mars | ~grid | ~5 MB | No | Static | PDS Geosciences | .tab files. Cl, Fe, H2O, K, Si, Th maps at 2x2/5x5/10x10 deg bins |
| 12 | ~~Venus Express Observations~~ | Venus | ~10K+ | ~10 MB | No | Static | ESA COSMOS portal | **Built 2026-04** as `venus-express`. XLS. Full mission observation tracking table (2006-2014) |
| 13 | ~~New Horizons Pluto Atmospherics~~ | Pluto | 1,869 | <1 MB | No | Static | PDS SBN | **Built 2026-04-04** as `pluto-atmosphere` |
| 14 | MAVEN Key Parameters | Mars | millions | ~100 MB | No | Static | LASP SDC API | Tab-delimited ASCII. Multi-instrument atmospheric data. Large, needs chunked download |
| 15 | ~~Astromat Lunar Geochemistry~~ | Moon | 58,289 | 1.4 MB | No | Static | EarthChem Library | **Built 2026-04-04** as `lunar-sample-geochemistry` |
| 16 | ~~Kinczyk Mercury Degradation~~ | Mercury | 3,253 | <1 MB | No | Static | Mendeley Data | **Built 2026-04-04** as `mercury-crater-degradation` |
| 17 | Juno Magnetometer (summary) | Jupiter | depends | ~50 MB | No | Static | PDS/PPI | ASCII. Would need perijove-only extraction. Large raw dataset |

---

## P2 — Remaining Candidates

| # | Dataset | Domain | Rows | Size | Incr? | Schedule | Notes |
|---|---------|--------|-----:|------|:-----:|----------|-------|
| 1 | ~~Substorm Onset List~~ | Weather | 253,319 | 3 MB | No | Quarterly | **Built 2026-04-04** as `substorm-onsets` (SuperMAG, 5 algorithms) |
| 2 | GPS NANU Archive | Orbital | 3,000 | 5 MB | Yes | Weekly | Append new NANUs by date |
| 3 | ~~Forbush Decreases~~ | Weather | 7,097 | <1 MB | No | Static | **Built 2026-04-04** as `forbush-decreases` (IZMIRAN FEID) |
| 4 | Aerospace Corp Reentries | Orbital | 1,000+ | 5 MB | Yes | Weekly | Append new reentries. Web scraping, fragile |
| 5 | Habitable Worlds Catalog | Astronomy | 70 | <1 MB | No | Quarterly | Full rebuild. Better as filtered exoplanets view |
| 6 | Orbital Debris Density | Orbital | derived | 1 MB | No | Static | Low standalone value |

## P3 — Large/complex or niche

| # | Dataset | Domain | Rows | Size | Incr? | Schedule | Notes |
|---|---------|--------|-----:|------|:-----:|----------|-------|
| 7 | AstDyS Proper Elements | Orbital | 1,500,000 | 200 MB | No | Monthly | Full rebuild. Bulk text parse. Overlaps SBDB |
| 8 | OGLE Variables (params) | Astronomy | 1,000,000 | 200 MB | No | Yearly | No bulk download. Query interface only |
| 9 | Thermospheric Density | Weather | 1,000,000 | 50 MB | No | Static | CHAMP/GRACE derived. Very niche |
| 10 | Ionosonde foF2/hmF2 | Weather | 1,000,000 | 20 MB | Yes | Daily | Append hourly readings. Specialized ionospheric |
| 11 | ASAS-SN Variables | Astronomy | 700,000 | 100 MB | No | Quarterly | Full rebuild. Overlaps GCVS |
| 12 | Gaia DR3 RR Lyrae (full) | Astronomy | 271,779 | 50 MB | No | Static | Overlaps existing Gaia RR Lyrae subset |
| 13 | SpaceTrack-TimeSeries | Orbital | 57,000,000 | 2 GB | No | Static | 57M rows. Overlaps TLE history |
| 14 | EGM2008 Geoid | Geodesy | 4,672,080 | 500 MB | No | Static | Extremely specialized |
| 15 | NANOGrav Pulsar Timing | Astronomy | 68 pulsars | 1 GB | No | Static | Complex format per release |
| 16 | NASA Fragmentation History | Orbital | 355 | 1 MB | No | Static | PDF extraction |
| 17 | ESA OPS-SAT Anomalies | Orbital | 2,123 | 10 MB | No | Static | Niche ML benchmark |
| 18 | Transients (TNS) | Astronomy | 10–50K | 5 MB | Yes | Daily | Needs free API key registration |

---

## Schedule Summary

| Type | Count | Datasets |
|------|------:|----------|
| **Static** | 12 | Venus Craters, GRS Elements, MAVEN, Juno Mag, Orbital Debris, Thermospheric Density, Gaia RR Lyrae full, SpaceTrack-TimeSeries, EGM2008, NANOGrav, NASA Fragmentation, ESA OPS-SAT |
| **Daily** | 2 | Ionosonde, Transients (TNS) |
| **Weekly** | 2 | GPS NANU, Aerospace Reentries |
| **Monthly** | 1 | AstDyS Proper Elements |
| **Quarterly** | 2 | Habitable Worlds, ASAS-SN |
| **Yearly** | 1 | OGLE |
| **Total remaining** | **20** | (4 solar system + 4 P2 + 12 P3) |

## Skip

| Dataset | Reason |
|---------|--------|
| Conjunction CDMs | Operator agreement required |
| ESA DISCOS | Institutional access only |
| ITU SNL filings | Bureaucratic, use SatNOGS instead |
| Satellite drag coefficients | No public dataset exists |
| Satellite link budgets | Proprietary |
| SDSS Spectra | ~TB scale |
| TESS Light Curves | ~100 GB+ |
| ZTF Alerts | ~TB/year |
| HyperLEDA full | GB-scale, SQL-only |
| Gaia full catalog | TB-scale |
| AllWISE full | 748M rows, 1.2 TB |
| 2MASS full | 471M rows, 40 GB |
| JLA SNe Ia | Superseded by Pantheon+ |
| Active Asteroids | <50 rows, no clean source |
| Mars Landing Sites | ~30 rows, no tabular source |
| Planetary Fact Sheets | ~200 rows, HTML scraping |
| Leap Seconds | 27 rows, include as EOP metadata |
| ESA/NASA Mission Catalogs | ~~No bulk download/API~~ → **Built as PDS Planetary Missions** (2026-03-27) |
| ISS Experiment Catalog | No bulk download |
| ILRS/IGS Stations | <500 rows, Earthdata login |
| AMS-02/PAMELA/CALET/DAMPE | Already covered by CRDB dataset |
| Telescope Array/HiRes | No public tabular catalog |
| ANTARES/KM3NeT | No public source catalog yet |
| Tibet ASgamma | No public catalog on VizieR/HEASARC |
| Mars Rover Photos API | api.nasa.gov endpoint down since 2026 |
| NSSDC Master Catalog | No API or bulk download, HTML only. Currently offline for maintenance (2026-03). Superseded by PDS Search API |
| Solar Radio Bursts (HEASARC) | `solarburst` table no longer exists on HEASARC (never successfully fetched). No alternative consolidated source. Script + workflow kept (schedule disabled) |
| UCS Satellite Database | All download URLs return 404/403 (2026-03). UCS may have taken database offline. Script + workflow kept (schedule disabled) |
| Astronaut Database (Mendeley) | Original Mendeley source dead (2026-03). **Rebuilt using Wikidata SPARQL** — 1,044 astronauts, CC0 licensed |
| Baumgardt Globular Clusters | Merged into globular-star-clusters dataset |
| Harris Globular Clusters | Merged into globular-star-clusters dataset |
| Bus-DeMeo Taxonomy | **Built** as bus-demeo-asteroid-taxonomy |
| Solar Proton Events | **Built** as solar-proton-events |
| Launch Cost to LEO | **Built** as launch-cost-to-leo |

---

## Auth Summary

- **No auth needed**: 19 of 20 remaining candidates (all except TNS)
- **Free API key**: TNS (#18 Transients) — free bot key registration

## If You Could Only Build 3 More

1. Transients/TNS (10–50K — supernovae/TDEs, needs API key registration)
2. Venus Craters / Herrick (900 — completes crater collection, blocked on USGS maintenance)
3. AstDyS Proper Elements (1.5M — bulk orbital element catalog)
