"""Banner images for HuggingFace dataset READMEs.

All images are copyright-free:
  - NASA: public domain (unless marked otherwise)
  - ESA/Hubble, ESA/Webb: CC-BY 4.0
  - NOAA: public domain (US government)

Usage in update scripts:
    from dataset_images import download_banner, banner_markdown

    banner_file = download_banner("exoplanets", tmp)
    banner_md = banner_markdown("exoplanets", banner_file)
    # Insert {banner_md} between the H1 title and collection backlink in README
"""

from pathlib import Path

import requests

# ── Domain default images ────────────────────────────────────────────────────
# Fallback when no per-dataset image is set. Keyed by domain slug.

DOMAIN_IMAGES = {
    "satellites": {
        "url": "https://images-assets.nasa.gov/image/iss071e439624/iss071e439624~medium.jpg",
        "alt": "An orbital sunrise illuminates the Earth's atmosphere, seen from the ISS",
        "credit": "NASA",
    },
    "small_bodies": {
        "url": "https://images-assets.nasa.gov/image/PIA17666/PIA17666~small.jpg",
        "alt": "Rosetta spacecraft approaching Comet 67P/Churyumov-Gerasimenko",
        "credit": "NASA/ESA",
    },
    "probes": {
        "url": "https://images-assets.nasa.gov/image/PIA14111/PIA14111~small.jpg",
        "alt": "Voyager spacecraft artist concept",
        "credit": "NASA/JPL-Caltech",
    },
    "planetary": {
        "url": "https://images-assets.nasa.gov/image/as08-14-2506/as08-14-2506~small.jpg",
        "alt": "The Moon seen from Apollo 8, showing craters and surface detail",
        "credit": "NASA/Apollo 8",
    },
    "weather": {
        "url": "https://images-assets.nasa.gov/image/iss072e159172/iss072e159172~medium.jpg",
        "alt": "Aurora borealis blankets the Earth, seen from the ISS",
        "credit": "NASA",
    },
    "stellar": {
        "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e000191/GSFC_20171208_Archive_e000191~medium.jpg",
        "alt": "A youthful globular star cluster observed by the Hubble Space Telescope",
        "credit": "NASA/ESA/Hubble",
    },
    "variable_stars": {
        "url": "https://images-assets.nasa.gov/image/PIA03606/PIA03606~small.jpg",
        "alt": "The Crab Nebula, a supernova remnant",
        "credit": "NASA/ESA/Hubble",
    },
    "galaxies": {
        "url": "https://images-assets.nasa.gov/image/PIA12110/PIA12110~small.jpg",
        "alt": "Hubble Deep Field revealing myriad galaxies across cosmic time",
        "credit": "NASA/ESA/STScI",
    },
    "sky_surveys": {
        "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e002215/GSFC_20171208_Archive_e002215~medium.jpg",
        "alt": "The gamma-ray sky as seen by NASA's Fermi telescope",
        "credit": "NASA/DOE/Fermi LAT Collaboration",
    },
    "physics": {
        "url": "https://images-assets.nasa.gov/image/PIA03519/PIA03519~small.jpg",
        "alt": "Cassiopeia A supernova remnant in X-ray, optical, and infrared light",
        "credit": "NASA/JPL-Caltech/STScI/CXC/SAO",
    },
    "solar_system": {
        "url": "https://images-assets.nasa.gov/image/PIA06193/PIA06193~small.jpg",
        "alt": "Saturn and its rings, captured by the Cassini spacecraft",
        "credit": "NASA/JPL-Caltech/SSI",
    },
    "exoplanets": {
        "url": "https://images-assets.nasa.gov/image/PIA21423/PIA21423~small.jpg",
        "alt": "Artist concept of the surface of TRAPPIST-1f exoplanet",
        "credit": "NASA/JPL-Caltech",
    },
    "essentials": {
        "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e001386/GSFC_20171208_Archive_e001386~medium.jpg",
        "alt": "Blue Marble — high-definition image of Earth from space",
        "credit": "NASA/GSFC/Suomi NPP",
    },
}

# ── Per-dataset overrides ────────────────────────────────────────────────────
# Only for datasets where a specific image is more relevant than the domain default.

