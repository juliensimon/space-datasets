"""Human-readable attribution for upstream data providers.

Dataset READMEs cite the compiled dataset and name its original source. The
source URL is all any pipeline records, so this maps the URL's host to the
organisation that actually produces the data.
"""

from urllib.parse import urlparse

# Host → the organisation to credit. Keys are bare hostnames, matched after
# stripping a leading "www.".
SOURCE_ATTRIBUTION = {
    # Astronomical data centres
    "vizier.cds.unistra.fr": "VizieR, Centre de Données astronomiques de Strasbourg (CDS)",
    "cdsarc.cds.unistra.fr": "CDS Archive, Centre de Données astronomiques de Strasbourg",
    "simbad.u-strasbg.fr": "SIMBAD, Centre de Données astronomiques de Strasbourg (CDS)",
    "heasarc.gsfc.nasa.gov": "NASA HEASARC (High Energy Astrophysics Science Archive Research Center)",
    "archive.stsci.edu": "MAST, Space Telescope Science Institute",
    "exoplanetarchive.ipac.caltech.edu": "NASA Exoplanet Archive, IPAC/Caltech",
    "gea.esac.esa.int": "ESA Gaia Archive",
    "hecate.ia.forth.gr": "HECATE, FORTH Institute of Astrophysics",
    # Planetary archives
    "psa.esa.int": "ESA Planetary Science Archive",
    "pds.nasa.gov": "NASA Planetary Data System",
    "pds-atmospheres.nmsu.edu": "NASA PDS Atmospheres Node, New Mexico State University",
    "pds-geosciences.wustl.edu": "NASA PDS Geosciences Node, Washington University",
    "sbn.psi.edu": "NASA PDS Small Bodies Node, Planetary Science Institute",
    "sbnarchive.psi.edu": "NASA PDS Small Bodies Node, Planetary Science Institute",
    "astropedia.astrogeology.usgs.gov": "USGS Astrogeology Science Center",
    "astrogeology.usgs.gov": "USGS Astrogeology Science Center",
    "planetarynames.wr.usgs.gov": "IAU/USGS Gazetteer of Planetary Nomenclature",
    "mars.nasa.gov": "NASA Mars Exploration Program",
    # Small bodies and orbits
    "ssd.jpl.nasa.gov": "NASA JPL Solar System Dynamics",
    "ssd-api.jpl.nasa.gov": "NASA JPL Solar System Dynamics",
    "cneos.jpl.nasa.gov": "NASA JPL Center for Near-Earth Object Studies (CNEOS)",
    "minorplanetcenter.net": "IAU Minor Planet Center",
    "minplanobs.org": "IAU Minor Planet Center",
    "ssp.imcce.fr": "IMCCE, Observatoire de Paris",
    "asterank.com": "Asterank",
    # Orbital / satellite tracking
    "celestrak.org": "CelesTrak",
    "space-track.org": "Space-Track.org, United States Space Force",
    "planet4589.org": "Jonathan McDowell, planet4589.org",
    "db.satnogs.org": "SatNOGS Network",
    "ll.thespacedevs.com": "The Space Devs, Launch Library",
    "starlinkinsider.com": "Starlink Insider",
    "fcc.report": "United States Federal Communications Commission (via fcc.report)",
    "space.oscar.wmo.int": "WMO OSCAR",
    "aerospace.csis.org": "CSIS Aerospace Security Project",
    "ucsusa.org": "Union of Concerned Scientists",
    "isro.vercel.app": "Indian Space Research Organisation (unofficial API mirror)",
    "spacex.com": "SpaceX",
    "esa.int": "European Space Agency",
    # Space weather and geomagnetism
    "swpc.noaa.gov": "NOAA Space Weather Prediction Center",
    "spaceweather.gov": "NOAA Space Weather Prediction Center",
    "ngdc.noaa.gov": "NOAA National Centers for Environmental Information",
    "data.ngdc.noaa.gov": "NOAA National Centers for Environmental Information",
    "wdc.kugi.kyoto-u.ac.jp": "World Data Center for Geomagnetism, Kyoto University",
    "supermag.jhuapl.edu": "SuperMAG, Johns Hopkins University Applied Physics Laboratory",
    "spdf.gsfc.nasa.gov": "NASA Space Physics Data Facility",
    "omniweb.gsfc.nasa.gov": "NASA Space Physics Data Facility, OMNIWeb",
    "ccmc.gsfc.nasa.gov": "NASA Community Coordinated Modeling Center",
    "spaceweather.izmiran.ru": "IZMIRAN Space Weather Prediction Center",
    "nmdb.eu": "Neutron Monitor Database (NMDB)",
    "sidc.be": "SILSO, Royal Observatory of Belgium",
    "lasp.colorado.edu": "Laboratory for Atmospheric and Space Physics, University of Colorado Boulder",
    "parkersolarprobe.jhuapl.edu": "Parker Solar Probe, Johns Hopkins University Applied Physics Laboratory",
    "iers.org": "International Earth Rotation and Reference Systems Service (IERS)",
    # High-energy and multi-messenger
    "gwosc.org": "Gravitational Wave Open Science Center (GWOSC)",
    "gracedb.ligo.org": "GraceDB, LIGO Scientific Collaboration, Virgo Collaboration and KAGRA Collaboration",
    "fermi.gsfc.nasa.gov": "NASA Fermi Gamma-ray Space Telescope",
    "cxc.cfa.harvard.edu": "Chandra X-ray Center",
    "user-web.icecube.wisc.edu": "IceCube Neutrino Observatory",
    "pdg.lbl.gov": "Particle Data Group, Lawrence Berkeley National Laboratory",
    "lpsc.in2p3.fr": "Laboratoire de Physique Subatomique et de Cosmologie, Grenoble",
    "data.desi.lbl.gov": "DESI Collaboration, Lawrence Berkeley National Laboratory",
    # Observatories and surveys
    "jb.man.ac.uk": "Jodrell Bank Centre for Astrophysics, University of Manchester",
    "mrao.cam.ac.uk": "Mullard Radio Astronomy Observatory, University of Cambridge",
    "physics.mcgill.ca": "Department of Physics, McGill University",
    "sai.msu.su": "Sternberg Astronomical Institute, Moscow State University",
    "ta3.sk": "Astronomical Institute, Slovak Academy of Sciences",
    "galah-survey.org": "GALAH Survey",
    "aavso.org": "American Association of Variable Star Observers (AAVSO)",
    "globalmeteornetwork.org": "Global Meteor Network",
    "service.iris.edu": "EarthScope Consortium (IRIS) Data Services",
    "data.galaxyzoo.org": "Galaxy Zoo",
    "eclipse.gsfc.nasa.gov": "NASA Goddard Space Flight Center Eclipse Web Site",
    "apod.nasa.gov": "NASA Astronomy Picture of the Day",
    "data.nasa.gov": "NASA Open Data Portal",
    # Additional archives found in published cards
    "cosmos.esa.int": "ESA Science Operations Centre (cosmos.esa.int)",
    "auger.org": "Pierre Auger Observatory",
    "cdaw.gsfc.nasa.gov": "CDAW Data Center, NASA GSFC and The Catholic University of America",
    "ui.adsabs.harvard.edu": "NASA Astrophysics Data System (ADS)",
    "icecube.wisc.edu": "IceCube Neutrino Observatory",
    "tevcat.uchicago.edu": "TeVCat, University of Chicago",
    "people.smp.uq.edu.au": "School of Mathematics and Physics, University of Queensland",
    "salims.pages.iu.edu": "Indiana University",

    # General-purpose hosts
    "wikidata.org": "Wikidata contributors",
    "github.com": "the project's GitHub repository",
    "archive.org": "Internet Archive",
    "doi.org": "the DOI-registered source repository",
}


def source_attribution(source_url: str | None) -> str | None:
    """Return the organisation to credit for ``source_url``.

    Falls back to the bare hostname when the host is not in the registry, so a
    new source still produces a usable citation rather than an empty one.
    """
    if not source_url:
        return None
    host = (urlparse(source_url).hostname or "").lower()
    if not host:
        return None
    if host.startswith("www."):
        host = host[4:]
    return SOURCE_ATTRIBUTION.get(host, host)
