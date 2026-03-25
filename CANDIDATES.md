# The Definitive Space Data Archive — Candidate Datasets

*Researched 2026-03-24, expanded 2026-03-25. Goal: the most comprehensive free, tabular space data collection on Hugging Face.*

**Built: 85 dataset scripts (83 uploaded)** | **Remaining candidates: 46** | All sources free, no auth (except 1 with free registration).

---

## Already Built (85 dataset scripts, 83 uploaded to HF)

All P0 candidates are built. Scripts in `scripts/update-*.py`, workflows in `.github/workflows/`.

**From P0 (all 14):** JPL SBDB, NVSS, Lunar Craters, FIRST, eROSITA, Mars Craters, Sunspot, GCVS, Fermi 4FGL, CHIME/FRB, Sentry, Fireballs, Pantheon+, PDG

**From P1 (30 of 30 — all complete):** IceCube, TGSS, CRDB, Gaia RR Lyrae, SUMSS, Hipparcos, WDS, Auger, CelesTrak SW, RC3, IERS EOP, F10.7, SWPC Alerts, Solar Radio, SatNOGS, UCS, TESS TOI, Open Clusters, NHATS, ICRF3, Astronauts, VLASS (3.4M), Chandra (28K), Cosmicflows-4, IAU Meteor Showers, GCAT, NASA EVA, Neutron Monitor (remaining), Transients (remaining), Reentry Events (blocked)

**From P1 Space Probes (all 4):** ChemCam MOC, ESA Mars Express (1.66M, weekly), ESA Rosetta (8.3M), Perseverance MEDA Weather (~3.2M, monthly)

**From P1 Particle Physics (all 5):** INTEGRAL IBIS, TeVCat, 1LHAASO, 3HWC HAWC, Fermi GBM Triggers (12.5K, daily)

**From P2 (4):** AE Index, Brown Dwarfs, Kepler EB, Planetary Nebulae

**From new research (7):** Deep Space Probes (1.2M, monthly), Cassini (63K), Swift-BAT, Fermi 4LAC, Fermi 3FHL, Gravitational Lenses (33K), Meteorite Landings (blocked)

**Pre-existing (23):** NEO, Starlink, SATCAT, Launch Log, Ground Stations, Constellation Census, DONKI, Dst Index, Kp Index, Solar Flares, Solar Wind, Space Weather, Exoplanets, GRB, Gravitational Waves, Pulsars, NGC/IC, SNR, Messier, Black Holes, Quasars, Galaxy Clusters

**Blocked (2):** Meteorite Landings (NASA SODA API 404), Reentry Events (TLE gap)

**Note on actual sizes:** VLASS is 3.4M rows (not 700K — full component catalog). Chandra is 28K rows (HEASARC TAP sync truncates the 407K master catalog).



---

## P1 — Connected Domains (remaining)


| #   | Dataset                                | Domain    | Rows       | Size   | Incr? | Schedule | Notes                                                                    |
| --- | -------------------------------------- | --------- | ---------- | ------ | ----- | -------- | ------------------------------------------------------------------------ |
| 1   | **Galaxy Zoo 2 Classifications**       | Astronomy | 243,500    | 30 MB  | No    | Static   | One-time upload. GZ2 is a fixed release. GZ-DESI would be separate       |
| 2   | **AAVSO VSX Variable Stars**           | Astronomy | 2,100,000  | 200 MB | No    | Monthly  | Full rebuild from bulk dump. Dump regenerated nightly but delta is small |
| 3   | **NEOWISE Asteroid Diameters/Albedos** | Orbital   | 164,000    | 20 MB  | No    | Static   | One-time upload. PDS archive, fixed release (V2.0)                       |
| 4   | **Geneva-Copenhagen Survey**           | Astronomy | 17,000     | 5 MB   | No    | Static   | One-time upload. Published catalog (Casagrande+ 2011)                    |
| 5   | **Open Supernova Catalog**             | Astronomy | 70,000     | 10 MB  | Yes   | Weekly   | Append new SNe by discovery date. ~50 new SNe/week from surveys          |
| 6   | **GALAH DR4** (stellar spectroscopy)   | Astronomy | 918,000    | 200 MB | No    | Static   | One-time upload per data release. DR5 would be separate                  |
| 7   | **Gaia DR3 Eclipsing Binaries**        | Astronomy | 2,184,000  | 200 MB | No    | Static   | One-time upload. Gaia DR4 would be separate                              |
| 8   | **DESI DR1 Redshifts** (subset)        | Astronomy | 28,400,000 | 2 GB   | No    | Static   | One-time upload per data release. Would need subsetting                  |


## P2 — Solid


