#!/usr/bin/env python3
"""Fetch active satellite constellations from CelesTrak, classify by shell, and upload to HF.

Covers ~20 constellations: Starlink, OneWeb, Kuiper, Qianfan, Hulianwang, Iridium,
Globalstar, ORBCOMM, Planet, Spire, GPS, Galileo, BeiDou, GLONASS, SBAS, SES,
Intelsat, Eutelsat, Telesat.

Source: CelesTrak GP data (NORAD/18th Space Defense Squadron)
"""

import math
import sys
import time
from datetime import datetime, timezone

import pandas as pd
import requests

from hf_dataset_utils import Pipeline
from hf_dataset_utils.upload import write_parquet

HF_REPO = "juliensimon/constellation-census"

MU = 398600.4418  # Earth GM (km^3/s^2)
R_EARTH = 6371.0  # km

# ── Constellation definitions ────────────────────────────────────────────────

CONSTELLATIONS = {
    "starlink": {
        "group": "starlink",
        "pattern": "STARLINK",
        "operator": "SpaceX",
        "country": "US",
        "orbit_type": "LEO",
        "shells": {
            0: {"name": "Shell 1 (33°/328km)", "inc": (0, 38), "alt": (300, 570)},
            1: {"name": "Shell 2 (43°/340km)", "inc": (38, 48), "alt": (300, 570)},
            2: {"name": "Shell 3 (53°/550km)", "inc": (48, 60), "alt": (460, 600)},
            3: {"name": "Shell 4 (70°/570km)", "inc": (60, 80), "alt": (460, 910)},
            4: {"name": "Shell 5 (97.6°/560km)", "inc": (80, 105), "alt": (460, 600)},
        },
    },
    "oneweb": {
        "group": "oneweb",
        "pattern": "ONEWEB",
        "operator": "Eutelsat OneWeb",
        "country": "GB",
        "orbit_type": "LEO",
        "shells": {
            0: {"name": "Gen1 (87.9°/1200km)", "inc": (85, 90), "alt": (1100, 1300)},
        },
    },
    "kuiper": {
        "group": "kuiper",
        "pattern": "KUIPER",
        "operator": "Amazon",
        "country": "US",
        "orbit_type": "LEO",
        "shells": {
            0: {"name": "Shell 1 (51.9°/590km)", "inc": (48, 55), "alt": (550, 650)},
            1: {"name": "Shell 2 (33°/610km)", "inc": (0, 38), "alt": (550, 650)},
            2: {"name": "Shell 3 (42°/610km)", "inc": (38, 48), "alt": (550, 650)},
        },
    },
    "qianfan": {
        "group": "qianfan",
        "pattern": "QIANFAN",
        "operator": "Shanghai Spacecom (G60)",
        "country": "CN",
        "orbit_type": "LEO",
        "shells": {
            0: {"name": "Primary (89°/~1160km)", "inc": (85, 95), "alt": (1000, 1300)},
        },
    },
    "hulianwang": {
        "group": "hulianwang",
        "pattern": "HULIANWANG",
        "operator": "China SatNet (GuoWang)",
        "country": "CN",
        "orbit_type": "LEO",
        "shells": {
            0: {"name": "Primary (86.5°)", "inc": (83, 90), "alt": (500, 1300)},
        },
    },
    "iridium": {
        "group": "iridium-NEXT",
        "pattern": "IRIDIUM",
        "operator": "Iridium",
        "country": "US",
        "orbit_type": "LEO",
        "shells": {
            0: {"name": "NEXT (86.4°/780km)", "inc": (84, 88), "alt": (760, 800)},
        },
    },
    "globalstar": {
        "group": "globalstar",
        "pattern": "GLOBALSTAR",
        "operator": "Globalstar",
        "country": "US",
        "orbit_type": "LEO",
        "shells": {
            0: {"name": "Primary (52°/1410km)", "inc": (48, 56), "alt": (1380, 1600)},
        },
    },
    "orbcomm": {
        "group": "orbcomm",
        "pattern": "ORBCOMM",
        "operator": "ORBCOMM",
        "country": "US",
        "orbit_type": "LEO",
        "shells": {
            0: {"name": "Primary", "inc": (0, 110), "alt": (400, 900)},
        },
    },
    "planet": {
        "group": "planet",
        "pattern": "SKYSAT",
        "operator": "Planet Labs",
        "country": "US",
        "orbit_type": "LEO",
        "shells": {
            0: {"name": "SSO (~97°/~500km)", "inc": (94, 100), "alt": (400, 600)},
        },
    },
    "spire": {
        "group": "spire",
        "pattern": "LEMUR",
        "operator": "Spire Global",
        "country": "US",
        "orbit_type": "LEO",
        "shells": {
            0: {"name": "SSO (~97°/~500km)", "inc": (94, 100), "alt": (400, 600)},
        },
    },
    "gps": {
        "group": "gps-ops",
        "pattern": "NAVSTAR",
        "operator": "USSF",
        "country": "US",
        "orbit_type": "MEO",
        "shells": {
            0: {"name": "GPS (55°/20200km)", "inc": (53, 58), "alt": (19500, 20700)},
        },
    },
    "galileo": {
        "group": "galileo",
        "pattern": "GSAT",
        "operator": "EU/ESA",
        "country": "EU",
        "orbit_type": "MEO",
        "shells": {
            0: {"name": "Galileo (56°/23220km)", "inc": (54, 58), "alt": (22800, 23600)},
        },
    },
    "beidou": {
        "group": "beidou",
        "pattern": "BEIDOU",
        "operator": "CNSA",
        "country": "CN",
        "orbit_type": "MEO",
        "shells": {
            0: {"name": "MEO (55°/21500km)", "inc": (53, 58), "alt": (21000, 22500)},
            1: {"name": "IGSO (55°/35800km)", "inc": (53, 58), "alt": (35000, 36500)},
            2: {"name": "GEO (0-5°/35800km)", "inc": (0, 10), "alt": (35000, 36500)},
        },
    },
    "glonass": {
        "group": "glo-ops",
        "pattern": "COSMOS",
        "operator": "Roscosmos",
        "country": "RU",
        "orbit_type": "MEO",
        "shells": {
            0: {"name": "GLONASS (64.8°/19100km)", "inc": (63, 67), "alt": (18800, 19500)},
        },
    },
    "sbas": {
        "group": "sbas",
        "pattern": None,
        "operator": "Various",
        "country": "INT",
        "orbit_type": "GEO",
        "shells": {
            0: {"name": "GEO (~0-5°/35800km)", "inc": (0, 10), "alt": (35000, 36500)},
        },
    },
    "ses": {
        "group": "ses",
        "pattern": None,
        "operator": "SES",
        "country": "LU",
        "orbit_type": "GEO",
        "shells": {
            0: {"name": "GEO", "inc": (0, 20), "alt": (35000, 36500)},
        },
    },
    "intelsat": {
        "group": "intelsat",
        "pattern": "INTELSAT",
        "operator": "Intelsat",
        "country": "US",
        "orbit_type": "GEO",
        "shells": {
            0: {"name": "GEO", "inc": (0, 20), "alt": (35000, 36500)},
        },
    },
    "eutelsat": {
        "group": "eutelsat",
        "pattern": "EUTELSAT",
        "operator": "Eutelsat",
        "country": "FR",
        "orbit_type": "GEO",
        "shells": {
            0: {"name": "GEO", "inc": (0, 20), "alt": (35000, 36500)},
        },
    },
    "telesat": {
        "group": "telesat",
        "pattern": "TELESAT",
        "operator": "Telesat",
        "country": "CA",
        "orbit_type": "GEO",
        "shells": {
            0: {"name": "GEO", "inc": (0, 20), "alt": (35000, 36500)},
        },
    },
}