DATASET_IMAGES = {
    "black-holes": {
        "url": "https://images-assets.nasa.gov/image/PIA22085/PIA22085~small.jpg",
        "alt": "Artist concept of a black hole with a relativistic jet",
        "credit": "NASA/JPL-Caltech",
    },
    "gravitational-waves": {
        "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e000415/GSFC_20171208_Archive_e000415~orig.jpg",
        "alt": "Artist illustration of two merging black holes emitting gravitational waves",
        "credit": "NASA/CXC/A. Hobart",
    },
    "pulsars": {
        "url": "https://images-assets.nasa.gov/image/PIA21085/PIA21085~small.jpg",
        "alt": "Pulsar artist concept showing a rapidly spinning neutron star",
        "credit": "NASA/JPL-Caltech",
    },
    "magnetars": {
        "url": "https://images-assets.nasa.gov/image/PIA23863/PIA23863~small.jpg",
        "alt": "Illustration of different types of neutron stars",
        "credit": "NASA/JPL-Caltech",
    },
    "neo": {
        "url": "https://images-assets.nasa.gov/image/PIA25329/PIA25329~small.jpg",
        "alt": "NASA's DART spacecraft approaching the Didymos asteroid system",
        "credit": "NASA/Johns Hopkins APL",
    },
    "solar-flares": {
        "url": "https://images-assets.nasa.gov/image/brief-outburst_16760026566_o/brief-outburst_16760026566_o~medium.jpg",
        "alt": "A solar eruption captured by NASA's Solar Dynamics Observatory",
        "credit": "NASA/SDO",
    },
    "sunspot": {
        "url": "https://images-assets.nasa.gov/image/brief-outburst_16760026566_o/brief-outburst_16760026566_o~medium.jpg",
        "alt": "The Sun showing solar activity captured by NASA's Solar Dynamics Observatory",
        "credit": "NASA/SDO",
    },
    "cassini": {
        "url": "https://images-assets.nasa.gov/image/PIA06193/PIA06193~small.jpg",
        "alt": "Saturn and its rings, captured by the Cassini spacecraft",
        "credit": "NASA/JPL-Caltech/SSI",
    },
    "exoplanets": {
        "url": "https://images-assets.nasa.gov/image/PIA21423/PIA21423~small.jpg",
        "alt": "Artist concept of the surface of TRAPPIST-1f exoplanet",
        "credit": "NASA/JPL-Caltech",
    },
    "mars-craters": {
        "url": "https://images-assets.nasa.gov/image/PIA24309/PIA24309~small.jpg",
        "alt": "Exploring Jezero Crater on Mars (illustration)",
        "credit": "NASA/JPL-Caltech",
    },
    "lunar-craters": {
        "url": "https://images-assets.nasa.gov/image/as08-14-2506/as08-14-2506~small.jpg",
        "alt": "The Moon from Apollo 8, showing craters and surface detail",
        "credit": "NASA/Apollo 8",
    },
    "supernovae": {
        "url": "https://images-assets.nasa.gov/image/PIA03606/PIA03606~small.jpg",
        "alt": "The Crab Nebula, remnant of a supernova explosion",
        "credit": "NASA/ESA/Hubble",
    },
    "snr": {
        "url": "https://images-assets.nasa.gov/image/PIA03606/PIA03606~small.jpg",
        "alt": "The Crab Nebula, a supernova remnant",
        "credit": "NASA/ESA/Hubble",
    },
    "fermi-4fgl": {
        "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e002215/GSFC_20171208_Archive_e002215~medium.jpg",
        "alt": "The gamma-ray sky as seen by NASA's Fermi telescope",
        "credit": "NASA/DOE/Fermi LAT Collaboration",
    },
    "fermi-3fhl": {
        "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e002215/GSFC_20171208_Archive_e002215~medium.jpg",
        "alt": "The gamma-ray sky as seen by NASA's Fermi telescope",
        "credit": "NASA/DOE/Fermi LAT Collaboration",
    },
    "quasars": {
        "url": "https://images-assets.nasa.gov/image/PIA12110/PIA12110~small.jpg",
        "alt": "Deep field image revealing distant galaxies and quasars",
        "credit": "NASA/ESA/STScI",
    },
    "starlink": {
        "url": "https://images-assets.nasa.gov/image/iss071e439624/iss071e439624~medium.jpg",
        "alt": "Orbital sunrise illuminating Earth's atmosphere, seen from the ISS",
        "credit": "NASA",
    },
    "astronauts": {
        "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e001386/GSFC_20171208_Archive_e001386~medium.jpg",
        "alt": "Blue Marble — Earth from space",
        "credit": "NASA/GSFC/Suomi NPP",
    },
    "rosetta": {
        "url": "https://images-assets.nasa.gov/image/PIA17666/PIA17666~small.jpg",
        "alt": "Rosetta spacecraft approaching Comet 67P/Churyumov-Gerasimenko",
        "credit": "NASA/ESA",
    },
    # Mars-related probes (override Voyager default)
    "chemcam": {
        "url": "https://images-assets.nasa.gov/image/PIA19808/PIA19808~small.jpg",
        "alt": "NASA's Curiosity rover on the surface of Mars",
        "credit": "NASA/JPL-Caltech/MSSS",
    },
    "exomars-tgo": {
        "url": "https://images-assets.nasa.gov/image/PIA24309/PIA24309~small.jpg",
        "alt": "Exploring Jezero Crater on Mars (illustration)",
        "credit": "NASA/JPL-Caltech",
    },
    "mars-express": {
        "url": "https://images-assets.nasa.gov/image/PIA24309/PIA24309~small.jpg",
        "alt": "Exploring Jezero Crater on Mars (illustration)",
        "credit": "NASA/JPL-Caltech",
    },
    "meda-weather": {
        "url": "https://images-assets.nasa.gov/image/PIA19808/PIA19808~small.jpg",
        "alt": "NASA's Curiosity rover on the surface of Mars",
        "credit": "NASA/JPL-Caltech/MSSS",
    },
    "venus-express": {
        "url": "https://images-assets.nasa.gov/image/PIA23791/PIA23791~small.jpg",
        "alt": "Venus as seen by Mariner 10",
        "credit": "NASA/JPL-Caltech",
    },
    # Planetary overrides
    "ceres-craters": {
        "url": "https://images-assets.nasa.gov/image/PIA12031/PIA12031~small.jpg",
        "alt": "Dawn spacecraft orbiting Ceres (artist concept)",
        "credit": "NASA/JPL-Caltech",
    },
    "solar-system-moons": {
        "url": "https://images-assets.nasa.gov/image/PIA00600/PIA00600~small.jpg",
        "alt": "Jupiter's Great Red Spot and the Galilean satellites",
        "credit": "NASA/JPL-Caltech",
    },
    "galileo-atmosphere": {
        "url": "https://images-assets.nasa.gov/image/PIA00600/PIA00600~small.jpg",
        "alt": "Jupiter's Great Red Spot and the Galilean satellites",
        "credit": "NASA/JPL-Caltech",
    },
    "huygens-atmosphere": {
        "url": "https://images-assets.nasa.gov/image/PIA06193/PIA06193~small.jpg",
        "alt": "Saturn and its rings, captured by the Cassini spacecraft",
        "credit": "NASA/JPL-Caltech/SSI",
    },
    # Radio survey overrides (override Fermi gamma-ray default)
    "first": {
        "url": "https://images-assets.nasa.gov/image/PIA13277/PIA13277~small.jpg",
        "alt": "Deep Space Network antenna at Goldstone",
        "credit": "NASA/JPL-Caltech",
    },
    "nvss": {
        "url": "https://images-assets.nasa.gov/image/PIA13277/PIA13277~small.jpg",
        "alt": "Deep Space Network antenna at Goldstone",
        "credit": "NASA/JPL-Caltech",
    },
    "sumss": {
        "url": "https://images-assets.nasa.gov/image/PIA13277/PIA13277~small.jpg",
        "alt": "Deep Space Network antenna at Goldstone",
        "credit": "NASA/JPL-Caltech",
    },
    "tgss": {
        "url": "https://images-assets.nasa.gov/image/PIA13277/PIA13277~small.jpg",
        "alt": "Deep Space Network antenna at Goldstone",
        "credit": "NASA/JPL-Caltech",
    },
    "vlass": {
        "url": "https://images-assets.nasa.gov/image/PIA13277/PIA13277~small.jpg",
        "alt": "Deep Space Network antenna at Goldstone",
        "credit": "NASA/JPL-Caltech",
    },
    "unified-radio": {
        "url": "https://images-assets.nasa.gov/image/PIA13277/PIA13277~small.jpg",
        "alt": "Deep Space Network antenna at Goldstone",
        "credit": "NASA/JPL-Caltech",
    },
    "chime-frb": {
        "url": "https://images-assets.nasa.gov/image/PIA13277/PIA13277~small.jpg",
        "alt": "Deep Space Network antenna at Goldstone",
        "credit": "NASA/JPL-Caltech",
    },
    "sentry": {
        "url": "https://images-assets.nasa.gov/image/PIA25329/PIA25329~small.jpg",
        "alt": "NASA's DART spacecraft approaching the Didymos asteroid system",
        "credit": "NASA/Johns Hopkins APL",
    },
    "insight-marsquakes": {
        "url": "https://images-assets.nasa.gov/image/PIA24309/PIA24309~small.jpg",
        "alt": "Exploring Jezero Crater on Mars (illustration)",
        "credit": "NASA/JPL-Caltech",
    },
    "solar-eclipses": {
        "url": "https://images-assets.nasa.gov/image/brief-outburst_16760026566_o/brief-outburst_16760026566_o~medium.jpg",
        "alt": "The Sun captured by NASA's Solar Dynamics Observatory",
        "credit": "NASA/SDO",
    },
    "constellations": {
        "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e000191/GSFC_20171208_Archive_e000191~medium.jpg",
        "alt": "A field of stars observed by the Hubble Space Telescope",
        "credit": "NASA/ESA/Hubble",
    },
    "messier": {
        "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e000191/GSFC_20171208_Archive_e000191~medium.jpg",
        "alt": "Star cluster observed by Hubble",
        "credit": "NASA/ESA/Hubble",
    },
    "nebulae": {
        "url": "https://images-assets.nasa.gov/image/PIA03606/PIA03606~small.jpg",
        "alt": "The Crab Nebula observed by the Hubble Space Telescope",
        "credit": "NASA/ESA/Hubble",
    },
    "globular-clusters": {
        "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e000191/GSFC_20171208_Archive_e000191~medium.jpg",
        "alt": "A youthful globular star cluster observed by Hubble",
        "credit": "NASA/ESA/Hubble",
    },
}

