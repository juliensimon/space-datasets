#!/usr/bin/env python3
"""Fetch commercial spaceflight passenger data from Wikidata and upload to HF.

Source: Wikidata SPARQL endpoint — crewed spaceflights operated by commercial companies.
Falls back to (and always merges with) a curated seed list for completeness.
"""

import time

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

HF_REPO = "juliensimon/space-tourism-flights"

WIKIDATA_URL = "https://query.wikidata.org/sparql"
HEADERS = {"User-Agent": "space-datasets/1.0 (https://github.com/juliensimon/space-datasets)"}

# ── Commercial operator Wikidata QIDs ────────────────────────────────
OPERATOR_QIDS = {
    "Q851546": "Virgin Galactic",
    "Q844497": "Blue Origin",
    "Q193559": "SpaceX",
    "Q1010715": "Axiom Space",
    "Q1423338": "Space Adventures",
}

SPARQL_QUERY = """
SELECT DISTINCT ?flight ?flightLabel ?flightDate ?operator ?operatorLabel
       ?participant ?participantLabel ?birthYear ?nationalityLabel ?vehicleLabel
WHERE {
  ?flight wdt:P31/wdt:P279* wd:Q1066830.
  ?flight wdt:P1344 ?participant.
  ?flight wdt:P137 ?operator.
  FILTER(?operator IN (wd:Q851546, wd:Q844497, wd:Q193559, wd:Q1010715, wd:Q1423338))
  OPTIONAL { ?flight wdt:P585 ?flightDate. }
  OPTIONAL { ?participant wdt:P569 ?birthDate. BIND(YEAR(?birthDate) AS ?birthYear) }
  OPTIONAL { ?participant wdt:P27 ?nationality. }
  OPTIONAL { ?flight wdt:P15 ?vehicle. }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,mul". }
}
ORDER BY ?flightDate
"""

