#!/usr/bin/env python3
"""Scrape Starlink ground station locations and upload to HF as a dataset.

Two configs:
  - gateways: ground stations from starlinkinsider.com + FCC IBFS bulk data
  - pops: 14 Points of Presence (DNS codes → cities with coordinates)

Sources:
  1. starlinkinsider.com — scraped daily, covers international stations with status
  2. FCC IBFS bulk extract (ftp://ftp.fcc.gov) — SpaceX SES filings with DMS coords

Starlinkinsider stations take priority for status. FCC-only stations (US) are
merged in with their FCC license status. Stations not in either source are dropped.
"""

import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests

from dataset_images import banner_markdown, download_banner
from validate import check_dataset

INSIDER_URL = "https://starlinkinsider.com/starlink-gateway-locations/"
FCC_FTP_URL = "ftp://ftp.fcc.gov/pub/Bureaus/International/databases/IBFS.zip"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HF_REPO = "juliensimon/starlink-ground-stations"
CACHE_PATH = Path(__file__).parent.parent / "data" / "ground-stations-cache.json"
USER_AGENT = "StarLink-MissionControl/1.0"

# ── PoPs ─────────────────────────────────────────────────────────────────────

# DNS codes from Starlink rDNS hostnames (customer.<code><N>.isp.starlink.com)
# Coordinates from SpaceX peering/IXP locations.
POPS = [
    {"code": "frntdeu", "city": "Frankfurt", "country": "DE", "lat": 50.1109, "lon": 8.6821},
    {"code": "frntfra", "city": "Frankfurt", "country": "DE", "lat": 50.1109, "lon": 8.6821},
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
        resp = subprocess.run(
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
        # Parse main.dat — find SpaceX SES (Satellite Earth Station) filings
        # Schema: filing_key[0], filing_state[1], callsign[2], file_number[3],
        #         subsystem_code[4], status_code[5], ..., description[40], address_key[41]
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

        # Parse site.dat — extract coordinates
        # Schema: site_key[0], filing_key[1], site_name[2], site_desc[3],
        #         contact[4], address[5], ?, city[7], county[8], state[9], zip[10],
        #         phone[11], elevation[12], lat_deg[13], lat_min[14], lat_sec[15],
        #         lat_hemi[16], lon_deg[17], lon_min[18], lon_sec[19], lon_hemi[20]
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
        # Clean duplicated state codes like "Arvin, CA., CA" or "Hillsboro, TX, TX"
        name = re.sub(r",\s*[A-Z]{2}\.,", ",", name)
        name = re.sub(r",\s*([A-Z]{2}),\s*\1$", r", \1", name)

        status_code = filing_status[r[1]]
        # A/C = authorized/conditional, ATPN = authorized to proceed notification
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


# ── HF README ────────────────────────────────────────────────────────────────

def build_readme(n_gateways: int, n_operational: int, n_planned: int, banner_md: str = "") -> str:
    return f"""---
license: cc-by-4.0
pretty_name: "Starlink Ground Stations and PoPs"
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
  - config_name: pops
    data_files:
      - split: train
        path: data/pops.parquet
size_categories:
  - n<1K
---

# Starlink Ground Stations & Points of Presence
{banner_md}
*Part of the [Orbital Mechanics Datasets](https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994) collection on Hugging Face.*

![Update Ground Stations](https://github.com/juliensimon/space-datasets/actions/workflows/update-ground-stations.yml/badge.svg)
![Updated](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/juliensimon/space-datasets/main/status.json&query=$['ground-stations']&label=updated&color=brightgreen)

Starlink ground infrastructure data: gateway earth stations and internet Points of Presence (PoPs).

## Dataset description

Starlink's ground segment is as critical to its operation as the satellites themselves. Each gateway earth station houses multiple parabolic antennas (typically 2-4 dishes per site) that maintain continuous Ka-band and Ku-band links with the overhead satellite constellation. When a user terminal communicates with a Starlink satellite, the signal is relayed down to the nearest gateway, which connects to the terrestrial internet backbone. The geographic distribution of gateways directly determines service quality: users far from any gateway experience higher latency because their traffic must hop across multiple satellites via inter-satellite laser links before reaching a ground connection point.

SpaceX has been aggressively expanding its gateway network worldwide to reduce this "bent-pipe" latency and increase aggregate network capacity. Early service relied on a handful of US gateways, but the network now spans six continents. Each gateway site requires regulatory approval from the host country's telecommunications authority -- in the US, this means FCC International Bureau (IBFS) earth station license filings, which are public record and provide precise geographic coordinates. The Points of Presence (PoPs) serve a different function: these are internet exchange points in major cities where Starlink peers with other networks and content delivery providers, determining the last-mile routing of user traffic after it exits the Starlink network.

This dataset is valuable for network performance modeling (estimating latency based on user-to-gateway distance), regulatory analysis of Starlink's global expansion strategy, competitive intelligence in the satellite broadband market, and visualization of the ground infrastructure that supports the world's largest satellite constellation.

## Configs

### `gateways` — {n_gateways} ground stations ({n_operational} operational, {n_planned} planned)

Gateway earth stations that connect Starlink satellites to the terrestrial internet.

**Sources:**
- [Starlink Insider](https://starlinkinsider.com/starlink-gateway-locations/) — international coverage, community-verified status
- [FCC IBFS](ftp://ftp.fcc.gov/pub/Bureaus/International/databases/) — US earth station license filings (SpaceX SES applications)

Starlinkinsider stations take priority for status when both sources cover the same location.

| Column | Type | Description |
|--------|------|-------------|
| `name` | string | Location name (City, State/Country) |
| `lat` | float | Latitude (WGS-84) |
| `lon` | float | Longitude (WGS-84) |
| `status` | string | `operational` or `planned` |

### `pops` — {len(POPS)} Points of Presence

Internet exchange points where Starlink traffic exits to the public internet.
Identified via reverse DNS patterns (`customer.<code><N>.isp.starlink.com`).

| Column | Type | Description |
|--------|------|-------------|
| `code` | string | DNS prefix code (e.g. `lax`, `frntdeu`) |
| `city` | string | City name |
| `country` | string | ISO 3166-1 alpha-2 country code |
| `lat` | float | Latitude (WGS-84) |
| `lon` | float | Longitude (WGS-84) |

## Usage

```python
from datasets import load_dataset

# Load gateways
gateways = load_dataset("juliensimon/starlink-ground-stations", "gateways", split="train")

# Load PoPs
pops = load_dataset("juliensimon/starlink-ground-stations", "pops", split="train")

# Operational stations only
operational = gateways.filter(lambda x: x["status"] == "operational")
```

## Data sources

- [Starlink Insider](https://starlinkinsider.com/starlink-gateway-locations/) — community-maintained list of Starlink gateway locations with operational status
- [FCC IBFS](ftp://ftp.fcc.gov/pub/Bureaus/International/databases/) — bulk extract of International Bureau Filing System earth station license data (SpaceX SES filings with DMS coordinates)
- [OpenStreetMap Nominatim](https://nominatim.openstreetmap.org/) — geocoding for stations without coordinates

## Update schedule

Daily at 09:00 UTC via [GitHub Actions](https://github.com/juliensimon/space-datasets).

## Related datasets

- [starlink-fleet-data](https://huggingface.co/datasets/juliensimon/starlink-fleet-data) — Daily Starlink constellation health snapshots
- [space-track-satcat](https://huggingface.co/datasets/juliensimon/space-track-satcat) — NORAD satellite catalog
- [space-launch-log](https://huggingface.co/datasets/juliensimon/space-launch-log) — Global launch history from GCAT

## See it in action

This dataset powers the ground station map in [Starlink Viz](https://github.com/juliensimon/starlink-viz) — interactive 3D visualization of gateway and PoP locations.

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/starlink-ground-stations) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{starlink_ground_stations,
  author = {{Simon, Julien}},
  title = {{Starlink Ground Stations}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/starlink-ground-stations}},
  note = {{Based on data from Starlink Insider and FCC IBFS}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
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

    # Build norm→cache-key map for coordinate lookup
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

    # Build DataFrames
    gw_records.sort(key=lambda s: s["name"])
    gw_df = pd.DataFrame(gw_records, columns=["name", "lat", "lon", "status"])
    pop_df = pd.DataFrame(POPS, columns=["code", "city", "country", "lat", "lon"])

    check_dataset(gw_df, "ground-stations", min_rows=50,
        expected_columns=["name", "lat", "lon", "status"],
        critical_columns=["lat", "lon"])

    n_operational = len(gw_df[gw_df["status"] == "operational"])
    n_planned = len(gw_df[gw_df["status"] == "planned"])
    print(f"\nGateways: {len(gw_df)} ({n_operational} operational, {n_planned} planned)")
    print(f"PoPs: {len(pop_df)}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        gw_path = data_dir / "gateways.parquet"
        pop_path = data_dir / "pops.parquet"
        gw_df.to_parquet(gw_path, index=False, engine="pyarrow")
        pop_df.to_parquet(pop_path, index=False, engine="pyarrow")
        print(f"  gateways.parquet: {gw_path.stat().st_size / 1024:.1f} KB")
        print(f"  pops.parquet: {pop_path.stat().st_size / 1024:.1f} KB")

        banner_file = download_banner("ground-stations", tmp)
        banner_md = banner_markdown("ground-stations", banner_file)
        readme_path = tmp / "README.md"
        readme_path.write_text(build_readme(len(gw_df), n_operational, n_planned, banner_md))

        print("\nUploading to HF...")
        commit_msg = (
            f"Update ground stations: {len(gw_df)} gateways "
            f"({n_operational} operational, {n_planned} planned), "
            f"{len(pop_df)} PoPs"
        )
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={len(gw_df)}\n")
    print("Done.")


if __name__ == "__main__":
    main()
