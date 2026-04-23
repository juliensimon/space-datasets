#!/usr/bin/env python3
"""Scrape Starlink ground station locations and upload to HF as a dataset.

Two configs:
  - gateways: ground stations from starlinkinsider.com + FCC IBFS bulk data
  - pops: 14 Points of Presence (DNS codes -> cities with coordinates)

Sources:
  1. starlinkinsider.com — scraped daily, covers international stations with status
  2. FCC IBFS bulk extract (ftp://ftp.fcc.gov) — SpaceX SES filings with DMS coords

Starlinkinsider stations take priority for status. FCC-only stations (US) are
merged in with their FCC license status. Stations not in either source are dropped.
"""

import json
import re
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests

from hf_dataset_utils import Pipeline, check_dataset, write_parquet
from hf_dataset_utils.banner import banner_markdown as render_banner
from hf_dataset_utils.banner import download_banner
from hf_dataset_utils.github import emit_output
from hf_dataset_utils.readme import _citation_bibtex, _size_category

INSIDER_URL = "https://starlinkinsider.com/starlink-gateway-locations/"
FCC_FTP_URL = "ftp://ftp.fcc.gov/pub/Bureaus/International/databases/IBFS.zip"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
PEERINGDB_API = "https://www.peeringdb.com/api"
HF_REPO = "juliensimon/starlink-ground-stations"
CACHE_PATH = Path(__file__).parent.parent / "data" / "ground-stations-cache.json"
USER_AGENT = "StarLink-MissionControl/1.0"

# SpaceX Starlink ASN on PeeringDB
STARLINK_ASN = 14593

# DNS codes derived from Starlink rDNS hostnames (customer.<code><N>.isp.starlink.com)
# Keyed by PeeringDB city name for injection into PeeringDB results.
KNOWN_DNS_CODES: dict[str, str] = {
    "Frankfurt am Main": "frntdeu",
    "Frankfurt": "frntdeu",
    "London": "lndngbr",
    "Madrid": "madresp",
    "Los Angeles": "lax",
    "Seattle": "sea",
    "Chicago": "chi",
    "Washington": "iad",
    "Ashburn": "iad",
    "Miami": "mia",
    "Amsterdam": "ams",
    "Paris": "par",
    "Singapore": "sin",
    "Sydney": "syd",
    "Tokyo": "nrt",
}

# Fallback hardcoded PoPs used if PeeringDB is unavailable
POPS_FALLBACK = [
    {"code": "frntdeu", "city": "Frankfurt", "country": "DE", "lat": 50.1109, "lon": 8.6821},
    {"code": "lndngbr", "city": "London", "country": "GB", "lat": 51.5074, "lon": -0.1278},
    {"code": "madresp", "city": "Madrid", "country": "ES", "lat": 40.4168, "lon": -3.7038},
    {"code": "lax", "city": "Los Angeles", "country": "US", "lat": 34.0522, "lon": -118.2437},
    {"code": "sea", "city": "Seattle", "country": "US", "lat": 47.6062, "lon": -122.3321},
    {"code": "chi", "city": "Chicago", "country": "US", "lat": 41.8781, "lon": -87.6298},
    {"code": "iad", "city": "Washington DC", "country": "US", "lat": 39.0438, "lon": -77.4874},
    {"code": "mia", "city": "Miami", "country": "US", "lat": 25.7617, "lon": -80.1918},
    {"code": "ams", "city": "Amsterdam", "country": "NL", "lat": 52.3676, "lon": 4.9041},
    {"code": "par", "city": "Paris", "country": "FR", "lat": 48.8566, "lon": 2.3522},
    {"code": "sin", "city": "Singapore", "country": "SG", "lat": 1.3521, "lon": 103.8198},
    {"code": "syd", "city": "Sydney", "country": "AU", "lat": -33.8688, "lon": 151.2093},
    {"code": "nrt", "city": "Tokyo", "country": "JP", "lat": 35.6762, "lon": 139.6503},
]

# ── Column descriptions ─────────────────────────────────────────────────────

