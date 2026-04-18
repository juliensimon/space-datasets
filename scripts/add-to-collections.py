#!/usr/bin/env python3
"""Add all datasets to their HF domain collections.

Run after uploading new datasets to HF. Safe to re-run — skips duplicates.

Collection hierarchy:
  Parent collections (umbrella):
    Orbital Mechanics, Space Probes, Planetary Science, Space Weather,
    Astronomy, Physics, Solar System

  Sub-collections (focused):
    Astronomy → Stellar Catalogs, Variable Stars & Transients,
                Galaxies & Cosmology, Sky Surveys
    Orbital   → Satellites & Launches, Asteroids & Small Bodies
"""

from huggingface_hub import add_collection_item

# ── Parent collections (umbrellas) ────────────────────────────────────────
ORBITAL = "juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994"
PROBES = "juliensimon/space-probe-and-mission-datasets-69c3fe82d410a42b1e313167"
PLANETARY = "juliensimon/planetary-science-datasets-69c2d4683bd6a66c34fb4af2"
WEATHER = "juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70"
ASTRONOMY = "juliensimon/astronomy-datasets-69c24caf2f17e36128946743"
PHYSICS = "juliensimon/physics-datasets-69c2d4682d37dfdb77447bd7"
SOLAR_SYSTEM = "juliensimon/solar-system-datasets-69c6fa681978de62dff2f347"

# ── Sub-collections (focused) ─────────────────────────────────────────────
# Cross-domain
ESSENTIALS = "juliensimon/space-essentials-69cbafd7ea046a10eff11405"
# Astronomy sub-collections
STELLAR = "juliensimon/stellar-catalogs-69c792b1a52ab2757b0eaa57"
VARIABLE_STARS = "juliensimon/variable-stars-and-transients-69c792b1dd7a45812c5a9b36"
GALAXIES = "juliensimon/galaxies-and-cosmology-69c792b117242a3b236df55d"
SKY_SURVEYS = "juliensimon/sky-surveys-69c792b17d77aba7996e2442"

# Orbital sub-collections
SATELLITES = "juliensimon/satellites-and-launches-69c792b1fca01f437233082d"
SMALL_BODIES = "juliensimon/asteroids-and-small-bodies-69c792b1e0240f3bf1235c66"