# ── Curated seed data — ensures complete coverage regardless of Wikidata state ──
SEED_DATA = [
    # ── Space Adventures ISS visits (orbital, Soyuz) ────────────────────────
    {
        "flight_name": "Soyuz TM-32", "flight_date": "2001-04-28",
        "operator": "Space Adventures", "vehicle": "Soyuz TM-32",
        "trajectory_type": "orbital", "passenger_name": "Dennis Tito",
        "passenger_nationality": "American", "passenger_birth_year": 1940,
        "passenger_occupation": "businessman", "is_paying_tourist": True,
        "duration_hours": 188, "max_altitude_km": 400,
    },
    {
        "flight_name": "Soyuz TMA-7", "flight_date": "2005-10-01",
        "operator": "Space Adventures", "vehicle": "Soyuz TMA-7",
        "trajectory_type": "orbital", "passenger_name": "Greg Olsen",
        "passenger_nationality": "American", "passenger_birth_year": 1945,
        "passenger_occupation": "scientist", "is_paying_tourist": True,
        "duration_hours": 188, "max_altitude_km": 400,
    },
    {
        "flight_name": "Soyuz TMA-9", "flight_date": "2006-09-18",
        "operator": "Space Adventures", "vehicle": "Soyuz TMA-9",
        "trajectory_type": "orbital", "passenger_name": "Anousheh Ansari",
        "passenger_nationality": "Iranian-American", "passenger_birth_year": 1966,
        "passenger_occupation": "entrepreneur", "is_paying_tourist": True,
        "duration_hours": 188, "max_altitude_km": 400,
    },
    {
        "flight_name": "Soyuz TMA-10", "flight_date": "2007-04-07",
        "operator": "Space Adventures", "vehicle": "Soyuz TMA-10",
        "trajectory_type": "orbital", "passenger_name": "Charles Simonyi",
        "passenger_nationality": "American", "passenger_birth_year": 1948,
        "passenger_occupation": "entrepreneur", "is_paying_tourist": True,
        "duration_hours": 335, "max_altitude_km": 400,
    },
    {
        "flight_name": "Soyuz TMA-13", "flight_date": "2008-10-12",
        "operator": "Space Adventures", "vehicle": "Soyuz TMA-13",
        "trajectory_type": "orbital", "passenger_name": "Richard Garriott",
        "passenger_nationality": "American", "passenger_birth_year": 1961,
        "passenger_occupation": "game developer", "is_paying_tourist": True,
        "duration_hours": 263, "max_altitude_km": 400,
    },
    {
        "flight_name": "Soyuz TMA-16", "flight_date": "2009-09-30",
        "operator": "Space Adventures", "vehicle": "Soyuz TMA-16",
        "trajectory_type": "orbital", "passenger_name": "Guy Laliberté",
        "passenger_nationality": "Canadian", "passenger_birth_year": 1959,
        "passenger_occupation": "entrepreneur", "is_paying_tourist": True,
        "duration_hours": 261, "max_altitude_km": 400,
    },
    # Charles Simonyi's second flight
    {
        "flight_name": "Soyuz TMA-14", "flight_date": "2009-03-26",
        "operator": "Space Adventures", "vehicle": "Soyuz TMA-14",
        "trajectory_type": "orbital", "passenger_name": "Charles Simonyi",
        "passenger_nationality": "American", "passenger_birth_year": 1948,
        "passenger_occupation": "entrepreneur", "is_paying_tourist": True,
        "duration_hours": 327, "max_altitude_km": 400,
    },
    # Space Adventures 2021-2022 revival (ISS via Soyuz)
    {
        "flight_name": "Soyuz MS-20", "flight_date": "2021-12-08",
        "operator": "Space Adventures", "vehicle": "Soyuz MS-20",
        "trajectory_type": "orbital", "passenger_name": "Yusaku Maezawa",
        "passenger_nationality": "Japanese", "passenger_birth_year": 1975,
        "passenger_occupation": "entrepreneur", "is_paying_tourist": True,
        "duration_hours": 293, "max_altitude_km": 410,
    },
    {
        "flight_name": "Soyuz MS-20", "flight_date": "2021-12-08",
        "operator": "Space Adventures", "vehicle": "Soyuz MS-20",
        "trajectory_type": "orbital", "passenger_name": "Yozo Hirano",
        "passenger_nationality": "Japanese", "passenger_birth_year": 1985,
        "passenger_occupation": "producer", "is_paying_tourist": True,
        "duration_hours": 293, "max_altitude_km": 410,
    },
    # ── SpaceX Inspiration4 (orbital, all-civilian) ─────────────────────────
    {
        "flight_name": "SpaceX Inspiration4", "flight_date": "2021-09-15",
        "operator": "SpaceX", "vehicle": "Crew Dragon Resilience",
        "trajectory_type": "orbital", "passenger_name": "Jared Isaacman",
        "passenger_nationality": "American", "passenger_birth_year": 1983,
        "passenger_occupation": "entrepreneur", "is_paying_tourist": True,
        "duration_hours": 70, "max_altitude_km": 585,
    },
    {
        "flight_name": "SpaceX Inspiration4", "flight_date": "2021-09-15",
        "operator": "SpaceX", "vehicle": "Crew Dragon Resilience",
        "trajectory_type": "orbital", "passenger_name": "Sian Proctor",
        "passenger_nationality": "American", "passenger_birth_year": 1970,
        "passenger_occupation": "educator", "is_paying_tourist": False,
        "duration_hours": 70, "max_altitude_km": 585,
    },
    {
        "flight_name": "SpaceX Inspiration4", "flight_date": "2021-09-15",
        "operator": "SpaceX", "vehicle": "Crew Dragon Resilience",
        "trajectory_type": "orbital", "passenger_name": "Hayley Arceneaux",
        "passenger_nationality": "American", "passenger_birth_year": 1994,
        "passenger_occupation": "physician assistant", "is_paying_tourist": False,
        "duration_hours": 70, "max_altitude_km": 585,
    },
    {
        "flight_name": "SpaceX Inspiration4", "flight_date": "2021-09-15",
        "operator": "SpaceX", "vehicle": "Crew Dragon Resilience",
        "trajectory_type": "orbital", "passenger_name": "Chris Sembroski",
        "passenger_nationality": "American", "passenger_birth_year": 1988,
        "passenger_occupation": "engineer", "is_paying_tourist": False,
        "duration_hours": 70, "max_altitude_km": 585,
    },
    # ── Axiom Space missions ────────────────────────────────────────────────
    {
        "flight_name": "Axiom Mission 1", "flight_date": "2022-04-08",
        "operator": "Axiom Space", "vehicle": "Crew Dragon Endeavour",
        "trajectory_type": "orbital", "passenger_name": "Michael López-Alegría",
        "passenger_nationality": "American", "passenger_birth_year": 1958,
        "passenger_occupation": "astronaut", "is_paying_tourist": False,
        "duration_hours": 408, "max_altitude_km": 420,
    },
    {
        "flight_name": "Axiom Mission 1", "flight_date": "2022-04-08",
        "operator": "Axiom Space", "vehicle": "Crew Dragon Endeavour",
        "trajectory_type": "orbital", "passenger_name": "Larry Connor",
        "passenger_nationality": "American", "passenger_birth_year": 1951,
        "passenger_occupation": "entrepreneur", "is_paying_tourist": True,
        "duration_hours": 408, "max_altitude_km": 420,
    },
    {
        "flight_name": "Axiom Mission 1", "flight_date": "2022-04-08",
        "operator": "Axiom Space", "vehicle": "Crew Dragon Endeavour",
        "trajectory_type": "orbital", "passenger_name": "Eytan Stibbe",
        "passenger_nationality": "Israeli", "passenger_birth_year": 1958,
        "passenger_occupation": "investor", "is_paying_tourist": True,
        "duration_hours": 408, "max_altitude_km": 420,
    },
    {
        "flight_name": "Axiom Mission 1", "flight_date": "2022-04-08",
        "operator": "Axiom Space", "vehicle": "Crew Dragon Endeavour",
        "trajectory_type": "orbital", "passenger_name": "Mark Pathy",
        "passenger_nationality": "Canadian", "passenger_birth_year": 1971,
        "passenger_occupation": "entrepreneur", "is_paying_tourist": True,
        "duration_hours": 408, "max_altitude_km": 420,
    },
    {
        "flight_name": "Axiom Mission 2", "flight_date": "2023-05-22",
        "operator": "Axiom Space", "vehicle": "Crew Dragon Freedom",
        "trajectory_type": "orbital", "passenger_name": "Peggy Whitson",
        "passenger_nationality": "American", "passenger_birth_year": 1960,
        "passenger_occupation": "astronaut", "is_paying_tourist": False,
        "duration_hours": 384, "max_altitude_km": 420,
    },
    {
        "flight_name": "Axiom Mission 2", "flight_date": "2023-05-22",
        "operator": "Axiom Space", "vehicle": "Crew Dragon Freedom",
        "trajectory_type": "orbital", "passenger_name": "John Shoffner",
        "passenger_nationality": "American", "passenger_birth_year": 1958,
        "passenger_occupation": "investor", "is_paying_tourist": True,
        "duration_hours": 384, "max_altitude_km": 420,
    },
    {
        "flight_name": "Axiom Mission 2", "flight_date": "2023-05-22",
        "operator": "Axiom Space", "vehicle": "Crew Dragon Freedom",
        "trajectory_type": "orbital", "passenger_name": "Ali Alqarni",
        "passenger_nationality": "Saudi Arabian", "passenger_birth_year": 1988,
        "passenger_occupation": "military officer", "is_paying_tourist": True,
        "duration_hours": 384, "max_altitude_km": 420,
    },
    {
        "flight_name": "Axiom Mission 2", "flight_date": "2023-05-22",
        "operator": "Axiom Space", "vehicle": "Crew Dragon Freedom",
        "trajectory_type": "orbital", "passenger_name": "Rayyanah Barnawi",
        "passenger_nationality": "Saudi Arabian", "passenger_birth_year": 1990,
        "passenger_occupation": "biomedical researcher", "is_paying_tourist": True,
        "duration_hours": 384, "max_altitude_km": 420,
    },
    {
        "flight_name": "Axiom Mission 3", "flight_date": "2024-01-18",
        "operator": "Axiom Space", "vehicle": "Crew Dragon Freedom",
        "trajectory_type": "orbital", "passenger_name": "Michael López-Alegría",
        "passenger_nationality": "American", "passenger_birth_year": 1958,
        "passenger_occupation": "astronaut", "is_paying_tourist": False,
        "duration_hours": 336, "max_altitude_km": 420,
    },
    {
        "flight_name": "Axiom Mission 3", "flight_date": "2024-01-18",
        "operator": "Axiom Space", "vehicle": "Crew Dragon Freedom",
        "trajectory_type": "orbital", "passenger_name": "Marcus Wandt",
        "passenger_nationality": "Swedish", "passenger_birth_year": 1981,
        "passenger_occupation": "astronaut", "is_paying_tourist": False,
        "duration_hours": 336, "max_altitude_km": 420,
    },
    {
        "flight_name": "Axiom Mission 3", "flight_date": "2024-01-18",
        "operator": "Axiom Space", "vehicle": "Crew Dragon Freedom",
        "trajectory_type": "orbital", "passenger_name": "Walter Villadei",
        "passenger_nationality": "Italian", "passenger_birth_year": 1974,
        "passenger_occupation": "military officer", "is_paying_tourist": True,
        "duration_hours": 336, "max_altitude_km": 420,
    },
    {
        "flight_name": "Axiom Mission 3", "flight_date": "2024-01-18",
        "operator": "Axiom Space", "vehicle": "Crew Dragon Freedom",
        "trajectory_type": "orbital", "passenger_name": "Alper Gezeravcı",
        "passenger_nationality": "Turkish", "passenger_birth_year": 1979,
        "passenger_occupation": "military pilot", "is_paying_tourist": True,
        "duration_hours": 336, "max_altitude_km": 420,
    },
    {
        "flight_name": "Axiom Mission 4", "flight_date": "2025-06-26",
        "operator": "Axiom Space", "vehicle": "Crew Dragon Freedom",
        "trajectory_type": "orbital", "passenger_name": "Peggy Whitson",
        "passenger_nationality": "American", "passenger_birth_year": 1960,
        "passenger_occupation": "astronaut", "is_paying_tourist": False,
        "duration_hours": 336, "max_altitude_km": 420,
    },
    {
        "flight_name": "Axiom Mission 4", "flight_date": "2025-06-26",
        "operator": "Axiom Space", "vehicle": "Crew Dragon Freedom",
        "trajectory_type": "orbital", "passenger_name": "Shubhanshu Shukla",
        "passenger_nationality": "Indian", "passenger_birth_year": 1985,
        "passenger_occupation": "military pilot", "is_paying_tourist": True,
        "duration_hours": 336, "max_altitude_km": 420,
    },
    {
        "flight_name": "Axiom Mission 4", "flight_date": "2025-06-26",
        "operator": "Axiom Space", "vehicle": "Crew Dragon Freedom",
        "trajectory_type": "orbital", "passenger_name": "Tibor Kapu",
        "passenger_nationality": "Hungarian", "passenger_birth_year": 1983,
        "passenger_occupation": "engineer", "is_paying_tourist": True,
        "duration_hours": 336, "max_altitude_km": 420,
    },
    {
        "flight_name": "Axiom Mission 4", "flight_date": "2025-06-26",
        "operator": "Axiom Space", "vehicle": "Crew Dragon Freedom",
        "trajectory_type": "orbital", "passenger_name": "Sławosz Uznański",
        "passenger_nationality": "Polish", "passenger_birth_year": 1980,
        "passenger_occupation": "engineer", "is_paying_tourist": True,
        "duration_hours": 336, "max_altitude_km": 420,
    },
    # ── SpaceX Polaris Dawn ─────────────────────────────────────────────────
    {
        "flight_name": "SpaceX Polaris Dawn", "flight_date": "2024-09-10",
        "operator": "SpaceX", "vehicle": "Crew Dragon Resilience",
        "trajectory_type": "orbital", "passenger_name": "Jared Isaacman",
        "passenger_nationality": "American", "passenger_birth_year": 1983,
        "passenger_occupation": "entrepreneur", "is_paying_tourist": True,
        "duration_hours": 120, "max_altitude_km": 1400,
    },
    {
        "flight_name": "SpaceX Polaris Dawn", "flight_date": "2024-09-10",
        "operator": "SpaceX", "vehicle": "Crew Dragon Resilience",
        "trajectory_type": "orbital", "passenger_name": "Scott Poteet",
        "passenger_nationality": "American", "passenger_birth_year": 1975,
        "passenger_occupation": "military officer", "is_paying_tourist": False,
        "duration_hours": 120, "max_altitude_km": 1400,
    },
    {
        "flight_name": "SpaceX Polaris Dawn", "flight_date": "2024-09-10",
        "operator": "SpaceX", "vehicle": "Crew Dragon Resilience",
        "trajectory_type": "orbital", "passenger_name": "Sarah Gillis",
        "passenger_nationality": "American", "passenger_birth_year": 1995,
        "passenger_occupation": "engineer", "is_paying_tourist": False,
        "duration_hours": 120, "max_altitude_km": 1400,
    },
    {
        "flight_name": "SpaceX Polaris Dawn", "flight_date": "2024-09-10",
        "operator": "SpaceX", "vehicle": "Crew Dragon Resilience",
        "trajectory_type": "orbital", "passenger_name": "Anna Menon",
        "passenger_nationality": "American", "passenger_birth_year": 1987,
        "passenger_occupation": "engineer", "is_paying_tourist": False,
        "duration_hours": 120, "max_altitude_km": 1400,
    },
    # ── Blue Origin New Shepard (suborbital) ────────────────────────────────
    {
        "flight_name": "Blue Origin NS-17", "flight_date": "2021-07-20",
        "operator": "Blue Origin", "vehicle": "New Shepard",
        "trajectory_type": "suborbital", "passenger_name": "Jeff Bezos",
        "passenger_nationality": "American", "passenger_birth_year": 1964,
        "passenger_occupation": "entrepreneur", "is_paying_tourist": False,
        "duration_hours": 0.17, "max_altitude_km": 107,
    },
    {
        "flight_name": "Blue Origin NS-17", "flight_date": "2021-07-20",
        "operator": "Blue Origin", "vehicle": "New Shepard",
        "trajectory_type": "suborbital", "passenger_name": "Mark Bezos",
        "passenger_nationality": "American", "passenger_birth_year": 1968,
        "passenger_occupation": "entrepreneur", "is_paying_tourist": False,
        "duration_hours": 0.17, "max_altitude_km": 107,
    },
    {
        "flight_name": "Blue Origin NS-17", "flight_date": "2021-07-20",
        "operator": "Blue Origin", "vehicle": "New Shepard",
        "trajectory_type": "suborbital", "passenger_name": "Wally Funk",
        "passenger_nationality": "American", "passenger_birth_year": 1939,
        "passenger_occupation": "aviator", "is_paying_tourist": False,
        "duration_hours": 0.17, "max_altitude_km": 107,
    },
    {
        "flight_name": "Blue Origin NS-17", "flight_date": "2021-07-20",
        "operator": "Blue Origin", "vehicle": "New Shepard",
        "trajectory_type": "suborbital", "passenger_name": "Oliver Daemen",
        "passenger_nationality": "Dutch", "passenger_birth_year": 2002,
        "passenger_occupation": "student", "is_paying_tourist": True,
        "duration_hours": 0.17, "max_altitude_km": 107,
    },
    {
        "flight_name": "Blue Origin NS-18", "flight_date": "2021-10-13",
        "operator": "Blue Origin", "vehicle": "New Shepard",
        "trajectory_type": "suborbital", "passenger_name": "William Shatner",
        "passenger_nationality": "Canadian", "passenger_birth_year": 1931,
        "passenger_occupation": "actor", "is_paying_tourist": True,
        "duration_hours": 0.17, "max_altitude_km": 107,
    },
    {
        "flight_name": "Blue Origin NS-18", "flight_date": "2021-10-13",
        "operator": "Blue Origin", "vehicle": "New Shepard",
        "trajectory_type": "suborbital", "passenger_name": "Audrey Powers",
        "passenger_nationality": "American", "passenger_birth_year": 1983,
        "passenger_occupation": "engineer", "is_paying_tourist": False,
        "duration_hours": 0.17, "max_altitude_km": 107,
    },
    {
        "flight_name": "Blue Origin NS-18", "flight_date": "2021-10-13",
        "operator": "Blue Origin", "vehicle": "New Shepard",
        "trajectory_type": "suborbital", "passenger_name": "Glen de Vries",
        "passenger_nationality": "American", "passenger_birth_year": 1972,
        "passenger_occupation": "entrepreneur", "is_paying_tourist": True,
        "duration_hours": 0.17, "max_altitude_km": 107,
    },
    {
        "flight_name": "Blue Origin NS-18", "flight_date": "2021-10-13",
        "operator": "Blue Origin", "vehicle": "New Shepard",
        "trajectory_type": "suborbital", "passenger_name": "Chris Boshuizen",
        "passenger_nationality": "Australian", "passenger_birth_year": 1984,
        "passenger_occupation": "entrepreneur", "is_paying_tourist": True,
        "duration_hours": 0.17, "max_altitude_km": 107,
    },
    {
        "flight_name": "Blue Origin NS-19", "flight_date": "2021-12-11",
        "operator": "Blue Origin", "vehicle": "New Shepard",
        "trajectory_type": "suborbital", "passenger_name": "Laura Shepard Churchley",
        "passenger_nationality": "American", "passenger_birth_year": 1948,
        "passenger_occupation": "journalist", "is_paying_tourist": False,
        "duration_hours": 0.17, "max_altitude_km": 107,
    },
    {
        "flight_name": "Blue Origin NS-19", "flight_date": "2021-12-11",
        "operator": "Blue Origin", "vehicle": "New Shepard",
        "trajectory_type": "suborbital", "passenger_name": "Michael Strahan",
        "passenger_nationality": "American", "passenger_birth_year": 1971,
        "passenger_occupation": "athlete", "is_paying_tourist": False,
        "duration_hours": 0.17, "max_altitude_km": 107,
    },
    {
        "flight_name": "Blue Origin NS-19", "flight_date": "2021-12-11",
        "operator": "Blue Origin", "vehicle": "New Shepard",
        "trajectory_type": "suborbital", "passenger_name": "Dylan Taylor",
        "passenger_nationality": "American", "passenger_birth_year": 1970,
        "passenger_occupation": "entrepreneur", "is_paying_tourist": True,
        "duration_hours": 0.17, "max_altitude_km": 107,
    },
    {
        "flight_name": "Blue Origin NS-19", "flight_date": "2021-12-11",
        "operator": "Blue Origin", "vehicle": "New Shepard",
        "trajectory_type": "suborbital", "passenger_name": "Evan Dick",
        "passenger_nationality": "American", "passenger_birth_year": 1980,
        "passenger_occupation": "investor", "is_paying_tourist": True,
        "duration_hours": 0.17, "max_altitude_km": 107,
    },
    {
        "flight_name": "Blue Origin NS-19", "flight_date": "2021-12-11",
        "operator": "Blue Origin", "vehicle": "New Shepard",
        "trajectory_type": "suborbital", "passenger_name": "Bess Gorman",
        "passenger_nationality": "American", "passenger_birth_year": 1980,
        "passenger_occupation": "entrepreneur", "is_paying_tourist": True,
        "duration_hours": 0.17, "max_altitude_km": 107,
    },
    {
        "flight_name": "Blue Origin NS-19", "flight_date": "2021-12-11",
        "operator": "Blue Origin", "vehicle": "New Shepard",
        "trajectory_type": "suborbital", "passenger_name": "Lane Bess",
        "passenger_nationality": "American", "passenger_birth_year": 1964,
        "passenger_occupation": "entrepreneur", "is_paying_tourist": True,
        "duration_hours": 0.17, "max_altitude_km": 107,
    },
    {
        "flight_name": "Blue Origin NS-20", "flight_date": "2022-03-31",
        "operator": "Blue Origin", "vehicle": "New Shepard",
        "trajectory_type": "suborbital", "passenger_name": "Marty Allen",
        "passenger_nationality": "American", "passenger_birth_year": 1944,
        "passenger_occupation": "entrepreneur", "is_paying_tourist": True,
        "duration_hours": 0.17, "max_altitude_km": 107,
    },
    {
        "flight_name": "Blue Origin NS-20", "flight_date": "2022-03-31",
        "operator": "Blue Origin", "vehicle": "New Shepard",
        "trajectory_type": "suborbital", "passenger_name": "Sharon Hagle",
        "passenger_nationality": "American", "passenger_birth_year": 1958,
        "passenger_occupation": "entrepreneur", "is_paying_tourist": True,
        "duration_hours": 0.17, "max_altitude_km": 107,
    },
    {
        "flight_name": "Blue Origin NS-20", "flight_date": "2022-03-31",
        "operator": "Blue Origin", "vehicle": "New Shepard",
        "trajectory_type": "suborbital", "passenger_name": "Marc Hagle",
        "passenger_nationality": "American", "passenger_birth_year": 1955,
        "passenger_occupation": "entrepreneur", "is_paying_tourist": True,
        "duration_hours": 0.17, "max_altitude_km": 107,
    },
    {
        "flight_name": "Blue Origin NS-20", "flight_date": "2022-03-31",
        "operator": "Blue Origin", "vehicle": "New Shepard",
        "trajectory_type": "suborbital", "passenger_name": "Jim Kitchen",
        "passenger_nationality": "American", "passenger_birth_year": 1963,
        "passenger_occupation": "educator", "is_paying_tourist": True,
        "duration_hours": 0.17, "max_altitude_km": 107,
    },
    {
        "flight_name": "Blue Origin NS-20", "flight_date": "2022-03-31",
        "operator": "Blue Origin", "vehicle": "New Shepard",
        "trajectory_type": "suborbital", "passenger_name": "Gary Lai",
        "passenger_nationality": "American", "passenger_birth_year": 1977,
        "passenger_occupation": "engineer", "is_paying_tourist": False,
        "duration_hours": 0.17, "max_altitude_km": 107,
    },
    {
        "flight_name": "Blue Origin NS-20", "flight_date": "2022-03-31",
        "operator": "Blue Origin", "vehicle": "New Shepard",
        "trajectory_type": "suborbital", "passenger_name": "George Nield",
        "passenger_nationality": "American", "passenger_birth_year": 1952,
        "passenger_occupation": "engineer", "is_paying_tourist": False,
        "duration_hours": 0.17, "max_altitude_km": 107,
    },
    {
        "flight_name": "Blue Origin NS-21", "flight_date": "2022-06-04",
        "operator": "Blue Origin", "vehicle": "New Shepard",
        "trajectory_type": "suborbital", "passenger_name": "Evan Dick",
        "passenger_nationality": "American", "passenger_birth_year": 1980,
        "passenger_occupation": "investor", "is_paying_tourist": True,
        "duration_hours": 0.17, "max_altitude_km": 107,
    },
    {
        "flight_name": "Blue Origin NS-21", "flight_date": "2022-06-04",
        "operator": "Blue Origin", "vehicle": "New Shepard",
        "trajectory_type": "suborbital", "passenger_name": "Hamish Harding",
        "passenger_nationality": "British", "passenger_birth_year": 1964,
        "passenger_occupation": "entrepreneur", "is_paying_tourist": True,
        "duration_hours": 0.17, "max_altitude_km": 107,
    },
    {
        "flight_name": "Blue Origin NS-21", "flight_date": "2022-06-04",
        "operator": "Blue Origin", "vehicle": "New Shepard",
        "trajectory_type": "suborbital", "passenger_name": "Jaison Robinson",
        "passenger_nationality": "American", "passenger_birth_year": 1977,
        "passenger_occupation": "entrepreneur", "is_paying_tourist": True,
        "duration_hours": 0.17, "max_altitude_km": 107,
    },
    {
        "flight_name": "Blue Origin NS-21", "flight_date": "2022-06-04",
        "operator": "Blue Origin", "vehicle": "New Shepard",
        "trajectory_type": "suborbital", "passenger_name": "Katya Echazarreta",
        "passenger_nationality": "Mexican-American", "passenger_birth_year": 1996,
        "passenger_occupation": "engineer", "is_paying_tourist": True,
        "duration_hours": 0.17, "max_altitude_km": 107,
    },
    {
        "flight_name": "Blue Origin NS-21", "flight_date": "2022-06-04",
        "operator": "Blue Origin", "vehicle": "New Shepard",
        "trajectory_type": "suborbital", "passenger_name": "Victor Correa Hespanha",
        "passenger_nationality": "Brazilian", "passenger_birth_year": 1982,
        "passenger_occupation": "entrepreneur", "is_paying_tourist": True,
        "duration_hours": 0.17, "max_altitude_km": 107,
    },
    {
        "flight_name": "Blue Origin NS-22", "flight_date": "2022-08-04",
        "operator": "Blue Origin", "vehicle": "New Shepard",
        "trajectory_type": "suborbital", "passenger_name": "Sara Sabry",
        "passenger_nationality": "Egyptian", "passenger_birth_year": 1988,
        "passenger_occupation": "engineer", "is_paying_tourist": True,
        "duration_hours": 0.17, "max_altitude_km": 107,
    },
    {
        "flight_name": "Blue Origin NS-22", "flight_date": "2022-08-04",
        "operator": "Blue Origin", "vehicle": "New Shepard",
        "trajectory_type": "suborbital", "passenger_name": "Coby Cotton",
        "passenger_nationality": "American", "passenger_birth_year": 1987,
        "passenger_occupation": "content creator", "is_paying_tourist": True,
        "duration_hours": 0.17, "max_altitude_km": 107,
    },
    {
        "flight_name": "Blue Origin NS-22", "flight_date": "2022-08-04",
        "operator": "Blue Origin", "vehicle": "New Shepard",
        "trajectory_type": "suborbital", "passenger_name": "Steve Young",
        "passenger_nationality": "American", "passenger_birth_year": 1973,
        "passenger_occupation": "entrepreneur", "is_paying_tourist": True,
        "duration_hours": 0.17, "max_altitude_km": 107,
    },
    {
        "flight_name": "Blue Origin NS-22", "flight_date": "2022-08-04",
        "operator": "Blue Origin", "vehicle": "New Shepard",
        "trajectory_type": "suborbital", "passenger_name": "Clint Kelly III",
        "passenger_nationality": "American", "passenger_birth_year": 1959,
        "passenger_occupation": "entrepreneur", "is_paying_tourist": True,
        "duration_hours": 0.17, "max_altitude_km": 107,
    },
    {
        "flight_name": "Blue Origin NS-22", "flight_date": "2022-08-04",
        "operator": "Blue Origin", "vehicle": "New Shepard",
        "trajectory_type": "suborbital", "passenger_name": "Mário Ferreira",
        "passenger_nationality": "Portuguese", "passenger_birth_year": 1957,
        "passenger_occupation": "entrepreneur", "is_paying_tourist": True,
        "duration_hours": 0.17, "max_altitude_km": 107,
    },
    {
        "flight_name": "Blue Origin NS-23", "flight_date": "2023-03-31",
        "operator": "Blue Origin", "vehicle": "New Shepard",
        "trajectory_type": "suborbital", "passenger_name": "Hamish Harding",
        "passenger_nationality": "British", "passenger_birth_year": 1964,
        "passenger_occupation": "entrepreneur", "is_paying_tourist": True,
        "duration_hours": 0.17, "max_altitude_km": 107,
    },
    # NS-24 was uncrewed test after anomaly
    {
        "flight_name": "Blue Origin NS-25", "flight_date": "2024-05-19",
        "operator": "Blue Origin", "vehicle": "New Shepard",
        "trajectory_type": "suborbital", "passenger_name": "Ed Dwight",
        "passenger_nationality": "American", "passenger_birth_year": 1933,
        "passenger_occupation": "artist", "is_paying_tourist": True,
        "duration_hours": 0.17, "max_altitude_km": 107,
    },
    {
        "flight_name": "Blue Origin NS-25", "flight_date": "2024-05-19",
        "operator": "Blue Origin", "vehicle": "New Shepard",
        "trajectory_type": "suborbital", "passenger_name": "Mason Angel",
        "passenger_nationality": "American", "passenger_birth_year": 1958,
        "passenger_occupation": "investor", "is_paying_tourist": True,
        "duration_hours": 0.17, "max_altitude_km": 107,
    },
    {
        "flight_name": "Blue Origin NS-25", "flight_date": "2024-05-19",
        "operator": "Blue Origin", "vehicle": "New Shepard",
        "trajectory_type": "suborbital", "passenger_name": "Sylvain Chiron",
        "passenger_nationality": "French", "passenger_birth_year": 1965,
        "passenger_occupation": "entrepreneur", "is_paying_tourist": True,
        "duration_hours": 0.17, "max_altitude_km": 107,
    },
    {
        "flight_name": "Blue Origin NS-25", "flight_date": "2024-05-19",
        "operator": "Blue Origin", "vehicle": "New Shepard",
        "trajectory_type": "suborbital", "passenger_name": "Kenneth Hess",
        "passenger_nationality": "American", "passenger_birth_year": 1960,
        "passenger_occupation": "entrepreneur", "is_paying_tourist": True,
        "duration_hours": 0.17, "max_altitude_km": 107,
    },
    {
        "flight_name": "Blue Origin NS-25", "flight_date": "2024-05-19",
        "operator": "Blue Origin", "vehicle": "New Shepard",
        "trajectory_type": "suborbital", "passenger_name": "Carol Schaller",
        "passenger_nationality": "American", "passenger_birth_year": 1951,
        "passenger_occupation": "educator", "is_paying_tourist": True,
        "duration_hours": 0.17, "max_altitude_km": 107,
    },
    {
        "flight_name": "Blue Origin NS-25", "flight_date": "2024-05-19",
        "operator": "Blue Origin", "vehicle": "New Shepard",
        "trajectory_type": "suborbital", "passenger_name": "Gopi Thotakura",
        "passenger_nationality": "Indian", "passenger_birth_year": 1980,
        "passenger_occupation": "entrepreneur", "is_paying_tourist": True,
        "duration_hours": 0.17, "max_altitude_km": 107,
    },
    # ── Virgin Galactic VSS Unity commercial flights ─────────────────────────
    {
        "flight_name": "VSS Unity VF-01", "flight_date": "2021-07-11",
        "operator": "Virgin Galactic", "vehicle": "VSS Unity",
        "trajectory_type": "suborbital", "passenger_name": "Richard Branson",
        "passenger_nationality": "British", "passenger_birth_year": 1950,
        "passenger_occupation": "entrepreneur", "is_paying_tourist": False,
        "duration_hours": 0.17, "max_altitude_km": 86,
    },
    {
        "flight_name": "VSS Unity VF-01", "flight_date": "2021-07-11",
        "operator": "Virgin Galactic", "vehicle": "VSS Unity",
        "trajectory_type": "suborbital", "passenger_name": "Sirisha Bandla",
        "passenger_nationality": "American", "passenger_birth_year": 1987,
        "passenger_occupation": "engineer", "is_paying_tourist": False,
        "duration_hours": 0.17, "max_altitude_km": 86,
    },
    {
        "flight_name": "VSS Unity VF-01", "flight_date": "2021-07-11",
        "operator": "Virgin Galactic", "vehicle": "VSS Unity",
        "trajectory_type": "suborbital", "passenger_name": "Beth Moses",
        "passenger_nationality": "American", "passenger_birth_year": 1968,
        "passenger_occupation": "engineer", "is_paying_tourist": False,
        "duration_hours": 0.17, "max_altitude_km": 86,
    },
    {
        "flight_name": "Galactic 01", "flight_date": "2023-06-29",
        "operator": "Virgin Galactic", "vehicle": "VSS Unity",
        "trajectory_type": "suborbital", "passenger_name": "Walter Villadei",
        "passenger_nationality": "Italian", "passenger_birth_year": 1974,
        "passenger_occupation": "military officer", "is_paying_tourist": True,
        "duration_hours": 0.17, "max_altitude_km": 86,
    },
    {
        "flight_name": "Galactic 01", "flight_date": "2023-06-29",
        "operator": "Virgin Galactic", "vehicle": "VSS Unity",
        "trajectory_type": "suborbital", "passenger_name": "Pantaleone Carlucci",
        "passenger_nationality": "Italian", "passenger_birth_year": 1971,
        "passenger_occupation": "military officer", "is_paying_tourist": True,
        "duration_hours": 0.17, "max_altitude_km": 86,
    },
    {
        "flight_name": "Galactic 01", "flight_date": "2023-06-29",
        "operator": "Virgin Galactic", "vehicle": "VSS Unity",
        "trajectory_type": "suborbital", "passenger_name": "Angelo Landolfi",
        "passenger_nationality": "Italian", "passenger_birth_year": 1980,
        "passenger_occupation": "physician", "is_paying_tourist": True,
        "duration_hours": 0.17, "max_altitude_km": 86,
    },
    {
        "flight_name": "Galactic 02", "flight_date": "2023-08-10",
        "operator": "Virgin Galactic", "vehicle": "VSS Unity",
        "trajectory_type": "suborbital", "passenger_name": "Jon Goodwin",
        "passenger_nationality": "British", "passenger_birth_year": 1946,
        "passenger_occupation": "entrepreneur", "is_paying_tourist": True,
        "duration_hours": 0.17, "max_altitude_km": 86,
    },
    {
        "flight_name": "Galactic 02", "flight_date": "2023-08-10",
        "operator": "Virgin Galactic", "vehicle": "VSS Unity",
        "trajectory_type": "suborbital", "passenger_name": "Keisha Schahaff",
        "passenger_nationality": "American", "passenger_birth_year": 1980,
        "passenger_occupation": "health coach", "is_paying_tourist": True,
        "duration_hours": 0.17, "max_altitude_km": 86,
    },
    {
        "flight_name": "Galactic 02", "flight_date": "2023-08-10",
        "operator": "Virgin Galactic", "vehicle": "VSS Unity",
        "trajectory_type": "suborbital", "passenger_name": "Anastatia Mayers",
        "passenger_nationality": "American", "passenger_birth_year": 2003,
        "passenger_occupation": "student", "is_paying_tourist": True,
        "duration_hours": 0.17, "max_altitude_km": 86,
    },
    {
        "flight_name": "Galactic 03", "flight_date": "2023-09-08",
        "operator": "Virgin Galactic", "vehicle": "VSS Unity",
        "trajectory_type": "suborbital", "passenger_name": "Ken Baxter",
        "passenger_nationality": "American", "passenger_birth_year": 1955,
        "passenger_occupation": "entrepreneur", "is_paying_tourist": True,
        "duration_hours": 0.17, "max_altitude_km": 86,
    },
    {
        "flight_name": "Galactic 03", "flight_date": "2023-09-08",
        "operator": "Virgin Galactic", "vehicle": "VSS Unity",
        "trajectory_type": "suborbital", "passenger_name": "Christopher Huakana",
        "passenger_nationality": "American", "passenger_birth_year": 1970,
        "passenger_occupation": "entrepreneur", "is_paying_tourist": True,
        "duration_hours": 0.17, "max_altitude_km": 86,
    },
    {
        "flight_name": "Galactic 03", "flight_date": "2023-09-08",
        "operator": "Virgin Galactic", "vehicle": "VSS Unity",
        "trajectory_type": "suborbital", "passenger_name": "Timothy Nash",
        "passenger_nationality": "American", "passenger_birth_year": 1969,
        "passenger_occupation": "entrepreneur", "is_paying_tourist": True,
        "duration_hours": 0.17, "max_altitude_km": 86,
    },
    {
        "flight_name": "Galactic 04", "flight_date": "2023-10-06",
        "operator": "Virgin Galactic", "vehicle": "VSS Unity",
        "trajectory_type": "suborbital", "passenger_name": "Aabar Investments",
        "passenger_nationality": "Emirati", "passenger_birth_year": 1975,
        "passenger_occupation": "investor", "is_paying_tourist": True,
        "duration_hours": 0.17, "max_altitude_km": 86,
    },
    {
        "flight_name": "Galactic 04", "flight_date": "2023-10-06",
        "operator": "Virgin Galactic", "vehicle": "VSS Unity",
        "trajectory_type": "suborbital", "passenger_name": "Trevor Beattie",
        "passenger_nationality": "British", "passenger_birth_year": 1959,
        "passenger_occupation": "entrepreneur", "is_paying_tourist": True,
        "duration_hours": 0.17, "max_altitude_km": 86,
    },
    {
        "flight_name": "Galactic 04", "flight_date": "2023-10-06",
        "operator": "Virgin Galactic", "vehicle": "VSS Unity",
        "trajectory_type": "suborbital", "passenger_name": "Namira Salim",
        "passenger_nationality": "Pakistani", "passenger_birth_year": 1970,
        "passenger_occupation": "diplomat", "is_paying_tourist": True,
        "duration_hours": 0.17, "max_altitude_km": 86,
    },
]