GP_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP={group}&FORMAT=json"
FETCH_DELAY = 1.0
MAX_RETRIES = 3

# ── Column descriptions for latest_satellites ────────────────────
COLUMN_DESCRIPTIONS = {
    "norad_id": "NORAD catalog number -- sequential integer assigned by the 18th Space Defense Squadron; primary key for cross-referencing with TLE databases and SATCAT",
    "name": "Satellite common name from the NORAD catalog (e.g. 'STARLINK-1234', 'NAVSTAR 78', 'ONEWEB-0001')",
    "constellation": "Lowercase constellation identifier (e.g. 'starlink', 'oneweb', 'gps', 'galileo'); matches the keys in the pipeline's CONSTELLATIONS config",
    "operator": "Name of the constellation operator or agency (e.g. 'SpaceX', 'Eutelsat OneWeb', 'USSF', 'EU/ESA')",
    "country": "ISO 3166-based two-letter country code of the operating nation (e.g. 'US', 'GB', 'CN', 'EU')",
    "orbit_type": "Orbit regime: LEO (low Earth orbit, <2000 km), MEO (medium, 2000-35000 km), GEO (geostationary, ~35786 km)",
    "shell_id": "Integer shell index within the constellation (0-based); for single-shell constellations always 0; for Starlink 0-4 mapping to the five inclination/altitude shells",
    "shell_name": "Human-readable shell label encoding inclination and target altitude (e.g. 'Shell 3 (53 deg/550km)', 'GPS (55 deg/20200km)')",
    "altitude_km": "Perigee altitude above Earth's surface in km, derived from TLE mean motion and eccentricity; for near-circular orbits this approximates the operational altitude",
    "inclination": "Orbital inclination in degrees (0-180); angle between the orbital plane and Earth's equatorial plane; determines ground coverage latitudes",
    "eccentricity": "Orbital eccentricity (dimensionless, 0-1); 0 = perfectly circular; operational LEO satellites typically <0.001; values >0.005 are flagged as anomalous",
    "mean_motion": "Mean motion in revolutions per day from the TLE; LEO ~14-17 rev/day, MEO ~2 rev/day, GEO ~1 rev/day; related to semi-major axis via Kepler's third law",
    "status": "Operational classification: operational (within shell altitude band), raising (maneuvering to target, LEO only), deorbiting (actively decaying, LEO only), decayed (below 150 km), anomalous (high eccentricity), non-operational (MEO/GEO outside band)",
    "launch_year": "Year the satellite was launched, extracted from the COSPAR international designator; 0 if the designator was missing or malformed",
    "epoch_utc": "Reference epoch of the TLE set (UTC); orbital elements are most accurate at this moment; position error grows roughly 1-3 km/day for LEO objects",
}