GW_COLUMN_DESCRIPTIONS = {
    "name": "Location name (City, State/Country) of the Starlink gateway earth station; derived from FCC IBFS filings or Starlink Insider community data",
    "lat": "Latitude in decimal degrees (WGS-84); precise to 4 decimal places for FCC-sourced stations, geocoded for Insider-sourced stations",
    "lon": "Longitude in decimal degrees (WGS-84); precise to 4 decimal places for FCC-sourced stations, geocoded for Insider-sourced stations",
    "status": "Operational status: 'operational' (live and serving traffic) or 'planned' (licensed/announced but not yet active); derived from Starlink Insider or FCC filing status codes",
}

POP_COLUMN_DESCRIPTIONS = {
    "code": "DNS prefix code from Starlink reverse DNS hostnames (e.g., 'lax', 'frntdeu'); identifies the PoP in customer.<code><N>.isp.starlink.com patterns; null for locations not yet observed in rDNS",
    "city": "City name where the Point of Presence is located; sourced from PeeringDB facility registrations for SpaceX AS54184/AS35340",
    "country": "ISO 3166-1 alpha-2 country code (e.g., 'US', 'DE', 'JP')",
    "lat": "Latitude in decimal degrees (WGS-84) of the facility",
    "lon": "Longitude in decimal degrees (WGS-84) of the facility",
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def normalize_city(name: str) -> str:
    """Normalize a city name for dedup: lowercase, strip punctuation/accents."""
    import unicodedata
    name = name.lower().split(",")[0].strip()
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    name = re.sub(r"[^a-z ]", "", name)
    return re.sub(r"\s+", " ", name).strip()


def load_cache() -> dict:
    if CACHE_PATH.exists():
        with open(CACHE_PATH) as f:
            return json.load(f)
    return {"stations": {}}


def save_cache(cache: dict):
    with open(CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def geocode(query: str) -> tuple[float, float] | None:
    """Geocode a location name via Nominatim."""
    try:
        resp = requests.get(
            NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": 1},
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        data = resp.json()
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception as e:
        print(f"  Geocode failed for '{query}': {e}")
    return None


# ── PeeringDB PoP fetch ──────────────────────────────────────────────────────

def fetch_peeringdb_pops(geo_cache: dict) -> list[dict]:
    """Fetch SpaceX Starlink PoP locations from PeeringDB (AS14593).

    Makes two requests: one to resolve the net_id, one to get all facility
    associations. Coordinates come from the existing geocoding cache or
    Nominatim (city + country query). Falls back to POPS_FALLBACK if
    PeeringDB is unreachable or returns fewer than 5 entries.
    """
    try:
        net_resp = requests.get(
            f"{PEERINGDB_API}/net",
            params={"asn": STARLINK_ASN},
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        net_resp.raise_for_status()
        nets = net_resp.json().get("data", [])
        if not nets:
            raise ValueError("No network record found for AS14593")
        net_id = nets[0]["id"]

        time.sleep(1)

        fac_resp = requests.get(
            f"{PEERINGDB_API}/netfac",
            params={"net_id": net_id},
            headers={"User-Agent": USER_AGENT},
            timeout=30,
        )
        fac_resp.raise_for_status()
        entries = fac_resp.json().get("data", [])

    except Exception as e:
        print(f"  WARNING: PeeringDB fetch failed: {e} — using hardcoded fallback")
        return POPS_FALLBACK

    pops: list[dict] = []
    seen_fac_ids: set[int] = set()
    geocoded = 0

    for nf in entries:
        fac_id = nf.get("fac_id")
        if not fac_id or fac_id in seen_fac_ids:
            continue
        seen_fac_ids.add(fac_id)

        city = (nf.get("city") or "").strip()
        country = (nf.get("country") or "").strip()
        if not city:
            continue

        # Try geocoding cache (keyed as "city, country" for PoPs)
        cache_key = f"{city}, {country}".lower()
        if cache_key in geo_cache:
            cached = geo_cache[cache_key]
            lat, lon = cached["lat"], cached["lon"]
        else:
            time.sleep(1.1)
            query = f"{city}, {country}" if country else city
            coords = geocode(query)
            if not coords:
                print(f"    -> Could not geocode {query}, skipping")
                continue
            lat, lon = round(coords[0], 4), round(coords[1], 4)
            geo_cache[cache_key] = {"name": city, "lat": lat, "lon": lon}
            geocoded += 1
            print(f"  Geocoded PoP: {query} -> {lat}, {lon}")

        pops.append({
            "code": KNOWN_DNS_CODES.get(city),
            "city": city,
            "country": country,
            "lat": lat,
            "lon": lon,
        })

    if geocoded > 0:
        print(f"  {geocoded} new PoP locations geocoded")

    if len(pops) < 5:
        print(f"  WARNING: PeeringDB returned only {len(pops)} PoPs — using hardcoded fallback")
        return POPS_FALLBACK

    print(f"  {len(pops)} PoPs from PeeringDB ({sum(1 for p in pops if p['code'])} with known DNS codes)")
    return pops


# ── Starlinkinsider scraper ──────────────────────────────────────────────────

def scrape_insider() -> list[dict]:
    """Scrape station names and statuses from starlinkinsider.com."""
    print(f"Fetching from {INSIDER_URL}...")
    resp = requests.get(INSIDER_URL, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()

    stations = []
    seen = set()
    for match in re.finditer(r"<li[^>]*>([^<]+)</li>", resp.text, re.IGNORECASE):
        text = match.group(1).strip()
        status_match = re.search(r"\(([^)]+)\)\s*$", text)
        status_raw = status_match.group(1) if status_match else "unknown"
        name = re.sub(r"\s*\([^)]*\)\s*$", "", text).strip()
        if len(name) <= 2:
            continue
        status = "operational" if status_raw == "live" else "planned"
        key = name.lower()
        if key not in seen:
            seen.add(key)
            stations.append({"name": name, "status": status})

    print(f"  {len(stations)} stations")
    if len(stations) < 50:
        raise RuntimeError(f"Only {len(stations)} stations scraped — site may have changed format")
    return stations


# ── FCC IBFS bulk extract ────────────────────────────────────────────────────

def _parse_ibfs_file(zf: zipfile.ZipFile, filename: str) -> list[list[str]]:
    """Parse a pipe-delimited IBFS .dat file from a zip archive."""
    with zf.open(filename) as f:
        text = f.read().decode("latin-1")
    rows = []
    for line in text.splitlines():
        line = line.rstrip("\r\n").rstrip("|^").rstrip("^")
        rows.append(line.split("|"))
    return rows


def _dms_to_decimal(deg: str, mins: str, secs: str, hemi: str) -> float | None:
    try:
        d = float(deg) + float(mins) / 60 + float(secs) / 3600
        if hemi in ("S", "W"):
            d = -d
        return round(d, 4)
    except (ValueError, TypeError):
        return None


def fetch_fcc_stations() -> list[dict]:
    """Download FCC IBFS bulk data and extract SpaceX earth stations."""
    print(f"Fetching FCC IBFS from {FCC_FTP_URL}...")
    try:
        subprocess.run(
            ["curl", "-s", "--max-time", "120", FCC_FTP_URL, "-o", "/tmp/IBFS.zip"],
            check=True, capture_output=True, text=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"  WARNING: FCC download failed: {e}")
        return []

    try:
        zf = zipfile.ZipFile("/tmp/IBFS.zip")
    except zipfile.BadZipFile:
        print("  WARNING: FCC zip is corrupted")
        return []

    with zf:
        main_rows = _parse_ibfs_file(zf, "main.dat")
        addr_rows = _parse_ibfs_file(zf, "address.dat")

        spacex_addr_keys = set()
        for r in addr_rows:
            if len(r) > 2 and ("spacex" in r[2].lower() or "space exploration" in r[2].lower()):
                spacex_addr_keys.add(r[0])

        filing_status: dict[str, str] = {}
        for r in main_rows:
            if len(r) > 41 and r[4] == "SES":
                addr_key = r[41]
                desc = r[40] if len(r) > 40 else ""
                if (addr_key in spacex_addr_keys
                        or "spacex" in desc.lower()
                        or "space exploration" in desc.lower()):
                    filing_status[r[0]] = r[5].strip()

        site_rows = _parse_ibfs_file(zf, "site.dat")

    # Dedup by normalized city name, prefer operational status
    city_stations: dict[str, dict] = {}
    for r in site_rows:
        if len(r) < 21 or r[1] not in filing_status:
            continue
        lat = _dms_to_decimal(r[13], r[14], r[15], r[16])
        lon = _dms_to_decimal(r[17], r[18], r[19], r[20])
        if lat is None or lon is None or (lat == 0 and lon == 0):
            continue

        city = r[7].strip() if len(r) > 7 else ""
        state = r[9].strip() if len(r) > 9 else ""
        if not city:
            continue

        name = f"{city}, {state}" if state else city
        name = re.sub(r",\s*[A-Z]{2}\.,", ",", name)
        name = re.sub(r",\s*([A-Z]{2}),\s*\1$", r", \1", name)

        status_code = filing_status[r[1]]
        status = "operational" if status_code in ("A/C", "ATPN", "AFP") else "planned"

        city_norm = normalize_city(name)
        if city_norm not in city_stations or (
            status == "operational" and city_stations[city_norm]["status"] == "planned"
        ):
            city_stations[city_norm] = {
                "name": name,
                "lat": lat,
                "lon": lon,
                "status": status,
            }

    stations = list(city_stations.values())
    op = sum(1 for s in stations if s["status"] == "operational")
    print(f"  {len(stations)} stations ({op} operational, {len(stations) - op} planned)")
    return stations


# ── Dataset description ──────────────────────────────────────────────────────
DESCRIPTION = """\
Starlink ground infrastructure data: gateway earth stations and internet Points of \
Presence (PoPs). Gateway earth stations maintain continuous Ka-band and Ku-band links \
with the overhead satellite constellation -- when a user terminal communicates with a \
Starlink satellite, the signal is relayed down to the nearest gateway, which connects \
to the terrestrial internet backbone.

SpaceX has been aggressively expanding its gateway network worldwide to reduce \
"bent-pipe" latency and increase aggregate network capacity. The Points of Presence \
(PoPs) serve a different function: these are internet exchange points in major cities \
where Starlink peers with other networks and content delivery providers.

This dataset is valuable for network performance modeling, regulatory analysis of \
Starlink's global expansion strategy, and visualization of the ground infrastructure \
that supports the world's largest satellite constellation.\
"""


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    cache = load_cache()
    geo_cache = cache.get("stations", {})
    print(f"Geocoding cache: {len(geo_cache)} entries")

    # ── Source 1: Starlinkinsider (international coverage + status) ───────
    insider: list[dict] = []
    try:
        insider = scrape_insider()
    except Exception as e:
        print(f"ERROR: Starlinkinsider scrape failed ({e})")
        sys.exit(1)

    # Build norm->cache-key map for coordinate lookup
    norm_to_key: dict[str, str] = {}
    for k in geo_cache:
        norm_to_key[normalize_city(k)] = k

    # Resolve coordinates for insider stations
    gw_records: list[dict] = []
    seen_norms: set[str] = set()
    geocoded = 0
    for entry in insider:
        name = entry["name"]
        city_norm = normalize_city(name)
        if city_norm in norm_to_key:
            cached = geo_cache[norm_to_key[city_norm]]
            gw_records.append({
                "name": cached["name"],
                "lat": cached["lat"],
                "lon": cached["lon"],
                "status": entry["status"],
            })
        else:
            time.sleep(1.1)
            print(f"  Geocoding: {name}")
            coords = geocode(name)
            if coords:
                key = name.lower()
                geo_cache[key] = {
                    "name": name,
                    "lat": round(coords[0], 4),
                    "lon": round(coords[1], 4),
                    "status": entry["status"],
                }
                norm_to_key[city_norm] = key
                gw_records.append(geo_cache[key])
                geocoded += 1
                print(f"    -> {coords[0]:.4f}, {coords[1]:.4f}")
            else:
                print(f"    -> Not found, skipping")
                continue
        seen_norms.add(city_norm)

    if geocoded > 0:
        cache["stations"] = geo_cache
        save_cache(cache)
        print(f"  {geocoded} new stations geocoded and cached")

    # ── Source 2: FCC IBFS (US earth station filings) ────────────────────
    fcc_stations = fetch_fcc_stations()
    fcc_added = 0
    for s in fcc_stations:
        city_norm = normalize_city(s["name"])
        if city_norm not in seen_norms:
            gw_records.append(s)
            seen_norms.add(city_norm)
            fcc_added += 1
    print(f"  {fcc_added} FCC-only stations added")

    # ── Source 3: PeeringDB (SpaceX PoP locations) ───────────────────────
    print("Fetching PoPs from PeeringDB...")
    cache_size_before = len(geo_cache)
    pop_records = fetch_peeringdb_pops(geo_cache)
    if len(geo_cache) > cache_size_before:
        cache["stations"] = geo_cache
        save_cache(cache)
    pop_records.sort(key=lambda p: (p["country"], p["city"]))

    # Build DataFrames
    gw_records.sort(key=lambda s: s["name"])
    gw_df = pd.DataFrame(gw_records, columns=["name", "lat", "lon", "status"])
    pop_df = pd.DataFrame(pop_records, columns=["code", "city", "country", "lat", "lon"])

    # Keep only described columns
    gw_df = gw_df[[c for c in gw_df.columns if c in GW_COLUMN_DESCRIPTIONS]]
    pop_df = pop_df[[c for c in pop_df.columns if c in POP_COLUMN_DESCRIPTIONS]]

    check_dataset(gw_df, "ground-stations", min_rows=50,
                  expected_columns=["name", "lat", "lon", "status"],
                  critical_columns=["lat", "lon"])

    n_operational = len(gw_df[gw_df["status"] == "operational"])
    n_planned = len(gw_df[gw_df["status"] == "planned"])
    print(f"\nGateways: {len(gw_df)} ({n_operational} operational, {n_planned} planned)")
    print(f"PoPs: {len(pop_df)}")

    # ── Schema helpers ───────────────────────────────────────────────
    def _schema(descs):
        lines = ["| Column | Type | Description |", "|--------|------|-------------|"]
        for col, desc in descs.items():
            lines.append(f"| `{col}` | -- | {desc} |")
        return "\n".join(lines)

    quick_stats = f"""\
- **{len(gw_df)}** gateway earth stations ({n_operational} operational, {n_planned} planned)
- **{len(pop_df)}** Points of Presence across {pop_df['country'].nunique()} countries
- Coverage spans {gw_df['lat'].min():.1f} to {gw_df['lat'].max():.1f} latitude"""

    usage = f"""\
```python
from datasets import load_dataset

# Load gateways
gateways = load_dataset("{HF_REPO}", "gateways", split="train")

# Load PoPs
pops = load_dataset("{HF_REPO}", "pops", split="train")

# Operational stations only
operational = gateways.filter(lambda x: x["status"] == "operational")

# Map gateway distribution with matplotlib
import matplotlib.pyplot as plt
df = gateways.to_pandas()
op = df[df["status"] == "operational"]
pl = df[df["status"] == "planned"]
plt.scatter(op["lon"], op["lat"], c="green", label="Operational", s=20)
plt.scatter(pl["lon"], pl["lat"], c="orange", label="Planned", s=20)
plt.xlabel("Longitude")
plt.ylabel("Latitude")
plt.legend()
plt.title("Starlink Ground Stations")
plt.show()
```"""

    total_rows = len(gw_df) + len(pop_df)

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Starlink Ground Stations & Points of Presence",
        description=DESCRIPTION,
        tags=["space", "starlink", "ground-stations", "satellite-internet",
              "geospatial", "earth-observation", "open-data", "spacex", "fcc",
              "tabular-data", "parquet"],
        source_url="https://starlinkinsider.com/starlink-gateway-locations/",
        collection_url="https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994",
        banner={
            "url": "https://images-assets.nasa.gov/image/iss071e439624/iss071e439624~medium.jpg",
            "alt": "An orbital sunrise illuminates the Earth's atmosphere, seen from the ISS",
            "credit": "NASA",
        },
    ) as p:
        write_parquet(gw_df, p.data_dir / "gateways.parquet")
        write_parquet(pop_df, p.data_dir / "pops.parquet")

        # Banner
        banner_file = download_banner(p.banner["url"], p.tmp_dir)
        banner_md = render_banner(
            p.banner["alt"], p.banner["credit"],
            filename=banner_file,
        ) if banner_file else ""

        readme = f"""---
license: cc-by-4.0
pretty_name: "Starlink Ground Stations & Points of Presence"
language:
  - en
description: "Worldwide Starlink gateway and Point of Presence locations from FCC IBFS filings and Starlink Insider. Updated daily."
task_categories:
  - tabular-classification
tags:
  - space
  - starlink
  - ground-stations
  - satellite-internet
  - geospatial
  - open-data
  - spacex
  - fcc
  - tabular-data
  - parquet
configs:
  - config_name: gateways
    data_files:
      - split: train
        path: data/gateways.parquet
    default: true
  - config_name: pops
    data_files:
      - split: train
        path: data/pops.parquet
size_categories:
  - {_size_category(total_rows)}
---

# Starlink Ground Stations & Points of Presence
{banner_md}
*Part of the [Orbital Mechanics Datasets](https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994) collection on Hugging Face.*

## Dataset description

{DESCRIPTION}

## Configs

### `gateways` -- {len(gw_df)} ground stations ({n_operational} operational, {n_planned} planned)

Gateway earth stations that connect Starlink satellites to the terrestrial internet.

{_schema(GW_COLUMN_DESCRIPTIONS)}

### `pops` -- {len(pop_df)} Points of Presence

Internet exchange points where Starlink traffic exits to the public internet.

{_schema(POP_COLUMN_DESCRIPTIONS)}

## Quick stats

{quick_stats}

## Usage

{usage}

## Data sources

- [Starlink Insider](https://starlinkinsider.com/starlink-gateway-locations/) -- community-maintained list with operational status
- [FCC IBFS](ftp://ftp.fcc.gov/pub/Bureaus/International/databases/) -- US earth station license filings
- [OpenStreetMap Nominatim](https://nominatim.openstreetmap.org/) -- geocoding for stations without coordinates
- [PeeringDB](https://www.peeringdb.com/) -- SpaceX AS54184/AS35340 facility registrations for PoP locations

## Update schedule

Daily at 09:00 UTC via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [juliensimon/starlink-fleet-data](https://huggingface.co/datasets/juliensimon/starlink-fleet-data) -- Daily Starlink constellation health snapshots
- [juliensimon/space-track-satcat](https://huggingface.co/datasets/juliensimon/space-track-satcat) -- NORAD satellite catalog
- [juliensimon/space-launch-log](https://huggingface.co/datasets/juliensimon/space-launch-log) -- Global launch history from GCAT

## Citation

{_citation_bibtex(HF_REPO, "Starlink Ground Stations & Points of Presence")}

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
"""
        (p.tmp_dir / "README.md").write_text(readme)

        # Upload
        from hf_dataset_utils import upload_to_hf
        commit_msg = (
            f"Update ground stations: {len(gw_df)} gateways "
            f"({n_operational} operational, {n_planned} planned), "
            f"{len(pop_df)} PoPs"
        )
        upload_to_hf(HF_REPO, p.tmp_dir, commit_msg)
        emit_output(rows=len(gw_df))

    print("Done.")


if __name__ == "__main__":
    main()