| #   | Dataset                      | Domain    | Rows      | Size   | Incr? | Schedule  | Notes                                             |
| --- | ---------------------------- | --------- | --------- | ------ | ----- | --------- | ------------------------------------------------- |
| 9   | SsODNet Asteroid Phys. Props | Orbital   | 1,200,000 | 500 MB | No    | Quarterly | Full rebuild. API-based, continuous minor updates |
| 10  | Nesvorny Asteroid Families   | Orbital   | 500,000   | 50 MB  | No    | Static    | PDS text format. Fixed release                    |
| 11  | Asterank Mining Economics    | Orbital   | 600,000   | 50 MB  | No    | Quarterly | Full rebuild. Derived/estimated values            |
| 12  | Gaia DR3 White Dwarfs        | Astronomy | 359,000   | 100 MB | No    | Static    | Fixed catalog release                             |
| 13  | Substorm Onset List          | Weather   | 10,000    | 2 MB   | No    | Quarterly | Full rebuild. Published periodically              |
| 14  | CNS5 Nearby Stars (25pc)     | Astronomy | 5,931     | 2 MB   | No    | Static    | Fixed catalog release                             |
| 15  | GPS NANU Archive             | Orbital   | 3,000     | 5 MB   | Yes   | Weekly    | Append new NANUs by date                          |
| 16  | MPC Comet Elements           | Orbital   | 1,000     | 500 KB | No    | Monthly   | Full rebuild (tiny). Overlaps SBDB comets         |
| 17  | Forbush Decreases            | Weather   | 1,000     | 500 KB | No    | Static    | Published event list                              |
| 18  | Aerospace Corp Reentries     | Orbital   | 1,000+    | 5 MB   | Yes   | Weekly    | Append new reentries. Web scraping, fragile       |
| 19  | Wolf-Rayet Stars             | Astronomy | 709       | <1 MB  | No    | Static    | Very small, fixed catalog                         |
| 20  | Bus-DeMeo Taxonomy           | Orbital   | 371       | <1 MB  | No    | Static    | Better combined with SBDB                         |
| 21  | Solar Proton Events          | Weather   | 300       | <1 MB  | Yes   | Monthly   | Append new events from SWPC lists                 |
| 22  | OTTER TDE Catalog            | Astronomy | 232       | 2 MB   | Yes   | Weekly    | Append new TDEs. Hot topic, ~30 new/year          |
| 23  | Baumgardt Globular Clusters  | Astronomy | 168       | 200 KB | No    | Static    | HTML scraping needed. Tiny                        |
| 24  | Harris Globular Clusters     | Astronomy | 157       | 30 KB  | No    | Static    | Fixed-width parse                                 |
| 25  | Launch Cost to LEO           | Economics | 100       | <1 MB  | No    | Yearly    | Full rebuild. ~100 rows                           |
| 26  | Habitable Worlds Catalog     | Astronomy | 70        | <1 MB  | No    | Quarterly | Full rebuild. Better as filtered exoplanets view  |
| 27  | Solar System Moons           | Planetary | 290       | <1 MB  | No    | Yearly    | Full rebuild. New moons found ~yearly             |
| 28  | McGill Magnetar Catalog      | Astronomy | 30        | <1 MB  | No    | Static    | ~30 objects                                       |
| 29  | Orbital Debris Density       | Orbital   | derived   | 1 MB   | No    | Static    | Low standalone value                              |


## P3 — Large/complex or niche


| #   | Dataset                         | Domain    | Rows       | Size   | Incr? | Schedule  | Notes                                           |
| --- | ------------------------------- | --------- | ---------- | ------ | ----- | --------- | ----------------------------------------------- |
| 30  | AAVSO VSX Variable Index (full) | Astronomy | 10,000,000 | 2 GB   | No    | Monthly   | Full rebuild from bulk dump. 2 GB pipeline      |
| 31  | Unified Radio Catalog           | Astronomy | 2,870,000  | 1.4 GB | No    | Static    | Cross-match of NVSS+FIRST+etc. 1.4 GB           |
| 32  | AstDyS Proper Elements          | Orbital   | 1,500,000  | 200 MB | No    | Monthly   | Full rebuild. Bulk text parse. Overlaps SBDB    |
| 33  | OGLE Variables (params)         | Astronomy | 1,000,000  | 200 MB | No    | Yearly    | No bulk download. Query interface only          |
| 34  | Thermospheric Density           | Weather   | 1,000,000  | 50 MB  | No    | Static    | CHAMP/GRACE derived. Very niche                 |
| 35  | Ionosonde foF2/hmF2             | Weather   | 1,000,000  | 20 MB  | Yes   | Daily     | Append hourly readings. Specialized ionospheric |
| 36  | ASAS-SN Variables               | Astronomy | 700,000    | 100 MB | No    | Quarterly | Full rebuild. Overlaps GCVS                     |
| 37  | Gaia DR3 RR Lyrae (full)        | Astronomy | 271,779    | 50 MB  | No    | Static    | Overlaps existing Gaia RR Lyrae subset          |
| 38  | SpaceTrack-TimeSeries           | Orbital   | 57,000,000 | 2 GB   | No    | Static    | 57M rows. Overlaps TLE history                  |
| 39  | EGM2008 Geoid                   | Geodesy   | 4,672,080  | 500 MB | No    | Static    | Extremely specialized                           |
| 40  | NANOGrav Pulsar Timing          | Astronomy | 68 pulsars | 1 GB   | No    | Static    | Complex format per release                      |
| 41  | Asteroid Lightcurves (LCDB)     | Astronomy | 30,000     | 3 MB   | No    | Quarterly | Full rebuild. Lower priority than SBDB          |
| 42  | NASA Fragmentation History      | Orbital   | 355        | 1 MB   | No    | Static    | PDF extraction                                  |
| 43  | ESA OPS-SAT Anomalies           | Orbital   | 2,123      | 10 MB  | No    | Static    | Niche ML benchmark                              |