# ── Column descriptions for daily_snapshots ────────────────────
COLUMN_DAILY_DESCRIPTIONS = {
    "date": "UTC date of the daily census snapshot; one row per constellation per date",
    "constellation": "Lowercase constellation identifier matching the latest_satellites config (e.g. 'starlink', 'gps')",
    "operator": "Name of the constellation operator or agency (e.g. 'SpaceX', 'USSF', 'EU/ESA')",
    "orbit_type": "Orbit regime of this constellation: LEO, MEO, or GEO",
    "total_count": "Total number of satellites tracked in this constellation on this date, across all operational statuses",
    "operational_count": "Number of satellites with altitude within the constellation's defined shell band(s) on this date",
    "median_altitude_km": "Median perigee altitude in km across all satellites in this constellation; useful for detecting constellation-wide altitude drift or shell transitions",
    "median_inclination": "Median orbital inclination in degrees across all satellites in this constellation",
}

# ── Dataset description ──────────────────────────────────────────────────────
DESCRIPTION = """\
Daily census of active satellite constellations with orbital shell classification. \
Tracks satellites from CelesTrak GP data across LEO mega-constellations (Starlink, \
OneWeb, Kuiper, Qianfan, Hulianwang), navigation systems (GPS, Galileo, BeiDou, \
GLONASS), communications fleets (Iridium, Globalstar, ORBCOMM, SES, Intelsat, \
Eutelsat, Telesat), and Earth observation (Planet, Spire).

The satellite constellation landscape is undergoing a historic transformation. Legacy \
GEO communications operators -- each operating dozens of spacecraft at 35,786 km altitude \
-- are being joined by LEO mega-constellations deploying thousands of satellites at \
altitudes below 600 km. Starlink alone now exceeds all other constellations combined in \
satellite count. Meanwhile, China's Qianfan and Hulianwang programs are rapidly deploying \
their own broadband mega-constellations.

This census is valuable for spectrum coordination, space traffic management, competitive \
intelligence in the satellite communications market, and as input to orbital debris \
environment models that depend on accurate population counts by orbit regime.\
"""