DATASETS = {
    # ── Parent: Orbital Mechanics (umbrella — all orbital datasets) ────────
    ORBITAL: [
        "juliensimon/asterank-asteroid-mining",
        "juliensimon/asteroid-lightcurves-lcdb",
        "juliensimon/bus-demeo-asteroid-taxonomy",
        "juliensimon/cassini-saturn-observations",
        "juliensimon/comet-catalog",
        "juliensimon/constellation-census",
        "juliensimon/deep-space-probes",
        "juliensimon/fireball-bolide-events",
        "juliensimon/gcat-launch-vehicles",
        "juliensimon/iau-meteor-showers",
        "juliensimon/jpl-small-body-database",
        "juliensimon/launch-cost-to-leo",
        "juliensimon/launch-vehicles",
        "juliensimon/mpc-comet-elements",
        "juliensimon/nasa-eva-chronology",
        "juliensimon/neo-close-approaches",
        "juliensimon/neowise-asteroid-properties",
        "juliensimon/nesvorny-asteroid-families",
        "juliensimon/nhats-accessible-asteroids",
        "juliensimon/orbital-fragmentation-events",
        "juliensimon/reentry-events",
        "juliensimon/satnogs-transmitters",
        "juliensimon/sdss-asteroid-taxonomy",
        "juliensimon/sentry-impact-risk",
        "juliensimon/space-agency-database",
        "juliensimon/space-launch-log",
        "juliensimon/space-missions",
        "juliensimon/space-track-satcat",
        "juliensimon/space-track-tle-history",
        "juliensimon/spacecraft-database",
        "juliensimon/ssodnet-asteroid-properties",
        "juliensimon/tno-centaur-properties",
        "juliensimon/starlink-fleet-data",
        "juliensimon/starlink-ground-stations",
        "juliensimon/starlink-tle-latest",
        "juliensimon/kuiper-fleet-data",
        "juliensimon/globalstar-fleet-data",
        "juliensimon/blue-origin-launches",
        "juliensimon/oneweb-fleet-data",
        "juliensimon/ast-spacemobile-fleet-data",
        "juliensimon/ula-launches",
        "juliensimon/fcc-ngso-filings",
        "juliensimon/ucs-satellite-database",
        "juliensimon/gcat-satellite-catalog",
        "juliensimon/spacex-launches",
        "juliensimon/wmo-oscar-satellites",
        "juliensimon/constellation-tle-latest",
    ],
    # ── Sub: Satellites & Launches ─────────────────────────────────────────
    SATELLITES: [
        "juliensimon/constellation-census",
        "juliensimon/deep-space-probes",
        "juliensimon/gcat-launch-vehicles",
        "juliensimon/launch-cost-to-leo",
        "juliensimon/launch-vehicles",
        "juliensimon/nasa-eva-chronology",
        "juliensimon/orbital-fragmentation-events",
        "juliensimon/reentry-events",
        "juliensimon/satnogs-transmitters",
        "juliensimon/space-launch-log",
        "juliensimon/space-missions",
        "juliensimon/space-track-satcat",
        "juliensimon/space-track-tle-history",
        "juliensimon/spacecraft-database",
        "juliensimon/starlink-fleet-data",
        "juliensimon/kuiper-fleet-data",
        "juliensimon/globalstar-fleet-data",
        "juliensimon/blue-origin-launches",
        "juliensimon/oneweb-fleet-data",
        "juliensimon/ast-spacemobile-fleet-data",
        "juliensimon/ula-launches",
        "juliensimon/fcc-ngso-filings",
        "juliensimon/starlink-ground-stations",
        "juliensimon/starlink-tle-latest",
        "juliensimon/ucs-satellite-database",
        "juliensimon/gcat-satellite-catalog",
        "juliensimon/spacex-launches",
        "juliensimon/wmo-oscar-satellites",
        "juliensimon/constellation-tle-latest",
    ],
    # ── Sub: Asteroids & Small Bodies ──────────────────────────────────────
    SMALL_BODIES: [
        "juliensimon/asterank-asteroid-mining",
        "juliensimon/asteroid-lightcurves-lcdb",
        "juliensimon/bus-demeo-asteroid-taxonomy",
        "juliensimon/comet-catalog",
        "juliensimon/fireball-bolide-events",
        "juliensimon/iau-meteor-showers",
        "juliensimon/jpl-small-body-database",
        "juliensimon/meteorite-database",
        "juliensimon/mpc-comet-elements",
        "juliensimon/neo-close-approaches",
        "juliensimon/neowise-asteroid-properties",
        "juliensimon/nesvorny-asteroid-families",
        "juliensimon/nhats-accessible-asteroids",
        "juliensimon/sdss-asteroid-taxonomy",
        "juliensimon/sentry-impact-risk",
        "juliensimon/ssodnet-asteroid-properties",
        "juliensimon/tno-centaur-properties",
    ],
    # ── Parent: Space Probes ───────────────────────────────────────────────
    PROBES: [
        "juliensimon/artemis-ii",
        "juliensimon/astronaut-database",
        "juliensimon/cassini-saturn-observations",
        "juliensimon/deep-space-probes",
        "juliensimon/esa-exomars-tgo-observations",
        "juliensimon/esa-mars-express-observations",
        "juliensimon/esa-rosetta-observations",
        "juliensimon/galileo-jupiter-atmosphere",
        "juliensimon/huygens-titan-atmosphere",
        "juliensimon/insight-marsquake-catalog",
        "juliensimon/mars-chemcam-compositions",
        "juliensimon/mars-perseverance-weather",
        "juliensimon/nasa-eva-chronology",
        "juliensimon/pluto-atmosphere",
        "juliensimon/pds-planetary-missions",
        "juliensimon/gcat-deep-space",
        "juliensimon/isro-missions",
        "juliensimon/esa-venus-express-observations",
        "juliensimon/esa-bepicolombo-observations",
        "juliensimon/esa-huygens-titan-descent",
        "juliensimon/esa-juice-observations",
        "juliensimon/nasa-maven-kp-insitu",
        "juliensimon/nasa-mars-rover-images",
    ],
    # ── Parent: Planetary Science ──────────────────────────────────────────
    PLANETARY: [
        "juliensimon/ceres-craters-dawn",
        "juliensimon/esa-exomars-tgo-observations",
        "juliensimon/impact-craters",
        "juliensimon/lunar-craters-robbins",
        "juliensimon/mars-craters-robbins",
        "juliensimon/lunar-sample-geochemistry",
        "juliensimon/mercury-craters-herrick",
        "juliensimon/mercury-crater-degradation",
        "juliensimon/meteorite-database",
        "juliensimon/meteorite-landings",
        "juliensimon/planetary-nomenclature",
        "juliensimon/solar-system-moons",
        "juliensimon/esa-bepicolombo-observations",
        "juliensimon/esa-huygens-titan-descent",
        "juliensimon/nasa-maven-kp-insitu",
        "juliensimon/nasa-mars-rover-images",
    ],
    # ── Parent: Space Weather ──────────────────────────────────────────────
    WEATHER: [
        "juliensimon/auroral-electrojet-index",
        "juliensimon/celestrak-space-weather",
        "juliensimon/donki-space-weather-events",
        "juliensimon/dst-index",
        "juliensimon/f107-solar-flux",
        "juliensimon/geomagnetic-kp-index",
        "juliensimon/iers-earth-orientation",
        "juliensimon/neutron-monitor-cosmic-rays",
        "juliensimon/omni-solar-wind-parameters",
        "juliensimon/silso-sunspot-number",
        "juliensimon/solar-flare-events",
        "juliensimon/solar-proton-events",
        "juliensimon/solar-radio-bursts",
        "juliensimon/solar-wind",
        "juliensimon/space-weather-indices",
        "juliensimon/substorm-onsets",
        "juliensimon/swpc-alerts",
        "juliensimon/forbush-decreases",
    ],
    # ── Parent: Astronomy (umbrella — all astronomy datasets) ──────────────
    ASTRONOMY: [
        "juliensimon/aavso-vsx-variable-stars",
        "juliensimon/apogee-dr17",
        "juliensimon/astronaut-database",
        "juliensimon/astronomer-database",
        "juliensimon/black-hole-catalog",
        "juliensimon/bright-star-catalog",
        "juliensimon/brown-dwarf-catalog",
        "juliensimon/carbon-stars",
        "juliensimon/cataclysmic-variable-catalog",
        "juliensimon/chandra-x-ray-sources",
        "juliensimon/chime-frb-catalog",
        "juliensimon/cns5-nearby-stars",
        "juliensimon/constellation-catalog",
        "juliensimon/cosmic-void-catalog",
        "juliensimon/cosmicflows-galaxy-distances",
        "juliensimon/desi-dr1-redshifts",
        "juliensimon/erosita-erass1-xray",
        "juliensimon/fermi-4fgl-dr4",
        "juliensimon/first-radio-catalog",
        "juliensimon/galex-observations",
        "juliensimon/gaia-dr3-cepheids",
        "juliensimon/gaia-dr3-eclipsing-binaries",
        "juliensimon/gaia-dr3-rrlyrae",
        "juliensimon/gaia-dr3-white-dwarfs",
        "juliensimon/gaia-dr3-young-stellar-objects",
        "juliensimon/galah-dr4-stellar-abundances",
        "juliensimon/galaxy-clusters",
        "juliensimon/galaxy-zoo-2-morphology",
        "juliensimon/gamma-ray-bursts",
        "juliensimon/gcvs-variable-stars",
        "juliensimon/geneva-copenhagen-stellar-survey",
        "juliensimon/globular-star-clusters",
        "juliensimon/gravitational-lenses",
        "juliensimon/gravitational-wave-events",
        "juliensimon/grbweb-unified-grb-catalog",
        "juliensimon/gswlc-galaxy-properties",
        "juliensimon/hecate-nearby-galaxies",
        "juliensimon/hipparcos-catalog",
        "juliensimon/hst-observations",
        "juliensimon/icecube-neutrino-catalog",
        "juliensimon/icrf3-reference-frame",
        "juliensimon/iue-observations",
        "juliensimon/jwst-observations",
        "juliensimon/k2-observations",
        "juliensimon/kepler-eclipsing-binaries",
        "juliensimon/kepler-observations",
        "juliensimon/kepler-transit-timing",
        "juliensimon/mcgill-magnetar-catalog",
        "juliensimon/messier-catalog",
        "juliensimon/milliquas",
        "juliensimon/nasa-exoplanets",
        "juliensimon/nebula-catalog",
        "juliensimon/ngc-ic-catalog",
        "juliensimon/nvss-radio-catalog",
        "juliensimon/observatory-database",
        "juliensimon/open-star-clusters",
        "juliensimon/open-supernova-catalog",
        "juliensimon/otter-tde-catalog",
        "juliensimon/pantheon-plus-sne-ia",
        "juliensimon/planck-sz2-clusters",
        "juliensimon/planetary-nebulae",
        "juliensimon/pulsar-catalog",
        "juliensimon/pulsar-glitch-catalog",
        "juliensimon/quasar-catalog",
        "juliensimon/rave-dr6",
        "juliensimon/rc3-galaxy-morphology",
        "juliensimon/solar-eclipse-catalog",
        "juliensimon/sumss-radio-catalog",
        "juliensimon/supernova-remnants",
        "juliensimon/tess-toi-candidates",
        "juliensimon/tgss-radio-catalog",
        "juliensimon/unified-radio-catalog",
        "juliensimon/vlass-radio-sources",
        "juliensimon/wds-double-stars",
        "juliensimon/wise-hii-regions",
        "juliensimon/wolf-rayet-stars",
        "juliensimon/xray-binary-catalog",
        "juliensimon/4xmm-dr14-xray-sources",
        "juliensimon/roma-bzcat-blazars",
        "juliensimon/planck-cold-clumps",
        "juliensimon/gaia-dr3-spectroscopic-binaries",
        "juliensimon/fermi-3pc-gamma-ray-pulsars",
    ],
    # ── Sub: Stellar Catalogs ──────────────────────────────────────────────
    STELLAR: [
        "juliensimon/apogee-dr17",
        "juliensimon/bright-star-catalog",
        "juliensimon/brown-dwarf-catalog",
        "juliensimon/carbon-stars",
        "juliensimon/cns5-nearby-stars",
        "juliensimon/gaia-dr3-white-dwarfs",
        "juliensimon/gaia-dr3-young-stellar-objects",
        "juliensimon/galah-dr4-stellar-abundances",
        "juliensimon/geneva-copenhagen-stellar-survey",
        "juliensimon/globular-star-clusters",
        "juliensimon/hipparcos-catalog",
        "juliensimon/mcgill-magnetar-catalog",
        "juliensimon/open-star-clusters",
        "juliensimon/planetary-nebulae",
        "juliensimon/pulsar-catalog",
        "juliensimon/pulsar-glitch-catalog",
        "juliensimon/rave-dr6",
        "juliensimon/wds-double-stars",
        "juliensimon/wolf-rayet-stars",
        "juliensimon/xray-binary-catalog",
        "juliensimon/gaia-dr3-spectroscopic-binaries",
        "juliensimon/fermi-3pc-gamma-ray-pulsars",
    ],
    # ── Sub: Variable Stars & Transients ───────────────────────────────────
    VARIABLE_STARS: [
        "juliensimon/aavso-vsx-variable-stars",
        "juliensimon/cataclysmic-variable-catalog",
        "juliensimon/gaia-dr3-cepheids",
        "juliensimon/gaia-dr3-eclipsing-binaries",
        "juliensimon/gaia-dr3-rrlyrae",
        "juliensimon/gcvs-variable-stars",
        "juliensimon/gravitational-wave-events",
        "juliensimon/kepler-eclipsing-binaries",
        "juliensimon/kepler-transit-timing",
        "juliensimon/nasa-exoplanets",
        "juliensimon/open-supernova-catalog",
        "juliensimon/otter-tde-catalog",
        "juliensimon/supernova-remnants",
        "juliensimon/tess-toi-candidates",
    ],
    # ── Sub: Galaxies & Cosmology ──────────────────────────────────────────
    GALAXIES: [
        "juliensimon/black-hole-catalog",
        "juliensimon/cosmic-void-catalog",
        "juliensimon/cosmicflows-galaxy-distances",
        "juliensimon/desi-dr1-redshifts",
        "juliensimon/galaxy-clusters",
        "juliensimon/galaxy-zoo-2-morphology",
        "juliensimon/gravitational-lenses",
        "juliensimon/gswlc-galaxy-properties",
        "juliensimon/hecate-nearby-galaxies",
        "juliensimon/messier-catalog",
        "juliensimon/milliquas",
        "juliensimon/ngc-ic-catalog",
        "juliensimon/pantheon-plus-sne-ia",
        "juliensimon/planck-sz2-clusters",
        "juliensimon/quasar-catalog",
        "juliensimon/rc3-galaxy-morphology",
        "juliensimon/roma-bzcat-blazars",
    ],
    # ── Sub: Sky Surveys ───────────────────────────────────────────────────
    SKY_SURVEYS: [
        "juliensimon/chandra-x-ray-sources",
        "juliensimon/chime-frb-catalog",
        "juliensimon/erosita-erass1-xray",
        "juliensimon/fermi-4fgl-dr4",
        "juliensimon/first-radio-catalog",
        "juliensimon/galex-observations",
        "juliensimon/gamma-ray-bursts",
        "juliensimon/grbweb-unified-grb-catalog",
        "juliensimon/hst-observations",
        "juliensimon/icecube-neutrino-catalog",
        "juliensimon/icrf3-reference-frame",
        "juliensimon/iue-observations",
        "juliensimon/jwst-observations",
        "juliensimon/nvss-radio-catalog",
        "juliensimon/sumss-radio-catalog",
        "juliensimon/tgss-radio-catalog",
        "juliensimon/unified-radio-catalog",
        "juliensimon/vlass-radio-sources",
        "juliensimon/wise-hii-regions",
        "juliensimon/4xmm-dr14-xray-sources",
        "juliensimon/planck-cold-clumps",
    ],
    # ── Parent: Physics ────────────────────────────────────────────────────
    PHYSICS: [
        "juliensimon/auger-cosmic-rays",
        "juliensimon/crdb-cosmic-ray-spectra",
        "juliensimon/fermi-3fhl-hard-gamma-ray",
        "juliensimon/fermi-4lac-agn-catalog",
        "juliensimon/fermi-gbm-triggers",
        "juliensimon/hawc-tev-gamma-ray",
        "juliensimon/icecat-neutrino-alerts",
        "juliensimon/integral-ibis-hard-xray",
        "juliensimon/lhaaso-gamma-ray-sources",
        "juliensimon/pdg-particle-properties",
        "juliensimon/physics-nobel-laureates",
        "juliensimon/swift-bat-hard-xray-survey",
        "juliensimon/tevcat-tev-gamma-ray",
        "juliensimon/fermi-3pc-gamma-ray-pulsars",
    ],
    # ── Parent: Solar System ───────────────────────────────────────────────
    SOLAR_SYSTEM: [
        "juliensimon/artemis-ii",
        "juliensimon/cassini-saturn-observations",
        "juliensimon/ceres-craters-dawn",
        "juliensimon/deep-space-probes",
        "juliensimon/esa-exomars-tgo-observations",
        "juliensimon/esa-mars-express-observations",
        "juliensimon/esa-rosetta-observations",
        "juliensimon/galileo-jupiter-atmosphere",
        "juliensimon/huygens-titan-atmosphere",
        "juliensimon/impact-craters",
        "juliensimon/insight-marsquake-catalog",
        "juliensimon/lunar-craters-robbins",
        "juliensimon/mars-chemcam-compositions",
        "juliensimon/mars-craters-robbins",
        "juliensimon/mars-perseverance-weather",
        "juliensimon/mercury-craters-herrick",
        "juliensimon/mercury-crater-degradation",
        "juliensimon/lunar-sample-geochemistry",
        "juliensimon/pluto-atmosphere",
        "juliensimon/meteorite-landings",
        "juliensimon/nasa-eva-chronology",
        "juliensimon/pds-planetary-missions",
        "juliensimon/planetary-nomenclature",
        "juliensimon/solar-eclipse-catalog",
        "juliensimon/solar-system-moons",
        "juliensimon/gcat-deep-space",
        "juliensimon/esa-venus-express-observations",
        "juliensimon/esa-bepicolombo-observations",
        "juliensimon/esa-huygens-titan-descent",
        "juliensimon/esa-juice-observations",
        "juliensimon/nasa-maven-kp-insitu",
        "juliensimon/nasa-mars-rover-images",
    ],
    # ── Sub: Space Essentials (general public, no jargon) ────────────────────
    ESSENTIALS: [
        "juliensimon/astronaut-database",
        "juliensimon/astronomer-database",
        "juliensimon/constellation-catalog",
        "juliensimon/meteorite-database",
        "juliensimon/physics-nobel-laureates",
        "juliensimon/space-agency-database",
        "juliensimon/space-missions",
    ],
}


def main():
    added = 0
    skipped = 0
    errors = 0

    for collection_slug, datasets in DATASETS.items():
        domain = collection_slug.split("/")[1].rsplit("-", 1)[0]
        print(f"\n{domain}:")
        for dataset_id in datasets:
            name = dataset_id.split("/")[1]
            try:
                add_collection_item(
                    collection_slug,
                    item_id=dataset_id,
                    item_type="dataset",
                )
                print(f"  + {name}")
                added += 1
            except Exception as e:
                err = str(e)
                if "already" in err.lower() or "409" in err:
                    print(f"  = {name} (already in collection)")
                    skipped += 1
                else:
                    print(f"  ! {name}: {err[:80]}")
                    errors += 1

    print(f"\nDone: {added} added, {skipped} already present, {errors} errors")


if __name__ == "__main__":
    main()
