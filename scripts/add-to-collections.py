#!/usr/bin/env python3
"""Add all datasets to their HF domain collections.

Run after uploading new datasets to HF. Safe to re-run — skips duplicates.
"""

from huggingface_hub import add_collection_item

ORBITAL = "juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994"
PROBES = "juliensimon/space-probe-and-mission-datasets-69c3fe82d410a42b1e313167"
PLANETARY = "juliensimon/planetary-science-datasets-69c2d4683bd6a66c34fb4af2"
WEATHER = "juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70"
ASTRONOMY = "juliensimon/astronomy-datasets-69c24caf2f17e36128946743"
PHYSICS = "juliensimon/physics-datasets-69c2d4682d37dfdb77447bd7"

DATASETS = {
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
    ],
    PROBES: [
        "juliensimon/deep-space-probes",
        "juliensimon/cassini-saturn-observations",
        "juliensimon/esa-mars-express-observations",
        "juliensimon/esa-rosetta-observations",
        "juliensimon/mars-chemcam-compositions",
        "juliensimon/mars-perseverance-weather",
        "juliensimon/nasa-eva-chronology",
    ],
    PLANETARY: [
        "juliensimon/lunar-craters-robbins",
        "juliensimon/mars-craters-robbins",
        "juliensimon/meteorite-landings",
        "juliensimon/solar-system-moons",
    ],
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
    ],
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
    ],
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