# ── Orbital mechanics helpers ────────────────────────────────────

def altitude_from_mean_motion(n: float, ecc: float) -> float:
    """Compute perigee altitude from mean motion (rev/day) and eccentricity."""
    if n <= 0:
        return -1.0
    n_rad = n * 2 * math.pi / 86400.0
    a = (MU / (n_rad ** 2)) ** (1.0 / 3.0)
    return a * (1 - ecc) - R_EARTH


def classify_shell(constellation_id: str, inc: float) -> tuple[int, str]:
    """Assign satellite to a shell within its constellation by inclination."""
    shells = CONSTELLATIONS[constellation_id]["shells"]
    for shell_id, shell in shells.items():
        lo, hi = shell["inc"]
        if lo <= inc < hi:
            return shell_id, shell["name"]
    first_id = next(iter(shells))
    return first_id, shells[first_id]["name"]


def classify_status(alt: float, inc: float, ecc: float,
                    epoch_age_hours: float, mm_dot: float,
                    constellation_id: str) -> str:
    """Classify satellite operational status from GP orbital elements."""
    shells = CONSTELLATIONS[constellation_id]["shells"]
    orbit_type = CONSTELLATIONS[constellation_id]["orbit_type"]

    shell_id, _ = classify_shell(constellation_id, inc)
    band = shells.get(shell_id, {}).get("alt", (0, 100000))
    min_alt, max_alt = band

    if alt < 150:
        return "decayed"
    if epoch_age_hours > 336 and alt < 250:
        return "decayed"

    if orbit_type in ("GEO", "MEO"):
        if ecc > 0.02:
            return "anomalous"
        if min_alt <= alt <= max_alt:
            return "operational"
        return "non-operational"

    if ecc > 0.005:
        return "anomalous"
    if min_alt <= alt <= max_alt:
        return "operational"
    if alt > max_alt:
        return "raising"
    if alt < min_alt:
        if mm_dot < -0.0001:
            return "raising"
        if mm_dot > 0.01 or alt < 300:
            return "deorbiting"
        if alt >= min_alt - 20:
            return "raising"
        return "raising"
    return "unknown"