# ── Dataset-to-domain mapping ────────────────────────────────────────────────
# Derived from add-to-collections.py. Each key maps to exactly one domain.

DATASET_DOMAIN = {
    # Exoplanets
    "exoplanets": "exoplanets",
    "tess-toi": "exoplanets",
    "kepler-eb": "exoplanets",
    "kepler-ttv": "exoplanets",
    # Stellar catalogs
    "apogee-dr17": "stellar",
    "bright-stars": "stellar",
    "brown-dwarfs": "stellar",
    "carbon-stars": "stellar",
    "cns5": "stellar",
    "gaia-wd": "stellar",
    "gaia-yso": "stellar",
    "galah": "stellar",
    "geneva-copenhagen": "stellar",
    "globular-clusters": "stellar",
    "hipparcos": "stellar",
    "magnetars": "stellar",
    "nebulae": "stellar",
    "open-clusters": "stellar",
    "planetary-nebulae": "stellar",
    "pulsars": "stellar",
    "pulsar-glitches": "stellar",
    "rave-dr6": "stellar",
    "wds": "stellar",
    "wolf-rayet": "stellar",
    "xray-binaries": "stellar",
    # Variable stars & transients
    "aavso-vsx": "variable_stars",
    "cataclysmic-variables": "variable_stars",
    "gaia-cepheids": "variable_stars",
    "gaia-eb": "variable_stars",
    "gaia-rrlyrae": "variable_stars",
    "gcvs": "variable_stars",
    "supernovae": "variable_stars",
    "snr": "variable_stars",
    "otter-tde": "variable_stars",
    # Galaxies & cosmology
    "black-holes": "galaxies",
    "cosmic-voids": "galaxies",
    "cosmicflows": "galaxies",
    "desi": "galaxies",
    "galaxy-clusters": "galaxies",
    "galaxy-zoo": "galaxies",
    "gravitational-lenses": "galaxies",
    "gswlc": "galaxies",
    "hecate": "galaxies",
    "messier": "galaxies",
    "milliquas": "galaxies",
    "ngc-ic": "galaxies",
    "pantheon": "galaxies",
    "planck-sz2": "galaxies",
    "quasars": "galaxies",
    "rc3": "galaxies",
    # Sky surveys
    "chandra": "sky_surveys",
    "chime-frb": "sky_surveys",
    "erosita": "sky_surveys",
    "first": "sky_surveys",
    "grb": "sky_surveys",
    "grbweb": "sky_surveys",
    "icecube": "sky_surveys",
    "icrf3": "sky_surveys",
    "nvss": "sky_surveys",
    "sumss": "sky_surveys",
    "tgss": "sky_surveys",
    "unified-radio": "sky_surveys",
    "vlass": "sky_surveys",
    "hii-regions": "sky_surveys",
    # Satellites & launches
    "constellation-census": "satellites",
    "gcat": "satellites",
    "gcat-satcat": "satellites",
    "launch-cost": "satellites",
    "launch-vehicles": "satellites",
    "launch-log": "satellites",
    "fragmentation-events": "satellites",
    "reentry-events": "satellites",
    "satnogs": "satellites",
    "satcat": "satellites",
    "tle-history": "satellites",
    "tle-latest": "satellites",
    "spacex-launches": "satellites",
    "starlink": "satellites",
    "ground-stations": "satellites",
    "ucs": "satellites",
    "wmo-oscar": "satellites",
    # Asteroids & small bodies
    "asterank": "small_bodies",
    "lcdb": "small_bodies",
    "bus-demeo": "small_bodies",
    "comets": "small_bodies",
    "fireballs": "small_bodies",
    "meteor-showers": "small_bodies",
    "sbdb": "small_bodies",
    "meteorites": "small_bodies",
    "meteorite-landings": "small_bodies",
    "mpc-comets": "small_bodies",
    "neo": "small_bodies",
    "neowise": "small_bodies",
    "nesvorny-families": "small_bodies",
    "nhats": "small_bodies",
    "sdss-taxonomy": "small_bodies",
    "sentry": "small_bodies",
    "ssodnet": "small_bodies",
    "constellation-tles": "satellites",
    # Space probes & missions
    "artemis-ii": "probes",
    "astronauts": "probes",
    "cassini": "probes",
    "chemcam": "probes",
    "deep-space-probes": "probes",
    "eva": "probes",
    "exomars-tgo": "probes",
    "gcat-deep-space": "probes",
    "galileo-atmosphere": "probes",
    "huygens-atmosphere": "probes",
    "insight-marsquakes": "probes",
    "isro": "probes",
    "mars-express": "probes",
    "meda-weather": "probes",
    "pds-missions": "probes",
    "rosetta": "probes",
    "space-missions": "probes",
    "spacecraft": "probes",
    "venus-express": "probes",
    # Planetary science
    "ceres-craters": "planetary",
    "impact-craters": "planetary",
    "lunar-craters": "planetary",
    "mars-craters": "planetary",
    "planetary-nomenclature": "planetary",
    "solar-system-moons": "planetary",
    # Space weather
    "ae-index": "weather",
    "celestrak-sw": "weather",
    "donki": "weather",
    "dst-index": "weather",
    "f107": "weather",
    "kp-index": "weather",
    "iers-eop": "weather",
    "neutron-monitor": "weather",
    "omni": "weather",
    "sunspot": "weather",
    "solar-eclipses": "weather",
    "solar-flares": "weather",
    "solar-proton-events": "weather",
    "solar-radio": "weather",
    "solar-wind": "weather",
    "space-weather": "weather",
    "swpc-alerts": "weather",
    # Physics
    "auger": "physics",
    "crdb": "physics",
    "fermi-3fhl": "physics",
    "fermi-4fgl": "physics",
    "fermi-4lac": "physics",
    "fermi-gbm-triggers": "physics",
    "gravitational-waves": "physics",
    "hawc": "physics",
    "icecat": "physics",
    "integral-ibis": "physics",
    "lhaaso": "physics",
    "pdg": "physics",
    "physics-nobel": "physics",
    "swift-bat": "physics",
    "tevcat": "physics",
    # Essentials / general
    "astronomers": "essentials",
    "constellations": "essentials",
    "observatories": "essentials",
    "space-agencies": "essentials",
}


