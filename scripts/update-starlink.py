#!/usr/bin/env python3
"""Fetch latest Starlink TLEs from CelesTrak, classify, aggregate, and upload to HF.

This is a lightweight daily updater -- it fetches the current constellation snapshot,
not historical data. For historical backfill, use the bulk ingestion scripts in
the starlink-viz repo.

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

CELESTRAK_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=json"
HF_REPO = "juliensimon/starlink-fleet-data"

MU = 398600.4418
R_EARTH = 6371.0

SHELL_NAMES = {
    0: "Shell 1 (33° / 328km)",
    1: "Shell 2 (43° / 340km)",
    2: "Shell 3 (53° / 550km)",
    3: "Shell 4 (70° / 570km)",
    4: "Shell 5 (97.6° / 560km)",
}

SHELL_ALT_BANDS = {
    0: (460, 570),
    1: (460, 570),
    2: (460, 570),
    3: (460, 910),
    4: (460, 600),
}

# ── Column descriptions ────────────────────────────────────────────
COLUMN_DAILY_DESCRIPTIONS = {
    "date": "UTC date of the daily snapshot; one set of rows per date per shell",
    "shell_id": "Integer shell identifier (0-4); maps to inclination bands: 0=33 deg, 1=43 deg, 2=53 deg, 3=70 deg, 4=97.6 deg",
    "shell_name": "Human-readable shell label encoding inclination and target altitude, e.g. 'Shell 3 (53 deg / 550km)'",
    "total_count": "Total number of Starlink objects tracked in this shell on this date, including all statuses",
    "operational_count": "Satellites with perigee altitude within the shell's operational band (typically 460-570 km depending on shell)",
    "raising_count": "Satellites currently maneuvering toward their target shell altitude via Hall-effect ion thrusters",
    "deorbiting_count": "Satellites in active controlled deorbit below their shell band with strong positive mean_motion_dot, or below 300 km",
    "isl_operational_count": "Operational satellites equipped with inter-satellite laser links (ISL); ISL-capable units were deployed from 2022 onward depending on shell",
    "new_launches": "Reserved for future use; currently always 0",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Daily health snapshots of the SpaceX Starlink constellation, derived from CelesTrak \
GP (General Perturbations) data. Tracks satellite count, orbital shells, operational \
status, and ISL capability across five inclination-based shells.

Starlink is the largest satellite constellation ever built, representing a fundamental \
shift in how broadband internet is delivered globally. SpaceX deploys satellites into \
five distinct orbital shells, each defined by its inclination and target altitude. The \
constellation operates in low Earth orbit (LEO) at altitudes between 328 km and 570 km, \
where orbital periods of roughly 90 minutes mean each satellite circles the Earth about \
16 times per day.

Understanding constellation health requires tracking each satellite through its lifecycle: \
initial deployment to a parking orbit, orbit raising via Hall-effect ion thrusters, \
operational service at target altitude, and eventual controlled deorbit. The mean motion \
derivative serves as a reliable proxy for whether a satellite is actively thrusting upward \
or decaying. The inter-satellite laser link (ISL) capability, rolled out starting in 2022, \
enables direct satellite-to-satellite routing without ground relay.\
"""


# ── Orbital mechanics helpers ────────────────────────────────────────────

def _fetch_celestrak(url: str, retries: int = 4, timeout: int = 60) -> list:
    """Fetch JSON from CelesTrak with exponential backoff (1s, 2s, 4s delays)."""
    last_exc: Exception = RuntimeError("no attempts made")
    for attempt in range(retries):
        if attempt > 0:
            wait = 2 ** (attempt - 1)
            print(f"  CelesTrak retry {attempt}/{retries - 1} in {wait}s...")
            time.sleep(wait)
        try:
            resp = requests.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            last_exc = e
            print(f"  CelesTrak fetch error (attempt {attempt + 1}): {e}")
    raise last_exc


def altitude_from_mean_motion(n: float, ecc: float) -> float:
    if n <= 0:
        return -1.0
    n_rad = n * 2 * math.pi / 86400.0
    a = (MU / (n_rad ** 2)) ** (1.0 / 3.0)
    return a * (1 - ecc) - R_EARTH