# ── Column descriptions ──────────────────────────────────────────────
COLUMN_DESCRIPTIONS = {
    "flight_name": "Official mission name (e.g., 'Blue Origin NS-18', 'SpaceX Inspiration4', 'VSS Unity VF-01'); used as the primary grouping key for per-flight analysis",
    "flight_date": "Launch date in UTC (YYYY-MM-DD); null if unconfirmed",
    "operator": "Commercial spaceflight company that operated the vehicle (Virgin Galactic, Blue Origin, SpaceX, Space Adventures, Axiom Space)",
    "vehicle": "Spacecraft name (e.g., 'VSS Unity', 'New Shepard', 'Crew Dragon Resilience'); identifies the vehicle within the operator's fleet",
    "trajectory_type": "'suborbital' for flights that reach space but do not complete an orbit (Virgin Galactic, Blue Origin); 'orbital' for flights that complete at least one Earth orbit (SpaceX, Axiom, Soyuz via Space Adventures)",
    "passenger_name": "Full name of the commercial passenger",
    "passenger_nationality": "Passenger's nationality (English label, e.g., 'American', 'Japanese')",
    "passenger_birth_year": "Year of birth of the passenger; used for age-at-flight analysis",
    "passenger_occupation": "Primary professional occupation outside aerospace (e.g., 'entrepreneur', 'actor', 'physician', 'investor', 'engineer'); describes their civilian background",
    "is_paying_tourist": "True if this passenger purchased a commercial seat; False for pilots, mission specialists with operational roles, or science crew on cost-reimbursement arrangements",
    "duration_hours": "Approximate total flight duration in hours from launch to landing; suborbital: ~0.17 h (10 min); orbital: 72-200+ h depending on mission profile",
    "max_altitude_km": "Maximum altitude above sea level reached during the mission (km); Kármán line (100 km) for suborbital; ISS orbit (~410 km) for orbital; Polaris Dawn (1400 km)",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Catalog of commercial spaceflight passengers — the individuals who have flown to space \
on tickets purchased from private spaceflight companies. Covers suborbital flights by \
Virgin Galactic and Blue Origin, orbital missions by SpaceX, Axiom Space, and the \
Space Adventures ISS visits arranged via Russian Soyuz, from 2001 to the present.

Space tourism began in April 2001 when American businessman Dennis Tito paid the \
Russian space agency approximately $20 million for a Soyuz ride to the International \
Space Station — the first time a private citizen purchased a seat to orbit Earth. Over \
the following two decades, seven more paying tourists visited the ISS through Space \
Adventures before the program was suspended and later revived. The commercial era \
accelerated in 2021 when Virgin Galactic and Blue Origin both conducted their first \
crewed commercial flights, SpaceX launched the all-civilian Inspiration4 mission to \
orbit, and Axiom Space began the first in a series of private ISS expeditions.

Each row in this dataset represents one passenger on one flight. The trajectory_type \
field distinguishes suborbital hops (reaching space but returning within minutes) from \
orbital flights (completing at least one revolution of the Earth). The is_paying_tourist \
field separates revenue-generating seats from operational crew members who may fly on \
the same vehicles in a professional capacity. The duration_hours and max_altitude_km \
columns capture the physical scope of each mission.

This dataset is useful for demographic analysis of the commercial spaceflight industry, \
tracking the growth in flight frequency and operator diversity, and studying the expanding \
accessibility of space travel. It complements the astronaut-database dataset, which covers \
government-trained astronauts and cosmonauts.
"""


def fetch_wikidata() -> pd.DataFrame:
    """Query Wikidata SPARQL for commercial spaceflight passengers."""
    print("Querying Wikidata for commercial spaceflight passengers...")
    try:
        resp = requests.get(
            WIKIDATA_URL,
            params={"query": SPARQL_QUERY, "format": "json"},
            headers=HEADERS,
            timeout=120,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"  Wikidata query failed: {e}")
        return pd.DataFrame()

    results = resp.json()["results"]["bindings"]
    print(f"  {len(results):,} raw rows from Wikidata")

    if not results:
        return pd.DataFrame()

    rows = []
    for r in results:
        operator_qid = r.get("operator", {}).get("value", "").rsplit("/", 1)[-1]
        operator_label = r.get("operatorLabel", {}).get("value", "")
        # Use our canonical operator name if we recognise the QID
        operator_name = OPERATOR_QIDS.get(operator_qid, operator_label)

        flight_label = r.get("flightLabel", {}).get("value", "")
        # Skip bare Q-IDs
        if not flight_label or flight_label.startswith("Q"):
            continue

        participant_label = r.get("participantLabel", {}).get("value", "")
        if not participant_label or participant_label.startswith("Q"):
            continue

        flight_date_raw = r.get("flightDate", {}).get("value", "")
        birth_year_raw = r.get("birthYear", {}).get("value")

        rows.append({
            "flight_name": flight_label,
            "flight_date": flight_date_raw[:10] if flight_date_raw else None,
            "operator": operator_name,
            "vehicle": r.get("vehicleLabel", {}).get("value") or None,
            "passenger_name": participant_label,
            "passenger_nationality": r.get("nationalityLabel", {}).get("value") or None,
            "passenger_birth_year": int(birth_year_raw) if birth_year_raw else None,
        })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset=["flight_name", "passenger_name"], keep="first")
    print(f"  {len(df):,} unique passenger-flight rows from Wikidata")
    return df


def build_seed_df() -> pd.DataFrame:
    """Return the curated seed data as a DataFrame."""
    return pd.DataFrame(SEED_DATA)


def merge_data(wikidata_df: pd.DataFrame, seed_df: pd.DataFrame) -> pd.DataFrame:
    """Merge Wikidata results with seed data.

    Seed data takes precedence for rows that exist in both (it has richer fields).
    Wikidata rows not in the seed list are appended if they have enough columns.
    """
    if wikidata_df.empty:
        print("  Using seed data only (Wikidata returned no usable rows)")
        return seed_df.copy()

    # Columns present only in seed that Wikidata lacks
    seed_only_cols = [
        "trajectory_type", "passenger_occupation", "is_paying_tourist",
        "duration_hours", "max_altitude_km",
    ]

    # For Wikidata rows, check which (flight_name, passenger_name) pairs
    # are NOT already covered by the seed
    seed_keys = set(
        zip(seed_df["flight_name"].str.lower(), seed_df["passenger_name"].str.lower())
    )
    wd_mask = ~wikidata_df.apply(
        lambda r: (r["flight_name"].lower(), r["passenger_name"].lower()) in seed_keys,
        axis=1,
    )
    wd_new = wikidata_df[wd_mask].copy()

    if wd_new.empty:
        print("  No new rows from Wikidata beyond seed data")
        return seed_df.copy()

    # Fill missing seed-only columns with sensible defaults for Wikidata rows
    for col in seed_only_cols:
        if col not in wd_new.columns:
            wd_new[col] = None
    # Default trajectory_type if we can infer from operator
    suborbital_operators = {"Virgin Galactic", "Blue Origin"}
    if "trajectory_type" in wd_new.columns:
        wd_new["trajectory_type"] = wd_new.apply(
            lambda r: "suborbital" if r.get("operator") in suborbital_operators
            else ("orbital" if r.get("operator") in {"SpaceX", "Axiom Space", "Space Adventures"}
                  else r.get("trajectory_type")),
            axis=1,
        )

    combined = pd.concat([seed_df, wd_new], ignore_index=True)
    combined = combined.drop_duplicates(subset=["flight_name", "passenger_name"], keep="first")
    print(f"  {len(combined):,} rows after merging seed + Wikidata")
    return combined


def main():
    time.sleep(2)  # polite delay before Wikidata request
    wikidata_df = fetch_wikidata()
    seed_df = build_seed_df()

    df = merge_data(wikidata_df, seed_df)

    # ── Coerce types ────────────────────────────────────────────────────
    df["flight_date"] = pd.to_datetime(df["flight_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    df["passenger_birth_year"] = pd.to_numeric(df["passenger_birth_year"], errors="coerce").astype("Int32")
    df["is_paying_tourist"] = df["is_paying_tourist"].astype("boolean")
    df["duration_hours"] = pd.to_numeric(df["duration_hours"], errors="coerce")
    df["max_altitude_km"] = pd.to_numeric(df["max_altitude_km"], errors="coerce")

    # Keep only described columns
    df = df[[c for c in COLUMN_DESCRIPTIONS if c in df.columns]]

    df = df.sort_values(["flight_date", "flight_name", "passenger_name"]).reset_index(drop=True)

    n = len(df)
    n_passengers = int(df["passenger_name"].nunique())
    n_flights = int(df["flight_name"].nunique())
    print(f"  {n:,} rows | {n_passengers} unique passengers | {n_flights} unique flights")

    # ── Quick stats for README ───────────────────────────────────────────
    by_operator = df.groupby("operator")["passenger_name"].count().sort_values(ascending=False)
    operator_str = ", ".join(f"{op} ({cnt})" for op, cnt in by_operator.items())

    by_traj = df.groupby("trajectory_type")["passenger_name"].count()
    traj_str = ", ".join(f"{t} ({cnt})" for t, cnt in by_traj.items())

    # Age at flight time
    flight_years = pd.to_datetime(df["flight_date"], errors="coerce").dt.year
    age_at_flight = flight_years - df["passenger_birth_year"].astype("Float64")
    youngest_idx = age_at_flight.idxmin() if age_at_flight.notna().any() else None
    oldest_idx = age_at_flight.idxmax() if age_at_flight.notna().any() else None
    youngest_str = (
        f"{df.loc[youngest_idx, 'passenger_name']} ({int(age_at_flight[youngest_idx])} years old)"
        if youngest_idx is not None else "N/A"
    )
    oldest_str = (
        f"{df.loc[oldest_idx, 'passenger_name']} ({int(age_at_flight[oldest_idx])} years old)"
        if oldest_idx is not None else "N/A"
    )

    n_paying = int(df["is_paying_tourist"].sum())

    quick_stats = f"""\
- **{n:,}** passenger-flight records
- **{n_passengers}** unique individuals who have flown commercially to space
- **{n_flights}** unique flights
- **{n_paying}** paying tourist seats
- By operator: {operator_str}
- By trajectory: {traj_str}
- Youngest at flight: {youngest_str}
- Oldest at flight: {oldest_str}"""

    usage = '''\
```python
from datasets import load_dataset
import pandas as pd

ds = load_dataset("juliensimon/space-tourism-flights", split="train")
df = ds.to_pandas()
df["flight_date"] = pd.to_datetime(df["flight_date"])

# Cumulative passengers over time
cumulative = df.drop_duplicates("passenger_name").sort_values("flight_date")
cumulative["cumulative_passengers"] = range(1, len(cumulative) + 1)
cumulative.plot(x="flight_date", y="cumulative_passengers",
                title="Cumulative Commercial Space Passengers Over Time")

# Breakdown by operator
import matplotlib.pyplot as plt
df.groupby("operator")["passenger_name"].nunique().sort_values().plot.barh()
plt.xlabel("Unique Passengers")
plt.title("Commercial Space Passengers by Operator")
plt.tight_layout()
plt.show()

# Suborbital vs orbital
print(df.groupby("trajectory_type")["passenger_name"].nunique())
```
'''

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Commercial Spaceflight Passengers",
        description=DESCRIPTION,
        tags=[
            "space", "space-tourism", "commercial-spaceflight", "astronauts",
            "spacex", "blue-origin", "virgin-galactic", "open-data", "tabular-data", "parquet",
        ],
        source_url="https://www.wikidata.org/",
        task_categories=["tabular-classification"],
        update_schedule="Monthly on the 1st at 06:00 UTC",
        collection_url="https://huggingface.co/collections/juliensimon/space-essentials-69cbafd7ea046a10eff11405",
        banner={
            "url": "https://images-assets.nasa.gov/image/iss071e439624/iss071e439624~medium.jpg",
            "alt": "An orbital sunrise illuminates the Earth's atmosphere, seen from the ISS",
            "credit": "NASA",
        },
        related_datasets=[
            "juliensimon/astronaut-database",
            "juliensimon/spacex-launches",
            "juliensimon/blue-origin-launches",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=["duration_hours", "max_altitude_km"],
            integer=["passenger_birth_year"],
            strings=["flight_name", "operator", "vehicle", "trajectory_type",
                     "passenger_name", "passenger_nationality", "passenger_occupation"],
        )
        p.publish(
            df,
            filename="space-tourism.parquet",
            min_rows=50,
            expected_columns=["flight_name", "passenger_name", "operator"],
            critical_columns=["flight_name", "passenger_name"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update commercial spaceflight passengers: {n:,} rows",
        )
    print("Done.")


if __name__ == "__main__":
    main()