def fetch_constellation_gp(constellation_id: str, cdef: dict, now: datetime) -> list[dict]:
    """Fetch GP data for one constellation from CelesTrak and return row dicts."""
    group = cdef["group"]
    url = GP_URL.format(group=group)

    records = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            records = resp.json()
            break
        except Exception as e:
            if attempt < MAX_RETRIES:
                wait = attempt * 2
                print(f"  WARNING: {constellation_id} attempt {attempt}/{MAX_RETRIES}: {e}, retrying in {wait}s...")
                time.sleep(wait)
            else:
                print(f"  WARNING: {constellation_id} ({group}): {e} (gave up after {MAX_RETRIES} attempts)")
                return []

    if not records:
        return []

    rows = []
    for r in records:
        norad_id = r["NORAD_CAT_ID"]
        name = r.get("OBJECT_NAME", "").strip()
        epoch_str = r["EPOCH"]
        if epoch_str.endswith("Z"):
            epoch_str = epoch_str[:-1] + "+00:00"
        epoch = datetime.fromisoformat(epoch_str)
        if epoch.tzinfo is None:
            epoch = epoch.replace(tzinfo=timezone.utc)

        inc = r["INCLINATION"]
        ecc = r["ECCENTRICITY"]
        mm = r["MEAN_MOTION"]
        mm_dot = r["MEAN_MOTION_DOT"]
        alt = altitude_from_mean_motion(mm, ecc)

        if alt < 0 or alt > 50000:
            continue

        intl = r.get("OBJECT_ID", "")
        launch_year = int(intl[:4]) if intl and intl[:4].isdigit() else 0

        shell_id, shell_name = classify_shell(constellation_id, inc)
        epoch_age_hours = (now - epoch).total_seconds() / 3600
        status = classify_status(alt, inc, ecc, epoch_age_hours, mm_dot, constellation_id)

        rows.append({
            "norad_id": norad_id,
            "name": name,
            "constellation": constellation_id,
            "operator": cdef["operator"],
            "country": cdef["country"],
            "orbit_type": cdef["orbit_type"],
            "shell_id": shell_id,
            "shell_name": shell_name,
            "altitude_km": round(alt, 2),
            "inclination": round(inc, 4),
            "eccentricity": ecc,
            "mean_motion": mm,
            "status": status,
            "launch_year": launch_year,
            "epoch_utc": epoch,
        })

    return rows


# ── Main pipeline ────────────────────────────────────────────────────

