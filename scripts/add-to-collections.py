#!/usr/bin/env python3
"""Add all datasets to their HF domain collections.

Run after uploading new datasets to HF. Safe to re-run — skips duplicates.
"""

from huggingface_hub import add_collection_item

ORBITAL = "juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994"
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
    ],
    PLANETARY: [
        "juliensimon/lunar-craters-robbins",
        "juliensimon/mars-craters-robbins",
        "juliensimon/meteorite-landings",
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
    ],
    PHYSICS: [
        "juliensimon/pdg-particle-properties",
        "juliensimon/crdb-cosmic-ray-spectra",
        "juliensimon/auger-cosmic-rays",
        "juliensimon/swift-bat-hard-xray-survey",
        "juliensimon/fermi-4lac-agn-catalog",
        "juliensimon/fermi-3fhl-hard-gamma-ray",
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