def get_image_info(dataset_key: str) -> dict:
    """Return image info dict for a dataset (per-dataset override or domain default)."""
    if dataset_key in DATASET_IMAGES:
        return DATASET_IMAGES[dataset_key]
    domain = DATASET_DOMAIN.get(dataset_key)
    if domain and domain in DOMAIN_IMAGES:
        return DOMAIN_IMAGES[domain]
    return DOMAIN_IMAGES["essentials"]


def download_banner(dataset_key: str, dest_dir) -> str | None:
    """Download banner image to dest_dir/banner.jpg. Returns filename or None."""
    info = get_image_info(dataset_key)
    try:
        resp = requests.get(info["url"], timeout=30)
        resp.raise_for_status()
        path = Path(dest_dir) / "banner.jpg"
        path.write_bytes(resp.content)
        return "banner.jpg"
    except Exception as e:
        print(f"  Warning: could not download banner image: {e}")
        return None


def banner_markdown(dataset_key: str, filename: str | None = None) -> str:
    """Return the markdown snippet for the banner image."""
    if filename is None:
        return ""
    info = get_image_info(dataset_key)
    alt = info.get("alt", "")
    credit = info.get("credit", "")
    lines = [
        "",
        '<div align="center">',
        f'  <img src="{filename}" alt="{alt}" width="400">',
    ]
    if credit:
        lines.append(f"  <p><em>Credit: {credit}</em></p>")
    lines.extend(["</div>", ""])
    return "\n".join(lines)