---

## Schedule Summary


| Type                     | Count | Datasets                                                                                                                                                                                                                                                                                                                              |
| ------------------------ | ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Static** (no workflow) | 20    | Galaxy Zoo 2, NEOWISE, Geneva-Copenhagen, GALAH, Gaia EB, DESI, Nesvorny, Gaia WD, CNS5, Forbush, Wolf-Rayet, Bus-DeMeo, Harris GC, Baumgardt GC, Magnetars, Debris Density, Unified Radio, Thermospheric, Gaia RRL, SpaceTrack |
| **Daily**                | 1     | Ionosonde |
| **Weekly**               | 4     | Open Supernova Catalog, GPS NANU, Aerospace Reentries, OTTER TDE |
| **Monthly**              | 3     | AAVSO VSX, MPC Comets, Solar Proton Events |
| **Quarterly**            | 4     | SsODNet, Asterank, Habitable Worlds, Substorm Onset |
| **Yearly**               | 3     | Launch Cost, Solar System Moons, OGLE |
| **Total remaining**      | **46**| *(includes P3: EGM2008, NANOGrav, Fragmentation, OPS-SAT, etc.)* |


## Skip


| Dataset                     | Reason                                |
| --------------------------- | ------------------------------------- |
| Conjunction CDMs            | Operator agreement required           |
| ESA DISCOS                  | Institutional access only             |
| ITU SNL filings             | Bureaucratic, use SatNOGS instead     |
| Satellite drag coefficients | No public dataset exists              |
| Satellite link budgets      | Proprietary                           |
| SDSS Spectra                | ~TB scale                             |
| TESS Light Curves           | ~100 GB+                              |
| ZTF Alerts                  | ~TB/year                              |
| HyperLEDA full              | GB-scale, SQL-only                    |
| Gaia full catalog           | TB-scale                              |
| AllWISE full                | 748M rows, 1.2 TB                     |
| 2MASS full                  | 471M rows, 40 GB                      |
| JLA SNe Ia                  | Superseded by Pantheon+               |
| Active Asteroids            | <50 rows, no clean source             |
| Mars Landing Sites          | ~30 rows, no tabular source           |
| Planetary Fact Sheets       | ~200 rows, HTML scraping              |
| Leap Seconds                | 27 rows, include as EOP metadata      |
| ESA/NASA Mission Catalogs   | No bulk download/API                  |
| ISS Experiment Catalog      | No bulk download                      |
| ILRS/IGS Stations           | <500 rows, Earthdata login            |
| AMS-02/PAMELA/CALET/DAMPE   | Already covered by CRDB dataset       |
| Telescope Array/HiRes       | No public tabular catalog             |
| ANTARES/KM3NeT              | No public source catalog yet          |
| Tibet ASgamma               | No public catalog on VizieR/HEASARC   |
| Mars Rover Photos API       | api.nasa.gov endpoint down since 2026 |
| NSSDC Master Catalog        | No API or bulk download, HTML only    |


---

## Auth Summary

- **No auth needed**: 46 of 46 remaining candidates
- (TNS Transients was listed as needing free API key — now built, no longer in candidates)

## If You Could Only Build 10 More

1. Galaxy Zoo 2 (243K — citizen-science morphology, ML-friendly, new domain)
2. NEOWISE Diameters/Albedos (164K — physical properties for asteroids, complements SBDB)
3. Gaia DR3 Eclipsing Binaries (2.18M — 700x larger than Kepler-EB)
4. AAVSO VSX Variable Stars (2.1M — massive upgrade over GCVS)
5. Open Supernova Catalog (70K — transient astronomy, new domain)
6. GALAH DR4 (918K — stellar spectroscopy, new domain)
7. SsODNet Asteroid Physical Props (1.2M — complements SBDB)
8. Gaia DR3 White Dwarfs (359K — largest WD catalog)
9. Geneva-Copenhagen Survey (17K — stellar ages, rare measurements)
10. DESI DR1 Redshifts (28.4M — largest spectroscopic survey ever)

