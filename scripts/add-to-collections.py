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
        "juliensimon/space-track-tle-history",
        "juliensimon/space-track-satcat",
        "juliensimon/space-launch-log",
        "juliensimon/starlink-fleet-data",
        "juliensimon/constellation-census",
        "juliensimon/starlink-ground-stations",
        "juliensimon/starlink-tle-latest",
        "juliensimon/neo-close-approaches",
        "juliensimon/jpl-small-body-database",
        "juliensimon/sentry-impact-risk",
        "juliensimon/fireball-bolide-events",
        "juliensimon/nhats-accessible-asteroids",
        "juliensimon/satnogs-transmitters",
        "juliensimon/ucs-satellite-database",
        "juliensimon/iau-meteor-showers",
        "juliensimon/gcat-launch-vehicles",
        "juliensimon/deep-space-probes",
        "juliensimon/cassini-saturn-observations",
        "juliensimon/nasa-eva-chronology",
        "juliensimon/reentry-events",
        "juliensimon/neowise-asteroid-properties",
        "juliensimon/ssodnet-asteroid-properties",
        "juliensimon/nesvorny-asteroid-families",
        "juliensimon/asterank-asteroid-mining",
        "juliensimon/asteroid-lightcurves-lcdb",
        "juliensimon/mpc-comet-elements",
        "juliensimon/bus-demeo-asteroid-taxonomy",
        "juliensimon/sdss-asteroid-taxonomy",
        "juliensimon/orbital-fragmentation-events",
        "juliensimon/launch-cost-to-leo",
        "juliensimon/space-missions",
        "juliensimon/spacecraft-database",
        "juliensimon/launch-vehicles",
        "juliensimon/space-agency-database",
        "juliensimon/comet-catalog",
    ],
    # ── Sub: Satellites & Launches ─────────────────────────────────────────
    SATELLITES: [
        "juliensimon/space-track-tle-history",
        "juliensimon/space-track-satcat",
        "juliensimon/space-launch-log",
        "juliensimon/starlink-fleet-data",
        "juliensimon/constellation-census",
        "juliensimon/starlink-ground-stations",
        "juliensimon/starlink-tle-latest",
        "juliensimon/satnogs-transmitters",
        "juliensimon/ucs-satellite-database",
        "juliensimon/gcat-launch-vehicles",
        "juliensimon/reentry-events",
        "juliensimon/orbital-fragmentation-events",
        "juliensimon/launch-cost-to-leo",
        "juliensimon/nasa-eva-chronology",
        "juliensimon/deep-space-probes",
        "juliensimon/space-missions",
        "juliensimon/spacecraft-database",
        "juliensimon/launch-vehicles",
    ],
    # ── Sub: Asteroids & Small Bodies ──────────────────────────────────────
    SMALL_BODIES: [
        "juliensimon/jpl-small-body-database",
        "juliensimon/neo-close-approaches",
        "juliensimon/sentry-impact-risk",
        "juliensimon/fireball-bolide-events",
        "juliensimon/nhats-accessible-asteroids",
        "juliensimon/neowise-asteroid-properties",
        "juliensimon/ssodnet-asteroid-properties",
        "juliensimon/nesvorny-asteroid-families",
        "juliensimon/asterank-asteroid-mining",
        "juliensimon/asteroid-lightcurves-lcdb",
        "juliensimon/mpc-comet-elements",
        "juliensimon/bus-demeo-asteroid-taxonomy",
        "juliensimon/sdss-asteroid-taxonomy",
        "juliensimon/iau-meteor-showers",
        "juliensimon/meteorite-database",
        "juliensimon/comet-catalog",
    ],
    # ── Parent: Space Probes ───────────────────────────────────────────────
    PROBES: [
        "juliensimon/artemis-ii",
        "juliensimon/deep-space-probes",
        "juliensimon/cassini-saturn-observations",
        "juliensimon/esa-mars-express-observations",
        "juliensimon/esa-rosetta-observations",
        "juliensimon/mars-chemcam-compositions",
        "juliensimon/mars-perseverance-weather",
        "juliensimon/nasa-eva-chronology",
        "juliensimon/pds-planetary-missions",
        "juliensimon/insight-marsquake-catalog",
        "juliensimon/galileo-jupiter-atmosphere",
        "juliensimon/huygens-titan-atmosphere",
        "juliensimon/astronaut-database",
    ],
    # ── Parent: Planetary Science ──────────────────────────────────────────
    PLANETARY: [
        "juliensimon/lunar-craters-robbins",
        "juliensimon/mars-craters-robbins",
        "juliensimon/meteorite-landings",
        "juliensimon/solar-system-moons",
        "juliensimon/planetary-nomenclature",
        "juliensimon/ceres-craters-dawn",
        "juliensimon/impact-craters",
        "juliensimon/meteorite-database",
    ],
    # ── Parent: Space Weather ──────────────────────────────────────────────
    WEATHER: [
        "juliensimon/space-weather-indices",
        "juliensimon/solar-flare-events",
        "juliensimon/dst-index",
        "juliensimon/donki-space-weather-events",
        "juliensimon/solar-wind",
        "juliensimon/geomagnetic-kp-index",
        "juliensimon/silso-sunspot-number",
        "juliensimon/f107-solar-flux",
        "juliensimon/swpc-alerts",
        "juliensimon/solar-radio-bursts",
        "juliensimon/iers-earth-orientation",
        "juliensimon/celestrak-space-weather",
        "juliensimon/auroral-electrojet-index",
        "juliensimon/neutron-monitor-cosmic-rays",
        "juliensimon/omni-solar-wind-parameters",
        "juliensimon/solar-proton-events",
    ],
    # ── Parent: Astronomy (umbrella — all astronomy datasets) ──────────────
    ASTRONOMY: [
        "juliensimon/nasa-exoplanets",
        "juliensimon/gamma-ray-bursts",
        "juliensimon/gravitational-wave-events",
        "juliensimon/pulsar-catalog",
        "juliensimon/ngc-ic-catalog",
        "juliensimon/supernova-remnants",
        "juliensimon/galaxy-clusters",
        "juliensimon/messier-catalog",
        "juliensimon/black-hole-catalog",
        "juliensimon/quasar-catalog",
        "juliensimon/nvss-radio-catalog",
        "juliensimon/first-radio-catalog",
        "juliensimon/erosita-erass1-xray",
        "juliensimon/gcvs-variable-stars",
        "juliensimon/fermi-4fgl-dr4",
        "juliensimon/chime-frb-catalog",
        "juliensimon/pantheon-plus-sne-ia",
        "juliensimon/tess-toi-candidates",
        "juliensimon/open-star-clusters",
        "juliensimon/icrf3-reference-frame",
        "juliensimon/tgss-radio-catalog",
        "juliensimon/sumss-radio-catalog",
        "juliensimon/hipparcos-catalog",
        "juliensimon/gaia-dr3-rrlyrae",
        "juliensimon/rc3-galaxy-morphology",
        "juliensimon/wds-double-stars",
        "juliensimon/astronaut-database",
        "juliensimon/icecube-neutrino-catalog",
        "juliensimon/brown-dwarf-catalog",
        "juliensimon/kepler-eclipsing-binaries",
        "juliensimon/planetary-nebulae",
        "juliensimon/gravitational-lenses",
        "juliensimon/cosmicflows-galaxy-distances",
        "juliensimon/vlass-radio-sources",
        "juliensimon/chandra-x-ray-sources",
        "juliensimon/galaxy-zoo-2-morphology",
        "juliensimon/geneva-copenhagen-stellar-survey",
        "juliensimon/open-supernova-catalog",
        "juliensimon/gaia-dr3-eclipsing-binaries",
        "juliensimon/aavso-vsx-variable-stars",
        "juliensimon/galah-dr4-stellar-abundances",
        "juliensimon/desi-dr1-redshifts",
        "juliensimon/gaia-dr3-white-dwarfs",
        "juliensimon/otter-tde-catalog",
        "juliensimon/cns5-nearby-stars",
        "juliensimon/wolf-rayet-stars",
        "juliensimon/unified-radio-catalog",
        "juliensimon/mcgill-magnetar-catalog",
        "juliensimon/gaia-dr3-young-stellar-objects",
        "juliensimon/globular-star-clusters",
        "juliensimon/grbweb-unified-grb-catalog",
        "juliensimon/gswlc-galaxy-properties",
        "juliensimon/hecate-nearby-galaxies",
        "juliensimon/kepler-transit-timing",
        "juliensimon/rave-dr6",
        "juliensimon/apogee-dr17",
        "juliensimon/gaia-dr3-cepheids",
        "juliensimon/milliquas",
        "juliensimon/bright-star-catalog",
        "juliensimon/carbon-stars",
        "juliensimon/astronomer-database",
        "juliensimon/observatory-database",
        "juliensimon/constellation-catalog",
        "juliensimon/nebula-catalog",
    ],
    # ── Sub: Stellar Catalogs ──────────────────────────────────────────────
    STELLAR: [
        "juliensimon/hipparcos-catalog",
        "juliensimon/bright-star-catalog",
        "juliensimon/cns5-nearby-stars",
        "juliensimon/brown-dwarf-catalog",
        "juliensimon/wolf-rayet-stars",
        "juliensimon/carbon-stars",
        "juliensimon/gaia-dr3-white-dwarfs",
        "juliensimon/gaia-dr3-young-stellar-objects",
        "juliensimon/mcgill-magnetar-catalog",
        "juliensimon/planetary-nebulae",
        "juliensimon/open-star-clusters",
        "juliensimon/globular-star-clusters",
        "juliensimon/wds-double-stars",
        "juliensimon/rave-dr6",
        "juliensimon/apogee-dr17",
        "juliensimon/galah-dr4-stellar-abundances",
        "juliensimon/geneva-copenhagen-stellar-survey",
        "juliensimon/pulsar-catalog",
    ],
    # ── Sub: Variable Stars & Transients ───────────────────────────────────
    VARIABLE_STARS: [
        "juliensimon/gcvs-variable-stars",
        "juliensimon/aavso-vsx-variable-stars",
        "juliensimon/gaia-dr3-rrlyrae",
        "juliensimon/gaia-dr3-cepheids",
        "juliensimon/gaia-dr3-eclipsing-binaries",
        "juliensimon/kepler-eclipsing-binaries",
        "juliensimon/kepler-transit-timing",
        "juliensimon/tess-toi-candidates",
        "juliensimon/nasa-exoplanets",
        "juliensimon/open-supernova-catalog",
        "juliensimon/otter-tde-catalog",
        "juliensimon/gravitational-wave-events",
        "juliensimon/supernova-remnants",
    ],
    # ── Sub: Galaxies & Cosmology ──────────────────────────────────────────
    GALAXIES: [
        "juliensimon/galaxy-clusters",
        "juliensimon/galaxy-zoo-2-morphology",
        "juliensimon/rc3-galaxy-morphology",
        "juliensimon/gswlc-galaxy-properties",
        "juliensimon/hecate-nearby-galaxies",
        "juliensimon/cosmicflows-galaxy-distances",
        "juliensimon/desi-dr1-redshifts",
        "juliensimon/quasar-catalog",
        "juliensimon/milliquas",
        "juliensimon/black-hole-catalog",
        "juliensimon/gravitational-lenses",
        "juliensimon/pantheon-plus-sne-ia",
        "juliensimon/messier-catalog",
        "juliensimon/ngc-ic-catalog",
    ],
    # ── Sub: Sky Surveys ───────────────────────────────────────────────────
    SKY_SURVEYS: [
        # Radio
        "juliensimon/nvss-radio-catalog",
        "juliensimon/first-radio-catalog",
        "juliensimon/tgss-radio-catalog",
        "juliensimon/sumss-radio-catalog",
        "juliensimon/vlass-radio-sources",
        "juliensimon/unified-radio-catalog",
        # X-ray
        "juliensimon/erosita-erass1-xray",
        "juliensimon/chandra-x-ray-sources",
        # Gamma-ray / high-energy
        "juliensimon/fermi-4fgl-dr4",
        "juliensimon/gamma-ray-bursts",
        "juliensimon/grbweb-unified-grb-catalog",
        "juliensimon/chime-frb-catalog",
        "juliensimon/icecube-neutrino-catalog",
        # Reference
        "juliensimon/icrf3-reference-frame",
        "juliensimon/astronaut-database",
    ],
    # ── Parent: Physics ────────────────────────────────────────────────────
    PHYSICS: [
        "juliensimon/pdg-particle-properties",
        "juliensimon/crdb-cosmic-ray-spectra",
        "juliensimon/auger-cosmic-rays",
        "juliensimon/swift-bat-hard-xray-survey",
        "juliensimon/fermi-4lac-agn-catalog",
        "juliensimon/fermi-3fhl-hard-gamma-ray",
        "juliensimon/fermi-gbm-triggers",
        "juliensimon/integral-ibis-hard-xray",
        "juliensimon/tevcat-tev-gamma-ray",
        "juliensimon/lhaaso-gamma-ray-sources",
        "juliensimon/hawc-tev-gamma-ray",
        "juliensimon/icecat-neutrino-alerts",
        "juliensimon/physics-nobel-laureates",
    ],
    # ── Parent: Solar System ───────────────────────────────────────────────
    SOLAR_SYSTEM: [
        "juliensimon/artemis-ii",
        "juliensimon/lunar-craters-robbins",
        "juliensimon/mars-craters-robbins",
        "juliensimon/meteorite-landings",
        "juliensimon/solar-system-moons",
        "juliensimon/deep-space-probes",
        "juliensimon/cassini-saturn-observations",
        "juliensimon/esa-mars-express-observations",
        "juliensimon/esa-rosetta-observations",
        "juliensimon/mars-chemcam-compositions",
        "juliensimon/mars-perseverance-weather",
        "juliensimon/nasa-eva-chronology",
        "juliensimon/pds-planetary-missions",
        "juliensimon/insight-marsquake-catalog",
        "juliensimon/planetary-nomenclature",
        "juliensimon/ceres-craters-dawn",
        "juliensimon/galileo-jupiter-atmosphere",
        "juliensimon/huygens-titan-atmosphere",
        "juliensimon/impact-craters",
    ],
    # ── Sub: Space Essentials (general public, no jargon) ────────────────────
    ESSENTIALS: [
        "juliensimon/astronaut-database",
        "juliensimon/astronomer-database",
        "juliensimon/space-missions",
        "juliensimon/constellation-catalog",
        "juliensimon/space-agency-database",
        "juliensimon/physics-nobel-laureates",
        "juliensimon/meteorite-database",
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