def get_shell_id(inc: float) -> int:
    if inc < 38:
        return 0
    if inc < 48:
        return 1
    if inc < 60:
        return 2
    if inc < 80:
        return 3
    return 4


def classify_status(
    alt: float, inc: float, ecc: float,
    epoch_age_hours: float, mm_dot: float,
) -> str:
    """Single-snapshot status classification."""
    shell_id = get_shell_id(inc)
    band = SHELL_ALT_BANDS.get(shell_id, (0, 0))
    min_alt, max_alt = band

    if alt < 150:
        return "decayed"
    if epoch_age_hours > 336 and alt < 250:
        return "decayed"
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


def is_isl_capable(inc: float, launch_year: int) -> bool:
    shell = get_shell_id(inc)
    if shell == 4:
        return launch_year >= 2022
    if shell == 2:
        return launch_year >= 2022
    if shell == 3:
        return launch_year >= 2022
    if shell == 1:
        return launch_year >= 2023
    if shell == 0:
        return launch_year >= 2024
    return False


# ── Main pipeline ────────────────────────────────────────────────────

def main():
    print("Fetching Starlink TLEs from CelesTrak...")
    records = _fetch_celestrak(CELESTRAK_URL)
    print(f"  {len(records):,} satellites")

    now = datetime.now(timezone.utc)
    rows = []

    for r in records:
        name = r.get("OBJECT_NAME", "")
        if not name.startswith("STARLINK"):
            continue

        norad_id = r["NORAD_CAT_ID"]
        epoch_str = r["EPOCH"]
        if epoch_str.endswith("Z"):
            epoch_str = epoch_str[:-1] + "+00:00"
        epoch = datetime.fromisoformat(epoch_str)
        if epoch.tzinfo is None:
            epoch = epoch.replace(tzinfo=timezone.utc)
        inc = r["INCLINATION"]
        ecc = r["ECCENTRICITY"]
        mm = r["MEAN_MOTION"]
        alt = altitude_from_mean_motion(mm, ecc)

        if alt < 0 or alt > 2000:
            continue

        intl = r.get("OBJECT_ID", "")
        launch_year = int(intl[:4]) if intl and intl[:4].isdigit() else 0

        shell_id = get_shell_id(inc)
        mm_dot = r["MEAN_MOTION_DOT"]
        epoch_age_hours = (now - epoch).total_seconds() / 3600

        status = classify_status(alt, inc, ecc, epoch_age_hours, mm_dot)

        rows.append({
            "norad_id": norad_id,
            "name": name,
            "epoch_utc": epoch,
            "inclination": round(inc, 4),
            "raan": round(r["RA_OF_ASC_NODE"], 4),
            "eccentricity": ecc,
            "mean_motion": mm,
            "mean_motion_dot": mm_dot,
            "altitude_km": round(alt, 2),
            "launch_year": launch_year,
            "shell_id": shell_id,
            "shell_name": SHELL_NAMES.get(shell_id, "Unknown"),
            "status": status,
            "is_isl_capable": is_isl_capable(inc, launch_year),
        })

    df = pd.DataFrame(rows)
    print(f"  {len(df):,} Starlink satellites processed")

    # Build latest_satellites
    df_latest = df.sort_values("epoch_utc").drop_duplicates("norad_id", keep="last")

    # Build daily_snapshots: per-shell aggregates for today
    today = pd.Timestamp(now.strftime("%Y-%m-%d"))
    daily_rows = []
    for sid in sorted(df_latest["shell_id"].unique()):
        shell = df_latest[df_latest["shell_id"] == sid]
        daily_rows.append({
            "date": today,
            "shell_id": int(sid),
            "shell_name": SHELL_NAMES.get(int(sid), "Unknown"),
            "total_count": len(shell),
            "operational_count": int((shell["status"] == "operational").sum()),
            "raising_count": int((shell["status"] == "raising").sum()),
            "deorbiting_count": int((shell["status"] == "deorbiting").sum()),
            "isl_operational_count": int((shell["is_isl_capable"] & (shell["status"] == "operational")).sum()),
            "new_launches": 0,
        })
    df_today = pd.DataFrame(daily_rows)

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Starlink Constellation Fleet Data",
        description=DESCRIPTION,
        tags=["space", "starlink", "satellites", "orbital-mechanics", "tle",
              "spacex", "constellation", "open-data", "norad", "leo",
              "mega-constellation", "tabular-data", "parquet"],
        source_url="https://celestrak.org/",
        license="other",
        license_name="celestrak-usage-policy",
        license_link="https://celestrak.org/usage-policy.php",
        task_categories=["time-series-forecasting", "tabular-classification"],
        update_schedule="Daily at 08:00 UTC via GitHub Actions",
        collection_url="https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994",
        banner={
            "url": "https://images-assets.nasa.gov/image/iss071e439624/iss071e439624~medium.jpg",
            "alt": "Orbital sunrise illuminating Earth's atmosphere, seen from the ISS",
            "credit": "NASA",
        },
        related_datasets=[
            "juliensimon/space-track-tle-history",
            "juliensimon/space-track-satcat",
            "juliensimon/space-launch-log",
            "juliensimon/starlink-ground-stations",
        ],
    ) as p:
        # Download existing daily_snapshots and append today
        df_existing_daily = p.download_existing("daily_snapshots.parquet")

        if df_existing_daily is None or len(df_existing_daily) < 100:
            print("::error::daily_snapshots.parquet not found or too small -- aborting to protect historical data")
            sys.exit(1)

        df_existing_daily["date"] = pd.to_datetime(df_existing_daily["date"])
        df_daily = p.append_by_date(df_existing_daily, df_today, date_col="date", min_existing=100)
        print(f"  daily_snapshots: appended {today} ({len(df_daily):,} total rows)")

        # Write daily_snapshots parquet to data_dir
        write_parquet(df_daily, p.data_dir / "daily_snapshots.parquet")

        active = len(df_latest[df_latest["status"] == "operational"])
        raising = int((df_latest["status"] == "raising").sum())
        deorbiting = int((df_latest["status"] == "deorbiting").sum())
        isl_count = int(df_latest["is_isl_capable"].sum())
        print(f"  {active:,} operational, {len(df_latest):,} total")

        # ── Stats for README ────────────────────────────────────────────
        total = len(df_latest)
        daily_rows_count = len(df_daily)
        date_range_start = df_daily["date"].min().strftime("%Y-%m-%d")
        date_range_end = df_daily["date"].max().strftime("%Y-%m-%d")

        quick_stats = f"""\
- **{total:,}** Starlink satellites tracked
- **{active:,}** operational, **{raising:,}** raising, **{deorbiting:,}** deorbiting
- **{isl_count:,}** ISL-capable satellites
- **{daily_rows_count:,}** daily snapshot rows ({date_range_start} to {date_range_end})"""

        usage = f"""\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/starlink-fleet-data", "daily_snapshots", split="train")
df = ds.to_pandas()

# Constellation growth over time
growth = df.groupby("date")["operational_count"].sum()
print(growth.tail(10))

# Per-shell fill rates
latest = df[df["date"] == df["date"].max()]
for _, row in latest.iterrows():
    print(f"{{row['shell_name']}}: {{row['operational_count']}} / {{row['total_count']}}")

# Plot operational growth by shell
import matplotlib.pyplot as plt
for sid in sorted(df["shell_id"].unique()):
    shell = df[df["shell_id"] == sid]
    plt.plot(shell["date"], shell["operational_count"], label=shell["shell_name"].iloc[0])
plt.xlabel("Date")
plt.ylabel("Operational Satellites")
plt.title("Starlink Constellation Growth by Shell")
plt.legend()
plt.show()
```"""

        p.publish(
            df_daily,
            filename="daily_snapshots.parquet",
            min_rows=100,
            expected_columns=["date", "shell_id", "total_count", "operational_count"],
            critical_columns=["date", "shell_id", "total_count"],
            column_descriptions=COLUMN_DAILY_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=(
                f"Update Starlink fleet: {total:,} satellites "
                f"({active:,} operational, {raising:,} raising, "
                f"{deorbiting:,} deorbiting)"
            ),
        )
    print("Done.")


if __name__ == "__main__":
    main()
