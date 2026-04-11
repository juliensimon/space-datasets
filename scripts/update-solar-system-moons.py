#!/usr/bin/env python3
"""Fetch all known natural satellites of planets and dwarf planets from JPL SSD
and upload to HF.

Sources:
  - JPL SSD Satellite Discovery:  https://ssd.jpl.nasa.gov/sats/discovery.html
  - JPL SSD Orbital Elements:     https://ssd.jpl.nasa.gov/sats/elem/
  - JPL SSD Physical Parameters:  https://ssd.jpl.nasa.gov/sats/phys_par/
"""

import time

import pandas as pd
import requests
from bs4 import BeautifulSoup

from hf_dataset_utils import Pipeline

HF_REPO = "juliensimon/solar-system-moons"
MIN_ROWS = 200

DISCOVERY_URL = "https://ssd.jpl.nasa.gov/sats/discovery.html"
ELEMENTS_URL = "https://ssd.jpl.nasa.gov/sats/elem/"
PHYS_PAR_URL = "https://ssd.jpl.nasa.gov/sats/phys_par/"

HEADERS = {"User-Agent": "SpaceDatasetsBot/1.0 (space-datasets HF pipeline)"}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "name": "IAU name or provisional designation",
    "parent_body": "Parent planet or dwarf planet",
    "iau_number": "IAU Roman numeral designation",
    "provisional_designation": "Survey designation (e.g. S/2003 J2)",
    "discovery_year": "Year of discovery",
    "discoverer": "Discoverer(s) or spacecraft mission",
    "group": "Dynamical group/family (e.g. Galilean, Himalia, Norse)",
    "semi_major_axis_km": "Mean orbital semi-major axis (km); ranges from ~128,000 km (Amalthea/Jupiter) to ~23.5 million km (Neso/Neptune)",
    "eccentricity": "Mean orbital eccentricity; regular (prograde) moons: <0.1; irregular (captured) moons: often 0.1\u20130.7",
    "inclination_deg": "Mean orbital inclination to the planet's equatorial plane (degrees, 0\u2013180); regular moons: <5\u00b0; irregular moons: can exceed 90\u00b0 (retrograde); see also is_retrograde",
    "orbital_period_days": "Sidereal orbital period (days); range ~0.29 days (Metis/Jupiter) to ~9,000 days (distant irregular moons); negative values indicate retrograde direction in some source conventions",
    "arg_periapsis_deg": "Argument of periapsis of the moon's orbit (degrees, 0\u2013360) at the reference epoch",
    "mean_anomaly_deg": "Mean anomaly at the reference epoch (degrees, 0\u2013360); used together with other elements to compute position",
    "long_ascending_node_deg": "Longitude of the ascending node (degrees, 0\u2013360) at the reference epoch",
    "epoch": "Reference epoch for the orbital elements in Barycentric Dynamical Time (TDB) format",
    "mean_radius_km": "Mean radius (km); available for major/well-characterised moons only; range <1 km (small inner moons) to 2,634 km (Ganymede); null for most irregular moons",
    "diameter_km": "Mean diameter (km) = 2 \u00d7 mean_radius_km; derived column; null when radius is null",
    "gm_km3s2": "Gravitational parameter GM = G \u00d7 mass (km\u00b3/s\u00b2); null for moons without a reliable mass determination",
    "mean_density_gcm3": "Mean bulk density (g/cm\u00b3); icy moons: ~1.0\u20132.0 g/cm\u00b3; rocky moons: ~2.5\u20133.5 g/cm\u00b3; null when mass and radius are not both known",
    "is_retrograde": "True if orbital inclination > 90\u00b0 (retrograde orbit); most retrograde moons are captured irregular bodies",
    "jpl_code": "JPL Horizons numeric satellite identifier used to query ephemerides",
}