def main():
    now = datetime.now(timezone.utc)
    today = pd.Timestamp(now.strftime("%Y-%m-%d"))

    all_rows = []
    seen_norad_ids = set()

    print(f"Fetching {len(CONSTELLATIONS)} constellations from CelesTrak...")

    for cid, cdef in CONSTELLATIONS.items():
        rows = fetch_constellation_gp(cid, cdef, now)
        new_rows = []
        for r in rows:
            if r["norad_id"] not in seen_norad_ids:
                seen_norad_ids.add(r["norad_id"])
                new_rows.append(r)
        all_rows.extend(new_rows)
        print(f"  {cid:20s} {len(new_rows):6,} satellites")
        time.sleep(FETCH_DELAY)

    df = pd.DataFrame(all_rows)
    if df.empty:
        print("::error::No satellites fetched from any constellation — CelesTrak appears fully unreachable. Aborting.")
        sys.exit(1)
    df["norad_id"] = df["norad_id"].astype("int32")
    n_constellations = df["constellation"].nunique()
    print(f"\nTotal: {len(df):,} satellites across {n_constellations} constellations")

    # Build daily_snapshots: per-constellation aggregates
    daily_rows = []
    for cid in sorted(df["constellation"].unique()):
        cdf = df[df["constellation"] == cid]
        cdef = CONSTELLATIONS.get(cid, {})
        daily_rows.append({
            "date": today,
            "constellation": cid,
            "operator": cdef.get("operator", "Unknown"),
            "orbit_type": cdef.get("orbit_type", "Unknown"),
            "total_count": len(cdf),
            "operational_count": int((cdf["status"] == "operational").sum()),
            "median_altitude_km": round(cdf["altitude_km"].median(), 2),
            "median_inclination": round(cdf["inclination"].median(), 4),
        })
    df_today = pd.DataFrame(daily_rows)

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Constellation Census",
        description=DESCRIPTION,
        tags=["open-data", "space", "satellites", "constellation", "orbital-mechanics",
              "tle", "norad", "starlink", "oneweb", "kuiper", "gps", "galileo",
              "earth-observation", "tabular-data", "parquet"],
        source_url="https://celestrak.org/",
        license="other",
        license_name="celestrak-usage-policy",
        license_link="https://celestrak.org/usage-policy.php",
        task_categories=["tabular-classification", "time-series-forecasting"],
        update_schedule="Daily at 09:00 UTC via GitHub Actions",
        collection_url="https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994",
        banner={
            "url": "https://images-assets.nasa.gov/image/iss071e439624/iss071e439624~medium.jpg",
            "alt": "An orbital sunrise illuminates the Earth's atmosphere, seen from the ISS",
            "credit": "NASA",
        },
        related_datasets=[
            "juliensimon/starlink-fleet-data",
            "juliensimon/space-track-satcat",
            "juliensimon/space-track-tle-history",
            "juliensimon/space-launch-log",
        ],
    ) as p:
        # Download existing daily_snapshots and append today
        df_existing_daily = p.download_existing("daily_snapshots.parquet")

        if df_existing_daily is None or len(df_existing_daily) < 10:
            print("::error::daily_snapshots.parquet not found or too small -- aborting to protect historical data")
            sys.exit(1)

        df_existing_daily["date"] = pd.to_datetime(df_existing_daily["date"])
        df_daily = p.append_by_date(df_existing_daily, df_today, date_col="date", min_existing=10)
        print(f"  daily_snapshots: appended {today} ({len(df_daily):,} total rows)")

        # Write both parquet files to data_dir
        write_parquet(df, p.data_dir / "latest_satellites.parquet")
        write_parquet(df_daily, p.data_dir / "daily_snapshots.parquet")

        # ── Stats for README ─────────────────────────────────────────────
        total = len(df)
        operational = int((df["status"] == "operational").sum())
        top = df.groupby("constellation")["norad_id"].count().sort_values(ascending=False).head(5)
        top_str = ", ".join(f"{c} ({n:,})" for c, n in top.items())
        daily_count = len(df_daily)
        d_min = df_daily["date"].min().strftime("%Y-%m-%d")
        d_max = df_daily["date"].max().strftime("%Y-%m-%d")

        quick_stats = f"""\
- **{total:,}** satellites across **{n_constellations}** constellations
- **{operational:,}** operational
- Top constellations: {top_str}
- **{daily_count:,}** daily snapshot rows ({d_min} to {d_max})"""

        usage = """\
```python
from datasets import load_dataset

# Per-satellite data
ds = load_dataset("juliensimon/constellation-census", "latest_satellites", split="train")
df = ds.to_pandas()

# Constellation sizes
sizes = df.groupby("constellation")["norad_id"].count().sort_values(ascending=False)
print(sizes)

# Daily growth trends
daily = load_dataset("juliensimon/constellation-census", "daily_snapshots", split="train")
df_daily = daily.to_pandas()
starlink_growth = df_daily[df_daily["constellation"] == "starlink"][["date", "total_count"]]

# Altitude distribution by orbit type
import matplotlib.pyplot as plt
for ot in ["LEO", "MEO", "GEO"]:
    sub = df[df["orbit_type"] == ot]
    plt.hist(sub["altitude_km"], bins=50, alpha=0.6, label=ot)
plt.xlabel("Altitude (km)")
plt.ylabel("Satellite Count")
plt.title("Satellite Altitude Distribution by Orbit Type")
plt.legend()
plt.show()
```"""

        # Publish latest_satellites as the main config
        # (daily_snapshots.parquet already written above, will be included in upload)
        p.publish(
            df,
            filename="latest_satellites.parquet",
            min_rows=5000,
            expected_columns=["norad_id", "name", "constellation", "altitude_km",
                              "inclination", "status", "shell_id"],
            critical_columns=["norad_id", "altitude_km", "constellation"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=(
                f"Update constellation census: {total:,} satellites "
                f"({operational:,} operational) across {n_constellations} constellations"
            ),
        )
    print("Done.")


if __name__ == "__main__":
    main()
