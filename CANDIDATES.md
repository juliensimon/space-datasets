# The Definitive Space Data Archive — Candidate Datasets

*Researched 2026-03-24, expanded 2026-03-26. Goal: the most comprehensive free, tabular space data collection on Hugging Face.*

**Built: 115 dataset scripts (110 uploaded, 5 pending source fixes)** | **Remaining candidates: 18** | All sources free, no auth.

---

## Already Built (115 dataset scripts, 110 uploaded to HF)

All P0 and P1 candidates are built. Scripts in `scripts/update-*.py`, workflows in `.github/workflows/`.

**From P0 (all 14):** JPL SBDB, NVSS, Lunar Craters, FIRST, eROSITA, Mars Craters, Sunspot, GCVS, Fermi 4FGL, CHIME/FRB, Sentry, Fireballs, Pantheon+, PDG

**From P1 Original (27 of 30):** IceCube, TGSS, CRDB, Gaia RR Lyrae, SUMSS, Hipparcos, WDS, Auger, CelesTrak SW, RC3, IERS EOP, F10.7, SWPC Alerts, Solar Radio, SatNOGS, UCS, TESS TOI, Open Clusters, NHATS, ICRF3, Astronauts, VLASS (3.4M), Chandra (28K), Cosmicflows-4, IAU Meteor Showers, GCAT, NASA EVA. *Not built: Transients (needs API key)*

**From P1 Space Probes (all 4):** ChemCam MOC (30K), ESA Mars Express (1.66M, weekly), ESA Rosetta (8.3M), Perseverance MEDA Weather (monthly)

**From P1 Particle Physics (all 5):** INTEGRAL IBIS, TeVCat, 1LHAASO, 3HWC HAWC, Fermi GBM Triggers (12.5K, daily)

**From P1 Connected Domains (all 8):** Galaxy Zoo 2 (243K), AAVSO VSX (10.3M), NEOWISE (183K), Geneva-Copenhagen (16K), Open Supernova Catalog (72K, weekly), GALAH DR4 (918K), Gaia DR3 Eclipsing Binaries (2.18M), DESI DR1 (5M BGS subset)

**From P1 Unblocked (2):** Neutron Monitor (470K, daily), Reentry Events (30K, daily)

**From P2 (16):** AE Index, Brown Dwarfs, Kepler EB, Planetary Nebulae, Gaia DR3 White Dwarfs (1.28M), SsODNet (1.49M), OTTER TDE (90), CNS5 (5.9K), Wolf-Rayet (380), Nesvorny Families (171K), Asterank Mining (600K), LCDB Lightcurves (36K), Solar System Moons (440), Magnetars (31), MPC Comets (1K), Unified Radio (1.66M)

**From new research (7):** Deep Space Probes (1.2M, monthly), Cassini (63K), Swift-BAT, Fermi 4LAC, Fermi 3FHL, Gravitational Lenses (33K), Meteorite Landings (blocked)

**Pre-existing (23):** NEO, Starlink, SATCAT, Launch Log, Ground Stations, Constellation Census, DONKI, Dst Index, Kp Index, Solar Flares, Solar Wind, Space Weather, Exoplanets, GRB, Gravitational Waves, Pulsars, NGC/IC, SNR, Messier, Black Holes, Quasars, Galaxy Clusters

**From P2 continued (7):** Unified Radio/SPECFIND (1.66M), Nesvorny Families (171K), Asterank Mining (600K), LCDB Lightcurves (36K), Solar System Moons (440), Magnetars (31), MPC Comets (1K)

**Gap-filling bridge datasets (8):** OMNI Solar Wind (500K+, daily), GRBweb Unified GRBs (9K), ICECAT-1 Neutrino Alerts (348), Kepler Transit Timing (295K), SDSS Asteroid Taxonomy (pending OOM fix), Gaia YSOs (pending source), HECATE Galaxies (pending source), GSWLC-2 (pending source)

**Blocked (5):** Meteorite Landings (NASA API 404), SDSS Taxonomy (OOM on merge), Gaia YSOs (table missing from Gaia archive), HECATE (VizieR table not found), GSWLC-2 (download URL broken)

**Note on actual sizes:** VLASS is 3.4M rows (not 700K — full component catalog). Chandra is 28K rows (HEASARC TAP truncates). AAVSO VSX is 10.3M (not 2.1M — catalog grew). DESI BGS subset is ~5M of the full 28.4M.

---

## P2 — Solid