# Moon group/family classification based on orbital characteristics
# Source: JPL + literature consensus
MOON_GROUPS = {
    # Jupiter groups
    "Metis": "Inner", "Adrastea": "Inner", "Amalthea": "Inner", "Thebe": "Inner",
    "Io": "Galilean", "Europa": "Galilean", "Ganymede": "Galilean",
    "Callisto": "Galilean",
    "Themisto": "Themisto",
    "Leda": "Himalia", "Himalia": "Himalia", "Ersa": "Himalia",
    "Lysithea": "Himalia", "Elara": "Himalia", "Dia": "Himalia",
    "Pandia": "Himalia",
    "Carpo": "Carpo", "Valetudo": "Valetudo",
    "Euporie": "Ananke", "Mneme": "Ananke", "Euanthe": "Ananke",
    "Harpalyke": "Ananke", "Praxidike": "Ananke", "Thyone": "Ananke",
    "Thelxinoe": "Ananke", "Helike": "Ananke", "Iocaste": "Ananke",
    "Ananke": "Ananke",
    "Hermippe": "Ananke",
    "Pasithee": "Carme", "Eurydome": "Carme", "Aitne": "Carme",
    "Chaldene": "Carme", "Isonoe": "Carme", "Erinome": "Carme",
    "Kale": "Carme", "Taygete": "Carme", "Carme": "Carme",
    "Kalyke": "Carme", "Arche": "Carme",
    "Pasiphae": "Pasiphae", "Callirrhoe": "Pasiphae",
    "Megaclite": "Pasiphae", "Sinope": "Pasiphae",
    "Hegemone": "Pasiphae", "Aoede": "Pasiphae",
    "Autonoe": "Pasiphae", "Cyllene": "Pasiphae", "Kore": "Pasiphae",
    # Saturn groups
    "Pan": "Inner", "Daphnis": "Inner", "Atlas": "Inner",
    "Prometheus": "Inner", "Pandora": "Inner",
    "Epimetheus": "Co-orbital", "Janus": "Co-orbital",
    "Aegaeon": "Inner", "Methone": "Inner", "Anthe": "Inner",
    "Pallene": "Inner",
    "Mimas": "Major", "Enceladus": "Major", "Tethys": "Major",
    "Dione": "Major", "Rhea": "Major",
    "Titan": "Major", "Hyperion": "Major", "Iapetus": "Major",
    "Phoebe": "Norse",
    "Telesto": "Trojan", "Calypso": "Trojan",
    "Helene": "Trojan", "Polydeuces": "Trojan",
    "Kiviuq": "Inuit", "Ijiraq": "Inuit", "Paaliaq": "Inuit",
    "Siarnaq": "Inuit", "Tarqeq": "Inuit",
    "Albiorix": "Gallic", "Bebhionn": "Gallic", "Erriapus": "Gallic",
    "Tarvos": "Gallic",
    "Skathi": "Norse", "Mundilfari": "Norse", "Narvi": "Norse",
    "Suttungr": "Norse", "Thrymr": "Norse", "Ymir": "Norse",
    "Surtur": "Norse", "Kari": "Norse", "Fenrir": "Norse",
    "Fornjot": "Norse", "Hati": "Norse", "Farbauti": "Norse",
    "Aegir": "Norse", "Bergelmir": "Norse", "Bestla": "Norse",
    "Hyrrokkin": "Norse", "Loge": "Norse", "Skoll": "Norse",
    "Greip": "Norse", "Jarnsaxa": "Norse",
    # Uranus groups
    "Cordelia": "Inner", "Ophelia": "Inner", "Bianca": "Inner",
    "Cressida": "Inner", "Desdemona": "Inner", "Juliet": "Inner",
    "Portia": "Inner", "Rosalind": "Inner", "Cupid": "Inner",
    "Belinda": "Inner", "Perdita": "Inner", "Puck": "Inner",
    "Mab": "Inner",
    "Miranda": "Major", "Ariel": "Major", "Umbriel": "Major",
    "Titania": "Major", "Oberon": "Major",
    "Francisco": "Irregular", "Caliban": "Irregular",
    "Stephano": "Irregular", "Trinculo": "Irregular",
    "Sycorax": "Irregular", "Margaret": "Irregular",
    "Prospero": "Irregular", "Setebos": "Irregular",
    "Ferdinand": "Irregular",
    # Neptune groups
    "Naiad": "Inner", "Thalassa": "Inner", "Despina": "Inner",
    "Galatea": "Inner", "Larissa": "Inner",
    "Hippocamp": "Inner", "Proteus": "Inner",
    "Triton": "Major",
    "Nereid": "Irregular", "Halimede": "Irregular",
    "Sao": "Irregular", "Laomedeia": "Irregular",
    "Psamathe": "Irregular", "Neso": "Irregular",
    # Mars
    "Phobos": "Regular", "Deimos": "Regular",
    # Earth
    "Moon": "Regular",
    # Pluto
    "Charon": "Major", "Nix": "Minor", "Hydra": "Minor",
    "Kerberos": "Minor", "Styx": "Minor",
}