| # | Dataset | Domain | Rows | Size | Incr? | Schedule | Notes |
|---|---------|--------|-----:|------|:-----:|----------|-------|
| 1 | Substorm Onset List | Weather | 10,000 | 2 MB | No | Quarterly | Full rebuild. Published periodically |
| 2 | GPS NANU Archive | Orbital | 3,000 | 5 MB | Yes | Weekly | Append new NANUs by date |
| 3 | Forbush Decreases | Weather | 1,000 | 500 KB | No | Static | Published event list |
| 4 | Aerospace Corp Reentries | Orbital | 1,000+ | 5 MB | Yes | Weekly | Append new reentries. Web scraping, fragile |
| 5 | Bus-DeMeo Taxonomy | Orbital | 371 | <1 MB | No | Static | Better combined with SBDB |
| 6 | Solar Proton Events | Weather | 300 | <1 MB | Yes | Monthly | Append new events from SWPC lists |
| 7 | Baumgardt Globular Clusters | Astronomy | 168 | 200 KB | No | Static | HTML scraping needed. Tiny |
| 8 | Harris Globular Clusters | Astronomy | 157 | 30 KB | No | Static | Fixed-width parse |
| 9 | Launch Cost to LEO | Economics | 100 | <1 MB | No | Yearly | Full rebuild. ~100 rows |
| 10 | Habitable Worlds Catalog | Astronomy | 70 | <1 MB | No | Quarterly | Full rebuild. Better as filtered exoplanets view |
| 11 | Orbital Debris Density | Orbital | derived | 1 MB | No | Static | Low standalone value |

## P3 — Large/complex or niche

| # | Dataset | Domain | Rows | Size | Incr? | Schedule | Notes |
|---|---------|--------|-----:|------|:-----:|----------|-------|
| 12 | AstDyS Proper Elements | Orbital | 1,500,000 | 200 MB | No | Monthly | Full rebuild. Bulk text parse. Overlaps SBDB |
| 13 | OGLE Variables (params) | Astronomy | 1,000,000 | 200 MB | No | Yearly | No bulk download. Query interface only |
| 14 | Thermospheric Density | Weather | 1,000,000 | 50 MB | No | Static | CHAMP/GRACE derived. Very niche |
| 15 | Ionosonde foF2/hmF2 | Weather | 1,000,000 | 20 MB | Yes | Daily | Append hourly readings. Specialized ionospheric |
| 16 | ASAS-SN Variables | Astronomy | 700,000 | 100 MB | No | Quarterly | Full rebuild. Overlaps GCVS |
| 17 | Gaia DR3 RR Lyrae (full) | Astronomy | 271,779 | 50 MB | No | Static | Overlaps existing Gaia RR Lyrae subset |
| 18 | SpaceTrack-TimeSeries | Orbital | 57,000,000 | 2 GB | No | Static | 57M rows. Overlaps TLE history |
| 19 | EGM2008 Geoid | Geodesy | 4,672,080 | 500 MB | No | Static | Extremely specialized |
| 20 | NANOGrav Pulsar Timing | Astronomy | 68 pulsars | 1 GB | No | Static | Complex format per release |
| 21 | NASA Fragmentation History | Orbital | 355 | 1 MB | No | Static | PDF extraction |
| 22 | ESA OPS-SAT Anomalies | Orbital | 2,123 | 10 MB | No | Static | Niche ML benchmark |
| 23 | Transients (TNS) | Astronomy | 10–50K | 5 MB | Yes | Daily | Needs free API key registration |

---

## Schedule Summary

| Type | Count | Datasets |
|------|------:|----------|
| **Static** (no workflow) | 9 | Forbush, Bus-DeMeo, Harris GC, Baumgardt GC, Debris Density, Thermospheric, Gaia RRL, SpaceTrack, EGM2008, NANOGrav, Fragmentation, OPS-SAT |
| **Daily** | 2 | Ionosonde, Transients (TNS) |
| **Weekly** | 2 | GPS NANU, Aerospace Reentries |
| **Monthly** | 1 | Solar Proton Events |
| **Quarterly** | 2 | Habitable Worlds, Substorm Onset |
| **Yearly** | 2 | Launch Cost, OGLE |
| **Total remaining** | **23** | |

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
| ESA/NASA Mission Catalogs | No bulk download/API |
| ISS Experiment Catalog | No bulk download |
| ILRS/IGS Stations | <500 rows, Earthdata login |
| AMS-02/PAMELA/CALET/DAMPE | Already covered by CRDB dataset |
| Telescope Array/HiRes | No public tabular catalog |
| ANTARES/KM3NeT | No public source catalog yet |
| Tibet ASgamma | No public catalog on VizieR/HEASARC |
| Mars Rover Photos API | api.nasa.gov endpoint down since 2026 |
| NSSDC Master Catalog | No API or bulk download, HTML only |

---

## Auth Summary

- **No auth needed**: 22 of 23 remaining candidates
- **Free API key**: TNS (#23 Transients) — free bot key registration

## If You Could Only Build 3 More

1. Transients/TNS (10–50K — supernovae/TDEs, needs API key registration)
2. ASAS-SN Variables (700K — complements AAVSO VSX)
3. Gaia DR3 RR Lyrae full (272K — expands existing subset)