# Known spelling corrections in elements table -> discovery table
ELEM_NAME_FIXES = {
    "Magaclite": "Megaclite",
    "Philophrosyn": "Philophrosyne",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Every known natural satellite of planets and dwarf planets in the Solar System \
with orbital elements, physical parameters, and discovery data. Sourced from \
NASA JPL Solar System Dynamics.

This dataset catalogs all recognized natural satellites orbiting the major planets \
(Earth through Neptune) and the dwarf planet Pluto, as maintained by NASA's Jet \
Propulsion Laboratory (JPL) Solar System Dynamics group. Each record combines \
discovery circumstances, mean orbital elements, and — where available — physical \
parameters (radius, density, gravitational parameter).

The dataset merges three authoritative JPL tables:
- **Discovery circumstances** — name, parent body, year, discoverer
- **Mean orbital elements** — semi-major axis, eccentricity, inclination, period
- **Physical parameters** — mean radius, GM, density (for major moons)

The natural satellites of the solar system span an extraordinary range of sizes, \
compositions, and dynamical histories. At one extreme, Jupiter's Ganymede \
(radius ~2,634 km) is larger than Mercury and possesses its own intrinsic \
magnetic field. At the other, many recently discovered irregular satellites are \
only a few kilometers across and occupy distant, highly inclined or retrograde \
orbits that betray their origin as captured objects from the primordial small-body \
population. The dynamical groupings recorded in this dataset — Galilean, Himalia, \
Ananke, Carme, Pasiphae for Jupiter; Inuit, Gallic, Norse for Saturn — reflect \
distinct capture and collisional fragmentation events that occurred during the \
chaotic early evolution of the giant planet systems.

Several moons in this catalog are among the most scientifically compelling worlds \
in the solar system. Europa's subsurface ocean beneath its icy shell is a prime \
target for astrobiology, while Enceladus actively vents water vapor and organic \
molecules through its south polar tiger stripes. Titan maintains a dense \
nitrogen-methane atmosphere with a complete hydrological cycle of methane rain, \
rivers, and lakes. Io is the most volcanically active body known, driven by \
intense tidal heating from its orbital resonance with Europa and Ganymede. \
Triton, captured by Neptune from the Kuiper Belt, exhibits active nitrogen \
geysers and a retrograde orbit that is gradually decaying.

The orbital elements in this dataset encode fundamental information about \
satellite dynamics: resonant relationships (such as the 1:2:4 Laplace resonance \
of Io, Europa, and Ganymede), tidal evolution timescales, and the stability \
boundaries that separate regular from irregular satellite populations. Combined \
with physical parameters like density and radius, these data enable studies of \
satellite formation, internal structure, and the delivery of volatiles to the \
outer solar system.
"""


def fetch_soup(url: str) -> BeautifulSoup:
    """Fetch a URL and return a BeautifulSoup object."""
    resp = requests.get(url, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "lxml")


def parse_discovery() -> pd.DataFrame:
    """Parse the JPL satellite discovery circumstances table."""
    print("Fetching satellite discovery data...")
    soup = fetch_soup(DISCOVERY_URL)
    table = soup.find("table")
    rows = table.find_all("tr")

    current_planet = None
    records = []
    for row in rows:
        cells = row.find_all(["td", "th"])
        texts = [c.get_text(strip=True) for c in cells]

        # Skip header row
        if texts and texts[0] == "IAUnumber":
            continue

        # Planet section header (single merged cell)
        if len(cells) == 1:
            text = cells[0].get_text(strip=True)
            if "Satellites of" in text:
                planet = text.split("Satellites of")[1].split(":")[0].strip()
                # Normalize "Dwarf Planet Pluto" -> "Pluto"
                current_planet = planet.replace("Dwarf Planet ", "")
            continue

        if len(texts) >= 5 and current_planet:
            records.append({
                "iau_number": texts[0],
                "name": texts[1] if texts[1] else texts[2],
                "provisional_designation": texts[2],
                "discovery_year": texts[3],
                "discoverer": texts[4],
                "parent_body": current_planet,
            })

    # JPL's discovery page omits Earth's Moon — add it explicitly
    records.insert(0, {
        "iau_number": "I",
        "name": "Moon",
        "provisional_designation": "",
        "discovery_year": "",
        "discoverer": "",
        "parent_body": "Earth",
    })

    df = pd.DataFrame(records)
    print(f"  {len(df)} satellites from discovery table")
    return df


def parse_elements() -> pd.DataFrame:
    """Parse the JPL satellite mean orbital elements table."""
    print("Fetching satellite orbital elements...")
    time.sleep(1)
    soup = fetch_soup(ELEMENTS_URL)
    tables = soup.find_all("table")
    table = tables[0]
    rows = table.find_all("tr")

    header_cells = rows[0].find_all("th")
    headers = [c.get_text(strip=True) for c in header_cells]

    records = []
    for row in rows[1:]:
        cells = row.find_all("td")
        if not cells:
            continue
        texts = [c.get_text(strip=True) for c in cells]
        if len(texts) >= len(headers):
            records.append(dict(zip(headers, texts)))

    df = pd.DataFrame(records)
    print(f"  {len(df)} satellites from orbital elements table")
    return df


def parse_physical() -> dict:
    """Parse the JPL satellite physical parameters table.

    Returns a dict keyed by satellite name with GM, mean_radius, mean_density.
    """
    print("Fetching satellite physical parameters...")
    time.sleep(1)
    soup = fetch_soup(PHYS_PAR_URL)
    table = soup.find_all("table")[0]
    rows = table.find_all("tr")

    phys = {}
    for row in rows[2:]:  # skip 2-row header
        cells = row.find_all("td")
        texts = [c.get_text(strip=True) for c in cells]
        if len(texts) >= 12:
            name = texts[1]
            gm = texts[3]
            radius = texts[6]
            density = texts[9]
            phys[name] = {
                "gm_km3s2": _to_float(gm.lstrip("<")),
                "mean_radius_km": _to_float(radius),
                "mean_density_gcm3": _to_float(density),
            }

    print(f"  {len(phys)} satellites with physical parameters")
    return phys


def _to_float(s: str):
    """Convert string to float, returning None on failure."""
    if not s or s == "n/a":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _normalize_name(name: str) -> str:
    """Normalize moon name for cross-table matching.

    The JPL elements table uses underscores (S2003_J_10) while the discovery
    table uses slashes and spaces (S/2003 J10).  Some names also have minor
    spelling differences (Magaclite vs Megaclite).
    """
    s = name.strip()
    # S2003_J_10  ->  S/2003 J10
    if s.startswith("S") and "_" in s and s[1:5].isdigit():
        # Pattern: S{year}_{planet}_{number}
        parts = s.split("_")
        if len(parts) == 3:
            s = f"S/{parts[0][1:]} {parts[1]}{parts[2]}"
        elif len(parts) == 4:
            # S2004_S_7_red or similar
            s = f"S/{parts[0][1:]} {parts[1]}{parts[2]}"
    return s.lower().replace(" ", "").replace("/", "").replace("_", "")


def classify_irregular(row: pd.Series) -> str:
    """Classify unnamed/unclassified moons based on orbital elements."""
    planet = row.get("parent_body", "")
    a_km = row.get("semi_major_axis_km")
    incl = row.get("inclination_deg")
    ecc = row.get("eccentricity")

    if pd.isna(a_km) or pd.isna(incl):
        return None

    # Retrograde orbit (inclination > 90 degrees) typically means irregular
    if incl is not None and incl > 90:
        if planet == "Jupiter":
            return "Irregular retrograde"
        elif planet == "Saturn":
            return "Norse"
        elif planet == "Uranus":
            return "Irregular"
        elif planet == "Neptune":
            return "Irregular"

    # Prograde distant moons
    if planet == "Jupiter" and a_km > 10_000_000:
        return "Irregular prograde"
    if planet == "Saturn" and a_km > 10_000_000:
        if incl and 40 < incl < 55:
            return "Inuit"
        elif incl and 30 < incl < 45:
            return "Gallic"

    return None


def main():
    # ── Fetch all three JPL data sources ──────────────────────────────
    discovery_df = parse_discovery()
    elements_df = parse_elements()
    phys_params = parse_physical()

    # ── Prepare orbital elements for merge ────────────────────────────
    elem_rename = {
        "Planet": "parent_body",
        "Satellite": "name",
        "Code": "jpl_code",
        "a(km)": "semi_major_axis_km",
        "e": "eccentricity",
        "i(deg)": "inclination_deg",
        "P(days)": "orbital_period_days",
        "\u03c9(deg)": "arg_periapsis_deg",
        "M(deg)": "mean_anomaly_deg",
        "node(deg)": "long_ascending_node_deg",
        "Epoch(TDB)": "epoch",
    }
    elements_df = elements_df.rename(columns=elem_rename)
    # Keep only columns we need
    elem_cols = [
        "parent_body", "name", "jpl_code",
        "semi_major_axis_km", "eccentricity", "inclination_deg",
        "orbital_period_days", "arg_periapsis_deg", "mean_anomaly_deg",
        "long_ascending_node_deg", "epoch",
    ]
    elements_df = elements_df[[c for c in elem_cols if c in elements_df.columns]]

    # Fix known spelling differences in elements table
    elements_df["name"] = elements_df["name"].replace(ELEM_NAME_FIXES)

    # Numeric conversions for orbital elements
    for col in ["semi_major_axis_km", "eccentricity", "inclination_deg",
                "orbital_period_days", "arg_periapsis_deg", "mean_anomaly_deg",
                "long_ascending_node_deg"]:
        if col in elements_df.columns:
            elements_df[col] = pd.to_numeric(
                elements_df[col].str.rstrip("."), errors="coerce"
            )

    # ── Merge discovery + elements ────────────────────────────────────
    # The two JPL tables use different naming conventions for provisional
    # designations: discovery uses "S/2003 J10", elements uses "S2003_J_10".
    # We create a normalized join key for fuzzy matching.
    discovery_df["_join_key"] = (
        discovery_df["parent_body"]
        + "|"
        + discovery_df["name"].apply(_normalize_name)
    )
    elements_df["_join_key"] = (
        elements_df["parent_body"]
        + "|"
        + elements_df["name"].apply(_normalize_name)
    )

    # Use discovery as primary, merge orbital elements via normalized key
    elem_cols_for_merge = [c for c in elements_df.columns if c != "parent_body"]
    df = discovery_df.merge(
        elements_df[elem_cols_for_merge].rename(columns={"name": "_elem_name"}),
        on="_join_key",
        how="left",
    )

    # For moons only in elements (e.g. Earth's Moon has no discovery entry),
    # add them separately
    matched_keys = set(df["_join_key"].dropna())
    elem_only = elements_df[~elements_df["_join_key"].isin(matched_keys)].copy()
    if len(elem_only) > 0:
        print(f"  Adding {len(elem_only)} moons from orbital elements "
              f"not in discovery table")
        df = pd.concat([df, elem_only], ignore_index=True)

    # Clean up temp columns
    df = df.drop(columns=["_join_key", "_elem_name"], errors="ignore")

    # ── Add physical parameters ───────────────────────────────────────
    df["gm_km3s2"] = df["name"].map(
        lambda n: phys_params.get(n, {}).get("gm_km3s2"))
    df["mean_radius_km"] = df["name"].map(
        lambda n: phys_params.get(n, {}).get("mean_radius_km"))
    df["mean_density_gcm3"] = df["name"].map(
        lambda n: phys_params.get(n, {}).get("mean_density_gcm3"))
    df["diameter_km"] = df["mean_radius_km"].apply(
        lambda r: round(r * 2, 2) if pd.notna(r) else None)

    # ── Discovery year ────────────────────────────────────────────────
    df["discovery_year"] = pd.to_numeric(df["discovery_year"], errors="coerce")
    df["discovery_year"] = df["discovery_year"].astype("Int64")

    # ── Moon group/family classification ──────────────────────────────
    df["group"] = df["name"].map(MOON_GROUPS)
    # For unclassified moons, attempt classification from orbital elements
    mask = df["group"].isna()
    df.loc[mask, "group"] = df.loc[mask].apply(classify_irregular, axis=1)

    # ── Derived columns ───────────────────────────────────────────────
    df["is_retrograde"] = df["inclination_deg"].apply(
        lambda i: i > 90 if pd.notna(i) else None
    )
    # Convert to boolean with nullable type
    df["is_retrograde"] = df["is_retrograde"].astype("boolean")

    # ── Column ordering ───────────────────────────────────────────────
    col_order = [
        "name", "parent_body", "iau_number", "provisional_designation",
        "discovery_year", "discoverer", "group",
        "semi_major_axis_km", "eccentricity", "inclination_deg",
        "orbital_period_days", "arg_periapsis_deg", "mean_anomaly_deg",
        "long_ascending_node_deg", "epoch",
        "mean_radius_km", "diameter_km", "gm_km3s2",
        "mean_density_gcm3", "is_retrograde", "jpl_code",
    ]
    col_order = [c for c in col_order if c in df.columns]
    df = df[col_order]

    # ── Sort ──────────────────────────────────────────────────────────
    planet_order = {
        "Earth": 0, "Mars": 1, "Jupiter": 2, "Saturn": 3,
        "Uranus": 4, "Neptune": 5, "Pluto": 6,
    }
    df["_sort"] = df["parent_body"].map(planet_order).fillna(99)
    df = df.sort_values(
        ["_sort", "semi_major_axis_km"],
        ascending=[True, True],
        na_position="last",
    ).drop(columns=["_sort"]).reset_index(drop=True)

    # ── Round floats ──────────────────────────────────────────────────
    for col in ["semi_major_axis_km", "eccentricity", "inclination_deg",
                "orbital_period_days", "arg_periapsis_deg", "mean_anomaly_deg",
                "long_ascending_node_deg", "gm_km3s2", "mean_density_gcm3"]:
        if col in df.columns:
            df[col] = df[col].round(6)
    if "mean_radius_km" in df.columns:
        df["mean_radius_km"] = df["mean_radius_km"].round(2)

    # ── Keep only columns with descriptions ───────────────────────────
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # ── Stats ─────────────────────────────────────────────────────────
    n_total = len(df)
    by_planet = df["parent_body"].value_counts()
    n_with_radius = int(df["mean_radius_km"].notna().sum())
    n_with_orbit = int(df["orbital_period_days"].notna().sum())
    n_retrograde = int(df["is_retrograde"].sum()) if "is_retrograde" in df.columns else 0
    year_min = int(df["discovery_year"].min())
    year_max = int(df["discovery_year"].max())
    largest = df.loc[df["mean_radius_km"].idxmax()] if n_with_radius else None

    print(f"\n  {n_total} total moons")
    for planet, count in by_planet.items():
        print(f"    {planet}: {count}")
    print(f"  {n_with_radius} with radius, {n_with_orbit} with orbital elements")
    print(f"  {n_retrograde} retrograde, discovery years {year_min}-{year_max}")

    planet_summary = "\n".join(
        f"- **{planet}**: {count} moons"
        for planet, count in by_planet.items()
    )
    largest_info = ""
    if largest is not None:
        largest_info = (
            f"\n- Largest moon: **{largest['name']}** "
            f"({largest['parent_body']}, "
            f"radius {largest['mean_radius_km']:,.1f} km)"
        )

    quick_stats = f"""\
- **{n_total}** total moons
{planet_summary}
- **{n_with_orbit}** moons with orbital elements
- **{n_with_radius}** moons with measured radius
- **{n_retrograde}** retrograde moons (inclination > 90\u00b0){largest_info}"""

    usage = """\
```python
from datasets import load_dataset
import matplotlib.pyplot as plt

ds = load_dataset("juliensimon/solar-system-moons", split="train")
df = ds.to_pandas()

# Moons per planet
print(df["parent_body"].value_counts())

# Galilean moons of Jupiter
galilean = df[df["group"] == "Galilean"]

# Retrograde irregular satellites
retro = df[df["is_retrograde"] == True].sort_values("orbital_period_days")

# Largest moons by radius
biggest = df.dropna(subset=["mean_radius_km"]).nlargest(10, "mean_radius_km")

# Plot moon sizes by planet
fig, ax = plt.subplots(figsize=(10, 6))
for planet in ["Jupiter", "Saturn", "Uranus", "Neptune"]:
    subset = df[(df["parent_body"] == planet) & df["mean_radius_km"].notna()]
    ax.scatter(subset["semi_major_axis_km"] / 1e6, subset["mean_radius_km"],
               label=planet, alpha=0.7, s=40)
ax.set_xlabel("Semi-major axis (million km)")
ax.set_ylabel("Mean radius (km)")
ax.set_title("Moon size vs. orbital distance")
ax.set_xscale("log")
ax.set_yscale("log")
ax.legend()
plt.tight_layout()
plt.show()

# Recent discoveries (2020+)
recent = df[df["discovery_year"] >= 2020]
```"""

    # ── Publish via Pipeline ──────────────────────────────────────────
    with Pipeline(
        repo=HF_REPO,
        pretty_name="Solar System Moons",
        description=DESCRIPTION,
        tags=["space", "moons", "planets", "solar-system", "planetary-science",
              "open-data", "natural-satellites", "orbital-mechanics", "jpl",
              "tabular-data", "parquet"],
        source_url="https://ssd.jpl.nasa.gov/sats/discovery.html",
        task_categories=["tabular-classification", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/planetary-science-datasets-68214dab0f1e965e6741fcd2",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA00600/PIA00600~small.jpg",
            "alt": "Jupiter's Great Red Spot and the Galilean satellites",
            "credit": "NASA/JPL-Caltech",
        },
        related_datasets=[
            "juliensimon/neo-close-approaches",
            "juliensimon/nasa-exoplanets",
            "juliensimon/jpl-small-body-database",
        ],
    ) as p:
        p.publish(
            df,
            filename="solar_system_moons.parquet",
            min_rows=MIN_ROWS,
            expected_columns=[
                "name", "parent_body", "discovery_year", "discoverer",
                "semi_major_axis_km", "eccentricity", "inclination_deg",
                "orbital_period_days",
            ],
            critical_columns=["name", "parent_body", "semi_major_axis_km"],
            max_null_pct=0.05,
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Solar system moons: {n_total} natural satellites",
        )

    print(f"Done. {n_total} moons uploaded to {HF_REPO}")


if __name__ == "__main__":
    main()
